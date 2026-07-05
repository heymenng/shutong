"""书童语音提醒测试脚本

用法：
    .venv/bin/python 07-工具区/工具脚本/语音提醒测试.py

功能：
    1. 初始化语音引擎
    2. 为小橙子（S3/8岁）和嘟嘟（S5/13岁）生成今日关键时间点的提醒
    3. 立即用语音播报，验证主动提醒机制可用
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.核心.多用户管理 import ChildProfile
from 书童程序.核心.作息模板 import ScheduleTemplateEngine
from 书童程序.核心.每日工作流 import DailyWorkflow


def create_demo_children():
    """创建测试用的小橙子和嘟嘟档案"""
    
    # 小橙子：8岁，小学二年级，按系统阶段应为 S4
    xiaochengzi = ChildProfile(
        child_id="xiaochengzi",
        name="小橙子",
        birth_date="2017-09-01",  # 约8岁
        stage="S4"
    )
    xiaochengzi.schedule_prefs.update({
        "wake_time": "07:00",
        "sleep_time": "21:30",
        "homework_time": "19:00",
    })
    
    # 嘟嘟：13岁，初中二年级，S5
    dudu = ChildProfile(
        child_id="dudu",
        name="嘟嘟",
        birth_date="2012-07-12",  # 约13岁
        stage="S5"
    )
    dudu.schedule_prefs.update({
        "wake_time": "06:45",
        "sleep_time": "21:30",
        "homework_time": "18:00",
    })
    
    return [xiaochengzi, dudu]


def generate_reminder_messages(children):
    """为每个孩子生成今日关键提醒消息"""
    template_engine = ScheduleTemplateEngine()
    messages = []
    
    for child in children:
        tasks = template_engine.generate_daily_tasks(child)
        
        # 只选取几个关键任务做演示
        key_task_ids = {
            "S4": ["S4_wake", "S4_school", "S4_homework", "S4_bedtime"],
            "S5": ["S5_wake", "S5_school", "S5_homework", "S5_bedtime"],
        }
        
        selected_ids = key_task_ids.get(child.stage, [])
        selected_tasks = [t for t in tasks if t["id"] in selected_ids]
        
        # 按时间排序
        selected_tasks.sort(key=lambda x: x["time"])
        
        # 用每日工作流的内容生成器
        workflow = DailyWorkflow(bookboy_system=None, journal_dir=project_root / "03-引擎区" / "书童程序" / "数据" / "修行记录")
        
        for task in selected_tasks:
            # 构造一个简化版 task 对象
            class SimpleTask:
                def __init__(self, task_dict):
                    self.task_id = task_dict["id"]
                    self.name = task_dict["name"]
                    self.scheduled_time = task_dict["time"]
                    self.task_type = task_dict["type"]
                    self.duration = task_dict["duration"]
                    self.child_id = child.child_id
                    self.must = task_dict.get("must", True)
                    self.status = "pending"
                    self.triggered_at = None
                    self.completed_at = None
                    self.confirmed_by = None
                    self.notes = ""
                    self.reminders = []
            
            simple_task = SimpleTask(task)
            content = workflow._generate_task_content(simple_task, child)
            messages.append({
                "child": child.name,
                "time": task["time"],
                "task": task["name"],
                "content": content,
            })
    
    return messages


def main():
    print("=" * 60)
    print("【书童语音提醒测试】")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 初始化语音引擎
    print("\n[1/3] 初始化语音引擎...")
    voice = VoiceEngine()
    
    if not voice.backend:
        print("❌ 语音引擎初始化失败，请检查配置和依赖")
        return 1
    
    print(f"✅ 语音引擎就绪，后端：{voice.backend}")
    
    # 创建孩子档案
    print("\n[2/3] 加载小橙子和嘟嘟的档案...")
    children = create_demo_children()
    for child in children:
        print(f"  ✅ {child.name} | {child.get_stage_name()} | 起床 {child.schedule_prefs['wake_time']}")
    
    # 生成提醒消息
    print("\n[3/3] 生成并播报今日关键提醒...")
    messages = generate_reminder_messages(children)
    
    for i, msg in enumerate(messages, 1):
        print(f"\n  提醒 {i}/{len(messages)}")
        print(f"  孩子：{msg['child']}")
        print(f"  时间：{msg['time']}")
        print(f"  任务：{msg['task']}")
        print(f"  内容：{msg['content']}")
        
        # 语音播报
        speak_text = f"{msg['time']}，{msg['content']}"
        voice.speak(speak_text)
    
    print("\n" + "=" * 60)
    print("【语音提醒测试完成】")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
