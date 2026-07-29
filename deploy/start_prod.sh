#!/bin/bash
# ============================================================
#  生产环境一键部署脚本
#
#  用法：
#    chmod +x deploy/start_prod.sh
#    ./deploy/start_prod.sh
#
#  前提：
#    - 服务器已安装 nginx / python3 / pip
#    - 已完成域名解析和 ICP 备案
#    - deploy/.env 已配置好 API_FOOTBALL_KEY 等变量
# ============================================================
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==== 中超预测后端 · 生产部署 ===="
echo ""

# ---- 1. 加载环境变量 ----
ENV_FILE="$ROOT/deploy/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ 缺少 $ENV_FILE"
    echo "   请先复制模板：cp deploy/.env.template deploy/.env"
    echo "   然后填写 API_FOOTBALL_KEY 等配置。"
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

echo "✅ 环境变量已加载"

# ---- 2. Python 虚拟环境 ----
VENV="$ROOT/venv"
if [ ! -d "$VENV" ]; then
    echo "📦 创建 Python 虚拟环境…"
    python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"

echo "📦 安装依赖…"
pip install -q -r requirements.txt

# ---- 3. 训练模型（如果还没训练过） ----
STRENGTH_FILE="$ROOT/data/csl_strength.json"
if [ ! -f "$STRENGTH_FILE" ]; then
    echo "🏋️ 首次部署，训练 Dixon-Coles 模型…"
    python3 -m data.train_strength
    echo "✅ 模型训练完成"
else
    echo "✅ 模型已存在，跳过训练（如需重训：python3 -m data.train_strength）"
fi

# ---- 4. Nginx 配置 ----
NGINX_CONF="$ROOT/deploy/nginx/csl-api.conf"
SITES_AVAILABLE="/etc/nginx/sites-available/csl-api"
SITES_ENABLED="/etc/nginx/sites-enabled/csl-api"

if [ ! -f "$SITES_AVAILABLE" ]; then
    echo ""
    echo "⚠️  Nginx 配置尚未安装到系统目录。"
    echo "   请手动执行以下命令（需要 sudo）："
    echo ""
    echo "   sudo cp $NGINX_CONF $SITES_AVAILABLE"
    echo "   sudo ln -sf $SITES_AVAILABLE $SITES_ENABLED"
    echo ""
    echo "   然后编辑 $SITES_AVAILABLE，把 'api.your-domain.com' 改成你的真实域名。"
    echo "   再执行证书申请："
    echo ""
    echo "   sudo certbot --nginx -d 你的域名"
    echo "   sudo nginx -t && sudo systemctl reload nginx"
    echo ""
fi

# ---- 5. systemd 服务 ----
SERVICE_FILE="/etc/systemd/system/csl-api.service"
SERVICE_SRC="$ROOT/deploy/systemd/csl-api.service"

if [ ! -f "$SERVICE_FILE" ]; then
    echo ""
    echo "⚠️  systemd 服务尚未安装。"
    echo "   请手动执行以下命令（需要 sudo）："
    echo ""
    echo "   # 先编辑 $SERVICE_SRC 中的 User/Group/WorkingDirectory/路径"
    echo "   sudo cp $SERVICE_SRC $SERVICE_FILE"
    echo "   sudo systemctl daemon-reload"
    echo "   sudo systemctl enable csl-api"
    echo "   sudo systemctl start csl-api"
    echo ""
fi

# ---- 6. 检查后端是否运行 ----
if systemctl is-active --quiet csl-api 2>/dev/null; then
    echo "✅ 后端服务已在运行 (systemd: csl-api)"
    echo "   重启：sudo systemctl restart csl-api"
    echo "   日志：journalctl -u csl-api -f"
else
    echo "🚀 启动后端（直接模式，适用于无 systemd 的环境）…"
    PORT="${PORT:-5001}" \
    API_FOOTBALL_KEY="${API_FOOTBALL_KEY}" \
    LIVE_SOURCE="${LIVE_SOURCE}" \
    GUNICORN_WORKERS="${GUNICORN_WORKERS:-4}" \
    "$VENV/bin/gunicorn" \
        --bind 127.0.0.1:5001 \
        -c gunicorn_conf.py \
        --daemon \
        --pid /tmp/csl-api.pid \
        --access-logfile /var/log/csl-api-access.log \
        --error-logfile /var/log/csl-api-error.log \
        webapp.app:app
    echo "✅ 后端已启动 (PID: $(cat /tmp/csl-api.pid 2>/dev/null || echo '?'))"
    echo "   监听：127.0.0.1:5001（由 Nginx 代理为 HTTPS）"
fi

echo ""
echo "==== 部署状态检查 ===="

# 检查后端是否响应
if curl -sf http://127.0.0.1:5001/api/health > /dev/null 2>&1; then
    echo "✅ 后端健康检查通过: http://127.0.0.1:5001/api/health"
else
    echo "❌ 后端未响应，请检查日志"
fi

# 检查 Nginx
if curl -sf https://localhost/api/health > /dev/null 2>&1; then
    echo "✅ Nginx HTTPS 代理正常"
else
    echo "⚠️  Nginx HTTPS 代理未就绪（可能尚未配置 SSL 证书）"
fi

echo ""
echo "==== 下一步 ===="
echo "1. 确认 Nginx + SSL 已配置（HTTPS 能访问 /api/health）"
echo "2. 修改 miniprogram/src/common/config.js 的 PROD_BASE 为你的 HTTPS 域名"
echo "3. 在微信后台添加 request 合法域名"
echo "4. npm run build:mp-weixin && 微信开发者工具上传"
