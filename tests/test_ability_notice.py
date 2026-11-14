"""The Game tab's "You can use your ability now" notice: only for the player
who can use an ability right now (its button is on the Role tab)."""
from web.panels import ABILITY_ACTIONS, ability_ready
from helpers import everyone, finish_pauses, make_game, play_first_round


def who_is_notified(ctl):
    return [p for p in ctl.state.seating if ability_ready(ctl.view(p))]


def test_only_oberon_is_notified_on_the_hammer_until_the_swap():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Mordred", "Oberon"])
    play_first_round(ctl)
    finish_pauses(ctl)
    assert who_is_notified(ctl) == []
    for _ in range(2):
        ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
        everyone(ctl, "vote", approve=False)
    ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
    assert who_is_notified(ctl) == ["p4"]
    ctl.act("p4", "changeling", replaced="p0")
    assert who_is_notified(ctl) == []


def test_only_morgana_is_notified_when_she_leads():
    state, ctl = make_game(["Merlin", "Servant", "Servant", "Morgana", "Mordred"])
    play_first_round(ctl)
    finish_pauses(ctl)
    while state.leader != "p3":
        assert who_is_notified(ctl) == []
        ctl.act(state.leader, "propose", team=["p0", "p1", "p2"])
        everyone(ctl, "vote", approve=False)
    assert who_is_notified(ctl) == ["p3"]


def test_ability_actions_are_the_role_tab_forms():
    with open("web/templates/game/abilities.html") as f:
        template = f.read()
    for action in ABILITY_ACTIONS:
        assert f"action_form('{action}'" in template
