import flask
from flask import Flask, render_template, request, session, url_for, g
import random
import secrets
import uuid as uuid_lib
from thavalon.dealing import (AvalonBuilder, default_num_evils, DEFAULT_TEAM_SIZES,
                              default_double_fail_quest, has_gareth)
from thavalon.roles import Role, all_roles, balin, pellinore, beast, gareth
import os
import sys
from dotenv import load_dotenv
load_dotenv()
from flask.views import MethodView
import rules
import rule_notes
import rule_text
from thavalon.ruleset import RuleSet, SETTINGS, DEFAULT as DEFAULT_RULES, ASSASSINATION_TARGETS
import events
from thavalon import GameController, GameState, RuleError
import store
from store import Store, Conflict
import votes
from votes import HostVote

app = Flask(__name__)

def _secret_key() -> str:
    """Signs session cookies, which hold who you are (player id, host): anyone
    who knows it can act as any player. Set SECRET_KEY on the server (each
    site its own, kept out of the repo). Without it, a random key is used
    for this run only, which is fine locally but not with several workers
    or across restarts, so it is refused when REDIS_URL is set."""
    key = os.environ.get('SECRET_KEY', '').strip()
    if key:
        return key
    if os.environ.get('REDIS_URL'):
        raise RuntimeError("SECRET_KEY is not set.")
    import logging
    logging.getLogger(__name__).warning(
        "SECRET_KEY is not set: using a random key (sessions end on restart).")
    return secrets.token_hex(32)

app.secret_key = _secret_key()
rules.init_app(app)
rule_text.init_app(app)
app.jinja_env.globals.update(
    rule_notes_for = rule_notes.notes_for,
    rule_summary_notes = rule_notes.summary_notes,
    expand_note = rule_notes.expand,
    assassination_label = lambda kind: ASSASSINATION_TARGETS[kind][1],
    assassination_size = lambda kind: len(ASSASSINATION_TARGETS[kind][0]))

app.register_blueprint(events.blueprint)

# Channel for "a game was opened" events, for players not in any game yet.
LOBBIES_CHANNEL = 'lobbies'

def new_event(event_name, channel, data = None):
    events.publish(channel, event_name, data)

@app.context_processor
def inject_events_url():
    """Pages that set g.channel get live updates from that channel."""
    channel = g.get('channel')
    if channel is None:
        return dict(events_url = None)
    return dict(events_url = url_for('events.stream', channel = channel,
                                     last_id = events.bus.current_id(channel)))

class GameSettings:
    """What the host chose. None means "use the default for the player count"."""
    num_evils : int | None = None
    team_sizes : list[int] | None = None
    double_fail : int | None = None   # quest number (1-5), 0 = no quest, None = default
    lady : bool = False               # play with the Lady of the Lake

    @classmethod
    def from_form(cls, form) -> GameSettings:
        """Raises ValueError with a readable message on bad input."""
        settings = cls()
        evils = form.get('evils', 'default')
        if evils != 'default':
            settings.num_evils = int(evils)
        sizes = [form.get(f'size{i}', '').strip() for i in range(1, 6)]
        if any(sizes):
            try:
                settings.team_sizes = [int(x) for x in sizes]
            except ValueError:
                raise ValueError("Fill in a team size for every quest.")
        double_fail = form.get('double_fail', 'default')
        if double_fail != 'default':
            settings.double_fail = int(double_fail)
        settings.lady = form.get('lady') == '1'
        return settings

    def resolve(self, num_players : int, roles : list[Role],
                ruleset : RuleSet | None = None) -> dict:
        """The rules actually in effect for a game of this size and roles."""
        n = num_players
        if n not in DEFAULT_TEAM_SIZES:
            raise ValueError("A game needs 5 to 10 players.")
        gareth = has_gareth(n, roles, ruleset)
        evils = self.num_evils if self.num_evils is not None else default_num_evils(n, gareth)
        sizes = self.team_sizes or DEFAULT_TEAM_SIZES[n]
        if any(not 2 <= k <= n for k in sizes):
            raise ValueError(f"Team sizes must be between 2 and {n} for {n} players.")
        double_fail = (self.double_fail if self.double_fail is not None
                       else default_double_fail_quest(n))
        if evils < 1 or n - evils - gareth < 1:
            raise ValueError(f"{evils} Evil players doesn't work with {n} players.")
        # Gareth counts towards proposals as if Evil (see GameState.num_evils).
        proposals = evils + gareth + 1
        return dict(num_players = n,
                    num_evils = evils,
                    gareth = gareth,
                    num_others = n - evils - gareth,
                    team_sizes = sizes,
                    double_fail = double_fail or None,
                    proposals = proposals,
                    lady = self.lady,
                    inquisition = ('none' if proposals <= 3
                                   else 'weak' if proposals == 4
                                   else 'strong'))

