"""测试 Schema HTML 报告生成器"""
import pytest

from apiscout.core.db_scanner.models import (
    ColumnInfo,
    ExplicitRelation,
    IndexInfo,
    InferredRelation,
    SchemaReport,
    TableInfo,
)
from apiscout.core.generator.schema_report_html import generate_schema_report_html


def _make_report() -> SchemaReport:
    """构造测试用 SchemaReport（2 表、1 显式 FK、1 推断关系、枚举值、采样数据）"""
    device_table = TableInfo(
        name="device",
        schema="public",
        comment="设备主表",
        row_count=200,
        columns=[
            ColumnInfo(
                name="id",
                data_type="bigint",
                normalized_type="integer",
                nullable=False,
                default=None,
                comment="主键",
                max_length=None,
                numeric_precision=19,
                is_primary_key=True,
                enum_values=None,
            ),
            ColumnInfo(
                name="status",
                data_type="varchar(20)",
                normalized_type="string",
                nullable=True,
                default="ACTIVE",
                comment="状态",
                max_length=20,
                numeric_precision=None,
                is_primary_key=False,
                enum_values=[
                    {"value": "ACTIVE", "count": 500},
                    {"value": "INACTIVE", "count": 120},
                    {"value": "MAINTENANCE", "count": 30},
                ],
            ),
        ],
        indexes=[
            IndexInfo(name="device_pkey", columns=["id"], is_unique=True, is_primary=True)
        ],
        sample_rows=[
            {"id": 1, "status": "ACTIVE"},
            {"id": 2, "status": "MAINTENANCE"},
        ],
    )

    work_order_table = TableInfo(
        name="work_order",
        schema="public",
        comment="工单表",
        row_count=1500,
        columns=[
            ColumnInfo(
                name="id",
                data_type="bigint",
                normalized_type="integer",
                nullable=False,
                default=None,
                comment="主键",
                max_length=None,
                numeric_precision=19,
                is_primary_key=True,
                enum_values=None,
            ),
            ColumnInfo(
                name="device_id",
                data_type="bigint",
                normalized_type="integer",
                nullable=False,
                default=None,
                comment="关联设备",
                max_length=None,
                numeric_precision=19,
                is_primary_key=False,
                enum_values=None,
            ),
        ],
        indexes=[],
        sample_rows=[],
    )

    return SchemaReport(
        dialect="postgresql",
        database="eam",
        scanned_at="2026-03-30T08:00:00Z",
        tables=[device_table, work_order_table],
        explicit_relations=[
            ExplicitRelation(
                source_table="work_order",
                source_column="device_id",
                target_table="device",
                target_column="id",
                constraint_name="fk_work_order_device",
            )
        ],
        inferred_relations=[
            InferredRelation(
                source_table="work_order",
                source_column="device_id",
                target_table="device",
                target_column="id",
                confidence=0.92,
                evidence="列名 device_id 与 device.id 命名匹配",
            )
        ],
    )


# ── 测试用例 ──────────────────────────────────────────────

def test_html_contains_tables():
    """HTML 中应包含两张表的名称"""
    html = generate_schema_report_html(_make_report())
    assert "device" in html
    assert "work_order" in html


def test_html_contains_columns():
    """HTML 中应包含列名和原始类型"""
    html = generate_schema_report_html(_make_report())
    assert "status" in html
    assert "varchar(20)" in html


def test_html_contains_enum_values():
    """HTML 中应包含枚举候选值及计数"""
    html = generate_schema_report_html(_make_report())
    assert "ACTIVE" in html
    assert "500" in html


def test_html_contains_relations():
    """HTML 中应包含外键信息"""
    html = generate_schema_report_html(_make_report())
    assert "fk_work_order_device" in html
    assert "device_id" in html


def test_html_contains_summary():
    """HTML 中应包含方言和数据库名"""
    html = generate_schema_report_html(_make_report())
    assert "postgresql" in html
    assert "eam" in html


def test_html_is_valid():
    """HTML 应以 DOCTYPE 开头并以 </html> 结尾"""
    html = generate_schema_report_html(_make_report())
    assert html.strip().startswith("<!DOCTYPE html>")
    assert html.strip().endswith("</html>")
