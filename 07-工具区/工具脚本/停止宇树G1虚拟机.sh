#!/bin/bash
# 书童AI - 宇树G1 虚拟机一键停止脚本

echo "停止桥接服务..."
multipass exec unitree-g1 -- sudo systemctl stop shutong-g1-bridge || true

echo "停止 unitree-g1 虚拟机..."
multipass stop unitree-g1

echo "完成"
