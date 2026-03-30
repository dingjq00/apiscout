#!/bin/bash
# 构建在线安装压缩包 — 只含源码 + 安装脚本，约 500KB
# 用法: bash pack/build_online_pack.sh

set -e
cd "$(dirname "$0")/.."

PACK_NAME="apiscout-online-install"
TEMP_DIR="/tmp/$PACK_NAME"
OUTPUT="$HOME/Desktop/$PACK_NAME.zip"

echo "构建在线安装包..."

# 清理
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR/apiscout-source"

# 拷贝源码（排除大文件和不必要的）
rsync -a \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='output' \
    --exclude='pack/portable' \
    --exclude='build' \
    --exclude='dist' \
    --exclude='*.egg-info' \
    --exclude='.claude' \
    . "$TEMP_DIR/apiscout-source/"

# 拷贝安装脚本到根目录（方便用户找到）
cp "$TEMP_DIR/apiscout-source/pack/一键安装.bat" "$TEMP_DIR/" 2>/dev/null || true
cp "$TEMP_DIR/apiscout-source/pack/setup_portable.ps1" "$TEMP_DIR/" 2>/dev/null || true

# 压缩
cd /tmp
rm -f "$OUTPUT"
zip -r "$OUTPUT" "$PACK_NAME" -x "*.DS_Store"

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo ""
echo "完成: $OUTPUT ($SIZE)"
echo "发给同事，解压后双击 一键安装.bat 即可"
