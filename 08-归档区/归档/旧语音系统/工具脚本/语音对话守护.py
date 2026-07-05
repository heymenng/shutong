#!/usr/bin/env python3
"""伴读书童AI - 语音对话守护进程

用途：
让书童在后台常驻运行，监听唤醒词，听到后进入语音对话模式。

启动方式：
    python3 工具脚本/语音对话守护.py
    python3 工具脚本/语音对话守护.py --speaker master

后台运行方式：
    nohup python3 工具脚本/语音对话守护.py > 临时交付/语音守护.log 2>&1 &

停止方式：
    pkill -f 语音对话守护.py
"""

import argparse
import asyncio
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from 书童程序.配置 import CONFIG

# 导入语音对话模式（工具脚本目录不是包，需要动态加载）
sys.path.insert(0, str(project_root / "工具脚本"))
from 语音对话模式 import VoiceDialogue


def log(message):
    """记录守护日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    
    log_dir = project_root / "临时交付"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "语音守护.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")


async def main_loop(speaker="auto", wake_cycles=1000, restart_delay=5):
    """主循环：崩溃后自动重启"""
    restart_count = 0
    
    while restart_count < wake_cycles:
        restart_count += 1
        log(f"启动第 {restart_count} 次守护实例...")
        
        try:
            dialogue = VoiceDialogue(
                speaker=speaker,
                max_rounds=20,
                silence_seconds=2.0,
                max_record_seconds=30,
            )
            
            # 一个实例内循环监听 100 次唤醒，期间 Whisper 模型只加载一次
            await dialogue.run_with_wakeup(wake_cycles=100)
            
        except KeyboardInterrupt:
            log("收到退出信号，守护进程结束")
            break
        except Exception as e:
            log(f"运行异常: {e}")
            log(traceback.format_exc())
            log(f"{restart_delay} 秒后重启...")
            time.sleep(restart_delay)


def main():
    parser = argparse.ArgumentParser(description="伴读书童AI 语音对话守护进程")
    parser.add_argument("--speaker", choices=["master", "child", "parent", "auto"],
                        default="master", help="默认说话者身份")
    parser.add_argument("--wake-cycles", type=int, default=1000,
                        help="最大唤醒周期数")
    parser.add_argument("--restart-delay", type=int, default=5,
                        help="崩溃后重启延迟（秒）")
    
    args = parser.parse_args()
    
    log("=" * 60)
    log("伴读书童AI 语音对话守护进程启动")
    log(f"默认说话对象: {args.speaker}")
    log("=" * 60)
    
    try:
        asyncio.run(main_loop(
            speaker=args.speaker,
            wake_cycles=args.wake_cycles,
            restart_delay=args.restart_delay,
        ))
    except KeyboardInterrupt:
        log("守护进程被手动终止")


if __name__ == "__main__":
    main()
