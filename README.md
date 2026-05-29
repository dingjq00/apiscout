# APIScout

> 给我一个 URL（或数据库、或 Swagger 文件），还你一份完整的系统接入方案。

客户系统接入方案生成器，insight68 客户实施的核心工具。不管客户系统什么技术栈、有没有
API 文档，都能快速生成接入方案（OpenAPI spec / 数据库 Schema 报告）。

支持场景：
- **有 REST API** — 录制操作 → 自动生成 OpenAPI spec
- **有 Swagger** — 直接导入 → 生成文档
- **有框架 metadata**（Jmix / Spring Boot / 若依）— 适配器自动生成 spec
- **有数据库** — 扫描 schema → 报告（表结构 + 枚举 + 关系）→ 交叉增强 OpenAPI

---

## 快速上手（开发者）

### 1. 环境要求
- Python **3.11+**
- 联网（首次需下载 Chromium 浏览器内核）

### 2. 安装

```bash
# 建议先建虚拟环境
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 安装依赖 + 本项目（可编辑模式，改代码立即生效）
pip install -e .

# 下载 Playwright 浏览器内核（必须，约 150MB）
playwright install chromium
```

> 数据库扫描功能需按目标库类型额外装驱动（可选）：
> ```bash
> pip install -e ".[postgresql]"   # 或 mysql / oracle / mssql / db-all
> pip install -e ".[ai]"           # AI 增强（DeepSeek/OpenAI）
> pip install -e ".[dev]"          # 跑测试需要的 pytest
> ```

### 3. 跑起来

```bash
apiscout web                       # Web 面板（推荐），打开 http://localhost:9527
apiscout scan https://target.com --manual   # 命令行手动模式（最稳定）
apiscout import swagger.json       # 导入已有 Swagger
apiscout db "postgresql://readonly:pass@host:5432/dbname"   # 扫数据库
```

### 4. 跑测试

```bash
pip install -e ".[dev]"
pytest tests/ -q                   # 197 个测试，纯 mock，不连真实系统
```

---

## 典型工作流（Web 面板）

1. `apiscout web` → 浏览器打开 `http://localhost:9527`
2. 输入目标系统 URL → 点「开始扫描」→ 弹出浏览器
3. 在浏览器里**登录系统、手动点一遍要接入的功能**
4. 点「停止录制 → 生成文档」
5. 查看 `output/<域名>/` 下的产物

| 产物 | 说明 |
|------|------|
| `api_docs.html` | 交互式 API 文档（Swagger UI，可直接发客户） |
| `draft_spec.yaml` | OpenAPI 3.1 规格书 |
| `auth_profile.yaml` | 认证方式档案 |
| `report.html` | 覆盖率报告 |
| `capture.jsonl` | 原始捕获数据（**含客户业务数据，勿外传/勿入库**） |

> **核心理念**：手动录制 + 分析是主线，自动探索只是锦上添花。纯自动推断 = demo 质量，
> 最终一定要人工审核。

---

## 项目结构

```
apiscout/
├── adapters/     框架发现策略（@register 注册：Jmix / Spring Boot / 若依）
├── core/         纯逻辑引擎，不依赖任何 UI
│   ├── crawler/    页面探索（导航/链接/JS 分析/滚动）
│   ├── capture/    网络捕获（只录不分析，存 JSONL）
│   ├── analyzer/   分析推断（schema 合并/路由参数化/认证检测）
│   ├── db_scanner/ 数据库 Schema 扫描（V1.1，多方言）
│   └── generator/  输出生成（OpenAPI / Swagger UI / 报告）
├── ui/cli.py     命令行入口
└── web/app.py    Web 面板（FastAPI + WebSocket）
```

详细架构与每个设计决策的「为什么」见：
- `docs/architecture.html`、`docs/guide.html`（浏览器打开）
- `docs/specs/`（完整设计规格）
- `CLAUDE.md`（开发规范、架构原则、偷师清单）

---

## 部署给客户 / 同事

U 盘便携部署、离线包、Windows 一键安装见 `pack/README_部署.md`。

---

## 开发约定（改代码前先读）

- **中文注释和日志**
- 全异步（`async/await`，Playwright 是异步的）
- `except Exception:`，不要裸 `except:`
- 配置走 `apiscout/config/default.yaml`，支持 CLI 参数覆盖
- 文件写入用原子操作或增量追加；时间戳用 UTC
- `core/` 必须保持纯逻辑，不能反向依赖 `ui/` 或 `web/`
- 加新框架适配器 → 在 `adapters/` 用 `@register`，不改旧代码

### 安全红线
- 不在代码中硬编码密钥；AI key 走环境变量或 CLI 参数
- `capture.jsonl` / `output/` / `test_output/` 含客户业务数据，**已 gitignore，不要提交**
- 自动探索有护栏：不点删除/提交/保存等危险按钮
