#!/usr/bin/env python3
import argparse
import base64
import collections
import json
import logging
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient

# arm actions and their IDs
ARM_ACTIONS = {
    "clap": 17,
    "high_five": 18,
    "hug": 19,
    "heart": 20,
    "face_wave": 25,
    "high_wave": 26,
    "shake_hand_arm": 27,
    "hands_up": 15,
    "release_arm": 99,
    "two_hand_kiss": 11,
}

log = logging.getLogger("g1.server")


class MemoryLogHandler(logging.Handler):
    """把日志记录存进环形缓冲 + 广播给 SSE 订阅者，供远程通过 HTTP 查看。"""

    def __init__(self, capacity: int = 2000):
        super().__init__()
        self._buffer = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._subscribers = []  # list[queue.Queue]
        self._sub_lock = threading.Lock()

    def emit(self, record):
        line = self.format(record)
        with self._lock:
            self._buffer.append(line)
        with self._sub_lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(line)
                except queue.Full:
                    pass  # 慢消费者丢掉，不阻塞日志线程

    def recent(self, n: int = 200):
        with self._lock:
            items = list(self._buffer)
        return items[-n:] if n < len(items) else items

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=1000)
        with self._sub_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._sub_lock:
            if q in self._subscribers:
                self._subscribers.remove(q)


memory_handler = MemoryLogHandler()


class RobotBusyError(Exception):
    """Raised when a motion action is rejected because another is in progress."""
    pass


