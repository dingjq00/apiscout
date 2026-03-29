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
