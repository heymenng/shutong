# 笔记本 Agent 调用 G1 控制服务说明（V2 — 实测修订版）

> 本文档是 `G1_CONTROL_CLIENT.md` 的实测修订版。原文档基于 API 设计编写，V2 基于真机实测结果，剔除了不生效的动作，新增了已验证的 `arm` 服务手臂动作。

## 核心变化速览

| 项目 | 原文档 (V1) | V2 实测版 |
|------|-------------|-----------|
| 手臂挥手 | `POST /action {"action":"wave"}` ❌ 不生效 | `POST /arm_action {"action":"face_wave"}` ✅ |
| 握手 | `POST /action {"action":"shake_hand"}` ❌ 不生效 | `POST /arm_action {"action":"shake_hand_arm"}` ✅ |
| 鼓掌/击掌/比心 | 不支持 | `POST /arm_action` ✅ |
| 高/低姿站立 | `POST /action {"action":"high_stand"}` ❌ | 已移除 |
| 零力矩 | `POST /action {"action":"zero_torque"}` ❌ 危险 | 已移除 |
| 端口 | 8000 | 8888（8000 被视频服务占用） |
| 手臂服务 | 无 | 新增 `POST /arm_action`，走 G1ArmActionClient |

> **原因说明**：`LocoClient`（sport 服务）的 `SetStandHeight`（API 7104）和 `SetTaskId`（API 7106）在当前固件上不工作。只有 `SetVelocity`（API 7105）和 `SetFsmId`（API 7101）正常。手臂动作改用独立的 `G1ArmActionClient`（arm 服务），已验证全部可用。

---

## 1. 总体架构

```text
笔记本 / Mac Agent
  用户语音 / 文本
      |
      v
本地 ASR / 本地 LLM / 对话 Agent / 本地 TTS
      |
      | 生成动作 JSON、TTS 文本或 PCM 音频
      v
HTTP POST
      |
      v
G1 PC2: robot_control_server.py
      |
      | unitree_sdk2_python / DDS
      |
      ├── sport 服务 → 移动控制（/action）
      ├── arm 服务 → 手臂动作（/arm_action）
      └── audio 服务 → 声音播放
      v
机器人执行动作 / 扬声器播放声音
```

---

## 2. 网络前提

| 设备 | 地址 | 说明 |
|------|------|------|
| G1 PC2 (WiFi) | `192.168.0.248:8888` | 笔记本通过 WiFi 访问（推荐） |
| G1 PC2 (G1内网) | `192.168.123.164:8888` | G1 内部网络 |

笔记本先确认连通性：

```bash
curl http://192.168.0.248:8888/health
# 期望: {"ok": true, "service": "g1_robot_control_server"}
```

---

## 3. 接口总览

| 方法 | 路径 | 作用 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/actions` | 查询全部接口和参数限制 |
| POST | `/action` | 运动/姿态控制（sport 服务） |
| POST | `/arm_action` | **新增** 手臂动作（arm 服务） |
| POST | `/audio/tts` | 文字转语音 |
| POST | `/audio/pcm` | PCM 音频播放（支持流式） |
| POST | `/audio/stop` | 停止音频流 |

---

## 4. 运动控制 `POST /action`

### 4.1 支持的 action（仅保留实测可用）

```
stand       ⚠️ 蹲姿起立
squat       ⚠️ 站立到蹲下
lie_to_stand ⚠️ 躺姿起立
damp        ⚠️ 阻尼模式（机器人会瘫倒，紧急情况用）
stop        急停

forward     前进
back        后退
left        左移
right       右移
turn_left   左转
turn_right  右转
move        自定义速度
```

### 4.2 已移除的 action（不生效或危险）

| 原 action | 移除原因 |
|-----------|----------|
| `wave` | sport 服务 SetTaskId 不工作 → 改用 `/arm_action` 的 `face_wave` 或 `high_wave` |
| `shake_hand` | sport 服务 SetTaskId 不工作 → 改用 `/arm_action` 的 `shake_hand_arm` |
| `low_stand` | sport 服务 SetStandHeight 不工作 |
| `high_stand` | sport 服务 SetStandHeight 不工作 |
| `zero_torque` | 不生效 + 危险（关节卸力） |

### 4.3 参数与限制

| action | 可选字段 | 范围 |
|--------|----------|------|
| `forward`/`back`/`left`/`right`/`turn_left`/`turn_right` | `duration` | 0.1~3.0s，默认 1.0 |
| `move` | `vx` | -0.5 ~ 0.5 |
| | `vy` | -0.4 ~ 0.4 |
| | `vrot` | -0.6 ~ 0.6 |
| | `duration` | 0.1~3.0s，默认 1.0 |

### 4.4 curl 示例

```bash
G1="http://192.168.0.248:8888"

# 移动
curl -X POST $G1/action -H "Content-Type: application/json" -d '{"action":"forward","duration":0.5}'
curl -X POST $G1/action -H "Content-Type: application/json" -d '{"action":"turn_left","duration":0.5}'
curl -X POST $G1/action -H "Content-Type: application/json" -d '{"action":"move","vx":0.2,"vy":0,"vrot":0,"duration":0.5}'

