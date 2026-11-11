"""Tests for host-changeable rules (ruleset.py), how they reach dealing, the
engine, the host page and the rules pages.  Run: python -m pytest"""
import contextlib
import html.parser
import io
import os
import pickle
import random
import re
import sys

import pytest
from werkzeug.datastructures import MultiDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import THavalon as T
import rule_notes
import rules as rules_mod
from actions import GameController, NotAllowed
from game import Card, GameState, Phase, RuleError, assassination_help
from ruleset import (ASSASSINATION_TARGETS, DEFAULT, SETTINGS, RuleSet, format_counts)

S, F = Card.SUCCESS, Card.FAIL


def rs(**changes):
    """RuleSet from keyword changes: rs(**{'Merlin.sees.Mordred': True})."""
    return RuleSet(changes)


def build(n, roles=None, rules=None, seed=0, num_evils=None):
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):        # AvalonBuilder prints
        return T.AvalonBuilder([f"P{i}" for i in range(n)],
                               T.all_roles if roles is None else roles,
                               num_evils, rules=rules)


def deal(roles_by_player, rules=None, n_players=None):
    """A builder with exactly these roles (no dealing), as dev.make_builder does."""
    b = object.__new__(T.AvalonBuilder)
    b.players = list(roles_by_player)
    b.role_to_player = {}
    b.rules = rules or DEFAULT
    soc = mom = 0
    for p, name in roles_by_player.items():
        if name == "Servant":
            role = T.SoC(soc); soc += 1
        elif name == "Minion":
            role = T.MoM(mom); mom += 1
        elif isinstance(name, T.Role):
            role = name
        else:
            role = T.string_to_role[name]
        b[role] = p
    return b


def info(b, player):
    role = next(r for r in b if b[r] == player)
    with contextlib.redirect_stdout(io.StringIO()):
        return role.get_info(b)


# ---------------------------------------------------------------- the RuleSet

OLD_CAN_APPEAR = {    # the hard-coded rules before settings existed
    "Guinevere": range(7, 11), "Gawain": [10], "Nilrem": range(7, 11),
    "Balin the Savage": [6, 9], "Agravaine": range(7, 11), "Colgrevance": [10],
    "Gareth": [9], "Pellinore": [9], "The Questing Beast": [9],
}


# Roles only reached by transforming used to say "any size"; they now say
# where they can really arise. That only feeds GameState.possible_roles, which
# matters for Oberon, Gawain, Agravaine and the Beast, so nothing plays differently.
DERIVED = {"Galahad": range(7, 11), "Uther": range(7, 11), "Ygraine": range(7, 11)}


@pytest.mark.parametrize("role", T.all_roles, ids=str)
def test_default_player_counts_are_the_old_ones(role):
    old = {**OLD_CAN_APPEAR, **DERIVED}
    for n in range(5, 11):
        assert role.can_appear(n) == (n in old.get(str(role), range(5, 11))), n
    if str(role) in DERIVED:
        return
    for n in range(5, 11):
        assert role.can_appear(n) == (n in OLD_CAN_APPEAR.get(str(role), range(5, 11))), n
    assert T.SoC(0).can_appear(5) and T.MoM(0).can_appear(10)


def test_default_ruleset_is_empty_and_compares_equal():
    assert DEFAULT.is_default and DEFAULT.to_json() == {}
    assert RuleSet({k: s.default for k, s in SETTINGS.items()}) == DEFAULT
    assert DEFAULT.assassination_kinds() == ["merlin", "nilrem", "lovers", "none"]
    assert DEFAULT.reversal_roles() == ["Lancelot", "Maelegant"]


