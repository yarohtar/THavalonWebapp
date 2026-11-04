"""Tests for game.GameState and actions.GameController.  Run: python -m pytest"""
import contextlib
import io
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import THavalon as T
from actions import GameController, NotAllowed
from game import Card, GameState, Phase, RuleError, quest_succeeds

S, F, R, Q = Card.SUCCESS, Card.FAIL, Card.REVERSAL, Card.QBWH


def make_game(role_names, sizes=(2, 3, 2, 3, 3), double_fail=None, seed=0):
    """Players p0..pN in seating order with the given roles.
    p0 and p1 propose in round 1, p2 starts round 2."""
    roles, soc, mom = {}, 0, 0
    for i, name in enumerate(role_names):
        if name == "Servant":
            role = T.SoC(soc); soc += 1
        elif name == "Minion":
            role = T.MoM(mom); mom += 1
        else:
            role = T.string_to_role[name]
        roles[f"p{i}"] = role
    seating = list(roles)
    state = GameState(seating, roles, list(sizes), double_fail,
                      ("p0", "p1"), "p2", rng=random.Random(seed))
    return state, GameController(state)


def everyone(ctl, action, **params):
    for p in ctl.state.seating:
        if action in ctl.available_actions(p):
            ctl.act(p, action, **params)


def play_first_round(ctl, team=("p0", "p1"), cards=None):
    ctl.act("p0", "propose_first_round", team=list(team))
    ctl.act("p1", "propose_first_round", team=list(team))
    everyone(ctl, "vote_first_round", proposer="p0")
    play_cards(ctl, cards or {})


def play_cards(ctl, cards):
    q = ctl.state.current_quest
    for p in q.team:
        ctl.act(p, "play_card", card=cards.get(p, ctl.state.allowed_cards(p)[0]))


# ---------------------------------------------------------------- quest results

@pytest.mark.parametrize("cards,needed,ok", [
    ([S, S], 1, True), ([S, F], 1, False), ([S, F, F], 2, False), ([S, S, F], 2, True),
    # one Reversal (rules page table)
    ([R, S], 1, False), ([R, F], 1, True), ([R, F, F], 1, False),
    ([R, S, S], 2, True), ([R, S, F], 2, False), ([R, F, F], 2, True), ([R, F, F, F], 2, False),
    # two Reversals cancel
    ([R, R, S], 1, True), ([R, R, F], 1, False),
    # no Success left to flip: R + F on a 2-Fail quest stays a Success
    ([R, F], 2, True),
])
def test_reversal(cards, needed, ok):
    assert quest_succeeds(cards, needed) is ok


def test_qbwh_value():
    assert quest_succeeds([Q, S], 1, qbwh_counts_as=F) is False
    assert quest_succeeds([Q, S], 1, qbwh_counts_as=S) is True


# ---------------------------------------------------------------- round 1

def test_first_round_tiebreak_goes_to_proposer_farther_from_starter():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion", "Servant"])
    ctl.act("p0", "propose_first_round", team=["p0", "p3"])
    ctl.act("p1", "propose_first_round", team=["p1", "p2"])
    for p, choice in zip(state.seating, ["p0", "p0", "p0", "p1", "p1", "p1"]):
        ctl.act(p, "vote_first_round", proposer=choice)
    # starter p2: p0 is 4 seats on, p1 is 5 seats on -> p1's team goes
    assert state.current_quest.team == ["p1", "p2"]
    assert state.current_quest.inquisition is None


def test_first_round_majority_and_wrong_size():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion"])
    with pytest.raises(RuleError):
        ctl.act("p0", "propose_first_round", team=["p0"])
    with pytest.raises(NotAllowed):
        ctl.act("p2", "propose_first_round", team=["p0", "p2"])
    ctl.act("p0", "propose_first_round", team=["p0", "p2"])
    ctl.act("p1", "propose_first_round", team=["p1", "p3"])
    everyone(ctl, "vote_first_round", proposer="p0")
    assert state.phase == Phase.QUEST and state.current_quest.team == ["p0", "p2"]


# ---------------------------------------------------------------- proposals

