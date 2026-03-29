"""滚动加载测试 — 测试逻辑函数，不启动浏览器"""
from apiscout.core.crawler.scroll_loader import ScrollConfig, should_continue_scrolling


def test_default_config():
    """默认配置"""
    cfg = ScrollConfig()
    assert cfg.max_scrolls == 10
    assert cfg.idle_timeout == 3.0
    assert cfg.scroll_delay == 0.5


def test_should_continue_initial():
    """初始状态应该继续滚动"""
    assert should_continue_scrolling(
        scroll_count=0,
        max_scrolls=10,
        new_requests_since_last=0,
        consecutive_idle=0,
        max_idle=3,
    )


def test_should_stop_max_scrolls():
    """达到最大滚动次数时停止"""
    assert not should_continue_scrolling(
        scroll_count=10,
        max_scrolls=10,
        new_requests_since_last=5,
        consecutive_idle=0,
        max_idle=3,
    )


def test_should_stop_idle():
    """连续无新请求时停止"""
    assert not should_continue_scrolling(
        scroll_count=3,
        max_scrolls=10,
        new_requests_since_last=0,
        consecutive_idle=3,
        max_idle=3,
    )


def test_should_continue_with_new_requests():
    """有新请求时继续"""
    assert should_continue_scrolling(
        scroll_count=5,
        max_scrolls=10,
        new_requests_since_last=2,
        consecutive_idle=0,
        max_idle=3,
    )
