# G1 HTTP 控制集成完成说明（V2 实测修订版）

> **致**：对方工程师（语树）  
> **来自**：伴读书童AI 开发端  
> **日期**：2026年6月29日  
> **主题**：笔记本/Mac Agent 通过 HTTP 调用 G1 控制服务的集成已按 V2 实测版修订

---

## 一、已完成的工作

我们已根据工程师发来的 `G1_CONTROL_CLIENT_V2.md`（实测修订版），将 G1 HTTP 控制能力接入伴读书童AI 本地系统，并更新了端口、动作集合与手臂动作接口。

### 1. 文档归档

- **当前生效文档：`项目文档/机器人/G1_CONTROL_CLIENT.md`（V2 实测修订版）**
- 历史副本：`项目文档/机器人/G1_CONTROL_CLIENT_V2.md`

### 2. Python HTTP 客户端

- 文件：`书童程序/核心/机器人对接/G1_HTTP客户端.py`
- 封装接口：
  - `POST /action` — 机器人运动动作（sport 服务）
  - `POST /arm_action` — **V2 新增** 手臂动作（arm 服务）
  - `POST /audio/tts` — G1 内置 TTS 播放
  - `POST /audio/pcm` — 播放已合成 PCM 音频
  - `POST /audio/stop` — 停止音频
  - `GET /health` — 服务健康检查
  - `GET /actions` — 获取能力列表与参数限制
- V2 变化：
  - 默认地址改为 `http://192.168.0.248:8888`（PC2 WiFi，推荐）
  - 移除不生效动作：`wave`、`shake_hand`、`low_stand`、`high_stand`、`zero_torque`
  - 新增手臂动作：`face_wave`、`high_wave`、`shake_hand_arm`、`clap`、`high_five`、`hug`、`heart`、`hands_up`、`two_hand_kiss`、`release_arm`
  - `execute_action_safe` 自动根据书童动作名路由到 `/action` 或 `/arm_action`

### 3. 音频格式转换

- 文件：`书童程序/核心/机器人对接/音频格式转换.py`
- 功能：
  - 将 MP3/WAV 转换为 G1 要求的 `s16le / 16000Hz / mono` PCM
  - 支持 PCM 分块，便于流式上传
  - 依赖系统 `ffmpeg`

### 4. 自然语言动作解析

- 文件：`书童程序/数据/提示词/G1动作解析提示词.md`
- V2 变化：
  - LLM 输出 JSON 新增 `endpoint` 字段（`action` 或 `arm_action`）
  - 手臂动作纳入安全白名单
  - `wave` 映射为 `{"endpoint":"arm_action","action":"face_wave"}`

### 5. 情感动作库兼容

- 文件：`书童程序/核心/机器人对接/情感动作库.py`
- 已适配 V2：
  - `wave` → `/arm_action` 的 `face_wave`
  - `dance` → `/arm_action` 的 `face_wave`
  - 其他运动动作仍走 `/action`

### 6. 后端接入

- 文件：`本地书童界面.py`
- 接入点：
  - 启动时若 `g1_http_enabled=true`，自动初始化 `G1HTTPClient`
  - `/api/robot/action` 支持通过 HTTP 控制 G1，请求体可带 `endpoint` 字段
  - `/api/robot/scene` 支持通过 HTTP 执行情感场景
  - `/api/status` 返回 `robot_status` 字段
- 师父 PC 端页面（`师父PC端.html`）已新增手臂动作按钮：挥手、握手、鼓掌、比心、击掌、手臂归位。

### 7. 配置项

- 文件：`书童程序/配置.py`、`config.json.template`
- 更新配置：
  ```json
  {
    "g1_http_enabled": false,
    "g1_http_control_url": "http://192.168.0.248:8888",
    "g1_http_control_token": "",
    "g1_http_app_name": "bookboy_agent",
    "g1_http_tts_speaker_id": 0,
    "g1_http_use_pcm": false
  }
  ```

---

## 二、如何启用

1. 确保 G1 PC2 上的 `robot_control_server.py` 已按 V2 启动（端口 `8888`）：
   ```bash
   cd ~/Desktop/unitree_sdk2_python
   PYTHONUNBUFFERED=1 nohup python3 example/g1/high_level/robot_control_server.py eth0 \
     --host 0.0.0.0 --port 8888 > ~/robot_server.log 2>&1 &
   ```
2. 在 `config.json` 中设置：
   ```json
   {
     "g1_http_enabled": true,
     "g1_http_control_url": "http://192.168.0.248:8888",
     "g1_http_control_token": "服务端设置的 token（如有）"
   }
   ```
3. 启动伴读书童服务：
   ```bash
   .venv/bin/python3 本地书童界面.py
   ```
4. 检查状态：
   ```bash
   curl "http://127.0.0.1:3876/api/status?family_id=default_family"
   ```
   返回中应包含 `robot_status`，`mode` 为 `g1_http`。

---

## 三、调用示例

### 3.1 执行运动动作

```bash
curl -X POST "http://127.0.0.1:3876/api/robot/action" \
  -H "Content-Type: application/json" \
  -d '{"action":"forward","duration":1}'
```

### 3.2 执行手臂动作

```bash
curl -X POST "http://127.0.0.1:3876/api/robot/action" \
  -H "Content-Type: application/json" \
  -d '{"endpoint":"arm_action","action":"face_wave"}'
```

### 3.3 执行情感场景

```bash
curl -X POST "http://127.0.0.1:3876/api/robot/scene" \
  -H "Content-Type: application/json" \
  -d '{"scene":"greet","child_name":"嘟嘟"}'
```

支持的 `scene`：`greet`、`comfort`、`encourage`、`play`、`bedtime`、`greet_master`。

### 3.4 播放 MP3 语音（通过 G1 扬声器）

在 Python 中：

```python
from 书童程序.核心.机器人对接.G1_HTTP客户端 import G1HTTPClient

client = G1HTTPClient()
client.play_mp3_file("reply.mp3", chunk_seconds=1.0)
```

---

## 四、环境要求

- Python 3.9+
- `requests` 库（已安装在虚拟环境）
- `ffmpeg`（用于 MP3 转 PCM，如仅使用 `/audio/tts` 则不需要）
- 网络可达 G1 PC2 控制服务（默认 `http://192.168.0.248:8888`）

---

## 五、安全说明

- 默认关闭 G1 HTTP 控制，不会自动连接真实机器人。
- 动作接口有安全白名单，危险动作不通过 LLM 暴露。
- V2 已移除 `low_stand`、`high_stand`、`zero_torque` 等不生效或危险动作。
- `damp` 等失力动作仅在明确需要时使用，常规急停使用 `stop`。
- 建议生产环境启用 `X-Robot-Token` 鉴权。

---

## 六、V2 核心变更清单

| 变化 | 说明 |
|------|------|
| 端口 8000 → 8888 | 8000 被视频录制服务占用 |
| 新增 `/arm_action` | G1ArmActionClient（arm 服务），10 个手臂动作实测可用 |
| 移除 `wave`、`shake_hand` | sport 服务 SetTaskId 不工作 |
| 移除 `low_stand`、`high_stand` | sport 服务 SetStandHeight 不工作 |
| 移除 `zero_torque` | 不生效且危险 |
| LLM 输出加 `endpoint` | 用于区分 `/action` 与 `/arm_action` |

---

**结论**：G1 HTTP 控制服务已按 V2 实测修订版接入伴读书童AI 后端，运动控制、手臂动作、TTS、PCM 播放、情感场景均已可用。对方工程师按上述配置启用后即可测试。
