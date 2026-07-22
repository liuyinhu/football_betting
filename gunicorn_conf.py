"""Gunicorn 生产服务器配置。

用法：
    gunicorn -c gunicorn_conf.py webapp.app:app

各项均可用环境变量覆盖，便于不同机器调优：
    PORT               监听端口（默认 5001）
    GUNICORN_WORKERS   worker 进程数（默认 = CPU 核数 × 2 + 1）
    GUNICORN_THREADS   每个 worker 的线程数（默认 2）
    GUNICORN_TIMEOUT   请求超时秒数（默认 60；实时接口会外呼 API，放宽些）
"""
import multiprocessing
import os

# 监听地址：0.0.0.0 允许通过外网/域名访问
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"

# worker 进程数：默认按 CPU 核数计算（官方推荐 2*核数+1）
workers = int(os.environ.get(
    "GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))

# 每个 worker 内再开线程，进一步提升 IO 并发（本服务有外呼 API 的 IO 等待）
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
worker_class = "gthread"

# 请求超时：实时接口会调用 API-Football，适当放宽
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))

# 优雅重启 / 连接队列
graceful_timeout = 30
keepalive = 5

# 处理一定请求数后重启 worker，规避潜在内存泄漏
max_requests = 1000
max_requests_jitter = 100

# 日志输出到标准流（由 start_web.sh 重定向到日志文件）
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
