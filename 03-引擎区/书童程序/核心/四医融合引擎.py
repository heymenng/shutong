"""伴读书童AI - 四医融合引擎（用层）

职责：
融合四种医学体系：
1. 西医（精准）- 指标、数据、证据
2. 中医（整体）- 辨证、经络、脏腑
3. 功能医学（根因）- 肠道、营养、毒素
4. 炁脉（系统）- 能量流动、经络通畅

输入：症状描述 + 孩子档案
输出：四医合参报告 + 个性化建议（不诊断、不开方）

原则：
- 只提供信息和建议，不诊断、不开方
- 严重情况必须建议就医
- 给孩子和家长都能理解的解释
"""

import json
import re
from typing import Dict, List, Optional


# ═══════════════════════════════════════════════════════════
# 中医辨证知识库（简化版）
# ═══════════════════════════════════════════════════════════

TCM_PATTERNS = {
    "风寒感冒": {
        "symptoms": ["怕冷", "无汗", "流清涕", "白痰", "头痛", "身痛"],
        "tongue": "舌苔薄白",
        "principle": "辛温解表",
        "food_remedy": ["葱白生姜水", "紫苏叶粥"],
        "acupressure": ["风池穴", "大椎穴"],
        "severity": "轻",
    },
    "风热感冒": {
        "symptoms": ["发热", "有汗", "流黄涕", "黄痰", "咽痛", "口渴"],
        "tongue": "舌苔薄黄",
        "principle": "辛凉解表",
        "food_remedy": ["金银花水", "梨汤"],
        "acupressure": ["曲池穴", "合谷穴"],
        "severity": "轻",
    },
    "积食": {
        "symptoms": ["口臭", "腹胀", "不思饮食", "便秘或腹泻", "睡不安"],
        "tongue": "舌苔厚腻",
        "principle": "消食导滞",
        "food_remedy": ["山楂水", "萝卜汤"],
        "acupressure": ["足三里", "中脘穴", "捏脊"],
        "severity": "轻",
    },
    "脾虚": {
        "symptoms": ["食欲差", "消瘦", "乏力", "大便溏", "易感冒"],
        "tongue": "舌淡苔白",
        "principle": "健脾益气",
        "food_remedy": ["山药粥", "小米粥", "茯苓饼"],
        "acupressure": ["足三里", "脾俞穴"],
        "severity": "中",
    },
    "心火旺盛": {
        "symptoms": ["口舌生疮", "烦躁", "失眠", "小便黄", "口渴"],
        "tongue": "舌尖红",
        "principle": "清心泻火",
        "food_remedy": ["莲子心水", "绿豆汤"],
        "acupressure": ["劳宫穴", "少府穴"],
        "severity": "轻",
    },
    "肝气郁结": {
        "symptoms": ["情绪低落", "胸闷", "叹气", "食欲差", "睡眠差"],
        "tongue": "舌边红",
        "principle": "疏肝解郁",
        "food_remedy": ["玫瑰花茶", "陈皮水"],
        "acupressure": ["太冲穴", "期门穴"],
        "severity": "中",
    },
}

# 功能医学视角
FUNCTIONAL_PERSPECTIVES = {
    "消化问题": {
        "root_causes": ["肠道菌群失衡", "食物不耐受", "消化酶不足", "肠漏"],
        "tests": ["粪便菌群检测", "食物不耐受检测"],
        "nutrition": ["益生菌", "消化酶", "锌", "谷氨酰胺"],
    },
    "免疫力低": {
        "root_causes": ["维生素D缺乏", "锌缺乏", "肠道菌群失衡", "慢性感染"],
        "tests": ["维生素D检测", "微量元素", "免疫功能检测"],
        "nutrition": ["维生素D", "锌", "维生素C", "益生菌"],
    },
    "注意力问题": {
        "root_causes": ["Omega-3缺乏", "铁缺乏", "血糖波动", "食物添加剂敏感"],
        "tests": ["红细胞脂肪酸", "血清铁蛋白", "血糖监测"],
        "nutrition": ["鱼油", "铁", "复合维生素B", "镁"],
    },
    "睡眠问题": {
        "root_causes": ["褪黑素分泌异常", "镁缺乏", "皮质醇节律紊乱", "蓝光暴露"],
        "tests": ["皮质醇节律", "褪黑素水平"],
        "nutrition": ["镁", "褪黑素", "GABA", "色氨酸"],
    },
}

