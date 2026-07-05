# G1 Robot Control Server 使用说明

本文档说明 `example/g1/high_level/robot_control_server.py` 提供的轻量级 HTTP 控制服务。

## 1. 设计目标

该服务运行在 G1 的 PC2 用户开发板上，例如 `192.168.123.164`。

推荐链路：

```text
局域网内笔记本 / Mac
  麦克风 / ASR / 本地 LLM / 本地 TTS / 上层业务
        |
        | HTTP JSON 请求
        v
G1 PC2: robot_control_server.py
        |
        | unitree_sdk2_python / DDS
        v
G1 PC1 / sport_mode / audio service
        |
        v
G1 机器人运动 / 扬声器播放
```

这样做的目的是：

- DDS 通信留在 G1 内部网络中；
- 笔记本通过普通 HTTP 请求 PC2；
- 笔记本不需要直接跨子网调用 DDS；
- 同时支持运动控制、G1 内置 TTS、外部 PCM 音频播放。

## 2. 服务文件位置

```text
example/g1/high_level/robot_control_server.py
```

## 3. HTTP 接口总览

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/actions` | 查询支持动作、音频接口和参数限制 |
| POST | `/action` | 执行机器人运动/姿态动作 |
| POST | `/audio/tts` | 让 G1 使用内置 TTS 播放文字 |
| POST | `/audio/pcm` | 上传 PCM 音频数据并通过 G1 扬声器播放 |
| POST | `/audio/stop` | 停止指定音频播放流 |

## 4. 运动控制能力

### 4.1 支持的 action

| action | 说明 | 底层 SDK 调用 |
|---|---|---|
| `damp` | 阻尼模式 | `LocoClient.Damp()` |
| `stand` | 蹲姿/阻尼后站起 | `Damp()` + `Squat2StandUp()` |
| `squat` | 站立到蹲下 | `StandUp2Squat()` |
| `lie_to_stand` | 躺姿起立 | `Damp()` + `Lie2StandUp()` |
| `low_stand` | 低姿站立 | `LowStand()` |
| `high_stand` | 高姿站立 | `HighStand()` |
| `zero_torque` | 零力矩 | `ZeroTorque()` |
| `wave` | 招手 | `WaveHand()` |
| `shake_hand` | 握手 | `ShakeHand()` 两阶段调用 |
| `stop` | 停止移动 | `StopMove()` |
| `move` | 自定义速度移动 | `SetVelocity(vx, vy, vrot, duration)` |
| `forward` | 前进 | `SetVelocity(0.3, 0, 0, duration)` |
| `back` | 后退 | `SetVelocity(-0.2, 0, 0, duration)` |
| `left` | 左移 | `SetVelocity(0, 0.2, 0, duration)` |
| `right` | 右移 | `SetVelocity(0, -0.2, 0, duration)` |
| `turn_left` | 左转 | `SetVelocity(0, 0, 0.3, duration)` |
| `turn_right` | 右转 | `SetVelocity(0, 0, -0.3, duration)` |

### 4.2 移动参数限制

| 参数 | 含义 | 范围 |
|---|---|---|
| `vx` | 前后速度，正数前进，负数后退 | `-0.5 ~ 0.5` |
| `vy` | 左右速度，正数左移，负数右移 | `-0.4 ~ 0.4` |
| `vrot` | 旋转速度，正数左转，负数右转 | `-0.6 ~ 0.6` |
| `duration` | 动作持续时间，单位秒 | `0.1 ~ 3.0` |

移动动作执行完成后，服务会自动调用 `StopMove()` 停止运动。

## 5. 声音输入接口

服务封装了两个声音输入接口：

```text
POST /audio/tts
POST /audio/pcm
```

### 5.1 `/audio/tts`：文字转语音

用途：笔记本只发送文字，G1 使用内置 TTS 合成并播放。

请求：

```json
{
  "text": "你好，我是宇树 G1",
  "speaker_id": 0
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | 是 | 要播放的文字，最多 500 字符 |
| `speaker_id` | int | 否 | G1 内置 TTS 发音人编号，默认 `0`，服务内限制为 `0~10` |

返回示例：

```json
{"ok": true, "type": "tts", "speaker_id": 0}
```

说明：

- TTS 模式传的是文字，不是音频；
- 音色由 G1 内置 TTS 的 `speaker_id` 决定；
- 当前 SDK 未暴露自定义音色上传、声纹克隆、语速、情绪等参数。

### 5.2 `/audio/pcm`：播放外部 PCM 音频

用途：笔记本或 Mac 已经完成文本和音色合成，上传 PCM 音频数据，让 G1 只负责播放。

请求：

```json
{
  "app_name": "mac_agent",
  "stream_id": "reply_001",
  "pcm_base64": "AAABAP//...",
  "stop_after": false
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pcm_base64` | string | 是 | PCM bytes 的 base64 字符串 |
| `app_name` | string | 否 | 播放应用名，默认 `mac_agent` |
| `stream_id` | string | 否 | 音频流 ID，不传则服务端自动生成 |
| `stop_after` | bool | 否 | 发送该块后是否调用 `PlayStop()`，默认 `false` |

PCM 格式要求：

```text
s16le / 16000Hz / mono
```

也就是：

```text
16kHz
单声道
16-bit signed PCM
little-endian
```

大小限制：

```text
每次请求最多 192000 bytes PCM
```

约等于 6 秒音频：

```text
16000 samples/s * 2 bytes * 6s = 192000 bytes
```

返回示例：

```json
{
  "ok": true,
  "type": "pcm",
  "app_name": "mac_agent",
  "stream_id": "reply_001",
  "bytes": 32000,
  "format": "s16le/16000Hz/mono"
}
```

说明：

- PCM 模式传的是声音本身；
- 音色、语速、情绪已经由笔记本本地 TTS 决定；
- G1 不再做语音合成，只播放音频数据；
- 如果要流式播放，笔记本可以多次调用 `/audio/pcm`，保持相同 `app_name` 和 `stream_id`，按顺序上传 PCM 分块。

### 5.3 `/audio/stop`：停止音频流

请求：

```json
{
  "app_name": "mac_agent"
}
```

返回：

```json
{"ok": true, "type": "audio_stop", "app_name": "mac_agent"}
```

## 6. PC2 上启动服务

### 6.1 将代码传到 PC2

如果 PC2 上还没有当前 SDK：

```bash
scp -r unitree_sdk2_python unitree@192.168.123.164:/home/unitree/
```

如果 PC2 上已经有 SDK，只传服务脚本即可：

```bash
scp example/g1/high_level/robot_control_server.py \
  unitree@192.168.123.164:/home/unitree/unitree_sdk2_python/example/g1/high_level/
```

### 6.2 登录 PC2

```bash
ssh unitree@192.168.123.164
cd ~/unitree_sdk2_python
```

### 6.3 安装 SDK

如果 PC2 上已经可以运行官方 G1 示例，可以跳过这一步。

```bash
pip3 install -e .
```

### 6.4 查看 PC2 的 G1 内部网卡名

```bash
ip a
```

找到带有 `192.168.123.164` 的网卡名，例如：

```text
eth0
```

下面命令中的 `eth0` 要替换成 PC2 上的实际网卡名。

### 6.5 启动服务

不带 token：

```bash
python3 example/g1/high_level/robot_control_server.py eth0 --host 0.0.0.0 --port 8000
```

带 token：

```bash
python3 example/g1/high_level/robot_control_server.py eth0 --host 0.0.0.0 --port 8000 --token g1secret
```

说明：

- `eth0`：PC2 上连接 G1 内部网络的网卡；
- `--host 0.0.0.0`：允许局域网内其他设备访问；
- `--port 8000`：HTTP 服务端口；
- `--token`：可选的简单访问令牌。

## 7. 笔记本访问方式

假设 PC2 地址是：

```text
192.168.123.164
```

服务端口是：

```text
8000
```

### 7.1 健康检查

```bash
curl http://192.168.123.164:8000/health
```

### 7.2 查询支持能力

```bash
curl http://192.168.123.164:8000/actions
```

### 7.3 运动控制示例

招手：

```bash
curl -X POST http://192.168.123.164:8000/action \
  -H "Content-Type: application/json" \
  -d '{"action":"wave"}'
```

前进 1 秒：

```bash
curl -X POST http://192.168.123.164:8000/action \
  -H "Content-Type: application/json" \
  -d '{"action":"forward","duration":1}'
```

停止：

```bash
curl -X POST http://192.168.123.164:8000/action \
  -H "Content-Type: application/json" \
  -d '{"action":"stop"}'
```

### 7.4 TTS 播放示例

```bash
curl -X POST http://192.168.123.164:8000/audio/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"你好，我是宇树 G1","speaker_id":0}'
```

### 7.5 PCM 播放示例

先在笔记本上准备 `reply.pcm`，格式必须是：

```text
s16le / 16000Hz / mono
```

如果有 wav 文件，可以用 ffmpeg 转：

```bash
ffmpeg -i reply.wav -f s16le -ar 16000 -ac 1 reply.pcm
```

发送：

```bash
PCM_BASE64=$(base64 -w 0 reply.pcm)

curl -X POST http://192.168.123.164:8000/audio/pcm \
  -H "Content-Type: application/json" \
  -d "{\"app_name\":\"mac_agent\",\"stream_id\":\"reply_001\",\"pcm_base64\":\"$PCM_BASE64\",\"stop_after\":true}"
```

macOS 的 `base64` 没有 `-w 0`，用：

```bash
PCM_BASE64=$(base64 < reply.pcm | tr -d '\n')
```

### 7.6 停止音频

```bash
curl -X POST http://192.168.123.164:8000/audio/stop \
  -H "Content-Type: application/json" \
  -d '{"app_name":"mac_agent"}'
```

### 7.7 带 token 请求

如果启动服务时使用了：

```bash
--token g1secret
```

请求时需要加：

```bash
-H "X-Robot-Token: g1secret"
```

## 8. Python 请求示例

```python
import base64
import requests

BASE_URL = "http://192.168.123.164:8000"


def send_action(payload):
    return requests.post(f"{BASE_URL}/action", json=payload, timeout=10).json()


def speak_tts(text, speaker_id=0):
    return requests.post(
        f"{BASE_URL}/audio/tts",
        json={"text": text, "speaker_id": speaker_id},
        timeout=10,
    ).json()


def play_pcm_file(path, app_name="mac_agent", stream_id="reply_001", stop_after=True):
    with open(path, "rb") as f:
        pcm_base64 = base64.b64encode(f.read()).decode("ascii")
    return requests.post(
        f"{BASE_URL}/audio/pcm",
        json={
            "app_name": app_name,
            "stream_id": stream_id,
            "pcm_base64": pcm_base64,
            "stop_after": stop_after,
        },
        timeout=20,
    ).json()


send_action({"action": "wave"})
speak_tts("你好，我是宇树 G1", 0)
play_pcm_file("reply.pcm")
```

## 9. 给本地 LLM 的推荐输出格式

运动控制 JSON：

```json
{"action":"stand"}
```

```json
{"action":"forward","duration":1}
```

TTS 输出可以由 Agent 直接调用 `/audio/tts`：

```json
{"text":"好的，我现在向前走一步","speaker_id":0}
```

如果使用本地 TTS 音色模型，则 Agent 先生成 PCM，再调用 `/audio/pcm`。

## 10. 安全注意事项

1. 启动服务前，确保机器人周围没有人和障碍物。
2. 第一次测试建议先调用 `wave`、`stand`、`squat` 等低风险动作。
3. 测试移动类动作时，先使用短时间，例如 `duration=0.5` 或 `duration=1`。
4. 建议启动服务时加 `--token`，避免同一局域网内其他设备误调用。
5. 服务使用互斥锁串行动作，音频接口也使用独立互斥锁串行发送。
6. PCM 模式下，确保音频格式为 `s16le/16000Hz/mono`。
7. 如果动作异常，优先调用 `/action` 的 `stop`，或使用实体急停/遥控器急停。

## 11. 常见问题

### 11.1 笔记本访问不到服务

检查 PC2 服务是否监听 `0.0.0.0`：

```bash
python3 example/g1/high_level/robot_control_server.py eth0 --host 0.0.0.0 --port 8000
```

检查笔记本能否 ping PC2：

```bash
ping 192.168.123.164
```

### 11.2 HTTP 返回 ok，但机器人没动

检查 `eth0` 是否是 PC2 上 `192.168.123.164` 对应网卡；再在 PC2 上运行官方示例确认 SDK 控制链路正常：

```bash
python3 example/g1/high_level/g1_loco_client_example.py eth0
```

### 11.3 TTS 没声音

检查音量、G1 音频服务状态，以及 PC2 上官方音频示例是否正常：

```bash
python3 example/g1/audio/g1_audio_client_example.py eth0
```

### 11.4 PCM 播放异常

优先检查 PCM 格式是否正确：

```text
s16le / 16000Hz / mono
```

使用 ffmpeg 转换：

```bash
ffmpeg -i input.wav -f s16le -ar 16000 -ac 1 reply.pcm
```

### 11.5 提示 unauthorized

说明服务启动时配置了 `--token`，请求时需要加：

```text
X-Robot-Token: 你的token
```
