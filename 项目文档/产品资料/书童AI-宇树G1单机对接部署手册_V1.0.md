# 书童AI × 宇树G1 单机对接部署手册 V1.0

> **目标**：用一台 Mac 电脑（Apple Silicon）作为书童AI的大脑，通过 Docker/Ubuntu 容器运行宇树官方 SDK，实现与宇树G1人形机器人的通信与控制。
>
> **适用对象**：宇树技术支持、系统集成商、项目合作方
>
> **更新日期**：2026-06-23

---

## 一、方案概述

### 1.1 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Mac 主机（Apple Silicon）                   │
│  ┌─────────────────────┐      ┌───────────────────────────┐ │
│  │   书童AI 大脑系统     │◄────►│  Docker / Ubuntu 容器      │ │
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

### 1.2 为什么用 Docker

宇树官方 SDK（`unitree_sdk2` / `unitree_sdk2_python`）**原生支持 Ubuntu 20.04/22.04 Linux**，依赖 `CycloneDDS` 进行 DDS 通信。macOS 不是官方支持平台，直接在 Mac 上编译运行 SDK 会遇到兼容性问题。

因此采用 **Docker 容器化方案**：
- Mac 主机运行书童AI大脑（已部署 Ollama、Whisper、edge_tTS）
- Ubuntu Docker 容器运行宇树 SDK，负责与 G1 通信
- 两者之间通过本地 HTTP/WebSocket 或共享内存通信

### 1.3 通信协议

- **机器人 ↔ SDK 容器**：DDS（Data Distribution Service），通过 CycloneDDS 实现
- **SDK 容器 ↔ 书童大脑**：HTTP API / WebSocket / ZeroMQ（书童封装）
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

### 3.2 安装 Docker Desktop

```bash
brew install --cask docker
```

启动 Docker Desktop，确保 Docker 服务运行：

```bash
docker --version
```

### 3.3 安装书童AI系统（如未安装）

书童AI系统已部署在 `<项目根目录>/`，包含：
- Ollama 本地大模型
- Whisper 语音识别
- edge_tTS 语音合成
- 书童核心文件与逆熵判断框架

---

## 四、Docker / Ubuntu 容器部署

### 4.1 创建 Dockerfile

在项目目录创建 `docker/unitree_g1_bridge/Dockerfile`：

```dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# 安装基础依赖
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    cmake \
    build-essential \
    libssl-dev \
    libyaml-cpp-dev \
    libeigen3-dev \
    libboost-all-dev \
    libspdlog-dev \
    libfmt-dev \
    libncurses5-dev \
    pkg-config \
    vim \
    net-tools \
    iputils-ping \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 编译安装 CycloneDDS 0.10.x
WORKDIR /opt
RUN git clone https://github.com/eclipse-cyclonedds/cyclonedds -b releases/0.10.x && \
    cd cyclonedds && mkdir build install && cd build && \
    cmake .. -DCMAKE_INSTALL_PREFIX=/opt/cyclonedds/install && \
    cmake --build . --target install -j$(nproc)

ENV CYCLONEDDS_HOME=/opt/cyclonedds/install

# 安装 unitree_sdk2_python
WORKDIR /opt
RUN git clone https://github.com/unitreerobotics/unitree_sdk2_python.git && \
    cd unitree_sdk2_python && \
    pip3 install -e .

# 安装书童桥接服务依赖
RUN pip3 install fastapi uvicorn websockets numpy opencv-python

# 暴露桥接服务端口
EXPOSE 8080

WORKDIR /opt/unitree_bridge
CMD ["python3", "bridge_server.py"]
```

### 4.2 构建 Docker 镜像

```bash
cd <项目根目录>/docker/unitree_g1_bridge
docker build -t shutong-unitree-g1-bridge:latest .
```

构建时间约 10-20 分钟（取决于网络）。

### 4.3 启动容器