class RobotController:
    def __init__(self, network_interface: str):
        ChannelFactoryInitialize(0, network_interface)

        self.client = LocoClient()
        self.client.SetTimeout(10.0)
        self.client.Init()

        self.audio_client = AudioClient()
        self.audio_client.SetTimeout(10.0)
        self.audio_client.Init()

        self.arm_client = G1ArmActionClient()
        self.arm_client.SetTimeout(10.0)
        self.arm_client.Init()

        self.lock = threading.Lock()
        self.audio_lock = threading.Lock()
        self.arm_lock = threading.Lock()
        self.stop_event = threading.Event()  # 急停信号,用于打断进行中动作的等待

    def execute(self, command: dict) -> dict:
        action = command.get("action")
        if not action:
            raise ValueError("missing action")

        # 急停优先:stop / damp 不排队、不被 409 拒绝、能打断进行中动作的等待。
        # 不获取 self.lock,因此机器人移动期间也能立即生效。
        if action == "stop":
            self.stop_event.set()
            self.client.StopMove()
            return {"ok": True, "action": "stop", "interrupted": True}
        if action == "damp":
            self.stop_event.set()
            self.client.Damp()
            return {"ok": True, "action": "damp", "interrupted": True}

        # 非阻塞获取:已有动作在执行则立即拒绝,避免请求无限排队、陈旧命令延迟执行
        if not self.lock.acquire(blocking=False):
            raise RobotBusyError("robot busy, another action is in progress")
        try:
            self.stop_event.clear()  # 复位急停标志,开始一个新动作
            log.info("execute action=%s", action)
            if action == "stand":
                self.client.Damp()
                if not self.stop_event.wait(0.5):
                    self.client.Squat2StandUp()
            elif action == "squat":
                self.client.StandUp2Squat()
            elif action == "lie_to_stand":
                self.client.Damp()
                if not self.stop_event.wait(0.5):
                    self.client.Lie2StandUp()
            elif action == "move":
                vx = self._clamp_float(command.get("vx", 0.0), -0.5, 0.5)
                vy = self._clamp_float(command.get("vy", 0.0), -0.4, 0.4)
                vrot = self._clamp_float(command.get("vrot", 0.0), -0.6, 0.6)
                duration = self._clamp_float(command.get("duration", 1.0), 0.1, 3.0)
                log.info("move vx=%.2f vy=%.2f vrot=%.2f duration=%.2f", vx, vy, vrot, duration)
                self.client.SetVelocity(vx, vy, vrot, duration)
                self.stop_event.wait(duration)  # 急停时立即返回,随后 StopMove 收尾
                self.client.StopMove()
            elif action == "forward":
                duration = self._clamp_float(command.get("duration", 1.0), 0.1, 3.0)
                self.client.SetVelocity(0.3, 0.0, 0.0, duration)
                self.stop_event.wait(duration)  # 急停时立即返回,随后 StopMove 收尾
                self.client.StopMove()
            elif action == "back":
                duration = self._clamp_float(command.get("duration", 1.0), 0.1, 3.0)
                self.client.SetVelocity(-0.2, 0.0, 0.0, duration)
                self.stop_event.wait(duration)  # 急停时立即返回,随后 StopMove 收尾
                self.client.StopMove()
            elif action == "left":
                duration = self._clamp_float(command.get("duration", 1.0), 0.1, 3.0)
                self.client.SetVelocity(0.0, 0.2, 0.0, duration)
                self.stop_event.wait(duration)  # 急停时立即返回,随后 StopMove 收尾
                self.client.StopMove()
            elif action == "right":
                duration = self._clamp_float(command.get("duration", 1.0), 0.1, 3.0)
                self.client.SetVelocity(0.0, -0.2, 0.0, duration)
                self.stop_event.wait(duration)  # 急停时立即返回,随后 StopMove 收尾
                self.client.StopMove()
            elif action == "turn_left":
                duration = self._clamp_float(command.get("duration", 1.0), 0.1, 3.0)
                self.client.SetVelocity(0.0, 0.0, 0.3, duration)
                self.stop_event.wait(duration)  # 急停时立即返回,随后 StopMove 收尾
                self.client.StopMove()
            elif action == "turn_right":
                duration = self._clamp_float(command.get("duration", 1.0), 0.1, 3.0)
                self.client.SetVelocity(0.0, 0.0, -0.3, duration)
                self.stop_event.wait(duration)  # 急停时立即返回,随后 StopMove 收尾
                self.client.StopMove()
            else:
                raise ValueError(f"unknown action: {action}")
        finally:
            self.lock.release()

        return {"ok": True, "action": action}

    def arm_action(self, command: dict) -> dict:
        action = command.get("action")
        if not action:
            raise ValueError("missing action")

        arm_id = ARM_ACTIONS.get(action)
        if arm_id is None:
            raise ValueError(f"unknown arm action: {action}")

        with self.arm_lock:
            code = self.arm_client.ExecuteAction(arm_id)
            log.info("arm_action action=%s id=%s code=%s", action, arm_id, code)
            if code != 0:
                raise RuntimeError(f"arm action {action} failed, code={code}")

        return {"ok": True, "action": action}

    def tts(self, command: dict) -> dict:
        text = command.get("text", "")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("missing text")
        if len(text) > 500:
            raise ValueError("text too long, max 500 characters")

        speaker_id = int(command.get("speaker_id", 0))
        speaker_id = max(0, min(10, speaker_id))

        with self.audio_lock:
            code = self.audio_client.TtsMaker(text, speaker_id)

        log.info("tts speaker_id=%s len=%d code=%s", speaker_id, len(text), code)
        if code != 0:
            raise RuntimeError(f"tts failed, code={code}")
        return {"ok": True, "type": "tts", "speaker_id": speaker_id}

    def play_pcm(self, command: dict) -> dict:
        pcm_base64 = command.get("pcm_base64", "")
        if not isinstance(pcm_base64, str) or not pcm_base64:
            raise ValueError("missing pcm_base64")

        app_name = command.get("app_name", "mac_agent")
        stream_id = command.get("stream_id") or str(int(time.time() * 1000))
        stop_after = bool(command.get("stop_after", False))

        pcm_data = base64.b64decode(pcm_base64, validate=True)
        if len(pcm_data) == 0:
            raise ValueError("empty pcm data")
        if len(pcm_data) > 192000:
            raise ValueError("pcm data too large, max 192000 bytes per request")

        with self.audio_lock:
            code, _ = self.audio_client.PlayStream(app_name, stream_id, pcm_data)
            log.info("play_pcm app=%s stream=%s bytes=%d code=%s stop_after=%s",
                     app_name, stream_id, len(pcm_data), code, stop_after)
            if code != 0:
                raise RuntimeError(f"play pcm failed, code={code}")
            if stop_after:
                self.audio_client.PlayStop(app_name)

        return {
            "ok": True,
            "type": "pcm",
            "app_name": app_name,
            "stream_id": stream_id,
            "bytes": len(pcm_data),
            "format": "s16le/16000Hz/mono"
        }

    def stop_audio(self, command: dict) -> dict:
        app_name = command.get("app_name", "mac_agent")
        with self.audio_lock:
            self.audio_client.PlayStop(app_name)
        return {"ok": True, "type": "audio_stop", "app_name": app_name}

    @staticmethod
    def _clamp_float(value, min_value: float, max_value: float) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = min_value
        return max(min_value, min(max_value, value))


