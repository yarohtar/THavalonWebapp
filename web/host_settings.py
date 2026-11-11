"""The host page's settings: the host's saved preferences (kept in their
session cookie: roles, Evil count and quests per player count, Lady, rule
changes), and the rules editor (which settings appear under which role,
and reading the submitted form into a RuleSet)."""
from __future__ import annotations

from flask import session

from thavalon.dealing import DEFAULT_TEAM_SIZES, default_double_fail_quest, default_num_evils
from thavalon.roles import Role, all_roles, balin, beast, gareth, pellinore
from thavalon.ruleset import RuleSet, SETTINGS


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

def _keys(prefix : str) -> list[str]:
    return [k for k in SETTINGS if k.startswith(prefix)]


# Roles as the host chooses them, each with the rules shown under it.
# rows: (subheading or None, setting keys).
HOST_GROUPS = [
    dict(title='Merlin', team='good', roles=['Merlin'], rows=[
        (None, ['Merlin.players', 'Merlin.lonely', 'Nilrem.known']),
        ('Merlin sees as Evil', _keys('Merlin.sees.'))]),
    dict(title='Percival', team='good', roles=['Percival'], rows=[
        (None, ['Percival.players', 'Percival.lonely']),
        ('Percival sees (as Merlin or Morgana)', _keys('Percival.sees.'))]),
    dict(title='The Lovers', team='good', roles=['Tristan', 'Iseult'], rows=[
        (None, ['Tristan.players', 'Iseult.players', 'Lovers.lonely'])],
         labels={'Tristan.players': 'Tristan: player counts',
                 'Iseult.players': 'Iseult: player counts'}),
    dict(title='Arthur', team='good', roles=['Arthur'], rows=[
        (None, ['Arthur.players', 'Arthur.proclaim_after'])]),
    dict(title='Lancelot', team='good', roles=['Lancelot'], rows=[
        (None, ['Lancelot.players', 'Lancelot.reversal'])]),
    dict(title='Guinevere', team='good', roles=['Guinevere'], rows=[
        (None, ['Guinevere.players', 'Guinevere.lonely']),
        ('Guinevere sees', _keys('Guinevere.sees.'))]),
    dict(title='Gawain', team='good', roles=['Gawain'], rows=[(None, ['Gawain.players'])]),
    dict(title='Balin the Savage', team='good', roles=['Balin the Savage'],
         rows=[(None, ['Balin the Savage.players'])]),
    dict(title='Mordred', team='evil', roles=['Mordred'], rows=[(None, ['Mordred.players'])]),
    dict(title='Morgana', team='evil', roles=['Morgana'], rows=[(None, ['Morgana.players'])]),
    dict(title='Maelegant', team='evil', roles=['Maelegant'], rows=[
        (None, ['Maelegant.players', 'Maelegant.reversal'])]),
    dict(title='Agravaine', team='evil', roles=['Agravaine'], rows=[
        (None, ['Agravaine.players', 'Agravaine.must_fail'])]),
    dict(title='Colgrevance', team='evil', roles=['Colgrevance'],
         rows=[(None, ['Colgrevance.players'])]),
    dict(title='Oberon', team='evil', roles=['Oberon'], rows=[
        (None, ['Oberon.players', 'Oberon.seen_by_evil', 'Oberon.sees_evil',
                'Oberon.announced'])]),
    dict(title='Gareth', team='either', roles=['Gareth'], rows=[
        (None, ['Gareth.players', 'Gareth.knows', 'Gareth.lady']),
        ('When Gareth is blue (Good)', _keys('Gareth.Good.')),
        ('When Gareth is red (Evil)', _keys('Gareth.Evil.'))],
         note="Careful: a rule that differs between blue and red Gareth tells whoever "
              "it applies to which team Gareth is on (by default Merlin and Evil see "
              "a red Gareth among the Evil players, as if Evil, but never a blue one)."),
    dict(title='Pellinore & the Questing Beast', team='neutral',
         roles=['Pellinore', 'The Questing Beast'], rows=[(None, ['Pellinore.players'])],
         labels={'Pellinore.players': 'Player counts (they always play together)'}),
]

for _g in HOST_GROUPS:
    _g['keys'] = [k for _, keys in _g['rows'] for k in keys]
    _g.setdefault('labels', {})
ASSASSINATION_KEYS = _keys('assassination.')
SELECTABLE_ROLES = [r for g_ in HOST_GROUPS for r in g_['roles']]


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
    return RuleSet(values)


def form_ruleset(form) -> RuleSet:
    """Rules from the host form, or the saved ones if the form had no rules."""
    return ruleset_from_form(form) if form.get('rules_form') else pref_ruleset()


def ordered_roles(role_names : list[str]) -> list[Role]:
    """Selected roles in the usual order (dealing is random, but this keeps
    it exactly as it always was)."""
    names = set(role_names)
    return [r for r in all_roles if str(r) in names]
