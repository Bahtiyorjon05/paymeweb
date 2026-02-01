# gunicorn_config.py
import multiprocessing
import os

# Server socket - use PORT from environment if available (for Railway)
port = os.environ.get('PORT', '8000')
bind = f"0.0.0.0:{port}"
backlog = 2048

# Worker processes - use fewer workers for Railway's limited resources
workers = int(os.environ.get('WEB_CONCURRENCY', 1))
worker_class = "sync"
worker_connections = 1000
timeout = 120  # Increased timeout for Railway
keepalive = 2

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "-"  # Log to stdout for Railway
errorlog = "-"   # Log to stderr for Railway
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'paymebot_gunicorn'

# Server mechanics
preload_app = True
daemon = False
pidfile = '/tmp/paymebot.pid'
user = None
group = None
tmp_upload_dir = None

# SSL
keyfile = None
certfile = None