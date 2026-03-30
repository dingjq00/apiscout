"""BaseDialect 接口 + 跨方言类型归一化测试"""

import pytest
from apiscout.core.db_scanner.dialect.base import normalize_type, BaseDialect


class TestNormalizeType:
    """测试 normalize_type() 跨方言类型归一化"""

    def test_integer_types(self):
        """各种整数类型 → integer"""
        cases = [
            "int", "int4", "int8", "integer", "bigint", "smallint", "tinyint",
            "serial", "bigserial", "NUMBER(10,0)", "NUMBER(19,0)",
        ]
        for t in cases:
            assert normalize_type(t) == "integer", f"期望 {t!r} → integer，实际 {normalize_type(t)!r}"

    def test_number_types(self):
        """浮点/精确数字类型 → number"""
        cases = [
            "float", "float8", "double", "real",
            "decimal", "numeric", "decimal(10,2)",
            "NUMBER(10,2)", "money",
        ]
        for t in cases:
            assert normalize_type(t) == "number", f"期望 {t!r} → number，实际 {normalize_type(t)!r}"

    def test_string_types(self):
        """各种字符串类型 → string"""
        cases = [
            "varchar", "varchar(255)", "text", "char", "char(10)",
            "VARCHAR2(100)", "nvarchar", "nvarchar(max)", "CLOB", "ntext",
        ]
        for t in cases:
            assert normalize_type(t) == "string", f"期望 {t!r} → string，实际 {normalize_type(t)!r}"

    def test_boolean_types(self):
        """布尔类型 → boolean"""
        cases = ["bool", "boolean", "bit"]
        for t in cases:
            assert normalize_type(t) == "boolean", f"期望 {t!r} → boolean，实际 {normalize_type(t)!r}"

    def test_datetime_types(self):
        """日期时间类型 → date-time"""
        cases = [
            "timestamp", "timestamptz", "datetime", "datetime2",
            "date", "time", "TIMESTAMP WITH TIME ZONE",
        ]
        for t in cases:
            assert normalize_type(t) == "date-time", f"期望 {t!r} → date-time，实际 {normalize_type(t)!r}"

    def test_binary_types(self):
        """二进制类型 → binary"""
        cases = ["bytea", "blob", "varbinary", "binary", "image", "RAW"]
        for t in cases:
            assert normalize_type(t) == "binary", f"期望 {t!r} → binary，实际 {normalize_type(t)!r}"

    def test_json_types(self):
        """JSON 类型 → object"""
        cases = ["json", "jsonb"]
        for t in cases:
            assert normalize_type(t) == "object", f"期望 {t!r} → object，实际 {normalize_type(t)!r}"

    def test_unknown_type(self):
        """未知类型 → string（兜底）"""
        assert normalize_type("geometry") == "string"


class TestBaseDialectIsAbstract:
    """BaseDialect 是抽象基类，不能直接实例化"""

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseDialect()  # type: ignore

    def test_concrete_subclass_must_implement_all_methods(self):
        """实现所有抽象方法后才能实例化"""

        class ConcreteDialect(BaseDialect):
            def get_tables(self, conn):
                return []

            def get_columns(self, conn, table_name, table_schema):
                return []

            def get_foreign_keys(self, conn):
                return []

            def get_indexes(self, conn, table_name, table_schema):
                return []

            def sample_rows(self, conn, table_name, table_schema, limit=20):
                return []

            def count_distinct(self, conn, table_name, table_schema, column_name):
                return 0

            def get_enum_values(self, conn, table_name, table_schema, column_name, limit=50):
                return []

        # 可以实例化
        dialect = ConcreteDialect()
        assert dialect is not None

    def test_partial_subclass_cannot_instantiate(self):
        """只实现部分方法时，仍不能实例化"""

        class PartialDialect(BaseDialect):
            def get_tables(self, conn):
                return []

        with pytest.raises(TypeError):
            PartialDialect()  # type: ignore
