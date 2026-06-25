#!/bin/bash
# 书童AI - 宇树G1 虚拟机一键启动脚本

set -e

echo "启动 unitree-g1 虚拟机..."
multipass start unitree-g1

echo "等待虚拟机启动..."
sleep 3

echo "检查桥接服务状态..."
multipass exec unitree-g1 -- sudo systemctl is-active shutong-g1-bridge || multipass exec unitree-g1 -- sudo systemctl start shutong-g1-bridge

echo "虚拟机信息:"
multipass info unitree-g1

echo ""
echo "桥接服务状态:"
IP=$(multipass info unitree-g1 --format json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['info']['unitree-g1']['ipv4'][0])")
curl -s http://$IP:8080/ | python3 -m json.tool
echo ""
echo "完成。虚拟机 IP: $IP"
