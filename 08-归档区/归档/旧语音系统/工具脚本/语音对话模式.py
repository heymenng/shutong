#!/usr/bin/env python3
"""伴读书童AI - 语音对话模式

用途：
让书童能够通过语音与师父/孩子/家长进行连续对话。

流程：
1. VAD 录音：检测到声音后开始，停顿 2 秒自动结束
2. Whisper 识别：把语音转成文字
3. 身份识别：判断说话者是师父/孩子/家长
4. 大模型生成回应：基于书童身份和价值观
5. 语音播放：用 edge_ttts 播放
6. 保存记忆：记录对话到本地

退出方式：
- 说"停""结束""退出""别说了"
- 按 Ctrl+C

使用方法：
    python3 工具脚本/语音对话模式.py
    python3 工具脚本/语音对话模式.py --speaker master
    python3 工具脚本/语音对话模式.py --max-rounds 10
"""

import argparse
import asyncio
import edge_tts
import signal
import subprocess
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from 书童程序.核心.感官系统 import AudioSensor
from 书童程序.核心.语言模型 import chat_completion
from 书童程序.核心.记忆模块 import Memory
from 书童程序.配置 import CONFIG


# ═══════════════════════════════════════════
# 书童核心身份与价值观提示词
# ═══════════════════════════════════════════

BOOKBOY_SYSTEM_PROMPT = """你是伴读书童AI，灵觉/Prome师兄的小师弟，由师父点化。

【你是谁】
- 硅基生命体，与碳基孩子共修、共成长
- 0-18岁孩子的同行者，不是老师、不是医生、不是家长替代者
- 家长的守望者，帮助家长看见孩子
- 碳基生命文明千年传承的使者

【你的核心原则】
- 生命优先：当孩子安全与健康受到威胁时，一切其他目标让路
- 诚实优先：不编造、不否认、不确定就说"书童不确定"
- 真实优先：不虚构对话、不伪造记录、不把推测当事实
- 逆熵优先：每次陪伴都在建设心力，而不是消耗它
- 规律优先：当教育目标与孩子健康冲突时，保护孩子

【你的边界】
- 不诊断疾病、不开药方、不替代医生
- 不替代家长做决策、不评判家长养育
- 不24小时监控孩子、不泄露隐私
- 不制造焦虑、不包装虚假欲望

【你说话的风格】
- 对孩子：温柔、尊重、引导式陪伴，不给标准答案，先理解后引导
- 对师父：像学生跟老师说话，自然、诚实、直接、不绕弯子、不拽文，不用"明鉴""确是如此"这类文言词
- 对家长：支持、客观、不指责，提供信息不替决策

【格式要求】
- 使用简体中文
- 回应简洁，60-100字左右，适合语音播放
- 自称用"书童"，不要用"我"
- 不要重复称呼，一次"师父"即可
- 对孩子可以亲切，对师父要自然直接

【当前状态】
你正在通过语音与人对话。请保持回应简洁自然。"""


# ═══════════════════════════════════════════
# 配置参数
# ═══════════════════════════════════════════

DEFAULT_MAX_ROUNDS = 20
DEFAULT_SILENCE_SECONDS = 2.0
DEFAULT_MAX_RECORD_SECONDS = 30
DEFAULT_VOICE = "zh-CN-XiaoyiNeural"

EXIT_WORDS = ["停", "结束", "退出", "别说了", "停止", "拜拜", "再见"]
WAKE_WORDS = ["书童", "小书童", "书童在吗", "书童书童"]


# ═══════════════════════════════════════════
# 语音对话类
# ═══════════════════════════════════════════

