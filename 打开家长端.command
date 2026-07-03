#!/bin/bash
# 伴读书童AI · 一键打开家长端
# 如果服务未运行，自动启动

cd "$(dirname "$0")"

PORT=3876
FAMILY_ID="default_family"
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "127.0.0.1")
URL="http://${LOCAL_IP}:${PORT}/family/${FAMILY_ID}/parent"
ENTRY_URL="http://${LOCAL_IP}:${PORT}/entry"

# 检查服务是否已运行
if lsof -i :$PORT >/dev/null 2>&1; then
    echo "[书童] 服务已在运行"
else
    echo "[书童] 正在启动服务..."
    .venv/bin/python3 本地书童界面.py > 书童运行日志.txt 2>&1 &
    sleep 5
fi

echo "[书童] 正在打开家长端：$URL"
echo "[书童] 家庭访问入口：$ENTRY_URL"
open "$URL"
