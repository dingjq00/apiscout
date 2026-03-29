"""路径参数化归并 — 参数化后 hash 聚合，非 Radix Tree（V1 规模 dict 足够）"""
import re
from collections import defaultdict


# 保留词 — 这些路径段永远不参数化（偷师 Optic 路径推断启发式）
RESERVED_SEGMENTS = {
    "api", "v1", "v2", "v3", "v4", "static", "admin", "auth",
    "public", "internal", "graphql", "ws", "health", "metrics",
}

# 日期格式 — 不参数化
DATE_PATTERNS = [
    re.compile(r'^\d{4}\d{2}\d{2}$'),       # 20260329
    re.compile(r'^\d{4}-\d{2}-\d{2}$'),      # 2026-03-29
]

# 参数检测模式，按优先级排列
PARAM_PATTERNS = [
    (re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I), 'uuid'),
    (re.compile(r'^\d{15,}$'), 'snowflakeId'),
    (re.compile(r'^[0-9a-f]{24}$'), 'objectId'),
    (re.compile(r'^[A-Z]{2,4}\d{8,}$'), 'code'),
    (re.compile(r'^\d+$'), 'id'),
    (re.compile(r'^[0-9a-f]{6,12}$'), 'hash'),
]


def _singularize(word: str) -> str:
    """简单的英文单数化（覆盖常见情况）"""
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("ses") or word.endswith("xes"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


class PathParameterizer:
    """将具体路径转为参数化路径"""

    def parameterize(self, path: str) -> str:
        segments = path.strip("/").split("/")
        result = []
        prev_segment = None

        for seg in segments:
            param_type = self._detect_param(seg)
            if param_type:
                if param_type == "id" and prev_segment:
                    name = _singularize(prev_segment) + "Id"
                else:
                    name = param_type
                result.append("{" + name + "}")
            else:
                result.append(seg)
                prev_segment = seg

        return "/" + "/".join(result)

    def _detect_param(self, segment: str) -> str | None:
        """检测路径段是否是参数"""
        # 保留词永远不参数化
        if segment.lower() in RESERVED_SEGMENTS:
            return None
        # 日期段不参数化
        for dp in DATE_PATTERNS:
            if dp.match(segment):
                return None
        for pattern, param_type in PARAM_PATTERNS:
            if pattern.match(segment):
                return param_type
        return None


class EndpointRouter:
    """端点归并 — 将具体路径归并到参数化端点"""

    def __init__(self):
        self._parameterizer = PathParameterizer()
        self._endpoints: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"count": 0, "concrete_paths": set()}
        )

    def add(self, path: str, method: str):
        parameterized = self._parameterizer.parameterize(path)
        key = (parameterized, method.upper())
        self._endpoints[key]["count"] += 1
        self._endpoints[key]["concrete_paths"].add(path)

    def lookup(self, path: str, method: str) -> str:
        parameterized = self._parameterizer.parameterize(path)
        return parameterized

    def get_endpoints(self) -> list[dict]:
        result = []
        for (path, method), data in self._endpoints.items():
            result.append({
                "path": path,
                "method": method,
                "observation_count": data["count"],
                "concrete_paths": list(data["concrete_paths"]),
            })
        return sorted(result, key=lambda e: (e["path"], e["method"]))
