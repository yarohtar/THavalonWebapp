"""The host page's settings: the host's saved preferences (kept in their
session cookie: roles, Evil count and quests per player count, Lady, rule
changes), and the rules editor (each setting listed once under its role,
with its wording; reading the submitted form into a RuleSet)."""
from __future__ import annotations

from dataclasses import dataclass

from flask import session

from thavalon.dealing import DEFAULT_TEAM_SIZES, default_double_fail_quest, default_num_evils
from thavalon.roles import Role, all_roles, balin, beast, gareth, pellinore
from thavalon.ruleset import (ASSASSINATION_TARGETS, GUINEVERE_SEES, MERLIN_SEES,
                              PERCIVAL_SEES, SETTINGS, TRANSFORMS, RuleSet, Setting,
                              SettingError)


# ---------------------------------------------------------------- saved preferences

# Roles selected until the host chooses (the Neutrals and Balin are opt-in).
DEFAULT_ROLE_NAMES = [str(r) for r in all_roles if r not in (balin, pellinore, beast)]


def _prefs() -> dict:
    return session.get('host_prefs', {})


def pref_roles() -> list[str]:
    roles = _prefs().get('roles', DEFAULT_ROLE_NAMES)
    if not _prefs().get('gareth_offered'):     # saved before Gareth existed
        roles = roles + [str(gareth)]
    return roles


def default_quests(n : int) -> dict:
    return dict(sizes = DEFAULT_TEAM_SIZES[n],
                double_fail = default_double_fail_quest(n) or 0)


def evils_key(n : int, gareth_plays : bool) -> str:
    return f'{n}+gareth' if gareth_plays else str(n)


def pref_evils(n : int, gareth_plays : bool) -> int:
    return _prefs().get('evils', {}).get(evils_key(n, gareth_plays),
                                         default_num_evils(n, gareth_plays))


def pref_quests(n : int, evils : int) -> dict:
    return _prefs().get('quests', {}).get(f'{n}-{evils}') or default_quests(n)


def pref_lady() -> bool:
    return _prefs().get('lady', False)


def pref_ruleset() -> RuleSet:
    """The host's rule changes, kept in their cookie (only what differs from
    the defaults)."""
    return RuleSet.from_json(_prefs().get('rules'))


def save_pref_ruleset(ruleset : RuleSet):
    prefs = _prefs()
    prefs['rules'] = ruleset.to_json()
    session['host_prefs'] = prefs
    session.modified = True


def save_prefs(roles : list[str], rules_used : dict):
    n, evils = rules_used['num_players'], rules_used['num_evils']
    prefs = _prefs()
    prefs['roles'] = roles
    prefs['gareth_offered'] = True
    prefs['lady'] = rules_used['lady']
    prefs.setdefault('evils', {})[evils_key(n, rules_used['gareth'])] = evils
    prefs.setdefault('quests', {})[f'{n}-{evils}'] = dict(
        sizes = rules_used['team_sizes'], double_fail = rules_used['double_fail'] or 0)
    session['host_prefs'] = prefs
    session.modified = True


def save_selection(roles : list[str], lady : bool):
    """Remember the selected roles and the Lady without starting a game."""
    prefs = _prefs()
    prefs['roles'] = roles
    prefs['gareth_offered'] = True
    prefs['lady'] = lady
    session['host_prefs'] = prefs


# ---------------------------------------------------------------- the rules editor

@dataclass(frozen=True)
class HostSetting:
    """A rule setting as the host page shows it."""
    setting : Setting
    label : str
    help : str = ""
    options : tuple = ()        # choice: ((value, label), ...) in the setting's order

    @property
    def kind(self) -> str:
        return self.setting.kind


# Every setting is listed once below, under the role it belongs to, with its
# wording. HOST_SETTINGS collects them by key.
HOST_SETTINGS : dict[str, HostSetting] = {}


def entry(key : str, label : str, help : str = "", choices : dict | None = None) -> str:
    """Register a setting's wording (choices: value -> label); returns its key."""
    assert key not in HOST_SETTINGS, f"{key} is listed twice"
    setting = SETTINGS[key]
    options = tuple((v, choices[v]) for v in setting.choices) if choices else ()
    HOST_SETTINGS[key] = HostSetting(setting, label, help, options)
    return key


def players(role : str, label : str = "Player counts") -> str:
    return entry(f"{role}.players", label, "Games this role can be dealt in, if selected.")


def lonely(key : str) -> str:
    return entry(f"{key}.lonely", f"Becomes {TRANSFORMS[key][1]} when lonely at")


def sees(viewer : str, roles) -> list[str]:
    return [entry(f"{viewer}.sees.{role}", role) for role in roles]


def gareth_team(team : str) -> list[str]:
    return [entry(f"Gareth.{team}.merlin_sees", "Merlin sees Gareth as Evil"),
            entry(f"Gareth.{team}.merlin_knows_role", "Merlin is told which player is Gareth"),
            entry(f"Gareth.{team}.evil_sees", "Evil players see Gareth as one of them"),
            entry(f"Gareth.{team}.evil_knows_role",
                  "Evil players are told which player is Gareth")]


def group(title : str, team : str, roles : list[str], *rows, note : str | None = None) -> dict:
    """A role card on the host page. rows: (subheading or None, setting keys)."""
    return dict(title=title, team=team, roles=roles, rows=list(rows), note=note,
                keys=[k for _, keys in rows for k in keys])


