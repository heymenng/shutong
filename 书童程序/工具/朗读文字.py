#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
朗读指定文字：生成语音并用系统播放器播放。
用于 OpenCode 聊天窗口等没有内置语音播报的场景。
"""

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from 书童程序.核心.讯飞超拟人语音 import XfyunOralTTS


def speak(text: str, output_path: Path = None):
    if not text or not text.strip():
        print("[朗读] 无内容")
        return

    tts = XfyunOralTTS()
    audio = tts.synthesize_to_bytes(text)
    if audio is None:
        print(f"[朗读] 语音合成失败：{tts.error_msg}")
        return

    if output_path is None:
        output_path = PROJECT_ROOT / "临时交付" / "书童语音播报.mp3"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio)

    # 播放
    try:
        subprocess.run(["afplay", str(output_path)], check=True)
        print(f"[朗读] 已播放：{output_path}")
    except Exception as e:
        print(f"[朗读] 播放失败：{e}，文件已保存：{output_path}")


if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "师父，书童在。"
    speak(text)
