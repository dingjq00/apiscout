"""AI 增强 — 调用 DeepSeek/OpenAI 兼容 API 增强端点描述"""
import json
import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# AI 提供商配置
PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}

# 每批处理的端点数（避免 token 超限）
BATCH_SIZE = 8


def build_enrichment_prompt(endpoints: list[dict]) -> str:
    """构建发给 AI 的 prompt，包含端点列表和期望的 JSON 输出格式"""
    endpoint_summaries = []
    for ep in endpoints:
        summary = {
            "path": ep["path"],
            "method": ep["method"],
            "response_schema": ep.get("response_schema", {}),
            "query_params": [p["name"] for p in ep.get("query_params", [])],
        }
        endpoint_summaries.append(summary)

    return f"""你是一个 API 文档专家。请为以下 API 端点生成中文描述。

对每个端点，返回：
- summary: 一句话中文摘要（如"获取设备列表"）
- description: 详细描述（1-2 句话）
- tags: 功能分组标签列表（如["设备管理"]）
- field_hints: 对 response 中关键字段的中文说明（如 {{"status": "1=运行中, 2=维修中"}}）

端点列表：
{json.dumps(endpoint_summaries, ensure_ascii=False, indent=2)}

要求：
1. 返回 JSON 数组，每个元素包含 path, method, summary, description, tags, field_hints
2. 用 ```json ``` 包裹
3. 根据路径和 schema 推断业务含义
4. 如果是制造业/设备管理系统的 API，用相应的业务术语"""


def parse_enrichment_response(response_text: str) -> list[dict]:
    """解析 AI 返回的 JSON，提取 ```json ... ``` 块，失败时返回空列表"""
    # 提取 ```json ... ``` 中的内容
    match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        json_str = response_text

    try:
        result = json.loads(json_str)
        if isinstance(result, list):
            return result
        return []
    except (json.JSONDecodeError, TypeError):
        logger.warning("AI 响应解析失败")
        return []


def _call_ai_api(prompt: str, api_key: str, provider: str = "deepseek"):
    """调用 AI API（此函数设计为可被 mock 替换）"""
    # openai 是可选依赖，在函数内部导入
    from openai import OpenAI

    config = PROVIDERS.get(provider, PROVIDERS["deepseek"])
    client = OpenAI(api_key=api_key, base_url=config["base_url"])

    return client.chat.completions.create(
        model=config["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )


def enrich_endpoints(
    endpoints: list[dict],
    api_key: str | None = None,
    provider: str = "deepseek",
) -> list[dict]:
    """
    AI 增强端点列表。

    无 API key 时返回原始端点（优雅降级），有 key 时分批调用 AI 补充语义描述。
    """
    if not api_key:
        logger.info("未提供 API key，跳过 AI 增强")
        return endpoints

    # 复制一份避免修改原始数据
    enriched = list(endpoints)

    # 分批处理，避免单次请求 token 超限
    total_batches = (len(endpoints) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(endpoints), BATCH_SIZE):
        batch = endpoints[i:i + BATCH_SIZE]
        prompt = build_enrichment_prompt(batch)

        try:
            response = _call_ai_api(prompt, api_key, provider)
            ai_results = parse_enrichment_response(response.choices[0].message.content)

            # 按 (path, method) 合并 AI 结果到端点
            result_map = {(r["path"], r["method"]): r for r in ai_results}
            for j, ep in enumerate(batch):
                key = (ep["path"], ep["method"])
                if key in result_map:
                    ai_data = result_map[key]
                    enriched[i + j] = {**ep, **{
                        "summary": ai_data.get("summary", ""),
                        "description": ai_data.get("description", ""),
                        "tags": ai_data.get("tags", []),
                        "field_hints": ai_data.get("field_hints", {}),
                    }}

            logger.info(
                "AI 增强批次 %d/%d 完成 (%d 个端点)",
                i // BATCH_SIZE + 1,
                total_batches,
                len(ai_results),
            )

        except Exception as e:
            logger.warning("AI 增强批次 %d 失败: %s", i // BATCH_SIZE + 1, e)

    return enriched


def write_enriched_spec(
    enriched_endpoints: list[dict],
    output_dir: str,
    title: str = "APIScout 增强后 API",
    base_url: str = "",
):
    """生成增强后的 OpenAPI spec YAML 并写入输出目录"""
    from apiscout.core.generator.openapi import generate_openapi

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 生成 spec（不带草稿标记）
    spec = generate_openapi(enriched_endpoints, title=title, base_url=base_url, draft=False)

    # 将 AI 增强的 summary/description/tags 写入 spec 对应 operation
    for ep in enriched_endpoints:
        path = ep["path"]
        method = ep["method"].lower()
        if path in spec["paths"] and method in spec["paths"][path]:
            op = spec["paths"][path][method]
            if ep.get("summary"):
                op["summary"] = ep["summary"]
            if ep.get("description"):
                op["description"] = ep["description"]
            if ep.get("tags"):
                op["tags"] = ep["tags"]

    with open(output_path / "enriched_spec.yaml", "w", encoding="utf-8") as f:
        yaml.dump(spec, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info("生成: enriched_spec.yaml")
