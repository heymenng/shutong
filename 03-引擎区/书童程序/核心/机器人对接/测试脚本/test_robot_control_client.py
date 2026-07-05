#!/usr/bin/env python3
"""G1 控制服务(robot_control_server.py)本地测试客户端。

直接连真实 PC2 上运行的控制服务,逐项触发各 HTTP 接口并校验行为。

安全分层(连的是真机,默认只跑不动机器人的测试):
  - 默认             : 只读测试(/health、/actions),不发声、不动身体;
  - --audio          : 音频测试(/audio/tts、/audio/pcm、/audio/stop),会发声;
  - --motion         : 运动测试(基本移动 + 409 忙时拒绝 + 急停打断),会让机器人动;
  - --all            : 以上全部。

运动测试会让机器人真实移动,运行前会要求确认机器人周围空旷、有人看护
(用 --yes 跳过确认)。每个移动测试结束后都会自动发 stop 收尾。

示例（在仓库根目录执行）:
  python deploy/test_robot_control_client.py --url http://192.168.123.164:8000
  python deploy/test_robot_control_client.py --audio
  python deploy/test_robot_control_client.py --motion --yes
  python deploy/test_robot_control_client.py --all --token g1secret
"""
import argparse
import base64
import math
import struct
import sys
import threading
import time

import requests


# ---------------------------------------------------------------------------
# 输出辅助
# ---------------------------------------------------------------------------
_counters = {"pass": 0, "fail": 0}


def _log(tag: str, msg: str):
    print(f"[{tag:^4}] {msg}", flush=True)


def info(msg):
    _log("INFO", msg)


def warn(msg):
    _log("WARN", msg)


def ok(msg):
    _counters["pass"] += 1
    _log("PASS", msg)


def fail(msg):
    _counters["fail"] += 1
    _log("FAIL", msg)


def section(title):
    print("\n" + "=" * 60, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 60, flush=True)


# ---------------------------------------------------------------------------
# HTTP 客户端
# ---------------------------------------------------------------------------
class Client:
    def __init__(self, base_url: str, token: str = None, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["X-Robot-Token"] = self.token
        return h

    def get(self, path: str):
        return requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=self.timeout)

    def post(self, path: str, payload: dict, timeout: float = None):
        return requests.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=self._headers(),
            timeout=timeout or self.timeout,
        )


# ---------------------------------------------------------------------------
# 只读测试
# ---------------------------------------------------------------------------
def test_health(client: Client):
    section("只读:GET /health")
    try:
        resp = client.get("/health")
    except requests.RequestException as e:
        fail(f"无法连接服务: {e}")
        return False
    if resp.status_code == 200 and resp.json().get("ok"):
        ok(f"/health -> {resp.json()}")
        return True
    fail(f"/health 异常: HTTP {resp.status_code} {resp.text}")
    return False


def test_actions(client: Client):
    section("只读:GET /actions")
    try:
        resp = client.get("/actions")
    except requests.RequestException as e:
        fail(f"请求失败: {e}")
        return
    if resp.status_code != 200:
        fail(f"/actions HTTP {resp.status_code} {resp.text}")
        return
    data = resp.json()
    actions = data.get("actions", [])
    info(f"支持的 action ({len(actions)}): {', '.join(actions)}")
    info(f"move_limits: {data.get('move_limits')}")
    info(f"pcm_format: {data.get('pcm_format')}, "
         f"pcm_max_bytes: {data.get('pcm_max_bytes_per_request')}")
    # 校验关键急停动作存在
    for must in ("stop", "damp"):
        if must in actions:
            ok(f"急停动作 '{must}' 在列表中")
        else:
            fail(f"急停动作 '{must}' 缺失")


def test_bad_request(client: Client):
    section("校验:非法请求应返回 400")
    resp = client.post("/action", {})  # 缺 action
    if resp.status_code == 400:
        ok(f"空 action -> 400 {resp.json().get('error')!r}")
    else:
        fail(f"空 action 期望 400,得到 HTTP {resp.status_code} {resp.text}")

    resp = client.post("/action", {"action": "no_such_action"})
    if resp.status_code == 400:
        ok(f"未知 action -> 400 {resp.json().get('error')!r}")
    else:
        fail(f"未知 action 期望 400,得到 HTTP {resp.status_code} {resp.text}")


