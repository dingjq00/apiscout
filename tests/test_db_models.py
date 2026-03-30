"""数据库 Schema 数据模型测试"""
import dataclasses
import json

import pytest

from apiscout.core.db_scanner.models import (
    ColumnInfo,
    ExplicitRelation,
    IndexInfo,
    InferredRelation,
    SchemaReport,
    TableInfo,
)


def _make_column(name: str = "id", enum_values=None) -> ColumnInfo:
    return ColumnInfo(
        name=name,
        data_type="INT",
        normalized_type="integer",
        nullable=False,
        default=None,
        comment=None,
        max_length=None,
        numeric_precision=10,
        is_primary_key=True,
        enum_values=enum_values,
    )


def _make_table(name: str = "orders", columns=None, indexes=None) -> TableInfo:
    return TableInfo(
        name=name,
        schema="public",
        comment="订单表",
        row_count=1000,
        columns=columns or [_make_column("id"), _make_column("status")],
        indexes=indexes or [],
        sample_rows=[],
    )


# ---------- ColumnInfo ----------

def test_column_info_basic():
    col = _make_column("id")
    assert col.name == "id"
    assert col.data_type == "INT"
    assert col.normalized_type == "integer"
    assert col.nullable is False
    assert col.default is None
    assert col.comment is None
    assert col.max_length is None
    assert col.numeric_precision == 10
    assert col.is_primary_key is True
    assert col.enum_values is None
    assert col.is_enum_candidate is False


def test_column_info_enum_candidate():
    enum_vals = [{"value": "ACTIVE", "count": 500}, {"value": "INACTIVE", "count": 100}]
    col = ColumnInfo(
        name="status",
        data_type="VARCHAR",
        normalized_type="string",
        nullable=True,
        default="ACTIVE",
        comment="状态字段",
        max_length=20,
        numeric_precision=None,
        is_primary_key=False,
        enum_values=enum_vals,
    )
    assert col.is_enum_candidate is True
    assert len(col.enum_values) == 2
    assert col.enum_values[0]["value"] == "ACTIVE"


# ---------- TableInfo ----------

def test_table_info():
    idx = IndexInfo(
        name="idx_status",
        columns=["status"],
        is_unique=False,
        is_primary=False,
    )
    table = _make_table(
        name="orders",
        columns=[_make_column("id"), _make_column("status")],
        indexes=[idx],
    )
    assert table.name == "orders"
    assert table.schema == "public"
    assert table.comment == "订单表"
    assert table.row_count == 1000
    assert len(table.columns) == 2
    assert len(table.indexes) == 1
    assert table.indexes[0].name == "idx_status"
    assert table.indexes[0].is_unique is False
    assert table.sample_rows == []


# ---------- SchemaReport properties ----------

def _make_report() -> SchemaReport:
    status_col = ColumnInfo(
        name="status",
        data_type="VARCHAR",
        normalized_type="string",
        nullable=True,
        default=None,
        comment=None,
        max_length=20,
        numeric_precision=None,
        is_primary_key=False,
        enum_values=[{"value": "OPEN", "count": 200}],
    )
    table1 = TableInfo(
        name="orders",
        schema="public",
        comment=None,
        row_count=500,
        columns=[_make_column("id"), status_col],
        indexes=[],
        sample_rows=[],
    )
    table2 = TableInfo(
        name="items",
        schema="public",
        comment=None,
        row_count=1000,
        columns=[_make_column("id")],
        indexes=[],
        sample_rows=[],
    )
    explicit = ExplicitRelation(
        source_table="items",
        source_column="order_id",
        target_table="orders",
        target_column="id",
        constraint_name="fk_items_orders",
    )
    inferred = InferredRelation(
        source_table="items",
        source_column="product_id",
        target_table="products",
        target_column="id",
        confidence=0.85,
        evidence="命名规范推断：product_id → products.id",
    )
    return SchemaReport(
        dialect="postgresql",
        database="mydb",
        scanned_at="2026-03-30T00:00:00Z",
        tables=[table1, table2],
        explicit_relations=[explicit],
        inferred_relations=[inferred],
    )


def test_schema_report_properties():
    report = _make_report()

    assert report.total_tables == 2
    # orders 有 2 列，items 有 1 列
    assert report.total_columns == 3
    assert report.total_foreign_keys == 1
    assert report.total_inferred_relations == 1
    # 只有 status 列有 enum_values
    candidates = report.enum_candidates
    assert len(candidates) == 1
    assert candidates[0].name == "status"


def test_schema_report_serialization():
    report = _make_report()
    d = dataclasses.asdict(report)
    # 能序列化成 JSON 且无异常
    raw = json.dumps(d, ensure_ascii=False)
    assert isinstance(raw, str)
    # 反序列化后结构完整
    parsed = json.loads(raw)
    assert parsed["dialect"] == "postgresql"
    assert len(parsed["tables"]) == 2
    assert parsed["tables"][0]["columns"][1]["enum_values"][0]["value"] == "OPEN"
