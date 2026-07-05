"""伴读书童AI - 文化传承引擎（魂层）

职责：
1. 文化场景触发器：根据对话内容自动匹配文化内容
2. 混龄共修执行：大带小内容推荐
3. 文明传承路径：按周/月生成"文明种子"
4. 故事智能匹配：根据情境推荐最合适的故事/古诗/经典

理念：
- 不是灌输，是唤醒
- 不是保护标本，是让文明基因在孩子身上变异、进化、新生
- 给路径，不是给答案
"""

import random
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# ═══════════════════════════════════════════════════════════
# 文化场景触发词库
# ═══════════════════════════════════════════════════════════

CULTURE_TRIGGERS = {
    "诚实": {
        "keywords": ["诚实", "撒谎", "骗人", "真话", "假话", "信用"],
        "stories": ["史记·季布一诺千金", "史记·商鞅立木为信"],
        "poems": ["君子一言，驷马难追"],
        "dialogue": "不是告诉孩子'要诚实'，是讲一个'诚实带来好结果'的故事，问孩子'你觉得他为什么这样做？'",
    },
    "勇敢": {
        "keywords": ["勇敢", "害怕", "胆小", "勇气", "不敢", "恐惧"],
        "stories": ["史记·项羽破釜沉舟", "史记·荆轲刺秦王"],
        "poems": ["千磨万击还坚劲，任尔东西南北风"],
        "dialogue": "勇敢不是不害怕，是害怕的时候还去做。",
    },
    "分享": {
        "keywords": ["分享", "自私", "独占", "给予", "帮助", "慷慨"],
        "stories": ["庄子·相濡以沫", "史记·管仲鲍叔牙"],
        "poems": ["赠人玫瑰，手有余香"],
        "dialogue": "分享的时候，你的身体会分泌催产素，让你感到快乐。",
    },
    "公平": {
        "keywords": ["公平", "不公平", "平等", "正义", "欺负", "偏袒"],
        "stories": ["史记·孔子世家", "史记·缇萦救父"],
        "poems": ["王子犯法，与庶民同罪"],
        "dialogue": "公平不是每个人都一样，是每个人都得到他需要的。",
    },
    "尊重": {
        "keywords": ["尊重", "礼貌", "长辈", "老师", "恭敬", "孝顺"],
        "stories": ["史记·孔子世家·尊师", "二十四孝·黄香温席"],
        "poems": ["谁言寸草心，报得三春晖"],
        "dialogue": "尊重别人，就是尊重自己。",
    },
    "自然": {
        "keywords": ["自然", "动物", "植物", "花", "树", "鸟", "昆虫", "季节"],
        "stories": ["庄子·庖丁解牛", "庄子·庄周梦蝶"],
        "poems": ["春眠不觉晓", "小荷才露尖尖角", "停车坐爱枫林晚"],
        "dialogue": "自然是人类最好的老师。",
    },
    "节气": {
        "keywords": ["节气", "春天", "夏天", "秋天", "冬天", "立春", "冬至", "清明"],
        "stories": ["二十四节气故事"],
        "poems": ["清明时节雨纷纷", "冬至阳生春又来"],
        "dialogue": "二十四节气是古人观察自然的智慧。",
    },
    "学习": {
        "keywords": ["学习", "读书", "知识", "努力", "考试", "成绩", "学校"],
        "stories": ["史记·孔子韦编三绝", "史记·苏秦刺股"],
        "poems": ["少壮不努力，老大徒伤悲", "书山有路勤为径"],
        "dialogue": "学习不是为了考试，是为了让自己有更多选择。",
    },
    "坚持": {
        "keywords": ["坚持", "放弃", "毅力", "耐心", "恒心", "半途而废"],
        "stories": ["史记·大禹治水", "史记·司马迁发愤著书"],
        "poems": ["锲而不舍，金石可镂", "水滴石穿"],
        "dialogue": "竹子用四年时间只长3厘米，第五年开始每天长30厘米。",
    },
    "谦逊": {
        "keywords": ["谦虚", "骄傲", "自满", "傲慢", "看不起", "谦虚"],
        "stories": ["史记·孔子入太庙每事问", "史记·张良拾履"],
        "poems": ["满招损，谦受益"],
        "dialogue": "真正厉害的人，都知道自己还有很多不知道。",
    },
}

