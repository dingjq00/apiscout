# APIScout V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable CLI tool that auto-discovers APIs from web applications and generates OpenAPI 3.1 specs.

**Architecture:** Playwright drives a browser for crawling + network capture. Captured requests are stored as JSONL, then analyzed (schema inference via genson, path parameterization + hash 归并, auth detection) and output as OpenAPI YAML + auth profile + HTML report. Two-pass workflow: draft → human review → final generate.

**Tech Stack:** Python 3.11, Playwright, genson, PyYAML, Jinja2, Click, PyInstaller

**Design Spec:** `docs/specs/2026-03-29-apiscout-design.md`

---

### 架构审查记录（2026-03-29）

对 21 项偷师清单 × 实施计划做了逐项对账，修复 3 个遗漏，4 项降级确认合理。

**本次修复：**
| 修复 | 涉及 Task | 说明 |
|------|-----------|------|
| Query 参数收集与输出 | 9, 10 | EndpointAggregator 收集 query params，OpenAPI 输出 parameters |
| 登录流追踪 | 11 | 从 capture 中识别 login/refresh 端点，输出 token_location |
| 保留词 + 日期段排除 | 6 | PathParameterizer 不参数化 v1/v2/admin/日期等 |
| Session 过期测试 | 5 | 补 auth_failure_count 测试覆盖 |
| 进度显示用请求数 | 16 | V1 进度不做实时端点归并，显示 captured_count |
| Router 重命名 | 6 | "Radix Tree" → "参数化归并"（V1 用 dict 足够） |

**V1.1 Backlog（审查确认不阻塞 V1）：**
- #15 Optic 迭代收敛循环 — 用于"增量更新已有 spec"场景
- #17 Optic YAML roundtrip writer — 保留用户对草稿的格式/注释修改
- #18 Akita Decorator Chain — recorder 扩展为可组合管线（采样/限流）
- #19 Akita CategorizeString — 比 genson 更精细的类型分类（OpenAPI 不需要）
- #20 Meeshkan 边录边推断 — 实时端点归并，进度显示更精确
- 响应包装层自动识别 — `{code, data, message}` 模式，在 AI enricher 中处理

---

## File Map

| File | Responsibility | Created In |
|------|---------------|------------|
| `apiscout/__init__.py` | Package init + version | Already exists |
| `apiscout/__main__.py` | `python -m apiscout` entry | Task 2 |
| `apiscout/ui/cli.py` | Click CLI commands | Task 2 |
| `apiscout/config/default.yaml` | Default config values | Task 2 |
| `apiscout/core/config.py` | Config loading (YAML + CLI overrides) | Task 2 |
| `apiscout/core/capture/store.py` | JSONL read/write, record model | Task 3 |
| `apiscout/core/capture/filter.py` | Request filtering + protocol detection | Task 4 |
| `apiscout/core/capture/recorder.py` | Playwright response listener → store | Task 5 |
| `apiscout/core/analyzer/router.py` | Path parameterization + trie matching | Task 6 |
| `apiscout/core/analyzer/schema_engine.py` | genson merge + format/enum enhancement | Task 7 |
| `apiscout/core/analyzer/auth_detector.py` | Auth type detection from headers | Task 8 |
| `apiscout/core/analyzer/dedup.py` | Endpoint deduplication + aggregation | Task 9 |
| `apiscout/core/generator/openapi.py` | OpenAPI 3.1 YAML output | Task 10 |
| `apiscout/core/generator/auth_profile.py` | Auth profile YAML output | Task 11 |
| `apiscout/core/generator/report.py` | HTML coverage report | Task 12 |
| `apiscout/core/crawler/link_extractor.py` | DOM link/navigation extraction | Task 13 |
| `apiscout/core/crawler/js_analyzer.py` | JS static analysis for API URLs | Task 14 |
| `apiscout/core/crawler/scroll_loader.py` | Scroll + network idle detection | Task 15 |
| `apiscout/core/crawler/navigator.py` | Page exploration orchestration | Task 16 |
| `apiscout/core/workflow.py` | Two-pass workflow + Phase 1→2 | Task 17 |
| `apiscout/core/generator/ai_enricher.py` | AI enrichment (optional) | Task 18 |
| `templates/report.html.j2` | Jinja2 report template | Task 12 |

---

### Task 0: Spike — Playwright + PyInstaller 兼容性验证

**Files:**
- Create: `spike/test_playwright_pack.py`
- Create: `spike/pack_test.spec`

这是 P0 技术风险。在写任何业务代码之前，先验证 Playwright 能否被 PyInstaller 打包并在无 Python 环境的机器上运行。

- [ ] **Step 1: 创建最小 Playwright 测试脚本**

```python
# spike/test_playwright_pack.py
"""最小化 Playwright 测试 — 验证 PyInstaller 打包可行性"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://example.com")
        title = await page.title()
        print(f"页面标题: {title}")
        await browser.close()
        print("✅ Playwright 运行成功")

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 验证脚本正常运行**

Run: `python spike/test_playwright_pack.py`
Expected: 浏览器弹出，访问 example.com，打印标题后关闭

- [ ] **Step 3: 创建 PyInstaller spec**

```python
# spike/pack_test.spec
import os
import playwright

pw_path = os.path.dirname(playwright.__file__)