# ---------------------------------------------------------------------------
# 音频测试
# ---------------------------------------------------------------------------
def _make_pcm(seconds: float = 0.4, freq: float = 440.0, amplitude: int = 4000) -> bytes:
    """生成 s16le / 16000Hz / mono 的正弦测试音。"""
    rate = 16000
    n = int(rate * seconds)
    buf = bytearray()
    for i in range(n):
        sample = int(amplitude * math.sin(2 * math.pi * freq * i / rate))
        buf += struct.pack("<h", sample)
    return bytes(buf)


def test_tts(client: Client):
    section("音频:POST /audio/tts")
    resp = client.post("/audio/tts", {"text": "测试,我是宇树 G1", "speaker_id": 0})
    if resp.status_code == 200 and resp.json().get("ok"):
        ok(f"/audio/tts -> {resp.json()}")
    else:
        fail(f"/audio/tts HTTP {resp.status_code} {resp.text}")

    # 边界:超长文本应 400
    resp = client.post("/audio/tts", {"text": "字" * 501})
    if resp.status_code == 400:
        ok("超长文本(>500) -> 400")
    else:
        fail(f"超长文本期望 400,得到 HTTP {resp.status_code}")


def test_pcm(client: Client):
    section("音频:POST /audio/pcm")
    pcm = _make_pcm()
    payload = {
        "app_name": "test_client",
        "stream_id": "test_pcm_001",
        "pcm_base64": base64.b64encode(pcm).decode("ascii"),
        "stop_after": True,
    }
    resp = client.post("/audio/pcm", payload, timeout=20)
    if resp.status_code == 200 and resp.json().get("ok"):
        ok(f"/audio/pcm ({len(pcm)} bytes) -> {resp.json()}")
    else:
        fail(f"/audio/pcm HTTP {resp.status_code} {resp.text}")

    # 边界:超大 PCM 应 400
    big = base64.b64encode(b"\x00" * 200000).decode("ascii")
    resp = client.post("/audio/pcm", {"pcm_base64": big}, timeout=20)
    if resp.status_code == 400:
        ok("超大 PCM(>192000) -> 400")
    else:
        fail(f"超大 PCM 期望 400,得到 HTTP {resp.status_code}")


def test_audio_stop(client: Client):
    section("音频:POST /audio/stop")
    resp = client.post("/audio/stop", {"app_name": "test_client"})
    if resp.status_code == 200 and resp.json().get("ok"):
        ok(f"/audio/stop -> {resp.json()}")
    else:
        fail(f"/audio/stop HTTP {resp.status_code} {resp.text}")


# ---------------------------------------------------------------------------
# 运动测试(会让机器人移动)
# ---------------------------------------------------------------------------
def test_basic_motion(client: Client, duration: float):
    section("运动:基本移动 forward + stop")
    resp = client.post("/action", {"action": "forward", "duration": duration},
                       timeout=duration + 5)
    if resp.status_code == 200 and resp.json().get("ok"):
        ok(f"forward(duration={duration}) -> {resp.json()}")
    else:
        fail(f"forward HTTP {resp.status_code} {resp.text}")
    # 收尾:确保停下
    client.post("/action", {"action": "stop"})
    info("已发送 stop 收尾")


def test_busy_409(client: Client):
    section("运动:并发忙时拒绝(409)")
    # 后台线程占用机器人(forward 2 秒),期间主线程发另一个动作应被 409 拒绝
    holder = {}

    def hold():
        try:
            r = client.post("/action", {"action": "forward", "duration": 2.0}, timeout=10)
            holder["status"] = r.status_code
        except requests.RequestException as e:
            holder["error"] = str(e)

    t = threading.Thread(target=hold)
    t.start()
    time.sleep(0.4)  # 等占锁动作开始
    resp = client.post("/action", {"action": "wave"})
    if resp.status_code == 409:
        ok(f"忙时第二个动作 -> 409 {resp.json().get('error')!r}")
    else:
        fail(f"忙时期望 409,得到 HTTP {resp.status_code} {resp.text}")
    t.join()
    info(f"占锁动作 forward 最终 HTTP {holder.get('status', holder.get('error'))}")
    client.post("/action", {"action": "stop"})


