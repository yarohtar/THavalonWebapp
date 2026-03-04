#!/usr/bin/env python3

from __future__ import annotations
import os
import random
import shutil
import sys
from types import new_class
from typing import Literal

class Role:
    def __str__(self) -> str:
        assert(False)

    def get_info_str(self, game : Avalon) -> str:
        return "noinfo"
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

    def full_description(self, game : Avalon) -> str:
        res = f"You are {str(self)}.\n\n"
        res += self.get_info_str(game)
        return res

    def write_to_file(self, game : Avalon):
        filename = "game/" + game[self]
        with open(filename, "w") as file:
            file.write(self.full_description(game))

class GoodRole(Role):
    def allegiance(self)->str:
        return "Good"

class Percival(GoodRole):
    def __str__(self) -> str:
        return "Percival"

    def get_info(self, game : Avalon) -> dict:
        seen = game.get_players_with_roles([merlin,morgana])
        return {'seen' : seen }

    def get_info_str(self, game : Avalon) -> str:
        percival_sess = game.get_players_with_roles([merlin, morgana])
        if len(percival_sess) == 0:
            return "Merlin and Morgana are not in this game\n"
        res = ""
        for person in percival_sess:
            res += f"You see {person} as Merlin or Morgana\n"
        return res
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

    def get_info_str(self, game : Avalon) -> str:
        res = "Merlin and Morgana are not in this game.\n\n"
        evils = [str(role) for role in game if role.allegiance() == "Evil"]
        res += f"Evil roles present in the game are {evils}.\n"
        return res

class Merlin(GoodRole):
    def __str__(self) -> str:
        return "Merlin"
    def get_info(self, game: Avalon) -> dict:
        evils = [game[role] for role in game if role.allegiance() == "Evil" and role != mordred]
        if lancelot in game:
            evils.append(game[lancelot])
        random.shuffle(evils)
        return {'seen' : evils}

    def get_info_str(self, game : Avalon) -> str:
        evils = [role for role in game if role.allegiance() == "Evil" and role != mordred]
        if lancelot in game:
            evils.append(lancelot)
        evil_players = [game[role] for role in evils]
        random.shuffle(evil_players)
        res = f"You see {evil_players} as evil.\n"
        res += "If Mordred is present, you didn't see them as evil.\n"
        res += "If Lancelot is present, you see them as evil.\n"
        return res

class Tristan(GoodRole):
    def __str__(self)->str:
        return "Tristan"
    def get_info(self, game: Avalon) -> dict:
        if iseult not in game:
            return {'lover': 'unloved'}
        return {'lover': game[iseult]}

    def get_info_str(self, game : Avalon) -> str:
        if iseult not in game:
            return "Nobody loves you. Iseult is not in this game.\n"
        lover = game[iseult]
        return f"{lover} is Iseult, your lover.\n"

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
    def get_info_str(self, game : Avalon) -> str:
        if tristan not in game:
            return "Nobody loves you. Iseult is not in this game."
        lover = game[tristan]
        return f"{lover} is Tristan, your lover.\n"

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

    def get_info_str(self, game : Avalon) -> str:
        res = "Nobody loves you. Tristan and Iseult are not in this game\n"
        other_goods = [role for role in game if role.allegiance() == "Good" and role != uther]
        stalked_role = random.sample(other_goods, 1)[0]
        stalked_player = game[stalked_role]
        res += f"You are stalking {stalked_player}; they are also good.\n"
        return res

class Arthur(GoodRole):
    def __str__(self) -> str:
        return "Arthur"
    def get_info(self, game: Avalon) -> dict:
        return {'good_roles': [role for role in game if role.allegiance()=="Good"]}
    def get_info_str(self, game : Avalon) -> str:
        goods = [str(role) for role in game if role.allegiance() == "Good"]
        return f"Good roles in the game are {goods}.\n"

class Lancelot(GoodRole):
    def __str__(self) -> str:
        return "Lancelot"
    def get_info_str(self, game : Avalon) -> str:
        res = "You may play Reversal cards when sent on missions.\n\n"
        res += "If Merlin is in the game, they see you as Evil.\n"
        return res

