"""伴读书童AI · 设置中心模块

按家庭存储轻量级偏好设置，如默认孩子、语音开关、界面语言等。
"""

import json
from pathlib import Path
from typing import Any, Dict

from ..工具.项目根目录 import get_project_root


DEFAULT_SETTINGS: Dict[str, Any] = {
    "voice_enabled": True,
    "auto_speak": True,
    "language": "zh",
    "default_child": "",
    "chat_mode": "child",  # child / parent / auto
    "theme": "light",
}


def _get_settings_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "settings.json"


def load_settings(data_dir: Path) -> Dict[str, Any]:
    """加载家庭设置，缺失项用默认值补齐"""
    path = _get_settings_path(data_dir)
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    settings = dict(DEFAULT_SETTINGS)
    settings.update(data)
    return settings


def save_settings(data_dir: Path, settings: Dict[str, Any]) -> Dict[str, Any]:
    """保存家庭设置，只保留已知键"""
    path = _get_settings_path(data_dir)
    current = load_settings(data_dir)
    for key in DEFAULT_SETTINGS:
        if key in settings:
            current[key] = settings[key]
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current
