"""Setting up a game: how many Evil players, team sizes, which roles are
dealt, and the deal itself (AvalonBuilder: who has which role).

Dealing is random. Randomness comes from `rng`, by default Python's
global `random` module (so `random.seed()` makes a deal repeatable).
"""
from __future__ import annotations

import random

from thavalon.roles import (Gareth, MoM, Role, SoC, arthur, balin, beast, gareth,
                            pellinore)
from thavalon.ruleset import RuleSet, DEFAULT as DEFAULT_RULES

PLAYER_LIMITS = (5, 12)        # the deal itself; games are 5 to 10 (DEFAULT_TEAM_SIZES)

DEFAULT_TEAM_SIZES : dict[int, list[int]] = {
    5:  [2, 3, 2, 3, 3],
    6:  [2, 3, 4, 3, 4],
    7:  [2, 3, 3, 4, 4],
    8:  [3, 4, 4, 5, 5],
    9:  [3, 4, 4, 5, 5],
    10: [3, 4, 4, 5, 5],
}


def default_double_fail_quest(num_players : int) -> int | None:
    """1-based index of the quest needing 2 Fails, or None."""
    return 4 if num_players >= 7 else None


def has_gareth(num_players : int, roles : list[Role], rules : RuleSet | None = None) -> bool:
    """Gareth plays when the host selected them and the player count allows (9 by default)."""
    return gareth in roles and gareth.can_appear(num_players, rules)


def default_num_evils(num_players : int, gareth_plays : bool = False) -> int:
    """Evil players, not counting Gareth. Gareth takes the place of one."""
    evils = (2 if num_players <= 6
             else 3 if num_players <= 8
             else 4 if num_players <= 11
             else 5)
    return evils - 1 if gareth_plays else evils


def generate_roles(num_players : int, base_roles : list[Role],
                   num_evils : int | None = None,
                   rules : RuleSet | None = None, rng=random) -> list[Role]:
    """The roles dealt in a game, in random order, chosen from the host's
    selection `base_roles`. Gareth, Pellinore with the Beast, and Balin are
    always dealt when possible; the rest of each team is drawn from the
    selected roles, filled up with Servants and Minions."""
    gareth_plays = has_gareth(num_players, base_roles, rules)
    base_roles = [role for role in base_roles
                  if role.is_base_role() and role != gareth]
    possible_roles = [role for role in base_roles if role.can_appear(num_players, rules)]
    goods = [role for role in possible_roles if role.allegiance() == "Good"]
    evils = [role for role in possible_roles if role.allegiance() == "Evil"]

    if num_evils is None:
        num_evils = default_num_evils(num_players, gareth_plays)
    num_goods = num_players - num_evils

    roles_in_play : list[Role] = []
    if gareth_plays:
        num_goods -= 1
        roles_in_play.append(gareth)
    if pellinore in possible_roles and beast in possible_roles:
        num_goods -= 2
        roles_in_play.append(pellinore)
        roles_in_play.append(beast)
    if balin in possible_roles:
        num_goods -= 1
        roles_in_play.append(balin)
        goods.remove(balin)  # already placed; don't deal it a second time

    if num_evils < 1 or num_goods < 1:
        raise ValueError(f"{num_evils} Evil players doesn't work with "
                         f"{num_players} players and the selected roles.")

    if len(goods) < num_goods:
        goods.extend([SoC(i) for i in range(num_goods - len(goods))])
    if len(evils) < num_evils:
        evils.extend([MoM(i) for i in range(num_evils - len(evils))])

    roles_in_play.extend(rng.sample(goods, num_goods))
    roles_in_play.extend(rng.sample(evils, num_evils))
    rng.shuffle(roles_in_play)
    return roles_in_play


class AvalonBuilder:
    """A deal: the players in proposal order, who has which role, and the
    game's rules. Iterating gives the roles in deal order; `deal[role]` is
    the player with that role.

    AvalonBuilder(players, selected_roles, ...) deals at random;
    AvalonBuilder.with_roles({...}) sets up a given deal (tests, scenarios).
    """
    players : list[str]
    role_to_player : dict[Role, str]
    rules : RuleSet = DEFAULT_RULES     # what roles see; read by Role.get_info
    rng = random                        # randomness for dealing and role info

    def __init__(self, players : list[str], roles_in_play : list[Role],
                 num_evils : int | None = None, rules : RuleSet | None = None,
                 rng=random):
        self.rules = rules or DEFAULT_RULES
        self.rng = rng
        players = list(set(players))
        rng.shuffle(players)
        self.players = players

        n = len(players)
        assert PLAYER_LIMITS[0] <= n <= PLAYER_LIMITS[1]
        roles = generate_roles(n, roles_in_play, num_evils, self.rules, rng)
        self.role_to_player = {}
        for player, role in zip(players, roles):
            self[role] = player
        self.transform_lonely_roles(roles)
        if gareth in self:
            self.choose_gareth_team()

    @classmethod
    def with_roles(cls, roles_by_player : dict[str, Role], rules : RuleSet | None = None,
                   players : list[str] | None = None) -> AvalonBuilder:
        """A deal of exactly these roles (in this deal order), with no
        shuffling, no lonely transformations and Gareth as given. `players`:
        the seating, if not the order of `roles_by_player`."""
        deal = object.__new__(cls)
        deal.rules = rules or DEFAULT_RULES
        deal.players = list(players or roles_by_player)
        deal.role_to_player = {}
        for player, role in roles_by_player.items():
            deal[role] = player
        return deal

    # ------------------------------------------------------------ the deal

    def __contains__(self, role : Role) -> bool:
        return role in self.role_to_player

    def __iter__(self):
        return iter(self.role_to_player)

    def __getitem__(self, role : Role) -> str:
        return self.role_to_player[role]

    def __setitem__(self, role : Role, player : str):
        self.role_to_player[role] = player

    def pop(self, role : Role) -> str:
        return self.role_to_player.pop(role)

    def get_first_mission_proposers(self) -> list[str]:
        return [self.players[0], self.players[1]]

    def get_second_mission_starter(self) -> str:
        return self.players[2]

    def get_players_with_roles(self, roles : list[Role]) -> list[str]:
        """Players with any of these roles, in random order."""
        players = [self[role] for role in roles if role in self]
        self.rng.shuffle(players)
        return players

    # ------------------------------------------------------------ dealing steps

    def transform_lonely_roles(self, roles : list[Role]):
        """Lonely roles change, all judged on the roles as dealt (so the
        order doesn't matter, e.g. when Percival is set not to see Merlin)."""
        changes = [(role, role.transform_if_lonely(self)) for role in roles]
        # Every role is re-added in deal order (the order roles are listed
        # in, which later random choices depend on).
        for role, new in changes:
            self[new] = self.pop(role)

    def choose_gareth_team(self):
        """Gareth joins the Knight's team; the Rival is from the other team."""
        player = self.pop(gareth)
        teams = {"Good": [], "Evil": []}
        for role, p in self.role_to_player.items():
            if role.allegiance() in teams:
                teams[role.allegiance()].append(p)
        # Arthur is never the Knight, unless the rules allow it.
        barred = None if self.rules['Gareth.arthur_knight'] else self.role_to_player.get(arthur)
        knight = self.rng.choice([p for p in teams["Good"] + teams["Evil"] if p != barred])
        team = "Good" if knight in teams["Good"] else "Evil"
        rival = self.rng.choice(teams["Evil" if team == "Good" else "Good"])
        self[Gareth(team, knight, rival)] = player
