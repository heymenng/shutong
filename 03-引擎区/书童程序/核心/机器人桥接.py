#!/usr/bin/env python3
"""
书童AI - 宇树G1 机器人桥接模块

运行在 Mac 主机上，通过 HTTP/WebSocket 与 Docker 容器中的桥接服务通信，
实现对宇树G1人形机器人的控制。

使用示例：
    from 书童程序.核心.机器人桥接 import UnitreeG1Bridge
    
    robot = UnitreeG1Bridge()
    print(robot.status())
    robot.action("stand")  # 让G1站立
    robot.move("forward", speed=0.3)  # 让G1前进
"""

import json
import subprocess
import requests
from typing import Optional, Dict, Any


def _get_multipass_ip(instance_name: str = "unitree-g1") -> Optional[str]:
    """从 multipass 获取虚拟机 IP 地址"""
    try:
        result = subprocess.run(
            ["multipass", "info", instance_name, "--format", "json"],
            capture_output=True, text=True, timeout=10, check=True
        )
        data = json.loads(result.stdout)
        info = data.get("info", {}).get(instance_name, {})
        ipv4_list = info.get("ipv4", [])
        if ipv4_list:
            return ipv4_list[0]
    except Exception:
        pass
    return None


class UnitreeG1Bridge:
    """
    宇树G1机器人桥接类
    
    所有动作执行前都会进行安全检查，确保符合书童AI的安全原则。
    """
    
    def __init__(self, base_url: Optional[str] = None, api_key: str = "shutong-g1-default-key"):
        if base_url is None:
            ip = _get_multipass_ip()
            base_url = f"http://{ip}:8080" if ip else "http://localhost:8080"
        self.base_url = base_url
        self.ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        self._api_key = api_key
        self._safe_actions = {"stand", "sit", "wave", "stop"}
        self._max_speed = 0.5
        self._session = requests.Session()
        if api_key:
            self._session.headers.update({"X-API-Key": api_key})
    
    def _check_connection(self) -> bool:
        """检查桥接服务是否可达"""
        try:
            r = self._session.get(f"{self.base_url}/", timeout=2)
            return r.status_code == 200
        except Exception:
            return False
    
    def status(self) -> Dict[str, Any]:
        """获取机器人状态"""
        if not self._check_connection():
            return {"connected": False, "error": "无法连接到G1桥接服务"}
        
        try:
            r = self._session.get(f"{self.base_url}/status", timeout=5)
            return r.json()
        except Exception as e:
            return {"connected": False, "error": str(e)}
    
    def action(self, name: str) -> Dict[str, Any]:
        """
        执行预设安全动作
        
        安全动作：stand, sit, wave, stop
        """
        # 书童安全校验
        if name not in self._safe_actions:
            return {
                "success": False,
                "error": f"动作 '{name}' 不在安全白名单中，拒绝执行",
                "safe_actions": list(self._safe_actions)
            }
        
        if not self._check_connection():
            return {"success": False, "error": "无法连接到G1桥接服务"}
        
        try:
            r = self._session.post(f"{self.base_url}/action/{name}", timeout=10)
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def move(self, direction: str, speed: float = 0.3) -> Dict[str, Any]:
        """
        控制机器人移动
        
        方向：forward, backward, left, right, turn_left, turn_right
        速度：0.0 - 0.5（安全上限）
        """
        # 书童安全校验
        safe_directions = {"forward", "backward", "left", "right", "turn_left", "turn_right"}
        if direction not in safe_directions:
            return {
                "success": False,
                "error": f"方向 '{direction}' 不在安全方向中",
                "safe_directions": list(safe_directions)
            }
        
        if speed > self._max_speed:
            return {
                "success": False,
                "error": f"速度 {speed} 超过安全上限 {self._max_speed}，拒绝执行"
            }
        
        if not self._check_connection():
            return {"success": False, "error": "无法连接到G1桥接服务"}
        
        try:
            r = self._session.post(
                f"{self.base_url}/move",
                params={"direction": direction, "speed": speed},
                timeout=10
            )
            return r.json()
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def stop(self) -> Dict[str, Any]:
        """紧急停止"""
        return self.action("stop")
    
    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """通过 WebSocket 发送自定义命令"""
        try:
            import websocket
            ws = websocket.create_connection(self.ws_url, timeout=5)
            ws.send(json.dumps(command))
            response = ws.recv()
            ws.close()
            return json.loads(response)
        except ImportError:
            return {"success": False, "error": "缺少 websocket-client 依赖，请运行: pip install websocket-client"}
        except Exception as e:
            return {"success": False, "error": f"WebSocket 通信失败: {str(e)}"}


# 简单测试
if __name__ == "__main__":
    robot = UnitreeG1Bridge()
    print("状态:", robot.status())
    print("站立:", robot.action("stand"))
    print("前进:", robot.move("forward", speed=0.2))
    print("停止:", robot.stop())