def test_ruleset_stores_only_changes_and_round_trips():
    r = rs(**{"Gawain.players": [7, 8], "Merlin.sees.Mordred": "1",
              "Arthur.proclaim_after": "1", "Agravaine.must_fail": True})
    assert r.to_json() == {"Arthur.proclaim_after": 1, "Gawain.players": [7, 8],
                           "Merlin.sees.Mordred": True}
    assert RuleSet.from_json(r.to_json()) == r
    assert r["Gawain.players"] == frozenset({7, 8}) and r["Agravaine.must_fail"] is True
    assert pickle.loads(pickle.dumps(r)) == r


def test_ruleset_rejects_bad_values_but_saved_ones_are_dropped():
    for bad in ({"Gawain.players": [4]}, {"Gareth.knows": "nobody"},
                {"Arthur.proclaim_after": 3}):
        with pytest.raises(ValueError):
            RuleSet(bad)
        assert RuleSet.from_json(bad) == DEFAULT
    # Unknown keys (e.g. from a newer version) are ignored.
    assert RuleSet({"No.such.rule": 1}) == DEFAULT
    assert RuleSet.from_json({"No.such.rule": 1, "Gawain.players": [9]}) == \
        rs(**{"Gawain.players": [9]})


def test_format_counts():
    assert format_counts({7, 8, 9, 10}) == "7–10"
    assert format_counts({6, 9}) == "6 or 9"
    assert format_counts({9}) == "9"
    assert format_counts({5, 6, 7, 9, 10}) == "5–7, 9 or 10"
    assert format_counts(set()) == "no"


def test_assassination_help_text():
    assert assassination_help(DEFAULT.assassination_kinds()) == \
        "Name one player as Merlin or Nilrem, two as the Lovers, or no one."
    assert assassination_help(["merlin"]) == "Name one player as Merlin."
    assert assassination_help(["lovers", "none"]) == "Name two as the Lovers or no one."


# ---------------------------------------------------------------- dealing and info

def test_player_counts_decide_who_is_dealt():
    # Gawain normally only at 10; allow at 7.
    r = rs(**{"Gawain.players": [7]})
    assert all(T.gawain in build(7, [T.gawain], r, seed) for seed in range(5))
    assert T.gawain not in build(7, [T.gawain], None)
    # Merlin never dealt.
    never = rs(**{"Merlin.players": []})
    assert not any(T.merlin in build(n, [T.merlin], never) or T.nilrem in
                   build(n, [T.merlin], never) for n in range(5, 11))


def test_gareth_and_neutrals_at_other_player_counts():
    r = rs(**{"Gareth.players": [7], "Pellinore.players": [8]})
    b = build(7, [T.gareth], r)
    assert T.gareth in b and sum(x.allegiance() == "Evil" for x in b
                                 if not isinstance(x, T.Gareth)) == 2
    assert T.pellinore in build(8, [T.pellinore, T.beast], r)
    assert T.beast in build(8, [T.pellinore, T.beast], r)
    # Pellinore without the Beast never plays.
    assert T.pellinore not in build(8, [T.pellinore], r)


def test_too_many_special_roles_is_a_readable_error():
    r = rs(**{"Gareth.players": [5], "Pellinore.players": [5]})
    with pytest.raises(ValueError):
        build(5, [T.gareth, T.pellinore, T.beast, T.merlin], r, num_evils=2)


def test_merlin_sight():
    roles = {"a": "Merlin", "b": "Percival", "c": "Lancelot", "d": "Mordred",
             "e": "Morgana", "f": "Oberon", "g": "Servant"}
    assert sorted(info(deal(roles), "a")["seen"]) == ["c", "e", "f"]
    r = rs(**{"Merlin.sees.Mordred": True, "Merlin.sees.Lancelot": False,
              "Merlin.sees.Oberon": False})
    assert sorted(info(deal(roles, r), "a")["seen"]) == ["d", "e"]
    nobody = RuleSet({f"Merlin.sees.{k}": False for k in
                      ["Morgana", "Oberon", "Lancelot", "Minion of Mordred"]})
    assert info(deal(roles, nobody), "a")["seen"] == []


