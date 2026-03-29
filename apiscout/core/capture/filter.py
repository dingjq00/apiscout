"""请求过滤 + 协议检测"""
import fnmatch
from urllib.parse import urlparse


class RequestFilter:
    """决定哪些请求值得捕获"""

    # 需要捕获的资源类型
    CAPTURE_TYPES = {"fetch", "xhr", "document"}
    # 跳过的文件扩展名
    SKIP_EXTENSIONS = {".css", ".js", ".png", ".jpg", ".gif", ".svg",
                       ".woff", ".woff2", ".ttf", ".ico", ".mp4", ".mp3"}

    def __init__(self, target_origin: str, exclude_patterns: list[str] | None = None):
        parsed = urlparse(target_origin)
        self.target_origin = f"{parsed.scheme}://{parsed.netloc}"
        self.exclude_patterns = exclude_patterns or []

    def should_capture(self, url: str, resource_type: str,
                       content_type: str, status: int) -> bool:
        """判断这个请求是否应该被捕获"""
        # 1. 资源类型过滤
        if resource_type not in self.CAPTURE_TYPES:
            return False

        # 2. 同源检查
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin != self.target_origin:
            return False

        # 3. 文件扩展名过滤
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in self.SKIP_EXTENSIONS):
            return False

        # 4. 排除模式
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(parsed.path, pattern):
                return False

        return True


class ProtocolDetector:
    """从请求/响应特征判断 API 协议类型"""

    def classify(self, url: str, request_body, response_content_type: str) -> str:
        # GraphQL: URL 包含 graphql，或 body 有 query 字段
        path = urlparse(url).path.rstrip("/")
        if path.endswith("/graphql") or path.endswith("/gql"):
            return "graphql"
        if isinstance(request_body, dict) and "query" in request_body:
            return "graphql"

        # SOAP: XML content type + envelope 结构
        if response_content_type and "xml" in response_content_type:
            if isinstance(request_body, str) and "<soap:" in request_body.lower():
                return "soap"
            return "rest_xml"

        # JSON-RPC: body 有 jsonrpc 字段
        if isinstance(request_body, dict) and "jsonrpc" in request_body:
            return "jsonrpc"

        # gRPC-Web
        if response_content_type and "grpc" in response_content_type:
            return "grpc"

        # 默认：REST + JSON
        if response_content_type and "json" in response_content_type:
            return "rest"

        return "unknown"
