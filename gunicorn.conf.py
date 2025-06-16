"""
Gunicorn configuration file for DANDI SQL production deployment.
"""

import os
from pathlib import Path

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = 4
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "/var/log/dandi-sql/gunicorn-access.log"
errorlog = "/var/log/dandi-sql/gunicorn-error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "dandi-sql"

# Server mechanics
daemon = False
pidfile = "/var/run/dandi-sql/gunicorn.pid"
user = None
group = None
tmp_upload_dir = None

# SSL (if using HTTPS)
# keyfile = "/path/to/ssl/key.pem"
# certfile = "/path/to/ssl/cert.pem"

# Environment
raw_env = [
    "DJANGO_SETTINGS_MODULE=dandi_sql.settings_production",
]

# Preload application for better performance
preload_app = True

# Worker timeout for long-running sync operations
graceful_timeout = 60

def when_ready(server):
    server.log.info("Server is ready. Spawning workers")

def worker_int(worker):
    worker.log.info("worker received INT or QUIT signal")

def pre_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_worker_init(worker):
    worker.log.info("Worker initialized (pid: %s)", worker.pid)

def worker_abort(worker):
    worker.log.info("Worker received SIGABRT signal")
