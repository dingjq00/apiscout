"""数据库 Schema 报告 — HTML 可视化"""
from pathlib import Path

from jinja2 import BaseLoader, Environment

from apiscout.core.db_scanner.models import SchemaReport


# 内联模板（不依赖外部文件，对 PyInstaller 打包友好）
_INLINE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Schema 报告 — {{ report.database }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #f8fafc; color: #333; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #1e40af; margin-bottom: 6px; }
        .subtitle { color: #64748b; font-size: 14px; margin-bottom: 24px; }
        h2 { color: #1e40af; font-size: 16px; margin-bottom: 12px; }
        /* 概览卡片 */
        .summary { display: flex; gap: 16px; margin-bottom: 28px; flex-wrap: wrap; }
        .stat-card { background: white; border-radius: 8px; padding: 16px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 130px; }
        .stat-card .number { font-size: 28px; font-weight: bold; color: #1e40af; }
        .stat-card .label { font-size: 13px; color: #718096; margin-top: 4px; }
        /* 表卡片 */
        .table-card { background: white; border-radius: 8px; padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .table-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
        .table-name { font-size: 17px; font-weight: bold; color: #1e40af; font-family: monospace; }
        .table-comment { font-size: 13px; color: #64748b; }
        .table-rowcount { font-size: 13px; color: #94a3b8; margin-left: auto; }
        /* 列表格 */
        table.col-table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
        table.col-table th { background: #1e40af; color: white; padding: 9px 12px; text-align: left; font-size: 13px; }
        table.col-table td { padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }
        table.col-table tr:nth-child(even) { background: #f8fafc; }
        table.col-table tr:hover { background: #eff6ff; }
        .pk-badge { background: #fef3c7; color: #92400e; border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: bold; }
        .nullable-yes { color: #94a3b8; }
        .nullable-no { color: #dc2626; font-weight: bold; }
        code { font-family: "Menlo", "Consolas", monospace; font-size: 12px; }
        /* 枚举值 */
        .enum-section { margin-top: 10px; margin-bottom: 16px; }
        .enum-section h4 { font-size: 13px; color: #64748b; margin-bottom: 6px; }
        .enum-tags { display: flex; flex-wrap: wrap; gap: 6px; }
        .enum-tag { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; border-radius: 4px; padding: 2px 8px; font-size: 12px; font-family: monospace; }
        .enum-tag .count { color: #94a3b8; font-size: 11px; margin-left: 4px; }
        /* 采样数据 */
        .sample-section { margin-top: 10px; }
        .sample-section h4 { font-size: 13px; color: #64748b; margin-bottom: 6px; }
        table.sample-table { width: 100%; border-collapse: collapse; font-size: 12px; }
        table.sample-table th { background: #e0f2fe; color: #0c4a6e; padding: 6px 10px; text-align: left; }
        table.sample-table td { padding: 5px 10px; border-bottom: 1px solid #f0f9ff; }
        table.sample-table tr:hover { background: #f0f9ff; }
        /* 关系区域 */
        .relations-section { background: white; border-radius: 8px; padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .rel-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }
        .rel-item:last-child { border-bottom: none; }
        .rel-src { font-family: monospace; color: #1e40af; }
        .rel-arrow { color: #94a3b8; font-weight: bold; }
        .rel-tgt { font-family: monospace; color: #065f46; }
        .rel-constraint { color: #94a3b8; font-size: 11px; }
        .rel-confidence { background: #fef3c7; color: #92400e; border-radius: 4px; padding: 1px 6px; font-size: 11px; }
        .rel-evidence { color: #64748b; font-size: 12px; }
        .rel-inferred { border-left: 3px dashed #fbbf24; padding-left: 10px; margin-left: 4px; }
        .section-title { font-size: 15px; font-weight: bold; color: #374151; margin-bottom: 12px; }
        .no-data { color: #94a3b8; font-size: 13px; font-style: italic; }
    </style>
</head>
<body>
<div class="container">
    <h1>数据库 Schema 报告 — {{ report.database }}</h1>
    <div class="subtitle">
        方言: <strong>{{ report.dialect }}</strong> &nbsp;|&nbsp;
        扫描时间: <strong>{{ report.scanned_at }}</strong>
    </div>

    <!-- 概览卡片 -->
    <div class="summary">
        <div class="stat-card">
            <div class="number">{{ report.total_tables }}</div>
            <div class="label">表总数</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ report.total_columns }}</div>
            <div class="label">字段总数</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ report.total_foreign_keys }}</div>
            <div class="label">外键数</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ report.total_inferred_relations }}</div>
            <div class="label">推断关系数</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ report.enum_candidates | length }}</div>
            <div class="label">枚举候选数</div>
        </div>
    </div>

    <!-- 逐表详情 -->
    {% for table in report.tables %}
    <div class="table-card">
        <div class="table-header">
            <span class="table-name">{{ table.name }}</span>
            {% if table.comment %}
            <span class="table-comment">{{ table.comment }}</span>
            {% endif %}
            {% if table.row_count is not none %}
            <span class="table-rowcount">≈ {{ table.row_count }} 行</span>
            {% endif %}
        </div>

        <!-- 列详情 -->
        <table class="col-table">
            <thead>
                <tr>
                    <th>字段名</th>
                    <th>类型（原始）</th>
                    <th>归一化类型</th>
                    <th>可空</th>
                    <th>默认值</th>
                    <th>注释</th>
                </tr>
            </thead>
            <tbody>
            {% for col in table.columns %}
                <tr>
                    <td>
                        <code>{{ col.name }}</code>
                        {% if col.is_primary_key %}<span class="pk-badge">PK</span>{% endif %}
                    </td>
                    <td><code>{{ col.data_type }}</code></td>
                    <td><code>{{ col.normalized_type }}</code></td>
                    <td class="{{ 'nullable-yes' if col.nullable else 'nullable-no' }}">
                        {{ "是" if col.nullable else "否" }}
                    </td>
                    <td>{{ col.default if col.default is not none else "—" }}</td>
                    <td>{{ col.comment if col.comment else "—" }}</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>

        <!-- 枚举候选值 -->
        {% set enum_cols = table.columns | selectattr("is_enum_candidate") | list %}
        {% if enum_cols %}
        <div class="enum-section">
            <h4>枚举候选值</h4>
            {% for col in enum_cols %}
            <div style="margin-bottom:8px;">
                <code style="color:#1e40af;">{{ col.name }}</code> ：
                <span class="enum-tags" style="display:inline-flex;">
                {% for ev in col.enum_values %}
                    <span class="enum-tag">{{ ev.value }}<span class="count">{{ ev.count }}</span></span>
                {% endfor %}
                </span>
            </div>
            {% endfor %}
        </div>
        {% endif %}

        <!-- 采样数据 -->
        {% if table.sample_rows %}
        <div class="sample-section">
            <h4>采样数据（前 {{ table.sample_rows | length }} 行）</h4>
            {% set headers = table.sample_rows[0].keys() | list %}
            <table class="sample-table">
                <thead>
                    <tr>{% for h in headers %}<th>{{ h }}</th>{% endfor %}</tr>
                </thead>
                <tbody>
                {% for row in table.sample_rows %}
                    <tr>{% for h in headers %}<td>{{ row[h] if row[h] is not none else "NULL" }}</td>{% endfor %}</tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
    </div>
    {% endfor %}

    <!-- 关系图 -->
    <div class="relations-section">
        <div class="section-title">表间关系</div>

        {% if report.explicit_relations %}
        <h2>显式外键</h2>
        {% for rel in report.explicit_relations %}
        <div class="rel-item">
            <span class="rel-src">{{ rel.source_table }}.{{ rel.source_column }}</span>
            <span class="rel-arrow">→</span>
            <span class="rel-tgt">{{ rel.target_table }}.{{ rel.target_column }}</span>
            <span class="rel-constraint">（约束: {{ rel.constraint_name }}）</span>
        </div>
        {% endfor %}
        {% else %}
        <p class="no-data">无显式外键</p>
        {% endif %}

        {% if report.inferred_relations %}
        <h2 style="margin-top:16px;">推断关系</h2>
        {% for rel in report.inferred_relations %}
        <div class="rel-item rel-inferred">
            <span class="rel-src">{{ rel.source_table }}.{{ rel.source_column }}</span>
            <span class="rel-arrow">→</span>
            <span class="rel-tgt">{{ rel.target_table }}.{{ rel.target_column }}</span>
            <span class="rel-confidence">{{ (rel.confidence * 100) | int }}%</span>
            <span class="rel-evidence">{{ rel.evidence }}</span>
        </div>
        {% endfor %}
        {% else %}
        <p class="no-data" style="margin-top:16px;">无推断关系</p>
        {% endif %}
    </div>
</div>
</body>
</html>"""


def generate_schema_report_html(report: SchemaReport) -> str:
    """从 SchemaReport 渲染 HTML 字符串"""
    env = Environment(loader=BaseLoader())
    template = env.from_string(_INLINE_TEMPLATE)
    return template.render(report=report)


def write_schema_report_html(report: SchemaReport, output_path: str) -> None:
    """生成并写入 Schema HTML 报告文件"""
    html = generate_schema_report_html(report)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
