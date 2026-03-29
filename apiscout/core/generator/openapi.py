"""OpenAPI 3.1 YAML 生成"""
import re
from pathlib import Path

import yaml


def generate_openapi(
    endpoints: list[dict],
    title: str = "APIScout 发现的 API",
    base_url: str = "",
    draft: bool = False,
) -> dict:
    """从聚合端点列表生成 OpenAPI 3.1 spec dict"""
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": title,
            "version": "1.0.0",
            "description": "由 APIScout 自动发现并生成",
        },
        "paths": {},
    }

    if base_url:
        spec["servers"] = [{"url": base_url}]

    for ep in endpoints:
        path = ep["path"]
        method = ep["method"].lower()

        if path not in spec["paths"]:
            spec["paths"][path] = {}

        operation = {
            "summary": f"{ep['method']} {path}",
            "responses": {},
        }

        # 路径参数（从 {xxx} 提取）
        path_params = re.findall(r'\{(\w+)\}', path)
        parameters = []
        for param_name in path_params:
            parameters.append({
                "name": param_name,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            })

        # Query 参数
        for qp in ep.get("query_params", []):
            parameters.append({
                "name": qp["name"],
                "in": "query",
                "required": qp.get("required", False),
                "schema": qp.get("schema", {"type": "string"}),
            })

        if parameters:
            operation["parameters"] = parameters

        # Request body
        if ep.get("request_schema"):
            operation["requestBody"] = {
                "content": {
                    "application/json": {
                        "schema": ep["request_schema"],
                    }
                }
            }

        # Response
        for status_code in ep.get("status_codes", [200]):
            status_str = str(status_code)
            resp = {"description": f"HTTP {status_code}"}
            if ep.get("response_schema"):
                resp["content"] = {
                    "application/json": {
                        "schema": ep["response_schema"],
                    }
                }
            operation["responses"][status_str] = resp

        if not operation["responses"]:
            operation["responses"]["200"] = {"description": "OK"}

        # 草稿模式标记（偷师 Optic 的 review annotation）
        if draft:
            operation["x-apiscout-review"] = ep.get("status", "confirmed")
            operation["x-apiscout-observations"] = ep.get("observation_count", 0)

        spec["paths"][path][method] = operation

    return spec


def write_openapi_yaml(
    endpoints: list[dict],
    output_path: str,
    title: str = "APIScout 发现的 API",
    base_url: str = "",
    draft: bool = False,
):
    """生成并写入 YAML 文件"""
    spec = generate_openapi(endpoints, title=title, base_url=base_url, draft=draft)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