def test_percival_and_guinevere_sight():
    roles = {"a": "Merlin", "b": "Percival", "c": "Morgana", "d": "Guinevere",
             "e": "Arthur", "f": "Maelegant", "g": "Servant"}
    assert sorted(info(deal(roles), "b")["seen"]) == ["a", "c"]
    r = rs(**{"Percival.sees.Morgana": False, "Guinevere.sees.Maelegant": False})
    assert info(deal(roles, r), "b")["seen"] == ["a"]
    assert info(deal(roles, r), "d")["seen"] == ["e"]


def test_lonely_roles_follow_their_player_counts():
    six = [T.merlin, T.mordred, T.morgana]          # no Percival
    assert T.merlin in build(6, six)
    early = rs(**{"Merlin.lonely": list(range(5, 11))})
    assert T.nilrem in build(6, six, early) and T.merlin not in build(6, six, early)
    never = rs(**{"Merlin.lonely": []})
    assert T.merlin in build(8, six, never)
    lovers = rs(**{"Lovers.lonely": [5]})
    assert T.uther in build(5, [T.tristan, T.mordred], lovers)
    assert T.tristan in build(7, [T.tristan, T.mordred], lovers)
    guin = rs(**{"Guinevere.lonely": [8]})
    assert T.ygraine in build(8, [T.guinevere, T.mordred], guin)
    assert T.guinevere in build(7, [T.guinevere, T.mordred], guin)


def test_transformations_are_judged_on_the_roles_as_dealt():
    """Percival sees only Morgana: with Merlin and Percival but no Morgana,
    Percival becomes Galahad, and Merlin stays Merlin (Percival was dealt),
    whatever order the roles are looked at in."""
    r = rs(**{"Percival.sees.Merlin": False})
    for order in ([T.merlin, T.percival], [T.percival, T.merlin]):
        b = deal({"a": order[0], "b": order[1], "c": "Mordred", "d": "Minion",
                  "e": "Servant", "f": "Servant", "g": "Minion"}, r)
        b.transform_lonely_roles(list(b.role_to_player))
        assert T.galahad in b and T.merlin in b and T.nilrem not in b


def test_percival_who_sees_no_one_is_always_lonely():
    r = rs(**{"Percival.sees.Merlin": False, "Percival.sees.Morgana": False})
    assert T.galahad in build(7, [T.percival, T.merlin, T.morgana, T.mordred], r)


def test_nilrem_can_be_kept_secret():
    roles = {"a": "Nilrem", "b": "Servant", "c": "Arthur", "d": "Mordred", "e": "Minion",
             "f": "Servant", "g": "Servant"}
    assert info(deal(roles), "b")["nilrem"] == "a"
    assert "nilrem" not in info(deal(roles, rs(**{"Nilrem.known": False})), "b")


def test_oberon_settings():
    roles = {"a": "Mordred", "b": "Oberon", "c": "Minion", "d": "Merlin", "e": "Servant"}
    i = info(deal(roles), "a")
    assert sorted(i["other_evils"]) == ["c"] and i["oberon"] is True
    assert sorted(info(deal(roles), "b")["other_evils"]) == ["a", "c"]
    seen = deal(roles, rs(**{"Oberon.seen_by_evil": True}))
    assert sorted(info(seen, "a")["other_evils"]) == ["b", "c"]
    assert info(seen, "a")["oberon"] is False        # not "lurking": they see Oberon
    blind = deal(roles, rs(**{"Oberon.sees_evil": False}))
    assert info(blind, "b")["other_evils"] == []
    hidden = deal(roles, rs(**{"Oberon.announced": False}))
    assert info(hidden, "a")["oberon"] is False


def gareth_deal(team, rules=None):
    g = T.Gareth(team, "a" if team == "Good" else "d", "d" if team == "Good" else "a")
    return deal({"a": "Merlin", "b": "Servant", "c": "Servant", "d": "Mordred",
                 "e": "Morgana", "f": "Colgrevance", "g": g}, rules), g


