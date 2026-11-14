"""The Role tab's "What you can work out" notes (web/rules/deductions.py)."""
import html
import random
import re

import pytest

from helpers import T, build, deal, info
from thavalon.dealing import num_extras, possible_extras
from thavalon.ruleset import RuleSet
from web.rules.deductions import BALIN, GARETH, Setup, World, deductions, observation

KEYS = ["Balin.evil_sees", "Balin.agravaine_knows", "Balin.or_gareth", "Arthur.sees_balin",
        "Arthur.sees_gareth", "Galahad.sees_gareth", "Gareth.Good.evil_sees",
        "Gareth.Evil.evil_sees", "Gareth.Good.evil_knows_role", "Gareth.Evil.evil_knows_role",
        "Gareth.Good.merlin_knows_role", "Gareth.Evil.merlin_knows_role", "Oberon.seen_by_evil"]


def setup_of_deal(b, pool, rules):
    n = len(b.players)
    possible = [str(r) for r in possible_extras(n, pool, rules)]
    gareth = next((r for r in b if r == T.gareth), None)
    return Setup(possible, num_extras(n, pool, rules) < len(possible),
                 sum(r.allegiance() == "Evil" and r != T.gareth for r in b),
                 World(gareth.team if gareth else None, T.balin in b))


def told(role, i, rules, setup, b):
    """What the role info really tells, in the shape observation() uses."""
    name = str(role)
    if name == "Arthur":
        return (T.balin in i["good_roles"], T.gareth in i["good_roles"])
    if name == "Galahad":
        return T.gareth in i["evil_roles"]
    if name == "Merlin":
        return "gareth" in i
    if name == "Colgrevance":
        roles = list(i["evil_roles"].values())
        return (T.gareth in roles, T.balin in roles)
    if name == GARETH:
        return True
    if name == BALIN:
        return True
    if role.allegiance() == "Evil":
        hidden_oberon = (T.oberon in b and role != T.oberon and not rules["Oberon.seen_by_evil"])
        extra = len(i["other_evils"]) - (setup.num_evils - 1 - hidden_oberon)
        if name == "Agravaine":
            return (extra, "balin" in i, "gareth" in i)
        return (extra, "gareth" in i)
    return None


def test_observation_matches_the_real_role_info():
    rng = random.Random(1)
    pool = [T.gareth, T.balin, T.arthur, T.merlin, T.mordred, T.morgana, T.agravaine,
            T.colgrevance, T.oberon, T.percival]
    checked = set()
    for seed in range(400):
        rules = RuleSet({k: rng.random() < 0.5 for k in KEYS} |
                        {"Colgrevance.players": [9], "Oberon.sees_evil": True})
        b = build(9, pool, seed=seed, rules=rules)
        setup = setup_of_deal(b, pool, rules)
        for role in b:
            want = told(role, role.get_info(b), rules, setup, b)
            if want is None or str(role) in (GARETH, BALIN):
                continue
            assert observation(str(role), rules, setup.actual) == want, (str(role), rules)
            checked.add(str(role))
    assert {"Arthur", "Merlin", "Colgrevance", "Agravaine", "Mordred", "Oberon"} <= checked


@pytest.fixture(autouse=True)
def app_context():
    from helpers import web_site
    with web_site().app.test_request_context():
        yield


def notes(role, i, setup, rules=None):
    """The notes as plain text."""
    return [html.unescape(re.sub(r"<[^>]+>", "", str(n)))
            for n in deductions(role, i, rules or RuleSet(), setup)]


BOTH = [GARETH, BALIN]


def test_arthur_without_balin_concludes_gareth():
    setup = Setup(BOTH, True, 3, World("Evil", False))
    out = notes("Arthur", {"allegiance": "Good"}, setup)
    assert any("is in this game, but you can't tell which team" in n for n in out)
    assert any("isn't in this game" in n and "Balin" in n for n in out)
    out = notes("Arthur", {"allegiance": "Good"}, Setup(BOTH, True, 3, World(None, True)))
    assert any("Gareth isn't in this game" in n for n in out)


def test_reds_conclusions():
    red = {"allegiance": "Evil"}
    # Gareth or Balin: no extra seen -> Gareth is Good.
    out = notes("Mordred", red, Setup(BOTH, True, 3, World("Good", False)))
    assert any("is in this game, and is Good" in n for n in out)
    # An extra seen: an Evil Gareth or Balin, can't tell.
    out = notes("Mordred", red, Setup(BOTH, True, 3, World("Evil", False)))
    assert len(out) == 1 and "either" in out[0] and "Balin" in out[0] and "Gareth" in out[0]
    assert out == notes("Mordred", red, Setup(BOTH, True, 3, World(None, True)))
    # Only Gareth possible: an extra is an Evil Gareth.
    out = notes("Morgana", red, Setup([GARETH], False, 3, World("Evil", False)))
    assert len(out) == 1 and "really an Evil" in out[0]
    # Agravaine, told about Balin: Gareth isn't in the game.
    out = notes("Agravaine", red | {"balin": "x"}, Setup(BOTH, True, 3, World(None, True)))
    assert any("Gareth isn't in this game" in n for n in out)


def test_gareth_and_balin_know_the_other_is_absent():
    out = notes(GARETH, {"allegiance": "Unknown"}, Setup(BOTH, True, 3, World("Good", False)))
    assert out and "isn't in this game" in out[0] and "Balin" in out[0]
    out = notes(BALIN, {"allegiance": "Good"}, Setup(BOTH, True, 3, World(None, True)))
    assert out and "Gareth isn't in this game" in out[0]


def test_nothing_to_say():
    assert notes("Merlin", {"allegiance": "Good"}, Setup(BOTH, True, 3, World("Evil", False))) == []
    assert notes("Mordred", {"allegiance": "Evil"}, Setup([], True, 4, World(None, False))) == []
    # Unannounced Oberon: Evil can't count.
    assert notes("Mordred", {"allegiance": "Evil"}, Setup(BOTH, True, 3, World("Evil", False)),
                 RuleSet({"Oberon.announced": False})) == []