# Roles as the host chooses them, each with the rules shown under it.
HOST_GROUPS = [
    group('Merlin', 'good', ['Merlin'],
          (None, [players('Merlin'), lonely('Merlin'),
                  entry('Nilrem.known', "Good players are told who Nilrem is")]),
          ('Merlin sees as Evil', sees('Merlin', MERLIN_SEES))),
    group('Percival', 'good', ['Percival'],
          (None, [players('Percival'), lonely('Percival')]),
          ('Percival sees (as Merlin or Morgana)', sees('Percival', PERCIVAL_SEES))),
    group('The Lovers', 'good', ['Tristan', 'Iseult'],
          (None, [players('Tristan', "Tristan: player counts"),
                  players('Iseult', "Iseult: player counts"), lonely('Lovers')])),
    group('Arthur', 'good', ['Arthur'],
          (None, [players('Arthur'),
                  entry('Arthur.proclaim_after', "Can Proclaim after",
                        choices={1: "1 failed Quest", 2: "2 failed Quests"})])),
    group('Lancelot', 'good', ['Lancelot'],
          (None, [players('Lancelot'), entry('Lancelot.reversal', "May play Reversal")])),
    group('Guinevere', 'good', ['Guinevere'],
          (None, [players('Guinevere'), lonely('Guinevere')]),
          ('Guinevere sees', sees('Guinevere', GUINEVERE_SEES))),
    group('Gawain', 'good', ['Gawain'], (None, [players('Gawain')])),
    group('Balin the Savage', 'good', ['Balin the Savage'],
          (None, [players('Balin the Savage')])),
    group('Mordred', 'evil', ['Mordred'], (None, [players('Mordred')])),
    group('Morgana', 'evil', ['Morgana'], (None, [players('Morgana')])),
    group('Maelegant', 'evil', ['Maelegant'],
          (None, [players('Maelegant'), entry('Maelegant.reversal', "May play Reversal")])),
    group('Agravaine', 'evil', ['Agravaine'],
          (None, [players('Agravaine'), entry('Agravaine.must_fail', "Must play Fail")])),
    group('Colgrevance', 'evil', ['Colgrevance'], (None, [players('Colgrevance')])),
    group('Oberon', 'evil', ['Oberon'],
          (None, [players('Oberon'),
                  entry('Oberon.seen_by_evil', "The other Evil players see Oberon"),
                  entry('Oberon.sees_evil', "Oberon sees the other Evil players"),
                  entry('Oberon.announced', "Evil players are told that an Oberon is in the game",
                        "Only matters when they don't see Oberon.")])),
    group('Gareth', 'either', ['Gareth'],
          (None, [players('Gareth'),
                  entry('Gareth.knows', "Gareth is told",
                        choices={"both": "their Knight and their Rival",
                                 "knight": "only their Knight", "rival": "only their Rival"}),
                  entry('Gareth.lady', "The Lady of the Lake shows Gareth as",
                        choices={"good": "Good, whatever their team",
                                 "team": "their real team"}),
                  entry('Gareth.arthur_knight', "Arthur can be Gareth's Knight")]),
          ('When Gareth is blue (Good)', gareth_team('Good')),
          ('When Gareth is red (Evil)', gareth_team('Evil')),
          note="Careful: a rule that differs between blue and red Gareth tells whoever "
               "it applies to which team Gareth is on (by default Merlin and Evil see "
               "a red Gareth among the Evil players, as if Evil, but never a blue one)."),
    group('Pellinore & the Questing Beast', 'neutral', ['Pellinore', 'The Questing Beast'],
          (None, [players('Pellinore', "Player counts (they always play together)")])),
]

# The Assassination has its own card: on/off, the targets, then "no one".
ASSASSINATION_KEYS = [
    entry("assassination.enabled", "Evil gets an Assassination",
          "If off, Good wins as soon as 3 Quests succeed."),
    *[entry(f"assassination.target.{kind}", f"{'Two' if len(roles) == 2 else 'One'} as {label}")
      for kind, (roles, label) in ASSASSINATION_TARGETS.items()],
    entry("assassination.none", "Naming no one is a choice",
          "Correct only if none of the targets above is in the game."),
]

assert HOST_SETTINGS.keys() == SETTINGS.keys(), \
    f"settings missing from the host page: {sorted(SETTINGS.keys() - HOST_SETTINGS.keys())}"
SELECTABLE_ROLES = [r for g in HOST_GROUPS for r in g['roles']]


def ruleset_from_form(form) -> RuleSet:
    """The host page's rules fields: `rule:<key>`. Checkboxes send
    nothing when unticked, so every setting is read (a missing bool is
    False, missing counts are none)."""
    values = {}
    for key, setting in SETTINGS.items():
        name = f"rule:{key}"
        if setting.kind == "bool":
            values[key] = name in form
        elif setting.kind == "counts":
            values[key] = form.getlist(name)
        elif name in form:
            values[key] = form[name]
    try:
        return RuleSet(values)
    except SettingError as e:
        raise ValueError(f"{HOST_SETTINGS[e.key].label}: {e.problem}") from None


def form_ruleset(form) -> RuleSet:
    """Rules from the host form, or the saved ones if the form had no rules."""
    return ruleset_from_form(form) if form.get('rules_form') else pref_ruleset()


def ordered_roles(role_names : list[str]) -> list[Role]:
    """Selected roles in the usual order (dealing is random, but this keeps
    it exactly as it always was)."""
    names = set(role_names)
    return [r for r in all_roles if str(r) in names]
