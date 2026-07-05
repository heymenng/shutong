"""伴读书童AI - 讯飞语音服务底层模块

封装讯飞开放平台的两项能力：
- 在线语音合成（TTS）：文字 -> 语音
- 实时语音转写（STT）：语音 -> 文字

依赖：websocket-client
"""

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import websocket

from ..配置 import CONFIG, XFYUN_APP_ID, XFYUN_API_KEY, XFYUN_API_SECRET


# ──────────────────────────────────────────
# 通用工具
# ──────────────────────────────────────────

def _has_credentials() -> bool:
    """检查是否配置了讯飞密钥"""
    return bool(XFYUN_APP_ID and XFYUN_API_KEY and XFYUN_API_SECRET)


def _rfc1123_date() -> str:
    """生成 RFC1123 日期字符串"""
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _build_authorization(host: str, api_key: str, api_secret: str, path: str) -> str:
    """构建讯飞 WebSocket 鉴权头

    签名原文字符串：
        host: {host}\n
        date: {date}\n
        GET {path} HTTP/1.1
    """
    date = _rfc1123_date()
    signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    return base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")


def _build_ws_url(host: str, path: str, params: Optional[dict] = None) -> str:
    """构建带鉴权参数的 WebSocket URL"""
    authorization = _build_authorization(host, XFYUN_API_KEY, XFYUN_API_SECRET, path)
    query = {
        "authorization": authorization,
        "date": _rfc1123_date(),
        "host": host,
    }
    if params:
        query.update(params)
    return f"wss://{host}{path}?{urlencode(query)}"


# ──────────────────────────────────────────
# 在线语音合成（TTS）
# ──────────────────────────────────────────

class XfyunTTS:
    """讯飞在线语音合成"""

    HOST = "tts-api.xfyun.cn"
    PATH = "/v2/tts"

    def __init__(self, app_id=None, api_key=None, api_secret=None):
        self.app_id = app_id or XFYUN_APP_ID
        self.api_key = api_key or XFYUN_API_KEY
        self.api_secret = api_secret or XFYUN_API_SECRET
        self.audio_frames = []
        self.is_error = False
        self.error_msg = ""
        self.finished = False

    def synthesize(self, text: str, output_path: str) -> bool:
        """合成语音并保存到文件"""
        audio = self.synthesize_to_bytes(text)
        if audio is None or self.is_error:
            return False
        Path(output_path).write_bytes(audio)
        return True

    def synthesize_to_bytes(self, text: str) -> Optional[bytes]:
        """合成语音，返回音频字节（PCM 或 MP3，取决于配置）"""
        if not self.app_id or not self.api_key or not self.api_secret:
            self.is_error = True
            self.error_msg = "讯飞密钥未配置"
            return None

        self.audio_frames = []
        self.is_error = False
        self.error_msg = ""
        self.finished = False

        ws_url = _build_ws_url(self.HOST, self.PATH)

        def on_open(ws):
            business = {
                "aue": "lame",          # lame=mp3, raw=pcm
                "sfl": 1,               # 开启流式返回 mp3（文档要求 aue=lame 时必传）
                "auf": "audio/L16;rate=16000",
                "vcn": CONFIG.get("voice_name", "x4_xiaoyan"),
                "speed": int(CONFIG.get("voice_speed", 50)),
                "volume": int(CONFIG.get("voice_volume", 100)),
                "pitch": int(CONFIG.get("voice_pitch", 50)),
                "bgs": 0,
                "tte": "UTF8",
            }
            data = {
                "status": 2,  # 一次性发送完
                "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
            }
            frame = {
                "common": {"app_id": self.app_id},
                "business": business,
                "data": data,
            }
            ws.send(json.dumps(frame))

        def on_message(ws, message):
            try:
                resp = json.loads(message)
                code = resp.get("code", -1)
                if code != 0:
                    self.is_error = True
                    self.error_msg = resp.get("message", "未知错误")
                    self.finished = True
                    return
                audio = resp.get("data", {}).get("audio")
                if audio:
                    self.audio_frames.append(base64.b64decode(audio))
                if resp.get("data", {}).get("status") == 2:
                    self.finished = True
            except Exception as e:
                self.is_error = True
                self.error_msg = str(e)
                self.finished = True

        def on_error(ws, error):
            self.is_error = True
            self.error_msg = str(error)
            self.finished = True

        def on_close(ws, close_status_code, close_msg):
            self.finished = True

        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        # 在后台线程运行 WebSocket
        wst = threading.Thread(target=ws.run_forever, kwargs={"ping_interval": 5, "ping_timeout": 3})
        wst.daemon = True
        wst.start()

        # 等待完成或超时（最多 30 秒）
        timeout = 30
        start = time.time()
        while not self.finished and time.time() - start < timeout:
            time.sleep(0.05)

        ws.close()
        wst.join(timeout=2)

        if self.is_error:
            print(f"[讯飞TTS] 合成失败: {self.error_msg}")
            return None

        if not self.audio_frames:
            print("[讯飞TTS] 未收到音频数据")
            return None

        return b"".join(self.audio_frames)