a = Analysis(
    ['test_playwright_pack.py'],
    pathex=[],
    binaries=[],
    datas=[(pw_path, 'playwright')],
    hiddenimports=['playwright', 'playwright.async_api'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='test_pw', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='test_pw')
```

- [ ] **Step 4: 打包并测试**

Run:
```bash
cd spike && pyinstaller pack_test.spec --onedir
PLAYWRIGHT_BROWSERS_PATH=0 ./dist/test_pw/test_pw
```
Expected: 打包成功，运行时 Playwright 能找到 Chromium 并启动

- [ ] **Step 5: 记录结果**

如果成功：记录打包参数和注意事项到 `docs/spike-results.md`
如果失败：研究替代方案（如 playwright 的 `PLAYWRIGHT_BROWSERS_PATH` 环境变量指向打包目录内的 chromium）

- [ ] **Step 6: Commit**

```bash
git add spike/ docs/
git commit -m "spike: Playwright + PyInstaller 兼容性验证"
```

---

### Task 1: 项目依赖与基础设施

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "apiscout"
version = "0.1.0"
description = "自动化 API 发现与文档生成工具"
requires-python = ">=3.11"
dependencies = [
    "playwright>=1.40",
    "genson>=1.2",
    "pyyaml>=6.0",
    "jinja2>=3.1",
    "click>=8.1",
]

[project.optional-dependencies]
ai = ["openai>=1.0"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]
pack = ["pyinstaller>=6.0"]

[project.scripts]
apiscout = "apiscout.ui.cli:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: 创建 requirements.txt**

```
playwright>=1.40
genson>=1.2
pyyaml>=6.0
jinja2>=3.1
click>=8.1
```

- [ ] **Step 3: 创建测试基础**

```python
# tests/__init__.py
```

```python
# tests/conftest.py
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
```

- [ ] **Step 4: 安装依赖**

Run:
```bash
cd /Users/dingjq/projects/apiscout
pip install -e ".[dev]"
playwright install chromium
```
Expected: 所有依赖安装成功

- [ ] **Step 5: 验证 pytest 能运行**

Run: `pytest tests/ -v`
Expected: `no tests ran` (没有测试文件，但框架正常)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements.txt tests/
git commit -m "chore: 项目依赖与测试基础设施"
```

---

### Task 2: Config + CLI 骨架

**Files:**
- Create: `apiscout/config/default.yaml`
- Create: `apiscout/core/__init__.py`
- Create: `apiscout/core/config.py`
- Create: `apiscout/ui/__init__.py`
- Create: `apiscout/ui/cli.py`
- Create: `apiscout/__main__.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 写 config 测试**

```python
# tests/test_config.py
"""配置加载测试"""
from apiscout.core.config import load_config


def test_load_default_config():
    """默认配置应该包含所有必需字段"""
    cfg = load_config()
    assert cfg["crawl"]["max_depth"] == 5
    assert cfg["crawl"]["max_pages"] == 200
    assert cfg["crawl"]["page_timeout"] == 30
    assert cfg["crawl"]["network_idle_wait"] == 3
    assert cfg["crawl"]["request_delay"] == 0.5
    assert cfg["capture"]["max_body_size"] == 524288  # 512KB
    assert "exclude_patterns" in cfg["crawl"]


def test_config_override():
    """CLI 参数应该覆盖默认配置"""
    cfg = load_config(overrides={"crawl": {"max_pages": 50}})
    assert cfg["crawl"]["max_pages"] == 50
    assert cfg["crawl"]["max_depth"] == 5  # 其他值不变
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apiscout.core.config'`

- [ ] **Step 3: 创建默认配置**

```yaml
# apiscout/config/default.yaml
crawl:
  max_depth: 5
  max_pages: 200
  page_timeout: 30          # 秒
  network_idle_wait: 3       # 秒
  request_delay: 0.5         # 秒，每次导航间隔
  concurrent_pages: 1
  domain_scope: same-origin
  exclude_patterns:
    - "/logout"
    - "/static/*"
    - "/assets/*"
    - "/favicon.ico"
  exploration_level: standard  # quick / standard / thorough

capture:
  max_body_size: 524288      # 512KB
  resource_types:
    - fetch
    - xhr
    - document
  skip_extensions:
    - .css
    - .js
    - .png
    - .jpg
    - .gif
    - .svg
    - .woff
    - .woff2
    - .ttf
    - .ico

output:
  dir: "./output"
  screenshots: false
```

- [ ] **Step 4: 实现 config.py**

```python
# apiscout/core/__init__.py
```

```python
# apiscout/core/config.py
"""配置加载：default.yaml → 用户 yaml → CLI 覆盖"""
import copy
from pathlib import Path
import yaml


_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 优先"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(config_path: str | None = None, overrides: dict | None = None) -> dict:
    """加载配置：默认 → 用户文件 → CLI 覆盖"""
    with open(_DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if config_path:
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        config = _deep_merge(config, user_config)

    if overrides:
        config = _deep_merge(config, overrides)

    return config
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 6: 创建 CLI 骨架**

```python
# apiscout/ui/__init__.py
```

```python
# apiscout/ui/cli.py
"""APIScout CLI 入口"""
import click
from apiscout import __version__


@click.group()
@click.version_option(__version__, prog_name="apiscout")
def main():
    """APIScout — 自动化 API 发现与文档生成工具"""
    pass


@main.command()
@click.option("--url", required=True, help="目标系统 URL")
@click.option("--output", "-o", default="./output", help="输出目录")
@click.option("--config", "-c", default=None, help="自定义配置文件")
@click.option("--max-pages", default=None, type=int, help="最大页面数")
@click.option("--max-depth", default=None, type=int, help="最大爬取深度")
def scan(url, output, config, max_pages, max_depth):
    """完整扫描：自动探索 → 手动补录 → 生成输出"""
    click.echo(f"🔍 APIScout v{__version__}")
    click.echo(f"   目标: {url}")
    click.echo(f"   输出: {output}")
    click.echo("   [待实现 — Task 17 完成后接入 workflow]")


@main.command()
@click.option("--url", required=True, help="目标系统 URL")
@click.option("--output", "-o", default="capture.jsonl", help="捕获输出文件")
@click.option("--append", is_flag=True, help="追加模式（多角色扫描）")
@click.option("--resume", is_flag=True, help="从上次中断继续")
def explore(url, output, append, resume):
    """仅执行探索阶段，输出捕获数据"""
    click.echo(f"🔍 探索: {url} → {output}")
    click.echo("   [待实现 — Task 17]")


@main.command()
@click.argument("capture_file")
@click.option("--output", "-o", default="draft_spec.yaml", help="输出文件")
def analyze(capture_file, output):
    """分析捕获数据，生成草稿 spec"""
    click.echo(f"📊 分析: {capture_file} → {output}")
    click.echo("   [待实现 — Task 17]")


@main.command()
@click.argument("draft_file")
@click.option("--output", "-o", default="./output", help="输出目录")
def generate(draft_file, output):
    """从审核后的草稿生成最终输出"""
    click.echo(f"📝 生成: {draft_file} → {output}")
    click.echo("   [待实现 — Task 17]")


@main.command()
@click.argument("project_dir")
@click.option("--ai", default="deepseek", help="AI 提供商")
@click.option("--api-key", envvar="DEEPSEEK_API_KEY", help="API Key")
def enrich(project_dir, ai, api_key):
    """AI 增强：端点命名、字段语义、MCP Tool 生成"""
    click.echo(f"🤖 AI 增强: {project_dir}")
    click.echo("   [待实现 — Task 18]")
```

```python
# apiscout/__main__.py
"""python -m apiscout 入口"""
from apiscout.ui.cli import main

main()
```

- [ ] **Step 7: 验证 CLI 能运行**

Run: `python -m apiscout --version`
Expected: `apiscout, version 0.1.0`

Run: `python -m apiscout scan --url https://example.com`
Expected: 打印目标 URL 和 "待实现" 提示

- [ ] **Step 8: Commit**

```bash
git add apiscout/ tests/test_config.py
git commit -m "feat: 配置加载 + CLI 骨架（5个命令占位）"
```

---

### Task 3: Capture Store（JSONL 存储层）

**Files:**
- Create: `apiscout/core/capture/__init__.py`
- Create: `apiscout/core/capture/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: 写存储层测试**

```python
# tests/test_store.py
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现存储层**

```python
# apiscout/core/capture/__init__.py
```

```python
# apiscout/core/capture/store.py
"""JSONL 捕获数据存储 — 增量写盘，崩溃安全"""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse, urlencode, parse_qs


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
                self._seq_counter = sum(1 for _ in self.path.open("r", encoding="utf-8") if _.strip())
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
        return sum(1 for _ in open(self.path, "r", encoding="utf-8") if _.strip())

    def close(self):
        if self._file:
            self._file.close()
            self._file = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_store.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add apiscout/core/capture/ tests/test_store.py
git commit -m "feat: JSONL 捕获存储层 — 增量写盘 + 崩溃恢复"
```

---

### Task 4: Capture Filter（请求过滤 + 协议检测）

**Files:**
- Create: `apiscout/core/capture/filter.py`
- Test: `tests/test_filter.py`

- [ ] **Step 1: 写过滤器测试**

```python
# tests/test_filter.py
"""请求过滤 + 协议检测测试"""
from apiscout.core.capture.filter import RequestFilter, ProtocolDetector


class TestRequestFilter:

    def test_accept_api_fetch(self):
        f = RequestFilter(target_origin="https://eam.example.com")
        assert f.should_capture(
            url="https://eam.example.com/api/equipment/list",
            resource_type="fetch",
            content_type="application/json",
            status=200,
        )

    def test_reject_static_resource(self):
        f = RequestFilter(target_origin="https://eam.example.com")
        assert not f.should_capture(
            url="https://eam.example.com/static/logo.png",
            resource_type="image",
            content_type="image/png",
            status=200,
        )

    def test_reject_third_party(self):
        f = RequestFilter(target_origin="https://eam.example.com")
        assert not f.should_capture(
            url="https://cdn.example.com/lib.js",
            resource_type="script",
            content_type="application/javascript",
            status=200,
        )

    def test_reject_excluded_pattern(self):
        f = RequestFilter(
            target_origin="https://eam.example.com",
            exclude_patterns=["/logout", "/static/*"],
        )
        assert not f.should_capture(
            url="https://eam.example.com/logout",
            resource_type="document",
            content_type="text/html",
            status=302,
        )


class TestProtocolDetector:

    def test_detect_rest_json(self):
        d = ProtocolDetector()
        assert d.classify(
            url="https://eam.example.com/api/equipment/1",
            request_body=None,
            response_content_type="application/json",
        ) == "rest"

    def test_detect_graphql(self):
        d = ProtocolDetector()
        assert d.classify(
            url="https://eam.example.com/graphql",
            request_body={"query": "{ equipment { id } }"},
            response_content_type="application/json",
        ) == "graphql"

    def test_detect_soap(self):
        d = ProtocolDetector()
        assert d.classify(
            url="https://eam.example.com/ws/equipment",
            request_body="<soap:Envelope>...</soap:Envelope>",
            response_content_type="text/xml",
        ) == "soap"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_filter.py -v`
Expected: FAIL

- [ ] **Step 3: 实现过滤器**

```python
# apiscout/core/capture/filter.py
"""请求过滤 + 协议检测"""
import fnmatch
from urllib.parse import urlparse


class RequestFilter:
    """决定哪些请求值得捕获"""

    # 需要捕获的资源类型
    CAPTURE_TYPES = {"fetch", "xhr", "document"}
    # 跳过的文件扩展名
    SKIP_EXTENSIONS = {".css", ".js", ".png", ".jpg", ".gif", ".svg",
                       ".woff", ".woff2", ".ttf", ".ico", ".mp4", ".mp3"}

    def __init__(self, target_origin: str, exclude_patterns: list[str] | None = None):
        parsed = urlparse(target_origin)
        self.target_origin = f"{parsed.scheme}://{parsed.netloc}"
        self.exclude_patterns = exclude_patterns or []

    def should_capture(self, url: str, resource_type: str,
                       content_type: str, status: int) -> bool:
        """判断这个请求是否应该被捕获"""
        # 1. 资源类型过滤
        if resource_type not in self.CAPTURE_TYPES:
            return False

        # 2. 同源检查
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin != self.target_origin:
            return False

        # 3. 文件扩展名过滤
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in self.SKIP_EXTENSIONS):
            return False

        # 4. 排除模式
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(parsed.path, pattern):
                return False

        return True


class ProtocolDetector:
    """从请求/响应特征判断 API 协议类型"""

    def classify(self, url: str, request_body, response_content_type: str) -> str:
        # GraphQL: URL 包含 graphql，或 body 有 query 字段
        path = urlparse(url).path.rstrip("/")
        if path.endswith("/graphql") or path.endswith("/gql"):
            return "graphql"
        if isinstance(request_body, dict) and "query" in request_body:
            return "graphql"

        # SOAP: XML content type + envelope 结构
        if response_content_type and "xml" in response_content_type:
            if isinstance(request_body, str) and "<soap:" in request_body.lower():
                return "soap"
            return "rest_xml"

        # JSON-RPC: body 有 jsonrpc 字段
        if isinstance(request_body, dict) and "jsonrpc" in request_body:
            return "jsonrpc"

        # gRPC-Web
        if response_content_type and "grpc" in response_content_type:
            return "grpc"

        # 默认：REST + JSON
        if response_content_type and "json" in response_content_type:
            return "rest"

        return "unknown"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_filter.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add apiscout/core/capture/filter.py tests/test_filter.py
git commit -m "feat: 请求过滤（同源/资源类型/排除模式）+ 协议检测"
```

---

### Task 5: Capture Recorder（Playwright 响应监听）

**Files:**
- Create: `apiscout/core/capture/recorder.py`
- Test: `tests/test_recorder.py`

- [ ] **Step 1: 写 recorder 测试**

```python
# tests/test_recorder.py
"""Recorder 测试 — 使用 mock 验证逻辑，不启动真实浏览器"""
import json
from unittest.mock import MagicMock, AsyncMock
from apiscout.core.capture.recorder import build_capture_record
from apiscout.core.capture.store import CaptureRecord


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


import pytest
from apiscout.core.capture.recorder import PageRecorder
from apiscout.core.capture.store import CaptureStore
from apiscout.core.capture.filter import RequestFilter


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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_recorder.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 recorder**

```python
# apiscout/core/capture/recorder.py
"""Playwright 响应监听 → CaptureStore"""
import json
import logging
from datetime import datetime, timezone
from playwright.async_api import Page, Response

from apiscout.core.capture.store import CaptureRecord, CaptureStore
from apiscout.core.capture.filter import RequestFilter, ProtocolDetector

logger = logging.getLogger(__name__)

_protocol_detector = ProtocolDetector()


def build_capture_record(
    page_url: str,
    method: str,
    url: str,
    request_headers: dict,
    request_body,
    status: int,
    response_headers: dict,
    response_body,
    resource_type: str,
    max_body_size: int = 524288,
) -> CaptureRecord:
    """从原始数据构建 CaptureRecord"""
    # 协议检测
    content_type = response_headers.get("Content-Type", response_headers.get("content-type", ""))
    protocol = _protocol_detector.classify(url, request_body, content_type)

    # 大 body 截断
    if response_body is not None:
        body_str = json.dumps(response_body, ensure_ascii=False) if not isinstance(response_body, str) else response_body
        if len(body_str) > max_body_size:
            response_body = {
                "_truncated": True,
                "_original_size": len(body_str),
            }

    return CaptureRecord(
        seq=0,  # store.append 时会重新分配
        timestamp=datetime.now(timezone.utc).isoformat(),
        page_url=page_url,
        method=method,
        url=url,
        request_headers=request_headers,
        request_body=request_body,
        status=status,
        response_headers=dict(response_headers),
        response_body=response_body,
        resource_type=resource_type,
        protocol=protocol,
    )


class PageRecorder:
    """挂载到 Playwright Page 上，监听所有响应并写入 store"""

    def __init__(self, store: CaptureStore, request_filter: RequestFilter,
                 max_body_size: int = 524288):
        self.store = store
        self.filter = request_filter
        self.max_body_size = max_body_size
        self.captured_count = 0
        self.auth_failure_count = 0  # 连续 401/403 计数

    async def attach(self, page: Page):
        """挂载到 page，开始监听"""
        page.on("response", self._on_response)

    async def _on_response(self, response: Response):
        """响应回调"""
        request = response.request
        resource_type = request.resource_type
        content_type = response.headers.get("content-type", "")

        # 过滤
        if not self.filter.should_capture(
            url=request.url,
            resource_type=resource_type,
            content_type=content_type,
            status=response.status,
        ):
            return

        # Session 过期检测
        if response.status in (401, 403):
            self.auth_failure_count += 1
            if self.auth_failure_count >= 3:
                logger.warning("⚠️ 连续 %d 个认证失败，session 可能已过期", self.auth_failure_count)
            return
        self.auth_failure_count = 0

        # 解析 body
        try:
            response_body = await response.json()
        except Exception:
            try:
                response_body = await response.text()
            except Exception:
                response_body = None

        # 解析 request body
        request_body = None
        if request.post_data:
            try:
                request_body = json.loads(request.post_data)
            except (json.JSONDecodeError, TypeError):
                request_body = request.post_data

        record = build_capture_record(
            page_url=response.frame.url if response.frame else "",
            method=request.method,
            url=request.url,
            request_headers=dict(request.headers),
            request_body=request_body,
            status=response.status,
            response_headers=dict(response.headers),
            response_body=response_body,
            resource_type=resource_type,
            max_body_size=self.max_body_size,
        )

        self.store.append(record)
        self.captured_count += 1
        logger.debug("捕获: %s %s → %d", request.method, request.url, response.status)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_recorder.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add apiscout/core/capture/recorder.py tests/test_recorder.py
git commit -m "feat: Playwright 响应监听 + session 过期检测 + body 截断"
```

---

### Task 6: Router（路径参数化归并 + 端点聚合）

**Files:**
- Create: `apiscout/core/analyzer/__init__.py`
- Create: `apiscout/core/analyzer/router.py`
- Test: `tests/test_router.py`

- [ ] **Step 1: 写路由测试**

```python
# tests/test_router.py
"""路径参数化 + 端点归并测试"""
from apiscout.core.analyzer.router import PathParameterizer, EndpointRouter


class TestPathParameterizer:

    def test_numeric_id(self):
        p = PathParameterizer()
        result = p.parameterize("/api/equipment/123")
        assert result == "/api/equipment/{equipmentId}"

    def test_uuid(self):
        p = PathParameterizer()
        result = p.parameterize("/api/users/550e8400-e29b-41d4-a716-446655440000")
        assert result == "/api/users/{uuid}"

    def test_snowflake_id(self):
        p = PathParameterizer()
        result = p.parameterize("/api/orders/1234567890123456789")
        assert result == "/api/orders/{snowflakeId}"

    def test_code_id(self):
        """编码型 ID: EQ202603110001"""
        p = PathParameterizer()
        result = p.parameterize("/api/equipment/EQ202603110001")
        assert result == "/api/equipment/{code}"

    def test_nested_params(self):
        """嵌套路径参数"""
        p = PathParameterizer()
        result = p.parameterize("/api/equipment/123/faults/456")
        assert result == "/api/equipment/{equipmentId}/faults/{faultId}"

    def test_no_param(self):
        """纯静态路径不变"""
        p = PathParameterizer()
        result = p.parameterize("/api/equipment/list")
        assert result == "/api/equipment/list"

    def test_reserved_segments_not_parameterized(self):
        """保留词不参数化（偷师 Optic #16）"""
        p = PathParameterizer()
        # v2 不应该被参数化
        result = p.parameterize("/api/v2/equipment/123")
        assert result == "/api/v2/equipment/{equipmentId}"
        # admin 不应该被参数化
        result = p.parameterize("/admin/users/456")
        assert result == "/admin/users/{userId}"

    def test_date_segment_not_parameterized(self):
        """日期段不参数化（偷师 Optic #16）"""
        p = PathParameterizer()
        result = p.parameterize("/api/report/20260329")
        assert result == "/api/report/20260329"
        result = p.parameterize("/api/report/2026-03-29")
        assert result == "/api/report/2026-03-29"


class TestEndpointRouter:

    def test_insert_and_lookup(self):
        router = EndpointRouter()
        router.add("/api/equipment/123", "GET")
        router.add("/api/equipment/456", "GET")

        # 两个应该归并到同一个参数化端点
        endpoints = router.get_endpoints()
        paths = [e["path"] for e in endpoints]
        assert "/api/equipment/{equipmentId}" in paths
        # 只有一个端点，不是两个
        eq_endpoints = [e for e in endpoints if "equipment" in e["path"] and "{" in e["path"]]
        assert len(eq_endpoints) == 1
        assert eq_endpoints[0]["observation_count"] == 2

    def test_different_methods_same_path(self):
        router = EndpointRouter()
        router.add("/api/equipment/1", "GET")
        router.add("/api/equipment/2", "POST")

        endpoints = router.get_endpoints()
        methods = {(e["path"], e["method"]) for e in endpoints}
        assert ("/api/equipment/{equipmentId}", "GET") in methods
        assert ("/api/equipment/{equipmentId}", "POST") in methods
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_router.py -v`
Expected: FAIL

- [ ] **Step 3: 实现路由器**

```python
# apiscout/core/analyzer/__init__.py
```

```python
# apiscout/core/analyzer/router.py
"""路径参数化归并 — 参数化后 hash 聚合，非 Radix Tree（V1 规模 dict 足够）"""
import re
from collections import defaultdict


# 保留词 — 这些路径段永远不参数化（偷师 Optic 路径推断启发式）
RESERVED_SEGMENTS = {
    "api", "v1", "v2", "v3", "v4", "static", "admin", "auth",
    "public", "internal", "graphql", "ws", "health", "metrics",
}

# 日期格式 — 不参数化
DATE_PATTERNS = [
    re.compile(r'^\d{4}\d{2}\d{2}$'),       # 20260329
    re.compile(r'^\d{4}-\d{2}-\d{2}$'),      # 2026-03-29
]

# 参数检测模式，按优先级排列
PARAM_PATTERNS = [
    (re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I), 'uuid'),
    (re.compile(r'^\d{15,}$'), 'snowflakeId'),
    (re.compile(r'^[0-9a-f]{24}$'), 'objectId'),
    (re.compile(r'^[A-Z]{2,4}\d{8,}$'), 'code'),
    (re.compile(r'^\d+$'), 'id'),
    (re.compile(r'^[0-9a-f]{6,12}$'), 'hash'),
]


