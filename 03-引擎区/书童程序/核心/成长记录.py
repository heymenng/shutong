"""伴读书童AI · 成长记录模块

记录孩子成长中的小事：第一次、身高体重、童言童语、照片瞬间。
数据按家庭存储为 JSON，支持图文混排和简单时间轴。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..工具.项目根目录 import get_project_root


DEFAULT_CATEGORIES = {
    "milestone": {"label": "里程碑", "color": "#7a9e7e"},
    "quote": {"label": "童言童语", "color": "#d47268"},
    "photo": {"label": "精彩瞬间", "color": "#4a90a4"},
    "height": {"label": "身高体重", "color": "#8b7355"},
    "study": {"label": "学习进步", "color": "#b54a3f"},
    "other": {"label": "其他", "color": "#888888"},
}


def _get_growth_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "growth_records.json"


def load_records(data_dir: Path) -> Dict:
    """加载家庭成长记录"""
    path = _get_growth_path(data_dir)
    if not path.exists():
        return {"version": 1, "items": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "items": []}


def save_records(data_dir: Path, records: Dict):
    """保存家庭成长记录"""
    path = _get_growth_path(data_dir)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def list_records(data_dir: Path, limit: int = 50, category: Optional[str] = None) -> List[Dict]:
    """返回按时间倒序的成长记录"""
    records = load_records(data_dir)
    items = records.get("items", [])
    if category:
        items = [i for i in items if i.get("category") == category]
    items.sort(key=lambda x: x.get("date", "") + (x.get("created_at", "") or ""), reverse=True)
    return items[:limit]


def add_record(data_dir: Path, data: Dict, created_by: str = "") -> Dict:
    """新增成长记录"""
    records = load_records(data_dir)
    item = {
        "id": str(uuid.uuid4())[:8],
        "date": (data.get("date") or "").strip() or datetime.now().strftime("%Y-%m-%d"),
        "content": (data.get("content") or "").strip(),
        "category": data.get("category", "other"),
        "image": (data.get("image") or "").strip(),
        "tags": data.get("tags", []),
        "created_by": created_by,
        "created_at": datetime.now().isoformat(),
    }
    if not item["content"] and not item["image"]:
        raise ValueError("内容和图片至少填一个")
    if not isinstance(item["tags"], list):
        item["tags"] = [t.strip() for t in str(item["tags"]).split(",") if t.strip()]
    records["items"].append(item)
    save_records(data_dir, records)
    return item


def delete_record(data_dir: Path, record_id: str) -> bool:
    """删除成长记录"""
    records = load_records(data_dir)
    before = len(records.get("items", []))
    records["items"] = [i for i in records.get("items", []) if i.get("id") != record_id]
    save_records(data_dir, records)
    return len(records["items"]) < before


def get_stats(data_dir: Path) -> Dict:
    """返回成长记录统计"""
    records = load_records(data_dir)
    items = records.get("items", [])
    return {
        "total": len(items),
        "this_month": sum(
            1 for i in items
            if i.get("date", "").startswith(datetime.now().strftime("%Y-%m"))
        ),
        "categories": {cat: sum(1 for i in items if i.get("category") == cat) for cat in DEFAULT_CATEGORIES},
    }
