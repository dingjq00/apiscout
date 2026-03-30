"""Playwright 响应监听 → CaptureStore"""
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apiscout.core.capture.store import CaptureRecord, CaptureStore
from apiscout.core.capture.filter import RequestFilter, ProtocolDetector

# 避免在没有 playwright 的环境（如 CI/测试）中报错
if TYPE_CHECKING:
    from playwright.async_api import Page, Response

logger = logging.getLogger(__name__)

_protocol_detector = ProtocolDetector()


def build_capture_record(
    page_url: str,
    method: str,
    url: str,
    request_headers: dict,
    request_body,
    status: int,
    response_headers: dict,
    response_body,
    resource_type: str,
    max_body_size: int = 524288,
) -> CaptureRecord:
    """从原始数据构建 CaptureRecord"""
    # 协议检测
    content_type = response_headers.get("Content-Type", response_headers.get("content-type", ""))
    protocol = _protocol_detector.classify(url, request_body, content_type)

    # 大 body 截断
    if response_body is not None:
        body_str = json.dumps(response_body, ensure_ascii=False) if not isinstance(response_body, str) else response_body
        if len(body_str) > max_body_size:
            response_body = {
                "_truncated": True,
                "_original_size": len(body_str),
            }

    return CaptureRecord(
        seq=0,  # store.append 时会重新分配
        timestamp=datetime.now(timezone.utc).isoformat(),
        page_url=page_url,
        method=method,
        url=url,
        request_headers=request_headers,
        request_body=request_body,
        status=status,
        response_headers=dict(response_headers),
        response_body=response_body,
        resource_type=resource_type,
        protocol=protocol,
    )


class PageRecorder:
    """挂载到 Playwright Page 上，监听所有响应并写入 store"""

    def __init__(self, store: CaptureStore, request_filter: RequestFilter,
                 max_body_size: int = 524288):
        self.store = store
        self.filter = request_filter
        self.max_body_size = max_body_size
        self.captured_count = 0
        self.auth_failure_count = 0  # 连续 401/403 计数

    async def attach(self, page: "Page"):
        """挂载到 page，开始监听"""
        page.on("response", self._on_response)

    async def _on_response(self, response: "Response"):
        """响应回调"""
        request = response.request
        resource_type = request.resource_type
        content_type = response.headers.get("content-type", "")

        # 过滤（filter 已改为黑名单模式，不再需要 origin 自动切换）
        if not self.filter.should_capture(
            url=request.url,
            resource_type=resource_type,
            content_type=content_type,
            status=response.status,
        ):
            return

        # Session 过期检测
        if response.status in (401, 403):
            self.auth_failure_count += 1
            if self.auth_failure_count >= 3:
                logger.warning("连续 %d 个认证失败，session 可能已过期", self.auth_failure_count)
            return
        self.auth_failure_count = 0

        # 解析响应 body
        try:
            response_body = await response.json()
        except Exception:
            try:
                response_body = await response.text()
            except Exception:
                logger.debug("响应 body 解析失败: %s %s", request.method, request.url)
                response_body = None

        # 解析请求 body
        request_body = None
        if request.post_data:
            try:
                request_body = json.loads(request.post_data)
            except (json.JSONDecodeError, TypeError):
                request_body = request.post_data

        record = build_capture_record(
            page_url=response.frame.url if response.frame else "",
            method=request.method,
            url=request.url,
            request_headers=dict(request.headers),
            request_body=request_body,
            status=response.status,
            response_headers=dict(response.headers),
            response_body=response_body,
            resource_type=resource_type,
            max_body_size=self.max_body_size,
        )

        self.store.append(record)
        self.captured_count += 1
        logger.debug("捕获: %s %s → %d", request.method, request.url, response.status)
