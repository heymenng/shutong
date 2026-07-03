#!/bin/bash
# 伴读书童AI · 阿里云 ECS 部署脚本
# 在本机运行，把云端书童部署到阿里云服务器
#
# 用法:
#   ./deploy/deploy_to_aliyun.sh <服务器IP> <密钥路径> [域名]
#
# 示例:
#   ./deploy/deploy_to_aliyun.sh 114.55.9.27 /Users/lingjue/.ssh/bookboy-key.pem bookkidai.com
#
# 前置条件（阿里云控制台操作）:
#   1. 域名购买完成
#   2. DNS 添加 A 记录: @ → 服务器IP
#   3. 等待 DNS 生效（约1-10分钟）

set -e

SERVER_IP="${1:-114.55.9.27}"
KEY_PATH="${2:-/Users/lingjue/.ssh/bookboy-key.pem}"
DOMAIN="${3:-bookkidai.com}"
REMOTE_USER="root"
REMOTE_DIR="/opt/bookboy-cloud"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "$KEY_PATH" ]; then
    echo "[错误] 密钥文件不存在: $KEY_PATH"
    exit 1
fi

chmod 600 "$KEY_PATH"

SSH_CMD="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i $KEY_PATH $REMOTE_USER@$SERVER_IP"
SCP_CMD="scp -o StrictHostKeyChecking=no -i $KEY_PATH"

echo "=========================================="
echo "伴读书童AI · 阿里云部署"
echo "=========================================="
echo "服务器: $SERVER_IP"
echo "项目目录: $REMOTE_DIR"
echo "=========================================="

# 1. 在服务器上创建目录并安装基础环境
echo "[1/8] 初始化服务器环境..."
$SSH_CMD << 'REMOTE_SCRIPT'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-pip python3-venv git nginx rsync

# 创建项目目录
mkdir -p /opt/bookboy-cloud
mkdir -p /opt/bookboy-cloud/logs

# 安装 supervisor（用于守护进程）
apt-get install -y supervisor || true

# 创建运行用户（可选，更安全）
id -u bookboy >/dev/null 2>&1 || useradd -r -s /bin/false bookboy
REMOTE_SCRIPT

echo "[2/8] 上传云端书童文件..."
# 创建本地临时目录，只放需要上传的文件
LOCAL_TMP=$(mktemp -d)
trap "rm -rf $LOCAL_TMP" EXIT

cp "$PROJECT_ROOT/cloud_server.py" "$LOCAL_TMP/"
cp "$PROJECT_ROOT/云端师父控制台.html" "$LOCAL_TMP/"
cp "$PROJECT_ROOT/requirements_cloud.txt" "$LOCAL_TMP/requirements.txt"
cp "$PROJECT_ROOT/AGENTS.md" "$LOCAL_TMP/"

# 云端核心模块
mkdir -p "$LOCAL_TMP/书童程序/核心"
cp "$PROJECT_ROOT/书童程序/__init__.py" "$LOCAL_TMP/书童程序/"
cp "$PROJECT_ROOT/书童程序/配置.py" "$LOCAL_TMP/书童程序/"
cp "$PROJECT_ROOT/书童程序/核心/__init__.py" "$LOCAL_TMP/书童程序/核心/"
cp "$PROJECT_ROOT/书童程序/核心/语言模型.py" "$LOCAL_TMP/书童程序/核心/"
cp "$PROJECT_ROOT/书童程序/核心/语音模块.py" "$LOCAL_TMP/书童程序/核心/"
cp "$PROJECT_ROOT/书童程序/核心/讯飞语音.py" "$LOCAL_TMP/书童程序/核心/"
cp "$PROJECT_ROOT/书童程序/核心/讯飞超拟人语音.py" "$LOCAL_TMP/书童程序/核心/"

# 提示词
mkdir -p "$LOCAL_TMP/书童程序/数据/提示词"
cp "$PROJECT_ROOT/书童程序/数据/提示词/系统提示词整合版_可运行.md" "$LOCAL_TMP/书童程序/数据/提示词/"
cp "$PROJECT_ROOT/书童程序/数据/提示词/师父模式系统提示词.md" "$LOCAL_TMP/书童程序/数据/提示词/"

# 使用 rsync 上传
rsync -avz -e "ssh -o StrictHostKeyChecking=no -i $KEY_PATH" \
    "$LOCAL_TMP/" "$REMOTE_USER@$SERVER_IP:$REMOTE_DIR/"

echo "[3/8] 创建虚拟环境并安装依赖..."
$SSH_CMD << REMOTE_SCRIPT
set -e
cd $REMOTE_DIR
# 清理旧的虚拟环境（如果有）
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
REMOTE_SCRIPT

echo "[4/8] 配置环境变量..."
# 从本机配置读取密钥，如果读不到则提示输入
MASTER_KEY="${MASTER_KEY:-master-aliyun-$(openssl rand -hex 8)}"
DEFAULT_FAMILY_KEY="${DEFAULT_FAMILY_KEY:-family-aliyun-$(openssl rand -hex 8)}"

