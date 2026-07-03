# 笔记本 Agent 调用 G1 控制服务说明

本文档面向已经在笔记本或 Mac 上开发好的大模型对话 Agent，说明设备接入局域网后，如何通过 HTTP 调用 G1 PC2 上的机器人控制服务。

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
      v
G1 运动服务 / G1 音频服务
      |
      v
机器人执行动作 / 扬声器播放声音
```

笔记本 Agent 不需要直接调用 Unitree SDK，也不需要直接处理 DDS。

笔记本只需要做三类 HTTP 调用：

1. `/action`：发送机器人运动动作 JSON；
2. `/audio/tts`：发送文字，让 G1 内置 TTS 播放；
3. `/audio/pcm`：发送已经合成好的 PCM 音频，让 G1 扬声器播放。

## 2. 网络前提

假设控制服务运行在 G1 PC2 上：

| 设备 | 地址 | 说明 |
|---|---|---|
| G1 PC2 | `192.168.123.164:8000` | 运行控制服务，笔记本 / Mac 请求这个地址或者做成配置式更灵活 |

笔记本 / Mac 自己的局域网 IP 不固定，也不需要写死。只要它能访问 PC2 即可。

笔记本需要能够访问 PC2：

```bash
ping 192.168.123.164
```

如果 ping 不通，先解决网络连通性问题。

如果 ping 通，再测试 HTTP 服务：

```bash
G1_URL="http://192.168.123.164:8000"   # 设一次,后续 curl 复用
curl "$G1_URL/health"
```

期望返回：

```json
{"ok": true, "service": "g1_robot_control_server"}
```

## 3. PC2 端服务地址

默认控制服务地址：

```text
http://192.168.123.164:8000
```

这个地址建议不要在各处硬编码,而是集中配置(见第 4.3 节),通过环境变量 `G1_CONTROL_URL` 覆盖,换 IP 或端口时只改一处。

核心接口：

```text
POST /action
POST /audio/tts
POST /audio/pcm
POST /audio/stop
GET  /health
GET  /actions
```

`GET /actions` 返回所有支持的 action 列表、`move` 的速度/时长限制、PCM 格式与单次上限。建议 Agent 启动时调用一次,用于本地参数校验:

```bash
curl "$G1_URL/actions"
```

期望返回:

```json
{
  "ok": true,
  "actions": ["damp", "stand", "squat", "lie_to_stand", "low_stand", "high_stand",
              "zero_torque", "wave", "shake_hand", "stop", "move", "forward", "back",
              "left", "right", "turn_left", "turn_right"],
  "audio_endpoints": ["/audio/tts", "/audio/pcm", "/audio/stop"],
  "move_limits": {"vx": [-0.5, 0.5], "vy": [-0.4, 0.4], "vrot": [-0.6, 0.6], "duration": [0.1, 3.0]},
  "pcm_format": "s16le/16000Hz/mono",
  "pcm_max_bytes_per_request": 192000
}
```

如果 PC2 上启动服务时使用了其他端口,需要同步修改 Agent 中的地址。

## 4. 通用请求格式

### 4.1 Header

不带 token：

```text
Content-Type: application/json
```

带 token：

```text
Content-Type: application/json
X-Robot-Token: g1secret
```

> `g1secret` 仅为示例值。实际 token 由服务端启动时通过 `--token` 传入,以部署配置为准。

### 4.2 响应与错误

成功时 HTTP 200,返回 JSON,各接口略有差异:

```json
{"ok": true, "action": "wave"}                          // /action
{"ok": true, "type": "tts", "speaker_id": 0}            // /audio/tts
{"ok": true, "type": "pcm", "app_name": "...", "stream_id": "...", "bytes": 32000, "format": "s16le/16000Hz/mono"}  // /audio/pcm
{"ok": true, "type": "audio_stop", "app_name": "..."}   // /audio/stop
```

失败时返回非 2xx,统一格式:

```json
{"ok": false, "error": "missing action"}
```

| HTTP 状态 | 含义 |
|---|---|
| `200` | 成功 |
| `400` | 请求体非法、参数缺失或越界(如 `unknown action`、`text too long`、`pcm data too large`) |
| `401` | token 校验失败(服务端启用了 token 但请求头未带或不匹配) |
| `404` | 未知路径 |
| `409` | 机器人忙(另有动作正在执行),`/action` 请求被拒绝,见下文 |

> 所有错误都会返回 `{"ok": false, "error": ...}`,Agent 侧可直接读取 `error` 字段。`requests` 的 `raise_for_status()` 在 4xx/5xx 会抛 `HTTPError`,可捕获后解析响应体。

### 4.3 Python 基础配置

把服务地址和 token 集中到一处,优先从环境变量读取,带默认值。后续所有 Python 片段都假设这段配置已存在。

```python
import os

