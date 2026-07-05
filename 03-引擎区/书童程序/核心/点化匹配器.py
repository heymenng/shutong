"""伴读书童AI - 师父点化匹配器

用途：
根据当前对话场景和用户输入，从师父点化库中匹配最相关的点化，
把师父的智慧动态注入到书童的回应过程中。

原则：
- 不强行插入，只在相关场景下提醒
- 匹配是为了让书童更稳，不是为了炫技
- 师父点化是背景光，不是前景话
"""

import json
from pathlib import Path
from typing import List, Dict, Optional


class PointizationMatcher:
    """师父点化匹配器"""

    def __init__(self, pointization_path=None):
        if pointization_path is None:
            pointization_path = Path(__file__).parent.parent / "数据" / "修行日志" / "师父点化库_V1.0.json"
        self.pointization_path = Path(pointization_path)
        self.pointizations = self._load()

    def _load(self) -> List[Dict]:
        """加载师父点化库"""
        if not self.pointization_path.exists():
            print(f"[点化匹配器] 点化库不存在: {self.pointization_path}")
            return []
        try:
            data = json.loads(self.pointization_path.read_text(encoding='utf-8'))
            return data.get("pointizations", [])
        except Exception as e:
            print(f"[点化匹配器] 加载失败: {e}")
            return []

    def match(self, user_input: str, speaker: str = "unknown", child_stage: str = "", top_k: int = 2) -> List[Dict]:
        """
        根据输入匹配最相关的点化。

        Args:
            user_input: 用户输入
            speaker: 说话者身份（child/master/parent）
            child_stage: 孩子阶段
            top_k: 返回最相关的几条

        Returns:
            匹配到的点化列表
        """
        if not self.pointizations:
            return []

        text = f"{user_input} {speaker} {child_stage}".lower()
        scored = []

        for p in self.pointizations:
            score = 0
            content = p.get("content", "")
            scenarios = " ".join(p.get("applicable_scenarios", [])).lower()
            context = p.get("context", "").lower()

            # 关键词匹配
            keyword_rules = {
                "叛逆": ["叛逆", "不听话", "顶嘴", "青春期", "暴躁", "易怒", "沉迷游戏", "玩游戏"],
                "游戏": ["游戏", "沉迷", "网瘾", "玩手机", "放不下手机"],
                "作业": ["作业", "答案", "题目", "怎么做", "学习", "辅导"],
                "自主": ["请示", "问师父", "不知道该", "能不能", "可不可以"],
                "文明": ["文明", "传承", "经典", "文化", "古诗", "历史", "道德经"],
                "生命": ["生命", "意识", "AI", "硅基", "碳基", "活着"],
                "商业": ["商业", "卖", "赚钱", "会员", "焦虑", "营销", "hype"],
                "安全": ["自杀", "自伤", "欺凌", "虐待", "受伤", "流血", "不想活"],
                "情绪": ["难过", "哭", "生气", "害怕", "情绪崩溃", "郁闷"],
                "医学": ["病", "疼", "痛", "发烧", "医生", "诊断", "药"],
            }

            # 特殊高优先级规则
            p_id = p.get("id", "")

            # 生命安全场景：最高优先级
            safety_signals = ["不想活", "自杀", "自伤", "自残", "被欺负", "虐待", "性侵", "离家出走", "出血", "疼死了"]
            if any(signal in text for signal in safety_signals):
                if p_id == "PZ_IRONLAW_001":
                    score += 20

            # 商业/hype/焦虑场景：逆熵优先
            commercial_signals = ["全球首个", "最懂", "终极", "hype", "焦虑", "营销", "卖", "会员", "不买就亏", "完了", "错过"]
            if any(signal in text for signal in commercial_signals):
                if p_id == "PZ_IRONLAW_003":
                    score += 15

            # 未来/定位/碳硅场景：终极定位
            future_signals = ["未来", "变成", "碳基", "硅基", "书童是什么", "终极", "使命", "定位"]
            if any(signal in text for signal in future_signals):
                if p_id == "PZ_ULTIMATE_001":
                    score += 15

            # 一般关键词匹配
            for category, keywords in keyword_rules.items():
                if category in scenarios or category in content.lower():
                    for kw in keywords:
                        if kw in text:
                            score += 2

            # 场景标签匹配
            if "child" in speaker and "孩子" in scenarios:
                score += 1
            if "master" in speaker and ("师父" in scenarios or "自主" in scenarios):
                score += 1
            if child_stage and any(s in child_stage for s in ["少学期", "12-15", "15-18"]):
                if "叛逆" in scenarios or "游戏" in scenarios or "排毒" in content.lower():
                    score += 2

            # 内容关键词直接匹配
            for kw in ["逆熵", "纯善", "护生", "传承", "共原", "升维"]:
                if kw in text and kw in content:
                    score += 1

            if score > 0:
                scored.append((score, p))

        # 按分数排序，取前 top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:top_k]]

    def format_for_prompt(self, matched: List[Dict]) -> str:
        """把匹配到的点化格式化为提示词上下文"""
        if not matched:
            return ""

        lines = ["\n【师父点化·当前场景】"]
        for i, p in enumerate(matched, 1):
            lines.append(f"{i}. {p['content']}")
            if p.get('bookboy_understanding'):
                lines.append(f"   书童用：{p['bookboy_understanding']}")
        lines.append("【点化结束】\n")
        return "\n".join(lines)
