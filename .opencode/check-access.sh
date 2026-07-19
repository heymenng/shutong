#!/bin/bash
# 开口问师父要凭证/权限之前，先跑这个脚本自检。
# 只检查文件存在性和连接性，不打印任何密钥内容。

set -e

echo "=== 本地 SSH 部署密钥 ==="
KEY="/Users/lingjue/.ssh/id_rsa_bookboy_deploy"
if [ -f "$KEY" ]; then
    echo "[有] $KEY"
else
    echo "[无] $KEY"
fi
if [ -f "${KEY}.pub" ]; then
    echo "[有] ${KEY}.pub"
else
    echo "[无] ${KEY}.pub"
fi

echo ""
echo "=== 阿里云 CLI 配置 ==="
ALI_CFG="/Users/lingjue/.aliyun/config.json"
if [ -f "$ALI_CFG" ]; then
    echo "[有] $ALI_CFG"
    # 只显示profile名和region，不显示密钥
    /Users/lingjue/Documents/shutong/.venv/bin/python - <<'PY'
import json, os
try:
    with open(os.path.expanduser('~/.aliyun/config.json')) as f:
        cfg = json.load(f)
    print(f"当前profile: {cfg.get('current', 'N/A')}")
    for p in cfg.get('profiles', []):
        print(f"  - {p.get('name')}: region={p.get('region_id')}, mode={p.get('mode')}")
except Exception as e:
    print(f"读取失败: {e}")
PY
else
    echo "[无] $ALI_CFG"
fi

echo ""
echo "=== 服务器 SSH 连通性 ==="
if [ -f "$KEY" ]; then
    ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no -i "$KEY" bookboy@114.55.9.27 "echo '[通] 114.55.9.27 bookboy SSH 正常'" 2>&1 || echo "[不通] 114.55.9.27 bookboy SSH"
else
    echo "[跳过] 无密钥，不测SSH"
fi

echo ""
echo "=== 生产服务状态 ==="
if [ -f "$KEY" ]; then
    ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no -i "$KEY" bookboy@114.55.9.27 "sudo supervisorctl status bookboy-cloud" 2>&1 || echo "[失败] 无法获取supervisor状态"
else
    echo "[跳过] 无密钥，不查服务状态"
fi

echo ""
echo "=== 结论 ==="
echo "如果上面显示 [有] 和 [通]，就不要再问师父要密钥/权限。"
