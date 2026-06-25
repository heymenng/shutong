#!/usr/bin/env python3
"""
伴读书童AI - 快速桥接脚本

简化外部AI桥接器的调用方式。

用法：
    python3 工具脚本/快速桥接.py set master                 # 设置当前身份为师父
    python3 工具脚本/快速桥接.py set child 小橙子            # 设置当前身份为小橙子
    python3 工具脚本/快速桥接.py who                         # 查看当前身份
    python3 工具脚本/快速桥接.py clear                       # 清除当前身份
    python3 工具脚本/快速桥接.py chat "你好" "你好呀"          # 处理对话（使用当前身份）
    python3 工具脚本/快速桥接.py child 小橙子 "你好" "你好呀"  # 处理孩子对话
    python3 工具脚本/快速桥接.py master "你好" "你好呀"        # 处理师父对话
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
BRIDGE_CMD = ["python3", "-m", "书童程序.核心.外部AI桥接器"]


def run_bridge(args):
    """运行桥接器命令"""
    cmd = BRIDGE_CMD + args + ["--no_voice"]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=False, text=True)
    return result.returncode


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    action = sys.argv[1]
    
    if action == "set":
        # 设置身份
        if len(sys.argv) < 3:
            print("用法: set child|master|parent [child_id]")
            return
        speaker = sys.argv[2]
        child_id = sys.argv[3] if len(sys.argv) > 3 else "default"
        run_bridge(["--set_speaker", speaker, "--child_id", child_id])
    
    elif action == "who":
        # 查看当前身份
        run_bridge(["--check_identity"])
    
    elif action == "clear":
        # 清除身份
        run_bridge(["--clear_speaker"])
    
    elif action == "chat":
        # 使用当前身份处理对话
        if len(sys.argv) < 4:
            print("用法: chat \"用户输入\" \"书童回复\"")
            return
        user_input = sys.argv[2]
        ai_response = sys.argv[3]
        run_bridge(["--input", user_input, "--response", ai_response, "--speaker", "auto"])
    
    elif action == "child":
        # 强制作为孩子对话
        if len(sys.argv) < 5:
            print("用法: child  child_id \"用户输入\" \"书童回复\"")
            return
        child_id = sys.argv[2]
        user_input = sys.argv[3]
        ai_response = sys.argv[4]
        run_bridge([
            "--input", user_input,
            "--response", ai_response,
            "--speaker", "child",
            "--child_id", child_id
        ])
    
    elif action == "master":
        # 强制作为师父对话
        if len(sys.argv) < 4:
            print("用法: master \"用户输入\" \"书童回复\"")
            return
        user_input = sys.argv[2]
        ai_response = sys.argv[3]
        run_bridge([
            "--input", user_input,
            "--response", ai_response,
            "--speaker", "master"
        ])
    
    elif action == "parent":
        # 强制作为家长对话
        if len(sys.argv) < 5:
            print("用法: parent child_id \"用户输入\" \"书童回复\"")
            return
        child_id = sys.argv[2]
        user_input = sys.argv[3]
        ai_response = sys.argv[4]
        run_bridge([
            "--input", user_input,
            "--response", ai_response,
            "--speaker", "parent",
            "--child_id", child_id
        ])
    
    else:
        print(f"未知动作: {action}")
        print(__doc__)


if __name__ == "__main__":
    main()
