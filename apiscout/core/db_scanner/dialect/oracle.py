"""Oracle 方言实现 — ALL_TABLES / ALL_TAB_COLUMNS / ALL_CONSTRAINTS 查询（Oracle 12c+）"""

from .base import BaseDialect, normalize_type


class OracleDialect(BaseDialect):
    """Oracle 专用方言。

    使用 :param 风格的具名绑定变量（cx_Oracle / python-oracledb 标准）。
    动态拼入标识符时使用双引号转义（Oracle 大小写敏感）。
    Oracle 系统视图返回的列名和标识符默认为大写，统一 lower() 后输出。

    过滤掉 Oracle 内置 schema：SYS / SYSTEM / DBSNMP。
    """

    name = "oracle"

    # 需要过滤的系统 schema（Oracle 的 owner 字段为大写）
    _SYSTEM_SCHEMAS = frozenset({"SYS", "SYSTEM", "DBSNMP"})

    # ------------------------------------------------------------------
    # get_tables
    # ------------------------------------------------------------------

    def get_tables(self, conn) -> list[dict]:
        """查询所有用户表：ALL_TABLES JOIN ALL_TAB_COMMENTS，含注释和行数估算。

        NUM_ROWS 是 ANALYZE / DBMS_STATS 后的统计估算值。
        过滤掉 Oracle 系统 schema。
        """
        # :1, :2, ... 是 cx_Oracle 的位置绑定风格；或者用 :owner1, :owner2 具名绑定
        # 这里用 IN + 字面量拼接，因为系统 schema 是固定常量，无注入风险
        system_list = ", ".join(f"'{s}'" for s in self._SYSTEM_SCHEMAS)
        sql = f"""
            SELECT
                t.OWNER         AS schema_name,
                t.TABLE_NAME    AS table_name,
                c.COMMENTS      AS table_comment,
                t.NUM_ROWS      AS row_count
            FROM ALL_TABLES t
            LEFT JOIN ALL_TAB_COMMENTS c
                   ON c.OWNER      = t.OWNER
                  AND c.TABLE_NAME = t.TABLE_NAME
                  AND c.TABLE_TYPE = 'TABLE'
            WHERE t.OWNER NOT IN ({system_list})
            ORDER BY t.OWNER, t.TABLE_NAME
        """
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        result = []
        for row in rows:
            schema, name, comment, row_count = row
            result.append({
                "schema":    schema.lower() if schema else schema,
                "name":      name.lower() if name else name,
                "comment":   comment or None,
                "row_count": int(row_count) if row_count is not None else None,
            })
        return result

    # ------------------------------------------------------------------
    # get_columns
    # ------------------------------------------------------------------

    def get_columns(self, conn, table_name: str, table_schema: str) -> list[dict]:
        """查询指定表的列元数据，含注释和主键标记。

        PK 检测：通过 ALL_CONSTRAINTS（CONSTRAINT_TYPE='P'）JOIN ALL_CONS_COLUMNS 获取。
        Oracle 标识符大写存储，返回时统一 lower()。
        """
        # Oracle 表名/schema 传入需要大写（系统视图按大写存储）
        upper_schema = table_schema.upper()
        upper_table  = table_name.upper()

        sql = """
            SELECT
                col.COLUMN_NAME,
                col.DATA_TYPE,
                col.NULLABLE,
                col.DATA_DEFAULT,
                com.COMMENTS        AS column_comment,
                col.CHAR_LENGTH,
                col.DATA_PRECISION,
                col.COLUMN_ID,
                CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS is_primary_key
            FROM ALL_TAB_COLUMNS col
            LEFT JOIN ALL_COL_COMMENTS com
                   ON com.OWNER       = col.OWNER
                  AND com.TABLE_NAME  = col.TABLE_NAME
                  AND com.COLUMN_NAME = col.COLUMN_NAME
            LEFT JOIN (
                SELECT cc.COLUMN_NAME
                FROM ALL_CONSTRAINTS  con
                JOIN ALL_CONS_COLUMNS cc
                     ON cc.OWNER           = con.OWNER
                    AND cc.CONSTRAINT_NAME = con.CONSTRAINT_NAME
                WHERE con.CONSTRAINT_TYPE = 'P'
                  AND con.OWNER           = :owner
                  AND con.TABLE_NAME      = :tname
            ) pk ON pk.COLUMN_NAME = col.COLUMN_NAME
            WHERE col.OWNER      = :owner
              AND col.TABLE_NAME = :tname
            ORDER BY col.COLUMN_ID
        """
        with conn.cursor() as cur:
            cur.execute(sql, {"owner": upper_schema, "tname": upper_table})
            rows = cur.fetchall()

        result = []
        for row in rows:
            col_name, data_type, nullable, default, comment, char_len, num_prec, col_id, is_pk = row
            result.append({
                "name":              col_name.lower() if col_name else col_name,
                "data_type":         data_type,
                "normalized_type":   normalize_type(data_type),
                "nullable":          nullable == "Y",
                "default":           str(default).strip() if default is not None else None,
                "comment":           comment or None,
                "max_length":        int(char_len) if char_len is not None else None,
                "numeric_precision": int(num_prec) if num_prec is not None else None,
                "is_primary_key":    bool(is_pk),
            })
        return result

    # ------------------------------------------------------------------
    # get_foreign_keys
    # ------------------------------------------------------------------

    def get_foreign_keys(self, conn) -> list[dict]:
        """查询数据库中所有外键关系。

        通过 ALL_CONSTRAINTS（CONSTRAINT_TYPE='R'）关联源端和目标端 ALL_CONS_COLUMNS。
        Oracle 的 R 类型约束通过 R_OWNER + R_CONSTRAINT_NAME 指向父侧约束，
        需要再 JOIN 一次 ALL_CONS_COLUMNS 取目标列名。
        过滤系统 schema。
        """
        system_list = ", ".join(f"'{s}'" for s in self._SYSTEM_SCHEMAS)
        sql = f"""
            SELECT
                fk.CONSTRAINT_NAME,
                fk.OWNER                AS source_schema,
                fk.TABLE_NAME           AS source_table,
                fk_col.COLUMN_NAME      AS source_column,
                pk.OWNER                AS target_schema,
                pk.TABLE_NAME           AS target_table,
                pk_col.COLUMN_NAME      AS target_column
            FROM ALL_CONSTRAINTS fk
            JOIN ALL_CONS_COLUMNS fk_col
                 ON fk_col.OWNER           = fk.OWNER
                AND fk_col.CONSTRAINT_NAME = fk.CONSTRAINT_NAME
                AND fk_col.POSITION        = 1          -- 仅取第一列，复合 FK 场景简化处理
            JOIN ALL_CONSTRAINTS pk
                 ON pk.OWNER           = fk.R_OWNER
                AND pk.CONSTRAINT_NAME = fk.R_CONSTRAINT_NAME
            JOIN ALL_CONS_COLUMNS pk_col
                 ON pk_col.OWNER           = pk.OWNER
                AND pk_col.CONSTRAINT_NAME = pk.CONSTRAINT_NAME
                AND pk_col.POSITION        = 1
            WHERE fk.CONSTRAINT_TYPE = 'R'
              AND fk.OWNER NOT IN ({system_list})
            ORDER BY fk.CONSTRAINT_NAME
        """
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        result = []
        for row in rows:
            constraint_name, src_schema, src_table, src_col, tgt_schema, tgt_table, tgt_col = row
            result.append({
                "constraint_name": constraint_name.lower() if constraint_name else constraint_name,
                "source_schema":   src_schema.lower() if src_schema else src_schema,
                "source_table":    src_table.lower() if src_table else src_table,
                "source_column":   src_col.lower() if src_col else src_col,
                "target_schema":   tgt_schema.lower() if tgt_schema else tgt_schema,
                "target_table":    tgt_table.lower() if tgt_table else tgt_table,
                "target_column":   tgt_col.lower() if tgt_col else tgt_col,
            })
        return result

    # ------------------------------------------------------------------
    # get_indexes
    # ------------------------------------------------------------------

    def get_indexes(self, conn, table_name: str, table_schema: str) -> list[dict]:
        """查询指定表的索引，从 ALL_INDEXES + ALL_IND_COLUMNS 获取。

        UNIQUENESS = 'UNIQUE' 为唯一索引；INDEX_TYPE = 'IOT - TOP' 或
        与主键约束同名的索引为主键索引（Oracle 主键索引与约束同名）。
        """
        upper_schema = table_schema.upper()
        upper_table  = table_name.upper()

        sql = """
            SELECT
                i.INDEX_NAME,
                LISTAGG(ic.COLUMN_NAME, ',') WITHIN GROUP (ORDER BY ic.COLUMN_POSITION) AS columns,
                CASE WHEN i.UNIQUENESS = 'UNIQUE' THEN 1 ELSE 0 END  AS is_unique,
                CASE WHEN c.CONSTRAINT_TYPE = 'P'  THEN 1 ELSE 0 END AS is_primary
            FROM ALL_INDEXES i
            JOIN ALL_IND_COLUMNS ic
                 ON ic.INDEX_OWNER = i.OWNER
                AND ic.INDEX_NAME  = i.INDEX_NAME
            LEFT JOIN ALL_CONSTRAINTS c
                 ON c.OWNER           = i.OWNER
                AND c.INDEX_NAME      = i.INDEX_NAME
                AND c.CONSTRAINT_TYPE = 'P'
            WHERE i.TABLE_OWNER = :owner
              AND i.TABLE_NAME  = :tname
            GROUP BY i.INDEX_NAME, i.UNIQUENESS, c.CONSTRAINT_TYPE
            ORDER BY i.INDEX_NAME
        """
        with conn.cursor() as cur:
            cur.execute(sql, {"owner": upper_schema, "tname": upper_table})
            rows = cur.fetchall()

        result = []
        for row in rows:
            index_name, columns_str, is_unique, is_primary = row
            columns = columns_str.split(",") if columns_str else []
            result.append({
                "name":       index_name.lower() if index_name else index_name,
                "columns":    [c.lower() for c in columns],
                "is_unique":  bool(is_unique),
                "is_primary": bool(is_primary),
            })
        return result

    # ------------------------------------------------------------------
    # sample_rows
    # ------------------------------------------------------------------

    def sample_rows(self, conn, table_name: str, table_schema: str, limit: int = 20) -> list[dict]:
        """随机采样 N 行，使用 SAMPLE(5) + FETCH FIRST N ROWS ONLY（Oracle 12c+）。

        列名统一转为小写，便于后续 AI 推断。
        双引号转义标识符，Oracle 大小写敏感模式下必须大写传入。
        """
        # Oracle 标识符需大写（未加引号时 Oracle 自动大写）
        safe_schema = table_schema.upper().replace('"', '""')
        safe_table  = table_name.upper().replace('"', '""')

        # SAMPLE(5) 从约 5% 的块中随机采样，比 ORDER BY DBMS_RANDOM.VALUE 快
        sql = (
            f'SELECT * FROM "{safe_schema}"."{safe_table}" '
            f"SAMPLE(5) FETCH FIRST {int(limit)} ROWS ONLY"
        )

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
        safe_schema = table_schema.upper().replace('"', '""')
        safe_table  = table_name.upper().replace('"', '""')
        safe_col    = column_name.upper().replace('"', '""')

        sql = f'SELECT COUNT(DISTINCT "{safe_col}") FROM "{safe_schema}"."{safe_table}"'

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
        Oracle 用 FETCH FIRST N ROWS ONLY 替代 LIMIT。
        """
        safe_schema = table_schema.upper().replace('"', '""')
        safe_table  = table_name.upper().replace('"', '""')
        safe_col    = column_name.upper().replace('"', '""')

        sql = (
            f'SELECT "{safe_col}", COUNT(*) AS cnt '
            f'FROM "{safe_schema}"."{safe_table}" '
            f'GROUP BY "{safe_col}" '
            f"ORDER BY cnt DESC "
            f"FETCH FIRST {int(limit)} ROWS ONLY"
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