# 尝试从本机书童配置读取
LOCAL_DEEPSEEK=$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_ROOT'); from 书童程序.配置 import CONFIG; print(CONFIG.get('deepseek_api_key', ''))" 2>/dev/null || true)
LOCAL_XFYUN_APP_ID=$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_ROOT'); from 书童程序.配置 import CONFIG; print(CONFIG.get('xfyun_app_id', ''))" 2>/dev/null || true)
LOCAL_XFYUN_API_KEY=$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_ROOT'); from 书童程序.配置 import CONFIG; print(CONFIG.get('xfyun_api_key', ''))" 2>/dev/null || true)
LOCAL_XFYUN_API_SECRET=$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_ROOT'); from 书童程序.配置 import CONFIG; print(CONFIG.get('xfyun_api_secret', ''))" 2>/dev/null || true)

DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-$LOCAL_DEEPSEEK}"
XFYUN_APP_ID="${XFYUN_APP_ID:-$LOCAL_XFYUN_APP_ID}"
XFYUN_API_KEY="${XFYUN_API_KEY:-$LOCAL_XFYUN_API_KEY}"
XFYUN_API_SECRET="${XFYUN_API_SECRET:-$LOCAL_XFYUN_API_SECRET}"

if [ -z "$DEEPSEEK_API_KEY" ]; then
    read -s -p "请输入 DEEPSEEK_API_KEY: " DEEPSEEK_API_KEY
    echo
fi
if [ -z "$XFYUN_APP_ID" ]; then
    read -s -p "请输入 XFYUN_APP_ID: " XFYUN_APP_ID
    echo
fi
if [ -z "$XFYUN_API_KEY" ]; then
    read -s -p "请输入 XFYUN_API_KEY: " XFYUN_API_KEY
    echo
fi
if [ -z "$XFYUN_API_SECRET" ]; then
    read -s -p "请输入 XFYUN_API_SECRET: " XFYUN_API_SECRET
    echo
fi

$SSH_CMD << REMOTE_SCRIPT
cat > /opt/bookboy-cloud/.env << EOF
PORT=5000
HOST=127.0.0.1
MASTER_KEY=$MASTER_KEY
DEFAULT_FAMILY_KEY=$DEFAULT_FAMILY_KEY
DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY
XFYUN_APP_ID=$XFYUN_APP_ID
XFYUN_API_KEY=$XFYUN_API_KEY
XFYUN_API_SECRET=$XFYUN_API_SECRET
FLASK_SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')
EOF
REMOTE_SCRIPT

echo "[5/8] 配置 Supervisor 守护进程..."
$SSH_CMD << REMOTE_SCRIPT
cat > /etc/supervisor/conf.d/bookboy-cloud.conf << EOF
[program:bookboy-cloud]
directory=/opt/bookboy-cloud
command=/opt/bookboy-cloud/.venv/bin/python /opt/bookboy-cloud/cloud_server.py
user=root
autostart=true
autorestart=true
startretries=3
stderr_logfile=/opt/bookboy-cloud/logs/cloud.err.log
stdout_logfile=/opt/bookboy-cloud/logs/cloud.out.log
environment=PORT="5000",HOST="127.0.0.1"
EOF

supervisorctl reread
supervisorctl update
REMOTE_SCRIPT

DOMAIN="bookkidai.com"

echo "[6/8] 配置 SSL 证书（Let's Encrypt）..."
$SSH_CMD << REMOTE_SCRIPT
apt-get install -y certbot python3-certbot-nginx

# 先配临时 HTTP 站点让 certbot 验证域名
cat > /etc/nginx/sites-available/bookboy-cloud << 'EOF'
server {
    listen 80;
    server_name bookkidai.com;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
}
EOF

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/bookboy-cloud /etc/nginx/sites-enabled/bookboy-cloud
nginx -t && systemctl restart nginx

# 申请 SSL 证书（自动配置 HTTPS）
certbot --nginx -d bookkidai.com --non-interactive --agree-tos -m admin@bookkidai.com || true

# 如果 certbot 成功，nginx 已自动配好 HTTPS
# 如果 certbot 失败（域名DNS未生效），保留 HTTP 配置后续手动执行
nginx -t && systemctl restart nginx || true
REMOTE_SCRIPT

echo "[7/8] 启动云端书童服务..."
$SSH_CMD << REMOTE_SCRIPT
supervisorctl restart bookboy-cloud
sleep 3
supervisorctl status bookboy-cloud
REMOTE_SCRIPT

echo "[8/8] 测试服务..."
curl -s http://$SERVER_IP/health | python3 -m json.tool || true

echo "=========================================="
echo "部署完成！"
echo "=========================================="
echo "访问地址:"
echo "  首页:       http://$SERVER_IP/"
echo "  健康检查:   http://$SERVER_IP/health"
echo "  师父控制台: http://$SERVER_IP/master"
echo ""
echo "重要密钥（请妥善保存）:"
echo "  MASTER_KEY:        $MASTER_KEY"
echo "  DEFAULT_FAMILY_KEY: $DEFAULT_FAMILY_KEY"
echo ""
echo "家庭端连接地址（示例）:"
echo "  http://$SERVER_IP/family/default_family"
echo "=========================================="