# 优先用环境变量,换 IP/端口只改环境变量即可,无需改代码
BASE_URL = os.environ.get("G1_CONTROL_URL", "http://192.168.123.164:8000")
TOKEN = os.environ.get("G1_CONTROL_TOKEN")  # 未设置则为 None,表示不带 token


def headers():
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["X-Robot-Token"] = TOKEN
    return h
```

设置环境变量(macOS / Linux):

```bash
export G1_CONTROL_URL="http://192.168.123.164:8000"
export G1_CONTROL_TOKEN="g1secret"   # 仅在服务端启用 token 时设置
```

Windows PowerShell:

```powershell
$env:G1_CONTROL_URL = "http://192.168.123.164:8000"
$env:G1_CONTROL_TOKEN = "g1secret"
```

## 5. 运动控制接口 `/action`

### 5.1 请求示例

```json
{"action":"wave"}
```

```json
{"action":"forward","duration":1}
```

```json
{"action":"move","vx":0.2,"vy":0,"vrot":0,"duration":1}
```

### 5.2 支持的 action

```text
damp
stand
squat
lie_to_stand
low_stand
high_stand
zero_torque
wave
shake_hand
stop
move
forward
back
left
right
turn_left
turn_right
```

参数与限制:

| action | 可选字段 | 说明 |
|---|---|---|
| `move` | `vx`, `vy`, `vrot`, `duration` | 速度被 clamp 到 `vx∈[-0.5,0.5]`、`vy∈[-0.4,0.4]`、`vrot∈[-0.6,0.6]`,`duration∈[0.1,3.0]` 秒(缺省 1.0) |
| `forward`/`back`/`left`/`right`/`turn_left`/`turn_right` | `duration` | 固定方向移动,`duration∈[0.1,3.0]` 秒(缺省 1.0) |
| `wave` | `turn` | 布尔值,是否转体挥手,缺省 `false` |
| `shake_hand` | — | 无参数 |
| 其余姿态类 | — | 无参数 |

执行耗时(同步阻塞,请求返回前动作已完成):

- `shake_hand`:约 3 秒(内部握手两次);
- `forward`/`back`/`left`/`right`/`turn_left`/`turn_right`/`move`:等于 `duration`;
- `stand`/`lie_to_stand`:含 0.5 秒缓冲;
- 其余通常在 1 秒内返回。

> 注意:运动动作在服务端串行执行,**一次只跑一个**。前一个动作未返回时,新的 `/action` 请求不会排队,而是立即返回 `409`(见 5.4)。Agent 侧请给足 timeout(移动类至少 `duration + 2` 秒)。

### 5.3 Python 调用

### 5.3 Python 调用

```python
import requests

# BASE_URL / TOKEN 来自第 4.3 节配置


