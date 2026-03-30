# CLAUDE.md — APIScout

## 项目概述

APIScout — 客户系统接入方案生成器。

**一句话**：给我一个 URL（或数据库、或 Swagger 文件），还你一份完整的系统接入方案。

**定位**：insight68 客户实施的核心工具。不管客户系统什么技术栈、有没有 API 文档，都能快速生成接入方案。

**核心场景**：
1. **有 API 的系统**：录制操作 → 自动生成 OpenAPI spec → 转为 insight68 MCP Tool
2. **有 Swagger 的系统**：直接导入 → 生成文档
3. **有框架 metadata 的系统**（Jmix/Spring Boot）：适配器自动生成 spec
4. **有数据库的系统**（V1.1）：扫描 schema → 报告（表结构 + 枚举 + 关系）→ 交叉增强 OpenAPI
5. **U 盘便携部署**：Windows 在线安装包 564KB，双击即用

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
- psycopg2 / mysql-connector / oracledb / pymssql — 数据库驱动（按需安装）
- PyInstaller — 打包为独立可执行文件

## 项目结构

```
apiscout/
├── adapters/                # 框架发现策略（@register 模式）
│   ├── registry.py          #   注册表 + detect_framework()
│   ├── jmix.py              #   Jmix metadata → spec
│   ├── spring_boot.py       #   Spring Boot /v3/api-docs → spec
│   └── ruoyi.py             #   若依 swagger → spec
├── core/                    # 核心引擎（纯逻辑，无 UI）
│   ├── crawler/             # 页面探索
│   │   ├── navigator.py     #   BFS + SPA 菜单点击 + 按钮探索
│   │   ├── api_prober.py    #   API 文档端点探测（15 个已知端点）
│   │   ├── link_extractor.py#   DOM 链接提取（含 hash 路由）
│   │   ├── js_analyzer.py   #   JS 静态分析提取 API URL
│   │   └── scroll_loader.py #   滚动加载触发
│   ├── capture/             # 网络捕获层
│   │   ├── recorder.py      #   Playwright 响应监听 + 子域名自动跳转
│   │   ├── filter.py        #   域名/资源类型/框架噪声过滤
│   │   └── store.py         #   JSONL 增量写盘（崩溃安全）
│   ├── analyzer/            # 分析推断引擎
│   │   ├── schema_engine.py #   genson 多次合并 + format/enum 检测
│   │   ├── router.py        #   路径参数化归并 + 保留词排除
│   │   ├── auth_detector.py #   认证检测（JWT/Basic/API Key/金蝶/用友）
│   │   ├── dedup.py         #   端点聚合 + query 参数推断
│   │   └── schema_enricher.py # 用 DB schema 增强 OpenAPI spec（V1.1）
│   ├── db_scanner/          # 数据库 Schema 扫描（V1.1）
│   │   ├── models.py        #   数据模型（ColumnInfo/TableInfo/SchemaReport）
│   │   ├── connector.py     #   连接管理 + 方言自动检测
│   │   ├── introspector.py  #   扫描编排（组合所有模块）
│   │   ├── sampler.py       #   枚举探测（置信度分级）+ 随机采样
│   │   ├── relations.py     #   关系推断（命名模式匹配）
│   │   └── dialect/         #   方言 SQL
│   │       ├── base.py      #     BaseDialect 接口 + 类型归一化
│   │       ├── postgresql.py#     PostgreSQL（information_schema + pg_stat）
│   │       ├── mysql.py     #     MySQL
│   │       ├── oracle.py    #     Oracle（ALL_TAB_COLUMNS）
│   │       └── mssql.py     #     SQL Server
│   ├── generator/           # 输出生成
│   │   ├── openapi.py       #   OpenAPI 3.1 YAML
│   │   ├── jmix_spec.py     #   Jmix metadata → 完整 CRUD spec
│   │   ├── swagger_ui.py    #   Swagger UI 单文件 HTML
│   │   ├── auth_profile.py  #   认证档案（含登录流追踪）
│   │   ├── report.py        #   HTML 覆盖率报告
│   │   ├── schema_report_html.py # DB Schema HTML 报告（V1.1）
│   │   └── ai_enricher.py   #   AI 增强（DeepSeek/OpenAI）
│   ├── config.py            # 配置加载
│   └── workflow.py          # 工作流编排
├── ui/
│   └── cli.py               # CLI（scan/import/analyze/enrich/web/db）
├── web/
│   └── app.py               # Web 面板（FastAPI + WebSocket）
├── config/
│   └── default.yaml         # 默认配置
├── tests/                   # 197 个测试
├── scripts/                 # 集成测试 + 调试工具
└── pack/                    # 部署打包
    ├── portable/            #   Windows 离线便携包（229MB）
    ├── 一键安装.bat          #   在线安装入口
    ├── setup_portable.ps1   #   PowerShell 在线安装脚本
    ├── build_online_pack.sh #   构建在线安装 zip（564KB）
    ├── install_windows.bat  #   有 Python 时一键安装
    └── run.bat              #   启动脚本
```

