"""PostgreSQL 方言测试 — 使用 mock 连接，无需真实数据库"""

from unittest.mock import MagicMock

import pytest

from apiscout.core.db_scanner.dialect.postgresql import PostgreSQLDialect


# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------

def _mock_cursor(rows, description=None):
    """构造一个返回固定数据的 mock cursor。"""
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    cursor.description = description
    # 支持 with conn.cursor() as cur: 语法
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    return cursor


def _mock_conn(cursor):
    """构造一个持有固定 cursor 的 mock 连接。"""
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


# ---------------------------------------------------------------------------
# 固定数据
# ---------------------------------------------------------------------------

DIALECT = PostgreSQLDialect()


# ---------------------------------------------------------------------------
# test_get_tables
# ---------------------------------------------------------------------------

class TestGetTables:
    """get_tables() — information_schema.tables + pg_stat + obj_description"""

    def test_returns_two_tables(self):
        """模拟 2 行数据，验证解析结果字段完整。"""
        rows = [
            ("public", "orders", "订单主表", 1024),
            ("public", "products", None, 512),
        ]
        cursor = _mock_cursor(rows)
        conn = _mock_conn(cursor)

        result = DIALECT.get_tables(conn)

        assert len(result) == 2

    def test_table_fields(self):
        """验证返回字典包含 schema / name / comment / row_count 四个键。"""
        rows = [
            ("public", "orders", "订单主表", 1024),
        ]
        cursor = _mock_cursor(rows)
        conn = _mock_conn(cursor)

        result = DIALECT.get_tables(conn)
        item = result[0]

        assert item["schema"] == "public"
        assert item["name"] == "orders"
        assert item["comment"] == "订单主表"
        assert item["row_count"] == 1024

    def test_null_comment_stays_none(self):
        """comment 为 NULL 时，返回 None 而不是字符串 'None'。"""
        rows = [
            ("public", "products", None, 512),
        ]
        cursor = _mock_cursor(rows)
        conn = _mock_conn(cursor)

        result = DIALECT.get_tables(conn)
        assert result[0]["comment"] is None


# ---------------------------------------------------------------------------
# test_get_columns
# ---------------------------------------------------------------------------

class TestGetColumns:
    """get_columns() — information_schema.columns + col_description + PK 检测"""

    def _make_rows(self):
        """id(int4,PK), name(varchar,NOT NULL), status(boolean,nullable)"""
        return [
            # name, data_type, nullable, default, comment, max_len, num_prec, ordinal, is_pk
            ("id",     "int4",    "NO",  None,   "主键ID", None, 32, 1, True),
            ("name",   "varchar", "NO",  None,   "姓名",   255,  None, 2, False),
            ("status", "boolean", "YES", "true", None,     None, None, 3, False),
        ]

    def test_returns_all_columns(self):
        rows = self._make_rows()
        cursor = _mock_cursor(rows)
        conn = _mock_conn(cursor)

        result = DIALECT.get_columns(conn, "users", "public")
        assert len(result) == 3

    def test_id_column(self):
        """id: int4 → normalized integer, is_primary_key=True"""
        rows = self._make_rows()
        cursor = _mock_cursor(rows)
        conn = _mock_conn(cursor)

        result = DIALECT.get_columns(conn, "users", "public")
        id_col = result[0]

        assert id_col["name"] == "id"
        assert id_col["data_type"] == "int4"
        assert id_col["normalized_type"] == "integer"
        assert id_col["is_primary_key"] is True
        assert id_col["nullable"] is False

    def test_name_column(self):
        """name: varchar → normalized string, not PK"""
        rows = self._make_rows()
        cursor = _mock_cursor(rows)
        conn = _mock_conn(cursor)

        result = DIALECT.get_columns(conn, "users", "public")
        name_col = result[1]

        assert name_col["name"] == "name"
        assert name_col["normalized_type"] == "string"
        assert name_col["is_primary_key"] is False
        assert name_col["max_length"] == 255

    def test_status_column(self):
        """status: boolean → normalized boolean, nullable=True, has default"""
        rows = self._make_rows()
        cursor = _mock_cursor(rows)
        conn = _mock_conn(cursor)

        result = DIALECT.get_columns(conn, "users", "public")
        status_col = result[2]

        assert status_col["normalized_type"] == "boolean"
        assert status_col["nullable"] is True
        assert status_col["default"] == "true"


# ---------------------------------------------------------------------------
# test_get_foreign_keys
# ---------------------------------------------------------------------------

