"""A lobby's game: the host's settings, the deal, every player's role info,
the engine's GameController, and the votes the host starts by hand.

AvalonGame is plain data, stored in Redis with its Lobby (see lobbies.py)
and changed only through Lobbies.update(). Players are known by their
browser's uuid here; the engine knows them by name (`names` maps one to
the other).
"""
from __future__ import annotations

from thavalon import GameController, GameState, RuleError
from thavalon.dealing import (AvalonBuilder, DEFAULT_TEAM_SIZES, default_double_fail_quest,
                              default_num_evils, num_extras, possible_extras)
from thavalon.roles import Role, all_roles
from thavalon.ruleset import RuleSet, DEFAULT as DEFAULT_RULES
from web import host_votes
from web.host_votes import HostVote


def extras_label(num_players : int, roles : list[Role], ruleset : RuleSet | None = None) -> str:
    """Who plays on top of the Evil players: 'Gareth', 'Balin', 'Gareth or
    Balin' (one of them, at random), 'Gareth + Balin', or ''."""
    names = [r.name.split()[0] for r in possible_extras(num_players, roles, ruleset)]
    joiner = " or " if num_extras(num_players, roles, ruleset) < len(names) else " + "
    return joiner.join(names)


class GameSettings:
    """What the host chose. None means "use the default for the player count"."""
    num_evils : int | None = None
    team_sizes : list[int] | None = None
    double_fail : int | None = None   # quest number (1-5), 0 = no quest, None = default
    lady : bool = False               # play with the Lady of the Lake

    @classmethod
    def from_form(cls, form) -> GameSettings:
        """The host page's game fields. Raises ValueError with a readable
        message on bad input."""
        settings = cls()
        evils = form.get('evils', 'default')
        if evils != 'default':
            settings.num_evils = int(evils)
        sizes = [form.get(f'size{i}', '').strip() for i in range(1, 6)]
        if any(sizes):
            try:
                settings.team_sizes = [int(x) for x in sizes]
            except ValueError:
                raise ValueError("Fill in a team size for every quest.")
        double_fail = form.get('double_fail', 'default')
        if double_fail != 'default':
            settings.double_fail = int(double_fail)
        settings.lady = form.get('lady') == '1'
        return settings

    def resolve(self, num_players : int, roles : list[Role],
                ruleset : RuleSet | None = None) -> dict:
        """The setup actually in effect for a game of this size and roles
        (shown to players as "This game"). ValueError if it can't work."""
        n = num_players
        if n not in DEFAULT_TEAM_SIZES:
            raise ValueError("A game needs 5 to 10 players.")
        extras = num_extras(n, roles, ruleset)
        evils = self.num_evils if self.num_evils is not None else default_num_evils(n, extras)
        sizes = self.team_sizes or DEFAULT_TEAM_SIZES[n]
        if any(not 2 <= k <= n for k in sizes):
            raise ValueError(f"Team sizes must be between 2 and {n} for {n} players.")
        double_fail = (self.double_fail if self.double_fail is not None
                       else default_double_fail_quest(n))
        if evils < 1 or n - evils - extras < 1:
            raise ValueError(f"{evils} Evil players doesn't work with {n} players.")
        # Gareth and Balin count towards proposals as if Evil (see GameState.num_evils).
        proposals = evils + extras + 1
        return dict(num_players = n,
                    num_evils = evils,
                    extras = extras,                    # Gareth and/or Balin
                    extra_label = extras_label(n, roles, ruleset),
                    num_others = n - evils - extras,
                    team_sizes = sizes,
                    double_fail = double_fail or None,
                    proposals = proposals,
                    lady = self.lady,
                    inquisition = ('none' if proposals <= 3
                                   else 'weak' if proposals == 4
                                   else 'strong'))


class RoleInfo:
    """What one player was told at the start: role.get_info() plus 'role'."""
    info : dict

    def __init__(self, role : Role, deal : AvalonBuilder):
        self.info = role.get_info(deal)
        self.info['role'] = str(role)

    def __getitem__(self, key : str):
        return self.info[key]

    def __contains__(self, key : str):
        return key in self.info


