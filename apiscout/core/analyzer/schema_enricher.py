"""用 DB schema 交叉增强 OpenAPI spec"""
import copy
import logging
import re
import yaml
from apiscout.core.db_scanner.models import SchemaReport, ColumnInfo

logger = logging.getLogger(__name__)


def enrich_openapi_with_schema(spec: dict | str, schema_report: SchemaReport) -> dict:
    """用数据库 schema 增强 OpenAPI spec。

    Args:
        spec: OpenAPI spec（dict）或文件路径（str）
        schema_report: DB schema 扫描报告

    Returns:
        增强后的 spec（deep copy，不修改原始输入）
    """
    # 如果传入文件路径，加载 YAML
    if isinstance(spec, str):
        with open(spec, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)

    # 始终在 deep copy 上操作，不污染原始输入
    result = copy.deepcopy(spec)

    # 构建列索引：{table_name: {col_name: ColumnInfo}}
    col_index: dict[str, dict[str, ColumnInfo]] = {}
    for table in schema_report.tables:
        col_index[table.name] = {col.name: col for col in table.columns}

    table_names = set(col_index.keys())

    # 遍历所有路径
    paths = result.get("paths", {})
    for path, path_item in paths.items():
        table_name = _guess_table_from_path(path, table_names)
        if not table_name:
            logger.debug("路径 %s 未匹配到任何表", path)
            continue

        col_map = col_index[table_name]
        logger.debug("路径 %s 匹配到表 %s，开始增强", path, table_name)

        # 遍历所有 HTTP 方法
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            operation = path_item.get(method)
            if operation:
                _enrich_operation(operation, col_map)

    return result


def _guess_table_from_path(path: str, table_names: set) -> str | None:
    """从 API 路径猜测对应的数据库表名。

    策略：
    1. 跳过路径参数（{xxx}）
    2. 从最后一段往前遍历
    3. 规范化（小写、- → _）
    4. 尝试去掉末尾 s（单数化，但不处理 ss）
    5. 直接匹配 + 带前缀匹配（t_/sys_/tb_）
    """
    # 提取非参数路径段
    segments = [seg for seg in path.split("/") if seg and not seg.startswith("{")]
    if not segments:
        return None

    # 常见 API 前缀，跳过不作为表名候选
    _SKIP_SEGMENTS = {"api", "v1", "v2", "v3", "rest", "service", "services"}
    _COMMON_PREFIXES = ("t_", "sys_", "tb_")

    # 从最后一段往前尝试
    for seg in reversed(segments):
        if seg.lower() in _SKIP_SEGMENTS:
            continue

        # 规范化：小写 + 连字符转下划线
        normalized = seg.lower().replace("-", "_")

        candidates = [normalized]

        # 单数化：去掉末尾 s（但不处理 ss 结尾）
        if normalized.endswith("s") and not normalized.endswith("ss"):
            candidates.append(normalized[:-1])

        for candidate in candidates:
            # 直接匹配
            if candidate in table_names:
                return candidate

            # 带前缀匹配
            for prefix in _COMMON_PREFIXES:
                prefixed = prefix + candidate
                if prefixed in table_names:
                    return prefixed

    return None


def _enrich_operation(operation: dict, col_map: dict) -> None:
    """增强单个操作（GET/POST 等）的响应 schema。"""
    responses = operation.get("responses", {})
    for status_code, response in responses.items():
        content = response.get("content", {})
        for media_type, media_obj in content.items():
            schema = media_obj.get("schema")
            if schema:
                _enrich_schema(schema, col_map)


def _enrich_schema(schema: dict, col_map: dict) -> None:
    """递归增强 schema。

    处理：
    - array：进入 items
    - object：检查 properties
    """
    schema_type = schema.get("type")

    if schema_type == "array":
        items = schema.get("items")
        if items:
            _enrich_schema(items, col_map)

    elif schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            # 递归处理嵌套对象/数组
            if prop_schema.get("type") in ("object", "array") or "properties" in prop_schema:
                _enrich_schema(prop_schema, col_map)

            # 精确匹配列名（区分大小写查找，找不到尝试小写）
            col = col_map.get(prop_name) or col_map.get(prop_name.lower())
            if col:
                _apply_column_info(prop_schema, col)


def _apply_column_info(prop_schema: dict, col: ColumnInfo) -> None:
    """将列元数据写入属性 schema（仅当字段不存在时才写入）。

    应用规则：
    - description ← col.comment
    - enum ← col.enum_values 中的 value（跳过 None）
    - maxLength ← col.max_length（仅 string 类型）
    - nullable ← col.nullable
    """
    # description：来自列注释
    if col.comment and "description" not in prop_schema:
        prop_schema["description"] = col.comment

    # enum：来自采样枚举值
    if col.enum_values is not None and "enum" not in prop_schema:
        values = [ev["value"] for ev in col.enum_values if ev.get("value") is not None]
        if values:
            prop_schema["enum"] = values

    # maxLength：仅对 string 类型有意义
    if col.max_length is not None and "maxLength" not in prop_schema:
        if prop_schema.get("type") == "string":
            prop_schema["maxLength"] = col.max_length

    # nullable：列是否允许 NULL
    if "nullable" not in prop_schema:
        prop_schema["nullable"] = col.nullable
