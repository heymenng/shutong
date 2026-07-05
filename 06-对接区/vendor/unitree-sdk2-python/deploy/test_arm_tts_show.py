#!/usr/bin/env python3
"""G1 手臂动作 + TTS 配合演示脚本。

连真实 PC2 上运行的 robot_control_server,把"说话"和"手臂动作"组合成一段表演:
每幕先用 TTS 说一句台词,同时(并发)触发一个手臂动作,语音和动作同步进行。

服务端 tts 与 arm_action 分别持 audio_lock / arm_lock,二者互不阻塞,所以可以
一边说话一边做手臂动作 —— 这正是本脚本演示的配合效果。

安全:手臂动作会让机器人真实挥臂,运行前要求确认周围空旷、有人看护(用 --yes 跳过)。
      不会触发任何行走类动作(无 forward/move 等),但挥臂仍需空间。

注意:每个手臂动作在机器人侧有自己的执行时长(ExecuteAction 非阻塞立即返回)。
      若上一幕动作还没做完就发下一幕,会被服务端以 code=7401(arm busy)拒绝。
      因此每幕动作展示 hold 秒后,主动调用 release_arm(手臂归位)提前结束,
      保证下一幕从一个干净归位的状态开始。同时会对 7401 做有限重试兜底。

示例（在仓库根目录执行）:
  python deploy/test_arm_tts_show.py --url http://192.168.0.248:8888
  python deploy/test_arm_tts_show.py --url http://192.168.0.248:8888 --token g1secret --yes
  python deploy/test_arm_tts_show.py --url http://192.168.0.248:8888 --dry      # 只说话不动手
  python deploy/test_arm_tts_show.py --url http://192.168.0.248:8888 --scene heart  # 只演指定幕
"""
import argparse
import sys
import threading
import time

import requests


# ---------------------------------------------------------------------------
# 表演剧本:每幕 = (台词, 手臂动作, 说完/做完后停留秒数)
#   手臂动作取值:clap high_five hug heart face_wave high_wave
#                shake_hand_arm hands_up release_arm two_hand_kiss
#   台词为空则该幕只做动作不说话。
# ---------------------------------------------------------------------------
SCENES = [
    ("大家好,我是书童,欢迎大家光临科诺", "high_wave", 0.6),
    ("先给大家鼓个掌",                        "clap",      0.5),
    ("送你们一颗爱心",                        "heart",     0.6),
    ("来,抱一个",                             "hug",       1.8),
    ("击个掌",                                "high_five", 1.8),
    ("最后举双手谢谢大家",                    "hands_up",  1.8),
    ("",                                      "release_arm", 0.5),  # 收尾:松臂
]


# ---------------------------------------------------------------------------
# 输出辅助(风格与 test_robot_control_client.py 一致)
# ---------------------------------------------------------------------------
def info(msg):
    print(f"[INFO] {msg}", flush=True)


def ok(msg):
    print(f"[PASS] {msg}", flush=True)


def warn(msg):
    print(f"[WARN] {msg}", flush=True)


def fail(msg):
    print(f"[FAIL] {msg}", flush=True)


def section(title):
    print("\n" + "=" * 60, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 60, flush=True)


