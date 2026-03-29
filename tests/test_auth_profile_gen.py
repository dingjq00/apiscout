"""认证档案生成测试"""
from apiscout.core.generator.auth_profile import generate_auth_profile, find_login_endpoint
from apiscout.core.capture.store import CaptureRecord


def _make_record(method, url, request_body=None, response_body=None, request_headers=None):
    return CaptureRecord(
        seq=0, timestamp="", page_url="", method=method, url=url,
        request_headers=request_headers or {},
        request_body=request_body,
        status=200,
        response_headers={"Content-Type": "application/json"},
        response_body=response_body or {},
        resource_type="fetch", protocol="rest",
    )


def test_generate_profile_bearer_jwt():
    """Bearer JWT 认证档案"""
    auth_info = {
        "type": "bearer_jwt",
        "token_analysis": {"algorithm": "RS256", "claims": ["sub", "exp", "iat"], "has_expiration": True},
    }
    profile = generate_auth_profile(auth_info)
    assert profile["auth"]["type"] == "bearer_jwt"
    assert profile["auth"]["token_analysis"]["algorithm"] == "RS256"
    assert profile["insight68_config_hint"]["auth_adapter"] == "jwt_bearer"


def test_generate_profile_api_key():
    """API Key 认证档案"""
    auth_info = {"type": "api_key", "header": "X-Api-Key", "sample": "abc123..."}
    profile = generate_auth_profile(auth_info)
    assert profile["insight68_config_hint"]["auth_adapter"] == "api_key"


def test_generate_profile_kingdee():
    """金蝶非标认证档案"""
    auth_info = {"type": "custom_header", "vendor": "kingdee", "headers": {"x-kdapi-acctid": "001"}}
    profile = generate_auth_profile(auth_info)
    assert profile["insight68_config_hint"]["auth_adapter"] == "custom_header"
    assert profile["insight68_config_hint"]["vendor"] == "kingdee"


def test_find_login_endpoint():
    """从捕获记录中识别登录端点"""
    records = [
        _make_record("POST", "https://ex.com/api/auth/login",
                     request_body={"username": "admin", "password": "123"},
                     response_body={"code": 0, "data": {"accessToken": "eyJ...", "refreshToken": "abc"}}),
        _make_record("GET", "https://ex.com/api/equipment/list",
                     response_body={"items": []}),
    ]
    login_info = find_login_endpoint(records)
    assert login_info is not None
    assert login_info["endpoint"] == "POST /api/auth/login"
    assert "accessToken" in login_info["token_location"]


def test_find_refresh_endpoint():
    """识别 refresh 端点"""
    records = [
        _make_record("POST", "https://ex.com/api/auth/refresh",
                     request_body={"refreshToken": "abc123"},
                     response_body={"accessToken": "eyJ...new"}),
    ]
    login_info = find_login_endpoint(records)
    assert login_info is not None
    assert login_info.get("refresh_endpoint") == "POST /api/auth/refresh"


def test_no_login_endpoint():
    """没有登录请求"""
    records = [
        _make_record("GET", "https://ex.com/api/list", response_body={"items": []}),
    ]
    login_info = find_login_endpoint(records)
    assert login_info is None
