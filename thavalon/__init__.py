"""THavalon game engine: everything about the game itself, nothing about
the website. The webapp (and the tests, and the dev scenarios) use it like
this:

    deal = AvalonBuilder(player_names, selected_roles, rules=ruleset)
    info = {deal[role]: role.get_info(deal) for role in deal}   # who sees what
    state = GameState.from_builder(deal, team_sizes, double_fail_quest,
                                   role_pool=selected_roles, lady_of_the_lake=True)
    game = GameController(state)
    game.available_actions(player)      # what this player may do now
    game.act(player, "propose", team=[...])
    game.view(player)                   # what this player may see

Modules, from the bottom up:

    errors        RuleError, NotAllowed
    ruleset       the rules a host can change (RuleSet), by role name
    roles         the roles and the info each is told at the start
    dealing       how many of each team, which roles are dealt, the deal
    cards         quest cards and quest results
    assassination who assassinates, what may be named, whether it's right
    scoring       Pellinore's and the Beast's scores
    state         GameState: the rules of play, phase by phase
    views         what a player may see of a GameState
    controller    GameController: who may act, acting, undo
"""
from thavalon.cards import Card
from thavalon.controller import GameController
from thavalon.dealing import AvalonBuilder
from thavalon.errors import NotAllowed, RuleError
from thavalon.ruleset import RuleSet
from thavalon.state import GameState, Phase, PAUSES

__all__ = ["AvalonBuilder", "Card", "GameController", "GameState", "NotAllowed", "PAUSES",
           "Phase", "RuleError", "RuleSet"]
