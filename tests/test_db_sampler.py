"""测试 sampler.py — 枚举探测 + 随机采样"""
import pytest
from unittest.mock import MagicMock

from apiscout.core.db_scanner.models import ColumnInfo
from apiscout.core.db_scanner.sampler import scan_table_samples, ENUM_CARDINALITY_THRESHOLD


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_col(name, data_type="varchar(20)", normalized="string", is_pk=False):
    """构造测试用 ColumnInfo"""
    return ColumnInfo(
        name=name,
        data_type=data_type,
        normalized_type=normalized,
        nullable=True,
        default=None,
        comment=None,
        max_length=20,
        numeric_precision=None,
        is_primary_key=is_pk,
        enum_values=None,
    )


def _make_dialect(count_distinct_val=0, enum_values=None, sample_rows=None):
    """构造 Mock dialect"""
    dialect = MagicMock()
    dialect.count_distinct.return_value = count_distinct_val
    dialect.get_enum_values.return_value = enum_values or []
    dialect.sample_rows.return_value = sample_rows or []
    return dialect


# ---------------------------------------------------------------------------
# 测试：低 cardinality → 枚举探测命中
# ---------------------------------------------------------------------------

def test_enum_detected():
    """count_distinct=3 < 50 时，status 列应被标记为枚举候选；id（PK）不应被探测"""
    conn = MagicMock()
    enum_vals = [
        {"value": "ACTIVE", "count": 500},
        {"value": "INACTIVE", "count": 100},
        {"value": "PENDING", "count": 50},
    ]
    dialect = _make_dialect(count_distinct_val=3, enum_values=enum_vals, sample_rows=[{"id": 1}])

    id_col = _make_col("id", "int", "integer", is_pk=True)
    status_col = _make_col("status", "varchar(20)", "string")
    columns = [id_col, status_col]

    updated, rows = scan_table_samples(conn, dialect, "orders", "public", columns)

    # id 是 PK，不应调用 count_distinct
    assert updated[0].name == "id"
    assert updated[0].enum_values is None
    assert not updated[0].is_enum_candidate

    # status 应有 enum_values（含置信度）
    assert updated[1].name == "status"
    assert updated[1].is_enum_candidate
    assert len(updated[1].enum_values) == 3
    assert updated[1].enum_values[0]["value"] == "ACTIVE"
    assert "confidence" in updated[1].enum_values[0]

    # count_distinct 只对 status 调用一次
    dialect.count_distinct.assert_called_once_with(conn, "orders", "public", "status")

    # 采样行正常返回
    assert rows == [{"id": 1}]


# ---------------------------------------------------------------------------
# 测试：高 cardinality → 不标记为枚举
# ---------------------------------------------------------------------------

def test_high_cardinality_not_enum():
    """count_distinct=200 >= 50，不应触发枚举值拉取"""
    conn = MagicMock()
    dialect = _make_dialect(count_distinct_val=200)

    name_col = _make_col("name", "varchar(255)", "string")
    updated, _ = scan_table_samples(conn, dialect, "users", "public", [name_col])

    assert updated[0].is_enum_candidate is False
    # 不应调用 get_enum_values
    dialect.get_enum_values.assert_not_called()


# ---------------------------------------------------------------------------
# 测试：PK 列跳过 count_distinct
# ---------------------------------------------------------------------------

def test_primary_key_skipped():
    """PK 列直接跳过，count_distinct 不应被调用"""
    conn = MagicMock()
    dialect = _make_dialect(count_distinct_val=1)

    pk_col = _make_col("id", "bigint", "integer", is_pk=True)
    updated, _ = scan_table_samples(conn, dialect, "products", "dbo", [pk_col])

    dialect.count_distinct.assert_not_called()
    assert updated[0].enum_values is None


# ---------------------------------------------------------------------------
# 测试：binary 类型列跳过
# ---------------------------------------------------------------------------

def test_binary_skipped():
    """normalized_type=binary 的列应跳过枚举探测，count_distinct 不应被调用"""
    conn = MagicMock()
    dialect = _make_dialect(count_distinct_val=5)

    blob_col = _make_col("thumbnail", "bytea", "binary")
    updated, _ = scan_table_samples(conn, dialect, "assets", "public", [blob_col])

    dialect.count_distinct.assert_not_called()
    assert updated[0].enum_values is None


# ---------------------------------------------------------------------------
# 额外：object 类型同样跳过
# ---------------------------------------------------------------------------

def test_object_type_skipped():
    """normalized_type=object（JSON 列）应跳过枚举探测"""
    conn = MagicMock()
    dialect = _make_dialect(count_distinct_val=5)

    json_col = _make_col("metadata", "jsonb", "object")
    updated, _ = scan_table_samples(conn, dialect, "events", "public", [json_col])

    dialect.count_distinct.assert_not_called()
    assert updated[0].enum_values is None


# ---------------------------------------------------------------------------
# 额外：输入列不被原地修改
# ---------------------------------------------------------------------------

def test_input_columns_not_mutated():
    """scan_table_samples 不应修改原始 ColumnInfo 对象"""
    conn = MagicMock()
    enum_vals = [{"value": "A", "count": 10}]
    dialect = _make_dialect(count_distinct_val=3, enum_values=enum_vals)

    col = _make_col("status", "varchar(20)", "string")
    original_enum_values = col.enum_values  # None

    updated, _ = scan_table_samples(conn, dialect, "codes", "public", [col])

    # 原始对象未被修改
    assert col.enum_values == original_enum_values
    # 返回的是新对象
    assert updated[0] is not col
    assert len(updated[0].enum_values) == 1
    assert updated[0].enum_values[0]["value"] == "A"
    assert "confidence" in updated[0].enum_values[0]


# ---------------------------------------------------------------------------
# 额外：单列 count_distinct 抛异常不影响其他列
# ---------------------------------------------------------------------------

def test_exception_on_one_column_continues():
    """某列 count_distinct 抛异常时，其他列应正常处理"""
    conn = MagicMock()
    dialect = MagicMock()
    dialect.sample_rows.return_value = []

    def _count_distinct_side_effect(conn, table, schema, col_name):
        if col_name == "bad_col":
            raise RuntimeError("数据库错误")
        return 3  # good_col → 枚举

    dialect.count_distinct.side_effect = _count_distinct_side_effect
    dialect.get_enum_values.return_value = [{"value": "X", "count": 1}]

    bad_col = _make_col("bad_col")
    good_col = _make_col("good_col")

    updated, _ = scan_table_samples(conn, dialect, "t", "s", [bad_col, good_col])

    # bad_col 失败后保持原样
    assert updated[0].name == "bad_col"
    assert updated[0].enum_values is None

    # good_col 正常被标记
    assert updated[1].name == "good_col"
    assert updated[1].is_enum_candidate