# 炁脉视角
QIMai_PERSPECTIVES = {
    "头痛": {"meridians": ["膀胱经", "胆经", "肝经"], "qi_status": "气滞或上逆"},
    "腹痛": {"meridians": ["脾经", "胃经", "任脉"], "qi_status": "气滞或寒凝"},
    "失眠": {"meridians": ["心经", "肝经", "肾经"], "qi_status": "心火亢或肝魂不安"},
    "疲劳": {"meridians": ["脾经", "肾经", "督脉"], "qi_status": "气虚或肾精不足"},
    "情绪低落": {"meridians": ["肝经", "心经", "心包经"], "qi_status": "肝气郁结或心神失养"},
}

# 西医警示信号（出现这些必须建议就医）
WESTERN_RED_FLAGS = {
    "发热": {"threshold": 39.0, "duration_days": 3, "message": "持续高烧或反复发热超过3天，建议就医"},
    "腹痛": {"severe_signs": ["右下腹剧痛", "板状腹", "呕血", "便血"], "message": "出现剧烈腹痛或伴随出血，立即就医"},
    "头痛": {"severe_signs": ["喷射性呕吐", "意识模糊", "颈部僵硬"], "message": "头痛伴随呕吐或意识改变，立即就医"},
    "皮疹": {"severe_signs": ["紫癜", "迅速扩散", "伴随高热"], "message": "特殊皮疹或伴随高热，建议就医"},
    "呼吸": {"severe_signs": ["呼吸困难", "口唇青紫", "喘息不止"], "message": "呼吸困难或口唇青紫，立即就医"},
}


