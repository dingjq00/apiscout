"""调试：看看页面上到底有什么菜单元素"""
import asyncio, sys
from playwright.async_api import async_playwright

async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.gtshebei.com"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--ignore-certificate-errors"])
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        print("请登录，然后按 Enter...")
        await asyncio.get_event_loop().run_in_executor(None, input)

        print(f"\n当前 URL: {page.url}\n")

        # 试所有可能的选择器
        selectors = [
            ".el-menu-item", ".el-submenu__title", ".el-submenu",
            ".ant-menu-item", ".ant-menu-submenu-title",
            "nav a", "[role='menuitem']", ".menu-item", ".nav-item",
            ".sidebar-menu li", ".navbar a", "header nav a",
            # 通用：所有看起来像菜单的东西
            "[class*='menu']", "[class*='nav']", "[class*='Menu']", "[class*='Nav']",
        ]
        for sel in selectors:
            try:
                items = await page.query_selector_all(sel)
                if items:
                    texts = []
                    for item in items[:5]:
                        t = (await item.text_content() or "").strip()[:30]
                        v = await item.is_visible()
                        texts.append(f"{'✅' if v else '❌'}{t}")
                    print(f"  {sel:30s} → {len(items)} 个  {texts}")
            except:
                pass

        # 额外：看看顶部导航栏的 HTML 结构
        print("\n--- 顶部导航 HTML ---")
        nav_html = await page.evaluate("""
            () => {
                const nav = document.querySelector('nav, .el-menu, [class*=header], [class*=navbar], [class*=topbar]');
                return nav ? nav.outerHTML.substring(0, 2000) : '未找到导航元素';
            }
        """)
        print(nav_html[:1500])

        await browser.close()

asyncio.run(main())
