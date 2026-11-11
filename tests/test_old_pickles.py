"""Games stored before the engine and the web app became packages still load
(web.store.MOVED) and play on."""
import os

from web import store
from helpers import everyone
from thavalon import GameController, Phase
from thavalon import roles as T

PICKLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                      "game_before_package.pickle")


def load():
    with open(PICKLE, "rb") as f:
        return store.loads(f.read())


def test_old_game_loads_into_the_new_classes_and_plays_on():
    saved = load()
    ctl = saved["controller"]
    assert type(ctl) is GameController
    assert ctl.state.rules == saved["rules"] and ctl.state.rules["Gareth.lady"] == "team"
    assert ctl.state.phase == Phase.VOTING and ctl.undo_label() == "p0 voted"
    assert ctl.state.roles["p8"] == T.gareth and ctl.state.allegiance("p8") == "Evil"
    ctl.undo()
    everyone(ctl, "vote", approve=True)
    assert ctl.state.phase == Phase.QUEST
    assert "you" in ctl.view("p3") and ctl.view("p3")["you"]["role"] == "Colgrevance"


def test_old_role_info_holds_the_new_roles():
    infos = load()["infos"]
    evil_roles = infos["p3"]["evil_roles"]          # Colgrevance's view, by player
    assert evil_roles["p4"] == T.mordred and isinstance(evil_roles["p4"], T.Mordred)
    assert isinstance(evil_roles["p6"], T.MoM) and evil_roles["p6"] == T.MoM(0)


def test_old_lobby_loads_into_the_web_package():
    """A lobby pickled by the old webapp module (with a host vote under way)."""
    from web.games import AvalonGame, RoleInfo
    from web.host_votes import HostVote
    from web.lobbies import Lobby
    with open(os.path.join(os.path.dirname(PICKLE), "lobby_before_package.pickle"), "rb") as f:
        lobby = store.loads(f.read())
    game = lobby.current_game
    assert type(lobby) is Lobby and type(game) is AvalonGame
    assert type(game.host_vote) is HostVote and game.host_vote.ballots == {"Ann": "approve"}
    assert all(type(i) is RoleInfo for i in game.player_info.values())
    assert len(lobby) == 7 and game.controller.state.phase == Phase.FIRST_ROUND_PROPOSING
    game.cast_host_vote("u1", game.host_vote.id, "reject")
    assert game.host_vote.ballots["Bob"] == "reject"
