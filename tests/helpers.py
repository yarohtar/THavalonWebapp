"""Shared helpers for the engine tests: set up deals and games with chosen
roles, and drive them through the controller."""
from __future__ import annotations

import contextlib
import io
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import THavalon as T                                   # noqa: E402
from actions import GameController                     # noqa: E402
from game import Card, GameState                       # noqa: E402
from ruleset import DEFAULT                            # noqa: E402

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


def deal(roles_by_player : dict, rules=None):
    """A builder with exactly these roles (no dealing, no transformations)."""
    b = object.__new__(T.AvalonBuilder)
    b.players = list(roles_by_player)
    b.role_to_player = {}
    b.rules = rules or DEFAULT
    for p, role in zip(roles_by_player, role_objects(roles_by_player.values())):
        b[role] = p
    return b


def info(b, player):
    role = next(r for r in b if b[r] == player)
    return role.get_info(b)


def build(n, roles=None, rules=None, seed=0, num_evils=None):
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):        # dealing prints
        return T.AvalonBuilder([f"P{i}" for i in range(n)],
                               T.all_roles if roles is None else roles,
                               num_evils, rules=rules)


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
    from game import PAUSES
    while ctl.state.phase in PAUSES:
        everyone(ctl, "ready")


def approve_and_play(ctl, team, cards=None, inquire=None):
    """The Leader proposes `team`, everyone approves, cards are played, any
    Inquisition looks at `inquire` (default: the first team member)."""
    from game import Phase
    s = ctl.state
    ctl.act(s.leader, "propose", team=list(team))
    if s.phase == Phase.VOTING:
        everyone(ctl, "vote", approve=True)
    finish_pauses(ctl)
    play_cards(ctl, cards)
    if s.phase == Phase.INQUISITION:
        ctl.act(s.current_quest.leader, "inquisition", target=inquire or team[0])
