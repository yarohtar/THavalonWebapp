"""The host's pages: create a lobby, choose roles and rules, start, run and
close the game. A browser hosts at most one lobby."""
from __future__ import annotations

import flask
from flask import Blueprint, g, request, session, url_for
from flask.views import MethodView

from thavalon.dealing import DEFAULT_TEAM_SIZES, default_num_evils, num_extras
from thavalon.roles import balin, gareth, roles_named
from thavalon.ruleset import SETTINGS
from web import events, host_settings as prefs, panels
from web.games import GameSettings, extras_label
from web.lobbies import LOBBIES, LOBBIES_CHANNEL, Lobby, close_lobby, random_game_name
from web.routes.common import change_game
from web.visitor import hosted_game_lobby, my_lobby

bp = Blueprint('host', __name__)


def render_host(lobby : Lobby, error = None, form = None, rename_error = None,
                saved = False):
    """The host page. `form`: what the host just submitted, shown again."""
    players = lobby.snapshot()
    n = len(players)
    ruleset = prefs.pref_ruleset()
    if form is not None:
        try:
            ruleset = prefs.form_ruleset(form)
        except ValueError:
            pass
    ctx = dict(lobby = lobby,
               players = players,
               groups = prefs.HOST_GROUPS,
               assassination_keys = prefs.ASSASSINATION_KEYS,
               settings = prefs.HOST_SETTINGS,
               ruleset = ruleset,
               saved = saved,
               rule_defaults = {k: s.to_json(s.default) for k, s in SETTINGS.items()},
               # Gareth / Balin could play at this size (if selected).
               extras_possible = [r.name for r in (gareth, balin) if r.can_appear(n, ruleset)],
               game_rules = lobby.current_game.rules,
               current_ruleset = lobby.current_game.game_ruleset,
               term_ruleset = (lobby.current_game.game_ruleset
                               if lobby.current_game.controller is not None else None),
               error = error,
               rename_error = rename_error,
               num_players = n,
               valid_count = n in DEFAULT_TEAM_SIZES)
    if form is not None:
        ctx['active_roles'] = form.getlist('items')
        ctx['lady'] = form.get('lady') == '1'
    else:
        ctx['active_roles'] = prefs.pref_roles()
        ctx['lady'] = prefs.pref_lady()
    if ctx['valid_count']:
        selected = [r for r in ctx['active_roles'] if r in (gareth.name, balin.name)]
        extras = num_extras(n, roles_named(selected), ruleset)
        evil_options = list(range(1, min(5, n - 1 - extras) + 1))
        quests = {e: prefs.pref_quests(n, e) for e in range(1, 6)}
        evils = prefs.pref_evils(n, extras)
        shown = quests.get(evils, prefs.default_quests(n))
        if form is not None:
            evils = form.get('evils', type=int, default=evils)
            shown = dict(sizes = [form.get(f'size{i}', '') for i in range(1, 6)],
                         double_fail = form.get('double_fail', type=int, default=0))
        ctx.update(evil_options = evil_options,
                   evils = evils,
                   shown = shown,
                   quest_prefs = quests,
                   extra_label = extras_label(n, roles_named(selected), ruleset),
                   extras_count = extras,
                   # Evil count to switch to when Gareth / Balin are toggled.
                   extra_evils = {'on': prefs.pref_evils(n, True),
                                  'off': prefs.pref_evils(n, False)},
                   defaults = dict(evils = default_num_evils(n, extras),
                                   evils_with_extra = default_num_evils(n, True),
                                   evils_without_extra = default_num_evils(n, False),
                                   **prefs.default_quests(n)))
    if lobby.current_game.controller is not None:
        ctx['host_panel'] = panels.panels(lobby.current_game, None)['host']
    g.channel = lobby.id
    return flask.render_template('host.html', **ctx)


def render_create(error = None, name = None):
    """The host has no lobby: offer to open one, with a free name filled in."""
    taken = {l.name for l in LOBBIES.active()}
    if name is None:
        name = session.get('game_name')
        if not name or name in taken:
            name = random_game_name(taken)
    return flask.render_template('host_create.html', name = name, error = error)


