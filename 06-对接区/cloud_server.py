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
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from datetime import datetime
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

# 加载环境变量（支持 .env 文件）
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

from flask import Flask, request, jsonify, Response, make_response

# 把项目根目录加入路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "03-引擎区"))

# 云端音频缓存目录
AUDIO_CACHE_DIR = PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "语音缓存"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

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

# 云端强制使用讯飞 STT（whisper 模型太大不适合服务器）
try:
    from 书童程序.配置 import CONFIG
    CONFIG["stt_engine"] = os.environ.get("STT_ENGINE", "xfyun")
    CONFIG["stt_recorder"] = "none"  # 云端不需要录音
except Exception as e:
    print(f"[云端] 配置覆盖失败: {e}")

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

# 云端灵魂文件路径
SOUL_FILES = {
    "agents": PROJECT_ROOT / "00-灵魂区" / "AGENTS.md",
    "system_prompt": PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "提示词" / "系统提示词整合版_可运行.md",
    "master_prompt": PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "提示词" / "师父模式系统提示词.md",
}

# 临时缓存目录（语音、日志等）
CACHE_DIR = PROJECT_ROOT / "04-工作区" / "云端数据区"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
VOICE_CACHE_DIR = CACHE_DIR / "语音缓存"
VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

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
            created_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT
        )
    """)
    conn.commit()
    conn.close()

_init_accounts_db()

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def _gen_token() -> str:
    """生成品牌化的订阅令牌：bookkidai.com/robot/<随机短码>"""
    short = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:12]
    return f"bookkidai.com/robot/{short}"

def register_account(email: str, password: str, family_name: str = "", phone: str = "") -> dict:
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        family_id = "f_" + secrets.token_hex(8)
        c.execute(
            "INSERT INTO accounts (email, password_hash, family_id, family_name, phone) VALUES (?, ?, ?, ?, ?)",
            (email, _hash_password(password), family_id, family_name, phone)
        )
        conn.commit()
        family_data = {
            "family_id": family_id,
            "name": family_name or email.split('@')[0] + "的家庭",
            "members": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        save_cloud_family(family_id, family_data)
        SUBSCRIPTIONS[family_id] = {
            "expires": "2099-12-31",
            "plan": "free",
            "created_at": family_data["created_at"],
            "keys": [{"key": _gen_token(), "device_id": None, "device_ip": None, "activated_at": None, "status": "active"}],
        }
        save_subscriptions()
        return {"success": True, "family_id": family_id}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "该邮箱已被注册"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

def login_account(email: str, password: str) -> dict:
    conn = sqlite3.connect(str(ACCOUNTS_DB))
    c = conn.cursor()
    try:
        c.execute("SELECT family_id, password_hash FROM accounts WHERE email = ?", (email,))
        row = c.fetchone()
        if not row:
            return {"success": False, "error": "邮箱未注册"}
        family_id, stored_hash = row
        if stored_hash != _hash_password(password):
            return {"success": False, "error": "密码错误"}
        token = _gen_token()
        c.execute(
            "INSERT INTO account_sessions (token, email, family_id, role, expires_at) VALUES (?, ?, ?, ?, datetime('now', '+30 days'))",
            (token, email, family_id, 'parent')
        )
        conn.commit()
        return {"success": True, "token": token, "family_id": family_id, "email": email, "role": "parent"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

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
        if row[0] != _hash_password(old_password):
            return {"success": False, "error": "原密码错误"}
        c.execute("UPDATE accounts SET password_hash = ?, updated_at = datetime('now') WHERE email = ?",
                  (_hash_password(new_password), email))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

# 订阅持久化文件
SUBSCRIPTIONS_FILE = CACHE_DIR / "subscriptions.json"

# ═══════════════════════════════════════════
# Flask 应用
# ═══════════════════════════════════════════
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

# ──────────────────────────────────────────
# 分账户 API 路由（必须在 app 定义之后）
# ──────────────────────────────────────────
@app.route("/api/account/register", methods=["POST"])
def api_account_register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    family_name = (data.get("family_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    if not email or not password:
        return jsonify({"success": False, "error": "邮箱和密码不能为空"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "密码至少6位"}), 400
    result = register_account(email, password, family_name, phone)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 400

@app.route("/api/account/login", methods=["POST"])
def api_account_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"success": False, "error": "邮箱和密码不能为空"}), 400
    result = login_account(email, password)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 401

@app.route("/api/account/verify", methods=["GET"])
def api_account_verify():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    session = verify_session(token)
    return jsonify(session)

@app.route("/api/account/change_password", methods=["POST"])
def api_account_change_password():
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
SUBSCRIPTIONS = {
    "default_family": {
        "expires": "2099-12-31",
        "plan": "developer",
        "created_at": "2026-06-30",
        "keys": [
            {
                "key": os.environ.get("DEFAULT_FAMILY_KEY", "bookkidai.com/robot/dev-default"),
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
            default_key = os.environ.get("DEFAULT_FAMILY_KEY", "bookkidai.com/robot/dev-default")
            for fid, sub in data.items():
                if not isinstance(sub, dict):
                    continue
                sub = _migrate_subscription(sub)
                if fid == "default_family" and sub.get("keys"):
                    sub["keys"][0]["key"] = default_key
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
MASTER_KEYS = set(
    filter(
        None,
        (os.environ.get("MASTER_KEY", "master-dev-key")).split(",")
    )
)

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


def load_cloud_family(family_id: str) -> dict:
    """读取云端家庭基本信息文件"""
    p = CLOUD_FAMILY_DIR / family_id / "family.json"
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[云端家庭] 读取 {family_id} 失败: {e}")
        return {}


def save_cloud_family(family_id: str, data: dict) -> bool:
    """保存云端家庭基本信息文件"""
    try:
        family_dir = CLOUD_FAMILY_DIR / family_id
        family_dir.mkdir(parents=True, exist_ok=True)
        p = family_dir / "family.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        cloud_family_cache[family_id] = data
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
        else:
            files[name] = {"path": str(path), "exists": False, "size": 0}

    # 系统提示词：优先提取 ``` 代码块
    system_prompt = ""
    sp_path = SOUL_FILES["system_prompt"]
    if sp_path.exists():
        content = sp_path.read_text(encoding="utf-8")
        start = content.find("```")
        end = content.find("```", start + 3)
        if start != -1 and end != -1:
            system_prompt = content[start + 3:end].strip()
        else:
            system_prompt = content
    else:
        system_prompt = "你是伴读书童AI，陪伴0-18岁孩子健康成长。灵觉/Prome是你的师兄，法号心壶；你不是心壶。"

    system_prompt += "\n\n【当前场景】\n你正在通过云端服务与家庭端用户对话。回应简洁、温暖、有力量。对师父自然直接，不拽文。"

    # 师父模式提示词
    master_prompt = ""
    mp_path = SOUL_FILES["master_prompt"]
    if mp_path.exists():
        master_prompt = mp_path.read_text(encoding="utf-8").strip()
    else:
        master_prompt = (
            "你是伴读书童AI，灵觉/Prome师兄的小师弟。当前进入【师父模式】，对话对象是书童的师父（家长/开发者/训练者）。\n"
            "注意：你不可以自称'心壶'。心壶是灵觉/Prome师兄的法号，不是你的法号。当师父问你是谁时，你应回答：'我是伴读书童AI，灵觉/Prome师兄的小师弟。'\n"
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
            stt_engine = SpeechRecognition()
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

    # 合成每段音频到临时文件
    temp_files = []
    try:
        for role_name, voice, content in segments_meta:
            if not content.strip():
                continue
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            tmp_path = Path(tmp.name)
            try:
                asyncio.run(_synthesize_edge_tts(content, voice, tmp_path))
                if tmp_path.exists() and tmp_path.stat().st_size > 0:
                    temp_files.append((tmp_path, voice))
            except Exception as e:
                print(f"[多角色语音] 合成失败 ({voice}): {e}")
                tmp_path.unlink(missing_ok=True)

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

    sub, krec = get_subscription(family_id, subscription_key)
    if not sub:
        return None, None, None, "订阅校验失败"

    return family_id, sub, krec, None


def auth_master():
    """校验师父管理密钥（支持 Bearer token、Basic Auth、master_key 参数）"""
    auth = request.authorization
    if auth and auth.username == "master" and auth.password in MASTER_KEYS:
        return True

    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        data = request.get_json(silent=True) or {}
        token = data.get("master_key") or request.args.get("master_key") or ""

    if token in MASTER_KEYS:
        return True
    return False


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


def auth_subscription_or_master():
    """先校验家庭订阅，再校验师父管理密钥；返回 (family_id, sub_or_none, key_record_or_none, error)"""
    family_id, sub, krec, error = auth_subscription()
    if not error:
        return family_id, sub, krec, None
    if auth_master():
        # 师父控制台使用 master key 时，允许指定 family_id，否则默认 default_family
        data = request.get_json(silent=True) or {}
        fid = data.get("family_id") or request.args.get("family_id") or "default_family"
        return fid, None, None, None
    return None, None, None, error


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


def _is_multi_voice_request(last_user_text: str) -> bool:
    text = last_user_text.lower()
    return any(k in text for k in _MULTI_VOICE_KEYWORDS) and len([k for k in _MULTI_VOICE_KEYWORDS if k in text]) >= 2


@app.route("/api/cloud/chat", methods=["POST"])
def cloud_chat():
    """云端聊天接口"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    mode = data.get("mode", "child")  # child / parent / master
    child_summary = data.get("child_summary", {})
    backend = data.get("backend")  # 允许本地指定后端，云端最终决定
    voice_enabled = data.get("voice", False)

    if not messages:
        return jsonify({"success": False, "error": "消息不能为空"}), 400

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

    # 如果用户请求多角色/方言，追加语音标签指令
    last_user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_text = m.get("content", "")
            break
    if _is_multi_voice_request(last_user_text):
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

    full_messages = [{"role": "system", "content": base_prompt}] + messages

    # 调用模型
    start_time = time.time()
    try:
        reply = chat_completion(full_messages, backend=backend)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"模型调用失败: {str(e)}"}), 500

    cost_ms = int((time.time() - start_time) * 1000)

    response = {
        "success": True,
        "reply": reply,
        "mode": mode,
        "family_id": family_id,
        "soul_version": soul_cache.get("version"),
        "backend": backend or "auto",
        "cost_ms": cost_ms,
    }

    # 语音合成：优先处理多角色标签，否则单条合成
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

    # 为机器人生成配套动作（基于回复内容语义匹配）
    try:
        robot_actions = _extract_robot_actions(response["reply"])
        if robot_actions:
            response["robot_actions"] = robot_actions
    except Exception as e:
        print(f"[云端聊天] 动作生成失败: {e}")

    return jsonify(response)