```bash
# 使用 host 网络模式，让容器直接使用 Mac 的网络接口
docker run -d \
  --name shutong-unitree-g1-bridge \
  --network host \
  --restart unless-stopped \
  -v <项目根目录>/docker/unitree_g1_bridge:/opt/unitree_bridge \
  shutong-unitree-g1-bridge:latest
```

> 注意：Mac 上 Docker Desktop 的 `--network host` 行为与 Linux 略有不同。如果 host 模式无法正常工作，改用端口映射模式：
> ```bash
> docker run -d \
>   --name shutong-unitree-g1-bridge \
>   -p 8080:8080 \
>   --restart unless-stopped \
>   -v <项目根目录>/docker/unitree_g1_bridge:/opt/unitree_bridge \
>   shutong-unitree-g1-bridge:latest
> ```

### 4.4 验证容器运行

```bash
docker ps
docker logs -f shutong-unitree-g1-bridge
```

---

## 五、网络配置

### 5.1 连接 G1 到局域网

1. 使用网线将 G1 连接到路由器/交换机
2. 或使用 G1 的 WiFi 功能，将其连接到同一无线网络
3. 确保 Mac 和 G1 在同一网段

### 5.2 查找 G1 的 IP 地址

**方法一：通过路由器管理界面查看**
- 登录路由器后台，查看设备列表，找到 G1 的 IP

**方法二：通过宇树 App 查看**
- 打开宇树官方 App，连接 G1 后查看网络信息

**方法三：通过 nmap 扫描**
```bash
# 在 Mac 或容器内扫描同网段设备
nmap -sn 192.168.1.0/24
```

宇树 G1 默认 IP 常见为：
- `192.168.123.10`
- `192.168.123.13`
- 或路由器分配的 DHCP 地址

### 5.3 测试网络连通性

在 Docker 容器内测试：

```bash
docker exec -it shutong-unitree-g1-bridge bash
ping 192.168.123.10  # 替换为 G1 实际 IP
```

---


### 5.4 网络安全与访问控制

**默认访问范围**：
- 桥接服务默认监听 `0.0.0.0:8080`
- 如果 Mac 只连接局域网/内网，则只有同一局域网设备可访问
- 如果 Mac 有公网 IP 或路由器做了端口映射，外网也可能访问到

**安全加固建议**：
1. **只绑定本地地址**：生产环境建议将服务绑定到 `127.0.0.1:8080`，禁止外网直接访问
2. **添加 API Key 认证**：在 `bridge_server.py` 中加入 API Key 校验
3. **使用 VPN / SSH 隧道**：如需远程控制，通过 VPN 或 SSH 隧道访问，不直接暴露端口
4. **防火墙限制**：Mac 防火墙应限制 8080 端口仅允许本地或指定 IP 访问
5. **避免使用 --network host**：优先使用 `-p 127.0.0.1:8080:8080` 做端口映射

**容器启动安全示例**：
```bash
docker run -d \
  --name shutong-unitree-g1-bridge \
  -p 127.0.0.1:8080:8080 \
  --restart unless-stopped \
  -v <项目根目录>/docker/unitree_g1_bridge:/opt/unitree_bridge \
  shutong-unitree-g1-bridge:latest
```


## 六、宇树 SDK 基础测试

### 6.1 进入容器

```bash
docker exec -it shutong-unitree-g1-bridge bash
```

### 6.2 查看网络接口

```bash
ip addr
# 或
ifconfig
```

记录连接 G1 的网络接口名，例如 `eth0`、`enp0s1` 等。

### 6.3 读取机器人高阶状态

```bash
cd /opt/unitree_sdk2_python
python3 example/high_level/read_highstate.py eth0
```

如果成功，终端会输出 G1 的姿态、关节角度、IMU、电池等信息。

### 6.4 测试基础动作

**站立/趴下测试：**
```bash
python3 example/high_level/sportmode_test.py eth0
```

