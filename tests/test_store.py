"""Tests for keeping games and events in Redis (store.py, events.py).
Run: python -m pytest      (uses fakeredis; set TEST_REDIS_URL to also use a real server)"""
import os
import sys
import threading

import pytest
import fakeredis
import redis

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import events
import store
from store import Store
from thavalon.roles import roles_named


@pytest.fixture(params=["fake"] + (["real"] if os.environ.get("TEST_REDIS_URL") else []))
def server(request):
    """Returns a factory for clients that all talk to the same Redis,
    like separate gunicorn workers (or a restarted app) would."""
    if request.param == "real":
        url = os.environ["TEST_REDIS_URL"]
        redis.Redis.from_url(url).flushdb()
        yield lambda: redis.Redis.from_url(url)
        redis.Redis.from_url(url).flushdb()
    else:
        shared = fakeredis.FakeServer()
        yield lambda: fakeredis.FakeRedis(server=shared)


class Counter:
    def __init__(self):
        self.n = 0
        self.seen = []


def test_objects_survive_a_new_connection(server):
    a = Store(server(), "t")
    a.put(a.key("x"), Counter(), ttl=60)
    a.update(a.key("x"), lambda c: setattr(c, "n", 5), ttl=60)
    b = Store(server(), "t")                 # e.g. after a redeploy
    assert b.get(b.key("x")).n == 5
    assert b.redis.ttl(b.key("x")) > 0


def test_concurrent_updates_are_not_lost(server):
    s = Store(server(), "t")
    s.put(s.key("c"), Counter(), ttl=60)

    def bump(i):
        def change(c):
            c.n += 1
            c.seen.append(i)
        Store(server(), "t").update(s.key("c"), change, ttl=60, attempts=200)

    threads = [threading.Thread(target=bump, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    c = s.get(s.key("c"))
    assert c.n == 20 and sorted(c.seen) == list(range(20))


def test_failed_change_is_not_saved(server):
    s = Store(server(), "t")
    s.put(s.key("c"), Counter(), ttl=60)

    def change(c):
        c.n = 99
        raise ValueError("rule broken")
    with pytest.raises(ValueError):
        s.update(s.key("c"), change, ttl=60)
    assert s.get(s.key("c")).n == 0
    with pytest.raises(KeyError):
        s.update(s.key("missing"), lambda c: None, ttl=60)


def test_unloadable_object_is_ignored(server):
    s = Store(server(), "t")
    s.redis.set(s.key("bad"), b"not a pickle")
    assert s.get(s.key("bad")) is None


def read(gen, n):
    return [next(gen) for _ in range(n)]


def test_events_reach_other_workers_and_replay(server):
    a = events.EventBus(server(), "t")
    b = events.EventBus(server(), "t")
    start = a.current_id("ch")
    assert start == "0-0"
    a.publish("ch", "game-update", {"x": 1})
    a.publish("ch", "new-game", None)
    # Another worker, reconnecting from before both events, gets both.
    out = read(b.stream("ch", start), 3)
    assert out[0].startswith("retry:")
    assert "event: game-update" in out[1] and 'data: {"x": 1}' in out[1]
    assert "event: new-game" in out[2]
    # From the latest id: nothing missed, only new events.
    gen = b.stream("ch", b.current_id("ch"))
    next(gen)
    a.publish("ch", "game-update", None)
    assert "event: game-update" in next(gen)


def test_events_resync_when_id_unknown_or_trimmed(server, monkeypatch):
    a = events.EventBus(server(), "t")
    out = read(a.stream("ch", "b8ee7440-3"), 2)       # an id from the old in-memory bus
    assert "event: resync" in out[1]
    monkeypatch.setattr(events, "BUFFER_SIZE", 5)
    first = None
    for i in range(8):
        a.publish("ch", "game-update", i)
        first = first or a.current_id("ch")
    out = read(a.stream("ch", first), 2)
    assert "event: resync" in out[1]


def test_lobbies_survive_restart_of_the_app(server, monkeypatch):
    """A game in progress is still there for a fresh Lobbies (a new process)."""
    import webapp
    lobbies = webapp.Lobbies(Store(server(), "t"))
    with webapp.app.test_request_context():
        lobby, created = lobbies.open("host-1", "Camelot")
        assert created
        for i, name in enumerate(["Ann", "Bob", "Cat", "Dan", "Eve"]):
            lobbies.update(lobby.id, lambda l: l.__setitem__(f"u{i}", name))
        settings = webapp.GameSettings()
        lobbies.update(lobby.id, lambda l: l.restart_game(
            roles_named(["Merlin", "Percival", "Morgana", "Mordred"]),
            settings))
        again = webapp.Lobbies(Store(server(), "t"))
        found = again.hosted_by("host-1")
        assert found.id == lobby.id and len(found) == 5
        assert found.current_game.controller.state.phase.value == "first_round_proposing"
        assert [l.name for l in again.active()] == ["Camelot"]
        # Still the same lobby when the host comes back.
        assert again.open("host-1")[0].id == lobby.id


def test_redis_reads_outlast_the_sse_wait(monkeypatch):
    """Live-update streams block in XREAD for HEARTBEAT_SECONDS; the client's
    read timeout must be longer, or every quiet stream errors out."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(store, "_client", None)
    kwargs = store.connect().connection_pool.connection_kwargs
    monkeypatch.setattr(store, "_client", None)
    assert kwargs["socket_timeout"] > events.HEARTBEAT_SECONDS
