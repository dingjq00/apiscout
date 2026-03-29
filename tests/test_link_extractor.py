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
