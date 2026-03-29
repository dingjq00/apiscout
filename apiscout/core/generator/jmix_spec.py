"""Jmix REST API spec 生成 — 从 metadata 直接生成 OpenAPI spec

当探测到 /rest/metadata/entities 时，直接用实体元数据生成 spec，
比抓包推断准确得多。Jmix REST API 遵循固定 pattern：
  GET    /rest/entities/{EntityName}        列表（支持 filter/sort/limit/offset）
  POST   /rest/entities/{EntityName}        创建
  GET    /rest/entities/{EntityName}/{id}   详情
  PUT    /rest/entities/{EntityName}/{id}   更新
  DELETE /rest/entities/{EntityName}/{id}   删除
"""
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# 框架实体前缀 — 跳过这些，只生成业务实体的 spec
FRAMEWORK_PREFIXES = (
    "sec_", "ui_", "report_", "audit_", "flowui_",
    "email_", "bpm_", "ntf_", "ldap_", "oidc_", "rest_",
    "data_", "sys_", "dashboard_",
)

# Jmix 类型 → OpenAPI 类型映射
TYPE_MAP = {
    "string": {"type": "string"},
    "int": {"type": "integer"},
    "long": {"type": "integer", "format": "int64"},
    "double": {"type": "number", "format": "double"},
    "decimal": {"type": "number"},
    "boolean": {"type": "boolean"},
    "date": {"type": "string", "format": "date"},
    "dateTime": {"type": "string", "format": "date-time"},
    "localDate": {"type": "string", "format": "date"},
    "localDateTime": {"type": "string", "format": "date-time"},
    "offsetDateTime": {"type": "string", "format": "date-time"},
    "time": {"type": "string", "format": "time"},
    "uuid": {"type": "string", "format": "uuid"},
    "byteArray": {"type": "string", "format": "byte"},
    "URI": {"type": "string", "format": "uri"},
}


def generate_jmix_spec(
    entities_metadata: list[dict],
    base_url: str = "",
    title: str = "Jmix REST API",
    include_framework: bool = False,
) -> dict:
    """从 Jmix metadata 生成 OpenAPI 3.1 spec"""
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": title,
            "version": "1.0.0",
            "description": "由 APIScout 从 Jmix metadata 自动生成",
        },
        "paths": {},
        "components": {"schemas": {}},
    }

    if base_url:
        spec["servers"] = [{"url": base_url}]

    for entity in entities_metadata:
        name = entity.get("entityName", "")

        # 跳过框架实体
        if not include_framework and name.startswith(FRAMEWORK_PREFIXES):
            continue

        properties = entity.get("properties", [])
        schema = _build_entity_schema(name, properties)
        spec["components"]["schemas"][name] = schema

        # 生成 CRUD 端点
        _add_crud_paths(spec["paths"], name, schema)

    return spec


def _build_entity_schema(entity_name: str, properties: list[dict]) -> dict:
    """从实体属性构建 JSON Schema"""
    schema = {
        "type": "object",
        "properties": {
            "_entityName": {"type": "string", "example": entity_name},
            "_instanceName": {"type": "string"},
            "id": {"type": "string", "format": "uuid"},
        },
        "required": ["_entityName"],
    }

    required = ["_entityName"]

    for prop in properties:
        prop_name = prop.get("name", "")
        prop_type = prop.get("type", "string")
        attr_type = prop.get("attributeType", "")
        mandatory = prop.get("mandatory", False)
        description = prop.get("description", "")

        if attr_type == "ASSOCIATION" or attr_type == "COMPOSITION":
            # 关联实体 — 引用
            prop_schema = {"$ref": f"#/components/schemas/{prop_type}"}
            if prop.get("cardinality") in ("ONE_TO_MANY", "MANY_TO_MANY"):
                prop_schema = {"type": "array", "items": {"$ref": f"#/components/schemas/{prop_type}"}}
        else:
            # 普通字段
            prop_schema = dict(TYPE_MAP.get(prop_type, {"type": "string"}))

        if description:
            prop_schema["description"] = description

        schema["properties"][prop_name] = prop_schema

        if mandatory:
            required.append(prop_name)

    if len(required) > 1:
        schema["required"] = required

    return schema


def _add_crud_paths(paths: dict, entity_name: str, schema: dict):
    """为一个实体添加标准 CRUD 路径"""
    list_path = f"/rest/entities/{entity_name}"
    detail_path = f"/rest/entities/{entity_name}/{{id}}"

    # GET 列表
    paths[list_path] = {
        "get": {
            "summary": f"查询 {entity_name} 列表",
            "tags": [entity_name],
            "parameters": [
                {"name": "filter", "in": "query", "schema": {"type": "string"},
                 "description": "JPQL 过滤条件（JSON 格式）"},
                {"name": "sort", "in": "query", "schema": {"type": "string"},
                 "description": "排序字段，如 +name,-createdDate"},
                {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 100},
                 "description": "返回条数限制"},
                {"name": "offset", "in": "query", "schema": {"type": "integer", "default": 0},
                 "description": "偏移量"},
                {"name": "fetchPlan", "in": "query", "schema": {"type": "string"},
                 "description": "Fetch plan 名称，控制返回字段深度"},
            ],
            "responses": {
                "200": {
                    "description": f"{entity_name} 列表",
                    "content": {
                        "application/json": {
                            "schema": {"type": "array", "items": {"$ref": f"#/components/schemas/{entity_name}"}},
                        }
                    }
                }
            },
        },
        "post": {
            "summary": f"创建 {entity_name}",
            "tags": [entity_name],
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{entity_name}"},
                    }
                }
            },
            "responses": {
                "201": {
                    "description": "创建成功",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity_name}"},
                        }
                    }
                }
            },
        },
    }

    # 详情/更新/删除
    paths[detail_path] = {
        "get": {
            "summary": f"获取 {entity_name} 详情",
            "tags": [entity_name],
            "parameters": [
                {"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                {"name": "fetchPlan", "in": "query", "schema": {"type": "string"}},
            ],
            "responses": {
                "200": {
                    "description": f"{entity_name} 详情",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity_name}"},
                        }
                    }
                }
            },
        },
        "put": {
            "summary": f"更新 {entity_name}",
            "tags": [entity_name],
            "parameters": [
                {"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
            ],
            "requestBody": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{entity_name}"},
                    }
                }
            },
            "responses": {
                "200": {
                    "description": "更新成功",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity_name}"},
                        }
                    }
                }
            },
        },
        "delete": {
            "summary": f"删除 {entity_name}",
            "tags": [entity_name],
            "parameters": [
                {"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
            ],
            "responses": {
                "200": {"description": "删除成功"},
            },
        },
    }


def write_jmix_spec(
    entities_metadata: list[dict],
    output_path: str,
    base_url: str = "",
    title: str = "Jmix REST API",
):
    """生成并写入 Jmix spec"""
    spec = generate_jmix_spec(entities_metadata, base_url=base_url, title=title)

    biz_count = len([s for s in spec["components"]["schemas"]])
    path_count = len(spec["paths"])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info("Jmix spec 生成: %s (%d 实体, %d 路径)", output_path, biz_count, path_count)
    return spec
