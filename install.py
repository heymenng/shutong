#!/usr/bin/env python3
"""
伴读书童AI · 家庭安装脚本
一键安装：检查 Python、创建虚拟环境、安装依赖、创建启动器、生成配置文件
"""
import os
import sys
import json
import subprocess
import platform
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_DIR = PROJECT_ROOT / ".venv"
REQ_FILE = PROJECT_ROOT / "requirements.txt"
CONFIG_TEMPLATE = PROJECT_ROOT / "config.json.template"
CONFIG_FILE = PROJECT_ROOT / "config.json"
README_FILE = PROJECT_ROOT / "README_安装说明.md"


def run(cmd, cwd=None, check=True):
    print(f"[执行] {' '.join(str(c) for c in cmd)}")
    try:
        subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, check=check)
    except subprocess.CalledProcessError as e:
        print(f"[错误] 命令执行失败：{e}")
        sys.exit(1)


def load_manifest():
    manifest_path = PROJECT_ROOT / "manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def create_config():
    manifest = load_manifest()
    family_id = manifest.get("family_id")
    
    if CONFIG_FILE.exists():
        print(f"[OK] 配置文件已存在：{CONFIG_FILE}")
        if family_id:
            print(f"[提示] 本安装包已预配置 family_id: {family_id}")
            print("[提示] 请打开 config.json，只需填入 api_key（订阅密钥）")
        else:
            print("[提醒] 请打开 config.json 填入您的 family_id 和订阅密钥")
        return
    
    if CONFIG_TEMPLATE.exists():
        shutil.copy(CONFIG_TEMPLATE, CONFIG_FILE)
        print(f"[创建] {CONFIG_FILE}")
        if family_id:
            print(f"[提示] 本安装包已预配置 family_id: {family_id}")
            print("[提醒] 请打开 config.json，只需填入 api_key（订阅密钥）")
        else:
            print("[提醒] 请打开 config.json 填入您的 family_id 和订阅密钥")
    else:
        print("[警告] 未找到 config.json.template")


def create_mac_launcher():
    cmd_path = PROJECT_ROOT / "启动书童.command"
    content = f"""#!/bin/bash
# 伴读书童AI 一键启动器（Mac）
cd "{PROJECT_ROOT}"
"{VENV_DIR / 'bin' / 'python'}" start.py
"""
    cmd_path.write_text(content, encoding="utf-8")
    cmd_path.chmod(0o755)
    print(f"[创建] {cmd_path}")


def create_win_launcher():
    bat_path = PROJECT_ROOT / "启动书童.bat"
    content = f"""@echo off
REM 伴读书童AI 一键启动器（Windows）
cd /d "{PROJECT_ROOT}"
"{VENV_DIR / 'Scripts' / 'python.exe'}" start.py
pause
"""
    bat_path.write_text(content, encoding="utf-8")
    print(f"[创建] {bat_path}")


def show_readme():
    if README_FILE.exists():
        print("\n[文档] 详细说明请查看：README_安装说明.md\n")


def main():
    print("=" * 50)
    print("伴读书童AI · 家庭版安装")
    print("本地存数据，云端供智慧")
    print("=" * 50)

    # 检查 Python 版本
    if sys.version_info < (3, 9):
        print("[错误] 需要 Python 3.9 或更高版本，请访问 python.org 下载")
        sys.exit(1)
    print(f"[OK] Python {sys.version}")

    # 创建虚拟环境
    if not VENV_DIR.exists():
        print("[步骤] 创建虚拟环境...")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    else:
        print("[OK] 虚拟环境已存在")

    # 确定 pip 路径
    if platform.system() == "Windows":
        pip = VENV_DIR / "Scripts" / "pip.exe"
        python = VENV_DIR / "Scripts" / "python.exe"
    else:
        pip = VENV_DIR / "bin" / "pip"
        python = VENV_DIR / "bin" / "python"

    # 升级 pip
    print("[步骤] 升级 pip...")
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])

    # 安装依赖
    if REQ_FILE.exists():
        print("[步骤] 安装依赖...")
        run([str(pip), "install", "-r", str(REQ_FILE)])
    else:
        print("[警告] 未找到 requirements.txt")

    # 生成配置文件
    print("[步骤] 生成配置文件...")
    create_config()

    # 创建启动器
    print("[步骤] 创建启动器...")
    if platform.system() == "Windows":
        create_win_launcher()
    else:
        create_mac_launcher()

    print("\n" + "=" * 50)
    print("安装完成！")
    print("下一步：")
    print("  1. 打开 config.json，填入 family_id 和订阅密钥")
    print("  2. 双击运行启动器")
    if platform.system() == "Windows":
        print("  启动器：启动书童.bat")
    else:
        print("  启动器：启动书童.command")
    print("=" * 50)

    show_readme()


if __name__ == "__main__":
    main()