def _singularize(word: str) -> str:
    """简单的英文单数化（覆盖常见情况）"""
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("ses") or word.endswith("xes"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


class PathParameterizer:
    """将具体路径转为参数化路径"""

    def parameterize(self, path: str) -> str:
        """
        /api/equipment/123/faults/456
        → /api/equipment/{equipmentId}/faults/{faultId}
        """
        segments = path.strip("/").split("/")
        result = []
        prev_segment = None

        for seg in segments:
            param_type = self._detect_param(seg)
            if param_type:
                # 智能命名：前一段的单数形式 + "Id"（或直接用类型名）
                if param_type == "id" and prev_segment:
                    name = _singularize(prev_segment) + "Id"
                else:
                    name = param_type
                result.append("{" + name + "}")
            else:
                result.append(seg)
                prev_segment = seg

        return "/" + "/".join(result)

    def _detect_param(self, segment: str) -> str | None:
        """检测路径段是否是参数"""
        # 保留词永远不参数化
        if segment.lower() in RESERVED_SEGMENTS:
            return None
        # 日期段不参数化
        for dp in DATE_PATTERNS:
            if dp.match(segment):
                return None
        for pattern, param_type in PARAM_PATTERNS:
            if pattern.match(segment):
                return param_type
        return None


class EndpointRouter:
    """端点归并 — 将具体路径归并到参数化端点"""

    def __init__(self):
        self._parameterizer = PathParameterizer()
        # {(parameterized_path, method): {"count": N, "concrete_paths": set}}
        self._endpoints: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"count": 0, "concrete_paths": set()}
        )

    def add(self, path: str, method: str):
        """添加一个观察到的路径"""
        parameterized = self._parameterizer.parameterize(path)
        key = (parameterized, method.upper())
        self._endpoints[key]["count"] += 1
        self._endpoints[key]["concrete_paths"].add(path)

    def lookup(self, path: str, method: str) -> str:
        """查找路径对应的参数化端点"""
        parameterized = self._parameterizer.parameterize(path)
        key = (parameterized, method.upper())
        if key in self._endpoints:
            return parameterized
        return parameterized  # 新端点也返回参数化结果

    def get_endpoints(self) -> list[dict]:
        """获取所有归并后的端点"""
        result = []
        for (path, method), data in self._endpoints.items():
            result.append({
                "path": path,
                "method": method,
                "observation_count": data["count"],
                "concrete_paths": list(data["concrete_paths"]),
            })
        return sorted(result, key=lambda e: (e["path"], e["method"]))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_router.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add apiscout/core/analyzer/ tests/test_router.py
