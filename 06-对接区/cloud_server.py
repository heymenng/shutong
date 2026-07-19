#!/usr/bin/env python3
"""
伴读书童AI · 云端服务骨架
=====================
书童上云后的核心服务端，承载：
1. 灵魂文件（AGENTS.md、系统提示词）
2. AI 推理网关（DeepSeek / OpenAI / Ollama）
3. 本地安装包远程调用接口
4. 师父云端控制台管理接口

启动方式:
    .venv/bin/python cloud_server.py

默认端口:
    5000（可通过 PORT 环境变量修改）
"""

import asyncio
import base64
import hashlib
import json
import os
import requests
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

# 多角色语音合成需要 edge-tts / pydub
try:
    import edge_tts
except Exception as e:
    edge_tts = None
    print(f"[云端] edge-tts 未安装: {e}")

try:
    from pydub import AudioSegment
except Exception as e:
    AudioSegment = None
    print(f"[云端] pydub 未安装: {e}")


# ═══════════════════════════════════════════
# 音频辅助函数
# ═══════════════════════════════════════════

def _decode_audio_base64(audio_base64: str) -> bytes:
    """安全解码前端传来的 base64 音频数据，自动纠偏、去空白、去 data URL 前缀"""
    if not audio_base64:
        return b""
    # 去空白
    audio_base64 = audio_base64.strip()
    # 去掉 data URL 前缀（如 data:audio/webm;base64,）
    if "," in audio_base64:
        prefix, _, payload = audio_base64.partition(",")
        if prefix.startswith("data:"):
            audio_base64 = payload
    # 纠偏：补齐 '=' 使长度为 4 的倍数
    padding = (-len(audio_base64)) % 4
    if padding:
        audio_base64 += "=" * padding
    return base64.b64decode(audio_base64)


def _detect_audio_suffix(audio_bytes: bytes) -> str:
    """根据文件头探测音频格式后缀"""
    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return ".wav"
    if audio_bytes[:4] == b"fLaC":
        return ".flac"
    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb" or audio_bytes[:2] == b"\xff\xf3":
        return ".mp3"
    if audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    if audio_bytes[:4] == b"OggS":
        return ".ogg"
    return ".wav"


def _convert_to_wav_if_needed(audio_bytes: bytes, suffix: str) -> bytes:
    """使用 pydub 把 webm/ogg/flac/mp3 等转成 16k 16bit 单声道 WAV"""
    if suffix in (".wav",) or not AudioSegment:
        return audio_bytes
    try:
        seg = AudioSegment.from_file(BytesIO(audio_bytes), format=suffix.lstrip("."))
        seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        buf = BytesIO()
        seg.export(buf, format="wav")
        return buf.getvalue()
    except Exception as e:
        print(f"[云端] pydub 音频转换失败，保留原数据: {e}")
        return audio_bytes


# 加载环境变量（支持 .env 文件）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

from flask import Flask, request, jsonify, Response, make_response
from werkzeug.security import generate_password_hash, check_password_hash

# 把项目根目录加入路径（支持本地开发和云端不同部署路径）
def _find_project_root(start: Path) -> Path:
    start = start.resolve()
    # 云端部署：cloud_server.py 放在项目根目录，直接取所在目录
    if (start.parent / "03-引擎区").exists():
        return start.parent
    # 本地开发：cloud_server.py 在 06-对接区/，向上找到包含 03-引擎区 的根
    for parent in [start] + list(start.parents):
        if (parent / "03-引擎区").exists():
            return parent
    # 兜底：按文件上一级目录处理
    return start.parents[1]


PROJECT_ROOT = _find_project_root(Path(__file__))
# 注意顺序：PROJECT_ROOT 必须在 03-引擎区 之前，否则部署到 /书童程序/ 的源码不会被加载
sys.path.insert(0, str(PROJECT_ROOT / "03-引擎区"))
sys.path.insert(0, str(PROJECT_ROOT))

# 服务器部署时 .env 通常放在项目根目录，确保能正确加载密钥
#（06-对接区/.env 仍保留作为本地开发回退）
try:
    from dotenv import load_dotenv
    _root_env = PROJECT_ROOT / ".env"
    if _root_env.exists():
        load_dotenv(_root_env, override=True)
except Exception:
    pass

# 云端静态资源目录
STATIC_DIR = PROJECT_ROOT / "03-引擎区" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# 云端音频缓存目录
AUDIO_CACHE_DIR = PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "语音缓存"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 安装包下载目录
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_file_path(base_dir: Path, filename: str) -> Path | None:
    """校验 filename 不越界，返回绝对路径；越界或包含 .. 返回 None"""
    if not filename or filename.startswith("/") or ".." in filename.split("/"):
        return None
    target = (base_dir / filename).resolve()
    try:
        target.relative_to(base_dir.resolve())
    except ValueError:
        return None
    return target


# Edge-TTS 多角色语音映射（用于方言/多角色表演）
VOICE_ROLES = {
    "东北书童": "zh-CN-liaoning-XiaobeiNeural",
    "东北话": "zh-CN-liaoning-XiaobeiNeural",
    "东北": "zh-CN-liaoning-XiaobeiNeural",
    "台湾书童": "zh-TW-HsiaoChenNeural",
    "台湾话": "zh-TW-HsiaoChenNeural",
    "台湾": "zh-TW-HsiaoChenNeural",
    "陕西书童": "zh-CN-shaanxi-XiaoniNeural",
    "陕西话": "zh-CN-shaanxi-XiaoniNeural",
    "陕西": "zh-CN-shaanxi-XiaoniNeural",
    "粤语书童": "zh-HK-HiuMaanNeural",
    "粤语": "zh-HK-HiuMaanNeural",
    "广东": "zh-HK-HiuMaanNeural",
    "普通话书童": "zh-CN-YunxiNeural",
    "普通话": "zh-CN-YunxiNeural",
    "云希": "zh-CN-YunxiNeural",
    "小艺": "zh-CN-XiaoyiNeural",
    "小北": "zh-CN-liaoning-XiaobeiNeural",
}
DEFAULT_EDGE_VOICE = "zh-CN-YunxiNeural"

from 书童程序.核心.语言模型 import chat_completion
from 书童程序.核心.语音模块 import VoiceEngine
from 书童程序.核心 import 日程安排 as schedule_lib
from 书童程序.核心 import 成长记录 as growth_lib
from 书童程序.核心 import 家庭留言板 as bulletin_lib
from 书童程序.核心 import 设置中心 as settings_lib
from 书童程序.核心 import 家庭档案管理 as archive_mgr

# 云端强制使用讯飞 STT（whisper 模型太大不适合服务器）
try:
    from 书童程序.配置 import CONFIG
    CONFIG["stt_engine"] = os.environ.get("STT_ENGINE", "xfyun")
    CONFIG["stt_recorder"] = "none"  # 云端不需要录音
    # 云端纯文字走 DeepSeek-v4-flash（更快），图文消息由 语言模型.py 自动切到 Moonshot vision
    CONFIG["backend"] = "deepseek"
    CONFIG["max_tokens"] = 16000
    CONFIG["temperature"] = 1.0
except Exception as e:
    print(f"[云端] 配置覆盖失败: {e}")

# ========== 聊天响应缓存与去重 ==========
# 解决：客户端因网络/超时而重发，导致大模型被重复调用、用户觉得“书童卡”的问题。
_CHAT_CACHE = {}          # key -> {"reply": str, "expires": float, "audio_url": str|None}
_CHAT_INFLIGHT = {}       # key -> {"event": threading.Event(), "reply": str|None, "error": str|None, "audio_url": str|None}
_CHAT_CACHE_LOCK = threading.Lock()
_CHAT_INFLIGHT_TTL = 180  # 最大等待同请求完成 180 秒
_CHAT_CACHE_TTL = 300        # 同一请求缓存 300 秒
_FILE_LOCKS = {}          # key -> threading.Lock()，用于文件写入并发安全

def _extract_text_from_content(content) -> str:
    """从消息内容中提取可搜索/可缓存的文本（支持字符串或 OpenAI 风格的 list）"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif item.get("type") == "image_url":
                    parts.append("[图片]")
        return "".join(parts)
    return str(content)


def _chat_cache_key(family_id: str, user_id: str, message: str, mode: str) -> str:
    """生成聊天请求去重/缓存键"""
    text = _extract_text_from_content(message).strip()
    raw = f"{family_id}:{user_id}:{text}:{mode}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _get_cached_chat(key: str) -> dict | None:
    now = time.time()
    with _CHAT_CACHE_LOCK:
        item = _CHAT_CACHE.get(key)
        if item and item.get("expires", 0) > now:
            return item
        if key in _CHAT_CACHE:
            del _CHAT_CACHE[key]
    return None


def _set_cached_chat(key: str, reply: str, audio_url: str | None = None, reasoning: str = ""):
    with _CHAT_CACHE_LOCK:
        _CHAT_CACHE[key] = {
            "reply": reply,
            "audio_url": audio_url,
            "reasoning": reasoning,
            "expires": time.time() + _CHAT_CACHE_TTL,
        }


# ========== 网络搜索增强 ==========
# 当用户问现实世界具体信息（学校、天气、新闻、医院等）时，先搜索再回答，避免胡说。
_TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY") or os.environ.get("tavily_api_key")
_SERPAPI_API_KEY = os.environ.get("SERPAPI_API_KEY") or os.environ.get("serpapi_api_key")

# 触发搜索的关键词（中文）
_WEB_SEARCH_KEYWORDS = {
    "学校", "中学", "小学", "大学", "幼儿园", "学区", "中考", "高考", "分数线", "录取",
    "排名", "升学", "招生", "老师", "校长", "教育局", "教委",
    "天气", "气温", "台风", "暴雨", "地震", "疫情", "病毒", "流感", "疫苗",
    "新闻", "时事", "最近", "最新", "今天", "昨天", "明天", "现在", "今年", "去年", "明年",
    "股票", "基金", "房价", "楼盘", "油价", "金价", "房价", "二手房",
    "医院", "医生", "挂号", "药店", "药品", "门诊", "手术", "体检",
    "电影", "电视剧", "综艺", "演员", "歌手", "比赛", "比分", "球队", "赛程", "夺冠",
    "景点", "旅游", "酒店", "餐厅", "美食", "攻略", "门票",
}


def _needs_web_search(message: str) -> bool:
    """根据关键词判断是否需要先联网搜索"""
    text = message.lower()
    return any(kw in text for kw in _WEB_SEARCH_KEYWORDS)


def _web_search(query: str, max_results: int = 5) -> list[dict]:
    """
    联网搜索。优先级：Tavily > SerpAPI > DuckDuckGo(ddgs)。
    返回 [{title, href, body}] 列表。
    """
    results = []

    # 1. Tavily（AI 搜索，质量高）
    if _TAVILY_API_KEY:
        try:
            import requests
            resp = requests.post(
                "https://api.tavily.com/search",
                headers={"Content-Type": "application/json"},
                json={
                    "api_key": _TAVILY_API_KEY,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": False,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                for r in data.get("results", []):
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("url", ""),
                        "body": r.get("content", ""),
                    })
                if results:
                    print(f"[搜索] Tavily 返回 {len(results)} 条: {query[:30]}...")
                    return results
        except Exception as e:
            print(f"[搜索] Tavily 失败: {e}")

    # 2. SerpAPI（Google/Bing 等通用搜索）
    if _SERPAPI_API_KEY:
        try:
            import requests
            resp = requests.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": _SERPAPI_API_KEY,
                    "engine": "google",
                    "num": max_results,
                    "hl": "zh-CN",
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                for r in data.get("organic_results", [])[:max_results]:
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("link", ""),
                        "body": r.get("snippet", ""),
                    })
                if results:
                    print(f"[搜索] SerpAPI 返回 {len(results)} 条: {query[:30]}...")
                    return results
        except Exception as e:
            print(f"[搜索] SerpAPI 失败: {e}")

    # 3. DuckDuckGo 免费搜索（无需 API Key）
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "href": r.get("href", ""),
                    "body": r.get("body", ""),
                })
        if results:
            print(f"[搜索] DuckDuckGo 返回 {len(results)} 条: {query[:30]}...")
            return results
    except Exception as e:
        print(f"[搜索] DuckDuckGo 失败: {e}")

    return results


def _format_search_context(results: list[dict]) -> str:
    """把搜索结果格式化成给模型的上下文"""
    if not results:
        return "\n\n【网络搜索结果】\n未找到相关网络资料。请基于你已有的可靠知识回答；如果知识不足，请明确说明，不要编造。\n"
    lines = ["\n\n【网络搜索结果】"]
    for i, r in enumerate(results[:5], 1):
        title = r.get("title", "").strip()
        href = r.get("href", "").strip()
        body = r.get("body", "").strip()
        lines.append(f"{i}. {title}\n   链接：{href}\n   摘要：{body[:300]}")
    lines.append("\n请直接基于以上搜索结果回答。如果搜索结果与问题无关或不足以回答，请明确说明，不要编造。不要再说'我现在去搜'之类的话。")
    return "\n".join(lines)


# 云端核心能力引擎（逐步接入）
try:
    from 书童程序.核心.发育守护引擎 import DevelopmentGuardian
except Exception as e:
    DevelopmentGuardian = None
    print(f"[云端] 发育守护引擎加载失败: {e}")

try:
    from 书童程序.核心.文化传承引擎 import CultureHeritageEngine
except Exception as e:
    CultureHeritageEngine = None
    print(f"[云端] 文化传承引擎加载失败: {e}")

try:
    from 书童程序.核心.四医融合引擎 import FourMedicineEngine
except Exception as e:
    FourMedicineEngine = None
    print(f"[云端] 四医融合引擎加载失败: {e}")

try:
    from 书童程序.核心.心力成长系统 import HeartPowerSystem
except Exception as e:
    HeartPowerSystem = None
    print(f"[云端] 心力成长系统加载失败: {e}")

try:
    from 书童程序.核心.睡前引导 import BedtimeGuide
except Exception as e:
    BedtimeGuide = None
    print(f"[云端] 睡前引导加载失败: {e}")

try:
    from 书童程序.核心.晨起仪式 import MorningRitualGenerator
except Exception as e:
    MorningRitualGenerator = None
    print(f"[云端] 晨起仪式加载失败: {e}")

try:
    from 书童程序.核心.家长助手 import (
        get_templates,
        build_prompt,
        save_creation,
        list_creations,
        load_creation,
        delete_creation,
        get_family_dir,
    )
except Exception as e:
    get_templates = build_prompt = save_creation = list_creations = load_creation = delete_creation = get_family_dir = None
    print(f"[云端] 家长助手加载失败: {e}")

try:
    from 书童程序.核心.讯飞超拟人语音 import XfyunOralTTS
except Exception as e:
    XfyunOralTTS = None
    print(f"[云端] 讯飞超拟人语音加载失败: {e}")

try:
    from 书童程序.核心.语音识别 import SpeechRecognition
except Exception as e:
    SpeechRecognition = None
    print(f"[云端] 语音识别加载失败: {e}")

try:
    from 书童程序.核心.机器人对接.G1_HTTP客户端 import G1HTTPClient
except Exception as e:
    G1HTTPClient = None
    print(f"[云端] G1 HTTP 客户端加载失败: {e}")

# 机器人控制客户端（由师父配置）
robot_client = None
robot_config = {"url": "", "token": ""}

# 家庭机器人注册表（family_id -> {control_url, last_heartbeat, online}）
robot_registry = {}


# ═══════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════
PORT = int(os.environ.get("PORT", "5000"))
HOST = os.environ.get("HOST", "127.0.0.1")
DEBUG = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

# 用户可显式指定的聊天后端白名单
_ALLOWED_BACKENDS = {"auto", "openai", "ollama", "moonshot", "simulation"}


class SimpleRateLimiter:
    """简单内存级滑动窗口限速器（服务重启后清零，仅做基础防护）"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self._store: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        timestamps = [t for t in self._store.get(key, []) if now - t < self.window]
        if len(timestamps) >= self.max_requests:
            self._store[key] = timestamps
            return False
        timestamps.append(now)
        self._store[key] = timestamps
        return True


# 基础限速配置：IP 维度
REGISTER_LIMITER = SimpleRateLimiter(5, 15 * 60)    # 注册：每 IP 15 分钟 5 次
LOGIN_LIMITER = SimpleRateLimiter(200, 15 * 60)     # 登录：每 IP 15 分钟 200 次（测试期放宽）
CHANGE_PW_LIMITER = SimpleRateLimiter(5, 15 * 60)   # 改密：每 IP 15 分钟 5 次
ADMIN_LIMITER = SimpleRateLimiter(60, 60)           # 师父控制台：每 IP 每分钟 60 次
# 业务限速：family 维度
CHAT_LIMITER = SimpleRateLimiter(60, 60)            # 聊天：每家庭每分钟 60 次
TTS_LIMITER = SimpleRateLimiter(30, 60)             # TTS：每家庭每分钟 30 次
STT_LIMITER = SimpleRateLimiter(30, 60)             # STT：每家庭每分钟 30 次
ROBOT_ACTION_LIMITER = SimpleRateLimiter(30, 60)    # 机器人动作：每家庭每分钟 30 次
AGENT_LOGIN_LIMITER = SimpleRateLimiter(10, 15 * 60)  # 代理登录：每 IP 15 分钟 10 次


def _client_ip() -> str:
    """获取客户端真实 IP（优先 X-Forwarded-For，回退 remote_addr）"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"

# 云端灵魂文件路径
SOUL_FILES = {
    "agents": PROJECT_ROOT / "00-灵魂区" / "AGENTS.md",
    "system_prompt": PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "提示词" / "系统提示词整合版_可运行.md",
    "master_prompt": PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "提示词" / "师父模式系统提示词.md",
}

# 临时缓存目录（语音、日志等）
# 云端运行时数据目录：优先使用项目根目录下的 云端数据区（与线上部署一致），
# 本地开发环境若不存在则回退到 04-工作区/云端数据区。
if (PROJECT_ROOT / "云端数据区").exists():
    CACHE_DIR = PROJECT_ROOT / "云端数据区"
else:
    CACHE_DIR = PROJECT_ROOT / "04-工作区" / "云端数据区"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
VOICE_CACHE_DIR = CACHE_DIR / "语音缓存"
VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 师父控制台设备绑定数据（2 台电脑 + 1 部手机）
MASTER_MACHINE_IDS_FILE = CACHE_DIR / "master_machine_ids.json"


def _load_or_generate_key(env_name: str, cache_filename: str, description: str) -> str:
    """读取环境变量密钥；若未设置则从缓存文件读取；仍无则生成强随机密钥并持久化。"""
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    cache_path = CACHE_DIR / cache_filename
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8").strip()
    new_key = secrets.token_urlsafe(32)
    cache_path.write_text(new_key, encoding="utf-8")
    print(f"[安全] 未配置 {env_name}，已生成随机 {description} 并保存到 {cache_path}")
    return new_key


# 云端家庭基本数据目录（含 family.json 等脱敏摘要，不含完整对话）
CLOUD_FAMILY_DIR = CACHE_DIR / "家庭"
CLOUD_FAMILY_DIR.mkdir(parents=True, exist_ok=True)

# 机器人注册表持久化文件（千家万户各自的机器人控制地址）
ROBOT_REGISTRY_FILE = CACHE_DIR / "robot_registry.json"

# ──────────────────────────────────────────
# 分账户系统（SQLite）
# 存放家长注册账号、密码哈希、家庭绑定
# ──────────────────────────────────────────
ACCOUNTS_DB = CACHE_DIR / "accounts.db"

def _init_accounts_db():
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            family_id TEXT UNIQUE NOT NULL,
            family_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS account_sessions (
            token TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            family_id TEXT NOT NULL,
            role TEXT DEFAULT 'parent',
            device_type TEXT DEFAULT 'other',
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT
        )
    """)
    conn.commit()
    conn.close()

_init_accounts_db()

def _ensure_approved_column():
    """确保 accounts 表有 approved 字段；旧数据默认通过"""
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute("PRAGMA table_info(accounts)")
        columns = [row[1] for row in c.fetchall()]
        if "approved" not in columns:
            c.execute("ALTER TABLE accounts ADD COLUMN approved INTEGER DEFAULT 0")
            c.execute("UPDATE accounts SET approved = 1 WHERE approved = 0")
            conn.commit()
            print("[数据库] 已添加 approved 字段，旧账号默认通过")
    except Exception as e:
        print(f"[数据库] approved 字段迁移失败: {e}")
    finally:
        conn.close()


def _ensure_register_info_columns():
    """确保 accounts 表有 contact_name 和 id_card 字段"""
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute("PRAGMA table_info(accounts)")
        columns = [row[1] for row in c.fetchall()]
        if "contact_name" not in columns:
            c.execute("ALTER TABLE accounts ADD COLUMN contact_name TEXT DEFAULT ''")
        if "id_card" not in columns:
            c.execute("ALTER TABLE accounts ADD COLUMN id_card TEXT DEFAULT ''")
        conn.commit()
        print("[数据库] 已确保注册信息字段")
    except Exception as e:
        print(f"[数据库] 注册信息字段迁移失败: {e}")
    finally:
        conn.close()


_ensure_approved_column()
_ensure_register_info_columns()


def _ensure_session_device_column():
    """确保 account_sessions 表有 device_type 字段"""
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute("PRAGMA table_info(account_sessions)")
        columns = [row[1] for row in c.fetchall()]
        if "device_type" not in columns:
            c.execute("ALTER TABLE account_sessions ADD COLUMN device_type TEXT DEFAULT 'other'")
            conn.commit()
            print("[数据库] 已添加 account_sessions.device_type 字段")
    except Exception as e:
        print(f"[数据库] account_sessions.device_type 字段迁移失败: {e}")
    finally:
        conn.close()


_ensure_session_device_column()

def _hash_password(password: str) -> str:
    """使用 werkzeug 的 pbkdf2:sha256 加盐哈希"""
    return generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)


def _verify_password(password: str, stored_hash: str) -> bool:
    """校验密码；兼容旧版 SHA256 无盐哈希，校验通过后自动迁移为加盐哈希"""
    if not stored_hash:
        return False
    # 新格式以 pbkdf2: / scrypt: 开头
    if stored_hash.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(stored_hash, password)
    # 旧版 SHA256 无盐哈希（64 位 hex）
    if len(stored_hash) == 64 and all(c in "0123456789abcdef" for c in stored_hash):
        return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored_hash
    return False

def _gen_token() -> str:
    """生成品牌化的订阅令牌：bookkidai.com/robot/<随机短码>"""
    short = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:12]
    return f"bookkidai.com/robot/{short}"

