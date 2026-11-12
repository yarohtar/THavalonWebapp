"""Test scenarios for the dev site: games set up in a particular state.

Only active when the app runs with AVALON_DEV=1 (the dev site's service);
the normal site never registers any of this.

    /dev/                     list of scenarios
    /dev/<slug>               reset the scenario's game, then view it
    /dev/<slug>/as/<who>      view it as a player (or "host")

Viewing as someone simply makes this browser session *be* that player: the
real pages (Game / Role / Vote tabs, host page) are used unchanged. A bar at
the top of every page switches player, resets the scenario and sends
feedback. Each tester (browser session) gets their own copy of every
scenario, so testers never see each other's games.

Feedback (/dev/feedback) is emailed through Amazon SES with the game's full
state, secrets included:

    DEV_FEEDBACK_EMAIL      where feedback goes (also the sender by default)
    DEV_FEEDBACK_FROM       optional: a different verified SES sender

Access: the dev site sits behind Cloudflare Access, whose policy decides who
gets in (add playtesters there). As a second lock, every request must carry
a valid Access token for this Access application (checked against the
team's keys), so the site stays closed if Access is ever switched off.
Without the first two settings below, everything is refused.

    CF_ACCESS_TEAM_DOMAIN   e.g. myteam.cloudflareaccess.com
    CF_ACCESS_AUD           the Access application's audience tag
    DEV_ALLOWED_EMAILS      optional, comma-separated: only these emails
                            (empty: whoever the Access policy lets in)
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import flask
from flask import Blueprint, g, request, session, url_for
from markupsafe import Markup

from thavalon import PAUSES, Phase, RuleSet
from thavalon import roles as T
from thavalon.dealing import AvalonBuilder
from web import events
from web.access import AccessCheck
from web.games import GameSettings
from web.lobbies import LOBBIES, Lobby

PLAYER_NAMES = ["Ann", "Bob", "Cat", "Dan", "Eve", "Fay", "Gus", "Hal", "Ivy", "Jon"]


def enabled() -> bool:
    return os.environ.get("AVALON_DEV") == "1"


# ---------------------------------------------------------------- driving

class Drive:
    """Plays a game forward quickly (as the players would) to set up a scenario."""

    def __init__(self, ctl):
        self.ctl = ctl

    @property
    def s(self):
        return self.ctl.state

    def act(self, player, action, **params):
        self.ctl.act(player, action, **params)

    def first_round(self, team, other=None, winner=0):
        a, b = self.s.first_proposers
        self.act(a, "propose_first_round", team=team)
        self.act(b, "propose_first_round", team=other or team)
        for p in self.s.seating:
            self.act(p, "vote_first_round", proposer=(a, b)[winner])

    def propose(self, team, approve=True):
        """The current Leader proposes `team`; approve: True, False or a set of approvers."""
        self.act(self.s.leader, "propose", team=team)
        if self.s.phase == Phase.VOTING:
            for p in self.s.seating:
                yes = approve if isinstance(approve, bool) else p in approve
                self.act(p, "vote", approve=yes)

    def reject_until_hammer(self, team):
        while not self.s.is_hammer():
            self.propose(team, approve=False)

    def cards(self, fails=(), **special):
        """Team members play: Fail if in `fails`, a card named in `special`,
        otherwise Success (or the only card their role allows)."""
        q = self.s.current_quest
        for p in q.team:
            allowed = [c.value for c in self.s.allowed_cards(p)]
            card = special.get(p) or ("Fail" if p in fails else "Success")
            if card not in allowed:
                card = allowed[0]
            self.act(p, "play_card", card=card)

    def inquisition(self, pick=0):
        """The Leader reveals the card of team member number `pick`, if they have Inquisition."""
        s = self.s
        if s.phase == Phase.INQUISITION:
            q = s.current_quest
            self.act(q.leader, "inquisition", target=q.team[pick])

    def settle(self):
        """Finish Inquisition and pauses until the next decision (stops at the Lady)."""
        for _ in range(20):
            s = self.s
            if s.phase == Phase.INQUISITION:
                q = s.current_quest
                self.act(q.leader, "inquisition", target=q.team[0])
            elif s.phase in PAUSES:
                for p in s.seating:
                    if p not in s.ready:
                        self.act(p, "ready")
            else:
                return

    def ready(self, *players):
        """These players press Ready in the current pause."""
        for p in players:
            self.act(p, "ready")

    def quest(self, team, fails=(), **special):
        """A whole round: team chosen (round 1) or approved, cards, aftermath."""
        if self.s.round == 1:
            self.first_round(team)
        else:
            self.propose(team)
        self.cards(fails, **special)
        self.settle()


# ---------------------------------------------------------------- scenarios

@dataclass
class Scenario:
    slug : str
    title : str
    about : str                         # the situation and what it tests
    expect : str                        # what should happen: what the tester checks
    roles : list[str]                   # dealt to Ann, Bob, ... in seating order
    setup : Callable[[Drive], None] = lambda d: None
    view : str | None = None            # who to show first; default: who acts
    sizes : list[int] | None = None
    double_fail : int | None = None     # None: default; 0: no quest needs 2 Fails
    lady : bool = False
    group : str = "Game flow"
    rules : dict | None = None          # rule changes (see ruleset.SETTINGS)

    @property
    def players(self) -> list[str]:
        return PLAYER_NAMES[:len(self.roles)]


def P(*idx):
    """Players by seat number: P(0, 2) -> ['Ann', 'Cat']."""
    return [PLAYER_NAMES[i] for i in idx]


def steps(*fns):
    """Several setup steps in order (each takes the Drive)."""
    def run(d):
        for fn in fns:
            fn(d)
    return run


# Seats: Ann Bob Cat Dan Eve Fay Gus Hal Ivy Jon. Ann and Bob propose in
# round 1, Cat proposes first in round 2; each later round starts with the
# player after the last proposer. Team sizes: 5p 2-3-2-3-3, 6p 2-3-4-3-4,
# 7p 2-3-3-4-4 (quest 4 needs 2 Fails from 7p), 8-10p 3-4-4-5-5. Proposals
# per round = Evil + 1 (Gareth counts as Evil): 3 → no Inquisition,
# 4 → Weak on the 1st approval, 5 → Strong on the 1st, Weak on the 2nd.
SEVEN = ["Merlin", "Percival", "Tristan", "Iseult", "Mordred", "Morgana", "Maelegant"]
TEN = ["Merlin", "Percival", "Servant of Camelot", "Tristan", "Iseult", "Arthur",
       "Mordred", "Morgana", "Maelegant", "Minion of Mordred"]
GAWAIN_TEN = ["Merlin", "Percival", "Servant of Camelot", "Gawain", "Tristan", "Iseult",
              "Mordred", "Morgana", "Maelegant", "Agravaine"]
BEAST_NINE = ["Merlin", "Percival", "Tristan", "Iseult", "Mordred", "Morgana", "Pellinore",
              "The Questing Beast", "Maelegant"]
OBERON_SEVEN = ["Merlin", "Percival", "Servant of Camelot", "Servant of Camelot",
                "Mordred", "Morgana", "Oberon"]
GARETH_NINE = ["Merlin", "Percival", "Tristan", "Iseult", "Servant of Camelot",
               "Mordred", "Morgana", "Maelegant"]       # + Gareth as Ivy

GOOD_WINS_SEVEN = lambda d: (d.quest(P(0, 1)), d.quest(P(0, 1, 2)), d.quest(P(0, 1, 2)))


def gawain_round2(d, remove=False):
    """10p, round 2: Cat's team Ann, Gus, Hal, Cat; Gus (Mordred) Fails; Cat
    uses Strong Inquisition on Gus's card (reveals it, or removes it)."""
    d.quest(P(0, 1, 2))
    d.propose(P(0, 6, 7, 2))
    d.cards(fails=P(6))
    d.act("Cat", "inquisition", target="Gus", remove=remove)


