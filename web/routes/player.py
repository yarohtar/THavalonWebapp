"""Player pages: the start page (game list or your game), joining a lobby,
registering a name, and the "everything" page for after the game."""
from __future__ import annotations

import flask
from flask import Blueprint, g, request, session, url_for
from flask.views import MethodView

from web import panels
from web.lobbies import LOBBIES, LOBBIES_CHANNEL
from web.visitor import join, joined_lobby, safe_next

bp = Blueprint('player', __name__)


@bp.route("/")
def index():
    lobby = joined_lobby()
    if lobby is None:
        active = LOBBIES.active()
        if len(active) == 1:
            lobby = join(active[0])
        else:
            g.channel = LOBBIES_CHANNEL
            return flask.render_template('games.html', name = g.name, lobbies = active)

    g.channel = lobby.id
    if g.uuid not in lobby.current_game:
        return flask.render_template('wait.html',
                                     name = g.name,
                                     lobby = lobby,
                                     in_lobby = g.uuid in lobby,
                                     other_games = len(LOBBIES.active()) > 1)
    return panels.role_page(lobby.current_game, g.uuid)


@bp.route("/games")
def games():
    g.channel = LOBBIES_CHANNEL
    return flask.render_template('games.html', name = g.name,
                                 lobbies = LOBBIES.active(),
                                 current = joined_lobby())


@bp.route("/join-lobby", methods=["GET", "POST"])
@bp.route("/join/<lobby_id>", methods=["GET", "POST"])
def join_lobby(lobby_id = None):
    lobby = LOBBIES.get(lobby_id) if lobby_id else joined_lobby()
    if lobby is not None:
        join(lobby)
    return flask.redirect(url_for('player.index'))


class RegisterView(MethodView):
    def get(self):
        return flask.render_template('registration.html',
                                     next = safe_next(request.args.get('next')))

    def post(self):
        player_name = request.form['player'].strip()
        if len(player_name) == 0:
            return flask.redirect(url_for('player.register'))
        session['name'] = player_name
        g.name = player_name
        lobby = joined_lobby()
        if lobby is not None and g.uuid in lobby:
            join(lobby)  # update name in the lobby
        return flask.redirect(safe_next(request.form.get('next')) or url_for('player.index'))


bp.add_url_rule('/register', view_func=RegisterView.as_view('register'))


@bp.route("/donotread")
def everything():
    """Every player's role and info (for after the game)."""
    lobby = LOBBIES.hosted_by(g.uuid) or joined_lobby()
    if lobby is None:
        return flask.redirect(url_for('player.index'))
    current_game = lobby.current_game.snapshot()
    gareth_team = next((r.allegiance() for r in lobby.current_game.roles_dealt()
                        if str(r) == 'Gareth'), None)
    return flask.render_template('donotread.html',
                                 game = current_game,
                                 gareth_team = gareth_team,
                                 names = lobby.snapshot(),
                                 num_players = len(current_game))
