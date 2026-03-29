@echo off
chcp 65001 >nul
echo ========================================
echo   APIScout 一键安装（Windows）
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.11+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/3] 安装依赖...
pip install playwright genson pyyaml jinja2 click fastapi uvicorn --quiet

echo [2/3] 安装浏览器引擎...
playwright install chromium

echo [3/3] 安装 APIScout...
pip install -e . --quiet

echo.
echo ========================================
echo   安装完成！
echo   启动命令: apiscout web
echo   然后打开: http://localhost:9527
echo ========================================
pause