## 与 insight68 的接口

APIScout 输出 → insight68 MCP Tool 输入：

| 客户情况 | APIScout 输出 | insight68 Tool 类型 |
|---------|-------------|-------------------|
| 有 REST API | OpenAPI spec | rest_api（调 API） |
| 有 Swagger 文件 | 导入 → OpenAPI spec | rest_api |
| 有框架 metadata | 适配器 → OpenAPI spec | rest_api |
| 有数据库 | Schema 报告 + 交叉增强 spec | rest_api（更精确）|
| 只有数据库（V2） | Schema + 文档 → SQL 模板集 | db_query（查 DB） |

## 开发规范

### 代码风格
- 中文注释和日志
- async/await 全异步（Playwright 是异步的）
- `except Exception:` 而非裸 `except:`
- 配置通过 `config/default.yaml`，支持 CLI 参数覆盖
- 文件写入用原子操作或增量追加
- 时间戳用 UTC

### 架构原则
- **core/ 是纯逻辑**：不依赖任何 UI，CLI / Web / 桌面端都能用
- **adapters/ 是发现策略**：@register 注册，加新框架不改旧代码
- **capture 只录不分析**：原始数据存 JSONL，分析交给 analyzer
- **analyzer 只推断不关心数据来源**：可以吃 JSONL，也可以吃 HAR
- **手动模式优先**：自动探索是锦上添花，录制+分析是核心
- **V1 聚焦 REST + JSON**：其他协议标记发现但不解析
- **枚举检测不追求完美**：置信度分级（high/medium/low），交给人/AI 最终判断
- **db_scanner/ 跟 crawler/ 平级**：可独立使用，也可交叉增强

### 安全
- 不在代码中硬编码密钥
- capture.jsonl 含客户业务数据，不入库
- AI enricher 的 API key 通过环境变量或 CLI 参数传入
- 自动探索有安全护栏：不点删除/提交/保存等危险按钮

## 常用命令

```bash
# Web 面板（推荐）
apiscout web

# 扫描 — 手动模式（最稳定）
apiscout scan https://target-system.com --manual

# 扫描 — 自动+手动
apiscout scan https://target-system.com

# 导入已有 Swagger
apiscout import swagger.json
apiscout import https://target-system.com/v3/api-docs

# 分析已有数据
apiscout analyze output/target/capture.jsonl -o output/target

# 数据库 Schema 扫描（V1.1）
apiscout db "postgresql://user:pass@host:5432/dbname"
apiscout db "postgresql://..." -x "act_*" -x "qrtz_*"    # 排除框架表
apiscout db "postgresql://..." --enrich output/target/openapi.yaml  # 交叉增强

# AI 增强
apiscout enrich output/target --api-key $DEEPSEEK_API_KEY

# 测试
pytest tests/ -v

# 测试系统
# eamNewGe: /Users/dingjq/IdeaProjects/eamNewGe (若依+Vue，PG: postgres:postgres@localhost:5432/eam_db)
# momExecution: /Users/dingjq/IdeaProjects/momExcetion (Jmix+Vaadin)
# gtshebei: https://www.gtshebei.com (Vue SPA)
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
