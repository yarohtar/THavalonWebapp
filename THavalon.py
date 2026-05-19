#!/usr/bin/env python3

from __future__ import annotations
import random
import sys

class Role:
    def __str__(self) -> str:
        assert(False)

    def get_info(self, game : Avalon) -> dict:
        return {'allegiance': self.allegiance()}

    def allegiance(self) -> str:
        return "none"
    def transform_if_lonely(self, game : Avalon) -> Role:
        return self
    def can_appear(self, num_players : int) -> bool:
        return True

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
    def get_info(self, game : Avalon) -> dict:
        info = super().get_info(game)
        if nilrem in game:
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

    def get_info(self, game : Avalon) -> dict:
        info = super().get_info(game)
        seen = game.get_players_with_roles([merlin,morgana])
        info['seen'] = seen
        return info

    def transform_if_lonely(self, game : Avalon) -> Role:
        n = game.num_of_players
        if n < 7:
            return self
        if merlin in game or morgana in game:
            return self
        return galahad

class Galahad(GoodRole):
    def __str__(self) -> str:
        return "Galahad"
    def get_info(self, game : Avalon) -> dict:
        info = super().get_info(game)
        info['evil_roles'] = [role for role in game if role.allegiance()=="Evil"]
        return info
    def is_base_role(self) -> bool:
        return False

class Merlin(GoodRole):
    def __str__(self) -> str:
        return "Merlin"
    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        evils = [game[role] for role in game 
                if role.allegiance() == "Evil" and role != mordred]
        if lancelot in game:
            evils.append(game[lancelot])
        if balin in game:
            evils.append(game[balin])
        random.shuffle(evils)
        info['seen'] = evils
        return info
    def transform_if_lonely(self, game: Avalon) -> Role:
        if game.num_of_players < 7:
            return self
        if percival not in game:
            return nilrem
        return self

class Tristan(GoodRole):
    def __str__(self)->str:
        return "Tristan"
    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        if iseult not in game:
            info['lover'] = 'unloved'
            return info
        info['lover'] = game[iseult]
        return info

    def transform_if_lonely(self, game: Avalon) -> Role:
        if game.num_of_players < 7: 
            return self
        if iseult not in game:
            return uther
        return self

class Iseult(GoodRole):
    def __str__(self) -> str:
        return "Iseult"
    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        if tristan not in game:
            info['lover'] = 'unloved'
            return info
        info['lover'] = game[tristan]
        return info

    def transform_if_lonely(self, game: Avalon) -> Role:
        if game.num_of_players < 7: 
            return self
        if tristan not in game:
            return uther
        return self

class Uther(GoodRole):
    def __str__(self) -> str:
        return "Uther"
    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        other_goods = [role for role in game if role.allegiance() == "Good" and role != uther]
        stalked_role = random.sample(other_goods, 1)[0]
        info['stalked_good'] = game[stalked_role]
        return info
    def is_base_role(self) -> bool:
        return False

class Arthur(GoodRole):
    def __str__(self) -> str:
        return "Arthur"
    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        info['good_roles'] = [role for role in game if role.allegiance()=="Good"]
        return info

class Lancelot(GoodRole):
    def __str__(self) -> str:
        return "Lancelot"

class Guinevere(GoodRole):
    def __str__(self) -> str:
        return "Guinevere"

    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        seen = game.get_players_with_roles([lancelot, arthur, maelegant])
        info['seen'] = seen
        return info

    def transform_if_lonely(self, game: Avalon) -> Role:
        if lancelot in game or arthur in game or maelegant in game:
            return self
        return ygraine

    def can_appear(self, num_players: int) -> bool:
        return num_players >= 7

class Ygraine(GoodRole):
    def __str__(self) -> str:
        return "Ygraine"
    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        evils = [role for role in game if role.allegiance() == "Evil"]
        stalked_role = random.sample(evils, 1)[0]
        info['stalked_evil'] = game[stalked_role]
        return info
    def is_base_role(self) -> bool:
        return False

class Gawain(GoodRole):
    def __str__(self) -> str:
        return "Gawain"
    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        goods = [role for role in game if role.allegiance() == "Good" and role != gawain]
        good_role_seen = random.sample(goods,1)[0]
        everyone_else = [role for role in game if role != gawain and role != good_role_seen]
        seen = random.sample(everyone_else, 2)
        seen.append(good_role_seen)
        random.shuffle(seen)
        seen_players = [game[role] for role in seen]
        info['seen'] = seen_players
        return info

    def can_appear(self, num_players: int) -> bool:
        return num_players >= 10

class Nilrem(GoodRole):
    def __str__(self) -> str:
        return "Nilrem"
    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        info.pop('nilrem', None)
        return info
    def can_appear(self, num_players: int) -> bool:
        return num_players >= 7
    def is_base_role(self) -> bool:
        return False

