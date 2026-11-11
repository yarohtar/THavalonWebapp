"""Who is asking: this browser's lobby and game (from the session), for the
request being handled. `g.uuid` is the browser's id, `g.name` the player's
name (see app.py)."""
from __future__ import annotations

import flask
from flask import g, session

from web import events
from web.lobbies import LOBBIES, Lobby


def joined_lobby() -> Lobby | None:
    """The game this player has joined (or was last in)."""
    return LOBBIES.get(session.get('game_id'))


def join(lobby : Lobby) -> Lobby:
    """Join (or rename yourself in) a lobby. Returns the lobby as saved."""
    LOBBIES.leave_all(g.uuid, except_id = lobby.id)
    session['game_id'] = lobby.id
    if lobby.get(g.uuid) != g.name:
        uuid, name = g.uuid, g.name
        try:
            lobby, _ = LOBBIES.update(lobby.id, lambda l: l.__setitem__(uuid, name))
        except KeyError:
            return lobby
        events.publish(lobby.id, 'new-player')
    return lobby


def my_lobby() -> Lobby | None:
    """The lobby this host has open (kept alive by looking at it), or None."""
    lobby = LOBBIES.hosted_by(g.uuid)
    if lobby is None or g.get('view_as'):     # an admin looking doesn't keep it alive
        return lobby
    try:
        lobby, _ = LOBBIES.update(lobby.id, lambda l: None)
    except KeyError:                    # closed just now
        return None
    return lobby


def playing_lobby() -> Lobby:
    """The lobby whose game this player is in; 404 if none."""
    lobby = joined_lobby()
    if lobby is None or g.uuid not in lobby.current_game \
            or lobby.current_game.controller is None:
        flask.abort(404)
    return lobby


def hosted_game_lobby() -> Lobby:
    """The lobby this host is running a game in; 404 if none."""
    lobby = LOBBIES.hosted_by(g.uuid)
    if lobby is None or lobby.current_game.controller is None:
        flask.abort(404)
    return lobby


def viewer_game() -> Lobby | None:
    """The game this browser is playing in or hosting right now, if any."""
    lobby = LOBBIES.hosted_by(g.uuid)
    if lobby is not None and lobby.current_game.controller is not None:
        return lobby
    lobby = joined_lobby()
    if lobby is not None and g.uuid in lobby.current_game \
            and lobby.current_game.controller is not None:
        return lobby
    return None


def safe_next(target : str | None) -> str | None:
    """A ?next= target, only if it is a page on this site."""
    if target and target.startswith('/') and not target.startswith('//'):
        return target
    return None