def test_rotation_hammer_and_next_round_leader():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion"])
    play_first_round(ctl)
    everyone(ctl, "ready"); everyone(ctl, "ready")      # reveal, result
    assert state.round == 2 and state.leader == "p2" and state.proposals_per_round == 3
    with pytest.raises(NotAllowed):
        ctl.act("p3", "propose", team=["p0", "p1", "p2"])
    for leader in ["p2", "p3"]:
        assert state.leader == leader
        ctl.act(leader, "propose", team=["p0", "p1", "p2"])
        everyone(ctl, "vote", approve=False)
    assert state.leader == "p4" and ctl.view("p4")["hammer"]
    ctl.act("p4", "propose", team=["p0", "p1", "p2"])
    assert state.phase == Phase.TEAM_ANNOUNCED           # Changeling pause, always
    everyone(ctl, "ready")
    assert state.phase == Phase.QUEST
    play_cards(ctl, {}); everyone(ctl, "ready"); everyone(ctl, "ready")
    assert state.round == 3 and state.leader == "p0"     # after the Hammer leader


def test_tied_vote_is_rejected():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion", "Servant"])
    play_first_round(ctl); everyone(ctl, "ready"); everyone(ctl, "ready")
    ctl.act("p2", "propose", team=["p0", "p1", "p2"])
    for p, vote in zip(state.seating, [True, True, True, False, False, False]):
        ctl.act(p, "vote", approve=vote)
    assert state.phase == Phase.PROPOSING and state.leader == "p3"


def test_sorceress_reverses_and_skips_previous_proposers():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Morgana", "Minion",
                            "Servant"], sizes=(2, 3, 3, 4, 4))
    play_first_round(ctl); everyone(ctl, "ready"); everyone(ctl, "ready")
    ctl.act("p2", "propose", team=["p0", "p1", "p2"]); everyone(ctl, "vote", approve=False)
    ctl.act("p3", "propose", team=["p0", "p1", "p2"]); everyone(ctl, "vote", approve=False)
    with pytest.raises(NotAllowed):
        ctl.act("p3", "sorceress", next_proposer="p6")
    assert state.leader == "p4" and "sorceress" in ctl.available_actions("p4")
    with pytest.raises(RuleError):
        ctl.act("p4", "sorceress", next_proposer="p2")    # already proposed
    ctl.act("p4", "sorceress", next_proposer="p6")       # counts as proposal 3
    assert state.direction == -1 and state.leader == "p6" and state.is_hammer()
    assert "sorceress" not in ctl.available_actions("p6")


def test_sorceress_can_be_used_again():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Morgana", "Servant",
                            "Servant", "Minion", "Servant", "Servant"], sizes=(3, 4, 4, 5, 5))
    # 3 Evil -> 4 proposals; p4 is Morgana
    play_first_round(ctl, team=("p0", "p1", "p5")); everyone(ctl, "ready"); everyone(ctl, "ready")
    ctl.act("p2", "propose", team=["p0", "p1", "p2", "p3"]); everyone(ctl, "vote", approve=False)
    ctl.act("p3", "propose", team=["p0", "p1", "p2", "p3"]); everyone(ctl, "vote", approve=False)
    ctl.act("p4", "sorceress", next_proposer="p1")
    assert state.direction == -1
    ctl.act("p1", "propose", team=["p0", "p1", "p2", "p3"])   # Hammer
    everyone(ctl, "ready"); play_cards(ctl, {}); everyone(ctl, "ready"); everyone(ctl, "ready")
    # round 3 starts after p1 going backwards: p0
    assert state.leader == "p0"
    ctl.act("p0", "propose", team=["p0", "p1", "p2", "p3"]); everyone(ctl, "vote", approve=False)
    assert state.leader == "p9"
    ctl.act("p9", "propose", team=["p0", "p1", "p2", "p3"]); everyone(ctl, "vote", approve=False)
    ctl.act("p8", "propose", team=["p0", "p1", "p2", "p3"]); everyone(ctl, "vote", approve=False)
    assert state.leader == "p7"   # hammer; Morgana (p4) not leader this round
    assert "sorceress" not in ctl.available_actions("p4")


# ---------------------------------------------------------------- inquisition

def ten_player_game(**kw):
    return make_game(["Merlin", "Percival", "Gawain", "Mordred", "Morgana", "Servant",
                      "Agravaine", "Minion", "Servant", "Servant"],
                     sizes=(3, 4, 4, 5, 5), double_fail=4, **kw)


def to_round_2(ctl):
    play_first_round(ctl, team=("p0", "p1", "p5"))
    everyone(ctl, "ready"); everyone(ctl, "ready")


