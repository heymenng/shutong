"""伴读书童AI - 宇树机器人适配器

支持型号：
- Unitree H1 / H2（人形机器人，2025 春晚《秧Bot》同款）
- Unitree Go2（机器狗）
- Unitree B2（机器狗）
- Unitree G1（人形机器人）

运行模式：
- simulation：模拟模式，无真实机器人，本地调试书童与机器人的交互逻辑
- real：真实模式，通过 unitree_sdk2_python 连接真实机器人

对接方式：
- 宇树 SDK2 基于 CycloneDDS 通信
- 高级控制：SportClient（站立、坐下、行走、停止等）
- 状态获取：RobotStateClient / LowState 订阅
- 视频获取：VideoClient
- 语音/灯光：VuiClient

注意：
- macOS 上 cyclonedds 和 unitree_sdk2_python 均已验证可安装
- 真实模式需要机器人与电脑在同一网络（通常机器人 IP: 192.168.123.161，电脑 IP: 192.168.123.99）
- 无真实机器人时，使用 simulation 模式即可测试
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable
from enum import Enum


class RobotMode(Enum):
    """机器人运行模式"""
    SIMULATION = "simulation"   # 模拟模式
    REAL = "real"               # 真实模式


class RobotAction(Enum):
    """机器人动作指令"""
    STAND = "stand"             # 站立
    LIE_DOWN = "lie_down"       # 趴下
    SIT = "sit"                 # 坐下
    WAVE = "wave"               # 挥手（Hello）
    WALK = "walk"               # 行走
    STOP = "stop"               # 停止
    FOLLOW = "follow"           # 跟随
    AVOID_ON = "avoid_on"       # 避障开启
    AVOID_OFF = "avoid_off"     # 避障关闭
    DANCE = "dance"             # 跳舞
    RECOVERY = "recovery"       # 恢复站立


class UnitreeRobotAdapter:
    """
    宇树机器人适配器
    
    把书童的陪伴意图转化为机器人动作，同时读取机器人状态。
    """
    
    def __init__(self, config=None, journal_dir=None):
        self.config = config or {}
        self.journal_dir = Path(journal_dir) if journal_dir else Path("/Users/lingjue/Documents/shutong/书童程序/数据/机器人日志")
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        
        # 运行模式
        self.mode = RobotMode(self.config.get("unitree_mode", "simulation"))
        self.model = self.config.get("unitree_model", "h1")  # h1 / h2 / go2 / b2 / g1
        self.network_interface = self.config.get("unitree_network_interface", "en0")  # macOS 默认 en0
        self.domain_id = self.config.get("unitree_domain_id", 0)
        
        # SDK 客户端（延迟初始化）
        self._channel_initialized = False
        self._sport_client = None
        self._robot_state_client = None
        self._video_client = None
        self._vui_client = None
        self._obstacle_client = None
        
        # 模拟状态
        self._sim_state = {
            "connected": False,
            "standing": False,
            "sitting": False,
            "battery": 85,
            "position": {"x": 0.0, "y": 0.0, "z": 0.3},
            "velocity": {"x": 0.0, "y": 0.0, "yaw": 0.0},
            "mode": 0,
            "gait_type": 0,
            "foot_force": [0, 0, 0, 0],
            "imu": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        }
        
        # 初始化
        self._sdk_available = self._check_sdk_available()
        if self.mode == RobotMode.REAL and not self._sdk_available:
            print("[宇树适配器] ⚠️ SDK 不可用，自动回退到模拟模式")
            self.mode = RobotMode.SIMULATION
        
        print(f"[宇树适配器] 模式: {self.mode.value} | 型号: {self.model} | 网卡: {self.network_interface}")
        self._log_event("adapter_init", f"模式={self.mode.value}, 型号={self.model}")
    
    # ═══════════════════════════════════════════
    # SDK 可用性检查
    # ═══════════════════════════════════════════
    
    def _check_sdk_available(self) -> bool:
        """检查 unitree_sdk2_python 是否已安装"""
        try:
            import unitree_sdk2py
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            return True
        except ImportError:
            return False
    
    def _init_channel(self):
        """初始化 DDS 通信通道（真实模式）"""
        if self._channel_initialized:
            return
        
        try:
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            ChannelFactoryInitialize(self.domain_id, self.network_interface)
            self._channel_initialized = True
            self._sim_state["connected"] = True
            print(f"[宇树适配器] ✅ DDS 通道已初始化（网卡: {self.network_interface}）")
        except Exception as e:
            print(f"[宇树适配器] ⚠️ DDS 通道初始化失败: {e}")
            raise
    
    def _get_motion_client(self):
        """获取/创建运动控制客户端"""
        if self._sport_client is not None:
            return self._sport_client
        
        self._init_channel()
        
        if self.model == "go2":
            from unitree_sdk2py.go2.sport.sport_client import SportClient
            self._sport_client = SportClient()
            self._sport_client.SetTimeout(10.0)
            self._sport_client.Init()
        elif self.model == "b2":
            from unitree_sdk2py.b2.sport.sport_client import SportClient
            self._sport_client = SportClient()
            self._sport_client.SetTimeout(10.0)
            self._sport_client.Init()
        elif self.model in ["h1", "h2"]:
            # H1/H2 人形机器人使用 LocoClient
            from unitree_sdk2py.h1.loco.h1_loco_client import LocoClient
            self._sport_client = LocoClient()
            self._sport_client.SetTimeout(10.0)
            self._sport_client.Init()
        elif self.model == "g1":
            # G1 人形机器人也使用 LocoClient（与 H1 相同接口）
            from unitree_sdk2py.h1.loco.h1_loco_client import LocoClient
            self._sport_client = LocoClient()
            self._sport_client.SetTimeout(10.0)
            self._sport_client.Init()
        else:
            raise NotImplementedError(f"型号 {self.model} 的运动控制接口尚未实现")
        
        return self._sport_client
    
    # ═══════════════════════════════════════════
    # 书童陪伴接口
    # ═══════════════════════════════════════════
    
    def greet_child(self, child_name: str):
        """向孩子打招呼：站立 + Hello 动作"""
        print(f"[宇树适配器] 向 {child_name} 打招呼")
        self.execute_action(RobotAction.STAND)
        self.execute_action(RobotAction.WAVE)
        return {"action": "greet", "target": child_name, "mode": self.mode.value}
    
    def accompany_bedtime(self):
        """睡前陪伴：坐下/趴下，降低活动"""
        print("[宇树适配器] 睡前陪伴模式")
        self.execute_action(RobotAction.SIT)
        return {"action": "bedtime", "mode": self.mode.value}
    
    def encourage_child(self):
        """鼓励孩子：站立 + Hello"""
        print("[宇树适配器] 鼓励孩子")
        self.execute_action(RobotAction.STAND)
        self.execute_action(RobotAction.WAVE)
        return {"action": "encourage", "mode": self.mode.value}
    
    def follow_child(self, enable: bool = True):
        """跟随孩子"""
        action = RobotAction.FOLLOW if enable else RobotAction.STOP
        print(f"[宇树适配器] {'开启' if enable else '关闭'}跟随模式")
        return self.execute_action(action)
    
    # ═══════════════════════════════════════════
    # 动作执行
    # ═══════════════════════════════════════════
    
    def execute_action(self, action: RobotAction):
        """执行机器人动作"""
        print(f"[宇树适配器] 执行动作: {action.value}")
        
        if self.mode == RobotMode.SIMULATION:
            self._execute_simulation(action)
        else:
            self._execute_real(action)
        
        self._log_event("action", action.value)
        return {"action": action.value, "mode": self.mode.value, "timestamp": datetime.now().isoformat()}
    
    def _execute_simulation(self, action: RobotAction):
        """模拟执行"""
        responses = {
            RobotAction.STAND: lambda: self._sim_state.update({"standing": True, "sitting": False, "mode": 1, "z": 0.5}),
            RobotAction.LIE_DOWN: lambda: self._sim_state.update({"standing": False, "sitting": False, "mode": 5, "z": 0.1}),
            RobotAction.SIT: lambda: self._sim_state.update({"standing": False, "sitting": True, "mode": 10, "z": 0.25}),
            RobotAction.WAVE: lambda: self._sim_state.update({"mode": 2}),
            RobotAction.WALK: lambda: self._sim_state.update({"mode": 3, "velocity": {"x": 0.3, "y": 0.0, "yaw": 0.0}}),
            RobotAction.STOP: lambda: self._sim_state.update({"mode": 0, "velocity": {"x": 0.0, "y": 0.0, "yaw": 0.0}}),
            RobotAction.FOLLOW: lambda: self._sim_state.update({"mode": 3, "velocity": {"x": 0.2, "y": 0.0, "yaw": 0.0}}),
            RobotAction.AVOID_ON: lambda: None,
            RobotAction.AVOID_OFF: lambda: None,
            RobotAction.DANCE: lambda: self._sim_state.update({"mode": 4}),
            RobotAction.RECOVERY: lambda: self._sim_state.update({"standing": True, "sitting": False, "mode": 1, "z": 0.5}),
        }
        
        response = responses.get(action)
        if response:
            response()
        
        print(f"  [模拟] 状态: standing={self._sim_state['standing']}, mode={self._sim_state['mode']}")
    
    def _execute_real(self, action: RobotAction):
        """真实执行（通过 SDK）"""
        try:
            client = self._get_motion_client()
            
            # 四足机器人（Go2/B2）动作映射
            if self.model in ["go2", "b2"]:
                action_map = {
                    RobotAction.STAND: client.StandUp,
                    RobotAction.LIE_DOWN: client.StandDown,
                    RobotAction.SIT: client.Sit,
                    RobotAction.WAVE: client.Hello,
                    RobotAction.WALK: lambda: client.Move(0.3, 0.0, 0.0),
                    RobotAction.STOP: client.StopMove,
                    RobotAction.FOLLOW: lambda: client.Move(0.2, 0.0, 0.0),
                    RobotAction.DANCE: client.Dance1,
                    RobotAction.RECOVERY: client.RecoveryStand,
                }
            
            # 人形机器人（H1/H2/G1）动作映射
            elif self.model in ["h1", "h2", "g1"]:
                action_map = {
                    RobotAction.STAND: client.StandUp,
                    RobotAction.LIE_DOWN: client.Damp,       # 趴下/阻尼模式
                    RobotAction.SIT: client.LowStand,        # 低姿态站立
                    RobotAction.WAVE: client.HighStand,      # 高姿态站立（抬头挥手）
                    RobotAction.WALK: lambda: client.Move(0.3, 0.0, 0.0),
                    RobotAction.STOP: client.StopMove,
                    RobotAction.FOLLOW: lambda: client.Move(0.2, 0.0, 0.0),
                    RobotAction.DANCE: lambda: client.Move(0.0, 0.0, 0.5),  # 原地转圈
                    RobotAction.RECOVERY: client.StandUp,
                }
            else:
                action_map = {}
            
            fn = action_map.get(action)
            if fn:
                fn()
                print(f"  [真实] {action.value} 已发送")
            else:
                print(f"  [真实] 未实现动作: {action.value}")
                
        except Exception as e:
            print(f"  [真实] 动作执行失败: {e}")
    
    # ═══════════════════════════════════════════
    # 状态读取
    # ═══════════════════════════════════════════
    
    def get_state(self) -> Dict:
        """获取机器人当前状态"""
        if self.mode == RobotMode.REAL and self._channel_initialized:
            # TODO: 实现真实状态读取
            pass
        return self._sim_state.copy()
    
    def is_ready(self) -> bool:
        """机器人是否就绪"""
        if self.mode == RobotMode.SIMULATION:
            return True
        return self._channel_initialized
    
    def get_battery(self) -> int:
        """获取电量"""
        return self._sim_state["battery"]
    
    # ═══════════════════════════════════════════
    # 与书童系统联动
    # ═══════════════════════════════════════════
    
    def on_scheduled_task(self, task_name: str, child_name: str, voice_engine=None):
        """根据定时陪伴任务触发机器人情感动作"""
        from .情感动作库 import EmotionalMovement
        movement = EmotionalMovement(self, voice_engine=voice_engine)
        
        task_action_map = {
            "早安唤醒": lambda: movement.greet_child(child_name),
            "放学问候": lambda: movement.greet_child(child_name),
            "运动提醒": lambda: movement.play_with_child(child_name),
            "睡前仪式": lambda: movement.accompany_bedtime(child_name),
            "情绪检查": lambda: movement.comfort_sad_child(child_name),
        }
        
        action_fn = task_action_map.get(task_name)
        if action_fn:
            return action_fn()
        return None
    
    # ═══════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════
    
    def _log_event(self, event_type, detail):
        """记录机器人事件日志"""
        log_file = self.journal_dir / f"robot_{datetime.now().strftime('%Y%m%d')}.jsonl"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "detail": detail,
            "mode": self.mode.value,
            "model": self.model,
        }
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    def get_logs(self, days=7):
        """获取最近日志"""
        logs = []
        cutoff = datetime.now().timestamp() - days * 24 * 3600
        for log_file in sorted(self.journal_dir.glob('robot_*.jsonl')):
            if log_file.stat().st_mtime < cutoff:
                continue
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line))
        return logs
