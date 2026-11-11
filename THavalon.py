#!/usr/bin/env python3

from __future__ import annotations
import random
import sys

from ruleset import RuleSet, DEFAULT as DEFAULT_RULES

class Role:
    def __str__(self) -> str:
        assert(False)

    def get_info(self, game : AvalonBuilder) -> dict:
        return {'allegiance': self.allegiance()}

    def allegiance(self) -> str:
        return "none"
    def transform_if_lonely(self, game : AvalonBuilder) -> Role:
        return self
    def can_appear(self, num_players : int, rules : RuleSet | None = None) -> bool:
        """Whether this role can be dealt in a game of this size (see ruleset)."""
        allowed = (rules or DEFAULT_RULES).can_appear(str(self), num_players)
        return True if allowed is None else allowed

    def __eq__(self, other) -> bool:
        return str(self) == str(other)
    def __ne__(self, other) -> bool:
        return not (self == other)

    def __hash__(self):
        return hash(str(self))

    def is_base_role(self) -> bool:
        return True

class GoodRole(Role):
    def allegiance(self)->str:
        return "Good"
    def get_info(self, game : AvalonBuilder) -> dict:
        info = super().get_info(game)
        if nilrem in game and game.rules['Nilrem.known']:
            info['nilrem'] = game[nilrem]
        return info

class SoC(GoodRole):
    index : int
    def __init__(self, index):
        self.index = index
    def __str__(self) -> str:
        return "Servant of Camelot"
    def __eq__(self, other) -> bool:
        return str(self) == str(other) and self.index==other.index
    def __ne__(self, other) -> bool:
        return not (self == other)
    def __hash__(self):
        return hash(str(self) + str(self.index))

class Percival(GoodRole):
    def __str__(self) -> str:
        return "Percival"

    def get_info(self, game : AvalonBuilder) -> dict:
        info = super().get_info(game)
        seen = game.get_players_with_roles(convert_strings_to_roles(game.rules.percival_sees()))
        info['seen'] = seen
        return info

    def transform_if_lonely(self, game : AvalonBuilder) -> Role:
        if len(game.players) not in game.rules.lonely_counts(str(self)):
            return self
        if any(string_to_role[r] in game for r in game.rules.percival_sees()):
            return self
        return galahad

class Galahad(GoodRole):
    def __str__(self) -> str:
        return "Galahad"
    def get_info(self, game : AvalonBuilder) -> dict:
        info = super().get_info(game)
        info['evil_roles'] = [role for role in game if role.allegiance()=="Evil"]
        return info
    def is_base_role(self) -> bool:
        return False

class Merlin(GoodRole):
    def __str__(self) -> str:
        return "Merlin"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        rules = game.rules
        evils = [game[role] for role in game
                 if (rules.gareth(role.team, 'merlin_sees') if isinstance(role, Gareth)
                     else role.allegiance() == "Evil" and rules.merlin_sees(str(role)))]
        if lancelot in game and rules.merlin_sees(str(lancelot)):
            evils.append(game[lancelot])
        if balin in game and rules.merlin_sees(str(balin)):
            evils.append(game[balin])
        random.shuffle(evils)
        info['seen'] = evils
        add_gareth_role(info, game, 'merlin_knows_role')
        return info
    def transform_if_lonely(self, game: AvalonBuilder) -> Role:
        if len(game.players) not in game.rules.lonely_counts(str(self)):
            return self
        if percival not in game:
            return nilrem
        return self

class Tristan(GoodRole):
    def __str__(self)->str:
        return "Tristan"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        if iseult not in game:
            info['lover'] = 'unloved'
            return info
        info['lover'] = game[iseult]
        return info

    def transform_if_lonely(self, game: AvalonBuilder) -> Role:
        if len(game.players) not in game.rules.lonely_counts(str(self)):
            return self
        if iseult not in game:
            return uther
        return self

class Iseult(GoodRole):
    def __str__(self) -> str:
        return "Iseult"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        if tristan not in game:
            info['lover'] = 'unloved'
            return info
        info['lover'] = game[tristan]
        return info

    def transform_if_lonely(self, game: AvalonBuilder) -> Role:
        if len(game.players) not in game.rules.lonely_counts(str(self)):
            return self
        if tristan not in game:
            return uther
        return self

class Uther(GoodRole):
    def __str__(self) -> str:
        return "Uther"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        other_goods = [role for role in game 
                       if role.allegiance() == "Good" 
                       and role != uther 
                       and role != nilrem]
        # Nobody to stalk can only happen with unusual settings.
        if not other_goods:
            info['stalked_good'] = None
            return info
        stalked_role = random.sample(other_goods, 1)[0]
        info['stalked_good'] = game[stalked_role]
        return info
    def is_base_role(self) -> bool:
        return False

class Arthur(GoodRole):
    def __str__(self) -> str:
        return "Arthur"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        info['good_roles'] = [role for role in game if role.allegiance()=="Good"]
        return info

