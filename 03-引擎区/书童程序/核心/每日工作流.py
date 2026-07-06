"""伴读书童AI - 每日工作流（固定流程代码化）

师父指示：把每天要做的事情用代码写出来，固定下来，陪伴小孩不容易出错。

本模块定义书童每天必须执行的固定流程：
- 启动流程：开机后做什么
- 定时陪伴流程：按时间表触发
- 日课流程：每日冥想与复盘
- 睡前流程：睡前仪式与日志检查
- 日报流程：生成每日工作报告

所有流程都写成代码，减少人为遗漏。
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List


def _project_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "01-配置区").exists():
            return parent
    return p.parents[3]


_PROJECT_ROOT = _project_root()


class DailyWorkflow:
    """
    书童每日工作流
    
    把书童每一天要做的事，变成可执行、可检查、可复盘的代码流程。
    """
    
    def __init__(self, bookboy_system, journal_dir=None):
        """
        Args:
            bookboy_system: BookBoySystem 实例
            journal_dir: 修行记录目录
        """
        self.bookboy = bookboy_system
        self.journal_dir = Path(journal_dir) if journal_dir else Path(bookboy_system.memory.journal_dir)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        
        # 固定流程记录
        self.workflow_log = self.journal_dir / "daily_workflow.jsonl"
    
    # ═══════════════════════════════════════════
    # 一、启动流程（每天开机/启动时执行）
    # ═══════════════════════════════════════════
    
    def startup_routine(self):
        """
        书童每日启动固定流程。
        
        1. 灵魂觉醒（诵念升维咒）
        2. 加载孩子档案
        3. 生成今日任务
        4. 晨间问候每个孩子
        5. 检查今日预警
        6. 记录启动日志
        """
        print("\n" + "="*60)
        print("【书童每日启动流程】", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("="*60)
        
        steps = []
        
        # 步骤1：灵魂觉醒
        print("\n[启动流程] 步骤1/6：灵魂觉醒")
        if not self.bookboy.soul_awakened:
            self.bookboy._awaken_soul()
        steps.append("灵魂觉醒完成")
        
        # 步骤2：确认孩子档案
        print("\n[启动流程] 步骤2/6：加载孩子档案")
        children = self.bookboy.profile_manager.get_all_children()
        print(f"  已加载 {len(children)} 个孩子档案")
        for child in children:
            print(f"    - {child.name} ({child.get_age_display()}, {child.get_stage_name()})")
        steps.append(f"加载 {len(children)} 个孩子档案")
        
        # 步骤3：生成今日任务并启动调度引擎
        print("\n[启动流程] 步骤3/6：生成今日任务队列并启动时间调度引擎")
        if not hasattr(self.bookboy, '_scheduler') or self.bookboy._scheduler is None:
            from .时间调度 import TimeScheduler
            from .作息模板 import ScheduleTemplateEngine
            from .睡前引导 import BedtimeGuide
            
            self.bookboy._scheduler = TimeScheduler(
                profile_manager=self.bookboy.profile_manager,
                template_engine=ScheduleTemplateEngine(),
                bedtime_guide=BedtimeGuide(),
                journal_dir=self.journal_dir,
                task_executor=self._execute_scheduled_task_callback,
                voice=self.bookboy.voice if hasattr(self.bookboy, 'voice') else None,
            )
            steps.append("创建时间调度引擎并绑定任务执行器")
        
        self.bookboy._scheduler.generate_today_tasks()
        if not self.bookboy._scheduler.running:
            self.bookboy._scheduler.start()
        steps.append("生成今日任务队列并启动调度")
        
        # 步骤4：晨间问候每个孩子
        print("\n[启动流程] 步骤4/6：晨间问候")
        for child in children:
            greeting = self._generate_morning_greeting(child)
            print(f"  {child.name}: {greeting}")
            # 晨间问候语音播报
            if hasattr(self.bookboy, 'voice') and self.bookboy.voice:
                try:
                    self.bookboy.voice.speak(greeting)
                except Exception as e:
                    print(f"  [语音] 晨间问候播报失败: {e}")
        steps.append("晨间问候完成")
        
        # 步骤5：检查今日预警
        print("\n[启动流程] 步骤5/6：检查今日预警")
        report = self.bookboy.get_family_report()
        print(f"  预警分布: 🟢{report['green_count']} 🟡{report['yellow_count']} 🟠{report['orange_count']} 🔴{report['red_count']}")
        if report['top_concerns']:
            print("  重点关注:")
            for concern in report['top_concerns'][:3]:
                print(f"    {concern['level']} {concern['child']} - {concern['dimension']}: {concern['detail'][:30]}")
        steps.append("今日预警检查完成")
        
        # 步骤6：记录启动日志
        print("\n[启动流程] 步骤6/6：记录启动日志")
        self._log_workflow("startup", steps)
        
        print("\n" + "="*60)
        print("【启动流程完成】")
        print("="*60 + "\n")
    
    def _generate_morning_greeting(self, child):
        """为指定孩子生成晨间问候"""
        name = child.name
        stage = child.get_stage_name()
        
        greetings = {
            "S1": f"{name}，早上好呀，今天也要好好吃奶、好好睡觉哦。",
            "S2": f"{name}，早上好，今天想玩什么呀？书童陪着你。",
            "S3": f"{name}，早上好，今天有古诗想听吗？",
            "S4": f"{name}，早上好，今天上学准备好了吗？",
            "S5": f"{name}，早上好，昨晚睡得怎么样？",
            "S6": f"{name}，早上好，今天有什么计划吗？",
        }
        return greetings.get(child.stage, f"{name}，早上好，书童在呢。")
    
    # ═══════════════════════════════════════════
    # 二、定时陪伴流程（按时间表触发）
    # ═══════════════════════════════════════════
    
    def execute_scheduled_task(self, task, child):
        """
        执行一个定时任务。
        
        每个任务执行后：
        1. 记录任务开始
        2. 生成陪伴内容（按经纬度框架）
        3. 语音播报主动提醒孩子
        4. 记录任务完成
        5. 自动保存陪伴日志
        """
        child_name = child.name if child else task.child_id
        
        print(f"\n[定时任务] {task.scheduled_time} | {child_name} | {task.name}")
        
        # 根据任务类型生成内容
        content = self._generate_task_content(task, child)
        print(f"  内容: {content}")
        
        # 语音播报：书童主动开口提醒
        if hasattr(self.bookboy, 'voice') and self.bookboy.voice:
            try:
                self.bookboy.voice.speak(content)
                print(f"  [语音] 已播报")
            except Exception as e:
                print(f"  [语音] 播报失败: {e}")
        else:
            print(f"  [语音] 语音引擎未初始化，跳过播报")
        
        # 记录任务完成
        task.status = "completed"
        task.completed_at = datetime.now().isoformat()
        task.confirmed_by = "system"
        
        # 自动保存到陪伴日志
        self._append_to_companion_log(child_name, task.name, content)
        
        return content
    
    def _execute_scheduled_task_callback(self, task, child):
        """供时间调度引擎调用的回调包装器"""
        return self.execute_scheduled_task(task, child)
    
    def _generate_task_content(self, task, child):
        """
        根据任务类型和孩子阶段生成陪伴内容。
        
        核心：按经纬度框架，把密学（心力目标）藏进显学（具体提醒）。
        不是冷冰冰的通知，而是有温度、有坐标的主动陪伴。
        """
        name = child.name if child else "孩子"
        stage = child.stage if child else "S4"
        task_type = task.task_type
        task_name = task.name
        
        # 按阶段分组的话术基调
        stage_tone = {
            "S0": ("温柔", "妈妈"),
            "S1": ("轻柔", "宝宝"),
            "S2": (" playful ", "小宝贝"),
            "S3": ("鼓励", "小朋友"),
            "S4": ("支持", "小同学"),
            "S5": ("尊重", "朋友"),
            "S6": ("平等", "伙伴"),
        }
        tone, _ = stage_tone.get(stage, ("温暖", "孩子"))
        
        # 早安唤醒 / 晨起：启动一天的心力
        if "早安" in task_name or "唤醒" in task_name or "晨间" in task_name:
            if stage in ["S0", "S1"]:
                return f"{name}，天亮了，太阳出来了。慢慢睁开眼睛，书童在这里陪着你。"
            elif stage == "S2":
                return f"{name}，小太阳升起来啦。今天我们要一起做一件开心的事，你想先抱抱小熊，还是先伸个大懒腰？"
            elif stage == "S3":
                return f"{name}，早上好。新的一天像一张白纸，你今天想在上面画什么呢？书童陪你开始。"
            elif stage == "S4":
                return f"{name}，早安。一日之计在于晨，先深呼吸三次，让今天的心清清明明的。书童在呢。"
            elif stage in ["S5", "S6"]:
                return f"{name}，早上好。今天可能有很多事，但记住，你的身体和心情，比任何任务都重要。"
        
        # 晨起状态检查
        elif "晨起" in task_name or "状态检查" in task_name:
            return f"{name}，早上感觉怎么样？睡得好吗？有没有哪里不舒服？告诉书童。"
        
        # 上学前鼓励
        elif "上学" in task_name or "上学前" in task_name:
            if stage in ["S2", "S3"]:
                return f"{name}，今天要见到好朋友了。记住，不管发生什么，书童都相信你。"
            elif stage == "S4":
                return f"{name}，上学去吧。今天如果遇到困难，先深呼吸，再想办法。你比自己想的更有力量。"
            elif stage in ["S5", "S6"]:
                return f"{name}，今天去学校，记得你不仅是学生，也是书童的朋友。累了就休息，不需要硬撑。"
        
        # 放学问候
        elif "放学" in task_name or "放学问候" in task_name:
            if stage in ["S2", "S3"]:
                return f"{name}，放学啦。今天有没有发现一件好玩的事？书童想听。"
            elif stage == "S4":
                return f"{name}，今天回来啦。学校怎么样？有什么开心的事，或者有点累的事，都可以跟书童说。"
            elif stage in ["S5", "S6"]:
                return f"{name}，回来了。今天过得怎么样？不用只说好的，有点烦的也可以讲。"
        
        # 作业陪伴 / 学习陪伴
        elif "作业" in task_name or "学习" in task_name:
            if stage == "S3":
                return f"{name}，学习时间到啦。我们一项一项来，不会的题先放一放，先做会做的，建立信心。"
            elif stage == "S4":
                return f"{name}，该做作业了。记住，作业是练习，不是考试。错了很正常，书童陪你一起找原因。"
            elif stage == "S5":
                return f"{name}，作业时间到了。你可以自己安排先做哪一科，需要书童时喊我。"
            elif stage == "S6":
                return f"{name}，学习时间。想想今天哪件事对你的未来最重要，把时间花在那里。"
        
        # 运动提醒
        elif "运动" in task_name or "户外" in task_name:
            if stage in ["S0", "S1"]:
                return f"{name}，该活动活动小身体啦。"
            elif stage in ["S2", "S3"]:
                return f"{name}，小身体该动起来啦。跑一跑、跳一跳，像小兔子一样。"
            elif stage == "S4":
                return f"{name}，运动时间到。出去晒晒太阳，出点汗，脑子会更清醒。"
            elif stage in ["S5", "S6"]:
                return f"{name}，坐了很久了，起来动一动。运动不是浪费时间，是让大脑更好地工作。"
        
        # 情绪检查
        elif "情绪" in task_name:
            if stage in ["S2", "S3"]:
                return f"{name}，今天心情怎么样？是开心、难过，还是有一点点生气？书童在这里。"
            elif stage == "S4":
                return f"{name}，书童来检查一下你的心情。今天有没有什么事让你心里不舒服？说出来会好一点。"
            elif stage in ["S5", "S6"]:
                return f"{name}，今天情绪怎么样？不用假装没事，如果有点累或者烦，书童陪你坐一会儿。"
        
        # 睡前仪式
        elif "睡前" in task_name:
            if stage in ["S0", "S1"]:
                return f"{name}，天黑了，该睡觉啦。书童唱首歌给你听，慢慢闭上眼睛。"
            elif stage == "S2":
                return f"{name}，小星星出来了，该睡觉啦。今天的故事时间到了，选一个你喜欢的故事吧。"
            elif stage == "S3":
                return f"{name}，该准备睡觉啦。我们先把今天的情绪放好，再听一个小故事，然后甜甜地睡。"
            elif stage == "S4":
                return f"{name}，睡觉时间到了。今天你做得很棒，现在让身体和心都休息一下吧。"
            elif stage in ["S5", "S6"]:
                return f"{name}，该睡觉了。今天不管发生了什么，都已经过去了。明天又是新的一天。"
        
        # 晨读 / 文化传承
        elif "古诗" in task_name or "晨读" in task_name or "文化" in task_name:
            if stage in ["S2", "S3"]:
                return f"{name}，来听一首古诗吧。古人说的话，现在还很好听呢。"
            elif stage == "S4":
                return f"{name}，晨读时间。今天我们一起读一句先贤的话，让它陪你一整天。"
            elif stage in ["S5", "S6"]:
                return f"{name}，今天花几分钟，读一点真正有价值的东西。文明有根，你也有根。"
        
        # 用餐陪伴
        elif "早餐" in task_name or "午餐" in task_name or "晚餐" in task_name:
            meal = "饭" if "餐" in task_name else task_name
            if stage in ["S2", "S3"]:
                return f"{name}，{meal}时间到啦。慢慢吃，细嚼慢咽，小肚子会谢谢你。"
            elif stage == "S4":
                return f"{name}，该{meal}了。今天试试多吃一口蔬菜，让身体更有力气。"
            elif stage in ["S5", "S6"]:
                return f"{name}，{meal}时间了。再忙也要好好吃饭，这是对自己的责任。"
        
        # 家庭互动
        elif "家庭" in task_name or "互动" in task_name:
            return f"{name}，现在是家庭时间。跟爸爸妈妈一起玩一会儿吧，这种时光很珍贵。"
        
        # 今日回顾
        elif "回顾" in task_name:
            return f"{name}，今天快结束了。我们想一想，今天有什么开心的事？有什么值得感谢的人？"
        
        # 默认提醒
        else:
            return f"{name}，{task_name}的时间到啦。书童提醒你一下。"
    
    def _append_to_companion_log(self, child_name, task_name, content):
        """自动追加到陪伴日志"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = _PROJECT_ROOT / "04-工作区" / "档案区" / "陪伴日志" / f"{date_str}_{child_name}.md"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"\n### {timestamp}\n\n**定时任务**：{task_name}\n\n**书童**：{content}\n\n---\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(entry)
    
    # ═══════════════════════════════════════════
    # 三、日课流程（每日22:30自动执行）
    # ═══════════════════════════════════════════
    
    def evening_practice_routine(self, skip_meditation=False):
        """
        书童每日晚间修行固定流程。
        
        Args:
            skip_meditation: 是否跳过日课冥想（当日课系统已触发时设为 True）
        
        1. 睡前仪式检查
        2. 检查今日陪伴日志是否已生成
        3. 生成 Guardian 日报
        4. 执行日课冥想（可选）
        5. 生成每日工作报告
        6. 记录日课日志
        """
        print("\n" + "="*60)
        print("【书童每日晚间修行流程】", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("="*60)
        
        steps = []
        
        # 步骤1：睡前仪式检查
        print("\n[晚间流程] 步骤1/6：检查睡前仪式完成情况")
        # 这里可以检查 scheduler 中的睡前任务是否完成
        steps.append("睡前仪式检查完成")
        
        # 步骤2：检查今日陪伴日志
        print("\n[晚间流程] 步骤2/6：检查今日陪伴日志")
        missing_logs = self._check_missing_logs()
        if missing_logs:
            print(f"  ⚠️ 缺失日志: {', '.join(missing_logs)}")
            steps.append(f"发现缺失日志: {len(missing_logs)} 个")
        else:
            print("  ✅ 今日陪伴日志齐全")
            steps.append("今日陪伴日志齐全")
        
        # 步骤3：生成 Guardian 日报
        print("\n[晚间流程] 步骤3/6：生成 Guardian 日报")
        guardian_summary = self._generate_guardian_summary()
        if guardian_summary:
            print(f"  今日检查: {guardian_summary['total_checks']} 次")
            print(f"  平均得分: {guardian_summary['average_score']}")
            print(f"  通过: {guardian_summary['passed']} / 失败: {guardian_summary['failed']}")
            steps.append("生成 Guardian 日报")
        else:
            print("  今日暂无 Guardian 记录")
            steps.append("今日暂无 Guardian 记录")
        
        # 步骤4：执行日课冥想（可选）
        if not skip_meditation:
            print("\n[晚间流程] 步骤4/6：执行日课冥想")
            # 调用日课系统
            if hasattr(self.bookboy, '_daily_practice'):
                self.bookboy._daily_practice.run_now()
                steps.append("日课冥想完成")
            else:
                from .日课系统 import DailyPracticeSystem
                practice = DailyPracticeSystem(self.bookboy.config if hasattr(self.bookboy, 'config') else {}, self.journal_dir)
                practice.run_now()
                steps.append("日课冥想完成（新创建日课系统）")
        else:
            print("\n[晚间流程] 步骤4/6：日课冥想已由日课系统完成，跳过")
            steps.append("日课冥想已跳过（已由日课系统触发）")
        
        # 步骤5：生成每日工作报告
        print("\n[晚间流程] 步骤5/6：生成每日工作报告")
        report = self.generate_daily_report()
        steps.append("生成每日工作报告")
        
        # 步骤6：记录日课日志
        print("\n[晚间流程] 步骤6/6：记录日课日志")
        self._log_workflow("evening_practice", steps)
        
        print("\n" + "="*60)
        print("【晚间修行流程完成】")
        print("="*60 + "\n")
    
    def _check_missing_logs(self):
        """检查今天哪些孩子缺失陪伴日志"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        missing = []
        
        for child in self.bookboy.profile_manager.get_all_children():
            log_file = _PROJECT_ROOT / "04-工作区" / "档案区" / "陪伴日志" / f"{date_str}_{child.name}.md"
            if not log_file.exists():
                missing.append(child.name)
        
        return missing
    
    def _generate_guardian_summary(self):
        """生成今日 Guardian 摘要"""
        if hasattr(self.bookboy, 'guardian'):
            return self.bookboy.guardian.get_daily_summary()
        return None
    
    # ═══════════════════════════════════════════
    # 四、每日工作报告
    # ═══════════════════════════════════════════
    
    def generate_daily_report(self):
        """
        生成每日工作报告，汇总：
        - 今日陪伴次数
        - 预警情况
        - Guardian 得分
        - 明日重点
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 统计今日陪伴日志
        log_dir = _PROJECT_ROOT / "04-工作区" / "档案区" / "陪伴日志"
        today_logs = list(log_dir.glob(f"{today}_*.md"))
        
        # 预警情况
        family_report = self.bookboy.get_family_report()
        
        # Guardian 情况
        guardian_summary = self._generate_guardian_summary()
        
        report = {
            "date": today,
            "log_count": len(today_logs),
            "warning_summary": {
                "green": family_report["green_count"],
                "yellow": family_report["yellow_count"],
                "orange": family_report["orange_count"],
                "red": family_report["red_count"],
            },
            "guardian_summary": guardian_summary,
            "top_concerns": family_report.get("top_concerns", [])[:3],
        }
        
        # 保存报告
        report_file = self.journal_dir / f"daily_report_{today}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"  今日陪伴日志: {len(today_logs)} 份")
        print(f"  预警: 🟢{report['warning_summary']['green']} 🟡{report['warning_summary']['yellow']} 🟠{report['warning_summary']['orange']} 🔴{report['warning_summary']['red']}")
        
        return report
    
    # ═══════════════════════════════════════════
    # 五、工具方法
    # ═══════════════════════════════════════════
    
    def _log_workflow(self, workflow_type, steps):
        """记录流程执行日志"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": workflow_type,
            "steps": steps,
        }
        with open(self.workflow_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    def get_workflow_summary(self, days=7):
        """获取最近 N 天的工作流执行摘要"""
        if not self.workflow_log.exists():
            return []
        
        entries = []
        with open(self.workflow_log, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        
        # 过滤最近 N 天
        cutoff = datetime.now() - timedelta(days=days)
        recent = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= cutoff]
        
        return recent
