"""伴读书童AI - 发育守护引擎（骨层）

职责：
1. 预警决策树执行（绿黄橙红四色预警）
2. 发育基准线对比（每日数据 vs 阶段基准）
3. 趋势追踪（7天/30天趋势分析）
4. 五位一体联动运算（劳作-经络-饮食-情绪-认知）

输入：孩子档案 + 最近N天数据
输出：预警报告 + 干预建议
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


# ═══════════════════════════════════════════════════════════
# 各阶段发育基准线（简化版，完整版从训练素材加载）
# ═══════════════════════════════════════════════════════════

DEVELOPMENT_BASELINES = {
    "S1": {  # 襁褓期 0-1岁
        "睡眠": {"min": 12, "max": 16, "unit": "小时/天"},
        "饮食": {"min": 6, "max": 8, "unit": "次奶/天"},
        "大运动": {"milestones": ["3月抬头", "6月坐", "8月爬", "12月扶走"]},
        "情绪": {"normal": "3月后社会性微笑，6月认生，10月分离焦虑"},
        "体重": {"min": 3.2, "max": 10.5, "unit": "kg（12月时）"},
    },
    "S2": {  # 幼童期 1-3岁
        "睡眠": {"min": 11, "max": 14, "unit": "小时/天（含午睡）"},
        "饮食": {"min": 3, "max": 5, "unit": "餐/天"},
        "运动": {"min": 60, "max": 180, "unit": "分钟/天"},
        "语言": {"milestones": ["1.5岁50词", "2岁短句", "3岁长句"]},
        "情绪": {"normal": "1-2岁自我意识觉醒，2-3岁秩序敏感期"},
    },
    "S3": {  # 蒙学期 3-6岁
        "睡眠": {"min": 10, "max": 13, "unit": "小时/天（含午睡1-2小时）"},
        "饮食": {"min": 3, "max": 3, "unit": "正餐+2加餐"},
        "运动": {"min": 60, "max": 180, "unit": "分钟/天"},
        "精细动作": {"milestones": ["4岁剪纸", "5岁写名字", "6岁系鞋带"]},
        "社交": {"normal": "3-4岁平行游戏，4-5岁合作游戏，5-6岁规则意识"},
    },
    "S4": {  # 小学期 6-12岁
        "睡眠": {"min": 9, "max": 11, "unit": "小时/天"},
        "运动": {"min": 60, "max": 120, "unit": "分钟/天"},
        "屏幕": {"max": 2, "unit": "小时/天"},
        "情绪": {"normal": "情绪波动增加，开始在意同伴评价"},
        "脊柱": {"warning": "书包过重、坐姿不正"},
    },
    "S5": {  # 初中 12-15岁
        "睡眠": {"min": 8, "max": 10, "unit": "小时/天"},
        "运动": {"min": 60, "max": 90, "unit": "分钟/天"},
        "屏幕": {"max": 2, "unit": "小时/天（学习除外）"},
        "情绪": {"normal": "多巴胺重组期，情绪起伏大，寻求独立"},
        "排毒": {"critical": "22:30前入睡，8-10小时睡眠，每天运动出汗"},
    },
    "S6": {  # 高中 15-18岁
        "睡眠": {"min": 7, "max": 9, "unit": "小时/天"},
        "运动": {"min": 30, "max": 60, "unit": "分钟/天"},
        "压力": {"warning": "高考压力、社交压力、身份认同压力"},
        "情绪": {"normal": "前额叶逐渐成熟，但压力可能导致焦虑抑郁"},
        "脊柱": {"warning": "久坐学习、缺乏运动"},
    },
}

# 五位一体联动规则
FIVE_DIMENSIONS = ["劳作", "经络", "饮食", "情绪", "认知"]

FIVE_LINKAGE_RULES = {
    # 当某两个维度同时异常时，触发联动预警
    ("劳作", "情绪"): {"level": "🟠", "desc": "运动不足+情绪低落→可能抑郁倾向"},
    ("饮食", "情绪"): {"level": "🟠", "desc": "饮食紊乱+情绪波动→脾胃失调/焦虑"},
    ("睡眠", "情绪"): {"level": "🔴", "desc": "睡眠不足+情绪低落→严重预警"},
    ("劳作", "经络"): {"level": "🟡", "desc": "久坐+经络不通→气血不畅"},
    ("饮食", "经络"): {"level": "🟡", "desc": "饮食不当+经络问题→痰湿内生"},
    ("认知", "情绪"): {"level": "🟠", "desc": "学习压力+情绪问题→ burnout"},
    ("睡眠", "认知"): {"level": "🟠", "desc": "睡眠不足+认知下降→效率恶性循环"},
}


class DevelopmentGuardian:
    """
    发育守护引擎
    
    核心能力：
    1. 每日自动评估（对比基准线）
    2. 四色预警判定
    3. 趋势追踪（7天/30天）
    4. 五位一体联动分析
    """
    
    def __init__(self, profile_manager):
        self.profile_manager = profile_manager
    
    # ═══════════════════════════════════════════
    # 1. 每日自动评估
    # ═══════════════════════════════════════════
    
    def daily_assessment(self, child_id) -> Dict:
        """
        对指定孩子进行每日发育评估
        
        返回：
        {
            "child_id": "",
            "date": "",
            "stage": "S4",
            "dimensions": {  # 各维度评估
                "睡眠": {"value": 8, "baseline": "9-11", "status": "🟡偏离", "trend": "下降"},
                ...
            },
            "overall_level": "🟡",  # 综合预警级别
            "warnings": [],  # 预警列表
            "suggestions": [],  # 建议列表
        }
        """
        child = self.profile_manager.get_child(child_id)
        if not child:
            return {"error": "孩子不存在"}
        
        stage = child.stage
        baseline = DEVELOPMENT_BASELINES.get(stage, {})
        
        assessment = {
            "child_id": child_id,
            "child_name": child.name,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "stage": stage,
            "stage_name": child.get_stage_name(),
            "dimensions": {},
            "overall_level": "🟢",
            "warnings": [],
            "suggestions": [],
        }
        
        # 评估各维度
        for dim_name in ["睡眠", "运动", "饮食", "情绪", "认知"]:
            dim_baseline = baseline.get(dim_name)
            if not dim_baseline:
                continue
            
            # 获取最近7天平均值
            avg_value = child.get_avg_growth(dim_name, days=7)
            
            dim_result = self._evaluate_dimension(dim_name, avg_value, dim_baseline, child)
            assessment["dimensions"][dim_name] = dim_result
            
            if dim_result["status"] != "🟢正常":
                assessment["warnings"].append({
                    "dimension": dim_name,
                    "level": dim_result["status"],
                    "detail": dim_result["detail"],
                })
        
        # 判定综合预警级别
        assessment["overall_level"] = self._calculate_overall_level(assessment["warnings"])
        
        # 生成建议
        assessment["suggestions"] = self._generate_suggestions(assessment)
        
        # 五位一体联动分析
        assessment["linkage_analysis"] = self._five_linkage_analysis(assessment["dimensions"])
        
        return assessment
    
    def _evaluate_dimension(self, dim_name, avg_value, baseline, child):
        """评估单个维度"""
        result = {
            "value": avg_value,
            "baseline": baseline,
            "status": "🟢正常",
            "detail": "",
            "trend": self._calculate_trend(child, dim_name),
        }
        
        if avg_value is None:
            result["status"] = "⚪无数据"
            result["detail"] = "暂无数据，请开始记录"
            return result
        
        # 数值型指标（睡眠、运动等）
        if "min" in baseline and "max" in baseline:
            if avg_value < baseline["min"]:
                result["status"] = "🟡偏离"
                result["detail"] = f"{avg_value}{baseline.get('unit', '')}，低于正常范围({baseline['min']}-{baseline['max']})"
                # 严重偏离
                if avg_value < baseline["min"] * 0.8:
                    result["status"] = "🟠严重偏离"
            elif avg_value > baseline["max"]:
                result["status"] = "🟡偏离"
                result["detail"] = f"{avg_value}{baseline.get('unit', '')}，高于正常范围({baseline['min']}-{baseline['max']})"
                if avg_value > baseline["max"] * 1.2:
                    result["status"] = "🟠严重偏离"
            else:
                result["status"] = "🟢正常"
                result["detail"] = f"{avg_value}{baseline.get('unit', '')}，在正常范围内"
        
        # 特殊预警（如排毒期）
        if "critical" in baseline and dim_name in ["睡眠", "运动"]:
            if result["status"] in ["🟡偏离", "🟠严重偏离"]:
                result["status"] = "🔴"
                result["detail"] += " | 排毒期关键指标异常，需立即干预"
        
        return result
    
    def _calculate_trend(self, child, dim_name):
        """计算趋势（上升/下降/平稳）"""
        data = child.growth_data.get(dim_name, [])
        if len(data) < 3:
            return "数据不足"
        
        recent = [d["value"] for d in data[-7:]]
        if len(recent) < 3:
            return "平稳"
        
        # 简单线性趋势
        first_half = sum(recent[:len(recent)//2]) / (len(recent)//2)
        second_half = sum(recent[len(recent)//2:]) / (len(recent) - len(recent)//2)
        
        diff = second_half - first_half
        if abs(diff) < 0.1:
            return "平稳"
        elif diff > 0:
            return "上升"
        else:
            return "下降"
    
    def _calculate_overall_level(self, warnings):
        """计算综合预警级别"""
        if not warnings:
            return "🟢"
        
        levels = [w["level"] for w in warnings]
        
        if "🔴" in levels:
            return "🔴"
        elif "🟠" in levels or levels.count("🟡") >= 3:
            return "🟠"
        elif "🟡" in levels:
            return "🟡"
        else:
            return "🟢"
    
    def _generate_suggestions(self, assessment):
        """根据评估生成建议"""
        suggestions = []
        
        for warning in assessment.get("warnings", []):
            dim = warning["dimension"]
            level = warning["level"]
            
            if dim == "睡眠":
                if level in ["🟡", "🟠", "🔴"]:
                    suggestions.append({
                        "target": "睡眠",
                        "action": "22:30前入睡，睡前1小时不看屏幕，可泡脚/捏脊助眠",
                        "priority": "高" if level in ["🟠", "🔴"] else "中",
                    })
            
            elif dim == "运动":
                if level in ["🟡", "🟠"]:
                    suggestions.append({
                        "target": "运动",
                        "action": "每天户外运动1小时，跳绳/跑步/球类，出微微汗",
                        "priority": "高",
                    })
            
            elif dim == "饮食":
                if level in ["🟡", "🟠"]:
                    suggestions.append({
                        "target": "饮食",
                        "action": "三餐定时，多吃蔬菜，少吃零食，每天喝够水",
                        "priority": "中",
                    })
            
            elif dim == "情绪":
                if level in ["🟡", "🟠", "🔴"]:
                    suggestions.append({
                        "target": "情绪",
                        "action": "多陪伴倾听，允许表达负面情绪，必要时寻求专业帮助",
                        "priority": "高" if level in ["🟠", "🔴"] else "中",
                    })
        
        # 排毒期特殊建议（12-18岁）
        if assessment["stage"] in ["S5", "S6"]:
            suggestions.append({
                "target": "排毒",
                "action": "22:30前入睡+每天运动出汗+梳头100下/天+多喝水",
                "priority": "高",
            })
        
        return suggestions
    
    # ═══════════════════════════════════════════
    # 2. 五位一体联动分析
    # ═══════════════════════════════════════════
    
    def _five_linkage_analysis(self, dimensions):
        """
        五位一体联动分析
        
        检查：当两个维度同时异常时，是否有联动效应
        """
        abnormal_dims = []
        for dim_name, result in dimensions.items():
            if result["status"] in ["🟡偏离", "🟠严重偏离", "🔴"]:
                abnormal_dims.append(dim_name)
        
        linkage_warnings = []
        
        # 检查所有异常维度的两两组合
        for i, dim1 in enumerate(abnormal_dims):
            for dim2 in abnormal_dims[i+1:]:
                # 标准化维度名称
                d1 = self._normalize_dim_name(dim1)
                d2 = self._normalize_dim_name(dim2)
                
                # 查找联动规则
                rule = FIVE_LINKAGE_RULES.get((d1, d2)) or FIVE_LINKAGE_RULES.get((d2, d1))
                if rule:
                    linkage_warnings.append({
                        "dims": [dim1, dim2],
                        "level": rule["level"],
                        "desc": rule["desc"],
                    })
        
        return {
            "abnormal_count": len(abnormal_dims),
            "abnormal_dimensions": abnormal_dims,
            "linkage_warnings": linkage_warnings,
            "summary": f"{len(abnormal_dims)}个维度异常，发现{len(linkage_warnings)}个联动风险" if linkage_warnings else f"{len(abnormal_dims)}个维度异常，暂无联动风险",
        }
    
    def _normalize_dim_name(self, dim):
        """标准化维度名称"""
        mapping = {
            "睡眠": "经络",
            "运动": "劳作",
            "饮食": "饮食",
            "情绪": "情绪",
            "认知": "认知",
        }
        return mapping.get(dim, dim)
    
    # ═══════════════════════════════════════════
    # 3. 趋势追踪
    # ═══════════════════════════════════════════
    
    def trend_analysis(self, child_id, dimension, days=7) -> Dict:
        """
        对指定维度进行趋势分析
        
        返回：
        {
            "dimension": "睡眠",
            "days": 7,
            "values": [8, 7.5, 7, 6.5, 6, 6, 5.5],
            "trend": "下降",
            "trend_strength": "强",  # 强/中/弱
            "prediction": "如果持续，3天后将降至5小时",
            "alert": True,
        }
        """
        child = self.profile_manager.get_child(child_id)
        if not child:
            return {"error": "孩子不存在"}
        
        data = child.growth_data.get(dimension, [])
        recent_data = data[-days:] if len(data) >= days else data
        
        if len(recent_data) < 3:
            return {
                "dimension": dimension,
                "days": len(recent_data),
                "values": [d["value"] for d in recent_data],
                "trend": "数据不足",
                "alert": False,
            }
        
        values = [d["value"] for d in recent_data]
        
        # 计算趋势
        trend = self._calculate_numeric_trend(values)
        
        # 预测（简单线性外推）
        prediction = None
        if len(values) >= 5 and trend["direction"] in ["上升", "下降"]:
            last_value = values[-1]
            avg_change = trend["avg_change"]
            predicted_3d = last_value + avg_change * 3
            prediction = f"如果持续{trend['direction']}，3天后将约{predicted_3d:.1f}"
        
        return {
            "dimension": dimension,
            "days": len(recent_data),
            "values": values,
            "dates": [d["date"] for d in recent_data],
            "trend": trend["direction"],
            "trend_strength": trend["strength"],
            "avg_change_per_day": round(trend["avg_change"], 2) if trend["avg_change"] else None,
            "prediction": prediction,
            "alert": trend["strength"] == "强" and trend["direction"] in ["上升", "下降"],
        }
    
    def _calculate_numeric_trend(self, values):
        """计算数值趋势"""
        if len(values) < 3:
            return {"direction": "平稳", "strength": "弱", "avg_change": 0}
        
        # 计算每日变化
        changes = [values[i] - values[i-1] for i in range(1, len(values))]
        avg_change = sum(changes) / len(changes)
        
        # 判断方向
        if abs(avg_change) < 0.05:
            direction = "平稳"
        elif avg_change > 0:
            direction = "上升"
        else:
            direction = "下降"
        
        # 判断强度
        consistency = sum(1 for c in changes if (avg_change > 0 and c > 0) or (avg_change < 0 and c < 0)) / len(changes)
        
        if consistency >= 0.8 and abs(avg_change) >= 0.2:
            strength = "强"
        elif consistency >= 0.6 or abs(avg_change) >= 0.1:
            strength = "中"
        else:
            strength = "弱"
        
        return {
            "direction": direction,
            "strength": strength,
            "avg_change": avg_change,
            "consistency": round(consistency, 2),
        }
    
    # ═══════════════════════════════════════════
    # 4. 批量评估
    # ═══════════════════════════════════════════
    
    def assess_all_children(self) -> Dict[str, Dict]:
        """评估所有孩子"""
        results = {}
        for child in self.profile_manager.get_all_children():
            results[child.child_id] = self.daily_assessment(child.child_id)
        return results
    
    def get_family_report(self) -> Dict:
        """生成家族发育报告（所有孩子的汇总）"""
        all_assessments = self.assess_all_children()
        
        report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_children": len(all_assessments),
            "green_count": 0,
            "yellow_count": 0,
            "orange_count": 0,
            "red_count": 0,
            "children": [],
            "top_concerns": [],
        }
        
        for child_id, assessment in all_assessments.items():
            level = assessment.get("overall_level", "🟢")
            if level == "🟢":
                report["green_count"] += 1
            elif level == "🟡":
                report["yellow_count"] += 1
            elif level == "🟠":
                report["orange_count"] += 1
            elif level == "🔴":
                report["red_count"] += 1
            
            report["children"].append({
                "name": assessment["child_name"],
                "level": level,
                "warnings_count": len(assessment.get("warnings", [])),
            })
            
            # 收集所有预警
            for w in assessment.get("warnings", []):
                report["top_concerns"].append({
                    "child": assessment["child_name"],
                    "dimension": w["dimension"],
                    "level": w["level"],
                    "detail": w["detail"],
                })
        
        # 按级别排序
        level_order = {"🔴": 0, "🟠": 1, "🟡": 2, "🟢": 3}
        report["top_concerns"].sort(key=lambda x: level_order.get(x["level"], 99))
        report["top_concerns"] = report["top_concerns"][:10]  # 最多10条
        
        return report
