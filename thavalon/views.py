"""The game as one player may see it (or the public, with no player).

Views are plain dicts for the pages to render. They never contain other
players' cards, votes before a vote is complete, or roles nobody declared.
"""
from __future__ import annotations

from thavalon.state import GameState, Phase, PAUSES, Proposal, Quest

# Log entries in which a player publicly reveals their role: the role, and
# the entry's field naming the player.
DECLARATIONS = {"sorceress": ("Morgana", "morgana"), "changeling": ("Oberon", "oberon"),
                "gawain": ("Gawain", "gawain"), "betrayal": ("Agravaine", "agravaine"),
                "proclamation": ("Arthur", "arthur")}


def declarations(s : GameState) -> list[dict]:
    """Players who have publicly revealed their role, in order."""
    seen, out = set(), []
    for e in s.log:
        if e["type"] in DECLARATIONS:
            role, field = DECLARATIONS[e["type"]]
            if e[field] not in seen:
                seen.add(e[field])
                out.append(dict(player=e[field], role=role))
    return out


def view(s : GameState, player : str | None, actions : dict | None,
         scoped : bool = True) -> dict:
    """Everything `player` may see; `actions` are theirs (None: not playing).

    scoped=True forgets details the table would have moved past, like a
    real game: older quests show only their result, and only the latest
    revealed quest and the current round keep their details (cards,
    Inquisition, votes). Declared roles are always kept."""
    v = full_view(s, player, actions)
    v["declarations"] = declarations(s)
    if not scoped:
        return v
    latest = max((i for i, q in enumerate(s.quests) if q.succeeded is not None),
                 default=None)
    current = len(s.quests) - 1 if s.quests and s.quests[-1].succeeded is None else None
    v["quests"] = [q if i in (latest, current)
                   else dict(round=q["round"], succeeded=q["succeeded"])
                   for i, q in enumerate(v["quests"])]
    v["latest_quest"] = v["quests"][latest] if latest is not None else None
    v["current_quest"] = v["quests"][current] if current is not None else None
    v["proposals"] = [p for p in v["proposals"] if p["round"] == s.round]
    if not (s.round == 1 or (latest is not None and s.quests[latest].round == 1)):
        v["first_round"] = None
    return v


def full_view(s : GameState, player : str | None, actions : dict | None) -> dict:
    first_round_done = s.phase not in (Phase.FIRST_ROUND_PROPOSING,
                                       Phase.FIRST_ROUND_VOTING)
    v = dict(
        phase = s.phase.value,
        round = s.round,
        seating = list(s.seating),
        direction = s.direction,
        leader = s.leader if s.round >= 2 else None,
        proposal_number = s.proposal_number,
        proposals_per_round = s.proposals_per_round,
        hammer = s.phase == Phase.PROPOSING and s.is_hammer(),
        team_sizes = list(s.team_sizes),
        double_fail_quest = s.double_fail_quest,
        successes = s.successes,
        failures = s.failures,
        first_round = dict(
            proposers = list(s.first_proposers),
            round2_starter = s.round2_starter,
            teams = dict(s.first_round_teams),
            voted = sorted(s.first_round_votes),
            votes = dict(s.first_round_votes) if first_round_done else None,
        ),
        proposals = [proposal_view(p) for p in s.proposals],
        quests = [quest_view(q) for q in s.quests],
        ready = sorted(s.ready) if s.phase in PAUSES else [],
        waiting_for = waiting_for(s),
        gawain_exiled = s.gawain_exiled,
        proclaimed = s.player_with_role("Arthur") if s.proclaimed else None,
        assassination = s.assassination,
        outcome = s.outcome,
        lady = None if s.lady_holder is None else dict(
            holder = s.lady_holder,
            uses = [dict(round=u["round"], holder=u["holder"], target=u["target"])
                    for u in s.lady_uses],
        ),
    )
    if player in s.roles:
        q = s.current_quest
        v["you"] = dict(
            name = player,
            role = s.role(player),
            card = q.cards[player].value if q and player in q.cards else None,
            # What the Lady of the Lake showed this player, and only them.
            lady_seen = [dict(round=u["round"], player=u["target"], team=u["team"])
                         for u in s.lady_uses if u["holder"] == player],
            # Gareth's own team, once Evil have revealed themselves.
            team = (s.allegiance(player) if s.role(player) == "Gareth"
                    and s.gareth_knows_team() else None),
        )
        v["actions"] = actions
    return v


def proposal_view(p : Proposal) -> dict:
    """Votes are shown once the vote is over (Hammer and Sorceress have none)."""
    complete = p.approved is not None and not p.hammer and p.sorceress_next is None
    return dict(round=p.round, number=p.number, leader=p.leader, team=list(p.team),
                hammer=p.hammer, approved=p.approved,
                sorceress_next=p.sorceress_next,
                voted=sorted(p.votes),
                votes=dict(p.votes) if complete else None,
                approved_by=[v for v in p.votes if p.votes[v]] if complete else None,
                rejected_by=[v for v in p.votes if not p.votes[v]] if complete else None)


def quest_view(q : Quest) -> dict:
    """Who has chosen a card, not what; the cards (shuffled) once revealed."""
    revealed = q.succeeded is not None
    return dict(round=q.round, leader=q.leader, team=list(q.team),
                fails_needed=q.fails_needed, inquisition=q.inquisition,
                chosen=sorted(q.cards),
                revealed={p: c.value for p, c in q.revealed.items()},
                removed=q.removed,
                gawain_target=q.gawain_target,
                played=[c.value for c in q.played] if revealed else None,
                qbwh_counts_as=q.qbwh_counts_as.value if q.qbwh_counts_as else None,
                succeeded=q.succeeded, betrayed=q.betrayed)


def waiting_for(s : GameState) -> list[str]:
    """Who the game is waiting on (public: names only)."""
    match s.phase:
        case Phase.FIRST_ROUND_PROPOSING:
            return [p for p in s.first_proposers if p not in s.first_round_teams]
        case Phase.FIRST_ROUND_VOTING:
            return [p for p in s.seating if p not in s.first_round_votes]
        case Phase.PROPOSING:
            return [s.leader]
        case Phase.VOTING:
            return [p for p in s.seating if p not in s.current_proposal.votes]
        case Phase.QUEST:
            return [p for p in s.current_quest.team if p not in s.current_quest.cards]
        case Phase.INQUISITION:
            return [s.current_quest.leader]
        case Phase.TEAM_ANNOUNCED | Phase.REVEAL | Phase.RESULT:
            return [p for p in s.seating if p not in s.ready]
        case Phase.LADY:
            return [s.lady_holder]
        case Phase.ASSASSINATION:
            return [s.assassin()]
        case Phase.PELLINORE_GUESS:
            return [s.player_with_role("Pellinore")]
    return []
