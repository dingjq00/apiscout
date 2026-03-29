"""APIScout 集成测试 — 纯黑盒模式

使用方式：
    python scripts/integration_test.py http://localhost:8080

只需要一个 URL，其他全靠 APIScout 自己发现。
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from apiscout.core.capture.store import CaptureStore
from apiscout.core.capture.filter import RequestFilter
from apiscout.core.capture.recorder import PageRecorder
from apiscout.core.crawler.navigator import NavigatorConfig, explore_pages
from apiscout.core.workflow import analyze_capture, generate_outputs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("apiscout")


async def main():
    from playwright.async_api import async_playwright
    from urllib.parse import urlparse

    # 唯一输入：一个 URL
    if len(sys.argv) < 2:
        print("用法: python scripts/integration_test.py <URL>")
        print("示例: python scripts/integration_test.py http://localhost:8080")
        sys.exit(1)

    target_url = sys.argv[1]
    parsed = urlparse(target_url)
    target_origin = f"{parsed.scheme}://{parsed.netloc}"
    project_name = parsed.netloc.replace(":", "_")

    output_dir = Path(__file__).parent.parent / "test_output" / project_name
    capture_file = output_dir / "capture.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("APIScout — 给我一个 URL，还你一份 OpenAPI spec")
    logger.info("=" * 60)
    logger.info("目标: %s", target_url)
    logger.info("输出: %s", output_dir)

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

        # 初始化捕获 — 只知道 origin，其他用默认配置
        store = CaptureStore(capture_file)
        request_filter = RequestFilter(target_origin=target_origin)
        recorder = PageRecorder(store, request_filter)
        await recorder.attach(page)

        # Phase 1a: 用户手动登录
        logger.info("")
        logger.info(">>> 打开目标系统...")
        await page.goto(target_url, wait_until="networkidle", timeout=30000)

        logger.info("")
        logger.info("=" * 60)
        logger.info("请在浏览器中登录系统")
        logger.info("登录完成后，回到终端按 Enter 开始自动探索")
        logger.info("=" * 60)
        await asyncio.get_event_loop().run_in_executor(None, input)

        current_url = page.url
        logger.info("当前 URL: %s", current_url)
        logger.info("登录过程已捕获 %d 个请求", recorder.captured_count)

        # Phase 0: API 文档端点探测（登录后带 session 探测）
        logger.info("")
        logger.info(">>> 探测已知 API 文档端点...")
        from apiscout.core.crawler.api_prober import probe_api_endpoints, summarize_probe_results
        probe_results = await probe_api_endpoints(page, target_origin)
        probe_summary = summarize_probe_results(probe_results)

        if probe_summary["openapi_spec"]:
            logger.info("发现现成 OpenAPI spec！直接使用，跳过抓包推断。")
            # 直接保存 spec，不需要抓包
            import yaml
            spec_path = output_dir / "discovered_spec.yaml"
            with open(spec_path, "w", encoding="utf-8") as f:
                yaml.dump(probe_summary["openapi_spec"], f,
                         default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info("已保存: %s", spec_path)
        else:
            if probe_summary["available_endpoints"]:
                logger.info("发现 %d 个可用端点（无完整 spec）:", len(probe_summary["available_endpoints"]))
                for ep in probe_summary["available_endpoints"]:
                    logger.info("   %s — %s", ep["path"], ep["desc"])
            if probe_summary["auth_required"]:
                logger.info("发现 %d 个需要认证的端点:", len(probe_summary["auth_required"]))
                for ep in probe_summary["auth_required"]:
                    logger.info("   🔒 %s — %s", ep["path"], ep["desc"])
            if probe_summary["framework_hints"]:
                logger.info("检测到框架: %s", ", ".join(probe_summary["framework_hints"]))

        # Phase 1b: 自动探索
        logger.info("")
        logger.info(">>> 开始自动探索（最多 30 页，深度 3）...")

        nav_config = NavigatorConfig(
            max_depth=3,
            max_pages=30,
            page_timeout=15,
            network_idle_wait=3,
            request_delay=1.0,
        )

        def on_progress(progress):
            logger.info(
                "页面: %d/%d  请求: %d  当前: %s",
                progress.pages_visited,
                progress.pages_total,
                progress.requests_captured,
                progress.current_url[-80:] if progress.current_url else "",
            )

        explore_result = await explore_pages(
            page=page,
            start_url=current_url,
            recorder=recorder,
            config=nav_config,
            progress_callback=on_progress,
        )

        logger.info("")
        logger.info(">>> Phase 1 完成")
        logger.info("   页面: %d 访问 / %d 发现", explore_result["pages_visited"], explore_result["total_discovered"])
        logger.info("   请求: %d 捕获", explore_result["requests_captured"])
        logger.info("   JS 端点: %d 发现", len(explore_result.get("js_endpoints", [])))

        # Phase 2: 手动补录
        logger.info("")
        logger.info("=" * 60)
        logger.info("浏览器保持打开，可以手动操作补录")
        logger.info("完成后按 Enter 生成输出（当前: %d 请求）", recorder.captured_count)
        logger.info("=" * 60)
        await asyncio.get_event_loop().run_in_executor(None, input)

        final_count = recorder.captured_count
        logger.info("最终捕获: %d 请求", final_count)

        store.close()
        await browser.close()

    # Phase 3: 分析 + 生成
    logger.info("")
    logger.info(">>> 分析中...")
    analysis = analyze_capture(
        str(capture_file),
        js_endpoints=explore_result.get("js_endpoints"),
    )

    stats = analysis["stats"]
    logger.info("   记录: %d", stats["total_records"])
    logger.info("   端点: %d (%d 确认, %d 待确认)", stats["total_endpoints"], stats["confirmed"], stats["uncertain"])
    logger.info("   认证: %s", analysis["auth"].get("type", "unknown"))

    if analysis.get("login_info"):
        logger.info("   登录端点: %s", analysis["login_info"].get("endpoint", "未检测到"))
        logger.info("   Token 位置: %s", analysis["login_info"].get("token_location", "未检测到"))

    logger.info("")
    logger.info(">>> 生成输出...")
    generate_outputs(analysis, str(output_dir), title=f"{parsed.netloc} API", base_url=target_origin)

    logger.info("")
    logger.info("=" * 60)
    logger.info("完成! 输出:")
    for f in sorted(output_dir.iterdir()):
        size = f.stat().st_size
        unit = "B" if size < 1024 else "KB"
        val = size if size < 1024 else size // 1024
        logger.info("   %s (%d%s)", f.name, val, unit)
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