SCENARIOS = [
    # ------------------------------------------------------------ Game flow
    Scenario("start", "Start of the game",
             "Round 1 of a 7-player game: Ann and Bob each propose a team of 2.",
             "Ann and Bob each get a team picker for 2 players; everyone else waits. "
             "Once both teams are in, everyone's Vote tab opens to choose one.", SEVEN),
    Scenario("first-round-vote", "First round vote",
             "Both round-1 teams are in (Ann: Ann+Bob, Bob: Bob+Cat); everyone chooses one.",
             "Every player's Vote tab opens with the two teams. Votes stay hidden until all "
             "7 are in; the team with more votes goes on the quest, with no Inquisition "
             "(round 1 never has one).", SEVEN,
             lambda d: (d.act("Ann", "propose_first_round", team=P(0, 1)),
                        d.act("Bob", "propose_first_round", team=P(1, 2)))),
    Scenario("proposal-vote", "Proposal vote",
             "Round 2: Cat proposed Cat, Dan, Eve; everyone approves or rejects.",
             "Everyone's Vote tab opens with Approve / Reject; votes are hidden until all are "
             "in. With 4+ approvals the quest starts and Cat earns Weak Inquisition (first "
             "approval of round 2, 3 Evil); otherwise Dan becomes Leader.", SEVEN,
             lambda d: (d.quest(P(0, 1)), d.act("Cat", "propose", team=P(2, 3, 4)))),
    Scenario("quest-cards", "Choosing quest cards",
             "Round 2 quest with Ann (Merlin), Eve (Mordred) and Gus (Maelegant).",
             "Only Ann, Eve and Gus get card buttons, inside a collapsed box on the Vote tab. "
             "Ann and Eve may play Success or Fail; Gus also Reversal. After the third card "
             "Cat (the Leader) uses Weak Inquisition.", SEVEN,
             lambda d: (d.quest(P(0, 1)), d.propose(P(0, 4, 6))), view="Gus"),
    Scenario("six-players", "First round tie (6 players)",
             "6 players, 2 Evil. Round 1 votes so far: Ann's team (Ann+Bob) 3, Bob's team "
             "(Bob+Cat) 2. Fay casts the last vote.",
             "If Fay votes for Bob's team it's 3-3 and the tie goes to Bob's team (Bob sits "
             "farther from Cat, the round-2 starter, counting forward); the result says so. "
             "Later rounds have 3 proposals each: no Inquisition at all, the 3rd proposal is "
             "the Hammer, and no quest needs 2 Fails.",
             ["Merlin", "Percival", "Tristan", "Iseult", "Mordred", "Morgana"],
             lambda d: (d.act("Ann", "propose_first_round", team=P(0, 1)),
                        d.act("Bob", "propose_first_round", team=P(1, 2)),
                        [d.act(p, "vote_first_round", proposer=c) for p, c in
                         (("Ann", "Ann"), ("Bob", "Bob"), ("Cat", "Bob"),
                          ("Dan", "Ann"), ("Eve", "Ann"))]),
             view="Fay"),
    Scenario("five-players", "Small game (5 players)",
             "5 players, 2 Evil. Round 2: Cat proposed Cat, Dan, Eve.",
             "If approved (3+ of 5) the quest starts with no Inquisition (only 3 proposals a "
             "round). If rejected, Dan then Eve lead; Eve's is the Hammer (3rd proposal): no "
             "vote, and Eve, though Morgana, can't declare instead. No quest needs 2 Fails.",
             ["Merlin", "Percival", "Servant of Camelot", "Mordred", "Morgana"],
             lambda d: (d.quest(P(0, 1)), d.act("Cat", "propose", team=P(2, 3, 4)))),
    Scenario("hammer-morgana", "Hammer without Changeling",
             "Round 2, 7 players, no Oberon: three proposals rejected, so Fay (Morgana) "
             "proposes the Hammer.",
             "Fay can only propose: no Sorceress on the Hammer. The team goes straight to "
             "choosing cards: no vote, no Ready pause (Oberon isn't possible), and no "
             "Inquisition on the Hammer.", SEVEN,
             lambda d: (d.quest(P(0, 1)), d.reject_until_hammer(P(0, 1, 2)))),

    # ------------------------------------------------------------ Role info
    Scenario("lonely-roles", "Lonely roles",
             "Start of a 7-player game with the lonely forms: Ann Nilrem, Bob Galahad, "
             "Cat Uther, Dan Ygraine; Evil Eve Mordred, Fay Morgana, Gus Maelegant.",
             "Role tabs: Bob, Cat and Dan are told Ann is Nilrem; Ann and the Evil players "
             "aren't. Bob (Galahad) is told the Evil roles are Mordred, Morgana and "
             "Maelegant, but not who has them. Cat (Uther) stalks Bob or Dan (never Ann). "
             "Dan (Ygraine) stalks Fay or Gus (never Mordred).",
             ["Nilrem", "Galahad", "Uther", "Ygraine", "Mordred", "Morgana", "Maelegant"],
             view="Bob", group="Role info"),
    Scenario("guinevere-court", "Guinevere, Arthur and Lancelot",
             "Start of an 8-player game: Ann Merlin, Bob Percival, Cat Guinevere, Dan "
             "Lancelot, Eve Arthur; Evil Fay Mordred, Gus Morgana, Hal Maelegant.",
             "Cat (Guinevere) sees Dan, Eve and Hal (Lancelot, Arthur, Maelegant) without "
             "being told which is which. Eve (Arthur) is told the Good roles: Merlin, "
             "Percival, Guinevere, Lancelot, Arthur. Ann (Merlin) sees Dan, Gus, Hal as Evil "
             "(Lancelot looks Evil; Mordred hidden). Bob (Percival) sees Ann and Gus.",
             ["Merlin", "Percival", "Guinevere", "Lancelot", "Arthur", "Mordred", "Morgana",
              "Maelegant"],
             view="Cat", group="Role info"),
    Scenario("colgrevance-oberon", "Colgrevance and Oberon",
             "Start of a 10-player game: Gawain (Eve), Arthur (Fay); Evil Gus Mordred, "
             "Hal Colgrevance, Ivy Oberon, Jon Morgana.",
             "Hal (Colgrevance) sees Gus as Mordred, Ivy as Oberon, Jon as Morgana. Gus and "
             "Jon see each other and Hal, not Ivy, and are told an Oberon is in the game. "
             "Ivy (Oberon) sees Gus, Hal and Jon. Eve (Gawain) sees three players, at least "
             "one of them Good. Ann (Merlin) sees Hal, Ivy, Jon (not Mordred).",
             ["Merlin", "Percival", "Tristan", "Iseult", "Gawain", "Arthur", "Mordred",
              "Colgrevance", "Oberon", "Morgana"],
             view="Hal", group="Role info"),
    Scenario("balin-agravaine", "Balin and Agravaine",
             "Start of a 9-player game: Cat is Balin the Savage, Hal is Agravaine.",
             "Cat (Balin) is told Hal is Agravaine; Hal (Agravaine) is told Cat is Balin. "
             "Ann (Merlin) sees Cat as Evil along with Gus, Hal and Ivy (not Fay, Mordred).",
             ["Merlin", "Percival", "Balin the Savage", "Tristan", "Iseult", "Mordred",
              "Morgana", "Agravaine", "Maelegant"],
             view="Cat", group="Role info"),

    # ------------------------------------------------------------ Abilities
    Scenario("hammer", "Hammer and Changeling",
             "Round 2: three proposals rejected; Fay proposed the Hammer (Ann, Bob, Cat). "
             "Oberon (Gus) isn't on it.",
             "No vote. Everyone presses Ready; Gus's Role tab offers Changeling: replace one "
             "of Ann, Bob, Cat. A swap is announced, changes the team and resets everyone's "
             "Ready. Then the team plays cards, with no Inquisition.",
             OBERON_SEVEN,
             lambda d: (d.quest(P(0, 1)), d.reject_until_hammer(P(0, 1, 2)),
                        d.act(d.s.leader, "propose", team=P(0, 1, 2))),
             view="Gus", group="Abilities"),
    Scenario("sorceress", "Sorceress",
             "Round 2: Cat (Morgana) is Leader.",
             "Cat may propose as usual, or declare as Morgana on the Role tab and choose the "
             "next Leader among players who haven't proposed this round. The declaration "
             "is announced and the proposal order reverses.",
             ["Merlin", "Percival", "Morgana", "Tristan", "Iseult", "Mordred", "Maelegant"],
             lambda d: d.quest(P(0, 1)), group="Abilities"),
    Scenario("weak-inquisition", "Weak Inquisition",
             "Round 2: the first proposal (Ann, Eve, Fay) was approved; Eve played Fail.",
             "Cat (the Leader) picks one of Ann, Eve, Fay; that card is shown to everyone. "
             "There's no option to remove a card. The result follows: 1 Fail, the quest "
             "fails.",
             SEVEN, lambda d: (d.quest(P(0, 1)), d.propose(P(0, 4, 5)), d.cards(fails=P(4))),
             group="Abilities"),
    Scenario("strong-inquisition", "Strong Inquisition",
             "10 players, 4 Evil: the first approved proposal of round 2 (Ann, Gus, Hal, "
             "Dan) gives Cat Strong Inquisition. Gus (Mordred) played Fail.",
             "Cat may reveal one card to everyone, or remove one card unseen. Removing Gus's "
             "card makes the quest succeed (only Successes left, three cards shown); "
             "revealing it shows a Fail and the quest fails.",
             TEN, lambda d: (d.quest(P(0, 1, 2)), d.propose(P(0, 6, 7, 3)), d.cards(fails=P(6))),
             group="Abilities"),
    Scenario("gawain", "Gawain's Inquisition",
             "10 players. Round 2 cards are in (Gus played Fail) and Cat's Inquisition "
             "revealed Cat's own card. Gawain (Dan) isn't on the quest.",
             "Everyone gets Ready. Dan's Role tab offers to declare and make Ann, Gus or Hal "
             "(not Cat, already shown) reveal their card. The card is shown at once; a "
             "Success exiles Gawain (no more Gawain pauses), a Fail doesn't. The Ready "
             "presses reset.",
             GAWAIN_TEN,
             lambda d: (d.quest(P(0, 1, 2)), d.propose(P(0, 6, 7, 2)),
                        d.cards(fails=P(6)), d.inquisition(pick=3)),
             view="Dan", group="Abilities"),
    Scenario("betrayal", "Betrayal",
             "Round 2 needs 2 Fails; Agravaine (Eve) played the only Fail, so the quest "
             "succeeded.",
             "Everyone gets Ready. Eve's Role tab offers Betrayal: declaring makes the quest "
             "fail, announced to all, and resets Ready. Without it, round 3 starts.",
             ["Merlin", "Percival", "Tristan", "Iseult", "Agravaine", "Morgana", "Mordred"],
             lambda d: (d.quest(P(0, 1)), d.propose(P(0, 1, 4)), d.cards(), d.inquisition()),
             double_fail=2, view="Eve", group="Abilities"),
    Scenario("proclamation", "Proclamation",
             "Two quests failed: Arthur (Bob) may proclaim.",
             "Bob's Role tab offers Proclaim at any moment (not only on his turn). Using it "
             "announces to everyone that Bob is Arthur; it can't be used again.",
             ["Merlin", "Arthur", "Percival", "Servant of Camelot", "Mordred", "Morgana",
              "Maelegant"],
             lambda d: (d.quest(P(0, 4), fails=P(4)), d.quest(P(2, 4, 5), fails=P(4))),
             view="Bob", group="Abilities"),
    Scenario("lady", "Lady of the Lake",
             "After quest 2, the Lady's holder (Bob, the player before Cat) uses her.",
             "Bob picks any other player; only Bob is shown that player's team (Good/Evil). "
             "Everyone sees whom the Lady went to; that player holds her after quest 3.",
             SEVEN,
             lambda d: (d.quest(P(0, 1)), d.quest(P(2, 3, 4), fails=P(4))),
             lady=True, group="Abilities"),
    Scenario("questing-beast", "Pellinore and the Questing Beast",
             "9 players. Round 2 quest with the Beast (Hal) and Pellinore (Gus).",
             "Hal can only play Questing Beast Was Here; Gus only Success. After the reveal "
             "the Beast's card counts as a Fail (fewer than 2 quests failed, none seen "
             "before), so the quest fails, and the result says what it counted as.",
             BEAST_NINE,
             lambda d: (d.quest(P(0, 1, 2)), d.propose(P(6, 7, 0, 1))),
             view="Hal", group="Abilities"),

    # ------------------------------------------------------------ Ability chains
    Scenario("sorceress-reversed", "After the Sorceress",
             "Round 2: Cat (Morgana) declared and chose Fay; the order is now reversed.",
             "Fay leads (proposal 2 of 4: the declaration counts as one). If Fay's team is "
             "rejected, Eve leads, then Dan, whose proposal is the Hammer. The Game tab "
             "shows Cat declared as Morgana.",
             ["Merlin", "Percival", "Morgana", "Tristan", "Iseult", "Mordred", "Maelegant"],
             lambda d: (d.quest(P(0, 1)), d.act("Cat", "sorceress", next_proposer="Fay")),
             view="Fay", group="Ability chains"),
    Scenario("changeling-used", "After the Changeling",
             "Round 2 Hammer (Ann, Bob, Cat): Ann and Bob had pressed Ready, then Gus "
             "(Oberon) swapped in for Cat.",
             "Everyone sees Gus declared as Oberon and the team is Ann, Bob, Gus. Ann and Bob "
             "must press Ready again. Gus has no Changeling left. Once all are Ready, Ann, "
             "Bob and Gus play cards (Gus may Fail), with no Inquisition.",
             OBERON_SEVEN,
             lambda d: (d.quest(P(0, 1)), d.reject_until_hammer(P(0, 1, 2)),
                        d.act(d.s.leader, "propose", team=P(0, 1, 2)),
                        d.ready("Ann", "Bob"), d.act("Gus", "changeling", replaced="Cat")),
             view="Ann", group="Ability chains"),
    Scenario("strong-remove-reversal", "Strong Inquisition and Reversal",
             "10 players, round 2: Ann and Dan played Success, Gus (Mordred) Fail, Ivy "
             "(Maelegant) Reversal. Cat has Strong Inquisition.",
             "As played the Reversal cancels the Fail: the quest succeeds. Remove Ivy's "
             "Reversal: it fails (1 Fail). Remove Gus's Fail: it still fails (the Reversal "
             "turns a Success into a Fail). Remove a Success, or just reveal: it succeeds.",
             TEN,
             lambda d: (d.quest(P(0, 1, 2)), d.propose(P(0, 3, 6, 8)),
                        d.cards(fails=P(6), Ivy="Reversal")),
             view="Cat", group="Ability chains"),
    Scenario("inquisition-order", "Inquisition on the second proposal",
             "10 players, 4 Evil (5 proposals a round). Round 2: Cat's proposal was "
             "rejected, Dan's (Ann, Dan, Gus, Hal) approved; Gus played Fail.",
             "Dan has Weak Inquisition (2nd approved proposal): reveal only, no remove. "
             "Strong is still unused, so the first approved proposal of round 3 will give "
             "Strong; after that, no more Inquisitions.",
             TEN,
             lambda d: (d.quest(P(0, 1, 2)), d.propose(P(0, 1, 2, 3), approve=False),
                        d.propose(P(0, 3, 6, 7)), d.cards(fails=P(6))),
             view="Dan", group="Ability chains"),
    Scenario("reversal-results", "Reversal results",
             "7 players, round 5 about to start; the Game tab shows four quests: "
             "2: Fail + Reversal; 3: two Reversals (Lancelot Bob, Maelegant Gus) + Fail; "
             "4 (needs 2 Fails): one Fail + Reversal.",
             "Quest 1 and 2 succeeded (the Reversal flipped the Fail), quest 3 failed (the "
             "Reversals cancel, the Fail stands), quest 4 failed (the Reversal turned a "
             "Success into the 2nd Fail). Score 2-2; Fay leads round 5.",
             ["Merlin", "Lancelot", "Percival", "Servant of Camelot", "Mordred", "Morgana",
              "Maelegant"],
             lambda d: (d.quest(P(0, 2)),
                        d.quest(P(0, 4, 6), fails=P(4), Gus="Reversal"),
                        d.quest(P(1, 4, 6), fails=P(4), Bob="Reversal", Gus="Reversal"),
                        d.quest(P(0, 2, 4, 6), fails=P(4), Gus="Reversal")),
             view="Ann", group="Ability chains"),
    Scenario("reversal-betrayal", "Reversal, then Betrayal",
             "Two quests have failed. Round 3: Agravaine (Eve) had to play Fail, but Gus "
             "(Maelegant) played Reversal, so the quest succeeded.",
             "Everyone gets Ready. If Eve Betrays, the quest fails, that's the 3rd failure "
             "and the game ends straight away: Evil wins (no Assassination). Otherwise "
             "round 4 starts at 1-2.",
             ["Merlin", "Percival", "Tristan", "Iseult", "Agravaine", "Morgana", "Maelegant"],
             lambda d: (d.quest(P(0, 5), fails=P(5)), d.quest(P(0, 1, 5), fails=P(5)),
                        d.propose(P(0, 4, 6)), d.cards(Gus="Reversal")),
             view="Eve", group="Ability chains"),
    Scenario("gawain-exiled", "Gawain exiled",
             "10 players. In round 2 Gawain (Dan) made Ann reveal a Success, so Gawain was "
             "exiled. Round 3: Dan's team (Ann, Bob, Cat, Gus) played; Gus played Fail.",
             "Dan uses Weak Inquisition (Strong was used in round 2). Then the cards are "
             "revealed at once: no Ready pause for Gawain, since Gawain is exiled. The quest "
             "fails.",
             GAWAIN_TEN,
             lambda d: (gawain_round2(d), d.act("Dan", "gawain", target="Ann"), d.settle(),
                        d.propose(P(0, 1, 2, 6)), d.cards(fails=P(6))),
             view="Dan", group="Ability chains"),
    Scenario("gawain-after-removal", "Gawain after a removed card",
             "10 players, round 2 (Ann, Gus, Hal, Cat): Gus played Fail and Cat's Strong "
             "Inquisition removed Gus's card.",
             "Dan (Gawain) may only pick Ann, Hal or Cat (not the removed card). All of them "
             "played Success, so declaring exiles Gawain. Then the quest succeeds and, as "
             "Agravaine (Jon) might betray, there is another Ready pause.",
             GAWAIN_TEN, lambda d: gawain_round2(d, remove=True),
             view="Dan", group="Ability chains"),
    Scenario("beast-late-game", "The Beast late in the game",
             "9 players. The Beast (Hal) was on quests 1 and 2, which both failed because "
             "of it. Round 3 team: Gus (Pellinore), Hal, Ann, Bob.",
             "Two Beast cards have been seen, so Gus (Pellinore) may only play Fail now, and "
             "Hal's card will count as a Success. Gus's Fail fails the quest: the 3rd "
             "failure, so the game goes to Pellinore's guess.",
             BEAST_NINE,
             lambda d: (d.quest(P(7, 0, 1)), d.quest(P(7, 0, 1, 2)),
                        d.propose(P(6, 7, 0, 1))),
             view="Gus", group="Ability chains"),
    Scenario("lady-chain-gareth", "Lady of the Lake and Gareth",
             "9 players, Gareth (Ivy) is Evil. After quest 2 Bob sent the Lady to Ivy; after "
             "quest 3 Ivy holds her.",
             "Bob's Role tab says the Lady showed Ivy as Good (Gareth always shows Good by "
             "default). Ivy may send the Lady to anyone except Bob and Ivy (previous "
             "holders); only Ivy sees the result.",
             GARETH_NINE + ["Gareth (Evil)"],
             lambda d: (d.quest(P(0, 1, 2)), d.quest(P(2, 3, 4, 5), fails=P(5)),
                        d.act("Bob", "lady", target="Ivy"), d.quest(P(0, 1, 2, 3))),
             lady=True, view="Ivy", group="Ability chains"),

    # ------------------------------------------------------------ End of game
    Scenario("pellinore-guess", "Pellinore's guess",
             "9 players. Good won 3 quests; Pellinore (Gus) names who they think is the "
             "Beast, then the Assassination.",
             "Gus picks a player (or no one); the guess isn't revealed yet. Then Eve "
             "(Mordred) assassinates. The game-over screen shows whether Gus was right and "
             "both Neutral scores.",
             BEAST_NINE,
             lambda d: (d.quest(P(0, 1, 2)), d.quest(P(0, 1, 2, 3)), d.quest(P(0, 1, 2, 3))),
             group="End of game"),
    Scenario("pellinore-evil-wins", "Pellinore's guess when Evil wins",
             "9 players. Three quests failed; the Beast (Hal) was on quest 3, never with "
             "Pellinore (Gus).",
             "Gus guesses, then the game ends at once (no Assassination when Evil wins). "
             "Naming Hal: Pellinore wins (sanity 4), the Beast loses (2 points). Naming "
             "anyone else: Pellinore loses (sanity 1), the Beast wins (5 points).",
             BEAST_NINE,
             lambda d: (d.quest(P(0, 1, 4), fails=P(4)), d.quest(P(0, 1, 4, 6), fails=P(4)),
                        d.quest(P(0, 1, 5, 7), fails=P(5))),
             view="Gus", group="End of game"),
    Scenario("assassination", "Assassination",
             "Good won 3 quests. Mordred (Eve) decides.",
             "Eve chooses: one player as Merlin or Nilrem, two as the Lovers, or no one. "
             "Naming Ann as Merlin, or Cat and Dan as the Lovers, wins for Evil; anything "
             "else (Nilrem isn't in the game, so 'no one' is wrong too) wins for Good.",
             SEVEN, GOOD_WINS_SEVEN, group="End of game"),
    Scenario("assassin-without-mordred", "Assassination without Merlin or Mordred",
             "7 players with no Merlin, Nilrem or Lovers, and no Mordred. Good won 3 quests.",
             "Eve (Morgana) is the assassin (highest-ranked Evil). The only right answer is "
             "'no one', since no possible target is in the game: that wins for Evil; "
             "naming anyone wins for Good.",
             ["Percival", "Arthur", "Lancelot", "Servant of Camelot", "Morgana", "Maelegant",
              "Oberon"],
             lambda d: (d.quest(P(0, 1)), d.quest(P(0, 1, 2)), d.quest(P(0, 1, 2))),
             view="Eve", group="End of game"),
    Scenario("good-wins", "Good wins",
             "Good won 3 quests and Mordred (Eve) named Bob (Percival) as Merlin.",
             "Game-over screen for everyone: Good wins, the Assassination named Bob as "
             "Merlin and was wrong, and every player's role is shown.",
             SEVEN,
             lambda d: (GOOD_WINS_SEVEN(d), d.act("Eve", "assassinate", kind="merlin",
                                                  targets=["Bob"])),
             view="Ann", group="End of game"),
    Scenario("evil-wins-assassination", "Evil wins the Assassination",
             "Good won 3 quests and Mordred (Eve) named Cat and Dan as the Lovers.",
             "Game-over screen: Evil wins, the Assassination of the Lovers was right, roles "
             "shown.",
             SEVEN,
             lambda d: (GOOD_WINS_SEVEN(d), d.act("Eve", "assassinate", kind="lovers",
                                                  targets=["Cat", "Dan"])),
             view="Ann", group="End of game"),
    Scenario("evil-wins", "Evil wins",
             "Three quests failed: the game is over.",
             "Game-over screen: Evil wins by failing 3 quests; no Assassination; roles "
             "shown.", SEVEN,
             lambda d: (d.quest(P(0, 4), fails=P(4)), d.quest(P(0, 1, 4), fails=P(4)),
                        d.quest(P(0, 1, 5), fails=P(5))),
             view="Ann", group="End of game"),

    # ------------------------------------------------------------ Changed rules
    Scenario("changed-rules", "Changed rules: who sees whom, Assassination",
             "Changed: Merlin sees Mordred but not Lancelot, Percival sees only Merlin, Evil "
             "may not name no one and may also assassinate Percival. Good won 3 quests.",
             "Ann (Merlin) sees Eve, Fay, Gus, not Cat (Lancelot); Bob (Percival) sees only "
             "Ann; those lines are tagged \"changed\". Eve's choices: Merlin, Nilrem, "
             "Percival or the Lovers, no 'no one'. Rules pages show the changes in a box.",
             ["Merlin", "Percival", "Lancelot", "Servant of Camelot", "Mordred", "Morgana",
              "Maelegant"],
             GOOD_WINS_SEVEN,
             rules={"Merlin.sees.Mordred": True, "Merlin.sees.Lancelot": False,
                    "Percival.sees.Morgana": False, "assassination.none": False,
                    "assassination.target.percival": True},
             group="Changed rules"),
    Scenario("changed-abilities", "Changed rules: abilities",
             "Changed: Agravaine may play Success, Lancelot and Maelegant have no Reversal, "
             "Arthur may proclaim after 1 failed quest. Quest 1 failed; round 2 quest: Cat "
             "(Lancelot), Eve (Agravaine), Gus (Maelegant).",
             "Eve may play Success or Fail; Cat and Gus only Success or Fail. Bob (Arthur) "
             "can already Proclaim. Their Role tabs show these lines tagged \"changed\".",
             ["Merlin", "Arthur", "Lancelot", "Percival", "Agravaine", "Mordred", "Maelegant"],
             lambda d: (d.quest(P(0, 5), fails=P(5)), d.propose(P(2, 4, 6))),
             rules={"Agravaine.must_fail": False, "Lancelot.reversal": False,
                    "Maelegant.reversal": False, "Arthur.proclaim_after": 1},
             view="Eve", group="Changed rules"),
    Scenario("changed-info", "Changed rules: Oberon, Nilrem, Guinevere, no Assassination",
             "Changed: Evil see Oberon, Oberon sees no one, Good aren't told Nilrem, "
             "Guinevere doesn't see Arthur, no Assassination. 8 players; 2 quests "
             "succeeded; round 3 team is all Good.",
             "Bob, Cat, Dan, Eve are not told Ann is Nilrem. Bob (Guinevere) sees only Dan "
             "(Lancelot), not Cat (Arthur). Fay and Gus see Hal as Evil and aren't told "
             "\"an Oberon is in the game\"; Hal (Oberon) sees nobody. When this quest "
             "succeeds, Good wins at once: no Assassination.",
             ["Nilrem", "Guinevere", "Arthur", "Lancelot", "Servant of Camelot", "Mordred",
              "Morgana", "Oberon"],
             lambda d: (d.quest(P(0, 1, 2)), d.quest(P(0, 1, 2, 3)),
                        d.propose(P(0, 1, 2, 3))),
             rules={"Oberon.seen_by_evil": True, "Oberon.sees_evil": False,
                    "Nilrem.known": False, "Guinevere.sees.Arthur": False,
                    "assassination.enabled": False},
             view="Bob", group="Changed rules"),

    # ------------------------------------------------------------ Gareth
    # Gareth (Ivy) is 9th: the Knight is the first player of Gareth's team, the
    # Rival the first of the other (Evil: Fay is the Knight, Ann the Rival;
    # Good: Ann is the Knight, Fay the Rival).
    Scenario("gareth-evil", "Gareth on Evil",
             "9 players, Gareth (Ivy) is Evil: Knight Fay (Mordred), Rival Ann (Merlin).",
             "Ivy's Role tab: team unknown, Knight Fay, Rival Ann. Ann (Merlin) sees Gus, "
             "Hal and Ivy as Evil. Fay, Gus and Hal see Ivy among the Evil players.",
             GARETH_NINE + ["Gareth (Evil)"], view="Ivy", group="Gareth"),
    Scenario("gareth-good", "Gareth on Good",
             "9 players, Gareth (Ivy) is Good: Knight Ann (Merlin), Rival Fay (Mordred).",
             "Ivy's Role tab: team unknown, Knight Ann, Rival Fay. Nobody sees Ivy: not Merlin, "
             "not the Evil players. The game still has 5 proposals a round (Gareth counts "
             "as Evil for that).",
             GARETH_NINE + ["Gareth (Good)"], view="Ivy", group="Gareth"),
    Scenario("gareth-assassination", "Gareth at the Assassination",
             "9 players, Gareth (Ivy) is Evil. Good won 3 quests.",
             "Ivy's Role tab now tells Ivy they are Evil, so they can join the Evil "
             "discussion. Fay (Mordred) makes the call, not Ivy.",
             GARETH_NINE + ["Gareth (Evil)"],
             lambda d: (d.quest(P(0, 1, 2)), d.quest(P(0, 1, 2, 3)), d.quest(P(0, 1, 2, 3))),
             view="Ivy", group="Gareth"),
    Scenario("gareth-changed-rules", "Gareth with changed rules",
             "9 players, Gareth (Ivy) is Good. Changed: Gareth knows only their Knight, "
             "Merlin sees a Good Gareth as Evil, the Lady shows Gareth's real team. After "
             "quest 2, Bob holds the Lady.",
             "Ivy's Role tab names only the Knight (Ann). Ann (Merlin) sees Ivy among the "
             "Evil players. If Bob sends the Lady to Ivy, Bob is shown Good (the real team). "
             "Changed lines are tagged \"changed\".",
             GARETH_NINE + ["Gareth (Good)"],
             lambda d: (d.quest(P(0, 1, 2)), d.quest(P(2, 3, 4, 5), fails=P(5))),
             lady=True, rules={"Gareth.knows": "knight", "Gareth.Good.merlin_sees": True,
                               "Gareth.lady": "team"},
             view="Ivy", group="Gareth"),

    # ------------------------------------------------------------ Host
    Scenario("host-votes", "Host votes",
             "Round 2, Cat proposing. Use the host page to start votes by hand.",
             "The host can start a proposal vote (pick a team) or a quest vote (pick who "
             "plays). Those players' Vote tabs open; quest votes offer Success, Fail and "
             "Reversal to everyone. Ending it shows the result; the game itself is unchanged.",
             SEVEN, lambda d: d.quest(P(0, 1)), view="host", group="Host"),
    Scenario("host-pause", "Host: skip waiting and undo",
             "10 players, Gawain's Ready pause in round 2: everyone except Dan has pressed "
             "Ready (Jon last).",
             "The host page shows \"Skip waiting\" and \"Undo: Jon pressed ready\". Undo makes "
             "Jon not ready again. Skip ends the pause without Dan: the cards are revealed "
             "and, since that reveals cards, it can't be undone.",
             GAWAIN_TEN,
             lambda d: (gawain_round2(d), d.ready(*[p for p in d.s.seating if p != "Dan"])),
             view="host", group="Host"),
]
BY_SLUG = {s.slug: s for s in SCENARIOS}


