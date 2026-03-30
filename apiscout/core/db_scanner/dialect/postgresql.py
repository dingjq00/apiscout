"""PostgreSQL 方言实现 — information_schema + pg_stat_user_tables + pg_catalog 查询"""

from .base import BaseDialect, normalize_type


class PostgreSQLDialect(BaseDialect):
    """PostgreSQL 专用方言。

    使用 psycopg2 风格的 %s 占位符（DBAPI 2.0 标准）。
    动态拼入标识符（表名、列名、schema）时使用双引号转义，防止 SQL 注入。
    """

    name = "postgresql"

    # ------------------------------------------------------------------
    # get_tables
    # ------------------------------------------------------------------

    def get_tables(self, conn) -> list[dict]:
        """查询所有用户表：information_schema.tables + pg_stat 行数估算 + obj_description 注释。

        过滤掉 pg_catalog 和 information_schema 两个系统 schema。
        """
        sql = """
            SELECT
                t.table_schema                         AS schema,
                t.table_name                           AS name,
                obj_description(
                    (quote_ident(t.table_schema) || '.' || quote_ident(t.table_name))::regclass,
                    'pg_class'
                )                                      AS comment,
                COALESCE(s.n_live_tup, 0)              AS row_count
            FROM information_schema.tables t
            LEFT JOIN pg_stat_user_tables s
                   ON s.schemaname = t.table_schema
                  AND s.relname    = t.table_name
            WHERE t.table_type = 'BASE TABLE'
              AND t.table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY t.table_schema, t.table_name
        """
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        result = []
        for row in rows:
            schema, name, comment, row_count = row
            result.append({
                "schema":    schema,
                "name":      name,
                "comment":   comment,  # 可能为 None
                "row_count": row_count,
            })
        return result

    # ------------------------------------------------------------------
    # get_columns
    # ------------------------------------------------------------------

    def get_columns(self, conn, table_name: str, table_schema: str) -> list[dict]:
        """查询指定表的列元数据，含注释和主键标记。

        通过 pg_catalog.col_description 获取列注释，
        通过 key_column_usage JOIN table_constraints 检测主键列。
        """
        sql = """
            SELECT
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default,
                col_description(
                    (quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass,
                    c.ordinal_position
                )                                       AS comment,
                c.character_maximum_length              AS max_length,
                c.numeric_precision,
                c.ordinal_position,
                CASE
                    WHEN kcu.column_name IS NOT NULL THEN TRUE
                    ELSE FALSE
                END                                     AS is_primary_key
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT kcu.column_name
                FROM information_schema.key_column_usage kcu
                JOIN information_schema.table_constraints tc
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema    = kcu.table_schema
                   AND tc.table_name      = kcu.table_name
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND kcu.table_schema   = %s
                  AND kcu.table_name     = %s
            ) kcu ON kcu.column_name = c.column_name
            WHERE c.table_schema = %s
              AND c.table_name   = %s
            ORDER BY c.ordinal_position
        """
        with conn.cursor() as cur:
            cur.execute(sql, (table_schema, table_name, table_schema, table_name))
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
                "comment":           comment,
                "max_length":        max_len,
                "numeric_precision": num_prec,
                "is_primary_key":    bool(is_pk),
            })
        return result

    # ------------------------------------------------------------------
    # get_foreign_keys
    # ------------------------------------------------------------------

    def get_foreign_keys(self, conn) -> list[dict]:
        """查询数据库中所有外键关系。

        通过 information_schema 三表 JOIN：
          table_constraints → key_column_usage → constraint_column_usage
        """
        sql = """
            SELECT
                tc.constraint_name,
                kcu.table_schema      AS source_schema,
                kcu.table_name        AS source_table,
                kcu.column_name       AS source_column,
                ccu.table_schema      AS target_schema,
                ccu.table_name        AS target_table,
                ccu.column_name       AS target_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON kcu.constraint_name = tc.constraint_name
               AND kcu.table_schema    = tc.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            ORDER BY tc.constraint_name
        """
        with conn.cursor() as cur:
            cur.execute(sql)
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
        """查询指定表的索引，从 pg_index + pg_class + pg_attribute 获取。

        返回索引名、列名列表、是否唯一、是否主键。
        """
        sql = """
            SELECT
                i.relname                              AS index_name,
                array_agg(a.attname ORDER BY k.ordinality) AS columns,
                ix.indisunique                         AS is_unique,
                ix.indisprimary                        AS is_primary
            FROM pg_index ix
            JOIN pg_class t  ON t.oid  = ix.indrelid
            JOIN pg_class i  ON i.oid  = ix.indexrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            CROSS JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ordinality)
            JOIN pg_attribute a
                ON a.attrelid = t.oid
               AND a.attnum   = k.attnum
            WHERE t.relname   = %s
              AND n.nspname   = %s
            GROUP BY i.relname, ix.indisunique, ix.indisprimary
            ORDER BY i.relname
        """
        with conn.cursor() as cur:
            cur.execute(sql, (table_name, table_schema))
            rows = cur.fetchall()

        result = []
        for row in rows:
            index_name, columns, is_unique, is_primary = row
            # columns 在真实 PG 中是列表；mock 场景直接用
            result.append({
                "name":       index_name,
                "columns":    list(columns) if columns else [],
                "is_unique":  bool(is_unique),
                "is_primary": bool(is_primary),
            })
        return result

    # ------------------------------------------------------------------
    # sample_rows
    # ------------------------------------------------------------------

    def sample_rows(self, conn, table_name: str, table_schema: str, limit: int = 20) -> list[dict]:
        """随机采样 N 行，使用双引号标识符防注入。

        列名统一转为小写，便于后续 AI 推断。
        """
        # 双引号转义：将标识符内的双引号转义为两个双引号
        safe_schema = table_schema.replace('"', '""')
        safe_table  = table_name.replace('"', '""')

        sql = f'SELECT * FROM "{safe_schema}"."{safe_table}" ORDER BY RANDOM() LIMIT {int(limit)}'

        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            # cursor.description 是 [(name, type_code, ...), ...]
            col_names = [desc[0].lower() for desc in cur.description]

        return [dict(zip(col_names, row)) for row in rows]

    # ------------------------------------------------------------------
    # count_distinct
    # ------------------------------------------------------------------

    def count_distinct(self, conn, table_name: str, table_schema: str, column_name: str) -> int:
        """统计指定列的 distinct 值数，用于判断低基数枚举字段。"""
        safe_schema = table_schema.replace('"', '""')
        safe_table  = table_name.replace('"', '""')
        safe_col    = column_name.replace('"', '""')

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
        """
        safe_schema = table_schema.replace('"', '""')
        safe_table  = table_name.replace('"', '""')
        safe_col    = column_name.replace('"', '""')

        sql = (
            f'SELECT "{safe_col}", COUNT(*) AS cnt '
            f'FROM "{safe_schema}"."{safe_table}" '
            f'GROUP BY "{safe_col}" '
            f'ORDER BY cnt DESC '
            f'LIMIT {int(limit)}'
        )

        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        return [
            {
                "value": row[0],   # None 保持 None，不做 str() 转换
                "count": int(row[1]),
            }
            for row in rows
        ]