# 急停
curl -X POST $G1/action -H "Content-Type: application/json" -d '{"action":"stop"}'
```

### 4.5 409 忙时拒绝

与 V1 相同：`/action` 采用忙时拒绝，`stop` / `damp` 不受限制、可打断进行中动作。

---

## 5. 手臂动作 `POST /arm_action`（新增）

### 5.1 支持的动作

| action | 底层 arm 服务 ID | 说明 |
|--------|------------------|------|
| `face_wave` | 25 | 脸部高度挥手 |
| `high_wave` | 26 | 高举挥手 |
| `shake_hand_arm` | 27 | 握手 |
| `clap` | 17 | 鼓掌 |
| `high_five` | 18 | 击掌 |
| `hug` | 19 | 拥抱 |
| `heart` | 20 | 比心 |
| `hands_up` | 15 | 举手 |
| `two_hand_kiss` | 11 | 双手飞吻 |
| `release_arm` | 99 | 手臂归位 |

### 5.2 请求格式

```json
{"action":"clap"}
```

所有手臂动作无额外参数。手臂动作使用独立锁，不与 `/action` 运动控制互斥。

### 5.3 curl 示例

```bash
G1="http://192.168.0.248:8888"

curl -X POST $G1/arm_action -H "Content-Type: application/json" -d '{"action":"clap"}'
curl -X POST $G1/arm_action -H "Content-Type: application/json" -d '{"action":"high_wave"}'
curl -X POST $G1/arm_action -H "Content-Type: application/json" -d '{"action":"shake_hand_arm"}'
curl -X POST $G1/arm_action -H "Content-Type: application/json" -d '{"action":"heart"}'
curl -X POST $G1/arm_action -H "Content-Type: application/json" -d '{"action":"release_arm"}'
```

### 5.4 Python 调用

```python
import requests

BASE_URL = "http://192.168.0.248:8888"

def arm_action(action: str) -> dict:
    resp = requests.post(
        f"{BASE_URL}/arm_action",
        json={"action": action},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

arm_action("clap")
arm_action("high_wave")
arm_action("release_arm")
```

---

## 6. 音频接口

与原文档一致，无变化：`POST /audio/tts`、`POST /audio/pcm`、`POST /audio/stop`。

---

## 7. `GET /actions` 返回示例

```json
{
  "ok": true,
  "actions": ["stand", "squat", "lie_to_stand", "damp", "stop",
              "forward", "back", "left", "right", "turn_left", "turn_right", "move"],
  "arm_actions": ["clap", "high_five", "hug", "heart", "face_wave", "high_wave",
                  "shake_hand_arm", "hands_up", "release_arm", "two_hand_kiss"],
  "arm_endpoint": "/arm_action",
  "audio_endpoints": ["/audio/tts", "/audio/pcm", "/audio/stop"],
  "move_limits": {"vx": [-0.5, 0.5], "vy": [-0.4, 0.4], "vrot": [-0.6, 0.6], "duration": [0.1, 3.0]},
  "pcm_format": "s16le/16000Hz/mono",
  "pcm_max_bytes_per_request": 192000
}
```

---

## 8. 推荐的 LLM 输出约束（更新）

```text
你是宇树 G1 机器人动作解析器。
你的任务是把用户自然语言转换成机器人动作 JSON。
你只能输出 JSON。

运动动作（发送到 /action）：
  允许: stand, stop, forward, back, left, right, turn_left, turn_right, move
  移动类可含 duration（秒，0.1~3）。
  move 可含 vx/vy/vrot。

手臂动作（发送到 /arm_action）：
  允许: face_wave, high_wave, shake_hand_arm, clap, high_five,
        hug, heart, hands_up, two_hand_kiss, release_arm

不确定时输出:
  运动: {"action":"stop"}
  手臂: {"action":"release_arm"}
```

---

## 9. 服务启动

PC2 上的启动命令：

```bash
cd ~/Desktop/unitree_sdk2_python
PYTHONUNBUFFERED=1 nohup python3 example/g1/high_level/robot_control_server.py eth0 \
  --host 0.0.0.0 --port 8888 > ~/robot_server.log 2>&1 &
```

列出自定义端口。之前 8000 已被视频录制服务占用所以改成 8888。

---

## 10. 变更清单（对比 V1）

| 变化 | 说明 |
|------|------|
| **新增 `/arm_action`** | G1ArmActionClient（arm 服务），10 个手臂动作全部实测通过 |
| **移除 `wave`、`shake_hand`** | sport 服务 SetTaskId（API 7106）不工作 |
| **移除 `low_stand`、`high_stand`** | sport 服务 SetStandHeight（API 7104）不工作 |
| **移除 `zero_torque`** | 不生效且危险 |
| **端口 8000→8888** | 8000 被占用 |
| **IP 补充 WiFi 地址** | `192.168.0.248` 供笔记本局域网访问 |
| **动作数变化** | /action: 17→12，新增 /arm_action: 0→10 |
