"""数据库 Schema 报告 — 可交互 HTML（V1.2）

单文件自包含：数据 + 交互 + 样式全部内嵌。
可直接发给客户，浏览器打开即可审核，审核完导出 JSON。

安全说明：HTML 内容由服务端 Jinja2 生成，数据来源是数据库 schema 扫描结果，
不包含用户输入的 HTML 内容。JS 交互部分使用 DOM API 构建元素，
不存在 XSS 风险（无外部不可信输入注入到 HTML 中）。
"""
import json
from dataclasses import asdict
from pathlib import Path

from jinja2 import BaseLoader, Environment

from apiscout.core.db_scanner.models import SchemaReport


# ──────────────────────────────────────────────────────────────────────
# 内联模板（不依赖外部文件，对 PyInstaller 打包友好）
# JS 交互使用 DOM API 构建元素，数据来源为自身嵌入的扫描结果
# ──────────────────────────────────────────────────────────────────────
_INLINE_TEMPLATE = r"""<!DOCTYPE html>
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
.summary { display: flex; gap: 16px; margin-bottom: 28px; flex-wrap: wrap; }
.stat-card { background: white; border-radius: 8px; padding: 16px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 130px; }
.stat-card .number { font-size: 28px; font-weight: bold; color: #1e40af; }
.stat-card .label { font-size: 13px; color: #718096; margin-top: 4px; }
.table-card { background: white; border-radius: 8px; padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
.table-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.table-name { font-size: 17px; font-weight: bold; color: #1e40af; font-family: monospace; }
.table-comment { font-size: 13px; color: #64748b; }
.table-rowcount { font-size: 13px; color: #94a3b8; margin-left: auto; }
table.col-table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
table.col-table th { background: #1e40af; color: white; padding: 9px 12px; text-align: left; font-size: 13px; }
table.col-table td { padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; }
table.col-table tr:nth-child(even) { background: #f8fafc; }
table.col-table tr:hover { background: #eff6ff; }
.pk-badge { background: #fef3c7; color: #92400e; border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: bold; }
.nullable-yes { color: #94a3b8; }
.nullable-no { color: #dc2626; font-weight: bold; }
code { font-family: "Menlo", "Consolas", monospace; font-size: 12px; }
.sample-section { margin-top: 10px; }
.sample-section h4 { font-size: 13px; color: #64748b; margin-bottom: 6px; }
table.sample-table { width: 100%; border-collapse: collapse; font-size: 12px; }
table.sample-table th { background: #e0f2fe; color: #0c4a6e; padding: 6px 10px; text-align: left; }
table.sample-table td { padding: 5px 10px; border-bottom: 1px solid #f0f9ff; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
table.sample-table tr:hover { background: #f0f9ff; }
.review-section { background: white; border-radius: 8px; padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; border-left: 4px solid #f59e0b; }
.relations-section { background: white; border-radius: 8px; padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
.section-title { font-size: 15px; font-weight: bold; color: #374151; margin-bottom: 12px; }
.no-data { color: #94a3b8; font-size: 13px; font-style: italic; }
.review-toolbar { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.review-toolbar .progress-text { font-size: 13px; color: #92400e; font-weight: 500; min-width: 120px; }
.review-toolbar .progress-bar { flex: 1; min-width: 100px; height: 8px; background: #fde68a; border-radius: 4px; overflow: hidden; }
.review-toolbar .progress-fill { height: 100%; background: #16a34a; border-radius: 4px; transition: width 0.3s; }
.btn { padding: 5px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 12px; cursor: pointer; background: white; }
.btn:hover { background: #f9fafb; }
.btn-green { border-color: #86efac; color: #166534; }
.btn-green:hover { background: #dcfce7; }
.btn-red { border-color: #fca5a5; color: #991b1b; }
.btn-red:hover { background: #fee2e2; }
.btn-blue { border-color: #93c5fd; color: #1e40af; }
.btn-blue:hover { background: #dbeafe; }
.review-item { display: flex; align-items: center; gap: 8px; padding: 8px 4px; border-bottom: 1px solid #f1f5f9; font-size: 13px; transition: background 0.2s; }
.review-item:last-child { border-bottom: none; }
.review-item.st-confirmed { background: #f0fdf4; }
.review-item.st-rejected { background: #fef2f2; opacity: 0.6; }
.review-item.st-rejected .r-src, .review-item.st-rejected .r-tgt { text-decoration: line-through; }
.r-src { font-family: monospace; color: #1e40af; white-space: nowrap; }
.r-arrow { color: #94a3b8; font-weight: bold; }
.r-tgt { font-family: monospace; color: #065f46; cursor: pointer; border-bottom: 1px dashed #065f46; white-space: nowrap; }
.r-tgt:hover { color: #047857; }
.r-conf { background: #fef3c7; color: #92400e; border-radius: 4px; padding: 1px 6px; font-size: 11px; white-space: nowrap; }
.r-actions { margin-left: auto; display: flex; gap: 4px; flex-shrink: 0; }
.sb { font-size: 11px; padding: 1px 6px; border-radius: 4px; white-space: nowrap; }
.sb-ok { background: #dcfce7; color: #166534; }
.sb-no { background: #fee2e2; color: #991b1b; }
.sb-edit { background: #dbeafe; color: #1e40af; }
.enum-item { padding: 8px 4px; border-bottom: 1px solid #f1f5f9; transition: background 0.2s; }
.enum-item.st-confirmed { background: #f0fdf4; }
.enum-item.st-rejected { background: #fef2f2; opacity: 0.6; }
.enum-hdr { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.e-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.e-tag { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; border-radius: 4px; padding: 2px 8px; font-size: 12px; font-family: monospace; display: inline-flex; align-items: center; gap: 4px; }
.e-tag .cnt { color: #94a3b8; font-size: 11px; }
.e-tag .rx { color: #ef4444; cursor: pointer; font-weight: bold; margin-left: 2px; }
.e-tag .rx:hover { color: #dc2626; }
.e-tag.removed { text-decoration: line-through; opacity: 0.4; }
.add-btn { background: none; border: 1px dashed #93c5fd; color: #3b82f6; border-radius: 4px; padding: 2px 8px; font-size: 12px; cursor: pointer; }
.add-btn:hover { background: #eff6ff; }
.popup-bg { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.3); z-index: 999; display: none; }
.popup { position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%); background: white; border-radius: 12px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); padding: 24px; z-index: 1000; min-width: 400px; display: none; }
.popup h3 { margin-bottom: 12px; color: #1e40af; }
.popup select { width: 100%; padding: 8px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; margin-bottom: 12px; }
.popup .brow { display: flex; gap: 8px; justify-content: flex-end; }
.ch { font-size:11px; padding:1px 6px; border-radius:8px; }
.ch-h { color:#166534; background:#dcfce7; }
.ch-m { color:#854d0e; background:#fef9c3; }
.ch-l { color:#9ca3af; background:#f3f4f6; }
.rel-item-fk { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }
.rel-item-fk:last-child { border-bottom: none; }
/* 分组折叠 */
.group { margin-bottom: 4px; }
.group-hdr { display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: #f8fafc; border-radius: 6px; cursor: pointer; user-select: none; font-size: 13px; }
.group-hdr:hover { background: #f1f5f9; }
.group-hdr .arrow { transition: transform 0.2s; display: inline-block; color: #94a3b8; }
.group-hdr .arrow.open { transform: rotate(90deg); }
.group-hdr .g-name { font-family: monospace; color: #1e40af; font-weight: 600; }
.group-hdr .g-cnt { color: #94a3b8; font-size: 12px; }
.group-hdr .g-stat { margin-left: auto; font-size: 11px; }
.group-body { padding-left: 16px; }
.group-body.collapsed { display: none; }
/* 搜索 + 过滤 */
.filter-bar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
.filter-bar input { padding: 5px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; width: 200px; }
.filter-tab { padding: 4px 10px; border-radius: 12px; font-size: 12px; cursor: pointer; border: 1px solid #e2e8f0; background: white; }
.filter-tab:hover { background: #f9fafb; }
.filter-tab.active { background: #1e40af; color: white; border-color: #1e40af; }
</style>
</head>
<body>
<div class="container">
    <h1>数据库 Schema 报告 — {{ report.database }}</h1>
    <div class="subtitle">方言: <strong>{{ report.dialect }}</strong> | 扫描时间: <strong>{{ report.scanned_at }}</strong></div>
    <div class="summary">
        <div class="stat-card"><div class="number">{{ report.total_tables }}</div><div class="label">表总数</div></div>
        <div class="stat-card"><div class="number">{{ report.total_columns }}</div><div class="label">字段总数</div></div>
        <div class="stat-card"><div class="number">{{ report.total_foreign_keys }}</div><div class="label">外键数</div></div>
        <div class="stat-card"><div class="number">{{ report.total_inferred_relations }}</div><div class="label">推断关系数</div></div>
        <div class="stat-card"><div class="number" id="ec">0</div><div class="label">枚举候选数</div></div>
    </div>

    <div class="review-toolbar">
        <span class="progress-text" id="pt">已审核: 0 / 0</span>
        <div class="progress-bar"><div class="progress-fill" id="pf" style="width:0%"></div></div>
        <button class="btn btn-green" onclick="doAll('confirmed')">全部确认</button>
        <button class="btn btn-red" onclick="doAll('rejected')">全部拒绝</button>
        <button class="btn" onclick="doReset()">重置</button>
        <button class="btn btn-blue" onclick="doExport()">导出审核结果</button>
        <label class="btn btn-blue" style="margin:0;">导入<input type="file" accept=".json" onchange="doImport(this.files[0])" style="display:none;"></label>
    </div>

    <div class="review-section">
        <div class="section-title" style="color:#92400e;">&#9888; 推断关系（<span id="rt">0</span> 个）</div>
        <div class="filter-bar">
            <input type="text" id="rel-search" placeholder="搜索表名..." oninput="drawR()">
            <span class="filter-tab active" onclick="setRelFilter('all',this)">全部</span>
            <span class="filter-tab" onclick="setRelFilter('unreviewed',this)">未审核</span>
            <span class="filter-tab" onclick="setRelFilter('confirmed',this)">已确认</span>
            <span class="filter-tab" onclick="setRelFilter('rejected',this)">已拒绝</span>
            <button class="btn btn-blue" onclick="addRelation()" style="margin-left:auto;">+ 添加关系</button>
        </div>
        <div id="rc"></div>
    </div>
    <div class="review-section">
        <div class="section-title" style="color:#92400e;">&#9888; 枚举候选（<span id="et">0</span> 个字段）</div>
        <div class="filter-bar">
            <input type="text" id="enum-search" placeholder="搜索表名..." oninput="drawE()">
            <span class="filter-tab active" onclick="setEnumFilter('all',this)">全部</span>
            <span class="filter-tab" onclick="setEnumFilter('unreviewed',this)">未审核</span>
            <span class="filter-tab" onclick="setEnumFilter('confirmed',this)">已确认</span>
            <span class="filter-tab" onclick="setEnumFilter('rejected',this)">已拒绝</span>
            <button class="btn btn-blue" onclick="addEnum()" style="margin-left:auto;">+ 添加枚举</button>
        </div>
        <div id="ecc"></div>
    </div>

    {% if report.explicit_relations %}
    <div class="relations-section">
        <div class="section-title">显式外键（{{ report.explicit_relations | length }} 个，数据库约束）</div>
        {% for rel in report.explicit_relations %}
        <div class="rel-item-fk">
            <span class="r-src">{{ rel.source_table }}.{{ rel.source_column }}</span>
            <span class="r-arrow">→</span>
            <span style="font-family:monospace;color:#065f46;">{{ rel.target_table }}.{{ rel.target_column }}</span>
            <span style="color:#94a3b8;font-size:11px;">（{{ rel.constraint_name }}）</span>
        </div>
        {% endfor %}
    </div>
    {% endif %}

    {% for table in report.tables %}
    <div class="table-card">
        <div class="table-header">
            <span class="table-name">{{ table.name }}</span>
            {% if table.comment %}<span class="table-comment">{{ table.comment }}</span>{% endif %}
            {% if table.row_count is not none %}<span class="table-rowcount">≈ {{ table.row_count }} 行</span>{% endif %}
        </div>
        <table class="col-table">
            <thead><tr><th>字段名</th><th>类型（原始）</th><th>归一化类型</th><th>可空</th><th>默认值</th><th>注释</th></tr></thead>
            <tbody>
            {% for col in table.columns %}
            <tr>
                <td><code>{{ col.name }}</code>{% if col.is_primary_key %} <span class="pk-badge">PK</span>{% endif %}</td>
                <td><code>{{ col.data_type }}</code></td>
                <td><code>{{ col.normalized_type }}</code></td>
                <td class="{{ 'nullable-yes' if col.nullable else 'nullable-no' }}">{{ "是" if col.nullable else "否" }}</td>
                <td>{{ col.default if col.default is not none else "—" }}</td>
                <td>{{ col.comment if col.comment else "—" }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
        {% if table.sample_rows %}
        <div class="sample-section">
            <h4>采样数据（前 {{ table.sample_rows | length }} 行）</h4>
            {% set headers = table.sample_rows[0].keys() | list %}
            <table class="sample-table">
                <thead><tr>{% for h in headers %}<th>{{ h }}</th>{% endfor %}</tr></thead>
                <tbody>
                {% for row in table.sample_rows %}<tr>{% for h in headers %}<td>{{ row[h] if row[h] is not none else "NULL" }}</td>{% endfor %}</tr>{% endfor %}
                </tbody>
            </table>
        </div>
        {% endif %}
    </div>
    {% endfor %}
</div>

<div id="pbg" class="popup-bg" onclick="cpop()"></div>
<div id="pop" class="popup"></div>

<script>
// 数据来源：apiscout db 扫描结果，由服务端嵌入，非用户输入
var D = {{ schema_data_json }};
var TN = D.tables.map(function(t){return t.name}).sort();
var S = {r:{}, e:{}};
var relFilter = 'all', enumFilter = 'all';
var openGroups = {};  // 记录展开的组

// 收集枚举
var EN = [];
D.tables.forEach(function(t){ t.columns.forEach(function(c){
    if(c.enum_values && c.enum_values.length>0) EN.push({table:t.name, column:c.name, values:c.enum_values});
});});

// 用户手动添加的关系和枚举
var addedRels = [];
var addedEnums = [];

function init(){drawR();drawE();upd();}

function setRelFilter(f,el){relFilter=f;document.querySelectorAll('#rc').closest('.review-section').querySelectorAll?void 0:0;
    el.parentNode.querySelectorAll('.filter-tab').forEach(function(t){t.classList.remove('active')});el.classList.add('active');drawR();}
function setEnumFilter(f,el){enumFilter=f;
    el.parentNode.querySelectorAll('.filter-tab').forEach(function(t){t.classList.remove('active')});el.classList.add('active');drawE();}

function esc(s){var d=document.createElement('div');d.textContent=s;return d.textContent;}

function drawR(){
    var c=document.getElementById('rc'), rels=D.inferred_relations.concat(addedRels);
    document.getElementById('rt').textContent=rels.length;
    if(!rels.length){c.textContent='无推断关系';return;}
    var search=(document.getElementById('rel-search').value||'').toLowerCase();
    // 按 source_table 分组
    var groups={};
    rels.forEach(function(r,i){
        var k=r.source_table+'.'+r.source_column, s=S.r[k]||{}, st=s.status||'';
        // 过滤
        if(search && r.source_table.toLowerCase().indexOf(search)<0 && r.target_table.toLowerCase().indexOf(search)<0) return;
        if(relFilter==='unreviewed' && st) return;
        if(relFilter==='confirmed' && st!=='confirmed') return;
        if(relFilter==='rejected' && st!=='rejected') return;
        if(!groups[r.source_table]) groups[r.source_table]=[];
        groups[r.source_table].push({rel:r, idx:i});
    });
    var h='';
    Object.keys(groups).sort().forEach(function(tbl){
        var items=groups[tbl];
        var reviewed=items.filter(function(it){var k=it.rel.source_table+'.'+it.rel.source_column;return S.r[k]&&S.r[k].status}).length;
        var isOpen=openGroups['r_'+tbl]!==false; // 默认展开
        h+='<div class="group"><div class="group-hdr" onclick="toggleGroup(\'r_'+esc(tbl)+'\')">'
            +'<span class="arrow'+(isOpen?' open':'')+'">▶</span>'
            +'<span class="g-name">'+esc(tbl)+'</span>'
            +'<span class="g-cnt">('+items.length+')</span>'
            +'<span class="g-stat" style="color:'+(reviewed===items.length?'#16a34a':'#94a3b8')+'">'+reviewed+'/'+items.length+'</span>'
            +'</div><div class="group-body'+(isOpen?'':' collapsed')+'">';
        items.forEach(function(it){
            var r=it.rel, i=it.idx, k=r.source_table+'.'+r.source_column, s=S.r[k]||{};
            var st=s.status||'', tgt=s.target_table||r.target_table, tgtC=s.target_column||r.target_column;
            var cls=st==='confirmed'?'st-confirmed':st==='rejected'?'st-rejected':'';
            var badge=st==='confirmed'&&s.edited?'<span class="sb sb-edit">✎</span>':st==='confirmed'?'<span class="sb sb-ok">✓</span>':st==='rejected'?'<span class="sb sb-no">✗</span>':'';
            var isAdded=r._added?'<span class="sb sb-edit">新增</span>':'';
            h+='<div class="review-item '+cls+'">'
                +'<span class="r-src">.'+esc(r.source_column)+'</span>'
                +'<span class="r-arrow">→</span>'
                +'<span class="r-tgt" onclick="eRT('+i+')" title="点击修改目标表">'+esc(tgt)+'.'+esc(tgtC)+'</span>'
                +'<span class="r-conf">'+Math.round(r.confidence*100)+'%</span>'
                +badge+isAdded
                +'<span class="r-actions">'
                +'<button class="btn btn-green" onclick="rR('+i+',\'confirmed\')">✓</button>'
                +'<button class="btn btn-red" onclick="rR('+i+',\'rejected\')">✗</button>'
                +'</span></div>';
        });
        h+='</div></div>';
    });
    c.textContent='';
    var tmp=document.createElement('div');
    tmp.innerHTML=h;
    while(tmp.firstChild) c.appendChild(tmp.firstChild);
}

function toggleGroup(key){
    if(openGroups[key]===undefined) openGroups[key]=false; else openGroups[key]=!openGroups[key];
    drawR();drawE();
}

function drawE(){
    var c=document.getElementById('ecc'), all=EN.concat(addedEnums);
    document.getElementById('et').textContent=all.length;
    document.getElementById('ec').textContent=all.length;
    if(!all.length){c.textContent='无枚举候选';return;}
    var search=(document.getElementById('enum-search').value||'').toLowerCase();
    var h='';
    all.forEach(function(en){
        var k=en.table+'.'+en.column, s=S.e[k]||{};
        var st=s.status||'';
        // 过滤
        if(search && en.table.toLowerCase().indexOf(search)<0 && en.column.toLowerCase().indexOf(search)<0) return;
        if(enumFilter==='unreviewed' && st) return;
        if(enumFilter==='confirmed' && st!=='confirmed') return;
        if(enumFilter==='rejected' && st!=='rejected') return;
        var rv=s.rv||[], av=s.av||[];
        var cls=st==='confirmed'?'st-confirmed':st==='rejected'?'st-rejected':'';
        var conf=en.values[0]&&en.values[0].confidence?en.values[0].confidence:'medium';
        var ccls=conf==='high'?'ch-h':conf==='medium'?'ch-m':'ch-l';
        var clab=conf==='high'?'高':conf==='medium'?'中':'低';
        var badge=st==='confirmed'?'<span class="sb sb-ok">✓</span>':st==='rejected'?'<span class="sb sb-no">✗</span>':'';
        var isAdded=en._added?'<span class="sb sb-edit">新增</span>':'';
        var tags='';
        en.values.forEach(function(v){
            var vs=v.value===null?'NULL':String(v.value);
            var rem=rv.indexOf(vs)>=0;
            tags+='<span class="e-tag'+(rem?' removed':'')+'">'+esc(vs)+'<span class="cnt">'+(v.count||'')+'</span>';
            if(!rem) tags+='<span class="rx" onclick="rmEV(\''+esc(k).replace(/'/g,"\\'")+'\',\''+esc(vs).replace(/'/g,"\\'")+'\')">×</span>';
            tags+='</span>';
        });
        av.forEach(function(v){
            tags+='<span class="e-tag" style="border-color:#86efac;">'+esc(v)+'<span class="rx" onclick="rmAV(\''+esc(k).replace(/'/g,"\\'")+'\',\''+esc(v).replace(/'/g,"\\'")+'\')">×</span></span>';
        });
        tags+='<span class="add-btn" onclick="addEV(\''+esc(k).replace(/'/g,"\\'")+'\')">+ 添加</span>';
        h+='<div class="enum-item '+cls+'"><div class="enum-hdr">'
            +'<code style="color:#64748b;font-size:12px;">'+esc(en.table)+'.</code>'
            +'<code style="color:#1e40af;">'+esc(en.column)+'</code>'
            +'<span class="ch '+ccls+'">'+clab+'</span>'+badge+isAdded
            +'<span class="r-actions">'
            +'<button class="btn btn-green" onclick="rE(\''+esc(k).replace(/'/g,"\\'")+'\',\'confirmed\')">✓</button>'
            +'<button class="btn btn-red" onclick="rE(\''+esc(k).replace(/'/g,"\\'")+'\',\'rejected\')">✗</button>'
            +'</span></div><div class="e-tags">'+tags+'</div></div>';
    });
    c.textContent='';
    var tmp=document.createElement('div');
    tmp.innerHTML=h;
    while(tmp.firstChild) c.appendChild(tmp.firstChild);
}

function rR(i,st){var r=D.inferred_relations[i],k=r.source_table+'.'+r.source_column;if(!S.r[k])S.r[k]={};S.r[k].status=st;drawR();upd();}
function rE(k,st){if(!S.e[k])S.e[k]={};S.e[k].status=st;drawE();upd();}

function eRT(i){
    var r=D.inferred_relations[i],k=r.source_table+'.'+r.source_column;
    var cur=(S.r[k]&&S.r[k].target_table)||r.target_table;
    var p=document.getElementById('pop'),bg=document.getElementById('pbg');
    var opts='';TN.forEach(function(t){opts+='<option value="'+esc(t)+'"'+(t===cur?' selected':'')+'>'+esc(t)+'</option>';});
    p.textContent='';
    var tmp=document.createElement('div');
    tmp.innerHTML='<h3>修改目标表</h3><p style="margin-bottom:12px;color:#64748b;font-size:13px;">'+esc(k)+' →</p><select id="ets">'+opts+'</select><div class="brow"><button class="btn" onclick="cpop()">取消</button><button class="btn btn-green" onclick="sRT('+i+')">确定</button></div>';
    while(tmp.firstChild) p.appendChild(tmp.firstChild);
    p.style.display='block';bg.style.display='block';
}
function sRT(i){
    var r=D.inferred_relations[i],k=r.source_table+'.'+r.source_column;
    var nt=document.getElementById('ets').value;
    if(!S.r[k])S.r[k]={};S.r[k].target_table=nt;S.r[k].target_column='id';S.r[k].status='confirmed';S.r[k].edited=true;
    cpop();drawR();upd();
}
function cpop(){document.getElementById('pop').style.display='none';document.getElementById('pbg').style.display='none';}

function rmEV(k,v){if(!S.e[k])S.e[k]={};if(!S.e[k].rv)S.e[k].rv=[];S.e[k].rv.push(v);S.e[k].status='confirmed';drawE();upd();}
function rmAV(k,v){if(!S.e[k]||!S.e[k].av)return;S.e[k].av=S.e[k].av.filter(function(x){return x!==v});drawE();}
function addEV(k){var v=prompt('输入新的枚举值:');if(!v)return;if(!S.e[k])S.e[k]={};if(!S.e[k].av)S.e[k].av=[];S.e[k].av.push(v);S.e[k].status='confirmed';drawE();upd();}

function doAll(st){
    D.inferred_relations.forEach(function(r){var k=r.source_table+'.'+r.source_column;if(!S.r[k]||!S.r[k].status){if(!S.r[k])S.r[k]={};S.r[k].status=st;}});
    EN.forEach(function(en){var k=en.table+'.'+en.column;if(!S.e[k]||!S.e[k].status){if(!S.e[k])S.e[k]={};S.e[k].status=st;}});
    drawR();drawE();upd();
}
function doReset(){if(!confirm('确定要清除所有审核状态？'))return;S.r={};S.e={};drawR();drawE();upd();}

function upd(){
    var total=D.inferred_relations.length+EN.length, done=0;
    D.inferred_relations.forEach(function(r){var k=r.source_table+'.'+r.source_column;if(S.r[k]&&S.r[k].status)done++;});
    EN.forEach(function(en){var k=en.table+'.'+en.column;if(S.e[k]&&S.e[k].status)done++;});
    document.getElementById('pt').textContent='已审核: '+done+' / '+total;
    document.getElementById('pf').style.width=total?(done/total*100)+'%':'0%';
}

function doExport(){
    var rels=D.inferred_relations.map(function(r){
        var k=r.source_table+'.'+r.source_column,s=S.r[k]||{};
        return{source_table:r.source_table,source_column:r.source_column,
            original_target_table:r.target_table,original_target_column:r.target_column,
            target_table:s.target_table||r.target_table,target_column:s.target_column||r.target_column,
            confidence:r.confidence,status:s.status||'unreviewed',edited:!!s.edited};
    });
    var enums=EN.map(function(en){
        var k=en.table+'.'+en.column,s=S.e[k]||{};
        var rv=s.rv||[],av=s.av||[];
        var ov=en.values.map(function(v){return v.value});
        var fv=ov.filter(function(v){return rv.indexOf(v===null?'NULL':String(v))<0}).concat(av);
        return{table:en.table,column:en.column,
            confidence:en.values[0]&&en.values[0].confidence?en.values[0].confidence:'medium',
            status:s.status||'unreviewed',values:fv,original_values:ov,edited:rv.length>0||av.length>0};
    });
    var cr=rels.filter(function(r){return r.status==='confirmed'}).length;
    var rr=rels.filter(function(r){return r.status==='rejected'}).length;
    var er=rels.filter(function(r){return r.edited}).length;
    var ce=enums.filter(function(e){return e.status==='confirmed'}).length;
    var re=enums.filter(function(e){return e.status==='rejected'}).length;
    var result={apiscout_version:'0.1.1',database:D.database,dialect:D.dialect,
        scanned_at:D.scanned_at,reviewed_at:new Date().toISOString(),
        summary:{total_relations:rels.length,confirmed_relations:cr,rejected_relations:rr,edited_relations:er,
            total_enums:enums.length,confirmed_enums:ce,rejected_enums:re},
        relations:rels,enums:enums};
    var blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'});
    var url=URL.createObjectURL(blob);var a=document.createElement('a');
    var dt=new Date().toISOString().slice(0,10).replace(/-/g,'');
    a.href=url;a.download=D.database+'_review_'+dt+'.json';a.click();URL.revokeObjectURL(url);
}

function doImport(file){
    if(!file)return;var reader=new FileReader();
    reader.onload=function(ev){
        try{
            var data=JSON.parse(ev.target.result);
            S.r={};(data.relations||[]).forEach(function(r){
                var k=r.source_table+'.'+r.source_column;
                S.r[k]={status:r.status!=='unreviewed'?r.status:undefined,
                    target_table:r.edited?r.target_table:undefined,
                    target_column:r.edited?r.target_column:undefined,edited:r.edited};
            });
            S.e={};(data.enums||[]).forEach(function(en){
                var k=en.table+'.'+en.column;
                var os=new Set((en.original_values||[]).map(String));
                var fs=new Set((en.values||[]).map(String));
                var rv=[];os.forEach(function(v){if(!fs.has(v))rv.push(v)});
                var av=[];fs.forEach(function(v){if(!os.has(v))av.push(v)});
                S.e[k]={status:en.status!=='unreviewed'?en.status:undefined,rv:rv,av:av};
            });
            drawR();drawE();upd();
            alert('导入成功！已恢复 '+(data.relations||[]).length+' 个关系 + '+(data.enums||[]).length+' 个枚举的审核状态');
        }catch(err){alert('导入失败: '+err.message);}
    };
    reader.readAsText(file);
}

// 添加新关系
function addRelation(){
    var p=document.getElementById('pop'),bg=document.getElementById('pbg');
    var cols=[];D.tables.forEach(function(t){t.columns.forEach(function(c){if(c.name.match(/_id$/))cols.push(t.name+'.'+c.name)})});
    var srcOpts=cols.map(function(c){return'<option value="'+esc(c)+'">'+esc(c)+'</option>'}).join('');
    var tgtOpts=TN.map(function(t){return'<option value="'+esc(t)+'">'+esc(t)+'</option>'}).join('');
    p.textContent='';
    var tmp=document.createElement('div');
    tmp.innerHTML='<h3>添加新关系</h3>'
        +'<label style="font-size:13px;color:#64748b;">源字段</label><select id="add-src">'+srcOpts+'</select>'
        +'<label style="font-size:13px;color:#64748b;">目标表</label><select id="add-tgt">'+tgtOpts+'</select>'
        +'<div class="brow"><button class="btn" onclick="cpop()">取消</button><button class="btn btn-green" onclick="saveNewRel()">确定</button></div>';
    while(tmp.firstChild)p.appendChild(tmp.firstChild);
    p.style.display='block';bg.style.display='block';
}
function saveNewRel(){
    var src=document.getElementById('add-src').value;
    var tgt=document.getElementById('add-tgt').value;
    var parts=src.split('.');
    var newRel={source_table:parts[0],source_column:parts[1],target_table:tgt,target_column:'id',confidence:1.0,evidence:'用户手动添加',_added:true};
    addedRels.push(newRel);
    var k=newRel.source_table+'.'+newRel.source_column;
    S.r[k]={status:'confirmed',target_table:tgt,target_column:'id',edited:true};
    cpop();drawR();upd();
}

// 添加新枚举
function addEnum(){
    var p=document.getElementById('pop'),bg=document.getElementById('pbg');
    var colOpts=[];D.tables.forEach(function(t){t.columns.forEach(function(c){
        if(!c.enum_values||c.enum_values.length===0) colOpts.push(t.name+'.'+c.name);
    })});
    var opts=colOpts.map(function(c){return'<option value="'+esc(c)+'">'+esc(c)+'</option>'}).join('');
    p.textContent='';
    var tmp=document.createElement('div');
    tmp.innerHTML='<h3>添加枚举字段</h3>'
        +'<label style="font-size:13px;color:#64748b;">选择字段</label><select id="add-enum-col">'+opts+'</select>'
        +'<label style="font-size:13px;color:#64748b;">枚举值（逗号分隔）</label><input id="add-enum-vals" placeholder="值1,值2,值3" style="width:100%;padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;font-size:14px;margin-bottom:12px;">'
        +'<div class="brow"><button class="btn" onclick="cpop()">取消</button><button class="btn btn-green" onclick="saveNewEnum()">确定</button></div>';
    while(tmp.firstChild)p.appendChild(tmp.firstChild);
    p.style.display='block';bg.style.display='block';
}
function saveNewEnum(){
    var col=document.getElementById('add-enum-col').value;
    var vals=document.getElementById('add-enum-vals').value.split(',').map(function(v){return v.trim()}).filter(function(v){return v});
    if(!vals.length){alert('请输入至少一个值');return;}
    var parts=col.split('.');
    var newEnum={table:parts[0],column:parts[1],values:vals.map(function(v){return{value:v,count:0,confidence:'medium'}}),_added:true};
    addedEnums.push(newEnum);
    var k=newEnum.table+'.'+newEnum.column;
    S.e[k]={status:'confirmed'};
    cpop();drawE();upd();
}

document.addEventListener('DOMContentLoaded',init);
</script>
</body>
</html>"""


def generate_schema_report_html(report: SchemaReport) -> str:
    """从 SchemaReport 渲染可交互 HTML 字符串"""
    env = Environment(loader=BaseLoader())
    template = env.from_string(_INLINE_TEMPLATE)

    # 序列化报告数据为 JSON，嵌入 HTML
    report_dict = asdict(report)

    def _clean(obj):
        """清理不可序列化的值（memoryview/bytes 等）"""
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if isinstance(obj, (memoryview, bytes)):
            return f"<binary {len(obj)} bytes>"
        return obj

    clean_data = _clean(report_dict)
    schema_data_json = json.dumps(clean_data, ensure_ascii=False, default=str)

    return template.render(report=report, schema_data_json=schema_data_json)


def write_schema_report_html(report: SchemaReport, output_path: str) -> None:
    """生成并写入可交互 Schema HTML 报告"""
    html = generate_schema_report_html(report)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
