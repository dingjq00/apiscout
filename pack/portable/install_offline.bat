@echo off
chcp 65001 >nul
echo ========================================
echo   APIScout 离线安装（无需联网）
echo ========================================
echo.

set BASE=%~dp0
set PYTHON_DIR=%BASE%python
set BROWSERS_DIR=%BASE%browsers\chromium

:: 步骤 1: 解压 Python
if not exist "%PYTHON_DIR%\python.exe" (
    echo [1/4] 解压 Python...
    powershell -Command "Expand-Archive -Path '%BASE%python-embed.zip' -DestinationPath '%PYTHON_DIR%' -Force"
    :: 启用 pip
    for %%f in (%PYTHON_DIR%\python*._pth) do (
        powershell -Command "(Get-Content '%%f') -replace '^#import site','import site' | Set-Content '%%f'"
    )
) else (
    echo [1/4] Python 已存在
)

:: 步骤 2: 安装 pip
if not exist "%PYTHON_DIR%\Scripts\pip.exe" (
    echo [2/4] 安装 pip...
    "%PYTHON_DIR%\python.exe" "%BASE%get-pip.py" --no-index --find-links="%BASE%wheels" 2>nul
    if not exist "%PYTHON_DIR%\Scripts\pip.exe" (
        "%PYTHON_DIR%\python.exe" "%BASE%get-pip.py" 2>nul
    )
) else (
    echo [2/4] pip 已存在
)

:: 步骤 3: 安装依赖（从本地 wheels）
echo [3/4] 安装依赖...
"%PYTHON_DIR%\Scripts\pip.exe" install --no-index --find-links="%BASE%wheels" playwright genson pyyaml jinja2 click fastapi uvicorn 2>nul
if errorlevel 1 (
    echo     本地安装失败，尝试在线安装...
    "%PYTHON_DIR%\Scripts\pip.exe" install playwright genson pyyaml jinja2 click fastapi uvicorn --quiet 2>nul
)

:: 步骤 4: 安装 Chromium
if not exist "%BROWSERS_DIR%" (
    echo [4/4] 解压 Chromium 浏览器...
    mkdir "%BROWSERS_DIR%" 2>nul
    powershell -Command "Expand-Archive -Path '%BASE%chromium-win64.zip' -DestinationPath '%BROWSERS_DIR%' -Force"
) else (
    echo [4/4] Chromium 已存在
)

:: 安装 APIScout
echo      安装 APIScout...
for %%d in ("%BASE%..") do set PROJECT_DIR=%%~fd
"%PYTHON_DIR%\Scripts\pip.exe" install -e "%PROJECT_DIR%" --quiet 2>nul

:: 创建启动脚本
echo @echo off> "%BASE%启动APIScout.bat"
echo chcp 65001 ^>nul>> "%BASE%启动APIScout.bat"
echo set PLAYWRIGHT_BROWSERS_PATH=%%~dp0browsers>> "%BASE%启动APIScout.bat"
echo set PATH=%%~dp0python;%%~dp0python\Scripts;%%PATH%%>> "%BASE%启动APIScout.bat"
echo echo APIScout 启动中...>> "%BASE%启动APIScout.bat"
echo start http://localhost:9527>> "%BASE%启动APIScout.bat"
echo python -m apiscout web>> "%BASE%启动APIScout.bat"
echo pause>> "%BASE%启动APIScout.bat"

echo.
echo ========================================
echo   安装完成!
echo   双击「启动APIScout.bat」即可使用
echo ========================================
pause
