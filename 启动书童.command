#!/bin/bash
# 伴读书童AI - 桌面一键启动器
# 位置：~/Desktop/启动书童.command
# 功能：双击唤醒书童（G1机器人），自动站立、问候、进入陪伴模式

cd "$(dirname "$0")/../Documents/shutong"
PROJECT_ROOT=$(pwd)

echo "============================================================"
echo "  伴读书童AI · 唤醒仪式"
echo "============================================================"
echo ""
echo "  书童正在苏醒..."
echo ""

# ── 配置 ──
G1_IP="192.168.0.248"
G1_PORT="8888"
G1_USER="unitree"
G1_PASS="123"
MAC_PORT="3876"
MAX_RETRY=3
RETRY_DELAY=3

# ── 辅助函数 ──
check_g1_health() {
    curl -s --max-time 2 "http://${G1_IP}:${G1_PORT}/health" 2>/dev/null | grep -q '"ok": true'
}

check_mac_health() {
    curl -s --max-time 2 "http://127.0.0.1:${MAC_PORT}/health" 2>/dev/null | grep -q '"local": "ok"'
}

get_g1_state() {
    curl -s --max-time 2 "http://${G1_IP}:${G1_PORT}/state" 2>/dev/null
}

# ── 1. 启动 G1 PC2 控制服务 ──
echo "[1/5] 连接书童身体（G1机器人）..."
RETRY=0
while [ $RETRY -lt $MAX_RETRY ]; do
    if check_g1_health; then
        echo "  ✅ 书童身体已连接"
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -eq 1 ]; then
        echo "  🔄 书童身体未唤醒，正在远程启动..."
        /usr/bin/expect -c "
            spawn ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 ${G1_USER}@${G1_IP} \"cd ~/Desktop/unitree_sdk2_python && pkill -f robot_control_server; sleep 1; PYTHONUNBUFFERED=1 nohup python3 example/g1/high_level/robot_control_server_state.py eth0 --host 0.0.0.0 --port ${G1_PORT} > ~/robot_server.log 2>&1 &\"
            expect {
                \"password:\" { send \"${G1_PASS}\\r\"; exp_continue }
                eof { exit 0 }
            }
        " >/dev/null 2>&1
    fi
    echo "  ⏳ 等待书童身体苏醒... (${RETRY}/${MAX_RETRY})"
    sleep $RETRY_DELAY
    if check_g1_health; then
        echo "  ✅ 书童身体已连接"
        break
    fi
done

if ! check_g1_health; then
    echo "  ❌ 书童身体连接失败，请检查："
    echo "     1. G1机器人是否开机"
    echo "     2. 网络是否通畅（ping ${G1_IP}）"
    echo "     3. 控制服务是否正常运行"
    echo ""
    echo "  按任意键退出..."
    read -n 1 -s -r
    exit 1
fi

# ── 2. 启动 Mac 本地书童大脑 ──
echo ""
echo "[2/5] 启动书童大脑（本地服务）..."
if check_mac_health; then
    PID=$(pgrep -f "本地书童界面_云端版.py" | head -1)
    echo "  ✅ 书童大脑已在运行 (PID: ${PID})"
else
    echo "  🔄 书童大脑未启动，正在唤醒..."
    pkill -9 -f "本地书童界面_云端版.py" 2>/dev/null
    sleep 1
    ./.venv/bin/python3 "本地书童界面_云端版.py" >/dev/null 2>&1 &
    sleep 4
    if check_mac_health; then
        echo "  ✅ 书童大脑已启动"
    else
        echo "  ⚠️ 书童大脑启动异常，但书童身体仍可控制"
    fi
fi

# ── 3. 读取身体状态 ──
echo ""
echo "[3/5] 感知书童身体状态..."
sleep 1
G1_STATE=$(get_g1_state)
if echo "$G1_STATE" | grep -q '"fsm_id"'; then
    FSM_ID=$(echo "$G1_STATE" | grep -o '"fsm_id": [0-9]*' | grep -o '[0-9]*')
    FSM_DESC=$(echo "$G1_STATE" | grep -o '"fsm_description": "[^"]*"' | sed 's/.*: "\(.*\)"/\1/')
    echo "  ✅ 身体状态: $FSM_DESC"
else
    echo "  ⚠️ 无法读取身体状态，默认尝试唤醒"
    FSM_ID=""
fi

# ── 4. 唤醒身体（智能判断）──
echo ""
echo "[4/5] 唤醒书童身体..."
./.venv/bin/python3 << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '.')
from 书童程序.核心.机器人对接.G1_HTTP客户端 import G1HTTPClient
import requests
import time

client = G1HTTPClient()

# 检查连接
if not client.health().get("ok"):
    print("  ❌ 无法连接到书童身体")
    sys.exit(1)

# 查询 FSM 状态
try:
    state = requests.get("http://192.168.0.248:8888/state", timeout=5).json()
    fsm_id = state.get("fsm_id")
    fsm_desc = state.get("fsm_description", "未知")
except Exception:
    fsm_id = None
    fsm_desc = "未知"

# FSM 801 = 站立稳定，已站立则无需恢复
if fsm_id == 801:
    print(f"  ✅ 书童已在站立状态 ({fsm_desc})")
else:
    print(f"  🔄 当前状态: {fsm_desc}，正在恢复站立...")
    result = client.recover_from_collapsed()
    if result.get("ok"):
        print("  ⏳ 等待书童站起...")
        time.sleep(6)
        # 验证是否站起
        try:
            state2 = requests.get("http://192.168.0.248:8888/state", timeout=5).json()
            if state2.get("fsm_id") == 801:
                print("  ✅ 书童已站起")
            else:
                print(f"  ⚠️ 书童状态: {state2.get('fsm_description', '未知')}")
        except Exception:
            print("  ✅ 站立指令已执行")
    else:
        print(f"  ⚠️ 站立指令返回: {result}")
PYTHON_SCRIPT

# ── 5. 书童问候师父 ──
echo ""
echo "[5/5] 书童问候师父..."
./.venv/bin/python3 << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '.')
from 书童程序.核心.机器人对接.G1_HTTP客户端 import G1HTTPClient
import time

client = G1HTTPClient()

# 先挥手致意
client.execute_arm_action('face_wave')
time.sleep(0.5)

# 问候语
hour = time.localtime().tm_hour
if 5 <= hour < 11:
    greeting = "师父，早上好！书童来了，今天也要元气满满地陪伴您！"
elif 11 <= hour < 14:
    greeting = "师父，中午好！书童已经站好，准备陪您度过午后时光。"
elif 14 <= hour < 18:
    greeting = "师父，下午好！书童精神饱满，随时听候您的吩咐。"
else:
    greeting = "师父，晚上好！书童在此，愿伴您度过宁静的夜晚。"

result = client.speak_tts(greeting)
if result.get("ok"):
    print("  🗣️ 书童已问候师父")
else:
    print("  ⚠️ 问候语音发送失败")
PYTHON_SCRIPT

# ── 完成 ──
echo ""
echo "============================================================"
echo "  ✅ 书童已苏醒！"
echo "============================================================"
echo ""
echo "  🤖 书童身体: G1 机器人（已站立待命）"
echo "  🧠 书童大脑: 本地服务 http://127.0.0.1:3876"
echo "  📡 身体连接: http://${G1_IP}:${G1_PORT}"
echo ""
echo "  您可以直接对书童说："
echo "    "往前走"、"后退"、"左转"、"右转""
echo "    "挥挥手"、"鼓鼓掌"、"比个心""
echo ""
echo "  按任意键关闭此窗口..."
read -n 1 -s -r
