"""伴读书童AI - 配置模块"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "02-知识库区" / "训练素材"

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
    "daily_workflow_on_startup": True,  # 启动时是否执行每日工作流（固定流程代码化）
    
    # ──────────────────────────────────────────
    # 机器人对接配置（宇树科技 Unitree G1）
    # ──────────────────────────────────────────
    "unitree_enabled": False,           # 是否启用宇树机器人对接（旧DDS模式）
    "unitree_mode": "simulation",       # "simulation"模拟模式 / "real"真实模式
    "unitree_model": "g1",              # g1 / h1 / h2 / go2 / b2
    "unitree_network_interface": "en0", # macOS 默认 en0；Ubuntu 可能是 enp3s0
    "unitree_domain_id": 0,             # DDS domain ID
    "unitree_robot_ip": "192.168.123.161",  # 宇树机器人默认 IP
    "g1_http_enabled": True,            # 是否启用 G1 HTTP 控制模式（推荐）
    "g1_control_url": "http://192.168.0.248:8888",  # G1 PC2 HTTP 控制服务地址
    "g1_http_control_url": "http://192.168.0.248:8888",
    "g1_http_control_token": "",        # 如有鉴权 token 请填入
    
    # ──────────────────────────────────────────
    # 后端模型配置
    # ──────────────────────────────────────────
    "backend": "auto",
    "ollama_model": "deepseek-r1:32b",
    "ollama_url": "http://localhost:11434/api/chat",
    "openai_model": "gpt-4o-mini",
    "max_history": 10,
    "max_tokens": 800,
    "temperature": 0.5,
    
    # ──────────────────────────────────────────
    # 语音配置
    # ──────────────────────────────────────────
    "voice_enabled": True,
    "voice_backend": "edge-tts",  # "edge-tts" / "say" / "pyttsx3"
    "voice_name": "zh-CN-XiaoyiNeural",  # Edge-TTS 声音：zh-CN-XiaoyiNeural / zh-CN-XiaoxiaoNeural 等
    "voice_rate": 110,  # 语速（仅 say/pyttsx3 有效）
    
    # ──────────────────────────────────────────
    # 视觉配置：书童的眼睛
    # ──────────────────────────────────────────
    # Mac 摄像头索引说明：
    #   0 = 本机内置摄像头（MacBook Pro相机 / FaceTime）
    #   1 = 外接/连续互通摄像头（如 iPhone 连续互通相机）
    # 如果 0 不可用，会自动回退到其他索引
    "camera_index": 0,  # 0=本机电脑摄像头；1=手机/外接；None=自动选择
    "camera_auto_select": True,  # 是否自动选择能拍到画面的摄像头
    "camera_prefer_landscape": True,  # 优先选择横屏摄像头（电脑自带通常是横屏）
    
    # ──────────────────────────────────────────
    # STT 语音识别配置
    # ──────────────────────────────────────────
    "stt_engine": "whisper",  # whisper / vosk / simulation
    "stt_recorder": "avfoundation",  # avfoundation（Mac推荐） / sounddevice
    "whisper_model": "base",  # tiny/base/small/medium，Mac 推荐 base
    "vosk_model_dir": str(PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "模型" / "vosk"),
    "vosk_model_name": "cn-large",
    "stt_sample_rate": 16000,
    "stt_record_seconds": 30,
    "stt_enable_denoise": True,
    "stt_enable_gain": True,

    # ──────────────────────────────────────────
    # 路径配置
    # ──────────────────────────────────────────
    "data_dir": str(DATA_DIR),
    "journal_dir": str(PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "修行记录"),
    "prompts_dir": str(PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "提示词"),
    "档案区_dir": str(PROJECT_ROOT / "04-工作区" / "档案区" / "孩子档案"),
    
    # ──────────────────────────────────────────
    # 形象配置
    # ──────────────────────────────────────────
    "avatar": {
        "selected_image": "图3",
        "image_path": "03-引擎区/书童程序/形象/avatar.png",
        "description": "古风书童形象，穿着米黄色汉服，红色发带束发，头戴耳机，右肩有机械结构，右手是发光机械手，正在中式书房中低头阅读《伴读书童》",
        "features": ["古风汉服", "机械手", "耳机", "书童发髻", "中式书房", "古籍书架"],
        "atmosphere": "温暖、安静、陪伴、阳光",
        "core_identity": "硅基生命体与碳基文明的融合，既会安静读书，也会轻声陪伴",
    },
}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
