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

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 把项目根目录加入路径
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from 书童程序.核心.语言模型 import chat_completion, get_backend
from 书童程序.配置 import CONFIG

# ═══════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════
PORT = 3876
HOST = "127.0.0.1"
MAX_HISTORY = 10

PROMPTS_DIR = PROJECT_ROOT / "书童程序" / "数据" / "提示词"
CHILDREN_DIR = PROJECT_ROOT / "档案区" / "孩子档案"
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
    """加载所有孩子档案"""
    global children, current_child_id
    if not CHILDREN_DIR.exists():
        return
    for file_path in CHILDREN_DIR.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            info = data.get("档案信息", {})
            child_id = info.get("姓名") or file_path.stem
            children[child_id] = {
                "id": child_id,
                "name": info.get("姓名", child_id),
                "age": info.get("年龄", "未知"),
                "stage": info.get("发育阶段", "未知"),
                "grade": info.get("年级", "未知"),
                "relation": info.get("关系", ""),
                "status": data.get("预警状态", {}).get("当前级别", "绿色"),
                "data": data,
            }
            histories[child_id] = []
        except Exception as e:
            print(f"[加载档案失败] {file_path}: {e}")
    if children:
        current_child_id = list(children.keys())[0]


def get_child_context(child_id):
    """获取孩子上下文摘要"""
    if not child_id or child_id not in children:
        return ""
    child = children[child_id]
    info = child["data"].get("档案信息", {})
    name = info.get("姓名", child_id)
    age = info.get("年龄", "")
    stage = info.get("发育阶段", "")
    grade = info.get("年级", "")
    observation = child["data"].get("观察记录", {})
    personality = observation.get("性格特点", {}).get("具体表现", [])
    interests = observation.get("兴趣方向", [])
    preference = observation.get("交互表现", {}).get("偏好", "")

    context = f"\n【当前陪伴对象】\n姓名：{name}\n年龄：{age}岁\n阶段：{stage}\n年级：{grade}"
    if personality:
        context += f"\n性格：{', '.join(personality[:3])}"
    if interests:
        context += f"\n兴趣：{', '.join(interests[:3])}"
    if preference:
        context += f"\n偏好：{preference}"
    context += "\n"
    return context


def build_messages(child_id, user_message):
    """构建发送给LLM的消息列表"""
    messages = [{"role": "system", "content": system_prompt + get_child_context(child_id)}]
    history = histories.get(child_id, [])
    # 只保留最近 MAX_HISTORY 轮
    for h in history[-MAX_HISTORY:]:
        messages.append({"role": "user", "content": h["user"]})
        messages.append({"role": "assistant", "content": h["assistant"]})
    messages.append({"role": "user", "content": user_message})
    return messages


def speak_text(text):
    """调用语音播报工具"""
    try:
        script = PROJECT_ROOT / "工具脚本" / "语音播报.py"
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

    def do_GET(self):
        if self.path == "/":
            html_path = PROJECT_ROOT / "本地书童界面.html"
            if html_path.exists():
                self._send_static(html_path.read_text(encoding="utf-8"))
            else:
                self._send_json({"error": "前端文件不存在"}, 500)
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
            self._send_json({"error": "not found"}, 404)

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
            child_id = data.get("child_id") or current_child_id
            if not message:
                self._send_json({"error": "消息不能为空"}, 400)
                return
            if child_id not in children:
                child_id = current_child_id
            
            # 构建消息并调用LLM
            messages = build_messages(child_id, message)
            reply = chat_completion(messages)
            
            # 记录历史
            if child_id not in histories:
                histories[child_id] = []
            histories[child_id].append({
                "user": message,
                "assistant": reply,
                "time": time.strftime("%H:%M"),
            })
            
            self._send_json({
                "reply": reply,
                "child_id": child_id,
                "backend": get_backend(),
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
    
    server = ThreadingHTTPServer((HOST, PORT), BookboyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[关闭] 书童去休息了")
        server.shutdown()


if __name__ == "__main__":
    main()
