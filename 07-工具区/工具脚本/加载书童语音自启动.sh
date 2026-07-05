#!/bin/bash
# 加载书童语音守护进程到 macOS 开机自启动

PLIST="com.shutong.bookboy.voice"

# 先卸载旧的（如果存在）
launchctl unload ~/Library/LaunchAgents/${PLIST}.plist 2>/dev/null

# 加载新的
launchctl load ~/Library/LaunchAgents/${PLIST}.plist

if [ $? -eq 0 ]; then
    echo "书童语音守护已加载到开机自启动"
    echo "立即启动中..."
    launchctl start ${PLIST}
    echo "已启动。您现在可以喊'书童'试试。"
else
    echo "加载失败，请检查权限或配置"
fi