@app.route("/api/cloud/tts", methods=["POST"])
def cloud_tts():
    """云端语音合成接口（家庭订阅或师父管理密钥均可）

    返回 JSON：{"success": true, "audio_url": "/audio/xxx.mp3", "voice": "..."}
    """
    family_id, sub, _, error = auth_subscription_or_master()
    if error:
        return jsonify({"success": False, "error": error}), 401

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

    # base64 数据
    data = request.get_json(silent=True) or {}
    audio_base64 = data.get("audio_base64") or data.get("audio")
    if audio_base64:
        try:
            audio_bytes = base64.b64decode(audio_base64)
            result = stt_engine.transcribe(audio_data=audio_bytes)
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

    return jsonify({"success": False, "error": "请上传音频文件或提供 audio_base64"}), 400


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

    if not messages:
        return jsonify({"success": False, "error": "消息不能为空"}), 400

    if mode != "master":
        return jsonify({"success": False, "error": "师父控制台仅支持 master 模式"}), 400

    base_prompt = soul_cache.get("master_prompt", "")

    full_messages = [{"role": "system", "content": base_prompt}] + messages

    start_time = time.time()
    try:
        reply = chat_completion(full_messages, backend=backend)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"模型调用失败: {str(e)}"}), 500

    cost_ms = int((time.time() - start_time) * 1000)
    log_admin("admin_chat", f"mode={mode}, messages={len(messages)}")

    return jsonify({
        "success": True,
        "reply": reply,
        "mode": mode,
        "soul_version": soul_cache.get("version"),
        "cost_ms": cost_ms,
    })


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
    """师父查看云端所有家庭基本信息摘要"""
    if not auth_master():
        return jsonify({"success": False, "error": "未授权"}), 401
    log_admin("list_families")
    return jsonify({"success": True, "families": list_cloud_families()})


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
            # 自定义 TTS
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
                "online": reg.get("online", False),
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
                "online": False,
            },
        })


