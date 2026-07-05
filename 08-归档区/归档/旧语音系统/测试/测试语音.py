#!/usr/bin/env python3
"""测试语音模块"""

import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from 书童程序.核心.语音模块 import VoiceEngine

print("=" * 40)
print("伴读书童AI - 语音模块测试")
print("=" * 40)

# 初始化语音引擎
engine = VoiceEngine()

if engine.backend is None:
    print("\n❌ 语音引擎未启动")
    print("可能原因：")
    print("  - pyttsx3 安装失败")
    print("  - macOS say 命令不可用")
    sys.exit(1)

print(f"\n✅ 语音引擎已启动")
print(f"   后端: {engine.backend}")

# 测试中文语音
test_texts = [
    "你好，我是伴读书童。",
    "小朋友，今天过得怎么样？",
    "走，钓鱼去！"
]

print("\n开始测试语音播放...")
for i, text in enumerate(test_texts, 1):
    print(f"\n测试 {i}/{len(test_texts)}: {text}")
    try:
        engine.speak(text)
        print("   ✅ 播放成功")
    except Exception as e:
        print(f"   ❌ 播放失败: {e}")

print("\n" + "=" * 40)
print("测试完成！")
print("=" * 40)