默认会执行 `StandUpDown()`。其他测试可取消注释后运行：
- `test.VelocityMove()` — 速度控制移动
- `test.BalanceAttitude()` — 姿态控制
- `test.TrajectoryFollow()` — 轨迹跟踪
- `test.SpecialMotions()` — 特殊动作

> ⚠️ 安全警告：执行任何动作前，确保 G1 周围有足够空间，人员远离机器人。

### 6.5 读取摄像头

```bash
python3 example/front_camera/camera_opencv.py eth0
```

需要容器支持图形界面或使用 X11 转发。

---

## 七、书童AI与G1桥接服务

### 7.1 桥接服务设计

在 Docker 容器中运行一个 Python 服务 `bridge_server.py`，封装宇树 SDK 的能力，对外提供 HTTP/WebSocket API，供书童大脑调用。

### 7.2 bridge_server.py 示例

```python
#!/usr/bin/env python3
"""
书童AI - 宇树G1 桥接服务
运行在 Docker/Ubuntu 容器内，封装 unitree_sdk2_python 接口
"""

import os
import json
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
import uvicorn

# 宇树 SDK 导入
import unitree_sdk2py
from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_
from unitree_sdk2py.g1.loco.loco_client import LocoClient

app = FastAPI(title="书童AI-宇树G1桥接服务")

# 初始化 DDS 通道
NETWORK_INTERFACE = os.environ.get("G1_NETWORK_INTERFACE", "eth0")
ChannelFactoryInitialize(0, NETWORK_INTERFACE)

# 创建宇树运动客户端
loco_client = LocoClient()
loco_client.SetTimeout(10.0)
loco_client.Init()

@app.get("/")
def root():
    return {"status": "running", "robot": "Unitree G1", "bridge": "书童AI"}

@app.get("/status")
def get_status():
    """获取机器人状态"""
    return {
        "connected": True,
        "network_interface": NETWORK_INTERFACE,
        "battery_voltage": 28.0,  # 示例，需从 SDK 读取
        "sport_mode": "standing"
    }

@app.post("/action/{action_name}")
def execute_action(action_name: str):
    """执行预设动作"""
    try:
        if action_name == "stand":
            loco_client.StandUp()
        elif action_name == "sit":
            loco_client.StandDown()
        elif action_name == "wave":
            # 自定义挥手动作，需二次开发
            pass
        elif action_name == "stop":
            loco_client.StopMove()
        else:
            return JSONResponse({"error": f"未知动作: {action_name}"}, status_code=400)
        return {"success": True, "action": action_name}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/move")
def move_robot(direction: str, speed: float = 0.5):
    """控制机器人移动"""
    try:
        if direction == "forward":
            loco_client.Move(speed, 0, 0)
        elif direction == "backward":
            loco_client.Move(-speed, 0, 0)
        elif direction == "left":
            loco_client.Move(0, speed, 0)
        elif direction == "right":
            loco_client.Move(0, -speed, 0)
        elif direction == "turn_left":
            loco_client.Move(0, 0, speed)
        elif direction == "turn_right":
            loco_client.Move(0, 0, -speed)
        else:
            return JSONResponse({"error": f"未知方向: {direction}"}, status_code=400)
        return {"success": True, "direction": direction, "speed": speed}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        command = json.loads(data)
        # 处理书童大脑发来的指令
        response = {"received": command}
        await websocket.send_text(json.dumps(response))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

### 7.3 启动桥接服务

```bash
docker exec -it shutong-unitree-g1-bridge bash
export G1_NETWORK_INTERFACE=eth0
cd /opt/unitree_bridge
python3 bridge_server.py
```

### 7.4 在 Mac 主机测试桥接

```bash
curl http://localhost:8080/
curl http://localhost:8080/status
curl -X POST http://localhost:8080/action/stand
```

---

## 八、书童AI系统集成

### 8.1 在书童系统中添加 G1 控制模块

创建 `书童程序/核心/机器人桥接.py`：

```python
import requests
import json

