"""若依 (RuoYi) 框架适配器 — 国内制造业最常见的 Java 快速开发平台

检测方式：探测 /dev-api/swagger-resources, /prod-api/swagger-resources
发现策略：download_spec（若依自带 Swagger）
"""
import logging
from pathlib import Path

import yaml

from apiscout.adapters.registry import BaseAdapter, FrameworkMatch, register

logger = logging.getLogger(__name__)

# 若依常见的 API 前缀
RUOYI_PREFIXES = ["/dev-api", "/prod-api", ""]


@register
class RuoYiAdapter(BaseAdapter):
    name = "若依 (RuoYi)"
    strategy = "download_spec"

    async def detect(self, page, base_url: str) -> FrameworkMatch | None:
        evidence = []
        confidence = 0.0
        self._spec_url = None

        for prefix in RUOYI_PREFIXES:
            # 探测 swagger-resources
            url = f"{base_url}{prefix}/swagger-resources"
            data = await self._probe_json(page, url)
            if isinstance(data, list) and len(data) > 0:
                # 若依的 swagger-resources 返回 [{name, url, ...}]
                first = data[0]
                if "url" in first or "location" in first:
                    confidence += 0.5
                    evidence.append(f"{prefix}/swagger-resources 返回 {len(data)} 个 API 组")

                    # 从 swagger-resources 提取 spec URL
                    spec_path = first.get("url") or first.get("location", "")
                    if spec_path:
                        self._spec_url = f"{base_url}{prefix}{spec_path}"
                        evidence.append(f"spec 路径: {prefix}{spec_path}")
                    break

            # 直接探测 api-docs
            url = f"{base_url}{prefix}/v3/api-docs"
            data = await self._probe_json(page, url)
            if isinstance(data, dict) and ("openapi" in data or "swagger" in data):
                confidence += 0.5
                self._spec_url = url
                evidence.append(f"{prefix}/v3/api-docs 可用")
                break

        # 若依特征：页面 HTML 中包含 "若依" 或 "ruoyi" 关键词
        try:
            html = await page.content()
            if "若依" in html or "ruoyi" in html.lower():
                confidence += 0.3
                evidence.append("页面包含'若依'关键词")
        except Exception:
            pass

        if confidence > 0:
            return FrameworkMatch(
                name=self.name,
                confidence=min(confidence, 1.0),
                adapter=self,
                strategy=self.strategy,
                evidence=evidence,
            )
        return None

    async def generate(self, page, base_url: str, output_dir: str) -> dict | None:
        if not self._spec_url:
            logger.warning("若依: 未找到 spec 端点")
            return None

        spec = await self._download_json(page, self._spec_url)
        if not isinstance(spec, dict):
            logger.warning("若依: spec 下载失败")
            return None

        output_path = Path(output_dir) / "discovered_spec.yaml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(spec, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        path_count = len(spec.get("paths", {}))
        logger.info("若依 spec 下载: %d 端点 → %s", path_count, output_path)

        return spec
