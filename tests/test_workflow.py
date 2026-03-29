"""工作流测试 — 测试分析和生成管线（不启动浏览器）"""
import json
import yaml
from pathlib import Path
from apiscout.core.workflow import analyze_capture, generate_outputs


def _write_jsonl(path, records):
    """写入测试 JSONL 文件"""
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _sample_records():
    return [
        {
            "seq": 1, "timestamp": "2026-03-29T14:30:05Z",
            "page_url": "https://eam.example.com/equipment/list",
            "method": "GET",
            "url": "https://eam.example.com/api/equipment/search?status=1&page=1&size=20",
            "request_headers": {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzExNzAwMDAwfQ.sig"},
            "request_body": None,
            "status": 200,
            "response_headers": {"Content-Type": "application/json"},
            "response_body": {"code": 0, "data": {"items": [{"id": 1, "name": "设备A"}], "total": 10}},
            "resource_type": "fetch",
            "protocol": "rest",
        },
        {
            "seq": 2, "timestamp": "2026-03-29T14:30:06Z",
            "page_url": "https://eam.example.com/equipment/1",
            "method": "GET",
            "url": "https://eam.example.com/api/equipment/1",
            "request_headers": {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzExNzAwMDAwfQ.sig"},
            "request_body": None,
            "status": 200,
            "response_headers": {"Content-Type": "application/json"},
            "response_body": {"id": 1, "name": "设备A", "status": 1, "location": "车间1"},
            "resource_type": "fetch",
            "protocol": "rest",
        },
        {
            "seq": 3, "timestamp": "2026-03-29T14:30:07Z",
            "page_url": "https://eam.example.com/equipment/2",
            "method": "GET",
            "url": "https://eam.example.com/api/equipment/2",
            "request_headers": {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzExNzAwMDAwfQ.sig"},
            "request_body": None,
            "status": 200,
            "response_headers": {"Content-Type": "application/json"},
            "response_body": {"id": 2, "name": "设备B", "status": 2},
            "resource_type": "fetch",
            "protocol": "rest",
        },
    ]


def test_analyze_capture(tmp_path):
    """分析 JSONL → 聚合结果"""
    jsonl_path = tmp_path / "capture.jsonl"
    _write_jsonl(jsonl_path, _sample_records())

    result = analyze_capture(str(jsonl_path))
    assert len(result["endpoints"]) >= 2  # /api/equipment/search + /api/equipment/{equipmentId}
    assert result["auth"]["type"] == "bearer_jwt"
    assert result["stats"]["total_records"] == 3


def test_generate_outputs(tmp_path):
    """生成全部输出文件"""
    jsonl_path = tmp_path / "capture.jsonl"
    _write_jsonl(jsonl_path, _sample_records())
    output_dir = tmp_path / "output"

    result = analyze_capture(str(jsonl_path))
    generate_outputs(result, str(output_dir), title="EAM 测试")

    # 验证文件存在
    assert (output_dir / "draft_spec.yaml").exists()
    assert (output_dir / "auth_profile.yaml").exists()
    assert (output_dir / "report.html").exists()
    assert (output_dir / "meta.yaml").exists()

    # 验证 spec 内容
    with open(output_dir / "draft_spec.yaml", "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    assert spec["openapi"] == "3.1.0"
    assert len(spec["paths"]) >= 2


def test_generate_outputs_meta(tmp_path):
    """meta.yaml 包含项目元信息"""
    jsonl_path = tmp_path / "capture.jsonl"
    _write_jsonl(jsonl_path, _sample_records())
    output_dir = tmp_path / "output"

    result = analyze_capture(str(jsonl_path))
    generate_outputs(result, str(output_dir))

    with open(output_dir / "meta.yaml", "r", encoding="utf-8") as f:
        meta = yaml.safe_load(f)
    assert "generated_at" in meta
    assert meta["tool"] == "APIScout"
    assert meta["stats"]["total_records"] == 3
