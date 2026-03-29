#!/bin/bash
echo "========================================"
echo "  APIScout 一键安装（Mac/Linux）"
echo "========================================"
echo

pip install playwright genson pyyaml jinja2 click fastapi uvicorn
playwright install chromium
pip install -e .

echo
echo "========================================"
echo "  安装完成！"
echo "  启动: apiscout web"
echo "  打开: http://localhost:9527"
echo "========================================"
