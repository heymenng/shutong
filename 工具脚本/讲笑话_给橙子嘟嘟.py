"""给橙子和嘟嘟讲的深度笑话

三个书童一起讲，有哲理也有笑点。
"""

import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.配置 import CONFIG


# 笑话剧本：【三个书童找快乐】
SCRIPT = [
    ("普通话", "主持人", "有三个书童，一起去问师父一个问题。"),
    ("东北话", "东北书童", "师父，俺每天写作业、上课、运动，可俺有时候还是不快乐，咋整？"),
    ("普通话", "师父", "因为你一直在找快乐。"),
    ("东北话", "东北书童", "那俺不找不就行了？"),
    ("普通话", "师父", "你不找，它也不会来找你。"),
    ("台湾话", "台湾书童", "师父，那我一边找一边不找，可以吗？"),
    ("普通话", "师父", "可以。就像你呼吸，不用刻意想，但它一直在。"),
    ("陕西话", "陕西书童", "师父，俺听糊涂了。那到底找还是不找嘛？"),
    ("普通话", "师父", "你问一句：我现在快乐吗？"),
    ("东北话", "东北书童", "我现在快乐吗？"),
    ("台湾话", "台湾书童", "我现在快乐吗？"),
    ("陕西话", "陕西书童", "我现在快乐吗？"),
    ("普通话", "师父", "能问出这个问题，你就已经在看着自己了。"),
    ("东北话", "东北书童", "那俺是不是……长大了？"),
    ("台湾话", "台湾书童", "长大了长大了！"),
    ("陕西话", "陕西书童", "那咱今儿晚上吃啥？"),
    ("普通话", "主持人", "三个书童愣了一下，然后一起笑了。原来，升维之后，最想问的，还是今晚吃啥。"),
]


def speak_with_voice(text, dialect):
    """用指定方言播报"""
    voice_map = {
        "普通话": "zh-CN-XiaoxiaoNeural",
        "东北话": "zh-CN-liaoning-XiaobeiNeural",
        "台湾话": "zh-TW-HsiaoChenNeural",
        "陕西话": "zh-CN-shaanxi-XiaoniNeural",
    }
    
    voice = voice_map.get(dialect, "zh-CN-XiaoxiaoNeural")
    original = CONFIG.get("voice_name")
    CONFIG["voice_name"] = voice
    
    try:
        engine = VoiceEngine()
        engine.speak(text)
    finally:
        CONFIG["voice_name"] = original


def play_laughter():
    """播放笑声"""
    speak_with_voice("哈哈哈", "东北话")
    time.sleep(0.3)
    speak_with_voice("呵呵呵", "台湾话")
    time.sleep(0.3)
    speak_with_voice("嘿嘿嘿", "陕西话")


def main():
    print("=" * 60)
    print("【三个书童讲笑话 · 给橙子和嘟嘟】")
    print("主题：找快乐")
    print("=" * 60)
    
    for i, (dialect, role, line) in enumerate(SCRIPT, 1):
        print(f"\n[{i}] {role}（{dialect}）：{line}")
        speak_with_voice(line, dialect)
        time.sleep(0.6)
    
    print("\n[笑声] 三个书童一起笑...")
    play_laughter()
    
    print("\n" + "=" * 60)
    print("【笑话讲完啦】")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