class AvalonGame:
    """The game a lobby is playing (or nothing yet: controller is None)."""
    player_info : dict[str, RoleInfo]   # uuid -> what they were told
    roles_in_game : list[Role]          # the host's selection
    proposers : list[str]               # round-1 proposers, then the round-2 starter
    rules : dict | None = None          # GameSettings.resolve()'s result
    ruleset : RuleSet | None = None     # the host's rules (None in games from before)
    controller : GameController | None = None
    names : dict[str, str]              # uuid -> player name (names are the game's ids)
    host_vote : HostVote | None = None  # the latest vote the host started

    def __init__(self):
        self.roles_in_game = all_roles[:]
        self.player_info = {}
        self.game_number = 0        # counts restarts, so vote keys never repeat
        self._host_vote_ids = 0

    @property
    def game_ruleset(self) -> RuleSet:
        return self.ruleset or DEFAULT_RULES

    def __getitem__(self, uuid : str) -> RoleInfo:
        return self.player_info[uuid]

    def __contains__(self, uuid : str):
        return uuid in self.player_info

    # ---- starting a game ----

    def restart(self, roles_in_game : list[Role], players : dict[str, str],
                settings : GameSettings, ruleset : RuleSet | None = None):
        """Deal a new game. Everything is built first, so a bad setting
        (ValueError) leaves the old game intact."""
        ruleset = ruleset or DEFAULT_RULES
        rules = settings.resolve(len(players), roles_in_game, ruleset)
        deal = AvalonBuilder(list(players.values()), roles_in_game,
                             rules['num_evils'], rules = ruleset)
        self.install(deal, roles_in_game, players, rules)

    def install(self, deal : AvalonBuilder, roles_in_game : list[Role],
                players : dict[str, str], rules : dict):
        """Start a game from roles already dealt (restart, or a dev scenario).
        The game's rule settings are the deal's."""
        self.player_info = {}
        self.roles_in_game = roles_in_game
        self.rules = rules
        self.ruleset = deal.rules
        uuid_of = {}
        for uuid, name in players.items():
            uuid_of.setdefault(name, uuid)
        for role in deal:
            self.player_info[uuid_of[deal[role]]] = RoleInfo(role, deal)
        self.proposers = deal.get_first_mission_proposers() + [deal.get_second_mission_starter()]
        self.names = dict(players)
        self.host_vote = None
        self.game_number += 1
        self.controller = GameController(GameState.from_builder(
            deal, rules['team_sizes'], rules['double_fail'],
            role_pool = roles_in_game, lady_of_the_lake = rules['lady']))

    # ---- playing ----

    def act(self, uuid : str, action : str, params : dict):
        self.controller.act(self.names[uuid], action, **params)

    def host_undo(self) -> str:
        return self.controller.undo()

    def host_skip(self):
        self.controller.skip_pause()

    # ---- votes the host starts by hand (don't affect the game) ----

    def start_host_vote(self, kind : str, team : list[str]):
        if self.host_vote and self.host_vote.open:
            raise RuleError("End the current vote first.")
        seating = self.controller.state.seating
        team = [p for p in seating if p in team]
        self._host_vote_ids += 1
        if kind == host_votes.MISSION:
            cards = host_votes.mission_cards(self.controller.state.possible_roles)
            self.host_vote = HostVote(self._host_vote_ids, kind, team, cards = cards)
        else:
            self.host_vote = HostVote(self._host_vote_ids, kind, seating, team = team)

    def end_host_vote(self, cancel : bool = False):
        if not (self.host_vote and self.host_vote.open):
            raise RuleError("No vote is going on.")
        self.host_vote.close(cancelled = cancel)

    def cast_host_vote(self, uuid : str, vote_id : int, choice : str):
        hv = self.host_vote
        if hv is None or hv.id != vote_id:
            raise RuleError("This vote has ended.")
        hv.cast(self.names[uuid], choice)

    def host_vote_view(self, uuid : str) -> dict | None:
        return self.host_vote.view(self.names[uuid]) if self.host_vote else None

    # ---- for the "everything" page and the admin ----

    def snapshot(self):
        return dict(self.player_info)

    def roles_dealt(self) -> list[Role]:
        return list(self.controller.state.roles.values()) if self.controller else []
