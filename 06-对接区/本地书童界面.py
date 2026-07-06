#!/usr/bin/env python3
"""
伴读书童AI · 本地Web对话界面
====================
师父专属的本地书童对话窗口。
不依赖 opencode，在浏览器里打开就能用。

启动方式:
    .venv/bin/python3 本地书童界面.py
    然后在浏览器打开: http://localhost:3876
"""

import base64
import json
import mimetypes
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
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

from 书童程序.核心.语言模型 import chat_completion, get_backend  # noqa: E402
from 书童程序.配置 import CONFIG  # noqa: E402

# ═══════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════
PORT = 3876
HOST = "127.0.0.1"
MAX_HISTORY = 10

PROMPTS_DIR = PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "提示词"
FAMILY_GROUP_DIR = PROJECT_ROOT / "04-工作区" / "档案区" / "家庭群"
STATIC_DIR = PROJECT_ROOT / "03-引擎区" / "static"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "系统提示词整合版_可运行.md"

# ═══════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════
children = {}
histories = {}
current_child_id = None
system_prompt = ""

# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def load_system_prompt():
    """加载书童系统提示词"""
    global system_prompt
    if SYSTEM_PROMPT_FILE.exists():
        content = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
        # 提取 ``` 之间的 system prompt
        start = content.find("```")
        end = content.find("```", start + 3)
        if start != -1 and end != -1:
            system_prompt = content[start+3:end].strip()
        else:
            system_prompt = content
    else:
        system_prompt = "你是伴读书童AI，陪伴0-18岁孩子健康成长。"
    # 追加当前场景说明
    system_prompt += "\n\n【当前场景】\n你正在通过本地Web界面与师父或孩子对话。回应简洁、温暖、有力量。对师父自然直接，不拽文。"


def load_children():
    """从 04-工作区/档案区/家庭群 下的 family.json 加载所有孩子"""
    global children, current_child_id
    if not FAMILY_GROUP_DIR.exists():
        return
    for family_json in FAMILY_GROUP_DIR.rglob("family.json"):
        try:
            family_data = json.loads(family_json.read_text(encoding="utf-8"))
            family_id = family_data.get("family_id", family_json.parent.name)
            for member in family_data.get("members", []):
                if member.get("role") != "孩子":
                    continue
                child_id = str(member.get("name", "")).strip()
                if not child_id:
                    continue
                children[child_id] = {
                    "id": child_id,
                    "name": child_id,
                    "age": member.get("age", "未知"),
                    "stage": member.get("stage", "未知"),
                    "grade": member.get("grade", "未知"),
                    "relation": member.get("relation", ""),
                    "status": "绿色",
                    "data": {"member": member, "family_id": family_id},
                }
                histories[child_id] = []
        except Exception as e:
            print(f"[加载家庭档案失败] {family_json}: {e}")
    if children:
        current_child_id = list(children.keys())[0]


def get_child_context(child_id):
    """获取孩子上下文摘要"""
    if not child_id or child_id not in children:
        return ""
    child = children[child_id]
    member = child["data"].get("member", {})
    name = member.get("name", child_id)
    age = member.get("age", "")
    stage = member.get("stage", "")
    grade = member.get("grade", "")
    quick_tips = member.get("quick_tips_child", [])
    welcome = member.get("welcome_child", "")

    context = f"\n【当前陪伴对象】\n姓名：{name}\n年龄：{age}岁\n阶段：{stage}\n年级：{grade}"
    if quick_tips:
        context += f"\n常用话题：{', '.join(quick_tips[:3])}"
    if welcome:
        context += f"\n欢迎语：{welcome}"
    context += "\n"
    return context


VISION_PROMPT = (
    "\n\n【图片/拍题答疑指令】\n"
    "用户可能上传了作业或题目照片。请像一位耐心的学习伙伴：\n"
    "1. 先肯定孩子愿意提问；\n"
    "2. 用孩子能听懂的话，逐步分析图片里的内容；\n"
    "3. 不要直接给出最终答案，而是给出思考方向或一个简单示例；\n"
    "4. 鼓励孩子自己再试一次，并问他“你想从哪一步开始？”"
)


def build_messages(child_id, user_message, image_data=None):
    """构建发送给LLM的消息列表，支持图片"""
    prompt = system_prompt + get_child_context(child_id)
    if image_data:
        prompt += VISION_PROMPT
    messages = [{"role": "system", "content": prompt}]
    history = histories.get(child_id, [])
    # 只保留最近 MAX_HISTORY 轮（历史消息为纯文本；当前图片仅参与当前轮）
    for h in history[-MAX_HISTORY:]:
        messages.append({"role": "user", "content": h["user"]})
        messages.append({"role": "assistant", "content": h["assistant"]})

    if image_data:
        content = [
            {"type": "text", "text": user_message or "请看看这张照片，帮我解答或讲解。"},
            {"type": "image_url", "image_url": {"url": image_data}},
        ]
    else:
        content = user_message
    messages.append({"role": "user", "content": content})
    return messages


