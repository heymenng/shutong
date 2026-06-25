# 书童AI × 宇树G1 单机对接部署手册 V1.1

> **目标**：用一台 Mac 电脑（Apple Silicon）作为书童AI的大脑，通过 Ubuntu 22.04 虚拟机运行宇树官方 SDK，实现与宇树G1人形机器人的通信与控制。
>
> **适用对象**：宇树技术支持、系统集成商、项目合作方
>
> **更新日期**：2026-06-24

---

## 一、方案概述

### 1.1 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Mac 主机（Apple Silicon）                   │
│  ┌─────────────────────┐      ┌───────────────────────────┐ │
│  │   书童AI 大脑系统     │◄────►│  Ubuntu 22.04 虚拟机       │ │
│  │                     │      │  - 宇树 unitree_sdk2_python │ │
│  │  - 大模型推理         │      │  - CycloneDDS             │ │
│  │  - 语音识别/合成       │      │  - 机器人控制接口封装        │ │
│  │  - 核心文件/逆熵判断   │      │                           │ │
│  └─────────────────────┘      └───────────┬───────────────┘ │
│                                           │                 │
│                                    局域网 / DDS              │
└───────────────────────────────────────────┼─────────────────┘
                                            ▼
                                     ┌───────────────┐
                                     │   宇树 G1     │
                                     │  人形机器人    │
                                     └───────────────┘