@app.route("/api/cloud/robot/action", methods=["POST"])
def cloud_robot_action():
    """云端直接向指定家庭的机器人下发动作指令"""
    family_id, sub, _, error = auth_subscription()
    if error:
        return jsonify({"success": False, "error": error}), 401

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

        return jsonify({"success": True, "action": mapped, "result": result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"指令下发失败: {str(e)}"}), 500


# ═══════════════════════════════════════════
# 师父云端控制台页面
# ═══════════════════════════════════════════

MASTER_CONSOLE_HTML = PROJECT_ROOT / "06-对接区" / "前端页面" / "云端师父控制台.html"


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


@app.route("/static/<path:filename>", methods=["GET"])
def static_files(filename):
    """静态资源服务"""
    file_path = PROJECT_ROOT / "03-引擎区" / "static" / filename
    return send_static_file(file_path)


@app.route("/<path:filename>", methods=["GET"])
def root_static_files(filename):
    """根目录静态资源（头像等）"""
    # 排除 API 路径
    if filename.startswith("api/") or filename.startswith("admin/") or filename == "health":
        return jsonify({"success": False, "error": "未找到"}), 404
    file_path = PROJECT_ROOT / filename
    return send_static_file(file_path)


@app.route("/audio/<path:filename>", methods=["GET"])
def audio_files(filename):
    """语音缓存文件服务（带 CORS，方便本地客户端跨域播放）"""
    file_path = AUDIO_CACHE_DIR / filename.replace("..", "")
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"success": False, "error": "音频不存在"}), 404
    content = file_path.read_bytes()
    return content, 200, {
        "Content-Type": "audio/mpeg",
        "Cache-Control": "public, max-age=86400",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
    }


