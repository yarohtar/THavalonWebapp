"""Small phrasing helpers shared by the rules texts (notes.py, role_text.py).
Text uses the [[Term]] link markup (see pages.py)."""
from __future__ import annotations


def and_list(items, word : str = "and") -> str:
    """['a', 'b', 'c'] -> 'a, b and c'."""
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" {word} " + items[-1]


def links(roles) -> list[str]:
    return [f"[[{r}]]" for r in roles]


def role_link(name : str) -> str:
    """A role as a link, plural for the Minions."""
    if name == "Minion of Mordred":
        return "the [[Minion of Mordred|Minions of Mordred]]"
    return f"[[{name}]]"


def format_counts(counts) -> str:
    """{7, 8, 9, 10} -> '7–10', {6, 9} -> '6 or 9', {} -> 'no'."""
    counts = sorted(counts)
    if not counts:
        return "no"
    parts, start = [], counts[0]
    for i, n in enumerate(counts):
        if i + 1 < len(counts) and counts[i + 1] == n + 1:
            continue
        if n - start >= 2:
            parts.append(f"{start}–{n}")
        else:
            parts.extend(str(k) for k in range(start, n + 1))
        if i + 1 < len(counts):
            start = counts[i + 1]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " or " + parts[-1]
