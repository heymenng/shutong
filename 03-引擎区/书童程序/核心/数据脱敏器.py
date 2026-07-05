"""伴读书童AI - 数据脱敏器

职责：
1. 把本地家庭原始数据脱敏成可上传云端的标签与指标
2. 去除所有个人身份信息（PII）
3. 生成不可逆的哈希ID
4. 把症状/观察转标准标签

原则：
- 只上传特征，不上传身份
- 只上传标签，不上传原文
- 聚合可用，个体不可反查
"""

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class DataSanitizer:
    """数据脱敏器"""

    def __init__(self, salt: Optional[str] = None, tag_library_path: Optional[str] = None):
        """
        Args:
            salt: 哈希盐值，建议用环境变量 BOOKBOY_CLOUD_SALT
            tag_library_path: 标准标签库路径
        """
        self.salt = salt or os.getenv("BOOKBOY_CLOUD_SALT", "bookboy_default_salt_2026")
        self.tag_library = self._load_tag_library(tag_library_path)

    def _load_tag_library(self, path: Optional[str]) -> Dict[str, List[str]]:
        """加载标准标签库"""
        if path and Path(path).exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)

        # 默认标签库
        default_path = Path(__file__).resolve().parents[1] / "数据" / "标签库" / "标准标签库.json"
        if default_path.exists():
            with open(default_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        return {}

    def hash_id(self, local_id: str) -> str:
        """把本地ID哈希成不可逆ID"""
        text = f"{local_id}::{self.salt}"
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]

    def sanitize_family_profile(self, family_id: str, family_data: dict) -> dict:
        """
        脱敏家庭画像
        保留：结构、学历、城市级别、家庭类型等统计维度
        去除：真实姓名、详细地址、电话
        """
        family_hash = self.hash_id(family_id)
        members = family_data.get("members", [])

        # 分析家庭成员
        parent_edus = []
        parent_fields = []
        children_count = 0
        has_grandparent = False

        # 用于城市提取的全文
        all_family_text = json.dumps(family_data, ensure_ascii=False)

        for m in members:
            role = m.get("role", "")
            if role in ("家长", "父亲", "母亲", "爸爸", "妈妈", "师父"):
                # 优先使用明确字段
                text_parts = [
                    m.get('relation', ''),
                    m.get('name', ''),
                    m.get('education', ''),
                    m.get('学历', ''),
                    m.get('field', ''),
                    m.get('领域', '')
                ]
                text = ' '.join(str(p) for p in text_parts if p)

                edu = self._extract_education(text)
                if edu:
                    parent_edus.append(edu)

                field = self._extract_field(text)
                if field:
                    parent_fields.append(field)

                if "祖父" in text or "祖母" in text or "爷爷" in text or "奶奶" in text:
                    has_grandparent = True

            elif role == "孩子":
                children_count += 1

        # 家庭结构推断
        family_structure = self._infer_family_structure(children_count, has_grandparent)

        return {
            "family_hash": family_hash,
            "family_structure": family_structure,
            "children_count": children_count,
            "parent_highest_edu": self._highest_education(parent_edus),
            "parent_field_tags": self._standard_tags(parent_fields, "家长领域"),
            "region_level": self._extract_region_level(family_data),
            "household_income_level": "未知",
            "sync_at": datetime.now().isoformat()
        }

    def sanitize_child_profile(self, family_id: str, child_data: dict) -> Optional[dict]:
        """
        脱敏孩子画像
        保留：年龄段、性别、发育阶段、关注标签、能力标签
        去除：姓名、精确生日、学校、年级原文
        """
        child_id = child_data.get("user_id") or child_data.get("child_id")
        if not child_id:
            return None

        family_hash = self.hash_id(family_id)
        child_hash = self.hash_id(f"{family_id}::{child_id}")

        age = child_data.get("age")
        birth_date = child_data.get("birth_date", "")
        if age is None and birth_date:
            age = self._age_from_birth_date(birth_date)

        age_group = self._age_to_group(age)
        stage = self._extract_stage(child_data.get("stage", ""))

        # 从各种字段提取标签
        raw_text = json.dumps(child_data, ensure_ascii=False)
        attention_tags = self._extract_attention_tags(raw_text)
        ability_tags = self._extract_ability_tags(raw_text)
        medical_tags = self._extract_medical_tags(raw_text)

        # 性别处理：兼容 gender / 性别
        gender = child_data.get("gender", "")
        if not gender:
            gender = child_data.get("性别", "未知")

        return {
            "family_hash": family_hash,
            "child_hash": child_hash,
            "age_group": age_group,
            "gender": gender,
            "development_stage": stage,
            "attention_tags": attention_tags,
            "ability_tags": ability_tags,
            "medical_tags": medical_tags,
            "education_setting": self._standard_education_setting(raw_text),
            "sync_at": datetime.now().isoformat()
        }

    def extract_health_events(self, family_id: str, child_id: str, records: List[dict]) -> List[dict]:
        """
        从记录中提取健康事件标签
        records: 观察记录、日记、预警等字典列表
        """
        events = []
        family_hash = self.hash_id(family_id)
        child_hash = self.hash_id(f"{family_id}::{child_id}")

        for record in records:
            text = json.dumps(record, ensure_ascii=False)
            for event_type in self.tag_library.get("健康事件", []):
                if event_type in text:
                    events.append({
                        "family_hash": family_hash,
                        "child_hash": child_hash,
                        "event_type": event_type,
                        "season": self._current_season(),
                        "week": self._current_week(),
                        "severity": self._infer_severity(text, event_type),
                        "duration_days": None,
                        "recovery_status": "未知",
                        "reported_at": datetime.now().isoformat()
                    })

        # 去重：同一孩子同一季节同一事件只保留一次
        seen = set()
        unique = []
        for e in events:
            key = (e["child_hash"], e["event_type"], e["season"])
            if key not in seen:
                seen.add(key)
                unique.append(e)

        return unique

    def extract_outcome_metrics(self, family_id: str, child_id: str, plan_records: List[dict]) -> List[dict]:
        """
        从陪伴计划/训练记录中提取成果指标
        现在先用占位结构，后续接入真实计划执行数据
        """
        family_hash = self.hash_id(family_id)
        child_hash = self.hash_id(f"{family_id}::{child_id}")

        metrics = []
        for record in plan_records:
            goal = record.get("目标") or record.get("goal") or "综合能力"
            method = record.get("方法") or record.get("method") or "综合陪伴"
            metrics.append({
                "family_hash": family_hash,
                "child_hash": child_hash,
                "goal": goal,
                "method": self._standard_tag(method, "训练方法") or method,
                "start_week": self._current_week(),
                "latest_week": self._current_week(),
                "baseline_score": None,
                "current_score": None,
                "trend": "未知",
                "improved": None
            })

        return metrics

    # ═══════════════════════════════════════════
    # 内部工具方法
    # ═══════════════════════════════════════════

    def _extract_education(self, text: str) -> Optional[str]:
        """从文本提取学历"""
        edu_keywords = {
            "博士": ["博士"],
            "硕士": ["硕士", "研究生"],
            "本科": ["本科", "学士"],
            "大专": ["大专", "专科"],
            "高中及以下": ["高中", "中专", "初中", "小学"]
        }
        for edu, keywords in edu_keywords.items():
            for kw in keywords:
                if kw in text:
                    return edu
        return None

    def _highest_education(self, edus: List[str]) -> str:
        """返回最高学历"""
        order = ["博士", "硕士", "本科", "大专", "高中及以下"]
        for e in order:
            if e in edus:
                return e
        return "未知"

    def _extract_field(self, text: str) -> Optional[str]:
        """从文本提取专业领域"""
        field_keywords = {
            "医学": ["医生", "医院", "医学", "中医", "西医"],
            "科研": ["科研", "研究", "教授", "博士"],
            "教育": ["老师", "教师", "教育"],
            "工程": ["工程师", "工程", "程序员", "开发"],
            "艺术": ["画家", "音乐", "艺术", "设计"],
            "商业": ["企业家", "老板", "商业", "管理"],
            "法律": ["律师", "法律", "法学"],
            "金融": ["金融", "银行", "投资", "经济"]
        }
        for field, keywords in field_keywords.items():
            for kw in keywords:
                if kw in text:
                    return field
        return None

    def _infer_family_structure(self, children_count: int, has_grandparent: bool) -> str:
        """推断家庭结构"""
        base = "双亲"
        if children_count == 1:
            base += "+独生子女"
        elif children_count == 2:
            base += "+二孩"
        elif children_count >= 3:
            base += "+多孩"
        if has_grandparent:
            base += "+隔代"
        return base

    def _extract_region_level(self, family_data: dict) -> str:
        """从家庭数据推断城市级别"""
        text = json.dumps(family_data, ensure_ascii=False)

        # 城市级别映射
        city_tiers = {
            "一线城市": ["北京", "上海", "广州", "深圳"],
            "新一线城市": ["杭州", "成都", "武汉", "西安", "南京", "重庆", "天津", "苏州", "长沙", "郑州", "东莞", "青岛", "沈阳", "宁波", "昆明"],
            "二线城市": ["无锡", "佛山", "合肥", "大连", "福州", "厦门", "哈尔滨", "济南", "温州", "南宁", "长春", "泉州", "石家庄", "贵阳", "南昌", "金华", "常州", "珠海", "惠州", "嘉兴", "南通", "中山", "保定", "兰州", "台州", "徐州", "太原", "绍兴", "烟台", "廊坊"]
        }

        for tier, cities in city_tiers.items():
            for city in cities:
                if city in text:
                    return tier

        # 如果没有任何城市信息，返回未知
        return "未知"

    def _age_from_birth_date(self, birth_date: str) -> Optional[int]:
        """从出生日期计算年龄"""
        try:
            # 处理 "7月12日" 这种格式
            if "月" in birth_date and "年" not in birth_date:
                birth_date = f"{datetime.now().year}-{birth_date.replace('月', '-').replace('日', '')}"
            birth = datetime.strptime(birth_date, "%Y-%m-%d")
            return int((datetime.now() - birth).days / 365.25)
        except Exception:
            return None

    def _age_to_group(self, age) -> str:
        """年龄转年龄段"""
        if age is None:
            return "未知"
        age = int(age)
        if age < 3:
            return "0-3岁"
        elif age < 6:
            return "3-6岁"
        elif age < 9:
            return "6-9岁"
        elif age < 12:
            return "9-12岁"
        elif age < 15:
            return "12-15岁"
        elif age <= 18:
            return "15-18岁"
        return "18岁以上"

    def _extract_stage(self, stage_text: str) -> str:
        """从阶段文本提取S0-S6"""
        match = re.search(r'S\d+', str(stage_text))
        if match:
            return match.group(0)
        return "未知"

    def _standard_tag(self, text: str, category: str) -> Optional[str]:
        """把文本匹配到标准标签"""
        text = str(text)
        for tag in self.tag_library.get(category, []):
            if tag in text:
                return tag
        return None

    def _standard_tags(self, texts: List[str], category: str) -> List[str]:
        """批量匹配标准标签并去重"""
        results = []
        for text in texts:
            tag = self._standard_tag(text, category)
            if tag and tag not in results:
                results.append(tag)
        return results

    def _extract_attention_tags(self, text: str) -> List[str]:
        """提取关注标签，支持组合推断"""
        tags = []

        # 直接匹配
        for tag in self.tag_library.get("关注标签", []):
            if tag in text:
                tags.append(tag)

        # 组合推断
        # 学科薄弱
        subjects = {
            "语文": "语文薄弱",
            "数学": "数学困难",
            "英语": "英语薄弱",
            "拼音": "语文薄弱",
            "阅读": "阅读障碍",
        }
        for subj, tag in subjects.items():
            if subj in text and ("较弱" in text or "弱" in text or "跟不上" in text or "困难" in text):
                if tag not in tags:
                    tags.append(tag)

        # 睡眠不足
        if "睡眠" in text and ("偏少" in text or "不足" in text or "不够" in text):
            if "睡眠不足" not in tags:
                tags.append("睡眠不足")

        # 运动不足
        if "运动" in text and ("不足" in text or "偏少" in text or "勉强" in text):
            if "运动不足" not in tags:
                tags.append("运动不足")

        # 屏幕时间
        if "屏幕" in text or "手机" in text or "平板" in text or "游戏" in text and ("长" in text or "多" in text):
            if "屏幕时间过长" not in tags:
                tags.append("屏幕时间过长")

        # 情绪波动 / 脾气
        if ("情绪" in text and ("波动" in text or "不稳" in text or "大" in text)) or "脾气" in text:
            if "情绪波动" not in tags:
                tags.append("情绪波动")

        # 注意力不集中
        if ("注意力" in text and ("分散" in text or "不集中" in text or "差" in text)) or "走神" in text:
            if "注意力不集中" not in tags:
                tags.append("注意力不集中")

        # 社交退缩
        if "社交" in text and ("退缩" in text or "害怕" in text or "不敢" in text):
            if "社交退缩" not in tags:
                tags.append("社交退缩")

        # 叛逆
        if "叛逆" in text or "对抗" in text or "不听话" in text:
            if "叛逆" not in tags:
                tags.append("叛逆")

        return tags

    def _extract_ability_tags(self, text: str) -> List[str]:
        """提取能力标签，支持组合推断"""
        tags = []

        # 直接匹配
        for tag in self.tag_library.get("能力标签", []):
            if tag in text:
                tags.append(tag)

        # 组合推断
        if "认知" in text and ("优秀" in text or "超越" in text or "强" in text):
            if "认知优秀" not in tags:
                tags.append("认知优秀")

        if "动手" in text and ("优秀" in text or "强" in text):
            if "动手优秀" not in tags:
                tags.append("动手优秀")

        if "社交" in text and ("良好" in text or "优秀" in text):
            if "社交良好" not in tags:
                tags.append("社交良好")

        if "价值观" in text and ("成熟" in text or "稳定" in text):
            if "价值观成熟" not in tags:
                tags.append("价值观成熟")

        if "性格" in text and ("健康" in text or "韧性" in text):
            if "性格健康" not in tags:
                tags.append("性格健康")

        if "逻辑思维" in text or "逻辑" in text and ("强" in text or "活跃" in text):
            if "逻辑思维强" not in tags:
                tags.append("逻辑思维强")

        if "好奇心" in text and ("强" in text):
            if "好奇心强" not in tags:
                tags.append("好奇心强")

        return tags

    def _extract_medical_tags(self, text: str) -> List[str]:
        """提取医学/健康标签"""
        return [tag for tag in self.tag_library.get("健康事件", []) if tag in text]

    def _standard_education_setting(self, text: str) -> str:
        """推断教育环境"""
        if "公立" in text:
            return "公立学校"
        if "私立" in text or "民办" in text:
            return "民办学校"
        if " homeschool" in text or "在家" in text:
            return "在家教育"
        return "未知"

    def _current_season(self) -> str:
        """当前季节"""
        now = datetime.now()
        year = now.year
        month = now.month
        if month in [12, 1, 2]:
            return f"{year}-冬季"
        elif month in [3, 4, 5]:
            return f"{year}-春季"
        elif month in [6, 7, 8]:
            return f"{year}-夏季"
        else:
            return f"{year}-秋季"

    def _current_week(self) -> str:
        """当前周"""
        now = datetime.now()
        return f"{now.year}-W{now.isocalendar()[1]:02d}"

    def _infer_severity(self, text: str, event_type: str) -> str:
        """推断严重程度"""
        severe_keywords = ["严重", "高烧", "住院", "持续", "无法"]
        mild_keywords = ["轻微", "有点", "少许", "偶尔"]

        for kw in severe_keywords:
            if kw in text:
                return "严重"
        for kw in mild_keywords:
            if kw in text:
                return "轻微"
        return "中等"


