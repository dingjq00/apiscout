"""JS 静态分析测试 — 从 JS 源码提取 API 端点"""
from apiscout.core.crawler.js_analyzer import extract_api_endpoints_from_js


def test_extract_fetch_urls():
    """提取 fetch() 调用中的 URL"""
    js = '''
    fetch("/api/equipment/list").then(r => r.json())
    fetch('/api/users/profile')
    '''
    endpoints = extract_api_endpoints_from_js(js)
    assert "/api/equipment/list" in endpoints
    assert "/api/users/profile" in endpoints


def test_extract_axios_urls():
    """提取 axios 调用中的 URL"""
    js = '''
    axios.get("/api/equipment/search")
    axios.post("/api/equipment/create", data)
    axios.delete(`/api/equipment/${id}`)
    '''
    endpoints = extract_api_endpoints_from_js(js)
    assert "/api/equipment/search" in endpoints
    assert "/api/equipment/create" in endpoints


def test_extract_base_url():
    """提取 baseURL 配置"""
    js = '''
    const instance = axios.create({
        baseURL: "/api/v2"
    })
    '''
    endpoints = extract_api_endpoints_from_js(js)
    assert "/api/v2" in endpoints


def test_extract_string_patterns():
    """提取字符串中的 API 路径模式"""
    js = '''
    const API = {
        EQUIPMENT_LIST: "/api/equipment/list",
        FAULT_DETAIL: "/v1/fault/detail",
    }
    '''
    endpoints = extract_api_endpoints_from_js(js)
    assert "/api/equipment/list" in endpoints
    assert "/v1/fault/detail" in endpoints


def test_dedup_results():
    """结果去重"""
    js = '''
    fetch("/api/test")
    axios.get("/api/test")
    '''
    endpoints = extract_api_endpoints_from_js(js)
    assert endpoints.count("/api/test") == 1


def test_ignore_static_resources():
    """忽略静态资源路径"""
    js = '''
    fetch("/api/data")
    import "/static/module.js"
    const img = "/assets/logo.png"
    '''
    endpoints = extract_api_endpoints_from_js(js)
    assert "/api/data" in endpoints
    assert "/static/module.js" not in endpoints
    assert "/assets/logo.png" not in endpoints
