"""Shared storage in Redis, so games survive restarts and redeploys, and
several gunicorn workers can serve the same games.

    REDIS_URL       e.g. redis://localhost:6379/0 (the dev site uses /1).
                    Unset: an in-process stand-in (fakeredis), for running
                    locally and for tests; nothing survives a restart then.
    REDIS_PREFIX    key prefix (default "avalon")

Objects are stored pickled. Changes go through Store.update(), an optimistic
transaction: load, change, save only if nobody else saved in between,
otherwise retry on the fresh copy. So the change function must be safe to
run more than once and must not have side effects (publish events after).

Pickles depend on the classes' code. If a deploy changes stored classes in
a way old pickles can't load into, bump SCHEMA: stored games are then
ignored (they expire on their own) instead of crashing pages.
"""
from __future__ import annotations

import logging
import os
import pickle
from typing import Callable, TypeVar

import redis

SCHEMA = 1
SOCKET_TIMEOUT = 60      # seconds; must exceed events.HEARTBEAT_SECONDS
T = TypeVar("T")
log = logging.getLogger(__name__)


_client : redis.Redis | None = None


def connect() -> redis.Redis:
    """This process's Redis client (shared: it holds a connection pool)."""
    global _client
    if _client is None:
        url = os.environ.get("REDIS_URL")
        if url:
            # SSE streams each hold a connection while they wait for events
            # (events.HEARTBEAT_SECONDS at a time), so reads must be allowed
            # to take longer than that.
            _client = redis.Redis.from_url(url, health_check_interval=30,
                                           socket_timeout=SOCKET_TIMEOUT,
                                           socket_connect_timeout=5)
        else:
            import fakeredis
            log.warning("REDIS_URL is not set: using in-memory fakeredis (nothing is kept).")
            _client = fakeredis.FakeRedis()
    return _client


class Conflict(Exception):
    """Too many other changes to the same object at once."""


class Store:
    def __init__(self, client : redis.Redis, prefix : str | None = None):
        self.redis = client
        self.prefix = f"{prefix or os.environ.get('REDIS_PREFIX', 'avalon')}:v{SCHEMA}"

    def key(self, *parts : str) -> str:
        return ":".join((self.prefix, *parts))

    @staticmethod
    def _load(raw : bytes | None, key : str):
        if raw is None:
            return None
        try:
            return pickle.loads(raw)
        except Exception:
            log.exception("Can't load %s (stored by older code?); ignoring it.", key)
            return None

    def get(self, key : str):
        return self._load(self.redis.get(key), key)

    def get_many(self, keys : list[str]) -> list:
        if not keys:
            return []
        return [self._load(raw, k) for k, raw in zip(keys, self.redis.mget(keys))]

    def put(self, key : str, obj, ttl : int):
        self.redis.set(key, pickle.dumps(obj, pickle.HIGHEST_PROTOCOL), ex=ttl)

    def update(self, key : str, change : Callable[[object], T], ttl : int,
               attempts : int = 20) -> tuple[object, T]:
        """Apply change(obj) to the stored object and save it, atomically.
        Returns (changed object, change's result). Exceptions raised by
        change abort without saving. Raises KeyError if nothing is stored."""
        for _ in range(attempts):
            with self.redis.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    obj = self._load(pipe.get(key), key)
                    if obj is None:
                        raise KeyError(key)
                    result = change(obj)
                    pipe.multi()
                    pipe.set(key, pickle.dumps(obj, pickle.HIGHEST_PROTOCOL), ex=ttl)
                    pipe.execute()
                    return obj, result
                except redis.WatchError:
                    continue
        raise Conflict(key)