class AvalonGame:
    """The game a lobby is playing. Plain data: it is stored in Redis with
    its Lobby and changed only through Lobbies.update()."""
    player_info : dict[str, RoleInfo]
    roles_in_game : list[Role]
    proposers : list[str]
    def __init__(self):
        self.roles_in_game = all_roles[:]
        self.player_info = {}
        self.game_number = 0        # counts restarts, so vote keys never repeat
        self._host_vote_ids = 0
    rules : dict | None = None
    ruleset : RuleSet | None = None     # the host's rules (None in games from before)
    controller : GameController | None = None
    names : dict[str, str]          # uuid -> player name (names are the game's ids)
    host_vote : HostVote | None = None   # the latest vote the host started

    def restart(self, roles_in_game : list[Role], players : dict[str,str],
                settings : GameSettings, ruleset : RuleSet | None = None):
        # Build everything first, so a bad setting leaves the old game intact.
        ruleset = ruleset or DEFAULT_RULES
        rules = settings.resolve(len(players), roles_in_game, ruleset)
        builder = AvalonBuilder(list(players.values()), roles_in_game,
                                rules['num_evils'], rules = ruleset)
        self.install(builder, roles_in_game, players, rules)

    @property
    def game_ruleset(self) -> RuleSet:
        return self.ruleset or DEFAULT_RULES

    def install(self, builder : AvalonBuilder, roles_in_game : list[Role],
                players : dict[str,str], rules : dict):
        """Start a game from roles already dealt (restart, or a dev scenario).
        The game's rule settings are the builder's."""
        self.player_info = {}
        self.roles_in_game = roles_in_game
        self.rules = rules
        self.ruleset = builder.rules
        for role in builder:
            self.player_info[next(p for p in players if players[p] == builder[role])] = RoleInfo(role, builder)
        proposers = builder.get_first_mission_proposers()
        proposers.append(builder.get_second_mission_starter())
        self.proposers = proposers
        self.names = dict(players)
        self.host_vote = None
        self.game_number += 1
        self.controller = GameController(GameState.from_builder(
            builder, rules['team_sizes'], rules['double_fail'],
            role_pool = roles_in_game, lady_of_the_lake = rules['lady']))
    def __getitem__(self, uuid : str) -> RoleInfo:
        return self.player_info[uuid]
    def __contains__(self, uuid : str):
        return uuid in self.player_info
    def render_html_info(self, uuid : str):
        player_info = self.player_info[uuid]
        filename = player_info['role'] + '.html'
        return render_template(filename,
                               info = player_info.info,
                               proposers = self.proposers,
                               game_rules = self.rules,
                               ruleset = self.game_ruleset,
                               term_ruleset = self.game_ruleset,
                               image = 'round_table.jpg',
                               num_players = len(self.player_info),
                               panels = self.render_panels(uuid))

    # ---- live game ----

    def render_panels(self, uuid : str | None) -> dict:
        """HTML for the live parts of the page. uuid=None: the host's
        public view (no private information at all)."""
        ctl = self.controller
        name = self.names.get(uuid) if uuid else None
        view = ctl.view(name)
        hv = self.host_vote.view(name) if self.host_vote else None
        ctx = dict(view = view, me = name, game_rules = self.rules,
                   ruleset = self.game_ruleset, host_vote = hv,
                   undo_label = ctl.undo_label() if uuid is None else None)
        if uuid is None:
            return dict(host = render_template('game/host_panel.html', **ctx))
        key, pending = vote_status(view, hv)
        key = f'{self.game_number}:{key}' if key else ''
        return dict(game = render_template('game/panel.html', **ctx),
                    abilities = render_template('game/abilities.html', **ctx),
                    vote = render_template('game/vote.html', vote_key = key,
                                           vote_pending = pending, **ctx))

    # ---- votes the host starts by hand (don't affect the game) ----

    def start_host_vote(self, kind : str, team : list[str]):
        if self.host_vote and self.host_vote.open:
            raise RuleError("End the current vote first.")
        seating = self.controller.state.seating
        team = [p for p in seating if p in team]
        self._host_vote_ids += 1
        if kind == votes.MISSION:
            cards = votes.mission_cards(self.controller.state.possible_roles)
            self.host_vote = HostVote(self._host_vote_ids, kind, team, cards = cards)
        else:
            self.host_vote = HostVote(self._host_vote_ids, kind, seating, team = team)

    def end_host_vote(self, cancel : bool = False):
        if not (self.host_vote and self.host_vote.open):
            raise RuleError("No vote is going on.")
        self.host_vote.close(cancelled = cancel)

    def cast_host_vote(self, uuid : str, vote_id : int, choice : str):
        hv = self.host_vote
        if hv is None or hv.id != vote_id:
            raise RuleError("This vote has ended.")
        hv.cast(self.names[uuid], choice)

    def host_vote_view(self, uuid : str) -> dict | None:
        return self.host_vote.view(self.names[uuid]) if self.host_vote else None

    def act(self, uuid : str, action : str, params : dict):
        self.controller.act(self.names[uuid], action, **params)

    def host_undo(self) -> str:
        return self.controller.undo()

    def host_skip(self):
        self.controller.skip_pause()
    def snapshot(self):
        return dict(self.player_info)
    def roles_dealt(self) -> list[Role]:
        return list(self.controller.state.roles.values()) if self.controller else []

