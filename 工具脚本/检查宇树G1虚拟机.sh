#!/bin/bash
# 书童AI - 宇树G1 虚拟机状态检查脚本

echo "虚拟机状态:"
multipass info unitree-g1

echo ""
echo "桥接服务状态:"
multipass exec unitree-g1 -- sudo systemctl status shutong-g1-bridge --no-pager || true

echo ""
echo "HTTP 测试:"
IP=$(multipass info unitree-g1 --format json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['info']['unitree-g1']['ipv4'][0])" 2>/dev/null || echo "")
if [ -n "$IP" ]; then
    curl -s http://$IP:8080/ | python3 -m json.tool || echo "桥接服务未响应"
else
    echo "虚拟机未运行"
fi
