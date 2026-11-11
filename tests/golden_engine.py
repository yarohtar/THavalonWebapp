"""Behaviour fingerprint of the game engine, for checking that a refactor
changes nothing.

For many seeds, player counts and rule sets it deals roles, records every
player's role info, then plays a random game through the controller,
recording after every step the public log, every player's view, the
available actions, error messages of deliberately bad requests, and undo.
Each case is reduced to a SHA-256 digest.

Dealing iterates sets of player names, so the result depends on string
hashing: always run with PYTHONHASHSEED=0 (tests/test_golden.py does).

    PYTHONHASHSEED=0 python tests/golden_engine.py            # print digests
    PYTHONHASHSEED=0 python tests/golden_engine.py --write    # update the file

Only regenerate the file when a behaviour change is intended.
"""
from __future__ import annotations

import contextlib
import enum
import hashlib
import io
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from thavalon import roles as R                                     # noqa: E402
from thavalon.controller import GameController                      # noqa: E402
from thavalon.dealing import AvalonBuilder                          # noqa: E402
from thavalon.errors import RuleError                               # noqa: E402
from thavalon.ruleset import ASSASSINATION_TARGETS, SETTINGS, RuleSet  # noqa: E402
from thavalon.state import GameState, Phase                         # noqa: E402

GOLDEN_FILE = os.path.join(ROOT, "tests", "golden_engine.json")

SIZES = {5: [2, 3, 2, 3, 3], 6: [2, 3, 4, 3, 4], 7: [2, 3, 3, 4, 4],
         8: [3, 4, 4, 5, 5], 9: [3, 4, 4, 5, 5], 10: [3, 4, 4, 5, 5]}


def plain(x):
    """JSON-able form, keeping dict order (it can matter to the pages)."""
    if isinstance(x, R.Role):
        return f"<{x}>"
    if isinstance(x, enum.Enum):
        return x.value
    if isinstance(x, dict):
        return [[plain(k), plain(v)] for k, v in x.items()]
    if isinstance(x, (set, frozenset)):
        return sorted(plain(v) for v in x)
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    return x


class Recorder:
    def __init__(self):
        self.h = hashlib.sha256()

    def add(self, *items):
        self.h.update(json.dumps(plain(items)).encode())
        self.h.update(b"\n")

    def digest(self) -> str:
        return self.h.hexdigest()[:24]


def random_rules(rng) -> RuleSet:
    values = {}
    for key, s in SETTINGS.items():
        if rng.random() < 0.75:
            continue
        if s.kind == "bool":
            values[key] = rng.random() < 0.5
        elif s.kind == "counts":
            values[key] = [n for n in range(5, 11) if rng.random() < 0.6]
        else:
            values[key] = rng.choice(s.choices)
    return RuleSet(values)


def random_pool(rng) -> list:
    if rng.random() < 0.4:
        return list(R.all_roles)
    return [r for r in R.all_roles if rng.random() < 0.6]


def params_for(action, o, rng):
    if action in ("propose", "propose_first_round"):
        return dict(team=rng.sample(o["players"], o["team_size"]))
    if action == "vote_first_round":
        return dict(proposer=rng.choice(o["choices"]))
    if action == "vote":
        return dict(approve=rng.random() < 0.45)
    if action == "play_card":
        return dict(card=rng.choice(o["cards"]))
    if action == "inquisition":
        return dict(target=rng.choice(o["choices"]),
                    remove=o["can_remove"] and rng.random() < 0.5)
    if action == "sorceress":
        return dict(next_proposer=rng.choice(o["choices"]))
    if action == "changeling":
        return dict(replaced=rng.choice(o["choices"]))
    if action in ("gawain", "lady"):
        return dict(target=rng.choice(o["choices"]))
    if action == "pellinore_guess":
        return dict(target=rng.choice(o["choices"] + [None]))
    if action == "assassinate":
        kind = rng.choice(o["kinds"])
        k = 0 if kind == "none" else len(ASSASSINATION_TARGETS[kind][0])
        return dict(kind=kind, targets=rng.sample(o["choices"], k))
    return {}


BAD_ACTIONS = ["propose", "propose_first_round", "vote", "vote_first_round", "play_card",
               "inquisition", "sorceress", "changeling", "gawain", "betray", "proclaim",
               "lady", "ready", "pellinore_guess", "assassinate", "nonsense"]


