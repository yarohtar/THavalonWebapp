"""The rules a host can change: who sees whom, which roles appear at which
player counts, lonely-role transformations, Gareth, the Assassination, and a
few card and ability rules.

A RuleSet stores only the settings that differ from the defaults (the normal
THavalon rules), so

  - the defaults are exactly the rules the game had before settings existed,
  - a host's cookie holds just their changes,
  - games pickled before a setting was added still load (it reads its default).

Every setting is described once in SETTINGS (key, kind, default, label, and
the section of the host page it belongs to). Code reads a setting with
`rules[key]`; the helpers below cover the questions the engine asks.

This module knows roles only by name, so every other part of the engine
can import it.
"""
from __future__ import annotations

from dataclasses import dataclass

COUNTS = tuple(range(5, 11))          # player counts a game can have
ALL_COUNTS = frozenset(COUNTS)


def _from(n : int) -> frozenset[int]:
    return frozenset(range(n, 11))


@dataclass(frozen=True)
class Setting:
    key : str
    kind : str                        # bool | counts | choice
    default : object
    label : str                       # shown on the host page
    section : str                     # host page card: a role name or "Assassination"
    options : tuple = ()              # choice: ((value, label), ...)
    help : str = ""                   # one-line explanation on the host page

    def parse(self, raw):
        """A stored/submitted value -> the setting's type. ValueError if invalid."""
        if self.kind == "bool":
            if isinstance(raw, str):
                return raw.lower() in ("1", "true", "on", "yes")
            return bool(raw)
        if self.kind == "counts":
            if isinstance(raw, str):
                raw = [x for x in raw.split(",") if x.strip()]
            counts = frozenset(int(x) for x in raw)
            if not counts <= ALL_COUNTS:
                raise ValueError(f"{self.label}: player counts must be 5 to 10.")
            return counts
        if self.kind == "choice":
            values = [v for v, _ in self.options]
            if raw not in values:
                # numbers come back from forms and JSON as strings
                match = [v for v in values if str(v) == str(raw)]
                if not match:
                    raise ValueError(f"{self.label}: unknown choice {raw!r}.")
                raw = match[0]
            return raw
        raise AssertionError(self.kind)

    def to_json(self, value):
        return sorted(value) if self.kind == "counts" else value


# ---------------------------------------------------------------- the settings

# Roles the host can select, with the player counts they appear at by default.
DEFAULT_PLAYERS : dict[str, frozenset[int]] = {
    "Merlin": ALL_COUNTS, "Percival": ALL_COUNTS, "Tristan": ALL_COUNTS,
    "Iseult": ALL_COUNTS, "Arthur": ALL_COUNTS, "Lancelot": ALL_COUNTS,
    "Guinevere": _from(7), "Gawain": _from(10), "Balin the Savage": frozenset({6, 9}),
    "Mordred": ALL_COUNTS, "Morgana": ALL_COUNTS, "Maelegant": ALL_COUNTS,
    "Agravaine": _from(7), "Colgrevance": _from(10), "Oberon": ALL_COUNTS,
    "Gareth": frozenset({9}),
    "Pellinore": frozenset({9}),       # and The Questing Beast: they always come together
}

# What a lonely role becomes, the role whose setting holds the player counts
# where it changes, and the default counts.
TRANSFORMS = {
    # key role : (roles it applies to, becomes, default counts)
    "Merlin": (("Merlin",), "Nilrem", _from(7)),
    "Percival": (("Percival",), "Galahad", _from(7)),
    "Lovers": (("Tristan", "Iseult"), "Uther", _from(7)),
    "Guinevere": (("Guinevere",), "Ygraine", ALL_COUNTS),
}

# Roles Merlin can be set to see (as Evil), with the default.
MERLIN_SEES = {"Mordred": False, "Morgana": True, "Maelegant": True, "Agravaine": True,
               "Colgrevance": True, "Oberon": True, "Minion of Mordred": True,
               "Lancelot": True, "Balin the Savage": True}
PERCIVAL_SEES = {"Merlin": True, "Morgana": True}
GUINEVERE_SEES = {"Lancelot": True, "Arthur": True, "Maelegant": True}

