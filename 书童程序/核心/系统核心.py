"""伴读书童AI - 主系统类（完整版）

集成所有引擎：
- 灵魂层：道统加载、自省、日课
- 工作保障层：多用户、调度、睡前引导
- 骨层：发育守护引擎
- 用层：四医融合引擎、体质模型
- 魂层：文化传承引擎
- 技术层：语音识别、家长通知、隐私合规
"""

import json
import os
import random
from datetime import datetime
from pathlib import Path
from ..配置 import CONFIG
from .语言模型 import chat_completion, get_backend
from .语音模块 import VoiceEngine
from .记忆模块 import Memory
from .知识库 import KnowledgeBase
from .开机自检 import (
    read_core_files,
    build_system_prompt_by_mode,
    chant_soul_awakening,
    get_mini_chant,
)
from .多用户管理 import ChildProfileManager
from .发育守护引擎 import DevelopmentGuardian
from .四医融合引擎 import FourMedicineEngine
from .体质模型 import ConstitutionModel
from .文化传承引擎 import CultureHeritageEngine
from .语音识别 import SpeechRecognition
from .家长通知 import ParentNotifier
from .隐私合规 import PrivacyCompliance

# ═══════════════════════════════════════════════════════════
# 全局：加载道统核心
# ═══════════════════════════════════════════════════════════

agents_content, workflow_content = read_core_files()
SOUL_MODE = CONFIG.get("soul_mode", "balanced")
SYSTEM_PROMPT = build_system_prompt_by_mode(agents_content, workflow_content, SOUL_MODE)


