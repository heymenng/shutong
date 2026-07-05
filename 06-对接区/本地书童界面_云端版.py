#!/usr/bin/env python3
"""
伴读书童AI · 云端版本地服务壳
==========================
这是书童上云后的轻量本地服务端：
- 灵魂文件（提示词、AGENTS.md）不在本地，由云端提供
- AI 推理走云端 /api/cloud/chat
- 家庭隐私数据（档案、对话）保存在本地
- 语音合成可本地或云端

启动方式:
    .venv/bin/python3 本地书童界面_云端版.py

访问地址:
    本机:   http://127.0.0.1:3876
    局域网: http://<本机IP>:3876
"""

import base64
import json
import os
import re
import secrets
import socket
import sys
import time
import uuid
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime
import socketserver


class NoDNSHTTPServer(ThreadingHTTPServer):
    """避免 server_bind 中 socket.getfqdn() 做反向 DNS 导致启动卡住"""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port

# 把项目根目录加入路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "03-引擎区"))

from 书童程序.核心.语音模块 import VoiceEngine

try:
    from 书童程序.核心.机器人对接.G1_HTTP客户端 import G1HTTPClient
except Exception as _g1_err:
    G1HTTPClient = None
    print(f"[机器人] G1HTTPClient 导入失败: {_g1_err}")

# 摄像头支持
try:
    from 书童程序.核心.感官系统 import VisionSensor
    _vision_sensor = VisionSensor(journal_dir=PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "感官日志")
    print("[摄像头] VisionSensor 已初始化")
except Exception as _vision_err:
    _vision_sensor = None
    print(f"[摄像头] VisionSensor 初始化失败: {_vision_err}")

# ═══════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════
PORT = 3876
HOST = "0.0.0.0"
LOCAL_HOST = "127.0.0.1"

CONFIG_FILE = PROJECT_ROOT / "01-配置区" / "config.json"
FAMILY_DATA_DIR = PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "家庭"
STATIC_DIR = PROJECT_ROOT / "03-引擎区" / "static"
AUDIO_CACHE_DIR = PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "语音缓存"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 默认配置
DEFAULT_CONFIG = {
    "cloud_api_base": "https://bookkidai.com",
    "family_id": "default_family",
    "api_key": "bookkidai.com/robot/dev-default",
    "voice_enabled": True,
    "voice_backend": "xfyun_oral",
    "voice_name": "x6_tianjingshaonv_pro",
    "g1_control_url": "http://192.168.0.248:8888",
    "g1_http_enabled": True,
}


