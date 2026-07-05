"""预生成常用陪伴语音

用途：把明天宇树现场演示会用到的常用语提前生成好，
避免现场首次播放时联网等待。
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from 书童程序.核心.语音模块 import VoiceEngine

# 明天现场会用到的常用语
COMMON_PHRASES = [
    "小橙子，你好呀！书童今天也在陪你哦。",
    "小橙子，书童在这里，愿意和我说说吗？",
    "没关系，情绪像云一样，会飘走的。我陪你。",
    "小橙子，你可以的！书童相信你！",
    "慢慢来，一步一步，你已经很棒了。",
    "小橙子，想活动一下吗？跟我一起动一动！",
    "好玩吗？我们休息一下。",
    "小橙子，该准备睡觉啦。",
    "闭上眼睛，慢慢呼吸，书童守着你。",
    "小明，早上好，今天上学准备好了吗？",
    "嘟嘟，早上好，昨晚睡得怎么样？",
    "橙子，早上好，今天有古诗想听吗？",
]


def main():
    print("=== 预生成常用陪伴语音 ===\n")
    voice = VoiceEngine()
    
    if voice.backend != 'edge-tts':
        print(f"⚠️ 当前后端不是 edge-tts，而是 {voice.backend}")
        return
    
    for i, text in enumerate(COMMON_PHRASES, 1):
        print(f"[{i}/{len(COMMON_PHRASES)}] {text[:30]}...")
        voice.speak(text)
    
    print(f"\n✅ 预生成完成，共 {len(COMMON_PHRASES)} 条")
    
    # 统计缓存
    cache_dir = voice.cache_dir
    cache_count = len(list(cache_dir.glob('*.mp3')))
    print(f"缓存文件数: {cache_count}")


if __name__ == "__main__":
    main()
