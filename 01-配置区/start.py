#!/usr/bin/env python3
"""
伴读书童AI · 一键启动脚本
启动本地服务，并自动打开浏览器
"""
import os
import sys
import time
import json
import webbrowser
import subprocess
import platform
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv():
    """从本地 .env 文件加载环境变量（用于 BOOKBOY_API_KEY 等敏感配置）。"""
    candidates = [
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / "01-配置区" / ".env",
    ]
    for env_path in candidates:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception as e:
                print(f"[配置] 读取 {env_path} 失败: {e}")


load_dotenv()


def _get_api_key(cfg):
    """优先从环境变量获取 api_key，其次 config.json。"""
    return os.environ.get("BOOKBOY_API_KEY", cfg.get("api_key", ""))


if platform.system() == "Windows":
    PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
else:
    PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"

URL = "http://127.0.0.1:3876"
LOCAL_HOST = "127.0.0.1"
PORT = "3876"
CONFIG_FILE = PROJECT_ROOT / "01-配置区" / "config.json"


def is_cloud_mode(cfg):
    """根据配置判断是否为云端模式"""
    cloud_api_base = cfg.get("cloud_api_base", "")
    api_key = _get_api_key(cfg)
    return (
        cloud_api_base
        and api_key
        and "订阅密钥" not in api_key
        and "请向师父" not in api_key
        and not api_key.startswith("__")
    )


def get_server_script(cfg):
    """根据配置选择启动的服务脚本"""
    if is_cloud_mode(cfg):
        return PROJECT_ROOT / "06-对接区" / "本地书童界面_云端版.py"
    return PROJECT_ROOT / "06-对接区" / "本地书童界面.py"


def check_config():
    if not CONFIG_FILE.exists():
        print("[错误] 未找到 config.json，请先运行 install.py 或手动创建")
        sys.exit(1)
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[错误] config.json 格式错误：{e}")
        sys.exit(1)

    family_id = cfg.get("family_id", "")
    api_key = _get_api_key(cfg)
    cloud_api_base = cfg.get("cloud_api_base", "")

    if not family_id or family_id == "default_family" or "您的家庭ID" in family_id:
        print("[警告] config.json 中的 family_id 尚未配置")
    if not api_key or "订阅密钥" in api_key or "请向师父" in api_key or api_key.startswith("__"):
        print("[警告] config.json 中的 api_key 尚未配置（请设置 01-配置区/.env 中的 BOOKBOY_API_KEY）")
        if cloud_api_base:
            print("[提示] 当前配置为云端模式，需要填写正确的 api_key 才能连接云端")
        else:
            print("[提示] 当前版本为本地完整版，可继续使用；云端版本需要密钥")
    elif cloud_api_base:
        print("[提示] 当前配置为云端模式，将连接云端书童服务")


def start_server():
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    server_script = get_server_script(cfg)

    print("[启动] 正在启动书童服务...")
    if is_cloud_mode(cfg):
        print(f"[启动] 云端模式：{cfg.get('cloud_api_base')}")
    else:
        print("[启动] 本地完整模式")

    if not PYTHON.exists():
        print("[错误] 未找到虚拟环境，请先运行 install.py 安装")
        sys.exit(1)
    if not server_script.exists():
        print(f"[错误] 未找到服务脚本：{server_script}")
        sys.exit(1)

    log_file = open(PROJECT_ROOT / "04-工作区" / "书童运行日志.txt", "a", encoding="utf-8")
    log_file.write(f"\\n===== 启动时间：{time.strftime('%Y-%m-%d %H:%M:%S')} =====\\n")
    proc = subprocess.Popen(
        [str(PYTHON), "-u", str(server_script)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    print(f"[OK] 服务进程已启动，PID: {proc.pid}")
    print(f"[OK] 服务脚本：{server_script.name}")
    return proc


def wait_for_server(timeout=30):
    import urllib.request
    print("[等待] 等待服务就绪...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            urllib.request.urlopen(URL, timeout=2)
            print("[OK] 服务已就绪")
            return True
        except Exception:
            time.sleep(1)
    print("[警告] 服务启动超时，请检查 书童运行日志.txt")
    return False


def verify_package_password():
    """如果安装包设置了启动密码，要求用户输入"""
    pwd_file = PROJECT_ROOT / ".package_password"
    if not pwd_file.exists():
        return True
    expected = pwd_file.read_text(encoding="utf-8").strip()
    if not expected:
        return True

    # 优先使用 tkinter 弹窗（双击启动时友好）
    try:
        import tkinter as tk
        from tkinter import simpledialog, messagebox
        root = tk.Tk()
        root.withdraw()
        password = simpledialog.askstring(
            "伴读书童AI",
            "请输入安装包启动密码：",
            show="*"
        )
        root.destroy()
        if password and password.strip() == expected:
            return True
        messagebox.showerror("密码错误", "安装包启动密码不正确，无法启动。")
        return False
    except Exception:
        pass

    # 回退到命令行输入
    try:
        password = input("请输入安装包启动密码: ").strip()
        if password == expected:
            return True
        print("[错误] 安装包启动密码不正确，无法启动。")
        return False
    except Exception:
        return False


def get_launch_url():
    """根据安装包类型决定启动后打开的默认页面"""
    manifest_path = PROJECT_ROOT / "manifest.json"
    family_id = "default_family"
    package_type = "full"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            family_id = manifest.get("family_id", family_id)
            package_type = manifest.get("package_type", "full")
        except Exception:
            pass

    base = f"http://{LOCAL_HOST}:{PORT}"
    if package_type == "parent":
        return f"{base}/family/{family_id}/parent"
    if package_type == "child":
        return f"{base}/family/{family_id}/child"
    if package_type == "mobile":
        return f"{base}/mobile/{family_id}"
    return f"{base}/entry"


def open_browser():
    url = get_launch_url()
    print(f"[打开] 正在打开浏览器：{url}")
    webbrowser.open(url)


def main():
    print("=" * 50)
    print("伴读书童AI · 一键启动")
    print("=" * 50)

    if not verify_package_password():
        sys.exit(1)

    check_config()
    proc = start_server()
    if wait_for_server():
        open_browser()

    print("\\n[提示] 服务正在后台运行")
    print("[提示] 请勿关闭此窗口，关闭此窗口将停止服务")
    print("[提示] 浏览器中可以正常使用了")

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\\n[停止] 正在停止服务...")
        proc.terminate()
        proc.wait()
        print("[OK] 服务已停止")


if __name__ == "__main__":
    main()
