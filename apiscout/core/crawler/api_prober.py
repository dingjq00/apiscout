"""API 文档端点探测 — 主动发现已有的 API 文档和 REST 端点

很多框架自带 API 文档（Swagger/OpenAPI）或标准 REST 端点。
在抓包之前先探测这些端点，如果找到了，直接用比抓包推断准确得多。
"""
import json
import logging
from dataclasses import dataclass
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


# 已知 API 文档/元数据端点，按优先级排列
PROBE_ENDPOINTS = [
    # OpenAPI / Swagger
    {"path": "/v3/api-docs", "type": "openapi", "desc": "OpenAPI 3.x (Spring Boot)"},
    {"path": "/v2/api-docs", "type": "swagger", "desc": "Swagger 2.x"},
    {"path": "/swagger-resources", "type": "swagger_meta", "desc": "Swagger 资源列表"},
    {"path": "/swagger-ui.html", "type": "swagger_ui", "desc": "Swagger UI"},
    {"path": "/doc.html", "type": "swagger_ui", "desc": "knife4j (国内常用)"},
    {"path": "/api-docs", "type": "openapi", "desc": "通用 API 文档"},

    # Jmix / CUBA
    {"path": "/rest/entities", "type": "jmix_entities", "desc": "Jmix 实体列表"},
    {"path": "/rest/services", "type": "jmix_services", "desc": "Jmix 服务列表"},
    {"path": "/rest/metadata/entities", "type": "jmix_metadata", "desc": "Jmix 元数据"},

    # Spring Actuator
    {"path": "/actuator", "type": "actuator", "desc": "Spring Actuator"},
    {"path": "/actuator/mappings", "type": "actuator_mappings", "desc": "Spring 路由映射"},

    # 若依 / JeecgBoot
    {"path": "/dev-api/swagger-resources", "type": "swagger_meta", "desc": "若依 Swagger"},

    # 通用 REST 路径探测
    {"path": "/api", "type": "api_root", "desc": "API 根路径"},
    {"path": "/api/v1", "type": "api_root", "desc": "API v1"},
    {"path": "/api/v2", "type": "api_root", "desc": "API v2"},
]


@dataclass
class ProbeResult:
    """探测结果"""
    path: str
    type: str
    desc: str
    status: int
    content_type: str = ""
    body: str | dict | list | None = None
    needs_auth: bool = False


async def probe_api_endpoints(
    page,
    base_url: str,
    output_dir: str | None = None,
) -> list[ProbeResult]:
    """
    主动探测已知 API 文档端点。

    使用浏览器的 fetch 发请求（自动带 cookie/session），
    这样已登录的 session 也能探测到需要认证的端点。
    对 OpenAPI/Swagger 端点，直接在浏览器里下载到本地文件（避免大 JSON 传输超限）。
    """
    results = []

    for endpoint in PROBE_ENDPOINTS:
        url = urljoin(base_url, endpoint["path"])
        is_spec_endpoint = endpoint["type"] in ("openapi", "swagger")

        try:
            # 用页面内 JS 发 fetch，自动携带 session
            # 普通端点：body 截断到 50KB
            # OpenAPI spec 端点：只取前 200 字符判断格式，完整内容另存
            probe_js = f"""
            async () => {{
                try {{
                    const resp = await fetch("{url}", {{
                        method: "GET",
                        headers: {{"Accept": "application/json, */*"}},
                    }});
                    const ct = resp.headers.get("content-type") || "";
                    let body = null;
                    let fullBody = null;
                    const isJson = ct.includes("json");
                    if (isJson) {{
                        const text = await resp.text();
                        body = text.substring(0, 50000);
                        fullBody = {'true' if is_spec_endpoint else 'false'} ? text : null;
                    }}
                    return {{
                        status: resp.status,
                        content_type: ct,
                        body: body,
                        fullBody: fullBody,
                        is_json: isJson,
                        bodySize: body ? body.length : 0,
                    }};
                }} catch (e) {{
                    return {{status: 0, content_type: "", body: null, fullBody: null, is_json: false, error: e.message}};
                }}
            }}
            """
            resp = await page.evaluate(probe_js)

            status = resp.get("status", 0)
            if status == 0:
                continue

            content_type = resp.get("content_type", "")
            is_json = resp.get("is_json", False)

            # Vaadin SPA 对所有路由返回 200 + text/html — 这不是真 API
            if status == 200 and not is_json and "html" in content_type:
                continue

            # 解析 body
            body = None
            if resp.get("body"):
                try:
                    body = json.loads(resp["body"])
                except (json.JSONDecodeError, TypeError):
                    body = resp["body"]

            # 对 OpenAPI/Swagger spec 端点，保存完整 JSON 到文件
            if is_spec_endpoint and status == 200 and is_json and resp.get("fullBody") and output_dir:
                try:
                    full_body = json.loads(resp["fullBody"])
                    if isinstance(full_body, dict) and ("openapi" in full_body or "swagger" in full_body):
                        from pathlib import Path
                        spec_file = Path(output_dir) / "discovered_spec.yaml"
                        import yaml
                        with open(spec_file, "w", encoding="utf-8") as f:
                            yaml.dump(full_body, f, default_flow_style=False,
                                     allow_unicode=True, sort_keys=False)
                        body = full_body  # 用完整的作为 body
                        logger.info("已保存完整 OpenAPI spec: %s (%d 字节)",
                                   spec_file, len(resp["fullBody"]))
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("OpenAPI spec 解析失败: %s", e)

            result = ProbeResult(
                path=endpoint["path"],
                type=endpoint["type"],
                desc=endpoint["desc"],
                status=status,
                content_type=content_type,
                body=body,
                needs_auth=(status in (401, 403)),
            )

            # 只记录有意义的结果（200 JSON / 401 / 403）
            if status == 200 and is_json:
                results.append(result)
                logger.info("✅ [%d] %s — %s", status, endpoint["path"], endpoint["desc"])
            elif status in (401, 403):
                results.append(result)
                logger.info("🔒 [%d] %s — %s", status, endpoint["path"], endpoint["desc"])

        except Exception as e:
            logger.debug("探测跳过 %s: %s", endpoint["path"], e)

    return results


def summarize_probe_results(results: list[ProbeResult]) -> dict:
    """汇总探测结果"""
    summary = {
        "openapi_spec": None,      # 如果找到了 OpenAPI/Swagger spec
        "available_endpoints": [],  # 可用的端点列表
        "auth_required": [],       # 需要认证的端点
        "framework_hints": [],     # 检测到的框架特征
    }

    for r in results:
        if r.status == 200:
            summary["available_endpoints"].append({
                "path": r.path, "type": r.type, "desc": r.desc,
            })

            # 如果是 OpenAPI/Swagger spec，直接保存
            if r.type in ("openapi", "swagger") and isinstance(r.body, dict):
                if "openapi" in r.body or "swagger" in r.body:
                    summary["openapi_spec"] = r.body
                    logger.info("发现现成的 OpenAPI spec！路径: %s", r.path)

            # 框架检测
            if r.type == "actuator" and "Spring Boot" not in summary["framework_hints"]:
                summary["framework_hints"].append("Spring Boot")
            elif r.type.startswith("jmix") and "Jmix" not in summary["framework_hints"]:
                summary["framework_hints"].append("Jmix")

        elif r.needs_auth:
            summary["auth_required"].append({
                "path": r.path, "type": r.type, "desc": r.desc,
            })

    return summary
