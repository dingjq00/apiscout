# APIScout 设计规格书

> 自动化 API 发现与文档生成工具
> 设计日期：2026-03-29
> 设计者：dingjq + Claude (playcard brainstorming)

---

## 1. 产品定位

### 项目背景

2026-03-29，insight68 项目的 L1-L5 质量评估暴露了严重问题（L3 全军覆没、L5 trend 聚合崩溃）。dingjq 决定：insight68 的质量问题交给那边的伙伴修，我们来做一个一直想做的实施工具 — 自动抓取客户系统 API。

### 一句话

给我一个 URL，还你一份 OpenAPI spec。

### 三重定位

1. **insight68 实施工具**（近期）— 到客户现场快速发现 API，缩短接入时间
2. **通用 API 逆向工程工具**（远期）— 面向开发者社区
3. 先解决自己的痛点，架构上不绑死 insight68

### 市场空白

现有工具都只做管道的一段。没有一个工具把"爬 → 抓 → 分析 → 生成"串起来：

| 工具 | 做什�� | 不做什么 |
|------|--------|---------|
| mitmproxy2swagger (9.3k stars) | HAR → OpenAPI | 不爬、不合并、不检测认证 |
| OpenAPI DevTools (4.3k stars) | 实时浏览器流量 → OpenAPI | 不爬、参数化只认 UUID |
| Crawlee / scrapy-playwright | SPA 爬虫 | 不抓 API、不生成 spec |
| Nango | 认证管理 | 不发现 API |

APIScout = 爬虫 + 抓包 + 推断 + 生成，完整闭环。

---

## 2. 核心工作流

### 三阶段

```
Phase 1: 自动探索（机器跑地图）
  启动 Playwright → 弹出浏览器 → 用户手动登录
  → 工具接管 session → 自动遍历页面
  → DOM 链接发现 + JS 静态分析 + 交互式探索
  → 实时收集所有 API 请求/响应
  → 输出：覆盖率报告（HTML）

Phase 2: 手动补录（人补盲区）— 可选
  Phase 1 完成后浏览��保持打开
  → 用户带着目标操作系统（报告里列出了未触发的端点）
  → 工具继续监听，实时显示新捕获的 API
  → 用户操作完毕 Ctrl+C 停止
  → 两批数据自动合并

Phase 3: 生成输出
  合并数据 → schema 推断 + 合并
  → ���径参数化 → 认证档案提取
  → 两遍设计：先出草稿 → 人工筛选 → 最终生成
  → 输出：OpenAPI 3.1 YAML + 认证档案 + HTML 报告 + 项目包
```

### Phase 1 → Phase 2 过渡

Phase 1 完成后终端提示：
```
✅ Phase 1 完成。报告已生成: report.html

当前浏览器保持打开，你可以：
  [Enter]  开始 Phase 2 手动补录
  [S]      跳过 Phase 2，直接生成
  [Q]      退出
```

### 关键设计决策

- **用户手动登录**：解决所有认证复杂度（SSO/MFA/CAPTCHA），工具只管接手 session
- **Phase 2 非必须**：如果 Phase 1 覆盖率够高，可跳过
- **两遍设计**（偷自 mitmproxy2swagger）：先生成全量草稿，标记不确定的端点让人审

---

## 3. 核心架构

### 分层结构

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
│   │   ├── router.py        #   路径参数化 + Radix tree 端点归并
│   │   ├── auth_detector.py #   认证模式检测
│   │   └── dedup.py         #   去重
│   ├── generator/           # 输出生成
│   │   ├── openapi.py       #   OpenAPI 3.1 YAML 生成
│   │   ├── auth_profile.py  #   认证档案（Nango 风格）
│   │   ├── report.py        #   HTML 覆盖率报告
│   │   └── ai_enricher.py   #   AI 增强（可选）
│   └── workflow.py          # 两遍工作流编排
├── ui/
│   ├── cli.py               # Click CLI 入口
│   └── live_panel.py        # 实时捕获面板（V1.1）
├── config/
│   └── default.yaml         # 默认配置
└── pack/
    └── pyinstaller.spec     # 打包脚本
