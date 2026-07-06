"""伴读书童AI · 家庭留言板模块

家庭成员之间可以互相留言，形成轻量级的家庭沟通空间。
数据按家庭存储为 JSON，支持新增、查看、删除留言。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ..工具.项目根目录 import get_project_root


def _get_bulletin_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "bulletin.json"


def load_messages(data_dir: Path) -> Dict:
    """加载家庭留言板"""
    path = _get_bulletin_path(data_dir)
    if not path.exists():
        return {"version": 1, "messages": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "messages": []}


def save_messages(data_dir: Path, bulletin: Dict):
    """保存家庭留言板"""
    path = _get_bulletin_path(data_dir)
    path.write_text(json.dumps(bulletin, ensure_ascii=False, indent=2), encoding="utf-8")


def list_messages(data_dir: Path, limit: int = 50) -> List[Dict]:
    """返回按时间倒序的留言"""
    bulletin = load_messages(data_dir)
    messages = bulletin.get("messages", [])
    messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return messages[:limit]


def add_message(data_dir: Path, data: Dict) -> Dict:
    """新增留言"""
    bulletin = load_messages(data_dir)
    text = (data.get("text") or "").strip()
    if not text:
        raise ValueError("留言内容不能为空")
    message = {
        "id": str(uuid.uuid4())[:8],
        "text": text,
        "author": (data.get("author") or "").strip() or "家人",
        "created_at": datetime.now().isoformat(),
    }
    bulletin["messages"].append(message)
    save_messages(data_dir, bulletin)
    return message


def delete_message(data_dir: Path, message_id: str) -> bool:
    """删除留言"""
    bulletin = load_messages(data_dir)
    before = len(bulletin.get("messages", []))
    bulletin["messages"] = [m for m in bulletin.get("messages", []) if m.get("id") != message_id]
    save_messages(data_dir, bulletin)
    return len(bulletin["messages"]) < before


def get_stats(data_dir: Path) -> Dict:
    """返回留言统计"""
    bulletin = load_messages(data_dir)
    messages = bulletin.get("messages", [])
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "total": len(messages),
        "today": sum(1 for m in messages if (m.get("created_at") or "").startswith(today)),
    }
