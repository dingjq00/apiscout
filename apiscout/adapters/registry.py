"""适配器注册表 — 框架检测 + 策略分发

每个适配器定义三件事：
1. detect — 怎么认出这个框架（探测签名）
2. strategy — 最优发现策略（download_spec / metadata_to_spec / traffic_capture）
3. generate — 生成 OpenAPI spec 的具体实现

使用流程：
  results = await detect_framework(page, base_url)
  → [FrameworkMatch(name="Jmix", confidence=1.0, adapter=JmixAdapter, ...)]
  spec = await adapter.generate(page, base_url, output_dir)
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 全局适配器注册表
_ADAPTERS: list[type] = []


def register(adapter_cls):
    """注册一个适配器（装饰器）"""
    _ADAPTERS.append(adapter_cls)
    return adapter_cls


def get_all_adapters() -> list[type]:
    """获取所有已注册的适配器"""
    return list(_ADAPTERS)


@dataclass
class FrameworkMatch:
    """框架匹配结果"""
    name: str              # 框架名称
    confidence: float      # 置信度 0.0-1.0
    adapter: object        # 适配器实例
    strategy: str          # 发现策略
    evidence: list[str]    # 匹配证据


async def detect_framework(page, base_url: str) -> list[FrameworkMatch]:
    """
    对目标系统做框架检测，返回匹配的适配器列表（按置信度排序）。

    page: Playwright Page（已登录状态）
    base_url: 目标系统 origin
    """
    matches = []

    for adapter_cls in _ADAPTERS:
        adapter = adapter_cls()
        try:
            match = await adapter.detect(page, base_url)
            if match and match.confidence > 0:
                matches.append(match)
                logger.info("检测到框架: %s (置信度: %.0f%%, 策略: %s)",
                           match.name, match.confidence * 100, match.strategy)
                for ev in match.evidence:
                    logger.info("  证据: %s", ev)
        except Exception as e:
            # 区分"不适用"（超时/404）和真正的代码错误
            if isinstance(e, (TimeoutError, ConnectionError, OSError)):
                logger.debug("适配器 %s 探测超时/连接失败: %s", adapter_cls.__name__, e)
            else:
                logger.warning("适配器 %s 检测异常: %s: %s", adapter_cls.__name__, type(e).__name__, e)

    # 按置信度降序排列
    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches


class BaseAdapter:
    """适配器基类 — 每个框架继承实现"""

    name: str = "unknown"
    strategy: str = "traffic_capture"  # download_spec / metadata_to_spec / traffic_capture

    async def detect(self, page, base_url: str) -> FrameworkMatch | None:
        """检测目标是否属于本框架，返回 FrameworkMatch 或 None"""
        raise NotImplementedError

    async def generate(self, page, base_url: str, output_dir: str) -> dict | None:
        """用本框架的最优策略生成 OpenAPI spec，返回 spec dict 或 None"""
        raise NotImplementedError

    async def _probe_json(self, page, url: str) -> dict | list | None:
        """用浏览器 fetch 探测一个 URL，返回 JSON 或 None"""
        try:
            resp = await page.evaluate(f"""
            async () => {{
                try {{
                    const r = await fetch("{url}", {{
                        headers: {{"Accept": "application/json"}},
                    }});
                    const ct = r.headers.get("content-type") || "";
                    if (!ct.includes("json")) return null;
                    return await r.json();
                }} catch(e) {{ return null; }}
            }}
            """)
            return resp
        except Exception:
            return None

    async def _download_json(self, page, url: str) -> dict | list | None:
        """用 Playwright request API 下载大 JSON（绕过 evaluate 大小限制）"""
        try:
            resp = await page.request.get(url)
            if resp.ok and "json" in resp.headers.get("content-type", ""):
                return await resp.json()
        except Exception:
            pass
        return None