@pytest.mark.parametrize("team", ["Good", "Evil"])
def test_gareth_default_visibility(team):
    b, g = gareth_deal(team)
    red = team == "Evil"
    assert ("g" in info(b, "a")["seen"]) == red
    assert ("g" in info(b, "d")["other_evils"]) == red
    assert ("g" in info(b, "f")["evil_roles"]) == red
    assert "gareth" not in info(b, "a") and "gareth" not in info(b, "d")
    assert info(b, "g") == {"allegiance": "Unknown", "knight": g.knight, "rival": g.rival}


@pytest.mark.parametrize("team", ["Good", "Evil"])
def test_gareth_visibility_settings_per_team(team):
    other = "Evil" if team == "Good" else "Good"
    flip = {f"Gareth.{team}.merlin_sees": team == "Good",
            f"Gareth.{team}.evil_sees": team == "Good",
            f"Gareth.{team}.merlin_knows_role": True,
            f"Gareth.{team}.evil_knows_role": True}
    b, g = gareth_deal(team, RuleSet(flip))
    blue = team == "Good"
    assert ("g" in info(b, "a")["seen"]) == blue
    assert ("g" in info(b, "d")["other_evils"]) == blue
    assert ("g" in info(b, "f")["evil_roles"]) == blue
    assert info(b, "a")["gareth"] == "g" and info(b, "e")["gareth"] == "g"
    # The settings for the other team don't apply.
    b2, _ = gareth_deal(other, RuleSet(flip))
    assert "gareth" not in info(b2, "a")


def test_gareth_told_only_knight_or_rival():
    b, g = gareth_deal("Good", rs(**{"Gareth.knows": "knight"}))
    assert info(b, "g") == {"allegiance": "Unknown", "knight": "a"}
    b, g = gareth_deal("Evil", rs(**{"Gareth.knows": "rival"}))
    assert info(b, "g") == {"allegiance": "Unknown", "rival": "a"}


# ---------------------------------------------------------------- the engine

def make_game(role_names, rules=None, sizes=(2, 3, 2, 3, 3), lady=False):
    roles, soc, mom = {}, 0, 0
    for i, name in enumerate(role_names):
        if name == "Servant":
            role = T.SoC(soc); soc += 1
        elif name == "Minion":
            role = T.MoM(mom); mom += 1
        elif isinstance(name, T.Role):
            role = name
        else:
            role = T.string_to_role[name]
        roles[f"p{i}"] = role
    state = GameState(list(roles), roles, list(sizes), None, ("p0", "p1"), "p2",
                      rng=random.Random(0), rules=rules, lady_of_the_lake=lady)
    return state, GameController(state)


def everyone(ctl, action, **params):
    for p in ctl.state.seating:
        if action in ctl.available_actions(p):
            ctl.act(p, action, **params)


def play_cards(ctl, cards=None):
    q = ctl.state.current_quest
    for p in q.team:
        ctl.act(p, "play_card", card=(cards or {}).get(p, ctl.state.allowed_cards(p)[0]))


def win_three(ctl):
    s = ctl.state
    ctl.act("p0", "propose_first_round", team=["p0", "p1"])
    ctl.act("p1", "propose_first_round", team=["p0", "p1"])
    everyone(ctl, "vote_first_round", proposer="p0")
    play_cards(ctl, {"p0": S, "p1": S}); everyone(ctl, "ready"); everyone(ctl, "ready")
    for team in (["p0", "p1", "p2"], ["p0", "p1"]):
        ctl.act(s.leader, "propose", team=team)
        everyone(ctl, "vote", approve=True)
        play_cards(ctl, {p: S for p in team})
        everyone(ctl, "ready"); everyone(ctl, "ready")


GAME5 = ["Merlin", "Percival", "Servant", "Mordred", "Minion"]


