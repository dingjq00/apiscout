"""MySQL 方言实现 — information_schema 查询（MySQL 5.7 / 8.0）"""

from .base import BaseDialect, normalize_type


class MySQLDialect(BaseDialect):
    """MySQL 专用方言。

    使用 %s 占位符（DBAPI 2.0 标准，mysqlclient / PyMySQL 均支持）。
    动态拼入标识符时使用反引号转义，防止 SQL 注入。

    过滤掉 MySQL 内置系统库：mysql / information_schema / performance_schema / sys。
    """

    name = "mysql"

    # 需要过滤的系统库
    _SYSTEM_SCHEMAS = frozenset(
        {"mysql", "information_schema", "performance_schema", "sys"}
    )

    # ------------------------------------------------------------------
    # get_tables
    # ------------------------------------------------------------------

    def get_tables(self, conn) -> list[dict]:
        """查询所有用户表：information_schema.tables，含注释和行数估算。

        MySQL 的 TABLE_ROWS 是 InnoDB 的统计估算值，不需要额外 JOIN。
        过滤掉系统库。
        """
        # 把系统库列表拼成 IN 子句占位符
        placeholders = ", ".join(["%s"] * len(self._SYSTEM_SCHEMAS))
        sql = f"""
            SELECT
                TABLE_SCHEMA          AS schema_name,
                TABLE_NAME            AS table_name,
                TABLE_COMMENT         AS table_comment,
                TABLE_ROWS            AS row_count
            FROM information_schema.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
              AND TABLE_SCHEMA NOT IN ({placeholders})
            ORDER BY TABLE_SCHEMA, TABLE_NAME
        """
        with conn.cursor() as cur:
            cur.execute(sql, tuple(self._SYSTEM_SCHEMAS))
            rows = cur.fetchall()

        result = []
        for row in rows:
            schema, name, comment, row_count = row
            result.append({
                "schema":    schema,
                "name":      name,
                "comment":   comment or None,
                "row_count": int(row_count) if row_count is not None else None,
            })
        return result

    # ------------------------------------------------------------------
    # get_columns
    # ------------------------------------------------------------------

    def get_columns(self, conn, table_name: str, table_schema: str) -> list[dict]:
        """查询指定表的列元数据，含注释和主键标记。

        COLUMN_KEY = 'PRI' 表示该列是主键列（MySQL information_schema 原生支持）。
        """
        sql = """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                COLUMN_DEFAULT,
                COLUMN_COMMENT,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                ORDINAL_POSITION,
                CASE WHEN COLUMN_KEY = 'PRI' THEN 1 ELSE 0 END AS is_primary_key
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME   = %s
            ORDER BY ORDINAL_POSITION
        """
        with conn.cursor() as cur:
            cur.execute(sql, (table_schema, table_name))
            rows = cur.fetchall()

        result = []
        for row in rows:
            col_name, data_type, is_nullable, default, comment, max_len, num_prec, ordinal, is_pk = row
            result.append({
                "name":              col_name,
                "data_type":         data_type,
                "normalized_type":   normalize_type(data_type),
                "nullable":          is_nullable == "YES",
                "default":           default,
                "comment":           comment or None,
                "max_length":        int(max_len) if max_len is not None else None,
                "numeric_precision": int(num_prec) if num_prec is not None else None,
                "is_primary_key":    bool(is_pk),
            })
        return result

    # ------------------------------------------------------------------
    # get_foreign_keys
    # ------------------------------------------------------------------

    def get_foreign_keys(self, conn) -> list[dict]:
        """查询数据库中所有外键关系。

        使用 information_schema.KEY_COLUMN_USAGE，
        过滤 REFERENCED_TABLE_NAME IS NOT NULL 即可得到外键列。
        同样过滤系统库。
        """
        placeholders = ", ".join(["%s"] * len(self._SYSTEM_SCHEMAS))
        sql = f"""
            SELECT
                CONSTRAINT_NAME,
                TABLE_SCHEMA          AS source_schema,
                TABLE_NAME            AS source_table,
                COLUMN_NAME           AS source_column,
                REFERENCED_TABLE_SCHEMA  AS target_schema,
                REFERENCED_TABLE_NAME    AS target_table,
                REFERENCED_COLUMN_NAME   AS target_column
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE REFERENCED_TABLE_NAME IS NOT NULL
              AND TABLE_SCHEMA NOT IN ({placeholders})
            ORDER BY CONSTRAINT_NAME
        """
        with conn.cursor() as cur:
            cur.execute(sql, tuple(self._SYSTEM_SCHEMAS))
            rows = cur.fetchall()

        result = []
        for row in rows:
            constraint_name, src_schema, src_table, src_col, tgt_schema, tgt_table, tgt_col = row
            result.append({
                "constraint_name": constraint_name,
                "source_schema":   src_schema,
                "source_table":    src_table,
                "source_column":   src_col,
                "target_schema":   tgt_schema,
                "target_table":    tgt_table,
                "target_column":   tgt_col,
            })
        return result

    # ------------------------------------------------------------------
    # get_indexes
    # ------------------------------------------------------------------

    def get_indexes(self, conn, table_name: str, table_schema: str) -> list[dict]:
        """查询指定表的索引，从 information_schema.STATISTICS 获取。

        STATISTICS 每行对应一个索引列，需要 GROUP BY 聚合成索引级结果。
        NON_UNIQUE = 0 表示唯一索引，INDEX_NAME = 'PRIMARY' 表示主键。
        """
        sql = """
            SELECT
                INDEX_NAME,
                GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') AS columns,
                MAX(CASE WHEN NON_UNIQUE = 0 THEN 1 ELSE 0 END)               AS is_unique,
                MAX(CASE WHEN INDEX_NAME = 'PRIMARY' THEN 1 ELSE 0 END)        AS is_primary
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME   = %s
            GROUP BY INDEX_NAME
            ORDER BY INDEX_NAME
        """
        with conn.cursor() as cur:
            cur.execute(sql, (table_schema, table_name))
            rows = cur.fetchall()

        result = []
        for row in rows:
            index_name, columns_str, is_unique, is_primary = row
            # GROUP_CONCAT 返回逗号分隔字符串，拆分为列表
            columns = columns_str.split(",") if columns_str else []
            result.append({
                "name":       index_name,
                "columns":    columns,
                "is_unique":  bool(is_unique),
                "is_primary": bool(is_primary),
            })
        return result

    # ------------------------------------------------------------------
    # sample_rows
    # ------------------------------------------------------------------

    def sample_rows(self, conn, table_name: str, table_schema: str, limit: int = 20) -> list[dict]:
        """随机采样 N 行，使用反引号标识符，ORDER BY RAND()。

        列名统一转为小写，便于后续 AI 推断。
        """
        # 反引号转义：将标识符内的反引号转义为两个反引号
        safe_schema = table_schema.replace("`", "``")
        safe_table  = table_name.replace("`", "``")

        sql = f"SELECT * FROM `{safe_schema}`.`{safe_table}` ORDER BY RAND() LIMIT {int(limit)}"

        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            col_names = [desc[0].lower() for desc in cur.description]

        return [dict(zip(col_names, row)) for row in rows]

    # ------------------------------------------------------------------
    # count_distinct
    # ------------------------------------------------------------------

    def count_distinct(self, conn, table_name: str, table_schema: str, column_name: str) -> int:
        """统计指定列的 distinct 值数，用于判断低基数枚举字段。"""
        safe_schema = table_schema.replace("`", "``")
        safe_table  = table_name.replace("`", "``")
        safe_col    = column_name.replace("`", "``")

        sql = f"SELECT COUNT(DISTINCT `{safe_col}`) FROM `{safe_schema}`.`{safe_table}`"

        with conn.cursor() as cur:
            cur.execute(sql)
            (count,) = cur.fetchall()[0]
        return int(count)

    # ------------------------------------------------------------------
    # get_enum_values
    # ------------------------------------------------------------------

    def get_enum_values(
        self,
        conn,
        table_name: str,
        table_schema: str,
        column_name: str,
        limit: int = 50,
    ) -> list[dict]:
        """获取低基数列的枚举值及频次，按出现次数倒序排列。

        NULL 值保留为 None，不转字符串。
        """
        safe_schema = table_schema.replace("`", "``")
        safe_table  = table_name.replace("`", "``")
        safe_col    = column_name.replace("`", "``")

        sql = (
            f"SELECT `{safe_col}`, COUNT(*) AS cnt "
            f"FROM `{safe_schema}`.`{safe_table}` "
            f"GROUP BY `{safe_col}` "
            f"ORDER BY cnt DESC "
            f"LIMIT {int(limit)}"
        )

        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        return [
            {
                "value": row[0],
                "count": int(row[1]),
            }
            for row in rows
        ]
