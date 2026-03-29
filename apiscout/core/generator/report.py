"""HTML 覆盖率报告生成"""
from collections import Counter
from pathlib import Path

from jinja2 import BaseLoader, Environment


# 内联模板（不依赖外部文件，对 PyInstaller 打包友好）
_INLINE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #f5f7fa; color: #333; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #1a365d; margin-bottom: 20px; }
        .summary { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
        .stat-card { background: white; border-radius: 8px; padding: 16px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 150px; }
        .stat-card .number { font-size: 28px; font-weight: bold; color: #2b6cb0; }
        .stat-card .label { font-size: 13px; color: #718096; margin-top: 4px; }
        table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        th { background: #2b6cb0; color: white; padding: 12px 16px; text-align: left; font-size: 13px; }
        td { padding: 10px 16px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }
        tr:nth-child(even) { background: #f7fafc; }
        tr:hover { background: #edf2f7; }
        .method { font-weight: bold; font-family: monospace; }
        .method-get { color: #2b6cb0; }
        .method-post { color: #2f855a; }
        .method-put { color: #b7791f; }
        .method-delete { color: #c53030; }
        .status-confirmed { color: #2f855a; }
        .status-uncertain { color: #b7791f; }
        .status-excluded { color: #a0aec0; }
        .phase2-hint { background: #fffbeb; border: 1px solid #f6e05e; border-radius: 8px; padding: 16px; margin-top: 24px; }
        .phase2-hint h3 { color: #b7791f; margin-bottom: 8px; }
        .phase2-hint ul { padding-left: 20px; margin-top: 8px; }
        .phase2-hint li { margin-top: 4px; }
    </style>
</head>
<body>
<div class="container">
    <h1>{{ title }}</h1>

    <div class="summary">
        <div class="stat-card">
            <div class="number">{{ total_endpoints }}</div>
            <div class="label">端点总数</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ confirmed_count }}</div>
            <div class="label">已确认</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ uncertain_count }}</div>
            <div class="label">待确认</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ methods.GET | default(0) }} / {{ methods.POST | default(0) }} / {{ methods.PUT | default(0) }} / {{ methods.DELETE | default(0) }}</div>
            <div class="label">GET / POST / PUT / DELETE</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>方法</th>
                <th>路径</th>
                <th>观察次数</th>
                <th>状态码</th>
                <th>状态</th>
            </tr>
        </thead>
        <tbody>
        {% for ep in endpoints %}
            <tr>
                <td class="method method-{{ ep.method | lower }}">{{ ep.method }}</td>
                <td><code>{{ ep.path }}</code></td>
                <td>{{ ep.observation_count }}</td>
                <td>{{ ep.status_codes | join(', ') }}</td>
                <td class="status-{{ ep.status }}">{{ ep.status }}</td>
            </tr>
        {% endfor %}
        </tbody>
    </table>

    {% if uncertain_endpoints %}
    <div class="phase2-hint">
        <h3>Phase 2 补录建议</h3>
        <p>以下端点仅从 JS 源码中发现，未被实际触发。建议在 Phase 2 手动操作相关功能：</p>
        <ul>
        {% for ep in uncertain_endpoints %}
            <li><code>{{ ep.path }}</code></li>
        {% endfor %}
        </ul>
    </div>
    {% endif %}
</div>
</body>
</html>"""


def generate_report(
    endpoints: list[dict],
    title: str = "APIScout 报告",
    auth_summary: dict | None = None,
) -> str:
    """生成 HTML 报告字符串"""
    # 统计各维度数据
    methods = Counter(ep["method"] for ep in endpoints)
    confirmed = [ep for ep in endpoints if ep.get("status") == "confirmed"]
    uncertain = [ep for ep in endpoints if ep.get("status") == "uncertain"]

    # 排序：confirmed 在前，uncertain 在后，同状态内按路径+方法排序
    sorted_endpoints = sorted(
        endpoints,
        key=lambda e: (e.get("status", "") != "confirmed", e["path"], e["method"]),
    )

    env = Environment(loader=BaseLoader())
    template = env.from_string(_INLINE_TEMPLATE)
    return template.render(
        title=title,
        endpoints=sorted_endpoints,
        total_endpoints=len(endpoints),
        confirmed_count=len(confirmed),
        uncertain_count=len(uncertain),
        methods=dict(methods),
        uncertain_endpoints=uncertain,
        auth_summary=auth_summary,
    )


def write_report(
    endpoints: list[dict],
    output_path: str,
    title: str = "APIScout 报告",
    auth_summary: dict | None = None,
):
    """生成并写入 HTML 报告文件"""
    html = generate_report(endpoints, title=title, auth_summary=auth_summary)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