def test_no_assassination_when_switched_off():
    state, ctl = make_game(GAME5, rs(**{"assassination.enabled": False}))
    win_three(ctl)
    assert state.phase == Phase.GAME_OVER and state.outcome["winner"] == "Good"
    assert state.assassination is None


def test_no_assassination_when_no_choice_is_left():
    off = RuleSet({**{f"assassination.target.{k}": False for k in ASSASSINATION_TARGETS},
                   "assassination.none": False})
    assert not off.assassination_on
    state, ctl = make_game(GAME5, off)
    win_three(ctl)
    assert state.phase == Phase.GAME_OVER


def test_assassination_targets_follow_the_rules():
    r = rs(**{"assassination.target.percival": True, "assassination.target.merlin": False,
              "assassination.none": False})
    state, ctl = make_game(GAME5, r)
    win_three(ctl)
    acts = ctl.available_actions("p3")["assassinate"]
    assert acts["kinds"] == ["nilrem", "lovers", "percival"]
    with pytest.raises(NotAllowed):
        ctl.act("p4", "assassinate", kind="percival", targets=["p1"])
    for kind, targets in (("merlin", ["p0"]), ("none", []), ("percival", ["p0", "p1"])):
        with pytest.raises(RuleError):
            ctl.act("p3", "assassinate", kind=kind, targets=targets)
    ctl.act("p3", "assassinate", kind="percival", targets=["p1"])
    assert state.assassination["correct"] and state.outcome["winner"] == "Evil"


def test_naming_no_one_counts_only_the_targets_in_play():
    # Merlin is in the game but isn't a target: naming no one is correct.
    r = rs(**{"assassination.target.merlin": False})
    state, ctl = make_game(GAME5, r)
    win_three(ctl)
    ctl.act("p3", "assassinate", kind="none")
    assert state.assassination["correct"]
    # By default Merlin is a target, so it's wrong.
    state, ctl = make_game(GAME5)
    win_three(ctl)
    ctl.act("p3", "assassinate", kind="none")
    assert not state.assassination["correct"]


def test_card_rules():
    names = ["Lancelot", "Agravaine", "Servant", "Maelegant", "Minion", "Servant", "Servant"]
    state, _ = make_game(names, sizes=(2, 3, 3, 4, 4))
    assert state.allowed_cards("p1") == [F]
    r = rs(**{"Agravaine.must_fail": False, "Lancelot.reversal": False})
    state, _ = make_game(names, r, sizes=(2, 3, 3, 4, 4))
    assert state.allowed_cards("p1") == [S, F]
    assert state.allowed_cards("p0") == [S, F]
    assert Card.REVERSAL in state.allowed_cards("p3")


def test_arthur_can_proclaim_after_one_fail():
    state, ctl = make_game(["Merlin", "Arthur", "Servant", "Mordred", "Minion"],
                           rs(**{"Arthur.proclaim_after": 1}))
    assert "proclaim" not in ctl.available_actions("p1")
    ctl.act("p0", "propose_first_round", team=["p0", "p3"])
    ctl.act("p1", "propose_first_round", team=["p0", "p3"])
    everyone(ctl, "vote_first_round", proposer="p0")
    play_cards(ctl, {"p0": S, "p3": F})
    assert state.failures == 1 and "proclaim" in ctl.available_actions("p1")
    ctl.act("p1", "proclaim")


@pytest.mark.parametrize("team", ["Good", "Evil"])
def test_lady_can_show_gareths_real_team(team):
    names = ["Merlin", "Percival", "Servant", "Servant", "Servant", "Mordred", "Morgana",
             "Minion", T.Gareth(team, "p0", "p5")]
    state, _ = make_game(names, sizes=(3, 4, 4, 5, 5), lady=True)
    assert state.lady_team("p8") == "Good"
    state, _ = make_game(names, rs(**{"Gareth.lady": "team"}), sizes=(3, 4, 4, 5, 5), lady=True)
    assert state.lady_team("p8") == team