def vote_status(view : dict, host_vote : dict | None) -> tuple[str, bool]:
    """(key, pending) for the player's Vote tab. key names the votes going on
    that this player is part of ('' if none); it changes when a new vote
    starts, which is when the page switches to the Vote tab. pending: this
    player still has to vote in one of them."""
    keys, pending = [], False
    acts = view.get('actions') or {}
    phase = view['phase']
    if phase == 'first_round_voting':
        keys.append('fr')
        pending |= acts.get('vote_first_round', {}).get('current', 0) is None
    elif phase == 'voting':
        prop = view['proposals'][-1]
        keys.append(f"p{prop['round']}.{prop['number']}")
        pending |= acts.get('vote', {}).get('current', 0) is None
    elif phase == 'quest' and view.get('you') \
            and view['you']['name'] in view['current_quest']['team']:
        keys.append(f"q{view['round']}")
        pending |= 'play_card' in acts
    if host_vote and host_vote['involved']:
        keys.append(host_vote['key'])
        pending |= host_vote['pending']
    return ' '.join(keys), pending

class Lobby:
    """An open game: who has joined, and the game being played. Plain data,
    stored in Redis by Lobbies."""
    max_capacity : int = 10
    current_game : AvalonGame
    def __init__(self, host_uuid : str, name : str):
        self.id = secrets.token_urlsafe(6)
        self.host_uuid = host_uuid
        self.name = name
        self._players : dict[str,str] = {}
        self.current_game = AvalonGame()
    def __setitem__(self, uuid : str, name : str):
        if uuid in self._players:
            self._players[uuid] = name
            return
        if name in self._players.values():
            return
        if len(self._players) >= self.max_capacity:
            return
        self._players[uuid] = name
    def get(self, uuid : str, default = None):
        return self._players.get(uuid, default)
    def pop(self, uuid : str):
        self._players.pop(uuid, None)
    def snapshot(self):
        return dict(self._players)
    def __len__(self):
        return len(self._players)
    def __contains__(self, uuid : str):
        return uuid in self._players
    def restart_game(self, roles : list[Role], settings : GameSettings,
                     ruleset : RuleSet | None = None):
        self.current_game.restart(roles, self._players, settings, ruleset)

