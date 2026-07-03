"""伴读书童AI - 讯飞 Spark 超拟人语音合成

使用讯飞官方 SDK：xfyunsdkspark.oral_client.OralClient
接口：wss://cbm01.cn-huabei-1.xf-yun.com/v1/private/mcd9m97e6

注意：该服务需要在讯飞控制台单独开通授权，否则返回 11200。
"""

import base64
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from ..配置 import CONFIG, XFYUN_APP_ID, XFYUN_API_KEY, XFYUN_API_SECRET


class XfyunOralTTS:
    """讯飞超拟人语音合成封装"""

    def __init__(self):
        self.app_id = XFYUN_APP_ID
        self.api_key = XFYUN_API_KEY
        self.api_secret = XFYUN_API_SECRET
        self.vcn = CONFIG.get("voice_name", "x4_lingxiaoxuan_oral")
        self.error_msg = ""

    def synthesize_to_bytes(self, text: str) -> Optional[bytes]:
        """合成语音，返回 mp3 字节"""
        try:
            from xfyunsdkspark.oral_client import OralClient
        except ImportError as e:
            self.error_msg = f"缺少 xfyunsdkspark 依赖: {e}"
            return None

        if not self.app_id or not self.api_key or not self.api_secret:
            self.error_msg = "讯飞密钥未配置"
            return None

        client = OralClient(
            app_id=self.app_id,
            api_key=self.api_key,
            api_secret=self.api_secret,
            vcn=self.vcn,
            encoding="lame",
            sample_rate=24000,
            oral_level=CONFIG.get("xfyun_oral_level", "mid"),
            spark_assist=CONFIG.get("xfyun_oral_spark_assist", 1),
            speed=CONFIG.get("voice_speed", 50),
            volume=CONFIG.get("voice_volume", 50),
            pitch=CONFIG.get("voice_pitch", 50),
        )

        chunks = []
        try:
            for chunk in client.stream(text):
                audio = chunk.get("audio", {}).get("audio")
                if audio:
                    chunks.append(base64.b64decode(audio))
            if not chunks:
                self.error_msg = "未收到音频数据"
                return None
            return b"".join(chunks)
        except Exception as e:
            self.error_msg = str(e)
            return None


def play_audio_bytes(audio_bytes: bytes) -> bool:
    """播放音频字节"""
    if not audio_bytes:
        return False
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        if sys.platform == "darwin":
            subprocess.run(["afplay", tmp_path], check=False, timeout=60)
        elif sys.platform == "linux":
            for cmd in [["ffplay", "-autoexit", "-nodisp", tmp_path],
                        ["mpg123", tmp_path],
                        ["cvlc", tmp_path]]:
                try:
                    subprocess.run(cmd, check=False, timeout=60,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except Exception:
                    continue
        else:
            os.startfile(tmp_path)

        def _cleanup():
            try:
                time.sleep(5)
                Path(tmp_path).unlink()
            except Exception:
                pass

        threading.Thread(target=_cleanup, daemon=True).start()
        return True
    except Exception as e:
        print(f"[播放] 失败: {e}")
        return False
