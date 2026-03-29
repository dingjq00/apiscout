"""页面探索编排 — BFS + 交互式探索 pipeline + 安全护栏"""
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


# 安全操作关键词（中英文）
SAFE_KEYWORDS = [
    "查看", "详情", "搜索", "筛选", "导出", "刷新", "展开", "收起", "列表", "返回",
    "view", "detail", "search", "filter", "export", "refresh", "expand", "collapse", "list", "back",
]

# 危险操作关键词（中英文）
DANGEROUS_KEYWORDS = [
    "删除", "提交", "审批", "确认", "发送", "保存", "新建", "编辑", "修改", "撤销",
    "delete", "submit", "approve", "confirm", "send", "save", "create", "edit", "modify", "revoke",
]

# 默认排除路径模式
_DEFAULT_EXCLUDE_PATTERNS = [
    "/logout",
    "/static/*",
    "/assets/*",
    "/favicon.ico",
]


def classify_action(text: str) -> str:
    """分类按钮/链接文本为 safe/dangerous/unknown"""
    text_lower = text.lower()
    for kw in DANGEROUS_KEYWORDS:
        if kw in text_lower:
            return "dangerous"
    for kw in SAFE_KEYWORDS:
        if kw in text_lower:
            return "safe"
    return "unknown"


@dataclass
class NavigatorConfig:
    """导航器配置"""
    max_depth: int = 5
    max_pages: int = 200
    page_timeout: int = 30           # 秒
    network_idle_wait: int = 3       # 秒
    request_delay: float = 0.5      # 秒
    exclude_patterns: list[str] = field(
        default_factory=lambda: list(_DEFAULT_EXCLUDE_PATTERNS)
    )

    @classmethod
    def from_config(cls, config: dict) -> "NavigatorConfig":
        """从配置字典创建"""
        crawl = config.get("crawl", {})
        return cls(
            max_depth=crawl.get("max_depth", 5),
            max_pages=crawl.get("max_pages", 200),
            page_timeout=crawl.get("page_timeout", 30),
            network_idle_wait=crawl.get("network_idle_wait", 3),
            request_delay=crawl.get("request_delay", 0.5),
            exclude_patterns=crawl.get("exclude_patterns", list(_DEFAULT_EXCLUDE_PATTERNS)),
        )


class PageQueue:
    """BFS 页面队列 — 去重 + 深度限制 + 页面数限制"""

    def __init__(self, max_pages: int = 200, max_depth: int = 5):
        self.max_pages = max_pages
        self.max_depth = max_depth
        self._queue: deque[tuple[str, int]] = deque()  # (url, depth)
        self._visited: set[str] = set()
        self._discovered: set[str] = set()

    def add(self, url: str, depth: int):
        """添加 URL 到队列，已访问/已发现/超深度/超数量则跳过"""
        if url in self._visited or url in self._discovered:
            return
        if depth > self.max_depth:
            return
        if len(self._discovered) >= self.max_pages:
            return
        self._discovered.add(url)
        self._queue.append((url, depth))

    def pop(self) -> tuple[str, int]:
        """取出下一个要访问的 URL，并标记为已访问"""
        url, depth = self._queue.popleft()
        self._visited.add(url)
        return url, depth

    def is_empty(self) -> bool:
        """队列是否为空"""
        return len(self._queue) == 0

    def size(self) -> int:
        """队列中待访问的 URL 数量"""
        return len(self._queue)

    def mark_visited(self, url: str):
        """标记为已访问（用于 --resume 恢复断点）"""
        self._visited.add(url)
        self._discovered.add(url)

    def stats(self) -> dict:
        """返回队列统计信息"""
        return {
            "visited": len(self._visited),
            "pending": len(self._queue),
            "total_discovered": len(self._discovered),
        }


@dataclass
class ExplorationProgress:
    """探索进度快照"""
    pages_visited: int = 0
    pages_total: int = 0
    requests_captured: int = 0
    current_url: str = ""