def test_games_stored_before_rules_existed_use_the_defaults():
    state, ctl = make_game(GAME5)
    del state.__dict__["rules"]                 # as unpickled from before
    state = pickle.loads(pickle.dumps(state))
    assert state.rules is DEFAULT or state.rules == DEFAULT
    assert state.allowed_cards("p0") == [S, F]


def random_rules(rng):
    values = {}
    for key, s in SETTINGS.items():
        if rng.random() < 0.7:
            continue
        if s.kind == "bool":
            values[key] = rng.random() < 0.5
        elif s.kind == "counts":
            values[key] = [n for n in range(5, 11) if rng.random() < 0.6]
        else:
            values[key] = rng.choice(s.options)[0]
    return RuleSet(values)


def random_play(state, rng):
    ctl = GameController(state)
    for _ in range(3000):
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


def test_random_rules_deal_and_play_to_the_end():
    """Any combination of settings deals valid roles, gives every player
    their info, and plays to a valid end."""
    rng = random.Random(1)
    played = 0
    for i in range(300):
        rules = random_rules(rng)
        n = rng.randint(5, 10)
        try:
            b = build(n, T.all_roles, rules, seed=i)
        except ValueError:
            continue                     # too many special roles for the size
        assert len(b.role_to_player) == n
        for role in b:
            assert role.can_appear(n, rules) or not role.is_base_role() \
                or isinstance(role, (T.SoC, T.MoM))
            info(b, b[role])
        sizes = {5: [2, 3, 2, 3, 3], 6: [2, 3, 4, 3, 4], 7: [2, 3, 3, 4, 4]}.get(n, [3, 4, 4, 5, 5])
        state = GameState.from_builder(b, sizes, 4 if n >= 7 else None,
                                       rng=random.Random(i), lady_of_the_lake=i % 2 == 0)
        assert state.rules is rules
        random_play(state, rng)
        assert state.outcome["winner"] in ("Good", "Evil")
        played += 1
    assert played > 200


# ---------------------------------------------------------------- notes

def test_no_notes_with_default_rules():
    assert rule_notes.game_notes(DEFAULT) == [] and rule_notes.game_notes(None) == []


@pytest.mark.parametrize("key", sorted(SETTINGS))
def test_every_setting_change_is_explained(key):
    """Changing any one setting produces at least one note, on real rules
    pages, with links that resolve."""
    s = SETTINGS[key]
    if s.kind == "bool":
        value = not s.default
    elif s.kind == "counts":
        value = [n for n in range(5, 11) if n not in s.default] or [5]
    else:
        value = next(v for v, _ in s.options if v != s.default)
    r = RuleSet({key: value})
    notes = rule_notes.game_notes(r)
    if key == "Oberon.announced":       # matters only when Oberon isn't seen
        assert notes
    assert notes, key
    with __import__("webapp").app.test_request_context():
        for n in notes:
            assert n.pages and set(n.pages) <= set(rules_mod.PAGES), n
            rule_notes.expand(n.text)    # unknown terms raise


def test_notes_with_everything_changed_render():
    rng = random.Random(3)
    import webapp
    with webapp.app.test_request_context():
        for _ in range(100):
            for n in rule_notes.game_notes(random_rules(rng)):
                assert set(n.pages) <= set(rules_mod.PAGES)
                rule_notes.expand(n.text)


def test_note_wording_examples():
    texts = [n.text for n in rule_notes.game_notes(rs(**{"Merlin.sees.Mordred": True}))]
    assert any("[[Merlin]] sees [[Mordred]] as Evil." == t for t in texts)
    texts = [n.text for n in rule_notes.game_notes(rs(**{"Gawain.players": [7, 8, 9, 10]}))]
    assert texts == ["[[Gawain]] can be dealt only in games with 7–10 players."]
    texts = [n.text for n in rule_notes.game_notes(rs(**{"assassination.enabled": False}))]
    assert texts == ["There is no [[Assassination]]: Good wins as soon as 3 Quests succeed.",
                     "[[Gareth]] learns their team when the game ends."]
    with __import__("webapp").app.test_request_context():
        html_ = str(rule_notes.expand("A <b> [[Merlin]] & [[Lovers|the Lovers]]"))
    assert "&lt;b&gt;" in html_ and "&amp;" in html_ and 'data-term="merlin"' in html_


