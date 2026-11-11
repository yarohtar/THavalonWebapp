"""The rules a host can change: who sees whom, which roles appear at which
player counts, lonely-role transformations, Gareth, the Assassination, and a
few card and ability rules.

A RuleSet stores only the settings that differ from the defaults (the normal
THavalon rules), so

  - the defaults are exactly the rules the game had before settings existed,
  - a host's cookie holds just their changes,
  - games pickled before a setting was added still load (it reads its default).

Every setting is described once in SETTINGS (key, kind, default, and the
allowed choices). Code reads a setting with `rules[key]`; the helpers below
cover the questions the engine asks. How settings are worded and laid out
for the host is the website's business (web/host_settings.py).

This module knows roles only by name, so every other part of the engine
can import it.
"""
from __future__ import annotations

from dataclasses import dataclass

COUNTS = tuple(range(5, 11))          # player counts a game can have
ALL_COUNTS = frozenset(COUNTS)


def _from(n : int) -> frozenset[int]:
    return frozenset(range(n, 11))


class SettingError(ValueError):
    """A setting was given a value it can't have."""
    def __init__(self, key : str, problem : str):
        super().__init__(f"{key}: {problem}")
        self.key = key
        self.problem = problem


@dataclass(frozen=True)
class Setting:
    key : str
    kind : str                        # bool | counts | choice
    default : object
    choices : tuple = ()              # choice: the allowed values

    def parse(self, raw):
        """A stored/submitted value -> the setting's type. SettingError if invalid."""
        if self.kind == "bool":
            if isinstance(raw, str):
                return raw.lower() in ("1", "true", "on", "yes")
            return bool(raw)
        if self.kind == "counts":
            if isinstance(raw, str):
                raw = [x for x in raw.split(",") if x.strip()]
            counts = frozenset(int(x) for x in raw)
            if not counts <= ALL_COUNTS:
                raise SettingError(self.key, "player counts must be 5 to 10.")
            return counts
        if self.kind == "choice":
            if raw not in self.choices:
                # numbers come back from forms and JSON as strings
                match = [v for v in self.choices if str(v) == str(raw)]
                if not match:
                    raise SettingError(self.key, f"unknown choice {raw!r}.")
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

    add(Setting("assassination.enabled", "bool", True))
    for kind in ASSASSINATION_TARGETS:
        add(Setting(f"assassination.target.{kind}", "bool", kind in DEFAULT_TARGETS))
    add(Setting("assassination.none", "bool", True))   # naming no one is a choice

    for role, counts in DEFAULT_PLAYERS.items():
        add(Setting(f"{role}.players", "counts", counts))
    for key, (_, _, counts) in TRANSFORMS.items():
        add(Setting(f"{key}.lonely", "counts", counts))

    for viewer, roles in (("Merlin", MERLIN_SEES), ("Percival", PERCIVAL_SEES),
                          ("Guinevere", GUINEVERE_SEES)):
        for role, default in roles.items():
            add(Setting(f"{viewer}.sees.{role}", "bool", default))

    add(Setting("Nilrem.known", "bool", True))           # Good players learn who Nilrem is
    add(Setting("Oberon.seen_by_evil", "bool", False))
    add(Setting("Oberon.sees_evil", "bool", True))
    add(Setting("Oberon.announced", "bool", True))       # Evil learn an Oberon is in the game

    add(Setting("Agravaine.must_fail", "bool", True))
    add(Setting("Lancelot.reversal", "bool", True))
    add(Setting("Maelegant.reversal", "bool", True))
    add(Setting("Arthur.proclaim_after", "choice", 2, choices=(1, 2)))   # failed Quests

    add(Setting("Gareth.knows", "choice", "both", choices=("both", "knight", "rival")))
    add(Setting("Gareth.lady", "choice", "good", choices=("good", "team")))  # what she shows
    gareth_defaults = {
        # what : (default when blue, default when red)
        "merlin_sees": (False, True),            # Merlin sees Gareth as Evil
        "merlin_knows_role": (False, False),     # Merlin is told which player is Gareth
        "evil_sees": (False, True),              # Evil see Gareth as one of them
        "evil_knows_role": (False, False),       # Evil are told which player is Gareth
    }
    for team in GARETH_TEAMS:
        for what, (blue, red) in gareth_defaults.items():
            add(Setting(f"Gareth.{team}.{what}", "bool", blue if team == "Good" else red))
    return s


SETTINGS : dict[str, Setting] = {s.key: s for s in _settings()}


# ---------------------------------------------------------------- RuleSet

class RuleSet:
    """The rules of one game (or a host's saved preferences). Immutable in
    use: build a new one to change it."""

    def __init__(self, values : dict | None = None):
        """values: key -> value (any parseable form). Unknown keys are ignored,
        so a cookie saved by another version of the app still works; bad
        values raise ValueError (SettingError when it names the setting)."""
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

    def changes(self, prefix : str = "") -> list[str]:
        """The changed settings whose keys start with `prefix`."""
        return [k for k in self.values if k.startswith(prefix)]

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