def test_strong_then_weak_inquisition():
    state, ctl = ten_player_game()
    to_round_2(ctl)
    ctl.act("p2", "propose", team=["p0", "p1", "p3", "p5"]); everyone(ctl, "vote", approve=True)
    assert state.current_quest.inquisition == "strong"
    play_cards(ctl, {"p3": F})
    assert state.phase == Phase.INQUISITION
    assert ctl.available_actions("p2")["inquisition"]["can_remove"]
    with pytest.raises(NotAllowed):
        ctl.act("p0", "inquisition", target="p3")
    ctl.act("p2", "inquisition", target="p3", remove=True)
    everyone(ctl, "ready")
    q = state.quests[-1]
    assert q.removed == "p3" and q.succeeded and len(q.played) == 3
    everyone(ctl, "ready")
    # next round: 1st proposal approved again -> Weak (Strong used)
    leader = state.leader
    ctl.act(leader, "propose", team=["p0", "p1", "p3", "p8"]); everyone(ctl, "vote", approve=True)
    assert state.current_quest.inquisition == "weak"
    play_cards(ctl, {"p3": F})
    assert not ctl.available_actions(leader)["inquisition"]["can_remove"]
    with pytest.raises(RuleError):
        ctl.act(leader, "inquisition", target="p0", remove=True)
    ctl.act(leader, "inquisition", target="p0")
    assert ctl.view("p9")["quests"][-1]["revealed"] == {"p0": "Success"}
    everyone(ctl, "ready"); everyone(ctl, "ready")
    # both used: no more Inquisition
    ctl.act(state.leader, "propose", team=["p0", "p1", "p5", "p8", "p9"])
    everyone(ctl, "vote", approve=True)
    assert state.current_quest.inquisition is None


def test_no_inquisition_with_two_evil():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion"])
    play_first_round(ctl); everyone(ctl, "ready"); everyone(ctl, "ready")
    ctl.act("p2", "propose", team=["p0", "p1", "p2"]); everyone(ctl, "vote", approve=True)
    assert state.current_quest.inquisition is None


# ---------------------------------------------------------------- abilities

def test_gawain_exile_and_reveal_pause():
    state, ctl = ten_player_game()
    play_first_round(ctl, team=("p0", "p1", "p5"))
    assert "gawain" not in ctl.available_actions("p2")       # not in round 1
    everyone(ctl, "ready"); everyone(ctl, "ready")
    ctl.act("p2", "propose", team=["p0", "p1", "p3", "p5"]); everyone(ctl, "vote", approve=False)
    ctl.act("p3", "propose", team=["p0", "p1", "p3", "p5"]); everyone(ctl, "vote", approve=True)
    play_cards(ctl, {"p3": F})
    assert state.phase == Phase.INQUISITION                 # 2nd proposal -> Weak
    ctl.act("p3", "inquisition", target="p3")
    ctl.act("p0", "ready")
    ctl.act("p2", "gawain", target="p1")                     # Success -> exiled
    assert state.gawain_exiled and state.ready == set()      # readiness reset
    assert "gawain" not in ctl.available_actions("p2")
    everyone(ctl, "ready"); everyone(ctl, "ready")
    assert "gawain" not in ctl.available_actions("p2")


def test_betrayal_on_two_fail_quest():
    state, ctl = ten_player_game()
    to_round_2(ctl)                                          # quest 1 succeeded
    for cards in ({}, {"p3": F}):                            # quest 2 succeeds, 3 fails
        ctl.act(state.leader, "propose", team=["p0", "p1", "p3", "p5"])
        everyone(ctl, "vote", approve=True)
        play_cards(ctl, cards)
        if state.phase == Phase.INQUISITION:
            ctl.act(state.current_quest.leader, "inquisition", target="p0")
        everyone(ctl, "ready"); everyone(ctl, "ready")
    assert state.round == 4 and state.fails_needed() == 2
    assert (state.successes, state.failures) == (2, 1)
    ctl.act(state.leader, "propose", team=["p0", "p1", "p5", "p6", "p8"])
    everyone(ctl, "vote", approve=True)
    assert state.current_quest.inquisition is None           # both used up
    play_cards(ctl, {})                                      # Agravaine (p6) must Fail
    everyone(ctl, "ready")
    assert state.current_quest.succeeded                     # 1 Fail of 2 needed
    assert "betray" in ctl.available_actions("p6")
    assert "betray" not in ctl.available_actions("p3")
    ctl.act("p0", "ready")
    ctl.act("p6", "betray")
    assert state.current_quest.succeeded is False and state.ready == set()
    assert (state.successes, state.failures) == (2, 2)