def make_builder(players : list[str], role_names : list[str],
                 rules : RuleSet | None = None) -> AvalonBuilder:
    """Roles dealt exactly as listed (no shuffling, no lonely transformations).

    Gareth: "Gareth (Good)" or "Gareth (Evil)" ("Gareth" alone is Evil). The
    Knight is the first listed player of Gareth's team, the Rival the first
    of the other team."""
    roles = {}
    soc = mom = 0
    gareth = None
    for player, name in zip(players, role_names):
        if name == "Servant of Camelot":
            roles[player] = T.SoC(soc); soc += 1
        elif name == "Minion of Mordred":
            roles[player] = T.MoM(mom); mom += 1
        elif name.startswith("Gareth"):
            gareth = (player, "Good" if name == "Gareth (Good)" else "Evil")
        else:
            roles[player] = T.string_to_role[name]
    if gareth is not None:
        player, team = gareth
        first = lambda t: next(p for p, r in roles.items() if r.allegiance() == t)
        roles[player] = T.Gareth(team, first(team), first("Evil" if team == "Good" else "Good"))
    return AvalonBuilder.with_roles(roles, rules, players=list(players))


# ---------------------------------------------------------------- feedback

def game_snapshot(game) -> dict:
    """Everything about a game, secrets included, for a feedback email."""
    ctl = game.controller
    if ctl is None:
        return {}
    s = ctl.state
    q = s.current_quest
    p = s.current_proposal
    hv = game.host_vote
    return dict(
        phase=s.phase.value, round=s.round, leader=s.leader,
        roles={pl: s.role(pl) for pl in s.seating},
        secret=dict(
            current_quest_cards={k: v.value for k, v in q.cards.items()} if q else None,
            current_proposal_votes=dict(p.votes) if p else None,
            first_round_votes=dict(s.first_round_votes),
            ready=sorted(s.ready),
            lady_uses=s.lady_uses,
            host_vote_ballots=dict(hv.ballots) if hv else None,
        ),
        host_vote=hv.view() if hv else None,
        undo=ctl.undo_label(),
        view=ctl.view(None, scoped=False),
        log=s.log,
    )