# Assassination choices: kind -> (roles that must all be named, label).
# The order here is the order the assassin sees them in.
ASSASSINATION_TARGETS : dict[str, tuple[tuple[str, ...], str]] = {
    "merlin": (("Merlin",), "Merlin"),
    "nilrem": (("Nilrem",), "Nilrem"),
    "lovers": (("Tristan", "Iseult"), "the Lovers"),
    "percival": (("Percival",), "Percival"),
    "galahad": (("Galahad",), "Galahad"),
    "arthur": (("Arthur",), "Arthur"),
    "guinevere": (("Guinevere",), "Guinevere"),
    "ygraine": (("Ygraine",), "Ygraine"),
    "uther": (("Uther",), "Uther"),
    "lancelot": (("Lancelot",), "Lancelot"),
    "gawain": (("Gawain",), "Gawain"),
}
DEFAULT_TARGETS = {"merlin", "nilrem", "lovers"}

GARETH_TEAMS = ("Good", "Evil")


def _settings() -> list[Setting]:
    s : list[Setting] = []
    add = s.append

    add(Setting("assassination.enabled", "bool", True, "Evil gets an Assassination",
                "Assassination",
                help="If off, Good wins as soon as 3 Quests succeed."))
    for kind, (roles, label) in ASSASSINATION_TARGETS.items():
        add(Setting(f"assassination.target.{kind}", "bool", kind in DEFAULT_TARGETS,
                    f"{'Two' if len(roles) == 2 else 'One'} as {label}", "Assassination"))
    add(Setting("assassination.none", "bool", True, "Naming no one is a choice",
                "Assassination",
                help="Correct only if none of the targets above is in the game."))

    for role, counts in DEFAULT_PLAYERS.items():
        label = ("Player counts (Pellinore and the Questing Beast)" if role == "Pellinore"
                 else "Player counts")
        add(Setting(f"{role}.players", "counts", counts, label, role,
                    help="Games this role can be dealt in, if selected."))

    for key, (roles, becomes, counts) in TRANSFORMS.items():
        section = "Tristan & Iseult" if key == "Lovers" else key
        add(Setting(f"{key}.lonely", "counts", counts, f"Becomes {becomes} when lonely at",
                    section))

    for role, default in MERLIN_SEES.items():
        add(Setting(f"Merlin.sees.{role}", "bool", default, role, "Merlin"))
    for role, default in PERCIVAL_SEES.items():
        add(Setting(f"Percival.sees.{role}", "bool", default, role, "Percival"))
    for role, default in GUINEVERE_SEES.items():
        add(Setting(f"Guinevere.sees.{role}", "bool", default, role, "Guinevere"))

    add(Setting("Nilrem.known", "bool", True, "Good players are told who Nilrem is", "Merlin"))

    add(Setting("Oberon.seen_by_evil", "bool", False,
                "The other Evil players see Oberon", "Oberon"))
    add(Setting("Oberon.sees_evil", "bool", True, "Oberon sees the other Evil players",
                "Oberon"))
    add(Setting("Oberon.announced", "bool", True,
                "Evil players are told that an Oberon is in the game", "Oberon",
                help="Only matters when they don't see Oberon."))

    add(Setting("Agravaine.must_fail", "bool", True, "Must play Fail", "Agravaine"))
    add(Setting("Lancelot.reversal", "bool", True, "May play Reversal", "Lancelot"))
    add(Setting("Maelegant.reversal", "bool", True, "May play Reversal", "Maelegant"))
    add(Setting("Arthur.proclaim_after", "choice", 2, "Can Proclaim after", "Arthur",
                options=((1, "1 failed Quest"), (2, "2 failed Quests"))))

    add(Setting("Gareth.knows", "choice", "both", "Gareth is told", "Gareth",
                options=(("both", "their Knight and their Rival"),
                         ("knight", "only their Knight"),
                         ("rival", "only their Rival"))))
    add(Setting("Gareth.lady", "choice", "good", "The Lady of the Lake shows Gareth as",
                "Gareth", options=(("good", "Good, whatever their team"),
                                   ("team", "their real team"))))
    gareth_defaults = {
        # what : (label, default when blue, default when red)
        "merlin_sees": ("Merlin sees Gareth as Evil", False, True),
        "merlin_knows_role": ("Merlin is told which player is Gareth", False, False),
        "evil_sees": ("Evil players see Gareth as one of them", False, True),
        "evil_knows_role": ("Evil players are told which player is Gareth", False, False),
    }
    for team in GARETH_TEAMS:
        for what, (label, blue, red) in gareth_defaults.items():
            add(Setting(f"Gareth.{team}.{what}", "bool", blue if team == "Good" else red,
                        label, "Gareth"))
    return s


