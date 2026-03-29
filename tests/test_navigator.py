"""Navigator 页面探索编排测试 — 测试编排逻辑，不启动浏览器"""
import pytest

from apiscout.core.crawler.navigator import (
    NavigatorConfig,
    PageQueue,
    classify_action,
)


class TestPageQueue:

    def test_add_and_pop(self):
        q = PageQueue(max_pages=100, max_depth=5)
        q.add("https://ex.com/page1", depth=0)
        q.add("https://ex.com/page2", depth=1)

        url, depth = q.pop()
        assert url == "https://ex.com/page1"
        assert depth == 0

    def test_skip_visited(self):
        q = PageQueue(max_pages=100, max_depth=5)
        q.add("https://ex.com/page1", depth=0)
        q.add("https://ex.com/page1", depth=1)  # 重复

        assert q.size() == 1

    def test_skip_beyond_max_depth(self):
        q = PageQueue(max_pages=100, max_depth=2)
        q.add("https://ex.com/deep", depth=3)  # 超过最大深度

        assert q.size() == 0

    def test_skip_beyond_max_pages(self):
        q = PageQueue(max_pages=2, max_depth=5)
        q.add("https://ex.com/p1", depth=0)
        q.add("https://ex.com/p2", depth=0)
        q.add("https://ex.com/p3", depth=0)  # 超过最大页面数

        assert q.size() == 2

    def test_empty(self):
        q = PageQueue(max_pages=100, max_depth=5)
        assert q.is_empty()
        q.add("https://ex.com/page1", depth=0)
        assert not q.is_empty()

    def test_visited_urls(self):
        """预加载已访问 URL（用于 --resume）"""
        q = PageQueue(max_pages=100, max_depth=5)
        q.mark_visited("https://ex.com/old")
        q.add("https://ex.com/old", depth=0)  # 不会被加入
        assert q.size() == 0

    def test_stats(self):
        q = PageQueue(max_pages=100, max_depth=5)
        q.add("https://ex.com/p1", depth=0)
        q.add("https://ex.com/p2", depth=0)
        q.pop()

        stats = q.stats()
        assert stats["visited"] == 1
        assert stats["pending"] == 1
        assert stats["total_discovered"] == 2


class TestClassifyAction:

    def test_safe_actions(self):
        """安全操作识别"""
        assert classify_action("查看详情") == "safe"
        assert classify_action("搜索") == "safe"
        assert classify_action("view detail") == "safe"
        assert classify_action("export") == "safe"

    def test_dangerous_actions(self):
        """危险操作识别"""
        assert classify_action("删除") == "dangerous"
        assert classify_action("提交审批") == "dangerous"
        assert classify_action("delete item") == "dangerous"
        assert classify_action("confirm order") == "dangerous"

    def test_unknown_actions(self):
        """未知操作默认安全"""
        assert classify_action("some random text") == "unknown"


class TestNavigatorConfig:

    def test_default_config(self):
        cfg = NavigatorConfig()
        assert cfg.max_depth == 5
        assert cfg.max_pages == 200
        assert cfg.request_delay == 0.5

    def test_from_dict(self):
        cfg = NavigatorConfig.from_config({
            "crawl": {"max_depth": 3, "max_pages": 50, "request_delay": 1.0}
        })
        assert cfg.max_depth == 3
        assert cfg.max_pages == 50
        assert cfg.request_delay == 1.0
