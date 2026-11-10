"""Event bus streamed to browsers with Server-Sent Events (SSE), kept in
Redis Streams so that every gunicorn worker sees every event and nothing is
lost over a restart or redeploy.

    events.publish(channel, 'new-game', {'any': 'json'})

Browsers subscribe with static/events.js. Each event's id is its Redis
stream id; when a connection drops (phone sleeps, tunnel hiccup, redeploy)
the browser reconnects with the last id it saw and gets the missed events
replayed. If they are no longer kept (only the latest BUFFER_SIZE are), or
the id is unknown, the browser receives `resync` and reloads the page.
"""
from __future__ import annotations

import json

from flask import Blueprint, Response, request, stream_with_context

import store

HEARTBEAT_SECONDS = 15   # Cloudflare drops connections idle for ~100s
BUFFER_SIZE = 100        # events kept per channel for replay
RETRY_MS = 2000          # how soon browsers reconnect
CHANNEL_TTL = 12 * 60 * 60   # a channel nobody publishes to expires


def _parse_id(event_id : str | None) -> tuple[int, int] | None:
    """A Redis stream id 'ms-seq', or None for anything else (such as ids
    from before events lived in Redis)."""
    if not event_id:
        return None
    ms, _, seq = event_id.partition('-')
    if not (ms.isdigit() and seq.isdigit()):
        return None
    return int(ms), int(seq)


class EventBus:
    def __init__(self, client = None, prefix : str | None = None):
        self._client = client
        self._prefix = prefix

    @property
    def redis(self):
        if self._client is None:
            self._client = store.connect()
        return self._client

    def _key(self, channel : str) -> str:
        return store.Store(self.redis, self._prefix).key('events', channel)

    def current_id(self, channel : str) -> str:
        """Id of the latest event, to render into a page so that its stream
        starts exactly where the page's content left off."""
        last = self.redis.xrevrange(self._key(channel), count=1)
        return last[0][0].decode() if last else '0-0'

    def publish(self, channel : str, event_type : str, data = None):
        key = self._key(channel)
        with self.redis.pipeline() as pipe:
            pipe.xadd(key, {'type': event_type, 'data': json.dumps(data)},
                      maxlen=BUFFER_SIZE, approximate=False)
            pipe.expire(key, CHANNEL_TTL)
            pipe.execute()

    def _missed_some(self, key : str, seen : tuple[int, int]) -> bool:
        """Were events after `seen` already trimmed away?"""
        if self.redis.xlen(key) < BUFFER_SIZE:
            return False
        first = self.redis.xrange(key, count=1)
        return bool(first) and _parse_id(first[0][0].decode()) > seen

    def stream(self, channel : str, last_id : str | None):
        yield f"retry: {RETRY_MS}\n\n"
        key = self._key(channel)
        seen = _parse_id(last_id)
        if last_id and (seen is None or self._missed_some(key, seen)):
            # Missed events we can no longer replay.
            cursor = self.current_id(channel)
            yield _format(cursor, 'resync', 'null')
        elif seen is None:
            cursor = self.current_id(channel)
        else:
            cursor = last_id

        while True:
            found = self.redis.xread({key: cursor}, count=BUFFER_SIZE,
                                     block=HEARTBEAT_SECONDS * 1000)
            if not found:
                yield ": ping\n\n"
                continue
            for event_id, fields in found[0][1]:
                cursor = event_id.decode()
                yield _format(cursor, fields[b'type'].decode(), fields[b'data'].decode())


def _format(event_id : str, event_type : str, payload : str) -> str:
    return f"id: {event_id}\nevent: {event_type}\ndata: {payload}\n\n"


bus = EventBus()
publish = bus.publish

blueprint = Blueprint('events', __name__)


@blueprint.route('/events/<channel>')
def stream(channel):
    last_id = request.headers.get('Last-Event-ID') or request.args.get('last_id')
    return Response(stream_with_context(bus.stream(channel, last_id)),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache, no-transform',
                             'X-Accel-Buffering': 'no'})