def load_config():
    """加载本地配置文件"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # 合并默认值
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception as e:
            print(f"[配置] 读取 config.json 失败: {e}，使用默认配置")
    return DEFAULT_CONFIG.copy()


CONFIG = load_config()

# 云端配置（本地模式：指向本地 cloud_server.py）
CLOUD_BASE = CONFIG.get("cloud_api_base", "http://127.0.0.1:5000").rstrip("/")
FAMILY_ID = CONFIG.get("family_id", "default_family")
API_KEY = CONFIG.get("api_key", "local-dev-key")


def get_device_id():
    """生成本机设备指纹（MAC + 机器名 + 安装目录哈希），用于云端一机一绑"""
    try:
        mac = uuid.getnode()
        hostname = socket.gethostname()
        install_path = str(PROJECT_ROOT)
        import hashlib
        raw = f"{mac}|{hostname}|{install_path}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    except Exception:
        return "unknown"


DEVICE_ID = get_device_id()

# 会话管理
sessions = {}

# 语音引擎
voice_engine = None

# G1 机器人客户端
g1_client = None


def init_g1_client(force: bool = False):
    """初始化 G1 机器人控制客户端（支持重复调用以自动重连）"""
    global g1_client
    if not G1HTTPClient:
        print("[机器人] G1HTTPClient 未加载，跳过初始化")
        return
    if g1_client and not force:
        return
    url = CONFIG.get("g1_control_url", "").strip() or os.environ.get("G1_CONTROL_URL", "").strip()
    token = CONFIG.get("g1_http_control_token", "").strip() or os.environ.get("G1_CONTROL_TOKEN", "")
    if not url:
        print("[机器人] 未配置 G1_CONTROL_URL，跳过初始化（如需接入请在 config.json 中设置 g1_control_url）")
        return
    try:
        g1_client = G1HTTPClient(base_url=url, token=token or None)
        health = g1_client.health()
        if health.get("ok"):
            print(f"[机器人] G1 控制客户端已连接: {url}")
        else:
            print(f"[机器人] G1 控制服务连接测试失败: {health.get('error', 'unknown')}")
            g1_client = None
    except Exception as e:
        print(f"[机器人] G1 初始化失败: {e}")
        g1_client = None


def _play_audio_on_g1(audio_url: str):
    """下载云端音频并推送到 G1 机器人扬声器播放"""
    if not g1_client:
        return
    import tempfile
    import urllib.request as req
    try:
        # 下载音频到临时文件
        suffix = ".mp3" if ".mp3" in audio_url.lower() else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
        req.urlretrieve(audio_url, tmp_path)
        # 调用 G1 HTTP 客户端播放（内部会转 PCM）
        result = g1_client.play_mp3_file(tmp_path, stream_id="bookboy_cloud_tts")
        if result.get("ok"):
            print(f"[机器人] 音频已推送播放: {audio_url}")
        else:
            print(f"[机器人] 音频推送失败: {result.get('error')}")
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    except Exception as e:
        print(f"[机器人] 音频下载/播放失败: {e}")


def init_voice_engine():
    """初始化本地语音引擎"""
    global voice_engine
    if CONFIG.get("voice_enabled", True):
        try:
            voice_engine = VoiceEngine()
            print(f"[语音] 本地语音引擎已初始化: {voice_engine.backend}")
        except Exception as e:
            print(f"[语音] 本地语音引擎初始化失败: {e}")


def cloud_request(path, data=None, method="POST", extra_headers=None, raw_body=None, content_type=None, timeout=120):
    """向云端发起请求"""
    url = f"{CLOUD_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
    }
    if extra_headers:
        headers.update(extra_headers)

    if raw_body is not None:
        body = raw_body
        if content_type:
            headers["Content-Type"] = content_type
    elif data is not None:
        body = json.dumps(data or {}, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    else:
        body = None

    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"success": False, "error": f"云端请求失败: {e.code}"}
    except Exception as e:
        return {"success": False, "error": f"云端连接失败: {str(e)}"}


def load_family_json(family_id):
    """加载本地家庭数据"""
    path = FAMILY_DATA_DIR / family_id / "family.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def save_family_json(family_id, data):
    """保存本地家庭数据"""
    try:
        family_dir = FAMILY_DATA_DIR / family_id
        family_dir.mkdir(parents=True, exist_ok=True)
        path = family_dir / "family.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[本地家庭] 保存失败: {e}")
        return False


def sync_family_from_cloud():
    """启动时从云端拉取家庭基本信息到本地"""
    print("[本地家庭] 正在从云端同步家庭基本信息...")
    resp = cloud_request(f"/api/cloud/family?family_id={FAMILY_ID}", method="GET")
    if not resp.get("success"):
        print(f"[本地家庭] 云端拉取失败: {resp.get('error')}")
        return False

    cloud_family = resp.get("family")
    if not cloud_family:
        print("[本地家庭] 云端暂无该家庭信息")
        return False

    local_family = load_family_json(FAMILY_ID)
    if local_family:
        print("[本地家庭] 本地已存在家庭数据，保留本地版本（如需覆盖请手动同步）")
        return True

    if save_family_json(FAMILY_ID, cloud_family):
        print(f"[本地家庭] 已从云端下载家庭信息: {cloud_family.get('name', FAMILY_ID)}")
        return True
    return False


def register_family_to_cloud():
    """将本地家庭基本信息注册/同步到云端"""
    family_data = load_family_json(FAMILY_ID)
    if not family_data:
        print("[本地家庭] 本地无家庭数据，无法同步到云端")
        return False

    # 上传家庭基本档案，不上传敏感隐私字段（详细对话、具体病历、家庭地址等）
    safe_data = {
        "family_id": family_data.get("family_id", FAMILY_ID),
        "name": family_data.get("name", ""),
        "description": family_data.get("description", ""),
        "notes": family_data.get("notes", ""),
        "welcome_parent": family_data.get("welcome_parent", ""),
        "quick_tips_parent": family_data.get("quick_tips_parent", []),
        "members": [
            {
                "user_id": m.get("user_id"),
                "name": m.get("name"),
                "role": m.get("role"),
                "relation": m.get("relation"),
                "age": m.get("age"),
                "stage": m.get("stage"),
                "welcome_child": m.get("welcome_child"),
                "quick_tips_child": m.get("quick_tips_child", []),
                "interests": m.get("interests", []),
                "gender": m.get("gender", ""),
            }
            for m in family_data.get("members", [])
        ],
        "created_at": family_data.get("created_at", datetime.now().isoformat()),
        "updated_at": family_data.get("updated_at", datetime.now().isoformat()),
    }

    resp = cloud_request("/api/cloud/register_family", {"family_data": safe_data})
    if resp.get("success"):
        print(f"[本地家庭] 已同步到云端: {resp.get('message')}")
        return True
    print(f"[本地家庭] 同步到云端失败: {resp.get('error')}")
    return False


# ═══════════════════════════════════════════
# HTTP 请求处理
# ═══════════════════════════════════════════

class BookBoyCloudHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 简化日志
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} {format % args}")

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_static(self, path, content_type=None, status=200, no_cache=False):
        if not path.exists():
            self.send_error(404)
            return

        content = path.read_bytes()
        ext = path.suffix.lower()
        if content_type is None:
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
            content_type = mime_types.get(ext, "application/octet-stream")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if no_cache or ext in (".html", ".js", ".css"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(content)

    def _get_request_json(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(body)
        except Exception:
            return {}

    def _inject_family_id(self, html_path, family_id):
        """向 HTML 注入锁定的家庭 ID"""
        content = html_path.read_text(encoding="utf-8")
        inject = f"<script>window.LOCKED_FAMILY_ID = '{family_id}'; window.CLOUD_MODE = true;</script>"
        content = content.replace("</head>", f"{inject}\n</head>")
        return self._inject_avatar(content)

    def _inject_avatar(self, html_content: str) -> str:
        """把 static/书童头像.jpg 以 base64 内嵌到 HTML，替换默认 emoji 头像占位"""
        avatar_path = PROJECT_ROOT / "03-引擎区/static/书童头像.jpg"
        if not avatar_path.exists():
            return html_content
        try:
            avatar_bytes = avatar_path.read_bytes()
            avatar_b64 = base64.b64encode(avatar_bytes).decode("utf-8")
            avatar_data_url = f"data:image/jpeg;base64,{avatar_b64}"
            avatar_html = f'<img src="{avatar_data_url}" alt="书童头像">'
            for placeholder in [
                '<span class="default-avatar">📜</span>',
                '<span class="default-avatar">📖</span>',
            ]:
                html_content = html_content.replace(placeholder, avatar_html)
            script = f"<script>window.BOOKBOY_AVATAR = '{avatar_data_url}';</script>"
            html_content = html_content.replace("</head>", f"{script}\n</head>")
        except Exception as e:
            print(f"[头像注入] 失败: {e}")
        return html_content

    def _parse_path(self):
        decoded = urllib.parse.unquote(self.path)
        parsed = urllib.parse.urlparse(decoded)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    def do_GET(self):
        global g1_client
        path, query = self._parse_path()

        # 首页
        if path == "/":
            self._send_json({
                "name": "伴读书童AI · 云端版本地服务壳",
                "family_id": FAMILY_ID,
                "cloud_api_base": CLOUD_BASE,
                "status": "running",
            })
            return

        # 家庭访问入口
        if path == "/entry":
            entry_path = PROJECT_ROOT / "06-对接区" / "前端页面" / "书童家庭访问入口.html"
            if entry_path.exists():
                self._send_static(entry_path, no_cache=True)
                return
            self.send_error(404)
            return

        # 健康检查
        if path == "/health":
            heartbeat = cloud_request("/api/cloud/heartbeat", data={"family_id": FAMILY_ID, "device_id": DEVICE_ID}, method="POST")
            self._send_json({
                "local": "ok",
                "cloud": heartbeat,
            })
            return

        # 本地家庭数据读取
        if path == "/api/family" or path.startswith("/api/family?"):
            family_id = query.get("family_id", [FAMILY_ID])[0]
            family_data = load_family_json(family_id)
            return self._send_json({
                "success": bool(family_data),
                "family_id": family_id,
                "family": family_data,
            })

        # 静态资源
        if path.startswith("/static/"):
            file_path = PROJECT_ROOT / path.lstrip("/")
            if file_path.exists() and file_path.is_file():
                self._send_static(file_path)
                return
            self.send_error(404)
            return

        # 摄像头拍照（实时画面）
        if path == "/camera.jpg":
            global _vision_sensor
            if _vision_sensor is None:
                return self._send_json({"error": "Camera not initialized"}, 503)
            try:
                import cv2
                frame = _vision_sensor.capture_frame(save=False)
                if frame is None:
                    return self._send_json({"error": "Failed to capture frame"}, 503)
                _, buf = cv2.imencode(".jpg", frame)
                if not _:
                    return self._send_json({"error": "JPEG encode failed"}, 500)
                data = buf.tobytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache, no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as e:
                return self._send_json({"error": str(e)}, 500)

        # 音频缓存
        if path.startswith("/audio/"):
            file_path = AUDIO_CACHE_DIR / path.replace("/audio/", "").replace("..", "")
            if file_path.exists() and file_path.is_file():
                self._send_static(file_path, content_type="audio/mpeg")
                return
            self.send_error(404)
            return

        # 家庭端页面（支持 /family/<id>、/family/<id>/parent、/family/<id>/child）
        m = re.match(r"^/family/([^/]+)(?:/(parent|child))?$", path)
        if m:
            family_id = urllib.parse.unquote(m.group(1))
            mode = m.group(2)
            html_path = PROJECT_ROOT / "06-对接区" / "前端页面" / "书童家庭端.html"
            if html_path.exists():
                content = html_path.read_text(encoding="utf-8")
                inject = f"<script>window.LOCKED_FAMILY_ID = '{family_id}'; window.CLOUD_MODE = true;"
                if mode:
                    inject += f" window.LOCKED_MODE = '{mode}';"
                inject += "</script>"
                content = content.replace("</head>", f"{inject}\n</head>")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
                return
            self.send_error(404)
            return

        # 手机端页面
        m = re.match(r"^/mobile/([^/]+)$", path)
        if m:
            family_id = m.group(1)
            html_path = PROJECT_ROOT / "06-对接区" / "前端页面" / "书童手机端.html"
            if html_path.exists():
                content = self._inject_family_id(html_path, family_id)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
                return
            self.send_error(404)
            return

        # 师父端页面
        m = re.match(r"^/master(?:/([^/]+))?$", path)
        if m:
            family_id = urllib.parse.unquote(m.group(1) or "") or FAMILY_ID
            html_path = PROJECT_ROOT / "06-对接区" / "前端页面" / "师父PC端.html"
            if html_path.exists():
                content = self._inject_family_id(html_path, family_id)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
                return
            self.send_error(404)
            return

        # 墨童（家长助手）页面
        m = re.match(r"^/motong(?:/([^/]+))?$", path)
        if m:
            family_id = urllib.parse.unquote(m.group(1) or "") or FAMILY_ID
            html_path = PROJECT_ROOT / "06-对接区" / "前端页面" / "墨童.html"
            if html_path.exists():
                content = self._inject_family_id(html_path, family_id)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
                return
            self.send_error(404)
            return

        # 书童头像图片（兼容 /avatar.jpg 和 /static/书童头像.jpg）
        if path in ("/avatar.jpg", "/static/书童头像.jpg"):
            avatar_path = PROJECT_ROOT / "03-引擎区/static/书童头像.jpg"
            if avatar_path.exists():
                self._send_static(avatar_path)
                return
            self.send_error(404)
            return

        # 系统状态（前端初始化用）
        if path == "/api/status" or path.startswith("/api/status?"):
            family_id = query.get("family_id", [FAMILY_ID])[0]
            family_data = load_family_json(family_id)
            children = []
            if family_data:
                for m in family_data.get("members", []):
                    if m.get("role") == "孩子":
                        children.append({
                            "id": m.get("user_id") or m.get("name"),
                            "name": m.get("name"),
                            "age": m.get("age", ""),
                            "stage": m.get("stage", ""),
                            "grade": m.get("grade", ""),
                            "relation": m.get("relation", ""),
                        })
            current_child = children[0]["id"] if children else None
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            session = sessions.get(token, {})
            robot_connected = False
            if not g1_client:
                init_g1_client()
            if g1_client:
                try:
                    robot_connected = g1_client.health().get("ok") is True
                except Exception:
                    g1_client = None
            return self._send_json({
                "children": children,
                "current_child": current_child,
                "session_child": session.get("child_id") or current_child,
                "backend": "cloud",
                "model": "deepseek-v4-flash",
                "voice": CONFIG.get("voice_name") if CONFIG else "x6_tianjingshaonv_pro",
                "voice_backend": CONFIG.get("voice_backend") if CONFIG else "xfyun_oral",
                "online": True,
                "require_login": False,
                "role": session.get("role", "adult"),
                "family_id": family_id,
                "has_avatar": (PROJECT_ROOT / "03-引擎区/static/书童头像.jpg").exists(),
                "robot_connected": robot_connected,
            })

        # 家庭列表（供无专属家庭时选择）
        if path == "/api/families":
            families = []
            if FAMILY_DATA_DIR.exists():
                for d in sorted(FAMILY_DATA_DIR.iterdir()):
                    if d.is_dir():
                        fd = load_family_json(d.name)
                        if fd:
                            families.append({
                                "family_id": d.name,
                                "name": fd.get("name") or d.name,
                            })
            return self._send_json({"success": True, "families": families})

        # 本地 HTML 文件
        html_path = PROJECT_ROOT / "06-对接区" / "前端页面" / path.lstrip("/")
        if not html_path.exists():
            html_path = PROJECT_ROOT / path.lstrip("/")
        if html_path.exists() and html_path.suffix == ".html":
            content = html_path.read_text(encoding="utf-8")
            content = self._inject_avatar(content)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
            return

        # 本地机器人状态查询
        if path == "/api/robot/status":
            if not g1_client:
                return self._send_json({"success": True, "connected": False, "message": "机器人未初始化"})
            try:
                health = g1_client.health()
                capabilities = g1_client.capabilities()
                return self._send_json({
                    "success": True,
                    "connected": health.get("ok") is True,
                    "health": health,
                    "capabilities": capabilities,
                    "control_url": g1_client.base_url,
                })
            except Exception as e:
                return self._send_json({"success": True, "connected": False, "error": str(e)})

        self.send_error(404)

    def do_POST(self):
        path, query = self._parse_path()

        # 语音识别：multipart 二进制数据，单独处理
        if path == "/api/stt":
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                return self._send_json({"success": False, "error": "未收到音频数据"}, 400)

            raw_body = self.rfile.read(content_length)
            cloud_resp = cloud_request(
                f"/api/cloud/stt?family_id={FAMILY_ID}",
                method="POST",
                raw_body=raw_body,
                content_type=content_type,
                timeout=60,
            )
            return self._send_json(cloud_resp)

        data = self._get_request_json()

        # 登录（云端版简化：本地不校验密码，由云端授权）
        if path == "/api/login":
            role = "adult"
            if data.get("password") == "master":
                role = "master"
            token = secrets.token_urlsafe(32)
            sessions[token] = {"role": role, "family_id": FAMILY_ID, "created_at": time.time()}
            return self._send_json({
                "success": True,
                "token": token,
                "role": role,
                "family_id": FAMILY_ID,
            })

        # 聊天：本地转发到云端
        if path == "/api/chat":
            mode = data.get("mode", "child")
            backend = data.get("backend")
            voice = data.get("voice", False)

            messages = data.get("messages", [])
            # 家庭端/手机端传的是单条 message，需要包装成 messages 列表
            if not messages:
                message_text = data.get("message", "").strip()
                image_data = data.get("image")
                if not message_text and not image_data:
                    return self._send_json({"success": False, "error": "消息不能为空"}, 400)
                user_content = message_text or ""
                if image_data:
                    # 简单图文：文字+图片一起发
                    user_content = [{"type": "text", "text": user_content or "请描述这张图片。"}]
                    user_content.append({"type": "image_url", "image_url": {"url": image_data}})
                messages = [{"role": "user", "content": user_content}]

            # 构造孩子上下文摘要（从本地 family.json）
            child_summary = {}
            child_id = data.get("child_id")
            family_data = load_family_json(FAMILY_ID)
            if family_data and child_id:
                members = family_data.get("members", [])
                for m in members:
                    if m.get("user_id") == child_id or m.get("name") == child_id:
                        child_summary = {
                            "name": m.get("name"),
                            "age": m.get("age"),
                            "stage": m.get("stage"),
                            "interests": m.get("interests", []),
                        }
                        break

            # 转发到云端
            cloud_resp = cloud_request("/api/cloud/chat", {
                "family_id": FAMILY_ID,
                "messages": messages,
                "mode": mode,
                "child_summary": child_summary,
                "backend": backend,
                "voice": voice,
            })

            # 把云端的相对音频 URL 补成绝对地址，方便本地界面直接播放
            if cloud_resp.get("success") and cloud_resp.get("audio_url", "").startswith("/"):
                cloud_resp["audio_url"] = CLOUD_BASE.rstrip("/") + cloud_resp["audio_url"]

            # 如果接入了 G1 机器人，自动执行动作 + 推送音频
            print(f"[机器人调试] g1_client={g1_client is not None}, available={g1_client.is_available() if g1_client else False}, success={cloud_resp.get('success')}")
            if g1_client and g1_client.is_available() and cloud_resp.get("success"):
                # 执行 robot_actions
                robot_actions = cloud_resp.pop("robot_actions", None)
                print(f"[机器人调试] robot_actions={robot_actions}")
                if robot_actions:
                    for act in robot_actions:
                        try:
                            ep = act.get("endpoint", "action")
                            ac = act.get("action", "")
                            if ep == "arm_action":
                                g1_client.execute_arm_action(ac)
                            else:
                                g1_client.execute_action(ac)
                            print(f"[机器人] 执行动作: {ep}/{ac}")
                        except Exception as e:
                            print(f"[机器人] 动作执行失败: {e}")
                # 推送音频到机器人扬声器
                audio_url = cloud_resp.get("audio_url", "")
                if audio_url:
                    try:
                        _play_audio_on_g1(audio_url)
                    except Exception as e:
                        print(f"[机器人] 音频推送失败: {e}")

            return self._send_json(cloud_resp)

        # 心跳代理
        if path == "/api/cloud/heartbeat":
            req_data = data.copy() if data else {}
            req_data.setdefault("family_id", FAMILY_ID)
            req_data.setdefault("device_id", DEVICE_ID)
            cloud_resp = cloud_request("/api/cloud/heartbeat", data=req_data, method="POST")
            return self._send_json(cloud_resp)

        # soul 版本代理
        if path == "/api/cloud/soul":
            cloud_resp = cloud_request("/api/cloud/soul", data={"family_id": FAMILY_ID}, method="GET")
            return self._send_json(cloud_resp)

        # 语音合成：带角色标签的请求直接走云端多角色合成；单条优先本地，失败回退云端
        if path == "/api/tts":
            text = data.get("text", "").strip()
            voice = data.get("voice")
            if not text:
                return self._send_json({"success": False, "error": "文本不能为空"}, 400)

            # 如果文本含角色标签，直接走云端（edge-tts 方言支持更好）
            if "【" in text and "】" in text:
                cloud_resp = cloud_request("/api/cloud/tts", {"text": text, "voice": voice})
                if cloud_resp.get("success") and cloud_resp.get("audio_url", "").startswith("/"):
                    cloud_resp["audio_url"] = CLOUD_BASE.rstrip("/") + cloud_resp["audio_url"]
                return self._send_json(cloud_resp)

            if voice_engine and voice_engine.backend:
                try:
                    output_path = voice_engine.synthesize_to_file(text)
                    if output_path:
                        import hashlib
                        cache_key = hashlib.md5(output_path.encode()).hexdigest()
                        cache_name = f"{cache_key}.mp3"
                        local_path = AUDIO_CACHE_DIR / cache_name
                        import shutil
                        shutil.copy(output_path, local_path)
                        return self._send_json({
                            "success": True,
                            "audio_url": f"/audio/{cache_name}",
                            "backend": voice_engine.backend,
                        })
                except Exception as e:
                    print(f"[本地TTS] 失败: {e}，尝试云端")

            # 云端 TTS（现在返回 JSON，内含 /audio/xxx.mp3）
            cloud_resp = cloud_request("/api/cloud/tts", {"text": text, "voice": voice})
            if cloud_resp.get("success") and cloud_resp.get("audio_url", "").startswith("/"):
                cloud_resp["audio_url"] = CLOUD_BASE.rstrip("/") + cloud_resp["audio_url"]
            return self._send_json(cloud_resp)

        # 保存家庭数据到本地，并同步基本信息到云端
        if path == "/api/family":
            family_data = data.get("data")
            if not family_data:
                return self._send_json({"success": False, "error": "缺少 data"}, 400)
            family_data["family_id"] = FAMILY_ID
            family_data["updated_at"] = datetime.now().isoformat()
            if not family_data.get("created_at"):
                family_data["created_at"] = family_data["updated_at"]

            if save_family_json(FAMILY_ID, family_data):
                # 异步上传基本信息到云端
                register_family_to_cloud()
                return self._send_json({
                    "success": True,
                    "family_id": FAMILY_ID,
                    "message": "已保存并同步到云端",
                })
            return self._send_json({"success": False, "error": "保存失败"}, 500)

        # 从云端同步家庭数据到本地
        if path == "/api/family/sync":
            result = sync_family_from_cloud()
            return self._send_json({
                "success": result,
                "family_id": FAMILY_ID,
                "message": "已从云端同步" if result else "同步失败或本地已存在",
            })

        # 切换当前孩子
        if path == "/api/switch_child":
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            session = sessions.get(token, {})
            child_id = data.get("child_id")
            session["child_id"] = child_id
            sessions[token] = session
            return self._send_json({
                "success": True,
                "current_child": child_id,
                "child": {"id": child_id, "name": child_id},
            })

        # 本地机器人动作控制（直接调用 G1，不绕云端）
        if path == "/api/robot/action":
            if not g1_client:
                return self._send_json({"success": False, "error": "机器人未初始化，请检查 G1_CONTROL_URL 配置"}, 503)
            action = data.get("action", "").strip()
            if not action:
                return self._send_json({"success": False, "error": "缺少动作参数"}, 400)
            try:
                if action in G1HTTPClient.SAFE_ARM_ACTIONS:
                    result = g1_client.execute_arm_action(action)
                elif action in G1HTTPClient.SAFE_ACTIONS:
                    result = g1_client.execute_action(action)
                else:
                    return self._send_json({"success": False, "error": f"未知或不安全的动作: {action}"}, 400)
                return self._send_json({"success": True, "action": action, "result": result})
            except Exception as e:
                return self._send_json({"success": False, "error": str(e)}, 500)

        self.send_error(404)


# ═══════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════

def main():
    print("=" * 60)
    print("伴读书童AI · 云端版本地服务壳")
    print("=" * 60)
    print(f"[本地] 家庭 ID: {FAMILY_ID}")
    print(f"[本地] 云端地址: {CLOUD_BASE}")
    print(f"[本地] 监听地址: {HOST}:{PORT}")
    print("=" * 60)

    init_voice_engine()
    init_g1_client()

    # 测试云端连接
    print("[本地] 正在连接云端...")
    heartbeat_data = {"family_id": FAMILY_ID, "device_id": DEVICE_ID}
    if g1_client and g1_client.base_url:
        heartbeat_data["robot_control_url"] = g1_client.base_url
    heartbeat = cloud_request("/api/cloud/heartbeat", data=heartbeat_data, method="POST")
    if heartbeat.get("success"):
        print(f"[本地] 云端连接成功，soul 版本: {heartbeat.get('soul_version')}")
        # 连接成功后，从云端同步家庭基本信息到本地
        sync_family_from_cloud()
    else:
        print(f"[本地] ⚠️ 云端连接失败: {heartbeat.get('error')}")
        print("[本地] 请检查 config.json 中的 cloud_api_base 和 api_key")

    server = NoDNSHTTPServer((HOST, PORT), BookBoyCloudHandler)
    print(f"[本地] 服务已启动: http://{LOCAL_HOST}:{PORT}")
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[本地] 服务已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
