"""认证检测测试"""
from apiscout.core.analyzer.auth_detector import AuthDetector


def test_detect_bearer_jwt():
    detector = AuthDetector()
    headers_list = [
        {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzExNzAwMDAwfQ.sig"},
        {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyIiwiZXhwIjoxNzExNzAwMDAwfQ.sig"},
    ]
    result = detector.detect(headers_list)
    assert result["type"] == "bearer_jwt"
    assert result["token_analysis"]["algorithm"] == "RS256"


def test_detect_basic_auth():
    detector = AuthDetector()
    headers_list = [{"Authorization": "Basic dXNlcjpwYXNz"}]
    result = detector.detect(headers_list)
    assert result["type"] == "basic"


def test_detect_api_key():
    detector = AuthDetector()
    headers_list = [{"X-API-Key": "abc123"}, {"X-API-Key": "abc123"}]
    result = detector.detect(headers_list)
    assert result["type"] == "api_key"
    assert result["header"] == "X-Api-Key"


def test_detect_kingdee():
    """金蝶非标认证"""
    detector = AuthDetector()
    headers_list = [
        {"X-KDApi-AcctID": "001", "X-KDApi-AppID": "app1", "X-KDApi-AppSec": "secret"},
    ]
    result = detector.detect(headers_list)
    assert result["type"] == "custom_header"
    assert result["vendor"] == "kingdee"


def test_detect_cookie_session():
    detector = AuthDetector()
    headers_list = [{"Cookie": "session_token=abc123; theme=dark"}]
    result = detector.detect(headers_list)
    assert result["type"] == "cookie"
    assert "session_token" in result["cookies"]


def test_no_auth():
    detector = AuthDetector()
    headers_list = [{"Accept": "application/json"}]
    result = detector.detect(headers_list)
    assert result["type"] == "none"
