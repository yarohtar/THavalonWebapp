"""In-process event bus streamed to browsers with Server-Sent Events (SSE).

    events.publish(channel, 'new-game', {'any': 'json'})

Browsers subscribe with static/events.js. Each event gets an id; when a
connection drops (phone sleeps, tunnel hiccup) the browser reconnects with the
last id it saw and gets the missed events replayed. If they are no longer
buffered, or the server restarted in between, the browser receives `resync`
and reloads the page.

Everything lives in memory, so the app must run as ONE process (threads are
fine). That is already required, since games are kept in memory too.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from collections import deque

from flask import Blueprint, Response, request, stream_with_context

HEARTBEAT_SECONDS = 15   # Cloudflare drops connections idle for ~100s
BUFFER_SIZE = 100        # events kept per channel for replay
RETRY_MS = 2000          # how soon browsers reconnect

# Changes on every server start, so ids from before a restart are detected.
_BOOT = secrets.token_hex(4)


class _Channel:
    def __init__(self):
        self.events : deque[tuple[int, str, str]] = deque(maxlen=BUFFER_SIZE)
        self.next_id = 1
        self.last_used = time.time()


class EventBus:
    def __init__(self):
        self._cond = threading.Condition()
        self._channels : dict[str, _Channel] = {}

    def _channel(self, name : str) -> _Channel:
        ch = self._channels.get(name)
        if ch is None:
            ch = self._channels[name] = _Channel()
        ch.last_used = time.time()
        return ch

    def current_id(self, channel : str) -> str:
        """Id of the latest event, to render into a page so that its stream
        starts exactly where the page's content left off."""
        with self._cond:
            return f"{_BOOT}-{self._channel(channel).next_id - 1}"

    def publish(self, channel : str, event_type : str, data = None):
        payload = json.dumps(data)
        with self._cond:
            ch = self._channel(channel)
            ch.events.append((ch.next_id, event_type, payload))
            ch.next_id += 1
            self._cond.notify_all()

    def _parse_last_id(self, last_id : str | None) -> int | None:
        """Event number from a previous connection, or None if the id is
        missing or from before a server restart."""
        if not last_id:
            return None
        boot, _, n = last_id.partition('-')
        if boot != _BOOT or not n.isdigit():
            return None
        return int(n)

    def stream(self, channel : str, last_id : str | None):
        yield f"retry: {RETRY_MS}\n\n"
        with self._cond:
            ch = self._channel(channel)
            seen = self._parse_last_id(last_id)
            if last_id and (seen is None
                            or (ch.events and seen < ch.events[0][0] - 1)):
                # Missed events we can no longer replay.
                seen = None
                resync = True
            else:
                resync = False
            if seen is None:
                seen = ch.next_id - 1
        if resync:
            yield _format(f"{_BOOT}-{seen}", 'resync', 'null')

        while True:
            with self._cond:
                ch = self._channel(channel)
                pending = [e for e in ch.events if e[0] > seen]
                if not pending:
                    self._cond.wait(timeout=HEARTBEAT_SECONDS)
                    ch = self._channel(channel)
                    pending = [e for e in ch.events if e[0] > seen]
            if not pending:
                yield ": ping\n\n"
                continue
            for n, event_type, payload in pending:
                seen = n
                yield _format(f"{_BOOT}-{n}", event_type, payload)

    def prune(self, max_idle_seconds : float):
        cutoff = time.time() - max_idle_seconds
        with self._cond:
            for name in [n for n, ch in self._channels.items() if ch.last_used < cutoff]:
                del self._channels[name]


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
