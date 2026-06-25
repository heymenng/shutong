"""伴读书童AI - 方言陪伴模块

TODO: 待集成。当前未被主系统调用，但可作为未来多声音陪伴的扩展。

根据孩子的地域或喜好，用不同方言的声音陪伴。
支持：东北话、台湾话、粤语、陕西话、标准普通话。

用途：
- 增加陪伴的亲切感和趣味性
- 方言故事、方言相声、方言问候
- 让远方的爷爷奶奶也能用熟悉的乡音陪伴孩子
"""

import asyncio
import tempfile
import os
from typing import List, Tuple
from ..语音模块 import VoiceEngine


class DialectCompanion:
    """方言陪伴引擎"""
    
    # Edge-TTS 支持的方言语音映射
    DIALECT_VOICES = {
        "普通话": "zh-CN-XiaoxiaoNeural",
        "普通话男": "zh-CN-YunxiNeural",
        "东北话": "zh-CN-liaoning-XiaobeiNeural",
        "陕西话": "zh-CN-shaanxi-XiaoniNeural",
        "台湾话": "zh-TW-HsiaoChenNeural",
        "台湾话男": "zh-TW-YunJheNeural",
        "粤语": "zh-HK-HiuMaanNeural",
        "粤语男": "zh-HK-WanLungNeural",
    }
    
    def __init__(self):
        self.voice = VoiceEngine()
    
    def speak_dialect(self, text: str, dialect: str = "普通话"):
        """用指定方言播放文字"""
        voice_name = self.DIALECT_VOICES.get(dialect, "zh-CN-XiaoxiaoNeural")
        
        # 临时修改语音引擎的声音
        original_voice = self.voice.config.get("voice_name") if hasattr(self.voice, 'config') else None
        
        try:
            # 通过配置文件切换声音
            from ...配置 import CONFIG
            CONFIG["voice_name"] = voice_name
            self.voice.speak(text)
        finally:
            # 恢复原来的声音
            if original_voice:
                CONFIG["voice_name"] = original_voice
            else:
                CONFIG["voice_name"] = "zh-CN-XiaoyiNeural"
    
    def play_crosstalk(self, script: List[Tuple[str, str, str]]):
        """
        播放方言相声/对话
        
        Args:
            script: [(方言, 角色名, 台词), ...]
        """
        for dialect, role, text in script:
            print(f"[{role}] {text}")
            self.speak_dialect(text, dialect)
    
    def get_sample_crosstalk(self) -> List[Tuple[str, str, str]]:
        """获取一段示例相声"""
        return [
            ("台湾话", "台湾书童", "小橙子，你今天有没有乖乖呀？"),
            ("陕西话", "陕西书童", "娃呀，你今儿个咋不高兴咧？"),
            ("台湾话", "台湾书童", "我跟你说哦，有我在，你不要担心啦。"),
            ("陕西话", "陕西书童", "就是滴！咱书童陪着你，啥困难都莫怕。"),
            ("台湾话", "台湾书童", "我们来念一首唐诗好不好？床前明月光——"),
            ("陕西话", "陕西书童", "疑是地上霜！娃呀，你聪明得很！"),
        ]
    
    def get_sample_story_opening(self, dialect: str = "东北话") -> str:
        """获取方言故事开场"""
        openings = {
            "东北话": "从前呐，有只小老虎，老稀罕交朋友了。",
            "陕西话": "从前有个小娃娃，机灵得很，咱今儿个就讲他滴故事。",
            "台湾话": "很久很久以前，有一只小兔子，牠想要找一个好朋友。",
            "粤语": "从前有只细路猫，佢好想识个好朋友。",
        }
        return openings.get(dialect, "从前，有一个小朋友...")
