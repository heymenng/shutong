"""伴读书童AI - 用户偏好管理

管理用户持久化偏好，如：
- voice_reply_enabled: 是否默认用语音回复
- voice_name: 默认发音人
- text_reply_enabled: 是否同时显示文字

这些偏好保存在 书童程序/数据/用户偏好.json 中，
书童每次回应前会读取，确保体验一致。
"""

import json
from pathlib import Path
from typing import Any, Optional


PREFERENCES_FILE = Path(__file__).resolve().parents[1] / "数据" / "用户偏好.json"


class UserPreferences:
    """用户偏好管理器"""

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path or PREFERENCES_FILE
        self._data = self._load()

    def _load(self) -> dict:
        """从文件加载偏好"""
        if self.file_path.exists():
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return self._defaults()

    def _defaults(self) -> dict:
        """默认偏好"""
        return {
            "voice_reply_enabled": True,
            "text_reply_enabled": True,
            "voice_name": "x6_tianjingshaonv_pro",
            "voice_volume": 100,
            "voice_speed": 50,
            "created_at": None,
            "updated_at": None,
        }

    def _save(self):
        """保存偏好到文件"""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        self._data["updated_at"] = datetime.now().isoformat()
        if self._data.get("created_at") is None:
            self._data["created_at"] = self._data["updated_at"]
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """获取偏好项"""
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """设置偏好项"""
        self._data[key] = value
        self._save()

    def enable_voice_reply(self):
        """开启语音回复"""
        self.set("voice_reply_enabled", True)

    def disable_voice_reply(self):
        """关闭语音回复"""
        self.set("voice_reply_enabled", False)

    def is_voice_reply_enabled(self) -> bool:
        """是否启用语音回复"""
        return self.get("voice_reply_enabled", True)

    def is_text_reply_enabled(self) -> bool:
        """是否同时显示文字"""
        return self.get("text_reply_enabled", True)

    def all_preferences(self) -> dict:
        """返回所有偏好"""
        return dict(self._data)


# 全局偏好实例
_preferences = None


def get_preferences() -> UserPreferences:
    """获取全局用户偏好实例"""
    global _preferences
    if _preferences is None:
        _preferences = UserPreferences()
    return _preferences


def should_voice_reply() -> bool:
    """书童每次回应前调用：是否应该用语音回复"""
    return get_preferences().is_voice_reply_enabled()


def set_voice_reply(enabled: bool):
    """设置语音回复开关"""
    pref = get_preferences()
    if enabled:
        pref.enable_voice_reply()
    else:
        pref.disable_voice_reply()


# 便捷命令识别
VOICE_ENABLE_KEYWORDS = [
    "用语音", "语音回复", "打开语音", "开启语音", "用声音", "播放语音"
]
VOICE_DISABLE_KEYWORDS = [
    "关闭语音", "关语音", "不用语音", "不要语音", "取消语音", "静音"
]


def detect_voice_command(text: str) -> Optional[bool]:
    """
    检测用户是否想切换语音回复开关
    返回：True=开启，False=关闭，None=没有相关指令
    """
    text = text.lower()
    for kw in VOICE_ENABLE_KEYWORDS:
        if kw in text:
            return True
    for kw in VOICE_DISABLE_KEYWORDS:
        if kw in text:
            return False
    return None


if __name__ == "__main__":
    pref = get_preferences()
    print("当前偏好：")
    print(json.dumps(pref.all_preferences(), ensure_ascii=False, indent=2))