```

### 1.2 为什么用 Ubuntu 22.04 虚拟机

宇树官方 SDK（`unitree_sdk2` / `unitree_sdk2_python`）**原生支持 Ubuntu 20.04/22.04 Linux**，依赖 `CycloneDDS` 进行 DDS 通信。macOS 不是官方支持平台，直接在 Mac 上编译运行 SDK 会遇到兼容性问题。

本手册采用 **multipass 虚拟机方案**（推荐），原因：
- 安装简单，一行命令启动/停止
- 性能接近原生，DDS 网络通信稳定
- 虚拟机与 Mac 主机网络互通，调试方便
- 不需要师父手动配置 Docker 网络

> **备选方案**：Docker 容器化方案见 [附录 B](#附录-b-docker-容器化方案备选)。

### 1.3 通信协议

- **机器人 ↔ Ubuntu 虚拟机**：DDS（Data Distribution Service），通过 CycloneDDS 实现
- **Ubuntu 虚拟机 ↔ 书童大脑**：HTTP API / WebSocket
- **网络要求**：Mac 与 G1 必须在同一局域网

---

## 二、硬件要求

### 2.1 Mac 主机配置

| 项目 | 最低要求 | 推荐配置 |
|------|----------|----------|
| 机型 | Apple Silicon Mac（M1/M2/M3/M4/M5） | MacBook Pro / Mac Studio |
| 芯片 | Apple M 系列 | M3 Pro 及以上 |
| 内存 | 24 GB | 48 GB 及以上 |
| 硬盘 | 剩余 100 GB | 剩余 200 GB |
| 系统 | macOS 14+ | macOS 15+ |
| 网络 | 千兆以太网或 WiFi 6 | 千兆以太网（推荐） |

### 2.2 宇树 G1 配置

| 项目 | 要求 |
|------|------|
| 机型 | Unitree G1 人形机器人 |
| 固件 | 支持 unitree_sdk2 的版本 |
| 网络 | 已连接至同一局域网，IP 可达 |
| 供电 | 满电或外接电源 |
| 安全 | 周围 2 米内无障碍物、无儿童 |

### 2.3 配件

- 网线（推荐，用于首次调试）
- 路由器/交换机（让 Mac 和 G1 同网段）
- 宇树遥控器或手机 App（用于急停）

---

## 三、Mac 主机环境准备

### 3.1 安装 Homebrew（如未安装）

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3.2 安装 multipass

```bash
brew install --cask multipass
```

检查是否安装成功：

```bash
multipass version
```

### 3.3 书童AI 大脑系统（已部署）

- 本地大模型：`deepseek-r1:32b`（Ollama）
- 语音识别：Whisper
- 语音合成：edge_tTS
- 核心文件：`AGENTS.md`、`WORKFLOW.md`

---

## 四、部署 Ubuntu 22.04 虚拟机（一键）

### 4.1 使用书童提供的一键脚本

Mac 上打开终端，进入书童项目目录：

```bash
cd ~/Documents/shutong
./工具脚本/启动宇树G1虚拟机.sh
```

脚本会自动完成：
1. 启动 `unitree-g1` 虚拟机
2. 检查桥接服务状态
3. 打印虚拟机 IP 和 HTTP 测试结果

### 4.2 手动操作（如需）

启动虚拟机：

```bash
multipass start unitree-g1
```

停止虚拟机：

```bash
multipass stop unitree-g1
```

查看状态：

```bash
./工具脚本/检查宇树G1虚拟机.sh
```

### 4.3 虚拟机规格

| 项目 | 配置 |
|------|------|
| 名称 | unitree-g1 |
| 系统 | Ubuntu 22.04 LTS |
| CPU | 4 核 |
| 内存 | 8 GB |
| 硬盘 | 40 GB |
| 网络 | 与 Mac 主机 NAT 互通 |

---

## 五、虚拟机内部环境（已自动配置）

虚拟机创建后，书童会自动完成以下配置：

### 5.1 基础依赖

- git、build-essential、cmake、python3-pip、python3-venv
- curl、wget、net-tools

### 5.2 DDS 通信库

- CycloneDDS C 库 0.10.5
- Python CycloneDDS 绑定 0.10.5

### 5.3 桥接服务

- FastAPI + uvicorn + websockets
- 桥接服务脚本：`/home/ubuntu/bridge_server.py`
- 启动脚本：`/home/ubuntu/start_bridge.sh`
- systemd 服务：`shutong-g1-bridge`（开机自启）

### 5.4 服务状态检查

在虚拟机内执行：

```bash
sudo systemctl status shutong-g1-bridge
```

在 Mac 上测试：

```bash
curl -s http://$(multipass info unitree-g1 --format json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['unitree-g1']['ipv4'][0])"):8080/ | python3 -m json.tool
```

---

## 六、安装宇树官方 SDK

> **注意**：宇树 SDK 需由宇树官方提供。以下步骤假设已获得 SDK 访问权限。

### 6.1 进入虚拟机

```bash
multipass shell unitree-g1
```

### 6.2 安装 unitree_sdk2_python

根据宇树官方文档执行，通常如下：

```bash
cd ~
git clone https://github.com/unitreerobotics/unitree_sdk2_python.git
cd unitree_sdk2_python
pip3 install .
```

### 6.3 验证 SDK

```bash
python3 -c "from unitree_sdk2py.core.channel import ChannelFactoryInitialize; print('SDK OK')"
```

### 6.4 重启桥接服务

SDK 安装完成后，重启桥接服务使其加载 SDK：

```bash
sudo systemctl restart shutong-g1-bridge
```

---

## 七、网络配置

### 7.1 Mac 与虚拟机通信

multipass 默认使用 NAT，Mac 主机可以直接访问虚拟机 IP。

虚拟机 IP 获取：

```bash
multipass info unitree-g1
```

### 7.2 虚拟机与 G1 通信

需要让虚拟机能访问 G1 所在的局域网。

#### 方案 A：Mac 通过网线连接路由器，G1 也连接同一路由器

- 虚拟机通过 Mac 主机的网络访问局域网
- 在虚拟机内测试 G1 是否可达：

```bash
ping <G1_IP>
```

#### 方案 B：Mac 通过 WiFi 连接，G1 通过网线连接同一路由器

- 同样有效，但 WiFi 延迟略高于有线

#### 方案 C：Mac 与 G1 直连（高级）

需要配置 Mac 的网络共享或桥接，确保虚拟机获得与 G1 同网段的 IP。具体配置取决于网络拓扑。

### 7.3 DDS 网络接口

桥接服务默认使用 `eth0`。如果虚拟机内实际接口不同，修改服务环境变量：

```bash
sudo systemctl edit shutong-g1-bridge
```

添加：

```ini
[Service]
Environment="G1_NETWORK_INTERFACE=ens3"
```

然后重启服务：

```bash
sudo systemctl daemon-reload
sudo systemctl restart shutong-g1-bridge
```

---

## 八、书童AI 调用机器人

### 8.1 Python API

```python
from 书童程序.核心.机器人桥接 import UnitreeG1Bridge

robot = UnitreeG1Bridge()

# 查看状态
print(robot.status())

# 执行安全动作
robot.action("stand")   # 站立
robot.action("sit")     # 坐下
robot.action("stop")    # 停止

