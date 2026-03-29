"""端点去重 + 数据聚合测试"""
from apiscout.core.analyzer.dedup import EndpointAggregator
from apiscout.core.capture.store import CaptureRecord


def _make_record(method, url, status=200, response_body=None, request_headers=None):
    return CaptureRecord(
        seq=0, timestamp="", page_url="", method=method, url=url,
        request_headers=request_headers or {},
        request_body=None, status=status,
        response_headers={"Content-Type": "application/json"},
        response_body=response_body or {},
        resource_type="fetch", protocol="rest",
    )


def test_aggregate_same_endpoint():
    """相同端点多次观察 → 合并 schema"""
    agg = EndpointAggregator()
    agg.add(_make_record("GET", "https://ex.com/api/equipment/1",
                         response_body={"id": 1, "name": "A", "status": 1}))
    agg.add(_make_record("GET", "https://ex.com/api/equipment/2",
                         response_body={"id": 2, "name": "B", "status": 2, "memo": "x"}))

    endpoints = agg.get_results()
    assert len(endpoints) == 1
    ep = endpoints[0]
    assert ep["path"] == "/api/equipment/{equipmentId}"
    assert ep["method"] == "GET"
    assert "id" in ep["response_schema"].get("required", [])
    assert "memo" not in ep["response_schema"].get("required", [])


def test_aggregate_query_params():
    """Query 参数收集与 schema 推断"""
    agg = EndpointAggregator()
    agg.add(_make_record("GET", "https://ex.com/api/equipment/search?status=1&page=1&size=20",
                         response_body={"items": []}))
    agg.add(_make_record("GET", "https://ex.com/api/equipment/search?status=2&page=2&size=20",
                         response_body={"items": []}))

    endpoints = agg.get_results()
    ep = endpoints[0]
    assert "query_params" in ep
    param_names = {p["name"] for p in ep["query_params"]}
    assert param_names == {"status", "page", "size"}


def test_aggregate_auth(sample_capture_record):
    """认证信息从请求头中提取"""
    agg = EndpointAggregator()
    record = CaptureRecord.from_dict(sample_capture_record)
    agg.add(record)

    auth = agg.get_auth_profile()
    assert auth["type"] == "bearer_jwt"


def test_skip_non_rest_records():
    """非 REST 协议记录被忽略"""
    agg = EndpointAggregator()
    record = CaptureRecord(
        seq=0, timestamp="", page_url="", method="GET",
        url="https://ex.com/api/data",
        request_headers={}, request_body=None, status=200,
        response_headers={}, response_body={},
        resource_type="script", protocol="other",
    )
    agg.add(record)
    assert agg.get_results() == []


def test_js_endpoint_appears_as_uncertain():
    """JS 静态分析发现但未触发的端点标记为 uncertain"""
    agg = EndpointAggregator()
    agg.add_js_endpoint("/api/reports/export")

    results = agg.get_results()
    assert len(results) == 1
    ep = results[0]
    assert ep["path"] == "/api/reports/export"
    assert ep["status"] == "uncertain"
    assert ep["method"] == "UNKNOWN"
    assert ep["observation_count"] == 0


def test_js_endpoint_confirmed_by_traffic():
    """已被流量命中的端点，JS 发现不重复计入"""
    agg = EndpointAggregator()
    agg.add(_make_record("GET", "https://ex.com/api/reports/export",
                         response_body={"url": "..."}))
    agg.add_js_endpoint("/api/reports/export")

    results = agg.get_results()
    # 只有一条，来自实际流量
    assert len(results) == 1
    assert results[0]["status"] == "confirmed"


def test_multiple_methods_same_path():
    """同路径不同 Method 分开记录"""
    agg = EndpointAggregator()
    agg.add(_make_record("GET", "https://ex.com/api/equipment/1",
                         response_body={"id": 1}))
    agg.add(_make_record("DELETE", "https://ex.com/api/equipment/2",
                         response_body={}))

    results = agg.get_results()
    assert len(results) == 2
    methods = {ep["method"] for ep in results}
    assert methods == {"GET", "DELETE"}


def test_status_codes_collected():
    """多个不同状态码被收集"""
    agg = EndpointAggregator()
    agg.add(_make_record("GET", "https://ex.com/api/equipment/1", status=200,
                         response_body={"id": 1}))
    agg.add(_make_record("GET", "https://ex.com/api/equipment/2", status=404,
                         response_body={"error": "not found"}))

    results = agg.get_results()
    assert results[0]["status_codes"] == [200, 404]


def test_request_body_schema_collected():
    """POST 请求体 schema 被推断"""
    agg = EndpointAggregator()
    record = CaptureRecord(
        seq=0, timestamp="", page_url="", method="POST",
        url="https://ex.com/api/equipment",
        request_headers={}, request_body={"name": "设备A", "location": "车间1"},
        status=201,
        response_headers={"Content-Type": "application/json"},
        response_body={"id": 100},
        resource_type="fetch", protocol="rest",
    )
    agg.add(record)

    results = agg.get_results()
    assert len(results) == 1
    ep = results[0]
    assert ep["request_schema"].get("type") == "object"
    assert "name" in ep["request_schema"].get("properties", {})


def test_empty_aggregator():
    """空聚合器返回空列表和 none 认证"""
    agg = EndpointAggregator()
    assert agg.get_results() == []
    assert agg.get_auth_profile() == {"type": "none"}
