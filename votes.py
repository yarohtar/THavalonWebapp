"""Votes the host starts by hand, outside the game's flow.

A fallback for when the game gets stuck or something went wrong: the host
starts a team proposal vote (everyone approves or rejects) or a mission vote
(the chosen players each play a card), the players vote on their Vote tab,
and the result is shown to everyone. Nothing here touches game.GameState;
the table carries on from the results by hand.

Like the game: proposal votes may be changed until everyone has voted and
are public once the vote ends; mission cards are final and only the
shuffled cards are shown.
"""
from __future__ import annotations

import random

from game import Card, RuleError

PROPOSAL = "proposal"
MISSION = "mission"
APPROVE, REJECT = "approve", "reject"


class HostVote:
    def __init__(self, vote_id : int, kind : str, voters : list[str],
                 team : list[str] = (), cards : list[str] = (),
                 rng : random.Random | None = None):
        if kind not in (PROPOSAL, MISSION):
            raise RuleError("Unknown kind of vote.")
        voters = list(dict.fromkeys(voters))
        if not voters:
            raise RuleError("Choose who plays a card." if kind == MISSION
                            else "Nobody to vote.")
        self.id = vote_id
        self.kind = kind
        self.voters = voters
        # Proposal: the team being voted on (optional, just shown).
        # Mission: the players on the mission, who are also the voters.
        self.team = list(dict.fromkeys(team)) if kind == PROPOSAL else list(voters)
        self.choices = [APPROVE, REJECT] if kind == PROPOSAL else list(cards)
        self.ballots : dict[str, str] = {}       # SECRET until the vote ends
        self.closed = False
        self.cancelled = False
        self.played : list[str] = []             # mission: shuffled cards
        self.rng = rng or random.Random()

    @property
    def key(self) -> str:
        return f"h{self.id}"

    @property
    def open(self) -> bool:
        return not self.closed

    def cast(self, voter : str, choice : str):
        if self.closed:
            raise RuleError("This vote has ended.")
        if voter not in self.voters:
            raise RuleError("You aren't part of this vote.")
        if choice not in self.choices:
            raise RuleError("That isn't one of the choices.")
        if self.kind == MISSION and voter in self.ballots:
            raise RuleError("You have already chosen your card.")
        self.ballots[voter] = choice
        if len(self.ballots) == len(self.voters):
            self.close()

    def close(self, cancelled : bool = False):
        """End the vote. Players who didn't vote are listed as missing."""
        if self.closed:
            raise RuleError("This vote has already ended.")
        self.closed = True
        self.cancelled = cancelled
        if self.kind == MISSION and not cancelled:
            self.played = list(self.ballots.values())
            self.rng.shuffle(self.played)

    def view(self, player : str | None = None) -> dict:
        """What `player` may see (None: the public view)."""
        done = self.closed and not self.cancelled
        v = dict(id=self.id, key=self.key, kind=self.kind, voters=list(self.voters),
                 team=list(self.team), choices=list(self.choices),
                 open=self.open, cancelled=self.cancelled,
                 voted=[p for p in self.voters if p in self.ballots],
                 waiting_for=[p for p in self.voters if p not in self.ballots],
                 approved_by=None, rejected_by=None, approved=None, played=None)
        if done and self.kind == PROPOSAL:
            v["approved_by"] = [p for p in self.voters if self.ballots.get(p) == APPROVE]
            v["rejected_by"] = [p for p in self.voters if self.ballots.get(p) == REJECT]
            v["approved"] = len(v["approved_by"]) * 2 > len(self.voters)
        if done and self.kind == MISSION:
            v["played"] = list(self.played)
        if player is not None:
            v["involved"] = self.open and player in self.voters
            v["mine"] = self.ballots.get(player)
            v["pending"] = v["involved"] and (player not in self.ballots)
        return v


def mission_cards(possible_roles : set[str]) -> list[str]:
    """Cards offered in a host mission vote: the same for everyone, so the
    buttons give nothing away. Players play what their role allows."""
    cards = [Card.SUCCESS, Card.FAIL, Card.REVERSAL]
    if "The Questing Beast" in possible_roles:
        cards.append(Card.QBWH)
    return [c.value for c in cards]
