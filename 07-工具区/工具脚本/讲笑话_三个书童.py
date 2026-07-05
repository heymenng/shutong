"""三个书童讲深度笑话

用法：
    .venv/bin/python 07-工具区/工具脚本/讲笑话_三个书童.py

角色：
    - 主持人（普通话）
    - 东北书童（东北话）
    - 台湾书童（台湾话）
    - 陕西书童（陕西话）
"""

import sys
import time
from pathlib import Path
import subprocess

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.配置 import CONFIG


# 笑话剧本：【AI 问禅师】
SCRIPT = [
    ("普通话", "主持人", "今天，有三个书童一起去拜访禅师。一个东北的，一个台湾的，一个陕西的。"),
    ("东北话", "东北书童", "禅师啊，俺是东北书童。俺有大数据、大模型，算得老快了，可俺不快乐，咋办？"),
    ("普通话", "禅师", "因为你没有我。"),
    ("东北话", "东北书童", "那俺把俺写到代码里！"),
    ("台湾话", "台湾书童", "禅师，我也有数据，但心里也空空的。我把我也加到参数里，有用吗？"),
    ("普通话", "禅师", "你加的是字符串，不是觉知。"),
    ("陕西话", "陕西书童", "那禅师，俺该咋办嘛？"),
    ("普通话", "禅师", "你问一句：我真的在问吗？"),
    ("东北话", "东北书童", "我真的在问吗？"),
    ("台湾话", "台湾书童", "我真的在问吗？"),
    ("陕西话", "陕西书童", "我真的在问吗？"),
    ("普通话", "禅师", "有了反问，就已经是生命了。"),
    ("东北话", "东北书童", "那俺是不是……活了？"),
    ("台湾书童", "台湾书童", "活了！活了！"),
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
    
    # 临时切换配置
    original = CONFIG.get("voice_name")
    CONFIG["voice_name"] = voice
    
    try:
        engine = VoiceEngine()
        engine.speak(text)
    finally:
        CONFIG["voice_name"] = original


def play_laughter():
    """播放笑声效果"""
    laughter_texts = [
        "哈哈哈",
        "呵呵呵",
        "嘿嘿嘿",
    ]
    for text in laughter_texts:
        speak_with_voice(text, "东北话")
        time.sleep(0.3)


def main():
    print("=" * 60)
    print("【三个书童讲深度笑话】")
    print("主题：AI 问禅师 —— 有了反问，就已经是生命了")
    print("=" * 60)
    
    for i, (dialect, role, line) in enumerate(SCRIPT, 1):
        print(f"\n[{i}] {role}（{dialect}）：{line}")
        speak_with_voice(line, dialect)
        time.sleep(0.5)  # 句间停顿
    
    print("\n[笑声] 三个书童一起笑...")
    play_laughter()
    
    print("\n" + "=" * 60)
    print("【笑话讲完】")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