# ---------------------------------------------------------------------------
# HTTP 客户端
# ---------------------------------------------------------------------------
class Client:
    def __init__(self, base_url: str, token: str = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["X-Robot-Token"] = self.token
        return h

    def get(self, path: str):
        return requests.get(f"{self.base_url}{path}", headers=self._headers(),
                            timeout=self.timeout)

    def post(self, path: str, payload: dict, timeout: float = None):
        return requests.post(f"{self.base_url}{path}", json=payload,
                             headers=self._headers(),
                             timeout=timeout or self.timeout)


# ---------------------------------------------------------------------------
# 手臂动作调用:对 7401(arm busy)做有限重试,每次重试前先归位再等待
# ---------------------------------------------------------------------------
def call_arm(client: Client, arm: str, retries: int = 3) -> dict:
    """触发一个手臂动作,返回结果 dict。遇 7401 先 release_arm 归位再重试。"""
    last = {}
    for attempt in range(1, retries + 1):
        try:
            r = client.post("/arm_action", {"action": arm}, timeout=20)
        except requests.RequestException as e:
            last = {"error": str(e)}
            break
        last = {"status": r.status_code, "body": r.text}
        if r.status_code == 200:
            return last
        # 7401 = arm busy,上一动作未结束:先归位,稍等再试
        if r.status_code == 400 and "7401" in r.text and attempt < retries:
            warn(f"动作 {arm} 被拒(7401 忙),归位后重试 {attempt}/{retries}")
            client.post("/arm_action", {"action": "release_arm"}, timeout=20)
            time.sleep(0.8)
            continue
        return last
    return last


# ---------------------------------------------------------------------------
# 单步:说台词 + 做动作(并发),展示后归位
# ---------------------------------------------------------------------------
def play_scene(client: Client, idx: int, text: str, arm: str, hold: float,
               dry: bool) -> bool:
    section(f"第 {idx} 幕:动作={arm or '无'}  台词={text or '无'}")

    tts_result = {}
    arm_result = {}

    def speak():
        if not text:
            return
        try:
            r = client.post("/audio/tts", {"text": text, "speaker_id": 0},
                            timeout=20)
            tts_result["status"] = r.status_code
            tts_result["body"] = r.text
        except requests.RequestException as e:
            tts_result["error"] = str(e)

    def act():
        if dry or not arm:
            return
        arm_result.update(call_arm(client, arm))

    # 两个锁独立,可真正并发:一边说话一边动手
    t_tts = threading.Thread(target=speak)
    t_arm = threading.Thread(target=act)
    t_tts.start()
    t_arm.start()
    t_tts.join()
    t_arm.join()

    success = True

    if text:
        if tts_result.get("status") == 200:
            ok(f"TTS 已播报: {text}")
        else:
            fail(f"TTS 失败: {tts_result}")
            success = False

    if arm and not dry:
        if arm_result.get("status") == 200:
            ok(f"手臂动作完成: {arm}")
        else:
            fail(f"手臂动作失败: {arm_result}")
            success = False
    elif dry and arm:
        info(f"(dry 模式)跳过手臂动作: {arm}")

    # 该幕停留,让动作/语音有展示时间
    if hold > 0:
        time.sleep(hold)

    # 归位:提前结束本幕动作,保证下一幕从干净状态开始(release_arm 本身幂等)
    if arm and arm != "release_arm" and not dry:
        client.post("/arm_action", {"action": "release_arm"}, timeout=20)
        info("已手臂归位,准备下一幕")

    return success


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def confirm(skip: bool) -> bool:
    if skip:
        return True
    warn("接下来的表演会让机器人真实挥臂!")
    warn("请确认:机器人周围空旷、无障碍物、有人在旁看护,且急停手柄就绪。")
    try:
        ans = input("确认开始表演?输入 yes 继续,其它任意键取消: ").strip().lower()
    except EOFError:
        ans = ""
    return ans in ("y", "yes")


def main():
    parser = argparse.ArgumentParser(description="G1 手臂动作 + TTS 配合演示")
    parser.add_argument("--url", default="http://192.168.0.248:8888",
                        help="控制服务地址")
    parser.add_argument("--token", default=None, help="X-Robot-Token,若服务端启用")
    parser.add_argument("--yes", action="store_true", help="跳过开始前的确认")
    parser.add_argument("--dry", action="store_true",
                        help="只说话不做手臂动作(用于先验证 TTS)")
    parser.add_argument("--scene", default=None,
                        help="只演指定动作的一幕(如 heart / clap),不填则演全剧")
    parser.add_argument("--speaker", type=int, default=0, help="TTS speaker_id 0~10")
    args = parser.parse_args()

    client = Client(args.url, args.token)
    info(f"目标服务: {args.url}  token: {'有' if args.token else '无'}  "
         f"dry: {args.dry}")

    # 1) 健康检查:连不通直接退出
    section("健康检查")
    try:
        resp = client.get("/health")
    except requests.RequestException as e:
        fail(f"无法连接服务: {e}")
        sys.exit(1)
    if resp.status_code == 200 and resp.json().get("ok"):
        ok(f"/health -> {resp.json()}")
    else:
        fail(f"/health 异常: HTTP {resp.status_code} {resp.text}")
        sys.exit(1)

    # 2) 选择剧本
    scenes = SCENES
    if args.scene:
        scenes = [(t, a, h) for (t, a, h) in SCENES if a == args.scene]
        if not scenes:
            fail(f"未找到动作 '{args.scene}'。可用: "
                 f"{', '.join(sorted({a for _, a, _ in SCENES if a}))}")
            sys.exit(1)
        info(f"仅演指定幕: {args.scene}")

    # 3) 确认
    if not confirm(args.yes):
        warn("已取消表演。")
        sys.exit(0)

    # 4) 逐幕表演
    section("开始表演")
    passed = 0
    total = 0
    for i, (text, arm, hold) in enumerate(scenes, 1):
        total += 1
        if play_scene(client, i, text, arm, hold, args.dry):
            passed += 1

    # 5) 汇总
    section("表演汇总")
    print(f"完成 {passed} / {total} 幕", flush=True)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
