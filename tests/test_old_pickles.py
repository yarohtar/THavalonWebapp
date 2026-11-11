"""Games stored before the engine became the thavalon package still load
(store.MOVED_MODULES) and play on."""
import os

import store
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
