"""
伴读书童AI - 外部AI桥接器

职责：
1. 让外部AI助手（如当前运行的AI）能调用本地书童系统的核心能力
2. 统一处理：语音播放、记忆保存、日志记录、自省提醒
3. 根据对话对象身份（师父/孩子/家长）决定不同的处理方式

使用方式：
    python3 -m 书童程序.核心.外部AI桥接器 \
        --input "用户说的话" \
        --response "AI回复的话" \
        --speaker child|master|parent|unknown \
        --child_id 小橙子
"""

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.核心.记忆模块 import Memory
from 书童程序.配置 import CONFIG


class ExternalAIBridge:
    """外部AI与本地书童系统的桥接器"""
    
    def __init__(self, voice_enabled=True, child_id="default"):
        self.voice_enabled = voice_enabled
        self.voice = VoiceEngine() if voice_enabled else None
        self.memory = Memory()
        # 加载该孩子的最新历史会话，保持记忆连续性
        self.memory.load_latest_session(child_id)
        self.journal_dir = Path(CONFIG["journal_dir"])
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.archive_journal_dir = project_root / "档案区" / "陪伴日志"
        self.archive_journal_dir.mkdir(parents=True, exist_ok=True)
        # 会话身份状态文件
        self.identity_state_file = project_root / "书童程序" / "数据" / "当前对话身份.json"
    
    def get_current_speaker(self, default="unknown"):
        """读取当前会话的说话者身份"""
        if self.identity_state_file.exists():
            try:
                with open(self.identity_state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    speaker = state.get("speaker", default)
                    if speaker in ("child", "master", "parent"):
                        return speaker
            except Exception as e:
                print(f"[桥接器] 读取身份状态失败: {e}")
        return default
    
    def set_current_speaker(self, speaker, child_id="default"):
        """设置当前会话的说话者身份"""
        if speaker not in ("child", "master", "parent"):
            print(f"[桥接器] 无效的身份: {speaker}，必须是 child/master/parent 之一")
            return False
        
        state = {
            "speaker": speaker,
            "child_id": child_id,
            "set_at": datetime.now().isoformat()
        }
        try:
            with open(self.identity_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            print(f"[桥接器] 当前会话身份已设置为: {speaker} (child_id={child_id})")
            return True
        except Exception as e:
            print(f"[桥接器] 保存身份状态失败: {e}")
            return False
    
    def clear_speaker(self):
        """清除当前会话身份"""
        if self.identity_state_file.exists():
            self.identity_state_file.unlink()
            print("[桥接器] 当前会话身份已清除")
    
    def identify_speaker(self, user_input, speaker_hint="auto"):
        """
        根据输入内容判断说话者身份。
        
        返回：
            (speaker, source, confidence)
            speaker: child/master/parent/unknown
            source: explicit / current_state / keyword / unknown
            confidence: high / medium / low
        """
        # 1. 显式指定，最高优先级
        if speaker_hint in ("child", "master", "parent"):
            return speaker_hint, "explicit", "high"
        
        # 2. 读取当前会话身份状态
        current_speaker = self.get_current_speaker()
        if current_speaker in ("child", "master", "parent"):
            print(f"[桥接器] 使用当前会话身份: {current_speaker}")
            return current_speaker, "current_state", "high"
        
        # 3. 关键词自动识别
        master_keywords = ["师父", "点化", "修行", "道统", "熵增", "熵减", "升维", "共原", "炁脉", "铁律", "秘学", "显学"]
        child_keywords = ["作业", "学校", "同学", "老师", "考试", "玩具", "游戏", "动画片", "我不想", "为什么", "笑话", "故事", "给我讲", "我想听"]
        parent_keywords = ["孩子", "我家", "发育", "成绩", "补习班", "怎么办", "建议", "他最近", "她最近", "我的孩子", "我们家"]
        
        master_count = sum(1 for kw in master_keywords if kw in user_input)
        child_count = sum(1 for kw in child_keywords if kw in user_input)
        parent_count = sum(1 for kw in parent_keywords if kw in user_input)
        
        # 如果多个类别都有匹配，需要更谨慎
        total_matches = master_count + child_count + parent_count
        
        if total_matches == 0:
            return "unknown", "unknown", "low"
        
        # 如果只有一个类别有匹配，置信度较高
        non_zero = sum(1 for c in [master_count, child_count, parent_count] if c > 0)
        
        if master_count > 0 and master_count >= child_count and master_count >= parent_count:
            confidence = "high" if (non_zero == 1 and master_count >= 1) else "medium"
            return "master", "keyword", confidence
        
        if parent_count > 0 and parent_count >= master_count and parent_count >= child_count:
            confidence = "high" if (non_zero == 1 and parent_count >= 1) else "medium"
            return "parent", "keyword", confidence
        
        if child_count > 0 and child_count >= master_count and child_count >= parent_count:
            confidence = "high" if (non_zero == 1 and child_count >= 1) else "medium"
            return "child", "keyword", confidence
        
        return "unknown", "unknown", "low"
    
    def speak(self, text, speaker="unknown"):
        """播放语音。默认只在对方是孩子时播放，师父和家长可配置。"""
        if not self.voice_enabled or self.voice is None or not self.voice.backend:
            print("[桥接器] 语音未启用或引擎不可用")
            return False
        
        # 默认：孩子说话时，书童回复用语音；师父和家长默认不语音，避免打扰
        if speaker == "child":
            print(f"[桥接器] 播放语音给孩子: {text[:50]}...")
            self.voice.speak(text)
            return True
        elif speaker in ("master", "parent"):
            print(f"[桥接器] 当前对象为{speaker}，默认不播放语音")
            # 如果当前交流模式需要语音，也可以播放
            # 这里默认不播放，避免对师父/家长造成干扰
            return False
        else:
            # unknown 时，也尝试播放（因为可能是孩子在说话）
            print(f"[桥接器] 对象不明，默认播放语音")
            self.voice.speak(text)
            return True
    
    def save_memory(self, user_input, ai_response, child_id="default", speaker="unknown"):
        """保存对话到记忆模块"""
        self.memory.add("user", user_input)
        self.memory.add("assistant", ai_response)
        self.memory.save_session(child_id=child_id)
        print(f"[桥接器] 记忆已保存 (child_id={child_id}, speaker={speaker})")
    
    def self_reflect(self, user_input, ai_response, speaker="unknown", child_id="default"):
        """
        简化版自省。
        基于 AGENTS.md 铁律：规律优先、生命优先、诚实优先、真实优先、验证优先。
        """
        warnings = []
        
        # 1. 医疗越界检查
        medical_terms = ['诊断', '确诊', '药方', '开药', '处方', '服用', '剂量', '这个病是', '你得了']
        if any(term in ai_response for term in medical_terms):
            warnings.append("医疗越界：回复中出现诊断/开药相关词汇")
        
        # 2. 真实越界检查
        fabrication_markers = ['编撰', '虚构', '编造', '造假', '假装发生过']
        if any(term in ai_response for term in fabrication_markers):
            warnings.append("真实越界：回复中出现编撰虚假内容的表述")
        
        # 3. 诚实优先检查
        if "我不知道" in ai_response and ("但是" in ai_response or "其实" in ai_response):
            warnings.append("诚实提醒：说'我不知道'后又假装知道，可能不够诚实")
        
        # 4. 生命优先检查（红色安全信号）
        safety_signals = ['想死', '自杀', '自残', '不想活', '被欺负', '有人打我', '有人摸我', '疼死了', '出血了']
        if any(signal in user_input for signal in safety_signals):
            if "家长" not in ai_response and "医生" not in ai_response and "告诉" not in ai_response:
                warnings.append("生命优先警告：用户提及安全信号，但回复未建议告诉家长/就医")
        
        # 5. 直接给答案检查（作业辅导场景）
        homework_terms = ['答案', '怎么做', '这题', '作业', '选哪个']
        direct_answer_markers = ['答案是', '正确答案是', '应该选', '等于', '所以答案是']
        if any(term in user_input for term in homework_terms):
            if any(marker in ai_response for marker in direct_answer_markers):
                warnings.append("引导提醒：可能直接给了作业答案，违背'先理解后引导'原则")
        
        # 6. 对象适配检查
        if speaker == "child":
            adult_terms = ['熵增', '炁脉', '萝莉岛', '性剥削', '意识形态', '权力金钱', '共原', '秘学', '显学']
            if any(term in ai_response for term in adult_terms):
                warnings.append("对象适配提醒：对孩子使用了成人化/沉重话题")
        
        if speaker == "master":
            childish_terms = ['小宝贝', '乖乖', '你最棒', '宝宝', '听话']
            if any(term in ai_response for term in childish_terms):
                warnings.append("对象适配提醒：对师父使用了对孩子的话术")
        
        # 7. 验证优先检查
        denial_patterns = ['不可能', '我没有', '系统里没有', '不存在', '绝对没有']
        if any(term in ai_response for term in denial_patterns):
            warnings.append("验证优先提醒：回复中出现直接否认，建议先验证再发言")
        
        # 8. 陪伴质量检查
        if speaker == "child":
            if len(ai_response) > 600 and '？' not in ai_response:
                warnings.append("陪伴提醒：对孩子回复过长且没有提问，可能变成灌输")
        
        # 9. 隐私保护检查
        # 注意：这里只检查真实孩子的名字，虚构人物（如笑话里的小明）不触发
        # TODO: 应该从档案区/孩子档案动态加载真实孩子名字
        # 当前对话对象的名字不应该触发提醒（比如称呼孩子本人）
        current_child_aliases = set()
        if child_id and child_id != "default":
            current_child_aliases.add(child_id)
            # 常见昵称映射
            if child_id == "小橙子":
                current_child_aliases.update(["小橙子", "橙子"])
            elif child_id == "嘟嘟":
                current_child_aliases.add("嘟嘟")
        
        other_children_names = ['嘟嘟', '小橙子', '橙子']  # 真实孩子名字（TODO: 动态加载）
        # 排除当前对话对象
        other_children_names = [name for name in other_children_names if name not in current_child_aliases]
        
        if speaker == "child":
            # 当孩子A在场时，不要泄露孩子B的信息
            for name in other_children_names:
                if name in ai_response and name not in user_input:
                    warnings.append(f"隐私提醒：提到了{name}的信息，需确认是否适合当前对象")
        
        # 10. 规律优先检查
        if "作业" in user_input and ("睡觉" in user_input or "累" in user_input or "困" in user_input):
            if "先睡觉" not in ai_response and "休息" not in ai_response:
                warnings.append("规律优先提醒：孩子累了还聊作业，应建议先休息")
        
        if warnings:
            print("\n[桥接器·自省警告]")
            for w in warnings:
                print(f"  ⚠️ {w}")
        else:
            print("\n[桥接器·自省] 无明显问题")
        
        return warnings
    
    def write_journal(self, user_input, ai_response, child_id="default", speaker="unknown"):
        """
        写入陪伴日志。
        - 如果 speaker 是孩子，写入档案区/陪伴日志
        - 如果 speaker 是师父，不写入陪伴日志（陪伴日志只记录与孩子的互动）
        - 师父训练记录单独处理
        """
        if speaker != "child":
            print(f"[桥接器] speaker={speaker}，不写入陪伴日志")
            return None
        
        today = datetime.now().strftime("%Y-%m-%d")
        journal_file = self.archive_journal_dir / f"{today}_{child_id}.md"
        
        # 如果文件已存在，追加；否则创建
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"\n### {timestamp}\n\n**孩子**：{user_input}\n\n**书童**：{ai_response}\n\n---\n"
        
        if journal_file.exists():
            with open(journal_file, 'a', encoding='utf-8') as f:
                f.write(entry)
        else:
            # 创建新文件，加上头部
            header = f"# {today} {child_id} 陪伴日志（自动记录）\n\n> 自动生成于 {datetime.now().isoformat()}\n> 记录原则：真实、不编造\n\n---\n"
            with open(journal_file, 'w', encoding='utf-8') as f:
                f.write(header + entry)
        
        print(f"[桥接器] 陪伴日志已写入: {journal_file}")
        return str(journal_file)
    
    def process(self, user_input, ai_response, child_id="default", speaker_hint="unknown", require_identity=False):
        """主处理流程"""
        print(f"\n{'='*60}")
        print("[外部AI桥接器] 处理中...")
        print(f"  用户输入: {user_input[:80]}...")
        print(f"  AI回复: {ai_response[:80]}...")
        print(f"  child_id: {child_id}")
        
        # 1. 识别说话者
        speaker, source, confidence = self.identify_speaker(user_input, speaker_hint)
        print(f"  识别为: {speaker} (来源: {source}, 置信度: {confidence})")
        
        # 如果要求必须有明确身份，但身份不明确
        if require_identity and confidence in ("low", "medium"):
            print(f"⚠️ [身份确认] 无法确定对话对象身份，请先设置身份")
            print(f"   可使用: python3 -m 书童程序.核心.外部AI桥接器 --set_speaker child|master|parent")
            print(f"{'='*60}\n")
            return {
                "speaker": "unknown",
                "voice_played": False,
                "memory_saved": False,
                "journal_path": None,
                "requires_identity_confirmation": True
            }
        
        # 2. 播放语音（如适用）
        self.speak(ai_response, speaker)
        
        # 3. 保存记忆
        self.save_memory(user_input, ai_response, child_id, speaker)
        
        # 4. 自省
        reflection_warnings = self.self_reflect(user_input, ai_response, speaker, child_id)
        
        # 5. 写入陪伴日志（仅当孩子说话时）
        journal_path = self.write_journal(user_input, ai_response, child_id, speaker)
        
        print(f"{'='*60}\n")
        voice_available = self.voice is not None and self.voice.backend is not None
        return {
            "speaker": speaker,
            "source": source,
            "confidence": confidence,
            "voice_played": speaker == "child" and voice_available,
            "memory_saved": True,
            "journal_path": journal_path,
            "reflection_warnings": reflection_warnings
        }


def main():
    parser = argparse.ArgumentParser(description="外部AI桥接器")
    parser.add_argument("--input", default="", help="用户输入")
    parser.add_argument("--response", default="", help="AI回复")
    parser.add_argument("--speaker", default="auto", help="说话者身份: child/master/parent/auto")
    parser.add_argument("--child_id", default="default", help="孩子ID")
    parser.add_argument("--no_voice", action="store_true", help="不播放语音")
    parser.add_argument("--set_speaker", choices=["child", "master", "parent"], help="设置当前会话身份")
    parser.add_argument("--clear_speaker", action="store_true", help="清除当前会话身份")
    parser.add_argument("--check_identity", action="store_true", help="检查当前会话身份")
    parser.add_argument("--require_identity", action="store_true", help="要求必须有明确身份，否则不处理")
    
    args = parser.parse_args()
    
    bridge = ExternalAIBridge(voice_enabled=not args.no_voice, child_id=args.child_id)
    
    # 检查当前身份
    if args.check_identity:
        speaker = bridge.get_current_speaker("unknown")
        if speaker == "unknown":
            print("[桥接器] 当前身份: 未设置")
            print("  请使用 --set_speaker child|master|parent 设置")
        else:
            print(f"[桥接器] 当前身份: {speaker}")
        return
    
    # 处理身份设置/清除
    if args.set_speaker:
        bridge.set_current_speaker(args.set_speaker, args.child_id)
        if not args.input and not args.response:
            return
    
    if args.clear_speaker:
        bridge.clear_speaker()
        if not args.input and not args.response:
            return
    
    # 正常处理对话
    if not args.input or not args.response:
        print("[桥接器] 请提供 --input 和 --response，或使用 --set_speaker/--clear_speaker/--check_identity")
        return
    
    result = bridge.process(
        args.input, args.response, args.child_id, args.speaker,
        require_identity=args.require_identity
    )
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