class FourMedicineEngine:
    """
    四医融合引擎
    
    核心流程：
    1. 接收症状描述
    2. 西医筛查（红橙灯？）
    3. 中医辨证（证型识别）
    4. 功能医学分析（根因追溯）
    5. 炁脉视角（经络能量）
    6. 融合输出（四医合参报告）
    """
    
    def __init__(self):
        self.tcm_patterns = TCM_PATTERNS
        self.functional = FUNCTIONAL_PERSPECTIVES
        self.qimai = QIMai_PERSPECTIVES
        self.red_flags = WESTERN_RED_FLAGS
    
    def analyze(self, symptoms_desc: str, child_age: int, child_stage: str) -> Dict:
        """
        四医合参分析
        
        Args:
            symptoms_desc: 症状描述（如"发烧38度5，头痛，怕冷，流清鼻涕"）
            child_age: 年龄
            child_stage: 阶段S0-S6
        
        Returns:
            四医合参报告
        """
        report = {
            "input": symptoms_desc,
            "child_age": child_age,
            "child_stage": child_stage,
            "western_screening": {},
            "tcm_analysis": {},
            "functional_analysis": {},
            "qimai_analysis": {},
            "integrated_suggestions": [],
            "must_see_doctor": False,
            "doctor_reason": "",
        }
        
        # 1. 西医筛查（红橙灯检查）
        western_result = self._western_screening(symptoms_desc)
        report["western_screening"] = western_result
        report["must_see_doctor"] = western_result.get("red_flag", False)
        report["doctor_reason"] = western_result.get("reason", "")
        
        # 如果出现红灯，直接建议就医，不再深入分析
        if report["must_see_doctor"]:
            report["integrated_suggestions"] = [{
                "priority": "紧急",
                "action": "建议立即就医",
                "reason": report["doctor_reason"],
            }]
            return report
        
        # 2. 中医辨证
        tcm_result = self._tcm_pattern_identification(symptoms_desc)
        report["tcm_analysis"] = tcm_result
        
        # 3. 功能医学分析
        functional_result = self._functional_analysis(symptoms_desc, child_stage)
        report["functional_analysis"] = functional_result
        
        # 4. 炁脉视角
        qimai_result = self._qimai_analysis(symptoms_desc)
        report["qimai_analysis"] = qimai_result
        
        # 5. 融合输出
        report["integrated_suggestions"] = self._generate_integrated_suggestions(
            report, child_age, child_stage
        )
        
        return report
    
    def _western_screening(self, symptoms_desc: str) -> Dict:
        """西医筛查：检查是否有必须就医的信号"""
        result = {"red_flag": False, "reason": "", "warnings": []}
        
        # 检查发热
        temp_match = re.search(r'(\d+\.?\d*)\s*度', symptoms_desc)
        if temp_match:
            temp = float(temp_match.group(1))
            if temp >= 39.0:
                result["warnings"].append(f"体温{temp}度，超过39度")
            elif temp >= 38.5:
                result["warnings"].append(f"体温{temp}度，需密切观察")
        
        # 检查严重信号词
        severe_keywords = ["呼吸困难", "口唇青紫", "意识模糊", "喷射性呕吐", 
                          "颈部僵硬", "板状腹", "便血", "呕血", "抽搐", "昏迷"]
        for keyword in severe_keywords:
            if keyword in symptoms_desc:
                result["red_flag"] = True
                result["reason"] += f"发现严重信号：{keyword}。"
        
        if result["red_flag"]:
            result["reason"] += "请立即就医。"
        
        return result
    
    def _tcm_pattern_identification(self, symptoms_desc: str) -> Dict:
        """中医辨证：识别证型"""
        result = {
            "identified_patterns": [],
            "primary_pattern": None,
            "confidence": 0,
        }
        
        # 匹配症状
        for pattern_name, pattern_info in self.tcm_patterns.items():
            match_count = 0
            matched_symptoms = []
            
            for symptom in pattern_info["symptoms"]:
                if symptom in symptoms_desc:
                    match_count += 1
                    matched_symptoms.append(symptom)
            
            if match_count > 0:
                confidence = match_count / len(pattern_info["symptoms"])
                result["identified_patterns"].append({
                    "name": pattern_name,
                    "matched_symptoms": matched_symptoms,
                    "confidence": round(confidence, 2),
                    "principle": pattern_info["principle"],
                    "food_remedy": pattern_info["food_remedy"],
                    "acupressure": pattern_info["acupressure"],
                    "severity": pattern_info["severity"],
                })
        
        # 排序，找最可能的证型
        if result["identified_patterns"]:
            result["identified_patterns"].sort(key=lambda x: x["confidence"], reverse=True)
            result["primary_pattern"] = result["identified_patterns"][0]
            result["confidence"] = result["primary_pattern"]["confidence"]
        
        return result
    
    def _functional_analysis(self, symptoms_desc: str, child_stage: str) -> Dict:
        """功能医学分析"""
        result = {
            "possible_roots": [],
            "relevant_nutrition": [],
            "lifestyle_factors": [],
        }
        
        # 匹配功能医学分类
        for category, info in self.functional.items():
            # 简单关键词匹配
            category_keywords = {
                "消化问题": ["肚子", "腹痛", "腹泻", "便秘", "消化不良", "口臭"],
                "免疫力低": ["感冒", "发烧", "反复", "易感染", "体质差"],
                "注意力问题": ["注意力", "多动", "走神", "学习困难"],
                "睡眠问题": ["失眠", "睡不着", "早醒", "睡眠差"],
            }
            
            keywords = category_keywords.get(category, [])
            if any(kw in symptoms_desc for kw in keywords):
                result["possible_roots"].append({
                    "category": category,
                    "root_causes": info["root_causes"],
                    "nutrition": info["nutrition"],
                })
                result["relevant_nutrition"].extend(info["nutrition"])
        
        # 去重
        result["relevant_nutrition"] = list(set(result["relevant_nutrition"]))
        
        # 生活方式因素（根据阶段）
        if child_stage in ["S5", "S6"]:
            result["lifestyle_factors"].extend(["睡眠不足", "学业压力", "屏幕时间过长"])
        elif child_stage in ["S3", "S4"]:
            result["lifestyle_factors"].extend(["户外活动不足", "零食过多", "作息不规律"])
        
        return result
    
    def _qimai_analysis(self, symptoms_desc: str) -> Dict:
        """炁脉视角分析"""
        result = {
            "affected_meridians": [],
            "qi_status": "",
            "suggestions": [],
        }
        
        # 匹配主要症状
        for symptom, info in self.qimai.items():
            if symptom in symptoms_desc:
                result["affected_meridians"].extend(info["meridians"])
                result["qi_status"] = info["qi_status"]
        
        # 去重
        result["affected_meridians"] = list(set(result["affected_meridians"]))
        
        # 生成炁脉建议
        if result["affected_meridians"]:
            result["suggestions"] = [
                f"相关经络：{'、'.join(result['affected_meridians'])}",
                f"炁的状态：{result['qi_status']}",
                "建议：轻柔按摩相关经络，或寻求专业炁脉调理",
            ]
        
        return result
    
    def _generate_integrated_suggestions(self, report, child_age, child_stage) -> List[Dict]:
        """生成融合建议"""
        suggestions = []
        
        # 优先级1：西医紧急情况（已在前面处理）
        
        # 优先级2：中医食疗+穴位
        tcm = report.get("tcm_analysis", {})
        if tcm.get("primary_pattern"):
            pattern = tcm["primary_pattern"]
            suggestions.append({
                "priority": "高",
                "category": "中医食疗",
                "action": f"可尝试：{'、'.join(pattern['food_remedy'][:2])}",
                "reason": f"辨证为{pattern['name']}，{pattern['principle']}",
                "safety": "食物调理，安全温和",
            })
            
            suggestions.append({
                "priority": "中",
                "category": "穴位按摩",
                "action": f"可按揉：{'、'.join(pattern['acupressure'][:2])}",
                "reason": "帮助疏通经络，缓解不适",
                "safety": "轻揉即可，孩子感到舒适为度",
            })
        
        # 优先级3：功能医学营养
        functional = report.get("functional_analysis", {})
        if functional.get("relevant_nutrition"):
            suggestions.append({
                "priority": "中",
                "category": "营养支持",
                "action": f"关注：{', '.join(functional['relevant_nutrition'][:3])}",
                "reason": "从功能医学角度，可能存在相关营养缺乏",
                "safety": "优先从食物中获取，必要时咨询营养师",
            })
        
        # 优先级4：炁脉调理
        qimai = report.get("qimai_analysis", {})
        if qimai.get("suggestions"):
            suggestions.append({
                "priority": "低",
                "category": "炁脉调理",
                "action": "轻柔推拿或寻求专业炁脉调理",
                "reason": qimai["suggestions"][1] if len(qimai["suggestions"]) > 1 else "",
                "safety": "轻柔操作，以孩子舒适为度",
            })
        
        # 通用建议
        suggestions.append({
            "priority": "高",
            "category": "基础照护",
            "action": "多休息、多喝水、观察症状变化",
            "reason": "身体需要能量对抗不适",
            "safety": "最基础也最重要",
        })
        
        # 12-18岁排毒期特殊建议
        if child_stage in ["S5", "S6"]:
            suggestions.append({
                "priority": "高",
                "category": "排毒支持",
                "action": "22:30前入睡，保证睡眠是最好的修复",
                "reason": "睡眠时脑脊液帮助大脑排毒",
                "safety": "自然规律，无副作用",
            })
        
        # 就医建议
        western = report.get("western_screening", {})
        if western.get("warnings"):
            suggestions.append({
                "priority": "观察",
                "category": "就医提醒",
                "action": "如果症状持续或加重，建议就医检查",
                "reason": "西医筛查发现需要关注的信号",
                "safety": "专业诊断不可替代",
            })
        
        return suggestions
    
    def format_for_child(self, report: Dict) -> str:
        """把四医报告格式化为孩子能听懂的话"""
        if report.get("must_see_doctor"):
            return f"{report['doctor_reason']}\n\n别怕，我陪着你去医院。"
        
        lines = []
        lines.append("书童看了你的身体...")
        lines.append("")
        
        # 中医部分
        tcm = report.get("tcm_analysis", {})
        if tcm.get("primary_pattern"):
            pattern = tcm["primary_pattern"]
            lines.append(f"你的身体在说：{pattern['name']}。")
            lines.append(f"意思是...{self._explain_in_child_language(pattern['name'])}。")
            lines.append("")
        
        # 建议
        for sg in report.get("integrated_suggestions", [])[:3]:
            if sg["priority"] in ["高", "紧急"]:
                lines.append(f"可以做：{sg['action']}")
                if sg.get("reason"):
                    lines.append(f"因为...{self._simplify_reason(sg['reason'])}")
                lines.append("")
        
        lines.append("如果明天还不好...")
        lines.append("我们去看医生。")
        lines.append("")
        lines.append("别怕...")
        lines.append("我陪着你。")
        
        return "\n".join(lines)
    
    def _explain_in_child_language(self, pattern_name: str) -> str:
        """用孩子能懂的话解释中医证型"""
        explanations = {
            "风寒感冒": "有冷风吹过你的身体，门窗关着，要把寒气赶出去",
            "风热感冒": "身体里有小火苗在烧，需要凉凉的水来浇灭",
            "积食": "肚子里堆了太多食物，消化小精灵忙不过来了",
            "脾虚": "消化小精灵太累了，没有力气工作",
            "心火旺盛": "心里有一团火在跳，需要平静一下",
            "肝气郁结": "心里的气堵住了，像堵车一样，需要疏通",
        }
        return explanations.get(pattern_name, "身体在调整自己")
    
    def _simplify_reason(self, reason: str) -> str:
        """简化原因说明"""
        if len(reason) > 20:
            return reason[:20] + "..."
        return reason
