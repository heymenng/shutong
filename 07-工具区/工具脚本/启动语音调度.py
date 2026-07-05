"""书童语音调度启动脚本

用法：
    .venv/bin/python 07-工具区/工具脚本/启动语音调度.py

功能：
    1. 加载档案区里的真实孩子档案（小橙子、嘟嘟等）
    2. 启动时间调度引擎
    3. 到了设定时间点，自动用语音提醒孩子该做什么
    4. 保持后台运行，直到按 Ctrl+C 停止

说明：
    - 这是书童的"主动触发机制"。
    - 书童不是被动等待孩子来找，而是到了时间就主动开口。
    - 提醒词按"文明知识经纬度图"生成，有温度、有坐标。
"""

import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.核心.系统核心 import BookBoySystem
from 书童程序.配置 import CONFIG


def main():
    print("=" * 60)
    print("【书童语音调度系统启动】")
    print(f"时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 初始化完整系统
    print("\n[1/3] 初始化书童系统...")
    bookboy = BookBoySystem(session_id="语音调度", fast_mode=False)
    
    # 检查加载了哪些孩子
    children = bookboy.profile_manager.get_all_children()
    print(f"\n[2/3] 已加载 {len(children)} 个孩子档案：")
    for child in children:
        print(f"  ✅ {child.name} | {child.get_stage_name()} | {child.get_age_display()}")
    
    # 启动每日工作流（含调度引擎）
    print("\n[3/3] 启动时间调度引擎...")
    bookboy._daily_workflow.startup_routine()
    
    scheduler = bookboy._scheduler
    if scheduler and scheduler.running:
        print("\n✅ 语音调度已启动，书童会在到点时主动开口提醒")
        print("   按 Ctrl+C 可以停止")
    else:
        print("\n❌ 调度引擎启动失败")
        return 1
    
    # 保持运行
    try:
        while True:
            time.sleep(60)
            # 每分钟打印一次心跳和接下来要执行的任务
            now = __import__('datetime').datetime.now().strftime('%H:%M')
            print(f"\n[心跳 {now}] 调度运行中...")
            for child in children:
                status = scheduler.get_child_today_status(child.child_id)
                upcoming = status.get("upcoming_tasks", [])
                if upcoming:
                    next_tasks = " | ".join([f"{t['time']} {t['name']}" for t in upcoming[:2]])
                    print(f"  {child.name} 接下来: {next_tasks}")
    except KeyboardInterrupt:
        print("\n\n正在停止调度引擎...")
        scheduler.stop()
        print("✅ 已停止")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
