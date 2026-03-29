"""APIScout CLI 入口"""
import click
from apiscout import __version__


@click.group()
@click.version_option(__version__, prog_name="apiscout")
def main():
    """APIScout — 自动化 API 发现与文档生成工具"""
    pass


@main.command()
@click.option("--url", required=True, help="目标系统 URL")
@click.option("--output", "-o", default="./output", help="输出目录")
@click.option("--config", "-c", default=None, help="自定义配置文件")
@click.option("--max-pages", default=None, type=int, help="最大页面数")
@click.option("--max-depth", default=None, type=int, help="最大爬取深度")
def scan(url, output, config, max_pages, max_depth):
    """完整扫描：自动探索 → 手动补录 → 生成输出"""
    click.echo(f"🔍 APIScout v{__version__}")
    click.echo(f"   目标: {url}")
    click.echo(f"   输出: {output}")
    click.echo("   [待实现 — Task 17 完成后接入 workflow]")


@main.command()
@click.option("--url", required=True, help="目标系统 URL")
@click.option("--output", "-o", default="capture.jsonl", help="捕获输出文件")
@click.option("--append", is_flag=True, help="追加模式（多角色扫描）")
@click.option("--resume", is_flag=True, help="从上次中断继续")
def explore(url, output, append, resume):
    """仅执行探索阶段，输出捕获数据"""
    click.echo(f"🔍 探索: {url} → {output}")
    click.echo("   [待实现 — Task 17]")


@main.command()
@click.argument("capture_file")
@click.option("--output", "-o", default="./output", help="输出目录")
@click.option("--title", default="APIScout 发现的 API", help="API 文档标题")
def analyze(capture_file, output, title):
    """分析捕获数据，生成草稿 spec"""
    from apiscout.core.workflow import analyze_capture, generate_outputs

    click.echo(f"分析: {capture_file}")

    result = analyze_capture(capture_file)
    stats = result["stats"]
    click.echo(f"   发现 {stats['total_endpoints']} 个端点 ({stats['confirmed']} 确认, {stats['uncertain']} 待确认)")
    click.echo(f"   认证类型: {result['auth'].get('type', 'unknown')}")

    generate_outputs(result, output, title=title)
    click.echo(f"   输出目录: {output}")


@main.command()
@click.argument("draft_file")
@click.option("--output", "-o", default="./output", help="输出目录")
def generate(draft_file, output):
    """从审核后的草稿生成最终输出"""
    click.echo(f"📝 生成: {draft_file} → {output}")
    click.echo("   [待实现 — Task 17]")


@main.command()
@click.argument("project_dir")
@click.option("--ai", default="deepseek", help="AI 提供商")
@click.option("--api-key", envvar="DEEPSEEK_API_KEY", help="API Key")
def enrich(project_dir, ai, api_key):
    """AI 增强：端点命名、字段语义、MCP Tool 生成"""
    from apiscout.core.generator.ai_enricher import enrich_endpoints, write_enriched_spec
    from pathlib import Path

    project_path = Path(project_dir)
    draft_path = project_path / "draft_spec.yaml"

    if not draft_path.exists():
        click.echo(f"错误: 未找到 {draft_path}")
        return

    click.echo(f"AI 增强: {project_dir} (提供商: {ai})")

    if not api_key:
        click.echo("   未提供 API key（环境变量 DEEPSEEK_API_KEY 或 --api-key），跳过增强")
        click.echo("   提示: apiscout enrich <project_dir> --api-key <key>")
        return

    # 读取 meta.json 获取端点信息
    meta_path = project_path / "meta.json"
    if not meta_path.exists():
        click.echo(f"   未找到 meta.json，无法读取端点数据")
        click.echo("   请先运行: apiscout analyze capture.jsonl -o <project_dir>")
        return

    import json
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    endpoints = meta.get("endpoints", [])
    if not endpoints:
        click.echo("   meta.json 中无端点数据")
        return

    click.echo(f"   端点数量: {len(endpoints)}")
    enriched = enrich_endpoints(endpoints, api_key=api_key, provider=ai)

    title = meta.get("title", "APIScout 增强后 API")
    base_url = meta.get("base_url", "")
    write_enriched_spec(enriched, project_dir, title=title, base_url=base_url)
    click.echo(f"   输出: {project_path / 'enriched_spec.yaml'}")
