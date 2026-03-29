"""滚动加载触发 — 偷师 Crawlee 的 infinite_scroll"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScrollConfig:
    """滚动配置"""
    max_scrolls: int = 10        # 最大滚动次数
    idle_timeout: float = 3.0    # 无新请求超时（秒）
    scroll_delay: float = 0.5    # 每次滚动间隔（秒）
    max_idle: int = 3            # 连续无新请求的轮次上限


def should_continue_scrolling(
    scroll_count: int,
    max_scrolls: int,
    consecutive_idle: int,
    max_idle: int,
) -> bool:
    """判断是否应该继续滚动"""
    if scroll_count >= max_scrolls:
        return False
    if consecutive_idle >= max_idle:
        return False
    return True


async def scroll_page(page, config: ScrollConfig | None = None, request_counter=None):
    """
    滚动页面加载更多内容。

    page: Playwright Page 对象
    config: 滚动配置
    request_counter: 可调用对象，返回当前已捕获的请求数
    """
    import asyncio

    config = config or ScrollConfig()
    scroll_count = 0
    consecutive_idle = 0
    last_request_count = request_counter() if request_counter else 0

    while should_continue_scrolling(scroll_count, config.max_scrolls, consecutive_idle, config.max_idle):
        # 滚动到底部
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(config.scroll_delay)

        # 等待网络空闲
        try:
            await page.wait_for_load_state("networkidle", timeout=config.idle_timeout * 1000)
        except Exception:
            pass

        scroll_count += 1

        # 检查是否有新请求
        if request_counter:
            current_count = request_counter()
            new_requests = current_count - last_request_count
            if new_requests > 0:
                consecutive_idle = 0
                last_request_count = current_count
                logger.debug("滚动 %d: 发现 %d 个新请求", scroll_count, new_requests)
            else:
                consecutive_idle += 1
                logger.debug("滚动 %d: 无新请求 (连续空闲 %d 次)", scroll_count, consecutive_idle)
        else:
            consecutive_idle += 1

    logger.info("滚动加载完成: %d 次滚动", scroll_count)
