"""Engine details not covered by test_game.py: refused requests, Inquisition
grants, the assassin, neutral scoring, views in every phase, undo."""
import pytest

from thavalon.assassination import assassination_help
from thavalon.cards import quest_succeeds
from thavalon.controller import MAX_UNDO
from thavalon.errors import NotAllowed, RuleError
from thavalon.state import Phase
from helpers import (F, Q, R, S, approve_and_play, everyone, finish_pauses, make_game,
                     play_cards, play_first_round)

FIVE = ["Merlin", "Servant", "Servant", "Mordred", "Minion"]
SEVEN = ["Merlin", "Servant", "Servant", "Mordred", "Morgana", "Minion", "Servant"]


def to_round_2(ctl, team=("p0", "p1")):
    play_first_round(ctl, team=team)
    finish_pauses(ctl)


# ---------------------------------------------------------------- refused requests

def test_first_round_refusals():
    state, ctl = make_game(FIVE)
    with pytest.raises(RuleError):
        state.propose_first_round("p2", ["p0", "p1"])            # not a proposer
    with pytest.raises(RuleError):
        state.propose_first_round("p0", ["p0", "nobody"])        # unknown player
    with pytest.raises(RuleError):
        state.propose_first_round("p0", ["p0", "p0"])            # duplicates count once
    with pytest.raises(RuleError):
        state.vote_first_round("p0", "p0")                       # not yet voting
    state.propose_first_round("p0", ["p0", "p1"])
    state.propose_first_round("p0", ["p0", "p2"])                # may change their team
    assert state.phase == Phase.FIRST_ROUND_PROPOSING
    state.propose_first_round("p1", ["p1", "p2"])
    with pytest.raises(RuleError):
        state.vote_first_round("p0", "p2")                       # p2 didn't propose


def test_votes_can_change_until_everyone_has_voted():
    state, ctl = make_game(FIVE)
    ctl.act("p0", "propose_first_round", team=["p0", "p1"])
    ctl.act("p1", "propose_first_round", team=["p2", "p3"])
    ctl.act("p0", "vote_first_round", proposer="p1")
    assert ctl.available_actions("p0")["vote_first_round"]["current"] == "p1"
    ctl.act("p0", "vote_first_round", proposer="p0")
    everyone(ctl, "vote_first_round", proposer="p0")
    assert state.current_quest.team == ["p0", "p1"]
    play_cards(ctl)
    ctl.act("p2", "propose", team=["p0", "p1", "p2"])
    ctl.act("p0", "vote", approve=False)
    ctl.act("p0", "vote", approve=True)
    assert ctl.available_actions("p0")["vote"]["current"] is True
    with pytest.raises(RuleError):
        state.vote("nobody", True)


def test_proposal_refusals():
    state, ctl = make_game(FIVE)
    with pytest.raises(RuleError):
        state.propose(["p0", "p1", "p2"])                        # round 1
    to_round_2(ctl)
    with pytest.raises(RuleError):
        state.propose(["p0", "p1"])                              # team of 3 needed
    # GameState doesn't check who is Morgana (the controller does).
    state.use_sorceress("p4")
    assert state.leader == "p4" and state.direction == -1


def test_sorceress_refusals():
    state, ctl = make_game(SEVEN, sizes=(2, 3, 3, 4, 4))
    to_round_2(ctl)
    for bad in ("p2", "nobody"):                                 # the leader / unknown
        with pytest.raises(RuleError):
            state.use_sorceress(bad)
    for _ in range(3):
        ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
        everyone(ctl, "vote", approve=False)
    assert state.is_hammer()
    with pytest.raises(RuleError):
        state.use_sorceress("p6")


def test_pause_refusals():
    state, ctl = make_game(FIVE)
    for call in (lambda: state.mark_ready("p0"), state.advance,
                 lambda: state.changeling("p0"), state.betray, state.proclaim,
                 lambda: state.gawain_inquisition("p0"), lambda: state.inquisition("p0"),
                 lambda: state.lady_of_the_lake("p0"), lambda: state.pellinore_guess(None),
                 lambda: state.assassinate("none")):
        with pytest.raises(RuleError):
            call()
    with pytest.raises(NotAllowed):
        ctl.skip_pause()


