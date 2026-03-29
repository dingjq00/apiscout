"""AI 增强模块测试 — 使用 mock 不调真实 API"""
from unittest.mock import patch, MagicMock
from apiscout.core.generator.ai_enricher import (
    build_enrichment_prompt,
    parse_enrichment_response,
    enrich_endpoints,
)


def _make_endpoint(path, method, response_schema=None):
    return {
        "path": path,
        "method": method,
        "observation_count": 5,
        "status_codes": [200],
        "response_schema": response_schema or {"type": "object", "properties": {"id": {"type": "integer"}}},
        "request_schema": {},
        "query_params": [],
        "status": "confirmed",
    }


def test_build_prompt():
    """构建增强 prompt"""
    endpoints = [
        _make_endpoint("/api/equipment/{equipmentId}", "GET"),
        _make_endpoint("/api/equipment/search", "GET"),
    ]
    prompt = build_enrichment_prompt(endpoints)
    assert "/api/equipment/{equipmentId}" in prompt
    assert "/api/equipment/search" in prompt
    assert "JSON" in prompt


def test_parse_response_valid():
    """解析有效的 AI 响应"""
    response_text = '''```json
    [
        {
            "path": "/api/equipment/{equipmentId}",
            "method": "GET",
            "summary": "获取设备详情",
            "description": "根据设备ID获取设备的详细信息",
            "tags": ["设备管理"]
        }
    ]
    ```'''
    results = parse_enrichment_response(response_text)
    assert len(results) == 1
    assert results[0]["summary"] == "获取设备详情"


def test_parse_response_invalid():
    """解析无效响应不崩溃"""
    results = parse_enrichment_response("这不是 JSON")
    assert results == []


def test_enrich_no_api_key():
    """没有 API key 时优雅降级"""
    endpoints = [_make_endpoint("/api/test", "GET")]
    result = enrich_endpoints(endpoints, api_key=None)
    # 应该返回原始端点，不崩溃
    assert len(result) == 1
    assert result[0]["path"] == "/api/test"


def test_enrich_with_mock_api():
    """使用 mock API 测试增强流程"""
    endpoints = [_make_endpoint("/api/equipment/{equipmentId}", "GET")]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '''```json
    [{"path": "/api/equipment/{equipmentId}", "method": "GET", "summary": "获取设备详情", "description": "根据设备ID获取设备详细信息", "tags": ["设备管理"]}]
    ```'''

    with patch("apiscout.core.generator.ai_enricher._call_ai_api", return_value=mock_response):
        result = enrich_endpoints(endpoints, api_key="test-key", provider="deepseek")

    assert result[0].get("summary") == "获取设备详情"
    assert result[0].get("tags") == ["设备管理"]