def test_changeling_before_cards():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Oberon", "Servant",
                            "Servant"], sizes=(2, 3, 3, 4, 4))
    play_first_round(ctl); everyone(ctl, "ready"); everyone(ctl, "ready")
    for _ in range(2):
        ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
        everyone(ctl, "vote", approve=False)
    ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])  # Hammer
    assert state.phase == Phase.TEAM_ANNOUNCED
    assert ctl.available_actions("p4")["changeling"]["choices"] == ["p0", "p1", "p2"]
    ctl.act("p0", "ready")
    ctl.act("p4", "changeling", replaced="p1")
    assert state.current_proposal.team == ["p0", "p4", "p2"] and state.ready == set()
    everyone(ctl, "ready")
    assert state.phase == Phase.QUEST and state.current_quest.team == ["p0", "p4", "p2"]
    assert "Fail" in ctl.available_actions("p4")["play_card"]["cards"]


def test_proclamation_after_two_fails():
    state, ctl = make_game(["Merlin", "Arthur", "Servant", "Mordred", "Minion"])
    assert "proclaim" not in ctl.available_actions("p1")
    play_first_round(ctl, team=("p0", "p3"), cards={"p3": F})
    everyone(ctl, "ready"); everyone(ctl, "ready")
    ctl.act("p2", "propose", team=["p0", "p3", "p4"]); everyone(ctl, "vote", approve=True)
    play_cards(ctl, {"p3": F}); everyone(ctl, "ready"); everyone(ctl, "ready")
    assert state.failures == 2
    ctl.act("p1", "proclaim")
    assert ctl.view()["proclaimed"] == "p1"
    assert "proclaim" not in ctl.available_actions("p1")


# ---------------------------------------------------------------- end of game

def win_three_quests(ctl, team_by_round):
    state = ctl.state
    ctl.act("p0", "propose_first_round", team=team_by_round[1])
    ctl.act("p1", "propose_first_round", team=team_by_round[1])
    everyone(ctl, "vote_first_round", proposer="p0")
    play_cards(ctl, {}); everyone(ctl, "ready"); everyone(ctl, "ready")
    for r in (2, 3):
        ctl.act(state.leader, "propose", team=team_by_round[r])
        everyone(ctl, "vote", approve=True)
        play_cards(ctl, {})
        if state.phase == Phase.INQUISITION:
            ctl.act(state.current_quest.leader, "inquisition", target=team_by_round[r][0])
        everyone(ctl, "ready"); everyone(ctl, "ready")


@pytest.mark.parametrize("kind,targets,evil_wins", [
    ("merlin", ["p0"], True), ("merlin", ["p1"], False),
    ("lovers", ["p1", "p2"], True), ("lovers", ["p1", "p5"], False),
    ("none", [], False), ("nilrem", ["p0"], False),
])
def test_assassination(kind, targets, evil_wins):
    state, ctl = make_game(["Merlin", "Tristan", "Iseult", "Morgana", "Mordred", "Servant"],
                           sizes=(2, 3, 4, 3, 4))
    win_three_quests(ctl, {1: ["p0", "p1"], 2: ["p0", "p1", "p2"], 3: ["p0", "p1", "p2", "p5"]})
    assert state.phase == Phase.ASSASSINATION
    assert ctl.available_actions("p4") and not ctl.available_actions("p3")  # Mordred decides
    ctl.act("p4", "assassinate", kind=kind, targets=targets)
    assert state.outcome["winner"] == ("Evil" if evil_wins else "Good")


def test_assassinate_no_one_correct_without_targets():
    state, ctl = make_game(["Percival", "Servant", "Tristan", "Morgana", "Minion"])
    win_three_quests(ctl, {1: ["p0", "p1"], 2: ["p0", "p1", "p2"], 3: ["p0", "p1"]})
    ctl.act("p3", "assassinate", kind="none")
    assert state.outcome["winner"] == "Evil"