def test_card_refusals():
    state, ctl = make_game(FIVE)
    ctl.act("p0", "propose_first_round", team=["p0", "p1"])
    ctl.act("p1", "propose_first_round", team=["p0", "p1"])
    everyone(ctl, "vote_first_round", proposer="p0")
    with pytest.raises(RuleError):
        state.play_card("p2", S)                                 # not on the team
    with pytest.raises(RuleError):
        state.play_card("p0", R)                                 # Merlin can't Reverse
    with pytest.raises(ValueError):
        state.play_card("p0", "Joker")
    state.play_card("p0", "Success")                             # names are accepted
    with pytest.raises(RuleError):
        state.play_card("p0", S)                                 # already chosen
    with pytest.raises(NotAllowed):
        ctl.act("p0", "play_card", card="Success")


def test_changeling_refusals():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Oberon"]
    state, ctl = make_game(names)
    to_round_2(ctl)
    for _ in range(2):
        ctl.act(state.leader, "propose", team=["p0", "p1", "p4"])
        everyone(ctl, "vote", approve=False)
    ctl.act(state.leader, "propose", team=["p0", "p1", "p4"])   # Oberon on the Hammer
    assert state.phase == Phase.TEAM_ANNOUNCED
    assert "changeling" not in ctl.available_actions("p4")
    with pytest.raises(RuleError):
        state.changeling("p0")
    state.current_proposal.team = ["p0", "p1", "p2"]
    with pytest.raises(RuleError):
        state.changeling("p3")                                   # not on the team
    state.changeling("p0")
    assert state.phase == Phase.QUEST                            # no second Ready round
    assert state.current_quest.team == ["p4", "p1", "p2"]
    with pytest.raises(RuleError):
        state.changeling("p1")                                   # used up
    state_no_oberon, _ = make_game(FIVE)
    state_no_oberon.phase = Phase.TEAM_ANNOUNCED
    state_no_oberon.proposals.append(type(state.current_proposal)(1, 1, "p0", ["p0", "p1"]))
    with pytest.raises(RuleError):
        state_no_oberon.changeling("p0")


def test_inquisition_target_must_be_on_the_team():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Minion", "Morgana", "Servant"]
    state, ctl = make_game(names, sizes=(2, 3, 3, 4, 4))        # 3 Evil: Weak on proposal 1
    to_round_2(ctl)
    ctl.act("p2", "propose", team=["p0", "p1", "p2"]); everyone(ctl, "vote", approve=True)
    assert state.current_quest.inquisition == "weak"
    play_cards(ctl)
    with pytest.raises(RuleError):
        ctl.act("p2", "inquisition", target="p5")
    ctl.act("p2", "inquisition", target="p1")
    assert state.current_quest.revealed == {"p1": S}


# ---------------------------------------------------------------- Inquisition grants

def test_four_proposals_grant_weak_once_on_first_proposal():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Minion", "Morgana", "Servant"]
    state, ctl = make_game(names, sizes=(2, 3, 3, 4, 4))
    assert state.proposals_per_round == 4
    to_round_2(ctl)
    ctl.act("p2", "propose", team=["p0", "p1", "p2"]); everyone(ctl, "vote", approve=False)
    ctl.act("p3", "propose", team=["p0", "p1", "p2"]); everyone(ctl, "vote", approve=True)
    assert state.current_quest.inquisition is None               # only proposal 1
    play_cards(ctl); finish_pauses(ctl)
    approve_and_play(ctl, ["p0", "p1", "p3"], cards={"p3": F})
    assert state.quests[-1].inquisition == "weak"
    finish_pauses(ctl)
    approve_and_play(ctl, ["p0", "p1", "p2", "p6"])
    assert state.quests[-1].inquisition is None                  # used up


