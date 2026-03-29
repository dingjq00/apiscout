"""API 文档端点探测测试"""
from apiscout.core.crawler.api_prober import (
    ProbeResult, summarize_probe_results, PROBE_ENDPOINTS,
)


def test_probe_endpoints_list():
    """探测端点列表包含关键路径"""
    paths = {e["path"] for e in PROBE_ENDPOINTS}
    assert "/v3/api-docs" in paths
    assert "/rest/entities" in paths
    assert "/actuator" in paths
    assert "/doc.html" in paths


def test_summarize_with_openapi_spec():
    """找到 OpenAPI spec 时正确提取"""
    results = [
        ProbeResult(
            path="/v3/api-docs", type="openapi", desc="OpenAPI 3.x",
            status=200, content_type="application/json",
            body={"openapi": "3.1.0", "info": {"title": "Test"}, "paths": {}},
        ),
    ]
    summary = summarize_probe_results(results)
    assert summary["openapi_spec"] is not None
    assert summary["openapi_spec"]["openapi"] == "3.1.0"


def test_summarize_auth_required():
    """需要认证的端点归类到 auth_required"""
    results = [
        ProbeResult(path="/v3/api-docs", type="openapi", desc="", status=401,
                    needs_auth=True),
        ProbeResult(path="/actuator", type="actuator", desc="", status=403,
                    needs_auth=True),
    ]
    summary = summarize_probe_results(results)
    assert len(summary["auth_required"]) == 2
    assert summary["openapi_spec"] is None


def test_summarize_framework_hints():
    """框架特征检测"""
    results = [
        ProbeResult(path="/actuator", type="actuator", desc="", status=200),
        ProbeResult(path="/rest/entities", type="jmix_entities", desc="", status=200,
                    body=[{"name": "Product"}]),
    ]
    summary = summarize_probe_results(results)
    assert "Spring Boot (Actuator)" in summary["framework_hints"]
    assert "Jmix" in summary["framework_hints"]


def test_summarize_empty():
    """无结果时返回空结构"""
    summary = summarize_probe_results([])
    assert summary["openapi_spec"] is None
    assert summary["available_endpoints"] == []
