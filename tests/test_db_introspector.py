"""测试 connector.py 和 introspector.py — 连接管理 + 扫描编排"""
import pytest
from unittest.mock import MagicMock, patch, call

from apiscout.core.db_scanner.connector import parse_connection_string
from apiscout.core.db_scanner.models import SchemaReport


# ===========================================================================
# TestParseConnectionString — 连接字符串解析
# ===========================================================================

class TestParseConnectionString:
    """验证各方言连接字符串的解析正确性"""

    def test_postgresql(self):
        """标准 PostgreSQL 连接字符串"""
        result = parse_connection_string("postgresql://user:pass@localhost:5432/eam")
        assert result["dialect"]  == "postgresql"
        assert result["host"]     == "localhost"
        assert result["port"]     == 5432
        assert result["user"]     == "user"
        assert result["password"] == "pass"
        assert result["database"] == "eam"

    def test_mysql(self):
        """MySQL 连接字符串"""
        result = parse_connection_string("mysql://root:123@10.0.0.1:3306/erp")
        assert result["dialect"]  == "mysql"
        assert result["host"]     == "10.0.0.1"
        assert result["port"]     == 3306
        assert result["user"]     == "root"
        assert result["password"] == "123"
        assert result["database"] == "erp"

    def test_oracle(self):
        """Oracle 连接字符串"""
        result = parse_connection_string("oracle://sys:oracle@dbhost:1521/ORCL")
        assert result["dialect"]  == "oracle"
        assert result["host"]     == "dbhost"
        assert result["port"]     == 1521
        assert result["user"]     == "sys"
        assert result["password"] == "oracle"
        assert result["database"] == "ORCL"

    def test_mssql(self):
        """SQL Server 连接字符串"""
        result = parse_connection_string("mssql://sa:Pass@srv:1433/master")
        assert result["dialect"]  == "mssql"
        assert result["host"]     == "srv"
        assert result["port"]     == 1433
        assert result["user"]     == "sa"
        assert result["password"] == "Pass"
        assert result["database"] == "master"

    def test_default_ports_postgresql(self):
        """PostgreSQL 不指定端口时，自动填充默认端口 5432"""
        result = parse_connection_string("postgresql://user:pass@localhost/mydb")
        assert result["port"] == 5432

    def test_default_ports_mysql(self):
        """MySQL 不指定端口时，自动填充默认端口 3306"""
        result = parse_connection_string("mysql://root:pw@10.0.0.2/shop")
        assert result["port"] == 3306

    def test_alias_postgres(self):
        """postgres 别名应归一化为 postgresql"""
        result = parse_connection_string("postgres://u:p@h:5432/db")
        assert result["dialect"] == "postgresql"

    def test_alias_mariadb(self):
        """mariadb 别名应归一化为 mysql"""
        result = parse_connection_string("mariadb://u:p@h:3306/db")
        assert result["dialect"] == "mysql"


# ===========================================================================
# TestScanDatabase — 扫描编排全流程 Mock 测试
# ===========================================================================

