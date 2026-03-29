# CLAUDE.md — APIScout

## 项目概述

APIScout — 自动化 API 发现与文档生成工具。

**一句话**：给我一个 URL，还你一份 OpenAPI spec。

**定位**：先解决 insight68 客户实施的痛点（快速发现客户系统 API），架构上保留通用化可能。

**核心场景**：实施工程师到客户现场，U 盘插上去运行，自动发现客户 B/S 系统的全部后端 API，生成 OpenAPI 3.1 spec + 认证档案，回办公室用 AI 增强后直接转为 insight68 MCP Tool 定义。

## 设计文档

**完整设计规格**：`docs/specs/2026-03-29-apiscout-design.md`
- 包含所有研究发现、偷师清单、技术选型理由、架构设计、V1 范围
- 任何设计决策的"为什么"都在这份文档里

**来源**：由 playcard 项目 brainstorming 产出（2026-03-29），dingjq + Claude 协作设计。

## 关联项目

| 项目 | 关系 |
|------|------|
| **insight68-platform** | APIScout 的输出（OpenAPI spec）是 insight68 MCP Tool 定义的输入 |
| **playcard** | APIScout 的设计过程、研究资料存放在 playcard |

## 技术栈

- Python 3.11 (miniconda)
- Playwright — 浏览器自动化 + 网络捕获 + HAR 录制（唯一引擎）
- genson — JSON Schema 推断与合并
- PyYAML — YAML 读写
- Jinja2 — HTML 报告模板
- Click — CLI 框架
- PyInstaller — 打包为独立可执行文件

## 项目结构

```
apiscout/
├── core/                    # 核心引擎（纯逻辑，无 UI）
│   ├── crawler/             # Phase 1 自动探索
│   │   ├── navigator.py     #   页面导航 + 菜单/按钮交互
│   │   ├── link_extractor.py#   DOM 链接提取
│   │   ├── js_analyzer.py   #   JS 静态分析提取 API URL
│   │   └── scroll_loader.py #   滚动加载触发
│   ├── capture/             # 网络捕获层
│   │   ├── recorder.py      #   page.on("response") 实时录制
│   │   ├── filter.py        #   域名/资源类型/协议过滤
│   │   └── store.py         #   JSONL 中间存储（增量写盘）
│   ├── analyzer/            # 分析推断引擎
│   │   ├── schema_engine.py #   genson 多次合并 + format/enum 检测
│   │   ├── router.py        #   路径参数化 + 端点归并
│   │   ├── auth_detector.py #   认证模式检测
│   │   └── dedup.py         #   去重
│   ├── generator/           # 输出生成
│   │   ├── openapi.py       #   OpenAPI 3.1 YAML 生成
│   │   ├── auth_profile.py  #   认证档案
│   │   ├── report.py        #   HTML 覆盖率报告
│   │   └── ai_enricher.py   #   AI 增强（可选，离线使用）
│   └── workflow.py          # 两遍工作流编排
├── ui/
│   ├── cli.py               # Click CLI 入口
│   └── live_panel.py        # 实时捕获面板（V1.1）
├── config/
│   └── default.yaml         # 默认配置
├── tests/                   # 测试
└── pack/
    └── pyinstaller.spec     # 打包配置
```

## 开发规范

### 代码风格
- 中文注释和日志
- async/await 全异步（Playwright 是异步的）
- `except Exception:` 而非裸 `except:`
- 配置通过 `config/default.yaml`，支持 CLI 参数覆盖
- 文件写入用原子操作或增量追加
- 时间戳用 UTC

### 架构原则
- **core/ 是纯逻辑**：不依赖任何 UI，可被 CLI 调用也可被未来 Web 面板调用
- **capture 只录不分析**：原始数据存 JSONL，分析交给 analyzer
- **analyzer 只推断不关心数据来源**���可以吃 JSONL，也可以吃 HAR
- **V1 聚焦 REST + JSON**：其他协议标记发现但不解析

### 安全
- 不在代码中硬编码密钥
- capture.jsonl 含客户业务数据，不入库
- AI enricher 的 API key 通过环境变量或 CLI 参数传入

## 常用命令

```bash
# 开发运行
python -m apiscout scan --url https://target-system.com

# 分步执行
python -m apiscout explore --url https://target-system.com -o capture.jsonl
python -m apiscout analyze capture.jsonl -o draft_spec.yaml
python -m apiscout generate draft_spec.yaml -o output/

# AI 增强���回办公室后）
python -m apiscout enrich output/ --ai deepseek --api-key $DEEPSEEK_API_KEY

# 打包
pyinstaller pack/pyinstaller.spec --onedir

# 测试（用 dingjq 本机的 EAM/MOM 系统）
# eamNge: /Users/dingjq/IdeaProjects/eamNge
# momException: /Users/dingjq/IdeaProjects/momExcetion
```

## 偷师清单

设计过程中深度审查了多个开源项目，提炼的可复用���式：

| # | 来源 | 偷什么 | 用在哪 |
|---|------|--------|--------|
| 1 | OpenAPI DevTools (4.3k stars) | genson schema 多次观察合并，required=交集 | schema_engine.py |
| 2 | OpenAPI DevTools | 路由匹配思路（V1 用参数化归并 dict） | router.py |
| 3 | OpenAPI DevTools | 认证自动推断（Bearer/Basic/API Key/Cookie） | auth_detector.py |
| 4 | OpenAPI DevTools | lib 层与 UI 层分离 | 整体架构 |
| 5 | mitmproxy2swagger (9.3k stars) | 两遍设计（发现→筛选→生成） | workflow.py |
| 6 | Crawlee | DOM 链接提取思路 | link_extractor.py |
| 7 | Crawlee | infinite_scroll（滚动+监听网络） | scroll_loader.py |
| 8 | Katana | JS 静态分析提取 API 端点 | js_analyzer.py |
| 9 | Nango (YC W23) | YAML 驱动认证配置+插值 | auth_profile.py |
| 10 | Nango | TWO_STEP 模式覆盖非标认证 | auth_profile.py |
| 11 | LinkFinder | 正则提取 JS 中的 API URL | js_analyzer.py |
| 12 | PlayCard 经验 | 域名过滤、JSONL 格式、协议优先 | capture/ |
| 13 | 深度审查 | 路径参数化覆盖数字ID/UUID/slug/hash/编码ID | router.py |
| 14 | 市场调研 | 中国 ERP 非标认证（用友/金蝶自定义 Header） | auth_detector.py |
| 15 | Optic (Atlassian 归档) | 迭代收敛循环：diff→patch→re-diff 直到稳定 | schema_engine.py |
| 16 | Optic | Path inference 启发式：保留词排除+父段单数化 | router.py |
| 17 | Optic | YAML roundtrip writer：AST 上 apply patch 保留格式 | openapi.py |
| 18 | Akita (Postman 归档) | Decorator Chain 处理管线：Collector 包 Collector | recorder.py |
| 19 | Akita | CategorizeString：int64→uint64→float64→bool→string | schema_engine.py |
| 20 | Meeshkan (关闭) | fold/reduce 增量构建 + 边录边推断 | workflow.py |
| 21 | Meeshkan | 失败教训：纯自动推断=demo质量，必须人工审核 | 两遍设计的理论支撑 |

详细的代码审查发现见设计文档的"研究发现"章节。
