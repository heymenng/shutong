"""伴读书童AI - 多用户档案管理系统

职责：
1. 管理每个孩子的基本信息（年龄、阶段、作息偏好）
2. 存储孩子的发育数据（运动/睡眠/饮食/情绪/认知）
3. 支持混龄共修匹配（大带小）
4. 为作息调度提供基础数据
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ChildProfile:
    """
    单个孩子的档案
    
    包含：
    - 基本信息（姓名、年龄、阶段）
    - 作息偏好（起床/睡觉时间、饮食偏好）
    - 发育数据（五维数据：劳作/经络/饮食/情绪/认知）
    - 预警历史
    - 陪伴记录摘要
    """
    
    def __init__(self, child_id, name, birth_date, stage=None):
        self.child_id = child_id
        self.name = name
        self.birth_date = birth_date  # YYYY-MM-DD
        self.stage = stage or self._auto_detect_stage()
        
        # 作息偏好（可配置）
        self.schedule_prefs = {
            "wake_time": "07:00",      # 起床时间
            "sleep_time": "21:30",     # 睡觉时间（不同年龄段不同）
            "nap_time": None,          # 午睡时间（幼童期有）
            "meal_times": ["07:30", "12:00", "18:30"],  # 三餐时间
            "homework_time": "19:00",  # 作业时间（学龄期）
            "outdoor_time": "16:00",   # 户外时间
            "bedtime_ritual_duration": 30,  # 睡前仪式时长（分钟）
        }
        
        # 发育数据（五维）- 最近7天
        self.growth_data = {
            "运动": [],      # 每日运动分钟数
            "睡眠": [],      # 每日睡眠小时数
            "饮食": [],      # 饮食评分1-5
            "情绪": [],      # 情绪评分1-5
            "认知": [],      # 学习/探索时间分钟数
        }
        
        # 预警历史
        self.warning_history = []
        
        # 特殊标签
        self.tags = []  # 如："过敏体质", "近视", "抽动症", "挑食"等
        
        # 家族档案连接
        self.family_id = None
        self.siblings = []  # 兄弟姐妹child_id列表
    
    def _auto_detect_stage(self):
        """根据出生日期自动判断发育阶段"""
        birth = datetime.strptime(self.birth_date, "%Y-%m-%d")
        age_days = (datetime.now() - birth).days
        age_years = age_days / 365.25
        
        if age_years < 0:
            return "S0"  # 孕育期
        elif age_years < 1:
            return "S1"  # 襁褓期
        elif age_years < 3:
            return "S2"  # 幼童期
        elif age_years < 6:
            return "S3"  # 蒙学期
        elif age_years < 12:
            return "S4"  # 小学期
        elif age_years < 15:
            return "S5"  # 少学期（初中）
        elif age_years <= 18:
            return "S6"  # 少学期（高中）
        else:
            return "S6"
    
    def get_age_display(self):
        """返回友好年龄显示"""
        birth = datetime.strptime(self.birth_date, "%Y-%m-%d")
        age_days = (datetime.now() - birth).days
        
        if age_days < 30:
            return f"{age_days}天"
        elif age_days < 365:
            months = age_days // 30
            return f"{months}个月"
        else:
            years = int(age_days / 365.25)
            months = int((age_days % 365.25) / 30)
            if months > 0:
                return f"{years}岁{months}个月"
            return f"{years}岁"
    
    def get_stage_name(self):
        """返回阶段中文名"""
        stage_names = {
            "S0": "孕育期",
            "S1": "襁褓期",
            "S2": "幼童期",
            "S3": "蒙学期",
            "S4": "小学期",
            "S5": "少学期（初中）",
            "S6": "少学期（高中）",
        }
        return stage_names.get(self.stage, "未知")
    
    def update_growth_data(self, dimension, value):
        """更新发育数据"""
        if dimension in self.growth_data:
            self.growth_data[dimension].append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "value": value,
            })
            # 只保留最近30天
            self.growth_data[dimension] = self.growth_data[dimension][-30:]
    
    def get_avg_growth(self, dimension, days=7):
        """获取最近N天平均值"""
        data = self.growth_data.get(dimension, [])
        recent = [d["value"] for d in data[-days:]]
        if recent:
            return sum(recent) / len(recent)
        return None
    
    def to_dict(self):
        return {
            "child_id": self.child_id,
            "name": self.name,
            "birth_date": self.birth_date,
            "stage": self.stage,
            "schedule_prefs": self.schedule_prefs,
            "growth_data": self.growth_data,
            "warning_history": self.warning_history,
            "tags": self.tags,
            "family_id": self.family_id,
            "siblings": self.siblings,
        }
    
    @classmethod
    def from_dict(cls, data):
        profile = cls(data["child_id"], data["name"], data["birth_date"], data.get("stage"))
        profile.schedule_prefs = data.get("schedule_prefs", profile.schedule_prefs)
        profile.growth_data = data.get("growth_data", profile.growth_data)
        profile.warning_history = data.get("warning_history", [])
        profile.tags = data.get("tags", [])
        profile.family_id = data.get("family_id")
        profile.siblings = data.get("siblings", [])
        return profile


class ChildProfileManager:
    """
    多用户档案管理器
    
    管理所有孩子的档案，支持：
    - 增删改查
    - 按阶段筛选
    - 混龄匹配（大带小）
    - 家族档案关联
    """
    
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_file = self.data_dir / "child_profiles.json"
        self.profiles: Dict[str, ChildProfile] = {}
        self._load_profiles()
    
    def _load_profiles(self):
        """从磁盘加载档案"""
        if self.profiles_file.exists():
            with open(self.profiles_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for child_id, profile_data in data.items():
                    self.profiles[child_id] = ChildProfile.from_dict(profile_data)
            print(f"[档案] 已加载 {len(self.profiles)} 个孩子档案")
        else:
            print("[档案] 暂无孩子档案，等待创建")
    
    def _save_profiles(self):
        """保存档案到磁盘"""
        data = {child_id: profile.to_dict() for child_id, profile in self.profiles.items()}
        with open(self.profiles_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    # ═══════════════════════════════════════════
    # 档案区自动扫描与加载
    # ═══════════════════════════════════════════
    
    def scan_archive_zone(self, archive_dir: str) -> int:
        """
        扫描固定档案区，自动加载真实孩子档案
        
        扫描规则：
        - 目录：档案区/孩子档案/
        - 文件名格式：*档案*.json
        - 自动提取姓名、年龄、阶段、观察记录等
        
        返回：加载的孩子数量
        """
        archive_path = Path(archive_dir)
        if not archive_path.exists():
            print(f"[档案区] 目录不存在: {archive_dir}")
            return 0
        
        loaded_count = 0
        
        for json_file in archive_path.glob("*档案*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    archive_data = json.load(f)
                
                # 解析档案信息
                profile_info = self._parse_archive_data(archive_data, json_file.stem)
                if not profile_info:
                    continue
                
                child_id = profile_info.get("child_id")
                name = profile_info.get("name")
                birth_date = profile_info.get("birth_date", "2016-01-01")
                
                # 如果已存在，更新；如果不存在，创建
                if child_id in self.profiles:
                    self._update_from_archive(self.profiles[child_id], profile_info)
                    print(f"[档案区] 已更新: {name} ({json_file.name})")
                else:
                    profile = ChildProfile(child_id, name, birth_date, profile_info.get("stage"))
                    self._update_from_archive(profile, profile_info)
                    self.profiles[child_id] = profile
                    print(f"[档案区] 已加载: {name} ({profile.get_age_display()}, {profile.get_stage_name()}) ← {json_file.name}")
                
                loaded_count += 1
                
            except Exception as e:
                print(f"[档案区] 加载失败 {json_file.name}: {e}")
        
        if loaded_count > 0:
            self._save_profiles()
            print(f"[档案区] 共加载 {loaded_count} 个真实档案")
        else:
            print(f"[档案区] 未发现档案文件 (扫描: {archive_dir})")
        
        return loaded_count
    
    def _parse_archive_data(self, archive_data: dict, filename: str) -> Optional[dict]:
        """解析档案JSON数据"""
        # 尝试提取档案信息
        info = archive_data.get("档案信息", {})
        
        if not info:
            # 尝试其他可能的键名
            info = archive_data.get("profile", {})
        
        if not info:
            return None
        
        name = info.get("姓名", info.get("name", ""))
        if not name:
            return None
        
        # 计算出生日期（从年龄反推）
        age = info.get("年龄", info.get("age", 8))
        birth_year = datetime.now().year - age
        birth_date_raw = info.get("生日", info.get("birth_date", ""))
        
        # 处理中文日期格式（如"7月12日"）
        if birth_date_raw:
            import re
            cn_match = re.search(r'(\d+)月(\d+)日', birth_date_raw)
            if cn_match:
                month, day = cn_match.groups()
                birth_date = f"{birth_year}-{int(month):02d}-{int(day):02d}"
            else:
                birth_date = birth_date_raw
        else:
            birth_date = f"{birth_year}-06-01"
        
        # 阶段
        stage = info.get("发育阶段", info.get("stage", ""))
        if stage:
            # 提取S0-S6
            import re
            stage_match = re.search(r'S\d+', stage)
            if stage_match:
                stage = stage_match.group(0)
        
        # 生成child_id
        child_id = f"archive_{name}_{filename.split('_')[0]}"
        
        result = {
            "child_id": child_id,
            "name": name,
            "birth_date": birth_date,
            "stage": stage,
            "raw_data": archive_data,  # 保留原始数据
        }
        
        # 提取观察记录中的关键数据
        observations = archive_data.get("观察记录", {})
        if observations:
            # 家庭观察（嘟嘟补充）
            family_obs = observations.get("家庭观察（嘟嘟补充，2026-06-06）", {})
            if family_obs:
                result["family_observations"] = family_obs
            
            # 睡眠
            sleep = observations.get("睡眠")
            if sleep:
                result["sleep_note"] = sleep
            
            # 兴趣
            interests = observations.get("兴趣爱好", [])
            if interests:
                result["interests"] = interests
        
        # 预警状态
        warnings = archive_data.get("预警状态", {})
        if warnings:
            result["warning_level"] = warnings.get("当前级别", "🟢")
        
        return result
    
    def _update_from_archive(self, profile: ChildProfile, info: dict):
        """用档案数据更新孩子档案"""
        # 更新基本信息
        if info.get("birth_date"):
            profile.birth_date = info["birth_date"]
        if info.get("stage"):
            profile.stage = info["stage"]
        
        # 更新标签
        tags = []
        
        # 从观察记录提取标签
        raw = info.get("raw_data", {})
        observations = raw.get("观察记录", {})
        
        # 学习能力标签（橙子档案结构）
        learning = observations.get("学习能力", {})
        for subject, data in learning.items():
            status = data.get("状态", "")
            if status in ["较弱", "弱"]:
                tags.append(f"{subject}较弱")
            elif status in ["优秀", "较好"]:
                tags.append(f"{subject}优秀")
        
        # 家庭观察标签（橙子档案结构）
        family_obs = observations.get("家庭观察（嘟嘟补充，2026-06-06）", {})
        if family_obs:
            sleep_eval = family_obs.get("睡眠评估", "")
            if "偏少" in sleep_eval:
                tags.append("睡眠不足")
            
            diet_eval = family_obs.get("饮食评估", "")
            if "挑食" in diet_eval:
                tags.append("挑食")
            
            emotion_eval = family_obs.get("情绪评估", "")
            if "脾气" in emotion_eval:
                tags.append("情绪波动")
            
            # 提取具体数据到growth_data
            sleep_note = family_obs.get("睡眠", "")
            if sleep_note:
                import re
                hour_match = re.search(r'(\d+)\s*小时', sleep_note)
                if hour_match:
                    profile.update_growth_data("睡眠", float(hour_match.group(1)))
        
        # 认知能力标签（嘟嘟档案结构）
        cognition = observations.get("认知能力", {})
        if cognition.get("状态") in ["优秀", "超越同龄平均水平"]:
            tags.append("认知优秀")
        
        # 价值观标签（嘟嘟档案结构）
        values = observations.get("价值观", {})
        if values.get("状态") in ["成熟稳定", "成熟"]:
            tags.append("价值观成熟")
        
        # 性格特点标签（嘟嘟档案结构）
        personality = observations.get("性格特点", {})
        if personality.get("状态") in ["健康，有韧性", "健康"]:
            tags.append("性格健康")
        
        # 社交标签（橙子档案结构）
        social = observations.get("社交能力", {})
        if social.get("状态") == "良好":
            tags.append("社交良好")
        
        # 动手能力（橙子档案结构）
        hands = observations.get("动手能力", {})
        if hands.get("状态") == "优秀":
            tags.append("动手优秀")
        
        # 预警标签
        if info.get("warning_level") in ["🟡", "🟠", "🔴"]:
            tags.append(f"预警{info['warning_level']}")
        
        profile.tags = list(set(tags))
        
        # 保存原始档案引用
        profile.archive_data = info.get("raw_data", {})
    
    def add_child(self, name, birth_date, child_id=None, **kwargs):
        """添加新孩子"""
        if child_id is None:
            child_id = f"child_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        if child_id in self.profiles:
            print(f"[档案] 孩子 {child_id} 已存在")
            return child_id
        
        profile = ChildProfile(child_id, name, birth_date)
        
        # 应用额外配置
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        self.profiles[child_id] = profile
        self._save_profiles()
        print(f"[档案] 已添加孩子: {name} ({profile.get_age_display()}, {profile.get_stage_name()})")
        return child_id
    
    def get_child(self, child_id) -> Optional[ChildProfile]:
        """获取指定孩子档案"""
        return self.profiles.get(child_id)
    
    def get_all_children(self) -> List[ChildProfile]:
        """获取所有孩子"""
        return list(self.profiles.values())
    
    def get_children_by_stage(self, stage) -> List[ChildProfile]:
        """按阶段筛选"""
        return [p for p in self.profiles.values() if p.stage == stage]
    
    def get_older_siblings_for(self, child_id) -> List[ChildProfile]:
        """
        混龄共修：为指定孩子找"大哥哥/大姐姐"
        返回比ta大1-3个阶段的孩子
        """
        child = self.get_child(child_id)
        if not child:
            return []
        
        stage_order = ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]
        child_idx = stage_order.index(child.stage) if child.stage in stage_order else -1
        
        older = []
        for profile in self.profiles.values():
            if profile.child_id == child_id:
                continue
            other_idx = stage_order.index(profile.stage) if profile.stage in stage_order else -1
            if other_idx > child_idx:
                older.append(profile)
        
        # 按年龄差排序（最接近的优先）
        older.sort(key=lambda p: abs(stage_order.index(p.stage) - child_idx))
        return older
    
    def get_family_children(self, family_id) -> List[ChildProfile]:
        """获取同一家族的所有孩子"""
        return [p for p in self.profiles.values() if p.family_id == family_id]
    
    def update_child(self, child_id, **kwargs):
        """更新孩子信息"""
        profile = self.get_child(child_id)
        if not profile:
            print(f"[档案] 孩子 {child_id} 不存在")
            return False
        
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        self._save_profiles()
        return True
    
    def remove_child(self, child_id):
        """移除孩子档案"""
        if child_id in self.profiles:
            del self.profiles[child_id]
            self._save_profiles()
            print(f"[档案] 已移除孩子: {child_id}")
            return True
        return False
    
    def get_stats(self):
        """获取档案统计"""
        stages = {}
        for p in self.profiles.values():
            stages[p.stage] = stages.get(p.stage, 0) + 1
        
        return {
            "total": len(self.profiles),
            "by_stage": stages,
        }
