#!/usr/bin/env python3

from __future__ import annotations
from enum import Enum
import random
import sys
from typing import Literal

class Role:
    def __str__(self) -> str:
        assert(False)

    def get_info(self, game : AvalonBuilder) -> dict:
        return {'allegiance': self.allegiance()}

    def allegiance(self) -> str:
        return "none"
    def transform_if_lonely(self, game : AvalonBuilder) -> Role:
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
    def get_info(self, game : AvalonBuilder) -> dict:
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

    def get_info(self, game : AvalonBuilder) -> dict:
        info = super().get_info(game)
        seen = game.get_players_with_roles([merlin,morgana])
        info['seen'] = seen
        return info

    def transform_if_lonely(self, game : AvalonBuilder) -> Role:
        n = len(game.players)
        if n < 7:
            return self
        if merlin in game or morgana in game:
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
        evils = [game[role] for role in game 
                if role.allegiance() == "Evil" and role != mordred]
        if lancelot in game:
            evils.append(game[lancelot])
        if balin in game:
            evils.append(game[balin])
        random.shuffle(evils)
        info['seen'] = evils
        return info
    def transform_if_lonely(self, game: AvalonBuilder) -> Role:
        if len(game.players) < 7:
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
        if len(game.players) < 7: 
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
        if len(game.players) < 7: 
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
        seen = game.get_players_with_roles([lancelot, arthur, maelegant])
        info['seen'] = seen
        return info

    def transform_if_lonely(self, game: AvalonBuilder) -> Role:
        if lancelot in game or arthur in game or maelegant in game:
            return self
        return ygraine

    def can_appear(self, num_players: int) -> bool:
        return num_players >= 7

class Ygraine(GoodRole):
    def __str__(self) -> str:
        return "Ygraine"
    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        evils = [role for role in game if role.allegiance() == "Evil" and role != mordred]
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
    def get_info(self, game: AvalonBuilder) -> dict:
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
    def get_info(self, game : AvalonBuilder) -> dict:
        info = super().get_info(game)
        if agravaine in game:
            info['agravaine'] = game[agravaine]
        return info
    def can_appear(self, num_players: int) -> bool:
        return num_players == 6 or num_players == 9

class EvilRole(Role):
    def allegiance(self)-> str:
        return "Evil"

    def get_visible_evils(self, game : AvalonBuilder) -> list[str]:
        evil_roles = [role for role in game 
                if role != self and role != oberon and role.allegiance()=="Evil"]
        return game.get_players_with_roles(evil_roles)

    def get_info(self, game: AvalonBuilder) -> dict:
        info = super().get_info(game)
        info['other_evils'] = self.get_visible_evils(game)
        info['oberon'] = oberon in game
        print(info)
        return info

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

    def can_appear(self, num_players: int) -> bool:
        return num_players >= 7

class Colgrevance(EvilRole):
    def __str__(self) -> str:
        return "Colgrevance"
    def get_info(self, game: AvalonBuilder) -> dict:
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
    def get_info(self, game: AvalonBuilder) -> dict:
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

    def get_info(self, game: AvalonBuilder) -> dict:
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

def default_num_evils(num_players : int) -> int:
    return (2 if num_players <= 6
            else 3 if num_players <= 8
            else 4 if num_players <= 11
            else 5)

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
                   num_evils : int | None = None) -> list[Role]:
    base_roles = [role for role in base_roles if role.is_base_role()]
    possible_roles = [role for role in base_roles if role.can_appear(num_players)]
    goods = [role for role in possible_roles if role.allegiance() == "Good"]
    evils = [role for role in possible_roles if role.allegiance() == "Evil"]

    if num_evils is None:
        num_evils = default_num_evils(num_players)
    num_goods = num_players - num_evils

    roles_in_play : list[Role] = []
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

class RoleInfo:
    info : dict
    def __init__(self, role : Role, game : AvalonBuilder):
        self.info = role.get_info(game)
        self.info['role'] = str(role)
    def __getitem__(self, key : str):
        return self.info[key]
    def __contains__(self, key : str):
        return key in self.info

class VotingCards(Enum):
    Success = "Success"
    Fail = "Fail"
    Reverse = "Reverse"
    QuestingBeast = "QuestingBeast"

class Vote[VotingType]:
    voters : list[str]
    votes : dict[str, VotingType]

    def __init__(self, voters : list[str]):
        self.voters = voters
        self.votes = {}
    def add_vote(self, voter : str, vote : VotingType):
        if self.voting_finished():
            raise RuntimeError(f"Voting has already finished.")
        if voter not in self.voters: 
            raise KeyError(f"Not allowed to vote here.")
        if voter in self.votes:
            raise KeyError(f"Already voted.")
        self.votes[voter] = vote
    def voting_finished(self):
        return len(self.voters) == len(self.votes)
    def get_votes(self):
        if not self.voting_finished():
            raise RuntimeError(f"Voting has not yet concluded.")
        res = {}
        for voter in self.votes:
            v = self.votes[voter] 
            if v not in res[v]:
                res[v] = 0
            res[v] += 1
        return res