class Lancelot(GoodRole):
    def __str__(self) -> str:
        return "Lancelot"

class Guinevere(GoodRole):
    def __str__(self) -> str:
        return "Guinevere"

    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        seen = game.get_players_with_roles(convert_strings_to_roles(game.rules.guinevere_sees()))
        info['seen'] = seen
        return info

    def transform_if_lonely(self, game: AvalonBuilder) -> Role:
        if len(game.players) not in game.rules.lonely_counts(str(self)):
            return self
        if any(string_to_role[r] in game for r in game.rules.guinevere_sees()):
            return self
        return ygraine

class Ygraine(GoodRole):
    def __str__(self) -> str:
        return "Ygraine"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        evils = [role for role in game if role.allegiance() == "Evil" and role != mordred]
        if not evils:         # e.g. Mordred is the only Evil player
            info['stalked_evil'] = None
            return info
        stalked_role = random.sample(evils, 1)[0]
        info['stalked_evil'] = game[stalked_role]
        return info
    def is_base_role(self) -> bool:
        return False

class Gawain(GoodRole):
    def __str__(self) -> str:
        return "Gawain"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        goods = [role for role in game if role.allegiance() == "Good" and role != gawain]
        if not goods or len(game.role_to_player) < 4:
            info['seen'] = []
            return info
        good_role_seen = random.sample(goods,1)[0]
        everyone_else = [role for role in game if role != gawain and role != good_role_seen]
        seen = random.sample(everyone_else, 2)
        seen.append(good_role_seen)
        random.shuffle(seen)
        seen_players = [game[role] for role in seen]
        info['seen'] = seen_players
        return info


class Nilrem(GoodRole):
    def __str__(self) -> str:
        return "Nilrem"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        info.pop('nilrem', None)
        return info
    def is_base_role(self) -> bool:
        return False

class Balin(GoodRole):
    def __str__(self) -> str:
        return "Balin the Savage"
    def get_info(self, game : AvalonBuilder) -> dict:
        info = super().get_info(game)
        if agravaine in game:
            info['agravaine'] = game[agravaine]
        return info

class EvilRole(Role):
    def allegiance(self)-> str:
        return "Evil"

    def get_visible_evils(self, game : AvalonBuilder) -> list[str]:
        if self == oberon and not game.rules['Oberon.sees_evil']:
            return []
        return game.get_players_with_roles(visible_evil_roles(game, self))

    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        info['other_evils'] = self.get_visible_evils(game)
        # Told that an Oberon lurks, when they don't see Oberon themselves.
        info['oberon'] = (oberon in game and game.rules['Oberon.announced']
                          and not game.rules['Oberon.seen_by_evil'])
        add_gareth_role(info, game, 'evil_knows_role')
        print(info)
        return info


def visible_evil_roles(game : AvalonBuilder, viewer : Role) -> list[Role]:
    """Roles an Evil player sees as fellow Evil (in the builder's order)."""
    rules = game.rules
    seen = []
    for role in game:
        if role == viewer:
            continue
        if isinstance(role, Gareth):
            if rules.gareth(role.team, 'evil_sees'):
                seen.append(role)
        elif role.allegiance() == "Evil" and (role != oberon or rules['Oberon.seen_by_evil']):
            seen.append(role)
    return seen


def add_gareth_role(info : dict, game : AvalonBuilder, rule : str):
    """Tell this player which player is Gareth, if the rules say so."""
    for role in game:
        if isinstance(role, Gareth) and game.rules.gareth(role.team, rule):
            info['gareth'] = game[role]

class MoM(EvilRole):
    index : int
    def __init__(self, index : int):
        self.index = index
    def __str__(self) -> str:
        return f"Minion of Mordred"
    def __eq__(self, other) -> bool:
        if not isinstance(other, MoM):
            return False
        return str(self) == str(other) and self.index == other.index
    def __ne__(self, other) -> bool:
        return not (self == other)
    def __hash__(self):
        return hash(str(self) + str(self.index))

class Mordred(EvilRole):
    def __str__(self) -> str:
        return "Mordred"

class Morgana(EvilRole):
    def __str__(self) -> str:
        return "Morgana"

class Maelegant(EvilRole):
    def __str__(self) -> str:
        return "Maelegant"

class Agravaine(EvilRole):
    def __str__(self) -> str:
        return "Agravaine"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        if balin in game:
            info['balin'] = game[balin]
        return info


class Colgrevance(EvilRole):
    def __str__(self) -> str:
        return "Colgrevance"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        # Every Evil role Colgrevance could see (Oberon included), by role.
        evil_roles = [role for role in game if role != colgrevance and (
            role.allegiance() == "Evil" and not isinstance(role, Gareth)
            or isinstance(role, Gareth) and game.rules.gareth(role.team, 'evil_sees'))]
        player_roles = {}
        for role in evil_roles:
            player_roles[game[role]] = role

        info['evil_roles'] = player_roles
        return info


