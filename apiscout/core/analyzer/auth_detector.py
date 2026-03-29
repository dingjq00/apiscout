"""认证模式检测 — 偷师 OpenAPI DevTools + 中国 ERP 非标扩展"""
import base64
import json
import re


# 已知的 API Key 头名
API_KEY_HEADERS = {
    "x-api-key", "x-auth-token", "api-key", "apikey", "auth-token",
    "x-token", "token", "x-access-token", "access-token",
}

# 中国 ERP 非标认证头
CHINESE_ERP_HEADERS = {
    "kingdee": {"x-kdapi-acctid", "x-kdapi-appid", "x-kdapi-appsec", "x-kdapi-username"},
    "yonyou": {"x-yonyou-appkey", "x-yonyou-appsecret"},
}

# Session cookie 关键词
SESSION_COOKIE_KEYWORDS = {"token", "session", "jwt", "auth", "sid", "jsessionid", "access"}


class AuthDetector:
    """从捕获的请求头中检测认证方式"""

    def detect(self, headers_list: list[dict]) -> dict:
        if not headers_list:
            return {"type": "none"}

        all_headers = {}
        for h in headers_list:
            for k, v in h.items():
                all_headers.setdefault(k.lower(), []).append(v)

        # 1. HTTP Authorization header
        auth_values = all_headers.get("authorization", [])
        if auth_values:
            return self._analyze_authorization(auth_values)

        # 2. 中国 ERP 非标认证
        for vendor, expected_headers in CHINESE_ERP_HEADERS.items():
            found = expected_headers & set(all_headers.keys())
            if len(found) >= 2:
                return {
                    "type": "custom_header",
                    "vendor": vendor,
                    "headers": {h: all_headers[h][0] for h in found},
                }

        # 3. API Key header
        for header_name in all_headers:
            if header_name in API_KEY_HEADERS:
                return {
                    "type": "api_key",
                    "header": header_name.title().replace(" ", "-"),
                    "sample": all_headers[header_name][0][:8] + "...",
                }

        # 4. Cookie/Session
        cookie_values = all_headers.get("cookie", [])
        if cookie_values:
            session_cookies = self._find_session_cookies(cookie_values[0])
            if session_cookies:
                return {
                    "type": "cookie",
                    "cookies": session_cookies,
                }

        return {"type": "none"}

    def _analyze_authorization(self, values: list[str]) -> dict:
        sample = values[0]
        if sample.lower().startswith("bearer "):
            token = sample[7:]
            jwt_info = self._parse_jwt(token)
            if jwt_info:
                return {
                    "type": "bearer_jwt",
                    "token_analysis": jwt_info,
                }
            return {"type": "bearer", "token_prefix": token[:16] + "..."}

        if sample.lower().startswith("basic "):
            return {"type": "basic"}

        if sample.lower().startswith("digest "):
            return {"type": "digest"}

        return {"type": "bearer", "raw_prefix": sample[:20] + "..."}

    def _parse_jwt(self, token: str) -> dict | None:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        try:
            header_b64 = parts[0] + "=" * (4 - len(parts[0]) % 4)
            header = json.loads(base64.urlsafe_b64decode(header_b64))

            payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))

            result = {
                "algorithm": header.get("alg", "unknown"),
                "claims": sorted(payload.keys()),
            }
            if "exp" in payload:
                result["has_expiration"] = True
            return result
        except Exception:
            return None

    def _find_session_cookies(self, cookie_string: str) -> list[str]:
        cookies = {}
        for pair in cookie_string.split(";"):
            pair = pair.strip()
            if "=" in pair:
                name, _, _ = pair.partition("=")
                cookies[name.strip()] = True

        return [
            name for name in cookies
            if any(kw in name.lower() for kw in SESSION_COOKIE_KEYWORDS)
        ]