class Balin(GoodRole):
    def __str__(self) -> str:
        return "Balin the Savage"
    def get_info(self, game : Avalon) -> dict:
        info = super().get_info(game)
        if agravaine in game:
            info['agravaine'] = game[agravaine]
        return info
    def can_appear(self, num_players: int) -> bool:
        return num_players == 6 or num_players == 9

class EvilRole(Role):
    def allegiance(self)-> str:
        return "Evil"

    def get_visible_evils(self, game : Avalon) -> list[str]:
        evil_roles = [role for role in game 
                if role != self and role != oberon and role.allegiance()=="Evil"]
        return game.get_players_with_roles(evil_roles)

    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        info['other_evils'] = self.get_visible_evils(game)
        info['oberon'] = oberon in game
        return info

class MoM(EvilRole):
    index : int
    def __init__(self, index : int):
        self.index = index
    def __str__(self) -> str:
        return "Minion of Mordred"
    def __eq__(self, other) -> bool:
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
    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        if balin in game:
            info['balin'] = game[balin]
        return info

    def can_appear(self, num_players: int) -> bool:
        return num_players >= 7

class Colgrevance(EvilRole):
    def __str__(self) -> str:
        return "Colgrevance"
    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        evil_roles = [role for role in game if role.allegiance() == "Evil" and role != colgrevance]
        player_roles = {}
        for role in evil_roles:
            player_roles[game[role]] = role

        info['evil_roles'] = player_roles
        return info

    def can_appear(self, num_players: int) -> bool:
        return num_players >= 10

class Oberon(EvilRole):
    def __str__(self) -> str:
        return "Oberon"
    def get_info(self, game: Avalon) -> dict:
          info = super().get_info(game)
          info['oberon'] = False
          return info

class NeutralRole(Role):
    def allegiance(self) -> str:
        return "Neutral"


class Pellinore(NeutralRole):
    def __str__(self) -> str:
        return "Pellinore"

    def can_appear(self, num_players: int) -> bool:
        return num_players == 9

class TheBeast(NeutralRole):
    def __str__(self) -> str:
        return "The Questing Beast"

    def get_info(self, game: Avalon) -> dict:
        info = super().get_info(game)
        info['pellinore'] = game[pellinore]
        return info

    def can_appear(self, num_players: int) -> bool:
        return num_players == 9


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
            
            pellinore, 
            beast, 
        ]

string_to_role : dict[str, Role] = { str(role): role for role in all_roles }

def convert_strings_to_roles(str_roles : list[str]):
    return [string_to_role[str_role] for str_role in str_roles]

def generate_roles(num_players : int, base_roles : list[Role]) -> list[Role]:
    base_roles = [role for role in base_roles if role.is_base_role()]
    possible_roles = [role for role in base_roles if role.can_appear(num_players)]
    goods = [role for role in possible_roles if role.allegiance() == "Good"]
    evils = [role for role in possible_roles if role.allegiance() == "Evil"]

    num_evils = (2 if num_players <= 6 
                 else 3 if num_players <= 8
                 else 4 if num_players <= 11
                 else 5)
    num_goods = num_players - num_evils

    roles_in_play : list[Role] = []
    if pellinore in possible_roles and beast in possible_roles:
        num_goods -= 2
        roles_in_play.append(pellinore)
        roles_in_play.append(beast)

    if balin in possible_roles:
        num_goods -= 1
        roles_in_play.append(balin)

    if len(goods) < num_goods:
        goods.extend([SoC(i) for i in range(num_goods - len(goods))])
    if len(evils) < num_evils:
        evils.extend([MoM(i) for i in range(num_evils - len(evils))])

    roles_in_play.extend(random.sample(goods, num_goods))
    roles_in_play.extend(random.sample(evils, num_evils))

    random.shuffle(roles_in_play)
    return roles_in_play

class Avalon:
    players : list[str]
    num_of_players : int
    role_to_player : dict[Role,str]

    def __init__(self, players: list[str], roles_in_play : list[Role]):
        players = list(set(players))
        random.shuffle(players)
        self.players = players
        self.num_of_players = len(players)
        assert(5 <= self.num_of_players <= 12)
        roles = generate_roles(self.num_of_players, roles_in_play)
        self.role_to_player = {}

        for (player, role) in zip(players, roles):
            self[role] = player
        for role in roles:
            self.transform_lonely(role)

    def __contains__(self, role : Role) -> bool:
        return str(role) in self.role_to_player

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

    def transform_lonely(self, role : Role):
        self[role.transform_if_lonely(self)] = self.pop(role)

    def get_players_with_roles(self, roles : list[Role]) -> list[str]:
        players = [self[role] for role in roles if role in self]
        random.shuffle(players)
        return players

if __name__ == "__main__":
    players = sys.argv[1:]
    game = Avalon(players, all_roles)
    exit(0)