def test_five_proposals_strong_on_first_weak_on_second():
    names = ["Merlin", "Percival", "Servant", "Mordred", "Morgana", "Servant",
             "Agravaine", "Minion", "Servant", "Servant"]
    state, ctl = make_game(names, sizes=(3, 4, 4, 5, 5), double_fail=4)
    assert state.proposals_per_round == 5
    to_round_2(ctl, team=("p0", "p1", "p2"))
    ctl.act("p2", "propose", team=["p0", "p1", "p2", "p5"]); everyone(ctl, "vote", approve=False)
    ctl.act("p3", "propose", team=["p0", "p1", "p2", "p5"]); everyone(ctl, "vote", approve=True)
    assert state.current_quest.inquisition == "weak"             # proposal 2
    play_cards(ctl, {"p5": F}); ctl.act("p3", "inquisition", target="p0"); finish_pauses(ctl)
    approve_and_play(ctl, ["p0", "p1", "p2", "p5"])
    assert state.quests[-1].inquisition == "strong"              # proposal 1
    finish_pauses(ctl)
    approve_and_play(ctl, ["p0", "p1", "p2", "p5", "p8"])
    assert state.quests[-1].inquisition is None


def test_first_proposal_gives_weak_when_strong_is_used():
    names = ["Merlin", "Percival", "Servant", "Mordred", "Morgana", "Servant",
             "Agravaine", "Minion", "Servant", "Servant"]
    state, ctl = make_game(names, sizes=(3, 4, 4, 5, 5), double_fail=4)
    to_round_2(ctl, team=("p0", "p1", "p2"))
    approve_and_play(ctl, ["p0", "p1", "p2", "p5"])
    assert state.quests[-1].inquisition == "strong"
    finish_pauses(ctl)
    approve_and_play(ctl, ["p0", "p1", "p2", "p5"])
    assert state.quests[-1].inquisition == "weak"


# ---------------------------------------------------------------- abilities

def test_gawain_limits():
    names = ["Merlin", "Percival", "Gawain", "Mordred", "Morgana", "Servant",
             "Agravaine", "Minion", "Servant", "Servant"]
    state, ctl = make_game(names, sizes=(3, 4, 4, 5, 5), double_fail=4)
    to_round_2(ctl, team=("p0", "p1", "p5"))
    ctl.act("p2", "propose", team=["p0", "p1", "p3", "p5"]); everyone(ctl, "vote", approve=True)
    play_cards(ctl, {"p3": F})
    ctl.act("p2", "inquisition", target="p1", remove=True)       # Strong: removes p1
    assert state.phase == Phase.REVEAL
    assert ctl.available_actions("p2")["gawain"]["choices"] == ["p0", "p3", "p5"]
    for bad in ("p1", "p4"):
        with pytest.raises(RuleError):
            state.gawain_inquisition(bad)
    ctl.act("p2", "gawain", target="p3")                         # Fail: not exiled
    assert not state.gawain_exiled and state.current_quest.revealed == {"p3": F}
    assert "gawain" not in ctl.available_actions("p2")          # once per quest
    assert ctl.declarations() == [dict(player="p2", role="Gawain")]
    finish_pauses(ctl)
    # Gawain on the team: no ability and, once declared, no pause
    approve_and_play(ctl, ["p0", "p1", "p2", "p5"])
    assert state.phase != Phase.REVEAL


def test_betrayal_needs_agravaine_on_a_successful_quest():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Agravaine", "Minion", "Servant"]
    state, ctl = make_game(names, sizes=(2, 3, 3, 4, 4), double_fail=4)
    play_first_round(ctl, team=("p0", "p1"))
    assert state.phase == Phase.RESULT                           # Agravaine possible
    assert "betray" not in ctl.available_actions("p4")          # not on the team
    with pytest.raises(RuleError):
        state.betray()
    everyone(ctl, "ready")
    assert state.phase == Phase.PROPOSING and state.successes == 1


def test_declared_agravaine_off_the_team_means_no_result_pause():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Agravaine", "Minion", "Servant"]
    state, ctl = make_game(names, sizes=(2, 3, 3, 4, 4), double_fail=1)
    play_first_round(ctl, team=("p0", "p4"))                     # 1 Fail of 2 needed
    ctl.act("p4", "betray")
    assert state.quests[0].betrayed and state.failures == 1
    finish_pauses(ctl)
    approve_and_play(ctl, ["p0", "p1", "p2"])
    assert state.phase == Phase.PROPOSING and state.round == 3   # no RESULT pause


