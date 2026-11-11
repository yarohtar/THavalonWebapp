"""Shared helpers for the engine tests: set up deals and games with chosen
roles, and drive them through the controller."""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from thavalon import roles as T                                      # noqa: E402
from thavalon.cards import Card                                       # noqa: E402
from thavalon.controller import GameController                        # noqa: E402
from thavalon.dealing import AvalonBuilder                            # noqa: E402
from thavalon.ruleset import ASSASSINATION_TARGETS                    # noqa: E402
from thavalon.state import GameState, Phase, PAUSES                   # noqa: E402

S, F, R, Q = Card.SUCCESS, Card.FAIL, Card.REVERSAL, Card.QBWH


def role_objects(names) -> list:
    """Role names -> roles. "Servant"/"Minion" give numbered generic roles;
    Role objects are passed through."""
    out, soc, mom = [], 0, 0
    for name in names:
        if isinstance(name, T.Role):
            out.append(name)
        elif name in ("Servant", "Servant of Camelot"):
            out.append(T.SoC(soc)); soc += 1
        elif name in ("Minion", "Minion of Mordred"):
            out.append(T.MoM(mom)); mom += 1
        else:
            out.append(T.string_to_role[name])
    return out


def make_game(role_names, sizes=(2, 3, 2, 3, 3), double_fail=None, rules=None,
              lady=False, seed=0, role_pool=None):
    """Players p0..pN in seating order with the given roles.
    p0 and p1 propose in round 1, p2 starts round 2."""
    roles = {f"p{i}": r for i, r in enumerate(role_objects(role_names))}
    state = GameState(list(roles), roles, list(sizes), double_fail, ("p0", "p1"), "p2",
                      rng=random.Random(seed), rules=rules, lady_of_the_lake=lady,
                      role_pool=role_pool)
    return state, GameController(state)


def deal(roles_by_player : dict, rules=None) -> AvalonBuilder:
    """A deal of exactly these roles (no dealing, no transformations)."""
    roles = role_objects(roles_by_player.values())
    return AvalonBuilder.with_roles(dict(zip(roles_by_player, roles)), rules)


def info(b, player):
    role = next(r for r in b if b[r] == player)
    return role.get_info(b)


def build(n, roles=None, rules=None, seed=0, num_evils=None) -> AvalonBuilder:
    """A random deal for players P0..P(n-1), from `roles` (default: all)."""
    random.seed(seed)
    return AvalonBuilder([f"P{i}" for i in range(n)],
                         T.all_roles if roles is None else roles, num_evils, rules=rules)


def everyone(ctl, action, **params):
    for p in ctl.state.seating:
        if action in ctl.available_actions(p):
            ctl.act(p, action, **params)


def play_cards(ctl, cards=None):
    q = ctl.state.current_quest
    for p in q.team:
        ctl.act(p, "play_card", card=(cards or {}).get(p, ctl.state.allowed_cards(p)[0]))


def play_first_round(ctl, team=("p0", "p1"), cards=None):
    ctl.act("p0", "propose_first_round", team=list(team))
    ctl.act("p1", "propose_first_round", team=list(team))
    everyone(ctl, "vote_first_round", proposer="p0")
    play_cards(ctl, cards)


def finish_pauses(ctl):
    """Press Ready for everyone until the game stops pausing."""
    while ctl.state.phase in PAUSES:
        everyone(ctl, "ready")


def approve_and_play(ctl, team, cards=None, inquire=None):
    """The Leader proposes `team`, everyone approves, cards are played, any
    Inquisition looks at `inquire` (default: the first team member)."""
    s = ctl.state
    ctl.act(s.leader, "propose", team=list(team))
    if s.phase == Phase.VOTING:
        everyone(ctl, "vote", approve=True)
    finish_pauses(ctl)
    play_cards(ctl, cards)
    if s.phase == Phase.INQUISITION:
        ctl.act(s.current_quest.leader, "inquisition", target=inquire or team[0])


def play_randomly(state, rng, max_steps=3000):
    """Random legal play until the game ends (fails if it gets stuck)."""
    ctl = GameController(state)
    for _ in range(max_steps):
        if state.phase == Phase.GAME_OVER:
            return state
        options = [(p, a, o) for p in state.seating for a, o in ctl.available_actions(p).items()]
        assert options, state.phase
        p, action, o = rng.choice(options)
        if action in ("propose", "propose_first_round"):
            ctl.act(p, action, team=rng.sample(o["players"], o["team_size"]))
        elif action == "vote_first_round":
            ctl.act(p, action, proposer=rng.choice(o["choices"]))
        elif action == "vote":
            ctl.act(p, action, approve=rng.random() < 0.4)
        elif action == "play_card":
            ctl.act(p, action, card=rng.choice(o["cards"]))
        elif action == "inquisition":
            ctl.act(p, action, target=rng.choice(o["choices"]),
                    remove=o["can_remove"] and rng.random() < 0.5)
        elif action == "sorceress":
            ctl.act(p, action, next_proposer=rng.choice(o["choices"]))
        elif action == "changeling":
            ctl.act(p, action, replaced=rng.choice(o["choices"]))
        elif action in ("gawain", "lady"):
            ctl.act(p, action, target=rng.choice(o["choices"]))
        elif action == "pellinore_guess":
            ctl.act(p, action, target=rng.choice(o["choices"] + [None]))
        elif action == "assassinate":
            kind = rng.choice(o["kinds"])
            k = 0 if kind == "none" else len(ASSASSINATION_TARGETS[kind][0])
            ctl.act(p, action, kind=kind, targets=rng.sample(o["choices"], k))
        else:
            ctl.act(p, action)
    raise AssertionError("game did not finish")


def web_site():
    """The web app's pieces tests use, with an empty store."""
    from types import SimpleNamespace
    from web import games, host_settings, lobbies
    from web.app import app
    lobbies.LOBBIES.store.redis.flushdb()
    app.config.update(TESTING=True)
    return SimpleNamespace(app=app, LOBBIES=lobbies.LOBBIES, GAME_NAMES=lobbies.GAME_NAMES,
                           Lobbies=lobbies.Lobbies, AvalonGame=games.AvalonGame,
                           GameSettings=games.GameSettings,
                           ruleset_from_form=host_settings.ruleset_from_form)