class Guinevere(GoodRole):
    def __str__(self) -> str:
        return "Guinevere"
    def get_info(self, game: Avalon) -> dict:
        seen = game.get_players_with_roles([lancelot, arthur, maelegant])
        return {'seen': seen}
    def get_info_str(self, game : Avalon) -> str:
        sees = game.get_players_with_roles([lancelot, arthur, maelegant])
        if len(sees) == 0:
            return "ERROR"
        res = ""
        for player in sees:
            res += (f"You see {player} as either your luscious Lancelot, "
                    "your lawfully wedded Arthur, or your kidnapper Maelegant.\n")
        return res
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

    def get_info_str(self, game : Avalon) -> str:
        evils = [role for role in game if role.allegiance() == "Evil"]
        stalked_role = random.sample(evils, 1)[0]
        stalked_player = game[stalked_role]
        res = f"You are stalking {stalked_player}; they are Evil.\n"
        res += "Guinevere, Lancelot, Arthur, and Maelegant are not in the game.\n"
        return res

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

    def get_info_str(self, game : Avalon) -> str:
        return f"The players {self.get_info(game)['seen']} are not all evil.\n"

    def can_appear(self, num_players: int) -> bool:
        return num_players == 10

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

    def get_info_str(self, game : Avalon) -> str:
        evils = game.get_players_with_roles([morgana, maelegant, agravaine, colgrevance])
        res = ""
        for player in evils: 
            res += f"{player} is a fellow member of the evil council.\n"
        if oberon in game:
            res += "Oberon is lurking in the shadows.\n"
        res += "\nIf Merlin is in the game, they do not see you as evil.\n"
        return res

class Morgana(EvilRole):
    def __str__(self) -> str:
        return "Morgana"

    def get_info_str(self, game : Avalon) -> str:
        evils = game.get_players_with_roles([mordred, maelegant, agravaine, colgrevance])
        res = ""
        for player in evils: 
            res += f"{player} is a fellow member of the evil council.\n"
        if oberon in game:
            res += "Oberon is lurking in the shadows.\n"
        return res

class Maelegant(EvilRole):
    def __str__(self) -> str:
        return "Maelegant"
    def get_info_str(self, game : Avalon) -> str:
        evils = game.get_players_with_roles([mordred, morgana, agravaine, colgrevance])
        res = "You may play Reversal cards when sent on missions.\n\n"
        for player in evils: 
            res += f"{player} is a fellow member of the evil council.\n"
        if oberon in game:
            res += "Oberon is lurking in the shadows.\n"
        return res

class Agravaine(EvilRole):
    def __str__(self) -> str:
        return "Agravaine"
    def get_info_str(self, game : Avalon) -> str:
        evils = game.get_players_with_roles([mordred, morgana, maelegant, colgrevance])
        res = "You have to play Fail cards if you are on a mission.\n\n"
        for player in evils: 
            res += f"{player} is a fellow member of the evil council.\n"
        if oberon in game:
            res += "Oberon is lurking in the shadows.\n"
        return res
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

    def get_info_str(self, game : Avalon) -> str:
        evil_roles = [role for role in game if role.allegiance() == "Evil" and role != colgrevance]
        res = ""
        for role in evil_roles:
            player = game[role]
            res += f"{player} is {role}, a fellow member of the evil council.\n"
        return res
    def can_appear(self, num_players: int) -> bool:
        return num_players >= 7

class Oberon(EvilRole):
    def __str__(self) -> str:
        return "Oberon"
    def get_info(self, game: Avalon) -> dict:
          info = super().get_info(game)
          info['oberon'] = False
          return info

    def get_info_str(self, game : Avalon) -> str:
        evils = game.get_players_with_roles([mordred, morgana, maelegant, agravaine, colgrevance])
        res = "You are not seen by other evil.\n\n"
        for player in evils: 
            res += f"{player} is a fellow member of the evil council.\n"
        return res