class TestGetForeignKeys:
    """get_foreign_keys() — information_schema constraint 查询"""

    def test_single_fk(self):
        """模拟 1 行外键，验证全部字段解析正确。"""
        rows = [
            (
                "fk_orders_customer",  # constraint_name
                "public",              # source_schema
                "orders",              # source_table
                "customer_id",         # source_column
                "public",              # target_schema
                "customers",           # target_table
                "id",                  # target_column
            )
        ]
        cursor = _mock_cursor(rows)
        conn = _mock_conn(cursor)

        result = DIALECT.get_foreign_keys(conn)

        assert len(result) == 1
        fk = result[0]
        assert fk["constraint_name"] == "fk_orders_customer"
        assert fk["source_schema"] == "public"
        assert fk["source_table"] == "orders"
        assert fk["source_column"] == "customer_id"
        assert fk["target_schema"] == "public"
        assert fk["target_table"] == "customers"
        assert fk["target_column"] == "id"

    def test_empty_result(self):
        """无外键时返回空列表。"""
        cursor = _mock_cursor([])
        conn = _mock_conn(cursor)

        result = DIALECT.get_foreign_keys(conn)
        assert result == []


# ---------------------------------------------------------------------------
# test_count_distinct
# ---------------------------------------------------------------------------

class TestCountDistinct:
    """count_distinct() — SELECT COUNT(DISTINCT col)"""

    def test_returns_int(self):
        cursor = _mock_cursor([(5,)])
        conn = _mock_conn(cursor)

        result = DIALECT.count_distinct(conn, "orders", "public", "status")
        assert result == 5
        assert isinstance(result, int)

    def test_zero_distinct(self):
        cursor = _mock_cursor([(0,)])
        conn = _mock_conn(cursor)

        result = DIALECT.count_distinct(conn, "empty_table", "public", "col")
        assert result == 0


# ---------------------------------------------------------------------------
# test_get_enum_values
# ---------------------------------------------------------------------------

class TestGetEnumValues:
    """get_enum_values() — GROUP BY + COUNT，按频次倒序"""

    def test_three_values(self):
        rows = [
            ("active",   80),
            ("inactive", 15),
            ("pending",   5),
        ]
        cursor = _mock_cursor(rows)
        conn = _mock_conn(cursor)

        result = DIALECT.get_enum_values(conn, "users", "public", "status")

        assert len(result) == 3
        assert result[0] == {"value": "active",   "count": 80}
        assert result[1] == {"value": "inactive", "count": 15}
        assert result[2] == {"value": "pending",  "count": 5}

    def test_none_value_stays_none(self):
        """NULL 枚举值应保留 None，不转为字符串 'None'。"""
        rows = [
            (None, 10),
            ("ok", 5),
        ]
        cursor = _mock_cursor(rows)
        conn = _mock_conn(cursor)

        result = DIALECT.get_enum_values(conn, "t", "public", "col")
        assert result[0]["value"] is None


# ---------------------------------------------------------------------------
# test_sample_rows
# ---------------------------------------------------------------------------

class TestSampleRows:
    """sample_rows() — SELECT * ORDER BY RANDOM() LIMIT N"""

    def _make_description(self, names):
        """模拟 cursor.description: 每项是 (列名, ...) 的元组。"""
        return [(name, None, None, None, None, None, None) for name in names]

    def test_returns_dicts(self):
        """返回结果是 dict 列表。"""
        desc = self._make_description(["Id", "Name", "Status"])
        rows = [
            (1, "Alice", "active"),
            (2, "Bob",   "inactive"),
        ]
        cursor = _mock_cursor(rows, description=desc)
        conn = _mock_conn(cursor)

        result = DIALECT.sample_rows(conn, "users", "public", limit=20)

        assert len(result) == 2
        assert isinstance(result[0], dict)

    def test_column_names_lowercase(self):
        """列名必须转为小写。"""
        desc = self._make_description(["Id", "UserName", "CreatedAt"])
        rows = [(1, "Alice", "2026-01-01")]
        cursor = _mock_cursor(rows, description=desc)
        conn = _mock_conn(cursor)

        result = DIALECT.sample_rows(conn, "users", "public")

        assert "id" in result[0]
        assert "username" in result[0]
        assert "createdat" in result[0]

    def test_values_correct(self):
        """验证值与列名正确对应。"""
        desc = self._make_description(["id", "name"])
        rows = [(42, "Charlie")]
        cursor = _mock_cursor(rows, description=desc)
        conn = _mock_conn(cursor)

        result = DIALECT.sample_rows(conn, "users", "public")

        assert result[0]["id"] == 42
        assert result[0]["name"] == "Charlie"

    def test_empty_table(self):
        """空表返回空列表。"""
        desc = self._make_description(["id"])
        cursor = _mock_cursor([], description=desc)
        conn = _mock_conn(cursor)

        result = DIALECT.sample_rows(conn, "empty", "public")
        assert result == []
