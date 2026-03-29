"""Schema 推断引擎 — genson 合并 + format/enum 增强
偷师 OpenAPI DevTools: 多次观察合并，required = 交集
"""
import re
from collections import defaultdict
from genson import SchemaBuilder


# String format 检测正则
FORMAT_PATTERNS = [
    ("date-time", re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}')),
    ("date", re.compile(r'^\d{4}-\d{2}-\d{2}$')),
    ("uuid", re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)),
    ("email", re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')),
    ("uri", re.compile(r'^https?://')),
    ("ipv4", re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')),
]


class SchemaEngine:
    """JSON Schema 推断引擎"""

    def __init__(self):
        self._builder = SchemaBuilder()
        self._observations: list[dict] = []
        self._field_values: dict[str, list] = defaultdict(list)

    def add_observation(self, obj: dict | list):
        self._builder.add_object(obj)
        self._observations.append(obj)
        if isinstance(obj, dict):
            self._collect_field_values(obj)

    def _collect_field_values(self, obj: dict, prefix: str = ""):
        for key, value in obj.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._collect_field_values(value, full_key)
            elif isinstance(value, list):
                pass
            else:
                self._field_values[full_key].append(value)

    def get_schema(self) -> dict:
        return self._builder.to_schema()

    def enhance_schema(self, schema: dict) -> dict:
        if schema.get("type") != "object" or "properties" not in schema:
            return schema

        enhanced = dict(schema)
        enhanced["properties"] = {}

        for prop_name, prop_schema in schema["properties"].items():
            prop_schema = dict(prop_schema)

            # Format 检测（只对 string 类型）
            if prop_schema.get("type") == "string":
                values = self._field_values.get(prop_name, [])
                fmt = self._detect_format(values)
                if fmt:
                    prop_schema["format"] = fmt

            # Enum 检测
            values = self._field_values.get(prop_name, [])
            if values:
                enum_values = self._detect_enum(values)
                if enum_values is not None:
                    prop_schema["enum"] = enum_values

            # 递归增强嵌套对象
            if prop_schema.get("type") == "object" and "properties" in prop_schema:
                prop_schema = self.enhance_schema(prop_schema)

            enhanced["properties"][prop_name] = prop_schema

        return enhanced

    def _detect_format(self, values: list) -> str | None:
        str_values = [v for v in values if isinstance(v, str) and v]
        if not str_values:
            return None
        for fmt_name, pattern in FORMAT_PATTERNS:
            match_count = sum(1 for v in str_values if pattern.match(v))
            if match_count >= len(str_values) * 0.8:
                return fmt_name
        return None

    def _detect_enum(self, values: list) -> list | None:
        non_null = [v for v in values if v is not None]
        if len(non_null) < 3:
            return None
        unique = set(non_null)
        if len(unique) > 10:
            return None
        if len(non_null) > len(unique) and (len(non_null) - len(unique)) / len(non_null) > 0.3:
            return sorted(unique, key=lambda x: (isinstance(x, str), x))
        return None
