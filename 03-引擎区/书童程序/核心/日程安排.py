"""伴读书童AI · 每日安排/日程模块

为孩子和家庭提供每日作息、学习、提醒的轻量级日程管理。
数据以 JSON 形式按家庭存储，支持打卡、重复（周几）、类型标签。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..工具.项目根目录 import get_project_root


DEFAULT_TYPES = {
    "study": {"label": "学习", "color": "#7a9e7e"},
    "rest": {"label": "休息", "color": "#8b7355"},
    "play": {"label": "玩耍", "color": "#d47268"},
    "sleep": {"label": "睡觉", "color": "#5a7a9c"},
    "chore": {"label": "家务", "color": "#c4a77d"},
    "sport": {"label": "运动", "color": "#b54a3f"},
}


def _get_schedule_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "schedule.json"


def load_schedule(data_dir: Path) -> Dict:
    """加载家庭的日程数据"""
    path = _get_schedule_path(data_dir)
    if not path.exists():
        return {"version": 1, "items": [], "history": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "items": [], "history": {}}


def save_schedule(data_dir: Path, schedule: Dict):
    """保存家庭的日程数据"""
    path = _get_schedule_path(data_dir)
    path.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _weekday_today() -> int:
    # Monday=0, Sunday=6
    return datetime.now().weekday()


def get_today_items(data_dir: Path) -> List[Dict]:
    """返回今天需要执行的日程项（按时间排序），并附上今日打卡状态"""
    schedule = load_schedule(data_dir)
    today = _today_str()
    weekday = _weekday_today()
    history = schedule.get("history", {}).get(today, {})
    items = []
    for item in schedule.get("items", []):
        days = item.get("days", [0, 1, 2, 3, 4, 5, 6])
        if weekday not in days:
            continue
        copy = dict(item)
        copy["checked"] = history.get(item.get("id"), False)
        items.append(copy)
    items.sort(key=lambda x: x.get("time", "00:00"))
    return items


def add_item(data_dir: Path, item: Dict) -> Dict:
    """新增日程项"""
    schedule = load_schedule(data_dir)
    new_item = {
        "id": str(uuid.uuid4())[:8],
        "time": item.get("time", "08:00"),
        "title": item.get("title", "").strip(),
        "type": item.get("type", "study"),
        "days": item.get("days", [0, 1, 2, 3, 4, 5, 6]),
        "note": item.get("note", "").strip(),
        "remind": item.get("remind", True),
    }
    if not new_item["title"]:
        raise ValueError("日程标题不能为空")
    schedule["items"].append(new_item)
    save_schedule(data_dir, schedule)
    return new_item


def update_item(data_dir: Path, item_id: str, updates: Dict) -> Optional[Dict]:
    """更新日程项"""
    schedule = load_schedule(data_dir)
    for item in schedule.get("items", []):
        if item.get("id") == item_id:
            if "title" in updates:
                item["title"] = updates["title"].strip()
            if "time" in updates:
                item["time"] = updates["time"]
            if "type" in updates:
                item["type"] = updates["type"]
            if "days" in updates:
                item["days"] = updates["days"]
            if "note" in updates:
                item["note"] = updates["note"].strip()
            if "remind" in updates:
                item["remind"] = bool(updates["remind"])
            save_schedule(data_dir, schedule)
            return item
    return None


def delete_item(data_dir: Path, item_id: str) -> bool:
    """删除日程项"""
    schedule = load_schedule(data_dir)
    before = len(schedule.get("items", []))
    schedule["items"] = [i for i in schedule.get("items", []) if i.get("id") != item_id]
    save_schedule(data_dir, schedule)
    return len(schedule["items"]) < before


def checkin_item(data_dir: Path, item_id: str, checked: bool = True) -> Optional[Dict]:
    """打卡/取消打卡某日程项"""
    schedule = load_schedule(data_dir)
    today = _today_str()
    if "history" not in schedule:
        schedule["history"] = {}
    if today not in schedule["history"]:
        schedule["history"][today] = {}
    schedule["history"][today][item_id] = bool(checked)
    save_schedule(data_dir, schedule)
    for item in get_today_items(data_dir):
        if item.get("id") == item_id:
            return item
    return None


def get_stats(data_dir: Path, days: int = 7) -> Dict:
    """返回最近 N 天打卡统计"""
    schedule = load_schedule(data_dir)
    history = schedule.get("history", {})
    return {
        "total_days": len(history),
        "today_checked": sum(1 for v in history.get(_today_str(), {}).values() if v),
        "today_total": len(get_today_items(data_dir)),
    }