class Lobbies:
    """All open games, kept in Redis (see store.py). Each host (browser
    session) has at most one. A lobby untouched for 12 hours expires.

    Objects returned by get() and friends are copies: change a lobby with
    update(), which saves the change atomically."""
    max_idle_seconds = 12 * 60 * 60

    def __init__(self, store : Store):
        self.store = store
        self._index = store.key('lobbies')          # set of lobby ids

    def _key(self, lobby_id : str) -> str:
        return self.store.key('lobby', lobby_id)
    def _host_key(self, host_uuid : str) -> str:
        return self.store.key('host', host_uuid)

    def get(self, lobby_id : str | None) -> Lobby | None:
        return self.store.get(self._key(lobby_id)) if lobby_id else None
    def update(self, lobby_id : str, change) -> tuple[Lobby, object]:
        """Run change(lobby) and save. Returns (lobby, change's result);
        KeyError if the lobby is gone."""
        lobby, result = self.store.update(self._key(lobby_id), change,
                                          ttl = self.max_idle_seconds)
        self.store.redis.expire(self._host_key(lobby.host_uuid), self.max_idle_seconds)
        return lobby, result
    def add(self, lobby : Lobby):
        """Save a lobby made elsewhere, replacing any with the same id (dev scenarios)."""
        r = self.store.redis
        self.store.put(self._key(lobby.id), lobby, self.max_idle_seconds)
        r.set(self._host_key(lobby.host_uuid), lobby.id, ex = self.max_idle_seconds)
        r.sadd(self._index, lobby.id)
    def hosted_by(self, host_uuid : str) -> Lobby | None:
        lobby_id = self.store.redis.get(self._host_key(host_uuid))
        return self.get(lobby_id.decode()) if lobby_id else None
    def open(self, host_uuid : str, name : str | None = None) -> tuple[Lobby, bool]:
        """The host's lobby, created if needed. Returns (lobby, created).
        A new lobby is called `name`, or a random unused Avalon name."""
        lobby = self.hosted_by(host_uuid)
        if lobby is not None:
            lobby, _ = self.update(lobby.id, lambda l: None)     # keeps it alive
            return lobby, False
        taken = {l.name for l in self.active()}
        if not name or name in taken:
            name = random_game_name(taken)
        lobby = Lobby(host_uuid, name)
        for i in range(app.config.get('DEV_FAKE_PLAYERS', 0)):
            lobby[f'fake{i}'] = f'p{i}'
        r = self.store.redis
        # Two requests from the same host at once: only one creates the lobby.
        if not r.set(self._host_key(host_uuid), lobby.id, nx = True,
                     ex = self.max_idle_seconds):
            return self.open(host_uuid, name)
        self.store.put(self._key(lobby.id), lobby, self.max_idle_seconds)
        r.sadd(self._index, lobby.id)
        return lobby, True
    def active(self) -> list[Lobby]:
        ids = sorted(i.decode() for i in self.store.redis.smembers(self._index))
        lobbies = self.store.get_many([self._key(i) for i in ids])
        gone = [i for i, l in zip(ids, lobbies) if l is None]
        if gone:
            self.store.redis.srem(self._index, *gone)
        return sorted((l for l in lobbies if l is not None), key=lambda l: l.name.casefold())
    def close(self, lobby_id : str) -> Lobby | None:
        """Remove a lobby now (instead of waiting for it to expire). Returns
        it as it was, or None if it was already gone. A change to it that is
        under way then fails (KeyError), as for an expired lobby."""
        lobby = self.get(lobby_id)
        r = self.store.redis
        r.delete(self._key(lobby_id))
        r.srem(self._index, lobby_id)
        if lobby is not None:
            host_key = self._host_key(lobby.host_uuid)
            current = r.get(host_key)
            if current is not None and current.decode() == lobby_id:
                r.delete(host_key)
        return lobby
    def idle_seconds(self, lobby_ids : list[str]) -> dict[str, int | None]:
        """How long ago each lobby was last changed (from its time to live)."""
        pipe = self.store.redis.pipeline()
        for i in lobby_ids:
            pipe.ttl(self._key(i))
        return {i: (self.max_idle_seconds - ttl if ttl is not None and ttl >= 0 else None)
                for i, ttl in zip(lobby_ids, pipe.execute())}
    def leave_all(self, uuid : str, except_id : str | None = None):
        for lobby in self.active():
            if lobby.id != except_id and uuid in lobby:
                self.update(lobby.id, lambda l: l.pop(uuid))

LOBBIES = Lobbies(Store(store.connect()))

GAME_NAMES = [
    "Camelot", "Tintagel", "Avalon", "Caerleon", "Lyonesse", "Broceliande",
    "Joyous Gard", "Corbenic", "Astolat", "Logres", "Glastonbury",
    "The Round Table", "The Siege Perilous", "The Green Chapel",
    "The Lady of the Lake", "Excalibur", "The Holy Grail", "The Perilous Bed",
]

def random_game_name(taken : set[str]) -> str:
    free = [n for n in GAME_NAMES if n not in taken]
    if free:
        return random.choice(free)
    return f"{random.choice(GAME_NAMES)} {random.randint(2, 99)}"

