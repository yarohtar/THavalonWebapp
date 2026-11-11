"""How the Neutral roles (Pellinore and the Questing Beast) score at the end."""
from __future__ import annotations


def neutral_scores(pellinore : str, beast : str, teams : list[list[str]],
                   successes : int, failures : int, qbwh_seen : int,
                   guessed : bool) -> dict:
    """`teams`: every quest's team. `guessed`: Pellinore named the Beast."""
    together = any(pellinore in team and beast in team for team in teams)
    sanity = -qbwh_seen + (1 if together else 0) + (2 if failures >= 3 else 0) \
        + (3 if guessed else 0)
    quests_on = sum(beast in team for team in teams)
    points = quests_on + (0 if together else 1) + (2 if successes >= 3 else 0) \
        + (0 if guessed else 3)
    return {
        "Pellinore": dict(player=pellinore, sanity=sanity, guessed_right=guessed,
                          won=qbwh_seen == 0 or sanity >= 2),
        "The Questing Beast": dict(player=beast, points=points,
                                   won=quests_on >= 1 and points >= 5),
    }