class Oberon(EvilRole):
    def __str__(self) -> str:
        return "Oberon"
    def get_info(self, game: AvalonBuilder) -> dict:
          info = super().get_info(game)
          info['oberon'] = False
          return info

class Gareth(Role):
    """Only in 9-player games, on top of the Evil players. Joins the team of a random player (the
    Knight); a random player of the other team is the Rival. Gareth doesn't
    know their own team. `team` is None until the builder decides it."""
    team : str | None
    knight : str | None
    rival : str | None
    def __init__(self, team : str | None = None,
                 knight : str | None = None, rival : str | None = None):
        self.team = team
        self.knight = knight
        self.rival = rival
    def __str__(self) -> str:
        return "Gareth"
    def allegiance(self) -> str:
        return self.team or "none"
    def get_info(self, game : AvalonBuilder) -> dict:
        # No Nilrem, no fellow Evil: anything more would reveal the team.
        knows = game.rules['Gareth.knows']
        info = {'allegiance': 'Unknown'}
        if knows in ('both', 'knight'):
            info['knight'] = self.knight
        if knows in ('both', 'rival'):
            info['rival'] = self.rival
        return info

class NeutralRole(Role):
    def allegiance(self) -> str:
        return "Neutral"


class Pellinore(NeutralRole):
    def __str__(self) -> str:
        return "Pellinore"


class TheBeast(NeutralRole):
    def __str__(self) -> str:
        return "The Questing Beast"

    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        info['pellinore'] = game[pellinore]
        return info



percival = Percival()
galahad = Galahad()
merlin = Merlin()
tristan = Tristan()
iseult = Iseult()
uther = Uther()
arthur = Arthur()
lancelot = Lancelot()
guinevere = Guinevere()
ygraine = Ygraine()
gawain = Gawain()
nilrem = Nilrem()
balin = Balin()

mordred = Mordred()
morgana = Morgana()
maelegant = Maelegant()
agravaine = Agravaine()
colgrevance = Colgrevance()
oberon = Oberon()

gareth = Gareth()

pellinore = Pellinore()
beast = TheBeast()

all_roles = [
            percival, 
            galahad, 
            merlin, 
            tristan, 
            iseult, 
            uther, 
            arthur, 
            lancelot, 
            guinevere, 
            ygraine, 
            gawain, 
            nilrem, 
            balin,
            
            mordred, 
            morgana, 
            maelegant, 
            agravaine, 
            colgrevance, 
            oberon, 

            gareth,

            pellinore, 
            beast, 
        ]

string_to_role : dict[str, Role] = { str(role): role for role in all_roles }

def convert_strings_to_roles(str_roles : list[str]):
    return [string_to_role[str_role] for str_role in str_roles]

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

def generate_roles(num_players : int, base_roles : list[Role],
                   num_evils : int | None = None,
                   rules : RuleSet | None = None) -> list[Role]:
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

    roles_in_play.extend(random.sample(goods, num_goods))
    roles_in_play.extend(random.sample(evils, num_evils))

    random.shuffle(roles_in_play)
    print(roles_in_play)
    return roles_in_play

class AvalonBuilder:
    players : list[str]
    role_to_player : dict[Role,str]
    rules : RuleSet = DEFAULT_RULES     # what roles see; read by Role.get_info

    def __init__(self, players: list[str], roles_in_play : list[Role],
                 num_evils : int | None = None, rules : RuleSet | None = None):
        self.rules = rules or DEFAULT_RULES
        players = list(set(players))
        random.shuffle(players)
        self.players = players

        n = len(players)
        assert(5 <= n <= 12)
        roles = generate_roles(n, roles_in_play, num_evils, self.rules)
        self.role_to_player = {}

        for (player, role) in zip(players, roles):
            self[role] = player
        self.transform_lonely_roles(roles)
        if gareth in self:
            self.choose_gareth_team()

    def __contains__(self, role : Role) -> bool:
        return role in self.role_to_player

    def __iter__(self):
        return iter(self.role_to_player)

    def get_first_mission_proposers(self) -> list[str]:
        return [self.players[0], self.players[1]]
    def get_second_mission_starter(self) -> str:
        return self.players[2]

    def __getitem__(self, role : Role) -> str:
        return self.role_to_player[role]
    def __setitem__(self, role : Role, player : str):
        self.role_to_player[role] = player
    def pop(self, role : Role) -> str:
        return self.role_to_player.pop(role)

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
        knight = random.choice(teams["Good"] + teams["Evil"])
        team = "Good" if knight in teams["Good"] else "Evil"
        rival = random.choice(teams["Evil" if team == "Good" else "Good"])
        self[Gareth(team, knight, rival)] = player

    def get_players_with_roles(self, roles : list[Role]) -> list[str]:
        players = [self[role] for role in roles if role in self]
        random.shuffle(players)
        return players



if __name__ == "__main__":
    players = sys.argv[1:]
    game = AvalonBuilder(players, all_roles)
    exit(0)

