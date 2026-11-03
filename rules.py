"""Registry of rule terms and the [[term]] link markup used in templates.

Every rule concept (role, ability, mechanic, card) is a Term. Rule text lives in
templates/rules/<page>.html. Anywhere in a template you can write

    [[Merlin]]                  -> link labelled "Merlin"
    [[Reversal|Reversal cards]] -> link to Reversal labelled "Reversal cards"

and it is expanded at template load time into a link (so player names and other
runtime data are never rewritten). Unknown terms raise an error when rendered,
which catches typos.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from flask import url_for
from jinja2.ext import Extension
from markupsafe import Markup

from THavalon import string_to_role


@dataclass
class Term:
    slug: str            # unique id
    title: str
    summary: str         # one line, shown in the tap-preview sheet
    kind: str = "rule"   # role | ability | rule | card
    team: str | None = None  # good | evil | neutral
    page: str | None = None  # page slug; defaults to own slug
    anchor: str | None = None
    aliases: tuple[str, ...] = ()
    players: str | None = None  # availability note, roles only
    retired: bool = False       # not currently played

    @property
    def page_slug(self) -> str:
        return self.page or self.slug

    def url(self) -> str:
        u = url_for("rules_page", slug=self.page_slug)
        return f"{u}#{self.anchor}" if self.anchor else u


def _players(role_name: str) -> str:
    """Availability derived from the engine's can_appear()."""
    role = string_to_role[role_name]
    counts = [n for n in range(5, 11) if role.can_appear(n)]
    if counts == list(range(5, 11)):
        return "5–10 players"
    if counts == list(range(counts[0], 11)):
        return f"{counts[0]}+ players" if counts[0] < 10 else "10 players"
    return " or ".join(map(str, counts)) + " players"


def role(slug, title, team, summary, players=None, **kw) -> Term:
    if players is None and title in string_to_role:
        players = _players(title)
    return Term(slug, title, summary, "role", team, players=players, **kw)


