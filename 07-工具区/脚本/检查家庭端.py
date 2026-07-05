#!/usr/bin/env python3
"""
书童家庭端发布前自动检查脚本。
每次改完 书童家庭端.html 后运行一次，避免让师父当测试员。
"""
import argparse
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
HTML_PATH = ROOT / "06-对接区" / "前端页面" / "书童家庭端.html"
COMMON_JS_PATH = ROOT / "03-引擎区" / "static" / "书童公共.js"
BASE_URL = "http://127.0.0.1:3876"


def check_static():
    """检查 HTML/JS 静态问题。"""
    print("== 静态检查 ==")
    if not HTML_PATH.exists():
        print(f"❌ 找不到文件: {HTML_PATH}")
        return False

    html = HTML_PATH.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    if not scripts:
        print("❌ 找不到 <script> 标签")
        return False
    script = scripts[-1]

    # 读取公共 JS，某些函数已迁移到公共脚本
    common_js = ""
    if COMMON_JS_PATH.exists():
        common_js = COMMON_JS_PATH.read_text(encoding="utf-8")

    ok = True

    # 1. id 一致性
    ids_used = set(re.findall(r"getElementById\(['\"](.+?)['\"]\)", html))
    ids_defined = set(re.findall(r'id=["\']([^"\']+)["\']', html))
    # chatAudioPlayer、audioBlockedHint 是动态创建的，允许缺失
    missing = ids_used - ids_defined - {"chatAudioPlayer", "audioBlockedHint"}
    if missing:
        print(f"❌ 使用了未定义的 id: {missing}")
        ok = False
    else:
        print("✅ 所有 getElementById 都有对应 id")

    # 2. 重复 id
    all_ids = re.findall(r'id=["\']([^"\']+)["\']', html)
    duplicates = {x for x in all_ids if all_ids.count(x) > 1}
    if duplicates:
        print(f"❌ 重复 id: {duplicates}")
        ok = False
    else:
        print("✅ 无重复 id")

    # 3. 关键函数存在（本页或公共脚本）
    key_funcs = [
        "sendMessage",
        "handleKeyDown",
        "switchRole",
        "playChatAudio",
        "synthesizeToUrl",
        "applyRoleVisibility",
    ]
    for fn in key_funcs:
        has_func = f"function {fn}" in script or f"function {fn}" in common_js or f"window.{fn}" in common_js
        has_click = f'onclick="{fn}' in html
        has_key = f'onkeydown="{fn}' in html
        if has_func or has_click or has_key:
            print(f"✅ {fn} 存在")
        else:
            print(f"❌ {fn} 缺失")
            ok = False

    # 4. 检查孤立代码块（函数体外有缩进的内容，粗略）
    # 把脚本按函数拆开后，检查顶层是否有大量缩进行
    top_level_lines = []
    in_function = False
    brace_depth = 0
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if re.match(r"^(async\s+)?function\s+\w+\s*\(", stripped):
            in_function = True
            brace_depth = stripped.count("{") - stripped.count("}")
            continue
        if in_function:
            brace_depth += stripped.count("{") - stripped.count("}")
            if brace_depth <= 0:
                in_function = False
            continue
        # 顶层代码
        if line.startswith("            ") and not line.startswith("        "):
            top_level_lines.append(stripped[:60])
    if top_level_lines:
        print(f"⚠️ 发现 {len(top_level_lines)} 行疑似孤立代码，请人工确认:")
        for line in top_level_lines[:5]:
            print(f"   {line}")
        # 不直接判失败，只警告

    return ok


def check_api():
    """检查后端接口。"""
    print("\n== 接口检查 ==")
    ok = True
    try:
        res = requests.get(f"{BASE_URL}/", timeout=10)
        if res.status_code == 200 and "书童家庭端" in res.text:
            print("✅ 家庭端页面可访问")
        else:
            print(f"❌ 家庭端页面异常: {res.status_code}")
            ok = False
    except Exception as e:
        print(f"❌ 家庭端页面访问失败: {e}")
        ok = False

    try:
        res = requests.get(f"{BASE_URL}/master", timeout=10)
        if res.status_code == 200:
            print("✅ 师父端页面可访问")
        else:
            print(f"❌ 师父端页面异常: {res.status_code}")
            ok = False
    except Exception as e:
        print(f"❌ 师父端页面访问失败: {e}")
        ok = False

    try:
        res = requests.get(f"{BASE_URL}/mobile", timeout=10)
        if res.status_code == 200 and "伴读书童" in res.text and "手机端" in res.text:
            print("✅ 手机端页面可访问")
        else:
            print(f"❌ 手机端页面异常: {res.status_code}")
            ok = False
    except Exception as e:
        print(f"❌ 手机端页面访问失败: {e}")
        ok = False

    try:
        res = requests.post(
            f"{BASE_URL}/api/chat",
            json={"message": "在吗", "child_id": "default", "mode": "child"},
            timeout=30,
        )
        data = res.json()
        if res.status_code == 200 and data.get("reply"):
            print(f"✅ /api/chat 正常，回复: {data['reply'][:20]}...")
        else:
            print(f"❌ /api/chat 异常: {res.status_code} {data}")
            ok = False
    except Exception as e:
        print(f"❌ /api/chat 请求失败: {e}")
        ok = False

    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", action="store_true", help="同时检查后端接口")
    args = parser.parse_args()

    static_ok = check_static()
    api_ok = check_api() if args.api else True

    print("\n== 结果 ==")
    if static_ok and api_ok:
        print("✅ 通过，可以让师父验收了")
        sys.exit(0)
    else:
        print("❌ 未通过，别叫师父来试")
        sys.exit(1)


if __name__ == "__main__":
    main()