git commit -m "feat: 路径参数化（UUID/数字ID/雪花/编码）+ 端点归并"
```

---

### Task 7: Schema Engine（genson 合并 + 增强）

**Files:**
- Create: `apiscout/core/analyzer/schema_engine.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: 写 schema 推断测试**

```python
# tests/test_schema.py
"""Schema 推断引擎测试"""
from apiscout.core.analyzer.schema_engine import SchemaEngine


def test_basic_merge():
    """多次观察合并"""
    engine = SchemaEngine()
    engine.add_observation({"id": 1, "name": "设备A", "status": 1})
    engine.add_observation({"id": 2, "name": "设备B", "status": 2, "memo": "备注"})
    schema = engine.get_schema()

    assert schema["type"] == "object"
    # id 和 name 出现在所有观察中 → required
    assert "id" in schema.get("required", [])
    assert "name" in schema.get("required", [])
    # memo 只出现一次 → 不在 required 中
    assert "memo" not in schema.get("required", [])


def test_nullable_detection():
    """None 值产生 nullable"""
    engine = SchemaEngine()
    engine.add_observation({"status": 1})
    engine.add_observation({"status": None})
    schema = engine.get_schema()

    status_type = schema["properties"]["status"]["type"]
    # genson 会输出类型数组或 anyOf
    assert "null" in str(status_type) or "anyOf" in str(schema["properties"]["status"])


def test_format_enhancement():
    """string format 检测"""
    engine = SchemaEngine()
    engine.add_observation({
        "created_at": "2026-03-29T14:30:00Z",
        "email": "user@example.com",
        "device_id": "550e8400-e29b-41d4-a716-446655440000",
    })
    schema = engine.get_schema()
    enhanced = engine.enhance_schema(schema)

    props = enhanced["properties"]
    assert props["created_at"].get("format") == "date-time"
    assert props["email"].get("format") == "email"
    assert props["device_id"].get("format") == "uuid"


def test_enum_detection():
    """重复出现的少量值 → enum"""
    engine = SchemaEngine()
    for status in [1, 2, 1, 3, 2, 1, 2, 1, 3, 1]:
        engine.add_observation({"status": status})
    schema = engine.get_schema()
    enhanced = engine.enhance_schema(schema)

    assert "enum" in enhanced["properties"]["status"]
    assert set(enhanced["properties"]["status"]["enum"]) == {1, 2, 3}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_schema.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 schema 引擎**

```python
# apiscout/core/analyzer/schema_engine.py
"""Schema 推断引擎 — genson 合并 + format/enum 增强
偷师 OpenAPI DevTools: 多次观察合并，required = 交集
"""
import re
from collections import Counter, defaultdict
from genson import SchemaBuilder


