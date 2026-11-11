"""The Assassination: who makes the call, what may be named, and whether
the guess is right."""
from __future__ import annotations

from thavalon.ruleset import ASSASSINATION_TARGETS

# Who makes the final Assassination decision, highest first.
# Gareth isn't ranked: an Evil Gareth joins the discussion, but their Knight
# is an Evil player ranked above them anyway.
ASSASSIN_RANKING = ["Mordred", "Morgana", "Maelegant", "Agravaine",
                    "Colgrevance", "Minion of Mordred", "Oberon"]


def targets_needed(kind : str) -> int:
    """How many players the assassin names for this kind of guess."""
    return 0 if kind == "none" else len(ASSASSINATION_TARGETS.get(kind, ((),))[0])


def guess_is_correct(kind : str, named_roles : list[str], kinds : list[str],
                     role_present) -> bool:
    """`named_roles`: the roles of the players named. `kinds`: the choices
    this game allows. `role_present(role_name)`: whether someone has it.
    Naming no one is correct only if no allowed target is (wholly) present."""
    if kind == "none":
        return not any(all(role_present(r) for r in ASSASSINATION_TARGETS[k][0])
                       for k in kinds if k != "none")
    return sorted(named_roles) == sorted(ASSASSINATION_TARGETS[kind][0])


def assassination_help(kinds : list[str], link : bool = False) -> str:
    """'Name one player as Merlin or Nilrem, two as the Lovers, or no one.'
    link: with [[Term]] markup (see rule_notes)."""
    def label(k):
        roles, text = ASSASSINATION_TARGETS[k]
        if not link:
            return text
        return f"[[{roles[0]}]]" if len(roles) == 1 else f"[[the Lovers|{text}]]"
    ones = [label(k) for k in kinds
            if k != "none" and len(ASSASSINATION_TARGETS[k][0]) == 1]
    twos = [label(k) for k in kinds
            if k != "none" and len(ASSASSINATION_TARGETS[k][0]) == 2]

    def either(names):
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]
    parts = []
    if ones:
        parts.append("one player as " + either(ones))
    if twos:
        parts.append("two as " + either(twos))
    if "none" in kinds:
        parts.append("no one")
    if not parts:
        return "There is no Assassination."
    text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + ", or " + parts[-1]
    if len(parts) == 2:
        text = f"{parts[0]}{',' if ' or ' in parts[0] else ''} or {parts[1]}"
    return "Name " + text + "."