def play_audio_bytes(audio_bytes: bytes) -> bool:
    """播放音频字节（mp3/pcm），优先使用系统播放器"""
    if not audio_bytes:
        return False
    try:
        # 保存为临时 mp3 文件
        suffix = ".mp3" if audio_bytes[:2] == b"\xff\xfb" or audio_bytes[:3] == b"ID3" else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
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

        # 异步清理临时文件
        def _cleanup():
            try:
                time.sleep(5)
                os.unlink(tmp_path)
            except Exception:
                pass

        threading.Thread(target=_cleanup, daemon=True).start()
        return True
    except Exception as e:
        print(f"[播放] 失败: {e}")
        return False


# ──────────────────────────────────────────
# 实时语音转写（STT）
# ──────────────────────────────────────────

class XfyunSTT:
    """讯飞实时语音转写（流式识别）"""

    HOST = "rtasr.xfyun.cn"
    PATH = "/v1/ws"

    def __init__(self, app_id=None, api_key=None, api_secret=None):
        self.app_id = app_id or XFYUN_APP_ID
        self.api_key = api_key or XFYUN_API_KEY
        self.api_secret = api_secret or XFYUN_API_SECRET
        self.results = []
        self.is_error = False
        self.error_msg = ""
        self.finished = False

    def _build_url(self) -> str:
        """实时语音转写使用 hmac-sha1 鉴权

        signa = base64(hmac_sha1(api_secret, md5(appid + ts)))
        """
        ts = int(time.time())
        tmp = hashlib.md5(f"{self.app_id}{ts}".encode("utf-8")).hexdigest()
        signa = base64.b64encode(
            hmac.new(
                self.api_secret.encode("utf-8"),
                tmp.encode("utf-8"),
                digestmod=hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        params = {
            "appid": self.app_id,
            "ts": ts,
            "signa": signa,
        }
        return f"wss://{self.HOST}{self.PATH}?{urlencode(params)}"

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> dict:
        """识别音频字节，返回 {"text": "...", "confidence": 0.9}"""
        if not self.app_id or not self.api_key or not self.api_secret:
            return {"text": "", "confidence": 0, "error": "讯飞密钥未配置"}

        self.results = []
        self.is_error = False
        self.error_msg = ""
        self.finished = False

        # 如果是 PCM，需要是 16k 16bit 单声道
        # 如果是 WAV，去掉文件头
        pcm_data = self._ensure_pcm(audio_bytes, sample_rate)
        if pcm_data is None:
            return {"text": "", "confidence": 0, "error": "音频格式不支持"}

        ws_url = self._build_url()

        def on_open(ws):
            # 分片发送，每片约 1280 样本（80ms @ 16k）
            chunk_size = 1280
            total = len(pcm_data)
            for i in range(0, total, chunk_size):
                end = min(i + chunk_size, total)
                is_last = end >= total
                audio_chunk = pcm_data[i:end]
                audio_b64 = base64.b64encode(audio_chunk).decode("utf-8")

                if i == 0:
                    # 第一帧：status=0，带参数
                    frame = {
                        "common": {"app_id": self.app_id},
                        "business": {
                            "language": CONFIG.get("xfyun_stt_language", "zh_cn"),
                            "domain": CONFIG.get("xfyun_stt_domain", "iat"),
                            "accent": "mandarin",
                            "dwa": "wpgs",
                        },
                        "data": {
                            "status": 0,
                            "format": "audio/L16;rate=16000",
                            "encoding": "raw",
                            "audio": audio_b64,
                        },
                    }
                elif is_last:
                    # 最后一帧：status=2
                    frame = {
                        "data": {
                            "status": 2,
                            "format": "audio/L16;rate=16000",
                            "encoding": "raw",
                            "audio": audio_b64,
                        }
                    }
                else:
                    # 中间帧：status=1
                    frame = {
                        "data": {
                            "status": 1,
                            "format": "audio/L16;rate=16000",
                            "encoding": "raw",
                            "audio": audio_b64,
                        }
                    }
                ws.send(json.dumps(frame))

        def on_message(ws, message):
            try:
                resp = json.loads(message)
                action = resp.get("action")
                if action == "result":
                    data = json.loads(resp.get("data", "{}"))
                    cn = data.get("cn", {})
                    st = cn.get("st", {})
                    rt_list = st.get("rt", [])
                    for rt in rt_list:
                        ws_list = rt.get("ws", [])
                        text_parts = []
                        for w in ws_list:
                            cw = w.get("cw", [])
                            for c in cw:
                                text_parts.append(c.get("w", ""))
                        text = "".join(text_parts)
                        if text:
                            self.results.append(text)
                elif action == "error":
                    self.is_error = True
                    self.error_msg = resp.get("desc", "识别错误")
                    self.finished = True
            except Exception as e:
                # 有时 message 不是 json，是结束信号
                if isinstance(message, str) and "success" in message.lower():
                    self.finished = True
                else:
                    self.is_error = True
                    self.error_msg = str(e)
                    self.finished = True

        def on_error(ws, error):
            err_str = str(error)
            # 忽略 WebSocket 正常关闭帧 (opcode=8, close code 1000)
            if "opcode=8" in err_str and "\\x03\\xe8" in err_str:
                print(f"[讯飞STT] WebSocket 正常关闭: {err_str}")
                self.finished = True
                return
            print(f"[讯飞STT] WebSocket 错误: {err_str}")
            self.is_error = True
            self.error_msg = err_str
            self.finished = True

        def on_close(ws, close_status_code, close_msg):
            print(f"[讯飞STT] WebSocket 关闭: code={close_status_code}, msg={close_msg}")
            self.finished = True

        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        wst = threading.Thread(target=ws.run_forever, kwargs={"ping_interval": 5, "ping_timeout": 3})
        wst.daemon = True
        wst.start()

        timeout = 60
        start = time.time()
        while not self.finished and time.time() - start < timeout:
            time.sleep(0.05)

        ws.close()
        wst.join(timeout=2)

        full_text = "".join(self.results)
        if self.is_error:
            return {"text": full_text, "confidence": 0, "error": self.error_msg}
        return {"text": full_text, "confidence": 0.9}

    def _ensure_pcm(self, audio_bytes: bytes, sample_rate: int) -> Optional[bytes]:
        """确保返回 16k 16bit 单声道 PCM 数据"""
        if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
            # WAV 文件，解析头
            try:
                with wave.open(BytesIO(audio_bytes), "rb") as wf:
                    channels = wf.getnchannels()
                    rate = wf.getframerate()
                    width = wf.getsampwidth()
                    pcm = wf.readframes(wf.getnframes())
                    return self._resample_if_needed(pcm, rate, channels, width)
            except Exception as e:
                print(f"[讯飞STT] WAV 解析失败: {e}")
                return None
        else:
            # 假设是 16k 16bit 单声道 PCM
            return audio_bytes

    def _resample_if_needed(self, pcm: bytes, rate: int, channels: int, width: int) -> Optional[bytes]:
        """重采样到 16k 单声道 16bit"""
        try:
            import numpy as np
            dtype = np.int16 if width == 2 else np.int8
            audio = np.frombuffer(pcm, dtype=dtype).astype(np.float32) / 32768.0
            if channels > 1:
                audio = audio.reshape(-1, channels).mean(axis=1)
            if rate != 16000:
                import librosa
                audio = librosa.resample(audio, orig_sr=rate, target_sr=16000)
            audio = np.clip(audio, -1.0, 1.0)
            return (audio * 32767).astype(np.int16).tobytes()
        except ImportError as e:
            print(f"[讯飞STT] 缺少重采样依赖: {e}")
            return None
        except Exception as e:
            print(f"[讯飞STT] 重采样失败: {e}")
            return None

