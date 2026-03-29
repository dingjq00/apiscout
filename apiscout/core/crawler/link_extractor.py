"""DOM 链接提取 — 偷师 Crawlee 的 enqueueLinks 思路"""
import fnmatch
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


# 链接提取的 HTML 属性
LINK_ATTRIBUTES = ["href", "data-href", "data-url", "data-route"]


class _LinkParser(HTMLParser):
    """从 HTML 中提取链接"""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        for attr_name in LINK_ATTRIBUTES:
            value = attrs_dict.get(attr_name)
            if value and not value.startswith(("javascript:", "mailto:", "tel:", "#")):
                self.links.append(value)


def normalize_url(url: str) -> str:
    """URL 规范化：去 fragment，去尾部斜杠"""
    parsed = urlparse(url)
    # 去 fragment
    normalized = parsed._replace(fragment="")
    result = normalized.geturl()
    # 去尾部斜杠（但保留根路径 /）
    if result.endswith("/") and urlparse(result).path != "/":
        result = result.rstrip("/")
    return result


def extract_links_from_html(
    html: str,
    base_url: str,
    exclude_patterns: list[str] | None = None,
) -> list[str]:
    """从 HTML 字符串提取同源链接"""
    exclude_patterns = exclude_patterns or []
    base_parsed = urlparse(base_url)
    base_origin = f"{base_parsed.scheme}://{base_parsed.netloc}"

    parser = _LinkParser()
    parser.feed(html)

    seen = set()
    results = []

    for raw_link in parser.links:
        # 解析为绝对 URL
        absolute = urljoin(base_url, raw_link)
        normalized = normalize_url(absolute)

        # 同源检查
        link_parsed = urlparse(normalized)
        link_origin = f"{link_parsed.scheme}://{link_parsed.netloc}"
        if link_origin != base_origin:
            continue

        # 排除模式
        excluded = False
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(link_parsed.path, pattern):
                excluded = True
                break
        if excluded:
            continue

        # 去重
        if normalized not in seen:
            seen.add(normalized)
            results.append(normalized)

    return results