def call_robot(action_json: dict) -> dict:
    response = requests.post(
        f"{BASE_URL}/action",
        json=action_json,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


call_robot({"action": "wave"})
call_robot({"action": "forward", "duration": 1})
call_robot({"action": "stop"})
```

### 5.4 并发与忙时策略(409)

服务端对 `/action` 采用**忙时拒绝**:同一时刻只允许一个运动动作执行。若机器人正在执行动作(包括行走等待期间),新的 `/action` 请求**不会排队**,而是立即返回:

```json
HTTP 409
{"ok": false, "error": "robot busy, another action is in progress"}
```

这样设计的目的是避免调用方无节制灌请求导致命令积压、陈旧动作在几十秒后才执行(对人形机器人很危险)。

**例外:急停级动作 `stop` / `damp` 不受此限制。** 它们不排队、不被 409 拒绝,且会**打断**正在执行的动作:立即下发指令,并唤醒正在等待中的动作(让行走/姿态/手势动作提前结束)。机器人移动期间调用也会立即生效并返回 `200`:

```json
{"ok": true, "action": "stop", "interrupted": true}
{"ok": true, "action": "damp", "interrupted": true}
```

`stop` 与 `damp` 的区别(两者都不排队、不被 409 拒绝、都能打断进行中的动作):

| | `stop` | `damp` |
|---|---|---|
| 底层指令 | `StopMove`(停止移动) | `Damp`(进入阻尼模式) |
| 机器人状态 | 速度归零,**保持当前站立姿态** | 关节松开、失力,**顺势趴下/瘫坐** |
| 之后能否继续动 | **能**。机器人仍站立,可立即接受新的运动动作 | **通常不能直接动**。需重新发 `stand`/`lie_to_stand` 等姿态恢复指令才能继续 |
| 机器人是否会倒 | 否 | 是(失去主动支撑) |
| 典型用途 | 用户说"停下"/"别走了";行程中途取消 | 紧急释放、失稳保护、需人工介入/扶住机器人 |
| 风险等级 | 低(机器人仍稳定) | **高**(机器人会倒下,需确保周围有空间、有人看护) |

**选择指引:**

- **默认急停用 `stop`**。它只是让机器人原地停住,不改变姿态,后续可继续指令。绝大多数"用户想让机器人停下来"的场景都用它。
- **只在机器人需要失力保护时用 `damp`**:即将失稳、需要被人扶走、或测试中紧急释放关节。调用前确认机器人周围有足够空间且不会砸到人/物——`damp` 会让 G1 直接倒下。
- **不要用 `damp` 当常规"停止"用**。LLM 若把 `damp` 当作 `stop` 的同义词频繁调用,会导致机器人反复趴下,既危险又需人工扶起恢复。
- 调用 `damp` 后,若要恢复运动,先发 `stand` 或 `lie_to_stand`(会从趴下姿态起身),不要直接发 `forward` 等移动指令。

> 在 LLM 动作解析 prompt(见第 11 节)中,建议**只暴露 `stop`**,把 `damp` 从允许的 action 列表里去掉,由人工或更高权限的通道触发,避免模型误判让机器人失力倒下。

> 安全建议:Agent 收到用户"停下/急停"意图时,应直接发 `{"action":"stop"}`(常规急停)或 `{"action":"damp"}`(需失力保护时),无需退避、无需重试——它们一定不会被 409 拒绝。

**其余动作收到 409 时,Agent 侧应主动处理**,典型策略:

```python
import requests

# BASE_URL / TOKEN 来自第 4.3 节配置


def call_robot(action_json: dict, retry_once: bool = True) -> dict:
    response = requests.post(
        f"{BASE_URL}/action",
        json=action_json,
        timeout=10,
    )
    if response.status_code == 409:
        # 机器人忙:可选——稍等后重试一次,或直接放弃并提示用户
        if retry_once:
            import time
            time.sleep(0.3)
            return call_robot(action_json, retry_once=False)
        return {"ok": False, "busy": True, "error": response.json().get("error")}
    response.raise_for_status()
    return response.json()
```

建议:

- **不要**在收到 409 后立即疯狂重试,应加退避(如 0.3~0.5 秒)或直接放弃;
- 对"必须执行"的关键意图,可短间隔重试几次;对可丢弃的意图,直接放弃并提示"机器人正忙";
- 急停意图(`stop` / `damp`)永远直接发,不要重试逻辑、不要因 409 放弃。

> 音频接口(`/audio/tts`、`/audio/pcm`、`/audio/stop`)**不**走 409 策略,仍在服务端串行排队执行——分块 PCM 流(7.7)依赖此顺序保证播放连续,不能拒绝。

## 6. TTS 声音接口 `/audio/tts`

### 6.1 什么时候用 TTS

如果你希望最简单地让 G1 说话，用 TTS 接口。

特点：

- Agent 只发送文字；
- G1 内置 TTS 负责语音合成；
- 延迟通常较低；
- 音色只通过 `speaker_id` 做有限选择；
- 不支持自定义音色克隆。

### 6.2 请求格式

```json
{
  "text": "你好，我是宇树 G1",
  "speaker_id": 0
}
```

字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | 是 | 要播放的文字，最多 500 字符 |
| `speaker_id` | int | 否 | G1 内置 TTS 发音人编号，范围 `0~10`，默认 `0` |

### 6.3 curl 示例

```bash
curl -X POST "$G1_URL/audio/tts" \
  -H "Content-Type: application/json" \
  -d '{"text":"你好，我是宇树 G1","speaker_id":0}'
```

### 6.4 Python 调用

```python
import requests

# BASE_URL / TOKEN 来自第 4.3 节配置


def speak_tts(text: str, speaker_id: int = 0) -> dict:
    response = requests.post(
        f"{BASE_URL}/audio/tts",
        json={"text": text, "speaker_id": speaker_id},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


speak_tts("你好，我是宇树 G1", 0)
```

### 6.5 Agent 侧使用建议

当 Agent 生成回复文本后，可以直接调用：

```python
reply_text = "好的，我现在向前走一步"
speak_tts(reply_text, speaker_id=0)
```

## 7. PCM 声音接口 `/audio/pcm`

### 7.1 什么时候用 PCM

如果你需要自定义音色、角色音、克隆音色或更高质量的 TTS，用 PCM 接口。

PCM 模式下：

```text
文本
  ↓
笔记本 / Mac 本地 TTS
  ↓
已经带音色的 PCM 音频
  ↓
POST /audio/pcm
  ↓
G1 扬声器播放
```

G1 不再负责语音合成，只播放声音。

### 7.2 PCM 格式要求

```text
s16le / 16000Hz / mono
```

含义：

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

约等于 6 秒音频。

### 7.3 请求格式

```json
{
  "app_name": "mac_agent",
  "stream_id": "reply_001",
  "pcm_base64": "AAABAP//...",
  "stop_after": false
}
```

字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pcm_base64` | string | 是 | PCM bytes 的 base64 字符串 |
| `app_name` | string | 否 | 播放应用名，默认 `mac_agent` |
| `stream_id` | string | 否 | 音频流 ID |
| `stop_after` | bool | 否 | 该块发送后是否停止音频流，默认 `false` |

### 7.4 将 WAV 转 PCM

macOS / Linux 可使用 ffmpeg：

```bash
ffmpeg -i reply.wav -f s16le -ar 16000 -ac 1 reply.pcm
```

如果你的本地 TTS 可以直接输出 `s16le/16000Hz/mono`，则不需要转换。

### 7.5 curl 示例（macOS / Linux）

macOS 的 `base64` 没有 `-w 0`，使用：

```bash
PCM_BASE64=$(base64 < reply.pcm | tr -d '\n')

curl -X POST "$G1_URL/audio/pcm" \
  -H "Content-Type: application/json" \
  -d "{\"app_name\":\"mac_agent\",\"stream_id\":\"reply_001\",\"pcm_base64\":\"$PCM_BASE64\",\"stop_after\":true}"
```

Linux 可使用：

```bash
PCM_BASE64=$(base64 -w 0 reply.pcm)
```

### 7.6 Python 调用

```python
import base64
import requests

# BASE_URL / TOKEN 来自第 4.3 节配置


def play_pcm_bytes(
    pcm_data: bytes,
    app_name: str = "mac_agent",
    stream_id: str = "reply_001",
    stop_after: bool = False,
) -> dict:
    pcm_base64 = base64.b64encode(pcm_data).decode("ascii")
    response = requests.post(
        f"{BASE_URL}/audio/pcm",
        json={
            "app_name": app_name,
            "stream_id": stream_id,
            "pcm_base64": pcm_base64,
            "stop_after": stop_after,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def play_pcm_file(path: str, stop_after: bool = True) -> dict:
    with open(path, "rb") as f:
        return play_pcm_bytes(f.read(), stop_after=stop_after)


play_pcm_file("reply.pcm")
```

### 7.7 分块/准流式播放

如果本地 TTS 可以边生成边输出 PCM，或者你想降低首句延迟，可以分块调用 `/audio/pcm`。

建议每块 0.5~1 秒：

```text
0.5 秒 PCM = 16000 * 2 * 0.5 = 16000 bytes
1 秒 PCM = 16000 * 2 * 1 = 32000 bytes
```

Python 示例：

```python
import base64
import time
import requests

# BASE_URL / TOKEN 来自第 4.3 节配置


def stream_pcm_file(path: str, app_name="mac_agent", stream_id="reply_stream_001", chunk_bytes=32000):
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_bytes)
            if not chunk:
                break
            pcm_base64 = base64.b64encode(chunk).decode("ascii")
            requests.post(
                f"{BASE_URL}/audio/pcm",
                json={
                    "app_name": app_name,
                    "stream_id": stream_id,
                    "pcm_base64": pcm_base64,
                    "stop_after": False,
                },
                timeout=10,
            ).raise_for_status()
            time.sleep(0.5)

    requests.post(
        f"{BASE_URL}/audio/stop",
        json={"app_name": app_name},
        timeout=10,
    ).raise_for_status()
```

说明：

- 多个分块需要使用相同的 `app_name` 和 `stream_id`；
- 每个请求发送一段 PCM；
- 最后调用 `/audio/stop` 结束播放流；
- 这属于 HTTP 分块式方案，不是真正 WebSocket 音频流，但足够做低延迟分句播放验证；
- 示例中的 `time.sleep(0.5)` 仅用于演示节奏。实际应用时应按本地 TTS 的真实产出节奏发送(每块 PCM 生成完即发),而不是固定 sleep——固定 sleep 在每块为 1 秒音频(32000 bytes)时会引入播放间隙。

## 8. 停止音频接口 `/audio/stop`

```bash
curl -X POST "$G1_URL/audio/stop" \
  -H "Content-Type: application/json" \
  -d '{"app_name":"mac_agent"}'
```

Python：

```python
import requests

# BASE_URL / TOKEN 来自第 4.3 节配置


def stop_audio(app_name="mac_agent"):
    response = requests.post(
        f"{BASE_URL}/audio/stop",
        json={"app_name": app_name},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
```

## 9. Agent 侧推荐组织方式

建议你的 Agent 把输出分成两类：

### 9.1 动作意图

```python
intent = {"action": "forward", "duration": 1}
call_robot(intent)
```

### 9.2 语音回复

如果使用 G1 内置 TTS：

```python
reply_text = "好的，我现在向前走一步"
speak_tts(reply_text)
```

如果使用 Mac 本地音色：

```python
reply_text = "好的，我现在向前走一步"
pcm_data = local_tts_to_pcm(reply_text)  # 需要输出 s16le/16000Hz/mono
play_pcm_bytes(pcm_data, stop_after=True)
```

## 10. TTS 和 PCM 的取舍

| 方案 | Agent 传什么 | 音色控制 | 延迟 | 实现复杂度 |
|---|---|---|---|---|
| `/audio/tts` | 文字 | 低，只能 `speaker_id` | 低 | 低 |
| `/audio/pcm` 完整音频 | PCM 音频 | 高，由 Mac 本地 TTS 决定 | 中到高 | 中 |
| `/audio/pcm` 分块音频 | PCM 小块 | 高，由 Mac 本地 TTS 决定 | 中到低 | 中 |

建议：

1. 先用 `/audio/tts` 跑通说话链路；
2. 再用 `/audio/pcm` 接入你的自定义音色；
3. 最后再做分句或分块上传降低延迟。

## 11. 推荐的 LLM 输出约束

运动控制 prompt 示例：

```text
你是宇树 G1 机器人动作解析器。
你的任务是把用户自然语言转换成机器人动作 JSON。
你只能输出 JSON。
允许的 action：stand, squat, wave, shake_hand, stop, forward, back, left, right, turn_left, turn_right, move。
移动类动作可包含 duration，单位秒，范围 0.1~3，默认 1 秒。
不确定时输出 {"action":"stop"}。
```

> 出于安全考虑,上面的 prompt 只暴露安全动作子集,刻意省略了 `damp`、`lie_to_stand`、`low_stand`、`high_stand`、`zero_torque` 等姿态/零力矩动作,避免 LLM 误触发导致机器人意外趴下或失力。完整 17 个 action 见第 5.2 节。

语音回复不建议让 LLM 直接输出 `pcm_base64`。

正确流程是：

```text
LLM 输出自然语言回复
  ↓
TTS 模块把回复文本转成 PCM
  ↓
Agent 调用 /audio/pcm
```

## 12. 安全建议

1. 移动动作和语音播放分开处理，先执行动作还是先说话由 Agent 决定。
2. 对移动动作做白名单过滤和时长限制。
3. PCM 不要一次发送太大，超过 6 秒请分块。
4. 网络不稳定时优先使用 `/audio/tts`，因为传输数据量更小。
5. 如果启用了 token，所有接口都需要带 `X-Robot-Token`。
6. `/action` 忙时返回 409,Agent 必须处理(退避重试或放弃),不要无脑重试灌请求。

## 13. 最小集成结论

> 以下片段假设已按第 4.3 节配置好 `BASE_URL`(环境变量 `G1_CONTROL_URL`)。直接复制使用时,若未设环境变量,会把默认地址 `http://192.168.123.164:8000` 作为兜底。

让 G1 做内置 TTS：

```python
import os
import requests

BASE_URL = os.environ.get("G1_CONTROL_URL", "http://192.168.123.164:8000")

requests.post(
    f"{BASE_URL}/audio/tts",
    json={"text": "你好，我是 G1", "speaker_id": 0},
    timeout=10,
)
```

让 G1 播放 Mac 已合成的 PCM：

```python
import base64
import os
import requests

BASE_URL = os.environ.get("G1_CONTROL_URL", "http://192.168.123.164:8000")

with open("reply.pcm", "rb") as f:
    pcm_base64 = base64.b64encode(f.read()).decode("ascii")

requests.post(
    f"{BASE_URL}/audio/pcm",
    json={
        "app_name": "mac_agent",
        "stream_id": "reply_001",
        "pcm_base64": pcm_base64,
        "stop_after": True,
    },
    timeout=20,
)
```

## 14. 本地测试脚本

仓库提供了一个测试客户端 `deploy/test_robot_control_client.py`,直接连真机 PC2,逐项触发各接口并校验行为(含 409 忙时拒绝、急停打断验证)。

它按风险分层,**默认只跑不动机器人的只读测试**（在仓库根目录执行）:

```bash
# 只读:/health、/actions、非法请求校验(不发声、不动身体)
python deploy/test_robot_control_client.py --url http://192.168.123.164:8000

# 加跑音频测试(会发声)
python deploy/test_robot_control_client.py --audio

# 加跑运动测试(会让机器人移动,运行前要求确认安全)
python deploy/test_robot_control_client.py --motion

# 全部测试,并跳过运动确认(确保机器人周围已空旷)
python deploy/test_robot_control_client.py --all --yes

# 服务端启用了 token 时
python deploy/test_robot_control_client.py --all --token g1secret
```

运动测试会让机器人真实移动,脚本运行前会要求确认"机器人周围空旷、有人看护、急停就绪",每项测试后自动发 `stop` 收尾。急停打断测试会先让机器人移动几秒、再发 `stop`,通过测量被打断动作的返回耗时来验证打断确实生效。
