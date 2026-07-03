"""
伴读书童AI - G1 HTTP 控制客户端

基于 G1_CONTROL_CLIENT_V2.md（实测修订版）实现，用于笔记本/Mac 通过 HTTP 调用 G1 PC2 上的控制服务。

控制服务地址：
    默认：http://192.168.0.248:8888（PC2 WiFi，推荐）
    内网：http://192.168.123.164:8888
    可通过环境变量 G1_CONTROL_URL 覆盖
    可通过环境变量 G1_CONTROL_TOKEN 设置鉴权 token

提供四类调用：
    1. /action      - 机器人运动动作（sport 服务）
    2. /arm_action  - 手臂动作（arm 服务，V2 新增）
    3. /audio/tts   - G1 内置 TTS 播放
    4. /audio/pcm   - 播放已合成的 PCM 音频
"""

import base64
import os
import time
from pathlib import Path
from typing import Optional

import requests


class G1HTTPClient:
    """G1 机器人 HTTP 控制客户端"""

    # 运动控制 /action 安全动作子集（V2 已剔除不生效或危险动作）
    SAFE_ACTIONS = {
        "stand", "squat", "stop",
        "forward", "back", "left", "right", "turn_left", "turn_right", "move",
    }

    # 运动控制 /action 完整动作列表（含 damp/lie_to_stand，仅高权限使用）
    ALL_ACTIONS = {
        "damp", "stand", "squat", "lie_to_stand", "stop", "move",
        "forward", "back", "left", "right", "turn_left", "turn_right",
    }

    # 手臂动作 /arm_action 安全动作子集（V2 新增，全部实测可用）
    SAFE_ARM_ACTIONS = {
        "face_wave", "high_wave", "shake_hand_arm", "clap", "high_five",
        "hug", "heart", "hands_up", "two_hand_kiss", "release_arm",
    }

    # 手臂动作完整列表
    ALL_ARM_ACTIONS = SAFE_ARM_ACTIONS

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = (base_url or os.environ.get("G1_CONTROL_URL", "http://192.168.0.248:8888")).rstrip("/")
        self.token = token or os.environ.get("G1_CONTROL_TOKEN")
        self.app_name = "bookboy_agent"
        self._capabilities = None

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["X-Robot-Token"] = self.token
        return h

    def health(self) -> dict:
        """检查控制服务健康状态"""
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def capabilities(self, force: bool = False) -> dict:
        """获取服务端支持的动作、速度限制、PCM 格式等"""
        if self._capabilities is not None and not force:
            return self._capabilities
        try:
            r = requests.get(f"{self.base_url}/actions", timeout=5)
            r.raise_for_status()
            self._capabilities = r.json()
            return self._capabilities
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def is_available(self) -> bool:
        """判断控制服务是否可用"""
        data = self.health()
        return data.get("ok") is True

    def execute_action(self, action: str, **kwargs) -> dict:
        """
        执行机器人运动动作（发送到 /action）。

        参数：
            action: 动作名称，如 forward/move/stop
            **kwargs: 动作参数，如 duration/vx/vy/vrot
        """
        payload = {"action": action, **kwargs}
        try:
            r = requests.post(
                f"{self.base_url}/action",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            # 忙时 409 不抛异常，返回原始响应便于调用方处理
            if r.status_code == 409:
                return {"ok": False, "busy": True, "error": r.json().get("error", "robot busy")}
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def execute_arm_action(self, action: str) -> dict:
        """
        执行手臂动作（发送到 /arm_action，V2 新增）。

        参数：
            action: 手臂动作名称，如 face_wave/clap/heart/shake_hand_arm
        """
        payload = {"action": action}
        try:
            r = requests.post(
                f"{self.base_url}/arm_action",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # 书童动作名 → (端点, G1 动作名) 映射
    # V2 说明：wave/shake_hand/dance 等已改为手臂动作
    BOOKBOY_TO_G1_ACTION = {
        "stand": ("action", "stand"),
        "sit": ("action", "squat"),           # 书童的"坐下"对应 G1 的蹲下
        "lie_down": ("action", "damp"),       # 书童的"趴下"对应 G1 damp（仅在明确需要失力保护时使用）
        "wave": ("arm_action", "face_wave"),
        "walk": ("action", "forward"),
        "stop": ("action", "stop"),
        "follow": ("action", "move"),         # 跟随用 move 原地微调示意
        "dance": ("arm_action", "face_wave"), # 跳舞用手臂挥手
        "recovery": ("action", "stand"),      # 恢复站立
        "shake_hand": ("arm_action", "shake_hand_arm"),
        "clap": ("arm_action", "clap"),
        "heart": ("arm_action", "heart"),
        "hug": ("arm_action", "hug"),
        "high_five": ("arm_action", "high_five"),
    }

    def execute_action_safe(self, action: str, retry_once: bool = True, **kwargs) -> dict:
        """
        执行动作，遇到 409 忙时退避重试一次。
        stop/damp 等急停动作直接发送，不重试。
        自动把书童动作名映射为 G1 控制服务动作名，并自动路由到 /action 或 /arm_action。
        """
        endpoint, g1_action = self.BOOKBOY_TO_G1_ACTION.get(action, ("action", action))

        if endpoint == "arm_action":
            return self.execute_arm_action(g1_action)

        if g1_action in ("stop", "damp"):
            return self.execute_action(g1_action, **kwargs)

        result = self.execute_action(g1_action, **kwargs)
        if result.get("busy") and retry_once:
            time.sleep(0.3)
            return self.execute_action(g1_action, **kwargs)
        return result

    def speak_tts(self, text: str, speaker_id: int = 0) -> dict:
        """调用 G1 内置 TTS 播放文字"""
        try:
            r = requests.post(
                f"{self.base_url}/audio/tts",
                json={"text": text, "speaker_id": speaker_id},
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError:
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def play_pcm_bytes(self, pcm_data: bytes, stream_id: str = "bookboy_reply_001", stop_after: bool = False) -> dict:
        """播放 PCM 音频数据（s16le/16000Hz/mono）"""
        pcm_base64 = base64.b64encode(pcm_data).decode("ascii")
        try:
            r = requests.post(
                f"{self.base_url}/audio/pcm",
                json={
                    "app_name": self.app_name,
                    "stream_id": stream_id,
                    "pcm_base64": pcm_base64,
                    "stop_after": stop_after,
                },
                headers=self._headers(),
                timeout=20,
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError:
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def play_pcm_file(self, path: str, stream_id: str = "bookboy_reply_001", stop_after: bool = True) -> dict:
        """播放 PCM 文件"""
        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": f"文件不存在: {path}"}
        return self.play_pcm_bytes(p.read_bytes(), stream_id=stream_id, stop_after=stop_after)

    def play_mp3_file(self, path: str, stream_id: str = "bookboy_reply_001", chunk_seconds: Optional[float] = None) -> dict:
        """
        播放 MP3 文件：自动转换为 G1 要求的 PCM 格式后播放。
        如果音频较长，可以按 chunk_seconds 分块流式上传。
        """
        try:
            from .音频格式转换 import convert_to_g1_pcm, split_pcm_chunks
        except ImportError:
            return {"ok": False, "error": "音频格式转换模块不可用"}

        try:
            pcm_bytes = convert_to_g1_pcm(path)
        except Exception as e:
            return {"ok": False, "error": f"MP3 转 PCM 失败: {e}"}

        if chunk_seconds:
            chunks = split_pcm_chunks(pcm_bytes, chunk_seconds)
            results = []
            for idx, chunk in enumerate(chunks):
                is_last = idx == len(chunks) - 1
                result = self.play_pcm_bytes(chunk, stream_id=stream_id, stop_after=is_last)
                results.append(result)
                if not result.get("ok"):
                    return result
            return {"ok": True, "chunks": len(chunks), "results": results}
        else:
            return self.play_pcm_bytes(pcm_bytes, stream_id=stream_id, stop_after=True)

    def stop_audio(self) -> dict:
        """停止当前音频播放"""
        try:
            r = requests.post(
                f"{self.base_url}/audio/stop",
                json={"app_name": self.app_name},
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError:
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def play_text_with_voice(self, text: str, pcm_callback=None, speaker_id: int = 0) -> dict:
        """
        播放文字回复。
        如果提供了 pcm_callback(text -> bytes)，则走 /audio/pcm；否则走 /audio/tts。
        """
        if pcm_callback:
            pcm_data = pcm_callback(text)
            if pcm_data:
                return self.play_pcm_bytes(pcm_data, stop_after=True)
        return self.speak_tts(text, speaker_id=speaker_id)


def create_g1_client_from_config(config: dict) -> G1HTTPClient:
    """从书童配置字典创建 G1 HTTP 客户端"""
    base_url = config.get("g1_control_url") or os.environ.get("G1_CONTROL_URL")
    token = config.get("g1_control_token") or os.environ.get("G1_CONTROL_TOKEN")
    return G1HTTPClient(base_url=base_url, token=token)


if __name__ == "__main__":
    client = G1HTTPClient()
    print("Health:", client.health())
    print("Capabilities:", client.capabilities())
