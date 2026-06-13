"""伴读书童AI - 记忆模块"""

import json
import os
from datetime import datetime
from pathlib import Path
from ..配置 import CONFIG

class Memory:
    def __init__(self):
        self.history = []
        self.max_history = CONFIG["max_history"]
        self.journal_dir = Path(CONFIG["journal_dir"])
        self.journal_dir.mkdir(parents=True, exist_ok=True)
    
    def add(self, role, content):
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_history * 2:
            self.history = self.history[-self.max_history * 2:]
    
    def get_messages(self, system_prompt):
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.history[-self.max_history * 2:])
        return messages
    
    def save_session(self, child_id="default"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.journal_dir / f"session_{child_id}_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "child_id": child_id,
                "history": self.history
            }, f, ensure_ascii=False, indent=2)
    
    def clear(self):
        self.history = []
