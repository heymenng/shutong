"""伴读书童AI - 体质模型（用层补充）

职责：
根据中医理论，辨识孩子的体质类型，提供个性化调养建议。

九种体质：
1. 平和质（健康）
2. 气虚质（容易累）
3. 阳虚质（怕冷）
4. 阴虚质（怕热）
5. 痰湿质（肥胖/痰多）
6. 湿热质（长痘/口苦）
7. 血瘀质（面色暗）
8. 气郁质（情绪低落）
9. 特禀质（过敏）

应用：
- 个性化饮食建议
- 个性化运动建议
- 个性化情绪陪伴策略
"""

from typing import Dict, List


# 九种体质定义
CONSTITUTION_TYPES = {
    "平和质": {
        "features": ["精力充沛", "睡眠好", "食欲正常", "二便调", "性格开朗"],
        "tendencies": [],
        "care": ["保持当前生活方式", "饮食多样化", "适度运动"],
        "food_favorable": ["五谷", "蔬菜", "水果", "肉类均衡"],
        "food_avoid": [],
    },
    "气虚质": {
        "features": ["容易疲劳", "说话声音低", "易出汗", "易感冒", "恢复慢"],
        "tendencies": ["免疫力低", "发育迟缓", "学习能力下降"],
        "care": ["避免过度劳累", "保证充足睡眠", "循序渐进运动"],
        "food_favorable": ["山药", "红枣", "小米", "鸡肉", "牛肉", "黄芪粥"],
        "food_avoid": ["生冷", "寒凉", "油腻"],
        "acupressure": ["足三里", "气海", "关元"],
    },
    "阳虚质": {
        "features": ["怕冷", "手脚冰凉", "喜热饮", "精神不振", "大便稀"],
        "tendencies": ["生长缓慢", "消化功能弱", "易腹泻"],
        "care": ["保暖", "多晒太阳", "避免生冷"],
        "food_favorable": ["生姜", "羊肉", "韭菜", "核桃", "桂圆", "红糖"],
        "food_avoid": ["冰饮", "西瓜", "苦瓜", "绿豆"],
        "acupressure": ["关元", "命门", "肾俞"],
    },
    "阴虚质": {
        "features": ["怕热", "手心热", "口干", "睡眠浅", "易烦躁"],
        "tendencies": ["注意力不集中", "易上火", "皮肤干燥"],
        "care": ["避免熬夜", "减少剧烈运动", "保持情绪平稳"],
        "food_favorable": ["银耳", "百合", "梨", "莲藕", "鸭肉", "麦冬"],
        "food_avoid": ["辛辣", "油炸", "羊肉", "桂圆"],
        "acupressure": ["太溪", "三阴交", "涌泉"],
    },
    "痰湿质": {
        "features": ["体型偏胖", "痰多", "口黏", "大便黏", "嗜睡"],
        "tendencies": ["肥胖", "代谢问题", "注意力涣散"],
        "care": ["控制饮食", "增加运动", "避免潮湿环境"],
        "food_favorable": ["薏米", "赤小豆", "冬瓜", "萝卜", "陈皮", "茯苓"],
        "food_avoid": ["甜食", "油腻", "冷饮", "乳制品"],
        "acupressure": ["丰隆", "阴陵泉", "中脘"],
    },
    "湿热质": {
        "features": ["面部油腻", "长痘", "口苦", "大便黏臭", "易烦躁"],
        "tendencies": ["皮肤问题", "消化问题", "情绪暴躁"],
        "care": ["清淡饮食", "多喝水", "保持皮肤清洁"],
        "food_favorable": ["绿豆", "苦瓜", "冬瓜", "薏米", "莲子", "菊花茶"],
        "food_avoid": ["辛辣", "油炸", "烧烤", "甜食", "羊肉"],
        "acupressure": ["曲池", "合谷", "阴陵泉"],
    },
    "血瘀质": {
        "features": ["面色暗", "易有瘀斑", "口唇暗", "易疼痛", "健忘"],
        "tendencies": ["血液循环差", "生长痛", "学习记忆受影响"],
        "care": ["适度运动", "避免久坐", "保持温暖"],
        "food_favorable": ["山楂", "玫瑰花", "黑木耳", "红糖", "洋葱", "醋"],
        "food_avoid": ["寒凉", "油腻"],
        "acupressure": ["血海", "膈俞", "三阴交"],
    },
    "气郁质": {
        "features": ["情绪低落", "易焦虑", "胸闷", "叹气", "睡眠差"],
        "tendencies": ["抑郁倾向", "社交退缩", "消化问题"],
        "care": ["多陪伴", "鼓励表达", "户外活动", "避免压抑"],
        "food_favorable": ["玫瑰花", "陈皮", "佛手", "橙子", "菠菜", "小麦"],
        "food_avoid": ["浓茶", "咖啡", "辛辣"],
        "acupressure": ["太冲", "期门", "膻中"],
    },
    "特禀质": {
        "features": ["易过敏", "荨麻疹", "鼻炎", "哮喘", "皮肤敏感"],
        "tendencies": ["过敏反应", "免疫失衡", "营养吸收差"],
        "care": ["避免过敏原", "保持环境清洁", "增强免疫力"],
        "food_favorable": ["山药", "红枣", "枸杞", "益生菌食品"],
        "food_avoid": ["已知过敏原", "海鲜", "坚果（如过敏）"],
        "acupressure": ["足三里", "肺俞", "大椎"],
    },
}


