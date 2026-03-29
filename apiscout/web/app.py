"""APIScout Web 面板 — 一个页面搞定扫描 + 结果展示"""
import asyncio
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("apiscout.web")

app = FastAPI(title="APIScout")

# 扫描状态
_state = {
    "status": "idle",       # idle / scanning / done / error
    "url": "",
    "captured": 0,
    "endpoints": 0,
    "message": "",
    "output_dir": "",
    "phase": "",            # login / detect / explore / manual / analyze
}

# 活跃的 WebSocket 连接
_ws_clients: list[WebSocket] = []


async def _broadcast(data: dict):
    """广播状态到所有 WebSocket 客户端"""
    _state.update(data)
    msg = json.dumps(_state, ensure_ascii=False)
    for ws in _ws_clients[:]:
        try:
            await ws.send_text(msg)
        except Exception:
            _ws_clients.remove(ws)


@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML_PAGE


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    await websocket.send_text(json.dumps(_state, ensure_ascii=False))
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "scan":
                asyncio.create_task(_run_scan(msg["url"], msg.get("manual", False)))
            elif msg.get("action") == "stop":
                _state["phase"] = "stopping"
                await _broadcast({"message": "正在停止录制..."})
    except Exception:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


@app.get("/output/{path:path}")
async def serve_output(path: str):
    file_path = Path(_state.get("output_dir", "")) / path
    if file_path.exists():
        return FileResponse(file_path)
    return HTMLResponse("文件不存在", status_code=404)


async def _run_scan(url: str, manual: bool = False):
    from playwright.async_api import async_playwright
    from apiscout.core.capture.store import CaptureStore
    from apiscout.core.capture.filter import RequestFilter
    from apiscout.core.capture.recorder import PageRecorder
    from apiscout.core.workflow import analyze_capture, generate_outputs
    from apiscout.core.generator.swagger_ui import generate_swagger_html

    parsed = urlparse(url)
    target_origin = f"{parsed.scheme}://{parsed.netloc}"
    host = parsed.netloc.replace(":", "_")
    output_dir = Path(f"./output/{host}")
    output_dir.mkdir(parents=True, exist_ok=True)
    capture_file = output_dir / "capture.jsonl"

    _state["output_dir"] = str(output_dir)

    await _broadcast({
        "status": "scanning", "url": url, "phase": "login",
        "message": "请在弹出的浏览器中登录系统...",
    })

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False, args=["--ignore-certificate-errors"],
            )
            context = await browser.new_context(
                ignore_https_errors=True, viewport={"width": 1440, "height": 900},
            )
            page = await context.new_page()

            store = CaptureStore(capture_file)
            request_filter = RequestFilter(target_origin=target_origin)
            recorder = PageRecorder(store, request_filter)
            await recorder.attach(page)

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _broadcast({"message": "浏览器已打开 — 请登录，然后自由操作系统。点击「停止录制」生成文档"})

            while _state["phase"] != "stopping":
                current = recorder.captured_count
                if current != _state["captured"]:
                    await _broadcast({
                        "captured": current,
                        "message": f"录制中... 已捕获 {current} 请求",
                    })

                # 检测域名跳转
                try:
                    actual_origin = f"{urlparse(page.url).scheme}://{urlparse(page.url).netloc}"
                    if actual_origin != recorder.filter.target_origin:
                        base1 = ".".join(urlparse(recorder.filter.target_origin).netloc.split(".")[-2:])
                        base2 = ".".join(urlparse(actual_origin).netloc.split(".")[-2:])
                        if base1 == base2:
                            recorder.filter.target_origin = actual_origin
                except Exception:
                    pass

                await asyncio.sleep(0.5)

            await _broadcast({"phase": "analyze", "message": "正在分析..."})
            store.close()
            await browser.close()

        analysis = analyze_capture(str(capture_file))
        stats = analysis["stats"]
        title = f"{parsed.netloc} API"

        generate_outputs(analysis, str(output_dir), title=title, base_url=target_origin)

        spec_path = output_dir / "draft_spec.yaml"
        if spec_path.exists():
            generate_swagger_html(
                spec=str(spec_path),
                output_path=str(output_dir / "api_docs.html"),
                title=title,
            )

        await _broadcast({
            "status": "done", "phase": "done",
            "endpoints": stats["total_endpoints"],
            "captured": stats["total_records"],
            "message": f"完成! {stats['total_endpoints']} 个端点",
        })

    except Exception as e:
        logger.exception("扫描失败")
        await _broadcast({
            "status": "error", "phase": "error",
            "message": f"错误: {e}",
        })


_HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>APIScout</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
  .container { max-width: 800px; margin: 0 auto; padding: 40px 20px; }
  h1 { font-size: 28px; color: #60a5fa; margin-bottom: 8px; }
  .subtitle { color: #94a3b8; margin-bottom: 40px; font-size: 15px; }
  .input-group { display: flex; gap: 12px; margin-bottom: 24px; }
  input[type="text"] {
    flex: 1; padding: 14px 18px; border: 2px solid #334155; border-radius: 10px;
    background: #1e293b; color: #f1f5f9; font-size: 16px; outline: none;
  }
  input:focus { border-color: #60a5fa; }
  .btn {
    padding: 14px 28px; border: none; border-radius: 10px; font-size: 15px;
    font-weight: 600; cursor: pointer; transition: all 0.2s; white-space: nowrap;
  }
  .btn-primary { background: #2563eb; color: white; }
  .btn-primary:hover { background: #3b82f6; }
  .btn-danger { background: #dc2626; color: white; }
  .btn-danger:hover { background: #ef4444; }
  .status-bar {
    background: #1e293b; border: 1px solid #334155; border-radius: 12px;
    padding: 20px 24px; margin-bottom: 24px;
  }
  .status-phase { font-size: 13px; color: #94a3b8; margin-bottom: 4px; }
  .status-message { font-size: 18px; font-weight: 500; }
  .stats { display: flex; gap: 40px; margin-top: 16px; }
  .stat-number { font-size: 36px; font-weight: 700; color: #60a5fa; }
  .stat-label { font-size: 12px; color: #94a3b8; }
  .result-links { margin-top: 24px; }
  .result-links a {
    display: inline-block; padding: 10px 20px; margin: 4px;
    background: #1e40af; color: white; border-radius: 8px;
    text-decoration: none; font-size: 14px;
  }
  .result-links a:hover { background: #2563eb; }
  .pulse { animation: pulse 2s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
  .hidden { display: none; }
</style>
</head>
<body>
<div class="container">
  <h1>APIScout</h1>
  <p class="subtitle">给我一个 URL，还你一份 OpenAPI spec</p>

  <div class="input-group">
    <input type="text" id="url" placeholder="https://eam.customer.com">
    <button class="btn btn-primary" id="startBtn" onclick="startScan()">开始扫描</button>
    <button class="btn btn-danger hidden" id="stopBtn" onclick="stopScan()">停止录制 → 生成文档</button>
  </div>

  <div class="status-bar">
    <div class="status-phase" id="phase"></div>
    <div class="status-message" id="message">输入目标系统 URL，点击「开始扫描」</div>
    <div class="stats">
      <div class="stat">
        <div class="stat-number" id="captured">0</div>
        <div class="stat-label">请求捕获</div>
      </div>
      <div class="stat">
        <div class="stat-number" id="endpoints">-</div>
        <div class="stat-label">API 端点</div>
      </div>
    </div>
  </div>

  <div id="results" class="result-links hidden"></div>
</div>

<script>
let ws;
function connect() {
  ws = new WebSocket('ws://' + location.host + '/ws');
  ws.onmessage = function(e) {
    const s = JSON.parse(e.data);
    document.getElementById('message').textContent = s.message || '';
    document.getElementById('captured').textContent = s.captured || 0;
    document.getElementById('endpoints').textContent = s.endpoints || '-';

    const phases = {
      login: '\u23f3 等待登录', detect: '\ud83d\udd0d 框架检测',
      explore: '\ud83e\udd16 自动探索', manual: '\ud83d\udc46 手动录制',
      stopping: '\u23f3 正在停止...', analyze: '\ud83d\udcca 分析生成',
      done: '\u2705 完成', error: '\u274c 出错',
    };
    document.getElementById('phase').textContent = phases[s.phase] || '';

    if (s.status === 'scanning') {
      document.getElementById('startBtn').classList.add('hidden');
      document.getElementById('stopBtn').classList.remove('hidden');
      document.getElementById('captured').classList.add('pulse');
    }
    if (s.status === 'done') {
      document.getElementById('stopBtn').classList.add('hidden');
      document.getElementById('startBtn').classList.remove('hidden');
      document.getElementById('captured').classList.remove('pulse');
      var el = document.getElementById('results');
      el.classList.remove('hidden');
      while (el.firstChild) el.removeChild(el.firstChild);
      var links = [
        ['/output/api_docs.html', '\ud83d\udcd6 Swagger UI 文档'],
        ['/output/report.html', '\ud83d\udcca 覆盖率报告'],
        ['/output/draft_spec.yaml', '\ud83d\udcc4 OpenAPI YAML'],
        ['/output/auth_profile.yaml', '\ud83d\udd10 认证档案'],
      ];
      links.forEach(function(l) {
        var a = document.createElement('a');
        a.href = l[0]; a.target = '_blank'; a.textContent = l[1];
        el.appendChild(a);
      });
    }
    if (s.status === 'error') {
      document.getElementById('stopBtn').classList.add('hidden');
      document.getElementById('startBtn').classList.remove('hidden');
      document.getElementById('captured').classList.remove('pulse');
    }
  };
  ws.onclose = function() { setTimeout(connect, 1000); };
}
connect();

function startScan() {
  var url = document.getElementById('url').value.trim();
  if (!url) { alert('请输入 URL'); return; }
  if (!url.startsWith('http')) url = 'https://' + url;
  ws.send(JSON.stringify({action: 'scan', url: url, manual: true}));
}
function stopScan() {
  ws.send(JSON.stringify({action: 'stop'}));
}
</script>
</body>
</html>"""


def start_server(host="0.0.0.0", port=9527):
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("APIScout Web 面板: http://localhost:%d", port)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    start_server()
