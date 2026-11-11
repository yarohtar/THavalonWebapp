"""Lobbies: open games, who has joined them, kept in Redis.

    LOBBIES.get(id) / active() / hosted_by(host)   copies of stored lobbies
    LOBBIES.update(id, change)                     change one atomically

`change` may run several times (retries on conflict), so it must have no
side effects: publish events after update() returns.
"""
from __future__ import annotations

import random
import secrets

from flask import current_app

from thavalon.roles import Role
from thavalon.ruleset import RuleSet
from web import events, store
from web.games import AvalonGame, GameSettings
from web.store import Store

# Channel for "a game was opened" events, for players not in any game yet.
LOBBIES_CHANNEL = 'lobbies'

GAME_NAMES = [
    "Camelot", "Tintagel", "Avalon", "Caerleon", "Lyonesse", "Broceliande",
    "Joyous Gard", "Corbenic", "Astolat", "Logres", "Glastonbury",
    "The Round Table", "The Siege Perilous", "The Green Chapel",
    "The Lady of the Lake", "Excalibur", "The Holy Grail", "The Perilous Bed",
]


def random_game_name(taken : set[str]) -> str:
    free = [n for n in GAME_NAMES if n not in taken]
    if free:
        return random.choice(free)
    return f"{random.choice(GAME_NAMES)} {random.randint(2, 99)}"


class Lobby:
    """An open game: who has joined (uuid -> name), and the game being
    played. Plain data, stored in Redis by Lobbies."""
    max_capacity : int = 10
    current_game : AvalonGame

    def __init__(self, host_uuid : str, name : str):
        self.id = secrets.token_urlsafe(6)
        self.host_uuid = host_uuid
        self.name = name
        self._players : dict[str, str] = {}
        self.current_game = AvalonGame()

    def __setitem__(self, uuid : str, name : str):
        """Join or rename. Ignored if the name is taken or the lobby is full."""
        if uuid in self._players:
            self._players[uuid] = name
            return
        if name in self._players.values():
            return
        if len(self._players) >= self.max_capacity:
            return
        self._players[uuid] = name

    def get(self, uuid : str, default = None):
        return self._players.get(uuid, default)

    def pop(self, uuid : str):
        self._players.pop(uuid, None)

    def snapshot(self):
        return dict(self._players)

    def __len__(self):
        return len(self._players)

    def __contains__(self, uuid : str):
        return uuid in self._players

    def restart_game(self, roles : list[Role], settings : GameSettings,
                     ruleset : RuleSet | None = None):
        self.current_game.restart(roles, self._players, settings, ruleset)


class Lobbies:
    """All open games, kept in Redis (see store.py). Each host (browser
    session) has at most one. A lobby untouched for 12 hours expires.

    Objects returned by get() and friends are copies: change a lobby with
    update(), which saves the change atomically."""
    max_idle_seconds = 12 * 60 * 60

    def __init__(self, store : Store):
        self.store = store
        self._index = store.key('lobbies')          # set of lobby ids

    def _key(self, lobby_id : str) -> str:
        return self.store.key('lobby', lobby_id)

    def _host_key(self, host_uuid : str) -> str:
        return self.store.key('host', host_uuid)

    def get(self, lobby_id : str | None) -> Lobby | None:
        return self.store.get(self._key(lobby_id)) if lobby_id else None

    def update(self, lobby_id : str, change) -> tuple[Lobby, object]:
        """Run change(lobby) and save. Returns (lobby, change's result);
        KeyError if the lobby is gone."""
        lobby, result = self.store.update(self._key(lobby_id), change,
                                          ttl = self.max_idle_seconds)
        self.store.redis.expire(self._host_key(lobby.host_uuid), self.max_idle_seconds)
        return lobby, result

    def add(self, lobby : Lobby):
        """Save a lobby made elsewhere, replacing any with the same id (dev scenarios)."""
        r = self.store.redis
        self.store.put(self._key(lobby.id), lobby, self.max_idle_seconds)
        r.set(self._host_key(lobby.host_uuid), lobby.id, ex = self.max_idle_seconds)
        r.sadd(self._index, lobby.id)

    def hosted_by(self, host_uuid : str) -> Lobby | None:
        lobby_id = self.store.redis.get(self._host_key(host_uuid))
        return self.get(lobby_id.decode()) if lobby_id else None

    def open(self, host_uuid : str, name : str | None = None) -> tuple[Lobby, bool]:
        """The host's lobby, created if needed. Returns (lobby, created).
        A new lobby is called `name`, or a random unused Avalon name."""
        lobby = self.hosted_by(host_uuid)
        if lobby is not None:
            lobby, _ = self.update(lobby.id, lambda l: None)     # keeps it alive
            return lobby, False
        taken = {l.name for l in self.active()}
        if not name or name in taken:
            name = random_game_name(taken)
        lobby = Lobby(host_uuid, name)
        for i in range(current_app.config.get('DEV_FAKE_PLAYERS', 0)):
            lobby[f'fake{i}'] = f'p{i}'
        r = self.store.redis
        # Two requests from the same host at once: only one creates the lobby.
        if not r.set(self._host_key(host_uuid), lobby.id, nx = True,
                     ex = self.max_idle_seconds):
            return self.open(host_uuid, name)
        self.store.put(self._key(lobby.id), lobby, self.max_idle_seconds)
        r.sadd(self._index, lobby.id)
        return lobby, True

    def active(self) -> list[Lobby]:
        ids = sorted(i.decode() for i in self.store.redis.smembers(self._index))
        lobbies = self.store.get_many([self._key(i) for i in ids])
        gone = [i for i, l in zip(ids, lobbies) if l is None]
        if gone:
            self.store.redis.srem(self._index, *gone)
        return sorted((l for l in lobbies if l is not None), key=lambda l: l.name.casefold())

    def close(self, lobby_id : str) -> Lobby | None:
        """Remove a lobby now (instead of waiting for it to expire). Returns
        it as it was, or None if it was already gone. A change to it that is
        under way then fails (KeyError), as for an expired lobby."""
        lobby = self.get(lobby_id)
        r = self.store.redis
        r.delete(self._key(lobby_id))
        r.srem(self._index, lobby_id)
        if lobby is not None:
            host_key = self._host_key(lobby.host_uuid)
            current = r.get(host_key)
            if current is not None and current.decode() == lobby_id:
                r.delete(host_key)
        return lobby

    def idle_seconds(self, lobby_ids : list[str]) -> dict[str, int | None]:
        """How long ago each lobby was last changed (from its time to live)."""
        pipe = self.store.redis.pipeline()
        for i in lobby_ids:
            pipe.ttl(self._key(i))
        return {i: (self.max_idle_seconds - ttl if ttl is not None and ttl >= 0 else None)
                for i, ttl in zip(lobby_ids, pipe.execute())}

    def leave_all(self, uuid : str, except_id : str | None = None):
        for lobby in self.active():
            if lobby.id != except_id and uuid in lobby:
                self.update(lobby.id, lambda l: l.pop(uuid))


LOBBIES = Lobbies(Store(store.connect()))


def close_lobby(lobby_id : str) -> Lobby | None:
    """Close a lobby now and tell open pages: players' pages reload (and find
    the game gone), game lists and host pages refresh."""
    lobby = LOBBIES.close(lobby_id)
    if lobby is not None:
        events.publish(lobby.id, 'new-game')
        events.publish(lobby.id, 'new-player')
        events.publish(LOBBIES_CHANNEL, 'new-lobby')
    return lobby
