"""Plain-language notes on how a game's rules differ from the defaults.

game_notes(rules) gives one Note per change (or group of related changes),
each tagged with the rules pages it belongs on. The rules pages show the
notes for their page to players in a game ("In your current game: ..."),
the tap-preview sheet shows them for the tapped term's page ("Changed in
this game"), and the game summary lists the ones marked `summary`. (The Role
tab instead renders the role's rules under the game's rules: role_text.py.)
With the default rules there are no notes.

Notes use the same [[Term]] markup as the templates; pages.expand() turns
them into links.
"""
from __future__ import annotations

from dataclasses import dataclass

from markupsafe import Markup

from thavalon.assassination import assassination_help
from thavalon.ruleset import (ASSASSINATION_TARGETS, GARETH_TEAMS, GUINEVERE_SEES,
                              MERLIN_SEES, PERCIVAL_SEES, SETTINGS, RuleSet)
from web.rules.pages import expand, get_term, script_json
from web.rules.wording import and_list, format_counts, links, role_link


@dataclass
class Note:
    pages : tuple[str, ...]          # rules page slugs
    text : str                       # with [[Term]] markup
    summary : bool = True            # also listed in the in-game summary


def page_of(role_name : str) -> str:
    """The rules page a role is described on."""
    return get_term(role_name).page_slug


def target_page(kind : str) -> str:
    """The rules page of an Assassination target ('lovers' -> the Lovers' page)."""
    return page_of(ASSASSINATION_TARGETS[kind][0][0])


