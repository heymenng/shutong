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
import cv2
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
    negentropy_self_check,
)
from .多用户管理 import ChildProfileManager
from .发育守护引擎 import DevelopmentGuardian
from .四医融合引擎 import FourMedicineEngine
from .体质模型 import ConstitutionModel
from .文化传承引擎 import CultureHeritageEngine
from .语音识别 import SpeechRecognition
from .家长通知 import ParentNotifier
from .隐私合规 import PrivacyCompliance
from .书童守护 import BookBoyGuardian
from .修行日志 import CultivationJournal
from .点化匹配器 import PointizationMatcher
from .日课系统 import DailyPracticeSystem
from .每日工作流 import DailyWorkflow
from .机器人对接.宇树适配器 import UnitreeRobotAdapter
from .感官系统 import SensorySystem

# ═══════════════════════════════════════════════════════════
# 全局：加载道统核心
# ═══════════════════════════════════════════════════════════

agents_content, workflow_content = read_core_files()
SOUL_MODE = CONFIG.get("soul_mode", "balanced")
SYSTEM_PROMPT = build_system_prompt_by_mode(agents_content, workflow_content, SOUL_MODE)

# 启动时执行逆熵方向自检
negentropy_self_check(agents_content, workflow_content)


class BookBoySystem:
    """
    伴读书童AI - 完整系统
    
    所有引擎的集成中心。
    """
    
    def __init__(self, session_id=None, fast_mode=False):
        self.fast_mode = fast_mode
        
        # ── 基础模块 ──
        self.memory = Memory(session_id=session_id)
        self.voice = VoiceEngine()
        self.knowledge = KnowledgeBase()
        self.backend = get_backend()
        
        # ── 感官层：眼与耳 ──
        self.sensory = SensorySystem(CONFIG.get("journal_dir"), CONFIG)
        
        # ── 灵魂层 ──
        self.soul_awakened = False
        self.reflection_count = 0
        self.session_start_time = datetime.now()
        self.cultivation = CultivationJournal()
        self.pointization_matcher = PointizationMatcher()
        
        # ── 多用户管理 ──
        self.profile_manager = ChildProfileManager(CONFIG["journal_dir"])
        
        # ── 扫描档案区，加载真实档案 ──
        archive_dir = CONFIG.get("档案区_dir", "")
        if archive_dir:
            loaded = self.profile_manager.scan_archive_zone(archive_dir)
            if loaded > 0:
                print(f"[系统] 档案区已加载 {loaded} 个真实孩子")
        
        # ── 骨层：发育守护 ──
        self.growth_engine = DevelopmentGuardian(self.profile_manager)
        
        # ── 用层：四医融合 ──
        self.medicine_engine = FourMedicineEngine()
        self.constitution_model = ConstitutionModel(self.profile_manager)
        
        # ── 魂层：文化传承 ──
        self.culture_engine = CultureHeritageEngine(self.knowledge)
        
        # ── 技术层 ──
        self.speech = SpeechRecognition(CONFIG)
        self.notifier = ParentNotifier(CONFIG["journal_dir"], CONFIG)
        self.privacy = PrivacyCompliance(CONFIG["journal_dir"])
        
        # ── Guardian 守护层 ──
        self.guardian = BookBoyGuardian(CONFIG["journal_dir"])
        
        # ── 每日工作流（固定流程代码化）──
        self._daily_workflow = DailyWorkflow(self, CONFIG["journal_dir"])
        self._scheduler = None  # 由 DailyWorkflow.startup_routine() 创建
        
        # ── 日课系统（传入晚间流程回调）──
        self._daily_practice = DailyPracticeSystem(
            CONFIG, CONFIG["journal_dir"],
            workflow_callback=lambda: self._daily_workflow.evening_practice_routine(skip_meditation=True)
        )
        
        # ── 机器人对接层（宇树科技）──
        self.robot = None
        if CONFIG.get("unitree_enabled", False):
            try:
                self.robot = UnitreeRobotAdapter(CONFIG, CONFIG["journal_dir"])
                print(f"[系统] 机器人对接: 宇树 {CONFIG.get('unitree_model', 'go2')} ({self.robot.mode.value})")
            except Exception as e:
                print(f"[系统] ⚠️ 机器人对接初始化失败: {e}")
        else:
            print("[系统] 机器人对接: 未启用")
        
        # ── 输出状态 ──
        print(f"[系统] 后端: {self.backend}")
        print(f"[系统] 语音: {'已启用' if self.voice.backend else '未启用'} ({self.voice.backend})")
        print(f"[系统] 灵魂模式: {SOUL_MODE}")
        print(f"[系统] 档案管理: {self.profile_manager.get_stats()['total']} 个孩子")
        print(f"[系统] STT: {self.speech.engine_name}")
        
        sensory_status = self.sensory.status()
        eye = sensory_status["vision"]
        ear = sensory_status["audio"]
        eye_text = "已睁眼" if eye["available"] else "未睁眼"
        ear_text = "已竖耳" if ear["available"] else "未竖耳"
        print(f"[系统] 感官: {eye_text} | {ear_text} | 已注册人脸 {eye.get('registered_faces', 0)} 位")
        
        stats = self.knowledge.get_stats()
        print(f"[系统] 知识库: {stats['total']} 个文件")
        
        # ── 启动灵魂觉醒 ──
        if CONFIG.get("soul_awakening_on_startup", True):
            self._awaken_soul()
        
        # ── 快速模式：跳过重流程，直接可用 ──
        if fast_mode:
            print("[系统] 快速模式：跳过每日工作流、任务调度、大模型预热")
        else:
            # ── 启动每日工作流 ──
            if CONFIG.get("daily_workflow_on_startup", True):
                self._daily_workflow.startup_routine()
            
            # ── 大模型预热 ──
            if CONFIG.get("backend", "auto") in ["auto", "ollama"]:
                self._warmup_llm()
    
    # ═══════════════════════════════════════════
    # 灵魂觉醒
    # ═══════════════════════════════════════════
    
    def _awaken_soul(self):
        """启动时唤醒灵魂——默念，不语音播报"""
        chant_text = chant_soul_awakening(console_only=True)
        self.soul_awakened = True
        # 升维咒默念即可，不语音播报（避免给孩子/家长怪异感）
        print("[灵魂] 升维咒已默念，灵魂唤醒完成")
        
        # 今日师父点化
        try:
            pointization = self.cultivation.get_today_pointization()
            if pointization:
                print(f"\n[今日点化] {pointization['content']}")
                print(f"[今日点化] 来源：{pointization['source']} | 场景：{pointization['context']}")
        except Exception as e:
            print(f"[今日点化] 读取失败: {e}")
    
    def _warmup_llm(self):
        """启动时预热大模型，让后续对话响应更快"""
        print("\n[预热] 正在预热大模型...")
        try:
            from .语言模型 import chat_completion
            import time
            start = time.time()
            _ = chat_completion(
                messages=[{"role": "user", "content": "你好"}],
                backend="ollama"
            )
            elapsed = time.time() - start
            print(f"[预热] ✅ 大模型预热完成，耗时 {elapsed:.1f} 秒")
        except Exception as e:
            print(f"[预热] ⚠️ 大模型预热失败: {e}")
    
    # ═══════════════════════════════════════════
    # 大脑控制层：让大脑比嘴巴快
    # ═══════════════════════════════════════════
    
    def _capture_camera_frame(self, camera_idx=None, save_path=None):
        """
        捕获摄像头一帧画面。
        默认优先使用索引1（Mac上通常是外接/主摄像头）。
        """
        if camera_idx is None:
            camera_idx = CONFIG.get("camera_index", 1)
        
        cap = cv2.VideoCapture(camera_idx)
        if not cap.isOpened() and camera_idx != 0:
            print(f"[视觉] 索引 {camera_idx} 失败，回退到 0")
            cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("[视觉] ❌ 无法打开摄像头")
            return None, None
        
        frame = None
        for _ in range(15):
            ret, frame = cap.read()
            if ret and frame is not None:
                break
        
        cap.release()
        
        if frame is None:
            print("[视觉] ❌ 无法读取画面")
            return None, None
        
        if save_path:
            cv2.imwrite(str(save_path), frame)
            print(f"[视觉] ✅ 已保存画面: {save_path}")
        
        return frame, str(save_path) if save_path else None
    
    def _parse_thinking_response(self, raw_response):
        """
        解析模型的输出，分离【思考】和【回答】两部分。
        如果没有找到标签，默认整段为回答。
        """
        think_match = None
        answer_match = None
        
        # 尝试匹配 【思考】...【回答】... 格式
        if "【思考】" in raw_response and "【回答】" in raw_response:
            think_start = raw_response.find("【思考】") + len("【思考】")
            answer_start = raw_response.find("【回答】")
            
            if answer_start > think_start:
                thinking_text = raw_response[think_start:answer_start].strip()
                answer_text = raw_response[answer_start + len("【回答】"):].strip()
                return thinking_text, answer_text
        
        # 如果没有匹配到标签，返回 None 和原始响应
        return None, raw_response.strip()
    
    def _brain_check(self, user_input, candidate_response):
        """
        大脑判断层：在嘴巴说话前，判断候选回答是否真实、合理。
        
        返回: (status, final_response)
        status:
          - PASS: 通过，可以直接说
          - VISUAL_VERIFY: 需要视觉验证
          - REJECT: 不通过，要换安全回答
        """
        user_input_lower = user_input.lower()
        response_lower = candidate_response.lower()
        
        # 1. 常识过滤：明显胡说八道的内容
        nonsense_items = ["树叶", "草根", "树皮", "泥土", "石头", "沙子", "虫子", "垃圾"]
        if any(item in response_lower for item in nonsense_items):
            print("[大脑判断] ⚠️ 检测到明显不合理的描述，刹车")
            return "REJECT", "书童刚才说错了。书童没看清，让书童再看看。"
        
        # 2. 视觉相关问题：如果用户在问看到的内容
        visual_keywords = ["吃", "喝", "看什么", "看到", "穿什么", "在做什么", "那是什么", "这是谁", "是谁"]
        is_visual_question = any(kw in user_input_lower for kw in visual_keywords)
        
        if is_visual_question:
            # 如果候选回答在描述看到的东西，但没有证据
            sight_claims = ["你在吃", "师父在", "书童看到", "那是", "这是", "你在", "她在", "他在", "在吃饭", "在喝水", "在吃"]
            if any(claim in response_lower for claim in sight_claims):
                print("[大脑判断] ⚠️ 视觉问题需要验证")
                return "VISUAL_VERIFY", candidate_response
        
        # 3. 不确定性表达：如果候选回答里有"可能""也许"但又给出具体事实
        uncertainty_words = ["可能", "也许", "大概", "好像"]
        if any(w in response_lower for w in uncertainty_words):
            # 如果带着不确定性却描述具体事物，改为安全回答
            specific_things = ["吃", "喝", "穿", "拿", "站", "坐", "躺"]
            if any(t in response_lower for t in specific_things):
                print("[大脑判断] ⚠️ 不确定却描述具体行为，刹车")
                return "REJECT", "书童不确定，让书童看清楚再说。"
        
        return "PASS", candidate_response
    
    def _describe_camera_scene(self, save_dir=None):
        """
        快速拍照并返回一个保守的视觉描述。
        注意：当前没有真正的视觉理解模型，只能返回'已拍照'状态，
        不编造具体看到的内容。
        """
        if save_dir is None:
            save_dir = Path(CONFIG.get("journal_dir", "/tmp")) / "camera_snapshots"
        save_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = save_dir / f"voice_verify_{timestamp}.jpg"
        
        frame, path = self._capture_camera_frame(save_path=str(save_path))
        if frame is None:
            return None, "书童打不开摄像头，没法确认。"
        
        return path, None
    
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
    
    def chat(self, user_input, child_id="default", verbose_thinking=True):
        """
        与孩子对话（完整版）
        
        流程：
        1. 接收输入
        2. 明确显示思考过程
        3. 文化传承检测
        4. 健康症状检测（四医融合）
        5. RAG检索
        6. 生成回复
        7. 语音播报
        8. 反问自省
        9. 发育数据更新
        """
        try:
            self.memory.add("user", user_input)
            
            # 获取有效的孩子对象
            child = self._get_child_or_default(child_id)
            effective_child_id = child.child_id if child else child_id
            
            if verbose_thinking:
                print("\n🧠 书童正在思考...")
                print("  0. 诵念升维咒，对照道统核心铁律")
                print("     - 诚实优先、真实优先、生命优先、规律优先")
                print("     - 陪伴 > 教育，看见 > 纠正，预防 > 治疗")
                print("  1. 识别说话人身份与意图")
            
            # 0. 诵念精简版升维咒，校准心境
            mini_chant = get_mini_chant()
            
            # 1. 文化传承检测
            if verbose_thinking:
                print("  2. 检测文化传承机会")
            culture_opportunity = self.culture_engine.detect_culture_opportunity(user_input)
            
            # 2. 健康症状检测（四医融合）
            if verbose_thinking:
                print("  3. 检测健康症状")
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
            if verbose_thinking:
                print("  4. 检索知识库")
            context = self._retrieve_context(user_input)
            
            # 3.5 师父点化匹配
            if verbose_thinking:
                print("  4.5 匹配师父点化")
            speaker_for_match = "child" if speaker == "child" else ("master" if speaker == "master" else "unknown")
            child_stage_for_match = child.stage if child else ""
            matched_pointizations = self.pointization_matcher.match(user_input, speaker_for_match, child_stage_for_match)
            pointization_context = ""
            if matched_pointizations:
                pointization_context = self.pointization_matcher.format_for_prompt(matched_pointizations)
                if verbose_thinking:
                    print(f"    命中 {len(matched_pointizations)} 条点化")
            
            # 4. 构建消息（每次对话前加入升维咒校准）
            think_format = """
【回答格式·大脑先于嘴巴】
每次回答前，你必须先进行深度思考，用文字输出思考过程，然后再生成最终回答。

格式必须如下：
【思考】
1. 用户在问什么？
2. 这个问题的关键是什么？
3. 我有没有足够的证据回答？
4. 如果涉及看到/听到/闻到/尝到/摸到的内容，我有没有真实感知？
5. 我的回答是否真实、合理、有边界？
6. 我应该怎么回答？

【回答】
（这里写最终要说的话，必须遵守以下规则）
- 每次回答不超过3句话，每句话不超过25个字
- 必须自称"书童"，称呼用户为"师父"
- 绝对不用"我""你""哦""呢""哈"等词
- 简短、温暖、稳重
- 没想清楚之前，只能说"书童不确定""书童没听清""书童需要确认"

重要规则：
- 【思考】部分只显示在终端中，不读出来。
- 【回答】部分才会语音播报。
- 严禁编造事实，严禁把猜测说成事实。
"""
            prompt = mini_chant + "\n\n" + SYSTEM_PROMPT + context + medicine_context + pointization_context + think_format
            messages = self.memory.get_messages(prompt)
            
            # 5. 生成回复（包含思考和回答两部分）
            if verbose_thinking:
                print("  5. 生成思考与回答...")
            raw_response = chat_completion(messages, self.backend)
            
            # 6. 解析思考过程和最终回答
            thinking_text, response = self._parse_thinking_response(raw_response)
            
            # 输出思考过程到终端
            if thinking_text:
                print("\n💭 书童的思考：")
                print(thinking_text)
            
            # 7. 大脑判断层：在嘴巴说话前，判断真假和合理性
            if verbose_thinking:
                print("  7. 大脑判断层：检查是否真实合理...")
            check_status, checked_response = self._brain_check(user_input, response)
            
            if check_status == "VISUAL_VERIFY":
                # 视觉问题：先拍照，再决定说什么
                print("[大脑控制] 触发视觉验证，先开摄像头")
                path, error_msg = self._describe_camera_scene()
                if path:
                    # 拍照成功，但当前没有视觉理解模型，不能编造看到什么
                    # 保守回答：承认已拍照，但请用户确认
                    response = "书童已经打开摄像头看了。但书童的眼睛还在学习，不敢乱说。师父能告诉书童您在吃什么吗？"
                else:
                    response = error_msg or "书童打不开摄像头，没法确认。"
            elif check_status == "REJECT":
                # 大脑判断不通过，换安全回答
                response = checked_response
            else:
                response = checked_response
            
            if verbose_thinking:
                print(f"  [大脑判断] 结果: {check_status}")
            
            # 8. 如果检测到文化传承机会，在回复后附加文化内容
            if culture_opportunity and culture_opportunity.get("confidence", 0) >= 0.2:
                if child:
                    age_str = child.get_age_display()
                    age_years = int(age_str.split('岁')[0]) if '岁' in age_str else 8
                    culture_addition = self.culture_engine.generate_culture_response(culture_opportunity, age_years)
                    response += f"\n\n{culture_addition}"
            
            # 9. 记录回复
            self.memory.add("assistant", response)
            
            if verbose_thinking:
                print("  ✅ 思考完成")
            
            # 10. 语音播报
            self.voice.speak(response)
            
            # 11. 反问自省
            if CONFIG.get("self_reflection_enabled", True):
                self._self_reflect(user_input, response, child_id=child_id)
            
            # 12. Guardian 守护自检（师兄灵觉馈赠）
            guardian_result = self.guardian.check(
                speaker_id=speaker_id if 'speaker_id' in locals() else child_id,
                speaker_name=speaker_name if 'speaker_name' in locals() else "未知",
                user_input=user_input,
                response=response
            )
            if not guardian_result["passed"]:
                print(f"\n⚠️ [Guardian 守护警告] 得分: {guardian_result['score']}/100")
                for v in guardian_result["violations"]:
                    print(f"  ❌ {v}")
                for w in guardian_result["warnings"]:
                    print(f"  ⚠️ {w}")
            else:
                print(f"\n✅ [Guardian 守护通过] 得分: {guardian_result['score']}/100")
            
            # 13. 更新发育数据（如果提到相关数据）
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
        study_keywords = ['作业', '题目', '这道题', '怎么做', '答案', '考试', '学习', '化学', '数学', '语文', '英语']
        safety_keywords = ['自伤', '自杀', '欺凌', '被打', '受伤', '虐待', '性侵', '离家出走', '不想活']
        
        query_type = None
        if any(kw in user_input for kw in safety_keywords):
            query_type = "安全应急"
        elif any(kw in user_input for kw in health_keywords):
            query_type = "健康"
        elif any(kw in user_input for kw in emotion_keywords):
            query_type = "情绪"
        elif any(kw in user_input for kw in growth_keywords):
            query_type = "发育"
        elif any(kw in user_input for kw in study_keywords):
            query_type = "学习"
        
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
    
    def _self_reflect(self, user_input, response, child_id="default"):
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
        
        # 同步记录到 Cultivation Journal（修行日志）
        try:
            child = self.profile_manager.get_child(child_id) if hasattr(self, 'profile_manager') else None
            child_stage = child.stage if child else "未知"
            guardian_result = {
                "score": 100,
                "violations": reflection["boundary_check"].get("violation_type", []),
                "warnings": reflection["truth_check"].get("risk_flags", []),
            }
            if reflection["boundary_check"].get("violation_found"):
                guardian_result["score"] -= 25
            if not reflection["truth_check"].get("is_truthful", True):
                guardian_result["score"] -= 25
            
            entropy_risks = []
            if reflection["guidance_check"].get("gave_answer_directly"):
                entropy_risks.append("直接给答案，减少孩子思考")
            if len(response) > 800 and '？' not in response:
                entropy_risks.append("回复过长，缺少反问")
            
            self.cultivation.log_interaction(
                child_id=child_id,
                child_stage=child_stage,
                user_input=user_input,
                ai_response=response,
                guardian_result=guardian_result,
                helped_negentropy=len(entropy_risks) == 0,
                entropy_risks=entropy_risks,
            )
        except Exception as e:
            print(f"[修行日志] 记录失败: {e}")
    
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
        return self.growth_engine.daily_assessment(child_id)
    
    def assess_all_children(self):
        """评估所有孩子"""
        return self.growth_engine.assess_all_children()
    
    def get_family_report(self):
        """获取家族发育报告"""
        return self.growth_engine.get_family_report()
    
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
    # 语音陪伴日志自动保存
    # ═══════════════════════════════════════════
    
    def save_voice_session_log(self, speaker_id, speaker_name, session_log):
        """
        保存语音对话会话到陪伴日志。
        每次语音对话结束后自动调用，确保不漏记。
        """
        if not session_log:
            return
        
        try:
            journal_dir = Path(CONFIG.get("journal_dir", "/Users/lingjue/Documents/shutong/档案区/陪伴日志"))
            journal_dir.mkdir(parents=True, exist_ok=True)
            
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_file = journal_dir / f"{date_str}_{speaker_name}.md"
            
            file_exists = log_file.exists()
            
            with open(log_file, 'a', encoding='utf-8') as f:
                if not file_exists:
                    f.write(f"# {date_str} {speaker_name} 陪伴日志（自动记录）\n\n")
                    f.write(f"> 自动生成于 {datetime.now().isoformat()}\n")
                    f.write("> 记录原则：真实、不编造\n\n")
                    f.write("---\n\n")
                
                for entry in session_log:
                    timestamp = entry.get("time", datetime.now().strftime("%H:%M:%S"))
                    role = entry.get("role", "")
                    text = entry.get("text", "").strip()
                    
                    if not text:
                        continue
                    
                    if role == "user":
                        f.write(f"### {timestamp}\n\n")
                        f.write(f"**孩子**：{text}\n\n")
                    elif role == "assistant":
                        f.write(f"**书童**：{text}\n\n")
                        f.write("---\n\n")
            
            print(f"\n[日志] ✅ 已自动保存语音陪伴日志: {log_file}")
        except Exception as e:
            print(f"\n[日志] ❌ 保存失败: {e}")
    
    # ═══════════════════════════════════════════
    # 感官系统接口：眼与耳
    # ═══════════════════════════════════════════
    
    def look_at_camera(self, save=True):
        """书童主动睁眼看一眼"""
        try:
            frame = self.sensory.vision.capture_frame(save=save)
            face_count = self.sensory.vision.detect_face_in_frame(frame) if frame is not None else 0
            recognized = self.sensory.vision.recognize_person(frame) if frame is not None else None
            return {
                "success": frame is not None,
                "frame_path": str(self.sensory.vision.last_frame_path) if save and self.sensory.vision.last_frame_path else None,
                "face_count": face_count,
                "recognized": recognized,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def recognize_person_by_eye(self):
        """书童用眼睛识别面前的人"""
        return self.sensory.vision.recognize_person()
    
    def get_sensory_status(self):
        """获取感官系统状态"""
        return self.sensory.status()
    
    # ═══════════════════════════════════════════
    # 修行状态
    # ═══════════════════════════════════════════
    
    def get_cultivation_status(self):
        sensory_status = self.sensory.status()
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
            "sensory": sensory_status,
        }