def test_arthur_cannot_proclaim_before_or_after_the_game():
    state, ctl = make_game(["Merlin", "Arthur", "Servant", "Mordred", "Minion"],
                           sizes=(2, 2, 2, 2, 2))
    with pytest.raises(RuleError):
        state.proclaim()
    for _ in range(3):
        if state.round == 1:
            play_first_round(ctl, team=("p0", "p3"), cards={"p3": F})
        else:
            approve_and_play(ctl, ["p0", "p3"], cards={"p3": F})
        finish_pauses(ctl)
    assert state.phase == Phase.GAME_OVER
    assert not state.proclamation_available()


def test_qbwh_counts_as_success_after_two_failed_quests():
    names = ["Merlin", "Pellinore", "The Questing Beast", "Mordred", "Morgana",
             "Minion", "Minion", "Servant", "Servant"]
    state, ctl = make_game(names, sizes=(3, 3, 3, 3, 3), double_fail=None)
    play_first_round(ctl, team=("p0", "p3", "p4"), cards={"p3": F})
    finish_pauses(ctl)
    approve_and_play(ctl, ["p0", "p3", "p4"], cards={"p3": F})
    finish_pauses(ctl)
    assert state.failures == 2 and state.qbwh_seen() == 0
    approve_and_play(ctl, ["p0", "p1", "p2"])
    assert state.quests[-1].qbwh_counts_as == S and state.quests[-1].succeeded


# ---------------------------------------------------------------- end of game

@pytest.mark.parametrize("names,assassin", [
    (["Merlin", "Servant", "Oberon", "Morgana", "Minion"], "p3"),
    (["Merlin", "Servant", "Oberon", "Minion", "Servant"], "p3"),
    (["Merlin", "Servant", "Oberon", "Servant", "Servant"], "p2"),
    (["Merlin", "Servant", "Servant", "Servant", "Servant"], None),
])
def test_assassin_ranking(names, assassin):
    state, _ = make_game(names)
    assert state.assassin() == assassin


def test_no_assassin_means_good_wins_straight_away():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Servant", "Pellinore"])
    for _ in range(3):
        if state.round == 1:
            play_first_round(ctl)
        else:
            approve_and_play(ctl, ["p0", "p1", "p2"][:state.team_size()])
        finish_pauses(ctl)
    assert state.phase == Phase.PELLINORE_GUESS
    assert ctl.view()["waiting_for"] == ["p4"]
    with pytest.raises(RuleError):
        state.pellinore_guess("nobody")
    ctl.act("p4", "pellinore_guess", target=None)
    assert state.phase == Phase.GAME_OVER and state.outcome["winner"] == "Good"
    assert "neutrals" not in state.outcome                       # no Beast
    assert state.outcome["roles"]["p4"] == "Pellinore"


def test_assassination_refusals():
    state, ctl = make_game(["Merlin", "Tristan", "Iseult", "Morgana", "Mordred"])
    state.phase = Phase.ASSASSINATION
    for kind, targets in [("bogus", []), ("merlin", []), ("merlin", ["p0", "p1"]),
                          ("lovers", ["p1"]), ("lovers", ["p1", "p1"]),
                          ("merlin", ["nobody"]), ("none", ["p0"])]:
        with pytest.raises(RuleError) as e:
            state.assassinate(kind, targets)
        assert str(e.value) == "Name one player as Merlin or Nilrem, two as the Lovers, or no one."
    state.assassinate("lovers", ["p2", "p1"])
    assert state.assassination == dict(kind="lovers", targets=["p2", "p1"], correct=True)
    assert [e["type"] for e in state.log[-3:]] == ["assassination", "game_over", "phase"]
    assert state.log[-3]["assassin"] == "p4"