def bad_request(ctl, rng, rec):
    """A random (usually invalid) request; record what happens."""
    s = ctl.state
    p = rng.choice(s.seating + ["nobody"])
    action = rng.choice(BAD_ACTIONS)
    junk = rng.choice(s.seating + ["nobody", None])
    params = dict(team=rng.sample(s.seating, rng.randint(0, len(s.seating))),
                  proposer=junk, approve=rng.random() < 0.5,
                  card=rng.choice(["Success", "Fail", "Reversal", "Questing Beast Was Here"]),
                  target=junk, remove=rng.random() < 0.5, next_proposer=junk, replaced=junk,
                  kind=rng.choice(list(ASSASSINATION_TARGETS) + ["none", "bogus"]),
                  targets=rng.sample(s.seating, rng.randint(0, 2)))
    try:
        ctl.act(p, action, **params)
        rec.add("bad-ok", p, action)
    except RuleError as e:
        rec.add("bad", p, action, type(e).__name__, str(e))
    except (KeyError, TypeError, ValueError) as e:
        rec.add("bad-crash", p, action, type(e).__name__, str(e))


def record_views(ctl, rec):
    s = ctl.state
    rec.add("view", None, ctl.view(None))
    for p in s.seating:
        rec.add("view", p, ctl.view(p))
    rec.add("full", ctl.view(s.seating[0], scoped=False))
    rec.add("undo", ctl.undo_label())


def play(state, rng, rec):
    ctl = GameController(state)
    for step in range(3000):
        record_views(ctl, rec)
        if state.phase == Phase.GAME_OVER:
            rec.add("log", state.log)
            return
        if rng.random() < 0.15:
            bad_request(ctl, rng, rec)
            state = ctl.state
        if ctl.undo_label() and rng.random() < 0.08:
            rec.add("undone", ctl.undo())
            state = ctl.state
            continue
        if state.phase in (Phase.TEAM_ANNOUNCED, Phase.REVEAL, Phase.RESULT) \
                and rng.random() < 0.05:
            ctl.skip_pause()
            state = ctl.state
            continue
        options = [(p, a, o) for p in state.seating
                   for a, o in ctl.available_actions(p).items()]
        p, action, o = rng.choice(options)
        ctl.act(p, action, **params_for(action, o, rng))
        state = ctl.state
    raise AssertionError("game did not finish")


def deal_case(n, seed, rules, pool, rec, lady):
    random.seed(seed)
    players = [f"P{i}" for i in range(n)]
    try:
        b = AvalonBuilder(players, pool, None, rules=rules)
    except ValueError as e:
        rec.add("deal-error", str(e))
        return None
    rec.add("deal", b.players, [(str(r), p) for r, p in b.role_to_player.items()],
            b.get_first_mission_proposers(), b.get_second_mission_starter())
    for role in b:      # the order the webapp asks (it shuffles some info)
        rec.add("info", b[role], str(role), role.get_info(b))
    state = GameState.from_builder(b, SIZES[n], 4 if n >= 7 else None,
                                   role_pool=pool, lady_of_the_lake=lady,
                                   rng=random.Random(seed))
    rec.add("state", sorted(state.possible_roles), state.num_evils,
            state.proposals_per_round, state.lady_holder, state.assassin())
    return state


def cases():
    meta = random.Random(12345)
    for n in range(5, 11):
        for seed in range(25):
            if seed < 8:
                rules, pool = RuleSet(), list(R.all_roles)
            else:
                rules, pool = random_rules(meta), random_pool(meta)
            lady = seed % 3 == 0
            yield f"n{n}-s{seed}", n, seed, rules, pool, lady


def run() -> dict[str, str]:
    out = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for name, n, seed, rules, pool, lady in cases():
            rec = Recorder()
            rec.add("rules", rules.to_json(), [str(r) for r in pool], lady)
            state = deal_case(n, seed, rules, pool, rec, lady)
            if state is not None:
                play(state, random.Random(seed * 7 + n), rec)
            out[name] = rec.digest()
    return out


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        sys.exit("Run with PYTHONHASHSEED=0.")
    digests = run()
    if "--write" in sys.argv:
        with open(GOLDEN_FILE, "w") as f:
            json.dump(digests, f, indent=0, sort_keys=True)
            f.write("\n")
    else:
        json.dump(digests, sys.stdout, indent=0, sort_keys=True)
