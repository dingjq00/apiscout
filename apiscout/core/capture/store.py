"""JSONL 捕获数据存储 — 增量写盘，崩溃安全"""
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse, parse_qs


@dataclass
class CaptureRecord:
    """一条捕获记录"""
    seq: int
    timestamp: str
    page_url: str
    method: str
    url: str
    request_headers: dict
    request_body: dict | None
    status: int
    response_headers: dict
    response_body: dict | list | str | None
    resource_type: str
    protocol: str

    @property
    def path(self) -> str:
        """URL 的路径部分（不含 query）"""
        return urlparse(self.url).path

    @property
    def query_params(self) -> dict:
        """URL 的查询参数"""
        return parse_qs(urlparse(self.url).query)

    @property
    def host(self) -> str:
        parsed = urlparse(self.url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CaptureRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class CaptureStore:
    """JSONL 文件存储 — 每条记录立即写盘"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._file = None
        self._seq_counter = 0

    def _ensure_open(self):
        if self._file is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # 读取已有记录数作为 seq 起点
            if self.path.exists():
                self._seq_counter = sum(1 for line in self.path.open("r", encoding="utf-8") if line.strip())
            self._file = open(self.path, "a", encoding="utf-8")

    def append(self, record: CaptureRecord):
        """追加一条记录（立即写盘）"""
        self._ensure_open()
        self._seq_counter += 1
        record.seq = self._seq_counter
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()

    def read_all(self) -> Iterator[CaptureRecord]:
        """读取所有记录"""
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield CaptureRecord.from_dict(json.loads(line))

    def get_visited_page_urls(self) -> set[str]:
        """获取所有已访问的页面 URL（用于 --resume）"""
        return {r.page_url for r in self.read_all()}

    def count(self) -> int:
        """记录总数"""
        if not self.path.exists():
            return 0
        return sum(1 for line in open(self.path, "r", encoding="utf-8") if line.strip())

    def close(self):
        if self._file:
            self._file.close()
            self._file = None
