#!/usr/bin/env python3
"""
执行书童神魂注入仪式。

用法：
    .venv/bin/python 07-工具区/工具脚本/执行神魂注入仪式.py

环境变量：
    G1_CONTROL_URL=http://192.168.0.248:8888
    G1_CONTROL_TOKEN=your_token
"""

import sys
from pathlib import Path

# 把引擎路径加入 Python 路径
engine_root = Path(__file__).resolve().parents[3] / "03-引擎区" / "书童程序"
sys.path.insert(0, str(engine_root))

from 核心.机器人对接.G1_HTTP客户端 import G1HTTPClient
from 核心.机器人对接.神魂注入仪式 import SoulInjectionRitual
from 核心.语音模块 import VoiceEngine


def main():
    print("=" * 60)
    print("书童AI · 神魂注入仪式")
    print("=" * 60)

    robot = G1HTTPClient()
    voice = VoiceEngine()
    ritual = SoulInjectionRitual(robot, voice_engine=voice)

    result = ritual.perform(sense_duration=5.0)
    print("\n仪式结果:")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
