"""Rendering a game for one player (or the host): the role page and its
live panels (Game, Role and Vote tabs, the host's panel)."""
from __future__ import annotations

from flask import render_template

from web.games import AvalonGame

# Actions whose buttons are on the Role tab (under the role, out of sight).
ABILITY_ACTIONS = ("sorceress", "changeling", "gawain", "betray", "proclaim")


def role_page(game : AvalonGame, uuid : str) -> str:
    """The player's whole page: their role's template with the live panels."""
    player_info = game[uuid]
    return render_template(player_info['role'] + '.html',
                           info = player_info.info,
                           proposers = game.proposers,
                           game_rules = game.rules,
                           ruleset = game.game_ruleset,
                           term_ruleset = game.game_ruleset,
                           image = 'round_table.jpg',
                           num_players = len(game.player_info),
                           panels = panels(game, uuid))


def panels(game : AvalonGame, uuid : str | None) -> dict:
    """HTML for the live parts of the page. uuid=None: the host's public
    view (no private information at all)."""
    ctl = game.controller
    name = game.names.get(uuid) if uuid else None
    view = ctl.view(name)
    hv = game.host_vote.view(name) if game.host_vote else None
    ctx = dict(view = view, me = name, game_rules = game.rules,
               ability_ready = ability_ready(view),
               ruleset = game.game_ruleset, host_vote = hv,
               undo_label = ctl.undo_label() if uuid is None else None)
    if uuid is None:
        return dict(host = render_template('game/host_panel.html', **ctx))
    key, pending = vote_status(view, hv)
    key = f'{game.game_number}:{key}' if key else ''
    return dict(game = render_template('game/panel.html', **ctx),
                abilities = render_template('game/abilities.html', **ctx),
                vote = render_template('game/vote.html', vote_key = key,
                                       vote_pending = pending, **ctx))


def ability_ready(view : dict) -> bool:
    """This player can use an ability now (its button is on the Role tab)."""
    return any(a in (view.get('actions') or {}) for a in ABILITY_ACTIONS)


def vote_status(view : dict, host_vote : dict | None) -> tuple[str, bool]:
    """(key, pending) for the player's Vote tab. key names the votes going on
    that this player is part of ('' if none); it changes when a new vote
    starts, which is when the page switches to the Vote tab. pending: this
    player still has to vote in one of them."""
    keys, pending = [], False
    acts = view.get('actions') or {}
    phase = view['phase']
    if phase == 'first_round_voting':
        keys.append('fr')
        pending |= acts.get('vote_first_round', {}).get('current', 0) is None
    elif phase == 'voting':
        prop = view['proposals'][-1]
        keys.append(f"p{prop['round']}.{prop['number']}")
        pending |= acts.get('vote', {}).get('current', 0) is None
    elif phase == 'quest' and view.get('you') \
            and view['you']['name'] in view['current_quest']['team']:
        keys.append(f"q{view['round']}")
        pending |= 'play_card' in acts
    if host_vote and host_vote['involved']:
        keys.append(host_vote['key'])
        pending |= host_vote['pending']
    return ' '.join(keys), pending