class NeutralRole(Role):
    def allegiance(self) -> str:
        return "Neutral"


class Pellinore(NeutralRole):
    def __str__(self) -> str:
        return "Pellinore"
    def get_info_str(self, game : Avalon) -> str:
        return ""
    def can_appear(self, num_players: int) -> bool:
        return num_players == 9

class TheBeast(NeutralRole):
    def __str__(self) -> str:
        return "The Questing Beast"
    def get_info(self, game: Avalon) -> dict:
        return { 'pelinor' : game[pellinore] }
    def get_info_str(self, game: Avalon) -> str:
        hunter = game[pellinore]
        return f"You are being hunted by {hunter}.\n"
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

    num_evils = 2 if num_players <= 6 else 3 if num_players <= 9 else 4
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
        assert(5 <= self.num_of_players <= 10)
        roles = generate_roles(self.num_of_players)
        self.role_to_player = {}

        for (player, role) in zip(players, roles):
            self[role] = player
        for role in roles:
            self.transform_lonely(role)

        self.write_files()
        
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

    def write_files(self):
        for role in self:
            role.write_to_file(self)
        with open("game/donotread", "w") as file:
            file.write(str(self.role_to_player))
            file.write(str(self.players))

if __name__ == "__main__":
    players = sys.argv[1:]
    game = Avalon(players)
    game.write_files()
    exit(0)





