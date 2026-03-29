@echo off
chcp 65001 >nul
echo APIScout Web 面板启动中...
echo 浏览器打开 http://localhost:9527
echo.
start http://localhost:9527
apiscout web
pause
