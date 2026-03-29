"""JS 静态分析提取 API 端点 — 偷师 Katana + LinkFinder"""
import re


# API 端点提取正则（偷师清单 #8 Katana + #11 LinkFinder）
ENDPOINT_PATTERNS = [
    re.compile(r'["\'](/api/[^"\'?#\s]+)["\']'),
    re.compile(r'["\'](/v[0-9]+/[^"\'?#\s]+)["\']'),
    re.compile(r'baseURL\s*[:=]\s*["\']([^"\']+)'),
    re.compile(r'fetch\s*\(\s*["\']([^"\']+)'),
    re.compile(r'axios\.[a-z]+\s*\(\s*["\']([^"\']+)'),
    re.compile(r'\.\s*(?:get|post|put|delete|patch)\s*\(\s*[`"\']([^`"\']+)'),
]

# 静态资源扩展名 — 排除
STATIC_EXTENSIONS = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".woff", ".woff2", ".ttf", ".ico", ".mp4", ".mp3",
    ".map", ".html", ".htm",
}

# 排除路径前缀
EXCLUDE_PREFIXES = {"/static/", "/assets/", "/public/", "/favicon"}


def extract_api_endpoints_from_js(js_content: str) -> list[str]:
    """从 JS 源码中提取 API 端点"""
    seen = set()
    results = []

    for pattern in ENDPOINT_PATTERNS:
        for match in pattern.finditer(js_content):
            endpoint = match.group(1)
            # 清理：去掉模板字符串变量部分
            endpoint = re.sub(r'\$\{[^}]*\}', '', endpoint)
            endpoint = endpoint.rstrip("/") or "/"

            if not _is_valid_endpoint(endpoint):
                continue

            if endpoint not in seen:
                seen.add(endpoint)
                results.append(endpoint)

    return results


def _is_valid_endpoint(endpoint: str) -> bool:
    """验证是否是有效的 API 端点"""
    # 必须以 / 开头
    if not endpoint.startswith("/"):
        return False

    # 排除静态资源
    lower = endpoint.lower()
    for ext in STATIC_EXTENSIONS:
        if lower.endswith(ext):
            return False

    # 排除已知非 API 路径
    for prefix in EXCLUDE_PREFIXES:
        if lower.startswith(prefix):
            return False

    # 太短不是 API（单个 /）
    if len(endpoint) < 3:
        return False

    return True
