"""Balin the Savage (reworked): Good, must play a Fail to win; Evil see Balin
as one of them, Agravaine is told who Balin is; Merlin sees Balin as Evil;
Arthur is told Balin is in the game. With Gareth also possible, only one of
the two is dealt. Arthur and Galahad aren't told about Gareth."""
import pytest

from thavalon.dealing import default_num_evils, num_extras
from thavalon.ruleset import RuleSet
from thavalon.state import Phase
from helpers import (F, S, T, approve_and_play, build, deal, finish_pauses, info,
                     make_game, play_first_round)


def rs(**changes):
    return RuleSet(changes)


def counts(b):
    alleg = [r.allegiance() for r in b if r not in (T.balin, T.gareth)]
    return alleg.count("Evil"), alleg.count("Good")


# ---------------------------------------------------------------- dealing

def test_balin_or_gareth_at_nine():
    seen = set()
    for seed in range(60):
        b = build(9, [T.balin, T.gareth, T.merlin], seed=seed)
        dealt = {str(r) for r in b} & {"Balin the Savage", "Gareth"}
        assert len(dealt) == 1
        seen |= dealt
        assert counts(b) == (3, 5)                  # 3 Evil + Balin or Gareth + 5 Good
    assert seen == {"Balin the Savage", "Gareth"}
    assert num_extras(9, [T.balin, T.gareth]) == 1


def test_both_when_the_rule_allows():
    rules = rs(**{"Balin.or_gareth": False})
    assert num_extras(9, [T.balin, T.gareth], rules) == 2
    for seed in range(10):
        b = build(9, [T.balin, T.gareth], seed=seed, rules=rules)
        assert T.balin in b and T.gareth in b
        assert counts(b) == (3, 4)


def test_balin_at_six_takes_a_good_place():
    rules = rs(**{"Balin the Savage.players": [6, 9]})
    assert default_num_evils(6, 1) == 2 and default_num_evils(9, 1) == 3
    for seed in range(10):
        b = build(6, [T.balin, T.merlin], seed=seed, rules=rules)
        assert T.balin in b and counts(b) == (2, 3)


# ---------------------------------------------------------------- who sees Balin

NINE = {"a": "Merlin", "b": "Arthur", "c": "Balin the Savage", "d": "Servant",
        "e": "Servant", "f": "Mordred", "g": "Agravaine", "h": "Oberon", "i": "Morgana"}


def test_what_everyone_sees_by_default():
    b = deal(NINE)
    assert "c" in info(b, "f")["other_evils"] and "c" in info(b, "i")["other_evils"]
    assert "c" in info(b, "h")["other_evils"]                      # Oberon sees Evil too
    assert "c" not in info(b, "g")["other_evils"] and info(b, "g")["balin"] == "c"
    assert "c" in info(b, "a")["seen"]                             # Merlin
    assert T.balin in info(b, "b")["good_roles"]                   # Arthur
    assert "balin" not in info(b, "f")


def test_colgrevance_sees_balins_role():
    b = deal({"a": "Colgrevance", "b": "Balin the Savage", "c": "Mordred", "d": "Servant"})
    assert info(b, "a")["evil_roles"] == {"b": T.balin, "c": T.mordred}
    b = deal({"a": "Colgrevance", "b": "Balin the Savage", "c": "Mordred"},
             rules=rs(**{"Balin.evil_sees": False}))
    assert info(b, "a")["evil_roles"] == {"c": T.mordred}


def test_changed_sight_rules():
    b = deal(NINE, rules=rs(**{"Balin.evil_sees": False, "Arthur.sees_balin": False,
                               "Merlin.sees.Balin the Savage": False}))
    assert "c" not in info(b, "f")["other_evils"] and info(b, "g")["balin"] == "c"
    assert "c" not in info(b, "a")["seen"] and T.balin not in info(b, "b")["good_roles"]
    b = deal(NINE, rules=rs(**{"Balin.agravaine_knows": False}))
    assert "c" in info(b, "g")["other_evils"] and "balin" not in info(b, "g")


# ---------------------------------------------------------------- Arthur, Galahad and Gareth

@pytest.mark.parametrize("team", ["Good", "Evil"])
def test_arthur_and_galahad_are_not_told_about_gareth(team):
    roles = {"a": "Arthur", "b": "Galahad", "c": "Mordred", "d": "Servant",
             "e": T.Gareth(team, "c" if team == "Evil" else "d", "d" if team == "Evil" else "c")}
    b = deal(roles)
    assert T.gareth not in info(b, "a")["good_roles"]
    assert T.gareth not in info(b, "b")["evil_roles"]
    b = deal(roles, rules=rs(**{"Arthur.sees_gareth": True, "Galahad.sees_gareth": True}))
    assert (T.gareth in info(b, "a")["good_roles"]) == (team == "Good")
    assert (T.gareth in info(b, "b")["evil_roles"]) == (team == "Evil")


# ---------------------------------------------------------------- the game

BALIN_FIVE = ["Merlin", "Balin the Savage", "Servant", "Mordred", "Minion"]


def test_balin_counts_as_evil_for_proposals():
    state, _ = make_game(BALIN_FIVE)
    assert state.proposals_per_round == 4


def play_to_good_win(ctl, balin_fails):
    """Good wins 3 Quests; Balin (p1) is on each team, playing Fail on the
    first one if `balin_fails` (the Quest still succeeds: it needs 2)."""
    play_first_round(ctl, team=("p0", "p1"),
                     cards={"p1": F} if balin_fails else None)
    finish_pauses(ctl)
    while ctl.state.phase not in (Phase.ASSASSINATION, Phase.GAME_OVER):
        approve_and_play(ctl, ["p0", "p1", "p2"][:ctl.state.team_size()])
        finish_pauses(ctl)


@pytest.mark.parametrize("fails,rules,won", [
    (True, None, True), (False, None, False),
    (False, rs(**{"Balin.must_fail": False}), True)])
def test_balin_wins_only_having_played_a_fail(fails, rules, won):
    state, ctl = make_game(BALIN_FIVE, sizes=(2, 3, 2, 3, 3), double_fail=1,
                           rules=rs(**{"assassination.enabled": False,
                                       **(rules.values if rules else {})}))
    play_to_good_win(ctl, fails)
    assert state.outcome["winner"] == "Good"
    assert state.outcome["balin"] == dict(player="p1", played_fail=fails, won=won)


def test_balin_loses_when_evil_wins():
    state, ctl = make_game(BALIN_FIVE)
    play_first_round(ctl, team=("p1", "p3"), cards={"p1": F, "p3": F})
    finish_pauses(ctl)
    while state.phase != Phase.GAME_OVER:
        approve_and_play(ctl, ["p3", "p4", "p1"][:state.team_size()], cards={"p3": F})
        finish_pauses(ctl)
    assert state.outcome["winner"] == "Evil"
    assert state.outcome["balin"]["played_fail"] and not state.outcome["balin"]["won"]
