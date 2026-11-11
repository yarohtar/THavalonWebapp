"""The layer between players and state.GameState.

GameController answers three questions for a given player:

    available_actions(player)  what may this player do right now (and with
                               which options), for building the UI
    act(player, action, ...)   do it, after checking this player is allowed
    view(player)               the game as this player may see it

GameState enforces the rules of the game; this class enforces *who* may act:
the Leader proposes, only team members play cards, only Morgana uses
Sorceress, and so on. It also makes sure nobody learns secret information
(other players' cards, how people voted before the vote is complete).

Identifying the player (sessions, logins) is the webapp's job; it passes in
the name of the player making the request. What each player sees is built
by views.py.

The host can undo actions, as long as nothing secret was revealed since.
"""
from __future__ import annotations

import copy

from thavalon import views
from thavalon.cards import Card
from thavalon.errors import NotAllowed
from thavalon.state import GameState, Phase, PAUSES

# Log entries that make secret information public. Once one of these has
# happened, nothing before it can be undone (the information is out).
REVEALING = {"inquisition", "gawain", "changeling", "sorceress", "betrayal", "lady",
             "proclamation", "quest_revealed", "pellinore_guess",
             "assassination", "game_over"}

MAX_UNDO = 50


class GameController:
    def __init__(self, state : GameState):
        self.state = state
        # (snapshot before the action, its log length, public description)
        self.history : list[tuple[GameState, int, str]] = []

    # ------------------------------------------------------------ undo

    def _record(self, run, description : str):
        """Run a change; remember how to undo it unless it revealed secrets."""
        # The log is append-only, so snapshots leave it out and undo just
        # truncates it (copying it every time gets slow in long games).
        log, self.state.log = self.state.log, []
        try:
            # Role objects never change: share them instead of copying.
            memo = {id(r): r for r in self.state.roles.values()}
            before = copy.deepcopy(self.state, memo)
        finally:
            self.state.log = log
        start = len(log)
        run()
        if any(e["type"] in REVEALING for e in self.state.log[start:]):
            self.history.clear()
        else:
            self.history.append((before, start, description))
            del self.history[:-MAX_UNDO]

    def undo_label(self) -> str | None:
        """Public description of what undo would take back, if anything."""
        return self.history[-1][2] if self.history else None

    def undo(self) -> str:
        if not self.history:
            raise NotAllowed("Nothing to undo.")
        before, log_length, description = self.history.pop()
        before.log = self.state.log[:log_length]
        before.log.append(dict(type="undo", description=description))
        self.state = before
        return description

    def skip_pause(self):
        """Host: stop waiting for players who haven't pressed Ready."""
        if self.state.phase not in PAUSES:
            raise NotAllowed("Not waiting for anyone.")
        self._record(self.state.advance, "Skipped waiting")

    # ------------------------------------------------------------ actions

    def available_actions(self, player : str) -> dict[str, dict]:
        """Action name -> options for the UI. Empty if the player can't act."""
        s = self.state
        if player not in s.roles:
            return {}
        role = s.role(player)
        everyone = list(s.seating)
        acts : dict[str, dict] = {}
        q = s.current_quest

        if s.phase == Phase.FIRST_ROUND_PROPOSING and player in s.first_proposers:
            acts["propose_first_round"] = dict(team_size=s.team_size(), players=everyone,
                                               current=s.first_round_teams.get(player))
        if s.phase == Phase.FIRST_ROUND_VOTING:
            acts["vote_first_round"] = dict(choices=list(s.first_proposers),
                                            current=s.first_round_votes.get(player))
        if s.phase == Phase.PROPOSING and player == s.leader:
            acts["propose"] = dict(team_size=s.team_size(), players=everyone,
                                   hammer=s.is_hammer())
            if role == "Morgana" and not s.is_hammer():
                done = {p.leader for p in s.proposals if p.round == s.round}
                acts["sorceress"] = dict(choices=[p for p in s.seating
                                                  if p not in done and p != player])
        if s.phase == Phase.VOTING:
            acts["vote"] = dict(current=s.current_proposal.votes.get(player))
        if s.phase == Phase.TEAM_ANNOUNCED and role == "Oberon" and not s.changeling_used \
                and player not in s.current_proposal.team:
            acts["changeling"] = dict(choices=list(s.current_proposal.team))
        if s.phase == Phase.QUEST and player in q.team and player not in q.cards:
            acts["play_card"] = dict(cards=[c.value for c in s.allowed_cards(player)])
        if s.phase == Phase.INQUISITION and player == q.leader:
            acts["inquisition"] = dict(kind=q.inquisition, choices=list(q.team),
                                       can_remove=q.inquisition == "strong")
        if role == "Gawain" and s.gawain_available():
            acts["gawain"] = dict(choices=[p for p in q.team
                                           if p != q.removed and p not in q.revealed])
        if role == "Agravaine" and s.betrayal_available():
            acts["betray"] = {}
        if role == "Arthur" and s.proclamation_available():
            acts["proclaim"] = {}
        if s.phase == Phase.LADY and player == s.lady_holder:
            acts["lady"] = dict(choices=s.lady_choices())
        if s.phase in PAUSES and player not in s.ready:
            acts["ready"] = {}
        if s.phase == Phase.PELLINORE_GUESS and role == "Pellinore":
            acts["pellinore_guess"] = dict(choices=[p for p in s.seating if p != player])
        if s.phase == Phase.ASSASSINATION and player == s.assassin():
            acts["assassinate"] = dict(kinds=s.rules.assassination_kinds(),
                                       choices=list(s.seating))
        return acts

    def act(self, player : str, action : str, **params):
        """Perform `action` for `player`. Raises NotAllowed if this player
        can't do it now, or RuleError if the details break the rules."""
        if action not in self.available_actions(player):
            raise NotAllowed(f"You can't {action.replace('_', ' ')} right now.")
        self._record(lambda: self._perform(player, action, params),
                     _describe(player, action, params))

    def _perform(self, player : str, action : str, params : dict):
        s = self.state
        match action:
            case "propose_first_round":
                s.propose_first_round(player, list(params["team"]))
            case "vote_first_round":
                s.vote_first_round(player, params["proposer"])
            case "propose":
                s.propose(list(params["team"]))
            case "sorceress":
                s.use_sorceress(params["next_proposer"])
            case "vote":
                s.vote(player, bool(params["approve"]))
            case "changeling":
                s.changeling(params["replaced"])
            case "play_card":
                s.play_card(player, Card(params["card"]))
            case "inquisition":
                s.inquisition(params["target"], remove=bool(params.get("remove", False)))
            case "gawain":
                s.gawain_inquisition(params["target"])
            case "betray":
                s.betray()
            case "proclaim":
                s.proclaim()
            case "lady":
                s.lady_of_the_lake(params["target"])
            case "ready":
                s.mark_ready(player)
            case "pellinore_guess":
                s.pellinore_guess(params.get("target"))
            case "assassinate":
                s.assassinate(params["kind"], list(params.get("targets", [])))
            case _:
                raise NotAllowed(f"Unknown action {action!r}.")

    # ------------------------------------------------------------ views

    def declarations(self) -> list[dict]:
        """Players who have publicly revealed their role, in order."""
        return views.declarations(self.state)

    def view(self, player : str | None = None, scoped : bool = True) -> dict:
        """Everything `player` may see (see views.view). With no player: the
        public view."""
        actions = self.available_actions(player) if player in self.state.roles else None
        return views.view(self.state, player, actions, scoped)


def _describe(player : str, action : str, params : dict) -> str:
    """Public, secret-free description of an action, for the host's undo."""
    team = ", ".join(params.get("team", []))
    return {
        "propose_first_round": f"{player} proposed {team}",
        "vote_first_round": f"{player} voted",
        "propose": f"{player} proposed {team}",
        "vote": f"{player} voted",
        "play_card": f"{player} chose a card",
        "ready": f"{player} pressed ready",
        "lady": f"{player} sent the Lady to {params.get('target')}",
    }.get(action, f"{player}: {action.replace('_', ' ')}")
