# APIScout 部署指南

## 场景 A：同事电脑已有 Python

```
1. U 盘拷贝整个 apiscout 项目文件夹
2. 双击 pack/install_windows.bat
3. 双击 pack/run.bat
4. 浏览器打开 http://localhost:9527
```

## 场景 B：同事电脑没有 Python（推荐）

```
1. U 盘拷贝整个 apiscout 项目文件夹
2. 右键 pack/setup_portable.ps1 → 用 PowerShell 运行
   （或在 cmd 中：powershell -ExecutionPolicy Bypass -File pack\setup_portable.ps1）
3. 等待自动下载 Python + Chromium（约 5 分钟，需联网）
4. 完成后双击 pack/启动APIScout.bat
```

## 场景 C：你的 Mac 能访问同事的系统

```
直接在你的 Mac 上：
apiscout web
然后输入同事系统的 URL
```

## 使用流程

1. Web 面板打开后输入目标系统 URL
2. 点击「开始扫描」→ 浏览器弹出
3. 在浏览器中登录系统
4. 自由点击操作系统各功能
5. 操作完后点击「停止录制 → 生成文档」
6. 查看生成的 Swagger UI 文档

## 输出文件

| 文件 | 说明 |
|------|------|
| api_docs.html | 交互式 API 文档（Swagger UI） |
| draft_spec.yaml | OpenAPI 3.1 规格书 |
| auth_profile.yaml | 认证方式档案 |
| report.html | 覆盖率报告 |
| capture.jsonl | 原始捕获数据 |
