"""Jmix 框架适配器 — 从 /rest/metadata/entities 生成完整 spec

检测方式：探测 /rest/metadata/entities 和 /rest/entities
发现策略：metadata_to_spec（从元数据按 CRUD pattern 生成）
"""
import logging
from pathlib import Path

import yaml

from apiscout.adapters.registry import BaseAdapter, FrameworkMatch, register
from apiscout.core.generator.jmix_spec import generate_jmix_spec

logger = logging.getLogger(__name__)


@register
class JmixAdapter(BaseAdapter):
    name = "Jmix"
    strategy = "metadata_to_spec"

    async def detect(self, page, base_url: str) -> FrameworkMatch | None:
        evidence = []
        confidence = 0.0

        # 探测 1: /rest/metadata/entities（核心标志）
        metadata = await self._probe_json(page, f"{base_url}/rest/metadata/entities")
        if isinstance(metadata, list) and len(metadata) > 0:
            # 检查是否有 Jmix 特征字段
            first = metadata[0]
            if "entityName" in first and "properties" in first:
                confidence += 0.6
                evidence.append(f"/rest/metadata/entities 返回 {len(metadata)} 个实体")
                self._metadata = metadata

        # 探测 2: /rest/entities
        entities = await self._probe_json(page, f"{base_url}/rest/entities")
        if entities is not None:
            confidence += 0.2
            evidence.append("/rest/entities 可访问")

        # 探测 3: /rest/services
        services = await self._probe_json(page, f"{base_url}/rest/services")
        if isinstance(services, list):
            confidence += 0.2
            evidence.append(f"/rest/services 返回 {len(services)} 个服务")

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
        # 如果 detect 时已经拿到 metadata，直接用
        metadata = getattr(self, "_metadata", None)
        if not metadata:
            metadata = await self._download_json(page, f"{base_url}/rest/metadata/entities")

        if not metadata or not isinstance(metadata, list):
            logger.warning("Jmix: 无法获取 metadata")
            return None

        spec = generate_jmix_spec(
            metadata,
            base_url=base_url,
            title=f"{base_url} Jmix REST API",
        )

        # 写文件
        output_path = Path(output_dir) / "jmix_spec.yaml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(spec, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        entity_count = len(spec.get("components", {}).get("schemas", {}))
        path_count = len(spec.get("paths", {}))
        logger.info("Jmix spec 生成: %d 实体, %d 端点 → %s", entity_count, path_count, output_path)

        return spec