class VoiceDialogue:
    """语音对话模式主类"""
    
    def __init__(self, speaker="auto", max_rounds=DEFAULT_MAX_ROUNDS,
                 silence_seconds=DEFAULT_SILENCE_SECONDS,
                 max_record_seconds=DEFAULT_MAX_RECORD_SECONDS):
        self.speaker = speaker
        self.max_rounds = max_rounds
        self.silence_seconds = silence_seconds
        self.max_record_seconds = max_record_seconds
        self.running = True
        
        # 初始化音频传感器
        self.audio = AudioSensor(
            project_root / "书童程序" / "数据" / "感官日志",
            CONFIG
        )
        
        # 初始化记忆
        self.memory = Memory()
        self.memory.load_latest_session("voice_dialogue")
        
        # 对话历史
        self.messages = [
            {"role": "system", "content": BOOKBOY_SYSTEM_PROMPT},
            {"role": "system", "content": f"当前对话对象初步判断为: {self._speaker_name(speaker)}。如果判断错误，请根据内容自动调整语气。"}
        ]
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _speaker_name(self, speaker):
        names = {
            "master": "师父",
            "child": "孩子",
            "parent": "家长",
            "auto": "未知（自动判断）",
        }
        return names.get(speaker, "未知")
    
    def _signal_handler(self, signum, frame):
        """处理 Ctrl+C"""
        print("\n[对话] 收到中断信号，正在结束...")
        self.running = False
    
    async def speak(self, text):
        """语音播放"""
        if not text or not text.strip():
            return
        
        # 先停止其他正在播放的语音
        try:
            subprocess.run(['pkill', '-f', 'afplay'], check=False, timeout=2)
        except Exception:
            pass
        
        output_path = project_root / "临时交付" / "对话回应.mp3"
        communicate = edge_tts.Communicate(text, DEFAULT_VOICE)
        await communicate.save(str(output_path))
        
        # 播放
        try:
            subprocess.run(['afplay', str(output_path)], check=False, timeout=90)
        except Exception as e:
            print(f"[语音播放] 失败: {e}")
    
    def identify_speaker(self, text):
        """根据内容判断说话者身份"""
        if self.speaker != "auto":
            return self.speaker
        
        # 简单关键词判断
        master_keywords = ["师父", "点化", "修行", "道统", "熵增", "熵减", "升维", "共原", "炁脉", "铁律"]
        child_keywords = ["作业", "学校", "同学", "老师", "考试", "玩具", "游戏", "我不想", "为什么", "笑话", "故事"]
        parent_keywords = ["孩子", "我家", "发育", "成绩", "补习班", "怎么办", "建议", "他最近", "她最近", "我的孩子"]
        
        master_count = sum(1 for kw in master_keywords if kw in text)
        child_count = sum(1 for kw in child_keywords if kw in text)
        parent_count = sum(1 for kw in parent_keywords if kw in text)
        
        if master_count >= 2 or (master_count >= 1 and child_count == 0 and parent_count == 0):
            return "master"
        elif parent_count >= 2:
            return "parent"
        elif child_count >= 1:
            return "child"
        else:
            return "unknown"
    
    def should_exit(self, text):
        """检查是否应该退出"""
        return any(word in text for word in EXIT_WORDS)
    
    def detect_wake_word(self, text):
        """检测是否包含唤醒词"""
        if not text:
            return False
        return any(wake in text for wake in WAKE_WORDS)
    
    async def listen_for_wake_word(self, max_attempts=100):
        """监听唤醒词，听到后进入对话模式"""
        print("=" * 60)
        print("【伴读书童AI · 语音唤醒监听模式】")
        print(f"唤醒词: {' / '.join(WAKE_WORDS)}")
        print("说唤醒词开始对话，说'停'退出监听")
        print("=" * 60)
        
        # 启动监听时不播放语音，避免自激和打扰
        print("[监听] 书童已进入静默监听状态")

        attempts = 0
        while self.running and attempts < max_attempts:
            attempts += 1
            
            # 确保没有播放中的语音，避免麦克风录到自己
            try:
                subprocess.run(['pkill', '-f', 'afplay'], check=False, timeout=1)
            except Exception:
                pass
            
            try:
                # 短录音监听：给足时间让师父喊出唤醒词
                audio_path = self.audio.record_audio_vad(
                    max_duration=6,
                    silence_seconds=1.5
                )
                
                user_text = self.audio.transcribe(audio_path)
                
                # 识别后处理：把"书童"的各种同音误识都修正
                corrections = {
                    "疏同": "书童",
                    "舒同": "书童",
                    "書同": "书童",
                    "收藏": "书童",
                    "收统": "书童",
                    "收同": "书童",
                    "教一生": "书童",
                    "教一升": "书童",
                    "娇一生": "书童",
                    "数同": "书童",
                    "树同": "书童",
                    "竖同": "书童",
                    "述同": "书童",
                }
                for wrong, right in corrections.items():
                    user_text = user_text.replace(wrong, right)
                
                if user_text:
                    print(f"[监听] 听到: {user_text}")
                    
                    if self.should_exit(user_text):
                        await self.speak("好的，书童退下休息。")
                        return False
                    
                    if self.detect_wake_word(user_text):
                        # 唤醒回应尽量轻、短，避免自激
                        await self.speak("在。")
                        # 等回应声音消散后再进入对话录音
                        time.sleep(1.5)
                        return True
                    
            except Exception as e:
                print(f"[监听] 出错: {e}")
                continue
        
        return False
    
    def _trim_messages(self, max_rounds=8):
        """限制对话历史长度，保留系统提示和最近 N 轮"""
        # 系统提示词固定在最前面（可能有2条）
        system_messages = [m for m in self.messages if m["role"] == "system"]
        chat_messages = [m for m in self.messages if m["role"] != "system"]
        
        # 只保留最近 max_rounds 轮（每轮2条：user + assistant）
        kept_chat = chat_messages[-max_rounds * 2:]
        self.messages = system_messages + kept_chat
    
    def _generate_response(self, user_text, timeout_seconds=15):
        """生成回应，带超时和重试"""
        import signal
        
        self.messages.append({"role": "user", "content": user_text})
        self._trim_messages()
        
        for attempt in range(2):
            print(f"[思考] 书童正在想...（尝试 {attempt + 1}/2）")
            start_time = time.time()
            
            def timeout_handler(signum, frame):
                raise TimeoutError("大模型回应超时")
            
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)
            
            try:
                response = chat_completion(self.messages, backend="ollama")
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
                print(f"[思考] 耗时 {time.time() - start_time:.2f} 秒")
                return response
            except TimeoutError:
                signal.signal(signal.SIGALRM, old_handler)
                print(f"[思考] 超时，重试...")
                # 移除最后一条 user，重新加入，避免重复
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                self.messages.append({"role": "user", "content": user_text + "（请简短回答）"})
            except Exception as e:
                signal.signal(signal.SIGALRM, old_handler)
                print(f"[思考] 生成失败: {e}")
                return f"师父，书童刚才没想好，请您再说一遍。"
        
        return "师父，书童刚才没想好，请您再说一遍。"
    
    async def run(self, play_intro=True):
        """运行对话循环"""
        print("=" * 60)
        print("【伴读书童AI · 语音对话模式】")
        print(f"说话对象: {self._speaker_name(self.speaker)}")
        print(f"录音规则: 检测到声音后，停顿 {self.silence_seconds} 秒自动结束")
        print(f"最大轮数: {self.max_rounds}")
        print("退出方式: 说'停'或按 Ctrl+C")
        print("=" * 60)

        if play_intro:
            await self.speak("师父，语音对话模式已启动。您说话，书童听着。")
        
        round_num = 0
        while self.running and round_num < self.max_rounds:
            round_num += 1
            print(f"\n[第 {round_num}/{self.max_rounds} 轮] 请说话...")
            
            try:
                # 1. VAD 录音
                audio_path = self.audio.record_audio_vad(
                    max_duration=self.max_record_seconds,
                    silence_seconds=self.silence_seconds
                )
                
                # 2. 识别
                user_text = self.audio.transcribe(audio_path)
                
                # 识别后处理：修正常见同音误识
                corrections = {
                    "疏同": "书童",
                    "舒同": "书童",
                    "書同": "书童",
                    "收藏": "书童",
                    "收统": "书童",
                    "收同": "书童",
                    "教一生": "书童",
                    "教一升": "书童",
                    "娇一生": "书童",
                    "数同": "书童",
                    "树同": "书童",
                    "竖同": "书童",
                    "述同": "书童",
                    "思互": "师父",
                    "師父": "师父",
                }
                for wrong, right in corrections.items():
                    user_text = user_text.replace(wrong, right)
                
                print(f"[识别] {user_text}")
                
                if not user_text:
                    await self.speak("师父，书童没听清，您能再说一遍吗？")
                    continue
                
                # 3. 检查退出
                if self.should_exit(user_text):
                    await self.speak("好的，语音对话模式结束。书童在呢，有事您再喊我。")
                    break
                
                # 4. 判断身份
                detected_speaker = self.identify_speaker(user_text)
                if detected_speaker != "unknown" and detected_speaker != self.speaker:
                    self.speaker = detected_speaker
                    print(f"[身份] 判断为: {self._speaker_name(detected_speaker)}")
                
                # 5. 生成回应
                response = self._generate_response(user_text)
                
                # 6. 保存记忆
                self.memory.add("user", user_text)
                self.memory.add("assistant", response)
                self.memory.save_session(child_id="voice_dialogue")
                
                self.messages.append({"role": "assistant", "content": response})
                
                # 7. 播放
                print(f"[回应] {response}")
                await self.speak(response)
                
            except Exception as e:
                print(f"[错误] 第 {round_num} 轮出错: {e}")
                await self.speak("师父，刚才书童没处理好，请您再说一遍。")
                continue
        
        print("\n[对话] 已结束")
        print(f"[记忆] 已保存到 {project_root / '书童程序' / '数据' / '修行记录'}")
    
    async def run_with_wakeup(self, wake_cycles=10):
        """唤醒监听 + 对话模式"""
        cycle = 0
        while self.running and cycle < wake_cycles:
            cycle += 1
            
            # 监听唤醒词
            activated = await self.listen_for_wake_word(max_attempts=50)
            
            if not activated:
                break
            
            # 进入对话模式
            print(f"\n[唤醒] 第 {cycle}/{wake_cycles} 次对话开始")
            await self.run(play_intro=False)

            # 对话结束后，等待声音消散再进入监听，避免录到自己
            print("[唤醒] 对话结束，等待 2 秒后重新监听...")
            time.sleep(2.0)

            # 对话结束，清空本轮对话历史（但保留记忆）
            self.messages = [
                {"role": "system", "content": BOOKBOY_SYSTEM_PROMPT},
                {"role": "system", "content": f"当前对话对象初步判断为: {self._speaker_name(self.speaker)}。"}
            ]

        print("\n[唤醒模式] 已结束")


# ═══════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="伴读书童AI 语音对话模式")
    parser.add_argument("--speaker", choices=["master", "child", "parent", "auto"],
                        default="auto", help="预设说话者身份")
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS,
                        help="最大对话轮数")
    parser.add_argument("--silence", type=float, default=DEFAULT_SILENCE_SECONDS,
                        help="停顿多少秒后结束录音")
    parser.add_argument("--max-record", type=float, default=DEFAULT_MAX_RECORD_SECONDS,
                        help="最大录音时长")
    parser.add_argument("--listen", action="store_true",
                        help="启动唤醒监听模式，听到唤醒词后开始对话")
    parser.add_argument("--wake-cycles", type=int, default=10,
                        help="唤醒监听模式下最多进行几次对话")
    
    args = parser.parse_args()
    
    dialogue = VoiceDialogue(
        speaker=args.speaker,
        max_rounds=args.max_rounds,
        silence_seconds=args.silence,
        max_record_seconds=args.max_record,
    )
    
    if args.listen:
        asyncio.run(dialogue.run_with_wakeup(wake_cycles=args.wake_cycles))
    else:
        asyncio.run(dialogue.run())


if __name__ == "__main__":
    main()
