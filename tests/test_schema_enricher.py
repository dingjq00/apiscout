"""Schema Enricher 测试 — 用 DB schema 增强 OpenAPI spec"""
import copy
import pytest
from apiscout.core.analyzer.schema_enricher import enrich_openapi_with_schema
from apiscout.core.db_scanner.models import SchemaReport, TableInfo, ColumnInfo, IndexInfo


# ─── 辅助构造函数 ────────────────────────────────────────────────


def _make_spec() -> dict:
    """构造最小 OpenAPI spec，路径 /api/devices GET 返回设备对象数组。"""
    return {
        "openapi": "3.1.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/api/devices": {
                "get": {
                    "operationId": "listDevices",
                    "responses": {
                        "200": {
                            "description": "设备列表",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "integer"},
                                                "status": {"type": "string"},
                                                "name": {"type": "string"},
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }


def _make_schema_report() -> SchemaReport:
    """构造包含 device 表的 SchemaReport。"""
    columns = [
        ColumnInfo(
            name="id",
            data_type="INT",
            normalized_type="integer",
            nullable=False,
            default=None,
            comment="设备ID",
            max_length=None,
            numeric_precision=11,
            is_primary_key=True,
            enum_values=None,
        ),
        ColumnInfo(
            name="status",
            data_type="VARCHAR(20)",
            normalized_type="string",
            nullable=True,
            default=None,
            comment="设备状态",
            max_length=20,
            numeric_precision=None,
            is_primary_key=False,
            enum_values=[
                {"value": "ACTIVE", "count": 500},
                {"value": "CLOSED", "count": 120},
            ],
        ),
        ColumnInfo(
            name="name",
            data_type="VARCHAR(100)",
            normalized_type="string",
            nullable=False,
            default=None,
            comment="设备名称",
            max_length=100,
            numeric_precision=None,
            is_primary_key=False,
            enum_values=None,
        ),
    ]

    table = TableInfo(
        name="device",
        schema="public",
        comment="设备主表",
        row_count=620,
        columns=columns,
        indexes=[IndexInfo(name="PRIMARY", columns=["id"], is_unique=True, is_primary=True)],
        sample_rows=[],
    )

    return SchemaReport(
        dialect="mysql",
        database="eam",
        scanned_at="2026-03-30T00:00:00Z",
        tables=[table],
        explicit_relations=[],
        inferred_relations=[],
    )


# ─── 测试用例 ─────────────────────────────────────────────────────


def test_enum_enrichment():
    """status 字段应被注入枚举值 ["ACTIVE", "CLOSED"]"""
    spec = _make_spec()
    report = _make_schema_report()

    enriched = enrich_openapi_with_schema(spec, report)

    items = enriched["paths"]["/api/devices"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"]
    status_prop = items["properties"]["status"]

    assert "enum" in status_prop, "status 应有 enum 字段"
    assert status_prop["enum"] == ["ACTIVE", "CLOSED"]


def test_description_enrichment():
    """name 字段应被注入 description = '设备名称'"""
    spec = _make_spec()
    report = _make_schema_report()

    enriched = enrich_openapi_with_schema(spec, report)

    items = enriched["paths"]["/api/devices"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"]
    name_prop = items["properties"]["name"]

    assert name_prop.get("description") == "设备名称"


def test_maxlength_enrichment():
    """name 字段（string 类型）应被注入 maxLength = 100"""
    spec = _make_spec()
    report = _make_schema_report()

    enriched = enrich_openapi_with_schema(spec, report)

    items = enriched["paths"]["/api/devices"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"]
    name_prop = items["properties"]["name"]

    assert name_prop.get("maxLength") == 100


def test_original_spec_unchanged():
    """enrich_openapi_with_schema 不应修改原始 spec（deep copy 保护）"""
    spec = _make_spec()
    original = copy.deepcopy(spec)
    report = _make_schema_report()

    enrich_openapi_with_schema(spec, report)

    assert spec == original, "原始 spec 不应被修改"


def test_no_match_path_unchanged():
    """路径无法匹配任何表时，schema 保持原样"""
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "1.0.0"},
        "paths": {
            "/api/unknownthing": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object", "properties": {"foo": {"type": "string"}}}
                                }
                            }
                        }
                    }
                }
            }
        },
    }
    report = _make_schema_report()
    original = copy.deepcopy(spec)

    enriched = enrich_openapi_with_schema(spec, report)

    # 路径不匹配，schema 内容不应有任何注入
    prop = enriched["paths"]["/api/unknownthing"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["properties"]["foo"]
    assert "description" not in prop
    assert "enum" not in prop


def test_existing_field_not_overwritten():
    """已有 description 的字段不应被覆盖"""
    spec = _make_spec()
    # 手动给 name 加上 description
    props = spec["paths"]["/api/devices"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"]["properties"]
    props["name"]["description"] = "已有描述"

    report = _make_schema_report()
    enriched = enrich_openapi_with_schema(spec, report)

    items = enriched["paths"]["/api/devices"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"]
    assert items["properties"]["name"]["description"] == "已有描述", "已有 description 不应被覆盖"


def test_integer_field_no_maxlength():
    """integer 类型字段不应被注入 maxLength（即使列有 max_length）"""
    spec = _make_spec()
    report = _make_schema_report()
    # 给 id 列临时加上 max_length（模拟异常数据）
    id_col = report.tables[0].columns[0]
    id_col.max_length = 11  # 通常 int 不会有 max_length，但容错测试

    enriched = enrich_openapi_with_schema(spec, report)

    items = enriched["paths"]["/api/devices"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"]
    # id 是 integer 类型，不应注入 maxLength
    assert "maxLength" not in items["properties"]["id"]


def test_table_prefix_matching():
    """路径 /api/devices 应能匹配表名 t_device（带前缀）"""
    spec = _make_spec()
    report = _make_schema_report()
    # 将表名改为 t_device
    report.tables[0].name = "t_device"

    enriched = enrich_openapi_with_schema(spec, report)

    items = enriched["paths"]["/api/devices"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["items"]
    # 如果匹配到 t_device，name 字段应有 description
    assert items["properties"]["name"].get("description") == "设备名称"