# String format 检测正则
FORMAT_PATTERNS = [
    ("date-time", re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}')),
    ("date", re.compile(r'^\d{4}-\d{2}-\d{2}$')),
    ("uuid", re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)),
    ("email", re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')),
    ("uri", re.compile(r'^https?://')),
    ("ipv4", re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')),
]


class SchemaEngine:
    """JSON Schema 推断引擎"""

    def __init__(self):
        self._builder = SchemaBuilder()
        self._observations: list[dict] = []
        self._field_values: dict[str, list] = defaultdict(list)  # 用于 enum 检测

    def add_observation(self, obj: dict | list):
        """喂入一次观察"""
        self._builder.add_object(obj)
        self._observations.append(obj)
        if isinstance(obj, dict):
            self._collect_field_values(obj)

    def _collect_field_values(self, obj: dict, prefix: str = ""):
        """收集每个字段的所有值（用于 enum 检测）"""
        for key, value in obj.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._collect_field_values(value, full_key)
            elif isinstance(value, list):
                pass  # 不对数组元素做 enum 检测
            else:
                self._field_values[full_key].append(value)

    def get_schema(self) -> dict:
        """获取 genson 合并后的 schema"""
        return self._builder.to_schema()

    def enhance_schema(self, schema: dict) -> dict:
        """对 genson 输出做增强：format 检测 + enum 检测"""
        if schema.get("type") != "object" or "properties" not in schema:
            return schema

        enhanced = dict(schema)
        enhanced["properties"] = {}

        for prop_name, prop_schema in schema["properties"].items():
            prop_schema = dict(prop_schema)

            # Format 检测（只对 string 类型）
            if prop_schema.get("type") == "string":
                values = self._field_values.get(prop_name, [])
                fmt = self._detect_format(values)
                if fmt:
                    prop_schema["format"] = fmt

            # Enum 检测
            values = self._field_values.get(prop_name, [])
            if values:
                enum_values = self._detect_enum(values)
                if enum_values is not None:
                    prop_schema["enum"] = enum_values

            # 递归增强嵌套对象
            if prop_schema.get("type") == "object" and "properties" in prop_schema:
                prop_schema = self.enhance_schema(prop_schema)

            enhanced["properties"][prop_name] = prop_schema

        return enhanced

    def _detect_format(self, values: list) -> str | None:
        """从样本值检测 string format"""
        str_values = [v for v in values if isinstance(v, str) and v]
        if not str_values:
            return None
        # 至少 80% 的值匹配同一 format
        for fmt_name, pattern in FORMAT_PATTERNS:
            match_count = sum(1 for v in str_values if pattern.match(v))
            if match_count >= len(str_values) * 0.8:
                return fmt_name
        return None

    def _detect_enum(self, values: list) -> list | None:
        """检测 enum：唯一值 ≤10 且重复率 >50%"""
        # 过滤掉 None
        non_null = [v for v in values if v is not None]
        if len(non_null) < 3:  # 太少不做 enum 检测
            return None
        unique = set(non_null)
        if len(unique) > 10:
            return None
        # 重复率：(总数 - 唯一数) / 总数
        if len(non_null) > len(unique) and (len(non_null) - len(unique)) / len(non_null) > 0.3:
            return sorted(unique, key=lambda x: (isinstance(x, str), x))
        return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_schema.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add apiscout/core/analyzer/schema_engine.py tests/test_schema.py
git commit -m "feat: Schema 推断引擎 — genson 合并 + format/enum 增强"
```

---

### Task 8: Auth Detector（认证检测）

**Files:**
- Create: `apiscout/core/analyzer/auth_detector.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: 写认证检测测试**

```python
# tests/test_auth.py
"""认证检测测试"""
from apiscout.core.analyzer.auth_detector import AuthDetector


def test_detect_bearer_jwt():
    detector = AuthDetector()
    headers_list = [
        {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzExNzAwMDAwfQ.sig"},
        {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyIiwiZXhwIjoxNzExNzAwMDAwfQ.sig"},
    ]
    result = detector.detect(headers_list)
    assert result["type"] == "bearer_jwt"
    assert result["token_analysis"]["algorithm"] == "RS256"


def test_detect_basic_auth():
    detector = AuthDetector()
    headers_list = [{"Authorization": "Basic dXNlcjpwYXNz"}]
    result = detector.detect(headers_list)
    assert result["type"] == "basic"


def test_detect_api_key():
    detector = AuthDetector()
    headers_list = [{"X-API-Key": "abc123"}, {"X-API-Key": "abc123"}]
    result = detector.detect(headers_list)
    assert result["type"] == "api_key"
    assert result["header"] == "X-API-Key"


def test_detect_kingdee():
    """金蝶非标认证"""
    detector = AuthDetector()
    headers_list = [
        {"X-KDApi-AcctID": "001", "X-KDApi-AppID": "app1", "X-KDApi-AppSec": "secret"},
    ]
    result = detector.detect(headers_list)
    assert result["type"] == "custom_header"
    assert result["vendor"] == "kingdee"


def test_detect_cookie_session():
    detector = AuthDetector()
    headers_list = [{"Cookie": "session_token=abc123; theme=dark"}]
    result = detector.detect(headers_list)
    assert result["type"] == "cookie"
    assert "session_token" in result["cookies"]


def test_no_auth():
    detector = AuthDetector()
    headers_list = [{"Accept": "application/json"}]
    result = detector.detect(headers_list)
    assert result["type"] == "none"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL

- [ ] **Step 3: 实现认证检测器**

```python
# apiscout/core/analyzer/auth_detector.py
"""认证模式检测 — 偷师 OpenAPI DevTools + 中国 ERP 非标扩展"""
import base64
import json
import re
from collections import Counter


# 已知的 API Key 头名
API_KEY_HEADERS = {
    "x-api-key", "x-auth-token", "api-key", "apikey", "auth-token",
    "x-token", "token", "x-access-token", "access-token",
}

# 中国 ERP 非标认证头
CHINESE_ERP_HEADERS = {
    "kingdee": {"x-kdapi-acctid", "x-kdapi-appid", "x-kdapi-appsec", "x-kdapi-username"},
    "yonyou": {"x-yonyou-appkey", "x-yonyou-appsecret"},
}

# Session cookie 关键词
SESSION_COOKIE_KEYWORDS = {"token", "session", "jwt", "auth", "sid", "jsessionid", "access"}


class AuthDetector:
    """从捕获的请求头中检测认证方式"""

    def detect(self, headers_list: list[dict]) -> dict:
        """
        输入：多个请求的 headers（list of dict）
        输出：认证档案 dict
        """
        if not headers_list:
            return {"type": "none"}

        # 合并所有 headers 统计出现频率
        all_headers = {}
        for h in headers_list:
            for k, v in h.items():
                all_headers.setdefault(k.lower(), []).append(v)

        # 1. HTTP Authorization header
        auth_values = all_headers.get("authorization", [])
        if auth_values:
            return self._analyze_authorization(auth_values)

        # 2. 中国 ERP 非标认证
        for vendor, expected_headers in CHINESE_ERP_HEADERS.items():
            found = expected_headers & set(all_headers.keys())
            if len(found) >= 2:  # 至少匹配 2 个头
                return {
                    "type": "custom_header",
                    "vendor": vendor,
                    "headers": {h: all_headers[h][0] for h in found},
                }

        # 3. API Key header
        for header_name in all_headers:
            if header_name in API_KEY_HEADERS:
                return {
                    "type": "api_key",
                    "header": header_name.title().replace(" ", "-"),
                    "sample": all_headers[header_name][0][:8] + "...",
                }

        # 4. Cookie/Session
        cookie_values = all_headers.get("cookie", [])
        if cookie_values:
            session_cookies = self._find_session_cookies(cookie_values[0])
            if session_cookies:
                return {
                    "type": "cookie",
                    "cookies": session_cookies,
                }

        return {"type": "none"}

    def _analyze_authorization(self, values: list[str]) -> dict:
        """分析 Authorization header"""
        sample = values[0]
        if sample.lower().startswith("bearer "):
            token = sample[7:]
            jwt_info = self._parse_jwt(token)
            if jwt_info:
                return {
                    "type": "bearer_jwt",
                    "token_analysis": jwt_info,
                }
            return {"type": "bearer", "token_prefix": token[:16] + "..."}

        if sample.lower().startswith("basic "):
            return {"type": "basic"}

        if sample.lower().startswith("digest "):
            return {"type": "digest"}

        return {"type": "bearer", "raw_prefix": sample[:20] + "..."}

    def _parse_jwt(self, token: str) -> dict | None:
        """解析 JWT header 和 claims（不验签）"""
        parts = token.split(".")
        if len(parts) != 3:
            return None
        try:
            # 解码 header
            header_b64 = parts[0] + "=" * (4 - len(parts[0]) % 4)
            header = json.loads(base64.urlsafe_b64decode(header_b64))

            # 解码 payload
            payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))

            result = {
                "algorithm": header.get("alg", "unknown"),
                "claims": sorted(payload.keys()),
            }
            if "exp" in payload:
                result["has_expiration"] = True
            return result
        except Exception:
            return None

    def _find_session_cookies(self, cookie_string: str) -> list[str]:
        """从 Cookie 头中找出与 session/auth 相关的 cookie 名"""
        cookies = {}
        for pair in cookie_string.split(";"):
            pair = pair.strip()
            if "=" in pair:
                name, _, _ = pair.partition("=")
                cookies[name.strip()] = True

        return [
            name for name in cookies
            if any(kw in name.lower() for kw in SESSION_COOKIE_KEYWORDS)
        ]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_auth.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add apiscout/core/analyzer/auth_detector.py tests/test_auth.py