SETTINGS : dict[str, Setting] = {s.key: s for s in _settings()}


# ---------------------------------------------------------------- RuleSet

class RuleSet:
    """The rules of one game (or a host's saved preferences). Immutable in
    use: build a new one to change it."""

    def __init__(self, values : dict | None = None):
        """values: key -> value (any parseable form). Unknown keys are ignored,
        so a cookie saved by another version of the app still works; bad
        values raise ValueError."""
        self.values : dict[str, object] = {}
        for key, raw in (values or {}).items():
            setting = SETTINGS.get(key)
            if setting is None:
                continue
            value = setting.parse(raw)
            if value != setting.default:
                self.values[key] = value

    def __getitem__(self, key : str):
        return self.values.get(key, SETTINGS[key].default)

    def __eq__(self, other) -> bool:
        return isinstance(other, RuleSet) and self.values == other.values

    def __hash__(self):
        return hash(tuple(sorted((k, str(v)) for k, v in self.values.items())))

    def __repr__(self) -> str:
        return f"RuleSet({self.to_json()!r})"

    @property
    def is_default(self) -> bool:
        return not self.values

    def changed(self, key : str) -> bool:
        return key in self.values

    def changed_in(self, section : str) -> list[str]:
        return [k for k in self.values if SETTINGS[k].section == section]

    def to_json(self) -> dict:
        """Only the changes, JSON-friendly (for the host's cookie)."""
        return {k: SETTINGS[k].to_json(v) for k, v in sorted(self.values.items())}

    @classmethod
    def from_json(cls, data : dict | None) -> RuleSet:
        """Like RuleSet(data), but a broken saved value is dropped, not an error."""
        values = {}
        for key, raw in (data or {}).items():
            try:
                RuleSet({key: raw})
            except (ValueError, TypeError):
                continue
            values[key] = raw
        return cls(values)

    # ------------------------------------------------------------ questions

    def players_key(self, role_name : str) -> str | None:
        if role_name == "The Questing Beast":
            role_name = "Pellinore"
        key = f"{role_name}.players"
        return key if key in SETTINGS else None

    def can_appear(self, role_name : str, n : int) -> bool | None:
        """Whether a role can be in an n-player game; None if the role has no
        player-count rule (Servants, Minions)."""
        key = self.players_key(role_name)
        if key is not None:
            return n in self[key]
        for tkey, (roles, becomes, _) in TRANSFORMS.items():
            if becomes == role_name:
                return n in self[f"{tkey}.lonely"] and any(
                    n in self[f"{r}.players"] for r in roles)
        return None

    def lonely_counts(self, role_name : str) -> frozenset[int]:
        """Player counts where `role_name` transforms when lonely (empty: never)."""
        for key, (roles, _, _) in TRANSFORMS.items():
            if role_name in roles:
                return self[f"{key}.lonely"]
        return frozenset()

    def merlin_sees(self, role_name : str) -> bool:
        return bool(self[f"Merlin.sees.{role_name}"]) if role_name in MERLIN_SEES else False

    def percival_sees(self) -> list[str]:
        return [r for r in PERCIVAL_SEES if self[f"Percival.sees.{r}"]]

    def guinevere_sees(self) -> list[str]:
        return [r for r in GUINEVERE_SEES if self[f"Guinevere.sees.{r}"]]

    def gareth(self, team : str, what : str) -> bool:
        """Gareth visibility rule for Gareth on `team` (Good/Evil)."""
        return bool(self[f"Gareth.{team}.{what}"]) if team in GARETH_TEAMS else False

    def assassination_kinds(self) -> list[str]:
        """The choices the assassin has ('none' last). Empty: no Assassination."""
        if not self["assassination.enabled"]:
            return []
        kinds = [k for k in ASSASSINATION_TARGETS if self[f"assassination.target.{k}"]]
        if self["assassination.none"]:
            kinds.append("none")
        return kinds

    @property
    def assassination_on(self) -> bool:
        return bool(self.assassination_kinds())

    def assassination_targets(self) -> list[str]:
        return [k for k in self.assassination_kinds() if k != "none"]

    def reversal_roles(self) -> list[str]:
        return [r for r in ("Lancelot", "Maelegant") if self[f"{r}.reversal"]]


DEFAULT = RuleSet()