def game_notes(rules : RuleSet | None) -> list[Note]:
    if rules is None or rules.is_default:
        return []
    notes : list[Note] = []
    add = notes.append

    # ---- Assassination
    if rules.changes("assassination."):
        kinds = rules.assassination_kinds()
        targets = rules.assassination_targets()
        every_target_page = tuple(target_page(k) for k in ASSASSINATION_TARGETS)
        if not kinds:
            add(Note(("assassination", "overview", "mordred", "gareth") + every_target_page,
                     "There is no [[Assassination]]: Good wins as soon as 3 Quests succeed."))
            add(Note(("gareth",), "[[Gareth]] learns their team when the game ends.",
                     summary=False))
        else:
            help_text = assassination_help(kinds, link=True)
            add(Note(("assassination", "overview"),
                     f"In the [[Assassination]], Evil must {help_text[0].lower()}{help_text[1:]}"))
            if not rules["assassination.none"]:
                add(Note(("assassination",), "Evil may not name no one: they must name "
                         "someone, even if no target is in the game."))
            elif targets != [k for k in ASSASSINATION_TARGETS
                             if SETTINGS[f'assassination.target.{k}'].default]:
                names = [ASSASSINATION_TARGETS[k][1] for k in targets]
                add(Note(("assassination",), "Naming no one is correct only if the game has "
                         f"none of these: {and_list(names, 'or')} (the Lovers count only as a "
                         "complete pair)." if "lovers" in targets else
                         "Naming no one is correct only if the game has "
                         f"none of these: {and_list(names, 'or')}.", summary=False))
            for k, (roles, label) in ASSASSINATION_TARGETS.items():
                key = f"assassination.target.{k}"
                if not rules.changed(key):
                    continue
                if rules[key]:
                    how = ("Evil must name both of them" if len(roles) == 2
                           else f"Evil must name them as {label}")
                    add(Note((target_page(k),), f"{label[0].upper() + label[1:]} "
                             f"{'are' if len(roles) == 2 else 'is'} a target of the "
                             f"[[Assassination]]. {how}.", summary=False))
                else:
                    add(Note((target_page(k),), f"{label[0].upper() + label[1:]} "
                             f"{'are' if len(roles) == 2 else 'is'} not a target of the "
                             "[[Assassination]].", summary=False))

    # ---- Player counts
    for key in rules.changes():
        if not key.endswith(".players"):
            continue
        role = key[:-len(".players")]
        counts = rules[key]
        if role == "Pellinore":
            who, pages = ("[[Pellinore]] and [[The Questing Beast|the Questing Beast]]",
                          ("pellinore", "questing-beast"))
            verb = "are"
        else:
            who, pages, verb = f"[[{role}]]", (page_of(role),), "is"
        if counts:
            add(Note(pages, f"{who} can be dealt only in games with {format_counts(counts)} players."
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
            when = (f"when {and_list(links(seen), 'and')} {'are' if len(seen) > 1 else 'is'} missing"
                    if seen else "")
        when = f" {when}" if when else ""
        if not counts:
            add(Note(pages, f"{who} never becomes {becomes}: lonely roles stay as they are."))
        elif len(counts) == 6:
            add(Note(pages, f"{who} becomes {becomes}{when} in games of any size."))
        else:
            add(Note(pages, f"{who} becomes {becomes}{when} only in games with "
                     f"{format_counts(counts)} players."))

    # ---- Merlin's sight
    merlin_changed = [r for r in MERLIN_SEES if rules.changed(f"Merlin.sees.{r}")]
    if merlin_changed:
        listed = list(MERLIN_SEES)
        seen = [role_link(r) for r in listed if rules.merlin_sees(r)]
        hidden = [role_link(r) for r in listed if not rules.merlin_sees(r)]
        text = (f"[[Merlin]] sees these roles as Evil: {and_list(seen)}."
                if seen else "[[Merlin]] doesn't see anyone as Evil.")
        if seen and hidden:
            text += f" Merlin doesn't see {and_list(hidden, 'or')}."
        add(Note(("merlin",), text))
        for r in merlin_changed:
            if rules.merlin_sees(r):
                add(Note((page_of(r),), f"[[Merlin]] sees {role_link(r)} as Evil.",
                         summary=False))
            else:
                add(Note((page_of(r),), f"[[Merlin]] doesn't see {role_link(r)}.",
                         summary=False))

    # ---- Percival's and Guinevere's sight
    for viewer, options, getter in (("Percival", PERCIVAL_SEES, rules.percival_sees),
                                    ("Guinevere", GUINEVERE_SEES, rules.guinevere_sees)):
        changed = [r for r in options if rules.changed(f"{viewer}.sees.{r}")]
        if not changed:
            continue
        seen = getter()
        becomes = "Galahad" if viewer == "Percival" else "Ygraine"
        pages = (page_of(viewer), page_of(becomes))
        if seen:
            sight = (f"sees only {and_list(links(seen))}, but not which is which"
                     if len(seen) > 1 else
                     f"sees only [[{seen[0]}]], and knows that player is {seen[0]}")
            missing = "none of them is" if len(seen) > 1 else f"{seen[0]} is not"
            add(Note(pages, f"[[{viewer}]] {sight}. {viewer} counts as lonely (and becomes "
                     f"[[{becomes}]] where lonely roles change) when {missing} in the game."))
        else:
            add(Note(pages, f"[[{viewer}]] sees no one, so is always lonely: "
                     f"[[{becomes}]] instead, wherever lonely roles change."))
        for r in changed:
            add(Note((page_of(r),), f"[[{viewer}]] {'sees' if r in seen else 'does not see'} "
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
            add(Note((page_of(r),), f"[[{r}]] can't play [[Reversal]].", summary=False))
    if reversal != ["Lancelot", "Maelegant"]:
        text = (f"Only [[{reversal[0]}]] can play [[Reversal]]." if reversal
                else "Nobody can play [[Reversal]].")
        add(Note(("reversal", "quests"), text))
    if rules.changed("Arthur.proclaim_after"):
        n = rules["Arthur.proclaim_after"]
        add(Note(("arthur",), f"[[Arthur]] may use [[Proclamation]] once "
                 f"{'one Quest has' if n == 1 else f'{n} Quests have'} failed."))

    # ---- Balin
    if not rules["Balin.must_fail"]:
        add(Note(("balin",), "[[Balin the Savage|Balin]] doesn't have to play a [[Fail]]: "
                 "Balin wins whenever Good wins."))
    if not rules["Balin.evil_sees"]:
        add(Note(("balin", "overview"), "Evil players don't see [[Balin the Savage|Balin]]."))
    if not rules["Balin.agravaine_knows"]:
        add(Note(("balin", "agravaine"), "[[Agravaine]] isn't told who "
                 "[[Balin the Savage|Balin]] is"
                 + (", and sees Balin among the Evil players like everyone else."
                    if rules["Balin.evil_sees"] else ".")))
    if not rules["Balin.or_gareth"]:
        add(Note(("balin", "gareth"), "[[Balin the Savage|Balin]] and [[Gareth]] can both be "
                 "in the game: Gareth takes an Evil player's place, Balin a Good player's."))
    if not rules["Arthur.sees_balin"]:
        add(Note(("arthur", "balin"), "[[Arthur]] isn't told whether "
                 "[[Balin the Savage|Balin]] is in the game."))
    if rules["Arthur.sees_gareth"]:
        add(Note(("arthur", "gareth"), "[[Arthur]]'s list of Good roles includes "
                 "[[Gareth]] when Gareth is Good."))
    if rules["Galahad.sees_gareth"]:
        add(Note(("galahad", "gareth"), "[[Galahad]]'s list of Evil roles includes "
                 "[[Gareth]] when Gareth is Evil."))

    # ---- Gareth
    if rules.changed("Gareth.knows"):
        knows = rules["Gareth.knows"]
        add(Note(("gareth",), "[[Gareth]] is told only who their "
                 f"{'Knight' if knows == 'knight' else 'Rival'} is, not their "
                 f"{'Rival' if knows == 'knight' else 'Knight'}."))
    if rules.changed("Gareth.arthur_knight"):
        add(Note(("gareth", "arthur"), "[[Arthur]] can be chosen as [[Gareth]]'s Knight."))
    if rules.changed("Gareth.lady"):
        add(Note(("gareth", "lady-of-the-lake"),
                 "The [[Lady of the Lake]] shows [[Gareth]]'s real team."))
    for team in GARETH_TEAMS:
        keys = [f"Gareth.{team}.{w}" for w in
                ("merlin_sees", "merlin_knows_role", "evil_sees", "evil_knows_role")]
        if not any(rules.changed(k) for k in keys):
            continue
        g = lambda what: rules.gareth(team, what)
        merlin = _sight("[[Merlin]]", "sees Gareth as Evil", "doesn't see Gareth",
                        g("merlin_sees"), g("merlin_knows_role"), plural=False)
        evil = _sight("the Evil players", "see Gareth as one of them", "don't see Gareth",
                      g("evil_sees"), g("evil_knows_role"), plural=True)
        color = "Good (blue)" if team == "Good" else "Evil (red)"
        evil_pages = (("overview",) if any(rules.changed(k) for k in keys[2:]) else ())
        add(Note(("gareth",) + evil_pages, f"When [[Gareth]] is {color}: {merlin}; {evil}."))
        if any(rules.changed(k) for k in keys[:2]):
            add(Note(("merlin",), f"When [[Gareth]] is {color}, {merlin}.", summary=False))
    return notes


def _sight(who, sees, not_seen, see : bool, told : bool, plural : bool) -> str:
    """'Merlin sees Gareth as Evil, without being told which player is Gareth', etc."""
    are = "are" if plural else "is"
    if see and told:
        return f"{who} {sees} and {are} told which player is Gareth"
    if see:
        return f"{who} {sees}, without being told which player is Gareth"
    if told:
        return (f"{who} {are} told which player is Gareth, but "
                f"{'don' if plural else 'doesn'}'t see Gareth "
                f"{'as one of them' if plural else 'as Evil'}")
    return f"{who} {not_seen}"


def notes_for(rules : RuleSet | None, page : str) -> list[Note]:
    return [n for n in game_notes(rules) if page in n.pages]


def summary_notes(rules : RuleSet | None) -> list[Note]:
    seen, out = set(), []
    for n in game_notes(rules):
        if n.summary and n.text not in seen:
            seen.add(n.text)
            out.append(n)
    return out


def game_notes_json(ruleset) -> Markup:
    """{page slug: [note HTML, ...]} of a game's rule changes, for the
    tap-preview sheet. {} with the default rules."""
    data : dict[str, list[str]] = {}
    for note in game_notes(ruleset):
        html = str(expand(note.text))
        for page in note.pages:
            if html not in data.setdefault(page, []):
                data[page].append(html)
    return script_json(data)


def init_app(app):
    app.jinja_env.globals.update(
        rule_notes_for = notes_for,
        rule_summary_notes = summary_notes,
        expand_note = expand,
        game_notes_json = game_notes_json)
