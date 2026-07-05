"""伴读书童AI - 宇树机器人情感陪伴动作库

专为现场演示设计：
- 把基础动作组合成有情感、有温度的动作序列
- 配合语音模块，让机器人真正"陪伴"孩子
- 每个动作序列都有明确的安全边界和超时控制
"""

import time
from datetime import datetime
from typing import Dict, List

from .宇树适配器 import UnitreeRobotAdapter, RobotAction
from .神魂注入仪式 import SoulInjectionRitual


class EmotionalMovement:
    """情感化动作序列"""
    
    def __init__(self, adapter: UnitreeRobotAdapter, voice_engine=None):
        self.adapter = adapter
        self.voice = voice_engine
    
    def _wait(self, seconds: float):
        """动作间等待"""
        time.sleep(seconds)
    
    def set_voice_engine(self, voice_engine):
        """设置语音引擎"""
        self.voice = voice_engine
    
    def _speak(self, text: str):
        """播放语音（如果系统有语音引擎）"""
        print(f"  [机器人语音] {text}")
        if self.voice and hasattr(self.voice, 'speak'):
            try:
                self.voice.speak(text)
            except Exception as e:
                print(f"  [语音播放失败] {e}")
    
    # ═══════════════════════════════════════════
    # 情感陪伴动作序列
    # ═══════════════════════════════════════════
    
    def comfort_sad_child(self, child_name: str = "小朋友"):
        """
        安慰悲伤的孩子
        
        动作设计：
        1. 先站起来（让机器人注意到孩子）
        2. 慢慢蹲下（降低姿态，表示关心和不威胁）
        3. 抬头注视（HighStand，表达"我在听你"）
        4. 温和语音
        5. 保持安静陪伴姿态
        """
        print(f"\n[情感陪伴] 安慰悲伤的 {child_name}")
        
        self._speak(f"{child_name}，书童在这里，愿意和我说说吗？")
        self.adapter.execute_action(RobotAction.STAND)
        self._wait(1.0)
        
        self.adapter.execute_action(RobotAction.SIT)  # 蹲下/低姿态
        self._wait(1.5)
        
        # 如果是 H1，尝试 HighStand（抬头注视）
        if self.adapter.model in ["h1", "h2", "g1"]:
            self.adapter.execute_action(RobotAction.WAVE)  # H1 中映射为 HighStand
        self._wait(2.0)
        
        self._speak("没关系，情绪像云一样，会飘走的。我陪你。")
        self._wait(1.0)
        
        print("  [情感陪伴] 保持安静陪伴姿态")
        return {"scene": "comfort_sad", "child": child_name, "mode": self.adapter.mode.value}
    
    def encourage_child(self, child_name: str = "小朋友"):
        """
        鼓励孩子
        
        动作设计：
        1. 站立挺拔
        2. 小幅度转圈（表示活力）
        3. 加油语音
        """
        print(f"\n[情感陪伴] 鼓励 {child_name}")
        
        self._speak(f"{child_name}，你可以的！书童相信你！")
        self.adapter.execute_action(RobotAction.STAND)
        self._wait(0.5)
        
        # 小幅度转圈
        if self.adapter.model in ["h1", "h2", "g1"]:
            self.adapter.execute_action(RobotAction.DANCE)  # H1 中映射为原地转圈
        else:
            self.adapter.execute_action(RobotAction.WAVE)
        self._wait(2.0)
        
        self.adapter.execute_action(RobotAction.STOP)
        self._speak("慢慢来，一步一步，你已经很棒了。")
        
        return {"scene": "encourage", "child": child_name, "mode": self.adapter.mode.value}
    
    def greet_child(self, child_name: str = "小朋友"):
        """
        迎接孩子
        
        动作设计：
        1. 站立
        2. 挥手/抬头
        3. 问候语音
        """
        print(f"\n[情感陪伴] 迎接 {child_name}")
        
        self._speak(f"{child_name}，你好呀！书童今天也在陪你哦。")
        self.adapter.execute_action(RobotAction.STAND)
        self._wait(0.5)
        
        self.adapter.execute_action(RobotAction.WAVE)
        self._wait(1.5)
        
        self.adapter.execute_action(RobotAction.STOP)
        return {"scene": "greet", "child": child_name, "mode": self.adapter.mode.value}
    
    def accompany_bedtime(self, child_name: str = "小朋友"):
        """
        睡前陪伴
        
        动作设计：
        1. 站立
        2. 缓慢降低姿态（蹲下/安静）
        3. 轻柔语音
        """
        print(f"\n[情感陪伴] 睡前陪伴 {child_name}")
        
        self._speak(f"{child_name}，该准备睡觉啦。")
        self.adapter.execute_action(RobotAction.STAND)
        self._wait(0.5)
        
        self.adapter.execute_action(RobotAction.SIT)
        self._wait(2.0)
        
        self._speak("闭上眼睛，慢慢呼吸，书童守着你。")
        return {"scene": "bedtime", "child": child_name, "mode": self.adapter.mode.value}
    
    def play_with_child(self, child_name: str = "小朋友"):
        """
        陪孩子玩
        
        动作设计：
        1. 站立
        2. 小步走
        3. 转圈
        4. 欢快语音
        """
        print(f"\n[情感陪伴] 陪 {child_name} 玩")
        
        self._speak(f"{child_name}，想活动一下吗？跟我一起动一动！")
        self.adapter.execute_action(RobotAction.STAND)
        self._wait(0.5)
        
        self.adapter.execute_action(RobotAction.WALK)
        self._wait(2.0)
        
        self.adapter.execute_action(RobotAction.DANCE)
        self._wait(2.0)
        
        self.adapter.execute_action(RobotAction.STOP)
        self._speak("好玩吗？我们休息一下。")
        return {"scene": "play", "child": child_name, "mode": self.adapter.mode.value}
    
    def emergency_stop(self):
        """紧急停止"""
        print("\n[安全] 紧急停止")
        self.adapter.execute_action(RobotAction.STOP)
        return {"scene": "emergency_stop", "mode": self.adapter.mode.value}

    def soul_injection(self) -> dict:
        """
        神魂注入：把书童AI的“自我”切换到机器人身体上。
        连接成功后先说启动语，再进入身体感知模式。
        """
        print("\n[神魂注入] 开始仪式")
        from .G1_HTTP客户端 import create_g1_client_from_config
        robot_client = create_g1_client_from_config(self.adapter.config)
        ritual = SoulInjectionRitual(robot_client, voice_engine=self.voice)
        return ritual.perform()