class TestScanDatabase:
    """用 Mock 验证 scan_database 的编排逻辑"""

    @patch("apiscout.core.db_scanner.introspector.connect")
    def test_full_scan_mock(self, mock_connect):
        """端到端 Mock 测试：1 张表，2 列，无外键，无索引，验证 SchemaReport 结构"""
        from apiscout.core.db_scanner.introspector import scan_database

        # ---- 构造 mock dialect ----
        mock_dialect = MagicMock()

        # get_tables → 1 张表
        mock_dialect.get_tables.return_value = [
            {
                "name":      "orders",
                "schema":    "public",
                "comment":   "订单表",
                "row_count": 1000,
            }
        ]

        # get_foreign_keys → 无外键
        mock_dialect.get_foreign_keys.return_value = []

        # get_columns → 2 列
        mock_dialect.get_columns.return_value = [
            {
                "name":              "id",
                "data_type":         "bigint",
                "normalized_type":   "integer",
                "nullable":          False,
                "default":           None,
                "comment":           "主键",
                "max_length":        None,
                "numeric_precision": 64,
                "is_primary_key":    True,
            },
            {
                "name":              "status",
                "data_type":         "varchar(20)",
                "normalized_type":   "string",
                "nullable":          True,
                "default":           "PENDING",
                "comment":           "订单状态",
                "max_length":        20,
                "numeric_precision": None,
                "is_primary_key":    False,
            },
        ]

        # get_indexes → 无索引
        mock_dialect.get_indexes.return_value = []

        # count_distinct → 3（用于枚举探测，由 scan_table_samples 调用）
        mock_dialect.count_distinct.return_value = 3

        # get_enum_values → 2 个枚举值
        mock_dialect.get_enum_values.return_value = [
            {"value": "PENDING",  "count": 300},
            {"value": "COMPLETE", "count": 700},
        ]

        # sample_rows → 1 行样本
        mock_dialect.sample_rows.return_value = [
            {"id": 1, "status": "PENDING"}
        ]

        # ---- mock conn ----
        mock_conn = MagicMock()
        mock_connect.return_value = (mock_conn, mock_dialect)

        # ---- 执行扫描 ----
        report = scan_database("postgresql://user:pass@localhost:5432/testdb")

        # ---- 验证返回类型 ----
        assert isinstance(report, SchemaReport)

        # ---- 验证基本字段 ----
        assert report.dialect  == "postgresql"
        assert report.database == "testdb"
        assert report.scanned_at  # 不为空

        # ---- 验证表结构 ----
        assert report.total_tables == 1
        assert report.tables[0].name    == "orders"
        assert report.tables[0].schema  == "public"
        assert report.tables[0].comment == "订单表"
        assert report.tables[0].row_count == 1000

        # ---- 验证列结构 ----
        assert report.total_columns == 2

        id_col = report.tables[0].columns[0]
        assert id_col.name         == "id"
        assert id_col.is_primary_key is True
        assert id_col.enum_values  is None  # PK 列不做枚举探测

        status_col = report.tables[0].columns[1]
        assert status_col.name == "status"
        assert status_col.is_enum_candidate is True
        assert len(status_col.enum_values) == 2

        # ---- 验证样本行 ----
        assert report.tables[0].sample_rows == [{"id": 1, "status": "PENDING"}]

        # ---- 验证索引 ----
        assert report.tables[0].indexes == []

        # ---- 验证外键 ----
        assert report.total_foreign_keys == 0
        assert report.explicit_relations == []

        # ---- 验证 conn.close() 被调用 ----
        mock_conn.close.assert_called_once()

    @patch("apiscout.core.db_scanner.introspector.connect")
    def test_conn_close_called_on_exception(self, mock_connect):
        """即使扫描中途抛异常，conn.close() 也必须被调用"""
        from apiscout.core.db_scanner.introspector import scan_database

        mock_dialect = MagicMock()
        mock_dialect.get_tables.side_effect = RuntimeError("模拟数据库断连")

        mock_conn = MagicMock()
        mock_connect.return_value = (mock_conn, mock_dialect)

        with pytest.raises(RuntimeError, match="模拟数据库断连"):
            scan_database("postgresql://u:p@h:5432/db")

        # 无论异常与否，连接必须关闭
        mock_conn.close.assert_called_once()

    @patch("apiscout.core.db_scanner.introspector.connect")
    def test_explicit_fk_excluded_from_infer(self, mock_connect):
        """外键已覆盖的列不参与推断关系"""
        from apiscout.core.db_scanner.introspector import scan_database

        mock_dialect = MagicMock()

        # 两张表：orders 和 customer
        mock_dialect.get_tables.return_value = [
            {"name": "orders",   "schema": "public", "comment": None, "row_count": 0},
            {"name": "customer", "schema": "public", "comment": None, "row_count": 0},
        ]

        # orders.customer_id 已有外键约束
        mock_dialect.get_foreign_keys.return_value = [
            {
                "constraint_name": "fk_orders_customer",
                "source_table":    "orders",
                "source_column":   "customer_id",
                "target_table":    "customer",
                "target_column":   "id",
            }
        ]

        def _get_columns(conn, table_name, table_schema):
            if table_name == "orders":
                return [
                    {
                        "name": "id", "data_type": "bigint", "normalized_type": "integer",
                        "nullable": False, "default": None, "comment": None,
                        "max_length": None, "numeric_precision": 64, "is_primary_key": True,
                    },
                    {
                        "name": "customer_id", "data_type": "bigint", "normalized_type": "integer",
                        "nullable": True, "default": None, "comment": None,
                        "max_length": None, "numeric_precision": 64, "is_primary_key": False,
                    },
                ]
            # customer 表
            return [
                {
                    "name": "id", "data_type": "bigint", "normalized_type": "integer",
                    "nullable": False, "default": None, "comment": None,
                    "max_length": None, "numeric_precision": 64, "is_primary_key": True,
                },
            ]

        mock_dialect.get_columns.side_effect   = _get_columns
        mock_dialect.get_indexes.return_value  = []
        mock_dialect.count_distinct.return_value = 100  # 高 cardinality，不做枚举
        mock_dialect.sample_rows.return_value  = []

        mock_conn = MagicMock()
        mock_connect.return_value = (mock_conn, mock_dialect)

        report = scan_database("postgresql://u:p@h:5432/db")

        # orders.customer_id 已由外键覆盖，不应出现在推断关系中
        inferred_cols = {
            (r.source_table, r.source_column)
            for r in report.inferred_relations
        }
        assert ("orders", "customer_id") not in inferred_cols

        # 显式外键正确解析
        assert report.total_foreign_keys == 1
        fk = report.explicit_relations[0]
        assert fk.source_table  == "orders"
        assert fk.source_column == "customer_id"
        assert fk.target_table  == "customer"

    @patch("apiscout.core.db_scanner.introspector.connect")
    def test_kwargs_params(self, mock_connect):
        """通过关键字参数（非 conn_str）也能正常扫描"""
        from apiscout.core.db_scanner.introspector import scan_database

        mock_dialect = MagicMock()
        mock_dialect.get_tables.return_value      = []
        mock_dialect.get_foreign_keys.return_value = []

        mock_conn = MagicMock()
        mock_connect.return_value = (mock_conn, mock_dialect)

        report = scan_database(
            host="10.0.0.1",
            port=5432,
            user="admin",
            password="secret",
            database="prod",
            dialect="postgresql",
        )

        assert isinstance(report, SchemaReport)
        assert report.total_tables == 0
        mock_conn.close.assert_called_once()
