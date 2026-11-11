"""Helpers shared by the routes that change a game."""
from __future__ import annotations

import flask

from thavalon import RuleError
from web import events
from web.lobbies import LOBBIES, Lobby
from web.store import Conflict


def change_game(lobby : Lobby, change, render, errors = (RuleError, KeyError, Conflict)):
    """Apply change(game) to the lobby's game and tell everyone; answer with
    render(game) as JSON, or a readable error (400)."""
    try:
        lobby, _ = LOBBIES.update(lobby.id, lambda l: change(l.current_game))
    except errors as e:
        message = e.args[0] if isinstance(e, RuleError) else "That didn't work, try again."
        return flask.jsonify(error = message), 400
    events.publish(lobby.id, 'game-update')
    return flask.jsonify(render(lobby.current_game))