class RobotRequestHandler(BaseHTTPRequestHandler):
    controller = None
    token = None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path == "/health":
            self._send_json(200, {"ok": True, "service": "g1_robot_control_server"})
        elif path == "/logs":
            # 返回最近 N 行日志（默认 200）
            try:
                n = int(qs.get("n", ["200"])[0])
            except ValueError:
                n = 200
            lines = memory_handler.recent(n)
            self._send_json(200, {"ok": True, "count": len(lines), "lines": lines})
        elif path == "/logs/stream":
            self._stream_logs()
        elif path == "/actions":
            self._send_json(200, {
                "ok": True,
                "actions": [
                    "stand", "squat", "lie_to_stand", "damp", "stop",
                    "forward", "back", "left", "right", "turn_left", "turn_right", "move"
                ],
                "arm_actions": list(ARM_ACTIONS.keys()),
                "arm_endpoint": "/arm_action",
                "audio_endpoints": ["/audio/tts", "/audio/pcm", "/audio/stop"],
                "log_endpoints": ["/logs", "/logs/stream"],
                "move_limits": {
                    "vx": [-0.5, 0.5],
                    "vy": [-0.4, 0.4],
                    "vrot": [-0.6, 0.6],
                    "duration": [0.1, 3.0]
                },
                "pcm_format": "s16le/16000Hz/mono",
                "pcm_max_bytes_per_request": 192000
            })
        else:
            self._send_json(404, {"ok": False, "error": "not found"})

    def _stream_logs(self):
        """SSE 风格的实时日志流，供 curl -N 接到本地文件。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        q = memory_handler.subscribe()
        # 先把当前缓冲已有的历史行推过去
        for line in memory_handler.recent(200):
            self._sse_write(line)
        try:
            while True:
                try:
                    line = q.get(timeout=15)
                    self._sse_write(line)
                except queue.Empty:
                    # 心跳，保持连接、防止中间网关断开
                    self._sse_write(": heartbeat")
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            memory_handler.unsubscribe(q)

    def _sse_write(self, data: str):
        self.wfile.write(("data: " + data + "\n\n").encode("utf-8"))
        self.wfile.flush()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/action", "/arm_action", "/audio/tts", "/audio/pcm", "/audio/stop"):
            self._send_json(404, {"ok": False, "error": "not found"})
            return

        if self.token and self.headers.get("X-Robot-Token") != self.token:
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return

        t0 = time.time()
        action = ""
        try:
            command = self._read_json_body(786432)
            action = command.get("action") or command.get("text") or command.get("app_name", "")
            if path == "/action":
                result = self.controller.execute(command)
            elif path == "/arm_action":
                result = self.controller.arm_action(command)
            elif path == "/audio/tts":
                result = self.controller.tts(command)
            elif path == "/audio/pcm":
                result = self.controller.play_pcm(command)
            else:
                result = self.controller.stop_audio(command)
            log.info("POST %s ok action=%s params=%s dt=%.0fms",
                     path, action, self._fmt_params(command), (time.time() - t0) * 1000)
            self._send_json(200, result)
        except RobotBusyError as e:
            log.warning("POST %s busy action=%s dt=%.0fms", path, action, (time.time() - t0) * 1000)
            self._send_json(409, {"ok": False, "error": str(e)})
        except Exception as e:
            log.warning("POST %s error action=%s %s dt=%.0fms",
                        path, action, e, (time.time() - t0) * 1000)
            self._send_json(400, {"ok": False, "error": str(e)})

    @staticmethod
    def _fmt_params(command: dict) -> str:
        """把请求参数压缩成一行日志友好格式，剔除大字段。"""
        safe = {}
        for k, v in command.items():
            if k == "pcm_base64":
                safe[k] = f"<{len(str(v))} chars>"
            elif k == "text":
                safe[k] = f"<{len(str(v))} chars>"
            else:
                safe[k] = v
        return json.dumps(safe, ensure_ascii=False)

    def log_message(self, fmt, *args):
        # 把 BaseHTTPRequestHandler 默认的访问日志接到 logging
        log.info("%s - %s", self.address_string(), fmt % args)

    def _read_json_body(self, max_length: int) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > max_length:
            raise ValueError("invalid content length")
        body = self.rfile.read(length).decode("utf-8")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("json body must be object")
        return data

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description="Unitree G1 lightweight robot control server")
    parser.add_argument("network_interface", help="PC2 network interface connected to G1 internal network, for example eth0")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--token", default=None, help="optional token required by X-Robot-Token header")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="log verbosity (default INFO)")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 日志同时进 stdout(落 ~/robot_server.log) + 内存缓冲(供 /logs 远程查看)
    log_fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    memory_handler.setFormatter(log_fmt)
    memory_handler.setLevel(args.log_level)
    logging.getLogger().addHandler(memory_handler)

    log.warning("Make sure the robot has enough free space around it before starting this server.")
    log.info("Initializing DDS on interface: %s", args.network_interface)

    RobotRequestHandler.controller = RobotController(args.network_interface)
    RobotRequestHandler.token = args.token

    server = ThreadingHTTPServer((args.host, args.port), RobotRequestHandler)
    log.info("Robot control server listening on http://%s:%s", args.host, args.port)
    log.info("Endpoints: GET /health, GET /actions, GET /logs, GET /logs/stream, POST /action, POST /arm_action, POST /audio/tts, POST /audio/pcm, POST /audio/stop")
    server.serve_forever()


if __name__ == "__main__":
    main()
