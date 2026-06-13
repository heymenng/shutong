"""伴读书童AI - 家长通知系统（技术层）

职责：
1. 预警推送：检测到黄/橙/红预警时通知家长
2. 任务完成报告：每日工作摘要推送
3. 异常提醒：任务超时、孩子情绪异常等
4. 支持多种渠道：控制台/日志/文件（可扩展为微信/短信/API）

推送原则：
- 绿色：不打扰
- 黄色：每日摘要
- 橙色：即时推送
- 红色：立即推送+重复提醒
- 不过度推送，避免家长焦虑
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ParentNotifier:
    """
    家长通知系统
    
    当前实现：
    - 控制台输出（开发调试）
    - 文件记录（持久化）
    - JSON格式（便于后续对接App/小程序）
    
    未来扩展：
    - 微信公众号推送
    - 短信通知
    - App推送
    - 邮件通知
    """
    
    def __init__(self, journal_dir, config=None):
        self.journal_dir = Path(journal_dir)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or {}
        
        # 通知渠道配置
        self.channels = {
            "console": True,      # 控制台输出
            "file": True,         # 文件记录
            "wechat": False,      # 微信（待对接）
            "sms": False,         # 短信（待对接）
            "app": False,         # App推送（待对接）
        }
        
        # 通知级别对应的渠道
        self.level_channels = {
            "🟢": ["file"],           # 绿色：只记录文件
            "🟡": ["console", "file"],  # 黄色：控制台+文件
            "🟠": ["console", "file"],  # 橙色：控制台+文件（未来加微信）
            "🔴": ["console", "file"],  # 红色：全部渠道
        }
        
        # 每日推送时间
        self.daily_report_time = "21:00"
        self.weekly_report_day = 7  # 周日
    
    # ═══════════════════════════════════════════
    # 核心推送方法
    # ═══════════════════════════════════════════
    
    def send(self, title: str, content: str, level: str = "🟢", 
             child_name: str = None, notification_type: str = "general") -> bool:
        """
        发送通知
        
        Args:
            title: 通知标题
            content: 通知内容
            level: 预警级别 🟢🟡🟠🔴
            child_name: 孩子姓名
            notification_type: 类型（warning/task/report/emergency）
        """
        notification = {
            "id": f"NOTIFY_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "title": title,
            "content": content,
            "level": level,
            "child_name": child_name,
            "type": notification_type,
            "read": False,
        }
        
        # 保存到文件
        if self.channels["file"]:
            self._save_notification(notification)
        
        # 控制台输出
        if self.channels["console"] and level in ["🟡", "🟠", "🔴"]:
            self._console_output(notification)
        
        # 未来：微信/短信/App推送
        # if level in ["🟠", "🔴"] and self.channels["wechat"]:
        #     self._send_wechat(notification)
        
        return True
    
    def _save_notification(self, notification: Dict):
        """保存通知到文件"""
        date_str = datetime.now().strftime("%Y%m%d")
        file_path = self.journal_dir / f"notifications_{date_str}.jsonl"
        
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(notification, ensure_ascii=False) + '\n')
    
    def _console_output(self, notification: Dict):
        """控制台输出通知"""
        level = notification["level"]
        title = notification["title"]
        content = notification["content"]
        child = notification.get("child_name", "")
        
        prefix = ""
        if level == "🟡":
            prefix = "【提醒】"
        elif level == "🟠":
            prefix = "【注意】"
        elif level == "🔴":
            prefix = "【紧急】"
        
        print(f"\n{'='*60}")
        print(f"{prefix} {title}")
        if child:
            print(f"孩子: {child}")
        print(f"{'-'*60}")
        print(content)
        print(f"{'='*60}")
    
    # ═══════════════════════════════════════════
    # 特定场景推送
    # ═══════════════════════════════════════════
    
    def send_warning(self, child_name: str, dimension: str, level: str, detail: str):
        """发送预警通知"""
        title = f"{child_name} {dimension}预警"
        content = f"检测到{child_name}的{dimension}出现异常：\n{detail}\n\n建议关注并适当调整。"
        
        return self.send(title, content, level, child_name, "warning")
    
    def send_task_timeout(self, child_name: str, task_name: str):
        """发送任务超时通知"""
        title = f"{child_name} {task_name}未完成"
        content = f"{child_name}的「{task_name}」在规定时间内未完成。\n\n可能原因：\n- 孩子正在忙其他事情\n- 忘记了时间\n- 不感兴趣\n\n建议家长协助提醒。"
        
        return self.send(title, content, "🟡", child_name, "task")
    
    def send_bedtime_reminder(self, child_name: str):
        """发送睡前提醒"""
        title = f"{child_name}该准备睡觉了"
        content = f"现在是{datetime.now().strftime('%H:%M')}，{child_name}的睡前仪式即将开始。\n\n建议：\n- 调暗灯光\n- 放下电子设备\n- 准备好舒适的睡眠环境"
        
        return self.send(title, content, "🟢", child_name, "routine")
    
    def send_daily_report(self, report: Dict):
        """发送每日报告"""
        title = f"【书童日报】{report.get('date', '')}"
        
        lines = []
        lines.append(f"今日陪伴 {report.get('total_children', 0)} 个孩子")
        lines.append(f"完成任务: {report.get('summary', {}).get('overall_completion_rate', 'N/A')}")
        
        # 异常汇总
        exceptions = report.get('exceptions', [])
        if exceptions:
            lines.append(f"\n需要关注 ({len(exceptions)}项):")
            for ex in exceptions[:5]:
                lines.append(f"  • {ex['child']}: {ex['issue']}")
        
        # 明日计划
        lines.append(f"\n明日重点任务:")
        for child in report.get('children', []):
            if child.get('upcoming_tasks'):
                tasks = [t['name'] for t in child['upcoming_tasks'][:2]]
                lines.append(f"  {child['name']}: {' | '.join(tasks)}")
        
        content = "\n".join(lines)
        
        return self.send(title, content, "🟢", None, "report")
    
    def send_emergency(self, child_name: str, reason: str):
        """发送紧急通知（安全风险）"""
        title = f"【紧急】{child_name} {reason}"
        content = f"检测到{child_name}出现紧急情况：\n\n{reason}\n\n请立即关注孩子状态，必要时寻求专业帮助。"
        
        return self.send(title, content, "🔴", child_name, "emergency")
    
    # ═══════════════════════════════════════════
    # 通知历史查询
    # ═══════════════════════════════════════════
    
    def get_unread_notifications(self, child_name: str = None) -> List[Dict]:
        """获取未读通知"""
        all_notifications = self._load_all_notifications()
        unread = [n for n in all_notifications if not n.get("read", False)]
        
        if child_name:
            unread = [n for n in unread if n.get("child_name") == child_name]
        
        return unread
    
    def mark_as_read(self, notification_id: str):
        """标记通知为已读"""
        # 简化版：实际实现需要修改文件
        pass
    
    def _load_all_notifications(self) -> List[Dict]:
        """加载所有通知"""
        notifications = []
        
        for file_path in self.journal_dir.glob("notifications_*.jsonl"):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        notifications.append(json.loads(line))
        
        return notifications
    
    # ═══════════════════════════════════════════
    # 配置方法
    # ═══════════════════════════════════════════
    
    def enable_channel(self, channel: str):
        """启用通知渠道"""
        if channel in self.channels:
            self.channels[channel] = True
            print(f"[通知] 已启用: {channel}")
        else:
            print(f"[通知] 未知渠道: {channel}")
    
    def disable_channel(self, channel: str):
        """禁用通知渠道"""
        if channel in self.channels:
            self.channels[channel] = False
            print(f"[通知] 已禁用: {channel}")
