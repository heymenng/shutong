# G1 远程服务启停指南

> 本文管**服务的启动 / 停止 / 状态查看 / 环境配置**。测各个 HTTP 接口的命令见 [SERVICE_TEST_COMMANDS.md](SERVICE_TEST_COMMANDS.md)。

## 前提

- PC2 已开机，与笔记本在同一个网络
- PC2 地址：`192.168.0.248`（WiFi）/ `192.168.123.164`（G1 内网）
- 笔记本能 ping 通 PC2

## 命令在哪运行

文档里的命令分两种执行位置，看命令开头就能区分：

| 命令样式 | 在哪执行 | 例子 |
|---------|---------|------|
| `python3 deploy/...` | **笔记本本地**（任意终端） | [unitree-demo](../../../../../Volumes/Ventoy/unitree-demo) |
| `ssh unitree@... '远程命令'` | 远程命令在 **PC2（Linux）** 上执行 | `ssh unitree@192.168.0.248 'tail -20 ~/robot_server.log'` |
| `curl http://192.168.0.248:8888/...` | **笔记本本地**，访问 PC2 的 HTTP 服务 | `curl http://192.168.0.248:8888/health` |
| `ssh-keygen` / `ssh-copy-id` | **笔记本本地** | 配免密用 |

> **SSH 命令的引号约定**：远程命令一律用**单引号**包住（`ssh host '...'`），PowerShell / Git Bash / Linux / Mac 通用——单引号内的 `$()`、`grep`、`awk`、`2>/dev/null` 都原样传给 PC2 执行，不在笔记本本地解析。cmd.exe 不认单引号，cmd 用户请先敲 `powershell` 进 PowerShell 再执行。

---

# 正常操作流程

## 1. 环境检测（首次使用时跑一次）

在笔记本终端（仓库根目录）执行：

```bash
python3 deploy/check_env.py            # 检测 + 交互式自动修复（缺失项会提示是否修复）
python3 deploy/check_env.py --check    # 只检测，不做任何修改
python3 deploy/check_env.py --yes      # 检测 + 全部自动修复，不再逐项确认
```

脚本逐项检查：Python 版本（≥ 3.8）、requests 包、SSH 客户端、SSH 免密登录。
缺失 `requests` 会自动 `pip install`；免密登录未配会自动生成密钥并推送到 PC2（`ssh-copy-id`，Windows 上回退到手动追加公钥）。