def send_email(to : str, subject : str, text : str, reply_to : str | None = None,
               sender : str | None = None):
    """Through Amazon SES with the server's instance role (aws CLI), like the
    maths site's feedback emails. Raises on failure."""
    # The service's PATH is only the app's virtualenv; the CLI is a system tool.
    aws = shutil.which("aws", path=os.environ.get("PATH", "") + ":/usr/local/bin:/usr/bin")
    if aws is None:
        raise RuntimeError("aws CLI not found")
    content = {"Simple": {"Subject": {"Data": subject[:200], "Charset": "UTF-8"},
                          "Body": {"Text": {"Data": text, "Charset": "UTF-8"}}}}
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
        json.dump(content, f)
        f.flush()
        cmd = [aws, "sesv2", "send-email",
               "--region", os.environ.get("AWS_REGION", "eu-west-2"),
               "--from-email-address", sender or to,
               "--destination", json.dumps({"ToAddresses": [to]}),
               "--content", f"file://{f.name}"]
        if reply_to:
            cmd += ["--reply-to-addresses", reply_to]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)


# ---------------------------------------------------------------- the app

def init_app(app, registration_exempt : list[str]):
    """Add the dev pages to the app; `registration_exempt`: the app's paths
    that need no player name."""

    bp = Blueprint("dev", __name__, url_prefix="/dev")

    # Every tester (browser session) gets their own copy of each scenario,
    # kept on the server under a random id stored in their session.
    def tester() -> str:
        if "dev_tester" not in session:
            session["dev_tester"] = secrets.token_hex(4)
        return session["dev_tester"]

    def uuid_of(slug, who):
        return f"dev-{tester()}-{slug}-{who}"

    def lobby_id(slug):
        return f"dev-{tester()}-{slug}"

    def build(sc : Scenario):
        """A fresh lobby with the scenario's game, replacing this tester's earlier one."""
        players = {uuid_of(sc.slug, n): n for n in sc.players}
        lobby = Lobby(uuid_of(sc.slug, "host"), f"Test: {sc.title}")
        lobby.id = lobby_id(sc.slug)
        lobby._players = dict(players)
        old = LOBBIES.get(lobby.id)
        if old is not None:      # keep counting games, so vote keys never repeat
            lobby.current_game.game_number = old.current_game.game_number
        ruleset = RuleSet(sc.rules)
        roles = [r for r in make_builder(sc.players, sc.roles)]
        settings = GameSettings()
        settings.num_evils = sum(r.allegiance() == "Evil" and str(r) != "Gareth" for r in roles)
        settings.team_sizes = sc.sizes
        settings.double_fail = sc.double_fail
        settings.lady = sc.lady
        rules = settings.resolve(len(players), roles, ruleset)
        builder = make_builder(sc.players, sc.roles, ruleset)
        lobby.current_game.install(builder, roles, players, rules)
        sc.setup(Drive(lobby.current_game.controller))
        LOBBIES.add(lobby)
        events.publish(lobby.id, "new-game")
        events.publish(lobby.id, "game-update")
        return lobby

    def current():
        """(scenario, lobby, who) this session is looking at, or Nones."""
        sc = BY_SLUG.get(session.get("dev_slug"))
        if sc is None:
            return None, None, None
        return sc, LOBBIES.get(lobby_id(sc.slug)), session.get("dev_as")

    def view_as(sc : Scenario, lobby, who : str):
        session["dev_slug"] = sc.slug
        session["dev_as"] = who
        session["player_id"] = uuid_of(sc.slug, who)
        session["game_id"] = lobby.id
        if who != "host":
            session["name"] = who
        return flask.redirect(url_for("host.page") if who == "host" else url_for("player.index"))

    @bp.route("/")
    def index():
        groups = {}
        for sc in SCENARIOS:
            groups.setdefault(sc.group, []).append(sc)
        return flask.render_template("dev/index.html", groups=groups)

    @bp.route("/<slug>")
    def start(slug):
        sc = BY_SLUG.get(slug) or flask.abort(404)
        lobby = build(sc)
        who = request.args.get("as") or sc.view
        if who is None:
            waiting = lobby.current_game.controller.view()["waiting_for"]
            who = waiting[0] if waiting else sc.players[0]
        return view_as(sc, lobby, who)

    @bp.route("/<slug>/as/<who>")
    def switch(slug, who):
        sc = BY_SLUG.get(slug) or flask.abort(404)
        if who != "host" and who not in sc.players:
            flask.abort(404)
        lobby = LOBBIES.get(lobby_id(slug)) or build(sc)
        return view_as(sc, lobby, who)

    @bp.route("/bar")
    def bar():
        return dev_bar()

    def dev_bar() -> Markup:
        sc, lobby, who = current()
        ctx = dict(scenario=sc, who=who, seats=[], waiting=[])
        if sc and lobby and lobby.current_game.controller:
            state = lobby.current_game.controller.state
            ctx["seats"] = [(p, state.role(p)) for p in state.seating]
            ctx["waiting"] = lobby.current_game.controller.view()["waiting_for"]
        return Markup(flask.render_template("dev/bar.html", **ctx))

    @app.context_processor
    def inject_dev_bar():
        return dict(dev_bar=dev_bar)

    # ---- feedback, emailed with the game's full state ----

    feedback_to = os.environ.get("DEV_FEEDBACK_EMAIL", "").strip()
    feedback_from = os.environ.get("DEV_FEEDBACK_FROM", "").strip() or feedback_to

    @bp.route("/feedback", methods=["GET", "POST"])
    def feedback():
        sc, lobby, who = current()
        page = request.values.get("page") or ""
        if not page.startswith("/") or page.startswith("//"):
            page = ""          # only pages on this site (it's used as a link)
        if request.method == "GET":
            return flask.render_template("dev/feedback.html", scenario=sc, who=who,
                                         page=page, configured=bool(feedback_to))
        text = request.form.get("description", "").strip()
        if not text:
            return flask.render_template("dev/feedback.html", scenario=sc, who=who, page=page,
                                         configured=bool(feedback_to),
                                         error="Describe what happened first."), 400
        tester_email = g.get("dev_email")
        report = dict(
            time=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            tester=tester_email, tester_id=session.get("dev_tester"),
            scenario=dict(slug=sc.slug, title=sc.title, about=sc.about) if sc else None,
            viewing_as=who, page=page,
            user_agent=request.headers.get("User-Agent"),
            game=game_snapshot(lobby.current_game) if lobby else None,
        )
        where = f"{sc.title} as {who}" if sc else "no scenario"
        body = (f"{text}\n\n"
                f"-- \nFrom: {tester_email or 'unknown tester'}\n"
                f"Scenario: {where}\nPage: {page or '?'}\n"
                f"Phase: {(report['game'] or {}).get('phase', '-')}\n\n"
                f"Full report (JSON):\n{json.dumps(report, indent=2, default=str)}\n")
        subject = f"[Avalon dev] {where}: {text.splitlines()[0][:80]}"
        if not feedback_to:
            app.logger.warning("Feedback not sent (DEV_FEEDBACK_EMAIL unset):\n%s", body)
            return flask.render_template("dev/feedback.html", scenario=sc, who=who, page=page,
                                         configured=False,
                                         error="Feedback isn't set up on this server."), 503
        try:
            app.config.get("DEV_SEND_EMAIL", send_email)(
                feedback_to, subject, body, reply_to=tester_email, sender=feedback_from)
        except Exception as e:
            app.logger.error("Feedback email failed: %s\n%s", e, body)
            return flask.render_template("dev/feedback.html", scenario=sc, who=who, page=page,
                                         configured=True, description=text,
                                         error="Sending failed. Try again in a moment."), 502
        return flask.render_template("dev/feedback.html", scenario=sc, who=who, page=page,
                                     configured=True, sent=True)

    # ---- access check: runs before everything else ----

    access = AccessCheck(os.environ.get("CF_ACCESS_TEAM_DOMAIN", ""),
                         os.environ.get("CF_ACCESS_AUD", ""))
    allowed = {e.strip().lower() for e in os.environ.get("DEV_ALLOWED_EMAILS", "").split(",")
               if e.strip()}

    def check_access():
        if app.config.get("DEV_NO_AUTH"):
            return None
        if not access.configured:
            return flask.Response("Dev site is not configured.", 403)
        email = access.email(request)
        if email is None or (allowed and email not in allowed):
            return flask.Response("Forbidden.", 403)
        g.dev_email = email or None
        return None

    app.before_request_funcs.setdefault(None, []).insert(0, check_access)
    # The dev pages don't need a player name.
    registration_exempt.append("/dev")
    app.register_blueprint(bp)
