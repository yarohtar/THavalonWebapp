"""A player's live game: fetching panels and state, acting, and voting in
the host's votes. All answer with JSON."""
from __future__ import annotations

import flask
from flask import Blueprint, g, request

from thavalon import RuleError
from web import panels
from web.store import Conflict
from web.routes.common import change_game
from web.visitor import playing_lobby

bp = Blueprint('play', __name__, url_prefix='/game')


def action_params(action : str, form) -> dict:
    """Form fields -> GameController.act() parameters."""
    params = {}
    if action in ('propose', 'propose_first_round'):
        params['team'] = form.getlist('team')
    if action == 'assassinate':
        params['targets'] = form.getlist('targets')
    for key in ('proposer', 'next_proposer', 'replaced', 'card', 'kind'):
        if key in form:
            params[key] = form[key]
    if 'target' in form:
        params['target'] = form['target'] or None
    for key in ('approve', 'remove'):
        if key in form:
            params[key] = form[key] == '1'
    return params


@bp.route("/panels", endpoint="panels")
def panels_json():
    lobby = playing_lobby()
    return flask.jsonify(panels.panels(lobby.current_game, g.uuid))


@bp.route("/state")
def state():
    """This player's view of the game as JSON (what their page shows)."""
    lobby = playing_lobby()
    game = lobby.current_game
    view = game.controller.view(game.names[g.uuid])
    host_vote = game.host_vote_view(g.uuid)
    return flask.jsonify(game_id = f'{lobby.id}:{game.game_number}',
                         host_vote = host_vote, **view)


@bp.route("/action", methods=["POST"])
def action():
    lobby = playing_lobby()
    name = request.form.get('action', '')
    params = action_params(name, request.form)
    uuid = g.uuid
    return change_game(lobby, lambda game: game.act(uuid, name, params),
                       lambda game: panels.panels(game, uuid),
                       errors = (RuleError, KeyError, ValueError, Conflict))


@bp.route("/host-vote", methods=["POST"])
def host_vote():
    """A player votes in the vote the host started."""
    lobby = playing_lobby()
    uuid, vote_id = g.uuid, request.form.get('vote', type=int)
    choice = request.form.get('choice', '')
    return change_game(lobby, lambda game: game.cast_host_vote(uuid, vote_id, choice),
                       lambda game: panels.panels(game, uuid))
