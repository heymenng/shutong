#!/usr/bin/env python3
"""
伴读书童AI · 云端灵魂文件同步脚本

功能：
1. 从云端 /api/cloud/soul 获取当前灵魂版本与文件哈希
2. 与本地 00-灵魂区/AGENTS.md、03-引擎区/书童程序/数据/提示词/ 下的提示词文件比对
3. 若不一致，使用师父管理密钥（BOOKBOY_MASTER_KEY）从 /admin/soul 下载最新内容并覆盖本地
4. 同步完成后更新 03-引擎区/书童程序/数据/核心文件校验.json

用法：
    BOOKBOY_MASTER_KEY=xxx .venv/bin/python 07-工具区/脚本/同步云端灵魂文件.py

注意：
    本脚本只读云端元数据时不需要 master key；真正下载覆盖时需要。
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "01-配置区" / "config.json"
VERIFY_PATH = PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "核心文件校验.json"

SOUL_FILE_MAP = {
    "agents": PROJECT_ROOT / "00-灵魂区" / "AGENTS.md",
    "system_prompt": PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "提示词" / "系统提示词整合版_可运行.md",
    "master_prompt": PROJECT_ROOT / "03-引擎区" / "书童程序" / "数据" / "提示词" / "师父模式系统提示词.md",
}


def load_dotenv():
    """从本地 .env 文件加载环境变量，用于读取 BOOKBOY_MASTER_KEY 等敏感配置。"""
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
                print(f"[警告] 读取 {env_path} 失败: {e}")


def load_config():
    if not CONFIG_PATH.exists():
        print(f"[错误] 未找到配置文件: {CONFIG_PATH}")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def cloud_request(base_url: str, api_key: str, path: str, data: dict = None, method: str = "GET"):
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        if method.upper() == "GET":
            r = requests.get(url, headers=headers, params=data, timeout=15)
        else:
            r = requests.post(url, headers=headers, json=data, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def admin_request(base_url: str, master_key: str, path: str):
    url = f"{base_url.rstrip('/')}{path}"
    try:
        r = requests.get(url, auth=("master", master_key), timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def sha256_file(path: Path, full: bool = False) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    digest = h.hexdigest()
    return digest if full else digest[:16]


def sha256_text(text: str, full: bool = False) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest if full else digest[:16]


def main():
    load_dotenv()
    config = load_config()
    base_url = config.get("cloud_api_base", "https://bookkidai.com")
    api_key = os.environ.get("BOOKBOY_API_KEY", config.get("api_key", ""))
    family_id = config.get("family_id", "")
    master_key = os.environ.get("BOOKBOY_MASTER_KEY", "")

    if not api_key:
        print("[错误] config.json 中未配置 api_key")
        sys.exit(1)

    print(f"[云端灵魂同步] 云端: {base_url} | 家庭: {family_id}")

    # 1. 获取云端灵魂元数据
    soul_meta = cloud_request(base_url, api_key, "/api/cloud/soul", {"family_id": family_id}, "GET")
    if not soul_meta.get("success"):
        print(f"[错误] 无法获取云端灵魂版本: {soul_meta.get('error')}")
        sys.exit(1)

    cloud_version = soul_meta.get("version")
    cloud_files = soul_meta.get("files", {})
    print(f"[云端] 当前 soul 版本: {cloud_version}")

    # 2. 比对本地文件
    mismatches = []
    for file_type, local_path in SOUL_FILE_MAP.items():
        cloud_info = cloud_files.get(file_type)
        if not cloud_info:
            print(f"  [跳过] 云端未返回 {file_type} 元数据")
            continue

        if not local_path.exists():
            print(f"  [缺失] 本地文件不存在: {local_path}")
            mismatches.append((file_type, cloud_info, None))
            continue

        local_hash = sha256_file(local_path)
        cloud_hash = cloud_info.get("sha256")
        if local_hash != cloud_hash:
            print(f"  [不匹配] {file_type}")
            print(f"    云端: {cloud_hash} 大小 {cloud_info.get('size')}")
            print(f"    本地: {local_hash} 大小 {local_path.stat().st_size}")
            mismatches.append((file_type, cloud_info, local_hash))
        else:
            print(f"  [一致] {file_type} ({local_hash})")

    if not mismatches:
        print("[完成] 本地灵魂文件已与云端完全匹配")
        sys.exit(0)

    # 3. 需要下载更新
    if not master_key:
        print("\n[提示] 发现不一致，需要师父管理密钥（BOOKBOY_MASTER_KEY）才能从 /admin/soul 下载最新内容。")
        print("      请设置环境变量后重试，例如：")
        print("      BOOKBOY_MASTER_KEY=xxx .venv/bin/python 07-工具区/脚本/同步云端灵魂文件.py")
        sys.exit(2)

    print("\n[下载] 正在使用 master key 从云端下载最新灵魂文件...")
    updated = []
    for file_type, cloud_info, _ in mismatches:
        resp = admin_request(base_url, master_key, f"/admin/soul?type={file_type}")
        if not resp.get("success"):
            print(f"  [失败] {file_type}: {resp.get('error')}")
            continue

        content = resp.get("content")
        if content is None:
            print(f"  [失败] {file_type}: 云端未返回内容")
            continue

        local_path = SOUL_FILE_MAP[file_type]
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")

        # 校验下载后的哈希（云端使用 sha256 前 16 位）
        new_hash = sha256_file(local_path)
        if new_hash != cloud_info.get("sha256"):
            print(f"  [警告] {file_type}: 下载后哈希与云端不一致，可能传输出错")
            print(f"         云端: {cloud_info.get('sha256')} 本地: {new_hash}")
        else:
            full_hash = sha256_file(local_path, full=True)
            print(f"  [成功] {file_type} 已更新 ({new_hash})")
            updated.append((file_type, new_hash, full_hash))

    if not updated:
        print("[失败] 没有文件被更新")
        sys.exit(1)

    # 4. 更新核心文件校验.json
    if VERIFY_PATH.exists():
        try:
            verify_data = json.loads(VERIFY_PATH.read_text(encoding="utf-8"))
        except Exception:
            verify_data = {"version": "1.0", "algorithm": "sha256", "hashes": {}}
    else:
        verify_data = {"version": "1.0", "algorithm": "sha256", "hashes": {}}

    for file_type, new_hash, full_hash in updated:
        if file_type == "agents":
            verify_data["hashes"]["AGENTS.md"] = full_hash
        elif file_type == "workflow":
            verify_data["hashes"]["WORKFLOW.md"] = full_hash
        # system_prompt / master_prompt 不在该校验文件中，跳过

    verify_data["last_updated_by"] = f"cloud_sync_{cloud_version}"
    verify_data["last_updated_at"] = __import__("datetime").datetime.now().isoformat()
    VERIFY_PATH.write_text(json.dumps(verify_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[更新] 已写入校验文件: {VERIFY_PATH}")

    print("\n[完成] 云端灵魂文件同步结束")


if __name__ == "__main__":
    main()