def test_assassination_help_without_choices():
    assert assassination_help([]) == "There is no Assassination."
    assert assassination_help(["merlin", "percival", "none"], link=True) == \
        "Name one player as [[Merlin]] or [[Percival]], or no one."
    assert assassination_help(["lovers"], link=True) == "Name two as [[the Lovers|the Lovers]]."


def neutral_game():
    names = ["Merlin", "Pellinore", "The Questing Beast", "Mordred", "Morgana",
             "Minion", "Minion", "Servant", "Servant"]
    return make_game(names, sizes=(3, 3, 3, 3, 3))


@pytest.mark.parametrize("beast_on,together,results,guess,pel,beast", [
    # Beast never on a quest: Pellinore sane (no QBWH seen); Beast can't win
    ((), False, "SSS", None, dict(sanity=0, won=True), dict(points=6, won=False)),
    # Beast on two quests alone with Good: both QBWH fail them
    ((2, 3), False, "SFFF", "p2", dict(sanity=3, won=True), dict(points=3, won=False)),
    # Beast on quest 2 with Pellinore; Good wins; Pellinore guesses wrong
    ((2,), True, "SFSS", "p5", dict(sanity=0, won=False), dict(points=6, won=True)),
])
def test_neutral_scores(beast_on, together, results, guess, pel, beast):
    state, ctl = neutral_game()
    for i, result in enumerate(results, start=1):
        team = ["p0", "p7", "p8"]
        cards = {}
        if i in beast_on:
            team = ["p0", "p2", "p1" if together and i == beast_on[0] else "p7"]
        if result == "F" and "p2" not in team:
            team, cards = ["p0", "p3", "p7"], {"p3": F}
        if i == 1:
            play_first_round(ctl, team=team, cards=cards)
        else:
            approve_and_play(ctl, team, cards=cards)
        finish_pauses(ctl)
        assert state.quests[-1].succeeded is (result == "S"), i
    if state.phase == Phase.PELLINORE_GUESS:
        ctl.act("p1", "pellinore_guess", target=guess)
    if state.phase == Phase.ASSASSINATION:
        ctl.act("p3", "assassinate", kind="none")
    scores = state.outcome["neutrals"]
    got_pel = {k: scores["Pellinore"][k] for k in pel}
    got_beast = {k: scores["The Questing Beast"][k] for k in beast}
    assert (got_pel, got_beast) == (pel, beast)
    assert scores["Pellinore"]["guessed_right"] == (guess == "p2")


# ---------------------------------------------------------------- views

def test_waiting_for_and_leader_in_every_phase():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Minion"]
    state, ctl = make_game(names, lady=True)
    v = ctl.view()
    assert v["waiting_for"] == ["p0", "p1"] and v["leader"] is None and "you" not in v
    ctl.act("p0", "propose_first_round", team=["p0", "p1"])
    assert ctl.view()["waiting_for"] == ["p1"]
    ctl.act("p1", "propose_first_round", team=["p0", "p1"])
    ctl.act("p3", "vote_first_round", proposer="p1")
    v = ctl.view()
    assert v["waiting_for"] == ["p0", "p1", "p2", "p4"]
    assert v["first_round"]["voted"] == ["p3"] and v["first_round"]["votes"] is None
    everyone(ctl, "vote_first_round", proposer="p0")
    assert ctl.view()["first_round"]["votes"]["p3"] == "p0"     # changed their vote
    assert ctl.view()["waiting_for"] == ["p0", "p1"]
    play_cards(ctl)
    assert ctl.view()["leader"] == "p2" and ctl.view()["waiting_for"] == ["p2"]
    ctl.act("p2", "propose", team=["p0", "p1", "p2"])
    ctl.act("p0", "vote", approve=True)
    assert ctl.view()["waiting_for"] == ["p1", "p2", "p3", "p4"]
    everyone(ctl, "vote", approve=True)
    play_cards(ctl)
    assert state.phase == Phase.LADY and ctl.view()["waiting_for"] == ["p1"]