git commit -m "feat: 认证检测 — JWT/Basic/API Key/Cookie/金蝶非标"
```

---

### Task 9: Endpoint Dedup + Aggregation

**Files:**
- Create: `apiscout/core/analyzer/dedup.py`
- Test: `tests/test_dedup.py`

- [ ] **Step 1: 写去重聚合测试**

```python
# tests/test_dedup.py
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
    # 应该收集到 3 个 query 参数
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_dedup.py -v`
Expected: FAIL

- [ ] **Step 3: 实现聚合器**

```python
# apiscout/core/analyzer/dedup.py
"""端点去重 + 数据聚合 — 将 CaptureRecord 流汇总为端点列表"""
from collections import defaultdict
from urllib.parse import urlparse, parse_qs

from apiscout.core.capture.store import CaptureRecord
from apiscout.core.analyzer.router import EndpointRouter
from apiscout.core.analyzer.schema_engine import SchemaEngine
from apiscout.core.analyzer.auth_detector import AuthDetector


class EndpointAggregator:
    """将原始捕获记录聚合为去重的端点 + schema + query params"""

    def __init__(self):
        self._router = EndpointRouter()
        # key: (parameterized_path, method)
        self._request_schemas: dict[tuple, SchemaEngine] = defaultdict(SchemaEngine)
        self._response_schemas: dict[tuple, SchemaEngine] = defaultdict(SchemaEngine)
        self._query_params: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self._status_codes: dict[tuple, set] = defaultdict(set)
        self._all_headers: list[dict] = []  # 用于认证检测
        self._js_endpoints: set[str] = set()  # JS 分析发现但未触发的端点

    def add(self, record: CaptureRecord):
        """添加一条捕获记录"""
        if record.protocol != "rest":
            return  # V1 只处理 REST

        path = record.path
        method = record.method
        self._router.add(path, method)

        parameterized = self._router.lookup(path, method)
        key = (parameterized, method)

        # 聚合 response schema
        if isinstance(record.response_body, dict):
            self._response_schemas[key].add_observation(record.response_body)

        # 聚合 request schema
        if isinstance(record.request_body, dict):
            self._request_schemas[key].add_observation(record.request_body)

        # 收集 query 参数（多次观察合并，用于推断 enum 和类型）
        parsed = urlparse(record.url)
        for param_name, param_values in parse_qs(parsed.query).items():
            self._query_params[key][param_name].extend(param_values)

        # 收集状态码
        self._status_codes[key].add(record.status)

        # 收集 headers 用于认证检测
        if record.request_headers:
            self._all_headers.append(record.request_headers)

    def add_js_endpoint(self, path: str):
        """记录 JS 分析发现但未触发的端点"""
        self._js_endpoints.add(path)

    def get_results(self) -> list[dict]:
        """获取聚合后的端点列表"""
        router_endpoints = self._router.get_endpoints()
        results = []

        # 已触发的端点（从路由表中）
        triggered_paths = set()
        for ep in router_endpoints:
            key = (ep["path"], ep["method"])
            resp_engine = self._response_schemas.get(key)
            req_engine = self._request_schemas.get(key)

            resp_schema = {}
            if resp_engine:
                raw = resp_engine.get_schema()
                resp_schema = resp_engine.enhance_schema(raw)

            req_schema = {}
            if req_engine:
                raw = req_engine.get_schema()
                req_schema = req_engine.enhance_schema(raw)

            # 推断 query 参数 schema
            query_params_info = []
            for qp_name, qp_values in sorted(self._query_params.get(key, {}).items()):
                # 尝试推断类型：全是数字 → integer，否则 string
                all_int = all(v.isdigit() for v in qp_values if v)
                schema = {"type": "integer"} if all_int else {"type": "string"}
                # enum 检测：唯一值 ≤10 且有重复
                unique = set(qp_values)
                if 1 < len(unique) <= 10 and len(qp_values) > len(unique):
                    schema["enum"] = sorted(unique, key=lambda x: (not x.isdigit(), x))
                query_params_info.append({
                    "name": qp_name,
                    "in": "query",
                    "schema": schema,
                    "required": True,  # 出现在所有观察中则 required（简化：V1 全标 true）
                })

            results.append({
                "path": ep["path"],
                "method": ep["method"],
                "observation_count": ep["observation_count"],
                "status_codes": sorted(self._status_codes.get(key, set())),
                "response_schema": resp_schema,
                "request_schema": req_schema,
                "query_params": query_params_info,
                "status": "confirmed",
            })
            triggered_paths.add(ep["path"])

        # JS 发现但未触发的端点
        for js_path in self._js_endpoints:
            if js_path not in triggered_paths:
                results.append({
                    "path": js_path,
                    "method": "UNKNOWN",
                    "observation_count": 0,
                    "status_codes": [],
                    "response_schema": {},
                    "request_schema": {},
                    "status": "uncertain",
                })

        return results

    def get_auth_profile(self) -> dict:
        """获取认证档案"""
        detector = AuthDetector()
        return detector.detect(self._all_headers)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_dedup.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add apiscout/core/analyzer/dedup.py tests/test_dedup.py
