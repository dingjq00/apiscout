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
    """内联展开 $ref（1 层深），嵌套关联用描述替代（HTML 文档专用）

    效果：Response 的 Example Value 能显示完整字段，而不是空 {}
    """
    import copy
    schemas = spec.get("components", {}).get("schemas", {})

    def resolve_ref(ref_str: str, depth: int) -> dict:
        """解析一个 $ref，depth=0 时完整内联，depth>0 时只放描述"""
        name = ref_str.split("/")[-1] if "/" in ref_str else ref_str
        if name not in schemas:
            return {"type": "object", "description": f"关联实体: {name}"}
        if depth > 0:
            return {"type": "object", "description": f"关联实体: {name}"}
        # depth=0：完整内联该 schema 的字段，但其中的 $ref 用 depth+1 处理
        return flatten(copy.deepcopy(schemas[name]), depth + 1)

    def flatten(obj, depth=0):
        if isinstance(obj, dict):
            if "$ref" in obj and isinstance(obj["$ref"], str):
                return resolve_ref(obj["$ref"], depth)
            return {k: flatten(v, depth) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [flatten(item, depth) for item in obj]
        return obj

    spec["paths"] = flatten(spec.get("paths", {}), depth=0)
    # components/schemas 里的 $ref 也处理（depth=1，只替换为描述）
    if "components" in spec and "schemas" in spec["components"]:
        for name in spec["components"]["schemas"]:
            spec["components"]["schemas"][name] = flatten(
                spec["components"]["schemas"][name], depth=1
            )
    return spec
