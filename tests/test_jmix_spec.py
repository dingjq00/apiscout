"""Jmix spec 生成测试"""
from apiscout.core.generator.jmix_spec import generate_jmix_spec


def _sample_metadata():
    return [
        {
            "entityName": "Product",
            "ancestor": None,
            "properties": [
                {"name": "code", "attributeType": "DATATYPE", "type": "string",
                 "cardinality": "NONE", "mandatory": True, "description": "产品编码"},
                {"name": "name", "attributeType": "DATATYPE", "type": "string",
                 "cardinality": "NONE", "mandatory": True, "description": "产品名称"},
                {"name": "createdDate", "attributeType": "DATATYPE", "type": "offsetDateTime",
                 "cardinality": "NONE", "mandatory": False, "description": "创建时间"},
                {"name": "productCategory", "attributeType": "ASSOCIATION", "type": "ProductCategory",
                 "cardinality": "MANY_TO_ONE", "mandatory": False, "description": "产品分类"},
            ],
        },
        {
            "entityName": "sec_RoleEntity",
            "ancestor": None,
            "properties": [
                {"name": "name", "attributeType": "DATATYPE", "type": "string",
                 "cardinality": "NONE", "mandatory": True, "description": ""},
            ],
        },
    ]


def test_generate_spec_basic():
    """基本生成"""
    spec = generate_jmix_spec(_sample_metadata(), title="Test API")
    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["title"] == "Test API"


def test_skip_framework_entities():
    """跳过框架实体"""
    spec = generate_jmix_spec(_sample_metadata())
    assert "Product" in spec["components"]["schemas"]
    assert "sec_RoleEntity" not in spec["components"]["schemas"]


def test_crud_paths():
    """生成 CRUD 路径"""
    spec = generate_jmix_spec(_sample_metadata())
    assert "/rest/entities/Product" in spec["paths"]
    assert "/rest/entities/Product/{id}" in spec["paths"]
    assert "get" in spec["paths"]["/rest/entities/Product"]
    assert "post" in spec["paths"]["/rest/entities/Product"]
    assert "put" in spec["paths"]["/rest/entities/Product/{id}"]
    assert "delete" in spec["paths"]["/rest/entities/Product/{id}"]


def test_property_types():
    """字段类型映射"""
    spec = generate_jmix_spec(_sample_metadata())
    props = spec["components"]["schemas"]["Product"]["properties"]
    assert props["code"]["type"] == "string"
    assert props["createdDate"]["format"] == "date-time"
    assert props["code"]["description"] == "产品编码"


def test_association_ref():
    """关联字段生成 $ref"""
    spec = generate_jmix_spec(_sample_metadata())
    props = spec["components"]["schemas"]["Product"]["properties"]
    assert "$ref" in props["productCategory"]


def test_required_fields():
    """必填字段"""
    spec = generate_jmix_spec(_sample_metadata())
    required = spec["components"]["schemas"]["Product"]["required"]
    assert "code" in required
    assert "name" in required


def test_query_params():
    """列表端点有 filter/sort/limit/offset 参数"""
    spec = generate_jmix_spec(_sample_metadata())
    params = spec["paths"]["/rest/entities/Product"]["get"]["parameters"]
    param_names = {p["name"] for p in params}
    assert {"filter", "sort", "limit", "offset", "fetchPlan"} == param_names