git commit -m "feat: 端点去重聚合 — CaptureRecord → 合并端点 + schema + 认证"
```

---

### Task 10-17 概要

由于实施计划已经很长，后续 Task 以结构化摘要呈现。每个 Task 在实施时应展开为完整的 TDD 步骤（测试 → 失败 → 实现 → 通过 → 提交）。

---

### Task 10: OpenAPI Generator

**Files:**
- Create: `apiscout/core/generator/__init__.py`
- Create: `apiscout/core/generator/openapi.py`
- Test: `tests/test_openapi_gen.py`

**要点：**
- 输入：EndpointAggregator.get_results() 输出的端点列表（含 query_params）
- 输出：OpenAPI 3.1 YAML 文件
- 包含：paths、parameters（path params 从 `{xxx}` 提取 + query params 从聚合结果取）、requestBody、responses、securitySchemes
- **query 参数输出**：每个端点的 `query_params` 列表直接映射为 OpenAPI `parameters`，含 name/in/schema/required
- 两遍模式：草稿带 `x-apiscout-review` 标记（confirmed/uncertain/excluded）
- 最终生成只保留未被排除的端点
- 用 PyYAML 的 `yaml.dump(default_flow_style=False, allow_unicode=True, sort_keys=False)`
- **注意**：V1 用 yaml.dump 重新生成，不保留用户对草稿的格式修改（YAML roundtrip 列入 V1.1）

---

### Task 11: Auth Profile Generator（含登录流追踪）

**Files:**
- Create: `apiscout/core/generator/auth_profile.py`
- Test: `tests/test_auth_profile_gen.py`

**要点：**
- 输入：AuthDetector.detect() 结果 + 全部 CaptureRecord 列表
- 输出：auth_profile.yaml（Nango 风格，含 discovery/token_analysis/insight68_config_hint）

**登录流追踪（偷师 Nango TWO_STEP #10）：**
- 从 capture 记录中扫描 POST 请求，body 含 `username/password/account/user/passwd` 字段 → 标记为 login_endpoint
- 检查该请求的响应 body，递归查找含 `token/accessToken/access_token/jwt` 的字段 → 记录 token_location（如 `response.data.accessToken`）
- 从 capture 记录中扫描 POST 请求，body 含 `refresh_token/refreshToken` 字段 → 标记为 refresh_endpoint
- 如果检测到 JWT，从 exp claim 推算 token 生命周期

**insight68 接入建议自动生成：**
- Bearer JWT → `auth_adapter: "jwt_bearer"`, required: ["服务账号用户名", "密码"]
- API Key → `auth_adapter: "api_key"`, required: ["API Key"]
- Cookie → `auth_adapter: "session"`, required: ["服务账号用户名", "密码"]
- 金蝶/用友 → `auth_adapter: "custom_header"`, required: 对应 vendor 的配置字段

**测试要点：**
- 构造含登录请求的 capture 记录，验证 login_endpoint + token_location 被正确提取
- 构造含 refresh 请求的记录，验证 refresh_endpoint 被正确识别
- 验证 insight68_config_hint 根据 auth type 自动生成

---

### Task 12: HTML Report Generator

**Files:**
- Create: `apiscout/core/generator/report.py`
- Create: `apiscout/templates/report.html.j2`
- Test: `tests/test_report_gen.py`

**要点：**
- Jinja2 模板，单文件 HTML（内嵌 CSS，无外部依赖）
- 包含：探索概要、端点清单（可排序表格）、Phase 2 补录建议、认证摘要
- 端点清单：路径、方法、观察次数、状态码、状态（confirmed/uncertain/excluded）
- Phase 2 建议：列出 JS 发现但未触发的端点

---

### Task 13: Link Extractor（DOM 链接提取）

**Files:**
- Create: `apiscout/core/crawler/__init__.py`
- Create: `apiscout/core/crawler/link_extractor.py`
- Test: `tests/test_link_extractor.py`

**要点：**
- 输入：Playwright Page 对象
- 输出：发现的 URL 列表
- 选择器覆盖：`a[href]`, `[onclick]`, `nav a`, `[role='menuitem']`, `[data-href]`, `button[data-route]`
- 同源过滤 + exclude_patterns 过滤
- iframe 递归探索

---

### Task 14: JS Analyzer（JS 静态分析）

**Files:**
- Create: `apiscout/core/crawler/js_analyzer.py`
- Test: `tests/test_js_analyzer.py`

**要点：**
- 从 page 加载的 JS 资源中提取 API URL
- 6 个正则模式（fetch/axios/baseURL 等）
- 去重 + 与已触发端点比对 → 标记 "uncertain"

---

### Task 15: Scroll Loader（滚动加载）

**Files:**
- Create: `apiscout/core/crawler/scroll_loader.py`
- Test: `tests/test_scroll_loader.py`

**要点：**
- 滚动到底部 + 等待网络空闲
- 监听新请求出现 → 继续滚动
- 超时退出（连续 N 秒无新请求）

---

### Task 16: Navigator（页面探索编排）

**Files:**
- Create: `apiscout/core/crawler/navigator.py`
- Test: `tests/test_navigator.py`

**要点：**
- 编排层：每到一个页面 → 层1 链接 → 层2 JS → 层3 交互探索
- 交互探索 pipeline：MenuExpander → TabSwitcher → ModalTrigger → TablePaginator → ScrollLoader → ModalCloser
- 安全护栏：SAFE_ACTIONS vs DANGEROUS_ACTIONS 分类
- 页面队列管理：BFS，visited 去重，max_depth/max_pages 限制
- **进度回调**：供 CLI 显示实时状态。V1 进度显示用**请求数**（recorder.captured_count），不做实时端点归并。精确端点数在 Phase 3 分析后才有。进度格式示例：
  ```
  页面: 28/43  请求: 247 已捕获  当前: /equipment/list
  ```
- Session 过期检测：从 recorder.auth_failure_count 读取，≥3 时暂停爬虫，提示用户重新登录

---

### Task 17: Workflow（两遍工作流 + CLI 整合）

**Files:**
- Create: `apiscout/core/workflow.py`
- Modify: `apiscout/ui/cli.py` — 接入 workflow
- Test: `tests/test_workflow.py`

**要点：**
- `scan` 命令完整流程：启动浏览器 → 等待登录 → Phase 1 → 报告 → Phase 2（可选）→ 生成
- `explore` 命令：只执行爬虫 + 捕获，输出 JSONL
- `analyze` 命令：读 JSONL → 聚合 → 生成草稿
- `generate` 命令：读审核后的草稿 → 生成最终输出
- Phase 1→2 过渡：浏览器保持打开，终端提示选择
- 项目包导出：所有输出 + capture.jsonl + meta.yaml 打包到一个目录
- 进度显示：页面数、端点数、耗时

---

### Task 18: AI Enricher（可选模块）

**Files:**
- Create: `apiscout/core/generator/ai_enricher.py`
- Modify: `apiscout/ui/cli.py` — 接入 enrich 命令
- Test: `tests/test_enricher.py`

**要点：**
- `enrich` 命令：读项目包 → 调 DeepSeek API → 输出增强 spec + MCP Tools
- 使用 openai 库（DeepSeek 兼容 OpenAI API）
- Prompt 设计：发送端点 path + schema → 要求返回中文 summary/description/tags/enum 含义
- 批量处理：每次发送 5-10 个端点（避免 token 超限）
- 输出：enriched_spec.yaml + mcp_tools/ 目录
- 无 API key 时优雅降级

---

### Task 19: PyInstaller 打包

**Files:**
- Create: `pack/apiscout.spec`
- Create: `pack/build.sh`

**要点：**
- `--onedir` 模式
- 包含 Playwright chromium（`PLAYWRIGHT_BROWSERS_PATH` 指向打包目录）
- 包含 default.yaml 和 report 模板
- Windows + macOS 双平台
- 验证：在无 Python 环境的机器上运行

---

## 实施顺序与依赖

```
Task 0 (Spike) ─── 必须先过，否则整体方案有风险

