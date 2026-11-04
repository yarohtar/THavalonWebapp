"""THavalon game state: the rules of play after roles have been dealt.

GameState holds the whole game and offers a direct API for changing it
(propose, vote, play_card, ...). It enforces the *mechanics*: phases, team
sizes, card values, Inquisition grants, Reversal, scoring and so on. It does
NOT check *who is asking*; every method acts on behalf of whoever the rules
say acts (the Leader, Morgana, ...). That is the job of actions.GameController,
which sits between players and this class. Calling GameState directly is how
a host (or a test) fixes mistakes.

Flow of a round (see Phase):

    round 1:  FIRST_ROUND_PROPOSING -> FIRST_ROUND_VOTING -> QUEST
    later:    PROPOSING -> VOTING -> QUEST            (rejected: next PROPOSING)
              PROPOSING -> [TEAM_ANNOUNCED] -> QUEST  (Hammer; Changeling pause)
    then:     QUEST -> [INQUISITION] -> [REVEAL] -> [RESULT] -> next round
    end:      [PELLINORE_GUESS] -> [ASSASSINATION] -> GAME_OVER

TEAM_ANNOUNCED (Oberon), REVEAL (Gawain) and RESULT (Agravaine) are pauses
that end once every player is ready. A pause happens only when a role that
could act in it might be in the game (the host's role selection at this
player count) and the rules currently allow the ability. Whether the role is
*actually* in the game never matters, so pausing reveals nothing. A role
using its ability during a pause resets everyone's readiness, so the table
notices the change.

Every change is appended to `log` as a dict of *public* information, for the
webapp to broadcast. Secret information (who played which card) stays in the
state and is exposed only through actions.GameController's per-player views.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from THavalon import AvalonBuilder, Role, all_roles


class RuleError(Exception):
    """The requested change is not allowed by the rules right now."""


class Card(str, Enum):
    SUCCESS = "Success"
    FAIL = "Fail"
    REVERSAL = "Reversal"
    QBWH = "Questing Beast Was Here"


class Phase(str, Enum):
    FIRST_ROUND_PROPOSING = "first_round_proposing"
    FIRST_ROUND_VOTING = "first_round_voting"
    PROPOSING = "proposing"
    VOTING = "voting"
    TEAM_ANNOUNCED = "team_announced"   # Hammer team; Oberon may swap in
    QUEST = "quest"                     # team members choose cards
    INQUISITION = "inquisition"         # Leader must use their Inquisition
    REVEAL = "reveal"                   # pause before reveal; Gawain may act
    RESULT = "result"                   # pause after reveal; Agravaine may betray
    PELLINORE_GUESS = "pellinore_guess"
    ASSASSINATION = "assassination"
    GAME_OVER = "game_over"


PAUSES = (Phase.TEAM_ANNOUNCED, Phase.REVEAL, Phase.RESULT)

# Who makes the final Assassination decision, highest first.
ASSASSIN_RANKING = ["Mordred", "Morgana", "Maelegant", "Agravaine",
                    "Colgrevance", "Minion of Mordred", "Oberon"]


@dataclass
class Proposal:
    round: int
    number: int                 # 1-based within the round
    leader: str
    team: list[str] = field(default_factory=list)
    hammer: bool = False
    votes: dict[str, bool] = field(default_factory=dict)
    approved: bool | None = None
    sorceress_next: str | None = None   # Morgana declared instead of proposing


@dataclass
class Quest:
    round: int
    leader: str
    team: list[str]
    fails_needed: int
    inquisition: str | None = None          # "weak" | "strong" | None
    cards: dict[str, Card] = field(default_factory=dict)   # SECRET until revealed
    revealed: dict[str, Card] = field(default_factory=dict)  # public, by player
    removed: str | None = None              # player whose card Strong Inquisition removed
    inquisition_done: bool = False
    gawain_target: str | None = None
    changeling: tuple[str, str] | None = None   # (oberon, replaced player)
    played: list[Card] = field(default_factory=list)  # shuffled, public after reveal
    qbwh_counts_as: Card | None = None
    succeeded: bool | None = None
    betrayed: bool = False


class GameState:
    def __init__(self,
                 seating : list[str],
                 roles : dict[str, Role],
                 team_sizes : list[int],
                 double_fail_quest : int | None,
                 first_proposers : tuple[str, str],
                 round2_starter : str,
                 role_pool : list[Role] | None = None,
                 rng : random.Random | None = None):
        assert len(team_sizes) == 5
        assert set(roles) == set(seating)
        self.seating = list(seating)            # proposal order
        self.roles = dict(roles)                # player -> Role
        self.team_sizes = list(team_sizes)
        self.double_fail_quest = double_fail_quest
        self.rng = rng or random.Random()
        # Roles that could be in this game, as far as the table knows: the
        # host's selection, limited to roles allowed at this player count.
        # Pauses are skipped when no role that could act in them is possible.
        n = len(seating)
        self.possible_roles = {str(r) for r in (role_pool or all_roles) if r.can_appear(n)}
        self.possible_roles |= {str(r) for r in roles.values()}
        self.num_evils = sum(r.allegiance() == "Evil" for r in roles.values())
        self.proposals_per_round = self.num_evils + 1

        self.phase = Phase.FIRST_ROUND_PROPOSING
        self.round = 1
        self.first_proposers = tuple(first_proposers)
        self.round2_starter = round2_starter
        self.first_round_teams : dict[str, list[str]] = {}
        self.first_round_votes : dict[str, str] = {}

        self.direction = 1                      # +1 or -1 through `seating`
        self.leader_index = self.seating.index(round2_starter)
        self.proposals : list[Proposal] = []    # all rounds
        self.quests : list[Quest] = []
        self.ready : set[str] = set()

        self.strong_used = False
        self.weak_used = False
        self.changeling_used = False
        self.gawain_exiled = False
        self.proclaimed = False

        self.pellinore_guess_target : str | None = None
        self.assassination : dict | None = None
        self.outcome : dict | None = None
        self.log : list[dict] = []

    @classmethod
    def from_builder(cls, builder : AvalonBuilder, team_sizes : list[int],
                     double_fail_quest : int | None, **kw) -> GameState:
        """Pass role_pool= (the host's selected roles) so that pauses for
        roles that can't be in the game are skipped."""
        roles = {builder[role]: role for role in builder}
        a, b = builder.get_first_mission_proposers()
        return cls(builder.players, roles, team_sizes, double_fail_quest,
                   (a, b), builder.get_second_mission_starter(), **kw)

    # ------------------------------------------------------------------ helpers

    def role(self, player : str) -> str:
        return str(self.roles[player])

    def players_with_role(self, role_name : str) -> list[str]:
        return [p for p in self.seating if self.role(p) == role_name]

    def player_with_role(self, role_name : str) -> str | None:
        found = self.players_with_role(role_name)
        return found[0] if found else None

    def allegiance(self, player : str) -> str:
        return self.roles[player].allegiance()

    @property
    def leader(self) -> str:
        return self.seating[self.leader_index]

    @property
    def current_proposal(self) -> Proposal | None:
        return self.proposals[-1] if self.proposals and self.proposals[-1].round == self.round else None

    @property
    def current_quest(self) -> Quest | None:
        return self.quests[-1] if self.quests and self.quests[-1].round == self.round else None

    @property
    def proposal_number(self) -> int:
        """Number of the proposal being made now (or last made) this round."""
        return sum(p.round == self.round for p in self.proposals) + (
            1 if self.phase == Phase.PROPOSING else 0)

    def team_size(self, round_number : int | None = None) -> int:
        return self.team_sizes[(round_number or self.round) - 1]

    def fails_needed(self, round_number : int | None = None) -> int:
        return 2 if (round_number or self.round) == self.double_fail_quest else 1

    @property
    def successes(self) -> int:
        return sum(q.succeeded is True for q in self.quests)

    @property
    def failures(self) -> int:
        return sum(q.succeeded is False for q in self.quests)

    def qbwh_seen(self) -> int:
        """Questing Beast Was Here cards revealed so far."""
        return sum(card == Card.QBWH for q in self.quests for card in q.played)

    def allowed_cards(self, player : str) -> list[Card]:
        role = self.role(player)
        if role == "The Questing Beast":
            return [Card.QBWH]
        if role == "Pellinore":
            return [Card.FAIL] if self.qbwh_seen() >= 2 else [Card.SUCCESS]
        if role == "Agravaine":
            return [Card.FAIL]
        if role == "Maelegant":
            return [Card.SUCCESS, Card.FAIL, Card.REVERSAL]
        if role == "Lancelot":
            return [Card.SUCCESS, Card.REVERSAL]
        if self.allegiance(player) == "Evil":
            return [Card.SUCCESS, Card.FAIL]
        return [Card.SUCCESS]

    def assassin(self) -> str | None:
        for role_name in ASSASSIN_RANKING:
            found = self.player_with_role(role_name)
            if found:
                return found
        return None

    def _emit(self, event_type : str, /, **data):
        self.log.append(dict(type=event_type, **data))

    def _set_phase(self, phase : Phase):
        self.phase = phase
        self.ready = set()
        self._emit("phase", phase=phase.value, round=self.round)

    def _require(self, *phases : Phase):
        if self.phase not in phases:
            raise RuleError(f"Not possible during {self.phase.value}.")

    def _check_team(self, team : list[str]) -> list[str]:
        team = list(dict.fromkeys(team))
        if any(p not in self.roles for p in team):
            raise RuleError("Unknown player on the team.")
        if len(team) != self.team_size():
            raise RuleError(f"The team must have {self.team_size()} players.")
        return team

    # ------------------------------------------------------------- round 1

    def propose_first_round(self, proposer : str, team : list[str]):
        self._require(Phase.FIRST_ROUND_PROPOSING)
        if proposer not in self.first_proposers:
            raise RuleError("Only the two first-round proposers propose.")
        self.first_round_teams[proposer] = self._check_team(team)
        self._emit("first_round_proposal", proposer=proposer, team=self.first_round_teams[proposer])
        if len(self.first_round_teams) == 2:
            self._set_phase(Phase.FIRST_ROUND_VOTING)

    def vote_first_round(self, voter : str, proposer : str):
        """Vote for one of the two first-round teams (named by its proposer)."""
        self._require(Phase.FIRST_ROUND_VOTING)
        if proposer not in self.first_proposers:
            raise RuleError("Vote for one of the two proposals.")
        self.first_round_votes[voter] = proposer
        self._emit("vote_cast", voter=voter)
        if len(self.first_round_votes) == len(self.seating):
            self._finish_first_round_vote()

    def _first_round_tiebreak(self) -> str:
        """The proposer farther from the round-2 starter, counting forward."""
        n = len(self.seating)
        start = self.seating.index(self.round2_starter)
        return max(self.first_proposers,
                   key=lambda p: (self.seating.index(p) - start) % n)

    def _finish_first_round_vote(self):
        a, b = self.first_proposers
        count = {a: 0, b: 0}
        for choice in self.first_round_votes.values():
            count[choice] += 1
        winner = a if count[a] > count[b] else b if count[b] > count[a] else self._first_round_tiebreak()
        self._emit("first_round_result", votes=dict(self.first_round_votes),
                   counts=count, chosen=winner)
        self._start_quest(winner, self.first_round_teams[winner], inquisition=None)

    # ------------------------------------------------------------- proposals

    def _proposed_this_round(self) -> set[str]:
        return {p.leader for p in self.proposals if p.round == self.round}

    def _advance_leader(self):
        """Move to the next proposer in the current direction, skipping
        anyone who already proposed this round."""
        done = self._proposed_this_round()
        n = len(self.seating)
        for _ in range(n):
            self.leader_index = (self.leader_index + self.direction) % n
            if self.seating[self.leader_index] not in done:
                return
        raise RuleError("Everyone has already proposed this round.")

    def is_hammer(self) -> bool:
        return self.proposal_number >= self.proposals_per_round

    def propose(self, team : list[str]):
        """The current Leader proposes a team."""
        self._require(Phase.PROPOSING)
        team = self._check_team(team)
        prop = Proposal(self.round, self.proposal_number, self.leader, team,
                        hammer=self.is_hammer())
        self.proposals.append(prop)
        self._emit("proposal", leader=prop.leader, team=team, number=prop.number,
                   hammer=prop.hammer)
        if not prop.hammer:
            self._set_phase(Phase.VOTING)
            return
        prop.approved = True
        if self._changeling_pause_needed():
            self._set_phase(Phase.TEAM_ANNOUNCED)
        else:
            self._start_quest(prop.leader, team, inquisition=None)

    def use_sorceress(self, next_proposer : str):
        """The current Leader (Morgana) declares instead of proposing: picks
        the next proposer and reverses the proposal order."""
        self._require(Phase.PROPOSING)
        if self.is_hammer():
            raise RuleError("Sorceress can't be used on the Hammer.")
        if next_proposer not in self.roles or next_proposer in self._proposed_this_round() \
                or next_proposer == self.leader:
            raise RuleError("Choose a player who hasn't proposed this round.")
        prop = Proposal(self.round, self.proposal_number, self.leader,
                        approved=False, sorceress_next=next_proposer)
        self.proposals.append(prop)
        self.direction *= -1
        self.leader_index = self.seating.index(next_proposer)
        self._emit("sorceress", morgana=prop.leader, next_proposer=next_proposer,
                   direction=self.direction)
        self._set_phase(Phase.PROPOSING)

    def vote(self, voter : str, approve : bool):
        self._require(Phase.VOTING)
        if voter not in self.roles:
            raise RuleError("Unknown player.")
        prop = self.current_proposal
        prop.votes[voter] = bool(approve)
        self._emit("vote_cast", voter=voter)
        if len(prop.votes) < len(self.seating):
            return
        approvals = sum(prop.votes.values())
        prop.approved = approvals * 2 > len(self.seating)
        self._emit("vote_result", votes=dict(prop.votes), approved=prop.approved,
                   number=prop.number)
        if prop.approved:
            self._start_quest(prop.leader, prop.team, self._grant_inquisition(prop.number))
        else:
            self._advance_leader()
            self._set_phase(Phase.PROPOSING)

    def _grant_inquisition(self, number : int) -> str | None:
        """Inquisition earned by approving proposal `number` (from round 2)."""
        if self.round == 1:
            return None
        p = self.proposals_per_round
        kind = None
        if p == 4 and number == 1:
            kind = "weak"
        elif p >= 5 and number == 1:
            kind = "strong" if not self.strong_used else "weak"
        elif p >= 5 and number == 2:
            kind = "weak"
        if kind == "strong" and not self.strong_used:
            self.strong_used = True
            return "strong"
        if kind == "weak" and not self.weak_used:
            self.weak_used = True
            return "weak"
        return None

    # ------------------------------------------------------------- Hammer pause

    def changeling(self, replaced : str):
        """Oberon swaps themselves in for `replaced` on the Hammer team."""
        self._require(Phase.TEAM_ANNOUNCED)
        oberon = self.player_with_role("Oberon")
        prop = self.current_proposal
        if oberon is None or self.changeling_used:
            raise RuleError("Changeling isn't available.")
        if oberon in prop.team or replaced not in prop.team:
            raise RuleError("Oberon must replace someone on a team without Oberon.")
        prop.team = [oberon if p == replaced else p for p in prop.team]
        self.changeling_used = True
        self.ready = set()
        self._emit("changeling", oberon=oberon, replaced=replaced, team=prop.team)

    # ------------------------------------------------------------- pauses
    #
    # A pause happens only if a role could act in it. The decision uses only
    # public information (possible roles, declared roles, results), so
    # skipping a pause never gives anything away.

    def _declared(self, role_name : str) -> str | None:
        """The player publicly known to have this role, if any."""
        q_all = self.quests
        if role_name == "Gawain" and any(q.gawain_target for q in q_all):
            return self.player_with_role("Gawain")
        if role_name == "Agravaine" and any(q.betrayed for q in q_all):
            return self.player_with_role("Agravaine")
        return None

    def _changeling_pause_needed(self) -> bool:
        return ("Oberon" in self.possible_roles and not self.changeling_used
                and self.failures <= 1)

    def _reveal_pause_needed(self) -> bool:
        q = self.current_quest
        gawain = self._declared("Gawain")
        return ("Gawain" in self.possible_roles and self.round >= 2
                and not self.gawain_exiled
                and not (gawain is not None and gawain in q.team))

    def _betrayal_pause_needed(self) -> bool:
        q = self.current_quest
        agravaine = self._declared("Agravaine")
        return ("Agravaine" in self.possible_roles and q.succeeded
                and not (agravaine is not None and agravaine not in q.team))

    def _to_reveal(self):
        if self._reveal_pause_needed():
            self._set_phase(Phase.REVEAL)
        else:
            self._reveal()

    def mark_ready(self, player : str):
        if self.phase not in PAUSES:
            raise RuleError("Nothing to wait for.")
        self.ready.add(player)
        self._emit("ready", player=player)
        if self.ready >= set(self.seating):
            self.advance()

    def advance(self):
        """End the current pause, even if not everyone is ready."""
        if self.phase == Phase.TEAM_ANNOUNCED:
            prop = self.current_proposal
            self._start_quest(prop.leader, prop.team, inquisition=None)
        elif self.phase == Phase.REVEAL:
            self._reveal()
        elif self.phase == Phase.RESULT:
            self._finish_round()
        else:
            raise RuleError("Nothing to wait for.")

    # ------------------------------------------------------------- quest

    def _start_quest(self, leader : str, team : list[str], inquisition : str | None):
        q = Quest(self.round, leader, list(team), self.fails_needed(),
                  inquisition=inquisition)
        self.quests.append(q)
        self._emit("quest_started", leader=leader, team=q.team,
                   fails_needed=q.fails_needed, inquisition=inquisition)
        self._set_phase(Phase.QUEST)

    def play_card(self, player : str, card : Card):
        self._require(Phase.QUEST)
        q = self.current_quest
        card = Card(card)
        if player not in q.team:
            raise RuleError("Only team members play cards.")
        if player in q.cards:
            raise RuleError("You have already chosen your card.")
        if card not in self.allowed_cards(player):
            raise RuleError(f"You can't play {card.value}.")
        q.cards[player] = card
        self._emit("card_chosen", player=player)
        if len(q.cards) == len(q.team):
            if q.inquisition:
                self._set_phase(Phase.INQUISITION)
            else:
                self._to_reveal()

    def inquisition(self, target : str, remove : bool = False):
        """The Leader reveals (or, with Strong Inquisition, removes) a card."""
        self._require(Phase.INQUISITION)
        q = self.current_quest
        if target not in q.team:
            raise RuleError("Choose a player on the team.")
        if remove and q.inquisition != "strong":
            raise RuleError("Only Strong Inquisition can remove a card.")
        if remove:
            q.removed = target
            self._emit("inquisition", kind=q.inquisition, target=target, removed=True)
        else:
            q.revealed[target] = q.cards[target]
            self._emit("inquisition", kind=q.inquisition, target=target, removed=False,
                       card=q.cards[target].value)
        q.inquisition_done = True
        self._to_reveal()

    def gawain_available(self) -> bool:
        q = self.current_quest
        gawain = self.player_with_role("Gawain")
        return (self.phase == Phase.REVEAL and gawain is not None and self.round >= 2
                and not self.gawain_exiled and gawain not in q.team
                and q.gawain_target is None)

    def gawain_inquisition(self, target : str):
        """Gawain declares and makes `target` reveal their card."""
        if not self.gawain_available():
            raise RuleError("Gawain's Inquisition isn't available.")
        q = self.current_quest
        if target not in q.team or target == q.removed or target in q.revealed:
            raise RuleError("Choose a team member whose card is still hidden.")
        card = q.cards[target]
        q.gawain_target = target
        q.revealed[target] = card
        exiled = card == Card.SUCCESS
        self.gawain_exiled = self.gawain_exiled or exiled
        self.ready = set()
        self._emit("gawain", gawain=self.player_with_role("Gawain"), target=target,
                   card=card.value, exiled=exiled)

    def _qbwh_value(self) -> Card:
        """What a Questing Beast Was Here card counts as on the current quest."""
        if self.failures >= 2 or self.qbwh_seen() >= 2:
            return Card.SUCCESS
        return Card.FAIL

    def _reveal(self):
        q = self.current_quest
        q.qbwh_counts_as = self._qbwh_value()
        cards = [c for p, c in q.cards.items() if p != q.removed]
        q.succeeded = quest_succeeds(cards, q.fails_needed, q.qbwh_counts_as)
        q.played = list(cards)
        self.rng.shuffle(q.played)
        self._emit("quest_revealed", cards=[c.value for c in q.played],
                   succeeded=q.succeeded, fails_needed=q.fails_needed,
                   qbwh_counts_as=q.qbwh_counts_as.value)
        if self._betrayal_pause_needed():
            self._set_phase(Phase.RESULT)
        else:
            self._finish_round()

    def betrayal_available(self) -> bool:
        q = self.current_quest
        agravaine = self.player_with_role("Agravaine")
        return (self.phase == Phase.RESULT and agravaine in q.team
                and q.succeeded and not q.betrayed)

    def betray(self):
        """Agravaine declares and makes the successful quest fail."""
        if not self.betrayal_available():
            raise RuleError("Betrayal isn't available.")
        q = self.current_quest
        q.betrayed = True
        q.succeeded = False
        self.ready = set()
        self._emit("betrayal", agravaine=self.player_with_role("Agravaine"))

    def _finish_round(self):
        if self.successes >= 3 or self.failures >= 3:
            self._start_end_game()
            return
        self.round += 1
        # The next round starts with the player after the last proposer.
        last = self.proposals[-1].leader if self.round > 2 else None
        if last is not None:
            self.leader_index = self.seating.index(last)
            self._advance_leader()
        self._set_phase(Phase.PROPOSING)

    # ------------------------------------------------------------- anytime

    def proclaim(self):
        """Arthur declares as Arthur (after two failed quests)."""
        arthur = self.player_with_role("Arthur")
        if arthur is None or self.proclaimed or self.failures < 2 \
                or self.phase == Phase.GAME_OVER:
            raise RuleError("Proclamation isn't available.")
        self.proclaimed = True
        self._emit("proclamation", arthur=arthur)

    # ------------------------------------------------------------- end game

    def _start_end_game(self):
        if self.player_with_role("Pellinore"):
            self._set_phase(Phase.PELLINORE_GUESS)
        else:
            self._after_pellinore()

    def pellinore_guess(self, target : str | None):
        """Pellinore names the player they think is the Beast (or no one)."""
        self._require(Phase.PELLINORE_GUESS)
        if target is not None and target not in self.roles:
            raise RuleError("Unknown player.")
        self.pellinore_guess_target = target
        self._emit("pellinore_guess", made=target is not None)  # result told later
        self._after_pellinore()

    def _after_pellinore(self):
        if self.successes >= 3 and self.assassin() is not None:
            self._set_phase(Phase.ASSASSINATION)
        else:
            self._finish_game()

    def assassinate(self, kind : str, targets : list[str] = ()):
        """kind: 'merlin' or 'nilrem' (one target), 'lovers' (two), 'none'."""
        self._require(Phase.ASSASSINATION)
        targets = list(dict.fromkeys(targets))
        expected = {"merlin": 1, "nilrem": 1, "lovers": 2, "none": 0}
        if kind not in expected or len(targets) != expected[kind] \
                or any(t not in self.roles for t in targets):
            raise RuleError("Name one player as Merlin or Nilrem, two as the Lovers, or no one.")
        roles = {self.role(t) for t in targets}
        lovers_present = self.player_with_role("Tristan") and self.player_with_role("Iseult")
        correct = {
            "merlin": roles == {"Merlin"},
            "nilrem": roles == {"Nilrem"},
            "lovers": roles == {"Tristan", "Iseult"},
            "none": not (self.player_with_role("Merlin") or self.player_with_role("Nilrem")
                         or lovers_present),
        }[kind]
        self.assassination = dict(kind=kind, targets=targets, correct=correct)
        self._emit("assassination", assassin=self.assassin(), **self.assassination)
        self._finish_game()

    def _finish_game(self):
        good_won = self.successes >= 3 and not (self.assassination or {}).get("correct")
        outcome = dict(winner="Good" if good_won else "Evil",
                       roles={p: self.role(p) for p in self.seating})
        pellinore = self.player_with_role("Pellinore")
        beast = self.player_with_role("The Questing Beast")
        if pellinore and beast:
            outcome["neutrals"] = self._neutral_scores(pellinore, beast)
        self.outcome = outcome
        self._emit("game_over", **outcome)
        self._set_phase(Phase.GAME_OVER)

    def _neutral_scores(self, pellinore : str, beast : str) -> dict:
        seen = self.qbwh_seen()
        guessed = self.pellinore_guess_target == beast
        together = any(pellinore in q.team and beast in q.team for q in self.quests)
        sanity = -seen + (1 if together else 0) + (2 if self.failures >= 3 else 0) \
                 + (3 if guessed else 0)
        quests_on = sum(beast in q.team for q in self.quests)
        points = quests_on + (0 if together else 1) + (2 if self.successes >= 3 else 0) \
                 + (0 if guessed else 3)
        return {
            "Pellinore": dict(player=pellinore, sanity=sanity, guessed_right=guessed,
                              won=seen == 0 or sanity >= 2),
            "The Questing Beast": dict(player=beast, points=points,
                                       won=quests_on >= 1 and points >= 5),
        }


def quest_succeeds(cards : list[Card], fails_needed : int,
                   qbwh_counts_as : Card = Card.FAIL) -> bool:
    """Result of a quest from the cards that count (removed card excluded).

    A Reversal counts as a Success and flips one other non-Reversal card,
    choosing one that changes the result if it can. Two Reversals cancel.
    """
    values = [qbwh_counts_as if c == Card.QBWH else c for c in cards]
    reversals = values.count(Card.REVERSAL) % 2
    fails = values.count(Card.FAIL)
    successes = values.count(Card.SUCCESS)
    failed = fails >= fails_needed
    if reversals:
        if failed and fails > 0 and fails - 1 < fails_needed:
            failed = False      # flip a Fail into a Success
        elif not failed and successes > 0 and fails + 1 >= fails_needed:
            failed = True       # flip a Success into a Fail
    return not failed
