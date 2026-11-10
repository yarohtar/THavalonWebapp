# Picked up automatically by gunicorn when started from this directory
# (the server's avalon.service does that). Options given on gunicorn's
# command line override these.
import os

# Games and live-update streams are kept in Redis (REDIS_URL, see store.py),
# so several worker processes can serve the same games. Without REDIS_URL
# everything is in one process's memory: then there must be ONE worker.
workers = int(os.environ.get("WEB_CONCURRENCY", 2 if os.environ.get("REDIS_URL") else 1))

# Each open browser page holds one thread for its live-update stream, so
# allow plenty of threads.
worker_class = "gthread"
threads = 100

# Live-update streams never finish by themselves; don't wait for them on
# restart (browsers reconnect automatically).
graceful_timeout = 2
