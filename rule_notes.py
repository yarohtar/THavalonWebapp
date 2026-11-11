"""Plain-language notes on how a game's rules differ from the defaults.

game_notes(rules) gives one Note per change (or group of related changes),
each tagged with the rules pages it belongs on. The rules pages show the
notes for their page to players in a game ("In your current game: ..."),
the Role tab shows them under the role's rules, and the game summary lists
the ones marked `summary`. With the default rules there are no notes.

Notes use the same [[Term]] markup as the templates; expand() turns them
into links.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from markupsafe import Markup, escape

from ruleset import (ASSASSINATION_TARGETS, DEFAULT, GARETH_TEAMS, GUINEVERE_SEES,
                     MERLIN_SEES, PERCIVAL_SEES, SETTINGS, TRANSFORMS, RuleSet,
                     format_counts)


@dataclass
class Note:
    pages : tuple[str, ...]          # rules page slugs
    text : str                       # with [[Term]] markup
    summary : bool = True            # also listed in the in-game summary


# Rules page of each role name used in settings.
PAGE = {"Merlin": "merlin", "Percival": "percival", "Tristan": "lovers", "Iseult": "lovers",
        "Arthur": "arthur", "Lancelot": "lancelot", "Guinevere": "guinevere",
        "Gawain": "gawain", "Balin the Savage": "balin", "Mordred": "mordred",
        "Morgana": "morgana", "Maelegant": "maelegant", "Agravaine": "agravaine",
        "Colgrevance": "colgrevance", "Oberon": "oberon",
        "Minion of Mordred": "minion-of-mordred", "Gareth": "gareth",
        "Pellinore": "pellinore", "Nilrem": "nilrem", "Galahad": "galahad",
        "Uther": "uther", "Ygraine": "ygraine"}
TARGET_PAGE = {"merlin": "merlin", "nilrem": "nilrem", "lovers": "lovers",
               "percival": "percival", "galahad": "galahad", "arthur": "arthur",
               "guinevere": "guinevere", "ygraine": "ygraine", "uther": "uther",
               "lancelot": "lancelot", "gawain": "gawain"}


def _and(items : list[str], word : str = "and") -> str:
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" {word} " + items[-1]


def _links(roles) -> list[str]:
    return [f"[[{r}]]" for r in roles]


def _changed(rules : RuleSet, prefix : str) -> list[str]:
    return [k for k in rules.values if k.startswith(prefix)]


def game_notes(rules : RuleSet | None) -> list[Note]:
    if rules is None or rules.is_default:
        return []
    notes : list[Note] = []
    add = notes.append

    # ---- Assassination
    if _changed(rules, "assassination."):
        kinds = rules.assassination_kinds()
        targets = rules.assassination_targets()
        every_target_page = tuple(TARGET_PAGE.values())
        if not kinds:
            add(Note(("assassination", "overview", "mordred", "gareth") + every_target_page,
                     "There is no [[Assassination]]: Good wins as soon as 3 Quests succeed."))
        else:
            choices = []
            for k in targets:
                roles, label = ASSASSINATION_TARGETS[k]
                choices.append(f"{'two players' if len(roles) == 2 else 'one player'} "
                               f"as [[{roles[0] if len(roles) == 1 else 'the Lovers'}|{label}]]")
            if "none" in kinds:
                choices.append("no one")
            add(Note(("assassination", "overview"),
                     f"In the [[Assassination]], Evil's choices are: {_and(choices, 'or')}."))
            if not rules["assassination.none"]:
                add(Note(("assassination",), "Evil may not name no one: they must name "
                         "someone, even if no target is in the game."))
            elif targets != [k for k in ASSASSINATION_TARGETS
                             if SETTINGS[f'assassination.target.{k}'].default]:
                names = [ASSASSINATION_TARGETS[k][1] for k in targets]
                add(Note(("assassination",), "Naming no one is correct only if the game has "
                         f"none of these: {_and(names, 'or')} (the Lovers count only as a "
                         "complete pair)." if "lovers" in targets else
                         "Naming no one is correct only if the game has "
                         f"none of these: {_and(names, 'or')}.", summary=False))
            for k, (roles, label) in ASSASSINATION_TARGETS.items():
                key = f"assassination.target.{k}"
                if not rules.changed(key):
                    continue
                if rules[key]:
                    how = ("Evil must name both of them" if len(roles) == 2
                           else f"Evil must name them as {label}")
                    add(Note((TARGET_PAGE[k],), f"{label[0].upper() + label[1:]} "
                             f"{'are' if len(roles) == 2 else 'is'} a target of the "
                             f"[[Assassination]]. {how}.", summary=False))
                else:
                    add(Note((TARGET_PAGE[k],), f"{label[0].upper() + label[1:]} "
                             f"{'are' if len(roles) == 2 else 'is'} not a target of the "
                             "[[Assassination]].", summary=False))

    # ---- Player counts
    for key in _changed(rules, ""):
        if not key.endswith(".players"):
            continue
        role = key[:-len(".players")]
        counts = rules[key]
        if role == "Pellinore":
            who, pages = "[[Pellinore]] and [[The Questing Beast]]", ("pellinore", "questing-beast")
            verb = "are"
        else:
            who, pages, verb = f"[[{role}]]", (PAGE[role],), "is"
        if counts:
            add(Note(pages, f"{who} can be dealt only in {format_counts(counts)}-player games."
                     if len(counts) < 6 else f"{who} can be dealt in games of any size."))
        else:
            add(Note(pages, f"{who} {verb} never dealt."))

    # ---- Lonely roles
    lonely_rule = {
        "Merlin": ("[[Merlin]]", "[[Nilrem]]", "when [[Percival]] is missing",
                   ("merlin", "nilrem", "transformations")),
        "Percival": ("[[Percival]]", "[[Galahad]]", None,
                     ("percival", "galahad", "transformations")),
        "Lovers": ("A lone [[Tristan]] or [[Iseult]]", "[[Uther]]", "",
                   ("lovers", "uther", "transformations")),
        "Guinevere": ("[[Guinevere]]", "[[Ygraine]]", None,
                      ("guinevere", "ygraine", "transformations")),
    }
    for key, (who, becomes, when, pages) in lonely_rule.items():
        if not rules.changed(f"{key}.lonely"):
            continue
        counts = rules[f"{key}.lonely"]
        if when is None:
            seen = (rules.percival_sees() if key == "Percival" else rules.guinevere_sees())
            when = (f"when {_and(_links(seen), 'and')} {'are' if len(seen) > 1 else 'is'} missing"
                    if seen else "")
        when = f" {when}" if when else ""
        if not counts:
            add(Note(pages, f"{who} never becomes {becomes}: lonely roles stay as they are."))
        elif len(counts) == 6:
            add(Note(pages, f"{who} becomes {becomes}{when} in games of any size."))
        else:
            add(Note(pages, f"{who} becomes {becomes}{when} only in "
                     f"{format_counts(counts)}-player games."))

    # ---- Merlin's sight
    merlin_changed = [r for r in MERLIN_SEES if rules.changed(f"Merlin.sees.{r}")]
    if merlin_changed:
        seen = [r for r in MERLIN_SEES if rules.merlin_sees(r)]
        hidden = [r for r in MERLIN_SEES if not rules.merlin_sees(r)]
        text = (f"[[Merlin]] sees these roles as Evil: {_and(_links(seen))}."
                if seen else "[[Merlin]] doesn't see anyone as Evil.")
        if seen and hidden:
            text += f" Merlin doesn't see {_and(_links(hidden), 'or')}."
        add(Note(("merlin",), text))
        for r in merlin_changed:
            if rules.merlin_sees(r):
                add(Note((PAGE[r],), f"[[Merlin]] sees [[{r}]] as Evil.", summary=False))
            else:
                add(Note((PAGE[r],), f"[[Merlin]] doesn't see [[{r}]].", summary=False))

    # ---- Percival's and Guinevere's sight
    for viewer, options, getter in (("Percival", PERCIVAL_SEES, rules.percival_sees),
                                    ("Guinevere", GUINEVERE_SEES, rules.guinevere_sees)):
        changed = [r for r in options if rules.changed(f"{viewer}.sees.{r}")]
        if not changed:
            continue
        seen = getter()
        becomes = "Galahad" if viewer == "Percival" else "Ygraine"
        pages = (PAGE[viewer], PAGE[becomes])
        if seen:
            sight = (f"sees only {_and(_links(seen))}, but not which is which"
                     if len(seen) > 1 else f"sees only [[{seen[0]}]], and knows it is {seen[0]}")
            missing = "none of them is" if len(seen) > 1 else f"{seen[0]} is not"
            add(Note(pages, f"[[{viewer}]] {sight}. {viewer} counts as lonely (and becomes "
                     f"[[{becomes}]] where lonely roles change) when {missing} in the game."))
        else:
            add(Note(pages, f"[[{viewer}]] sees no one, so is always lonely: "
                     f"[[{becomes}]] instead, wherever lonely roles change."))
        for r in changed:
            add(Note((PAGE[r],), f"[[{viewer}]] {'sees' if r in seen else 'does not see'} "
                     f"[[{r}]].", summary=False))

    # ---- Nilrem
    if not rules["Nilrem.known"]:
        add(Note(("nilrem", "overview"), "Good players are not told who [[Nilrem]] is, "
                 "or whether Nilrem is in the game."))

    # ---- Oberon
    if rules.changed("Oberon.seen_by_evil"):
        add(Note(("oberon", "overview"), "The other Evil players see [[Oberon]] among them, "
                 "without being told which player is Oberon."))
    if rules.changed("Oberon.sees_evil"):
        add(Note(("oberon", "overview"), "[[Oberon]] doesn't see the other Evil players."))
    if rules.changed("Oberon.announced") and not rules["Oberon.seen_by_evil"]:
        add(Note(("oberon", "overview"),
                 "Evil players are not told whether an [[Oberon]] is in the game."))

    # ---- Cards and abilities
    if not rules["Agravaine.must_fail"]:
        add(Note(("agravaine", "quests"), "[[Agravaine]] doesn't have to play [[Fail]]: "
                 "Agravaine may play [[Success]] or Fail like everyone else."))
    reversal = rules.reversal_roles()
    for r in ("Lancelot", "Maelegant"):
        if rules.changed(f"{r}.reversal"):
            add(Note((PAGE[r],), f"[[{r}]] can't play [[Reversal]].", summary=False))
    if reversal != ["Lancelot", "Maelegant"]:
        text = (f"Only [[{reversal[0]}]] can play [[Reversal]]." if reversal
                else "Nobody can play [[Reversal]].")
        add(Note(("reversal", "quests"), text))
    if rules.changed("Arthur.proclaim_after"):
        n = rules["Arthur.proclaim_after"]
        add(Note(("arthur",), f"[[Arthur]] may use [[Proclamation]] once "
                 f"{'one Quest has' if n == 1 else f'{n} Quests have'} failed."))

    # ---- Gareth
    if rules.changed("Gareth.knows"):
        knows = rules["Gareth.knows"]
        add(Note(("gareth",), "[[Gareth]] is told only who their "
                 f"{'Knight' if knows == 'knight' else 'Rival'} is, not their "
                 f"{'Rival' if knows == 'knight' else 'Knight'}."))
    if rules.changed("Gareth.lady"):
        add(Note(("gareth", "lady-of-the-lake"),
                 "The [[Lady of the Lake]] shows [[Gareth]]'s real team."))
    for team in GARETH_TEAMS:
        keys = [f"Gareth.{team}.{w}" for w in
                ("merlin_sees", "merlin_knows_role", "evil_sees", "evil_knows_role")]
        if not any(rules.changed(k) for k in keys):
            continue
        g = lambda what: rules.gareth(team, what)
        facts = [
            ("[[Merlin]] sees Gareth as Evil" if g("merlin_sees")
             else "[[Merlin]] doesn't see Gareth"),
            ("Merlin is told which player is Gareth" if g("merlin_knows_role") else None),
            ("the Evil players see Gareth as one of them" if g("evil_sees")
             else "the Evil players don't see Gareth"),
            ("the Evil players are told which player is Gareth" if g("evil_knows_role")
             else None),
        ]
        color = "Good (blue)" if team == "Good" else "Evil (red)"
        add(Note(("gareth",), f"When [[Gareth]] is {color}: "
                 f"{_and([f for f in facts if f])}."))
        if any(rules.changed(k) for k in keys[:2]):
            add(Note(("merlin",), f"When [[Gareth]] is {color}, "
                     f"{_and([f for f in facts[:2] if f])}.", summary=False))
    return notes


def notes_for(rules : RuleSet | None, page : str) -> list[Note]:
    return [n for n in game_notes(rules) if page in n.pages]


def summary_notes(rules : RuleSet | None) -> list[Note]:
    seen, out = set(), []
    for n in game_notes(rules):
        if n.summary and n.text not in seen:
            seen.add(n.text)
            out.append(n)
    return out


_MARKUP = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")


def expand(text : str) -> Markup:
    """[[Term]] markup -> links; everything else escaped."""
    from rules import term_link
    out, pos = [], 0
    for m in _MARKUP.finditer(text):
        out.append(escape(text[pos:m.start()]))
        out.append(term_link(m.group(1).strip(),
                             m.group(2).strip() if m.group(2) else None))
        pos = m.end()
    out.append(escape(text[pos:]))
    return Markup("").join(out)
