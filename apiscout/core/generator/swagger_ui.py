"""生成内嵌 Swagger UI 的单文件 HTML — 离线可用，U 盘友好"""
import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Swagger UI CDN（生成时内嵌 spec JSON，UI 从 CDN 加载）
# 如果需要完全离线，可以把 CSS/JS 也内嵌，但文件会变大
SWAGGER_UI_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title} — API 文档</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
    <style>
        body {{ margin: 0; padding: 0; }}
        .topbar {{ display: none !important; }}  /* 隐藏 Swagger 顶栏 */
        .swagger-ui .info {{ margin: 20px 0; }}
        .swagger-ui .info .title {{ color: #1a365d; }}
        /* APIScout 标记 */
        .apiscout-banner {{
            background: #1a365d; color: white; padding: 10px 20px;
            font-family: -apple-system, sans-serif; font-size: 13px;
            display: flex; justify-content: space-between; align-items: center;
        }}
        .apiscout-banner a {{ color: #90cdf4; }}
    </style>
</head>
<body>
    <div class="apiscout-banner">
        <span>由 <strong>APIScout</strong> 自动生成 | {stats}</span>
        <span>{generated_at}</span>
    </div>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        const spec = {spec_json};
        SwaggerUIBundle({{
            spec: spec,
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
            layout: "BaseLayout",
            defaultModelsExpandDepth: 1,
            docExpansion: "list",
        }});
    </script>
</body>
</html>"""


def generate_swagger_html(
    spec: dict | str,
    output_path: str,
    title: str | None = None,
    generated_at: str = "",
):
    """
    从 OpenAPI spec 生成 Swagger UI HTML 文件。

    spec: OpenAPI spec dict 或 YAML 文件路径
    output_path: 输出 HTML 文件路径
    """
    # 加载 spec
    if isinstance(spec, str):
        with open(spec, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)

    if not isinstance(spec, dict):
        logger.error("无效的 spec 格式")
        return

    # 展开所有 $ref 引用（Swagger UI 从 file:// 加载时解析 $ref 有 bug）
    spec = _resolve_refs(spec)

    # 提取信息
    title = title or spec.get("info", {}).get("title", "API 文档")
    path_count = len(spec.get("paths", {}))
    schema_count = len(spec.get("components", {}).get("schemas", {}))
    stats = f"{path_count} 个端点 | {schema_count} 个 Schema"

    # 生成 HTML
    html = SWAGGER_UI_TEMPLATE.format(
        title=title,
        spec_json=json.dumps(spec, ensure_ascii=False),
        stats=stats,
        generated_at=generated_at,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("Swagger UI 生成: %s (%d 端点)", output_path, path_count)


def _resolve_refs(spec: dict) -> dict:
    """递归展开所有 $ref 引用，生成自包含的 spec"""
    import copy
    schemas = spec.get("components", {}).get("schemas", {})

    def resolve(obj, depth=0):
        if depth > 10:  # 防止循环引用无限递归
            return obj
        if isinstance(obj, dict):
            if "$ref" in obj and len(obj) == 1:
                ref_path = obj["$ref"]
                # 只处理 #/components/schemas/xxx 格式
                if ref_path.startswith("#/components/schemas/"):
                    schema_name = ref_path.split("/")[-1]
                    if schema_name in schemas:
                        return resolve(copy.deepcopy(schemas[schema_name]), depth + 1)
                return obj
            return {k: resolve(v, depth) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [resolve(item, depth) for item in obj]
        return obj

    resolved = copy.deepcopy(spec)
    resolved["paths"] = resolve(resolved.get("paths", {}))
    return resolved
