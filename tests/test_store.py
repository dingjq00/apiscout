"""JSONL 存储层测试"""
import json
from pathlib import Path
from apiscout.core.capture.store import CaptureStore, CaptureRecord


def test_record_model(sample_capture_record):
    """CaptureRecord 能从 dict 创建"""
    record = CaptureRecord.from_dict(sample_capture_record)
    assert record.method == "GET"
    assert record.status == 200
    assert record.protocol == "rest"
    assert "/api/equipment/search" in record.path


def test_write_and_read(tmp_output, sample_capture_record):
    """写入后能正确读回"""
    path = tmp_output / "test.jsonl"
    store = CaptureStore(path)
    record = CaptureRecord.from_dict(sample_capture_record)

    store.append(record)
    store.append(record)

    records = list(store.read_all())
    assert len(records) == 2
    assert records[0].method == "GET"


def test_append_mode(tmp_output, sample_capture_record):
    """多次打开同一文件，数据追加不覆盖"""
    path = tmp_output / "test.jsonl"
    record = CaptureRecord.from_dict(sample_capture_record)

    store1 = CaptureStore(path)
    store1.append(record)
    store1.close()

    store2 = CaptureStore(path)
    store2.append(record)
    store2.close()

    store3 = CaptureStore(path)
    records = list(store3.read_all())
    assert len(records) == 2


def test_visited_urls(tmp_output, sample_capture_record):
    """已访问 URL 列表持久化"""
    path = tmp_output / "test.jsonl"
    store = CaptureStore(path)
    record = CaptureRecord.from_dict(sample_capture_record)
    store.append(record)

    visited = store.get_visited_page_urls()
    assert "https://eam.example.com/equipment/list" in visited
