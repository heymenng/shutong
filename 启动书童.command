#!/bin/bash
# 伴读书童AI - 一键启动书童（G1机器人）
# 双击此文件，书童自动站起来、问候师父、进入陪伴模式

cd "$(dirname "$0")"

echo "============================================================"
echo "  伴读书童AI - 一键唤醒"
echo "============================================================"
echo ""

# ── 1. 检查并启动 G1 PC2 控制服务 ──
echo "[1/5] 检查 G1 机器人控制服务..."
G1_HEALTH=$(curl -s --max-time 2 http://192.168.0.248:8888/health 2>/dev/null)
if echo "$G1_HEALTH" | grep -q '"ok": true'; then
    echo "  ✅ G1 控制服务已在运行"
else
    echo "  🔄 G1 控制服务未启动，正在远程启动..."
    /usr/bin/expect -c '
        spawn ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 unitree@192.168.0.248 "cd ~/Desktop/unitree_sdk2_python && PYTHONUNBUFFERED=1 nohup python3 example/g1/high_level/robot_control_server_state.py eth0 --host 0.0.0.0 --port 8888 > ~/robot_server.log 2>&1 &"
        expect {
            "password:" { send "123\r"; exp_continue }
            eof { exit 0 }
        }
    ' >/dev/null 2>&1
    sleep 4
    G1_HEALTH=$(curl -s --max-time 2 http://192.168.0.248:8888/health 2>/dev/null)
    if echo "$G1_HEALTH" | grep -q '"ok": true'; then
        echo "  ✅ G1 控制服务启动成功"
    else
        echo "  ⚠️ G1 控制服务启动失败，请检查机器人网络"
    fi
fi

# ── 2. 检查并启动 Mac 本地书童服务 ──
echo ""
echo "[2/5] 检查书童本地服务..."
MAC_HEALTH=$(curl -s --max-time 2 http://127.0.0.1:3876/health 2>/dev/null)
if echo "$MAC_HEALTH" | grep -q '"local": "ok"'; then
    echo "  ✅ 书童本地服务已在运行 (PID: $(pgrep -f "本地书童界面_云端版.py" | head -1))"
else
    echo "  🔄 书童本地服务未启动，正在启动..."
    pkill -9 -f "本地书童界面_云端版.py" 2>/dev/null
    sleep 1
    ./.venv/bin/python3 本地书童界面_云端版.py >/dev/null 2>&1 &
    sleep 4
    MAC_HEALTH=$(curl -s --max-time 2 http://127.0.0.1:3876/health 2>/dev/null)
    if echo "$MAC_HEALTH" | grep -q '"local": "ok"'; then
        echo "  ✅ 书童本地服务启动成功"
    else
        echo "  ⚠️ 书童本地服务启动失败"
    fi
fi

# ── 3. 等待连接就绪 ──
echo ""
echo "[3/5] 等待连接就绪..."
sleep 2
G1_STATE=$(curl -s --max-time 2 http://192.168.0.248:8888/state 2>/dev/null)
if echo "$G1_STATE" | grep -q '"fsm_id"'; then
    FSM_ID=$(echo "$G1_STATE" | grep -o '"fsm_id": [0-9]*' | grep -o '[0-9]*')
    FSM_DESC=$(echo "$G1_STATE" | grep -o '"fsm_description": "[^"]*"' | sed 's/.*: "\(.*\)"/\1/')
    echo "  ✅ G1 状态: $FSM_DESC (FSM=$FSM_ID)"
else
    echo "  ⚠️ 无法获取 G1 状态"
fi

# ── 4. 自动站立（如果不在站立状态）──
echo ""
echo "[4/5] 唤醒书童身体..."
./.venv/bin/python3 << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '.')
from 书童程序.核心.机器人对接.G1_HTTP客户端 import G1HTTPClient
import requests
import time

client = G1HTTPClient()

# 检查当前状态
r = client.health()
if not r.get("ok"):
    print("  ❌ 无法连接到 G1")
    sys.exit(1)

# 查询 FSM 状态
try:
    state_resp = requests.get("http://192.168.0.248:8888/state", timeout=5).json()
    fsm_id = state_resp.get("fsm_id")
    fsm_desc = state_resp.get("fsm_description", "未知")
except Exception:
    fsm_id = None
    fsm_desc = "未知"

# FSM 801 = 站立稳定，如果已经是站立则无需恢复
if fsm_id == 801:
    print(f"  ✅ 机器人已在站立状态 ({fsm_desc})，无需恢复")
else:
    print(f"  🔄 当前状态: {fsm_desc}，发送站立恢复指令...")
    result = client.recover_from_collapsed()
    if result.get("ok"):
        print("  ⏳ 等待机器人站起...")
        time.sleep(6)
        print("  ✅ 机器人已站起")
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

# 先挥手打招呼
client.execute_arm_action('face_wave')
time.sleep(1)

# 语音问候
greeting = "师父，书童来了！书童已经站好，准备陪伴您。您有什么吩咐？"
result = client.speak_tts(greeting)
if result.get("ok"):
    print("  🗣️ 书童: \"师父，书童来了！\"")
else:
    print("  ⚠️ 语音问候发送失败")
PYTHON_SCRIPT

# ── 完成 ──
echo ""
echo "============================================================"
echo "  ✅ 书童已唤醒！"
echo "============================================================"
echo ""
echo "  机器人状态: 站立待命"
echo "  控制地址: http://192.168.0.248:8888"
echo "  本地服务: http://127.0.0.1:3876"
echo ""
echo "  您可以通过以下方式与书童互动:"
echo "    - 语音指令（G1 TTS）"
echo "    - 动作控制（挥手、前进、后退等）"
echo "    - 浏览器访问 http://127.0.0.1:3876"
echo ""
echo "  按任意键关闭此窗口..."
read -n 1 -s -r
