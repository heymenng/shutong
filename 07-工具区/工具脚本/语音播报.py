"""书童语音播报工具

统一入口，让所有书童主动发出的声音都走 Edge-TTS。
用法：
    .venv/bin/python 07-工具区/工具脚本/语音播报.py "要播报的文字"
    .venv/bin/python 07-工具区/工具脚本/语音播报.py "要播报的文字" --voice zh-CN-liaoning-XiaobeiNeural
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.配置 import CONFIG


def main():
    parser = argparse.ArgumentParser(description="书童语音播报工具")
    parser.add_argument("text", help="要播报的文字")
    parser.add_argument("--voice", default=None, help="指定 Edge-TTS 声音，如 zh-CN-liaoning-XiaobeiNeural")
    args = parser.parse_args()
    
    original_name = CONFIG.get("voice_name")
    original_backend = CONFIG.get("voice_backend")
    CONFIG["voice_backend"] = "edge-tts"
    if args.voice:
        CONFIG["voice_name"] = args.voice

    try:
        engine = VoiceEngine()
        engine.speak(args.text)
    finally:
        CONFIG["voice_name"] = original_name
        CONFIG["voice_backend"] = original_backend


if __name__ == "__main__":
    main()