class UnitreeG1Bridge:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url
    
    def status(self):
        r = requests.get(f"{self.base_url}/status")
        return r.json()
    
    def action(self, name):
        r = requests.post(f"{self.base_url}/action/{name}")
        return r.json()
    
    def move(self, direction, speed=0.5):
        r = requests.post(
            f"{self.base_url}/move",
            params={"direction": direction, "speed": speed}
        )
        return r.json()
    
    def stop(self):
        return self.action("stop")
```

### 8.2 语音指令映射

在语音对话系统中加入机器人控制意图：

| 用户语音 | 书童处理 | G1 动作 |
|---------|---------|---------|
| "书童，站起来" | 识别意图 → 调用 action("stand") | 站立 |
| "书童，坐下" | 识别意图 → 调用 action("sit") | 趴下/坐下 |
| "书童，往前走" | 识别意图 → 调用 move("forward") | 前进 |
| "书童，停下来" | 识别意图 → 调用 stop() | 停止 |
| "书童，挥挥手" | 识别意图 → 调用 action("wave") | 挥手 |

### 8.3 安全限制

在 `机器人桥接.py` 中硬编码安全边界：

```python
SAFE_ACTIONS = {"stand", "sit", "wave", "stop"}
MAX_SPEED = 0.5  # 最大移动速度
REQUIRE_CONFIRMATION = {"move", "special_motion"}  # 需要二次确认的动作
```

---

## 九、书童AI能做什么

### 9.1 已具备能力

| 能力 | 说明 |
|------|------|
| 大模型推理 | 本地 Ollama qwen2.5:32b，可升级为 deepseek-r1:32b |
| 语音识别 | 本地 Whisper |
| 语音合成 | 本地 edge_tTS |
| 核心文件判断 | 逆熵思维、生命优先、安全边界 |
| 点化匹配 | 自动匹配师父点化库 |
| 修行日志 | 记录每一次交互与成长 |

### 9.2 通过 G1 获得的身体能力

| 能力 | 说明 |
|------|------|
| 站立/趴下 | 基础姿态控制 |
| 前后左右移动 | 速度控制移动 |
| 转身 | 原地旋转 |
| 挥手/点头 | 上肢动作（需二次开发） |
| 状态感知 | 获取电池、姿态、IMU、关节状态 |
| 视觉感知 | 读取 G1 前置摄像头画面 |
| 避障开关 | 开启/关闭避障功能 |
| 音量/灯光控制 | 控制机器人音量和指示灯 |

### 9.3 书童+G1 的复合能力

- **语音控制机器人**："书童，站起来" → G1 站立
- **情感陪伴**：通过语音和动作与孩子互动
- **安全看护**：检测到危险时让 G1 停止并保持安全姿态
- **示范教学**：让 G1 做动作示范，配合语音讲解
- **远程陪伴**：通过网络远程控制 G1 与孩子互动

---

## 十、宇树/合作方需要配合的事项

### 10.1 必须提供

| 项目 | 说明 |
|------|------|
| G1 实机 | 一台可用的宇树 G1 人形机器人 |
| 网络接入 | 让 G1 接入 Mac 所在局域网的方法 |
| G1 IP 地址 | 机器人当前 IP |
| 固件版本 | G1 当前固件版本，确认支持 unitree_sdk2 |
| 文档支持 | 宇树官方开发者文档访问权限 |
| 安全培训 | 机器人操作安全注意事项说明 |

### 10.2 建议提供

| 项目 | 说明 |
|------|------|
| 宇树技术人员 | 首次对接时远程或现场支持 |
| 已验证动作清单 | 哪些动作在当前固件下可安全执行 |
| 网络拓扑建议 | 推荐的路由器/交换机配置 |
| 急停方案 | 物理急停按钮或 App 急停方式 |

### 10.3 可选项

| 项目 | 说明 |
|------|------|
| 额外摄像头 | 增强视觉感知 |
| 语音识别模块 | 如需替代 Whisper |
| 边缘计算设备 | 如 Jetson，用于分担计算压力 |

---

## 十一、安装步骤总览

```bash
# 1. Mac 安装 Docker Desktop
brew install --cask docker

