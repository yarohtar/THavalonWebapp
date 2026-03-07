#!/usr/bin/env python3

from __future__ import annotations
import random
import sys

class Role:
    def __str__(self) -> str:
        assert(False)

    def get_info(self, game : Avalon) -> dict:
        return {}

    def allegiance(self) -> str:
        return "none"
    def transform_if_lonely(self, game : Avalon) -> Role:
        return self
    def can_appear(self, num_players : int) -> bool:
        return True

    def __eq__(self, other) -> bool:
        return str(self) == str(other)
    def __ne__(self, other) -> bool:
        return str(self) != str(other)

    def __hash__(self):
        return hash(str(self))

class GoodRole(Role):
    def allegiance(self)->str:
        return "Good"

class Percival(GoodRole):
    def __str__(self) -> str:
        return "Percival"

    def get_info(self, game : Avalon) -> dict:
        seen = game.get_players_with_roles([merlin,morgana])
        return {'seen' : seen }

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
        return {'evil_roles' : [role for role in game if role.allegiance()=="Evil"]}

class Merlin(GoodRole):
    def __str__(self) -> str:
        return "Merlin"
    def get_info(self, game: Avalon) -> dict:
        evils = [game[role] for role in game if role.allegiance() == "Evil" and role != mordred]
        if lancelot in game:
            evils.append(game[lancelot])
        random.shuffle(evils)
        return {'seen' : evils}

class Tristan(GoodRole):
    def __str__(self)->str:
        return "Tristan"
    def get_info(self, game: Avalon) -> dict:
        if iseult not in game:
            return {'lover': 'unloved'}
        return {'lover': game[iseult]}

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
        if tristan not in game:
            return {'lover': 'unloved'}
        return {'lover': game[tristan]}

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
        other_goods = [role for role in game if role.allegiance() == "Good" and role != uther]
        stalked_role = random.sample(other_goods, 1)[0]
        return {'stalked_good' : game[stalked_role]}

class Arthur(GoodRole):
    def __str__(self) -> str:
        return "Arthur"
    def get_info(self, game: Avalon) -> dict:
        return {'good_roles': [role for role in game if role.allegiance()=="Good"]}

class Lancelot(GoodRole):
    def __str__(self) -> str:
        return "Lancelot"

class Guinevere(GoodRole):
    def __str__(self) -> str:
        return "Guinevere"

    def get_info(self, game: Avalon) -> dict:
        seen = game.get_players_with_roles([lancelot, arthur, maelegant])
        return {'seen': seen}

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
        evils = [role for role in game if role.allegiance() == "Evil"]
        stalked_role = random.sample(evils, 1)[0]
        return {'stalked_evil' : game[stalked_role]}

class Gawain(GoodRole):
    def __str__(self) -> str:
        return "Gawain"
    def get_info(self, game: Avalon) -> dict:
        goods = [role for role in game if role.allegiance() == "Good" and role != gawain]
        good_role_seen = random.sample(goods,1)[0]
        everyone_else = [role for role in game if role != gawain and role != good_role_seen]
        seen = random.sample(everyone_else, 2)
        seen.append(good_role_seen)
        random.shuffle(seen)
        seen_players = [game[role] for role in seen]
        return {'seen' : seen_players }

    def can_appear(self, num_players: int) -> bool:
        return num_players >= 10

class EvilRole(Role):
    def allegiance(self)-> str:
        return "Evil"

    def get_visible_evils(self, game : Avalon) -> list[str]:
        evil_roles = [role for role in game 
                if role != self and role != oberon and role.allegiance()=="Evil"]
        return game.get_players_with_roles(evil_roles)

    def get_info(self, game: Avalon) -> dict:
        return {'other_evils' : self.get_visible_evils(game), 
                'oberon' : oberon in game }

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

    def can_appear(self, num_players: int) -> bool:
        return num_players >= 7

class Colgrevance(EvilRole):
    def __str__(self) -> str:
        return "Colgrevance"
    def get_info(self, game: Avalon) -> dict:
        evil_roles = [role for role in game if role.allegiance() == "Evil" and role != colgrevance]
        player_roles = {}
        for role in evil_roles:
            player_roles[game[role]] = role

        return {'evil_roles' : player_roles }

    def can_appear(self, num_players: int) -> bool:
        return num_players >= 7

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
        return { 'pelinor' : game[pellinore] }

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

mordred = Mordred()
morgana = Morgana()
maelegant = Maelegant()
agravaine = Agravaine()
colgrevance = Colgrevance()
oberon = Oberon()

pellinore = Pellinore()
beast = TheBeast()

base_roles : list[Role] = [percival, merlin, tristan, iseult, arthur, lancelot, guinevere, gawain, mordred, morgana, maelegant, agravaine, colgrevance, oberon]

def generate_roles(num_players : int) -> list[Role]:
    possible_roles = [role for role in base_roles if role.can_appear(num_players)]
    goods = [role for role in possible_roles if role.allegiance() == "Good"]
    evils = [role for role in possible_roles if role.allegiance() == "Evil"]

    num_evils = (2 if num_players <= 6 
                 else 3 if num_players <= 9 
                 else 4 if num_players <= 11
                 else 5)
    num_goods = num_players - num_evils

    roles_in_play : list[Role] = []
    if num_players == 9:
        num_goods -= 2
        roles_in_play.append(pellinore)
        roles_in_play.append(beast)

    roles_in_play.extend(random.sample(goods, num_goods))
    roles_in_play.extend(random.sample(evils, num_evils))

    random.shuffle(roles_in_play)
    return roles_in_play

class Avalon:
    players : list[str]
    num_of_players : int
    role_to_player : dict[Role,str]

    def __init__(self, players: list[str]):
        players = list(set(players))
        random.shuffle(players)
        self.players = players
        self.num_of_players = len(players)
        assert(5 <= self.num_of_players <= 12)
        roles = generate_roles(self.num_of_players)
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
    game = Avalon(players)
    exit(0)

