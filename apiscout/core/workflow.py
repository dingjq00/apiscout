"""两遍工作流编排 — 连接 capture → analyze → generate"""
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml

from apiscout.core.capture.store import CaptureStore
from apiscout.core.analyzer.dedup import EndpointAggregator
from apiscout.core.generator.openapi import write_openapi_yaml
from apiscout.core.generator.auth_profile import (
    write_auth_profile, find_login_endpoint,
)
from apiscout.core.generator.report import write_report
from apiscout.core.generator.swagger_ui import generate_swagger_html

logger = logging.getLogger(__name__)


def analyze_capture(
    capture_path: str,
    js_endpoints: list[str] | None = None,
) -> dict:
    """
    分析 JSONL 捕获数据 → 聚合结果。

    返回 dict 包含：endpoints, auth, login_info, stats
    """
    store = CaptureStore(capture_path)
    aggregator = EndpointAggregator()

    records = list(store.read_all())
    for record in records:
        aggregator.add(record)

    # JS 发现的端点（explore 阶段 js_analyzer 提供）
    if js_endpoints:
        for ep in js_endpoints:
            aggregator.add_js_endpoint(ep)

    endpoints = aggregator.get_results()
    auth = aggregator.get_auth_profile()
    login_info = find_login_endpoint(records)

    return {
        "endpoints": endpoints,
        "auth": auth,
        "login_info": login_info,
        "stats": {
            "total_records": len(records),
            "total_endpoints": len(endpoints),
            "confirmed": sum(1 for e in endpoints if e["status"] == "confirmed"),
            "uncertain": sum(1 for e in endpoints if e["status"] == "uncertain"),
        },
    }


def generate_outputs(
    analysis_result: dict,
    output_dir: str,
    title: str = "APIScout 发现的 API",
    base_url: str = "",
) -> dict:
    """
    从分析结果生成所有输出文件。

    输出：
    - draft_spec.yaml  — OpenAPI 3.1 草稿（含审核标记）
    - auth_profile.yaml — 认证档案
    - report.html      — HTML 覆盖率报告
    - meta.yaml        — 项目元信息
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    endpoints = analysis_result["endpoints"]
    auth = analysis_result["auth"]
    login_info = analysis_result.get("login_info")
    stats = analysis_result["stats"]

    # 1. OpenAPI spec（草稿模式，偷师 Optic 的 review annotation）
    write_openapi_yaml(
        endpoints,
        str(output_path / "draft_spec.yaml"),
        title=title,
        base_url=base_url,
        draft=True,
    )
    logger.info("生成: draft_spec.yaml (%d 个端点)", stats["total_endpoints"])

    # 2. 认证档案（偷师 Nango 的 provider config）
    write_auth_profile(
        auth,
        str(output_path / "auth_profile.yaml"),
        login_info=login_info,
    )
    logger.info("生成: auth_profile.yaml (类型: %s)", auth.get("type", "unknown"))

    # 3. HTML 覆盖率报告
    write_report(
        endpoints,
        str(output_path / "report.html"),
        title=title,
        auth_summary=auth,
    )
    logger.info("生成: report.html")

    # 4. Swagger UI 交互式文档
    generate_swagger_html(
        spec=str(output_path / "draft_spec.yaml"),
        output_path=str(output_path / "api_docs.html"),
        title=title,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    logger.info("生成: api_docs.html (交互式 API 文档)")

    # 5. 项目元信息（供后续 enrich/集成使用）
    meta = {
        "tool": "APIScout",
        "version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "stats": stats,
        "auth_type": auth.get("type", "unknown"),
    }
    with open(output_path / "meta.yaml", "w", encoding="utf-8") as f:
        yaml.dump(meta, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info("生成: meta.yaml")

    return {
        "output_dir": str(output_path),
        "files": ["draft_spec.yaml", "auth_profile.yaml", "report.html", "meta.yaml"],
    }


def scan_db(
    conn_str: str = None,
    output_dir: str = None,
    enrich_spec: str = None,
    exclude_patterns: list[str] | None = None,
    **conn_kwargs,
) -> dict:
    """扫描数据库 schema → 生成报告"""
    import json
    from dataclasses import asdict
    from apiscout.core.db_scanner.introspector import scan_database
    from apiscout.core.db_scanner.connector import parse_connection_string
    from apiscout.core.generator.schema_report_html import write_schema_report_html

    # 扫描
    if conn_str:
        params = parse_connection_string(conn_str)
        report = scan_database(conn_str, exclude_patterns=exclude_patterns)
    else:
        params = conn_kwargs
        report = scan_database(exclude_patterns=exclude_patterns, **conn_kwargs)

    db_name = params.get("database", "unknown")

    # 输出目录
    if not output_dir:
        output_dir = f"./output/{db_name}"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 写 JSON
    def _json_default(obj):
        """处理不可序列化类型（memoryview/bytes/datetime 等）"""
        if isinstance(obj, (memoryview, bytes)):
            return f"<binary {len(obj)} bytes>"
        return str(obj)

    json_path = output_path / "schema_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, ensure_ascii=False, indent=2, default=_json_default)
    logger.info("生成: schema_report.json (%d 张表)", report.total_tables)

    # 写 HTML
    write_schema_report_html(report, str(output_path / "schema_report.html"))
    logger.info("生成: schema_report.html")

    # 交叉增强（可选）
    if enrich_spec:
        from apiscout.core.analyzer.schema_enricher import enrich_openapi_with_schema
        enriched = enrich_openapi_with_schema(enrich_spec, report)
        enriched_path = output_path / "enriched_spec.yaml"
        with open(enriched_path, "w", encoding="utf-8") as f:
            yaml.dump(enriched, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        logger.info("生成: enriched_spec.yaml（交叉增强）")

    return {"output_dir": str(output_path), "report": report}