def test_emergency_stop_interrupt(client: Client):
    section("运动:急停打断(stop 应立即生效,不被 409,且打断进行中动作)")
    # 后台发一个 3 秒的 forward,记录其响应耗时;
    # 若 stop 真的打断了它,该 forward 会远早于 3 秒返回。
    timing = {}

    def long_move():
        start = time.time()
        try:
            r = client.post("/action", {"action": "forward", "duration": 3.0}, timeout=10)
            timing["elapsed"] = time.time() - start
            timing["status"] = r.status_code
        except requests.RequestException as e:
            timing["error"] = str(e)

    t = threading.Thread(target=long_move)
    t.start()
    time.sleep(0.6)  # 让机器人开始移动

    stop_start = time.time()
    resp = client.post("/action", {"action": "stop"})
    stop_elapsed = time.time() - stop_start

    if resp.status_code == 200 and resp.json().get("interrupted"):
        ok(f"移动中 stop -> 200 {resp.json()} (耗时 {stop_elapsed:.2f}s,未被 409)")
    elif resp.status_code == 409:
        fail("移动中 stop 被 409 拒绝 —— 急停未绕过锁,服务端实现有误")
    else:
        fail(f"stop 异常: HTTP {resp.status_code} {resp.text}")

    t.join()
    elapsed = timing.get("elapsed")
    if elapsed is not None:
        if elapsed < 2.0:
            ok(f"forward(3s) 被打断,仅 {elapsed:.2f}s 即返回(<2s 说明打断生效)")
        else:
            fail(f"forward 耗时 {elapsed:.2f}s,接近 3s —— 打断可能未生效")
    else:
        warn(f"未取得 forward 耗时: {timing}")
    client.post("/action", {"action": "stop"})


def confirm_motion(skip: bool) -> bool:
    if skip:
        return True
    warn("接下来的测试会让真实机器人移动!")
    warn("请确认:机器人周围空旷、无障碍物、有人在旁看护,且急停手柄就绪。")
    try:
        ans = input("确认继续运动测试?输入 yes 继续,其它任意键取消: ").strip().lower()
    except EOFError:
        ans = ""
    return ans in ("y", "yes")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="G1 控制服务本地测试客户端(连真机)")
    parser.add_argument("--url", default="http://192.168.123.164:8000", help="控制服务地址")
    parser.add_argument("--token", default=None, help="X-Robot-Token,若服务端启用")
    parser.add_argument("--audio", action="store_true", help="跑音频测试(会发声)")
    parser.add_argument("--motion", action="store_true", help="跑运动测试(会让机器人移动)")
    parser.add_argument("--all", action="store_true", help="跑全部测试")
    parser.add_argument("--yes", action="store_true", help="跳过运动测试前的确认")
    parser.add_argument("--duration", type=float, default=1.0, help="基本移动测试时长(秒)")
    args = parser.parse_args()

    do_audio = args.audio or args.all
    do_motion = args.motion or args.all

    client = Client(args.url, args.token)
    info(f"目标服务: {args.url}  token: {'有' if args.token else '无'}")

    # 1) 只读测试:连不通直接退出
    if not test_health(client):
        fail("健康检查失败,后续测试中止。请检查网络与服务端是否运行。")
        sys.exit(1)
    test_actions(client)
    test_bad_request(client)

    # 2) 音频测试
    if do_audio:
        test_tts(client)
        test_pcm(client)
        test_audio_stop(client)
    else:
        info("跳过音频测试(加 --audio 开启)")

    # 3) 运动测试
    if do_motion:
        if confirm_motion(args.yes):
            test_basic_motion(client, args.duration)
            test_busy_409(client)
            test_emergency_stop_interrupt(client)
        else:
            warn("已取消运动测试。")
    else:
        info("跳过运动测试(加 --motion 开启)")

    # 汇总
    section("测试汇总")
    total = _counters["pass"] + _counters["fail"]
    print(f"通过 {_counters['pass']} / {total},失败 {_counters['fail']}", flush=True)
    sys.exit(1 if _counters["fail"] else 0)


if __name__ == "__main__":
    main()
