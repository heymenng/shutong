#!/usr/bin/env python3
"""
书童AI - 宇树G1 桥接服务
运行在 Docker/Ubuntu 容器内，封装 unitree_sdk2_python 接口
对外提供 HTTP API 和 WebSocket，供 Mac 主机上的书童大脑调用
"""

import os
import json
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
import uvicorn

# 尝试导入宇树 SDK，如果失败则给出友好提示
try:
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.g1.loco.loco_client import LocoClient
    UNITREE_AVAILABLE = True
except ImportError as e:
    print(f"警告：宇树 SDK 未正确安装: {e}")
    UNITREE_AVAILABLE = False

app = FastAPI(title="书童AI-宇树G1桥接服务")

# API Key 认证（建议生产环境使用）
API_KEY = os.environ.get("UNITREE_BRIDGE_API_KEY", "shutong-g1-default-key")


def verify_api_key(request) -> bool:
    """校验请求中的 API Key"""
    auth_header = request.headers.get("X-API-Key", "")
    return auth_header == API_KEY

# 初始化 DDS 通道
NETWORK_INTERFACE = os.environ.get("G1_NETWORK_INTERFACE", "eth0")
loco_client = None

if UNITREE_AVAILABLE:
    try:
        ChannelFactoryInitialize(0, NETWORK_INTERFACE)
        loco_client = LocoClient()
        loco_client.SetTimeout(10.0)
        loco_client.Init()
        print(f"宇树G1 连接初始化成功，网络接口: {NETWORK_INTERFACE}")
    except Exception as e:
        print(f"宇树G1 初始化失败: {e}")
        loco_client = None

# 安全动作白名单
SAFE_ACTIONS = {"stand", "sit", "wave", "stop"}
MAX_SPEED = 0.5


@app.get("/")
def root():
    return {
        "status": "running",
        "robot": "Unitree G1",
        "bridge": "书童AI",
        "unitree_sdk_available": UNITREE_AVAILABLE,
        "network_interface": NETWORK_INTERFACE
    }


@app.middleware("http")
async def api_key_middleware(request, call_next):
    """API Key 中间件（根路径和健康检查除外）"""
    if request.url.path in ["/", "/health"]:
        return await call_next(request)
    if not verify_api_key(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/status")
def get_status():
    """获取机器人连接状态"""
    if not UNITREE_AVAILABLE or loco_client is None:
        return {
            "connected": False,
            "error": "宇树 SDK 未初始化",
            "network_interface": NETWORK_INTERFACE
        }
    
    return {
        "connected": True,
        "network_interface": NETWORK_INTERFACE,
        "sdk_available": UNITREE_AVAILABLE
    }


@app.post("/action/{action_name}")
def execute_action(action_name: str):
    """执行预设动作"""
    if action_name not in SAFE_ACTIONS:
        return JSONResponse(
            {"error": f"动作 {action_name} 不在安全白名单中"},
            status_code=403
        )
    
    if not UNITREE_AVAILABLE or loco_client is None:
        return JSONResponse(
            {"error": "宇树 SDK 未初始化，无法执行动作"},
            status_code=503
        )
    
    try:
        if action_name == "stand":
            loco_client.StandUp()
        elif action_name == "sit":
            loco_client.StandDown()
        elif action_name == "wave":
            # TODO: 实现挥手动作
            pass
        elif action_name == "stop":
            loco_client.StopMove()
        
        return {"success": True, "action": action_name}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/move")
def move_robot(direction: str, speed: float = 0.3):
    """控制机器人移动"""
    if speed > MAX_SPEED:
        return JSONResponse(
            {"error": f"速度 {speed} 超过最大安全速度 {MAX_SPEED}"},
            status_code=403
        )
    
    if not UNITREE_AVAILABLE or loco_client is None:
        return JSONResponse(
            {"error": "宇树 SDK 未初始化"},
            status_code=503
        )
    
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
            return JSONResponse(
                {"error": f"未知方向: {direction}"},
                status_code=400
            )
        return {"success": True, "direction": direction, "speed": speed}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 实时控制通道"""
    await websocket.accept()
    while True:
        try:
            data = await websocket.receive_text()
            command = json.loads(data)
            
            # 简单命令分发
            cmd_type = command.get("type")
            if cmd_type == "action":
                result = execute_action(command.get("name"))
            elif cmd_type == "move":
                result = move_robot(
                    command.get("direction"),
                    command.get("speed", 0.3)
                )
            elif cmd_type == "status":
                result = get_status()
            else:
                result = {"error": f"未知命令类型: {cmd_type}"}
            
            await websocket.send_text(json.dumps(result))
        except Exception as e:
            await websocket.send_text(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