class ConstitutionModel:
    """
    体质模型
    
    1. 根据症状/表现辨识体质
    2. 提供个性化调养建议
    3. 长期跟踪体质变化
    """
    
    def __init__(self, profile_manager):
        self.profile_manager = profile_manager
        self.constitutions = CONSTITUTION_TYPES
    
    def assess_constitution(self, child_id, symptoms: List[str] = None) -> Dict:
        """
        评估孩子体质
        
        通过症状列表匹配，返回最可能的体质类型及评分。
        """
        if symptoms is None:
            # 从档案标签中获取
            child = self.profile_manager.get_child(child_id)
            if not child:
                return {"error": "孩子不存在"}
            symptoms = child.tags
        
        scores = {}
        
        for const_name, const_info in self.constitutions.items():
            score = 0
            matched_features = []
            
            for feature in const_info["features"]:
                for symptom in symptoms:
                    if symptom in feature or feature in symptom:
                        score += 1
                        matched_features.append(feature)
            
            scores[const_name] = {
                "score": score,
                "matched": matched_features,
                "total_features": len(const_info["features"]),
                "ratio": score / len(const_info["features"]) if const_info["features"] else 0,
            }
        
        # 排序
        sorted_scores = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
        
        # 最可能的体质
        primary = sorted_scores[0]
        secondary = sorted_scores[1] if len(sorted_scores) > 1 else None
        
        return {
            "child_id": child_id,
            "primary_constitution": primary[0],
            "primary_score": primary[1],
            "secondary_constitution": secondary[0] if secondary else None,
            "secondary_score": secondary[1] if secondary else None,
            "all_scores": {k: v for k, v in sorted_scores},
            "assessment_date": datetime.now().isoformat(),
        }
    
    def get_personalized_care(self, child_id, constitution_name: str = None) -> Dict:
        """获取个性化调养方案"""
        child = self.profile_manager.get_child(child_id)
        if not child:
            return {"error": "孩子不存在"}
        
        if constitution_name is None:
            # 自动评估
            assessment = self.assess_constitution(child_id)
            constitution_name = assessment.get("primary_constitution", "平和质")
        
        const = self.constitutions.get(constitution_name)
        if not const:
            return {"error": f"未知体质: {constitution_name}"}
        
        return {
            "child_name": child.name,
            "constitution": constitution_name,
            "features": const["features"],
            "care_principles": const["care"],
            "diet": {
                "recommended": const.get("food_favorable", []),
                "avoid": const.get("food_avoid", []),
            },
            "acupressure": const.get("acupressure", []),
            "lifestyle": const["care"],
            "risks": const.get("tendencies", []),
        }
    
    def get_diet_suggestion(self, child_id, meal_type: str = "日常") -> List[str]:
        """根据体质获取饮食建议"""
        care = self.get_personalized_care(child_id)
        
        if "error" in care:
            return ["均衡饮食即可"]
        
        suggestions = []
        const = care["constitution"]
        
        if care["diet"]["recommended"]:
            suggestions.append(f"【{const}推荐】多吃：{'、'.join(care['diet']['recommended'][:5])}")
        
        if care["diet"]["avoid"]:
            suggestions.append(f"【{const}忌口】少吃：{'、'.join(care['diet']['avoid'][:5])}")
        
        return suggestions
    
    def get_emotion_strategy(self, child_id) -> Dict:
        """根据体质获取情绪陪伴策略"""
        care = self.get_personalized_care(child_id)
        
        if "error" in care:
            return {"strategy": "通用陪伴", "tips": ["倾听", "理解", "支持"]}
        
        const = care["constitution"]
        
        strategies = {
            "气虚质": {
                "strategy": "温柔鼓励，避免批评",
                "tips": ["多肯定", "给足够的时间", "不要催促", "允许休息"],
            },
            "阳虚质": {
                "strategy": "温暖陪伴，增加安全感",
                "tips": ["多拥抱", "温暖的环境", "鼓励尝试", "小步前进"],
            },
            "阴虚质": {
                "strategy": "平静安抚，避免刺激",
                "tips": ["低声说话", "安静的环境", "帮助放松", "避免争论"],
            },
            "痰湿质": {
                "strategy": "积极引导，增加运动",
                "tips": ["鼓励户外活动", "游戏化运动", "避免久坐", "设定小目标"],
            },
            "湿热质": {
                "strategy": "帮助释放，疏导情绪",
                "tips": ["允许表达愤怒", "运动释放", "冷水洗脸", "安静角落"],
            },
            "血瘀质": {
                "strategy": "耐心倾听，促进循环",
                "tips": ["多倾听", "温和运动", "热敷", "按摩"],
            },
            "气郁质": {
                "strategy": "重点关怀，预防抑郁",
                "tips": ["每天专门聊天时间", "鼓励表达", "户外活动", "必要时专业帮助"],
            },
            "特禀质": {
                "strategy": "细心观察，避免触发",
                "tips": ["注意环境", "记录过敏源", "温和安抚", "增强免疫力"],
            },
            "平和质": {
                "strategy": "保持现状，适当挑战",
                "tips": ["维持规律", "适度挑战", "均衡生活"],
            },
        }
        
        return strategies.get(const, {"strategy": "通用陪伴", "tips": ["倾听", "理解", "支持"]})


from datetime import datetime