class RoleInfo:
    info : dict
    def __init__(self, role : Role, game : AvalonBuilder):
        self.info = role.get_info(game)
        self.info['role'] = str(role)
    def __getitem__(self, key : str):
        return self.info[key]
    def __contains__(self, key : str):
        return key in self.info

# ---- host preferences (stored in the host's session) ----

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

def _evils_key(n : int, gareth_plays : bool) -> str:
    return f'{n}+gareth' if gareth_plays else str(n)

def pref_evils(n : int, gareth_plays : bool) -> int:
    return _prefs().get('evils', {}).get(_evils_key(n, gareth_plays),
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
    prefs.setdefault('evils', {})[_evils_key(n, rules_used['gareth'])] = evils
    prefs.setdefault('quests', {})[f'{n}-{evils}'] = dict(
        sizes = rules_used['team_sizes'], double_fail = rules_used['double_fail'] or 0)
    session['host_prefs'] = prefs
    session.modified = True

# ---- the host page's rules editor ----

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

# ---- request setup ----

@app.before_request
def assign_uuid():
    session.permanent = True
    if 'player_id' not in session:
        session['player_id'] = str(uuid_lib.uuid4())
    g.uuid = session['player_id']

REGISTRATION_EXEMPT = ['/register', '/static', '/rules', '/events',
                       '/host', '/restart', '/donotread']

@app.before_request
def require_registration():
    # Hosts don't need a player name; only players do.
    if any(request.path.startswith(p) for p in REGISTRATION_EXEMPT):
        return  # allow through
    if 'name' not in session:
        next_page = request.full_path.rstrip('?') if request.method == 'GET' else None
        return flask.redirect(url_for('register_api', next = next_page))
    g.name = session['name']

def joined_lobby() -> Lobby | None:
    """The game this player has joined (or was last in)."""
    return LOBBIES.get(session.get('game_id'))

def join(lobby : Lobby) -> Lobby:
    """Join (or rename yourself in) a lobby. Returns the lobby as saved."""
    LOBBIES.leave_all(g.uuid, except_id = lobby.id)
    session['game_id'] = lobby.id
    if lobby.get(g.uuid) != g.name:
        uuid, name = g.uuid, g.name
        try:
            lobby, _ = LOBBIES.update(lobby.id, lambda l: l.__setitem__(uuid, name))
        except KeyError:
            return lobby
        new_event('new-player', lobby.id)
    return lobby

# ---- player pages ----

@app.route("/")
def index():
    lobby = joined_lobby()
    if lobby is None:
        active = LOBBIES.active()
        if len(active) == 1:
            lobby = join(active[0])
        else:
            g.channel = LOBBIES_CHANNEL
            return flask.render_template('games.html', name = g.name, lobbies = active)

    g.channel = lobby.id
    if g.uuid not in lobby.current_game:
        return flask.render_template('wait.html',
                                     name = g.name,
                                     lobby = lobby,
                                     in_lobby = g.uuid in lobby,
                                     other_games = len(LOBBIES.active()) > 1)
    return lobby.current_game.render_html_info(g.uuid)

@app.route("/games")
def games():
    g.channel = LOBBIES_CHANNEL
    return flask.render_template('games.html', name = g.name,
                                 lobbies = LOBBIES.active(),
                                 current = joined_lobby())

@app.route("/join-lobby", methods=["GET", "POST"])
@app.route("/join/<lobby_id>", methods=["GET", "POST"])
def join_lobby(lobby_id = None):
    lobby = LOBBIES.get(lobby_id) if lobby_id else joined_lobby()
    if lobby is not None:
        join(lobby)
    return flask.redirect(url_for('index'))

def safe_next(target : str | None) -> str | None:
    if target and target.startswith('/') and not target.startswith('//'):
        return target
    return None

class RegisterView(MethodView):
    def get(self):
        return flask.render_template('registration.html',
                                     next = safe_next(request.args.get('next')))
    def post(self):
        player_name = request.form['player'].strip()
        if len(player_name) == 0:
            return flask.redirect(url_for('register_api'))
        session['name'] = player_name
        g.name = player_name
        lobby = joined_lobby()
        if lobby is not None and g.uuid in lobby:
            join(lobby)  # update name in the lobby
        return flask.redirect(safe_next(request.form.get('next')) or url_for('index'))

app.add_url_rule('/register', view_func=RegisterView.as_view('register_api'))

# ---- host pages ----

def render_host(lobby : Lobby, error = None, form = None, rename_error = None,
                saved = False):
    players = lobby.snapshot()
    n = len(players)
    ruleset = pref_ruleset()
    if form is not None:
        try:
            ruleset = form_ruleset(form)
        except ValueError:
            pass
    ctx = dict(lobby = lobby,
               players = players,
               groups = HOST_GROUPS,
               assassination_keys = ASSASSINATION_KEYS,
               settings = SETTINGS,
               ruleset = ruleset,
               saved = saved,
               rule_defaults = {k: s.to_json(s.default) for k, s in SETTINGS.items()},
               gareth_possible = gareth.can_appear(n, ruleset),
               game_rules = lobby.current_game.rules,
               current_ruleset = lobby.current_game.game_ruleset,
               term_ruleset = (lobby.current_game.game_ruleset
                               if lobby.current_game.controller is not None else None),
               error = error,
               rename_error = rename_error,
               num_players = n,
               valid_count = n in DEFAULT_TEAM_SIZES)
    if form is not None:  # re-show what the host just submitted
        ctx['active_roles'] = form.getlist('items')
        ctx['lady'] = form.get('lady') == '1'
    else:
        ctx['active_roles'] = pref_roles()
        ctx['lady'] = pref_lady()
    if ctx['valid_count']:
        gareth_plays = gareth.can_appear(n, ruleset) and str(gareth) in ctx['active_roles']
        evil_options = list(range(1, min(5, n - 1 - gareth_plays) + 1))
        quests = {e: pref_quests(n, e) for e in range(1, 6)}
        evils = pref_evils(n, gareth_plays)
        shown = quests.get(evils, default_quests(n))
        if form is not None:
            evils = form.get('evils', type=int, default=evils)
            shown = dict(sizes = [form.get(f'size{i}', '') for i in range(1, 6)],
                         double_fail = form.get('double_fail', type=int, default=0))
        ctx.update(evil_options = evil_options,
                   evils = evils,
                   shown = shown,
                   quest_prefs = quests,
                   gareth_plays = gareth_plays,
                   # Evil count to switch to when Gareth is toggled.
                   gareth_evils = {'on': pref_evils(n, True), 'off': pref_evils(n, False)},
                   defaults = dict(evils = default_num_evils(n, gareth_plays),
                                   evils_with_gareth = default_num_evils(n, True),
                                   evils_without_gareth = default_num_evils(n, False),
                                   **default_quests(n)))
    if lobby.current_game.controller is not None:
        ctx['host_panel'] = lobby.current_game.render_panels(None)['host']
    g.channel = lobby.id
    return flask.render_template('host.html', **ctx)

def my_lobby() -> Lobby | None:
    """The lobby this host has open (kept alive by looking at it), or None."""
    lobby = LOBBIES.hosted_by(g.uuid)
    if lobby is None or g.get('view_as'):     # an admin looking doesn't keep it alive
        return lobby
    try:
        lobby, _ = LOBBIES.update(lobby.id, lambda l: None)
    except KeyError:                    # closed just now
        return None
    return lobby

def render_create(error = None, name = None):
    """The host has no lobby: offer to open one, with a free name filled in."""
    taken = {l.name for l in LOBBIES.active()}
    if name is None:
        name = session.get('game_name')
        if not name or name in taken:
            name = random_game_name(taken)
    return flask.render_template('host_create.html', name = name, error = error)

class LobbyView(MethodView):
    def get(self):
        lobby = my_lobby()
        if lobby is None:
            return render_create()
        return render_host(lobby)
    def post(self):
        lobby = my_lobby()
        if lobby is None:
            return flask.redirect(url_for('lobby_api'))
        if 'player' in request.form:
            player = request.form['player']
            lobby, _ = LOBBIES.update(lobby.id, lambda l: l.pop(player))
        new_name = request.form.get('game_name', '').strip()[:40]
        if new_name and new_name != lobby.name:
            if any(l.name == new_name for l in LOBBIES.active()):
                return render_host(lobby, rename_error = f'"{new_name}" is already taken.'), 400
            LOBBIES.update(lobby.id, lambda l: setattr(l, 'name', new_name))
            session['game_name'] = new_name
            new_event('new-lobby', LOBBIES_CHANNEL)
        return flask.redirect(url_for('lobby_api'))

app.add_url_rule('/host', view_func=LobbyView.as_view('lobby_api'))

@app.route("/host/create", methods=["POST"])
def host_create():
    name = request.form.get('game_name', '').strip()[:40]
    if my_lobby() is None:
        if not name:
            return render_create(error = "Give the game a name.", name = ''), 400
        if any(l.name == name for l in LOBBIES.active()):
            return render_create(error = f'"{name}" is already taken.', name = name), 400
        lobby, created = LOBBIES.open(g.uuid, name)
        session['game_name'] = lobby.name
        if created:
            new_event('new-lobby', LOBBIES_CHANNEL)
    return flask.redirect(url_for('lobby_api'))

def close_lobby(lobby_id : str) -> Lobby | None:
    """Close a lobby now and tell open pages: players' pages reload (and find
    the game gone), game lists and host pages refresh."""
    lobby = LOBBIES.close(lobby_id)
    if lobby is not None:
        new_event('new-game', lobby.id)
        new_event('new-player', lobby.id)
        new_event('new-lobby', LOBBIES_CHANNEL)
    return lobby

@app.route("/host/close", methods=["POST"])
def host_close():
    lobby = LOBBIES.hosted_by(g.uuid)
    if lobby is not None:
        close_lobby(lobby.id)
    return flask.redirect(url_for('lobby_api'))

@app.route("/restart", methods=["POST"])
def restart():
    lobby = my_lobby()
    if lobby is None:
        return flask.redirect(url_for('lobby_api'))
    role_names = request.form.getlist('items')
    try:
        settings = GameSettings.from_form(request.form)
        ruleset = form_ruleset(request.form)
        roles = ordered_roles(role_names)
        lobby, _ = LOBBIES.update(lobby.id,
                                  lambda l: l.restart_game(roles, settings, ruleset))
    except ValueError as e:
        return render_host(lobby, error = str(e), form = request.form), 400
    save_prefs(role_names, lobby.current_game.rules)
    save_pref_ruleset(ruleset)
    new_event('new-game', lobby.id)
    return flask.redirect(url_for('lobby_api'))

@app.route("/host/save", methods=["POST"])
def host_save():
    """Remember the roles and rules without starting a game."""
    lobby = my_lobby()
    if lobby is None:
        return flask.redirect(url_for('lobby_api'))
    try:
        ruleset = form_ruleset(request.form)
    except ValueError as e:
        return render_host(lobby, error = str(e), form = request.form), 400
    prefs = _prefs()
    prefs['roles'] = request.form.getlist('items')
    prefs['gareth_offered'] = True
    prefs['lady'] = request.form.get('lady') == '1'
    session['host_prefs'] = prefs
    save_pref_ruleset(ruleset)
    return render_host(lobby, saved = True)

# ---- live game ----

def action_params(action : str, form) -> dict:
    """Form fields -> GameController.act() parameters."""
    params = {}
    if action in ('propose', 'propose_first_round'):
        params['team'] = form.getlist('team')
    if action == 'assassinate':
        params['targets'] = form.getlist('targets')
    for key in ('proposer', 'next_proposer', 'replaced', 'card', 'kind'):
        if key in form:
            params[key] = form[key]
    if 'target' in form:
        params['target'] = form['target'] or None
    for key in ('approve', 'remove'):
        if key in form:
            params[key] = form[key] == '1'
    return params

def current_game_for_player():
    lobby = joined_lobby()
    if lobby is None or g.uuid not in lobby.current_game \
            or lobby.current_game.controller is None:
        flask.abort(404)
    return lobby

@app.route("/game/panels")
def game_panels():
    lobby = current_game_for_player()
    return flask.jsonify(lobby.current_game.render_panels(g.uuid))

@app.route("/game/state")
def game_state():
    """This player's view of the game as JSON (what their page shows)."""
    lobby = current_game_for_player()
    game = lobby.current_game
    view = game.controller.view(game.names[g.uuid])
    host_vote = game.host_vote_view(g.uuid)
    return flask.jsonify(game_id = f'{lobby.id}:{game.game_number}',
                         host_vote = host_vote, **view)

@app.route("/game/action", methods=["POST"])
def game_action():
    lobby = current_game_for_player()
    action = request.form.get('action', '')
    params = action_params(action, request.form)
    uuid = g.uuid
    try:
        lobby, _ = LOBBIES.update(lobby.id, lambda l: l.current_game.act(uuid, action, params))
    except (RuleError, KeyError, ValueError, Conflict) as e:
        message = e.args[0] if isinstance(e, RuleError) else "That didn't work, try again."
        return flask.jsonify(error = message), 400
    new_event('game-update', lobby.id)
    return flask.jsonify(lobby.current_game.render_panels(g.uuid))

@app.route("/game/host-vote", methods=["POST"])
def game_host_vote():
    """A player votes in the vote the host started."""
    lobby = current_game_for_player()
    uuid, vote_id = g.uuid, request.form.get('vote', type=int)
    choice = request.form.get('choice', '')
    try:
        lobby, _ = LOBBIES.update(
            lobby.id, lambda l: l.current_game.cast_host_vote(uuid, vote_id, choice))
    except (RuleError, KeyError, Conflict) as e:
        message = e.args[0] if isinstance(e, RuleError) else "That didn't work, try again."
        return flask.jsonify(error = message), 400
    new_event('game-update', lobby.id)
    return flask.jsonify(lobby.current_game.render_panels(g.uuid))

def hosted_game():
    lobby = LOBBIES.hosted_by(g.uuid)
    if lobby is None or lobby.current_game.controller is None:
        flask.abort(404)
    return lobby

@app.route("/host/game/panels")
def host_game_panels():
    return flask.jsonify(hosted_game().current_game.render_panels(None))

@app.route("/host/game/<command>", methods=["POST"])
def host_game_command(command):
    lobby = hosted_game()
    kind, team = request.form.get('kind', ''), request.form.getlist('team')
    commands = {
        'undo': lambda game: game.host_undo(),
        'skip': lambda game: game.host_skip(),
        'vote-start': lambda game: game.start_host_vote(kind, team),
        'vote-end': lambda game: game.end_host_vote(),
        'vote-cancel': lambda game: game.end_host_vote(cancel = True),
    }
    if command not in commands:
        flask.abort(404)
    try:
        lobby, _ = LOBBIES.update(lobby.id, lambda l: commands[command](l.current_game))
    except (RuleError, KeyError, Conflict) as e:
        message = e.args[0] if isinstance(e, RuleError) else "That didn't work, try again."
        return flask.jsonify(error = message), 400
    new_event('game-update', lobby.id)
    return flask.jsonify(lobby.current_game.render_panels(None))

@app.route("/rules/")
@app.route("/rules/<slug>")
def rules_page(slug = "overview"):
    if slug not in rules.PAGES:
        flask.abort(404)
    lobby = viewer_game()
    return flask.render_template('rules/page.html',
                                 page = rules.BY_SLUG[slug],
                                 terms = rules.TERMS,
                                 game_lobby = lobby,
                                 ruleset = lobby.current_game.game_ruleset if lobby else None,
                                 term_ruleset = lobby.current_game.game_ruleset if lobby else None)

def viewer_game() -> Lobby | None:
    """The game this browser is playing in or hosting right now, if any."""
    lobby = LOBBIES.hosted_by(g.uuid)
    if lobby is not None and lobby.current_game.controller is not None:
        return lobby
    lobby = joined_lobby()
    if lobby is not None and g.uuid in lobby.current_game \
            and lobby.current_game.controller is not None:
        return lobby
    return None

@app.route("/donotread")
def all_info():
    lobby = LOBBIES.hosted_by(g.uuid) or joined_lobby()
    if lobby is None:
        return flask.redirect(url_for('index'))
    current_game = lobby.current_game.snapshot()
    gareth_team = next((r.allegiance() for r in lobby.current_game.roles_dealt()
                        if str(r) == 'Gareth'), None)
    return flask.render_template('donotread.html', 
                                 game = current_game,
                                 gareth_team = gareth_team,
                                 names = lobby.snapshot(),
                                 num_players = len(current_game))

# Test scenarios, only on the dev site (AVALON_DEV=1). See dev.py.
import dev
if dev.enabled():
    dev.init_app(app, sys.modules[__name__])

# Admin pages (/admin), behind Cloudflare Access. See admin.py.
import admin
admin.init_app(app, sys.modules[__name__])

if __name__ == "__main__":
    # Development server only: every new lobby starts with 9 fake players.
    app.config['DEV_FAKE_PLAYERS'] = 9
    # Local dev scenarios skip the Cloudflare Access login check.
    app.config['DEV_NO_AUTH'] = True
    # And the admin pages too.
    app.config['ADMIN_NO_AUTH'] = True
    app.run(host="0.0.0.0", port=5000, debug=True)
