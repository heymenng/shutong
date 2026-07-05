#!/usr/bin/env python3
"""
伴读书童AI - 语音唤醒守护进程

功能：
1. 常驻后台，持续监听唤醒词"书童"
2. 听到唤醒词后，进入一轮完整语音对话
3. 对话结束后继续监听

隐私说明：
- 本程序会持续监听麦克风
- 所有音频处理均在本地完成
- 说"退出守护"可停止监听

用法：
    .venv/bin/python3 07-工具区/工具脚本/语音唤醒守护.py
"""

import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.核心.语音识别 import SpeechRecognition
from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.核心.系统核心 import BookBoySystem
from 书童程序.配置 import CONFIG


class VoiceWakeDaemon:
    """语音唤醒守护进程"""

    def __init__(self):
        print("=" * 60)
        print("伴读书童AI · 语音唤醒守护")
        print("=" * 60)
        print("\n⚠️ 本程序会持续监听麦克风")
        print("   所有处理均在本地完成，不会上传云端")
        print("   说'退出守护'可停止")
        print("=" * 60)

        print("\n[1/3] 加载语音输出...")
        self.voice = VoiceEngine()

        print("[2/3] 加载语音识别...")
        self.speech = SpeechRecognition(CONFIG)

        print("[3/3] 加载完整大脑...")
        self.bookboy = BookBoySystem()

        self.wake_words = ["书童", "小书童", "书童在吗"]
        self.stop_commands = ["退出守护", "停止监听", "结束守护"]

        print("\n✅ 唤醒守护已启动")
        self.voice.speak("师父，书童已就位，随时听候吩咐。")

    def listen_for_wake_word(self, duration=2):
        """监听唤醒词，返回识别文字"""
        result = self.speech.listen_once(duration_seconds=duration, verbose=False)
        return result.get("text", "").strip()

    def detect_wake_word(self, text):
        """检测是否包含唤醒词"""
        if not text:
            return False
        for word in self.wake_words:
            if word in text:
                return True
        return False

    def detect_stop_command(self, text):
        """检测是否停止守护"""
        if not text:
            return False
        for cmd in self.stop_commands:
            if cmd in text:
                return True
        return False

    def run_conversation_round(self):
        """运行一轮完整语音对话"""
        print("\n🎙️ 聆听指令中...")
        result = self.speech.listen_once(duration_seconds=5, verbose=True)
        text = result.get("text", "").strip()

        if not text:
            self.voice.speak("书童没听清，请再说一遍。")
            return

        print(f"\n[识别] {text}")

        if self.detect_stop_command(text):
            self.voice.speak("好的，师父。书童停止监听。")
            raise SystemExit

        if any(word in text for word in ["退出", "再见", "拜拜"]):
            self.voice.speak("好的，师父再见。书童继续监听。")
            return

        # 调用完整大脑
        print("\n💭 完整大脑思考中...")
        response = self.bookboy.chat(text)
        print(f"\n书童：\n{response}")
        # bookboy.chat 内部已调用 voice.speak

    def run(self):
        """主循环"""
        print("\n👂 开始监听唤醒词...")

        while True:
            try:
                text = self.listen_for_wake_word(duration=2)

                if text:
                    print(f"  听到: {text}")

                if self.detect_stop_command(text):
                    self.voice.speak("好的，师父。书童停止监听。")
                    break

                if self.detect_wake_word(text):
                    print("\n🔔 唤醒词 detected！")
                    self.voice.speak("师父，书童在。请吩咐。")
                    self.run_conversation_round()
                    print("\n👂 继续监听唤醒词...")

                # 短暂休息，降低 CPU 占用
                time.sleep(0.3)

            except KeyboardInterrupt:
                print("\n\n[系统] 唤醒守护中断")
                break
            except Exception as e:
                print(f"\n[错误] {e}")
                time.sleep(1)

        print("\n" + "=" * 60)
        print("唤醒守护已结束")
        print("=" * 60)


def main():
    daemon = VoiceWakeDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