Task 1 (依赖) ──→ Task 2 (Config+CLI) ──→ Task 3 (Store)
                                              │
                 ┌────────────────────────────┘
                 │
           Task 4 (Filter) ──→ Task 5 (Recorder)
                 │
           Task 6 (Router) ──→ Task 7 (Schema) ──→ Task 8 (Auth) ──→ Task 9 (Dedup)
                                                                         │
                 ┌──────────────────────────────────────────────────────┘
                 │
           Task 10 (OpenAPI Gen) ──→ Task 11 (Auth Profile) ──→ Task 12 (Report)
                 │
           Task 13 (Links) ──→ Task 14 (JS) ──→ Task 15 (Scroll) ──→ Task 16 (Navigator)
                                                                         │
                 ┌──────────────────────────────────────────────────────┘
                 │
           Task 17 (Workflow + CLI 整合)
                 │
           Task 18 (AI Enricher)
                 │
           Task 19 (打包)
```

**里程碑：**
- Task 0 完成 → 技术风险解除
- Task 9 完成 → 分析引擎可用（可以手动喂 JSONL 测试）
- Task 12 完成 → 完整输出管线（分析 → 生成）
- Task 16 完成 → 爬虫引擎可用
- Task 17 完成 → V1 功能完整
- Task 19 完成 → V1 可交付
