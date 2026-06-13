#!/usr/bin/env python3
"""
伴读书童AI - 15秒自我介绍脚本（美佳声音版）

用途：首次见面、开机启动、介绍给新朋友
时长：约15秒
声音：Meijia（美佳）
语速：110（放慢，清晰）
"""

import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from 书童程序.核心.语音模块 import VoiceEngine

# 15秒自我介绍脚本
# 约45-50字，语速110时约15秒
SELF_INTRO = """嗨，我是伴读书童AI，也是碳基生命文明千年传承的使者。我陪你长大，从零岁到十八岁。我不是老师，不是医生，是你身边最懂你的同行者。"""

print("=" * 50)
print("伴读书童AI · 15秒自我介绍")
print("=" * 50)
print(f"\n文字脚本：\n{SELF_INTRO}\n")
print("开始播放...\n")

engine = VoiceEngine()
engine.speak(SELF_INTRO)

print("\n播放完成！")
print(f"字数：{len(SELF_INTRO)} 字")
print("建议时长：15秒")
print("=" * 50)