def test_evil_wins_on_three_fails_without_assassination():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion"],
                           sizes=(2, 3, 3, 3, 3))
    play_first_round(ctl, team=("p0", "p3"), cards={"p3": F})
    everyone(ctl, "ready"); everyone(ctl, "ready")
    for _ in range(2):
        ctl.act(state.leader, "propose", team=["p0", "p3", "p4"])
        everyone(ctl, "vote", approve=True)
        play_cards(ctl, {"p3": F}); everyone(ctl, "ready"); everyone(ctl, "ready")
    assert state.phase == Phase.GAME_OVER and state.outcome["winner"] == "Evil"


def test_pellinore_and_beast():
    roles = ["Merlin", "Pellinore", "The Questing Beast", "Mordred", "Morgana",
             "Minion", "Minion", "Servant", "Servant"]
    state, ctl = make_game(roles, sizes=(3, 4, 4, 5, 5), double_fail=4)
    assert ctl.available_actions  # smoke
    # round 1: Beast plays QBWH, counts as Fail (no fails / QBWH yet)
    play_first_round(ctl, team=("p0", "p1", "p2"))
    assert state.quests[-1].cards["p2"] == Q
    everyone(ctl, "ready")
    assert state.quests[-1].succeeded is False and state.qbwh_seen() == 1
    everyone(ctl, "ready")
    assert ctl.available_actions("p1") == {}  # no ability now
    # round 2: second QBWH
    ctl.act(state.leader, "propose", team=["p0", "p1", "p2", "p7"]); everyone(ctl, "vote", approve=True)
    assert ctl.available_actions("p1")["play_card"]["cards"] == ["Success"]
    play_cards(ctl, {})
    if state.phase == Phase.INQUISITION:
        ctl.act(state.current_quest.leader, "inquisition", target="p0")
    everyone(ctl, "ready"); everyone(ctl, "ready")
    assert state.qbwh_seen() == 2
    # Pellinore now enraged; QBWH counts as Success from now on
    ctl.act(state.leader, "propose", team=["p0", "p1", "p2", "p7"]); everyone(ctl, "vote", approve=True)
    assert ctl.available_actions("p1")["play_card"]["cards"] == ["Fail"]
    play_cards(ctl, {})
    if state.phase == Phase.INQUISITION:
        ctl.act(state.current_quest.leader, "inquisition", target="p0")
    everyone(ctl, "ready")
    assert state.quests[-1].qbwh_counts_as == S and state.quests[-1].succeeded is False
    everyone(ctl, "ready")
    assert state.failures == 3 and state.phase == Phase.PELLINORE_GUESS
    ctl.act("p1", "pellinore_guess", target="p2")
    pel = state.outcome["neutrals"]["Pellinore"]
    beast = state.outcome["neutrals"]["The Questing Beast"]
    # sanity: -3 seen +1 together +2 three fails +3 guessed = 3
    assert pel == dict(player="p1", sanity=3, guessed_right=True, won=True)
    # points: 3 quests, 0 (with Pellinore), 0 (fails), 0 (guessed) -> 3
    assert beast["points"] == 3 and not beast["won"]


# ---------------------------------------------------------------- pauses

def pool(*names):
    return [T.string_to_role[n] for n in names]


def test_no_pauses_in_small_games():
    # 5 players: Gawain and Agravaine can't appear; Oberon isn't selected
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion"])
    state.possible_roles.discard("Oberon")
    play_first_round(ctl)
    assert state.phase == Phase.PROPOSING and state.round == 2   # no reveal/result pause
    for _ in range(2):
        ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
        everyone(ctl, "vote", approve=False)
    ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])      # Hammer
    assert state.phase == Phase.QUEST                              # no Changeling pause


def test_changeling_pause_only_if_oberon_possible():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Minion"]
    for selected, expected in [(("Merlin", "Mordred", "Oberon"), Phase.TEAM_ANNOUNCED),
                               (("Merlin", "Mordred"), Phase.QUEST)]:
        state, ctl = make_game(names)
        state.possible_roles = GameState(state.seating, state.roles, [2, 3, 2, 3, 3], None,
                                         ("p0", "p1"), "p2", role_pool=pool(*selected)).possible_roles
        play_first_round(ctl)
        for _ in range(2):
            ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
            everyone(ctl, "vote", approve=False)
        ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
        assert state.phase == expected, selected