def main():
	if not (6 <= len(sys.argv) <= 11):
		print("Invalid number of players")
		exit(1)

	players = sys.argv[1:]
	num_players = len(players)
	players = set(players) # use as set to avoid duplicate players
	players = list(players) # convert to list
	random.shuffle(players) # ensure random order, though set should already do that
	if len(players) != num_players:
		print("No duplicate player names")
		exit(1)

	# choose 3 players
	three_players = random.sample(players, 3)

	# first two proppose for the first mission, last is starting player of second round
	first_mission_proposers = three_players[:2]
	second_mission_starter = three_players[2]

	all_good_roles_in_order = ["Percival", "Merlin", "Galahad", "Tristan", "Iseult", "Uther", "Arthur", "Lancelot", "Guinevere", "Ygraine", "Gawain"]
	all_evil_roles_in_order = ["Mordred", "Morgana", "Maelegant", "Agravaine", "Colgrevance", "Oberon"]

	# assign the roles in the game
	good_roles = ["Merlin", "Percival", "Tristan", "Iseult"]
	evil_roles = ["Mordred", "Morgana"]

	good_roles.append("Lancelot")
	evil_roles.append("Maelegant")


	if num_players >= 7:
		good_roles.append("Guinevere")
		good_roles.append("Arthur")
		evil_roles.append("Agravaine")
		evil_roles.append("Colgrevance")
		if num_players != 9:
			evil_roles.append("Oberon")

	if num_players == 10:
		good_roles.append("Gawain")

	# shuffle the roles
	random.shuffle(good_roles)
	random.shuffle(evil_roles)

	# determine the number of roles in the game
	if num_players == 10:
		num_evil = 4
		num_good = 6
	elif num_players == 9:
		num_evil  = 3
		num_good = 4
	elif num_players == 7 or num_players == 8:
		num_evil = 3
		num_good = num_players - num_evil
	else: # 5 or 6
		num_evil = 2
		num_good = num_players - num_evil

	# assign players to teams
	assignments = {}
	reverse_assignments = {}
	good_roles_in_game = set()
	evil_roles_in_game = set()

	if num_players == 9:
		pelinor = players[8]
		assignments[pelinor] = "Pelinor"
		reverse_assignments["Pelinor"] = pelinor

		questing_beast = players[7]
		assignments[questing_beast] = "Questing Beast"
		reverse_assignments["Questing Beast"] = questing_beast

	good_players = players[:num_good]
	evil_players = players[num_good:num_good + num_evil]


	# assign good roles
	for good_player in good_players:
		player_role = good_roles.pop()
		assignments[good_player] = player_role
		reverse_assignments[player_role] = good_player
		good_roles_in_game.add(player_role)

	# assign evil roles
	for evil_player in evil_players:
		player_role = evil_roles.pop()
		assignments[evil_player] = player_role
		reverse_assignments[player_role] = evil_player
		evil_roles_in_game.add(player_role)
	
	# lone tristan
	if ("Tristan" in good_roles_in_game and "Iseult" not in good_roles_in_game and num_players >= 7):
		good_roles_in_game.remove("Tristan")
		good_roles_in_game.add("Uther")
		tristan_player = reverse_assignments["Tristan"]
		assignments[tristan_player] = "Uther" 
		del reverse_assignments["Tristan"]
		reverse_assignments["Uther"] = tristan_player
	
	# lone iseult
	if ("Iseult" in good_roles_in_game and "Tristan" not in good_roles_in_game and num_players >= 7):
		good_roles_in_game.remove("Iseult")
		good_roles_in_game.add("Uther")
		iseult_player = reverse_assignments["Iseult"]
		assignments[iseult_player] = "Uther" 
		del reverse_assignments["Iseult"]
		reverse_assignments["Uther"] = iseult_player
	
	# lone guinevere -> ygraine
	if ("Guinevere" in good_roles_in_game and "Lancelot" not in good_roles_in_game and "Arthur" not in good_roles_in_game and "Maelegant" not in evil_roles_in_game and num_players >= 7):
		good_roles_in_game.remove("Guinevere")
		good_roles_in_game.add("Ygraine")
		guinevere_player = reverse_assignments["Guinevere"]
		assignments[guinevere_player] = "Ygraine" 
		del reverse_assignments["Guinevere"]
		reverse_assignments["Ygraine"] = guinevere_player
	
	# lone percival -> galahad
	if ("Percival" in good_roles_in_game and "Merlin" not in good_roles_in_game and "Morgana" not in evil_roles_in_game and num_players >= 7):
		good_roles_in_game.remove("Percival")
		good_roles_in_game.add("Galahad")
		percival_player = reverse_assignments["Percival"]
		assignments[percival_player] = "Galahad" 
		del reverse_assignments["Percival"]
		reverse_assignments["Galahad"] = percival_player
	
	# delete and recreate game directory
	if os.path.isdir("game"):
		shutil.rmtree("game")
	os.mkdir("game")

	# make every role's file

	# Merlin sees: Morgana, Maelegant, Oberon, Agravaine, Colgrevance, Lancelot* as evil 
	if "Merlin" in good_roles_in_game:
		# determine who Merlin sees
		seen = []
		for evil_player in evil_players:
			if assignments[evil_player] != "Mordred":
				seen.append(evil_player)
		if "Lancelot" in good_roles_in_game:
			seen.append(reverse_assignments["Lancelot"])
		random.shuffle(seen)

		# and write this info to Merlin's file
		player_name = reverse_assignments["Merlin"]
		filename = "./game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Merlin.\n")
			for seen_player in seen:
				file.write("You see " + seen_player + " as evil.\n")

	# Percil sees Merlin, Morgana* as Merlin
	if "Percival" in good_roles_in_game:
		# determine who Percival sees
		seen = []
		if "Merlin" in good_roles_in_game:
			seen.append(reverse_assignments["Merlin"])
		if "Morgana" in evil_roles_in_game:
			seen.append(reverse_assignments["Morgana"])
		random.shuffle(seen)

		# and write this info to Percival's file
		player_name = reverse_assignments["Percival"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Percival.\n")
			for seen_player in seen:
				file.write("You see " + seen_player + " as Merlin (or is it...?).\n")

	if "Tristan" in good_roles_in_game:
		# write the info to Tristan's file
		player_name = reverse_assignments["Tristan"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Tristan.\n")
			# write Iseult's info to file
			if "Iseult" in good_roles_in_game:
				iseult_player = reverse_assignments["Iseult"]
				file.write(iseult_player + " is your lover.\n")
			else: 
				file.write("Nobody loves you. Not even your cat.\n")

	if "Iseult" in good_roles_in_game:
		# write this info to Iseult's file
		player_name = reverse_assignments["Iseult"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Iseult.\n")
			# write Tristan's info to file
			if "Tristan" in good_roles_in_game:
				tristan_player = reverse_assignments["Tristan"]
				file.write(tristan_player + " is your lover.\n")
			else: 
				file.write("Nobody loves you.\n")

	if "Lancelot" in good_roles_in_game: 
		# write ability to Lancelot's file 
		player_name = reverse_assignments["Lancelot"] 
		filename = "game/" + player_name 
		with open(filename, "w") as file:
			file.write("You are Lancelot. You are on the Good team. \n\n") 
			file.write("Ability: Reversal \n")	
			file.write("You are able to play Reversal cards while on missions. A Reversal card inverts the result of a mission; a mission that would have succeeded now fails and vice versa. \n \n")
			file.write("Note: In games with at least 7 players, a Reversal played on the 4th mission results in a failed mission if there is only one Fail card, and otherwise succeeds. Reversal does not interfere with Agravaine's ability to cause the mission to fail\n")

	if "Guinevere" in good_roles_in_game:
		# determine who Guinevere sees
		seen = []
		if "Arthur" in good_roles_in_game:
			seen.append(reverse_assignments["Arthur"])
		if "Maelegant" in evil_roles_in_game:
			seen.append(reverse_assignments["Maelegant"])
		if "Lancelot" in good_roles_in_game:
			seen.append(reverse_assignments["Lancelot"])
		random.shuffle(seen)

		# and write this info to Guinevere's file
		player_name = reverse_assignments["Guinevere"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Guinevere.\n")
			for seen_player in seen:
				file.write("You see " + seen_player + " as either your luscious Lancelot, your lawfully wedded Arthur, or your kidnapper Maelegant.\n")

	if "Arthur" in good_roles_in_game:
		# determine which roles Arthur sees
		seen = []
		for good_role in good_roles_in_game:
			seen.append(good_role)
		random.shuffle(seen)

		# and write this info to Arthur's file
		player_name = reverse_assignments["Arthur"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Arthur.\n\n")
			file.write("The following good roles are in the game:\n")
			for seen_role in seen:
				if seen_role != "Arthur":
					file.write(seen_role + "\n")
			file.write("\n")
			file.write("Ability: Proclamation\n")
			file.write("If two missions have failed, you may formally reveal that you are Arthur, establishing that you are Good for the remainder of the game. You may still propose and vote on missions, as well as be chosen to be part of a mission team, as per usual.\n")

	if "Gawain" in good_roles_in_game: 
		# determine what Gawain sees 
		seen = []
		player_name = reverse_assignments["Gawain"]
		good_players_no_gawain = set(good_players) - set([player_name])
		# guaranteed see a good player
		seen_good = random.sample(good_players_no_gawain, 1)
		seen.append(seen_good[0])

		# choose two other players randomly
		remaining_players = set(players) - set([player_name]) - set(seen_good)
		seen += random.sample(remaining_players, 2)

		random.shuffle(seen)
		
		# write info to Gawain's file 
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Gawain.\n\n")
			file.write("The following players are not all evil:\n")
			for seen_player in seen:
				file.write(seen_player + "\n")
			file.write("\nAbility: Whenever a mission (other than the 1st) is sent, you may declare as Gawain to reveal a single person's played mission card. The mission card still affects the mission. (This ability functions identically to weak Inquisition and occurs after regular Inquisitions.) If the card you reveal is a Success, you are immediately 'Exiled' and may not go on missions for the remainder of the game, although you may still vote and propose missions.\n\n")
			file.write("You may use this ability once per mission as long as you are neither on the mission team nor 'Exiled'. You may choose to not use your ability on any round, even if you would be able to use it.\n");

	stalked_good = None;
	
	if "Uther" in good_roles_in_game:
		# write this info to Uther's file
		player_name = reverse_assignments["Uther"]
		filename = "game/" + player_name
		good_players_no_uther = set(good_players) - set([player_name]) 
		stalked_good = random.sample(good_players_no_uther, 1)[0] 
		with open(filename, "w") as file:
			file.write("You are Uther.\n")
			file.write("You are stalking " + stalked_good + "; they are also good.\n")
			# write Uther's info to file
	
	stalked_evil = None;
		
	if "Ygraine" in good_roles_in_game:
		# write this info to Ygraine's file
		player_name = reverse_assignments["Ygraine"]
		filename = "game/" + player_name
		evil_players_no_mordred = set(evil_players) - set(reverse_assignments["Mordred"]) 
		stalked_evil = random.sample(evil_players_no_mordred, 1)[0] 
		with open(filename, "w") as file:
			file.write("You are Ygraine.\n")
			file.write("You are stalking " + stalked_evil + "; they are evil.\n")
			file.write("\n (The following roles are not in the game: Guinevere, Lancelot, Arthur, and Maelegant.)\n")
			
	if "Galahad" in good_roles_in_game:
		# determine which roles Galahad sees
		seen = []
		for evil_role in evil_roles_in_game:
			seen.append(evil_role)
		random.shuffle(seen)

		# and write this info to Arthur's file
		player_name = reverse_assignments["Galahad"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Galahad.\n\n")
			file.write("The following evil roles are in the game:\n")
			for seen_role in seen:
					file.write(seen_role + "\n")
			file.write("\n (The following roles are not in the game: Percival, Merlin, and Morgana.)\n")
			
	# make list of evil players seen to other evil
	if "Oberon" in evil_roles_in_game:
		evil_players_no_oberon = list(set(evil_players) - set([reverse_assignments["Oberon"]]))
	else: 
		evil_players_no_oberon = list(set(evil_players))
		
	random.shuffle(evil_players_no_oberon)

	if "Mordred" in evil_roles_in_game:
		player_name = reverse_assignments["Mordred"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Mordred. (Join us, we have jackets and meet on Thursdays. ~ Andrew and Kath)\n")
			for evil_player in evil_players_no_oberon:
				if evil_player != player_name:
					file.write(evil_player + " is a fellow member of the evil council.\n")
			if "Oberon" in evil_roles_in_game:
				file.write("There is an Oberon lurking in the shadows.\n")

	if "Morgana" in evil_roles_in_game:
		player_name = reverse_assignments["Morgana"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Morgana.\n")
			for evil_player in evil_players_no_oberon:
				if evil_player != player_name:
					file.write(evil_player + " is a fellow member of the evil council.\n")
			if "Oberon" in evil_roles_in_game:
				file.write("There is an Oberon lurking in the shadows.\n")
			file.write("\nAbility: Once per game, when you would propose a mission team, you may declare as Morgana and permanently reverse mission order. The next proposal is granted to the person sitting next to the first proposer of the round. Morgana may NOT use this ablity if they have the last proposal of a round.\n");

	if "Oberon" in evil_roles_in_game:
		player_name = reverse_assignments["Oberon"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Oberon.\n")
			for evil_player in evil_players_no_oberon:
				file.write(evil_player + " is a member of the evil council.\n")	
				
			file.write("\nAbility: Should any mission get to the last proposal of the round, after the people on the mission have been named, you may declare as Oberon to replace one person on that mission with yourself.\n\n")
			file.write("Note: You may not use this ability after two missions have already failed. Furthermore, you may only use this ability once per game.\n")
			file.write("Drawback: The other evil players do not know that you are Evil, only that there is an Oberon present.\n");
			
	if "Agravaine" in evil_roles_in_game:
		player_name = reverse_assignments["Agravaine"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Agravaine.\n")
			for evil_player in evil_players_no_oberon:
				if evil_player != player_name:
					file.write(evil_player + " is a fellow member of the evil council.\n")
			if "Oberon" in evil_roles_in_game:
				file.write("There is an Oberon lurking in the shadows.\n")
				
			file.write("\nAbility: On any mission you are on, after the mission cards have been revealed, should the mission not result in a Fail (such as via a Reversal, requiring 2 fails, or other mechanics), you may formally declare as Agravaine to force the mission to Fail anyway.\n\n");
			file.write("Drawback: You may only play Fail cards while on missions.\n");
			
				
	if "Maelegant" in evil_roles_in_game: 
		# write ability to Lancelot's file 
		player_name = reverse_assignments["Maelegant"] 
		filename = "game/" + player_name 
		with open(filename, "w") as file:
			file.write("You are Maelegant. \n\n") 
			for evil_player in evil_players_no_oberon:
				if evil_player != player_name:
					file.write(evil_player + " is a fellow member of the evil council.\n")
			if "Oberon" in evil_roles_in_game:
				file.write("There is an Oberon lurking in the shadows.\n")
			file.write("\nAbility: Reversal \n")	
			file.write("You are able to play Reversal cards while on missions. A Reversal card inverts the result of a mission; a mission that would have succeeded now fails and vice versa. \n \n")
			file.write("Note: In games with at least 7 players, a Reversal played on the 4th mission results in a failed mission if there is only one Fail card, and otherwise succeeds. Reversal does not interfere with Agravaine's ability to cause the mission to fail.")
			
				
	if "Colgrevance" in evil_roles_in_game:
		player_name = reverse_assignments["Colgrevance"]
		filename = "game/" + player_name
		with open(filename, "w") as file:
			file.write("You are Colgrevance.\n")
			for evil_player in evil_players:
				if evil_player != player_name:
					file.write(evil_player + " is " + assignments[evil_player] + ".\n")

	# TODO: pelinor + questing beast
	if num_players == 9:
		# write pelinor's information
		pelinor_filename = "game/" + pelinor
		with open(pelinor_filename, "w") as file:
			file.write("You are Pelinor.\n\n")
			file.write("You win if one of the following conditions are met:\n")
			file.write("[1]: No Questing Beast Was Here cards are played.\n")
			file.write("[2]: You are on a mission where a Questing Beast Was Here Card is played, and three missions succeed.\n")
			file.write("[3]: If neither of the previous two conditions are met at the end of the game, you declare as Pelinor prior to Assassination and name the person you believe to be the Questing Beast. You are told if you are correct at the conclusion of any other post-game phases. If you are correct, you win.\n")

		questing_beast_filename = "game/" + questing_beast
		with open(questing_beast_filename, "w") as file:
			file.write("You are the Questing Beast.\n")
			file.write("You must play the 'Questing Beast Was Here' card on missions. Once per game, you can play a Success card instead of a Questing Beast Was Here card.\n\n")
			file.write("You win if all of the following conditions are met:\n")
			file.write("[1]: You play at least one Questing Beast Was Here card.\n")
			file.write("[2]: Either a) Pelinor is never on a mission where a Questing Beast Was Here card is played; or b) 3 Quests fail.\n\n")
			file.write("[3]: Pelinor fails to identify you after the conclusion of the game.\n\n")
			file.write(pelinor + " is Pelinor.\n")

#uther
#	if stalked_good: 
#		stalked_good_filename = "game/" + stalked_good 
#		with open(stalked_good_filename, "a") as file: 
#			file.write("\n \n \nYou are being stalked... o.o");
		
	# write start file
	with open("game/start", "w") as file:
		file.write("The players proposing teams for the first mission are:\n")
		for first_mission_proposer in first_mission_proposers:
			file.write(first_mission_proposer + "\n")
		file.write("\n" + second_mission_starter + " is the starting player of the 2nd round.\n")

	# write do not open
	with open("game/DoNotOpen", "w") as file:
		file.write("Player -> Role\n\nGOOD TEAM:\n")
		for role in all_good_roles_in_order:
			if role in reverse_assignments:
				file.write(reverse_assignments[role] + " -> " + role + "\n")
		file.write("\n\nEVIL TEAM:\n")
		for role in all_evil_roles_in_order:
			if role in reverse_assignments:
				file.write(reverse_assignments[role] + " -> " + role + "\n")


if __name__ == "__main__":
	main()