```

### 分层原则

- `core/` 纯逻辑，不依赖 UI — 可被 CLI 调用，也可被未来 Web 面板调用
- `capture/` 只录不分析 — 原始数据存 JSONL
- `analyzer/` 只推断不关心来源 — 可吃 JSONL 也可吃 HAR
- `generator/` 只输出不关心推断过程

### 数据流

```
Playwright Browser
    │
    ├── crawler/* (探索页面，触发请求)
    │
    └── capture/recorder.py (监听所有响应)
            │
            ▼
    capture/store.py (JSONL 中间存储)
            │
            ▼
    analyzer/* (schema 推断 + 路由���配 + 认证检测)
            │
            ▼
    generator/* (OpenAPI + 认证档案 + 报告)
```

---

## 4. 自动爬虫引擎

市面上没��现成的 SPA "主动探索"方案。所有框架（Crawlee、scrapy-playwright）都只做"被动发现"（从 DOM 提取链接），不做"主动探索"（点击按钮���展开菜单）。这是我们的核心技术。

### 三层发现策略

**层 1：DOM 链接提取**

```python
selectors = [
    "a[href]",                          # 传统链接
    "[onclick]",                         # 点击事件
    "nav a, .sidebar a, .menu a",       # 导航菜单
    "[role='menuitem']",                 # ARIA 菜单项
    "[data-href], [data-url]",          # 数据属性链接
    "button[data-route]",               # SPA 路由按钮
]
```

**层 2：JS 静态分析**

从页面加载的 JS 文件中用正则提取 API 端点：

```python
patterns = [
    r'["\'](/api/[^"\']+)["\']',
    r'["\'](/v[0-9]+/[^"\']+)["\']',
    r'baseURL\s*[:=]\s*["\']([^"\']+)',
    r'fetch\s*\(\s*["\']([^"\']+)',
    r'axios\.[a-z]+\s*\(\s*["\']([^"\']+)',
    r'\.(?:get|post|put|delete|patch)\s*\(\s*[`"\']([^`"\']+)',
]
```

额外：如果发现 `.map` sourcemap 文件（V1.1），解析还原源码树做更深层分析。

**层 3：交互式探索**

系统化的视图发现引擎，覆盖企业系统的所有隐藏视图：

```python
view_discovery_pipeline = [
    # 1. 基础导航
    MenuExpander(),        # 展开所有菜单层级
    LinkCollector(),       # DOM 链接提取

    # 2. 页内视图切换
    TabSwitcher(),         # 点击所有 Tab 页签
    AccordionExpander(),   # 展开所有折叠面板
    TreeNodeExpander(),    # 树形菜单逐层展开

    # 3. 弹出视图
    ModalTrigger(),        # 点击"查看/详情"按钮 → 触发弹窗
    DrawerTrigger(),       # 侧边抽屉
    DropdownProber(),      # Select/Combobox ���程选项加载

    # 4. 数据交互
    TablePaginator(),      # 表格翻 2-3 页（捕获分页参数模式）
    SearchProber(),        # 空搜索触发搜索 API
    ScrollLoader(),        # 滚动加载

    # 5. 清理
    ModalCloser(),         # 关闭弹窗恢复页面状态
]
```

### 安全护栏

```python
SAFE_ACTIONS = ["查看", "详情", "搜索", "筛选", "导出", "刷新", "展开", "view", "detail", "search", "filter", "export"]
DANGEROUS_ACTIONS = ["删除", "提交", "审批", "确认", "发送", "保存", "新建", "delete", "submit", "approve", "confirm", "create"]
# DANGEROUS_ACTIONS：只记录按钮存在，不点击
```

### iframe 处理

```python
async def explore_page(self, page):
    await self._explore_frame(page.main_frame)
    for frame in page.frames:
        if frame != page.main_frame and frame.url != "about:blank":
            await self._explore_frame(frame)
```

### 爬虫控制

```yaml
crawl:
  max_depth: 5
  max_pages: 200
  page_timeout: 30s
  network_idle_wait: 3s
  request_delay: 500ms         # 对客户系统友好
  concurrent_pages: 1          # V1 单页顺序爬
  domain_scope: same-origin
  exclude_patterns: ["/logout", "/static/*", "/assets/*"]
  exploration_level: standard  # quick / standard / thorough
  respect_rate_limit: true     # 遇到 429 自动退避
```

### 执行顺序

每到一个新页面：层1 提取链接 → 层2 分析 JS → 层3 交互探索 → 收集所�� API → 下一个页面

---

## 5. 网络捕获层

### 捕获机制

Playwright `page.on("response")` 捕获所有��览器网络请求。对 B/S 系统，这和 mitmproxy 的捕获率没有实质差距（所有 XHR/fetch 都能捕到），但不需要安装 CA 证书。

### 协议检测

```python
class ProtocolDetector:
    def classify(self, request, response) -> str:
        if is_graphql(request):      return "graphql"
        if is_soap(request):         return "soap"
        if is_jsonrpc(request):      return "jsonrpc"
        if is_grpc_web(response):    return "grpc"
        if is_json_rest(response):   return "rest"      # 主路径
        if is_xml_rest(response):    return "rest_xml"
        return "unknown"
```

V1 聚焦 `rest`，其他协议标记发现但不做 schema 推断。

### JSONL 存储格式

```json
{
  "seq": 1,
  "timestamp": "2026-03-29T14:30:05Z",
  "page_url": "https://eam.customer.com/equipment/list",
  "method": "GET",
  "url": "https://eam.customer.com/api/equipment/search?status=1&page=1&size=20",
  "request_headers": {"Authorization": "Bearer eyJ..."},
  "request_body": null,
  "status": 200,
  "response_headers": {"Content-Type": "application/json"},
  "response_body": {"code": 0, "data": {"items": [...], "total": 165}},
  "resource_type": "fetch",
  "protocol": "rest"
}
```

response_body 存解析后的 JSON（不是原始字符串），方便后续 AI 增强时直接理解。

### 过滤规则

- 只捕获 XHR/fetch/document 类型
- 只捕获 same-origin 请求（不抓第三方 CDN/统计）
- 跳过 image/css/font/media 资源
- 大响应体截断：512KB 上限，保留前 512KB 用于 schema 推���

### 增量写盘 + 崩溃恢复

每抓到一个请求立即追加到 JSONL 文件。崩溃后 `--resume` 从上次中断继续，跳过已访问的 URL。

### Session 过期处理

监控响应状态码，连续出现 3 个 401/403 时暂停爬虫，提示用户重新登录。

### 多角色扫描

一个账号看不全所有功能。支持 `--append` 模式多次扫描：

```bash
# 第一次：管理员账号
apiscout explore --url https://eam.customer.com -o capture.jsonl

# 第二次：普通用户（追加到同一个文件）
apiscout explore --url https://eam.customer.com -o capture.jsonl --append

# 分析时自动合并去重
apiscout analyze capture.jsonl -o draft_spec.yaml
```

不同角色看到的端点并集 = 更完整的 API 覆盖。

### 进度显示

Phase 1 自动爬取期间，终端实时显示状态：

```
🔍 APIScout 自动探索中...

  页面: [===========     ] 28/43  当前: /equipment/list
  API:  89 个端点已捕获 (67 GET, 18 POST, 3 PUT, 1 DELETE)
  JS:   23 个端点从源码发现
  耗时: 12:35 / 预估剩余: ~8 分钟

  最近捕获:
    GET /api/equipment/search?status=1&page=2  → 200 (1.2s)
    GET /api/fault/list?equipmentId=1666       → 200 (0.8s)
```

---

## 6. Schema 推断引擎

### 多次观察合并

同一端点的每次��求/响应都收集，按 `(method, parameterized_path)` 聚合，最后合并 schema。

使用 Python `genson` 库：

```python
from genson import SchemaBuilder

builder = SchemaBuilder()
builder.add_object({"id": 1, "name": "设备A", "status": 1})
builder.add_object({"id": 2, "name": "设备B", "status": None, "memo": "备注"})

# 结果：
# - status: [integer, null]（nullable）
# - memo: 不在 required 里（optional）
# - required: [id, name]（交集）
```

### genson 之上的增强

| 增强项 | 方法 |
|--------|------|
| string format 检测 | 后处理正则：date-time/email/uuid/uri |
| enum 检测 | 同一字段唯一值 ≤10 且重复率 >50% → enum |
| 字段语义启发 | `*_id` → 关联ID，`*_time/*_at` → datetime |
| integer vs number | genson Python 版已区分 |

### 路径参数化

比 OpenAPI DevTools（只认 UUID）和 mitmproxy2swagger（只认纯数字）都强：

```python
param_patterns = [
    (r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', '{uuid}'),
    (r'^\d{15,}$', '{snowflakeId}'),       # 雪花 ID
    (r'^[0-9a-f]{24}$', '{objectId}'),      # MongoDB ObjectId
    (r'^\d+$', '{id}'),                     # ��数字 ID
    (r'^[0-9a-f]{6,12}$', '{hash}'),        # 短 hash
    (r'^[A-Z]{2,4}\d{8,}$', '{code}'),      # 编码型 ID（EQ202603110001）
]
```

智能命名：`/api/equipment/123/faults/456` → `/api/equipment/{equipmentId}/faults/{faultId}`（前一个路径段的单数形式 + "Id"）

### Radix Tree 路由匹配

新 URL 进来时：
1. 查 trie 有没有匹配的参数化路径
2. 有 → 归并到已有端点，合并 schema
3. 没有 → 检查路径段是否匹配 param_patterns → 参数化 → 插入 trie
4. 两个不同的具体路径参数化后相同 → 自动合并

---

## 7. 认证检测

### 检测逻辑

```python
class AuthDetector:
    def detect(self, requests) -> AuthProfile:
        # 1. HTTP 标准认证
        #    Bearer → 解析 JWT 的 exp/claims
        #    Basic → 标记

        # 2. API Key（标准头名）
        #    X-API-Key, X-Auth-Token, Api-Key 等

        # 3. 中国 ERP 非标认证
        #    X-KDApi-AcctID, X-KDApi-AppID, X-KDApi-AppSec（金蝶）
        #    用友自定义签名头

        # 4. Cookie/Session
        #    包含 token/session/jwt/auth/sid 关键词的 cookie
```

### 认证档案输出（Nango 风格）

```yaml
auth:
  type: bearer_jwt
  discovery:
    login_endpoint: POST /api/auth/login
    login_request_body:
      username: string
      password: string
    token_location: response.data.accessToken
    refresh_endpoint: POST /api/auth/refresh
    refresh_token_location: response.data.refreshToken
  token_analysis:
    algorithm: RS256
    lifetime_seconds: 7200
    claims: [sub, exp, iat, roles]
  insight68_config_hint:
    auth_adapter: "jwt_bearer"
    required_from_customer: ["服务账号用户名", "密码"]
```

### insight68 认证接入分析

insight68 生产环境调客户 API 时的三种方案：

| 方案 | 描述 | 适用场景 |
|------|------|---------|
| 共享服务账号 | insight68 用一个客户提供的服务账号 | 80% 客户，最简单 |
| 用户身份映射 | insight68 用户 ↔ 客户系统账号 映射表 | 需要"我的工单"等个人数据 |
| 统一身份源 | SSO/OIDC 集成 | 大企业，要求 IT 成熟度高 |

认证档案会根据检测到的认证类型，推荐最合适的接入方案。

---

## 8. 输出物

### 为什么输出 OpenAPI 而非直接生成 MCP Tool？

dingjq 的洞察：**"有些系统本身就可以提供 swagger"**。

这意味着有两条路通向 insight68 MCP Tool：
1. 系统自带 Swagger → 直接拿 OpenAPI spec
2. 系统没有文档 → APIScout 抓包生成 OpenAPI spec

两条路汇合到同一个格式（OpenAPI），downstream 的 MCP Tool 生成只需要一套逻辑。OpenAPI 是中间层标准，不是最终产物。

### 四件输出

1. **OpenAPI 3.1 YAML** — 标准格式，含 schema、parameters、responses、securitySchemes
2. **认证档案 auth_profile.yaml** — 认证类型、登录端点、token 生命周��、insight68 接入建议
3. **HTML 覆盖率报告** — 页面覆盖、端点清单、Phase 2 补录建议、认证摘要
4. **项目包**（可导出） — 以上所有 + capture.jsonl + meta.yaml，U 盘拷走

### 项目包结构

```
eam-customer-20260329/
├── capture.jsonl          # 原始捕获数据
├── draft_spec.yaml        # 规则引擎初步 spec（含审核标记）
├── auth_profile.yaml      # 认证档案
├── report.html            # 覆盖率报告
├── js_endpoints.json      # JS 静态分析发现的端点
├── screenshots/           # 每页自动截图（可选）
└── meta.yaml              # 项目元信息
```

### 两遍工作流

**第一遍：生成草稿**

所有发现的端点写�� `draft_spec.yaml`，附带审核标记：
- `confirmed` — 多��观察，确信度高
- `uncertain` — 只在 JS 中发��，未实际触发
- `excluded` — 看起来是系统内部接口
- `infrastructure` — 认证端点，归入认证档案

**人工审核**后，**第二遍：最终生成**。

### AI 增强（离线）

客户现场抓完，回办公室跑 AI 增强：

```bash
apiscout enrich ./eam-customer-20260329/ --ai deepseek
```

AI 增强内容：
- 端点命名和描述（`/api/equipment/{id}` → "获取设备详情"）
- 字段��义（`status: 1` → "1=运行中, 2=���修中"）
- enum 值含义标注
- 端点分组打 tags
- MCP Tool 描述生成（直接用于 insight68）

增强后输出：
- `enriched_spec.yaml` — AI 增强后的 OpenAPI spec
- `mcp_tools/` — insight68 可直接用的 MCP Tool 定义
- `enriched_report.html` — 增强后的报告

---

## 9. 技术约束与兼容性

### 前端技术兼容性

| 技术 | 支持 | 说明 |
|------|------|------|
| React / Vue / Angular | ✅ | Playwright 渲染 JS |
| jQuery / 传统 MVC (JSP/PHP) | ✅ | 全页刷新，更容易 |
| 若依 / JeecgBoot | ✅ | 国内制造业最常见 |
| Ext.js | ✅ 困�� | DOM 结构深，选择器复杂 |
| iframe 嵌套 | ✅ 需处理 | 自动检测并进入 |
| Shadow DOM | ✅ 需处理 | Playwright 可穿透 |
| 微前端 | ⚠️ | 多子应用各有路由 |
| Canvas/WebGL | ❌ 内容不可见 | API 调用仍可捕获 |

### 后端协议兼容性

| 协议 | V1 支持 | 说明 |
|------|---------|------|
| REST + JSON | ✅ 完整 | 主路径 |
| REST + XML | V1.1 | 用友/金蝶老版本 |
| GraphQL | V1.1 | 按 operationName 拆分 |
| SOAP | 标记发现 | 不做 schema 推断 |
| gRPC-Web | 标记发现 | 二进制无法解析 |
| WebSocket | 标记发现 | 不属于 OpenAPI 范畴 |

---

## 10. 打包与部署

### PyInstaller 打包

```
apiscout-portable/
├─��� apiscout.exe / apiscout     # 可执行文件
├── chromium/                    # Playwright 内置 Chromium
├── config/default.yaml
└── README.txt
```

使用 `--onedir` 模式（非 `--onefile`），避免启动时解压延迟。

### 跨平台

| 平台 | 优先级 | 说明 |
|------|--------|------|
| Windows x64 | P0 | 制造业 90% 是 Windows |
| macOS arm64 | P1 | 工程师自己的 Mac |
| Linux x64 | P2 | 按需 |

### 客户现场流程

1. 插 U 盘
2. 终端运行 `apiscout scan --url https://eam.customer.com`
3. 浏览���弹出 → 客户 IT 登录
4. 按 Enter → 自动探索 10-30 分钟
5. 查看报告 → 决定是否 Phase 2 补录
6. 完成 → 项目包自动生成在 U 盘上
7. 拔 U 盘回公司 → `apiscout enrich` AI 增强

全程不需要安装任何软件、Python、浏览器、代理、证书。

### 技术风险

**Playwright + PyInstaller 打包兼容性** 是 V1 最大的技术风险。需要第一个 spike 验证：
- Playwright 自定义 Chromium 路径（`PLAYWRIGHT_BROWSERS_PATH`）
- PyInstaller 打包 Playwright Python 绑定
- 打包后在无 Playwright 环境的机器上运行

---

## 11. V1 范围

### 做

| 模块 | 范围 |
|------|------|
| 爬虫 | 三层发现 + 隐藏视图探索 + 安全护栏 + iframe |
| 捕获 | REST + JSON，增量��盘，崩溃恢复 |
| Schema 推断 | genson 合并 + format/enum 检测 + 智能路径参数化 |
| 认证检测 | Bearer/Basic/API Key/Cookie/中国 ERP 非标 |
| 输出 | OpenAPI 3.1 YAML + 认证档案 + HTML 报告 + 项目包导出 |
| 工作流 | 两遍设计（草稿 → 审核 → 生成）|
| AI 增强 | `apiscout enrich` 离线增强 |
| 打包 | PyInstaller, Windows + macOS |

### 不做

| 非目标 | 原因 | 计划 |
|--------|------|------|
| C/S 桌面客户端 | 复杂度翻倍 | V2 评估 |
| REST + XML | 需要 XML schema 推断 | V1.1 |
| GraphQL | 需按 operationName 拆分 | V1.1 |
| SOAP / gRPC | 协议差异太大 | V2 或不做 |
| 实时 Web 面�� | CLI 够用 | V1.1 |
| 自动登录 | 用户手动登录更可靠 | 不做 |
| 数据脱敏 | `apiscout sanitize` | V1.1 |
| Sourcemap 反编译 | 深度 JS 分析 | V1.1 |
| Linux 打包 | 制造业不用 Linux 桌面 | 按需 |

### 成功标准

对标准 Vue + Spring Boot 系统（如若依框架）：

| 指标 | V1 目标 |
|------|--------|
| Phase 1 端点发现率 | ≥60%（读操作 API）|
| Schema 准确率 | ≥85%（字段类型 + required）|
| 认证检�� | 100% 识别类型 |
| 全流程耗时 | Phase 1 ≤30 分钟（100 页以内）|
| 打包体积 | ≤350MB |
| ���户现场零安装 | U 盘即用 |

### 技术依赖

```
核心（打进包）：
├── playwright          # 浏览器 + 网络捕获
├── genson              # JSON schema 推断
├── pyyaml              # YAML
├── jinja2              # HTML 报告
└── click               # CLI

AI 增强（仅办公室）：
└── openai              # DeepSeek API（OpenAI 兼容）
```

---

## 12. 研究发现（深度代码审查）

���下是设计过程中对关键开源项目的深度代码审查结论，供实现时参考。

### mitmproxy2swagger (9.3k stars)

- 总共 ~950 行实际逻辑，9 个 Python 文件
- **两遍设计是精华**：发现 → `x-path-templates` 带 `ignore:` 前缀 → 人工筛选 �� 生成
- **Schema 推断太弱**：只看第一次观察，���合并；不区分 integer/number；不检测 format；array 只看 `[0]`
- **HAR 请求头有 BUG**：`get_request_headers()` 缺少 return 语句
- **零认证检测**：无 securitySchemes
- **重度依赖 mitmproxy**：即使只用 HAR 功能也要装整个 mitmproxy 栈
- **可做 library 用**：Reader 类可独立导入，但 `main()` 返回 None（写文件不返回结果）

### OpenAPI DevTools (4.3k stars)

- ~800 行核心逻辑，TypeScript，架构清晰
- **genson-js 做 schema 合并是核心**：多次观��合并，required = 交集，nullable 自动处理
- **Radix tree 路由匹配**：高效的 URL 归并，参数化路径自动合并后续请求
- **认证推断**：Bearer/Basic/Digest + 17 个 API Key 头名 + Cookie 关键词匹配
- **自动参数化只认 UUID**：数字 ID 不自动识别，是最大弱点
- **路径参数类型永远 string**：不从观察值推断
- **lib 层可脱离 Chrome 扩展独立使用**：架构分层做得好
- **每次全量重建 spec**：无增量更新，大量端点时可能有性能问题

### scrapy-playwright / Crawlee

- scrapy-playwright：~980 ���，本质是 Scrapy Download Handler 替换
- Crawlee enqueueLinks()：就是 `querySelectorAll('a')` 取 href
- **两者都不做**：SPA 路由发现、API 捕获、HAR 录制、交互式探索
- **结论**：SPA 自动爬虫市面上没有现成方案，必须自建

### Nango (YC W23)

- **YAML 驱动认证配置是核心模式**：734 个 provider 全靠 YAML + `${interpolation}`
- **TWO_STEP 模式**：可处理中国 ERP 的非���认证（多步 token 获取、自定义 Header）
- **Token 刷新 production-grade**：分布式锁 + 内存去重 + 4 天疲劳熔断
- **没有正式 adapter 接口**：150 行 if/else 链
- **�� APIScout ���价值**：认证档案输出格式参考；对 insight68 的价值：AuthAdapter 参考架构

### 中国 ERP 认证模式

| 系统 | 认证方式 |
|------|---------|
| 用友 U8 | 自定义 Header (X-KDApi-*) + SHA256 签名 |
| 金蝶云星空 | AppID + AppSecret + 账套ID |
| 钉钉 | AppKey + AppSecret → access_token (2h) |
| 简道云 | API Key in Bearer header |

标准 OAuth 在中国制造业很少见。auth_detector.py 必须覆盖这些非标模式。

---

## 13. 测试策略

### 开发��试系统

使用 dingjq 本机的真实系统：
- `/Users/dingjq/IdeaProjects/eamNge` — EAM 系统
- `/Users/dingjq/IdeaProjects/momExcetion` — MOM 系统

### 同事验证

V1 功能稳定后，打包交给同事在他们机器上的系统测试，验证：
- 可移��性（零安装运行）
- 跨系统兼容性（不同前端框架/后端技术）
- 覆盖率表现
