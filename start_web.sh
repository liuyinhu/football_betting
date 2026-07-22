#!/bin/bash
# ============================================================
#  中超赛前预测 Web 应用 一键启动脚本
#  - 后端：Flask (webapp/app.py)  端口 5001
#  - 前端：Vite + Vue3           端口 5173（/api 代理到后端）
# ============================================================
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# 若本机存在通过 n 安装的新版 Node（Vite 需 Node 18+），优先使用
if [ -x "$HOME/.n/bin/node" ]; then
  export PATH="$HOME/.n/bin:$PATH"
fi

echo "== 使用 Node: $(node -v 2>/dev/null || echo '未找到 node') =="

# ---- 实时数据源提示 ----
# 若设置了 API_FOOTBALL_KEY 环境变量，实时预测页将拉取真实进行中的中超比赛；
# 否则实时页会提示「未启用实时更新」。用法：
#   API_FOOTBALL_KEY=你的key ./start_web.sh
if [ -n "$API_FOOTBALL_KEY" ]; then
  echo "== 实时数据源: API-Football (已检测到 API_FOOTBALL_KEY) =="
else
  echo "== 实时数据源: 未启用 (未设置 API_FOOTBALL_KEY，实时页将提示未启用) =="
  echo "   如需开启实时预测: API_FOOTBALL_KEY=你的key ./start_web.sh"
fi

# ---- 启动后端 ----
# 默认用 Flask 开发服务器（方便调试）；设 PROD=1 时用 gunicorn 生产服务器
# （多进程/多线程，更稳更快，无「development server」警告）。
#   PROD=1 ./start_web.sh
if [ "$PROD" = "1" ]; then
  echo "== 启动后端 (Gunicorn 生产模式, :${PORT:-5001}) =="
  PORT="${PORT:-5001}" gunicorn -c gunicorn_conf.py webapp.app:app \
    > /tmp/csl_backend.log 2>&1 &
else
  echo "== 启动后端 (Flask 开发模式, :5001) =="
  PORT=5001 python3 -m webapp.app > /tmp/csl_backend.log 2>&1 &
fi
BACKEND_PID=$!
echo "   后端 PID=$BACKEND_PID  日志: /tmp/csl_backend.log"

# ---- 启动前端 ----
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  echo "   首次运行，安装前端依赖…"
  npm install
fi
if [ "$PROD" = "1" ]; then
  echo "== 构建并启动前端 (Vite 生产预览, :5173) =="
  npm run build
  npm run preview -- --host 0.0.0.0 --port 5173 > /tmp/csl_frontend.log 2>&1 &
else
  echo "== 启动前端 (Vite 开发模式, :5173) =="
  npm run dev > /tmp/csl_frontend.log 2>&1 &
fi
FRONTEND_PID=$!
echo "   前端 PID=$FRONTEND_PID  日志: /tmp/csl_frontend.log"

echo ""
echo "============================================================"
echo "  前端页面:  http://127.0.0.1:5173/"
echo "  后端 API:  http://127.0.0.1:5001/api/matches"
echo "  按 Ctrl+C 停止两个服务"
echo "============================================================"

trap "echo '正在停止…'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