def test_reveal_pause_follows_gawain():
    state, ctl = ten_player_game()
    play_first_round(ctl, team=("p0", "p1", "p5"))
    assert state.phase == Phase.RESULT          # round 1: no Gawain; success: Agravaine pause
    everyone(ctl, "ready")
    ctl.act("p2", "propose", team=["p0", "p1", "p3", "p5"]); everyone(ctl, "vote", approve=False)
    ctl.act("p3", "propose", team=["p0", "p1", "p3", "p5"]); everyone(ctl, "vote", approve=True)
    play_cards(ctl, {})
    ctl.act("p3", "inquisition", target="p3")
    assert state.phase == Phase.REVEAL          # Gawain possible
    ctl.act("p2", "gawain", target="p0")        # Success -> exiled
    everyone(ctl, "ready")
    assert state.phase == Phase.RESULT
    everyone(ctl, "ready")
    ctl.act(state.leader, "propose", team=["p0", "p1", "p5", "p8"]); everyone(ctl, "vote", approve=True)
    play_cards(ctl, {"p0": S})
    if state.phase == Phase.INQUISITION:
        ctl.act(state.current_quest.leader, "inquisition", target="p0")
    assert state.phase != Phase.REVEAL          # Gawain exiled: no pause


def test_reveal_pause_skipped_when_gawain_not_selected():
    roles = ["Merlin", "Percival", "Servant", "Mordred", "Morgana", "Servant",
             "Minion", "Minion", "Servant", "Servant"]
    state, ctl = make_game(roles, sizes=(3, 4, 4, 5, 5), double_fail=4)
    state.possible_roles -= {"Gawain", "Agravaine"}
    to_round_2(ctl)
    ctl.act("p2", "propose", team=["p0", "p1", "p5", "p8"]); everyone(ctl, "vote", approve=True)
    play_cards(ctl, {})
    ctl.act("p2", "inquisition", target="p0")
    assert state.phase == Phase.PROPOSING and state.round == 3


def test_result_pause_only_after_success():
    state, ctl = ten_player_game()
    play_first_round(ctl, team=("p0", "p1", "p3"), cards={"p3": F})
    assert state.phase == Phase.PROPOSING        # failed quest: nothing to betray


# ---------------------------------------------------------------- views

def test_views_hide_secrets():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion"])
    ctl.act("p0", "propose_first_round", team=["p0", "p3"])
    ctl.act("p1", "propose_first_round", team=["p0", "p3"])
    everyone(ctl, "vote_first_round", proposer="p0")
    ctl.act("p3", "play_card", card="Fail")
    v = ctl.view("p0")
    assert v["you"]["role"] == "Merlin" and v["you"]["card"] is None
    assert v["quests"][0]["chosen"] == ["p3"] and v["quests"][0]["played"] is None
    assert "Fail" not in str(v["quests"]) and "Mordred" not in str(v)
    assert ctl.view("p3")["you"]["card"] == "Fail"
    ctl.act("p0", "play_card", card="Success")
    everyone(ctl, "ready"); everyone(ctl, "ready")
    ctl.act("p2", "propose", team=["p0", "p1", "p2"])
    ctl.act("p0", "vote", approve=True)
    v = ctl.view("p1")
    assert v["proposals"][-1]["voted"] == ["p0"] and v["proposals"][-1]["votes"] is None
    for p in ["p1", "p2", "p3", "p4"]:
        ctl.act(p, "vote", approve=False)
    assert ctl.view("p1")["proposals"][-1]["votes"]["p0"] is True


def test_cards_restricted_by_role():
    state, ctl = make_game(["Lancelot", "Agravaine", "Servant", "Maelegant", "Minion",
                            "Servant", "Servant"], sizes=(2, 3, 3, 4, 4))
    ctl.act("p0", "propose_first_round", team=["p0", "p1"])
    ctl.act("p1", "propose_first_round", team=["p0", "p1"])
    everyone(ctl, "vote_first_round", proposer="p0")
    assert ctl.available_actions("p0")["play_card"]["cards"] == ["Success", "Reversal"]
    assert ctl.available_actions("p1")["play_card"]["cards"] == ["Fail"]
    with pytest.raises(RuleError):
        ctl.act("p1", "play_card", card="Success")
    with pytest.raises(NotAllowed):
        ctl.act("p2", "play_card", card="Success")


# ---------------------------------------------------------------- random games

