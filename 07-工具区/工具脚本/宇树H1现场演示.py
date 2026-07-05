"""宇树 H1 现场演示脚本

用途：明天下午在宇树现场连接 H1 机器人，展示书童的情感陪伴能力。

安全提示：
- 运行前确保 H1 周围 2 米内无障碍物和人员
- 演示人员站在能随时按急停的位置
- H1 电量充足
- 首次运行建议先执行基础动作测试
"""

import sys
import time
import subprocess
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "03-引擎区"))

from 书童程序.核心.机器人对接.宇树适配器 import UnitreeRobotAdapter, RobotAction
from 书童程序.核心.机器人对接.情感动作库 import EmotionalMovement


def check_network(robot_ip="192.168.123.161"):
    """检查网络是否能 ping 通机器人"""
    print(f"\n[网络检查] 正在 ping {robot_ip} ...")
    try:
        result = subprocess.run(
            ["ping", "-c", "3", "-W", "2", robot_ip],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print("✅ 网络连接正常，可以连接机器人")
            return True
        else:
            print("❌ 无法 ping 通机器人")
            print(result.stdout)
            return False
    except Exception as e:
        print(f"❌ 网络检查失败: {e}")
        return False


def confirm_safety():
    """安全确认"""
    print("\n" + "="*60)
    print("【安全确认】")
    print("="*60)
    checks = [
        "H1 已开机并处于可控制状态",
        "网线/WiFi 已连接",
        "周围 2 米内无障碍物和人员",
        "演示人员站在急停按钮附近",
        "H1 电量充足",
    ]
    for i, check in enumerate(checks, 1):
        print(f"  {i}. {check}")
    
    # 自动演示模式下不等待输入
    print("\n[演示模式] 自动继续（正式演示前请人工确认安全）")
    time.sleep(2)
    return True


def demo_basic_actions(adapter):
    """基础动作测试"""
    print("\n" + "="*60)
    print("【第一阶段：基础动作测试】")
    print("="*60)
    
    actions = [
        ("站立", RobotAction.STAND),
        ("停止", RobotAction.STOP),
        ("低姿态", RobotAction.SIT),
        ("高姿态/抬头", RobotAction.WAVE),
        ("恢复站立", RobotAction.STAND),
        ("停止", RobotAction.STOP),
    ]
    
    for name, action in actions:
        print(f"\n[基础动作] {name}")
        adapter.execute_action(action)
        time.sleep(2.0)


def demo_emotional_companion(adapter):
    """情感陪伴动作展示"""
    print("\n" + "="*60)
    print("【第二阶段：情感陪伴动作展示】")
    print("="*60)
    
    movement = EmotionalMovement(adapter)
    
    # 1. 迎接孩子
    movement.greet_child("小橙子")
    time.sleep(2.0)
    
    # 2. 安慰悲伤的孩子
    movement.comfort_sad_child("小橙子")
    time.sleep(2.0)
    
    # 3. 鼓励孩子
    movement.encourage_child("小橙子")
    time.sleep(2.0)
    
    # 4. 陪孩子玩
    movement.play_with_child("小橙子")
    time.sleep(2.0)
    
    # 5. 睡前陪伴
    movement.accompany_bedtime("小橙子")


def main():
    print("="*60)
    print("【伴读书童AI · 宇树 H1 现场演示】")
    print("="*60)
    
    # 配置
    config = {
        "unitree_mode": "real",
        "unitree_model": "h1",
        "unitree_network_interface": "en0",  # 根据现场网卡修改
    }
    
    # 网络检查
    if not check_network():
        print("\n网络未通，切换到模拟模式演示")
        config["unitree_mode"] = "simulation"
    
    # 安全确认
    confirm_safety()
    
    # 创建适配器
    print("\n[初始化] 创建宇树适配器...")
    adapter = UnitreeRobotAdapter(config)
    
    # 演示
    try:
        demo_basic_actions(adapter)
        demo_emotional_companion(adapter)
    except KeyboardInterrupt:
        print("\n[中断] 用户中断，执行安全停止")
        adapter.execute_action(RobotAction.STOP)
    except Exception as e:
        print(f"\n[异常] {e}")
        adapter.execute_action(RobotAction.STOP)
        raise
    
    print("\n" + "="*60)
    print("【演示完成】")
    print("="*60)


if __name__ == "__main__":
    main()