class MissionVote(Vote[VotingCards]):
    fails_needed : Literal[1, 2]
    betrayal : bool
    def __init__(self, 
                 voters : list[str], 
                 fails_needed : Literal[1, 2]):
        super().__init__(voters)
        self.fails_needed = fails_needed
        self.betrayal = False


    def result(self) -> Literal[VotingCards.Success, VotingCards.Fail]:
        votes = self.get_votes()
        Fail = VotingCards.Fail
        Reverse = VotingCards.Reverse
        Success = VotingCards.Success

        if self.betrayal:
            return Fail

        reverse = votes[Reverse] % 2
        fails = votes[Fail]
        if fails >= self.fails_needed:
            fails -= reverse
        else:
            fails += reverse

        if fails >= self.fails_needed:
            return Fail
        return Success

    def activate_betrayal(self):
        self.betrayal = True


class Mission:
    proposal : Vote[bool]
    mission : MissionVote
    wins_tiebreakers : bool

    def __init__(self, 
                 team : list[str],
                 players : list[str], 
                 fails_needed : Literal[1, 2],
                 wins_tiebreakers : bool = False):
        self.proposal = Vote[bool](players)
        self.mission = MissionVote(team, fails_needed)
        self.wins_tiebreakers = wins_tiebreakers

    def proposal_vote(self, player : str, vote : bool):
        self.proposal.add_vote(player, vote)
    def proposal_successful(self) -> bool:
        votes = self.proposal.get_votes()
        if votes[True] > votes[False]:
            return True
        if votes[True] == votes[False] and self.wins_tiebreakers:
            return True
        return False

    def mission_vote(self, player : str, vote : VotingCards):
        if not self.proposal_successful():
            raise RuntimeError("Mission proposal was unsuccessful - you cannot vote.")
        self.mission.add_vote(player, vote)
    def vote(self, player : str, vote : bool | VotingCards):
        if isinstance(vote, bool):
            self.proposal.add_vote(player, vote)
            return
        if not self.proposal_successful():
            raise RuntimeError("Mission proposal was unsuccessful - you cannot vote.")
        self.mission.add_vote(player, vote)

class FirstRound:
    missions : list[Mission | None]
    players : list[str]
    proposers : list[str]

    chosen_mission : Mission

    def __init__(self,
                 players : list[str],
                 proposers : list[str]):
        self.players = players
        self.proposers = proposers
        self.missions = [None, None]

    def propose(self, 
                player : str, 
                team : list[str]):
        i = self.proposers.index(player)
        if self.missions[i] is not None:
            raise RuntimeError("Mission has already been proposed.")
        self.missions[i] = Mission(team, self.players, 1, i==0)

    def vote(self, player : str, vote : str | VotingCards):
        if None in self.missions:
            raise RuntimeError("Missions not proposed yet.")
        if isinstance(vote, str):
            i = self.proposers.index(vote)
            self.missions[i].vote(player, True)
            self.missions[1-i].vote(player, False)

            if self.missions[0].proposal.voting_finished():
                if self.missions[0].proposal_successful():
                    self.chosen_mission = self.missions[0]
                else:
                    self.chosen_mission = self.missions[1]
        elif isinstance(vote, VotingCards):
            self.chosen_mission.vote(player, vote)

class Round:
    missions : list[Mission]
    def __init__(self, 
                 players : list[str],
                 ):
        ...

    def finished(self):
        return (len(self.missions) > 0 
                and self.missions[-1].proposal_successful() 
                and self.missions[-1].mission.voting_finished())
    def result(self):
        if not self.finished():
            raise RuntimeError("Round not finished yet.")
        return self.missions[-1].mission.result()





class Avalon:
    player_info : dict[str, RoleInfo]
    proposal_order : list[str]
    first_mission_proposers : list[int]
    current_proposer_index : int

    round_number : int
    proposal_number : int

    past_proposals : list[Mission] # or smth

    def __init__(self, builder : AvalonBuilder):
        self.player_info = { builder[role] : RoleInfo(role, builder) 
                            for role in builder }
        self.proposal_order = builder.players
        proposers = random.sample(range(0, len(builder.players)), 3)
        self.first_mission_proposers = [proposers[0], proposers[1]]
        self.current_proposer_index = proposers[2]

        self.round_number = 1
        self.proposal_number = 1

        self.past_proposals = []

    def current_proposer(self) -> str | list[str]:
        return self.proposal_order[self.current_proposer_index]

    

class AvalonBuilder:
    players : list[str]
    role_to_player : dict[Role,str]

    def __init__(self, players: list[str], roles_in_play : list[Role],
                 num_evils : int | None = None):
        players = list(set(players))
        random.shuffle(players)
        self.players = players

        n = len(players)
        assert(5 <= n <= 12)
        roles = generate_roles(n, roles_in_play, num_evils)
        self.role_to_player = {}

        for (player, role) in zip(players, roles):
            self[role] = player
        for role in roles:
            self.transform_lonely(role)

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

    def transform_lonely(self, role : Role):
        self[role.transform_if_lonely(self)] = self.pop(role)

    def get_players_with_roles(self, roles : list[Role]) -> list[str]:
        players = [self[role] for role in roles if role in self]
        random.shuffle(players)
        return players



if __name__ == "__main__":
    players = sys.argv[1:]
    game = AvalonBuilder(players, all_roles)
    exit(0)

