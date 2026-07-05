# G1 服务测试命令速查

> 前提：已完成环境配置（Python + requests + SSH 免密），见 [REMOTE_SERVICE_GUIDE.md](REMOTE_SERVICE_GUIDE.md)。
> 服务地址：`http://192.168.0.248:8888`（PC2 IP + 端口）。

---

## ⚠️ 先看你用的是哪个终端，别复制错版本！

| 你的终端 | 看提示符 | 复制哪一版 |
|---------|---------|-----------|
| **PowerShell** | `PS C:\...>` | ✅ **PowerShell 版**（Windows 默认主推） |
| **cmd.exe** | `C:\...>`（无 `PS`） | ✅ **cmd.exe 版**，或先敲 `powershell` 进 PS 用 PowerShell 版 |
| **Git Bash** | `MINGW ...$` | ✅ **curl 版** |
| **Linux / Mac 终端** | `user@host:~$` | ✅ **curl 版** |

**为什么不能混用**：
- PowerShell 的 `curl` 是 `Invoke-WebRequest` 的别名，不认 `-H`/`-d` → 报"无法绑定参数 Headers"
- cmd.exe 不认单引号，`-d '{"action":...}'` 会让 body 变空 → 报 `Expecting value: line 1 column 1`
- 只有 Git Bash / Linux / Mac 里 `curl` 是真 curl 且单引号合法

> **Windows 用户最省心**：用 PowerShell，复制 PowerShell 版即可。在 PowerShell 想用真 curl 写 `curl.exe`（注意双引号内 `\"` 转义）。

---

## 0. 常量

| 项 | 值 |
|----|----|
| PC2 地址 | `192.168.0.248` |
| SSH 用户 | `unitree` |
| 服务端口 | `8888` |
| 服务基址 | `http://192.168.0.248:8888` |

> **服务启停 / 状态查看 / 日志查看 / SSH 免密配置** 见 [REMOTE_SERVICE_GUIDE.md](REMOTE_SERVICE_GUIDE.md)。本文档只管**测试各个 HTTP 接口**。

---

## 1. 健康检查 & 可用动作

**PowerShell**：

```powershell
Invoke-RestMethod -Uri http://192.168.0.248:8888/health
Invoke-RestMethod -Uri http://192.168.0.248:8888/actions
```

**cmd.exe**（真 curl.exe，无 body，无引号坑）：

```cmd
curl http://192.168.0.248:8888/health
curl http://192.168.0.248:8888/actions
```

**curl 版终端**：

```bash
curl http://192.168.0.248:8888/health
curl http://192.168.0.248:8888/actions
```

期望：`{"ok": true, "service": "g1_robot_control_server"}`

---

## 2. 整机动作（POST /action）

可用动作：`stand` `squat` `lie_to_stand` `damp` `stop` `forward` `back` `left` `right` `turn_left` `turn_right` `move`
- `move` 可带 `vx` `vy` `vrot` `duration`（范围见 /actions 的 move_limits）
- 其余移动动作可带 `duration`（0.1~3.0 秒，默认 1.0）
- `stop` / `damp` 可打断正在执行的动作

### PowerShell

先定义快捷函数（同一窗口定义一次，反复用）：

```powershell
$post = { param($body) Invoke-RestMethod -Uri http://192.168.0.248:8888/action -Method Post -ContentType "application/json" -Body $body }
```

然后：

```powershell
& $post '{"action":"stand"}'          # 起立
& $post '{"action":"squat"}'          # 蹲下
& $post '{"action":"lie_to_stand"}'   # 躺→站
& $post '{"action":"damp"}'           # 阻尼松弛
& $post '{"action":"stop"}'           # 急停（打断当前动作）
& $post '{"action":"forward","duration":1.0}'    # 前进 1 秒
& $post '{"action":"back","duration":1.0}'       # 后退 1 秒
& $post '{"action":"left","duration":1.0}'       # 左移 1 秒
& $post '{"action":"right","duration":1.0}'      # 右移 1 秒
& $post '{"action":"turn_left","duration":1.0}'  # 原地左转 1 秒
& $post '{"action":"turn_right","duration":1.0}' # 原地右转 1 秒
& $post '{"action":"move","vx":0.3,"vy":0.0,"vrot":0.0,"duration":1.5}'  # 自定义速度（前进 0.3，1.5 秒）
```

### cmd.exe（真 curl.exe，双引号内 `\"` 转义）

