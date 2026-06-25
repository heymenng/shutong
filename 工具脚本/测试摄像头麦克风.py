#!/usr/bin/env python3
"""测试书童的眼睛和耳朵：摄像头 + 麦克风"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from 书童程序.核心.感官系统 import SensorySystem

print("=== 书童感官系统测试 ===\n")

sensory = SensorySystem()
status = sensory.status()

print(f"平台: {status['platform']}")
print(f"摄像头可用: {status['vision']['available']}")
print(f"麦克风可用: {status['audio']['available']}")
print()

# 测试摄像头
if status['vision']['available']:
    print("正在测试摄像头，请看向摄像头...")
    try:
        frame = sensory.vision.capture_frame()
        face_count, faces = sensory.vision.detect_face()
        print(f"✅ 摄像头测试成功")
        print(f"   保存路径: {sensory.vision.last_frame_path}")
        print(f"   检测到人脸: {face_count} 张")
    except Exception as e:
        print(f"❌ 摄像头测试失败: {e}")
else:
    print("❌ 摄像头不可用，请检查权限和硬件")

print()

# 测试麦克风
if status['audio']['available']:
    print("正在测试麦克风，请对着麦克风说几句话...")
    try:
        text = sensory.audio.listen_and_transcribe(duration=5)
        print(f"✅ 麦克风测试成功")
        print(f"   识别结果: {text}")
    except Exception as e:
        print(f"❌ 麦克风测试失败: {e}")
else:
    print("❌ 麦克风不可用，请检查权限和硬件")

print("\n=== 测试结束 ===")
