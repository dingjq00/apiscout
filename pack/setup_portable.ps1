# APIScout 便携安装（无需预装 Python）
# 右键 → 使用 PowerShell 运行
# 或: powershell -ExecutionPolicy Bypass -File setup_portable.ps1

$ErrorActionPreference = "Stop"
$PYTHON_VERSION = "3.11.9"
$PYTHON_URL = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-embed-amd64.zip"
$PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
$BASE_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON_DIR = "$BASE_DIR\python"
$PYTHON_EXE = "$PYTHON_DIR\python.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  APIScout 便携安装" -ForegroundColor Cyan
Write-Host "  无需预装任何软件" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 步骤 1: 下载 Python 嵌入式版本
if (!(Test-Path $PYTHON_EXE)) {
    Write-Host "[1/5] 下载 Python $PYTHON_VERSION ..." -ForegroundColor Yellow
    $zipPath = "$BASE_DIR\python_embed.zip"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $PYTHON_URL -OutFile $zipPath -UseBasicParsing

    Write-Host "       解压中..." -ForegroundColor Gray
    Expand-Archive -Path $zipPath -DestinationPath $PYTHON_DIR -Force
    Remove-Item $zipPath

    # 启用 pip 支持（修改 python311._pth 文件）
    $pthFile = Get-ChildItem "$PYTHON_DIR\python*._pth" | Select-Object -First 1
    if ($pthFile) {
        $content = Get-Content $pthFile.FullName
        $content = $content -replace "^#import site", "import site"
        Set-Content $pthFile.FullName $content
    }
} else {
    Write-Host "[1/5] Python 已存在，跳过下载" -ForegroundColor Green
}

# 步骤 2: 安装 pip
if (!(Test-Path "$PYTHON_DIR\Scripts\pip.exe")) {
    Write-Host "[2/5] 安装 pip ..." -ForegroundColor Yellow
    $pipPy = "$BASE_DIR\get-pip.py"
    Invoke-WebRequest -Uri $PIP_URL -OutFile $pipPy -UseBasicParsing
    & $PYTHON_EXE $pipPy --no-warn-script-location 2>$null
    Remove-Item $pipPy -ErrorAction SilentlyContinue
} else {
    Write-Host "[2/5] pip 已存在，跳过" -ForegroundColor Green
}

$PIP_EXE = "$PYTHON_DIR\Scripts\pip.exe"

# 步骤 3: 安装依赖
Write-Host "[3/5] 安装 Python 依赖 ..." -ForegroundColor Yellow
& $PIP_EXE install playwright genson pyyaml jinja2 click fastapi uvicorn --quiet --no-warn-script-location 2>$null

# 步骤 4: 安装 Chromium
Write-Host "[4/5] 安装 Chromium 浏览器引擎 ..." -ForegroundColor Yellow
$env:PLAYWRIGHT_BROWSERS_PATH = "$BASE_DIR\browsers"
& $PYTHON_EXE -m playwright install chromium 2>$null

# 步骤 5: 安装 APIScout
Write-Host "[5/5] 安装 APIScout ..." -ForegroundColor Yellow
$PROJECT_DIR = Split-Path -Parent $BASE_DIR
& $PIP_EXE install -e $PROJECT_DIR --quiet --no-warn-script-location 2>$null

# 创建启动脚本
$startScript = @"
@echo off
chcp 65001 >nul
set PLAYWRIGHT_BROWSERS_PATH=%~dp0browsers
set PATH=%~dp0python;%~dp0python\Scripts;%PATH%
echo APIScout Web 启动中...
start http://localhost:9527
python -m apiscout web
pause
"@
Set-Content "$BASE_DIR\启动APIScout.bat" $startScript -Encoding Default

# 创建 CLI 启动脚本
$cliScript = @"
@echo off
chcp 65001 >nul
set PLAYWRIGHT_BROWSERS_PATH=%~dp0browsers
set PATH=%~dp0python;%~dp0python\Scripts;%PATH%
echo APIScout CLI
echo.
echo 用法:
echo   apiscout scan URL              自动+手动扫描
echo   apiscout scan URL --manual     纯手动扫描
echo   apiscout web                   Web 面板
echo   apiscout analyze FILE          分析数据
echo.
cmd /k
"@
Set-Content "$BASE_DIR\APIScout命令行.bat" $cliScript -Encoding Default

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  安装完成!" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host "  双击 启动APIScout.bat 打开 Web 面板" -ForegroundColor Green
Write-Host "  双击 APIScout命令行.bat 使用命令行" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
pause
