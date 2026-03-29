"""适配器框架测试"""
from apiscout.adapters.registry import (
    get_all_adapters, BaseAdapter, FrameworkMatch,
)


def test_adapters_registered():
    """导入后适配器自动注册"""
    import apiscout.adapters.jmix  # noqa: F401
    import apiscout.adapters.spring_boot  # noqa: F401
    import apiscout.adapters.ruoyi  # noqa: F401

    adapters = get_all_adapters()
    names = {a.name for a in adapters}
    assert "Jmix" in names
    assert "Spring Boot" in names
    assert "若依 (RuoYi)" in names


def test_base_adapter_interface():
    """BaseAdapter 基类定义了必需的接口"""
    adapter = BaseAdapter()
    assert hasattr(adapter, "detect")
    assert hasattr(adapter, "generate")
    assert hasattr(adapter, "_probe_json")
    assert hasattr(adapter, "_download_json")


def test_framework_match_structure():
    """FrameworkMatch 数据结构"""
    match = FrameworkMatch(
        name="Test",
        confidence=0.9,
        adapter=BaseAdapter(),
        strategy="test_strategy",
        evidence=["found /test endpoint"],
    )
    assert match.confidence == 0.9
    assert match.strategy == "test_strategy"
    assert len(match.evidence) == 1