```cmd
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"stand\"}"            REM 起立
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"squat\"}"            REM 蹲下
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"lie_to_stand\"}"     REM 躺→站
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"damp\"}"             REM 阻尼松弛
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"stop\"}"             REM 急停（打断当前动作）
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"forward\",\"duration\":1.0}"    REM 前进 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"back\",\"duration\":1.0}"       REM 后退 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"left\",\"duration\":1.0}"       REM 左移 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"right\",\"duration\":1.0}"      REM 右移 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"turn_left\",\"duration\":1.0}"  REM 原地左转 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"turn_right\",\"duration\":1.0}" REM 原地右转 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d "{\"action\":\"move\",\"vx\":0.3,\"vy\":0.0,\"vrot\":0.0,\"duration\":1.5}"  REM 自定义速度（前进 0.3，1.5 秒）
```

### curl 版终端（Git Bash / Linux / Mac）

```bash
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"stand"}'          # 起立
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"squat"}'          # 蹲下
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"lie_to_stand"}'   # 躺→站
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"damp"}'           # 阻尼松弛
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"stop"}'           # 急停（打断当前动作）
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"forward","duration":1.0}'    # 前进 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"back","duration":1.0}'       # 后退 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"left","duration":1.0}'       # 左移 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"right","duration":1.0}'      # 右移 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"turn_left","duration":1.0}'  # 原地左转 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"turn_right","duration":1.0}' # 原地右转 1 秒
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -d '{"action":"move","vx":0.3,"vy":0.0,"vrot":0.0,"duration":1.5}'  # 自定义速度（前进 0.3，1.5 秒）
```

---

## 3. 手臂动作（POST /arm_action）

可用动作对照：

| action | 效果 |
|--------|------|
| `clap` | 拍手鼓掌 |
| `high_five` | 击掌 |
| `hug` | 拥抱（G1 预设全身动作，可能带向前迈步） |
| `heart` | 双手比心 |
| `face_wave` | 脸前挥手（小幅） |
| `high_wave` | 高举挥手（大幅） |
| `shake_hand_arm` | 伸手握手 |
| `hands_up` | 双手举起 |
| `release_arm` | 手臂归位（回到默认姿态，动作后建议发一次） |
| `two_hand_kiss` | 双手飞吻 |

### PowerShell

```powershell
$arm = { param($body) Invoke-RestMethod -Uri http://192.168.0.248:8888/arm_action -Method Post -ContentType "application/json" -Body $body }

& $arm '{"action":"clap"}'              # 拍手鼓掌
& $arm '{"action":"high_five"}'         # 击掌
& $arm '{"action":"hug"}'               # 拥抱（可能带迈步）
& $arm '{"action":"heart"}'             # 双手比心
& $arm '{"action":"face_wave"}'         # 脸前挥手
& $arm '{"action":"high_wave"}'         # 高举挥手
& $arm '{"action":"shake_hand_arm"}'    # 伸手握手
& $arm '{"action":"hands_up"}'          # 双手举起
& $arm '{"action":"release_arm"}'       # 手臂归位
& $arm '{"action":"two_hand_kiss"}'     # 双手飞吻
```

### cmd.exe

```cmd
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d "{\"action\":\"clap\"}"            REM 拍手鼓掌
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d "{\"action\":\"high_five\"}"      REM 击掌
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d "{\"action\":\"hug\"}"            REM 拥抱（可能带迈步）
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d "{\"action\":\"heart\"}"          REM 双手比心
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d "{\"action\":\"face_wave\"}"      REM 脸前挥手
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d "{\"action\":\"high_wave\"}"      REM 高举挥手
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d "{\"action\":\"shake_hand_arm\"}" REM 伸手握手
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d "{\"action\":\"hands_up\"}"       REM 双手举起
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d "{\"action\":\"release_arm\"}"    REM 手臂归位
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d "{\"action\":\"two_hand_kiss\"}"  REM 双手飞吻
```

### curl 版终端（Git Bash / Linux / Mac）

```bash
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d '{"action":"clap"}'              # 拍手鼓掌
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d '{"action":"high_five"}'         # 击掌
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d '{"action":"hug"}'               # 拥抱（可能带迈步）
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d '{"action":"heart"}'             # 双手比心
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d '{"action":"face_wave"}'         # 脸前挥手
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d '{"action":"high_wave"}'         # 高举挥手
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d '{"action":"shake_hand_arm"}'    # 伸手握手
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d '{"action":"hands_up"}'          # 双手举起
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d '{"action":"release_arm"}'       # 手臂归位
curl -X POST http://192.168.0.248:8888/arm_action -H "Content-Type: application/json" -d '{"action":"two_hand_kiss"}'     # 双手飞吻
```

---

## 4. 语音 / 音频（POST /audio/*）

### 4.1 TTS 文字转语音（POST /audio/tts）

- `text`：必填，≤500 字
- `speaker_id`：可选，0~10，默认 0

**PowerShell**：

