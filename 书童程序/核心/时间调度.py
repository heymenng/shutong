"""伴读书童AI - 时间调度引擎（核心中的核心）

职责：
这是书童的"心脏"——保证每天所有任务按时触发、按时执行。

核心能力：
1. 维护每个孩子的任务队列
2. 定时扫描，到时间自动触发
3. 任务完成确认（孩子回应/家长确认/超时判断）
4. 未完成任务自动提醒（先提醒孩子→再提醒家长）
5. 生成每日工作报告

设计原则：
- 不丢任务：每个任务必须有结果（完成/超时/跳过）
- 及时提醒：到点前5分钟预提醒，到点时正式触发
-  Escalation：孩子无回应→提醒家长→记录异常
- 闭环追踪：任务开始→执行→确认→记录
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Timer, Thread, Lock
from typing import Dict, List, Optional


class TaskStatus:
    """任务状态常量"""
    PENDING = "pending"          # 待执行
    REMINDED = "reminded"        # 已预提醒
    TRIGGERED = "triggered"      # 已触发
    IN_PROGRESS = "in_progress"  # 执行中
    COMPLETED = "completed"      # 已完成
    TIMEOUT = "timeout"          # 超时未完成
    SKIPPED = "skipped"          # 跳过


class ScheduledTask:
    """
    单个调度任务
    
    包含任务的所有状态和执行历史。
    """
    
    def __init__(self, task_id, name, scheduled_time, task_type, duration, 
                 child_id, must=True, metadata=None):
        self.task_id = task_id
        self.name = name
        self.scheduled_time = scheduled_time  # HH:MM
        self.task_type = task_type  # 陪伴/观察/记录/睡前/引导/文化传承
        self.duration = duration  # 分钟
        self.child_id = child_id
        self.must = must  # 是否必须完成
        
        self.status = TaskStatus.PENDING
        self.triggered_at = None
        self.completed_at = None
        self.confirmed_by = None  # child/parent/system
        self.notes = ""  # 执行备注
        self.metadata = metadata or {}
        
        # 提醒历史
        self.reminders = []  # [{"time": "", "type": "pre|formal|escalation", "to": "child|parent"}]
    
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "name": self.name,
            "scheduled_time": self.scheduled_time,
            "task_type": self.task_type,
            "duration": self.duration,
            "child_id": self.child_id,
            "must": self.must,
            "status": self.status,
            "triggered_at": self.triggered_at,
            "completed_at": self.completed_at,
            "confirmed_by": self.confirmed_by,
            "notes": self.notes,
            "reminders": self.reminders,
        }
    
    @classmethod
    def from_dict(cls, data):
        task = cls(
            data["task_id"], data["name"], data["scheduled_time"],
            data["task_type"], data["duration"], data["child_id"], data.get("must", True),
        )
        task.status = data.get("status", TaskStatus.PENDING)
        task.triggered_at = data.get("triggered_at")
        task.completed_at = data.get("completed_at")
        task.confirmed_by = data.get("confirmed_by")
        task.notes = data.get("notes", "")
        task.reminders = data.get("reminders", [])
        return task


class TimeScheduler:
    """
    时间调度引擎
    
    书童的心脏。每分钟扫描一次任务队列，到时间触发。
    """
    
    def __init__(self, profile_manager, template_engine, bedtime_guide, 
                 journal_dir, check_interval=60):
        """
        Args:
            profile_manager: 多用户管理器
            template_engine: 作息模板引擎
            bedtime_guide: 睡前引导系统
            journal_dir: 修行记录目录
            check_interval: 扫描间隔（秒，默认60秒）
        """
        self.profile_manager = profile_manager
        self.template_engine = template_engine
        self.bedtime_guide = bedtime_guide
        self.journal_dir = Path(journal_dir)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        
        self.check_interval = check_interval
        self.running = False
        self.lock = Lock()
        self.timers = []
        
        # 今日任务队列 {child_id: [ScheduledTask, ...]}
        self.today_tasks: Dict[str, List[ScheduledTask]] = {}
        
        # 预提醒提前时间（分钟）
        self.pre_remind_minutes = 5
        # 超时判定时间（任务开始后N分钟无确认视为超时）
        self.timeout_minutes = 15
        # Escalation时间（超时后N分钟提醒家长）
        self.escalation_minutes = 10
        
        # 加载今日任务（如果已生成）
        self._load_today_tasks()
    
    # ═══════════════════════════════════════════
    # 任务生成
    # ═══════════════════════════════════════════
    
    def generate_today_tasks(self):
        """为所有孩子生成今日任务队列"""
        print("\n" + "="*60)
        print("【生成今日任务队列】", datetime.now().strftime("%Y-%m-%d %H:%M"))
        print("="*60)
        
        self.today_tasks = {}
        
        for child in self.profile_manager.get_all_children():
            tasks = self.template_engine.generate_daily_tasks(child)
            
            scheduled_tasks = []
            for task in tasks:
                st = ScheduledTask(
                    task_id=f"{child.child_id}_{task['id']}_{datetime.now().strftime('%Y%m%d')}",
                    name=task["name"],
                    scheduled_time=task["time"],
                    task_type=task["type"],
                    duration=task["duration"],
                    child_id=child.child_id,
                    must=task.get("must", True),
                    metadata={"stage": child.stage},
                )
                scheduled_tasks.append(st)
            
            self.today_tasks[child.child_id] = scheduled_tasks
            print(f"  {child.name} ({child.get_stage_name()}): {len(scheduled_tasks)} 个任务")
        
        self._save_today_tasks()
        print(f"\n✅ 共为 {len(self.today_tasks)} 个孩子生成任务")
    
    # ═══════════════════════════════════════════
    # 核心调度循环
    # ═══════════════════════════════════════════
    
    def start(self):
        """启动调度引擎"""
        if self.running:
            print("[调度] 引擎已在运行")
            return
        
        self.running = True
        print("\n[调度] 时间调度引擎启动")
        print(f"[调度] 扫描间隔: {self.check_interval}秒")
        print(f"[调度] 预提醒提前: {self.pre_remind_minutes}分钟")
        print(f"[调度] 超时判定: {self.timeout_minutes}分钟")
        
        # 如果没有今日任务，生成
        if not self.today_tasks:
            self.generate_today_tasks()
        
        # 启动调度线程
        self.scheduler_thread = Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
    
    def stop(self):
        """停止调度引擎"""
        self.running = False
        for timer in self.timers:
            timer.cancel()
        print("[调度] 时间调度引擎已停止")
    
    def _scheduler_loop(self):
        """调度主循环：每分钟扫描一次"""
        while self.running:
            try:
                self._scan_tasks()
            except Exception as e:
                print(f"[调度] 扫描异常: {e}")
            
            time.sleep(self.check_interval)
    
    def _scan_tasks(self):
        """扫描所有任务，处理到期的"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_dt = datetime.strptime(current_time, "%H:%M")
        
        with self.lock:
            for child_id, tasks in self.today_tasks.items():
                child = self.profile_manager.get_child(child_id)
                if not child:
                    continue
                
                for task in tasks:
                    task_dt = datetime.strptime(task.scheduled_time, "%H:%M")
                    time_diff = (task_dt - current_dt).total_seconds() / 60  # 分钟差
                    
                    # 预提醒（到点前5分钟）
                    if 0 < time_diff <= self.pre_remind_minutes and task.status == TaskStatus.PENDING:
                        self._pre_remind(task, child)
                    
                    # 正式触发（到点了）
                    if time_diff <= 0 and task.status in [TaskStatus.PENDING, TaskStatus.REMINDED]:
                        self._trigger_task(task, child)
                    
                    # 超时检查（任务触发后N分钟无确认）
                    if task.status == TaskStatus.TRIGGERED and task.triggered_at:
                        triggered_dt = datetime.fromisoformat(task.triggered_at)
                        elapsed = (now - triggered_dt).total_seconds() / 60
                        
                        if elapsed >= self.timeout_minutes:
                            self._handle_timeout(task, child)
                        elif elapsed >= self.escalation_minutes and not any(r["type"] == "escalation" for r in task.reminders):
                            self._escalate_to_parent(task, child)
    
    # ═══════════════════════════════════════════
    # 任务触发与执行
    # ═══════════════════════════════════════════
    
    def _pre_remind(self, task, child):
        """预提醒：到点前5分钟"""
        task.status = TaskStatus.REMINDED
        task.reminders.append({
            "time": datetime.now().isoformat(),
            "type": "pre",
            "to": "child",
            "message": f"{child.name}，还有5分钟就是{task.name}的时间啦。",
        })
        
        print(f"\n⏰ [预提醒] {child.name} | {task.scheduled_time} {task.name} (还有5分钟)")
        self._save_today_tasks()
    
    def _trigger_task(self, task, child):
        """正式触发任务"""
        task.status = TaskStatus.TRIGGERED
        task.triggered_at = datetime.now().isoformat()
        
        print(f"\n{'='*60}")
        print(f"【任务触发】{child.name} | {task.scheduled_time} {task.name}")
        print(f"{'='*60}")
        
        # 根据任务类型执行不同操作
        if task.task_type == "睡前":
            self._execute_bedtime_task(task, child)
        elif task.task_type == "陪伴":
            self._execute_companion_task(task, child)
        elif task.task_type == "观察":
            self._execute_observation_task(task, child)
        elif task.task_type == "记录":
            self._execute_record_task(task, child)
        elif task.task_type == "引导":
            self._execute_guidance_task(task, child)
        elif task.task_type == "文化传承":
            self._execute_culture_task(task, child)
        else:
            print(f"  [执行] 通用任务: {task.name}")
        
        self._save_today_tasks()
    
    def _execute_bedtime_task(self, task, child):
        """执行睡前仪式"""
        print(f"  [睡前仪式] 开始为 {child.name} 准备睡前引导")
        
        # 获取今日特殊情况
        custom_notes = self._get_today_notes(child.child_id)
        
        # 生成睡前引导内容
        session = self.bedtime_guide.generate_bedtime_session(
            child, 
            duration_minutes=task.duration,
            custom_notes=custom_notes
        )
        
        music = self.bedtime_guide.get_music_recommendation(child)
        
        print(f"  🎵 音乐: {music['recommendation']} ({music['details']['tempo']}BPM)")
        print(f"  📖 引导词: {session['title']}")
        print(f"  ⏱️  预计时长: {session['total_duration']} 分钟")
        print(f"\n  引导词预览:")
        print(f"  {self.bedtime_guide.get_script_preview(child, max_lines=10)}")
        
        # 标记为执行中
        task.status = TaskStatus.IN_PROGRESS
        task.notes = f"睡前仪式已开始 | 音乐: {music['recommendation']} | 预计{session['total_duration']}分钟"
        
        # 设置完成定时器（仪式时长后自动询问是否完成）
        def ask_completion():
            if task.status == TaskStatus.IN_PROGRESS:
                print(f"\n  [睡前仪式] {child.name} 的{task.name}已持续{task.duration}分钟")
                print(f"  等待孩子/家长确认完成...")
        
        timer = Timer(task.duration * 60, ask_completion)
        timer.daemon = True
        timer.start()
        self.timers.append(timer)
    
    def _execute_companion_task(self, task, child):
        """执行陪伴任务"""
        messages = {
            "早安唤醒": f"{child.name}，早安！今天会是美好的一天。",
            "早餐陪伴": f"{child.name}，早餐要慢慢吃，细嚼慢咽对身体好。",
            "午睡陪伴": f"{child.name}，闭上眼睛，书童给你讲个故事...",
            "晚餐陪伴": f"{child.name}，今天在学校有什么好玩的事吗？",
            "放学问候": f"{child.name}，放学啦！今天过得怎么样？",
            "家庭互动": f"{child.name}，跟爸爸妈妈一起玩个游戏吧。",
        }
        
        message = messages.get(task.name, f"{child.name}，{task.name}的时间到了。")
        print(f"  [陪伴] {message}")
        task.status = TaskStatus.IN_PROGRESS
    
    def _execute_observation_task(self, task, child):
        """执行观察任务"""
        messages = {
            "提醒准妈妈运动": "准妈妈，该起来活动活动了，散步30分钟。",
            "提醒俯卧练习": "宝宝该练习趴着了，每天趴一会儿，头会抬得更好。",
            "户外时间提醒": f"{child.name}，该出去活动了，阳光和运动对长高很重要。",
            "运动提醒": f"{child.name}，该运动了，出点汗，晚上睡得更香。",
            "情绪检查": f"{child.name}，今天心情怎么样？跟我说说。",
            "晨起状态检查": f"{child.name}，早上感觉怎么样？有没有哪里不舒服？",
        }
        
        message = messages.get(task.name, f"[观察] {task.name}")
        print(f"  {message}")
        task.status = TaskStatus.IN_PROGRESS
    
    def _execute_record_task(self, task, child):
        """执行记录任务"""
        print(f"  [记录] {task.name} - 请记录今日数据")
        task.status = TaskStatus.IN_PROGRESS
    
    def _execute_guidance_task(self, task, child):
        """执行引导任务"""
        print(f"  [引导] {task.name} - 书童陪伴时间")
        task.status = TaskStatus.IN_PROGRESS
    
    def _execute_culture_task(self, task, child):
        """执行文化传承任务"""
        print(f"  [文化传承] {task.name} - 今天的文明种子")
        task.status = TaskStatus.IN_PROGRESS
    
    # ═══════════════════════════════════════════
    # 超时与 Escalation
    # ═══════════════════════════════════════════
    
    def _handle_timeout(self, task, child):
        """处理任务超时"""
        task.status = TaskStatus.TIMEOUT
        
        print(f"\n⚠️ [超时] {child.name} | {task.name} 未在{self.timeout_minutes}分钟内完成")
        
        # 如果是必须完成的任务，记录异常
        if task.must:
            print(f"  [异常记录] 必须任务超时: {task.name}")
            self._log_exception(child.child_id, task, "任务超时未完成")
    
    def _escalate_to_parent(self, task, child):
        """升级提醒家长"""
        task.reminders.append({
            "time": datetime.now().isoformat(),
            "type": "escalation",
            "to": "parent",
            "message": f"{child.name}的{task.name}尚未完成，请协助。",
        })
        
        print(f"\n📢 [提醒家长] {child.name} | {task.name} 未完成，请家长协助")
        self._save_today_tasks()
    
    # ═══════════════════════════════════════════
    # 任务完成确认
    # ═══════════════════════════════════════════
    
    def confirm_task_completion(self, child_id, task_id, confirmed_by="child", notes=""):
        """
        确认任务完成
        
        Args:
            child_id: 孩子ID
            task_id: 任务ID
            confirmed_by: 谁确认的 (child/parent/system)
            notes: 备注
        """
        with self.lock:
            tasks = self.today_tasks.get(child_id, [])
            for task in tasks:
                if task.task_id == task_id:
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.now().isoformat()
                    task.confirmed_by = confirmed_by
                    task.notes = notes or task.notes
                    
                    child = self.profile_manager.get_child(child_id)
                    name = child.name if child else child_id
                    print(f"\n✅ [完成] {name} | {task.name} (由{confirmed_by}确认)")
                    
                    self._save_today_tasks()
                    return True
        
        return False
    
    def confirm_task_by_name(self, child_id, task_name, confirmed_by="child", notes=""):
        """通过任务名确认完成（更方便的接口）"""
        with self.lock:
            tasks = self.today_tasks.get(child_id, [])
            for task in tasks:
                if task.name == task_name and task.status != TaskStatus.COMPLETED:
                    return self.confirm_task_completion(child_id, task.task_id, confirmed_by, notes)
        return False
    
    def skip_task(self, child_id, task_id, reason=""):
        """跳过任务（如孩子生病、外出等）"""
        with self.lock:
            tasks = self.today_tasks.get(child_id, [])
            for task in tasks:
                if task.task_id == task_id:
                    task.status = TaskStatus.SKIPPED
                    task.notes = f"跳过原因: {reason}"
                    
                    child = self.profile_manager.get_child(child_id)
                    name = child.name if child else child_id
                    print(f"\n⏭️ [跳过] {name} | {task.name} ({reason})")
                    
                    self._save_today_tasks()
                    return True
        return False
    
    # ═══════════════════════════════════════════
    # 今日状态查询
    # ═══════════════════════════════════════════
    
    def get_child_today_status(self, child_id) -> Dict:
        """获取指定孩子今日任务状态"""
        tasks = self.today_tasks.get(child_id, [])
        
        total = len(tasks)
        completed = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
        pending = len([t for t in tasks if t.status == TaskStatus.PENDING])
        in_progress = len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS])
        timeout = len([t for t in tasks if t.status == TaskStatus.TIMEOUT])
        skipped = len([t for t in tasks if t.status == TaskStatus.SKIPPED])
        must_total = len([t for t in tasks if t.must])
        must_completed = len([t for t in tasks if t.must and t.status == TaskStatus.COMPLETED])
        
        # 接下来的任务
        current_time = datetime.now().strftime("%H:%M")
        upcoming = []
        for task in tasks:
            if task.status in [TaskStatus.PENDING, TaskStatus.REMINDED]:
                upcoming.append({
                    "time": task.scheduled_time,
                    "name": task.name,
                    "type": task.task_type,
                })
        upcoming.sort(key=lambda x: x["time"])
        
        return {
            "child_id": child_id,
            "total_tasks": total,
            "completed": completed,
            "pending": pending,
            "in_progress": in_progress,
            "timeout": timeout,
            "skipped": skipped,
            "completion_rate": f"{completed}/{total}" if total > 0 else "N/A",
            "must_completion_rate": f"{must_completed}/{must_total}" if must_total > 0 else "N/A",
            "upcoming_tasks": upcoming[:3],
        }
    
    def get_all_children_status(self) -> Dict[str, Dict]:
        """获取所有孩子今日状态"""
        return {child_id: self.get_child_today_status(child_id) 
                for child_id in self.today_tasks.keys()}
    
    def get_current_task(self, child_id) -> Optional[ScheduledTask]:
        """获取孩子当前正在进行的任务"""
        tasks = self.today_tasks.get(child_id, [])
        for task in tasks:
            if task.status in [TaskStatus.TRIGGERED, TaskStatus.IN_PROGRESS]:
                return task
        return None
    
    # ═══════════════════════════════════════════
    # 每日工作报告
    # ═══════════════════════════════════════════
    
    def generate_daily_report(self) -> Dict:
        """生成每日工作报告"""
        report_date = datetime.now().strftime("%Y-%m-%d")
        
        print("\n" + "="*60)
        print(f"【书童每日工作报告】{report_date}")
        print("="*60)
        
        all_status = self.get_all_children_status()
        
        report = {
            "date": report_date,
            "generated_at": datetime.now().isoformat(),
            "children": [],
            "summary": {
                "total_children": len(all_status),
                "total_tasks": 0,
                "total_completed": 0,
                "total_timeout": 0,
                "overall_completion_rate": 0,
            },
            "exceptions": [],
            "tomorrow_preparation": [],
        }
        
        total_tasks = 0
        total_completed = 0
        total_timeout = 0
        
        for child_id, status in all_status.items():
            child = self.profile_manager.get_child(child_id)
            if not child:
                continue
            
            child_report = {
                "name": child.name,
                "stage": child.get_stage_name(),
                "total_tasks": status["total_tasks"],
                "completed": status["completed"],
                "timeout": status["timeout"],
                "completion_rate": status["completion_rate"],
                "must_completion_rate": status["must_completion_rate"],
                "status": "良好" if status["timeout"] == 0 else "需关注",
            }
            
            report["children"].append(child_report)
            total_tasks += status["total_tasks"]
            total_completed += status["completed"]
            total_timeout += status["timeout"]
            
            # 记录异常
            if status["timeout"] > 0:
                report["exceptions"].append({
                    "child": child.name,
                    "issue": f"有{status['timeout']}个任务超时",
                    "suggestion": "建议家长关注孩子的作息规律",
                })
            
            print(f"\n  {child.name} ({child.get_stage_name()})")
            print(f"    任务: {status['completion_rate']} | 必须任务: {status['must_completion_rate']}")
            if status["upcoming_tasks"]:
                print(f"    接下来: {' | '.join([t['name'] for t in status['upcoming_tasks']])}")
        
        report["summary"] = {
            "total_children": len(all_status),
            "total_tasks": total_tasks,
            "total_completed": total_completed,
            "total_timeout": total_timeout,
            "overall_completion_rate": f"{total_completed}/{total_tasks}" if total_tasks > 0 else "N/A",
        }
        
        print(f"\n{'='*60}")
        print(f"总计: {report['summary']['overall_completion_rate']} 完成")
        print(f"异常: {len(report['exceptions'])} 项")
        print("="*60)
        
        # 保存报告
        self._save_daily_report(report)
        
        return report
    
    # ═══════════════════════════════════════════
    # 书童自检
    # ═══════════════════════════════════════════
    
    def self_check(self) -> Dict:
        """
        书童自检：检查今天该做的事做完了吗？
        
        返回自检报告。
        """
        print("\n" + "="*60)
        print("【书童自检】今天的工作完成度检查")
        print("="*60)
        
        all_status = self.get_all_children_status()
        
        check_items = []
        issues = []
        
        # 1. 任务完成度检查
        for child_id, status in all_status.items():
            child = self.profile_manager.get_child(child_id)
            if not child:
                continue
            
            # 必须任务完成率
            must_rate = status.get("must_completion_rate", "0/0")
            if status.get("timeout", 0) > 0:
                issues.append(f"{child.name}: 有{status['timeout']}个任务超时")
                check_items.append({"item": f"{child.name}任务完成", "status": "⚠️", "detail": f"超时{status['timeout']}个"})
            else:
                check_items.append({"item": f"{child.name}任务完成", "status": "✅", "detail": must_rate})
        
        # 2. 睡前仪式检查（最重要的任务）
        bedtime_completed = True
        for child_id, tasks in self.today_tasks.items():
            child = self.profile_manager.get_child(child_id)
            for task in tasks:
                if task.task_type == "睡前" and task.status != TaskStatus.COMPLETED:
                    bedtime_completed = False
                    issues.append(f"{child.name if child else child_id}: 睡前仪式未完成")
        
        if bedtime_completed:
            check_items.append({"item": "所有睡前仪式", "status": "✅", "detail": "全部完成"})
        else:
            check_items.append({"item": "所有睡前仪式", "status": "⚠️", "detail": "部分未完成"})
        
        # 3. 异常处理检查
        if issues:
            check_items.append({"item": "异常处理", "status": "⚠️", "detail": f"{len(issues)}项待处理"})
        else:
            check_items.append({"item": "异常处理", "status": "✅", "detail": "无异常"})
        
        # 4. 修行记录检查
        journal_exists = any(self.journal_dir.glob("reflection_*.jsonl"))
        check_items.append({"item": "修行记录", "status": "✅" if journal_exists else "⚠️", 
                           "detail": "已记录" if journal_exists else "未记录"})
        
        # 输出结果
        for item in check_items:
            print(f"  {item['status']} {item['item']}: {item['detail']}")
        
        overall = "合格" if not issues else f"有{len(issues)}项待改进"
        print(f"\n  总体评价: {overall}")
        
        return {
            "check_time": datetime.now().isoformat(),
            "items": check_items,
            "issues": issues,
            "overall": overall,
        }
    
    # ═══════════════════════════════════════════
    # 数据持久化
    # ═══════════════════════════════════════════
    
    def _save_today_tasks(self):
        """保存今日任务队列"""
        data = {}
        for child_id, tasks in self.today_tasks.items():
            data[child_id] = [t.to_dict() for t in tasks]
        
        file_path = self.journal_dir / f"tasks_{datetime.now().strftime('%Y%m%d')}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _load_today_tasks(self):
        """加载今日任务队列"""
        file_path = self.journal_dir / f"tasks_{datetime.now().strftime('%Y%m%d')}.json"
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for child_id, tasks_data in data.items():
                    self.today_tasks[child_id] = [ScheduledTask.from_dict(t) for t in tasks_data]
            print(f"[调度] 已加载今日任务队列: {len(self.today_tasks)} 个孩子")
    
    def _save_daily_report(self, report):
        """保存每日工作报告"""
        file_path = self.journal_dir / f"daily_report_{report['date']}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[报告] 已保存: {file_path}")
    
    def _log_exception(self, child_id, task, reason):
        """记录异常"""
        exception = {
            "timestamp": datetime.now().isoformat(),
            "child_id": child_id,
            "task": task.to_dict(),
            "reason": reason,
        }
        
        file_path = self.journal_dir / f"exceptions_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(exception, ensure_ascii=False) + '\n')
    
    def _get_today_notes(self, child_id) -> str:
        """获取孩子今日特殊情况备注"""
        # 这里可以从情绪记录、家长反馈等获取
        return ""
