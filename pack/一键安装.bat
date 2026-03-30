@echo off
chcp 65001 >nul
title APIScout 在线安装

echo ========================================
echo   APIScout 在线安装
echo   无需预装任何软件，自动下载一切
echo ========================================
echo.

REM 检测 PowerShell
where powershell >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 PowerShell，请手动运行 setup_portable.ps1
    pause
    exit /b 1
)

REM 找到 setup_portable.ps1 的位置
set "SCRIPT_DIR=%~dp0"

REM 优先在当前目录找，其次在 apiscout-source/pack/ 里找
if exist "%SCRIPT_DIR%setup_portable.ps1" (
    set "PS_SCRIPT=%SCRIPT_DIR%setup_portable.ps1"
) else if exist "%SCRIPT_DIR%apiscout-source\pack\setup_portable.ps1" (
    set "PS_SCRIPT=%SCRIPT_DIR%apiscout-source\pack\setup_portable.ps1"
) else (
    echo [错误] 找不到 setup_portable.ps1
    pause
    exit /b 1
)

echo 启动安装程序...
echo.
powershell -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
pause
