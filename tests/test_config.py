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
