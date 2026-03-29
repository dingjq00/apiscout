"""APIScout CLI 入口"""
import asyncio
import logging
import click
from apiscout import __version__

logger = logging.getLogger("apiscout")


@click.group()
@click.version_option(__version__, prog_name="apiscout")
@click.option("--debug", is_flag=True, help="显示 DEBUG 日志")
def main(debug):
    """APIScout — 给我一个 URL，还你一份 OpenAPI spec"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


@main.command()
@click.argument("url")
@click.option("--output", "-o", default=None, help="输出目录（默认自动用域名命名）")
@click.option("--title", default=None, help="API 文档标题")
@click.option("--manual", is_flag=True, help="纯手动模式（不自动探索，只录你的操作）")
@click.option("--append", is_flag=True, help="追加模式（多次扫描累积数据）")
def scan(url, output, title, manual, append):
    """完整扫描：打开浏览器 → 登录 → 探索 → 生成文档

    \b
    示例：
      apiscout scan https://eam.customer.com
      apiscout scan https://eam.customer.com --manual
      apiscout scan https://eam.customer.com -o ./my_output
    """
    from urllib.parse import urlparse
    # 默认输出目录用域名命名
    if not output:
        host = urlparse(url).netloc.replace(":", "_")
        output = f"./output/{host}"
    asyncio.run(_scan(url, output, title, manual, append))


async def _scan(url, output, title, manual, append):
    from pathlib import Path
    from urllib.parse import urlparse
    from playwright.async_api import async_playwright
    from apiscout.core.capture.store import CaptureStore
    from apiscout.core.capture.filter import RequestFilter
    from apiscout.core.capture.recorder import PageRecorder
    from apiscout.core.workflow import analyze_capture, generate_outputs
    from apiscout.core.generator.swagger_ui import generate_swagger_html

    parsed = urlparse(url)
    target_origin = f"{parsed.scheme}://{parsed.netloc}"
    if not title:
        title = f"{parsed.netloc} API"

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    capture_file = output_dir / "capture.jsonl"

    click.echo(f"APIScout v{__version__}")
    click.echo(f"目标: {url}")
    click.echo(f"输出: {output_dir}")
    click.echo(f"模式: {'手动' if manual else '自动+手动'}")
    click.echo()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--ignore-certificate-errors"],
        )
        context = await browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()

        # 初始化捕获
        store = CaptureStore(capture_file)
        request_filter = RequestFilter(target_origin=target_origin)
        recorder = PageRecorder(store, request_filter)
        await recorder.attach(page)

        # 打开目标
        click.echo(">>> 打开目标系统...")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        click.echo()
        click.echo("=" * 50)
        click.echo("请在浏览器中登录系统")
        click.echo("登录完成后按 Enter 继续")
        click.echo("=" * 50)
        await asyncio.get_event_loop().run_in_executor(None, input)

        # 检测域名跳转
        current_url = page.url
        actual_origin = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}"
        if actual_origin != target_origin:
            click.echo(f"检测到域名跳转: {target_origin} → {actual_origin}")
            recorder.filter.target_origin = actual_origin
            target_origin = actual_origin

        click.echo(f"当前: {current_url}")
        click.echo(f"已捕获: {recorder.captured_count} 请求")

        # 框架检测
        click.echo()
        click.echo(">>> 框架检测...")
        import apiscout.adapters.jmix       # noqa: F401
        import apiscout.adapters.spring_boot  # noqa: F401
        import apiscout.adapters.ruoyi      # noqa: F401
        from apiscout.adapters.registry import detect_framework

        matches = await detect_framework(page, target_origin)
        adapter_spec = None
        if matches:
            best = matches[0]
            click.echo(f"检测到: {best.name} (置信度 {best.confidence*100:.0f}%)")
            adapter_spec = await best.adapter.generate(page, target_origin, str(output_dir))
            if adapter_spec:
                path_count = len(adapter_spec.get("paths", {}))
                click.echo(f"适配器生成: {path_count} 个端点")
                generate_swagger_html(
                    spec=adapter_spec,
                    output_path=str(output_dir / "api_docs.html"),
                    title=title,
                )
        else:
            click.echo("未匹配已知框架，使用通用模式")

        # Phase 1: 自动探索（除非 --manual）
        explore_result = {"js_endpoints": []}
        if not manual:
            click.echo()
            from apiscout.core.crawler.navigator import NavigatorConfig, explore_pages
            from apiscout.core.config import load_config
            cfg = load_config()
            nav_config = NavigatorConfig.from_config(cfg)
            click.echo(f">>> 自动探索（最多 {nav_config.max_pages} 页，深度 {nav_config.max_depth}）...")

            explore_result = await explore_pages(
                page=page,
                start_url=current_url,
                recorder=recorder,
                config=nav_config,
            )

            click.echo()
            click.echo(f"自动探索完成: {explore_result['pages_visited']} 页, {explore_result['requests_captured']} 请求")

        # Phase 2: 手动补录（实时显示捕获计数）
        click.echo()
        click.echo("=" * 50)
        click.echo("浏览器保持打开，你可以自由操作系统")
        click.echo("所有操作都在录制中")
        click.echo("完成后按 Enter 生成文档")
        click.echo("=" * 50)

        # 后台定时刷新捕获计数
        stop_counter = asyncio.Event()

        async def _show_counter():
            last = 0
            while not stop_counter.is_set():
                current = recorder.captured_count
                if current != last:
                    click.echo(f"\r  录制中... 已捕获 {current} 请求", nl=False)
                    last = current
                await asyncio.sleep(1)

        counter_task = asyncio.create_task(_show_counter())
        await asyncio.get_event_loop().run_in_executor(None, input)
        stop_counter.set()
        await counter_task
        click.echo()  # 换行
        click.echo(f"最终捕获: {recorder.captured_count} 请求")
        store.close()
        await browser.close()

    # Phase 3: 分析 + 生成
    click.echo()
    click.echo(">>> 分析 + 生成...")
    analysis = analyze_capture(
        str(capture_file),
        js_endpoints=explore_result.get("js_endpoints"),
    )
    stats = analysis["stats"]
    click.echo(f"端点: {stats['total_endpoints']} ({stats['confirmed']} 确认, {stats['uncertain']} 待确认)")
    click.echo(f"认证: {analysis['auth'].get('type', 'unknown')}")

    generate_outputs(analysis, str(output_dir), title=title, base_url=target_origin)

    # 如果适配器生成了更好的 spec，覆盖 api_docs
    if adapter_spec:
        generate_swagger_html(
            spec=adapter_spec,
            output_path=str(output_dir / "api_docs.html"),
            title=title,
        )

    click.echo()
    click.echo("=" * 50)
    click.echo("完成! 输出文件:")
    for f in sorted(output_dir.iterdir()):
        if not f.name.startswith('.'):
            size = f.stat().st_size
            click.echo(f"  {f.name} ({size//1024}KB)" if size > 1024 else f"  {f.name} ({size}B)")
    click.echo("=" * 50)

    # 自动打开文档
    docs_path = output_dir / "api_docs.html"
    if docs_path.exists():
        import webbrowser
        webbrowser.open(f"file://{docs_path.resolve()}")


@main.command()
@click.argument("capture_file")
@click.option("--output", "-o", default="./output", help="输出目录")
@click.option("--title", default="APIScout 发现的 API", help="API 文档标题")
def analyze(capture_file, output, title):
    """分析捕获数据，生成 OpenAPI spec + 文档

    \b
    示例：
      apiscout analyze capture.jsonl
      apiscout analyze output/capture.jsonl -o output/
    """
    from apiscout.core.workflow import analyze_capture, generate_outputs
    from apiscout.core.generator.swagger_ui import generate_swagger_html
    from pathlib import Path

    click.echo(f"分析: {capture_file}")
    result = analyze_capture(capture_file)
    stats = result["stats"]
    click.echo(f"  端点: {stats['total_endpoints']} ({stats['confirmed']} 确认, {stats['uncertain']} 待确认)")
    click.echo(f"  认证: {result['auth'].get('type', 'unknown')}")

    generate_outputs(result, output, title=title)

    # 生成 Swagger UI
    spec_path = Path(output) / "draft_spec.yaml"
    if spec_path.exists():
        generate_swagger_html(
            spec=str(spec_path),
            output_path=str(Path(output) / "api_docs.html"),
            title=title,
        )

    click.echo(f"  输出: {output}")


@main.command()
@click.argument("project_dir")
@click.option("--ai", default="deepseek", help="AI 提供商")
@click.option("--api-key", envvar="DEEPSEEK_API_KEY", help="API Key")
def enrich(project_dir, ai, api_key):
    """AI 增强：端点命名、字段语义

    \b
    示例：
      apiscout enrich output/ --api-key sk-xxx
    """
    from apiscout.core.generator.ai_enricher import enrich_endpoints, write_enriched_spec
    from pathlib import Path

    project_path = Path(project_dir)
    if not api_key:
        click.echo("未提供 API key（环境变量 DEEPSEEK_API_KEY 或 --api-key）")
        return

    click.echo(f"AI 增强: {project_dir} (提供商: {ai})")
    click.echo("  [待完善]")