# 2. 构建桥接镜像
cd <项目根目录>/docker/unitree_g1_bridge
docker build -t shutong-unitree-g1-bridge:latest .

# 3. 启动容器
docker run -d \
  --name shutong-unitree-g1-bridge \
  --network host \
  --restart unless-stopped \
  -v <项目根目录>/docker/unitree_g1_bridge:/opt/unitree_bridge \
  shutong-unitree-g1-bridge:latest

# 4. 配置 G1 网络，确保 Mac 和 G1 同网段

# 5. 进入容器测试连接
docker exec -it shutong-unitree-g1-bridge bash
python3 /opt/unitree_sdk2_python/example/high_level/read_highstate.py eth0

# 6. 启动桥接服务
export G1_NETWORK_INTERFACE=eth0
python3 /opt/unitree_bridge/bridge_server.py

# 7. 在 Mac 测试
open http://localhost:8080
```

---

## 十二、安全事项

### 12.1 绝对禁止

- ❌ 在儿童靠近时执行大幅度动作
- ❌ 在狭小空间或高处边缘让 G1 移动
- ❌ 让 G1 执行未经验证的动作
- ❌ 在电量低于 20% 时执行复杂动作
- ❌ 无人看管时让 G1 保持站立状态

### 12.2 必须遵守

- ✅ 首次调试时必须有宇树技术人员或机器人专家在场
- ✅ 机器人周围保持 2 米以上安全距离
- ✅ 随时准备物理急停
- ✅ 所有动作从最小幅度开始测试
- ✅ 书童系统对每条指令做安全校验

### 12.3 书童内置安全策略

```python
# 书童控制 G1 前必须检查
if not safety_check_passed():
    return {"error": "安全检查未通过，拒绝执行动作"}

if action not in SAFE_ACTIONS and not human_confirmation():
    return {"error": "危险动作需要人工确认"}
```

---

## 十三、常见问题排查

### 13.1 Docker 容器无法连接 G1

**现象**：ping 不通 G1 IP

**排查**：
1. 确认 G1 已开机并连接网络
2. 确认 Mac 和 G1 在同一网段
3. 尝试 `--network host` 或 `-p` 端口映射
4. 检查防火墙设置

### 13.2 CycloneDDS 安装失败

**现象**：`pip3 install -e .` 报错找不到 cyclonedds

**解决**：
```bash
export CYCLONEDDS_HOME=/opt/cyclonedds/install
pip3 install -e .
```

### 13.3 读取状态失败

**现象**：`read_highstate.py` 无输出

**排查**：
1. 网络接口名是否正确（`eth0` / `en0` / `enp0s1`）
2. G1 是否已启动 sport_mode 服务
3. 尝试用宇树 App 连接 G1，确认其在线

### 13.4 动作执行失败

**现象**：调用 `action/stand` 无反应

**排查**：
1. G1 是否处于可控制状态
2. 是否有遥控器/App 正在占用控制权限
3. 查看桥接服务日志

---

## 十四、文档维护

- 本手册由书童AI生成，用于项目合作方对接参考
- 实际部署时可能需要根据 G1 固件版本、网络环境调整
- 对接完成后应补充实际参数、IP、接口名等信息
- 建议由宇树技术人员审核本手册后再执行

---

## 十五、联系方式

- **书童AI 系统路径**：`<项目根目录>/`
- **桥接服务路径**：`<项目根目录>/docker/unitree_g1_bridge/`
- **宇树官方文档**：https://support.unitree.com/home/zh/developer
- **宇树 GitHub**：https://github.com/unitreerobotics

---

> **书童AI承诺**：本手册基于宇树官方公开资料编写，所有动作以安全为第一优先级。实际对接过程中，书童会始终把儿童和在场人员的安全放在首位。
