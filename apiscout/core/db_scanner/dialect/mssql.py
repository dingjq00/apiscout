"""MSSQL 方言实现 — INFORMATION_SCHEMA + sys.* 系统视图查询（SQL Server 2012+）"""

from .base import BaseDialect, normalize_type


class MSSQLDialect(BaseDialect):
    """SQL Server 专用方言。

    使用 %s 占位符（pyodbc / pymssql 均支持 DBAPI 2.0 标准）。
    动态拼入标识符时使用方括号转义，防止 SQL 注入。

    过滤掉 SQL Server 内置系统 schema：sys / INFORMATION_SCHEMA。
    """

    name = "mssql"

    # 需要过滤的系统 schema
    _SYSTEM_SCHEMAS = frozenset({"sys", "INFORMATION_SCHEMA"})

    # ------------------------------------------------------------------
    # get_tables
    # ------------------------------------------------------------------

    def get_tables(self, conn) -> list[dict]:
        """查询所有用户表：INFORMATION_SCHEMA.TABLES + sys.extended_properties（注释）+ sys.partitions（行数）。

        表注释存储在 sys.extended_properties，name='MS_Description'，level0type='SCHEMA'，level1type='TABLE'。
        行数取 sys.partitions 中 index_id IN (0,1)（堆表或聚集索引）的 row_count 之和。
        过滤系统 schema。
        """
        placeholders = ", ".join(["%s"] * len(self._SYSTEM_SCHEMAS))
        sql = f"""
            SELECT
                t.TABLE_SCHEMA                             AS schema_name,
                t.TABLE_NAME                               AS table_name,
                ep.value                                   AS table_comment,
                ISNULL(SUM(p.row_count), 0)                AS row_count
            FROM INFORMATION_SCHEMA.TABLES t
            LEFT JOIN sys.extended_properties ep
                   ON ep.major_id      = OBJECT_ID(t.TABLE_SCHEMA + '.' + t.TABLE_NAME)
                  AND ep.minor_id      = 0
                  AND ep.name          = 'MS_Description'
                  AND ep.class         = 1
            LEFT JOIN sys.partitions p
                   ON p.object_id      = OBJECT_ID(t.TABLE_SCHEMA + '.' + t.TABLE_NAME)
                  AND p.index_id      IN (0, 1)
            WHERE t.TABLE_TYPE = 'BASE TABLE'
              AND t.TABLE_SCHEMA NOT IN ({placeholders})
            GROUP BY t.TABLE_SCHEMA, t.TABLE_NAME, ep.value
            ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
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
                "comment":   str(comment) if comment is not None else None,
                "row_count": int(row_count) if row_count is not None else None,
            })
        return result

    # ------------------------------------------------------------------
    # get_columns
    # ------------------------------------------------------------------

    def get_columns(self, conn, table_name: str, table_schema: str) -> list[dict]:
        """查询指定表的列元数据，含注释和主键标记。

        列注释通过 sys.extended_properties（minor_id = sys.columns.column_id）获取。
        PK 检测：通过 INFORMATION_SCHEMA.KEY_COLUMN_USAGE + TABLE_CONSTRAINTS 联查。
        """
        sql = """
            SELECT
                c.COLUMN_NAME,
                c.DATA_TYPE,
                c.IS_NULLABLE,
                c.COLUMN_DEFAULT,
                CAST(ep.value AS NVARCHAR(MAX))            AS column_comment,
                c.CHARACTER_MAXIMUM_LENGTH,
                c.NUMERIC_PRECISION,
                c.ORDINAL_POSITION,
                CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS is_primary_key
            FROM INFORMATION_SCHEMA.COLUMNS c
            LEFT JOIN sys.extended_properties ep
                   ON ep.major_id  = OBJECT_ID(%s + '.' + %s)
                  AND ep.minor_id  = (
                          SELECT sc.column_id
                          FROM sys.columns sc
                          WHERE sc.object_id = OBJECT_ID(%s + '.' + %s)
                            AND sc.name      = c.COLUMN_NAME
                      )
                  AND ep.name      = 'MS_Description'
                  AND ep.class     = 1
            LEFT JOIN (
                SELECT kcu.COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                   AND tc.TABLE_SCHEMA    = kcu.TABLE_SCHEMA
                   AND tc.TABLE_NAME      = kcu.TABLE_NAME
                WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                  AND kcu.TABLE_SCHEMA   = %s
                  AND kcu.TABLE_NAME     = %s
            ) pk ON pk.COLUMN_NAME = c.COLUMN_NAME
            WHERE c.TABLE_SCHEMA = %s
              AND c.TABLE_NAME   = %s
            ORDER BY c.ORDINAL_POSITION
        """
        with conn.cursor() as cur:
            # 占位符顺序：schema+table（for ep subquery x2）, schema+table（for pk）, schema+table（主 WHERE）
            cur.execute(
                sql,
                (
                    table_schema, table_name,   # ep.major_id OBJECT_ID 第一处
                    table_schema, table_name,   # ep.minor_id 子查询
                    table_schema, table_name,   # pk 子查询
                    table_schema, table_name,   # 主 WHERE
                ),
            )
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

        INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS 提供约束名和目标约束名，
        再通过 KEY_COLUMN_USAGE 两次 JOIN 分别取源列和目标列。
        过滤系统 schema。
        """
        placeholders = ", ".join(["%s"] * len(self._SYSTEM_SCHEMAS))
        sql = f"""
            SELECT
                rc.CONSTRAINT_NAME,
                kcu.TABLE_SCHEMA          AS source_schema,
                kcu.TABLE_NAME            AS source_table,
                kcu.COLUMN_NAME           AS source_column,
                kcu2.TABLE_SCHEMA         AS target_schema,
                kcu2.TABLE_NAME           AS target_table,
                kcu2.COLUMN_NAME          AS target_column
            FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                 ON kcu.CONSTRAINT_NAME   = rc.CONSTRAINT_NAME
                AND kcu.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
                 ON kcu2.CONSTRAINT_NAME   = rc.UNIQUE_CONSTRAINT_NAME
                AND kcu2.CONSTRAINT_SCHEMA = rc.UNIQUE_CONSTRAINT_SCHEMA
                AND kcu2.ORDINAL_POSITION  = kcu.ORDINAL_POSITION
            WHERE kcu.TABLE_SCHEMA NOT IN ({placeholders})
            ORDER BY rc.CONSTRAINT_NAME
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
        """查询指定表的索引，从 sys.indexes + sys.index_columns + sys.columns 获取。

        is_primary_key 字段直接来自 sys.indexes。
        is_unique 包含唯一索引和主键索引（主键强制唯一）。
        """
        sql = """
            SELECT
                i.name                                          AS index_name,
                STRING_AGG(c.name, ',') WITHIN GROUP (ORDER BY ic.key_ordinal) AS columns,
                CAST(i.is_unique     AS INT)                   AS is_unique,
                CAST(i.is_primary_key AS INT)                  AS is_primary
            FROM sys.indexes i
            JOIN sys.index_columns ic
                 ON ic.object_id = i.object_id
                AND ic.index_id  = i.index_id
            JOIN sys.columns c
                 ON c.object_id  = i.object_id
                AND c.column_id  = ic.column_id
            WHERE i.object_id = OBJECT_ID(%s + '.' + %s)
              AND i.name IS NOT NULL              -- 排除堆表的 NULL 索引记录
              AND ic.is_included_column = 0       -- 排除 INCLUDE 列，只保留键列
            GROUP BY i.name, i.is_unique, i.is_primary_key
            ORDER BY i.name
        """
        with conn.cursor() as cur:
            cur.execute(sql, (table_schema, table_name))
            rows = cur.fetchall()

        result = []
        for row in rows:
            index_name, columns_str, is_unique, is_primary = row
            # STRING_AGG 返回逗号分隔字符串；pyodbc 有时返回 None（空索引极少见）
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
        """随机采样 N 行，使用 SELECT TOP N + ORDER BY NEWID()，方括号转义标识符。

        列名统一转为小写，便于后续 AI 推断。
        """
        # 方括号转义：将标识符内的 ] 转义为 ]]
        safe_schema = table_schema.replace("]", "]]")
        safe_table  = table_name.replace("]", "]]")

        sql = (
            f"SELECT TOP {int(limit)} * "
            f"FROM [{safe_schema}].[{safe_table}] "
            f"ORDER BY NEWID()"
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
        safe_schema = table_schema.replace("]", "]]")
        safe_table  = table_name.replace("]", "]]")
        safe_col    = column_name.replace("]", "]]")

        sql = f"SELECT COUNT(DISTINCT [{safe_col}]) FROM [{safe_schema}].[{safe_table}]"

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
        SQL Server 使用 SELECT TOP N 替代 LIMIT。
        """
        safe_schema = table_schema.replace("]", "]]")
        safe_table  = table_name.replace("]", "]]")
        safe_col    = column_name.replace("]", "]]")

        sql = (
            f"SELECT TOP {int(limit)} [{safe_col}], COUNT(*) AS cnt "
            f"FROM [{safe_schema}].[{safe_table}] "
            f"GROUP BY [{safe_col}] "
            f"ORDER BY cnt DESC"
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
