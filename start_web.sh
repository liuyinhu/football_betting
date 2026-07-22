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

# ---- 启动后端 ----
echo "== 启动后端 (Flask, :5001) =="
PORT=5001 python3 -m webapp.app > /tmp/csl_backend.log 2>&1 &
BACKEND_PID=$!
echo "   后端 PID=$BACKEND_PID  日志: /tmp/csl_backend.log"

# ---- 启动前端 ----
echo "== 启动前端 (Vite, :5173) =="
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  echo "   首次运行，安装前端依赖…"
  npm install
fi
npm run dev > /tmp/csl_frontend.log 2>&1 &
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
