"""OpenAPI 3.1 YAML 生成测试"""
import yaml
from apiscout.core.generator.openapi import generate_openapi


def _make_endpoint(path, method, response_schema=None, query_params=None, status="confirmed"):
    return {
        "path": path,
        "method": method,
        "observation_count": 3,
        "status_codes": [200],
        "response_schema": response_schema or {},
        "request_schema": {},
        "query_params": query_params or [],
        "status": status,
    }


def test_basic_generation():
    """基本 OpenAPI 生成"""
    endpoints = [
        _make_endpoint("/api/equipment/{equipmentId}", "GET",
                       response_schema={"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}}}),
    ]
    spec = generate_openapi(endpoints, title="EAM API", base_url="https://eam.example.com")

    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["title"] == "EAM API"
    assert "/api/equipment/{equipmentId}" in spec["paths"]
    path_item = spec["paths"]["/api/equipment/{equipmentId}"]
    assert "get" in path_item


def test_path_params_extracted():
    """路径参数自动提取"""
    endpoints = [
        _make_endpoint("/api/equipment/{equipmentId}/faults/{faultId}", "GET"),
    ]
    spec = generate_openapi(endpoints, title="Test")
    params = spec["paths"]["/api/equipment/{equipmentId}/faults/{faultId}"]["get"]["parameters"]
    param_names = {p["name"] for p in params}
    assert "equipmentId" in param_names
    assert "faultId" in param_names


def test_query_params_included():
    """query 参数写入 parameters"""
    endpoints = [
        _make_endpoint("/api/equipment/search", "GET",
                       query_params=[
                           {"name": "status", "in": "query", "schema": {"type": "integer"}, "required": True},
                           {"name": "page", "in": "query", "schema": {"type": "integer"}, "required": True},
                       ]),
    ]
    spec = generate_openapi(endpoints, title="Test")
    params = spec["paths"]["/api/equipment/search"]["get"]["parameters"]
    param_names = {p["name"] for p in params}
    assert "status" in param_names
    assert "page" in param_names


def test_draft_mode_markers():
    """草稿模式带 x-apiscout-review 标记"""
    endpoints = [
        _make_endpoint("/api/equipment", "GET", status="confirmed"),
        _make_endpoint("/api/hidden", "GET", status="uncertain"),
    ]
    spec = generate_openapi(endpoints, title="Test", draft=True)
    assert spec["paths"]["/api/equipment"]["get"].get("x-apiscout-review") == "confirmed"
    assert spec["paths"]["/api/hidden"]["get"].get("x-apiscout-review") == "uncertain"


def test_yaml_output(tmp_path):
    """YAML 文件输出"""
    from apiscout.core.generator.openapi import write_openapi_yaml
    endpoints = [_make_endpoint("/api/test", "GET")]
    output_path = tmp_path / "spec.yaml"
    write_openapi_yaml(endpoints, str(output_path), title="Test")

    with open(output_path, "r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    assert loaded["openapi"] == "3.1.0"
