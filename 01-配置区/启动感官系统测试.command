#!/bin/bash
# 书童感官系统测试启动器
# 必须在 Terminal / iTerm 中运行，才能获得 Mac 摄像头和麦克风权限

cd "$(dirname "$0")/.."
.venv/bin/python 07-工具区/工具脚本/测试摄像头麦克风.py

# 防止窗口立即关闭
echo "按回车键退出..."
read
