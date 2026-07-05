#!/bin/bash
# 伴读书童AI 语音对话守护进程启动脚本

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

# 停止旧的守护进程
pkill -f "语音对话守护.py" 2>/dev/null
sleep 2

# 启动新的守护进程
nohup .venv/bin/python3 07-工具区/工具脚本/语音对话守护.py --speaker master > 05-交付区/临时交付/语音守护.log 2>&1 &

PID=$!
echo "书童语音守护已启动，PID: $PID"
echo "日志文件: $PROJECT_ROOT/05-交付区/临时交付/语音守护.log"
echo "停止方式: pkill -f 语音对话守护.py"
