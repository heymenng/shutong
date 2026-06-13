"""伴读书童AI - 作息模板引擎

职责：
根据孩子的发育阶段（S0-S6），自动生成每日任务模板。
每个阶段有固定的时间节点和任务类型。

设计原则：
- 符合0-18岁各阶段发育规律
- 覆盖观察/记录/预警/陪伴/引导五大职责
- 包含必须完成的任务和可选任务
- 睡前仪式是核心（30分钟+慢节奏引导）
"""

from typing import List, Dict
from datetime import datetime, timedelta


# ═══════════════════════════════════════════════════════════
# 各阶段每日任务模板
# ═══════════════════════════════════════════════════════════

DAILY_TEMPLATES = {
    "S0": {  # 孕育期
        "name": "孕育期",
        "tasks": [
            {"id": "S0_morning", "name": "早安问候", "time": "08:00", "type": "陪伴", "duration": 5, "must": True},
            {"id": "S0_movement", "name": "提醒准妈妈运动", "time": "10:00", "type": "观察", "duration": 5, "must": True},
            {"id": "S0_nutrition", "name": "饮食记录提醒", "time": "12:00", "type": "记录", "duration": 3, "must": True},
            {"id": "S0_emotion", "name": "情绪陪伴", "time": "15:00", "type": "陪伴", "duration": 10, "must": True},
            {"id": "S0_relax", "name": "放松音乐", "time": "20:00", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S0_sleep", "name": "睡前仪式", "time": "21:30", "type": "睡前", "duration": 20, "must": True},
        ]
    },
    
    "S1": {  # 襁褓期 0-1岁
        "name": "襁褓期",
        "tasks": [
            {"id": "S1_wake", "name": "早安唤醒", "time": "07:00", "type": "陪伴", "duration": 10, "must": True},
            {"id": "S1_feed", "name": "喂养记录", "time": "09:00", "type": "记录", "duration": 3, "must": True},
            {"id": "S1_tummy", "name": "提醒俯卧练习", "time": "10:00", "type": "观察", "duration": 5, "must": True},
            {"id": "S1_nap", "name": "午睡陪伴", "time": "13:00", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S1_massage", "name": "抚触提醒", "time": "16:00", "type": "陪伴", "duration": 10, "must": True},
            {"id": "S1_bath", "name": "洗澡准备", "time": "19:00", "type": "陪伴", "duration": 10, "must": True},
            {"id": "S1_bedtime", "name": "睡前仪式（抚触+音乐）", "time": "20:00", "type": "睡前", "duration": 30, "must": True},
        ]
    },
    
    "S2": {  # 幼童期 1-3岁
        "name": "幼童期",
        "tasks": [
            {"id": "S2_wake", "name": "早安唤醒", "time": "07:30", "type": "陪伴", "duration": 10, "must": True},
            {"id": "S2_breakfast", "name": "早餐陪伴", "time": "08:00", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S2_outdoor", "name": "户外时间提醒", "time": "10:00", "type": "观察", "duration": 5, "must": True},
            {"id": "S2_lunch", "name": "午餐陪伴", "time": "12:00", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S2_nap", "name": "午睡陪伴（故事）", "time": "13:30", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S2_play", "name": "游戏陪伴", "time": "15:30", "type": "陪伴", "duration": 20, "must": True},
            {"id": "S2_dinner", "name": "晚餐陪伴", "time": "18:00", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S2_bath", "name": "洗澡时间", "time": "19:30", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S2_bedtime", "name": "睡前仪式（故事+音乐+引导）", "time": "20:30", "type": "睡前", "duration": 30, "must": True},
        ]
    },
    
    "S3": {  # 蒙学期 3-6岁
        "name": "蒙学期",
        "tasks": [
            {"id": "S3_wake", "name": "早安唤醒", "time": "07:30", "type": "陪伴", "duration": 10, "must": True},
            {"id": "S3_morning", "name": "晨起检查（穿衣/书包）", "time": "08:00", "type": "观察", "duration": 5, "must": True},
            {"id": "S3_poem", "name": "晨读（古诗/经典）", "time": "08:30", "type": "文化传承", "duration": 10, "must": True},
            {"id": "S3_outdoor", "name": "户外活动提醒", "time": "10:00", "type": "观察", "duration": 5, "must": True},
            {"id": "S3_lunch", "name": "午餐陪伴", "time": "12:00", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S3_nap", "name": "午睡引导", "time": "13:30", "type": "陪伴", "duration": 10, "must": False},  # 可选
            {"id": "S3_homework", "name": "学习陪伴", "time": "15:30", "type": "引导", "duration": 30, "must": True},
            {"id": "S3_play", "name": "自由游戏", "time": "16:30", "type": "陪伴", "duration": 30, "must": True},
            {"id": "S3_dinner", "name": "晚餐陪伴", "time": "18:00", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S3_family", "name": "家庭互动", "time": "19:30", "type": "陪伴", "duration": 20, "must": True},
            {"id": "S3_bedtime", "name": "睡前仪式（冥想+音乐+引导）", "time": "20:30", "type": "睡前", "duration": 30, "must": True},
        ]
    },
    
    "S4": {  # 小学期 6-12岁
        "name": "小学期",
        "tasks": [
            {"id": "S4_wake", "name": "早安唤醒", "time": "07:00", "type": "陪伴", "duration": 10, "must": True},
            {"id": "S4_morning", "name": "晨起检查", "time": "07:30", "type": "观察", "duration": 5, "must": True},
            {"id": "S4_poem", "name": "晨读（古诗/经典）", "time": "07:45", "type": "文化传承", "duration": 10, "must": True},
            {"id": "S4_school", "name": "上学前鼓励", "time": "08:00", "type": "陪伴", "duration": 5, "must": True},
            {"id": "S4_return", "name": "放学问候", "time": "16:00", "type": "陪伴", "duration": 10, "must": True},
            {"id": "S4_homework", "name": "作业陪伴", "time": "16:30", "type": "引导", "duration": 60, "must": True},
            {"id": "S4_outdoor", "name": "户外运动提醒", "time": "17:30", "type": "观察", "duration": 5, "must": True},
            {"id": "S4_dinner", "name": "晚餐陪伴", "time": "18:30", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S4_review", "name": "今日回顾", "time": "19:30", "type": "引导", "duration": 10, "must": True},
            {"id": "S4_bedtime", "name": "睡前仪式（冥想+音乐+引导）", "time": "21:00", "type": "睡前", "duration": 30, "must": True},
        ]
    },
    
    "S5": {  # 少学期（初中）12-15岁
        "name": "少学期（初中）",
        "tasks": [
            {"id": "S5_wake", "name": "早安唤醒", "time": "06:45", "type": "陪伴", "duration": 5, "must": True},
            {"id": "S5_check", "name": "晨起状态检查", "time": "07:00", "type": "观察", "duration": 3, "must": True},
            {"id": "S5_school", "name": "上学前鼓励", "time": "07:30", "type": "陪伴", "duration": 5, "must": True},
            {"id": "S5_return", "name": "放学问候", "time": "17:00", "type": "陪伴", "duration": 10, "must": True},
            {"id": "S5_emotion", "name": "情绪检查", "time": "17:30", "type": "观察", "duration": 10, "must": True},
            {"id": "S5_homework", "name": "作业陪伴", "time": "18:00", "type": "引导", "duration": 60, "must": True},
            {"id": "S5_sport", "name": "运动提醒", "time": "19:30", "type": "观察", "duration": 5, "must": True},
            {"id": "S5_dinner", "name": "晚餐陪伴", "time": "20:00", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S5_bedtime", "name": "睡前仪式（排毒冥想+音乐+引导）", "time": "21:30", "type": "睡前", "duration": 30, "must": True},
        ]
    },
    
    "S6": {  # 少学期（高中）15-18岁
        "name": "少学期（高中）",
        "tasks": [
            {"id": "S6_wake", "name": "早安唤醒", "time": "06:30", "type": "陪伴", "duration": 5, "must": True},
            {"id": "S6_check", "name": "晨起状态检查", "time": "06:45", "type": "观察", "duration": 3, "must": True},
            {"id": "S6_morning", "name": "晨间鼓励", "time": "07:00", "type": "陪伴", "duration": 5, "must": True},
            {"id": "S6_return", "name": "放学问候", "time": "18:00", "type": "陪伴", "duration": 10, "must": True},
            {"id": "S6_emotion", "name": "情绪检查", "time": "18:30", "type": "观察", "duration": 10, "must": True},
            {"id": "S6_homework", "name": "学习陪伴", "time": "19:00", "type": "引导", "duration": 90, "must": True},
            {"id": "S6_sport", "name": "运动提醒", "time": "20:30", "type": "观察", "duration": 5, "must": True},
            {"id": "S6_dinner", "name": "晚餐陪伴", "time": "21:00", "type": "陪伴", "duration": 15, "must": True},
            {"id": "S6_bedtime", "name": "睡前仪式（排毒冥想+音乐+引导）", "time": "22:00", "type": "睡前", "duration": 30, "must": True},
        ]
    },
}


# ═══════════════════════════════════════════════════════════
# 作息模板引擎
# ═══════════════════════════════════════════════════════════

class ScheduleTemplateEngine:
    """
    作息模板引擎
    
    根据孩子的阶段和个人偏好，生成个性化每日任务清单。
    """
    
    def __init__(self):
        self.templates = DAILY_TEMPLATES
    
    def generate_daily_tasks(self, child_profile) -> List[Dict]:
        """
        为指定孩子生成今日任务清单
        
        流程：
        1. 获取阶段模板
        2. 应用个人作息偏好（起床/睡觉时间偏移）
        3. 标记混龄共修机会
        4. 返回完整任务清单
        """
        stage = child_profile.stage
        template = self.templates.get(stage, self.templates["S4"])
        
        tasks = []
        for task in template["tasks"]:
            # 复制任务
            personalized_task = task.copy()
            
            # 应用作息偏好偏移
            personalized_task["time"] = self._apply_time_offset(
                task["time"],
                child_profile.schedule_prefs.get("wake_time", "07:00"),
                stage
            )
            
            # 如果是睡前仪式，使用个人偏好时长
            if task["type"] == "睡前":
                duration = child_profile.schedule_prefs.get("bedtime_ritual_duration", 30)
                personalized_task["duration"] = duration
            
            tasks.append(personalized_task)
        
        return tasks
    
    def _apply_time_offset(self, base_time: str, wake_time: str, stage: str) -> str:
        """
        根据孩子实际起床时间，对模板时间进行微调
        
        例如：模板起床07:00，孩子实际07:30起床，则所有时间延后30分钟
        """
        base_dt = datetime.strptime(base_time, "%H:%M")
        
        # 计算偏移量（基于起床时间）
        template_wake = {"S0": "08:00", "S1": "07:00", "S2": "07:30", 
                        "S3": "07:30", "S4": "07:00", "S5": "06:45", "S6": "06:30"}
        template_wake_time = template_wake.get(stage, "07:00")
        
        template_wake_dt = datetime.strptime(template_wake_time, "%H:%M")
        actual_wake_dt = datetime.strptime(wake_time, "%H:%M")
        
        offset = actual_wake_dt - template_wake_dt
        
        # 应用偏移
        adjusted = base_dt + offset
        return adjusted.strftime("%H:%M")
    
    def get_bedtime_task(self, child_profile) -> Dict:
        """获取指定孩子的睡前任务"""
        tasks = self.generate_daily_tasks(child_profile)
        for task in tasks:
            if task["type"] == "睡前":
                return task
        return None
    
    def get_next_tasks(self, child_profile, current_time=None, count=3) -> List[Dict]:
        """获取接下来N个任务"""
        if current_time is None:
            current_time = datetime.now().strftime("%H:%M")
        
        tasks = self.generate_daily_tasks(child_profile)
        current_dt = datetime.strptime(current_time, "%H:%M")
        
        # 找到当前时间之后的任务
        future_tasks = []
        for task in tasks:
            task_dt = datetime.strptime(task["time"], "%H:%M")
            if task_dt >= current_dt:
                future_tasks.append(task)
        
        return future_tasks[:count]
    
    def get_task_summary(self, child_profile) -> Dict:
        """获取今日任务统计"""
        tasks = self.generate_daily_tasks(child_profile)
        
        total = len(tasks)
        must_do = len([t for t in tasks if t.get("must", False)])
        optional = total - must_do
        bedtime_duration = sum(t["duration"] for t in tasks if t["type"] == "睡前")
        total_duration = sum(t["duration"] for t in tasks)
        
        return {
            "total_tasks": total,
            "must_do": must_do,
            "optional": optional,
            "bedtime_duration": bedtime_duration,
            "total_duration": total_duration,
            "stage_name": self.templates.get(child_profile.stage, {}).get("name", "未知"),
        }
    
    def get_all_stages_summary(self):
        """获取所有阶段的任务概览"""
        summary = {}
        for stage, template in self.templates.items():
            tasks = template["tasks"]
            summary[stage] = {
                "name": template["name"],
                "task_count": len(tasks),
                "must_count": len([t for t in tasks if t.get("must", False)]),
                "bedtime_duration": sum(t["duration"] for t in tasks if t["type"] == "睡前"),
            }
        return summary
