"""Quest cards and how a quest's result follows from the cards played."""
from __future__ import annotations

from enum import Enum


class Card(str, Enum):
    SUCCESS = "Success"
    FAIL = "Fail"
    REVERSAL = "Reversal"
    QBWH = "Questing Beast Was Here"


def qbwh_value(failed_quests : int, qbwh_seen : int) -> Card:
    """What a Questing Beast Was Here card counts as: a Fail, until two
    quests have failed or two such cards have been revealed."""
    if failed_quests >= 2 or qbwh_seen >= 2:
        return Card.SUCCESS
    return Card.FAIL


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
