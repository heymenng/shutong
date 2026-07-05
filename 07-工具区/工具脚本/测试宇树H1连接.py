"""宇树 H1 单机真实连接测试脚本"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.核心.机器人对接.宇树适配器 import UnitreeRobotAdapter, RobotAction

print("=== 宇树 H1 真实连接测试 ===")
print("请确认：")
print("1. H1 已开机")
print("2. 网线已连接 Mac 和 H1")
print("3. Mac IP 已设置为 192.168.123.99")
print("4. 周围 2 米内无障碍物和人员")
print()

adapter = UnitreeRobotAdapter({
    "unitree_mode": "real",
    "unitree_model": "h1",
    "unitree_network_interface": "en0",  # 根据实际网卡修改
})

print("\n=== 测试 1：站立 ===")
adapter.execute_action(RobotAction.STAND)

print("\n=== 测试 2：停止 ===")
adapter.execute_action(RobotAction.STOP)

print("\n=== 测试 3：状态读取 ===")
print(adapter.get_state())

print("\n测试完成")
