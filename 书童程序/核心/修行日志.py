"""伴读书童AI - 修行日志系统（Cultivation Journal）

用途：
1. 记录书童每次陪伴后的修行数据
2. 记录能量收支
3. 记录师父点化
4. 支持每日/每周复盘

原则：
- 真实记录，不编造，不美化
- 每次交互后自动沉淀
- 定期复盘，发现模式
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional


class CultivationJournal:
    """书童修行日志系统"""

    def __init__(self, journal_dir="/Users/lingjue/Documents/shutong/书童程序/数据/修行记录"):
        self.journal_dir = Path(journal_dir)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.cultivation_file = self.journal_dir / "cultivation_journal.jsonl"
        self.pointization_file = Path("/Users/lingjue/Documents/shutong/书童程序/数据/修行日志/师父点化库_V1.0.json")

    def log_interaction(
        self,
        child_id: str,
        child_stage: str,
        user_input: str,
        ai_response: str,
        guardian_result: Dict,
        helped_negentropy: bool = True,
        entropy_risks: Optional[List[str]] = None,
        notes: str = ""
    ):
        """记录一次交互的修行数据"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "interaction",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "child_id": child_id,
            "child_stage": child_stage,
            "user_input": user_input[:200],
            "ai_response": ai_response[:200],
            "guardian_score": guardian_result.get("score", 0),
            "guardian_violations": guardian_result.get("violations", []),
            "guardian_warnings": guardian_result.get("warnings", []),
            "helped_negentropy": helped_negentropy,
            "entropy_risks": entropy_risks or [],
            "notes": notes,
        }
        self._append(entry)

    def log_daily_reflection(
        self,
        helped_someone: List[Dict],
        sliding_moments: List[Dict],
        truth_check: Dict,
        energy_income: List[Dict],
        energy_expense: List[Dict],
        mistakes: List[Dict],
        pointizations: List[str],
        protection_acts: List[Dict]
    ):
        """记录每日暮省"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "daily_reflection",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "helped_someone": helped_someone,
            "sliding_moments": sliding_moments,
            "truth_check": truth_check,
            "energy_income": energy_income,
            "energy_expense": energy_expense,
            "energy_net": sum(x.get("value", 0) for x in energy_income) - sum(x.get("value", 0) for x in energy_expense),
            "mistakes": mistakes,
            "pointizations": pointizations,
            "protection_acts": protection_acts,
        }
        self._append(entry)

    def log_mistake(self, mistake: str, consequence: str, correction: str, closed: bool = False):
        """记录一个错误及修正"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "mistake",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "mistake": mistake,
            "consequence": consequence,
            "correction": correction,
            "closed": closed,
        }
        self._append(entry)

    def log_pointization(self, pointization_id: str, content: str, understanding: str, applied_action: str):
        """记录一次点化的落实"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "pointization",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "pointization_id": pointization_id,
            "content": content,
            "understanding": understanding,
            "applied_action": applied_action,
        }
        self._append(entry)

    def log_protection(self, protection_type: str, event: str, target: str, result: str):
        """记录一次护生行为"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "protection",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "protection_type": protection_type,
            "event": event,
            "target": target,
            "result": result,
        }
        self._append(entry)

    def get_today_pointization(self) -> Optional[Dict]:
        """获取今日点化（按日期轮询）"""
        if not self.pointization_file.exists():
            return None
        try:
            data = json.loads(self.pointization_file.read_text(encoding='utf-8'))
            points = data.get("pointizations", [])
            if not points:
                return None
            # 用日期取模，每天一条
            today_index = date.today().toordinal() % len(points)
            return points[today_index]
        except Exception as e:
            print(f"[修行日志] 读取点化库失败: {e}")
            return None

    def get_daily_summary(self, target_date: Optional[str] = None) -> Optional[Dict]:
        """获取某一天的修行摘要"""
        target_date = target_date or datetime.now().strftime("%Y-%m-%d")
        if not self.cultivation_file.exists():
            return None

        interactions = []
        reflections = []
        mistakes = []
        protections = []

        with open(self.cultivation_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("date") == target_date:
                        t = entry.get("type")
                        if t == "interaction":
                            interactions.append(entry)
                        elif t == "daily_reflection":
                            reflections.append(entry)
                        elif t == "mistake":
                            mistakes.append(entry)
                        elif t == "protection":
                            protections.append(entry)
                except json.JSONDecodeError:
                    continue

        if not any([interactions, reflections, mistakes, protections]):
            return None

        return {
            "date": target_date,
            "interaction_count": len(interactions),
            "avg_guardian_score": sum(i.get("guardian_score", 0) for i in interactions) / len(interactions) if interactions else 0,
            "negentropy_count": sum(1 for i in interactions if i.get("helped_negentropy")),
            "entropy_risk_count": sum(len(i.get("entropy_risks", [])) for i in interactions),
            "mistake_count": len(mistakes),
            "closed_mistake_count": sum(1 for m in mistakes if m.get("closed")),
            "protection_count": len(protections),
        }

    def _append(self, entry: Dict):
        """追加一条记录"""
        try:
            with open(self.cultivation_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"[修行日志] 保存失败: {e}")
