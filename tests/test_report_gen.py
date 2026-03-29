"""HTML 覆盖率报告测试"""
from apiscout.core.generator.report import generate_report


def _make_endpoint(path, method, observation_count=3, status="confirmed"):
    return {
        "path": path,
        "method": method,
        "observation_count": observation_count,
        "status_codes": [200],
        "response_schema": {},
        "request_schema": {},
        "query_params": [],
        "status": status,
    }


def test_report_contains_endpoints():
    """报告包含端点列表"""
    endpoints = [
        _make_endpoint("/api/equipment/{equipmentId}", "GET"),
        _make_endpoint("/api/equipment/search", "GET"),
    ]
    html = generate_report(endpoints, title="EAM API 报告")
    assert "EAM API 报告" in html
    assert "/api/equipment/{equipmentId}" in html
    assert "/api/equipment/search" in html


def test_report_shows_uncertain_endpoints():
    """报告标记不确定端点"""
    endpoints = [
        _make_endpoint("/api/confirmed", "GET", status="confirmed"),
        _make_endpoint("/api/uncertain", "GET", status="uncertain", observation_count=0),
    ]
    html = generate_report(endpoints, title="Test")
    assert "uncertain" in html
    assert "confirmed" in html


def test_report_summary_stats():
    """报告包含统计摘要"""
    endpoints = [
        _make_endpoint("/api/a", "GET"),
        _make_endpoint("/api/b", "POST"),
        _make_endpoint("/api/c", "GET", status="uncertain"),
    ]
    html = generate_report(endpoints, title="Test")
    # 应该包含端点总数
    assert "3" in html


def test_report_writes_file(tmp_path):
    """报告写入文件"""
    from apiscout.core.generator.report import write_report
    endpoints = [_make_endpoint("/api/test", "GET")]
    output_path = tmp_path / "report.html"
    write_report(endpoints, str(output_path), title="Test")
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "<html" in content
