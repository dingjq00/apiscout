"""DOM 链接提取测试"""
from apiscout.core.crawler.link_extractor import extract_links_from_html, normalize_url


def test_extract_anchor_links():
    """提取 a[href] 链接"""
    html = '''
    <html><body>
        <a href="/equipment/list">设备列表</a>
        <a href="/equipment/123">设备详情</a>
        <a href="https://external.com/page">外部链接</a>
    </body></html>
    '''
    links = extract_links_from_html(html, base_url="https://eam.example.com")
    assert "https://eam.example.com/equipment/list" in links
    assert "https://eam.example.com/equipment/123" in links
    # 外部链接被排除（同源过滤）
    assert "https://external.com/page" not in links


def test_extract_nav_links():
    """提取导航菜单链接"""
    html = '''
    <html><body>
        <nav>
            <a href="/dashboard">仪表盘</a>
            <a href="/settings">设置</a>
        </nav>
        <div class="sidebar">
            <a href="/reports">报告</a>
        </div>
    </body></html>
    '''
    links = extract_links_from_html(html, base_url="https://eam.example.com")
    assert "https://eam.example.com/dashboard" in links
    assert "https://eam.example.com/settings" in links
    assert "https://eam.example.com/reports" in links


def test_extract_data_attributes():
    """提取 data-href, data-url 等属性链接"""
    html = '''
    <html><body>
        <div data-href="/api/data">数据</div>
        <button data-url="/module/action">操作</button>
    </body></html>
    '''
    links = extract_links_from_html(html, base_url="https://eam.example.com")
    assert "https://eam.example.com/api/data" in links
    assert "https://eam.example.com/module/action" in links


def test_exclude_patterns():
    """排除模式过滤"""
    html = '''
    <html><body>
        <a href="/equipment/list">设备列表</a>
        <a href="/logout">退出</a>
        <a href="/static/logo.png">Logo</a>
    </body></html>
    '''
    links = extract_links_from_html(
        html,
        base_url="https://eam.example.com",
        exclude_patterns=["/logout", "/static/*"],
    )
    assert "https://eam.example.com/equipment/list" in links
    assert "https://eam.example.com/logout" not in links
    assert "https://eam.example.com/static/logo.png" not in links


def test_spa_hash_routes():
    """SPA hash 路由（#/page）保留，纯锚点（#section）去掉"""
    html = '''
    <html><body>
        <a href="#/devices">设备管理</a>
        <a href="#/maintenance">维修保养</a>
        <a href="#/inspection">点检巡检</a>
        <a href="#section">页内锚点</a>
    </body></html>
    '''
    links = extract_links_from_html(html, base_url="https://eam.example.com/#/home")
    # SPA hash 路由应保留
    assert any("#/devices" in l for l in links)
    assert any("#/maintenance" in l for l in links)
    # 纯锚点应去掉
    assert not any(l.endswith("#section") for l in links)


def test_skip_link_tags_and_static_resources():
    """不从 <link> 标签提取，不导航到静态资源"""
    html = '''
    <html>
    <head>
        <link rel="icon" href="/icons/icon-2732x2048.png?-990272340">
        <link rel="stylesheet" href="/styles/main.css">
        <link rel="manifest" href="/manifest.json">
    </head>
    <body>
        <a href="/dashboard">仪表盘</a>
        <a href="/report.pdf">下载报告</a>
    </body></html>
    '''
    links = extract_links_from_html(html, base_url="https://eam.example.com")
    # <link> 标签的 href 不应被提取
    assert not any("icon" in l for l in links)
    assert not any(".css" in l for l in links)
    # <a> 标签的正常链接应该保留
    assert "https://eam.example.com/dashboard" in links
    # 但 .pdf 静态资源也应过滤
    assert not any(".pdf" in l for l in links)


def test_normalize_url():
    """URL 规范化"""
    assert normalize_url("https://ex.com/path?a=1#frag") == "https://ex.com/path?a=1"
    assert normalize_url("https://ex.com/path/") == "https://ex.com/path"
    assert normalize_url("https://ex.com") == "https://ex.com"


def test_deduplicate_links():
    """去重"""
    html = '''
    <html><body>
        <a href="/page">Page</a>
        <a href="/page">Page Again</a>
        <a href="/page#section">Page Section</a>
    </body></html>
    '''
    links = extract_links_from_html(html, base_url="https://eam.example.com")
    # /page and /page#section should normalize to same URL
    assert links.count("https://eam.example.com/page") == 1