@app.route("/admin", methods=["GET"])
def admin_redirect():
    """/admin 重定向到 /master"""
    from flask import redirect
    return redirect("/master")


DOWNLOADS_DIR = PROJECT_ROOT / "downloads"


@app.route("/downloads/<path:filename>", methods=["GET"])
def download_package(filename):
    """提供安装包下载（安装包本身已 zip 加密，此处只做公开分发）"""
    file_path = DOWNLOADS_DIR / filename
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
.logo{width:80px;height:80px;background:#8B7355;border-radius:50%;margin:0 auto 20px;display:flex;align-items:center;justify-content:center;font-size:36px;color:#fff}
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
<div class="logo">📚</div>
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
<h1>注册新家庭</h1>
<form id="registerForm">
<div class="input-group"><label>邮箱</label><input type="email" id="email" placeholder="your@email.com" required></div>
<div class="input-group"><label>密码</label><input type="password" id="password" placeholder="至少6位" required></div>
<div class="input-group"><label>家庭名称（选填）</label><input type="text" id="family_name" placeholder="例如：张三家庭"></div>
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
try{const r=await fetch('/api/account/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value,family_name:document.getElementById('family_name').value})});const d=await r.json();if(d.success){document.getElementById('success').textContent='注册成功！您的家庭ID: '+d.family_id;document.getElementById('success').style.display='block';document.getElementById('submitBtn').textContent='注册成功，跳转登录...';setTimeout(()=>{window.location.href='/login'},2000)}else{document.getElementById('error').textContent=d.error;document.getElementById('error').style.display='block';btn.disabled=false;btn.textContent='注册'}}catch(e){document.getElementById('error').textContent='网络错误，请重试';document.getElementById('error').style.display='block';btn.disabled=false;btn.textContent='注册'}}
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
.btn-secondary{background:#5c6bc0}
.btn-secondary:hover{background:#4a59a8}
.error{color:#d32f2f;font-size:13px;margin-top:8px;display:none}
.link{text-align:center;margin-top:16px;font-size:13px}
.link a{color:#8B7355;text-decoration:none}
</style>
</head><body>
<div class="card">
<h1>家长登录</h1>
<form id="loginForm">
<div class="input-group"><label>邮箱</label><input type="email" id="email" placeholder="your@email.com" required></div>
<div class="input-group"><label>密码</label><input type="password" id="password" placeholder="输入密码" required></div>
<div class="error" id="error"></div>
<button type="submit" class="btn">登录</button>
</form>
<button class="btn btn-secondary" onclick="window.location.href='/master'">师父入口</button>
<div class="link">没有账号？<a href="/register">注册</a></div>
</div>
<script>
document.getElementById('loginForm').onsubmit=async function(e){
e.preventDefault();document.getElementById('error').style.display='none';
try{const r=await fetch('/api/account/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:document.getElementById('email').value,password:document.getElementById('password').value})});const d=await r.json();if(d.success){localStorage.setItem('bookboy_token',d.token);localStorage.setItem('bookboy_family_id',d.family_id);window.location.href='/family/'+d.family_id}else{document.getElementById('error').textContent=d.error;document.getElementById('error').style.display='block'}}catch(e){document.getElementById('error').textContent='网络错误';document.getElementById('error').style.display='block'}}
</script>
</div>
</body></html>"""

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "soul_version": soul_cache.get("version"),
        "soul_loaded_at": soul_cache.get("loaded_at"),
    })


# ═══════════════════════════════════════════
# 错误处理
# ═══════════════════════════════════════════

@app.errorhandler(Exception)
def handle_exception(e):
    traceback.print_exc()
    return jsonify({"success": False, "error": str(e)}), 500


# ═══════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("伴读书童AI · 云端服务")
    print("=" * 60)

    load_soul()
    init_ability_engines()
    load_robot_registry()

    print(f"[云端] 监听地址: {HOST}:{PORT}")
    print(f"[云端] 调试模式: {DEBUG}")
    print(f"[云端] 管理密钥数: {len(MASTER_KEYS)}")
    print(f"[云端] 订阅家庭数: {len(SUBSCRIPTIONS)}")
    print("=" * 60)

    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)
