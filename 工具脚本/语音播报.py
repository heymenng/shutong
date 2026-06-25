"""书童语音播报工具

统一入口，让所有书童主动发出的声音都走 Edge-TTS。
用法：
    .venv/bin/python 工具脚本/语音播报.py "要播报的文字"
    .venv/bin/python 工具脚本/语音播报.py "要播报的文字" --voice zh-CN-liaoning-XiaobeiNeural
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.配置 import CONFIG


def main():
    parser = argparse.ArgumentParser(description="书童语音播报工具")
    parser.add_argument("text", help="要播报的文字")
    parser.add_argument("--voice", default=None, help="指定 Edge-TTS 声音，如 zh-CN-liaoning-XiaobeiNeural")
    args = parser.parse_args()
    
    if args.voice:
        original = CONFIG.get("voice_name")
        CONFIG["voice_name"] = args.voice
        try:
            engine = VoiceEngine()
            engine.speak(args.text)
        finally:
            CONFIG["voice_name"] = original
    else:
        engine = VoiceEngine()
        engine.speak(args.text)


if __name__ == "__main__":
    main()
