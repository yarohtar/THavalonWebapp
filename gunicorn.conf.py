# Picked up automatically by gunicorn when started from this directory
# (the server's avalon.service does that).
#
# Games and live-update streams are kept in memory, so there must be exactly
# ONE worker process. Each open browser page holds one thread for its
# live-update stream, so allow plenty of threads.
workers = 1
worker_class = "gthread"
threads = 100

# Live-update streams never finish by themselves; don't wait for them on
# restart (browsers reconnect automatically).
graceful_timeout = 2