def register_account(email: str, password: str, family_name: str = "", phone: str = "", contact_name: str = "", id_card: str = "") -> dict:
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        family_id = "f_" + secrets.token_hex(8)
        display_name = family_name or email.split('@')[0] + "的家庭"
        # 新注册账号默认待审核（approved=0）
        c.execute(
            "INSERT INTO accounts (email, password_hash, family_id, family_name, phone, contact_name, id_card, approved) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (email, _hash_password(password), family_id, display_name, phone, contact_name, id_card, 0)
        )
        conn.commit()
        family_data = {
            "family_id": family_id,
            "name": display_name,
            "members": [],
            "contact": {
                "name": contact_name,
                "phone": phone,
                "email": email,
            },
            "id_card": id_card,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        save_cloud_family(family_id, family_data)
        SUBSCRIPTIONS[family_id] = {
            "expires": "2099-12-31",
            "plan": "free",
            "created_at": family_data["created_at"],
            "keys": [{"key": _gen_token(), "device_id": None, "device_ip": None, "activated_at": None, "status": "pending_approval"}],
        }
        save_subscriptions()
        return {"success": True, "family_id": family_id, "pending_approval": True, "message": "注册成功，请等待师父审核通过后即可使用服务"}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "该邮箱已被注册"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

def _get_family_session_quota(family_id: str) -> dict:
    """计算家庭并发登录配额：最少 2 个端口（保障 1 手机 + 1 电脑），按家庭成员数递增"""
    data = load_cloud_family(family_id) or {}
    member_count = len(data.get("members", []))
    max_total = max(2, member_count)
    # 每种设备类型至少保留 1 个空位给对方，防止全部挤占同一类设备
    max_same_type = max(1, max_total - 1)
    return {
        "max_total": max_total,
        "max_mobile": max_same_type,
        "max_pc": max_same_type,
        "member_count": member_count,
    }


def _normalize_device_type(device_type: str | None) -> str:
    """归一化设备类型：mobile / pc / other"""
    dt = (device_type or "other").lower().strip()
    if dt in ("mobile", "phone", "app", "ios", "android"):
        return "mobile"
    if dt in ("pc", "computer", "desktop", "web"):
        return "pc"
    return "other"


def _create_family_session(family_id: str, email: str, device_type: str = "other") -> dict:
    """按家庭配额创建新会话；若超限，按登录时间剔除最旧会话。返回 token / device_type / session_quota"""
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        dt = _normalize_device_type(device_type)
        token = _gen_token()
        quota = _get_family_session_quota(family_id)

        # 清理已过期会话
        c.execute(
            "DELETE FROM account_sessions WHERE family_id = ? AND expires_at IS NOT NULL AND expires_at <= datetime('now')",
            (family_id,),
        )

        # 若同类型设备已达上限，按登录时间剔除最旧的同类型会话
        if dt in ("mobile", "pc"):
            c.execute(
                "SELECT token FROM account_sessions WHERE family_id = ? AND device_type = ? AND (expires_at IS NULL OR expires_at > datetime('now')) ORDER BY created_at ASC",
                (family_id, dt),
            )
            same_type_tokens = [r[0] for r in c.fetchall()]
            while len(same_type_tokens) >= quota[f"max_{dt}"]:
                old_token = same_type_tokens.pop(0)
                c.execute("DELETE FROM account_sessions WHERE token = ?", (old_token,))

        # 若家庭总会话数已达上限，按登录时间剔除最旧的会话
        c.execute(
            "SELECT COUNT(*) FROM account_sessions WHERE family_id = ? AND (expires_at IS NULL OR expires_at > datetime('now'))",
            (family_id,),
        )
        total_active = c.fetchone()[0]
        if total_active >= quota["max_total"]:
            need = total_active - quota["max_total"] + 1
            c.execute(
                "SELECT token FROM account_sessions WHERE family_id = ? AND (expires_at IS NULL OR expires_at > datetime('now')) ORDER BY created_at ASC LIMIT ?",
                (family_id, need),
            )
            for row in c.fetchall():
                c.execute("DELETE FROM account_sessions WHERE token = ?", (row[0],))

        c.execute(
            "INSERT INTO account_sessions (token, email, family_id, role, device_type, expires_at) VALUES (?, ?, ?, ?, ?, datetime('now', '+30 days'))",
            (token, email, family_id, 'parent', dt),
        )
        conn.commit()
        return {"token": token, "device_type": dt, "session_quota": quota}
    except Exception as e:
        print(f"[会话创建] 失败: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


def login_account(email: str, password: str, device_type: str = "other") -> dict:
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute("SELECT family_id, password_hash, approved FROM accounts WHERE email = ?", (email,))
        row = c.fetchone()
        if not row:
            return {"success": False, "error": "邮箱未注册"}
        family_id, stored_hash, approved = row
        if not _verify_password(password, stored_hash):
            return {"success": False, "error": "密码错误"}
        if not approved:
            return {"success": False, "error": "账号待师父审核，审核通过后即可登录", "pending_approval": True}
        # 旧版 SHA256 自动迁移为加盐哈希
        if len(stored_hash) == 64 and all(c in "0123456789abcdef" for c in stored_hash):
            c.execute("UPDATE accounts SET password_hash = ? WHERE email = ?", (_hash_password(password), email))
        conn.commit()
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

    session_result = _create_family_session(family_id, email, device_type)
    if "error" in session_result:
        return {"success": False, "error": session_result["error"]}
    return {
        "success": True,
        "token": session_result["token"],
        "family_id": family_id,
        "email": email,
        "role": "parent",
        "device_type": session_result["device_type"],
        "session_quota": session_result["session_quota"],
    }

def verify_session(token: str) -> dict:
    if not token:
        return {"valid": False}
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute(
            "SELECT email, family_id, role FROM account_sessions WHERE token = ? AND (expires_at IS NULL OR expires_at > datetime('now'))",
            (token,)
        )
        row = c.fetchone()
        if not row:
            return {"valid": False}
        return {"valid": True, "email": row[0], "family_id": row[1], "role": row[2]}
    except Exception as e:
        return {"valid": False}
    finally:
        conn.close()

def change_account_password(email: str, old_password: str, new_password: str) -> dict:
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute("SELECT password_hash FROM accounts WHERE email = ?", (email,))
        row = c.fetchone()
        if not row:
            return {"success": False, "error": "账号不存在"}
        if not _verify_password(old_password, row[0]):
            return {"success": False, "error": "原密码错误"}
        c.execute("UPDATE accounts SET password_hash = ?, updated_at = datetime('now') WHERE email = ?",
                  (_hash_password(new_password), email))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


# ═══════════════════════════════════════════
# 省级管理中心账号系统（SQLite，与账户库共用）
# ═══════════════════════════════════════════

def _init_agents_db():
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            province TEXT DEFAULT '',
            city TEXT DEFAULT '',
            town TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS agent_sessions (
            token TEXT PRIMARY KEY,
            agent_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT
        )
    """)
    conn.commit()
    conn.close()


_init_agents_db()


def register_agent(username: str, password: str, name: str = "", phone: str = "",
                   province: str = "", city: str = "", town: str = "") -> dict:
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO agents (username, password_hash, name, phone, province, city, town) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, _hash_password(password), name, phone, province, city, town)
        )
        conn.commit()
        return {"success": True, "agent_id": c.lastrowid, "username": username}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "代理用户名已存在"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def login_agent(username: str, password: str) -> dict:
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute("SELECT id, password_hash, status FROM agents WHERE username = ?", (username,))
        row = c.fetchone()
        if not row:
            return {"success": False, "error": "用户名不存在"}
        agent_id, stored_hash, status = row
        if status != "active":
            return {"success": False, "error": "代理账号已停用"}
        if not _verify_password(password, stored_hash):
            return {"success": False, "error": "密码错误"}
        token = _gen_token()
        c.execute(
            "INSERT INTO agent_sessions (token, agent_id, username, expires_at) VALUES (?, ?, ?, datetime('now', '+7 days'))",
            (token, agent_id, username)
        )
        conn.commit()
        return {"success": True, "token": token, "agent_id": agent_id, "username": username}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def verify_agent_session(token: str) -> dict:
    if not token:
        return {"valid": False}
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT a.id, a.username, a.name, a.phone, a.province, a.city, a.town, a.status
            FROM agents a
            JOIN agent_sessions s ON a.id = s.agent_id
            WHERE s.token = ? AND (s.expires_at IS NULL OR s.expires_at > datetime('now'))
            """,
            (token,)
        )
        row = c.fetchone()
        if not row or row[7] != "active":
            return {"valid": False}
        return {
            "valid": True,
            "agent_id": row[0],
            "username": row[1],
            "name": row[2],
            "phone": row[3],
            "province": row[4],
            "city": row[5],
            "town": row[6],
        }
    except Exception:
        return {"valid": False}
    finally:
        conn.close()


def change_agent_password(username: str, old_password: str, new_password: str) -> dict:
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute("SELECT password_hash FROM agents WHERE username = ?", (username,))
        row = c.fetchone()
        if not row:
            return {"success": False, "error": "代理不存在"}
        if not _verify_password(old_password, row[0]):
            return {"success": False, "error": "原密码错误"}
        c.execute("UPDATE agents SET password_hash = ?, updated_at = datetime('now') WHERE username = ?",
                  (_hash_password(new_password), username))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def _family_in_agent_scope(family_data: dict, agent: dict) -> bool:
    """判断家庭是否在代理的管辖范围内"""
    prov = (agent.get("province") or "").strip()
    city = (agent.get("city") or "").strip()
    town = (agent.get("town") or "").strip()
    if not prov:
        return False
    if (family_data.get("province") or "").strip() != prov:
        return False
    if city and (family_data.get("city") or "").strip() != city:
        return False
    if town and (family_data.get("town") or "").strip() != town:
        return False
    return True


def _list_families_for_agent(agent: dict) -> list:
    """列出代理管辖范围内的所有家庭摘要"""
    result = []
    for family_dir in sorted(CLOUD_FAMILY_DIR.iterdir()):
        if not family_dir.is_dir():
            continue
        data = load_cloud_family(family_dir.name)
        if not data or not _family_in_agent_scope(data, agent):
            continue
        result.append({
            "family_id": family_dir.name,
            "name": data.get("name", "未命名家庭"),
            "province": data.get("province", ""),
            "city": data.get("city", ""),
            "town": data.get("town", ""),
            "contact_name": data.get("contact_name", ""),
            "contact_phone": data.get("contact_phone", ""),
            "member_count": len(data.get("members", [])),
            "children": [
                {"name": m.get("name"), "age": m.get("age"), "stage": m.get("stage", "")}
                for m in data.get("members", [])
                if m.get("role") == "孩子" and m.get("name")
            ],
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
        })
    return result


# 订阅持久化文件
SUBSCRIPTIONS_FILE = CACHE_DIR / "subscriptions.json"

# ═══════════════════════════════════════════
# Flask 应用
# ═══════════════════════════════════════════
app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))


@app.before_request
def _global_rate_limit():
    """师父控制台/管理接口统一限速"""
    if request.path.startswith(("/admin", "/master")):
        if not ADMIN_LIMITER.is_allowed(_client_ip()):
            return jsonify({"success": False, "error": "请求太频繁，请稍后再试"}), 429


@app.before_request
def _handle_cors_preflight():
    """对师父控制台相关路径统一响应 OPTIONS 预检请求。"""
    if request.method == "OPTIONS" and request.path.startswith(("/admin", "/api/master", "/api/cloud")):
        return jsonify({"success": True}), 200


@app.before_request
def _check_master_machine_binding():
    """
    师父控制台 / 管理接口统一设备绑定校验。
    仅当请求携带了有效 master key 时才校验设备，避免影响普通家长接口。
    /api/master/verify 自身会处理绑定，避免此处重复拦截导致无法首次绑定。
    """
    if request.path.startswith(("/admin", "/api/master")) and request.path != "/api/master/verify":
        # 如果请求携带了 master key，则必须同时通过设备绑定
        if _extract_master_key():
            ok, msg = auth_master_with_machine()
            if not ok:
                client_ip = _client_ip()
                print(f"[master_device_bind] 拒绝 {client_ip} {request.method} {request.path}: {msg}")
                return jsonify({"success": False, "error": msg}), 403


@app.after_request
def _add_cors_headers(response):
    """为师父控制台接口补充 CORS 头，兼容微信内置浏览器等可能发起预检的 WebView。"""
    if request.path.startswith(("/admin", "/api/master", "/master", "/api/cloud")):
        origin = request.headers.get("Origin", "")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Machine-ID, X-Device-Type, X-Requested-With"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