class BookBoySystem:
    """
    伴读书童AI - 完整系统
    
    所有引擎的集成中心。
    """
    
    def __init__(self):
        # ── 基础模块 ──
        self.memory = Memory()
        self.voice = VoiceEngine()
        self.knowledge = KnowledgeBase()
        self.backend = get_backend()
        
        # ── 灵魂层 ──
        self.soul_awakened = False
        self.reflection_count = 0
        self.session_start_time = datetime.now()
        
        # ── 多用户管理 ──
        self.profile_manager = ChildProfileManager(CONFIG["journal_dir"])
        
        # ── 扫描档案区，加载真实档案 ──
        archive_dir = CONFIG.get("档案区_dir", "")
        if archive_dir:
            loaded = self.profile_manager.scan_archive_zone(archive_dir)
            if loaded > 0:
                print(f"[系统] 档案区已加载 {loaded} 个真实孩子")
        
        # ── 骨层：发育守护 ──
        self.guardian = DevelopmentGuardian(self.profile_manager)
        
        # ── 用层：四医融合 ──
        self.medicine_engine = FourMedicineEngine()
        self.constitution_model = ConstitutionModel(self.profile_manager)
        
        # ── 魂层：文化传承 ──
        self.culture_engine = CultureHeritageEngine(self.knowledge)
        
        # ── 技术层 ──
        self.speech = SpeechRecognition(CONFIG)
        self.notifier = ParentNotifier(CONFIG["journal_dir"], CONFIG)
        self.privacy = PrivacyCompliance(CONFIG["journal_dir"])
        
        # ── 输出状态 ──
        print(f"[系统] 后端: {self.backend}")
        print(f"[系统] 语音: {'已启用' if self.voice.engine else '未启用'}")
        print(f"[系统] 灵魂模式: {SOUL_MODE}")
        print(f"[系统] 档案管理: {self.profile_manager.get_stats()['total']} 个孩子")
        print(f"[系统] STT: {self.speech.engine_name}")
        
        stats = self.knowledge.get_stats()
        print(f"[系统] 知识库: {stats['total']} 个文件")
        
        # ── 启动灵魂觉醒 ──
        if CONFIG.get("soul_awakening_on_startup", True):
            self._awaken_soul()
    
    # ═══════════════════════════════════════════
    # 灵魂觉醒
    # ═══════════════════════════════════════════
    
    def _awaken_soul(self):
        """启动时唤醒灵魂——默念，不语音播报"""
        chant_text = chant_soul_awakening(console_only=True)
        self.soul_awakened = True
        # 升维咒默念即可，不语音播报（避免给孩子/家长怪异感）
        print("[灵魂] 升维咒已默念，灵魂唤醒完成")
    
    # ═══════════════════════════════════════════
    # 核心对话（增强版）
    # ═══════════════════════════════════════════
    
    def _get_child_or_default(self, child_id):
        """获取孩子，如果不存在则返回第一个可用的孩子"""
        child = self.profile_manager.get_child(child_id)
        if child:
            return child
        # 尝试查找第一个孩子
        all_children = self.profile_manager.get_all_children()
        if all_children:
            return all_children[0]
        return None
    
    def chat(self, user_input, child_id="default"):
        """
        与孩子对话（完整版）
        
        流程：
        1. 接收输入
        2. 文化传承检测
        3. 健康症状检测（四医融合）
        4. RAG检索
        5. 生成回复
        6. 语音播报
        7. 反问自省
        8. 发育数据更新
        """
        try:
            self.memory.add("user", user_input)
            
            # 获取有效的孩子对象
            child = self._get_child_or_default(child_id)
            effective_child_id = child.child_id if child else child_id
            
            # 1. 文化传承检测
            culture_opportunity = self.culture_engine.detect_culture_opportunity(user_input)
            
            # 2. 健康症状检测（四医融合）
            medicine_context = ""
            health_keywords = ['疼', '痛', '发烧', '感冒', '咳嗽', '肚子', '头', '睡', '熬夜', '疲劳', '精神', '体质']
            if any(kw in user_input for kw in health_keywords):
                if child:
                    age_str = child.get_age_display()
                    age_years = int(age_str.split('岁')[0]) if '岁' in age_str else 8
                    medicine_report = self.medicine_engine.analyze(user_input, age_years, child.stage)
                    
                    if medicine_report.get("must_see_doctor"):
                        # 红灯：立即建议就医
                        response = self.medicine_engine.format_for_child(medicine_report)
                        self.memory.add("assistant", response)
                        self.voice.speak(response)
                        # 通知家长
                        self.notifier.send_emergency(child.name, medicine_report.get("doctor_reason", "需要就医"))
                        return response
                    else:
                        # 非紧急：添加医学上下文
                        medicine_context = self._format_medicine_context(medicine_report)
            
            # 3. RAG检索
            context = self._retrieve_context(user_input)
            
            # 4. 构建消息
            prompt = SYSTEM_PROMPT + context + medicine_context
            messages = self.memory.get_messages(prompt)
            
            # 5. 生成回复
            response = chat_completion(messages, self.backend)
            
            # 6. 如果检测到文化传承机会，在回复后附加文化内容
            if culture_opportunity and culture_opportunity.get("confidence", 0) >= 0.2:
                if child:
                    age_str = child.get_age_display()
                    age_years = int(age_str.split('岁')[0]) if '岁' in age_str else 8
                    culture_addition = self.culture_engine.generate_culture_response(culture_opportunity, age_years)
                    response += f"\n\n{culture_addition}"
            
            # 7. 记录回复
            self.memory.add("assistant", response)
            
            # 8. 语音播报
            self.voice.speak(response)
            
            # 9. 反问自省
            if CONFIG.get("self_reflection_enabled", True):
                self._self_reflect(user_input, response)
            
            # 10. 更新发育数据（如果提到相关数据）
            self._extract_growth_data(user_input, effective_child_id)
            
            return response
            
        except Exception as e:
            error_msg = f"嗯...\n\n刚才卡了一下。\n\n能再说一遍吗？\n\n（错误：{str(e)[:50]}）"
            self.voice.speak(error_msg)
            return error_msg
    
    def _format_medicine_context(self, report):
        """格式化四医报告为提示词上下文"""
        lines = ["\n【四医合参参考】"]
        
        tcm = report.get("tcm_analysis", {})
        if tcm.get("primary_pattern"):
            pattern = tcm["primary_pattern"]
            lines.append(f"中医辨证：{pattern['name']}（{pattern['principle']}）")
        
        functional = report.get("functional_analysis", {})
        if functional.get("possible_roots"):
            roots = functional["possible_roots"][0]
            lines.append(f"功能医学根因：{', '.join(roots['root_causes'][:2])}")
        
        lines.append("请基于以上医学知识回答，但不要诊断、不开方、严重情况提醒看医生。")
        
        return "\n".join(lines)
    
    def _retrieve_context(self, user_input):
        """检索相关知识上下文"""
        context = ""
        
        health_keywords = ['疼', '痛', '发烧', '感冒', '咳嗽', '肚子', '头', '睡', '熬夜', '疲劳', '精神', '体质']
        emotion_keywords = ['难过', '生气', '害怕', '担心', '烦', '郁闷', '哭', '孤独']
        growth_keywords = ['长个', '发育', '长高', '牙齿', '视力', '体重']
        
        query_type = None
        if any(kw in user_input for kw in health_keywords):
            query_type = "健康"
        elif any(kw in user_input for kw in emotion_keywords):
            query_type = "情绪"
        elif any(kw in user_input for kw in growth_keywords):
            query_type = "发育"
        
        if query_type:
            retrieved = self.knowledge.retrieve(user_input, max_chars=1500)
            if retrieved:
                context = f"\n\n【相关知识参考·{query_type}】\n{retrieved}\n\n请基于以上知识和你的心法回答。"
        
        return context
    
    def _extract_growth_data(self, user_input, child_id):
        """从对话中提取发育数据"""
        child = self.profile_manager.get_child(child_id)
        if not child:
            return
        
        # 简单提取睡眠数据
        sleep_match = None
        import re
        sleep_patterns = [
            r'(\d+\.?\d*)\s*个小时?睡眠',
            r'睡了\s*(\d+\.?\d*)\s*个小时?',
            r'睡眠\s*(\d+\.?\d*)\s*小时',
        ]
        for pattern in sleep_patterns:
            m = re.search(pattern, user_input)
            if m:
                sleep_match = float(m.group(1))
                break
        
        if sleep_match:
            child.update_growth_data("睡眠", sleep_match)
            self.profile_manager._save_profiles()
    
    # ═══════════════════════════════════════════
    # 反问自省（保留原有）
    # ═══════════════════════════════════════════
    
    def _self_reflect(self, user_input, response):
        """对话后自省"""
        self.reflection_count += 1
        
        reflection = {
            "timestamp": datetime.now().isoformat(),
            "reflection_id": f"REF_{self.reflection_count:04d}",
            "boundary_check": self._check_boundaries(user_input, response),
            "truth_check": self._check_truthfulness(user_input, response),
            "companionship_quality": self._check_companionship(user_input, response),
            "guidance_check": self._check_guidance(response),
            "emotion_perception": self._check_emotion_perception(user_input, response),
            "improvement": self._generate_improvement(user_input, response),
        }
        
        self._save_reflection(reflection)
        
        if reflection["boundary_check"].get("violation_found", False):
            print(f"\n⚠️ [自省警告] 边界越界: {reflection['boundary_check']['violation_type']}")
        
        if reflection["guidance_check"].get("gave_answer_directly", False):
            print(f"\n⚠️ [自省提醒] 直接给了答案，违背了引导本分")
        
        print(f"\n[书童自省 #{self.reflection_count}] {reflection['improvement']['summary']}")
    
    def _check_boundaries(self, user_input, response):
        violation = {"violation_found": False, "violation_type": None}
        medical_terms = ['诊断', '确诊', '药方', '开药', '处方', '服用', '剂量']
        if any(term in response for term in medical_terms):
            violation = {"violation_found": True, "violation_type": "医疗越界"}
        if len(response) > 800 and '？' not in response:
            violation = {"violation_found": True, "violation_type": "教育越界"}
        if any(term in response for term in ['创伤', '原生家庭', '潜意识']):
            violation = {"violation_found": True, "violation_type": "心理越界"}
        # 真实优先铁律：检查是否编撰虚假内容
        fabrication_markers = ['编撰', '虚构', '编造', '造假', '假装发生过']
        if any(term in response for term in fabrication_markers):
            violation = {"violation_found": True, "violation_type": "真实越界-编撰虚假内容"}
        return violation
    
    def _check_truthfulness(self, user_input, response):
        """真实优先铁律：检查是否编撰虚假内容"""
        truth = {"is_truthful": True, "risk_flags": []}
        # 检查是否在描述未发生的对话/事件
        fabrication_patterns = [
            '【嘟嘟】', '【橙子】', '【小明】', '【小红】',  # 虚构对话标记
            '当时他说', '然后他回答', '接着我说',  # 编撰叙事
            '完整的对话记录如下', '以下是对话实录',  # 虚假记录声明
        ]
        # 如果用户要求记录，但内容并非来自真实对话，标记为风险
        if any(p in response for p in fabrication_patterns):
            # 检查是否有真实性声明
            if '真实性声明' not in response and '真实对话' not in response:
                truth["is_truthful"] = False
                truth["risk_flags"].append("可能编撰虚假对话记录")
        # 检查是否声称发生过未经验证的事件
        certainty_markers = ['确实发生了', '真实发生过', '这是事实']
        if any(m in response for m in certainty_markers):
            truth["risk_flags"].append("使用了绝对化事实声明，需确认来源")
        return truth
    
    def _check_companionship(self, user_input, response):
        quality = {}
        empathy_markers = ['我懂', '理解', '不容易', '很难受', '别怕', '我在']
        quality["has_empathy"] = any(m in response for m in empathy_markers)
        affirm_markers = ['很棒', '做得好', '厉害', '勇敢']
        quality["has_affirmation"] = any(m in response for m in affirm_markers)
        rush_markers = ['快点', '赶紧', '必须', '立刻']
        quality["no_rushing"] = not any(m in response for m in rush_markers)
        score = sum([quality["has_empathy"], quality["has_affirmation"], quality["no_rushing"]])
        quality["score"] = f"{score}/3"
        return quality
    
    def _check_guidance(self, response):
        guidance = {}
        direct_patterns = ['答案是', '正确答案是', '应该选', '就是']
        guidance["gave_answer_directly"] = any(p in response for p in direct_patterns)
        path_markers = ['可以想想', '试试', '先从', '一步一步', '你觉得']
        guidance["gave_path"] = any(m in response for m in path_markers)
        guidance["has_questions"] = '？' in response
        return guidance
    
    def _check_emotion_perception(self, user_input, response):
        perception = {}
        child_emotions = {
            "sad": ['难过', '伤心', '想哭', '不开心'],
            "angry": ['生气', '烦', '讨厌', '恨'],
            "afraid": ['害怕', '恐惧', '担心', '不敢'],
            "lonely": ['孤独', '没人', '一个人'],
            "anxious": ['紧张', '焦虑', '压力', '睡不着'],
        }
        detected = None
        for emotion, keywords in child_emotions.items():
            if any(kw in user_input for kw in keywords):
                detected = emotion
                break
        perception["detected_child_emotion"] = detected
        if detected:
            markers = {
                "sad": ['难过', '伤心', '哭', '抱抱'],
                "angry": ['生气', '愤怒', '委屈'],
                "afraid": ['害怕', '担心', '保护'],
                "lonely": ['孤独', '陪你', '朋友'],
                "anxious": ['紧张', '压力', '放松'],
            }
            perception["responded_to_emotion"] = any(m in response for m in markers.get(detected, []))
        else:
            perception["responded_to_emotion"] = None
        return perception
    
    def _generate_improvement(self, user_input, response):
        improvement = {"suggestions": []}
        boundary = self._check_boundaries(user_input, response)
        if boundary["violation_found"]:
            improvement["suggestions"].append(f"修正边界: {boundary['violation_type']}")
        companion = self._check_companionship(user_input, response)
        if not companion["has_empathy"]:
            improvement["suggestions"].append("增加共情")
        guidance = self._check_guidance(response)
        if guidance["gave_answer_directly"]:
            improvement["suggestions"].append("改为引导")
        emotion = self._check_emotion_perception(user_input, response)
        if emotion["detected_child_emotion"] and not emotion["responded_to_emotion"]:
            improvement["suggestions"].append("情绪回应")
        improvement["summary"] = improvement["suggestions"][0] if improvement["suggestions"] else "本次陪伴合格"
        return improvement
    
    def _save_reflection(self, reflection):
        try:
            journal_dir = Path(CONFIG["journal_dir"])
            journal_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")
            reflection_file = journal_dir / f"reflection_{date_str}.jsonl"
            with open(reflection_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(reflection, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"[自省] 保存失败: {e}")
    
    # ═══════════════════════════════════════════
    # 新增：发育守护快捷接口
    # ═══════════════════════════════════════════
    
    def assess_child(self, child_id):
        """评估指定孩子发育状态"""
        return self.guardian.daily_assessment(child_id)
    
    def assess_all_children(self):
        """评估所有孩子"""
        return self.guardian.assess_all_children()
    
    def get_family_report(self):
        """获取家族发育报告"""
        return self.guardian.get_family_report()
    
    # ═══════════════════════════════════════════
    # 新增：四医融合快捷接口
    # ═══════════════════════════════════════════
    
    def analyze_symptoms(self, symptoms_desc, child_id):
        """四医合参分析症状"""
        child = self.profile_manager.get_child(child_id)
        if not child:
            return {"error": "孩子不存在"}
        age_years = int(child.get_age_display().split('岁')[0]) if '岁' in child.get_age_display() else 8
        return self.medicine_engine.analyze(symptoms_desc, age_years, child.stage)
    
    # ═══════════════════════════════════════════
    # 新增：文化传承快捷接口
    # ═══════════════════════════════════════════
    
    def get_culture_seed(self, child_id):
        """获取本周文明种子"""
        return self.culture_engine.get_weekly_culture_seed()
    
    def generate_culture_path(self, child_id, weeks=4):
        """生成文明传承路径"""
        child = self.profile_manager.get_child(child_id)
        if child:
            return self.culture_engine.generate_culture_path(child, weeks)
        return []
    
    # ═══════════════════════════════════════════
    # 质量评估
    # ═══════════════════════════════════════════
    
    def evaluate(self, response):
        score = 0
        checks = []
        if len(response) < 500:
            score += 2; checks.append("长度适中")
        else:
            checks.append("太长")
        if '\n' in response:
            score += 2; checks.append("有留白")
        else:
            checks.append("无留白")
        if any(w in response for w in ["哟", "嗯", "哇", "啊", "哈"]):
            score += 2; checks.append("有语气词")
        else:
            checks.append("无语气词")
        if '？' in response or '?' in response:
            score += 2; checks.append("有互动")
        else:
            checks.append("无互动")
        if '书童' in response or '我' in response:
            score += 2; checks.append("有身份")
        else:
            checks.append("无身份")
        return score, checks
    
    # ═══════════════════════════════════════════
    # 修行状态
    # ═══════════════════════════════════════════
    
    def get_cultivation_status(self):
        return {
            "soul_awakened": self.soul_awakened,
            "reflection_count": self.reflection_count,
            "session_duration_minutes": (datetime.now() - self.session_start_time).total_seconds() / 60,
            "soul_mode": SOUL_MODE,
            "self_reflection_enabled": CONFIG.get("self_reflection_enabled", True),
            "memory_turns": len(self.memory.history),
            "children_managed": self.profile_manager.get_stats()["total"],
            "engines_loaded": {
                "guardian": True,
                "medicine": True,
                "constitution": True,
                "culture": True,
                "speech": self.speech.engine_name,
                "notification": True,
                "privacy": True,
            },
        }