```powershell
Invoke-RestMethod -Uri http://192.168.0.248:8888/audio/tts -Method Post -ContentType "application/json" -Body '{"text":"你好，我是G1","speaker_id":0}'
```

**cmd.exe**：

```cmd
curl -X POST http://192.168.0.248:8888/audio/tts -H "Content-Type: application/json" -d "{\"text\":\"你好，我是G1\",\"speaker_id\":0}"
```

**curl 版终端**：

```bash
curl -X POST http://192.168.0.248:8888/audio/tts -H "Content-Type: application/json" -d '{"text":"你好，我是G1","speaker_id":0}'
```

### 4.2 停止音频（POST /audio/stop）

**PowerShell**：

```powershell
Invoke-RestMethod -Uri http://192.168.0.248:8888/audio/stop -Method Post -ContentType "application/json" -Body '{"app_name":"mac_agent"}'
```

**cmd.exe**：

```cmd
curl -X POST http://192.168.0.248:8888/audio/stop -H "Content-Type: application/json" -d "{\"app_name\":\"mac_agent\"}"
```

**curl 版终端**：

```bash
curl -X POST http://192.168.0.248:8888/audio/stop -H "Content-Type: application/json" -d '{"app_name":"mac_agent"}'
```

### 4.3 播放 PCM 裸音频（POST /audio/pcm）

- `pcm_base64`：必填，PCM 的 base64（格式 s16le / 16000Hz / mono，单次 ≤192000 字节）
- `app_name`：可选，默认 `mac_agent`
- `stream_id`：可选，不填用时间戳
- `stop_after`：可选，播完立即停

**PowerShell**（生成 1 秒静音 PCM 再发）：

```powershell
$pcm = [Convert]::ToBase64String(([byte[]]@(0)*32000))
$body = @{ pcm_base64 = $pcm; app_name = "mac_agent"; stop_after = $true } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri http://192.168.0.248:8888/audio/pcm -Method Post -ContentType "application/json" -Body $body
```

**cmd.exe**（用 Python 生成 PCM，双引号转义）：

```cmd
FOR /F %i IN ('python3 -c "import base64;print(base64.b64encode(b'\x00\x00'*16000).decode())"') DO SET PCM=%i
curl -X POST http://192.168.0.248:8888/audio/pcm -H "Content-Type: application/json" -d "{\"pcm_base64\":\"%PCM%\",\"app_name\":\"mac_agent\",\"stop_after\":true}"
```

**curl 版终端**：

```bash
PCM=$(python3 -c "import base64;print(base64.b64encode(b'\x00\x00'*16000).decode())")
curl -X POST http://192.168.0.248:8888/audio/pcm -H "Content-Type: application/json" \
  -d "{\"pcm_base64\":\"$PCM\",\"app_name\":\"mac_agent\",\"stop_after\":true}"
```

---

## 5. 带 Token 的请求（启动时用了 --token）

若用 `python3 deploy/start_robot_server.py --token g1secret` 启动，所有 POST 需带请求头 `X-Robot-Token: g1secret`，否则返回 401。

**PowerShell**：

```powershell
Invoke-RestMethod -Uri http://192.168.0.248:8888/action -Method Post -ContentType "application/json" `
  -Headers @{ "X-Robot-Token" = "g1secret" } -Body '{"action":"stand"}'
```

**cmd.exe**：

```cmd
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -H "X-Robot-Token: g1secret" -d "{\"action\":\"stand\"}"
```

**curl 版终端**：

```bash
curl -X POST http://192.168.0.248:8888/action -H "Content-Type: application/json" -H "X-Robot-Token: g1secret" -d '{"action":"stand"}'
```

---

## 6. 常见返回码

| HTTP | 含义 | 触发场景 |
|------|------|----------|
| 200 | 成功 | 正常执行 |
| 400 | 参数错误 | 缺 action / 未知动作 / JSON 非法 |
| 401 | 未授权 | 启用了 token 但请求头没带或不对 |
| 404 | 路径不存在 | URL 写错 |
| 409 | 机器人忙 | 上一个动作还没结束又下发新动作（用 `stop` 打断） |

> 看到 `{"ok": false, "error": "Expecting value: line 1 column 1 (char 0)"}` 说明 body 为空 → 多半是 **cmd.exe 里用了单引号 `-d '{...}'`**，cmd 不认单引号。改用双引号 `\"` 转义，或进 PowerShell 用 `Invoke-RestMethod`。

---

## 7. 安全提醒

- **开机第一个动作建议先 `stand`**，确认机器人站稳、周围有空间再下发移动类动作。
- 移动类动作会真实行走，**务必保证周围无障碍、无人、有足够空间**。
- 出现异常立刻发 `{"action":"stop"}` 急停，必要时发 `{"action":"damp"}` 进入阻尼松弛。
