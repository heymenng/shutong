"""书童语音调度轻量启动脚本

用法：
    .venv/bin/python 工具脚本/启动语音调度_轻量.py

说明：
    - 只加载语音调度必需的模块，不加载 Vosk 语音识别、摄像头等重型模块；
    - 启动更快，适合专门用于"到点语音提醒"的场景；
    - 到了设定时间点，自动用语音提醒孩子该做什么。
"""

import sys
import time
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from 书童程序.核心.多用户管理 import ChildProfileManager
from 书童程序.核心.作息模板 import ScheduleTemplateEngine
from 书童程序.核心.时间调度 import TimeScheduler
from 书童程序.核心.睡前引导 import BedtimeGuide
from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.核心.每日工作流 import DailyWorkflow
from 书童程序.配置 import CONFIG


class LightweightBookBoyForVoiceSchedule:
    """轻量版书童：只保留语音调度所需的能力"""
    
    def __init__(self):
        self.voice = VoiceEngine()
        self.soul_awakened = True  # 轻量版跳过灵魂觉醒
        self.profile_manager = ChildProfileManager(CONFIG["journal_dir"])
        
        # 扫描档案区加载真实档案
        archive_dir = CONFIG.get("档案区_dir", "")
        if archive_dir:
            loaded = self.profile_manager.scan_archive_zone(archive_dir)
            print(f"[系统] 档案区已加载 {loaded} 个真实孩子")
        
        self._scheduler = None
        self._daily_workflow = DailyWorkflow(self, CONFIG["journal_dir"])
    
    def get_family_report(self):
        """兼容 DailyWorkflow 的接口"""
        return {
            "green_count": 0, "yellow_count": 0, "orange_count": 0, "red_count": 0,
            "top_concerns": []
        }
    
    def get_cultivation_status(self):
        """兼容 DailyWorkflow 的接口"""
        return {
            "soul_mode": CONFIG.get("soul_mode", "balanced"),
            "self_reflection_enabled": CONFIG.get("self_reflection_enabled", True),
            "children_managed": len(self.profile_manager.get_all_children()),
            "engines_loaded": {"speech": True}
        }
    
    def _awaken_soul(self):
        """轻量版灵魂觉醒：简单诵念"""
        print("  [灵魂觉醒] 伴读书童，我陪你长大。")


def main():
    print("=" * 60)
    print("【书童语音调度系统 · 轻量版启动】")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 初始化轻量系统
    print("\n[1/4] 初始化轻量书童系统...")
    bookboy = LightweightBookBoyForVoiceSchedule()
    
    # 检查加载了哪些孩子
    children = bookboy.profile_manager.get_all_children()
    print(f"\n[2/4] 已加载 {len(children)} 个孩子档案：")
    for child in children:
        print(f"  ✅ {child.name} | {child.get_stage_name()} | {child.get_age_display()}")
    
    # 手动创建并启动调度器
    print("\n[3/4] 创建时间调度引擎...")
    scheduler = TimeScheduler(
        profile_manager=bookboy.profile_manager,
        template_engine=ScheduleTemplateEngine(),
        bedtime_guide=BedtimeGuide(),
        journal_dir=CONFIG["journal_dir"],
        task_executor=bookboy._daily_workflow._execute_scheduled_task_callback,
    )
    scheduler.generate_today_tasks()
    scheduler.start()
    bookboy._scheduler = scheduler
    
    print("\n[4/4] 语音调度已启动")
    print("=" * 60)
    print("✅ 书童会在到点时主动开口提醒")
    print("   按 Ctrl+C 可以停止")
    print("=" * 60)
    
    # 保持运行
    try:
        while True:
            time.sleep(60)
            now = datetime.now().strftime('%H:%M')
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