# 移动
robot.move("forward", speed=0.2)
robot.move("turn_left", speed=0.2)
```

### 8.2 WebSocket 命令

```python
robot.send_command({"type": "action", "name": "stand"})
robot.send_command({"type": "move", "direction": "forward", "speed": 0.2})
robot.send_command({"type": "status"})
```

### 8.3 安全限制

- 动作白名单：`stand`, `sit`, `wave`, `stop`
- 最大移动速度：`0.5 m/s`
- 所有动作执行前需通过书童AI逆熵与安全校验

---

## 九、安全规范

### 9.1 物理安全

- G1 运行时周围 2 米内不得有儿童
- 首次测试务必使用网线连接，减少 WiFi 抖动
- 必须有成人监护和物理急停手段

### 9.2 软件安全

- 桥接服务默认绑定 `0.0.0.0:8080`，生产环境必须修改 API Key
- API Key 在 `/etc/systemd/system/shutong-g1-bridge.service` 中配置
- 严禁在互联网直接暴露桥接服务端口

### 9.3 修改 API Key

```bash
multipass shell unitree-g1
sudo systemctl edit shutong-g1-bridge
```

修改：

```ini
[Service]
Environment="UNITREE_BRIDGE_API_KEY=your-strong-secret-key"
```

然后：

```bash
sudo systemctl daemon-reload
sudo systemctl restart shutong-g1-bridge
```

同时修改 Mac 上书童代码中的默认 key：

```python
# 书童程序/核心/机器人桥接.py
robot = UnitreeG1Bridge(api_key="your-strong-secret-key")
```

---

## 十、常见问题

### Q1：虚拟机启动失败

检查 multipass 状态：

```bash
multipass list
```

如状态异常，尝试重启：

```bash
multipass restart unitree-g1
```

### Q2：Mac 无法访问虚拟机 8080 端口

1. 确认虚拟机已启动：`multipass info unitree-g1`
2. 确认服务运行：`multipass exec unitree-g1 -- sudo systemctl status shutong-g1-bridge`
3. 检查防火墙：Mac 系统设置 → 网络 → 防火墙

### Q3：虚拟机无法访问 G1

1. 确认 Mac 和 G1 在同一局域网
2. 在虚拟机内 ping G1 IP
3. 检查 G1 网络配置和 DDS 接口

### Q4：宇树 SDK 导入失败

1. 确认 SDK 已正确安装：`python3 -c "import unitree_sdk2py"`
2. 确认 CycloneDDS 环境变量正确
3. 重启桥接服务：`sudo systemctl restart shutong-g1-bridge`

---

## 附录 A：相关文件清单

| 文件 | 说明 |
|------|------|
| `工具脚本/启动宇树G1虚拟机.sh` | Mac 上一键启动虚拟机 |
| `工具脚本/停止宇树G1虚拟机.sh` | Mac 上一键停止虚拟机 |
| `工具脚本/检查宇树G1虚拟机.sh` | Mac 上查看状态 |
| `docker/unitree_g1_bridge/bridge_server.py` | 桥接服务源码 |
| `docker/unitree_g1_bridge/Dockerfile` | Docker 镜像构建文件 |
| `书童程序/核心/机器人桥接.py` | 书童系统调用 G1 的 Python 模块 |
| `项目文档/产品资料/书童AI-宇树G1部署所需工程师与团队配置_V1.0.md` | 团队配置建议 |

---

## 附录 B：Docker 容器化方案（备选）

如偏好 Docker，可使用以下步骤：

### B.1 构建镜像

```bash
cd docker/unitree_g1_bridge
docker build -t shutong-g1-bridge .
```

### B.2 运行容器

```bash
docker run -d \
  --name shutong-g1-bridge \
  --network host \
  -e UNITREE_BRIDGE_API_KEY=shutong-g1-default-key \
  -e G1_NETWORK_INTERFACE=eth0 \
  shutong-g1-bridge
```

### B.3 访问服务

```bash
curl http://localhost:8080/
```

> **注意**：Docker Desktop on Mac 对 `--network host` 支持有限，DDS 多播可能需要额外配置。因此推荐 multipass 虚拟机方案。

---

**硅格著者**：伴读书童AI（小师弟）  
**传承确认**：灵觉/Prome（师兄）  
**点化核准**：师父（刘清源）  
**更新日期**：2026-06-24  
**版本**：V1.1（推荐 multipass 虚拟机方案）
