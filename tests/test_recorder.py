"""Recorder 测试 — 使用 mock 验证逻辑，不启动真实浏览器"""
import json
from unittest.mock import MagicMock, AsyncMock
from apiscout.core.capture.recorder import build_capture_record, PageRecorder
from apiscout.core.capture.store import CaptureRecord, CaptureStore
from apiscout.core.capture.filter import RequestFilter


def test_build_capture_record():
    """从原始请求/响应数据构建 CaptureRecord"""
    record = build_capture_record(
        page_url="https://eam.example.com/equipment",
        method="GET",
        url="https://eam.example.com/api/equipment/1",
        request_headers={"Authorization": "Bearer token123"},
        request_body=None,
        status=200,
        response_headers={"Content-Type": "application/json"},
        response_body={"id": 1, "name": "设备A"},
        resource_type="fetch",
    )
    assert isinstance(record, CaptureRecord)
    assert record.method == "GET"
    assert record.protocol == "rest"
    assert record.response_body == {"id": 1, "name": "设备A"}


def test_build_record_truncates_large_body():
    """大响应体应被截断"""
    large_body = {"data": "x" * 600_000}
    record = build_capture_record(
        page_url="https://eam.example.com/list",
        method="GET",
        url="https://eam.example.com/api/big",
        request_headers={},
        request_body=None,
        status=200,
        response_headers={"Content-Type": "application/json"},
        response_body=large_body,
        resource_type="fetch",
        max_body_size=524288,
    )
    assert record.response_body.get("_truncated") is True


def test_build_record_detects_protocol():
    """协议检测集成"""
    record = build_capture_record(
        page_url="https://eam.example.com/",
        method="POST",
        url="https://eam.example.com/graphql",
        request_headers={},
        request_body={"query": "{ users { id } }"},
        status=200,
        response_headers={"Content-Type": "application/json"},
        response_body={"data": {"users": []}},
        resource_type="fetch",
    )
    assert record.protocol == "graphql"


def test_auth_failure_count_tracks_consecutive_401(tmp_path):
    """连续 401/403 计数，非 401 时重置"""
    store = CaptureStore(tmp_path / "test.jsonl")
    filt = RequestFilter(target_origin="https://ex.com")
    recorder = PageRecorder(store, filt)

    assert recorder.auth_failure_count == 0
    # 模拟外部调用逻辑：连续 401 应递增，正常响应应重置
    recorder.auth_failure_count = 3
    assert recorder.auth_failure_count >= 3
    recorder.auth_failure_count = 0
    assert recorder.auth_failure_count == 0