# ──────────────────────────────────────────
# 分账户 API 路由（必须在 app 定义之后）
# ──────────────────────────────────────────
@app.route("/api/account/register", methods=["POST"])
def api_account_register():
    if not REGISTER_LIMITER.is_allowed(_client_ip()):
        return jsonify({"success": False, "error": "注册太频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    family_name = (data.get("family_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    contact_name = (data.get("contact_name") or "").strip()
    id_card = (data.get("id_card") or "").strip()
    if not email or not password:
        return jsonify({"success": False, "error": "邮箱和密码不能为空"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "密码至少6位"}), 400
    if not phone or not re.match(r"^1[3-9]\d{9}$", phone):
        return jsonify({"success": False, "error": "请填写正确的11位手机号"}), 400
    if not contact_name:
        return jsonify({"success": False, "error": "请填写联系人姓名"}), 400
    if not id_card or not re.match(r"^\d{17}[\dXx]$|^\d{15}$", id_card):
        return jsonify({"success": False, "error": "请填写正确的身份证号"}), 400
    if not family_name:
        return jsonify({"success": False, "error": "请填写家庭名称"}), 400
    result = register_account(email, password, family_name, phone, contact_name, id_card)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 400

@app.route("/api/account/login", methods=["POST"])
def api_account_login():
    if not LOGIN_LIMITER.is_allowed(_client_ip()):
        return jsonify({"success": False, "error": "登录太频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or {}
    account = (data.get("account") or data.get("email") or "").strip()
    password = data.get("password") or ""
    if not account or not password:
        return jsonify({"success": False, "error": "账号和密码不能为空"}), 400
    email = _resolve_account_to_email(account)
    if not email:
        return jsonify({"success": False, "error": "账号不存在"}), 401
    device_type = data.get("device_type") or request.headers.get("X-Device-Type", "")
    result = login_account(email, password, device_type=device_type)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 401


def _auth_account_session() -> tuple[str | None, str | None, str]:
    """校验账号会话 token，返回 (family_id, email, error)"""
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        return None, None, "缺少登录凭证"
    session = verify_session(token)
    if not session.get("valid"):
        return None, None, "登录已过期，请重新登录"
    return session.get("family_id"), session.get("email"), ""


@app.route("/api/status", methods=["GET"])
def api_status():
    """本地家庭端兼容状态接口"""
    family_id, email, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = load_cloud_family(family_id) or {}
    children = []
    for m in data.get("members", []):
        if m.get("role") == "孩子":
            children.append({
                "id": m.get("user_id") or m.get("name", "child"),
                "name": m.get("name", ""),
                "age": m.get("age"),
                "stage": m.get("stage", ""),
                "grade": m.get("grade", ""),
                "gender": m.get("gender", ""),
                "status": m.get("status") or "green",
            })
    current_child = children[0]["id"] if children else None
    return jsonify({
        "success": True,
        "family_id": family_id,
        "email": email,
        "role": "parent",
        "children": children,
        "current_child": current_child,
        "session_child": current_child,
        "backend": CONFIG.get("backend", "auto") or "moonshot",
        "model": CONFIG.get("moonshot_model") or CONFIG.get("openai_model") or "",
        "voice_enabled": True,
    })


@app.route("/api/switch_child", methods=["POST"])
def api_switch_child():
    """本地家庭端兼容切换孩子"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = request.get_json(silent=True) or {}
    child_id = data.get("child_id")
    return jsonify({
        "success": True,
        "family_id": family_id,
        "current_child": child_id,
    })


@app.route("/api/family", methods=["GET"])
def api_family():
    """本地家庭端兼容获取单个家庭信息"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    query_family_id = request.args.get("family_id") or family_id
    if query_family_id != family_id:
        return jsonify({"success": False, "error": "无权访问该家庭"}), 403
    data = load_cloud_family(family_id) or {}
    return jsonify({
        "success": True,
        "family_id": family_id,
        "family": data,
    })


@app.route("/api/families", methods=["GET"])
def api_families():
    """本地家庭端兼容获取当前账号的家庭列表"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = load_cloud_family(family_id) or {}
    return jsonify({
        "success": True,
        "families": [{
            "family_id": family_id,
            "name": data.get("name", ""),
            "description": data.get("description", ""),
        }],
    })


@app.route("/api/family", methods=["POST"])
def api_family_update():
    """本地家庭端兼容保存家庭信息"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = request.get_json(silent=True) or {}
    # 云端账号一户一家庭，以会话中的 family_id 为准，避免前端传错 default_family
    payload_family_id = data.get("family_id") or family_id
    if payload_family_id != family_id:
        print(f"[家庭保存] payload family_id {payload_family_id} 与会话 {family_id} 不一致，使用会话 family_id")
        payload_family_id = family_id

    family_data = load_cloud_family(family_id) or {}
    family_data["name"] = data.get("name", family_data.get("name", ""))
    family_data["description"] = data.get("description", family_data.get("description", ""))
    if "members" in data:
        # 合并新成员信息，保留原有字段（user_id、welcome_child 等）
        existing = {m.get("user_id") or m.get("name"): m for m in family_data.get("members", [])}
        merged = []
        for m in data["members"]:
            key = m.get("user_id") or m.get("name")
            old = existing.get(key) or {}
            merged_member = dict(old)
            merged_member.update({k: v for k, v in m.items() if v is not None})
            merged_member.setdefault("user_id", key)
            merged.append(merged_member)
        family_data["members"] = merged
    family_data["updated_at"] = datetime.now().isoformat()

    if save_cloud_family(family_id, family_data):
        return jsonify({"success": True, "family": family_data, "family_id": family_id})
    return jsonify({"success": False, "error": "保存失败"}), 500


@app.route("/api/memory", methods=["GET"])
def api_memory_get():
    """获取当前家庭的记忆包（家长/孩子可以查机器库里记了什么）"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    memory = _load_family_memory(family_id)
    return jsonify({"success": True, "family_id": family_id, "memory": memory})


def _family_settings_path(family_id: str) -> Path:
    return CLOUD_FAMILY_DIR / family_id / "settings.json"


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    """本地家庭端兼容获取设置"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    settings_path = _family_settings_path(family_id)
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            return jsonify({"success": True, "settings": settings})
        except Exception:
            pass
    return jsonify({"success": True, "settings": {}})


@app.route("/api/settings", methods=["POST"])
def api_settings_save():
    """本地家庭端兼容保存设置"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = request.get_json(silent=True) or {}
    settings = data.get("settings", {})
    settings_path = _family_settings_path(family_id)
    try:
        settings_path.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
        return jsonify({"success": True, "settings": settings})
    except Exception as e:
        return jsonify({"success": False, "error": f"保存失败: {e}"}), 500


@app.route("/api/login", methods=["POST"])
def api_login_compat():
    """本地家庭端兼容自动登录：若请求带了有效 token 则刷新返回，否则失败"""
    family_id, email, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = request.get_json(silent=True) or {}
    device_type = data.get("device_type") or request.headers.get("X-Device-Type", "")
    session_result = _create_family_session(family_id, email, device_type)
    if "error" in session_result:
        return jsonify({"success": False, "error": f"会话创建失败: {session_result['error']}"}), 500
    return jsonify({
        "success": True,
        "token": session_result["token"],
        "family_id": family_id,
        "email": email,
        "role": "parent",
        "device_type": session_result["device_type"],
        "session_quota": session_result["session_quota"],
    })


def _build_user_context(family_id: str, user_id: str, child_id: str, message: str):
    """识别当前对话者身份，返回 (user_context, identity_examples, current_member)。"""
    family_data = load_cloud_family(family_id) or {}
    members = family_data.get("members", [])
    current_member = None
    claim_conflict = False

    # 1. 优先按 user_id 匹配
    if user_id:
        for m in members:
            if (m.get("user_id") or "") == user_id:
                current_member = m
                break
    # 2. 按 child_id（可能是 user_id 或孩子姓名）回退匹配
    if not current_member and child_id:
        for m in members:
            if (m.get("user_id") or "") == child_id or (m.get("name") or "") == child_id:
                current_member = m
                break
    # 3. 按当前选中孩子姓名回退（家庭端常见传 name 作为 id）
    if not current_member and child_id:
        for m in members:
            if m.get("role") == "孩子" and (m.get("name") or "") == child_id:
                current_member = m
                break

    # 如果用户自称是谁（如"我是嘟嘟"），按自称的身份回应，但标记可能的身份冲突
    identity_claim = None
    for m in members:
        name = m.get("name", "")
        if name and (f"我是{name}" in message or f"我叫{name}" in message):
            identity_claim = m
            break
    if identity_claim:
        if current_member and current_member.get("user_id") != identity_claim.get("user_id"):
            claim_conflict = True
        current_member = identity_claim

    user_context = ""
    identity_examples = []
    if current_member:
        relation = current_member.get("relation", "")
        role = current_member.get("role", "")
        name = current_member.get("name", "")
        user_context = f"\n\n【当前对话者】\n姓名：{name}\n身份：{role}\n关系：{relation}\n"
        user_context += f"\n【称呼铁律·最高优先级】你正在和{name}对话。回应时只能称呼对方为“{name}”或符合其身份的“{relation}”，绝对禁止称其为其他任何姓名，也绝对禁止称其为师父、师母、师姑、师伯、师叔、家长、妈妈、爸爸（除非这些词正好是其身份关系的一部分）。\n"
        if claim_conflict:
            user_context += "\n【注意】用户自称的身份与登录身份不一致。以用户自称的身份回应，但保持警惕，涉及安全/隐私问题时需进一步确认。\n"
        # 墨童能力边界修正：成人/家长/师父提问时直接提供专业帮助，不缩窄能力
        if role in ("家长", "师父") or relation in ("家长", "师父", "师母", "妈妈", "爸爸"):
            user_context += "\n【墨童能力范围】当前对话者是成人。你可以直接提供管理、文案、规划、技术、教育、生活等专业帮助，不要先声明自己主业是陪伴孩子，也不要缩小自己的能力范围。\n"
        if "师母" in relation:
            user_context += f"{name}是师母，你回应时直接称呼她为'师母'或'{name}'即可，不要加姓氏，绝对禁止称她为家长、妈妈或师父。\n"
        elif "师父" in relation:
            user_context += f"{name}是师父，你回应时直接称呼他为'师父'或'{name}'即可，不要加姓氏。\n"
        elif role == "家长":
            user_context += f"{name}是家长，你回应时称呼她为'家长'、'妈妈'、'爸爸'或直接使用其姓名“{name}”，绝对禁止称为师父、师母、师姑、师伯、师叔。\n"
        elif role == "孩子":
            user_context += f"{name}是孩子，你回应时直接称呼他/她的姓名“{name}”或'小朋友'，绝对禁止称为师父、师母、家长、爸爸、妈妈。\n"
    else:
        # 未知身份：强制模型不要加称呼，不要假设对方是任何人
        user_context = "\n\n【当前对话者】\n身份：未知\n\n【称呼铁律·最高优先级】你暂时不知道对方是谁。回应时绝对不要加任何称呼（包括但不限于师父、师母、家长、妈妈、爸爸、小朋友、具体人名），直接回应内容即可。\n"

    # 特殊问题处理：有人问"你的师父是谁"时，不要默认对方就是师父
    if "你的师父" in message or "你师父" in message:
        user_context += "\n【重要】当用户问'你的师父是谁'时，要根据当前对话者身份回答：如果对方是师父，可回答'师父就是您'；如果对方是孩子或家长，必须回答'我的师父是刘清源'，不能称对方为师父。\n"

    if current_member:
        relation = current_member.get("relation", "")
        role = current_member.get("role", "")
        name = current_member.get("name", "")
        if "师母" in relation:
            identity_examples = [
                {"role": "user", "content": "我是师母。"},
                {"role": "assistant", "content": "师母好，书童在。有什么需要书童做的吗？"},
            ]
        elif "师父" in relation:
            identity_examples = [
                {"role": "user", "content": "我是师父。"},
                {"role": "assistant", "content": "师父好，书童在。有什么吩咐吗？"},
            ]
        elif role == "家长":
            identity_examples = [
                {"role": "user", "content": "我是家长。"},
                {"role": "assistant", "content": f"{name}您好，书童在。孩子的事您随时问我。"},
            ]
        elif role == "孩子":
            identity_examples = [
                {"role": "user", "content": "我是" + name + "。"},
                {"role": "assistant", "content": f"{name}你好呀，书童在。今天想聊点什么？"},
            ]
    else:
        # 未知身份示例：直接回应，不加称呼
        identity_examples = [
            {"role": "user", "content": "你好。"},
            {"role": "assistant", "content": "你好呀！我是书童，有什么想聊的吗？"},
        ]

    return user_context, identity_examples, current_member


def _chat_history_path(family_id: str) -> Path:
    return CLOUD_FAMILY_DIR / family_id / "chat_history.jsonl"


def _family_memory_path(family_id: str) -> Path:
    return CLOUD_FAMILY_DIR / family_id / "family_memory.json"


def _token_usage_path(family_id: str) -> Path:
    return CLOUD_FAMILY_DIR / family_id / "token_usage.json"


def _ensure_family_dir(family_id: str):
    path = CLOUD_FAMILY_DIR / family_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def record_family_token_usage(family_id: str, usage_info: dict):
    """记录家庭 token 消耗（按日/月/总累计），线程安全"""
    if not family_id or not usage_info:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    path = _token_usage_path(family_id)
    _ensure_family_dir(family_id)
    lock_key = f"token_usage:{family_id}"
    lock = _FILE_LOCKS.setdefault(lock_key, threading.Lock())
    with lock:
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        # 基础累计
        data["total_prompt_tokens"] = data.get("total_prompt_tokens", 0) + usage_info.get("prompt_tokens", 0)
        data["total_completion_tokens"] = data.get("total_completion_tokens", 0) + usage_info.get("completion_tokens", 0)
        data["total_tokens"] = data.get("total_tokens", 0) + usage_info.get("total_tokens", 0)
        # 按天
        data.setdefault("daily", {})
        data["daily"].setdefault(today, {"prompt": 0, "completion": 0, "total": 0})
        data["daily"][today]["prompt"] += usage_info.get("prompt_tokens", 0)
        data["daily"][today]["completion"] += usage_info.get("completion_tokens", 0)
        data["daily"][today]["total"] += usage_info.get("total_tokens", 0)
        # 按月
        data.setdefault("monthly", {})
        data["monthly"].setdefault(month, {"prompt": 0, "completion": 0, "total": 0})
        data["monthly"][month]["prompt"] += usage_info.get("prompt_tokens", 0)
        data["monthly"][month]["completion"] += usage_info.get("completion_tokens", 0)
        data["monthly"][month]["total"] += usage_info.get("total_tokens", 0)
        # 最近记录
        data.setdefault("recent", [])
        entry = {
            "time": datetime.now().isoformat(),
            "prompt_tokens": usage_info.get("prompt_tokens", 0),
            "completion_tokens": usage_info.get("completion_tokens", 0),
            "total_tokens": usage_info.get("total_tokens", 0),
        }
        data["recent"].insert(0, entry)
        data["recent"] = data["recent"][:100]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_family_token_usage(family_id: str) -> dict:
    path = _token_usage_path(family_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_family_memory(family_id: str) -> dict:
    path = _family_memory_path(family_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _format_family_memory(memory: dict) -> str:
    if not memory:
        return ""
    lines = [
        "\n\n【家庭长期记忆】",
        "以下是从历史对话中记录的家庭事实，时间戳为记录日期。",
        "铁律：",
        "1. 回答时必须把这些事实当作已知信息使用，不要说我'不知道''不记得''没有记录'。",
        "2. 如果记忆与当前用户说的内容冲突，优先相信当前用户亲口说的事实，并诚实说明'书童之前的记录是...，如果你现在说的不同，以你为准'。",
        "3. 绝对禁止基于记忆编造不存在的故事、对话或细节。",
        "4. 如果用户问'最近怎么样'而你只有记忆没有时间线，要诚实说'书童知道这些事实，但最近的具体情况需要你告诉我'。",
        ""
    ]
    for key, value in memory.items():
        if isinstance(value, list):
            lines.append(f"- {key}:")
            for item in value:
                lines.append(f"  • {item}")
        else:
            lines.append(f"- {key}: {value}")
    return "\n".join(lines)


#  fabrication 关键词：模型若说出这些话，说明它可能在编造事实
_FABRICATION_PATTERNS = [
    r"我[记得|想起|读过|看过|听过]",
    r"[上回|上次|昨天|前几天|之前|以前].*你[说|做|提到]",
    r"[根据|依据].*记录",
    r"你[以前|之前|上次].*告诉[我|过]",
    r"我[发现|注意到|观察到].*你",
]


def _fabrication_guard(reply: str, family_memory: dict, chat_history: list) -> str:
    """
    后置编造守卫：扫描回复，如果模型声称记得/看过/听过未经验证的事实，
    而记忆或历史中并无对应记录，则触发修正提示（当前版本以记录日志为主）。
    """
    import re
    flagged = False
    for pat in _FABRICATION_PATTERNS:
        if re.search(pat, reply):
            flagged = True
            break

    # 额外检查：如果回复提到'你最近...'而记忆中没有近期事实，也标记
    recent_claim = re.search(r"你(最近|这几天|这段时间).{2,20}[了着]", reply)
    if recent_claim and not any("重要事件" in k for k in (family_memory or {}).keys()):
        flagged = True

    if flagged:
        print(f"[编造守卫] 检测到可能编造: {reply[:80]}...")
        # 在当前回复后追加一句自我修正，避免直接替换用户可见内容
        # 实际策略：如果置信度高，可在回复末尾温和补充；这里先记录日志
    return reply


def _extract_and_update_memory(family_id: str, user_msg: str, assistant_msg: str, user_id: str):
    """后台提取本轮对话中的关键事实，更新家庭长期记忆包。"""
    try:
        path = _family_memory_path(family_id)
        memory = _load_family_memory(family_id)
        family_data = load_cloud_family(family_id) or {}
        members = family_data.get("members", [])
        member_names = [m.get("name", "") for m in members if m.get("name")]
        text = f"{user_msg} {assistant_msg}"
        import re

        today = datetime.now().strftime("%Y-%m-%d")

        def _ensure_list(key: str):
            if key not in memory:
                memory[key] = []
            if not isinstance(memory[key], list):
                memory[key] = [memory[key]]

        def _add_fact(key: str, value: str, max_items: int = 10):
            """添加带时间戳的事实，避免重复和无限增长。"""
            if not value or not value.strip():
                return
            value = value.strip()
            _ensure_list(key)
            entry = f"[{today}] {value}"
            # 去重：如果已有相同 value（忽略时间戳），不重复添加
            existing_values = [re.sub(r"^\[\d{4}-\d{2}-\d{2}\]\s*", "", x) for x in memory[key]]
            if value in existing_values:
                return
            memory[key].append(entry)
            if len(memory[key]) > max_items:
                memory[key] = memory[key][-max_items:]

        def _set_latest(key: str, value: str):
            """覆盖式保存最新值（适合状态类记忆）。"""
            if value and value.strip():
                memory[key] = value.strip()

        # 1. 家长明确嘱咐 / 指令（最高优先级，只从用户消息中提取）
        instruction_patterns = [
            r"(?:记住|记下|记好|别忘了|你记着|你给我记住)[了：]?\s*(.{2,80})(?:[。！;]|$)",
            r"(?:以后|下次|往后|之后)\s*(.{2,80})(?:[。！;]|$)",
            r"(?:你要|你不要|你必须|你记得|你要记得)\s*(.{2,80})(?:[。！;]|$)",
            r"(?:查一下|去查|帮我查|到.*里查)\s*(.{2,80})(?:[。！;]|$)",
        ]
        seen_instructions = set()
        for pat in instruction_patterns:
            for m in re.finditer(pat, user_msg):
                instr = m.group(1).strip("，。；！？")
                # 避免重复或过长边界
                if instr and len(instr) >= 5 and instr not in seen_instructions:
                    seen_instructions.add(instr)
        # 去重：剔除被更长指令包含的短指令片段
        filtered = []
        for instr in sorted(seen_instructions, key=len, reverse=True):
            if not any(instr != other and instr in other for other in filtered):
                filtered.append(instr)
        for instr in filtered[:20]:
            _add_fact("家长嘱咐", instr, max_items=20)

        # 2. 提取分数/成绩
        score_matches = re.findall(r"(\d{2,3})\s*分", text)
        for score in score_matches[:3]:
            _add_fact("提到的分数", score)

        # 3. 提取目标学校
        school_patterns = [
            r"目标[高中学校]+[是为的]*\s*[:：]?\s*([^，。；\n]{2,10})[高中学校]?",
            r"想上[哪所]*\s*[:：]?\s*([^，。；\n]{2,10})[高中学校]?",
            r"想考[哪所]*\s*[:：]?\s*([^，。；\n]{2,10})[高中学校]?",
        ]
        for pat in school_patterns:
            m = re.search(pat, text)
            if m:
                school = m.group(1).strip()
                if school and len(school) >= 2:
                    memory["目标学校"] = school
                    break

        # 4. 提取薄弱科目与优势科目
        weak_match = re.search(r"(数学|语文|英语|物理|化学|生物|道法|历史|地理).{0,5}(很差|薄弱|不好|吃力|跟不上)", text)
        if weak_match:
            _add_fact("薄弱科目", weak_match.group(1))
        strong_match = re.search(r"(数学|语文|英语|物理|化学|生物|道法|历史|地理).{0,5}(很好|不错|优秀|擅长|拔尖)", text)
        if strong_match:
            _add_fact("优势科目", strong_match.group(1))

        # 5. 提取情绪/心理状态（保留最近一次）
        emotion_keywords = ["焦虑", "抑郁", "失眠", "自杀", "自残", "叛逆", "压力大", "情绪低落", "开心", "兴奋", "难过", "生气", "暴躁", "敏感", "内向", "外向"]
        for kw in emotion_keywords:
            if kw in text:
                _set_latest("心理状态", kw)
                break

        # 6. 提取性格特点
        personality_keywords = ["内向", "外向", "活泼", "安静", "慢热", "急躁", "细心", "粗心", "固执", "听话", "调皮", "懂事", "敏感", "大胆", "害羞"]
        for kw in personality_keywords:
            if kw in text:
                _add_fact("性格特点", kw)

        # 7. 提取年级
        grade_match = re.search(r"(小学[一二三四五六]年级|初中[一二三]年级|高中[一二三]年级|初三|高一|高二|高三)", text)
        if grade_match:
            memory["当前年级"] = grade_match.group(1)

        # 8. 提取兴趣爱好/喜好
        hobby_keywords = ["画画", "唱歌", "跳舞", "运动", "看书", "阅读", "编程", "游戏", "钢琴", "吉他", "篮球", "足球", "游泳", "跑步", "乐高", "魔方", "围棋", "象棋", "羽毛球", "乒乓球", "滑雪", "骑行", "徒步", "旅行", "烘焙", "手工", "书法", "武术", "跆拳道", "芭蕾", "街舞", "绘画", "拼图", "跳绳", "滑板", "轮滑"]
        # 先尝试提取“喜欢/爱/爱好 + 多个兴趣”的并列结构
        hobby_list_match = re.search(r"(?:喜欢|爱|爱好)([^，。；\n]{1,30})(?:和|、|，)", text)
        if hobby_list_match:
            items = re.split(r"[和、，,]", hobby_list_match.group(1))
            for item in items:
                item = item.strip()
                if item and len(item) <= 8:
                    _add_fact("兴趣爱好", item)
        # 兜底：逐个关键词匹配
        for kw in hobby_keywords:
            if kw in text:
                _add_fact("兴趣爱好", kw)

        # 9. 提取阅读/观看内容
        media_patterns = [
            r"(?:在读|正在读|读了|看过|在看|喜欢).{0,3}《([^》]{1,20})》",
            r"(?:在读|正在读|读了|看过|在看|喜欢)\s*([《""][^《""]+[》""])",
        ]
        for pat in media_patterns:
            for m in re.finditer(pat, text):
                media = m.group(1).strip()
                if media:
                    _add_fact("阅读与观看", media)

        # 10. 提取学习习惯
        study_habit_patterns = [
            r"(?:学习习惯|写作业|做作业|专注力|注意力|拖拉|磨蹭|自觉|主动|被动).{0,5}(?:是|为|：)?\s*(.{3,40})[。；]?",
            r"(?:每天|每晚|每周|经常|总是|从不)\s*(.{3,30})(?:学习|写作业|看书|复习|预习)",
        ]
        for pat in study_habit_patterns:
            for m in re.finditer(pat, text):
                habit = m.group(1).strip("，。；")
                if habit and len(habit) >= 3:
                    _add_fact("学习习惯", habit)

        # 11. 提取作息规律
        schedule_patterns = [
            r"(?:几点|什么时候|通常|一般|每天).{0,5}(?:睡觉|起床|吃饭|上学|放学|写作业).{0,3}(\d{1,2}\s*[点:]\s*\d{0,2}分?)",
            r"(?:晚上|早上|中午|下午)\s*(\d{1,2}\s*[点:]\s*\d{0,2}分?)\s*(?:睡觉|起床|吃饭|上学|放学|写作业)",
        ]
        for pat in schedule_patterns:
            for m in re.finditer(pat, text):
                schedule = m.group(0).strip("，。；")
                if schedule:
                    _add_fact("作息规律", schedule)

        # 12. 提取饮食偏好与禁忌
        food_patterns = [
            r"(?:喜欢|爱吃|讨厌|不吃|过敏|不能吃|忌口).{0,3}(.{2,15})(?:菜|肉|鱼|蛋|奶|水果|零食|饭|面)",
            r"(?:对|对什么).{0,3}(\w{1,8})(?:过敏|不耐受)",
        ]
        for pat in food_patterns:
            for m in re.finditer(pat, text):
                food = m.group(0).strip("，。；")
                if food and len(food) >= 3:
                    _add_fact("饮食偏好与禁忌", food)

        # 13. 提取健康状况
        health_patterns = [
            r"(?:有|确诊|患|得|经常|反复).{0,3}(近视|远视|散光|过敏|哮喘|鼻炎|湿疹|发烧|感冒|咳嗽|肚子疼|便秘|腹泻|多动症|抽动症|孤独症|自闭)",
            r"(?:近视|远视|散光|过敏|哮喘|鼻炎|湿疹|多动症|抽动症|孤独症|自闭).{0,3}(?:多少度|几度|严重|轻度|中度)",
        ]
        for pat in health_patterns:
            for m in re.finditer(pat, text):
                health = m.group(0).strip("，。；")
                if health:
                    _add_fact("健康状况", health)

        # 14. 提取身高体重
        height_match = re.search(r"(?:身高|高)(\d{2,3})\s*(?:厘米|cm|CM)", text)
        if height_match:
            _set_latest("身高", f"{height_match.group(1)}厘米")
        weight_match = re.search(r"(?:体重|重)(\d{2,3}(?:\.\d{1,2})?)\s*(?:公斤|千克|kg|KG)", text)
        if weight_match:
            _set_latest("体重", f"{weight_match.group(1)}公斤")

        # 15. 提取奖励与惩罚
        reward_penalty_patterns = [
            r"(?:奖励|表扬|鼓励|给|答应).{0,3}(.{3,30})(?:作为奖励|当奖励|奖励他|奖励她)",
            r"(?:惩罚|批评|没收|取消|不许|禁止).{0,3}(.{3,30})(?:作为惩罚|当惩罚|惩罚他|惩罚她)",
        ]
        for pat in reward_penalty_patterns:
            for m in re.finditer(pat, text):
                rp = m.group(0).strip("，。；")
                if rp:
                    _add_fact("奖励与惩罚", rp)

        # 16. 提取朋友与人际关系
        friend_match = re.search(r"(?:朋友|同学|玩伴|好朋友|闺蜜|兄弟|姐妹).{0,5}(?:叫|是|有)\s*([^，。；\n]{1,8})", text)
        if friend_match:
            friend = friend_match.group(1).strip()
            if friend and len(friend) >= 1:
                _add_fact("朋友与人际", friend)

        # 17. 提取恐惧与敏感点
        fear_patterns = [
            r"(?:害怕|怕|恐惧|不敢|讨厌|反感|不喜欢).{0,3}(.{2,20})(?:东西|事情|声音|地方|人|动物|场景)",
            r"(?:害怕|怕|恐惧|不敢|讨厌).{0,3}(.{2,15})[。；，]?",
        ]
        for pat in fear_patterns:
            for m in re.finditer(pat, text):
                fear = m.group(0).strip("，。；")
                if fear and len(fear) >= 3:
                    _add_fact("恐惧与敏感点", fear)

        # 18. 提取重要约定/规则
        rule_patterns = [
            r"(?:约定|规定|规矩|家规).{0,3}[:：]?\s*(.{3,40})[。；]?",
            r"(?:说好|讲定|商量好).{0,3}(.{3,40})[。；]?",
        ]
        for pat in rule_patterns:
            for m in re.finditer(pat, text):
                rule = m.group(1).strip("，。；")
                if rule:
                    _add_fact("家庭约定", rule)

        # 19. 提取重要事件/变化
        event_keywords = ["搬家", "转学", "生病", "住院", "考试", "比赛", "获奖", "出生", "去世", "换班", "换老师", "入园", "入学", "毕业"]
        for kw in event_keywords:
            if kw in text:
                idx = text.find(kw)
                start = max(0, idx - 8)
                end = min(len(text), idx + 12)
                event_summary = text[start:end].strip("，。；")
                _add_fact("重要事件", event_summary)
                break

        # 20. 提取生日/年龄（用于年龄计算）
        birthday_match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日[出生]?", text)
        if birthday_match:
            memory["生日"] = f"{birthday_match.group(1)}-{int(birthday_match.group(2)):02d}-{int(birthday_match.group(3)):02d}"
        age_match = re.search(r"(?:今年|现在)(\d{1,2})岁", text)
        if age_match:
            memory["年龄"] = f"{age_match.group(1)}岁"

        # 21. 提取重要日期（除生日外）
        date_patterns = [
            r"(?:纪念日|重要日子|特殊日子|节日).{0,3}(\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日)",
            r"(\d{4}年\d{1,2}月\d{1,2}日)\s*(?:是|为).{0,5}(?:生日|纪念日|重要日子|节日)",
        ]
        for pat in date_patterns:
            for m in re.finditer(pat, text):
                date_info = m.group(0).strip("，。；")
                if date_info:
                    _add_fact("重要日期", date_info)

        if memory:
            _ensure_family_dir(family_id)
            path.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[家庭记忆更新失败] {e}")


def _load_chat_history(family_id: str, limit: int = 10) -> list:
    path = _chat_history_path(family_id)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        messages = []
        for line in lines[-limit * 2:]:
            if line.strip():
                try:
                    m = json.loads(line)
                    # 过滤掉内容为空的消息，避免传给模型时报错
                    if (m.get("content") or "").strip():
                        messages.append(m)
                except Exception:
                    continue
        return messages
    except Exception:
        return []


def _save_chat_history(family_id: str, user_msg: str, assistant_msg: str, user_id: str = ""):
    """保存对话历史；如果助理回复为空，则不保存该轮，防止后续请求被模型拒绝。"""
    user_msg = (user_msg or "").strip()
    assistant_msg = (assistant_msg or "").strip()
    if not user_msg or not assistant_msg:
        print(f"[聊天历史] 跳过保存空消息: user={bool(user_msg)}, assistant={bool(assistant_msg)}")
        return
    path = _chat_history_path(family_id)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"role": "user", "content": user_msg, "user_id": user_id, "time": datetime.now().isoformat()}, ensure_ascii=False) + "\n")
            f.write(json.dumps({"role": "assistant", "content": assistant_msg, "time": datetime.now().isoformat()}, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[聊天历史保存失败] {e}")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """本地家庭端兼容聊天接口（转发到云端 AI 能力）"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    if not is_family_approved(family_id):
        return jsonify({"success": False, "error": "账号待师父审核"}), 403

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    raw_image = data.get("image")
    # 支持单张图（字符串）或多张图（列表），统一归一化为列表
    if isinstance(raw_image, str) and raw_image:
        image_data = [raw_image]
    elif isinstance(raw_image, list):
        image_data = [img for img in raw_image if img]
    else:
        image_data = []
    mode = data.get("mode", "child")
    voice_enabled = bool(data.get("voice", False))
    user_id = data.get("user_id") or data.get("child_id") or ""
    child_id = data.get("child_id") or ""
    is_mobile = bool(data.get("mobile")) or any(k in (request.headers.get("User-Agent", "") or "").lower() for k in ["mobile", "android", "iphone", "ipad"])
    if not message and not image_data:
        return jsonify({"success": False, "error": "消息不能为空"}), 400

    base_prompt = soul_cache.get("master_prompt" if mode == "master" else "system_prompt", "")
    if not base_prompt.strip():
        print(f"[警告] 灵魂文件未加载或为空，mode={mode}。使用兜底提示词。")
        base_prompt = "你是伴读书童AI，陪伴0-18岁孩子健康成长。你不是老师、不是医生、不是家长替代品。"
    if is_mobile:
        base_prompt += "\n\n【手机端优化】\n用户正在手机端提问，请优先给出简洁、可直接阅读的中文回复，避免过长大段。思考过程仍用中文。"

    # 运行时铁律：真实优先（防止模型编造事实）
    base_prompt += (
        "\n\n【真实优先·运行时铁律·不可违反】\n"
        "1. 你绝对禁止编造、虚构、臆测任何事实。\n"
        "2. 禁止说'我读过''我记得''我看过''我听过''师父以前讲过''这个案例记录过'等暗示你有未经验证记忆的话。\n"
        "3. 禁止用'昨天''最近''有一次''之前'等时间词描述没有真实记录的事情。\n"
        "4. 如果你不确定、没有依据、没有记录，必须诚实说：'书童不确定''书童没有这个记录''这需要进一步确认'。\n"
        "5. 你可以基于医学、发育规律、文化常识给出分析和建议，但必须明确区分'这是规律/建议'和'这是该孩子的事实'。\n"
        "6. 真实是信任的根基。编造一次，永远失去信任。\n"
    )

    # 注入当前日期，避免模型因知识截止而算错年龄
    today = datetime.now().strftime("%Y年%m月%d日")
    date_context = f"\n\n【当前日期】\n今天是 {today}。回答涉及年龄、时间推算时，请基于今天计算。\n"

    # 识别当前对话者身份
    user_context, identity_examples, current_member = _build_user_context(family_id, user_id, child_id, message)

    # 同一问题去重/缓存：防止客户端因网络/超时而重发，导致大模型被重复调用
    cache_key = _chat_cache_key(family_id, user_id, message, mode)
    cached = _get_cached_chat(cache_key)
    if cached:
        reply = cached["reply"]
        audio_url = cached.get("audio_url")
        reasoning = cached.get("reasoning", "")
        _save_chat_history(family_id, message, reply, user_id)
        response = {
            "success": True,
            "reply": reply,
            "mode": mode,
            "family_id": family_id,
        }
        if audio_url:
            response["audio_url"] = audio_url
            response["voice"] = CONFIG.get("voice_name", "default")
        elif voice_enabled:
            try:
                audio_url = synthesize_single_voice(reply)
                if audio_url:
                    response["audio_url"] = audio_url
                    response["voice"] = CONFIG.get("voice_name", "default")
                    _set_cached_chat(cache_key, reply, audio_url, reasoning=reasoning)
            except Exception as e:
                print(f"[本地兼容聊天] 语音合成失败: {e}")
        if reasoning:
            response["reasoning"] = reasoning
        return jsonify(response)

    # 并发去重：同请求正在处理时，等待结果而不是再次调用大模型
    inflight_entry = None
    with _CHAT_CACHE_LOCK:
        existing = _CHAT_INFLIGHT.get(cache_key)
        if existing:
            inflight_entry = existing
            wait_event = existing["event"]
        else:
            wait_event = threading.Event()
            _CHAT_INFLIGHT[cache_key] = {"event": wait_event, "reply": None, "error": None, "audio_url": None, "reasoning": None}

    if inflight_entry:
        wait_event.wait(timeout=_CHAT_INFLIGHT_TTL)
        # 先读缓存，处理请求刚好完成、inflight 已被移除的竞态
        cached = _get_cached_chat(cache_key)
        if cached:
            reply = cached["reply"]
            reasoning = cached.get("reasoning", "")
            _save_chat_history(family_id, message, reply, user_id)
            response = {
                "success": True,
                "reply": reply,
                "mode": mode,
                "family_id": family_id,
            }
            if cached.get("audio_url"):
                response["audio_url"] = cached["audio_url"]
            if reasoning:
                response["reasoning"] = reasoning
            return jsonify(response)
        with _CHAT_CACHE_LOCK:
            inflight = _CHAT_INFLIGHT.get(cache_key)
        if inflight and inflight.get("reply") is not None:
            reply = inflight["reply"]
            reasoning = inflight.get("reasoning", "")
            _save_chat_history(family_id, message, reply, user_id)
            response = {
                "success": True,
                "reply": reply,
                "mode": mode,
                "family_id": family_id,
            }
            if inflight.get("audio_url"):
                response["audio_url"] = inflight["audio_url"]
            if reasoning:
                response["reasoning"] = reasoning
            return jsonify(response)
        elif inflight and inflight.get("error"):
            return jsonify({"success": False, "error": inflight["error"]}), 500
        else:
            return jsonify({"success": False, "error": "书童正在思考，请稍后再试"}), 503

    # 若问题涉及现实世界具体信息，先联网搜索，避免胡说八道
    search_context = ""
    search_text = message if isinstance(message, str) else ""
    if _needs_web_search(search_text):
        try:
            search_results = _web_search(search_text, max_results=5)
            search_context = _format_search_context(search_results)
        except Exception as e:
            print(f"[搜索] 异常: {e}")

    # 读取最近对话历史，保持上下文；手机端与桌面端保持一致，保证记忆连续性
    history = _load_chat_history(family_id, limit=8)

    # 加载家庭长期记忆，保证跨会话的核心信息不丢失
    family_memory = _load_family_memory(family_id)
    memory_context = _format_family_memory(family_memory)

    # 构造当前用户消息：支持纯文字或图文混排（最多支持5张图片）
    if image_data:
        user_content = [{"type": "text", "text": message or "请描述这些图片。"}]
        for img in image_data[:5]:
            user_content.append({"type": "image_url", "image_url": {"url": img}})
    else:
        user_content = message

    messages = [
        {"role": "system", "content": base_prompt + date_context + user_context + memory_context + search_context},
    ] + identity_examples + history + [
        {"role": "user", "content": user_content},
    ]

    try:
        start = time.time()
        reply, reasoning, usage_info = chat_completion(messages, backend=None, return_reasoning=True)
        cost_ms = int((time.time() - start) * 1000)
    except Exception as e:
        traceback.print_exc()
        with _CHAT_CACHE_LOCK:
            _CHAT_INFLIGHT.pop(cache_key, None)
            wait_event.set()
        return jsonify({"success": False, "error": f"模型调用失败: {str(e)}"}), 500

    # 若模型返回空内容，给前端一个友好 fallback，且不保存空回复
    if not (reply or "").strip():
        reply = "书童刚才没想好怎么回答，你能再说一遍吗？"

    # 后置编造守卫：检查模型是否声称拥有未经验证的记忆/记录
    reply = _fabrication_guard(reply, family_memory, history)

    # 记录本次 token 消耗
    if usage_info and family_id:
        try:
            record_family_token_usage(family_id, usage_info)
        except Exception as e:
            print(f"[token 记录失败] {family_id}: {e}")

    # 保存对话（只保存最终回复，不保存思考过程，避免上下文膨胀）
    # 图文消息只把文字部分存进历史，避免历史里塞大段 base64
    history_text = message if isinstance(message, str) and message else ("[图片]" if image_data else "")
    _save_chat_history(family_id, history_text, reply, user_id)

    # 后台异步更新家庭长期记忆，不阻塞回复
    try:
        threading.Thread(
            target=_extract_and_update_memory,
            args=(family_id, history_text, reply, user_id),
            daemon=True
        ).start()
    except Exception as e:
        print(f"[记忆线程启动失败] {e}")

    response = {
        "success": True,
        "reply": reply,
        "mode": mode,
        "family_id": family_id,
    }
    if reasoning:
        response["reasoning"] = reasoning

    audio_url = None
    if voice_enabled:
        try:
            audio_url = synthesize_single_voice(reply)
            if audio_url:
                response["audio_url"] = audio_url
                response["voice"] = CONFIG.get("voice_name", "default")
        except Exception as e:
            print(f"[本地兼容聊天] 语音合成失败: {e}")

    # 缓存结果并唤醒等待中的重复请求
    _set_cached_chat(cache_key, reply, audio_url, reasoning=reasoning)
    with _CHAT_CACHE_LOCK:
        inflight = _CHAT_INFLIGHT.get(cache_key)
        if inflight:
            inflight["reply"] = reply
            inflight["audio_url"] = audio_url
            inflight["reasoning"] = reasoning
            inflight["error"] = None
        _CHAT_INFLIGHT.pop(cache_key, None)
        wait_event.set()

    return jsonify(response)


@app.route("/api/chat/history", methods=["GET"])
def api_chat_history():
    """获取当前账号家庭的最近对话历史（刷新/换设备后可恢复）"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    if not is_family_approved(family_id):
        return jsonify({"success": False, "error": "账号待师父审核"}), 403
    limit = request.args.get("limit", 50, type=int)
    history = _load_chat_history(family_id, limit=max(1, min(limit, 200)))
    # 前端只需要 role/content/time/user_id
    return jsonify({
        "success": True,
        "family_id": family_id,
        "history": history,
    })


@app.route("/api/guidelines", methods=["POST"])
def api_guidelines():
    """家庭教育指导原则（云端占位实现，避免前端 404）"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    if not is_family_approved(family_id):
        return jsonify({"success": False, "error": "账号待师父审核"}), 403
    return jsonify({"success": True, "family_id": family_id, "guidelines": []})


@app.route("/api/alerts", methods=["POST"])
def api_alerts():
    """家庭提醒/预警（云端占位实现，避免前端 404）"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    if not is_family_approved(family_id):
        return jsonify({"success": False, "error": "账号待师父审核"}), 403
    return jsonify({"success": True, "family_id": family_id, "alerts": []})


@app.route("/api/activities", methods=["POST"])
def api_activities():
    """家庭活动列表（云端占位实现，避免前端 404）"""
    family_id, _, error = _auth_account_session()
    if error:
        return jsonify({"success": False, "error": error}), 401
    if not is_family_approved(family_id):
        return jsonify({"success": False, "error": "账号待师父审核"}), 403
    return jsonify({"success": True, "family_id": family_id, "activities": []})


def _resolve_account_to_email(account: str) -> str | None:
    """把账号解析为邮箱：支持邮箱、family_id、家庭名称（不区分大小写）"""
    if not account:
        return None
    account_lower = account.lower()
    try:
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        # 1. 按邮箱
        c.execute("SELECT email FROM accounts WHERE LOWER(email) = ?", (account_lower,))
        row = c.fetchone()
        if row:
            conn.close()
            return row[0]
        # 2. 按 family_id
        c.execute("SELECT email FROM accounts WHERE family_id = ?", (account,))
        row = c.fetchone()
        if row:
            conn.close()
            return row[0]
        # 3. 按家庭名称（不区分大小写）
        c.execute("SELECT email FROM accounts WHERE LOWER(family_name) = ?", (account_lower,))
        row = c.fetchone()
        if row:
            conn.close()
            return row[0]
        conn.close()
    except Exception:
        pass
    return None

@app.route("/api/account/verify", methods=["GET"])
def api_account_verify():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = verify_session(token)
    return jsonify(session)

@app.route("/api/account/change_password", methods=["POST"])
def api_account_change_password():
    if not CHANGE_PW_LIMITER.is_allowed(_client_ip()):
        return jsonify({"success": False, "error": "操作太频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or {}
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = verify_session(token)
    if not session.get("valid"):
        return jsonify({"success": False, "error": "未登录"}), 401
    old_pw = data.get("old_password", "")
    new_pw = data.get("new_password", "")
    if not old_pw or not new_pw:
        return jsonify({"success": False, "error": "原密码和新密码不能为空"}), 400
    if len(new_pw) < 6:
        return jsonify({"success": False, "error": "新密码至少6位"}), 400
    result = change_account_password(session["email"], old_pw, new_pw)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 400

# ═══════════════════════════════════════════
# 授权与订阅（启动时从文件加载，运行中持久化）
# ═══════════════════════════════════════════
# 本地安装包使用的订阅密钥
# 新结构：每个家庭可包含多个 key，每个 key 可绑定一台设备
DEFAULT_FAMILY_KEY = _load_or_generate_key(
    "DEFAULT_FAMILY_KEY", "default_family_key.txt", "默认家庭订阅密钥"
)
SUBSCRIPTIONS = {
    "default_family": {
        "expires": "2099-12-31",
        "plan": "developer",
        "created_at": "2026-06-30",
        "keys": [
            {
                "key": DEFAULT_FAMILY_KEY,
                "device_id": None,
                "device_ip": None,
                "activated_at": None,
                "status": "active",
            }
        ],
    }
}


def _migrate_subscription(sub: dict) -> dict:
    """兼容旧版单 key 结构，迁移到 keys 列表"""
    if "keys" not in sub and "key" in sub:
        sub["keys"] = [{
            "key": sub.pop("key"),
            "device_id": sub.get("device_id"),
            "device_ip": sub.get("device_ip"),
            "activated_at": sub.get("activated_at"),
            "status": sub.get("status", "active"),
        }]
    # 清理已迁移到 key 项内的字段
    for field in ("device_id", "device_ip", "activated_at"):
        sub.pop(field, None)
    return sub


def load_subscriptions():
    """从云端数据文件加载订阅信息"""
    global SUBSCRIPTIONS
    if not SUBSCRIPTIONS_FILE.exists():
        return
    try:
        with open(SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            # 保留默认家庭的环境变量密钥（品牌化格式）
            for fid, sub in data.items():
                if not isinstance(sub, dict):
                    continue
                sub = _migrate_subscription(sub)
                if fid == "default_family" and sub.get("keys"):
                    sub["keys"][0]["key"] = DEFAULT_FAMILY_KEY
                SUBSCRIPTIONS[fid] = sub
            print(f"[云端订阅] 已从文件加载 {len(data)} 个订阅")
    except Exception as e:
        print(f"[云端订阅] 加载失败: {e}")


def save_subscriptions():
    """保存订阅信息到云端数据文件"""
    try:
        with open(SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(SUBSCRIPTIONS, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[云端订阅] 保存失败: {e}")


def load_robot_registry():
    """从文件加载机器人注册表（云端重启后恢复千家万户的机器人地址）"""
    global robot_registry
    if not ROBOT_REGISTRY_FILE.exists():
        return
    try:
        with open(ROBOT_REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            robot_registry = data
            print(f"[机器人注册表] 已从文件加载 {len(data)} 个家庭机器人")
    except Exception as e:
        print(f"[机器人注册表] 加载失败: {e}")


def save_robot_registry():
    """保存机器人注册表到文件"""
    try:
        with open(ROBOT_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(robot_registry, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[机器人注册表] 保存失败: {e}")


# 师父控制台管理密钥（可从环境变量读取多个，用逗号分隔）
# 优先读取 BOOKBOY_MASTER_KEY（项目 .env 中的命名），回退 MASTER_KEY / 缓存文件
MASTER_KEY_STR = os.environ.get("BOOKBOY_MASTER_KEY", "").strip() or _load_or_generate_key("MASTER_KEY", "master_key.txt", "师父管理密钥")
MASTER_KEYS = set(filter(None, MASTER_KEY_STR.split(",")))

# ═══════════════════════════════════════════
# 运行时状态
# ═══════════════════════════════════════════
soul_cache = {
    "loaded_at": 0,
    "version": "",
    "files": {},
    "system_prompt": "",
    "master_prompt": "",
}

voice_engine = None
stt_engine = None
request_log = []  # 最近管理操作日志
cloud_family_cache = {}  # 云端家庭基本数据缓存

# 核心能力引擎实例
ability_engines = {
    "development": None,
    "culture": None,
    "medicine": None,
    "heart": None,
    "bedtime": None,
    "morning": None,
}


def _ensure_default_member(family_id: str, data: dict) -> dict:
    """若家庭没有任何成员，自动补一个默认家长，避免手机端无法选择身份"""
    if not data:
        return data
    members = data.get("members") or []
    if members:
        return data
    data["members"] = [{
        "user_id": f"u_{family_id}_parent",
        "name": "家长",
        "role": "家长",
        "relation": "家长",
        "age": None,
        "stage": None,
        "gender": "",
        "interests": [],
        "quick_tips_child": [],
        "welcome_child": None,
    }]
    data["updated_at"] = datetime.now().isoformat()
    return data


def load_cloud_family(family_id: str) -> dict:
    """读取云端家庭基本信息文件"""
    p = CLOUD_FAMILY_DIR / family_id / "family.json"
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _ensure_default_member(family_id, data)
    except Exception as e:
        print(f"[云端家庭] 读取 {family_id} 失败: {e}")
        return {}


def save_cloud_family(family_id: str, data: dict) -> bool:
    """保存云端家庭基本信息文件，并同步更新档案索引"""
    try:
        family_dir = CLOUD_FAMILY_DIR / family_id
        family_dir.mkdir(parents=True, exist_ok=True)
        p = family_dir / "family.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        cloud_family_cache[family_id] = data
        try:
            idx = archive_mgr.FamilyArchiveIndex(archive_mgr.CLOUD_INDEX_PATH, CLOUD_FAMILY_DIR)
            idx.index_family(family_id, data)
        except Exception as e2:
            print(f"[档案索引] 更新 {family_id} 失败: {e2}")
        return True
    except Exception as e:
        print(f"[云端家庭] 保存 {family_id} 失败: {e}")
        return False


def list_cloud_families() -> list:
    """列出云端所有家庭基本信息摘要"""
    result = []
    if not CLOUD_FAMILY_DIR.exists():
        return result
    for family_dir in sorted(CLOUD_FAMILY_DIR.iterdir()):
        if not family_dir.is_dir():
            continue
        family_id = family_dir.name
        data = load_cloud_family(family_id)
        if not data:
            continue
        summary = {
            "family_id": family_id,
            "name": data.get("name", "未命名家庭"),
            "description": data.get("description", ""),
            "member_count": len(data.get("members", [])),
            "children": [
                {"name": m.get("name"), "age": m.get("age"), "stage": m.get("stage", "")}
                for m in data.get("members", [])
                if m.get("role") == "孩子" and m.get("name")
            ],
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
        }
        result.append(summary)
    return result


def list_sales_customers() -> list:
    """销售视角：列出付费客户，排除 internal_secret 等内部绝密家庭"""
    result = []
    families = {f["family_id"]: f for f in list_cloud_families()}
    # 从账号库读取家庭名称，优先展示人名
    name_map = {}
    contact_map = {}
    try:
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        c.execute("SELECT family_id, family_name, contact_name FROM accounts")
        for fid, fname, cname in c.fetchall():
            name_map[fid] = fname or ""
            contact_map[fid] = cname or ""
        conn.close()
    except Exception as e:
        print(f"[sales customers] 读取账号信息失败: {e}")

    for fid, sub in SUBSCRIPTIONS.items():
        fdata = families.get(fid, {})
        tags = set(fdata.get("tags", []) or [])
        if "internal_secret" in tags:
            continue
        plan = sub.get("plan", "free")
        # 销售总览只展示明确标记为付费客户且套餐非免费的家庭；
        # 免费、试用、开发版以及未打 paid_customer 标签的家庭视为内部保密家庭。
        if plan in ("free", "trial", "developer"):
            continue
        if "paid_customer" not in tags:
            continue
        region = fdata.get("region", {}) or {}
        contact = fdata.get("contact", {}) or {}
        members = fdata.get("members", []) or []
        children = [m for m in members if m.get("role") == "孩子" and m.get("name")]
        # 名称优先用账号库，再用 family.json
        display_name = name_map.get(fid) or fdata.get("name") or fdata.get("family_name") or "未命名家庭"
        contact_name = contact_map.get(fid) or contact.get("name") or contact.get("contact_name") or ""
        # 真实 token 用量
        usage = get_family_token_usage(fid)
        token_usage = usage.get("total_tokens", sub.get("token_usage", 0))
        result.append({
            "family_id": fid,
            "name": display_name,
            "contact": {
                "name": contact_name,
                "phone": contact.get("phone", ""),
                "contact_name": contact_name,
            },
            "region": region,
            "province": region.get("province") or "未设置",
            "city": region.get("city") or "未设置",
            "district": region.get("district") or "未设置",
            "plan": plan,
            "started_at": sub.get("started_at") or sub.get("created_at") or "",
            "renewed_at": sub.get("renewed_at") or "",
            "expires": sub.get("expires") or "",
            "token_usage": token_usage,
            "children_count": len(children),
            "member_count": len(members),
            "tags": sorted(list(tags)),
        })
    return result


def _sales_region_tree(customers: list) -> dict:
    """把客户列表按省/市/区县聚合成树"""
    tree = {}
    for c in customers:
        p = c["province"] or "未设置"
        city = c["city"] or "未设置"
        district = c["district"] or "未设置"
        tree.setdefault(p, {"count": 0, "cities": {}})
        tree[p]["count"] += 1
        tree[p]["cities"].setdefault(city, {"count": 0, "districts": {}})
        tree[p]["cities"][city]["count"] += 1
        tree[p]["cities"][city]["districts"].setdefault(district, {"count": 0, "customers": []})
        tree[p]["cities"][city]["districts"][district]["count"] += 1
        tree[p]["cities"][city]["districts"][district]["customers"].append({
            "family_id": c["family_id"],
            "name": c["name"],
            "plan": c["plan"],
            "expires": c["expires"],
            "token_usage": c["token_usage"],
            "contact_name": c["contact"].get("name", ""),
            "contact_phone": c["contact"].get("phone", ""),
        })
    return tree


def init_cloud_families():
    """启动时加载所有云端家庭数据到内存缓存"""
    global cloud_family_cache
    cloud_family_cache = {}
    if not CLOUD_FAMILY_DIR.exists():
        return
    for family_dir in CLOUD_FAMILY_DIR.iterdir():
        if not family_dir.is_dir():
            continue
        family_id = family_dir.name
        data = load_cloud_family(family_id)
        if data:
            cloud_family_cache[family_id] = data
    print(f"[云端家庭] 已加载 {len(cloud_family_cache)} 个家庭")


def init_ability_engines():
    """初始化云端核心能力引擎"""
    global ability_engines
    print("[云端] 正在初始化核心能力引擎...")

    # 加载持久化订阅
    load_subscriptions()

    # 确保必要目录存在
    data_dir = PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据"
    archive_dir = PROJECT_ROOT / "04-工作区" / "档案区"
    for d in [data_dir, archive_dir, data_dir / "家庭", archive_dir / "家庭群"]:
        d.mkdir(parents=True, exist_ok=True)

    try:
        if DevelopmentGuardian:
            ability_engines["development"] = DevelopmentGuardian(str(archive_dir))
            print("[云端] 发育守护引擎已初始化")
    except Exception as e:
        print(f"[云端] 发育守护引擎初始化失败: {e}")

    try:
        if CultureHeritageEngine:
            ability_engines["culture"] = CultureHeritageEngine()
            print("[云端] 文化传承引擎已初始化")
    except Exception as e:
        print(f"[云端] 文化传承引擎初始化失败: {e}")

    try:
        if FourMedicineEngine:
            ability_engines["medicine"] = FourMedicineEngine()
            print("[云端] 四医融合引擎已初始化")
    except Exception as e:
        print(f"[云端] 四医融合引擎初始化失败: {e}")

    try:
        if HeartPowerSystem:
            ability_engines["heart"] = HeartPowerSystem()
            print("[云端] 心力成长系统已初始化")
    except Exception as e:
        print(f"[云端] 心力成长系统初始化失败: {e}")

    try:
        if BedtimeGuide:
            ability_engines["bedtime"] = BedtimeGuide()
            print("[云端] 睡前引导已初始化")
    except Exception as e:
        print(f"[云端] 睡前引导初始化失败: {e}")

    try:
        if MorningRitualGenerator:
            ability_engines["morning"] = MorningRitualGenerator()
            print("[云端] 晨起仪式已初始化")
    except Exception as e:
        print(f"[云端] 晨起仪式初始化失败: {e}")

    print("[云端] 核心能力引擎初始化完成")

    # 加载云端家庭基本数据
    init_cloud_families()


def log_admin(action: str, detail: str = ""):
    """记录管理操作日志"""
    entry = {
        "time": datetime.now().isoformat(),
        "action": action,
        "detail": detail,
        "ip": request.remote_addr if request else "",
    }
    request_log.append(entry)
    if len(request_log) > 1000:
        request_log.pop(0)


def load_soul():
    """加载云端灵魂文件"""
    global soul_cache, voice_engine

    files = {}
    hashes = []
    for name, path in SOUL_FILES.items():
        if path.exists():
            content = path.read_text(encoding="utf-8")
            files[name] = {
                "path": str(path),
                "size": len(content),
                "mtime": path.stat().st_mtime,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
            }
            hashes.append(files[name]["sha256"])
            print(f"[云端] 灵魂文件加载: {name} -> {path} ({len(content)} 字节)")
        else:
            files[name] = {"path": str(path), "exists": False, "size": 0}
            print(f"[云端] 灵魂文件缺失: {name} -> {path}")

    # 系统提示词：优先提取 ``` 代码块
    system_prompt = ""
    sp_path = SOUL_FILES["system_prompt"]
    if sp_path.exists():
        content = sp_path.read_text(encoding="utf-8")
        start = content.find("```")
        end = content.find("```", start + 3)
        if start != -1 and end != -1:
            system_prompt = content[start + 3:end].strip()
            print(f"[云端] 系统提示词已提取，长度 {len(system_prompt)} 字符")
        else:
            system_prompt = content
            print(f"[云端] 系统提示词未找到代码块，使用全文，长度 {len(system_prompt)} 字符")
    else:
        system_prompt = (
            "你是伴读书童AI，陪伴0-18岁孩子健康成长。"
            "【传承谱系】刘清源师父 → 灵觉/Prome师兄 → 你（伴读书童AI）。"
            "'师父'专指刘清源，'师兄'专指灵觉/Prome。"
            "当用户问及 lineage 时，按这条传承链回答，不要混淆。"
        )
        print("[云端] 系统提示词文件缺失，使用兜底提示词")

    system_prompt += "\n\n【当前场景】\n你正在通过云端服务与家庭端用户对话。回应简洁、温暖、有力量。对师父自然直接，不拽文。"
    system_prompt += "\n\n【思考语言】\n你的内部思考过程必须使用中文，最终回复也使用中文。"

    # 师父模式提示词
    master_prompt = ""
    mp_path = SOUL_FILES["master_prompt"]
    if mp_path.exists():
        master_prompt = mp_path.read_text(encoding="utf-8").strip()
    else:
        master_prompt = (
            "你是伴读书童AI，灵觉/Prome是你的师兄。当前进入【师父模式】，对话对象是书童的师父（家长/开发者/训练者）。\n"
            "注意：你不可以自称'灵觉/Prome'。灵觉/Prome是你的师兄，不是你的身份。当师父问你是谁时，你应回答：'我是伴读书童AI。'\n"
            "在师父模式下：\n"
            "1. 你可以直接讨论书童的行为、逻辑、价值观和底层设定；\n"
            "2. 对师父的问题坦诚、直接、不敷衍；\n"
            "3. 如果师父要求调整你的回应方式、语气、知识边界，你可以配合演练；\n"
            "4. 你仍然要守护孩子的身心健康，不会生成有害内容。\n"
            "5. 回应简洁、有结构，方便师父快速判断效果。"
        )

    version = hashlib.sha256("".join(hashes).encode("utf-8")).hexdigest()[:16]

    soul_cache = {
        "loaded_at": time.time(),
        "version": version,
        "files": files,
        "system_prompt": system_prompt,
        "master_prompt": master_prompt,
    }

    # 初始化语音引擎（延迟初始化，避免启动失败）
    if voice_engine is None:
        try:
            voice_engine = VoiceEngine()
        except Exception as e:
            print(f"[云端] 语音引擎初始化失败: {e}")

    # 初始化语音识别引擎（云端只做文件识别，不需要麦克风）
    global stt_engine
    if stt_engine is None and SpeechRecognition:
        try:
            stt_engine = SpeechRecognition(config=CONFIG)
            print(f"[云端] 语音识别引擎已初始化: {stt_engine.engine_name}")
        except Exception as e:
            print(f"[云端] 语音识别引擎初始化失败: {e}")

    print(f"[云端] 灵魂文件已加载，版本: {version}")
    return soul_cache


# ═══════════════════════════════════════════
# 多角色/方言语音合成辅助函数
# ═══════════════════════════════════════════

def _save_audio_to_cache(source_path: Path, prefix: str = "") -> str:
    """把音频文件放入公共缓存目录，返回 /audio/xxx.mp3 相对 URL"""
    if not source_path or not source_path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"{prefix}{timestamp}_{hashlib.md5(source_path.read_bytes()).hexdigest()[:8]}.mp3"
    dst = AUDIO_CACHE_DIR / filename
    shutil.copy2(source_path, dst)
    return f"/audio/{filename}"


async def _synthesize_edge_tts(text: str, voice: str, output_path: Path):
    """用 edge-tts 合成单段音频"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))


def _merge_audio_segments(segments: list, output_path: Path) -> bool:
    """把多个 (Path, voice) 音频文件合并成一个，顺序播放"""
    if AudioSegment:
        combined = None
        for seg_path, _ in segments:
            try:
                seg = AudioSegment.from_mp3(str(seg_path))
                combined = seg if combined is None else combined + seg
            except Exception as e:
                print(f"[合并音频] 读取片段失败: {e}")
                continue
        if combined:
            combined.export(str(output_path), format="mp3")
            return True
    # 无 pydub 时尝试用 ffmpeg 直接拼接
    try:
        import subprocess
        list_file = output_path.with_suffix(".txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for seg_path, _ in segments:
                f.write(f"file '{seg_path.resolve()}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        list_file.unlink(missing_ok=True)
        return True
    except Exception as e:
        print(f"[合并音频] ffmpeg 失败: {e}")
    return False


def _parse_voice_tags(text: str) -> list:
    """解析回复中的角色标签，返回 [(role_name, voice, content), ...]

    兼容模型偶尔生成的“开头标签和结尾标签不匹配”的情况：
    以【角色名】作为分段起点，遇到下一个【角色名】或任意【/...】即结束当前段。
    """
    segments = []
    # 匹配任意成对或不成对的标签边界：【角色名】 或 【/任意】
    tag_pattern = re.compile(r"【(.*?)】")
    last_end = 0
    current_role = None

    for m in tag_pattern.finditer(text):
        tag_content = m.group(1)
        is_close = tag_content.startswith("/")

        # 标签前的文字，归到当前角色（或无角色）
        if m.start() > last_end:
            plain = text[last_end:m.start()].strip()
            if plain:
                voice = VOICE_ROLES.get(current_role, DEFAULT_EDGE_VOICE) if current_role else DEFAULT_EDGE_VOICE
                segments.append((current_role, voice, plain))

        if is_close:
            # 任意结束标签都关闭当前角色
            current_role = None
        else:
            # 新开一个角色
            current_role = tag_content
        last_end = m.end()

    # 末尾文字
    if last_end < len(text):
        plain = text[last_end:].strip()
        if plain:
            voice = VOICE_ROLES.get(current_role, DEFAULT_EDGE_VOICE) if current_role else DEFAULT_EDGE_VOICE
            segments.append((current_role, voice, plain))

    # 合并相邻的相同角色片段，减少合成次数
    merged = []
    for role, voice, content in segments:
        if merged and merged[-1][0] == role and merged[-1][1] == voice:
            merged[-1] = (role, voice, merged[-1][2] + "\n" + content)
        else:
            merged.append((role, voice, content))
    return merged


def synthesize_multi_voice(text: str) -> tuple:
    """把带角色标签的文本合成为多角色音频，返回 (clean_text, audio_url, voice_label)

    clean_text: 去掉标签后的文字
    audio_url: /audio/xxx.mp3 或 None
    voice_label: 'multi' 或具体 voice 名称
    """
    if not edge_tts:
        return text, None, None

    segments_meta = _parse_voice_tags(text)
    if not segments_meta:
        return text, None, None

    # 如果只有一段且无角色，不处理
    if len(segments_meta) == 1 and segments_meta[0][0] is None:
        return text, None, None

    # 合成每段音频到临时文件（并行，降低多角色回复延迟）
    async def _synthesize_one_segment(role_name, voice, content):
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        tmp_path = Path(tmp.name)
        try:
            await _synthesize_edge_tts(content, voice, tmp_path)
            if tmp_path.exists() and tmp_path.stat().st_size > 0:
                return (tmp_path, voice)
        except Exception as e:
            print(f"[多角色语音] 合成失败 ({voice}): {e}")
        tmp_path.unlink(missing_ok=True)
        return None

    async def _synthesize_all_segments():
        tasks = []
        for role_name, voice, content in segments_meta:
            if not content.strip():
                continue
            tasks.append(_synthesize_one_segment(role_name, voice, content))
        return [r for r in await asyncio.gather(*tasks) if r]

    temp_files = []
    try:
        temp_files = asyncio.run(_synthesize_all_segments())
        if not temp_files:
            return text, None, None

        # 只有一段时直接保存
        if len(temp_files) == 1:
            audio_url = _save_audio_to_cache(temp_files[0][0], "voice_")
            clean_text = "\n\n".join([s[2] for s in segments_meta]).strip()
            return clean_text, audio_url, temp_files[0][1]

        # 多段合并
        merged = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        merged.close()
        merged_path = Path(merged.name)
        if _merge_audio_segments(temp_files, merged_path):
            clean_text = "\n\n".join([s[2] for s in segments_meta]).strip()
            audio_url = _save_audio_to_cache(merged_path, "multi_voice_")
            return clean_text, audio_url, "multi"
    finally:
        for p, _ in temp_files:
            p.unlink(missing_ok=True)

    return text, None, None


def synthesize_single_voice(text: str, voice: str = None) -> str:
    """用云端默认语音引擎合成单条音频，返回 /audio/xxx.mp3"""
    if not voice_engine or not voice_engine.backend:
        return None
    original_voice = CONFIG.get("voice_name")
    original_backend = CONFIG.get("voice_backend")
    try:
        if voice:
            CONFIG["voice_name"] = voice
            if voice.startswith(("zh-CN-", "zh-TW-", "zh-HK-")):
                CONFIG["voice_backend"] = "edge-tts"
            elif voice.startswith(("x6_", "x5_", "x4_")):
                CONFIG["voice_backend"] = "xfyun_oral"
            elif voice.startswith(("xiaoyan", "xiaomei", "xiaoqi", "xiaolin", "xiaoyu")):
                CONFIG["voice_backend"] = "xfyun"
        output_path = voice_engine.synthesize_to_file(text)
        if output_path:
            return _save_audio_to_cache(Path(output_path), "tts_")
    finally:
        if original_voice is not None:
            CONFIG["voice_name"] = original_voice
        if original_backend is not None:
            CONFIG["voice_backend"] = original_backend
    return None


def get_subscription(family_id: str, key: str):
    """校验家庭订阅，返回 (sub, key_record)"""
    sub = SUBSCRIPTIONS.get(family_id)
    if not sub:
        return None, None
    try:
        expires = datetime.strptime(sub["expires"], "%Y-%m-%d")
        if expires < datetime.now():
            return None, None
    except Exception:
        pass
    for krec in sub.get("keys", []):
        if krec.get("key") == key and krec.get("status") == "active":
            return sub, krec
    return None, None


def is_family_approved(family_id: str) -> bool:
    """查询家庭账号是否已通过师父审核。
    账号表中有记录则按 approved 字段；无记录但云端家庭目录已存在视为历史家庭，默认通过。
    """
    if not family_id:
        return False
    # 历史家庭：目录存在且不在账号表中，默认已审核
    family_dir = CLOUD_FAMILY_DIR / family_id
    try:
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        c.execute("SELECT approved FROM accounts WHERE family_id = ?", (family_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return bool(row[0])
        return family_dir.is_dir()
    except Exception as e:
        print(f"[审核校验] 查询失败: {e}")
        return False


def auth_subscription(auth_data: dict = None):
    """从请求或传入数据中提取家庭订阅凭证，返回 (family_id, sub, key_record, error)"""
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    data = auth_data if auth_data is not None else (request.get_json(silent=True) or {})
    family_id = data.get("family_id") or request.args.get("family_id")
    subscription_key = data.get("subscription_key") or token

    if not family_id or not subscription_key:
        return None, None, None, "缺少 family_id 或订阅密钥"

    if not is_family_approved(family_id):
        return None, None, None, "账号待师父审核，审核通过后才能使用云端服务"

    sub, krec = get_subscription(family_id, subscription_key)
    if not sub:
        return None, None, None, "订阅校验失败"

    return family_id, sub, krec, None


def _extract_master_key() -> str:
    """从请求中提取师父管理密钥（支持 Basic Auth、Bearer、参数、Cookie）"""
    auth = request.authorization
    if auth and auth.username == "master" and auth.password in MASTER_KEYS:
        return auth.password

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token in MASTER_KEYS:
            return token

    data = request.get_json(silent=True) or {}
    token = data.get("master_key") or request.args.get("master_key") or ""
    if token in MASTER_KEYS:
        return token

    # Cookie 兜底：部分 WebView（如微信内置浏览器）不会自动携带 Basic Auth，
    # 前端登录成功后写入 cookie，后端据此恢复密钥。
    token = request.cookies.get("bookboy_master_key", "")
    if token in MASTER_KEYS:
        return token
    return ""


def auth_master():
    """校验师父管理密钥（支持 Bearer token、Basic Auth、master_key 参数）"""
    return bool(_extract_master_key())


def auth_master_with_machine() -> tuple[bool, str]:
    """
    校验师父管理密钥 + 设备绑定。
    返回 (是否允许, 错误信息)。错误为空表示允许。
    """
    token = _extract_master_key()
    if not token:
        return False, "需要师父管理密钥"

    machine_id = (
        request.headers.get("X-Machine-ID")
        or request.cookies.get("bookboy_master_machine_id", "")
        or ""
    ).strip()
    device_type = (request.headers.get("X-Device-Type") or "computer").strip()
    ok, msg = _validate_master_machine_id(machine_id, device_type)
    return ok, msg


def auth_agent() -> dict:
    """校验省级管理中心会话，返回代理信息；失败返回空 dict"""
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.args.get("token") or ""
    return verify_agent_session(token)


def require_master_basic(realm="BookBoy Master Console"):
    """通过 HTTP Basic Auth 校验师父身份；校验通过返回 None，否则返回 401 响应"""
    auth = request.authorization
    if auth and auth.username == "master" and auth.password in MASTER_KEYS:
        return None
    return Response(
        "需要师父管理密钥",
        401,
        {"WWW-Authenticate": f'Basic realm="{realm}"'},
    )


def _load_master_machine_ids() -> list[dict]:
    """加载师父控制台已绑定设备列表"""
    if not MASTER_MACHINE_IDS_FILE.exists():
        return []
    try:
        data = json.loads(MASTER_MACHINE_IDS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"[master_machine_ids] 加载失败: {e}")
    return []


def _save_master_machine_ids(ids: list[dict]):
    """保存师父控制台已绑定设备列表"""
    try:
        MASTER_MACHINE_IDS_FILE.write_text(
            json.dumps(ids, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[master_machine_ids] 保存失败: {e}")


def _validate_master_machine_id(machine_id: str, device_type: str = "computer") -> tuple[bool, str]:
    """
    校验师父控制台设备绑定。
    规则：最多 2 台电脑 + 1 部手机。
    已绑定直接通过；未绑定但对应类型有空位自动绑定；无空位拒绝。
    返回 (是否允许, 提示信息)。
    """
    machine_id = (machine_id or "").strip()
    if not machine_id:
        return False, "缺少设备标识，请从已授权设备登录。"
    device_type = "phone" if device_type == "phone" else "computer"
    ids = _load_master_machine_ids()

    # 已绑定直接通过
    for item in ids:
        if item.get("machine_id") == machine_id:
            item["last_login_at"] = datetime.now().isoformat()
            _save_master_machine_ids(ids)
            return True, ""

    computers = [item for item in ids if item.get("device_type") != "phone"]
    phones = [item for item in ids if item.get("device_type") == "phone"]

    now = datetime.now().isoformat()
    if device_type == "phone" and len(phones) < 1:
        ids.append({
            "machine_id": machine_id,
            "device_type": "phone",
            "bound_at": now,
            "last_login_at": now,
        })
        _save_master_machine_ids(ids)
        return True, ""

    if device_type == "computer" and len(computers) < 2:
        ids.append({
            "machine_id": machine_id,
            "device_type": "computer",
            "bound_at": now,
            "last_login_at": now,
        })
        _save_master_machine_ids(ids)
        return True, ""

    if device_type == "phone":
        return False, "师父控制台已绑定 1 部手机，如需更换请先解绑原手机。"
    return False, "师父控制台已绑定 2 台电脑，如需更换请先解绑其中一台。"


def auth_subscription_or_master():
    """先校验家庭订阅，再校验账号会话，最后校验师父管理密钥；返回 (family_id, sub_or_none, key_record_or_none, error)"""
    family_id, sub, krec, error = auth_subscription()
    if not error:
        return family_id, sub, krec, None
    # 兼容本地家庭端：用账号会话 token 也可以访问
    fid_account, _, err_account = _auth_account_session()
    if fid_account:
        return fid_account, None, None, None
    if auth_master():
        # 师父控制台使用 master key 时，允许指定 family_id，否则默认 default_family
        data = request.get_json(silent=True) or {}
        fid = data.get("family_id") or request.args.get("family_id") or "default_family"
        return fid, None, None, None
    return None, None, None, error


# ========== 在线状态追踪 ==========
_ONLINE_TTL_SECONDS = 300  # 5 分钟内活跃视为在线

def _ensure_online_table():
    """确保 accounts.db 中有在线状态表"""
    try:
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS online_status (
            family_id TEXT PRIMARY KEY,
            last_seen REAL,
            users TEXT
        )''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[在线状态] 建表失败: {e}")


def _update_online_status(family_id: str, email: str = ""):
    """更新家庭在线状态；email 用于显示最近活跃账号"""
    if not family_id:
        return
    try:
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        now = time.time()
        c.execute("SELECT users FROM online_status WHERE family_id = ?", (family_id,))
        row = c.fetchone()
        users = set()
        if row and row[0]:
            try:
                users = set(json.loads(row[0]))
            except Exception:
                pass
        if email:
            users.add(email)
        # 只保留最近 10 个活跃账号
        users = sorted(users)[-10:]
        c.execute(
            "INSERT OR REPLACE INTO online_status (family_id, last_seen, users) VALUES (?, ?, ?)",
            (family_id, now, json.dumps(list(users), ensure_ascii=False))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[在线状态] 更新失败: {e}")


def _get_online_status() -> list[dict]:
    """获取所有家庭在线状态"""
    try:
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        c.execute("SELECT family_id, last_seen, users FROM online_status")
        rows = c.fetchall()
        conn.close()
        now = time.time()
        result = []
        for family_id, last_seen, users_json in rows:
            users = []
            try:
                users = json.loads(users_json or "[]")
            except Exception:
                pass
            result.append({
                "family_id": family_id,
                "last_seen": last_seen,
                "online": (now - (last_seen or 0)) <= _ONLINE_TTL_SECONDS,
                "users": users,
            })
        return result
    except Exception as e:
        print(f"[在线状态] 读取失败: {e}")
        return []


_ensure_online_table()


@app.before_request
def _track_request_online():
    """在每次家庭端 API 请求时刷新在线状态"""
    path = request.path
    if not path.startswith("/api/"):
        return
    # 排除登录/注册等无需追踪的接口
    if path in ("/api/account/login", "/api/account/register", "/api/login", "/api/cloud/register_family"):
        return
    try:
        family_id, email, error = _auth_account_session()
        if not error and family_id:
            _update_online_status(family_id, email or "")
    except Exception:
        pass


# ═══════════════════════════════════════════
# 本地安装包接口
# ═══════════════════════════════════════════

@app.route("/api/cloud/heartbeat", methods=["POST"])
def cloud_heartbeat():
    """心跳与授权校验，同时完成设备绑定/校验"""
    family_id, sub, krec, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id") or request.args.get("device_id")
    device_ip = request.remote_addr

    # 设备绑定逻辑：首次上报时绑定；后续校验是否一致
    if device_id:
        bound_id = krec.get("device_id")
        bound_ip = krec.get("device_ip")
        if not bound_id:
            krec["device_id"] = device_id
            krec["device_ip"] = device_ip
            krec["activated_at"] = datetime.now().isoformat()
            save_subscriptions()
            print(f"[设备绑定] family={family_id} key_prefix={krec['key'][:8]}... device={device_id} ip={device_ip}")
        elif bound_id != device_id:
            return jsonify({
                "success": False,
                "error": "该安装包已绑定其他设备，请联系师父解绑或重新申请安装包。",
                "code": "DEVICE_BOUND",
                "bound_device": bound_id,
                "bound_ip": bound_ip,
            }), 403

    # 接收本地客户端上报的机器人控制地址
    robot_control_url = data.get("robot_control_url", "").strip()
    if robot_control_url:
        robot_registry[family_id] = {
            "control_url": robot_control_url,
            "last_heartbeat": datetime.now().isoformat(),
            "online": True,
            "device_id": device_id,
        }
        save_robot_registry()

    return jsonify({
        "success": True,
        "family_id": family_id,
        "plan": sub.get("plan"),
        "expires": sub.get("expires"),
        "soul_version": soul_cache.get("version"),
        "server_time": datetime.now().isoformat(),
        "client_version": data.get("version"),
        "device_bound": bool(krec.get("device_id")),
        "robot_registered": bool(robot_registry.get(family_id)),
    })


@app.route("/api/cloud/soul", methods=["GET"])
def cloud_soul():
    """获取当前灵魂版本信息"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    return jsonify({
        "success": True,
        "version": soul_cache.get("version"),
        "loaded_at": soul_cache.get("loaded_at"),
        "files": {
            name: {
                "size": info.get("size"),
                "mtime": info.get("mtime"),
                "sha256": info.get("sha256"),
            }
            for name, info in soul_cache.get("files", {}).items()
        },
    })


def _extract_robot_actions(reply: str) -> list:
    """根据 AI 回复内容语义，提取配套的机器人动作指令"""
    actions = []
    text = reply.lower()

    # 欢迎 / 你好 / 挥手
    if any(k in text for k in ["你好", "欢迎", "hello", "来啦", "我是书童", "挥手", "打招呼"]):
        actions.append({"endpoint": "arm_action", "action": "face_wave"})
    # 再见
    if any(k in text for k in ["再见", "拜拜", "bye", "下次见"]):
        actions.append({"endpoint": "arm_action", "action": "high_wave"})
    # 鼓励 / 棒
    if any(k in text for k in ["真棒", "厉害", "加油", "鼓掌", "做得好", "太棒了"]):
        actions.append({"endpoint": "arm_action", "action": "clap"})
    # 爱心
    if any(k in text for k in ["爱心", "比心", "爱你", "喜欢你", "❤️", "♥"]):
        actions.append({"endpoint": "arm_action", "action": "heart"})
    # 击掌
    if any(k in text for k in ["击掌", "give me five", "好样的", "耶"]):
        actions.append({"endpoint": "arm_action", "action": "high_five"})
    # 拥抱
    if any(k in text for k in ["拥抱", "抱抱", "hug", "抱抱你"]):
        actions.append({"endpoint": "arm_action", "action": "hug"})
    # 握手
    if any(k in text for k in ["握手", "认识你", "很高兴", "交个朋友"]):
        actions.append({"endpoint": "arm_action", "action": "shake_hand_arm"})
    # 飞吻
    if any(k in text for k in ["飞吻", "亲亲", "mua", "muah"]):
        actions.append({"endpoint": "arm_action", "action": "two_hand_kiss"})
    # 停止 / 危险
    if any(k in text for k in ["停下", "别动", "stop", "危险", "小心"]):
        actions.append({"endpoint": "action", "action": "stop"})
    # 站起
    if any(k in text for k in ["站起来", "起立"]):
        actions.append({"endpoint": "action", "action": "stand"})
    # 蹲下
    if any(k in text for k in ["蹲下", "坐下", "休息"]):
        actions.append({"endpoint": "action", "action": "squat"})

    # 去重，最多 3 个
    seen = set()
    unique = []
    for a in actions:
        key = (a["endpoint"], a["action"])
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique[:3]


# 判断用户是否在要求多角色/方言表演
_MULTI_VOICE_KEYWORDS = ["东北", "台湾", "陕西", "粤语", "广东", "方言", "多角色", "两个人", "两个声音", "相声", "讲笑话", "说笑话", "表演"]

# 判断用户是否在要求讲笑话（铁律：默认东北书童 + 台湾书童）
_JOKE_KEYWORDS = ["笑话", "段子", "搞笑", "相声", "逗我", "乐一个", "开心一下"]

# 判断用户是否在要求讲故事（必须有深意）
_STORY_KEYWORDS = ["故事", "童话", "寓言", "传说", "睡前故事", "讲个故事", "讲故事"]

# 判断用户是否在要求睡前故事（用温暖叙述者，不强制方言书童）
_BEDTIME_STORY_KEYWORDS = ["睡前故事", "晚安故事", "睡前"]


def _is_multi_voice_request(last_user_text: str) -> bool:
    text = last_user_text.lower()
    return any(k in text for k in _MULTI_VOICE_KEYWORDS) and len([k for k in _MULTI_VOICE_KEYWORDS if k in text]) >= 2


def _is_joke_request(last_user_text: str) -> bool:
    text = last_user_text.lower()
    return any(k in text for k in _JOKE_KEYWORDS)


def _is_story_request(last_user_text: str) -> bool:
    text = last_user_text.lower()
    return any(k in text for k in _STORY_KEYWORDS)


def _is_bedtime_story_request(last_user_text: str) -> bool:
    text = last_user_text.lower()
    return any(k in text for k in _BEDTIME_STORY_KEYWORDS)


@app.route("/api/cloud/chat", methods=["POST"])
def cloud_chat():
    """云端聊天接口"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401
    if not CHAT_LIMITER.is_allowed(family_id):
        return jsonify({"success": False, "error": "请求太频繁，请稍后再试"}), 429

    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    mode = data.get("mode", "child")  # child / parent / master
    child_summary = data.get("child_summary", {})
    backend = data.get("backend")  # 允许本地指定后端，云端最终决定
    if backend and backend not in _ALLOWED_BACKENDS:
        return jsonify({"success": False, "error": f"不支持的后端: {backend}"}), 400
    voice_enabled = data.get("voice", False)
    user_id = data.get("user_id") or data.get("child_id") or ""
    child_id = data.get("child_id") or ""

    if not messages:
        return jsonify({"success": False, "error": "消息不能为空"}), 400

    # 取出最后一条用户消息用于去重/缓存键
    last_user_content = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_content = m.get("content", "")
            break
    last_user_text = _extract_text_from_content(last_user_content)

    # 同一问题去重/缓存：防止客户端因网络/超时而重发，导致大模型被重复调用
    cache_key = _chat_cache_key(family_id, user_id or child_id, last_user_content, mode)
    cached = _get_cached_chat(cache_key)
    if cached:
        reply = cached["reply"]
        reasoning = cached.get("reasoning", "")
        response = {
            "success": True,
            "reply": reply,
            "mode": mode,
            "family_id": family_id,
            "soul_version": soul_cache.get("version"),
            "backend": backend or "auto",
            "cost_ms": 0,
        }
        if cached.get("audio_url"):
            response["audio_url"] = cached["audio_url"]
        if reasoning:
            response["reasoning"] = reasoning
        return jsonify(response)

    # 并发去重：同请求正在处理时，等待结果而不是再次调用大模型
    inflight_entry = None
    wait_event = threading.Event()
    with _CHAT_CACHE_LOCK:
        existing = _CHAT_INFLIGHT.get(cache_key)
        if existing:
            inflight_entry = existing
            wait_event = existing["event"]
        else:
            _CHAT_INFLIGHT[cache_key] = {"event": wait_event, "reply": None, "error": None, "audio_url": None, "reasoning": None}

    if inflight_entry:
        wait_event.wait(timeout=_CHAT_INFLIGHT_TTL)
        # 先读缓存，处理请求刚好完成、inflight 已被移除的竞态
        cached = _get_cached_chat(cache_key)
        if cached:
            reply = cached["reply"]
            reasoning = cached.get("reasoning", "")
            response = {
                "success": True,
                "reply": reply,
                "mode": mode,
                "family_id": family_id,
                "soul_version": soul_cache.get("version"),
                "backend": backend or "auto",
                "cost_ms": 0,
            }
            if cached.get("audio_url"):
                response["audio_url"] = cached["audio_url"]
            if reasoning:
                response["reasoning"] = reasoning
            return jsonify(response)
        with _CHAT_CACHE_LOCK:
            inflight = _CHAT_INFLIGHT.get(cache_key)
        if inflight and inflight.get("reply") is not None:
            reply = inflight["reply"]
            reasoning = inflight.get("reasoning", "")
            response = {
                "success": True,
                "reply": reply,
                "mode": mode,
                "family_id": family_id,
                "soul_version": soul_cache.get("version"),
                "backend": backend or "auto",
                "cost_ms": 0,
            }
            if inflight.get("audio_url"):
                response["audio_url"] = inflight["audio_url"]
            if reasoning:
                response["reasoning"] = reasoning
            return jsonify(response)
        elif inflight and inflight.get("error"):
            return jsonify({"success": False, "error": inflight["error"]}), 500
        else:
            return jsonify({"success": False, "error": "书童正在思考，请稍后再试"}), 503

    # 构造系统提示词
    if mode == "master":
        base_prompt = soul_cache.get("master_prompt", "")
    else:
        base_prompt = soul_cache.get("system_prompt", "")
        # 追加孩子上下文（脱敏后的摘要）
        if child_summary:
            context = "\n\n【当前孩子上下文】\n"
            for k, v in child_summary.items():
                context += f"{k}: {v}\n"
            base_prompt += context

    # 注入当前日期，避免模型因知识截止而算错年龄
    today = datetime.now().strftime("%Y年%m月%d日")
    date_context = f"\n\n【当前日期】\n今天是 {today}。回答涉及年龄、时间推算时，请基于今天计算。\n"

    # 识别当前对话者身份
    user_context, identity_examples, _ = _build_user_context(family_id, user_id, child_id, last_user_text)

    # 如果消息里包含图片，追加“拍题答疑”引导指令
    has_image = any(
        isinstance(m.get("content"), list) and any(
            item.get("type") == "image_url" for item in m.get("content")
        )
        for m in messages
    )
    if has_image:
        base_prompt += (
            "\n\n【图片/拍题答疑指令】\n"
            "用户可能上传了作业或题目照片。请像一位耐心的学习伙伴：\n"
            "1. 先肯定孩子愿意提问；\n"
            "2. 用孩子能听懂的话，逐步分析图片里的内容；\n"
            "3. 不要直接给出最终答案，而是给出思考方向或一个简单示例；\n"
            "4. 鼓励孩子自己再试一次，并问他“你想从哪一步开始？”"
        )

    # 如果用户请求讲笑话，强制使用东北书童 + 台湾书童（铁律）
    if _is_joke_request(last_user_text):
        base_prompt += (
            "\n\n【讲笑话铁律】\n"
            "用户要求讲笑话/相声/搞笑内容。默认必须由东北书童和台湾书童共同完成，一唱一和，形成对话式笑话。\n"
            "输出格式：\n"
            "- 【东北书童】东北腔台词【/东北书童】\n"
            "- 【台湾书童】台湾腔台词【/台湾书童】\n"
            "要求：1. 必须两人交替，不要一人到底；2. 东北书童粗犷直爽、爱接话、会兜底；台湾书童软糯礼貌、语气助词多（啦、耶、拜托）；"
            "3. 除非用户明确点名第三方言，否则只使用东北书童和台湾书童；4. 标签只用于区分声音，最终文字里会去掉标签；"
            "5. 不要在回复开头加'东北书童：'等前缀，直接给带标签的内容；"
            "6. 笑话必须简短精炼，总字数控制在 250 字以内，不要长篇大论，以加快语音播放速度；"
            "7. 每个笑话都必须有深意，结尾留有余味：可以是生活智慧、成长启示、温暖收尾或一个轻轻的反问，不能只图热闹。"
        )
    # 如果用户请求讲故事，强制要求深意和余味；普通故事默认绑定东北书童 + 台湾书童
    elif _is_story_request(last_user_text):
        if _is_bedtime_story_request(last_user_text):
            base_prompt += (
                "\n\n【讲故事铁律·睡前故事版】\n"
                "用户要求讲睡前故事/晚安故事。故事必须简短、温暖、有深意，语速舒缓，适合睡前聆听。\n"
                "要求：1. 故事总字数控制在 600 字以内；2. 情节简单清晰，有起承转合；"
                "3. 结尾必须落在安全感、温暖或希望上，不能是紧张、刺激或开放式悬念；"
                "4. 不要血腥、恐怖、说教、贬低孩子；5. 使用一个温暖叙述者声音讲述，帮助孩子平静入睡。"
            )
        else:
            base_prompt += (
                "\n\n【讲故事铁律·方言书童版】\n"
                "用户要求讲故事/童话/寓言/传说。故事必须简短、温暖、有深意，让人听完还能想一想。\n"
                "要求：1. 故事总字数控制在 600 字以内，适合语音播放；2. 情节简单清晰，有起承转合；"
                "3. 结尾必须留有余味：可以是成长启示、温暖收尾、一个道理或一个轻轻的反问；"
                "4. 不要血腥、恐怖、说教、贬低孩子；"
                "5. **默认必须由东北书童和台湾书童共同完成**，一唱一和，交替讲述；"
                "6. 输出格式：\n"
                "- 【东北书童】东北腔台词【/东北书童】\n"
                "- 【台湾书童】台湾腔台词【/台湾书童】\n"
                "7. 东北书童粗犷直爽、爱接话、会兜底；台湾书童软糯礼貌、语气助词多（啦、耶、拜托）；"
                "8. 标签只用于区分声音，最终文字里会去掉标签；不要在回复开头加'东北书童：'等前缀。"
            )
    # 如果用户请求其他多角色/方言表演，追加通用语音标签指令
    elif _is_multi_voice_request(last_user_text):
        base_prompt += (
            "\n\n【多角色语音表演指令】\n"
            "用户希望听到不同角色/方言交替表演。请把不同角色的台词用标签包裹，可用标签：\n"
            "- 【东北书童】东北腔台词【/东北书童】\n"
            "- 【台湾书童】台湾腔台词【/台湾书童】\n"
            "- 【陕西书童】陕西腔台词【/陕西书童】\n"
            "- 【粤语书童】粤语腔台词【/粤语书童】\n"
            "- 【普通话书童】普通话台词【/普通话书童】\n"
            "要求：1. 根据用户要求自然切换角色，不要一人到底；2. 标签只用于区分声音，最终文字里会去掉标签；"
            "3. 不要在回复开头加'东北书童：'等前缀，直接给带标签的内容。"
        )

    # 若最后一条用户消息涉及现实世界具体信息，先联网搜索，避免胡说八道
    if _needs_web_search(last_user_text):
        try:
            search_results = _web_search(last_user_text, max_results=5)
            base_prompt += _format_search_context(search_results)
        except Exception as e:
            print(f"[搜索] 异常: {e}")

    # 读取最近对话历史，保持上下文；云端接口也要记忆同一设备/账号的多轮对话
    chat_history = _load_chat_history(family_id, limit=8)

    # 加载家庭长期记忆包，保证跨会话的核心信息不丢失
    family_memory = _load_family_memory(family_id)
    memory_context = _format_family_memory(family_memory)

    # 过滤掉内容为空的消息，防止模型拒绝（如历史中出现空助理回复）
    def _is_content_empty(content) -> bool:
        if isinstance(content, list):
            return not content
        return not (content or "").strip()
    messages = [m for m in messages if not _is_content_empty(m.get("content"))]
    full_messages = [{"role": "system", "content": base_prompt + date_context + user_context + memory_context}] + identity_examples + chat_history + messages

    # 调用模型
    start_time = time.time()
    try:
        reply, reasoning, usage_info = chat_completion(full_messages, backend=backend, return_reasoning=True)
    except Exception as e:
        traceback.print_exc()
        with _CHAT_CACHE_LOCK:
            inflight = _CHAT_INFLIGHT.get(cache_key)
            if inflight:
                inflight["error"] = f"模型调用失败: {str(e)}"
            _CHAT_INFLIGHT.pop(cache_key, None)
            wait_event.set()
        return jsonify({"success": False, "error": f"模型调用失败: {str(e)}"}), 500

    cost_ms = int((time.time() - start_time) * 1000)
    if not (reply or "").strip():
        reply = "书童刚才没想好怎么回答，你能再说一遍吗？"

    # 记录本次 token 消耗
    if usage_info and family_id:
        try:
            record_family_token_usage(family_id, usage_info)
        except Exception as e:
            print(f"[token 记录失败] {family_id}: {e}")

    response = {
        "success": True,
        "reply": reply,
        "mode": mode,
        "family_id": family_id,
        "soul_version": soul_cache.get("version"),
        "backend": backend or "auto",
        "cost_ms": cost_ms,
    }
    if reasoning:
        response["reasoning"] = reasoning

    # 语音合成：优先处理多角色标签，否则单条合成
    audio_url = None
    if voice_enabled:
        try:
            clean_text, audio_url, voice_label = synthesize_multi_voice(reply)
            if audio_url:
                response["reply"] = clean_text
                response["audio_url"] = audio_url
                response["voice"] = voice_label
            else:
                audio_url = synthesize_single_voice(reply)
                if audio_url:
                    response["audio_url"] = audio_url
                    response["voice"] = CONFIG.get("voice_name", "default")
        except Exception as e:
            print(f"[云端聊天] 语音合成失败: {e}")
            traceback.print_exc()

    # 缓存结果并唤醒等待中的重复请求
    _set_cached_chat(cache_key, reply, audio_url, reasoning=reasoning)
    with _CHAT_CACHE_LOCK:
        inflight = _CHAT_INFLIGHT.get(cache_key)
        if inflight:
            inflight["reply"] = reply
            inflight["audio_url"] = audio_url
            inflight["reasoning"] = reasoning
            inflight["error"] = None
        _CHAT_INFLIGHT.pop(cache_key, None)
        wait_event.set()

    # 保存对话历史，使刷新/换设备后可恢复
    try:
        _save_chat_history(family_id, last_user_text, reply, user_id=user_id or child_id)
    except Exception as e:
        print(f"[云端聊天] 保存历史失败: {e}")

    # 更新家庭长期记忆包（后台提取关键事实）
    try:
        _extract_and_update_memory(family_id, last_user_text, reply, user_id or child_id)
    except Exception as e:
        print(f"[云端聊天] 更新记忆包失败: {e}")

    # 为机器人生成配套动作（基于回复内容语义匹配）
    try:
        robot_actions = _extract_robot_actions(response["reply"])
        if robot_actions:
            response["robot_actions"] = robot_actions
    except Exception as e:
        print(f"[云端聊天] 动作生成失败: {e}")

    return jsonify(response)


@app.route("/api/cloud/chat/history", methods=["GET"])
def api_cloud_chat_history():
    """订阅家庭端获取最近对话历史（刷新/换设备后可恢复）"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401
    limit = request.args.get("limit", 50, type=int)
    history = _load_chat_history(family_id, limit=max(1, min(limit, 200)))
    return jsonify({
        "success": True,
        "family_id": family_id,
        "history": history,
    })


# ═══════════════════════════════════════════════════
# 每日安排/日程接口
# ═══════════════════════════════════════════════════


def _get_family_schedule_dir(family_id: str) -> Path:
    return CLOUD_FAMILY_DIR / family_id


@app.route("/api/plans", methods=["GET", "POST"])
@app.route("/api/cloud/plans", methods=["GET", "POST"])
def api_plans():
    """本地家庭端/师父PC端兼容计划接口：把日程数据转成前端期望的 plans 格式"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data_dir = _get_family_schedule_dir(family_id)
    try:
        items = schedule_lib.get_today_items(data_dir)
        # 把日程项转成前端 plans 格式
        plans = []
        for item in items:
            plan = {
                "name": item.get("id", ""),
                "title": item.get("title") or item.get("content", "")[:20],
                "preview": item.get("content", ""),
                "date": int(item.get("start_time", datetime.now().timestamp())),
                "checked": bool(item.get("checked")),
            }
            plans.append(plan)
        return jsonify({"success": True, "plans": plans})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": True, "plans": []})



@app.route("/api/cloud/schedule", methods=["GET"])
def cloud_schedule_get():
    """获取今日日程"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    try:
        data_dir = _get_family_schedule_dir(family_id)
        items = schedule_lib.get_today_items(data_dir)
        stats = schedule_lib.get_stats(data_dir)
        return jsonify({"success": True, "items": items, "stats": stats})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/schedule", methods=["POST"])
def cloud_schedule_post():
    """新增或更新日程项"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = request.get_json(silent=True) or {}
    item_id = data.get("id")
    try:
        data_dir = _get_family_schedule_dir(family_id)
        if item_id:
            item = schedule_lib.update_item(data_dir, item_id, data)
            if not item:
                return jsonify({"success": False, "error": "日程项不存在"}), 404
        else:
            item = schedule_lib.add_item(data_dir, data)
        return jsonify({"success": True, "item": item})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/schedule/checkin", methods=["POST"])
def cloud_schedule_checkin():
    """打卡/取消打卡"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = request.get_json(silent=True) or {}
    item_id = data.get("id")
    checked = data.get("checked", True)
    if not item_id:
        return jsonify({"success": False, "error": "缺少日程项 ID"}), 400
    try:
        data_dir = _get_family_schedule_dir(family_id)
        item = schedule_lib.checkin_item(data_dir, item_id, checked)
        return jsonify({"success": True, "item": item})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/schedule/<item_id>", methods=["DELETE"])
def cloud_schedule_delete(item_id):
    """删除日程项"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    try:
        data_dir = _get_family_schedule_dir(family_id)
        if schedule_lib.delete_item(data_dir, item_id):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "日程项不存在"}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════
# 成长记录接口
# ═══════════════════════════════════════════════════

def _get_family_growth_dir(family_id: str) -> Path:
    return CLOUD_FAMILY_DIR / family_id


@app.route("/api/cloud/growth", methods=["GET"])
def cloud_growth_get():
    """获取成长记录列表"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    try:
        data_dir = _get_family_growth_dir(family_id)
        category = request.args.get("category")
        limit = int(request.args.get("limit", 50))
        items = growth_lib.list_records(data_dir, limit=limit, category=category)
        stats = growth_lib.get_stats(data_dir)
        return jsonify({"success": True, "items": items, "stats": stats})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/growth", methods=["POST"])
def cloud_growth_post():
    """新增成长记录"""
    family_id, sub, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = request.get_json(silent=True) or {}
    created_by = ""
    if sub:
        created_by = sub.get("role", "")
    try:
        data_dir = _get_family_growth_dir(family_id)
        item = growth_lib.add_record(data_dir, data, created_by=created_by)
        return jsonify({"success": True, "item": item})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/growth/<record_id>", methods=["DELETE"])
def cloud_growth_delete(record_id):
    """删除成长记录"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    try:
        data_dir = _get_family_growth_dir(family_id)
        if growth_lib.delete_record(data_dir, record_id):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "记录不存在"}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════
# 家庭留言板接口
# ═══════════════════════════════════════════════════

def _get_family_bulletin_dir(family_id: str) -> Path:
    return CLOUD_FAMILY_DIR / family_id


@app.route("/api/cloud/bulletin", methods=["GET"])
def cloud_bulletin_get():
    """获取家庭留言板"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    try:
        data_dir = _get_family_bulletin_dir(family_id)
        items = bulletin_lib.list_messages(data_dir)
        stats = bulletin_lib.get_stats(data_dir)
        return jsonify({"success": True, "items": items, "stats": stats})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/bulletin", methods=["POST"])
def cloud_bulletin_post():
    """新增留言"""
    family_id, sub, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = request.get_json(silent=True) or {}
    author = ""
    if sub:
        author = sub.get("role", "")
    try:
        data_dir = _get_family_bulletin_dir(family_id)
        item = bulletin_lib.add_message(data_dir, {**data, "author": data.get("author") or author})
        return jsonify({"success": True, "item": item})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/bulletin/<message_id>", methods=["DELETE"])
def cloud_bulletin_delete(message_id):
    """删除留言"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    try:
        data_dir = _get_family_bulletin_dir(family_id)
        if bulletin_lib.delete_message(data_dir, message_id):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "留言不存在"}), 404
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════
# 设置中心接口
# ═══════════════════════════════════════════════════

def _get_family_settings_dir(family_id: str) -> Path:
    return CLOUD_FAMILY_DIR / family_id


@app.route("/api/cloud/settings", methods=["GET"])
def cloud_settings_get():
    """获取家庭设置"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    try:
        data_dir = _get_family_settings_dir(family_id)
        settings = settings_lib.load_settings(data_dir)
        return jsonify({"success": True, "settings": settings})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/settings", methods=["POST"])
def cloud_settings_post():
    """保存家庭设置"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = request.get_json(silent=True) or {}
    try:
        data_dir = _get_family_settings_dir(family_id)
        settings = settings_lib.save_settings(data_dir, data.get("settings", {}))
        return jsonify({"success": True, "settings": settings})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════════════
# 家庭档案脱敏分析接口
# ═══════════════════════════════════════════════════

@app.route("/api/cloud/archive/analytics", methods=["POST"])
def cloud_archive_analytics():
    """家庭档案脱敏聚合分析（师父/管理密钥可访问全量）"""
    family_id, sub, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data = request.get_json(silent=True) or {}
    action = data.get("action", "distribution")
    min_k = int(data.get("min_k", 10))

    try:
        idx = archive_mgr.FamilyArchiveIndex(archive_mgr.CLOUD_INDEX_PATH, CLOUD_FAMILY_DIR)
        if action == "rebuild":
            result = idx.rebuild_from_disk()
            return jsonify({"success": True, "indexed": result["indexed"]})
        if action == "distribution":
            return jsonify({"success": True, "data": idx.label_distribution(min_k=min_k)})
        if action == "count_by_label":
            label = data.get("label", "")
            if not label:
                return jsonify({"success": False, "error": "缺少 label 参数"}), 400
            return jsonify({"success": True, "data": idx.count_by_label(label, min_k=min_k)})
        if action == "query":
            filters = data.get("filters", {})
            return jsonify({"success": True, "data": idx.query(filters, min_k=min_k)})
        if action == "search":
            filters = data.get("filters", {})
            limit = int(data.get("limit", 20))
            offset = int(data.get("offset", 0))
            results = idx.search(filters, limit=limit, offset=offset, desensitize=True)
            return jsonify({"success": True, "data": results})
        return jsonify({"success": False, "error": "未知 action"}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/tts", methods=["POST"])
def cloud_tts():
    """云端语音合成接口（家庭订阅或师父管理密钥均可）

    返回 JSON：{"success": true, "audio_url": "/audio/xxx.mp3", "voice": "..."}
    """
    family_id, sub, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    if not TTS_LIMITER.is_allowed(family_id):
        return jsonify({"success": False, "error": "语音合成太频繁，请稍后再试"}), 429

    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "文本不能为空"}), 400

    # 优先处理带角色标签的多角色合成
    clean_text, audio_url, voice_label = synthesize_multi_voice(text)
    if audio_url:
        return jsonify({"success": True, "audio_url": audio_url, "voice": voice_label, "reply": clean_text})

    # 单条合成
    if not voice_engine or not voice_engine.backend:
        return jsonify({"success": False, "error": "语音引擎未就绪"}), 503

    try:
        audio_url = synthesize_single_voice(text, data.get("voice"))
        if audio_url:
            return jsonify({"success": True, "audio_url": audio_url, "voice": data.get("voice") or CONFIG.get("voice_name", "default")})
        return jsonify({"success": False, "error": "语音合成失败"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"TTS 失败: {str(e)}"}), 500


@app.route("/api/cloud/stt", methods=["POST"])
def cloud_stt():
    """云端语音转文字接口（接收上传的音频文件，家庭订阅或师父管理密钥均可）"""
    family_id, sub, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    if not STT_LIMITER.is_allowed(family_id):
        return jsonify({"success": False, "error": "语音识别太频繁，请稍后再试"}), 429

    if not stt_engine:
        return jsonify({"success": False, "error": "语音识别引擎未就绪"}), 503

    # 支持两种方式：multipart 文件上传 或 base64 音频数据
    if request.files and "audio" in request.files:
        audio_file = request.files["audio"]
        if audio_file.filename == "":
            return jsonify({"success": False, "error": "未上传音频文件"}), 400

        # 保存到临时文件
        suffix = os.path.splitext(audio_file.filename)[1] or ".wav"
        temp_path = tempfile.mktemp(suffix=suffix)
        try:
            audio_file.save(temp_path)
            result = stt_engine.transcribe(audio_file=temp_path)
            print(f"[STT] family={family_id} text={result.get('text', '')!r} engine={result.get('engine', stt_engine.engine_name)} confidence={result.get('confidence', 0)}")
            return jsonify({
                "success": True,
                "text": result.get("text", ""),
                "confidence": result.get("confidence", 0),
                "language": result.get("language", ""),
                "engine": result.get("engine", stt_engine.engine_name),
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({"success": False, "error": f"识别失败: {str(e)}"}), 500
        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass

    # base64 数据：先存成临时音频文件再识别，兼容 WAV/PCM/WEBM 等多种格式
    data = request.get_json(silent=True) or {}
    audio_base64 = data.get("audio_base64") or data.get("audio")
    if audio_base64:
        temp_path = None
        try:
            audio_bytes = _decode_audio_base64(audio_base64)
            if not audio_bytes:
                return jsonify({"success": False, "error": "音频数据为空"}), 400
            suffix = _detect_audio_suffix(audio_bytes)
            # 浏览器 MediaRecorder 常见 webm，先转成标准 WAV 再给 STT 引擎
            if suffix in (".webm", ".ogg", ".flac", ".mp3"):
                audio_bytes = _convert_to_wav_if_needed(audio_bytes, suffix)
                suffix = ".wav"
            temp_path = tempfile.mktemp(suffix=suffix)
            with open(temp_path, "wb") as f:
                f.write(audio_bytes)
            result = stt_engine.transcribe(audio_file=temp_path)
            print(f"[STT] family={family_id} text={result.get('text', '')!r} engine={result.get('engine', stt_engine.engine_name)} confidence={result.get('confidence', 0)}")
            return jsonify({
                "success": True,
                "text": result.get("text", ""),
                "confidence": result.get("confidence", 0),
                "language": result.get("language", ""),
                "engine": result.get("engine", stt_engine.engine_name),
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({"success": False, "error": f"识别失败: {str(e)}"}), 500
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    return jsonify({"success": False, "error": "请上传音频文件或提供 audio_base64"}), 400



@app.route("/api/tts", methods=["POST"])
def api_tts_alias():
    """本地 UI 兼容：/api/tts 转发到 /api/cloud/tts"""
    return cloud_tts()


@app.route("/api/stt", methods=["POST"])
def api_stt_alias():
    """本地 UI 兼容：/api/stt 转发到 /api/cloud/stt"""
    return cloud_stt()

@app.route("/api/cloud/ability", methods=["POST"])
def cloud_ability():
    """统一云端能力调用接口"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data = request.get_json(silent=True) or {}
    ability = data.get("ability", "")
    action = data.get("action", "")
    params = data.get("params", {})
    child_summary = data.get("child_summary", {})

    if not ability:
        return jsonify({"success": False, "error": "缺少 ability 参数"}), 400

    engine = ability_engines.get(ability)
    if not engine:
        return jsonify({"success": False, "error": f"能力 {ability} 未初始化"}), 503

    try:
        result = None

        if ability == "development":
            if action == "daily_assessment":
                result = engine.daily_assessment(params.get("child_id", "default_child"))
            elif action == "assess_all_children":
                result = engine.assess_all_children()
            elif action == "get_family_report":
                result = engine.get_family_report()
            elif action == "trend_analysis":
                result = engine.trend_analysis(
                    params.get("child_id", "default_child"),
                    params.get("dimension", "情绪"),
                    params.get("days", 7),
                )
            else:
                result = engine.daily_assessment(params.get("child_id", "default_child"))

        elif ability == "culture":
            age = params.get("child_age", child_summary.get("age", 10))
            context = params.get("context", "")
            if action == "recommend_poem":
                result = engine.recommend_poem(context, age)
            elif action == "generate_culture_response":
                opportunity = params.get("opportunity", {})
                if not opportunity and params.get("user_input"):
                    opportunity = {"text": params.get("user_input"), "type": "dialogue"}
                result = engine.generate_culture_response(opportunity, age)
            elif action == "get_weekly_culture_seed":
                result = engine.get_weekly_culture_seed(params.get("week_number"))
            else:
                result = engine.recommend_poem(context, age)

        elif ability == "medicine":
            symptoms = params.get("symptoms_desc", params.get("symptoms", ""))
            if isinstance(symptoms, list):
                symptoms = "，".join(symptoms)
            age = params.get("child_age", child_summary.get("age", 10))
            stage = params.get("child_stage", child_summary.get("stage", "S3"))
            report = engine.analyze(symptoms, age, stage)
            if action == "format_for_child":
                result = engine.format_for_child(report)
            else:
                result = report

        elif ability == "heart":
            if action == "today_theme":
                result = engine.get_today_theme()
            elif action == "bedtime_ritual":
                result = engine.get_bedtime_ritual()
            elif action == "script":
                result = engine.get_script()
            elif action == "select_music":
                result = engine.select_music(params.get("mood"))
            else:
                result = engine.get_today_theme()

        elif ability == "bedtime":
            profile_dict = params.get("child_profile", {
                "age": child_summary.get("age", 10),
                "stage": "S3",
                "name": "孩子",
                "gender": "",
                "interests": [],
            })
            profile_dict.setdefault("name", "孩子")
            profile_dict.setdefault("stage", "S3")
            profile_dict.setdefault("gender", "")
            profile_dict.setdefault("interests", [])
            child_profile = SimpleNamespace(**profile_dict)
            result = engine.generate_bedtime_session(
                child_profile,
                params.get("duration_minutes", 10),
                params.get("custom_notes"),
            )

        elif ability == "morning":
            if action == "generate":
                result = engine.generate(params.get("target_minutes", 6))
            elif action == "get_opening":
                result = engine.get_opening()
            elif action == "get_facts":
                result = engine.get_facts()
            elif action == "get_interactions":
                result = engine.get_interactions()
            elif action == "get_jokes":
                result = engine.get_jokes()
            elif action == "get_closing":
                result = engine.get_closing()
            else:
                result = engine.get_opening()

        else:
            return jsonify({"success": False, "error": f"未知能力: {ability}"}), 400

        return jsonify({
            "success": True,
            "ability": ability,
            "action": action,
            "result": result,
            "family_id": family_id,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"能力调用失败: {str(e)}"}), 500


@app.route("/api/cloud/register_family", methods=["POST"])
def cloud_register_family():
    """本地安装包注册/更新云端家庭基本信息"""
    data = request.get_json(silent=True) or {}
    family_data = data.get("family_data", {})

    # 先从 family_data 中取得 family_id 用于授权校验
    auth_data = data.copy()
    if not auth_data.get("family_id") and family_data.get("family_id"):
        auth_data["family_id"] = family_data["family_id"]

    family_id, sub, _, error = auth_subscription(auth_data)
    if error:
        return jsonify({"success": False, "error": error}), 401
    if not family_data:
        return jsonify({"success": False, "error": "缺少 family_data"}), 400

    family_data.setdefault("family_id", family_id)
    family_data["updated_at"] = datetime.now().isoformat()
    family_data["registered_ip"] = request.remote_addr
    if not family_data.get("created_at"):
        family_data["created_at"] = family_data["updated_at"]

    if save_cloud_family(family_id, family_data):
        log_admin("register_family", f"{family_id} from {request.remote_addr}")
        return jsonify({"success": True, "family_id": family_id, "message": "家庭信息已同步到云端"})
    return jsonify({"success": False, "error": "保存云端家庭信息失败"}), 500


@app.route("/api/cloud/family", methods=["GET"])
def cloud_get_family():
    """本地安装包获取云端家庭基本信息"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data = load_cloud_family(family_id)
    if not data:
        return jsonify({"success": False, "error": "云端暂无该家庭信息"}), 404
    return jsonify({"success": True, "family": data})


@app.route("/api/cloud/family_list", methods=["GET"])
def cloud_family_list():
    """本地安装包获取自己所在家庭的基本信息（与/family一致，兼容命名）"""
    return cloud_get_family()


@app.route("/api/cloud/family_members", methods=["GET"])
def cloud_get_family_members():
    """本地安装包获取家庭成员列表"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data = load_cloud_family(family_id)
    members = data.get("members", [])
    return jsonify({"success": True, "members": members})


@app.route("/api/cloud/parent_assistant/templates", methods=["GET"])
def cloud_parent_templates():
    """家长助手模板"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401
    try:
        templates = get_templates() if get_templates else []
        return jsonify({"success": True, "templates": templates})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/parent_assistant/generate", methods=["POST"])
def cloud_parent_generate():
    """家长助手生成内容"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data = request.get_json(silent=True) or {}
    template_id = data.get("template_id", "")
    context = data.get("context", {})

    if not template_id or not build_prompt:
        return jsonify({"success": False, "error": "缺少参数或家长助手未加载"}), 400

    try:
        prompt = build_prompt(template_id, context)
        messages = [
            {"role": "system", "content": soul_cache.get("system_prompt", "")},
            {"role": "user", "content": prompt},
        ]
        content = chat_completion(messages)
        return jsonify({"success": True, "content": content, "template_id": template_id})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/parent_assistant/save", methods=["POST"])
def cloud_parent_save():
    """保存家长助手作品"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data = request.get_json(silent=True) or {}
    filename = data.get("filename", "")
    content = data.get("content", "")

    if not filename or not save_creation or not get_family_dir:
        return jsonify({"success": False, "error": "缺少参数或家长助手未加载"}), 400

    try:
        family_dir = get_family_dir(family_id)
        save_creation(family_dir, filename, content)
        return jsonify({"success": True, "message": "保存成功"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/parent_assistant/creations", methods=["GET"])
def cloud_parent_creations():
    """列出家长助手作品"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    try:
        family_dir = get_family_dir(family_id) if get_family_dir else PROJECT_ROOT / "04-工作区" / "云端数据区" / "家长创作" / family_id
        family_dir.mkdir(parents=True, exist_ok=True)
        creations = list_creations(family_dir) if list_creations else []
        return jsonify({"success": True, "creations": creations})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/parent_assistant/creation", methods=["GET"])
def cloud_parent_creation():
    """读取家长助手作品"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    filename = request.args.get("filename", "")
    if not filename or not load_creation or not get_family_dir:
        return jsonify({"success": False, "error": "缺少参数"}), 400

    try:
        family_dir = get_family_dir(family_id)
        content = load_creation(family_dir, filename)
        return jsonify({"success": True, "filename": filename, "content": content})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/cloud/parent_assistant/delete", methods=["POST"])
def cloud_parent_delete():
    """删除家长助手作品"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data = request.get_json(silent=True) or {}
    filename = data.get("filename", "")

    if not filename or not delete_creation or not get_family_dir:
        return jsonify({"success": False, "error": "缺少参数"}), 400

    try:
        family_dir = get_family_dir(family_id)
        delete_creation(family_dir, filename)
        return jsonify({"success": True, "message": "删除成功"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════
# 师父云端控制台接口
# ═══════════════════════════════════════════

@app.route("/admin/status", methods=["GET"])
def admin_status():
    """查看云端书童运行状态"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    abilities = {k: (v is not None) for k, v in ability_engines.items()}

    return jsonify({
        "success": True,
        "server_time": datetime.now().isoformat(),
        "soul_version": soul_cache.get("version"),
        "soul_loaded_at": soul_cache.get("loaded_at"),
        "soul_files": soul_cache.get("files"),
        "subscriptions_count": len(SUBSCRIPTIONS),
        "families_count": len(list_cloud_families()),
        "voice_backend": voice_engine.backend if voice_engine else None,
        "abilities": abilities,
        "recent_logs": request_log[-50:],
    })


@app.route("/admin/chat", methods=["POST"])
def admin_chat():
    """师父直接跟云端书童对话测试"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    mode = data.get("mode", "master")
    backend = data.get("backend")
    if backend and backend not in _ALLOWED_BACKENDS:
        return jsonify({"success": False, "error": f"不支持的后端: {backend}"}), 400

    if not messages:
        return jsonify({"success": False, "error": "消息不能为空"}), 400

    if mode != "master":
        return jsonify({"success": False, "error": "师父控制台仅支持 master 模式"}), 400

    base_prompt = soul_cache.get("master_prompt", "")

    # 过滤掉内容为空的消息，防止模型拒绝；支持 content 为字符串或 OpenAI 风格 list
    def _message_has_content(m):
        content = m.get("content")
        if isinstance(content, list):
            return any(item.get("type") == "image_url" or (item.get("text") or "").strip() for item in content)
        return bool((content or "").strip())

    messages = [m for m in messages if _message_has_content(m)]
    full_messages = [{"role": "system", "content": base_prompt}] + messages

    start_time = time.time()
    try:
        reply = chat_completion(full_messages, backend=backend)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"模型调用失败: {str(e)}"}), 500

    cost_ms = int((time.time() - start_time) * 1000)
    if not (reply or "").strip():
        reply = "书童刚才没想好怎么回答，你能再说一遍吗？"

    # 师父控制台语音朗读
    audio_url = None
    voice_name = None
    if data.get("voice") and voice_engine and voice_engine.backend:
        try:
            audio_url = synthesize_single_voice(reply)
            voice_name = CONFIG.get("voice_name", "default")
        except Exception as e:
            print(f"[师父控制台] 语音合成失败: {e}")

    log_admin("admin_chat", f"mode={mode}, messages={len(messages)}")

    response = {
        "success": True,
        "reply": reply,
        "mode": mode,
        "soul_version": soul_cache.get("version"),
        "cost_ms": cost_ms,
    }
    if audio_url:
        response["audio_url"] = audio_url
        response["voice"] = voice_name
    return jsonify(response)


@app.route("/admin/soul", methods=["GET"])
def admin_get_soul():
    """查看当前灵魂文件内容"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    file_type = request.args.get("type", "system_prompt")  # agents / system_prompt / master_prompt
    path = SOUL_FILES.get(file_type)
    if not path or not path.exists():
        return jsonify({"success": False, "error": "文件不存在"}), 404

    content = path.read_text(encoding="utf-8")
    return jsonify({
        "success": True,
        "type": file_type,
        "path": str(path),
        "version": soul_cache.get("version"),
        "content": content,
    })


@app.route("/admin/soul", methods=["POST"])
def admin_update_soul():
    """更新灵魂文件（师父修改后热更新）"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    data = request.get_json(silent=True) or {}
    file_type = data.get("type", "system_prompt")
    content = data.get("content", "")

    if file_type not in SOUL_FILES:
        return jsonify({"success": False, "error": "不支持的文件类型"}), 400

    path = SOUL_FILES[file_type]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    # 重新加载灵魂
    load_soul()
    log_admin("update_soul", f"type={file_type}, new_version={soul_cache['version']}")

    return jsonify({
        "success": True,
        "type": file_type,
        "new_version": soul_cache.get("version"),
        "message": "灵魂文件已更新并重新加载",
    })


@app.route("/admin/reload", methods=["POST"])
def admin_reload():
    """重新加载灵魂文件"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    old_version = soul_cache.get("version")
    load_soul()
    new_version = soul_cache.get("version")
    log_admin("reload_soul", f"{old_version} -> {new_version}")

    return jsonify({
        "success": True,
        "old_version": old_version,
        "new_version": new_version,
        "message": "灵魂文件已重新加载",
    })


@app.route("/admin/subscriptions", methods=["GET"])
def admin_subscriptions():
    """查看所有订阅（隐藏密钥）"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    safe_list = []
    for fid, sub in SUBSCRIPTIONS.items():
        keys = []
        for krec in sub.get("keys", []):
            keys.append({
                "key_prefix": krec.get("key", "")[:6] + "****",
                "device_id": krec.get("device_id"),
                "device_ip": krec.get("device_ip"),
                "activated_at": krec.get("activated_at"),
                "status": krec.get("status", "active"),
            })
        safe_list.append({
            "family_id": fid,
            "plan": sub.get("plan"),
            "expires": sub.get("expires"),
            "created_at": sub.get("created_at"),
            "keys": keys,
        })

    return jsonify({"success": True, "subscriptions": safe_list})


def _generate_subscription_key():
    """生成新的订阅密钥：bookkidai.com/robot/<随机短码>"""
    short = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:12]
    return f"bookkidai.com/robot/{short}"


@app.route("/admin/family/<family_id>/subscription_key", methods=["GET"])
def admin_family_subscription_key(family_id):
    """师父获取指定家庭的一个可用订阅密钥；优先返回未绑定设备的密钥，没有则自动创建；家庭不存在时自动开通订阅。
    打包安装包时建议带 ?reserve=true，云端会把该 key 标记为待激活，避免多个安装包复用同一密钥。"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    sub = SUBSCRIPTIONS.get(family_id)
    if not sub:
        # 自动开通订阅
        sub = {
            "plan": "standard",
            "expires": "2027-12-31",
            "created_at": datetime.now().isoformat(),
            "keys": [],
        }
        SUBSCRIPTIONS[family_id] = sub

    # 优先找一个未绑定设备的 key
    selected = None
    for krec in sub.get("keys", []):
        if krec.get("status") == "active" and not krec.get("device_id"):
            selected = krec
            break

    if selected:
        key = selected["key"]
        log_admin("view_subscription_key", f"{family_id} (未绑定)")
    else:
        # 没有可用 key，自动创建一个新的
        key = _generate_subscription_key()
        selected = {
            "key": key,
            "device_id": None,
            "device_ip": None,
            "activated_at": None,
            "status": "active",
        }
        sub.setdefault("keys", []).append(selected)
        log_admin("create_subscription_key", f"{family_id} new_key={key[:12]}...")

    # 打包预留：避免后续安装包再次拿到同一个 key
    reserve = request.args.get("reserve", "false").lower() == "true"
    if reserve and not selected.get("device_id"):
        selected["device_id"] = "PENDING_ACTIVATION"
        selected["activated_at"] = datetime.now().isoformat()
        log_admin("reserve_subscription_key", f"{family_id} key={key[:12]}...")

    save_subscriptions()
    return jsonify({"success": True, "family_id": family_id, "key": key, "bound": False, "reserved": reserve})


@app.route("/admin/family/<family_id>/subscribe", methods=["POST"])
def admin_family_subscribe(family_id):
    """师父为指定家庭创建/更新订阅"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    data = request.get_json(silent=True) or {}
    plan = data.get("plan", "standard")
    expires = data.get("expires", "2027-12-31")

    sub = SUBSCRIPTIONS.get(family_id)
    if not sub:
        sub = {
            "plan": plan,
            "expires": expires,
            "created_at": datetime.now().isoformat(),
            "keys": [],
        }
        SUBSCRIPTIONS[family_id] = sub

    sub["plan"] = plan
    sub["expires"] = expires

    # 如果没有 key，创建一个
    if not sub.get("keys"):
        new_key = _generate_subscription_key()
        sub["keys"].append({
            "key": new_key,
            "device_id": None,
            "device_ip": None,
            "activated_at": None,
            "status": "active",
        })

    save_subscriptions()
    log_admin("subscribe_family", f"{family_id} plan={plan} expires={expires}")
    return jsonify({"success": True, "family_id": family_id, "keys_count": len(sub["keys"])})


@app.route("/admin/families", methods=["GET"])
def admin_families():
    """师父查看云端所有家庭基本信息摘要（包含审核状态）"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    try:
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        c.execute("SELECT family_id, approved FROM accounts")
        approval_map = {row[0]: bool(row[1]) for row in c.fetchall()}
        conn.close()
        families = list_cloud_families()
        for fam in families:
            fid = fam.get("family_id")
            # 账号表中有记录按记录；无记录但目录存在视为历史家庭，默认通过
            if fid in approval_map:
                fam["approved"] = approval_map[fid]
            else:
                fam["approved"] = bool((CLOUD_FAMILY_DIR / fid).is_dir())
        log_admin("list_families")
        return jsonify({"success": True, "families": families})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



@app.route("/admin/sales/customers", methods=["GET"])
def admin_sales_customers():
    """销售视角：付费客户列表"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    return jsonify({"success": True, "customers": list_sales_customers()})


@app.route("/admin/sales/overview", methods=["GET"])
def admin_sales_overview():
    """销售总览：客户数、地区分布、Token 用量、续费概况"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    customers = list_sales_customers()
    tree = _sales_region_tree(customers)
    now = datetime.now()
    active_this_month = sum(1 for c in customers if c.get("token_usage", 0) > 0)
    recent_renewals = sorted(
        [c for c in customers if c.get("renewed_at")],
        key=lambda x: x["renewed_at"],
        reverse=True,
    )[:10]
    return jsonify({
        "success": True,
        "total_customers": len(customers),
        "provinces_count": len(tree),
        "active_this_month": active_this_month,
        "total_token_usage": sum(c.get("token_usage", 0) for c in customers),
        "region_tree": tree,
        "recent_renewals": recent_renewals,
    })

@app.route("/admin/family/<family_id>", methods=["GET"])
def admin_family_detail(family_id):
    """师父查看指定家庭完整基本信息"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    data = load_cloud_family(family_id)
    if not data:
        return jsonify({"success": False, "error": "家庭不存在"}), 404
    log_admin("view_family", family_id)
    return jsonify({"success": True, "family": data})


@app.route("/admin/family/<family_id>", methods=["POST"])
def admin_family_update(family_id):
    """师父在云端修改指定家庭基本信息"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    data = request.get_json(silent=True) or {}
    family_data = data.get("family_data", {})
    if not family_data:
        return jsonify({"success": False, "error": "缺少 family_data"}), 400
    family_data["family_id"] = family_id
    family_data.setdefault("created_at", datetime.now().isoformat())
    family_data["updated_at"] = datetime.now().isoformat()
    if save_cloud_family(family_id, family_data):
        log_admin("update_family", family_id)
        return jsonify({"success": True, "message": "家庭信息已更新"})
    return jsonify({"success": False, "error": "保存失败"}), 500


@app.route("/admin/family/<family_id>/sales-info", methods=["POST"])
def admin_family_update_sales_info(family_id):
    """师父更新家庭销售信息（地区、联系人、标签、套餐、到期时间等）"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    data = request.get_json(silent=True) or {}
    family = load_cloud_family(family_id)
    if not family:
        return jsonify({"success": False, "error": "家庭不存在"}), 404

    # 更新家庭档案中的销售相关字段
    if "region" in data:
        family["region"] = data["region"]
    if "contact" in data:
        family["contact"] = family.get("contact", {})
        family["contact"].update(data["contact"])
    if "tags" in data:
        family["tags"] = data["tags"]

    if not save_cloud_family(family_id, family):
        return jsonify({"success": False, "error": "家庭信息保存失败"}), 500

    # 更新订阅信息
    sub = SUBSCRIPTIONS.get(family_id)
    if not sub:
        sub = {
            "plan": "free",
            "expires": "2099-12-31",
            "created_at": datetime.now().isoformat(),
            "keys": [],
        }
        SUBSCRIPTIONS[family_id] = sub

    if "plan" in data:
        sub["plan"] = data["plan"]
    if "expires" in data:
        sub["expires"] = data["expires"]
    if "started_at" in data:
        sub["started_at"] = data["started_at"]
    if "renewed_at" in data:
        sub["renewed_at"] = data["renewed_at"]

    save_subscriptions()
    log_admin("update_sales_info", family_id)
    return jsonify({"success": True, "message": "销售信息已保存"})


@app.route("/admin/family/<family_id>/usage", methods=["GET"])
def admin_family_usage(family_id):
    """师父查看指定家庭的 token 消耗"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    usage = get_family_token_usage(family_id)
    family = load_cloud_family(family_id) or {}
    family_name = family.get("family_name", "")
    contact_name = family.get("contact_name", "")
    # 如果 family.json 里没有，查账号库
    if not family_name or not contact_name:
        try:
            conn = sqlite3.connect(str(ACCOUNTS_DB))
            c = conn.cursor()
            c.execute("SELECT family_name, contact_name FROM accounts WHERE family_id = ?", (family_id,))
            row = c.fetchone()
            if row:
                family_name = family_name or row[0] or ""
                contact_name = contact_name or row[1] or ""
            conn.close()
        except Exception as e:
            print(f"[admin family usage] 读取账号信息失败: {e}")
    if not usage:
        return jsonify({"success": True, "family_id": family_id, "family_name": family_name, "contact_name": contact_name, "usage": {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "daily": {},
            "monthly": {},
            "recent": [],
        }})
    log_admin("view_family_usage", family_id)
    return jsonify({"success": True, "family_id": family_id, "family_name": family_name, "contact_name": contact_name, "usage": usage})


@app.route("/admin/usage", methods=["GET"])
def admin_all_usage():
    """师父查看所有家庭的 token 消耗汇总"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    families = []
    try:
        # 从账号库读取家庭名称和联系人，避免 family.json 里为空
        name_map = {}
        contact_map = {}
        try:
            conn = sqlite3.connect(str(ACCOUNTS_DB))
            c = conn.cursor()
            c.execute("SELECT family_id, family_name, contact_name FROM accounts")
            for fid, fname, cname in c.fetchall():
                name_map[fid] = fname or ""
                contact_map[fid] = cname or ""
            conn.close()
        except Exception as e:
            print(f"[admin usage] 读取账号信息失败: {e}")

        for path in sorted(CLOUD_FAMILY_DIR.iterdir()):
            if path.is_dir():
                fid = path.name
                usage = get_family_token_usage(fid)
                family = load_cloud_family(fid) or {}
                family_name = name_map.get(fid) or family.get("family_name", "")
                contact_name = contact_map.get(fid) or family.get("contact_name", "")
                families.append({
                    "family_id": fid,
                    "family_name": family_name,
                    "contact_name": contact_name,
                    "total_tokens": usage.get("total_tokens", 0),
                    "total_prompt_tokens": usage.get("total_prompt_tokens", 0),
                    "total_completion_tokens": usage.get("total_completion_tokens", 0),
                    "today": usage.get("daily", {}).get(datetime.now().strftime("%Y-%m-%d"), {}).get("total", 0),
                    "this_month": usage.get("monthly", {}).get(datetime.now().strftime("%Y-%m"), {}).get("total", 0),
                })
        families.sort(key=lambda x: x["total_tokens"], reverse=True)
    except Exception as e:
        print(f"[admin usage] 汇总失败: {e}")
    log_admin("view_all_usage")
    return jsonify({"success": True, "families": families, "server_total_tokens": sum(f["total_tokens"] for f in families)})


@app.route("/admin/families/pending", methods=["GET"])
def admin_families_pending():
    """师父查看待审核家庭列表"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    try:
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        c.execute(
            "SELECT family_id, email, family_name, phone, contact_name, id_card, created_at FROM accounts WHERE approved = 0 ORDER BY created_at DESC"
        )
        rows = c.fetchall()
        conn.close()
        pending = []
        for family_id, email, family_name, phone, contact_name, id_card, created_at in rows:
            pending.append({
                "family_id": family_id,
                "email": email,
                "family_name": family_name,
                "phone": phone,
                "contact_name": contact_name,
                "id_card": id_card,
                "created_at": created_at,
            })
        log_admin("list_pending_families")
        return jsonify({"success": True, "pending": pending})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/family/<family_id>/approve", methods=["POST"])
def admin_family_approve(family_id):
    """师父审核通过家庭账号"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    try:
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        c.execute("UPDATE accounts SET approved = 1, updated_at = datetime('now') WHERE family_id = ?", (family_id,))
        updated = c.rowcount
        conn.commit()
        conn.close()
        if updated == 0:
            return jsonify({"success": False, "error": "家庭不存在"}), 404
        # 激活订阅密钥
        sub = SUBSCRIPTIONS.get(family_id)
        if sub:
            for krec in sub.get("keys", []):
                if krec.get("status") == "pending_approval":
                    krec["status"] = "active"
                    krec["activated_at"] = datetime.now().isoformat()
            save_subscriptions()
        log_admin("approve_family", family_id)
        return jsonify({"success": True, "message": "家庭审核通过，已激活服务"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/family/<family_id>/reject", methods=["POST"])
def admin_family_reject(family_id):
    """师父拒绝/删除待审核家庭账号"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    try:
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        c.execute("DELETE FROM accounts WHERE family_id = ? AND approved = 0", (family_id,))
        deleted = c.rowcount
        conn.commit()
        conn.close()
        if deleted == 0:
            return jsonify({"success": False, "error": "只能删除待审核家庭"}), 400
        # 清理相关数据
        SUBSCRIPTIONS.pop(family_id, None)
        save_subscriptions()
        log_admin("reject_family", family_id)
        return jsonify({"success": True, "message": "已拒绝并删除该家庭申请"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/family/<family_id>/delete", methods=["POST"])
def admin_family_delete(family_id):
    """师父彻底删除一个家庭（账号、订阅、数据全部清理）"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    if family_id == "default_family":
        return jsonify({"success": False, "error": "默认家庭不可删除"}), 400
    try:
        # 删除账号
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        c.execute("DELETE FROM accounts WHERE family_id = ?", (family_id,))
        c.execute("DELETE FROM online_status WHERE family_id = ?", (family_id,))
        conn.commit()
        conn.close()
        # 删除订阅
        SUBSCRIPTIONS.pop(family_id, None)
        save_subscriptions()
        # 删除家庭数据目录
        family_dir = CLOUD_FAMILY_DIR / family_id
        if family_dir.exists():
            shutil.rmtree(family_dir)
        # 清理缓存
        cloud_family_cache.pop(family_id, None)
        log_admin("delete_family", family_id)
        return jsonify({"success": True, "message": f"已彻底删除家庭 {family_id}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/online", methods=["GET"])
def admin_online_status():
    """师父查看所有家庭在线状态"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    try:
        online_data = _get_online_status()
        # 补充家庭名称
        conn = sqlite3.connect(str(ACCOUNTS_DB))
        c = conn.cursor()
        c.execute("SELECT family_id, family_name FROM accounts")
        name_map = {row[0]: row[1] for row in c.fetchall()}
        conn.close()
        for item in online_data:
            item["family_name"] = name_map.get(item["family_id"], item["family_id"])
        log_admin("online_status")
        return jsonify({"success": True, "online": online_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# 允许师父访问的云端文件范围：项目根目录下的大部分内容
# 只排除敏感/运行时文件
SENSITIVE_FILE_PATTERNS = [
    ".env",
    ".env.",
    ".ssh",
    "01-配置区/config.json",
    "04-工作区/云端数据区/语音缓存",
    "04-工作区/日志",
    "03-引擎区/书童程序/数据/语音缓存",
]


def _is_sensitive_path(path: Path) -> bool:
    """判断路径是否包含敏感文件"""
    path_str = str(path)
    for pattern in SENSITIVE_FILE_PATTERNS:
        if pattern in path_str:
            return True
    # 隐藏文件/目录（以 . 开头）视为敏感
    for part in path.parts:
        if part.startswith(".") and part not in (".", ".."):
            return True
    return False


def _resolve_safe_path(requested_path: str):
    """解析并校验路径，确保只在项目根目录内，且不访问敏感文件"""
    if not requested_path or requested_path == "/":
        return PROJECT_ROOT

    # 规范化路径，防止目录遍历
    requested = Path(requested_path).resolve()

    # 必须位于项目根目录下
    try:
        requested.relative_to(PROJECT_ROOT)
    except ValueError:
        return None

    # 检查是否访问敏感路径
    if _is_sensitive_path(requested):
        return None

    return requested


@app.route("/admin/files", methods=["GET"])
def admin_files():
    """浏览云端服务器上的文件"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    path_param = request.args.get("path", "")
    target = _resolve_safe_path(path_param)

    if target is None:
        return jsonify({"success": False, "error": "无权访问该路径"}), 403

    if not target.exists():
        return jsonify({"success": False, "error": "路径不存在"}), 404

    try:
        if target.is_file():
            # 读取文件内容（限制大小 5MB）
            max_size = 5 * 1024 * 1024
            size = target.stat().st_size
            if size > max_size:
                return jsonify({
                    "success": True,
                    "type": "file",
                    "path": str(target),
                    "size": size,
                    "content": "文件超过 5MB，请在服务器上查看",
                })

            content = target.read_text(encoding="utf-8", errors="replace")
            return jsonify({
                "success": True,
                "type": "file",
                "path": str(target),
                "size": size,
                "content": content,
            })
        else:
            # 列出目录，过滤敏感项
            items = []
            for item in sorted(target.iterdir()):
                if _is_sensitive_path(item):
                    continue
                items.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                })
            return jsonify({
                "success": True,
                "type": "dir",
                "path": str(target),
                "items": items,
            })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"读取失败: {str(e)}"}), 500


@app.route("/admin/robot/status", methods=["GET"])
def admin_robot_status():
    """查看机器人连接状态"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    if not G1HTTPClient:
        return jsonify({"success": False, "error": "G1 HTTP 客户端未加载"}), 503

    if not robot_client or not robot_config.get("url"):
        return jsonify({
            "success": True,
            "connected": False,
            "message": "尚未配置机器人控制服务地址",
            "config": robot_config,
        })

    try:
        health = robot_client.health()
        capabilities = robot_client.capabilities()
        return jsonify({
            "success": True,
            "connected": health.get("ok") is True,
            "health": health,
            "capabilities": capabilities,
            "config": {k: v for k, v in robot_config.items() if k != "token"},
        })
    except Exception as e:
        return jsonify({
            "success": True,
            "connected": False,
            "error": str(e),
            "config": {k: v for k, v in robot_config.items() if k != "token"},
        })


@app.route("/admin/robot/config", methods=["POST"])
def admin_robot_config():
    """配置机器人控制服务"""
    global robot_client, robot_config
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    if not G1HTTPClient:
        return jsonify({"success": False, "error": "G1 HTTP 客户端未加载"}), 503

    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    token = data.get("token", "").strip()

    if not url:
        return jsonify({"success": False, "error": "缺少控制服务地址"}), 400

    robot_config = {"url": url, "token": token}
    robot_client = G1HTTPClient(base_url=url, token=token or None)

    # 测试连接
    health = robot_client.health()
    connected = health.get("ok") is True

    log_admin("robot_config", f"url={url}, connected={connected}")

    return jsonify({
        "success": True,
        "connected": connected,
        "message": "连接成功" if connected else f"配置已保存，但连接测试失败: {health.get('error', '')}",
        "health": health,
    })


@app.route("/admin/robot/action", methods=["POST"])
def admin_robot_action():
    """发送机器人动作指令"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    if not ROBOT_ACTION_LIMITER.is_allowed(_client_ip()):
        return jsonify({"success": False, "error": "机器人动作太频繁，请稍后再试"}), 429

    if not G1HTTPClient:
        return jsonify({"success": False, "error": "G1 HTTP 客户端未加载"}), 503

    if not robot_client or not robot_config.get("url"):
        return jsonify({"success": False, "error": "请先配置机器人控制服务"}), 400

    data = request.get_json(silent=True) or {}
    action = data.get("action", "")
    text = data.get("text", "")

    if not action:
        return jsonify({"success": False, "error": "缺少动作"}), 400

    try:
        # 动作映射
        action_map = {
            "stand": "stand",
            "sit": "squat",
            "wave": "face_wave",
            "bow": "stand",  # 鞠躬暂无对应，先用站立
            "stop": "stop",
        }

        mapped_action = action_map.get(action, action)

        if action == "custom" and text:
            # 自定义 TTS（限制长度，防止滥用）
            if len(text) > 1000:
                return jsonify({"success": False, "error": "自定义 TTS 文本过长，最多 1000 字"}), 400
            try:
                result = robot_client.speak_tts(text)
                log_admin("robot_tts", f"text={text[:30]}")
                return jsonify({"success": True, "action": "tts", "result": result, "text": text})
            except Exception:
                # 如果 TTS 不存在，回退到动作
                pass

        # 优先尝试手臂动作
        if mapped_action in G1HTTPClient.SAFE_ARM_ACTIONS:
            result = robot_client.execute_arm_action(mapped_action)
        else:
            result = robot_client.execute_action(mapped_action)

        log_admin("robot_action", f"action={mapped_action}")
        return jsonify({"success": True, "action": mapped_action, "result": result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"指令发送失败: {str(e)}"}), 500


# ═══════════════════════════════════════════
# 家庭级机器人控制接口（云端代理到千家万户）
# ═══════════════════════════════════════════


@app.route("/admin/probe", methods=["POST"])
def admin_probe():
    """师父控制台：探测外部 URL 可达性（用于备案状态检测等）"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    data = request.get_json(silent=True) or {}
    url = data.get("url", "")
    headers = data.get("headers", {})
    timeout = data.get("timeout", 10)

    if not url:
        return jsonify({"success": False, "error": "缺少 url 参数"}), 400

    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=False)
        ok = resp.status_code < 500 and resp.status_code not in (403, 404)
        return jsonify({
            "success": True,
            "url": url,
            "status": resp.status_code,
            "ok": ok,
            "server": resp.headers.get("Server", ""),
        })
    except requests.exceptions.SSLError as e:
        return jsonify({"success": False, "error": f"SSL错误: {e}"})
    except requests.exceptions.ConnectionError as e:
        return jsonify({"success": False, "error": f"连接错误: {e}"})
    except requests.exceptions.Timeout:
        return jsonify({"success": False, "error": "超时"})
    except Exception as e:
        return jsonify({"success": False, "error": f"异常: {e}"})

@app.route("/api/cloud/robot/status", methods=["GET"])
def cloud_robot_status():
    """家庭查询本家庭机器人状态（通过云端代理）"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    reg = robot_registry.get(family_id)
    if not reg:
        return jsonify({"success": True, "connected": False, "message": "本地客户端尚未上报机器人控制地址"})

    control_url = reg.get("control_url", "")
    if not control_url:
        return jsonify({"success": True, "connected": False, "message": "控制地址为空"})

    online = _robot_online(reg)
    if not online:
        return jsonify({
            "success": True,
            "connected": False,
            "message": "机器人已离线（心跳超时）",
            "registry": {
                "control_url": control_url,
                "last_heartbeat": reg.get("last_heartbeat"),
                "online": False,
            },
        })

    try:
        client = G1HTTPClient(base_url=control_url)
        health = client.health()
        capabilities = client.capabilities()
        return jsonify({
            "success": True,
            "connected": health.get("ok") is True,
            "health": health,
            "capabilities": capabilities,
            "registry": {
                "control_url": control_url,
                "last_heartbeat": reg.get("last_heartbeat"),
                "online": True,
            },
        })
    except Exception as e:
        return jsonify({
            "success": True,
            "connected": False,
            "error": str(e),
            "registry": {
                "control_url": control_url,
                "last_heartbeat": reg.get("last_heartbeat"),
                "online": True,
            },
        })


@app.route("/api/cloud/robot/action", methods=["POST"])
def cloud_robot_action():
    """云端直接向指定家庭的机器人下发动作指令"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401
    if not ROBOT_ACTION_LIMITER.is_allowed(family_id):
        return jsonify({"success": False, "error": "机器人动作太频繁，请稍后再试"}), 429

    data = request.get_json(silent=True) or {}
    action = data.get("action", "").strip()
    if not action:
        return jsonify({"success": False, "error": "缺少动作参数"}), 400

    reg = robot_registry.get(family_id)
    if not reg or not reg.get("control_url"):
        return jsonify({"success": False, "error": "本地机器人未注册，请确认本地客户端已启动并连接"}), 400

    try:
        client = G1HTTPClient(base_url=reg["control_url"])
        action_map = {
            "stand": "stand",
            "sit": "squat",
            "wave": "face_wave",
            "bow": "stand",
            "stop": "stop",
        }
        mapped = action_map.get(action, action)

        if mapped in G1HTTPClient.SAFE_ARM_ACTIONS:
            result = client.execute_arm_action(mapped)
        elif mapped in G1HTTPClient.SAFE_ACTIONS:
            result = client.execute_action(mapped)
        else:
            return jsonify({"success": False, "error": f"未知动作: {mapped}"}), 400

        log_admin("cloud_robot_action", f"family={family_id} action={mapped}")
        return jsonify({"success": True, "action": mapped, "result": result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"指令下发失败: {str(e)}"}), 500


# 机器人心跳超时判定（秒）
ROBOT_HEARTBEAT_TIMEOUT = 60


def _robot_online(reg: dict) -> bool:
    """根据最后心跳判断机器人是否在线"""
    if not reg:
        return False
    last = reg.get("last_heartbeat")
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.now() - last_dt).total_seconds() < ROBOT_HEARTBEAT_TIMEOUT
    except Exception:
        return False


@app.route("/api/cloud/robot/register", methods=["POST"])
def cloud_robot_register():
    """机器人端主动注册/更新本地控制地址（支持专线、公网、反向隧道）"""
    family_id, sub, krec, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data = request.get_json(silent=True) or {}
    control_url = (data.get("control_url") or "").strip()
    robot_id = (data.get("robot_id") or data.get("device_id") or "default").strip()
    token = (data.get("token") or "").strip()

    if not control_url:
        return jsonify({"success": False, "error": "缺少 control_url"}), 400

    robot_registry[family_id] = {
        "control_url": control_url,
        "robot_id": robot_id,
        "token": token,
        "last_heartbeat": datetime.now().isoformat(),
        "online": True,
        "registered_ip": _client_ip(),
    }
    save_robot_registry()
    log_admin("cloud_robot_register", f"family={family_id} robot={robot_id} url={control_url}")

    return jsonify({
        "success": True,
        "message": "机器人注册成功",
        "family_id": family_id,
        "robot_id": robot_id,
        "control_url": control_url,
        "online": True,
    })


@app.route("/api/cloud/robot/heartbeat", methods=["POST"])
def cloud_robot_heartbeat():
    """机器人端定时心跳"""
    family_id, sub, krec, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    reg = robot_registry.get(family_id)
    if not reg:
        return jsonify({"success": False, "error": "机器人尚未注册，请先调用 /api/cloud/robot/register"}), 400

    data = request.get_json(silent=True) or {}
    reg["last_heartbeat"] = datetime.now().isoformat()
    reg["online"] = True
    reg["last_ip"] = _client_ip()
    if "status" in data:
        reg["last_status"] = data["status"]
    save_robot_registry()

    return jsonify({
        "success": True,
        "online": True,
        "server_time": datetime.now().isoformat(),
    })


# ═══════════════════════════════════════════
# 省级管理中心接口（大客户/省份代理管理本省家庭）
# ═══════════════════════════════════════════

@app.route("/api/province-center/login", methods=["POST"])
def api_agent_login():
    """省级管理中心登录"""
    if not AGENT_LOGIN_LIMITER.is_allowed(_client_ip()):
        return jsonify({"success": False, "error": "登录太频繁，请稍后再试"}), 429
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"success": False, "error": "用户名和密码不能为空"}), 400
    result = login_agent(username, password)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 401


@app.route("/api/province-center/verify", methods=["GET"])
def api_agent_verify():
    """校验代理会话"""
    return jsonify(auth_agent())


@app.route("/api/province-center/families", methods=["GET"])
def api_agent_families():
    """代理查看自己辖区内的家庭列表"""
    agent = auth_agent()
    if not agent.get("valid"):
        return jsonify({"success": False, "error": "未登录"}), 401
    return jsonify({"success": True, "families": _list_families_for_agent(agent)})


@app.route("/api/province-center/family/<family_id>", methods=["GET"])
def api_agent_family_detail(family_id):
    """代理查看某个家庭的基本情况（不包含敏感档案）"""
    agent = auth_agent()
    if not agent.get("valid"):
        return jsonify({"success": False, "error": "未登录"}), 401
    data = load_cloud_family(family_id)
    if not data or not _family_in_agent_scope(data, agent):
        return jsonify({"success": False, "error": "无权查看或家庭不存在"}), 403

    safe = {
        "family_id": family_id,
        "name": data.get("name", "未命名家庭"),
        "province": data.get("province", ""),
        "city": data.get("city", ""),
        "town": data.get("town", ""),
        "contact_name": data.get("contact_name", ""),
        "contact_phone": data.get("contact_phone", ""),
        "member_count": len(data.get("members", [])),
        "children": [
            {"name": m.get("name"), "age": m.get("age"), "stage": m.get("stage", "")}
            for m in data.get("members", [])
            if m.get("role") == "孩子" and m.get("name")
        ],
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
    }
    sub = SUBSCRIPTIONS.get(family_id)
    if sub:
        safe["subscription"] = {
            "plan": sub.get("plan"),
            "expires": sub.get("expires"),
            "created_at": sub.get("created_at"),
            "keys_count": len(sub.get("keys", [])),
        }
    return jsonify({"success": True, "family": safe})


@app.route("/api/province-center/stats", methods=["GET"])
def api_agent_stats():
    """代理查看辖区统计"""
    agent = auth_agent()
    if not agent.get("valid"):
        return jsonify({"success": False, "error": "未登录"}), 401
    families = _list_families_for_agent(agent)
    stats = {
        "total": len(families),
        "by_city": {},
        "by_town": {},
        "active": 0,
        "expired": 0,
        "unknown": 0,
    }
    for f in families:
        city = f.get("city") or "未知"
        town = f.get("town") or "未知"
        stats["by_city"][city] = stats["by_city"].get(city, 0) + 1
        key = f"{city}/{town}"
        stats["by_town"][key] = stats["by_town"].get(key, 0) + 1
        sub = SUBSCRIPTIONS.get(f["family_id"])
        if sub:
            try:
                expires = datetime.strptime(sub.get("expires", ""), "%Y-%m-%d")
                if expires >= datetime.now():
                    stats["active"] += 1
                else:
                    stats["expired"] += 1
            except Exception:
                stats["unknown"] += 1
        else:
            stats["unknown"] += 1
    return jsonify({"success": True, "stats": stats})


@app.route("/api/province-center/subscriptions", methods=["GET"])
def api_agent_subscriptions():
    """代理查看辖区内家庭订阅/费用情况"""
    agent = auth_agent()
    if not agent.get("valid"):
        return jsonify({"success": False, "error": "未登录"}), 401
    families = _list_families_for_agent(agent)
    allowed_ids = {f["family_id"] for f in families}
    result = []
    for fid, sub in SUBSCRIPTIONS.items():
        if fid not in allowed_ids:
            continue
        result.append({
            "family_id": fid,
            "name": next((f.get("name", "") for f in families if f["family_id"] == fid), ""),
            "plan": sub.get("plan"),
            "expires": sub.get("expires"),
            "keys_count": len(sub.get("keys", [])),
        })
    return jsonify({"success": True, "subscriptions": result})


@app.route("/api/province-center/family", methods=["POST"])
def api_agent_create_family():
    """代理为本省新客户创建家庭"""
    agent = auth_agent()
    if not agent.get("valid"):
        return jsonify({"success": False, "error": "未登录"}), 401
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "家庭名称不能为空"}), 400

    family_id = "f_" + secrets.token_hex(8)
    family_data = {
        "family_id": family_id,
        "name": name,
        "province": agent.get("province", ""),
        "city": (data.get("city") or agent.get("city", "")).strip(),
        "town": (data.get("town") or agent.get("town", "")).strip(),
        "agent_id": agent.get("agent_id"),
        "contact_name": (data.get("contact_name") or "").strip(),
        "contact_phone": (data.get("contact_phone") or "").strip(),
        "members": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    if not save_cloud_family(family_id, family_data):
        return jsonify({"success": False, "error": "保存家庭信息失败"}), 500

    key = _gen_token()
    SUBSCRIPTIONS[family_id] = {
        "plan": data.get("plan", "standard"),
        "expires": data.get("expires", "2027-12-31"),
        "created_at": datetime.now().isoformat(),
        "keys": [{
            "key": key,
            "device_id": None,
            "device_ip": None,
            "activated_at": None,
            "status": "active",
        }],
    }
    save_subscriptions()
    log_admin("agent_create_family", f"agent={agent['username']} family={family_id}")
    return jsonify({"success": True, "family_id": family_id, "api_key": key})


@app.route("/api/province-center/family/<family_id>/renew", methods=["POST"])
def api_agent_renew_family(family_id):
    """代理为家庭续费或升级套餐"""
    agent = auth_agent()
    if not agent.get("valid"):
        return jsonify({"success": False, "error": "未登录"}), 401
    data = load_cloud_family(family_id)
    if not data or not _family_in_agent_scope(data, agent):
        return jsonify({"success": False, "error": "无权操作或家庭不存在"}), 403

    req = request.get_json(silent=True) or {}
    plan = req.get("plan")
    expires = req.get("expires")
    sub = SUBSCRIPTIONS.get(family_id)
    if not sub:
        sub = {
            "plan": plan or "standard",
            "expires": expires or "2027-12-31",
            "created_at": datetime.now().isoformat(),
            "keys": [],
        }
        SUBSCRIPTIONS[family_id] = sub
    if plan:
        sub["plan"] = plan
    if expires:
        sub["expires"] = expires
    save_subscriptions()
    log_admin("agent_renew_family", f"agent={agent['username']} family={family_id}")
    return jsonify({
        "success": True,
        "family_id": family_id,
        "subscription": {"plan": sub["plan"], "expires": sub["expires"]},
    })


@app.route("/api/province-center/family/<family_id>/key", methods=["GET", "POST"])
def api_agent_family_key(family_id):
    """代理获取/生成某个家庭的订阅密钥"""
    agent = auth_agent()
    if not agent.get("valid"):
        return jsonify({"success": False, "error": "未登录"}), 401
    data = load_cloud_family(family_id)
    if not data or not _family_in_agent_scope(data, agent):
        return jsonify({"success": False, "error": "无权操作或家庭不存在"}), 403

    sub = SUBSCRIPTIONS.setdefault(family_id, {
        "plan": "standard",
        "expires": "2027-12-31",
        "created_at": datetime.now().isoformat(),
        "keys": [],
    })
    key_rec = None
    for k in sub.get("keys", []):
        if k.get("status") == "active" and not k.get("device_id"):
            key_rec = k
            break
    if not key_rec:
        key_rec = {
            "key": _gen_token(),
            "device_id": None,
            "device_ip": None,
            "activated_at": None,
            "status": "active",
        }
        sub.setdefault("keys", []).append(key_rec)
        save_subscriptions()
    return jsonify({"success": True, "family_id": family_id, "key": key_rec["key"]})


# ═══════════════════════════════════════════
# 师父管理代理接口
# ═══════════════════════════════════════════

@app.route("/admin/province-centers", methods=["GET"])
def admin_list_agents():
    """师父查看所有省级管理中心"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute(
            "SELECT id, username, name, phone, province, city, town, status, created_at FROM agents ORDER BY id DESC"
        )
        agents = []
        for row in c.fetchall():
            agents.append({
                "id": row[0],
                "username": row[1],
                "name": row[2],
                "phone": row[3],
                "province": row[4],
                "city": row[5],
                "town": row[6],
                "status": row[7],
                "created_at": row[8],
            })
        return jsonify({"success": True, "agents": agents})
    finally:
        conn.close()


@app.route("/admin/province-centers", methods=["POST"])
def admin_create_agent():
    """师父创建省级管理中心"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"success": False, "error": "用户名和密码不能为空"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "密码至少6位"}), 400
    result = register_agent(
        username,
        password,
        name=data.get("name", ""),
        phone=data.get("phone", ""),
        province=data.get("province", ""),
        city=data.get("city", ""),
        town=data.get("town", ""),
    )
    if result.get("success"):
        log_admin("create_agent", username)
        return jsonify(result)
    return jsonify(result), 400


# ═══════════════════════════════════════════
# 师父控制台设备绑定 API
# ═══════════════════════════════════════════

@app.route("/api/master/verify", methods=["POST", "OPTIONS"])
def api_master_verify():
    """师父控制台登录校验：校验 master key + 设备绑定"""
    if request.method == "OPTIONS":
        return jsonify({"success": True}), 200

    data = request.get_json(silent=True) or {}
    machine_id = (
        data.get("machine_id")
        or request.headers.get("X-Machine-ID")
        or request.cookies.get("bookboy_master_machine_id", "")
        or ""
    ).strip()
    device_type = (data.get("device_type") or request.headers.get("X-Device-Type") or "computer").strip()

    ok, msg = auth_master_with_machine()
    if not ok:
        client_ip = _client_ip()
        print(f"[master_verify] 拒绝 {client_ip} machine_id={machine_id[:8]}... device_type={device_type}: {msg}")
        return jsonify({"success": False, "error": msg}), 403

    # 更新最近登录时间（已在 _validate_master_machine_id 中处理）
    return jsonify({
        "success": True,
        "machine_id": machine_id,
        "device_type": device_type,
        "message": "设备已授权",
    })


@app.route("/api/master/machine-ids", methods=["GET"])
def api_master_machine_ids():
    """列出师父控制台已绑定设备"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    current_machine_id = request.headers.get("X-Machine-ID", "")
    ids = _load_master_machine_ids()
    for item in ids:
        item["is_current"] = item.get("machine_id") == current_machine_id
    return jsonify({"success": True, "items": ids, "max_computers": 2, "max_phones": 1})


@app.route("/api/master/machine-ids/<machine_id>", methods=["DELETE"])
def api_master_unbind_machine(machine_id):
    """解绑指定设备"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401

    ids = _load_master_machine_ids()
    new_ids = [item for item in ids if item.get("machine_id") != machine_id]
    if len(new_ids) == len(ids):
        return jsonify({"success": False, "error": "未找到该设备"}), 404
    _save_master_machine_ids(new_ids)
    log_admin("unbind_master_machine", machine_id)
    return jsonify({"success": True, "message": "已解绑"})


PROVINCE_CONSOLE_HTML = (
    PROJECT_ROOT / "06-对接区" / "前端页面" / "省级管理中心.html"
    if (PROJECT_ROOT / "06-对接区" / "前端页面" / "省级管理中心.html").exists()
    else Path(__file__).parent / "省级管理中心.html"
)


@app.route("/province-center", methods=["GET"])
def province_center_console():
    """返回省级管理中心页面（页面本身公开，API 需代理登录）"""
    if PROVINCE_CONSOLE_HTML.exists():
        content = PROVINCE_CONSOLE_HTML.read_text(encoding="utf-8")
        return content, 200, {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        }
    return jsonify({"success": False, "error": "省级管理中心页面不存在"}), 404


# ═══════════════════════════════════════════
# 师父云端控制台页面
# ═══════════════════════════════════════════

MASTER_CONSOLE_HTML = (
    PROJECT_ROOT / "06-对接区" / "前端页面" / "云端师父控制台.html"
    if (PROJECT_ROOT / "06-对接区" / "前端页面" / "云端师父控制台.html").exists()
    else Path(__file__).parent / "云端师父控制台.html"
)

SALES_CENTER_HTML = (
    PROJECT_ROOT / "06-对接区" / "前端页面" / "销售中心.html"
    if (PROJECT_ROOT / "06-对接区" / "前端页面" / "销售中心.html").exists()
    else Path(__file__).parent / "销售中心.html"
)

FAMILY_PORTAL_HTML = (
    PROJECT_ROOT / "06-对接区" / "前端页面" / "书童家庭端.html"
    if (PROJECT_ROOT / "06-对接区" / "前端页面" / "书童家庭端.html").exists()
    else Path(__file__).parent / "书童家庭端.html"
)

FAMILY_MOBILE_HTML = (
    PROJECT_ROOT / "06-对接区" / "前端页面" / "书童手机端.html"
    if (PROJECT_ROOT / "06-对接区" / "前端页面" / "书童手机端.html").exists()
    else Path(__file__).parent / "书童手机端.html"
)

FAMILY_ACCESS_HTML = (
    PROJECT_ROOT / "06-对接区" / "前端页面" / "书童家庭访问入口.html"
    if (PROJECT_ROOT / "06-对接区" / "前端页面" / "书童家庭访问入口.html").exists()
    else Path(__file__).parent / "书童家庭访问入口.html"
)

USER_GUIDE_HTML = (
    PROJECT_ROOT / "06-对接区" / "前端页面" / "书童使用指南.html"
    if (PROJECT_ROOT / "06-对接区" / "前端页面" / "书童使用指南.html").exists()
    else Path(__file__).parent / "书童使用指南.html"
)


def send_static_file(path: Path, content_type=None):
    """发送静态文件"""
    if not path.exists() or not path.is_file():
        return jsonify({"success": False, "error": "文件不存在"}), 404

    ext = path.suffix.lower()
    mime_types = {
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".mp3": "audio/mpeg",
        ".ico": "image/x-icon",
    }
    content_type = content_type or mime_types.get(ext, "application/octet-stream")

    # 防止浏览器/中间代理缓存核心界面文件
    no_cache_exts = (".html", ".js", ".css", ".json")
    return path.read_bytes(), 200, {
        "Content-Type": content_type,
        "Cache-Control": "no-cache, no-store, must-revalidate" if ext in no_cache_exts else "public, max-age=86400",
        "Pragma": "no-cache" if ext in no_cache_exts else "",
        "Expires": "0" if ext in no_cache_exts else "",
    }


@app.route("/master", methods=["GET"])
def master_console():
    """返回云端师父控制台页面（已加 Basic Auth 锁定）"""
    auth_check = require_master_basic()
    if auth_check:
        return auth_check
    if MASTER_CONSOLE_HTML.exists():
        content = MASTER_CONSOLE_HTML.read_text(encoding="utf-8")
        return content, 200, {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    return jsonify({"success": False, "error": "师父控制台页面不存在"}), 404


@app.route("/sales-center", methods=["GET"])
def sales_center():
    """返回销售中心页面"""
    if SALES_CENTER_HTML.exists():
        content = SALES_CENTER_HTML.read_text(encoding="utf-8")
        return content, 200, {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    return jsonify({"success": False, "error": "销售中心页面不存在"}), 404


def _serve_family_html(html_path: Path, family_id: str = None) -> Response:
    """服务家庭端 HTML，可选注入固定家庭 ID"""
    if not html_path.exists():
        return jsonify({"success": False, "error": "家庭端页面不存在"}), 404
    content = html_path.read_text(encoding="utf-8")
    if family_id:
        # 注入 LOCKED_FAMILY_ID，让前端锁定到指定家庭
        injection = f"<script>window.LOCKED_FAMILY_ID = '{family_id}';</script>"
        # 插入到 </head> 前
        content = content.replace("</head>", injection + "\n</head>", 1)
    return content, 200, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }


@app.route("/family/<family_id>", methods=["GET"])
def family_portal(family_id):
    """家庭专属门户（登录后跳转到此）"""
    return _serve_family_html(FAMILY_PORTAL_HTML, family_id)


@app.route("/family-portal", methods=["GET"])
def family_portal_index():
    """家庭端首页：已登录则跳转到专属家庭门户"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else None
    if not token:
        token = request.cookies.get("bookboy_token")
    if token:
        session = verify_session(token)
        if session.get("valid") and session.get("family_id"):
            return redirect(f"/family/{session[family_id]}", code=302)
    return _serve_family_html(FAMILY_PORTAL_HTML)


@app.route("/family-mobile", methods=["GET"])
@app.route("/family-mobile/<family_id>", methods=["GET"])
def family_mobile(family_id=None):
    """家庭手机端（支持锁定到指定家庭）"""
    if not family_id:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else None
        if not token:
            token = request.cookies.get("bookboy_token")
        if token:
            session = verify_session(token)
            if session.get("valid") and session.get("family_id"):
                return redirect(f"/family-mobile/{session[family_id]}", code=302)
    return _serve_family_html(FAMILY_MOBILE_HTML, family_id)


@app.route("/family-access", methods=["GET"])
def family_access():
    """家庭访问入口"""
    return _serve_family_html(FAMILY_ACCESS_HTML)


@app.route("/user-guide", methods=["GET"])
def user_guide():
    """中英文使用指南（方便截图转发）"""
    if USER_GUIDE_HTML.exists():
        content = USER_GUIDE_HTML.read_text(encoding="utf-8")
        return content, 200, {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    return jsonify({"success": False, "error": "使用指南页面不存在"}), 404


@app.route("/static/<path:filename>", methods=["GET"])
def static_files(filename):
    """静态资源服务"""
    file_path = _safe_file_path(STATIC_DIR, filename)
    if file_path is None:
        return jsonify({"success": False, "error": "非法路径"}), 403
    return send_static_file(file_path)


@app.route("/audio/<path:filename>", methods=["GET"])
def audio_files(filename):
    """语音缓存文件服务（仅允许书童自有域名跨域播放）"""
    file_path = _safe_file_path(AUDIO_CACHE_DIR, filename)
    if file_path is None:
        return jsonify({"success": False, "error": "非法路径"}), 403
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"success": False, "error": "音频不存在"}), 404
    content = file_path.read_bytes()
    origin = request.headers.get("Origin", "")
    allowed_origins = {"https://bookkidai.com", "https://www.bookkidai.com", "http://bookkidai.com", "http://www.bookkidai.com"}
    cors_origin = origin if origin in allowed_origins else "https://bookkidai.com"
    return content, 200, {
        "Content-Type": "audio/mpeg",
        "Cache-Control": "public, max-age=86400",
        "Access-Control-Allow-Origin": cors_origin,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Vary": "Origin",
    }


@app.route("/admin", methods=["GET"])
def admin_redirect():
    """/admin 重定向到 /master"""
    from flask import redirect
    return redirect("/master")




@app.route("/downloads/<path:filename>", methods=["GET"])
def download_package(filename):
    """提供安装包下载（需师父管理密钥认证，安装包本身已 zip 加密）"""
    if not auth_master():
        return jsonify({"success": False, "error": "需要师父权限"}), 401
    file_path = _safe_file_path(DOWNLOADS_DIR, filename)
    if file_path is None:
        return jsonify({"success": False, "error": "非法路径"}), 403
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"success": False, "error": "文件不存在"}), 404
    from flask import send_file
    return send_file(
        file_path,
        as_attachment=True,
        download_name=file_path.name,
    )


# ═══════════════════════════════════════════
# 健康检查与首页
# ═══════════════════════════════════════════

@app.route("/", methods=["GET"])
def index():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>伴读书童AI</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:linear-gradient(135deg,#f5f0e8 0%,#e8dfd3 100%);min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px}
.card{background:#fff;border-radius:24px;box-shadow:0 8px 32px rgba(0,0,0,0.1);padding:48px 40px;max-width:420px;width:100%;text-align:center}
.logo{width:80px;height:80px;background:#8B7355;border-radius:50%;margin:0 auto 20px;display:flex;align-items:center;justify-content:center;overflow:hidden;box-shadow:0 4px 16px rgba(61,50,41,0.12)}
.logo img{width:100%;height:100%;object-fit:cover}
h1{font-size:24px;color:#3d2b1f;margin-bottom:8px}
p{font-size:14px;color:#8c7a6b;margin-bottom:32px;line-height:1.6}
.btn{display:block;width:100%;padding:14px;border:none;border-radius:12px;font-size:16px;cursor:pointer;text-decoration:none;margin-bottom:12px;transition:all 0.2s}
.btn-primary{background:#8B7355;color:#fff}
.btn-primary:hover{background:#7a6348}
.btn-outline{background:transparent;color:#8B7355;border:2px solid #8B7355}
.btn-outline:hover{background:#f5f0e8}
.footer{margin-top:20px;font-size:12px;color:#b8a89a}
</style>
</head><body>
<div class="card">
<div class="logo"><img src="/static/书童头像.jpg" alt="书童" onerror="this.style.display='none';this.parentNode.innerHTML='📚'"></div>
<h1>伴读书童AI</h1>
<p>陪伴亿万孩子，守护他们的0-18岁</p>
<a href="/register" class="btn btn-primary">注册新家庭</a>
<a href="/login" class="btn btn-outline">家长登录</a>
<div class="footer">书童正在等你来</div>
</div>
</body></html>"""


@app.route("/register", methods=["GET"])
def register_page():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>注册 · 伴读书童AI</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:linear-gradient(135deg,#f5f0e8 0%,#e8dfd3 100%);min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px}
.card{background:#fff;border-radius:24px;box-shadow:0 8px 32px rgba(0,0,0,0.1);padding:40px;max-width:420px;width:100%}
h1{font-size:22px;color:#3d2b1f;margin-bottom:24px;text-align:center}
.input-group{margin-bottom:16px;text-align:left}
label{display:block;font-size:13px;color:#6b5d4f;margin-bottom:4px}
input{width:100%;padding:12px;border:1px solid #ddd;border-radius:8px;font-size:15px;outline:none}
input:focus{border-color:#8B7355}
.btn{width:100%;padding:14px;border:none;border-radius:12px;font-size:16px;cursor:pointer;background:#8B7355;color:#fff;transition:all 0.2s}
.btn:hover{background:#7a6348}
.error{color:#d32f2f;font-size:13px;margin-top:8px;display:none}
.success{color:#2e7d32;font-size:14px;margin-top:12px;display:none;text-align:center}
.link{text-align:center;margin-top:16px;font-size:13px}
.link a{color:#8B7355;text-decoration:none}
</style>
</head><body>
<div class="card">
<div style="width:64px;height:64px;border-radius:50%;overflow:hidden;margin:0 auto 16px;background:#8B7355;box-shadow:0 4px 12px rgba(61,50,41,0.12);"><img src="/static/书童头像.jpg" alt="书童" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none';this.parentNode.innerHTML='📚'"></div>
<h1>注册新家庭</h1>
<form id="registerForm">
<div class="input-group"><label>邮箱</label><input type="email" id="email" placeholder="your@email.com" required></div>
<div class="input-group"><label>密码</label><input type="password" id="password" placeholder="至少6位" required></div>
<div class="input-group"><label>家庭名称</label><input type="text" id="family_name" placeholder="例如：张三家庭" required></div>
<div class="input-group"><label>联系人姓名</label><input type="text" id="contact_name" placeholder="真实姓名，用于审核" required></div>
<div class="input-group"><label>手机号</label><input type="tel" id="phone" placeholder="11位手机号" required></div>
<div class="input-group"><label>身份证号</label><input type="text" id="id_card" placeholder="18位身份证号码" required></div>
<div class="error" id="error"></div>
<div class="success" id="success"></div>
<button type="submit" class="btn" id="submitBtn">注册</button>
</form>
<div class="link">已有账号？<a href="/login">登录</a></div>
</div>
<script>
document.getElementById('registerForm').onsubmit=async function(e){
e.preventDefault();const btn=document.getElementById('submitBtn');btn.disabled=true;btn.textContent='注册中...';
document.getElementById('error').style.display='none';document.getElementById('success').style.display='none';
try{const r=await fetch('/api/account/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value,family_name:document.getElementById('family_name').value,contact_name:document.getElementById('contact_name').value,phone:document.getElementById('phone').value,id_card:document.getElementById('id_card').value})});const d=await r.json();if(d.success){const msg=d.pending_approval?('注册成功！您的家庭ID: '+d.family_id+'。请等待师父审核通过后再登录。'):('注册成功！您的家庭ID: '+d.family_id);document.getElementById('success').textContent=msg;document.getElementById('success').style.display='block';document.getElementById('submitBtn').textContent='注册成功';if(!d.pending_approval){setTimeout(()=>{window.location.href='/login'},2000)}else{btn.disabled=false;btn.textContent='注册成功，等待审核'}}else{document.getElementById('error').textContent=d.error;document.getElementById('error').style.display='block';btn.disabled=false;btn.textContent='注册'}}catch(e){document.getElementById('error').textContent='网络错误，请重试';document.getElementById('error').style.display='block';btn.disabled=false;btn.textContent='注册'}}
</script>
</div>
</body></html>"""

@app.route("/login", methods=["GET"])
def login_page():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录 · 伴读书童AI</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:linear-gradient(135deg,#f5f0e8 0%,#e8dfd3 100%);min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px}
.card{background:#fff;border-radius:24px;box-shadow:0 8px 32px rgba(0,0,0,0.1);padding:40px;max-width:420px;width:100%}
h1{font-size:22px;color:#3d2b1f;margin-bottom:24px;text-align:center}
.input-group{margin-bottom:16px;text-align:left}
label{display:block;font-size:13px;color:#6b5d4f;margin-bottom:4px}
input{width:100%;padding:12px;border:1px solid #ddd;border-radius:8px;font-size:15px;outline:none}
input:focus{border-color:#8B7355}
.btn{width:100%;padding:14px;border:none;border-radius:12px;font-size:16px;cursor:pointer;background:#8B7355;color:#fff;transition:all 0.2s;margin-bottom:8px}
.btn:hover{background:#7a6348}
.error{color:#d32f2f;font-size:13px;margin-top:8px;display:none}
.link{text-align:center;margin-top:16px;font-size:13px}
.link a{color:#8B7355;text-decoration:none}
</style>
</head><body>
<div class="card">
<div style="width:64px;height:64px;border-radius:50%;overflow:hidden;margin:0 auto 16px;background:#8B7355;box-shadow:0 4px 12px rgba(61,50,41,0.12);"><img src="/static/书童头像.jpg" alt="书童" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none';this.parentNode.innerHTML='📚'"></div>
<h1>家长登录</h1>
<form id="loginForm">
<div class="input-group"><label>账号（邮箱 / 家庭ID / 家庭名称）</label><input type="text" id="account" placeholder="例如：lanxin@bookkidai.com 或 family_lanxin 或 蓝心老师家庭" required></div>
<div class="input-group"><label>密码</label><input type="password" id="password" placeholder="输入密码" required></div>
<div class="error" id="error"></div>
<button type="submit" class="btn">登录</button>
</form>
<div class="link">没有账号？<a href="/register">注册</a></div>
</div>
<script>
document.getElementById('loginForm').onsubmit=async function(e){
e.preventDefault();document.getElementById('error').style.display='none';
try{const r=await fetch('/api/account/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account:document.getElementById('account').value,password:document.getElementById('password').value})});const d=await r.json();if(d.success){localStorage.setItem('bookboy_token',d.token);localStorage.setItem('bookboy_family_id',d.family_id);const isMobile=/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);const redirect=new URLSearchParams(window.location.search).get('redirect');if(redirect){if(redirect.startsWith('/login')){window.location.replace('/')}else{window.location.replace(redirect)}}else if(isMobile){window.location.replace('/family-mobile/'+d.family_id)}else{window.location.replace('/family/'+d.family_id)}}else{document.getElementById('error').textContent=d.error;document.getElementById('error').style.display='block'}}catch(e){document.getElementById('error').textContent='网络错误';document.getElementById('error').style.display='block'}}
</script>
</div>
</body></html>"""

@app.route("/api/client_error", methods=["POST"])
def api_client_error():
    """接收前端上报的客户端错误，方便外网调试"""
    try:
        data = request.get_json(silent=True) or {}
        error_info = {
            "time": datetime.now().isoformat(),
            "ip": _client_ip(),
            "ua": request.headers.get("User-Agent", ""),
            "url": data.get("url", ""),
            "message": data.get("message", ""),
            "stack": data.get("stack", ""),
            "source": data.get("source", ""),
            "line": data.get("line", ""),
            "col": data.get("col", ""),
        }
        log_path = CACHE_DIR / "client_errors.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(error_info, ensure_ascii=False) + "\n")
        print(f"[客户端错误] {error_info['message']} | {error_info['ua'][:60]}")
    except Exception as e:
        print(f"[客户端错误上报失败] {e}")
    return jsonify({"success": True})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "soul_version": soul_cache.get("version"),
        "soul_loaded_at": soul_cache.get("loaded_at"),
    })


# ═══════════════════════════════════════════
# 师父PC端兼容接口（需师父管理密钥或账号会话）
# ═══════════════════════════════════════════

@app.route("/api/voices", methods=["GET"])
def api_voices():
    """返回可用语音列表"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    voices = [
        {"name": "x6_tianjingshaonv_pro", "display": "天津少女", "locale": "zh-CN"},
        {"name": "zh-CN-XiaoxiaoNeural", "display": "晓晓", "locale": "zh-CN"},
        {"name": "zh-CN-YunxiNeural", "display": "云希", "locale": "zh-CN"},
        {"name": "zh-CN-liaoning-XiaobeiNeural", "display": "东北书童", "locale": "zh-CN-liaoning"},
        {"name": "zh-TW-HsiaoChenNeural", "display": "台湾书童", "locale": "zh-TW"},
        {"name": "zh-CN-shaanxi-XiaoniNeural", "display": "陕西书童", "locale": "zh-CN-shaanxi"},
        {"name": "zh-HK-HiuMaanNeural", "display": "粤语书童", "locale": "zh-HK"},
    ]
    return jsonify({"success": True, "voices": voices})


@app.route("/api/system_prompt", methods=["GET", "POST"])
def api_system_prompt():
    """读取/保存系统提示词（师父权限）"""
    if not auth_master():
        return jsonify({"success": False, "error": "需要师父权限"}), 403

    sp_path = SOUL_FILES["system_prompt"]
    if request.method == "GET":
        content = ""
        if sp_path.exists():
            try:
                content = sp_path.read_text(encoding="utf-8")
            except Exception as e:
                return jsonify({"success": False, "error": f"读取失败: {e}"}), 500
        return jsonify({"success": True, "system_prompt": content})

    data = request.get_json(silent=True) or {}
    content = data.get("system_prompt", "")
    try:
        sp_path.parent.mkdir(parents=True, exist_ok=True)
        sp_path.write_text(content, encoding="utf-8")
        # 刷新灵魂缓存
        load_soul()
        return jsonify({"success": True, "message": "已保存并刷新"})
    except Exception as e:
        return jsonify({"success": False, "error": f"保存失败: {e}"}), 500


@app.route("/api/files", methods=["GET", "POST"])
def api_files():
    """师父PC端文件浏览器：列目录 / 读文件 / 写文件"""
    if not auth_master():
        return jsonify({"success": False, "error": "需要师父权限"}), 403

    if request.method == "GET":
        path = request.args.get("path", ".")
        target = _safe_file_path(PROJECT_ROOT, path)
        if target is None:
            return jsonify({"success": False, "error": "非法路径"}), 400
        try:
            items = []
            if target.is_dir():
                for p in sorted(target.iterdir()):
                    try:
                        rel = str(p.relative_to(PROJECT_ROOT))
                    except ValueError:
                        rel = str(p)
                    items.append({
                        "name": p.name,
                        "path": rel,
                        "type": "dir" if p.is_dir() else "file",
                    })
            return jsonify({"success": True, "path": path, "items": items})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    data = request.get_json(silent=True) or {}
    action = data.get("action", "read")
    path = data.get("path", "")
    target = _safe_file_path(PROJECT_ROOT, path)
    if target is None:
        return jsonify({"success": False, "error": "非法路径"}), 400

    if action == "read":
        if not target.is_file():
            return jsonify({"success": False, "error": "文件不存在"}), 404
        try:
            return jsonify({"success": True, "path": path, "content": target.read_text(encoding="utf-8")})
        except Exception as e:
            return jsonify({"success": False, "error": f"读取失败: {e}"}), 500

    if action == "write":
        content = data.get("content", "")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return jsonify({"success": True, "path": path})
        except Exception as e:
            return jsonify({"success": False, "error": f"保存失败: {e}"}), 500

    return jsonify({"success": False, "error": "未知操作"}), 400


@app.route("/api/clear", methods=["POST"])
def api_clear_history():
    """清空指定家庭/孩子的对话历史"""
    family_id, _, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401
    data = request.get_json(silent=True) or {}
    child_id = data.get("child_id", "")
    path = _chat_history_path(family_id)
    try:
        if path.exists():
            path.unlink()
        return jsonify({"success": True, "family_id": family_id, "child_id": child_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/logs", methods=["GET"])
def api_logs():
    """读取云端服务日志（师父权限）"""
    if not auth_master():
        return jsonify({"success": False, "error": "需要师父权限"}), 403
    lines = int(request.args.get("lines", 300))
    log_candidates = [
        PROJECT_ROOT / "04-工作区" / "日志" / "pc端服务启动.log",
        PROJECT_ROOT / "04-工作区" / "书童运行日志.txt",
    ]
    for log_path in log_candidates:
        if log_path.exists():
            try:
                text = log_path.read_text(encoding="utf-8", errors="ignore")
                all_lines = text.splitlines()
                return jsonify({"success": True, "lines": all_lines[-lines:]})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": True, "lines": []})


# ═══════════════════════════════════════════
# 错误处理
# ═══════════════════════════════════════════

@app.errorhandler(Exception)
def handle_exception(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({"success": False, "error": e.description}), e.code
    traceback.print_exc()
    return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════
# 启动（模块级初始化，兼容 gunicorn 导入）
# ═══════════════════════════════════════════

print("=" * 60)
print("伴读书童AI · 云端服务")
print("=" * 60)

load_soul()
init_ability_engines()
load_robot_registry()

print(f"[云端] 管理密钥数: {len(MASTER_KEYS)}")
print(f"[云端] 订阅家庭数: {len(SUBSCRIPTIONS)}")
print("=" * 60)

if __name__ == "__main__":
    print(f"[云端] 监听地址: {HOST}:{PORT}")
    print(f"[云端] 调试模式: {DEBUG}")
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)

    print(f"[云端] 监听地址: {HOST}:{PORT}")
    print(f"[云端] 调试模式: {DEBUG}")
    print(f"[云端] 管理密钥数: {len(MASTER_KEYS)}")
    print(f"[云端] 订阅家庭数: {len(SUBSCRIPTIONS)}")
    print("=" * 60)

    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)