四项全过即可进入下一步。检测不过的修复方法见文末「[异常处理](#异常处理)」。

> 不想用脚本可手动检测：`python3 --version` / `python3 -c "import requests"` / `ssh -V` / `ssh -o PasswordAuthentication=no unitree@192.168.0.248 echo ok`（弹密码则需配置免密）。

---

## 2. 启动服务

### 方式一：脚本（推荐）

在仓库根目录执行：

```bash
python3 deploy/start_robot_server.py
```

代码有更新时加 `--sync`：

```bash
python3 deploy/start_robot_server.py --sync
```

服务启动并验证通过后，脚本会**自动在笔记本后台拉起日志流**，实时把 PC2 服务日志写到本地 `robot_server.log`（无需 SSH、无需 G1 外接屏幕）。相关选项：

```bash
python3 deploy/start_robot_server.py --sync --log-file logs/g1.log   # 指定本地日志路径
python3 deploy/start_robot_server.py --log-level DEBUG               # 同时调高服务端日志级别
python3 deploy/start_robot_server.py --no-log-stream                 # 不自动启动日志流
```

日志流进程独立运行，`start_robot_server.py` 退出后仍在后台继续接收。每次重新启动会自动清理上次的旧日志流进程（靠 `robot_server.log.pid`），不会堆积。手动停止日志流：

```bash
# Linux/Mac
kill $(cat robot_server.log.pid)
# Windows PowerShell
taskkill /PID (Get-Content robot_server.log.pid) /F
```

实时查看本地落盘的日志：

```bash
tail -f robot_server.log              # Linux/Mac
Get-Content robot_server.log -Wait    # Windows PowerShell
```

### 方式二：手动 SSH

```bash
ssh unitree@192.168.0.248 'tmux kill-session -t robot 2>/dev/null; tmux new-session -d -s robot "cd /home/unitree/Desktop/unitree_sdk2_python && PYTHONUNBUFFERED=1 python3 example/g1/high_level/robot_control_server.py eth0 --host 0.0.0.0 --port 8888 > ~/robot_server.log 2>&1"'
```

> 外层单引号让笔记本本地 shell（PowerShell/bash）原样传给 PC2；内层双引号是 PC2 上 tmux 需要的。

### 验证启动

```bash
curl http://192.168.0.248:8888/health
# 期望: {"ok": true, "service": "g1_robot_control_server"}
```

---

## 3. 查看状态 / 日志

### 通过 SSH 查看日志

```bash
# 进程是否在跑
ssh unitree@192.168.0.248 'ps aux | grep robot_control | grep -v grep || echo "服务未运行"'

# 查看最近 20 行日志
ssh unitree@192.168.0.248 'tail -20 ~/robot_server.log'

# 实时日志（Ctrl+C 退出）
ssh unitree@192.168.0.248 'tail -f ~/robot_server.log'

# 只看错误/告警
ssh unitree@192.168.0.248 'grep -E "WARNING|ERROR" ~/robot_server.log | tail -30'

# tmux 会话（可 attach 进去看）
ssh unitree@192.168.0.248 'tmux ls 2>/dev/null || echo "无 tmux 会话"'
```

### 服务端日志说明

服务端用 `logging` 模块输出带时间戳的日志到 stdout，启动脚本已重定向到 `~/robot_server.log`。每条日志包含级别和时间：

```
2026-07-02 14:30:01 INFO    [g1.server] POST /action ok action=forward params={"duration":2.0} dt=2003ms
2026-07-02 14:30:05 WARNING [g1.server] POST /action busy action=move dt=0ms
2026-07-02 14:30:10 INFO    [g1.server] arm_action action=clap id=17 code=0
2026-07-02 14:30:20 WARNING [g1.server] POST /arm_action error action=hug arm action hug failed, code=-1 dt=50ms
```

- `dt=` 单个请求耗时（毫秒）
- `code=` SDK 返回码，非 0 即失败
- `params=` 请求参数（`pcm_base64`/`text` 等大字段已折叠为 `<N chars>`，不刷屏）
- `busy` 说明上一个动作还在执行，被 409 拒绝

### 通过 HTTP 远程看/存日志（无需 SSH、无需外接屏幕）

服务端额外提供两个 HTTP 日志接口，日志同时存在 PC2 的内存缓冲区里，笔记本直接通过 HTTP 拉取：

- `GET /logs?n=200` — 返回最近 N 行（JSON）
- `GET /logs/stream` — 实时流（SSE），可一直接收新日志

用配套脚本 `fetch_logs.py`，日志直接落到笔记本本地：

```bash
# 抓最近 200 行，打印到屏幕
python3 deploy/fetch_logs.py

# 抓最近 1000 行，存到本地文件
python3 deploy/fetch_logs.py --n 1000 --out logs.txt

# 实时流，持续写入本地文件（Ctrl+C 停止）
python3 deploy/fetch_logs.py --stream --out logs.txt

# 实时流直接打印到屏幕
python3 deploy/fetch_logs.py --stream

# 服务端带了 token 时
python3 deploy/fetch_logs.py --stream --token g1secret --out logs.txt
```

不带脚本也能直接用 curl：

```bash
# 最近 200 行
curl http://192.168.0.248:8888/logs?n=200

# 实时流到本地文件
curl -N http://192.168.0.248:8888/logs/stream >> logs.txt
```

> `--stream` 模式会先把缓冲区里的历史日志发一遍，再持续推新日志；断开重连不会丢已发生的日志。

### 日志级别

启动时可用 `--log-level` 控制详细度（默认 INFO），需要更详细的调试信息加 `DEBUG`：

```bash
python3 deploy/start_robot_server.py --sync --log-level DEBUG
# 或手动启动时直接传给服务脚本
ssh unitree@192.168.0.248 'tmux kill-session -t robot 2>/dev/null; tmux new-session -d -s robot "cd /home/unitree/Desktop/unitree_sdk2_python && PYTHONUNBUFFERED=1 python3 example/g1/high_level/robot_control_server.py eth0 --host 0.0.0.0 --port 8888 --log-level DEBUG > ~/robot_server.log 2>&1"'
```

---

## 4. 停止服务

```bash
ssh unitree@192.168.0.248 'tmux kill-session -t robot 2>/dev/null; pkill -f robot_control_server 2>/dev/null; echo done'
```

> `pkill -f robot_control_server` 按进程名匹配杀掉服务进程，等价于原来的 `kill $(ps | grep | awk ...)`，但无需管道和单引号嵌套，跨终端更稳。

---

## 5. 测试各接口

服务起来后，测各个 HTTP 接口（动作 / 手臂 / 语音）的命令见 [SERVICE_TEST_COMMANDS.md](SERVICE_TEST_COMMANDS.md)。

---

## 6. PC2 远程桌面（NoMachine）

如果需要在 PC2 上直接操作（改代码、调试等），通过 NoMachine 连接：

1. 下载安装 NoMachine：https://www.nomachine.com/download
2. 打开 NoMachine → **New**
3. Host：`192.168.0.248`，Port：`4000`，Protocol：`NX`
4. 连接后输入用户名 `unitree` 和 PC2 密码

> NoMachine 使用自有的 NX 协议（端口 4000），不需要先 SSH。只要 PC2 开机、nxserver 在跑就能连。

---

# 异常处理

## A. 免密登录手动配置

环境检测里免密没配成功时，手动配置。

### Linux / Mac

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
ssh-copy-id unitree@192.168.0.248
```

若 `ssh-copy-id` 因权限或文件不存在报错，手动追加公钥：

```bash
cat ~/.ssh/id_rsa.pub | ssh unitree@192.168.0.248 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

### Windows

PowerShell 中执行（`ssh-copy-id` 在 Windows 上不可用）：

```powershell
# 1. 生成密钥
ssh-keygen -t rsa -b 4096 -f "$env:USERPROFILE\.ssh\id_rsa" -N '""'

# 2. 手动复制公钥到 PC2
type "$env:USERPROFILE\.ssh\id_rsa.pub" | ssh unitree@192.168.0.248 'cat >> ~/.ssh/authorized_keys'
```

配置完重跑 `python3 deploy/check_env.py --check`，免密项通过即可。

---

## B. Mac 环境修复

环境检测跑不过时，按对应项处理。Mac 上 SSH 客户端和 `ssh-copy-id` 都自带，通常问题出在 Python。

### Python 未安装 / 版本低于 3.8

macOS 自带的 `python3` 可能缺失或版本过旧。推荐用 Homebrew 安装：

```bash
# 1. 安装 Homebrew（如已装可跳过）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 安装 Python 3
brew install python

# 3. 验证（Apple Silicon 路径为 /opt/homebrew/bin，Intel 为 /usr/local/bin）
python3 --version
```

如果 `python3` 装完仍找不到，把 Homebrew 路径加到 PATH：

```bash
# Apple Silicon
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

# Intel
echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/usr/local/bin/brew shellenv)"
```

不想装 Homebrew 也可以从 https://python.org 下载官方安装包，装完勾选的 "Install Certificates.command" 要执行一下（否则 `requests` 走 HTTPS 会报证书错误）。

### requests 包缺失

```bash
pip3 install requests
```

若提示 `externally-managed-environment`（新版 Homebrew Python 的限制），用虚拟环境或加 `--break-system-packages`：

```bash
# 方式一：虚拟环境（推荐）
python3 -m venv ~/venv
source ~/venv/bin/activate
pip install requests

# 方式二：强制安装到用户目录
pip3 install --user --break-system-packages requests
```

用虚拟环境时，后续跑 `start_robot_server.py` 要先 `source ~/venv/bin/activate`。

### SSH 免密登录

见上方 [A. 免密登录手动配置](#a-免密登录手动配置)。

### 重新检测

配置完重跑 `python3 deploy/check_env.py --check`，四项全过即可。

---

## C. NoMachine 连不上

SSH 到 PC2 检查 nxserver 状态：

```bash
ssh unitree@192.168.0.248 'sudo systemctl status nxserver --no-pager'
```

---

## D. 平台差异说明

启动脚本 `start_robot_server.py` 在任何平台都能跑，只需要 Python 3 和 `requests` 包，内部用 `subprocess` 调用系统的 `ssh`/`scp`。

### 路径

文档中的 `/home/mario/Desktop/unitree/unitree_sdk2_python` 是 Linux 示例，其他平台对应：

| 平台 | 项目路径示例 |
|------|-------------|
| Linux | `/home/mario/Desktop/unitree/unitree_sdk2_python` |
| Mac | `/Users/mario/Desktop/unitree/unitree_sdk2_python` |
| Windows | `C:\Users\mario\Desktop\unitree\unitree_sdk2_python` |

### Python

| 平台 | 命令 |
|------|------|
| Linux | `python3` |
| Mac | `python3` |
| Windows | `python`（安装时勾选 "Add to PATH"） |

Windows 需从 https://python.org 下载安装，另外安装 `requests`：

```powershell
pip install requests
```

### SSH

| 平台 | 说明 |
|------|------|
| Linux / Mac | 自带 |
| Windows | Win10 1803+ 自带 OpenSSH 客户端，旧版用 PuTTY 或 Git Bash |

### curl

| 平台 | 说明 |
|------|------|
| Linux | 通常自带 |
| Mac | 自带 |
| Windows | Win10 1803+ 自带；旧版可从 https://curl.se 安装，或用 PowerShell 替代 |

> Windows 上 curl 引号/别名坑较多，测接口建议参考 [SERVICE_TEST_COMMANDS.md](SERVICE_TEST_COMMANDS.md) 顶部「按终端选版本」表，直接用对应终端的写法。
