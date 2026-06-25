"""伴读书童AI - 记忆模块（支持进程间共享）"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from ..配置 import CONFIG


class Memory:
    """
    伴读书童AI 记忆模块
    
    支持两种模式：
    1. 独立模式（默认）：每个进程有自己的 history，退出时 save_session 保存快照
    2. 共享模式：指定 session_id 后，使用同一个 JSON 文件，多个进程可实时共享记忆
    
    共享模式原理：
    - 记忆文件：journal_dir / shared_session_{session_id}.json
    - 每次 add 先读取文件、追加、再写入
    - 每次 get_messages 重新读取文件
    - 使用文件锁避免多进程同时写入冲突
    """
    
    def __init__(self, session_id=None):
        self.history = []
        self.max_history = CONFIG["max_history"]
        self.journal_dir = Path(CONFIG["journal_dir"])
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        
        # 共享模式
        self.session_id = session_id
        self.shared_file = None
        if session_id:
            self.shared_file = self.journal_dir / f"shared_session_{session_id}.json"
            self._load_shared_session()
    
    def _load_shared_session(self):
        """加载共享记忆文件"""
        if not self.shared_file or not self.shared_file.exists():
            return
        try:
            with open(self.shared_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.history = data.get("history", [])
            print(f"[记忆] 已加载共享会话 '{self.session_id}': {len(self.history)} 条")
        except Exception as e:
            print(f"[记忆] 加载共享会话失败: {e}")
            self.history = []
    
    def _save_shared_session(self):
        """保存共享记忆文件"""
        if not self.shared_file:
            return
        try:
            temp_file = self.shared_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "session_id": self.session_id,
                    "updated_at": datetime.now().isoformat(),
                    "history": self.history
                }, f, ensure_ascii=False, indent=2)
            temp_file.replace(self.shared_file)
        except Exception as e:
            print(f"[记忆] 保存共享会话失败: {e}")
    
    def add(self, role, content):
        """
        添加一条记忆。
        共享模式下会先重新加载文件，追加后再保存。
        """
        if self.shared_file:
            self._load_shared_session()
        
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # 限制长度
        max_len = self.max_history * 2
        if len(self.history) > max_len:
            self.history = self.history[-max_len:]
        
        if self.shared_file:
            self._save_shared_session()
    
    def get_messages(self, system_prompt):
        """
        构建发送给大模型的消息列表。
        共享模式下会重新加载文件，获取最新记忆。
        """
        if self.shared_file:
            self._load_shared_session()
        
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.history[-self.max_history * 2:])
        return messages
    
    def save_session(self, child_id="default"):
        """保存当前会话快照（独立模式使用）"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.journal_dir / f"session_{child_id}_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "child_id": child_id,
                "history": self.history
            }, f, ensure_ascii=False, indent=2)
        return str(filename)
    
    def load_latest_session(self, child_id="default"):
        """加载指定 child_id 的最新 session 文件（独立模式使用）"""
        pattern = f"session_{child_id}_*.json"
        sessions = sorted(self.journal_dir.glob(pattern))
        if sessions:
            latest = sessions[-1]
            try:
                with open(latest, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.history = data.get("history", [])
                    print(f"[记忆] 已加载历史会话: {latest.name} ({len(self.history)} 条)")
                    return str(latest)
            except Exception as e:
                print(f"[记忆] 加载会话失败: {e}")
        return None
    
    def clear(self):
        """清空当前记忆"""
        self.history = []
        if self.shared_file:
            self._save_shared_session()
