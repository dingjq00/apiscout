"""Spring Boot 适配器 — 下载已有的 OpenAPI/Swagger spec

检测方式：探测 /actuator, /v3/api-docs, /v2/api-docs
发现策略：download_spec（直接下载现成 spec）
"""
import logging
from pathlib import Path

import yaml

from apiscout.adapters.registry import BaseAdapter, FrameworkMatch, register

logger = logging.getLogger(__name__)

# 可能的 spec 端点，按优先级
SPEC_ENDPOINTS = [
    "/v3/api-docs",
    "/v2/api-docs",
    "/api-docs",
]


@register
class SpringBootAdapter(BaseAdapter):
    name = "Spring Boot"
    strategy = "download_spec"

    async def detect(self, page, base_url: str) -> FrameworkMatch | None:
        evidence = []
        confidence = 0.0
        self._spec_url = None

        # 探测 1: /actuator（Spring Boot 标志）
        actuator = await self._probe_json(page, f"{base_url}/actuator")
        if isinstance(actuator, dict) and "_links" in actuator:
            confidence += 0.4
            evidence.append("/actuator 可访问（Spring Boot Actuator）")

        # 探测 2: OpenAPI spec 端点
        for endpoint in SPEC_ENDPOINTS:
            # 用小 probe 只看 content-type 和前几个 key
            data = await self._probe_json(page, f"{base_url}{endpoint}")
            if isinstance(data, dict) and ("openapi" in data or "swagger" in data):
                confidence += 0.5
                version = data.get("openapi", data.get("swagger", ""))
                evidence.append(f"{endpoint} 返回 OpenAPI {version} spec")
                self._spec_url = f"{base_url}{endpoint}"
                break  # 找到第一个就够了

        # 探测 3: /swagger-ui.html
        swagger_ui = await self._probe_json(page, f"{base_url}/swagger-resources")
        if isinstance(swagger_ui, list):
            confidence += 0.1
            evidence.append("/swagger-resources 可访问")

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
            # detect 时没找到，再试一遍
            for endpoint in SPEC_ENDPOINTS:
                url = f"{base_url}{endpoint}"
                data = await self._download_json(page, url)
                if isinstance(data, dict) and ("openapi" in data or "swagger" in data):
                    self._spec_url = url
                    break

        if not self._spec_url:
            logger.warning("Spring Boot: 未找到 OpenAPI spec 端点")
            return None

        # 用 page.request 下载完整 spec（可能很大）
        spec = await self._download_json(page, self._spec_url)
        if not isinstance(spec, dict):
            logger.warning("Spring Boot: spec 下载失败")
            return None

        # 写文件
        output_path = Path(output_dir) / "discovered_spec.yaml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(spec, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        path_count = len(spec.get("paths", {}))
        logger.info("Spring Boot spec 下载: %d 端点 → %s", path_count, output_path)

        return spec