def random_game(n, seed):
    rng = random.Random(seed)
    builder = T.AvalonBuilder([f"P{i}" for i in range(n)], T.all_roles)
    sizes = {5: [2, 3, 2, 3, 3], 6: [2, 3, 4, 3, 4], 7: [2, 3, 3, 4, 4]}.get(n, [3, 4, 4, 5, 5])
    state = GameState.from_builder(builder, sizes, 4 if n >= 7 else None, rng=rng)
    ctl = GameController(state)
    for step in range(2000):
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
        elif action in ("sorceress",):
            ctl.act(p, action, next_proposer=rng.choice(o["choices"]))
        elif action in ("changeling",):
            ctl.act(p, action, replaced=rng.choice(o["choices"]))
        elif action == "gawain":
            ctl.act(p, action, target=rng.choice(o["choices"]))
        elif action == "pellinore_guess":
            ctl.act(p, action, target=rng.choice(o["choices"] + [None]))
        elif action == "assassinate":
            kind = rng.choice(o["kinds"])
            k = {"merlin": 1, "nilrem": 1, "lovers": 2, "none": 0}[kind]
            ctl.act(p, action, kind=kind, targets=rng.sample(o["choices"], k))
        else:
            ctl.act(p, action)
    raise AssertionError("game did not finish")


@pytest.mark.parametrize("n", range(5, 11))
def test_random_games_finish(n):
    """Random legal play never gets stuck and always ends in a valid outcome."""
    for seed in range(80):
        random.seed(seed)
        with contextlib.redirect_stdout(io.StringIO()):    # AvalonBuilder prints
            state = random_game(n, seed)
        assert state.outcome["winner"] in ("Good", "Evil")
        assert state.successes == 3 or state.failures == 3
        # each round's proposers are distinct
        for r in range(2, state.round + 1):
            leaders = [p.leader for p in state.proposals if p.round == r]
            assert len(leaders) == len(set(leaders))
            assert len(leaders) <= state.proposals_per_round


# ---------------------------------------------------------------- undo & scoping

def test_undo_until_something_is_revealed():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion"])
    ctl.act("p0", "propose_first_round", team=["p0", "p3"])
    assert ctl.undo_label() == "p0 proposed p0, p3"
    ctl.undo()
    assert ctl.state.first_round_teams == {}
    play_first_round(ctl, team=("p0", "p3"), cards={"p3": F})
    # the last card revealed the quest (no pauses with 5 players): no undo
    assert ctl.undo_label() is None
    with pytest.raises(NotAllowed):
        ctl.undo()
    s = ctl.state
    ctl.act(s.leader, "propose", team=["p0", "p1", "p2"])
    ctl.act("p0", "vote", approve=True)
    assert ctl.undo_label() == "p0 voted"            # no hint of how
    ctl.undo()
    assert ctl.state.current_proposal.votes == {}
    assert ctl.state.log[-1]["type"] == "undo"
    ctl.undo(); assert ctl.state.phase == Phase.PROPOSING


def test_undo_label_never_shows_a_card():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion"])
    ctl.act("p0", "propose_first_round", team=["p0", "p3"])
    ctl.act("p1", "propose_first_round", team=["p0", "p3"])
    everyone(ctl, "vote_first_round", proposer="p0")
    ctl.act("p3", "play_card", card="Fail")
    assert ctl.undo_label() == "p3 chose a card"
    ctl.undo()
    assert "p3" not in ctl.state.current_quest.cards


def test_declaring_cannot_be_undone_and_stays_visible():
    state, ctl = ten_player_game()
    to_round_2(ctl)
    ctl.act("p2", "propose", team=["p0", "p1", "p3", "p5"]); everyone(ctl, "vote", approve=False)
    ctl.act("p3", "propose", team=["p0", "p1", "p3", "p5"]); everyone(ctl, "vote", approve=False)
    ctl.act("p4", "sorceress", next_proposer="p6")
    assert ctl.undo_label() is None
    assert ctl.view("p0")["declarations"] == [dict(player="p4", role="Morgana")]


def test_scoped_view_forgets_old_details():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Minion"])
    play_first_round(ctl, team=("p0", "p3"), cards={"p3": F})
    v = ctl.view("p1")
    assert v["latest_quest"]["played"] and v["first_round"] is not None
    ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
    everyone(ctl, "vote", approve=True)
    play_cards(ctl, {})
    v = ctl.view("p1")
    assert v["quests"][0] == dict(round=1, succeeded=False)      # only the result
    assert v["latest_quest"]["round"] == 2 and v["first_round"] is None
    assert v["proposals"] == []                                   # round 3 has none yet
    full = ctl.view("p1", scoped=False)
    assert full["quests"][0]["played"]
