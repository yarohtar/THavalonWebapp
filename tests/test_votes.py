"""Tests for votes.HostVote and the Vote tab.  Run: python -m pytest"""
import os
import random
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import RuleError
from votes import HostVote, mission_cards, MISSION, PROPOSAL

PLAYERS = ["a", "b", "c", "d", "e"]


def test_proposal_vote_can_change_until_complete_and_hides_votes():
    hv = HostVote(1, PROPOSAL, PLAYERS, team=["a", "b"])
    hv.cast("a", "approve")
    hv.cast("a", "reject")
    v = hv.view("a")
    assert v["mine"] == "reject" and v["voted"] == ["a"]
    assert v["approved_by"] is None and "mine" not in hv.view()
    for p in "bcd":
        hv.cast(p, "approve")
    assert hv.open
    hv.cast("e", "reject")
    v = hv.view()
    assert not v["open"] and v["approved"] is True
    assert v["approved_by"] == ["b", "c", "d"] and v["rejected_by"] == ["a", "e"]
    with pytest.raises(RuleError):
        hv.cast("a", "approve")


def test_tied_proposal_vote_is_rejected():
    hv = HostVote(1, PROPOSAL, ["a", "b", "c", "d"])
    for p, c in zip("abcd", ["approve", "approve", "reject", "reject"]):
        hv.cast(p, c)
    assert hv.view()["approved"] is False


def test_mission_vote_only_team_plays_once_and_cards_are_shuffled():
    cards = mission_cards(set())
    assert cards == ["Success", "Fail", "Reversal"]
    hv = HostVote(2, MISSION, ["a", "b", "c"], cards=cards, rng=random.Random(1))
    with pytest.raises(RuleError):
        hv.cast("d", "Success")         # not on the mission
    with pytest.raises(RuleError):
        hv.cast("a", "Questing Beast Was Here")
    hv.cast("a", "Fail")
    with pytest.raises(RuleError):
        hv.cast("a", "Success")         # cards are final
    assert hv.view()["played"] is None
    assert hv.view("b")["pending"] and not hv.view("a")["pending"]
    assert not hv.view("d")["involved"]
    hv.cast("b", "Success")
    hv.cast("c", "Reversal")
    assert sorted(hv.view()["played"]) == ["Fail", "Reversal", "Success"]
    assert "ballots" not in hv.view()


def test_beast_card_offered_when_beast_is_possible():
    assert "Questing Beast Was Here" in mission_cards({"The Questing Beast"})


def test_end_early_and_cancel():
    hv = HostVote(1, MISSION, ["a", "b"], cards=mission_cards(set()))
    hv.cast("a", "Success")
    hv.close()
    v = hv.view()
    assert v["played"] == ["Success"] and v["waiting_for"] == ["b"]
    hv = HostVote(2, PROPOSAL, PLAYERS)
    hv.cast("a", "approve")
    hv.close(cancelled=True)
    v = hv.view()
    assert v["cancelled"] and v["approved_by"] is None
    with pytest.raises(RuleError):
        hv.close()


def test_mission_needs_players():
    with pytest.raises(RuleError):
        HostVote(1, MISSION, [], cards=mission_cards(set()))


# ---- through the web app ----

@pytest.fixture
def table():
    """A host and five registered players in a started game."""
    import webapp
    webapp.LOBBIES.store.redis.flushdb()
    webapp.app.config.update(TESTING=True, DEV_FAKE_PLAYERS=0)
    host = webapp.app.test_client()
    host.get("/host")
    players = {}
    for name in ["Ann", "Bob", "Cat", "Dan", "Eve"]:
        c = webapp.app.test_client()
        c.post("/register", data={"player": name})
        c.get("/")
        players[name] = c
    r = host.post("/restart", data={"items": ["Merlin", "Percival", "Morgana", "Mordred",
                                              "Tristan", "Iseult"]})
    assert r.status_code == 302
    return host, players


def vote_screen(client):
    html = client.get("/game/panels").get_json()["vote"]
    key, pending = re.search(r'data-vote-key="([^"]*)" data-vote-pending="([^"]*)"', html).groups()
    return key, pending == "1", html


def test_host_vote_reaches_players_and_does_not_touch_the_game(table):
    host, players = table
    before = players["Ann"].get("/game/state").get_json()
    key0, _, _ = vote_screen(players["Ann"])
    assert key0 == ""        # first round: proposers still proposing

    r = host.post("/host/game/vote-start", data={"kind": "mission", "team": ["Ann", "Bob"]})
    assert r.status_code == 200
    key, pending, html = vote_screen(players["Ann"])
    assert key and pending and "Started by the host" in html and 'value="Reversal"' in html
    assert vote_screen(players["Cat"])[0] == ""      # not on the mission
    assert host.post("/host/game/vote-start", data={"kind": "proposal"}).status_code == 400

    state = players["Ann"].get("/game/state").get_json()
    vote_id = state["host_vote"]["id"]
    assert players["Cat"].post("/game/host-vote", data={"vote": vote_id, "choice": "Fail"}).status_code == 400
    assert players["Ann"].post("/game/host-vote", data={"vote": vote_id, "choice": "Fail"}).status_code == 200
    assert vote_screen(players["Ann"])[1] is False
    players["Bob"].post("/game/host-vote", data={"vote": vote_id, "choice": "Success"})
    assert vote_screen(players["Ann"])[0] == ""      # over: back to the Game tab
    panel = players["Cat"].get("/game/panels").get_json()["game"]
    assert "Host vote: mission" in panel and "card-fail" in panel

    after = players["Ann"].get("/game/state").get_json()
    for k in ("phase", "round", "quests", "proposals", "first_round"):
        assert before[k] == after[k]


def test_game_votes_move_to_the_vote_tab(table):
    host, players = table
    state = players["Ann"].get("/game/state").get_json()
    a, b = state["first_round"]["proposers"]
    size = state["team_sizes"][0]
    for p in (a, b):
        players[p].post("/game/action", data={"action": "propose_first_round",
                                              "team": state["seating"][:size]})
    key, pending, html = vote_screen(players["Ann"])
    assert key.endswith(":fr") and pending and 'name="proposer"' in html
    game = players["Ann"].get("/game/panels").get_json()["game"]
    assert 'data-goto-tab="vote"' in game and 'name="proposer"' not in game

    # A host vote on top of a game vote gets a new key (and opens the tab again).
    host.post("/host/game/vote-start", data={"kind": "proposal"})
    key2, pending2, html = vote_screen(players["Ann"])
    assert key2 != key and pending2 and "Started by the host" in html
    assert 'name="proposer"' in html      # the game's vote is still there too


def test_game_and_host_votes_share_one_screen(table):
    """Both kinds render through the same markup; only the hint differs."""
    host, players = table
    host.post("/host/game/vote-start", data={"kind": "mission", "team": ["Ann"]})
    _, _, html = vote_screen(players["Ann"])
    assert 'class="vote-box"' in html and 'class="card-picker"' in html
    assert "Cards chosen: 0 / 1" in html