# 每周文明种子
WEEKLY_CULTURE_SEEDS = {
    "week_1": {"theme": "春耕", "concept": "播种与希望", "activity": "种一颗种子，观察生长"},
    "week_2": {"theme": "诚信", "concept": "言出必行", "activity": "做一件承诺的事并完成"},
    "week_3": {"theme": "感恩", "concept": "滴水之恩", "activity": "给帮助过你的人写感谢卡"},
    "week_4": {"theme": "勇气", "concept": "面对恐惧", "activity": "尝试一件你害怕的小事"},
    "week_5": {"theme": "自然", "concept": "天人合一", "activity": "去户外观察一种动植物"},
    "week_6": {"theme": "节气", "concept": "顺应天时", "activity": "了解本周的节气习俗"},
    "week_7": {"theme": "家庭", "concept": "家和万事兴", "activity": "采访爷爷奶奶，记录家族故事"},
    "week_8": {"theme": "坚持", "concept": "水滴石穿", "activity": "连续7天做一件小事"},
}


class CultureHeritageEngine:
    """
    文化传承引擎
    
    三大能力：
    1. 场景触发：对话中自动识别文化切入点
    2. 混龄推荐：大孩子内容适配给小孩子
    3. 文明路径：按时间线生成传承计划
    """
    
    def __init__(self, knowledge_base=None):
        self.triggers = CULTURE_TRIGGERS
        self.weekly_seeds = WEEKLY_CULTURE_SEEDS
        self.knowledge_base = knowledge_base
    
    # ═══════════════════════════════════════════
    # 1. 文化场景触发
    # ═══════════════════════════════════════════
    
    def detect_culture_opportunity(self, dialogue_text: str) -> Optional[Dict]:
        """
        检测对话中的文化传承机会
        
        返回：
        {
            "theme": "诚实",
            "confidence": 0.8,
            "matched_keyword": "撒谎",
            "suggestion": "建议引入季布一诺千金的故事",
        }
        """
        text = dialogue_text.lower()
        
        best_match = None
        best_confidence = 0
        
        for theme, data in self.triggers.items():
            matched_keywords = []
            for kw in data["keywords"]:
                if kw in text:
                    matched_keywords.append(kw)
            
            if matched_keywords:
                confidence = len(matched_keywords) / len(data["keywords"])
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = {
                        "theme": theme,
                        "confidence": round(confidence, 2),
                        "matched_keywords": matched_keywords,
                        "stories": data["stories"],
                        "poems": data["poems"],
                        "dialogue_approach": data["dialogue"],
                    }
        
        return best_match
    
    def generate_culture_response(self, opportunity: Dict, child_age: int) -> str:
        """
        生成文化传承回应
        
        根据孩子年龄调整深度：
        - 3-6岁：故事为主，不讲道理
        - 6-12岁：故事+提问
        - 12-18岁：故事+哲学思考
        """
        theme = opportunity["theme"]
        stories = opportunity["stories"]
        poems = opportunity["poems"]
        
        story = stories[0] if stories else ""
        poem = poems[0] if poems else ""
        
        if child_age < 6:
            # 幼儿：讲故事
            return self._tell_story_simple(theme, story)
        elif child_age < 12:
            # 小学：故事+提问
            return self._tell_story_with_question(theme, story, poem)
        else:
            # 中学：故事+哲学
            return self._tell_story_with_philosophy(theme, story, poem)
    
    def _tell_story_simple(self, theme, story):
        """3-6岁版本：纯故事"""
        return f"我给你讲个关于{theme}的故事...\n\n很久很久以前...{story}...\n\n你觉得他做得对吗？"
    
    def _tell_story_with_question(self, theme, story, poem):
        """6-12岁版本：故事+提问"""
        return f"说到{theme}...我想起一个故事...\n\n{story}...\n\n古人还有一句诗：{poem}...\n\n如果是你，你会怎么做？"
    
    def _tell_story_with_philosophy(self, theme, story, poem):
        """12-18岁版本：故事+哲学"""
        return f"{theme}...这个话题很有意思。\n\n历史上有个故事：{story}...\n\n{poem}...\n\n你觉得，{theme}在今天的意义是什么？"
    
    # ═══════════════════════════════════════════
    # 2. 混龄共修执行
    # ═══════════════════════════════════════════
    
    def generate_senior_to_junior_content(self, senior_child, junior_child) -> Dict:
        """
        生成大带小内容
        
        大孩子教小孩子，书童提供框架。
        """
        age_gap = self._calculate_age_gap(senior_child, junior_child)
        
        return {
            "senior": senior_child.name,
            "junior": junior_child.name,
            "age_gap": age_gap,
            "activity_type": self._select_activity_by_gap(age_gap),
            "senior_role": "小老师",
            "junior_role": "小学员",
            "suggested_topics": self._get_shared_topics(senior_child, junior_child),
            "bookboy_prompt": f"鼓励{senior_child.name}教{junior_child.name}，但不强迫",
        }
    
    def _calculate_age_gap(self, senior, junior):
        """计算年龄差"""
        from datetime import datetime
        s_age = (datetime.now() - datetime.strptime(senior.birth_date, "%Y-%m-%d")).days / 365.25
        j_age = (datetime.now() - datetime.strptime(junior.birth_date, "%Y-%m-%d")).days / 365.25
        return round(s_age - j_age, 1)
    
    def _select_activity_by_gap(self, age_gap):
        """根据年龄差选择活动类型"""
        if age_gap >= 6:
            return "故事讲述+简单辅导"
        elif age_gap >= 3:
            return "共同游戏+学习陪伴"
        else:
            return "平行活动+互相学习"
    
    def _get_shared_topics(self, senior, junior):
        """获取两个孩子共同感兴趣的话题"""
        # 简化版：返回通用话题
        return ["自然观察", "传统节日", "家族故事", "手工制作"]
    
    # ═══════════════════════════════════════════
    # 3. 文明传承路径
    # ═══════════════════════════════════════════
    
    def get_weekly_culture_seed(self, week_number: int = None) -> Dict:
        """获取本周文明种子"""
        if week_number is None:
            week_number = datetime.now().isocalendar()[1]  # 一年中的第几周
        
        week_key = f"week_{(week_number % 8) + 1}"  # 8周循环
        return self.weekly_seeds.get(week_key, self.weekly_seeds["week_1"])
    
    def generate_culture_path(self, child_profile, weeks: int = 4) -> List[Dict]:
        """
        生成未来N周的文明传承路径
        
        根据孩子年龄和季节定制。
        """
        path = []
        current_week = datetime.now().isocalendar()[1]
        
        for i in range(weeks):
            week_num = (current_week + i) % 52 + 1
            seed = self.get_weekly_culture_seed(week_num)
            
            # 根据年龄调整活动难度
            adapted_activity = self._adapt_activity(seed["activity"], child_profile)
            
            path.append({
                "week": week_num,
                "theme": seed["theme"],
                "concept": seed["concept"],
                "activity": adapted_activity,
                "story_suggestion": self._get_story_for_theme(seed["theme"]),
            })
        
        return path
    
    def _adapt_activity(self, activity, child_profile):
        """根据年龄调整活动"""
        age = child_profile.get_age_display()
        
        if "岁" in age and int(age.split("岁")[0]) < 6:
            # 幼儿简化
            return activity.replace("写", "画").replace("采访", "听")
        
        return activity
    
    def _get_story_for_theme(self, theme):
        """为主题匹配故事"""
        trigger = self.triggers.get(theme)
        if trigger:
            return trigger["stories"][0] if trigger["stories"] else ""
        return ""
    
    # ═══════════════════════════════════════════
    # 4. 古诗智能推荐
    # ═══════════════════════════════════════════
    
    def recommend_poem(self, context: str, child_age: int) -> Dict:
        """根据情境推荐古诗"""
        # 检测情境
        opportunity = self.detect_culture_opportunity(context)
        
        if opportunity and opportunity.get("poems"):
            poem = opportunity["poems"][0]
            return {
                "poem": poem,
                "theme": opportunity["theme"],
                "occasion": "对话触发",
            }
        
        # 默认推荐（按季节）
        month = datetime.now().month
        seasonal_poems = {
            "spring": ["春眠不觉晓", "好雨知时节", "草长莺飞二月天"],
            "summer": ["小荷才露尖尖角", "接天莲叶无穷碧", "意欲捕鸣蝉"],
            "autumn": ["停车坐爱枫林晚", "月落乌啼霜满天", "空山新雨后"],
            "winter": ["墙角数枝梅", "千山鸟飞绝", "晚来天欲雪"],
        }
        
        season = "spring" if month in [3,4,5] else "summer" if month in [6,7,8] else "autumn" if month in [9,10,11] else "winter"
        poems = seasonal_poems[season]
        
        return {
            "poem": random.choice(poems),
            "theme": season,
            "occasion": "季节推荐",
        }
    
    # ═══════════════════════════════════════════
    # 5. 家族档案引导
    # ═══════════════════════════════════════════
    
    def generate_family_heritage_prompt(self, child_profile) -> str:
        """
        生成家族文化传承引导
        
        鼓励孩子了解家族历史，成为文明传承节点。
        """
        age = child_profile.get_age_display()
        
        prompts = [
            f"{child_profile.name}，你知道爷爷奶奶小时候玩什么游戏吗？",
            f"你们家有什么特别的传统吗？比如过年一定要做的事？",
            f"你姓{child_profile.name[0] if child_profile.name else 'X'}，知道这个字的意思吗？",
            f"如果你是一本家族故事书，你想写什么进去？",
        ]
        
        return random.choice(prompts)