class HostView(MethodView):
    def get(self):
        lobby = my_lobby()
        if lobby is None:
            return render_create()
        return render_host(lobby)

    def post(self):
        """Remove a player, or rename the lobby."""
        lobby = my_lobby()
        if lobby is None:
            return flask.redirect(url_for('host.page'))
        if 'player' in request.form:
            player = request.form['player']
            lobby, _ = LOBBIES.update(lobby.id, lambda l: l.pop(player))
        new_name = request.form.get('game_name', '').strip()[:40]
        if new_name and new_name != lobby.name:
            if any(l.name == new_name for l in LOBBIES.active()):
                return render_host(lobby, rename_error = f'"{new_name}" is already taken.'), 400
            LOBBIES.update(lobby.id, lambda l: setattr(l, 'name', new_name))
            session['game_name'] = new_name
            events.publish(LOBBIES_CHANNEL, 'new-lobby')
        return flask.redirect(url_for('host.page'))


bp.add_url_rule('/host', view_func=HostView.as_view('page'))


@bp.route("/host/create", methods=["POST"])
def create():
    name = request.form.get('game_name', '').strip()[:40]
    if my_lobby() is None:
        if not name:
            return render_create(error = "Give the game a name.", name = ''), 400
        if any(l.name == name for l in LOBBIES.active()):
            return render_create(error = f'"{name}" is already taken.', name = name), 400
        lobby, created = LOBBIES.open(g.uuid, name)
        session['game_name'] = lobby.name
        if created:
            events.publish(LOBBIES_CHANNEL, 'new-lobby')
    return flask.redirect(url_for('host.page'))


@bp.route("/host/close", methods=["POST"])
def close():
    lobby = LOBBIES.hosted_by(g.uuid)
    if lobby is not None:
        close_lobby(lobby.id)
    return flask.redirect(url_for('host.page'))


@bp.route("/restart", methods=["POST"])
def restart():
    """Deal a new game with the submitted roles, settings and rules."""
    lobby = my_lobby()
    if lobby is None:
        return flask.redirect(url_for('host.page'))
    role_names = request.form.getlist('items')
    try:
        settings = GameSettings.from_form(request.form)
        ruleset = prefs.form_ruleset(request.form)
        roles = prefs.ordered_roles(role_names)
        lobby, _ = LOBBIES.update(lobby.id,
                                  lambda l: l.restart_game(roles, settings, ruleset))
    except ValueError as e:
        return render_host(lobby, error = str(e), form = request.form), 400
    prefs.save_prefs(role_names, lobby.current_game.rules)
    prefs.save_pref_ruleset(ruleset)
    events.publish(lobby.id, 'new-game')
    return flask.redirect(url_for('host.page'))


@bp.route("/host/save", methods=["POST"])
def save():
    """Remember the roles and rules without starting a game."""
    lobby = my_lobby()
    if lobby is None:
        return flask.redirect(url_for('host.page'))
    try:
        ruleset = prefs.form_ruleset(request.form)
    except ValueError as e:
        return render_host(lobby, error = str(e), form = request.form), 400
    prefs.save_selection(request.form.getlist('items'), request.form.get('lady') == '1')
    prefs.save_pref_ruleset(ruleset)
    return render_host(lobby, saved = True)


# ---- running the game ----

@bp.route("/host/game/panels")
def game_panels():
    return flask.jsonify(panels.panels(hosted_game_lobby().current_game, None))


@bp.route("/host/game/<command>", methods=["POST"])
def game_command(command):
    lobby = hosted_game_lobby()
    kind, team = request.form.get('kind', ''), request.form.getlist('team')
    commands = {
        'undo': lambda game: game.host_undo(),
        'skip': lambda game: game.host_skip(),
        'vote-start': lambda game: game.start_host_vote(kind, team),
        'vote-end': lambda game: game.end_host_vote(),
        'vote-cancel': lambda game: game.end_host_vote(cancel = True),
    }
    if command not in commands:
        flask.abort(404)
    return change_game(lobby, commands[command], lambda game: panels.panels(game, None))
