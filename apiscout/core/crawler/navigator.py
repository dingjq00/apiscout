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


async def _explore_spa_menus(page, recorder, config, known_urls: set | None = None) -> list[str]:
    """SPA 菜单点击探索 — 不依赖特定 CSS 选择器，通用发现导航项

    策略：在页面顶部/侧边导航区域找到所有可见的短文本可点击元素，
    逐个点击并观察 URL 变化和新请求产生。
    """
    import asyncio

    logger.info("SPA 菜单探索开始 (当前 URL: %s)", page.url)

    # 用 JS 在页面里找到导航项 — 不依赖特定框架选择器
    nav_items = await page.evaluate("""
        () => {
            // 找导航容器：header、nav、sidebar、或含 menu/nav/header 类名的元素
            const containers = document.querySelectorAll(
                'header, nav, aside, [class*="menu"], [class*="nav"], [class*="sidebar"], [class*="side"], [class*="aside"], [class*="header"], [class*="tab"]'
            );

            const items = new Set();
            const seen_texts = new Set();

            for (const container of containers) {
                // 找容器内所有可见的叶子元素（有文本、没有子块元素的）
                const candidates = container.querySelectorAll('a, div, span, li, button');
                for (const el of candidates) {
                    const text = el.textContent.trim();
                    // 过滤：有文本、文本短（菜单项通常 < 10 字）、不重复
                    if (!text || text.length > 15 || text.length < 2) continue;
                    if (seen_texts.has(text)) continue;
                    // 必须可见
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    // 排除：在页面很下方的不太可能是导航
                    if (rect.top > 600) continue;
                    // 尽量选叶子节点（没有块级子元素）
                    const hasBlockChild = Array.from(el.children).some(
                        c => ['DIV','UL','OL','TABLE'].includes(c.tagName)
                    );
                    if (hasBlockChild) continue;

                    seen_texts.add(text);
                    // 返回元素的唯一选择器路径
                    let selector = '';
                    if (el.id) {
                        selector = '#' + el.id;
                    } else {
                        // 构建 nth-child 路径
                        let path = [];
                        let current = el;
                        while (current && current !== document.body) {
                            let idx = 1;
                            let sib = current.previousElementSibling;
                            while (sib) { idx++; sib = sib.previousElementSibling; }
                            path.unshift(current.tagName.toLowerCase() + ':nth-child(' + idx + ')');
                            current = current.parentElement;
                        }
                        selector = 'body > ' + path.join(' > ');
                    }
                    items.add(JSON.stringify({text, selector, top: rect.top}));
                }
            }
            return Array.from(items).map(s => JSON.parse(s));
        }
    """)

    if not nav_items:
        logger.info("未找到导航项")
        return []

    logger.info("发现 %d 个可能的导航项", len(nav_items))
    for item in nav_items[:10]:
        logger.info("  [%.0fpx] %s", item["top"], item["text"])

    discovered_urls = set()
    original_url = page.url

    for item in nav_items:
        text = item["text"]
        selector = item["selector"]

        # 安全检查
        action = classify_action(text)
        if action == "dangerous":
            logger.debug("  跳过危险: %s", text)
            continue

        before_count = recorder.captured_count

        try:
            el = await page.query_selector(selector)
            if not el:
                continue
            await el.click(timeout=5000)
            await asyncio.sleep(config.network_idle_wait)
        except Exception:
            continue

        new_url = page.url
        after_count = recorder.captured_count
        new_requests = after_count - before_count
        all_known = discovered_urls | (known_urls or set())
        url_changed = new_url != original_url and new_url not in all_known

        if url_changed:
            discovered_urls.add(new_url)

        if url_changed or new_requests > 0:
            logger.info("  点击: %s → %s (新增 %d 请求)", text, new_url[-50:], new_requests)

    # 回到原始页面
    if page.url != original_url:
        try:
            await page.goto(original_url, timeout=config.page_timeout * 1000,
                          wait_until="domcontentloaded")
            await asyncio.sleep(1)
        except Exception:
            pass

    return list(discovered_urls)


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

        # 层 1.5：SPA 菜单点击探索（Vue/React 等 SPA 框架的菜单没有 href）
        if depth <= 1:  # 首页 + 一级页面都做菜单探索
            try:
                # 传入已知 URL，避免重复点击已访问的路由（防死循环）
                all_known_urls = queue._visited | queue._discovered
                menu_urls = await _explore_spa_menus(page, recorder, config, known_urls=all_known_urls)
                for menu_url in menu_urls:
                    queue.add(menu_url, depth=depth + 1)
                if menu_urls:
                    logger.info("SPA 菜单探索发现 %d 个路由", len(menu_urls))
            except Exception as e:
                logger.warning("SPA 菜单探索失败: %s: %s", type(e).__name__, e)

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
