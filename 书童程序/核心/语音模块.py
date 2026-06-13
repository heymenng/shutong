"""伴读书童AI - 语音模块"""

import re
import subprocess
import sys
import platform
from ..配置 import CONFIG

class VoiceEngine:
    def __init__(self):
        self.engine = None
        self.backend = None  # 'pyttsx3' | 'say' | None
        
        if not CONFIG["voice_enabled"]:
            return
            
        # 尝试 pyttsx3（跨平台）
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', CONFIG["voice_rate"])
            self.backend = 'pyttsx3'
            print("[语音] 使用 pyttsx3 引擎")
            return
        except Exception as e:
            print(f"[语音] pyttsx3 不可用: {e}")
        
        # macOS 回退到系统 say 命令
        if platform.system() == 'Darwin':
            try:
                result = subprocess.run(['which', 'say'], capture_output=True, text=True)
                if result.returncode == 0:
                    self.backend = 'say'
                    print("[语音] 使用 macOS say 引擎")
                    return
            except Exception as e:
                print(f"[语音] say 命令不可用: {e}")
        
        print("[语音] 无可用 TTS 引擎，语音功能已禁用")
    
    def speak(self, text):
        clean_text = re.sub(r'[（(].*?[）)]', '', text)
        clean_text = clean_text.strip()
        if not clean_text:
            return
            
        try:
            if self.backend == 'pyttsx3' and self.engine:
                self.engine.say(clean_text)
                self.engine.runAndWait()
            elif self.backend == 'say':
                # macOS say 命令，使用中文语音
                subprocess.run(
                    ['say', '-v', 'Meijia', clean_text],
                    capture_output=True,
                    timeout=30
                )
        except Exception as e:
            print(f"[语音] 播放失败: {e}")