def test_view_of_an_inquisition_and_the_assassination():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Minion", "Morgana", "Servant"]
    state, ctl = make_game(names, sizes=(2, 3, 3, 4, 4))
    to_round_2(ctl)
    ctl.act("p2", "propose", team=["p0", "p1", "p2"]); everyone(ctl, "vote", approve=True)
    play_cards(ctl)
    assert state.phase == Phase.INQUISITION and ctl.view()["waiting_for"] == ["p2"]
    ctl.act("p2", "inquisition", target="p0")
    finish_pauses(ctl)
    approve_and_play(ctl, ["p0", "p1", "p2"])
    finish_pauses(ctl)
    assert state.phase == Phase.ASSASSINATION
    assert ctl.view()["waiting_for"] == ["p3"]
    assert ctl.available_actions("p3")["assassinate"]["kinds"] == \
        ["merlin", "nilrem", "lovers", "none"]


def test_proposal_views():
    state, ctl = make_game(SEVEN, sizes=(2, 3, 3, 4, 4))
    to_round_2(ctl)
    ctl.act("p2", "propose", team=["p0", "p1", "p2"])
    for p, vote in zip(state.seating, [True, False, True, False, True, False, False]):
        ctl.act(p, "vote", approve=vote)
    ctl.act("p3", "propose", team=["p0", "p1", "p2"]); everyone(ctl, "vote", approve=False)
    ctl.act("p4", "sorceress", next_proposer="p6")
    ctl.act("p6", "propose", team=["p0", "p1", "p2"])           # Hammer
    first, _, sorc, hammer = ctl.view("p0")["proposals"]
    assert first["approved_by"] == ["p0", "p2", "p4"] and first["approved"] is False
    assert first["rejected_by"] == ["p1", "p3", "p5", "p6"] and first["number"] == 1
    assert sorc == dict(round=2, number=3, leader="p4", team=[], hammer=False, approved=False,
                        sorceress_next="p6", voted=[], votes=None, approved_by=None,
                        rejected_by=None)
    assert hammer["hammer"] and hammer["approved"] and hammer["votes"] is None
    assert ctl.view()["direction"] == -1 and ctl.view()["proposal_number"] == 4


def test_quest_view_and_ready():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Agravaine", "Minion", "Servant"]
    state, ctl = make_game(names, sizes=(2, 3, 3, 4, 4), double_fail=4)
    play_first_round(ctl, team=("p0", "p1"))
    ctl.act("p0", "ready")
    v = ctl.view("p1")
    assert v["ready"] == ["p0"] and v["phase"] == "result"
    assert v["waiting_for"] == ["p1", "p2", "p3", "p4", "p5", "p6"]
    q = v["latest_quest"]
    assert q["played"] == ["Success", "Success"] and q["succeeded"] is True
    assert q["chosen"] == ["p0", "p1"] and q["qbwh_counts_as"] == "Fail"
    assert v["you"]["card"] == "Success" and v["actions"] == {"ready": {}}
    ctl.skip_pause()
    assert state.phase == Phase.PROPOSING and ctl.view()["ready"] == []
    assert ctl.view("p1")["you"]["card"] is None                 # new round


def test_everyone_sees_declarations_once_in_order():
    names = ["Merlin", "Arthur", "Servant", "Mordred", "Morgana", "Minion", "Servant"]
    state, ctl = make_game(names, sizes=(2, 3, 3, 4, 4), rules=None)
    play_first_round(ctl, team=("p0", "p3"), cards={"p3": F}); finish_pauses(ctl)
    ctl.act("p2", "propose", team=["p0", "p1", "p2"]); everyone(ctl, "vote", approve=False)
    ctl.act("p3", "propose", team=["p0", "p1", "p2"]); everyone(ctl, "vote", approve=False)
    ctl.act("p4", "sorceress", next_proposer="p1")
    approve_and_play(ctl, ["p0", "p3", "p5"], cards={"p3": F})
    finish_pauses(ctl)
    ctl.act("p1", "proclaim")
    assert ctl.view("p6")["declarations"] == [dict(player="p4", role="Morgana"),
                                             dict(player="p1", role="Arthur")]
    assert ctl.view()["proclaimed"] == "p1"


# ---------------------------------------------------------------- controller

