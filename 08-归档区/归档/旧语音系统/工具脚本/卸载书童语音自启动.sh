#!/bin/bash
# 卸载书童语音守护进程的开机自启动

PLIST="com.shutong.bookboy.voice"

launchctl unload ~/Library/LaunchAgents/${PLIST}.plist 2>/dev/null

if [ $? -eq 0 ]; then
    echo "书童语音守护已从开机自启动中移除"
else
    echo "卸载命令已执行（可能原本就没有加载）"
fi

# 同时停止手动启动的守护进程
pkill -f "语音对话守护.py" 2>/dev/null
echo "已停止运行中的守护进程"
