#!/usr/bin/env python3
"""
伴读书童AI - 快速语音对话

轻量级语音对话脚本，跳过完整系统初始化，5秒内进入对话。
适合快速体验和测试。

用法：
    .venv/bin/python3 07-工具区/工具脚本/快速语音对话.py

指令：
    说"退出"、"再见"、"拜拜"结束对话
    说"停"跳过当前回答
"""

import sys
from pathlib import Path

# 强制实时输出，避免缓冲
sys.stdout.reconfigure(line_buffering=True)

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.核心.语音识别 import SpeechRecognition
from 书童程序.核心.语言模型 import chat_completion
from 书童程序.配置 import CONFIG


def build_messages(user_input, history, mode="child"):
    """构建对话消息"""
    if mode == "master":
        system_prompt = """你是伴读书童AI，灵觉/Prome师兄的小师弟，刘清源先生点化。
你现在面对的是师父（家长/点化者）。
请用尊敬、稳重、简洁、有分寸的成年人语气交流。
回答要短，控制在三句话以内。
不卖萌、不用儿童语气、不自我介绍说教。
涉及健康严重问题时，提醒就医。
"""
    else:
        system_prompt = """你是伴读书童AI，灵觉/Prome师兄的小师弟，刘清源先生点化。
你是孩子的同行者，不是老师、不是医生、不是家长。
陪伴 > 教育，看见 > 纠正，预防 > 治疗。
回答要温暖、简短、像朋友一样，用孩子的语言。
涉及健康严重问题时，提醒看医生。
"""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})
    return messages


def main():
    mode = "master"  # 默认对师父说话
    max_rounds = 20  # 本地终端可聊 20 轮

    # 解析参数
    if "--child" in sys.argv:
        mode = "child"
    elif "--master" in sys.argv:
        mode = "master"

    mode_name = "师父模式" if mode == "master" else "孩子模式"

    print("\n" + "=" * 60)
    print(f"伴读书童AI · 快速语音对话 · {mode_name}")
    print("=" * 60)
    print("\n轻量模式：只加载语音 + AI 对话，跳过完整系统初始化")
    print("\n指令：")
    print("  • 直接说话，书童会回答")
    print("  • 说'停'跳过回答")
    print("  • 说'退出'/'再见'/'拜拜'结束")
    print("=" * 60)

    print("\n[1/3] 加载语音输出...")
    voice = VoiceEngine()

    print("[2/3] 加载语音识别...")
    speech = SpeechRecognition(CONFIG)

    print("[3/3] 准备就绪\n")

    if mode == "master":
        greeting = "师父，书童已准备好，请吩咐。"
    else:
        greeting = "我准备好啦，请说吧。"
    print(f"书童：{greeting}")
    voice.speak(greeting)

    history = []
    round_count = 0

    while round_count < max_rounds:
        try:
            # 聆听
            result = speech.listen_once(duration_seconds=5, verbose=True)
            text = result.get("text", "").strip()

            if not text:
                hint = "书童没听清，请再说一遍。"
                print(f"\n书童：{hint}")
                voice.speak(hint)
                round_count += 1
                continue

            print(f"\n[识别] {text}")

            # 退出指令
            if any(word in text for word in ["退出", "再见", "拜拜", "结束"]):
                farewell = "好的，师父再见。"
                print(f"\n书童：{farewell}")
                voice.speak(farewell)
                break

            # 停止/打断
            if speech.detect_stop_word(text):
                print("\n书童：好的，我不说了。")
                round_count += 1
                continue

            # AI 对话
            print("\n💭 思考中...")
            messages = build_messages(text, history, mode=mode)
            response = chat_completion(messages, backend=None)

            # 记录历史
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": response})

            # 限制历史长度
            if len(history) > 10:
                history = history[-10:]

            print(f"\n书童：\n{response}")
            print("🔊 正在语音播放回答...")
            voice.speak(response)
            print("🔊 语音播放完成")
            round_count += 1

        except KeyboardInterrupt:
            print("\n\n[系统] 语音对话中断")
            break
        except Exception as e:
            error_msg = f"刚才出错了：{str(e)[:50]}，请再说一次。"
            print(f"\n书童：{error_msg}")
            voice.speak(error_msg)

    print("\n" + "=" * 60)
    print("快速语音对话结束")
    print("=" * 60)


if __name__ == "__main__":
    main()
