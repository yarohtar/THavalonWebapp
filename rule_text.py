"""Sentences for the role rules templates (templates/rules/<role>.html).

Those templates describe a role under a given RuleSet: the rules pages
render them with the default rules (and list the current game's changes
above them), the Role tab renders them with the game's rules, marking the
lines that differ from the defaults. With the default rules the text is
exactly the usual rules text.

Functions here return text with [[Term]] markup already expanded (Markup).
"""
from __future__ import annotations

from markupsafe import Markup

from rule_notes import _and, expand, format_counts
from thavalon.assassination import assassination_help
from thavalon.ruleset import ASSASSINATION_TARGETS, COUNTS, DEFAULT, RuleSet, SETTINGS


def counts_phrase(counts) -> str:
    """'in games with 7 or more players', 'in games of any size', ...;
    '' for no counts."""
    counts = sorted(counts)
    if not counts:
        return ""
    if counts == list(COUNTS):
        return "in games of any size"
    if counts == list(range(counts[0], COUNTS[-1] + 1)) and counts[0] < COUNTS[-1]:
        return f"in games with {counts[0]} or more players"
    return f"in games with {format_counts(counts)} players"


def changed(rules : RuleSet, *keys : str) -> bool:
    """Whether any of these settings differs from the default."""
    return any(rules.changed(k) for k in keys)


def roles_list(roles, word : str = "and") -> Markup:
    """['Merlin', 'Morgana'] -> '[[Merlin]] and [[Morgana]]' as links."""
    return expand(_and([f"[[{r}]]" for r in roles], word))


def is_target(rules : RuleSet, kind : str) -> bool:
    return kind in rules.assassination_targets()


def target_changed(rules : RuleSet, kind : str) -> bool:
    """Whether being an Assassination target differs from the defaults
    (switching the Assassination off counts only for default targets)."""
    default = SETTINGS[f"assassination.target.{kind}"].default
    return is_target(rules, kind) != default


def assassination_choices(rules : RuleSet) -> Markup:
    """'Evil must name one player as Merlin, ... or no one.'"""
    text = assassination_help(rules.assassination_kinds(), link=True)
    return expand(f"Evil must {text[0].lower()}{text[1:]}")


def merlin_evil_sight(rules : RuleSet) -> Markup:
    """Merlin's main line: which Evil roles Merlin sees."""
    evil = ["Mordred", "Morgana", "Maelegant", "Agravaine", "Colgrevance", "Oberon",
            "Minion of Mordred"]
    hidden = [r for r in evil if not rules.merlin_sees(r)]
    seen = [r for r in evil if rules.merlin_sees(r)]
    link = lambda r: ("the [[Minion of Mordred|Minions of Mordred]]"
                      if r == "Minion of Mordred" else f"[[{r}]]")
    if not hidden:
        return expand("Sees every Evil player.")
    if not seen:
        return expand("Doesn't see any Evil players.")
    if len(hidden) <= len(seen):
        return expand(f"Sees every Evil player except {_and([link(r) for r in hidden])}.")
    return expand(f"Sees only {_and([link(r) for r in seen])} as Evil.")


def gareth_sight(rules : RuleSet, viewer : str) -> Markup:
    """How Merlin ('merlin') or the Evil players ('evil') see Gareth, as a
    sentence (or two, if it depends on Gareth's team)."""
    if viewer == "merlin":
        subject, sees, not_seen, is_ = "[[Merlin]]", "sees Gareth as Evil", "doesn't", "is"
    else:
        subject, sees, not_seen, is_ = ("the other Evil players", "see Gareth as one of them",
                                        "don't", "are")

    def phrase(team):
        see = rules.gareth(team, f"{viewer}_sees")
        told = rules.gareth(team, f"{viewer}_knows_role")
        if see and told:
            return f"{sees} and {is_} told which player is Gareth"
        if see:
            return f"{sees}, without being told which player is Gareth"
        if told:
            return f"{is_} told which player is Gareth, but {not_seen} see Gareth"
        return f"{not_seen} see Gareth"
    good, evil = phrase("Good"), phrase("Evil")
    if good == evil:
        tail = "" if good.startswith(not_seen) else ", whatever Gareth's team"
        text = f"{subject} {good}{tail}."
        return expand(text[0].upper() + text[1:])
    return expand(f"When [[Gareth]] is Good, {subject} {good}. "
                  f"When Gareth is Evil, {subject} {evil}.")


def init_app(app):
    app.jinja_env.globals.update(
        default_rules=DEFAULT,
        counts_phrase=counts_phrase,
        rules_changed=changed,
        roles_list=roles_list,
        is_target=is_target,
        target_changed=target_changed,
        merlin_evil_sight=merlin_evil_sight,
        assassination_choices=assassination_choices,
        gareth_sight=gareth_sight,
        assassination_targets=ASSASSINATION_TARGETS,
    )