# 便捷函数：直接脱敏一个家庭
def sanitize_family(family_id: str, family_json_path: str, archive_dir: Optional[str] = None) -> dict:
    """
    脱敏一个完整家庭的数据
    
    Returns:
        {
            "family_profile": {...},
            "children_profiles": [...],
            "health_events": [...],
            "outcome_metrics": [...]
        }
    """
    sanitizer = DataSanitizer()

    with open(family_json_path, 'r', encoding='utf-8') as f:
        family_data = json.load(f)

    family_profile = sanitizer.sanitize_family_profile(family_id, family_data)
    children_profiles = []
    health_events = []
    outcome_metrics = []

    # 预加载档案目录下所有JSON文件
    child_archive_records = {}
    if archive_dir:
        archive_path = Path(archive_dir)
        child档案_dir = archive_path / "孩子档案"
        if child档案_dir.exists():
            for json_file in child档案_dir.glob("*.json"):
                try:
                    with open(json_file, 'r', encoding='utf-8') as ff:
                        record = json.load(ff)
                        # 尝试关联到孩子：用文件名或档案信息里的姓名
                        info = record.get("档案信息", {})
                        name = info.get("姓名", "")
                        child_archive_records[name] = record
                        child_archive_records[json_file.stem] = record
                except Exception:
                    continue

    for member in family_data.get("members", []):
        if member.get("role") == "孩子":
            child_name = member.get("name", "")
            user_id = member.get("user_id", "")

            # 合并孩子档案数据（如果有）
            merged_child_data = dict(member)
            if child_name and child_name in child_archive_records:
                archive_record = child_archive_records[child_name]
                merged_child_data["_archive_record"] = archive_record
                # 把档案信息合并进来
                info = archive_record.get("档案信息", {})
                for key in ["年龄", "性别", "发育阶段"]:
                    if key in info and key not in merged_child_data:
                        merged_child_data[key] = info[key]
                if "生日" in info and "birth_date" not in merged_child_data:
                    merged_child_data["birth_date"] = info["生日"]

            child_profile = sanitizer.sanitize_child_profile(family_id, merged_child_data)
            if child_profile:
                children_profiles.append(child_profile)

            # 提取健康事件
            child_records = list(child_archive_records.values())
            health_events.extend(sanitizer.extract_health_events(family_id, user_id or child_name, child_records))

    return {
        "family_profile": family_profile,
        "children_profiles": children_profiles,
        "health_events": health_events,
        "outcome_metrics": outcome_metrics
    }


if __name__ == "__main__":
    # 测试
    import sys
    project_root = Path(__file__).resolve().parents[3]
    family_json = project_root / "04-工作区" / "档案区" / "家庭群" / "师父直系" / "default_family" / "family.json"
    archive_dir = project_root / "04-工作区" / "档案区" / "家庭群" / "师父直系" / "default_family"

    result = sanitize_family("default_family", str(family_json), str(archive_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