def test_players_outside_the_game_can_do_nothing():
    state, ctl = make_game(FIVE)
    assert ctl.available_actions("nobody") == {}
    with pytest.raises(NotAllowed):
        ctl.act("nobody", "ready")
    with pytest.raises(NotAllowed):
        ctl.act("p0", "fly")
    assert "you" not in ctl.view("nobody")


def test_skipping_a_pause_can_be_undone_if_nothing_was_revealed():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Oberon"]
    state, ctl = make_game(names)
    to_round_2(ctl)
    for _ in range(2):
        ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
        everyone(ctl, "vote", approve=False)
    ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
    ctl.act("p0", "ready")
    ctl.skip_pause()
    assert ctl.state.phase == Phase.QUEST and ctl.undo_label() == "Skipped waiting"
    assert ctl.undo() == "Skipped waiting"
    assert ctl.state.phase == Phase.TEAM_ANNOUNCED and ctl.state.ready == {"p0"}
    assert ctl.undo_label() == "p0 pressed ready"


def test_undo_history_is_limited():
    state, ctl = make_game(FIVE)
    ctl.act("p0", "propose_first_round", team=["p0", "p1"])
    ctl.act("p1", "propose_first_round", team=["p0", "p1"])
    for i in range(MAX_UNDO + 5):
        ctl.act("p0", "vote_first_round", proposer="p0" if i % 2 else "p1")
    assert len(ctl.history) == MAX_UNDO
    for _ in range(MAX_UNDO):
        ctl.undo()
    assert ctl.undo_label() is None
    assert ctl.state.first_round_votes == {"p0": "p1"}            # vote 5 of 55
    # Each undo cuts the log back to before the undone action, which also
    # drops the earlier "undo" entries: only the latest one remains.
    undos = [e for e in ctl.state.log if e["type"] == "undo"]
    assert undos == [dict(type="undo", description="p0 voted")]


def test_undo_descriptions():
    names = ["Merlin", "Servant", "Servant", "Mordred", "Minion"]
    state, ctl = make_game(names, lady=True)
    ctl.act("p0", "propose_first_round", team=["p0", "p1"])
    ctl.act("p1", "propose_first_round", team=["p0", "p1"])
    ctl.act("p2", "vote_first_round", proposer="p0")
    assert ctl.undo_label() == "p2 voted"


# ---------------------------------------------------------------- quest results

def reference_result(cards, needed, qbwh=F):
    """Brute force: a Reversal flips any one other non-Reversal card (or none,
    when nothing is left); the Reversers get the result they want."""
    values = [qbwh if c == Q else c for c in cards]
    if values.count(R) % 2 == 0:
        return values.count(F) < needed
    others = [v for v in values if v != R]
    base = others.count(F) >= needed
    outcomes = set()
    for i, v in enumerate(others):
        flipped = others[:i] + [S if v == F else F] + others[i + 1:]
        outcomes.add(flipped.count(F) >= needed)
    # the Reversal changes the result whenever one flip can
    failed = (not base) if (not base) in outcomes else base
    return not failed


@pytest.mark.parametrize("needed", [1, 2])
def test_quest_result_matches_brute_force(needed):
    import itertools
    for size in range(2, 6):
        for cards in itertools.product([S, F, R, Q], repeat=size):
            for qbwh in (S, F):
                assert quest_succeeds(list(cards), needed, qbwh) == \
                    reference_result(cards, needed, qbwh), (cards, needed, qbwh)


def test_assassin_names_only_players_who_are_not_evil():
    state, ctl = make_game(["Merlin", "Tristan", "Iseult", "Morgana", "Mordred"])
    state.phase = Phase.ASSASSINATION
    assert ctl.available_actions("p4")["assassinate"]["choices"] == ["p0", "p1", "p2"]
    with pytest.raises(RuleError):
        state.assassinate("merlin", ["p3"])
    with pytest.raises(RuleError):
        ctl.act("p4", "assassinate", kind="merlin", targets=["p4"])
    state.assassinate("merlin", ["p0"])
    assert state.assassination["correct"]