# ---------------------------------------------------------------- the web app

@pytest.fixture
def web():
    import webapp
    webapp.app.config.update(TESTING=True)
    webapp.LOBBIES.store.redis.flushdb()
    return webapp


class FormFields(html.parser.HTMLParser):
    """What a browser would submit from the host page's start form."""
    def __init__(self):
        super().__init__()
        self.fields, self.in_form, self.select = [], False, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and a.get("id") == "start-form":
            self.in_form = True
        if not self.in_form:
            return
        if tag == "input" and "name" in a:
            if a.get("type") in ("checkbox", "radio"):
                if "checked" in a:
                    self.fields.append((a["name"], a.get("value", "on")))
            else:
                self.fields.append((a["name"], a.get("value", "")))
        elif tag == "select":
            self.select = a["name"]
        elif tag == "option" and self.select and "selected" in a:
            self.fields.append((self.select, a["value"]))

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_form = False
        if tag == "select":
            self.select = None


def host_form(page_html):
    p = FormFields()
    p.feed(page_html)
    return MultiDict(p.fields)


def lobby_with_players(web, n):
    host = web.app.test_client()
    host.get("/host")
    lobby = web.LOBBIES.active()[0]
    clients = {}
    for i in range(n):
        c = web.app.test_client()
        name = f"Pl{i}"
        c.post("/register", data={"player": name})
        c.get(f"/join/{lobby.id}")
        clients[name] = c
    return host, lobby.id, clients


def test_host_page_has_every_setting_once(web):
    host, _, _ = lobby_with_players(web, 7)
    page = host.get("/host").get_data(as_text=True)
    for key, s in SETTINGS.items():
        count = len(re.findall(r'<(?:input|select)[^>]*name="rule:' + re.escape(key) + '"', page))
        assert count == (6 if s.kind == "counts" else 1), key


def test_host_page_with_defaults_submits_the_default_rules(web):
    host, lobby_id, _ = lobby_with_players(web, 7)
    form = host_form(host.get("/host").get_data(as_text=True))
    assert form.get("rules_form") == "1"
    assert RuleSet.from_form(form) == DEFAULT
    assert host.post("/restart", data=form).status_code == 302
    game = web.LOBBIES.get(lobby_id).current_game
    assert game.ruleset == DEFAULT and game.controller.state.rules == DEFAULT
    # Nothing about rules is stored for a host who changed nothing.
    with host.session_transaction() as sess:
        assert sess["host_prefs"]["rules"] == {}


def test_changed_rules_are_used_remembered_and_shown(web):
    host, lobby_id, players = lobby_with_players(web, 7)
    form = host_form(host.get("/host").get_data(as_text=True))
    form.setlist("rule:Merlin.sees.Mordred", ["1"])
    form.setlist("rule:Gawain.players", ["7", "10"])
    form.setlist("items", ["Merlin", "Percival", "Mordred", "Morgana", "Gawain"])
    assert host.post("/restart", data=form).status_code == 302
    game = web.LOBBIES.get(lobby_id).current_game
    expected = rs(**{"Merlin.sees.Mordred": True, "Gawain.players": [7, 10]})
    assert game.ruleset == expected and game.controller.state.rules == expected
    assert "Gawain" in [str(r) for r in game.roles_dealt()]
    # The host page remembers it.
    page = host.get("/host").get_data(as_text=True)
    assert re.search(r'name="rule:Merlin.sees.Mordred" value="1"\s+checked', page)
    assert "Current game's rule changes (2)" in page
    # Players in the game see the changes on the rules pages...
    c = next(iter(players.values()))
    page = c.get("/rules/mordred").get_data(as_text=True)
    assert "In your current game" in page and "as Evil." in page
    assert "In your current game" not in c.get("/rules/percival").get_data(as_text=True)
    # ...and on their Game tab summary.
    panels = c.get("/game/panels").get_json()
    assert "The host changed these rules" in panels["game"]
    # Someone not in the game sees the plain rules.
    other = web.app.test_client()
    assert "In your current game" not in other.get("/rules/mordred").get_data(as_text=True)


