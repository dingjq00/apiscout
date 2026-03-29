"""共享 fixtures"""
import json
import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def tmp_output(tmp_path):
    """临时输出目录"""
    return tmp_path


@pytest.fixture
def sample_capture_record():
    """一条典型的捕获记录"""
    return {
        "seq": 1,
        "timestamp": "2026-03-29T14:30:05Z",
        "page_url": "https://eam.example.com/equipment/list",
        "method": "GET",
        "url": "https://eam.example.com/api/equipment/search?status=1&page=1&size=20",
        "request_headers": {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzExNzAwMDAwfQ.sig"},
        "request_body": None,
        "status": 200,
        "response_headers": {"Content-Type": "application/json"},
        "response_body": {
            "code": 0,
            "data": {
                "items": [
                    {"id": 1, "name": "设备A", "status": 1, "location": "车间1"},
                    {"id": 2, "name": "设备B", "status": 2, "location": "车间2"}
                ],
                "total": 165
            }
        },
        "resource_type": "fetch",
        "protocol": "rest"
    }


@pytest.fixture
def sample_records(sample_capture_record):
    """多条捕获记录，模拟同一端点的多次观察"""
    r1 = sample_capture_record.copy()
    r2 = sample_capture_record.copy()
    r2["seq"] = 2
    r2["url"] = "https://eam.example.com/api/equipment/search?status=2&page=1&size=20"
    r2["response_body"] = {
        "code": 0,
        "data": {
            "items": [
                {"id": 3, "name": "设备C", "status": 2, "memo": "维修中"}
            ],
            "total": 12
        }
    }
    return [r1, r2]