TERMS: list[Term] = [
    # ---- game flow ----
    Term("overview", "Overview", "Teams, how to win, and how a round works.",
         aliases=("Rules",)),
    Term("first-round", "First Round",
         "Two players propose teams at once; everyone votes between them.",
         aliases=("First Quest", "first mission")),
    Term("proposals", "Proposals",
         "Each round has one more proposal than there are Evil players.",
         aliases=("Proposal", "Leader", "proposal order")),
    Term("hammer", "Hammer",
         "The last proposal of a round is not voted on: it is automatically approved.",
         page="proposals", anchor="hammer", aliases=("Force",)),
    Term("inquisition", "Inquisition",
         "From round 2, approving an early proposal lets the Leader peek at Quest cards.",
         aliases=("Inquisitions",)),
    Term("weak-inquisition", "Weak Inquisition",
         "The Leader reveals one Quest card of their choice (it still counts).",
         page="inquisition", anchor="weak"),
    Term("strong-inquisition", "Strong Inquisition",
         "The Leader either reveals one Quest card, or removes one without revealing it.",
         page="inquisition", anchor="strong"),
    Term("quests", "Quests",
         "Team sizes, which cards you may play, and when a Quest fails.",
         aliases=("Quest", "mission", "missions", "Quest card", "Quest cards")),
    Term("assassination", "Assassination",
         "If Good wins 3 Quests, Evil gets one shot at Merlin, Nilrem or the Lovers.",
         aliases=("Assassinate", "assassinated")),
    Term("transformations", "Lonely Roles",
         "In 7+ player games, some roles change if their partners are missing.",
         aliases=("Transformations", "lonely")),

    # ---- cards ----
    Term("success", "Success", "The normal Good Quest card.", "card",
         page="quests", anchor="cards"),
    Term("fail", "Fail", "Evil's Quest card. Enough of them fail the Quest.", "card",
         page="quests", anchor="cards", aliases=("Fails",)),
    Term("reversal", "Reversal",
         "Played by Lancelot or Maelegant: flips one other card, preferring one that changes the result.",
         "card", aliases=("Reversals", "Reverse")),
    Term("qbwh", "Questing Beast Was Here",
         "The Questing Beast's mandatory Quest card.", "card",
         page="questing-beast", anchor="card",
         aliases=("The Questing Beast Was Here",)),

    # ---- Good ----
    role("merlin", "Merlin", "good",
         "Sees Evil players (except Mordred), but also sees Lancelot as Evil. Assassination target."),
    role("percival", "Percival", "good",
         "Sees Merlin and Morgana, but not which is which."),
    role("galahad", "Galahad", "good",
         "Replaces a lone Percival. Knows which Evil roles are in the game.",
         players="7+ players"),
    role("nilrem", "Nilrem", "good",
         "Replaces Merlin when Percival is absent. Every Good player knows who Nilrem is."),
    role("tristan", "Tristan", "good",
         "One of the Lovers: knows Iseult. Assassination target as a pair.",
         page="lovers"),
    role("iseult", "Iseult", "good",
         "One of the Lovers: knows Tristan. Assassination target as a pair.",
         page="lovers"),
    role("lovers", "The Lovers", "good",
         "Tristan and Iseult know each other. Evil can assassinate them as a pair.",
         players="5–10 players", aliases=("Lovers",)),
    role("uther", "Uther", "good",
         "Replaces a lone Lover. Knows one other Good player.",
         players="7+ players"),
    role("arthur", "Arthur", "good",
         "Knows which Good roles are in the game. Can Proclaim after 2 failed Quests."),
    Term("proclamation", "Proclamation",
         "After 2 failed Quests, Arthur may publicly reveal themselves as Good.",
         "ability", "good", page="arthur", anchor="proclamation"),
    role("lancelot", "Lancelot", "good",
         "May play Reversal. Appears Evil to Merlin."),
    role("guinevere", "Guinevere", "good",
         "Sees Lancelot, Arthur and Maelegant, but not which is which."),
    role("ygraine", "Ygraine", "good",
         "Replaces a lone Guinevere. Knows one Evil player (never Mordred).",
         players="7+ players"),
    role("gawain", "Gawain", "good",
         "May declare and force a player on a Quest to reveal their card."),
    Term("gawain-inquisition", "Gawain's Inquisition",
         "Gawain forces a player on a Quest to reveal their card; revealing a Success exiles Gawain.",
         "ability", "good", page="gawain", anchor="ability",
         aliases=("Exiled", "Exile")),
    role("servant-of-camelot", "Servant of Camelot", "good",
         "A plain Good role with no information.", players="5–10 players",
         aliases=("Servant", "Servants of Camelot")),
    role("balin", "Balin the Savage", "good",
         "Not currently played.", aliases=("Balin",), retired=True),

    # ---- Evil ----
    role("mordred", "Mordred", "evil", "Hidden from Merlin."),
    role("morgana", "Morgana", "evil",
         "Appears as Merlin to Percival. Can reverse the proposal order."),
    Term("sorceress", "Sorceress",
         "Morgana declares on her proposal, picks the next proposer and reverses the proposal order.",
         "ability", "evil", page="morgana", anchor="sorceress"),
    role("maelegant", "Maelegant", "evil",
         "May play Reversal. Seen by Guinevere."),
    role("agravaine", "Agravaine", "evil",
         "Must play Fail. Can Betray to fail a Quest that succeeded anyway."),
    Term("betrayal", "Betrayal",
         "If a Quest with Agravaine succeeds, Agravaine may declare and make it fail.",
         "ability", "evil", page="agravaine", anchor="betrayal"),
    role("colgrevance", "Colgrevance", "evil",
         "Knows exactly which role every other Evil player has, Oberon included."),
    role("oberon", "Oberon", "evil",
         "Sees the other Evil players, who don't see them back. Can join a Hammer team."),
    Term("changeling", "Changeling",
         "Once per game, Oberon may swap themselves onto a team sent by Hammer.",
         "ability", "evil", page="oberon", anchor="changeling"),
    role("minion-of-mordred", "Minion of Mordred", "evil",
         "A plain Evil role.", players="5–10 players",
         aliases=("Minion", "Minions of Mordred")),

    # ---- Neutral ----
    role("pellinore", "Pellinore", "neutral",
         "Hunts the Questing Beast and wins by keeping their sanity.",
         aliases=("Pelinor",)),
    role("questing-beast", "The Questing Beast", "neutral",
         "Must play Questing Beast Was Here cards and score points by evading Pellinore.",
         aliases=("Questing Beast", "Beast")),
]

BY_SLUG: dict[str, Term] = {t.slug: t for t in TERMS}
_LOOKUP: dict[str, Term] = {}
for _t in TERMS:
    for _name in (_t.slug, _t.title, *_t.aliases):
        key = _name.casefold()
        assert _LOOKUP.get(key, _t) is _t, f"duplicate rule term {_name!r}"
        _LOOKUP[key] = _t

# Pages that have their own template under templates/rules/.
PAGES = sorted({t.page_slug for t in TERMS})


def get_term(name: str) -> Term:
    try:
        return _LOOKUP[str(name).casefold()]
    except KeyError:
        raise KeyError(f"Unknown rule term {name!r}; add it to rules.TERMS") from None


def term_link(name, label=None) -> Markup:
    t = get_term(name)
    team = f" term-{t.team}" if t.team else ""
    return Markup('<a class="term{}" href="{}" data-term="{}">{}</a>').format(
        team, t.url(), t.slug, label if label is not None else str(name))


def terms_json() -> Markup:
    data = {t.slug: {"title": t.title, "summary": t.summary,
                     "team": t.team, "url": t.url()} for t in TERMS}
    # Safe inside <script>: escape the characters that could end the tag.
    s = json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup(s)


_MARKUP = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]+?))?\]\]")


class TermLinkExtension(Extension):
    """Expands [[Term]] and [[Term|label]] into {{ term(...) }} calls at load time."""

    def preprocess(self, source, name, filename=None):
        def repl(m):
            args = json.dumps(m.group(1).strip())
            if m.group(2):
                args += ", " + json.dumps(m.group(2).strip())
            return "{{ term(" + args + ") }}"
        return _MARKUP.sub(repl, source)


def init_app(app):
    app.jinja_env.add_extension(TermLinkExtension)
    app.jinja_env.globals["term"] = term_link
    app.jinja_env.globals["terms_json"] = terms_json
    app.jinja_env.globals["get_term"] = get_term