def speak_text(text):
    """调用语音播报工具"""
    try:
        script = PROJECT_ROOT / "07-工具区" / "工具脚本" / "语音播报.py"
        if not script.exists():
            return False
        # 过滤掉 emoji 和特殊标记
        clean_text = text.replace("🟢", "").replace("🟡", "").replace("🟠", "").replace("🔴", "")
        clean_text = clean_text.replace("**", "").replace("#", "")
        subprocess.Popen(
            [str(PROJECT_ROOT / ".venv" / "bin" / "python3"), str(script), clean_text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        print(f"[语音播报失败] {e}")
        return False


# ═══════════════════════════════════════════
# HTTP 请求处理
# ═══════════════════════════════════════════

class BookboyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # 简化日志
        print(f"[本地书童] {self.address_string()} {format % args}")

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_static(self, content, content_type="text/html; charset=utf-8"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if isinstance(content, str):
            content = content.encode("utf-8")
        self.wfile.write(content)

    def _send_file(self, file_path: Path):
        """发送本地文件，自动判断 MIME"""
        if not file_path.exists():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _inject_avatar(self, html_content: str) -> str:
        """把 static/书童头像.jpg 以 base64 内嵌到 HTML"""
        avatar_path = STATIC_DIR / "书童头像.jpg"
        if not avatar_path.exists():
            return html_content
        try:
            avatar_b64 = base64.b64encode(avatar_path.read_bytes()).decode("utf-8")
            avatar_data_url = f"data:image/jpeg;base64,{avatar_b64}"
            script = f"<script>window.BOOKBOY_AVATAR = '{avatar_data_url}';</script>"
            html_content = html_content.replace("</head>", f"{script}\n</head>")
            # 替换顶部品牌图标里的默认卷轴 emoji
            html_content = html_content.replace(
                '<div class="brand-icon">📜</div>',
                f'<div class="brand-icon"><img src="{avatar_data_url}" alt="书童" style="width:100%;height:100%;object-fit:cover;border-radius:50%;"></div>'
            )
        except Exception:
            pass
        return html_content

    def do_GET(self):
        if self.path == "/":
            html_path = PROJECT_ROOT / "06-对接区" / "前端页面" / "本地书童界面.html"
            if html_path.exists():
                content = self._inject_avatar(html_path.read_text(encoding="utf-8"))
                self._send_static(content)
            else:
                self._send_json({"error": "前端文件不存在"}, 500)
        elif self.path == "/entry":
            # 本地完整模式下 /entry 就是主界面
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
        elif self.path.startswith("/static/"):
            file_path = STATIC_DIR / self.path[len("/static/"):]
            if file_path.exists() and file_path.is_file():
                self._send_file(file_path)
            else:
                self.send_error(404)
        elif self.path == "/avatar.jpg":
            avatar_path = STATIC_DIR / "书童头像.jpg"
            if avatar_path.exists():
                self._send_file(avatar_path)
            else:
                self.send_error(404)
        elif self.path == "/api/status":
            self._send_json({
                "children": list(children.values()),
                "current_child": current_child_id,
                "backend": get_backend(),
                "model": CONFIG.get("ollama_model") if get_backend() == "ollama" else CONFIG.get("openai_model"),
                "voice": CONFIG.get("voice_name"),
                "online": True,
                "histories": {k: len(v) for k, v in histories.items()},
            })
        else:
            self.send_error(404)

    def do_POST(self):
        global current_child_id
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}

        if self.path == "/api/chat":
            message = data.get("message", "").strip()
            image_data = data.get("image", "").strip()
            child_id = data.get("child_id") or current_child_id
            if not message and not image_data:
                self._send_json({"error": "消息或图片至少填一项"}, 400)
                return
            if child_id not in children:
                child_id = current_child_id
            
            # 构建消息并调用LLM
            messages = build_messages(child_id, message, image_data)
            reply = chat_completion(messages)
            
            # 记录历史（图片仅记占位，避免历史膨胀）
            history_user = message
            if image_data:
                history_user += " [图片]"
            if child_id not in histories:
                histories[child_id] = []
            histories[child_id].append({
                "user": history_user,
                "assistant": reply,
                "time": time.strftime("%H:%M"),
            })
            
            self._send_json({
                "reply": reply,
                "child_id": child_id,
                "backend": get_backend(),
                "has_image": bool(image_data),
            })

        elif self.path == "/api/speak":
            text = data.get("text", "").strip()
            if text:
                success = speak_text(text)
                self._send_json({"success": success})
            else:
                self._send_json({"error": "文本不能为空"}, 400)

        elif self.path == "/api/switch_child":
            child_id = data.get("child_id")
            if child_id in children:
                current_child_id = child_id
                self._send_json({
                    "current_child": current_child_id,
                    "child": children[child_id],
                })
            else:
                self._send_json({"error": "孩子不存在"}, 404)

        elif self.path == "/api/clear":
            child_id = data.get("child_id") or current_child_id
            if child_id in histories:
                histories[child_id] = []
            self._send_json({"success": True, "child_id": child_id})

        else:
            self._send_json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# ═══════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════

def main():
    print("=" * 60)
    print("  伴读书童AI · 本地Web对话界面")
    print("=" * 60)
    print("\n[初始化] 加载书童灵魂...")
    load_system_prompt()
    print(f"[初始化] 系统提示词已加载 ({len(system_prompt)} 字符)")
    
    print("[初始化] 加载孩子档案...")
    load_children()
    if children:
        for c in children.values():
            print(f"  · {c['name']} ({c['age']}岁, {c['stage']})")
    else:
        print("  未找到孩子档案")
    
    print(f"\n[启动] 书童正在开门迎客...")
    print(f"[地址] http://{HOST}:{PORT}")
    print(f"[后端] {get_backend()}")
    print("\n请在浏览器中打开上面的地址")
    print("按 Ctrl+C 停止\n")
    
    server = NoDNSHTTPServer((HOST, PORT), BookboyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[关闭] 书童去休息了")
        server.shutdown()


if __name__ == "__main__":
    main()