def test_saving_rules_without_starting(web):
    host, lobby_id, _ = lobby_with_players(web, 6)
    form = host_form(host.get("/host").get_data(as_text=True))
    form.setlist("rule:assassination.enabled", [])
    assert host.post("/host/save", data=form).status_code == 200
    assert web.LOBBIES.get(lobby_id).current_game.controller is None
    with host.session_transaction() as sess:
        assert sess["host_prefs"]["rules"] == {"assassination.enabled": False}


def test_bad_rule_value_shows_an_error(web):
    host, _, _ = lobby_with_players(web, 6)
    form = host_form(host.get("/host").get_data(as_text=True))
    form.setlist("rule:Gareth.knows", ["everything"])
    r = host.post("/restart", data=form)
    assert r.status_code == 400 and "unknown choice" in r.get_data(as_text=True)


def test_every_page_renders_under_random_rules(web):
    """Role tabs, panels and rules pages for every player, many rule sets."""
    rng = random.Random(7)
    started = 0
    for i in range(25):
        host, lobby_id, players = lobby_with_players(web, rng.randint(5, 10))
        rules = random_rules(rng)
        form = host_form(host.get("/host").get_data(as_text=True))
        for key in SETTINGS:
            form.poplist(f"rule:{key}")
        for key, s in SETTINGS.items():
            v = rules[key]
            if s.kind == "bool":
                if v:
                    form.add(f"rule:{key}", "1")
            elif s.kind == "counts":
                for n in sorted(v):
                    form.add(f"rule:{key}", str(n))
            else:
                form.add(f"rule:{key}", str(v))
        form.setlist("items", [str(r) for r in T.all_roles])
        r = host.post("/restart", data=form)
        if r.status_code == 400:
            web.LOBBIES.store.redis.flushdb()
            continue                    # a combination that can't be dealt
        assert r.status_code == 302, r.get_data(as_text=True)[-500:]
        assert web.LOBBIES.get(lobby_id).current_game.ruleset == rules
        started += 1
        assert host.get("/host").status_code == 200
        for c in players.values():
            assert c.get("/").status_code == 200
            for slug in rules_mod.PAGES:
                assert c.get(f"/rules/{slug}").status_code == 200
        web.LOBBIES.store.redis.flushdb()
    assert started >= 15, started


def test_role_tab_text_follows_the_rules(web):
    """Role pages render the right sentences for changed rules."""
    import webapp
    from flask import render_template
    with webapp.app.test_request_context():
        r = rs(**{"Percival.sees.Morgana": False})
        b = deal({"a": "Percival", "b": "Merlin", "c": "Mordred", "d": "Minion",
                  "e": "Servant"}, r)
        game = webapp.AvalonGame()
        game.install(b, T.all_roles, {f"u{p}": p for p in "abcde"}, dict(
            num_players=5, num_evils=2, gareth=False, num_others=3,
            team_sizes=[2, 3, 2, 3, 3], double_fail=None, proposals=3, lady=False,
            inquisition="none"))
        page = game.render_html_info("ua")
        assert "You see the following players as" in page and "Morgana</a>:" not in page
        assert "[[Percival]] sees only [[Merlin]]" not in page        # expanded
        assert "In this game" in page and "sees only" in page
        merlin = game.render_html_info("ub")
        assert "In this game" not in merlin                          # nothing for Merlin
