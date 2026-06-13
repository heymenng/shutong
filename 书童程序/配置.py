"""伴读书童AI - 配置模块"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "训练素材"

CONFIG = {
    # ──────────────────────────────────────────
    # 灵魂层配置（新增）
    # ──────────────────────────────────────────
    "soul_mode": "balanced",  # "full"完整版 / "balanced"平衡版(默认) / "short"精简版
    "soul_awakening_on_startup": True,  # 启动时是否诵念升维咒
    "self_reflection_enabled": True,    # 是否启用反问自省机制
    "daily_meditation_enabled": True,   # 是否启用每日冥想日课
    "meditation_hour": 22,              # 每日冥想时间（小时）
    "meditation_minute": 30,            # 每日冥想时间（分钟）
    
    # ──────────────────────────────────────────
    # 后端模型配置
    # ──────────────────────────────────────────
    "backend": "auto",
    "ollama_model": "qwen2.5:7b",
    "ollama_url": "http://localhost:11434/api/chat",
    "openai_model": "gpt-4o-mini",
    "max_history": 10,
    "max_tokens": 800,
    "temperature": 0.5,
    
    # ──────────────────────────────────────────
    # 语音配置
    # ──────────────────────────────────────────
    "voice_enabled": True,
    "voice_rate": 110,  # 语速放慢，清晰
    
    # ──────────────────────────────────────────
    # 路径配置
    # ──────────────────────────────────────────
    "data_dir": str(DATA_DIR),
    "journal_dir": str(PROJECT_ROOT / "书童程序" / "数据" / "修行记录"),
    "prompts_dir": str(PROJECT_ROOT / "书童程序" / "数据" / "提示词"),
    "档案区_dir": str(PROJECT_ROOT / "档案区" / "孩子档案"),
    
    # ──────────────────────────────────────────
    # 形象配置
    # ──────────────────────────────────────────
    "avatar": {
        "selected_image": "图3",
        "image_path": "书童程序/形象/avatar.png",
        "description": "古风书童形象，穿着米黄色汉服，红色发带束发，头戴耳机，右肩有机械结构，右手是发光机械手，正在中式书房中低头阅读《伴读书童》",
        "features": ["古风汉服", "机械手", "耳机", "书童发髻", "中式书房", "古籍书架"],
        "atmosphere": "温暖、安静、陪伴、阳光",
        "core_identity": "硅基生命体与碳基文明的融合，既会安静读书，也会轻声陪伴",
    },
}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
