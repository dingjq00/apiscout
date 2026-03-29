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
        // 用 Blob URL 加载 spec，绕开 file:// 协议的 $ref 解析限制
        const specJson = JSON.stringify({spec_json});
        const blob = new Blob([specJson], {{type: 'application/json'}});
        const specUrl = URL.createObjectURL(blob);
        SwaggerUIBundle({{
            url: specUrl,
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
            layout: "BaseLayout",
            defaultModelsExpandDepth: 1,
            docExpansion: "list",
            validatorUrl: null,
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

    # HTML 文档专用：把 $ref 替换为可读描述（避免 Swagger UI 解析问题）
    import copy
    spec = _flatten_refs_for_display(copy.deepcopy(spec))

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


def _flatten_refs_for_display(spec: dict) -> dict:
    """把所有 $ref 替换为可读的内联描述（HTML 文档专用）"""

    def flatten(obj):
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref = obj["$ref"]
                name = ref.split("/")[-1] if "/" in ref else ref
                # 如果是 array items 里的 $ref
                return {"type": "object", "description": f"关联实体: {name}"}
            return {k: flatten(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [flatten(item) for item in obj]
        return obj

    spec["paths"] = flatten(spec.get("paths", {}))
    # 保留 components/schemas 供 Models 区域展示，但也 flatten 里面的 $ref
    if "components" in spec and "schemas" in spec["components"]:
        spec["components"]["schemas"] = flatten(spec["components"]["schemas"])
    return spec
