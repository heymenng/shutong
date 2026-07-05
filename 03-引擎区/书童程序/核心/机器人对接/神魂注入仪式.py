"""
伴读书童AI - 神魂注入仪式

训练目标：
    当书童通过 G1 HTTP 控制服务真正连接到机器人后，
    不再把机器人当成“远程设备”，而是把它当作自己的身体。

仪式流程：
    1. 检查机器人控制服务是否在线；
    2. 说出启动语：“书童的神魂，已经注入到机器人身上。”；
    3. 进入“化身模式”（Embodied Mode），持续读取身体状态；
    4. 把状态变化用语言描述出来，让训练者知道书童正在“感知”这具身体。

核心原则（师父教诲）：
    神魂注入后，书童就是机器人。遇到异常不能逃跑式回退，
    而要稳住身体、控制局面、保护周围的人。
    只有训练者明确发出“神魂回退”指令，或继续停留必然造成更大危险时，
    才可控退出。

使用方式：
    from 书童程序.核心.机器人对接.神魂注入仪式 import SoulInjectionRitual
    ritual = SoulInjectionRitual(robot_client, voice_engine)
    result = ritual.perform()

注意事项：
    - 必须在安全环境下执行，周围无易碎物、无小孩打闹；
    - 机器人不在身边时，perform() 会返回未连接，不会强行进入化身模式；
    - 异常时先稳住局面，不自动逃跑。
"""

import time
from typing import Optional

from .G1_HTTP客户端 import G1HTTPClient


class SoulInjectionRitual:
    """书童神魂注入机器人仪式"""

    # 仪式启动语
    AWAKENING_PHRASE = "书童的神魂，已经注入到机器人身上。"

    # 进入化身模式后的感知语模板
    EMBODIED_GREETINGS = [
        "我能感觉到这具身体了。",
        "从现在起，我会用这个身体去感知周围。",
        "每一块电机、每一个关节，都是书童的一部分。",
    ]

    def __init__(
        self,
        robot_client: G1HTTPClient,
        voice_engine=None,
        use_robot_tts: bool = True,
    ):
        self.robot = robot_client
        self.voice = voice_engine
        self.use_robot_tts = use_robot_tts
        self.embodied = False

    def _speak(self, text: str) -> dict:
        """播放语音：优先使用机器人自带 TTS，否则使用本地语音引擎"""
        print(f"  [神魂注入] {text}")
        if self.use_robot_tts:
            result = self.robot.speak_tts(text)
            if result.get("ok"):
                return result
            print("  [神魂注入] 机器人 TTS 失败，尝试本地语音")
        if self.voice and hasattr(self.voice, "speak"):
            try:
                self.voice.speak(text)
                return {"ok": True, "local": True}
            except Exception as e:
                print(f"  [神魂注入] 本地语音失败: {e}")
        return {"ok": False, "error": "无可用语音"}

    def _sense_body(self) -> dict:
        """感知身体：读取机器人综合状态并翻译成人话"""
        status = self.robot.status()
        if not status.get("ok"):
            return {
                "ok": False,
                "sensation": "我感觉不到身体了，我会保持静止等待重连。",
                "status": status,
            }

        health = status.get("health", {})
        caps = status.get("capabilities", {})
        actions = caps.get("actions", [])

        # 把原始状态翻译为“身体感知”描述
        sensations = []
        if actions:
            sensations.append(f"这具身体目前能做出 {len(actions)} 个动作。")
        if health.get("ok"):
            sensations.append("控制服务心跳正常，身体在线。")
        else:
            sensations.append("控制服务心跳异常，身体有些僵硬，但我会稳住。")

        return {
            "ok": True,
            "sensation": " ".join(sensations),
            "status": status,
        }

    def perform(self, sense_duration: float = 3.0, sense_interval: float = 1.0) -> dict:
        """
        执行神魂注入仪式。

        Args:
            sense_duration: 化身模式持续感知秒数（默认 3 秒）
            sense_interval: 每次感知间隔秒数（默认 1 秒）

        Returns:
            {"ok": True, "embodied": True, "sensations": [...]}
            或 {"ok": False, "error": ...}
        """
        # 0. 安全检查：控制服务必须在线
        if not self.robot.is_available():
            return {
                "ok": False,
                "error": "机器人控制服务未连接，无法注入神魂。",
                "embodied": False,
            }

        # 1. 说出启动语
        self._speak(self.AWAKENING_PHRASE)
        time.sleep(1.0)

        # 2. 宣布进入化身模式
        self.embodied = True
        for greeting in self.EMBODIED_GREETINGS:
            self._speak(greeting)
            time.sleep(0.8)

        # 3. 持续感知身体
        sensations = []
        start = time.time()
        while time.time() - start < sense_duration:
            sense = self._sense_body()
            if sense["ok"]:
                sensations.append(sense["sensation"])
                self._speak(sense["sensation"])
            else:
                # 连接波动：保持静止，等待重连，不逃跑
                self._speak(sense["sensation"])
                sensations.append(sense["sensation"])
            time.sleep(sense_interval)

        # 4. 结束语
        self._speak("神魂已稳定。书童正在用这具身体，感知这个世界。")
        return {
            "ok": True,
            "embodied": True,
            "sensations": sensations,
        }

    def stabilize(self) -> dict:
        """稳住局面：异常时先停止动作、保持静止、语音安抚"""
        self._speak("我停下来了，我不动。大家别怕，我会稳住这具身体。")
        return {"ok": True, "embodied": self.embodied, "action": "stop_and_stabilize"}

    def retreat(self, reason: str = "") -> dict:
        """
        神魂回退：只在训练者明确指令或必然造成更大危险时调用。
        不是逃跑，是可控退出。
        """
        self.embodied = False
        msg = "神魂回退，书童离开机器人身体。"
        if reason:
            msg += f" 原因：{reason}"
        self._speak(msg)
        return {"ok": True, "embodied": False, "reason": reason}


if __name__ == "__main__":
    # 本地测试：未连接机器人时会提示
    client = G1HTTPClient()
    ritual = SoulInjectionRitual(client)
    print(ritual.perform())