async def explore_pages(
    page,
    start_url: str,
    recorder,
    config: NavigatorConfig | None = None,
    progress_callback: Callable[[ExplorationProgress], None] | None = None,
    visited_urls: set[str] | None = None,
) -> dict:
    """
    BFS 探索所有页面。

    page:              Playwright Page 对象
    start_url:         起始 URL
    recorder:          PageRecorder 实例（读取 captured_count / auth_failure_count）
    config:            导航器配置
    progress_callback: 进度回调
    visited_urls:      已访问的 URL 集合（用于 --resume 恢复）

    返回汇总字典：pages_visited / total_discovered / requests_captured / js_endpoints
    """
    import asyncio
    from urllib.parse import urlparse

    from apiscout.core.crawler.js_analyzer import extract_api_endpoints_from_js
    from apiscout.core.crawler.link_extractor import extract_links_from_html
    from apiscout.core.crawler.scroll_loader import ScrollConfig, scroll_page

    config = config or NavigatorConfig()
    base_parsed = urlparse(start_url)
    base_origin = f"{base_parsed.scheme}://{base_parsed.netloc}"

    queue = PageQueue(max_pages=config.max_pages, max_depth=config.max_depth)

    # 预加载已访问 URL（--resume）
    if visited_urls:
        for url in visited_urls:
            queue.mark_visited(url)

    queue.add(start_url, depth=0)
    js_endpoints: list[str] = []

    while not queue.is_empty():
        url, depth = queue.pop()

        # Session 过期检测 — 连续 3 次认证失败则暂停
        if recorder.auth_failure_count >= 3:
            logger.warning("Session 可能已过期（连续认证失败 %d 次），暂停探索", recorder.auth_failure_count)
            break

        # 导航到页面
        try:
            await page.goto(url, timeout=config.page_timeout * 1000, wait_until="domcontentloaded")
            # DOM 加载后等一段时间让 API 请求发出
            await asyncio.sleep(config.network_idle_wait)
        except Exception as e:
            logger.warning("导航失败: %s → %s", url, e)
            continue

        await asyncio.sleep(config.request_delay)

        # 进度回调
        if progress_callback:
            progress = ExplorationProgress(
                pages_visited=queue.stats()["visited"],
                pages_total=queue.stats()["total_discovered"],
                requests_captured=recorder.captured_count,
                current_url=url,
            )
            progress_callback(progress)

        logger.info(
            "探索: [%d/%d] %s (深度=%d, 已捕获=%d)",
            queue.stats()["visited"],
            queue.stats()["total_discovered"],
            url,
            depth,
            recorder.captured_count,
        )

        # 层 1：DOM 链接提取
        try:
            html = await page.content()
            new_links = extract_links_from_html(
                html, base_url=base_origin, exclude_patterns=config.exclude_patterns
            )
            for link in new_links:
                queue.add(link, depth=depth + 1)
        except Exception as e:
            logger.warning("链接提取失败: %s", e)

        # 层 2：JS 静态分析（同源脚本，最多处理 20 个）
        try:
            scripts = await page.evaluate("""
                () => Array.from(document.querySelectorAll('script[src]'))
                         .map(s => s.src)
                         .filter(s => s.startsWith(window.location.origin))
            """)
            for script_url in scripts[:20]:
                try:
                    resp = await page.evaluate(f"fetch('{script_url}').then(r => r.text())")
                    endpoints = extract_api_endpoints_from_js(resp)
                    js_endpoints.extend(endpoints)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("JS 分析跳过: %s", e)

        # 层 3：滚动加载（触发懒加载/分页）
        try:
            scroll_cfg = ScrollConfig(max_scrolls=5, idle_timeout=2.0)
            await scroll_page(
                page,
                config=scroll_cfg,
                request_counter=lambda: recorder.captured_count,
            )
        except Exception as e:
            logger.debug("滚动加载跳过: %s", e)

    return {
        "pages_visited": queue.stats()["visited"],
        "total_discovered": queue.stats()["total_discovered"],
        "requests_captured": recorder.captured_count,
        "js_endpoints": list(set(js_endpoints)),
    }
