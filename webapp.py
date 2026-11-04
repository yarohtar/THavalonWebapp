import flask
from flask import Flask, render_template, request, session, url_for, g
import random
import secrets
import threading
import time
import uuid as uuid_lib
from THavalon import (AvalonBuilder, Role, convert_strings_to_roles, all_roles,
                      balin, pellinore, beast,
                      default_num_evils, DEFAULT_TEAM_SIZES, default_double_fail_quest)
import os
from dotenv import load_dotenv
load_dotenv()
from flask.views import MethodView
import rules
import events

app = Flask(__name__)
app.secret_key = "secret"
rules.init_app(app)

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
        return settings

    def resolve(self, num_players : int) -> dict:
        """The rules actually in effect for a game of this size."""
        n = num_players
        if n not in DEFAULT_TEAM_SIZES:
            raise ValueError("A game needs 5 to 10 players.")
        evils = self.num_evils if self.num_evils is not None else default_num_evils(n)
        sizes = self.team_sizes or DEFAULT_TEAM_SIZES[n]
        if any(not 2 <= k <= n for k in sizes):
            raise ValueError(f"Team sizes must be between 2 and {n} for {n} players.")
        double_fail = (self.double_fail if self.double_fail is not None
                       else default_double_fail_quest(n))
        proposals = evils + 1
        return dict(num_players = n,
                    num_evils = evils,
                    num_others = n - evils,
                    team_sizes = sizes,
                    double_fail = double_fail or None,
                    proposals = proposals,
                    inquisition = ('none' if proposals <= 3
                                   else 'weak' if proposals == 4
                                   else 'strong'))

class AvalonGame:
    player_info : dict[str, RoleInfo]
    roles_in_game : list[Role]
    proposers : list[str]
    def __init__(self):
        self._lock = threading.Lock()
        self.roles_in_game = all_roles[:]
        self.player_info = {}
    rules : dict | None = None
    def restart(self, roles_in_game : list[Role], players : dict[str,str],
                settings : GameSettings):
        # Build everything first, so a bad setting leaves the old game intact.
        rules = settings.resolve(len(players))
        builder = AvalonBuilder(list(players.values()), roles_in_game,
                                rules['num_evils'])
        with self._lock:
            self.player_info = {}
            self.roles_in_game = roles_in_game
            self.rules = rules
            for role in builder:
                self.player_info[next(p for p in players if players[p] == builder[role])] = RoleInfo(role, builder)
            proposers = builder.get_first_mission_proposers()
            proposers.append(builder.get_second_mission_starter())
            self.proposers = proposers
    def __getitem__(self, uuid : str) -> RoleInfo:
        with self._lock:
            return self.player_info[uuid]
    def __contains__(self, uuid : str):
        with self._lock:
            return uuid in self.player_info
    def render_html_info(self, uuid : str):
        with self._lock:
            player_info = self.player_info[uuid]
            filename = player_info['role'] + '.html'
            return render_template(filename, 
                                   info = player_info.info,
                                   proposers = self.proposers,
                                   game_rules = self.rules,
                                   image = 'round_table.jpg',
                                   num_players = len(self.player_info))
    def snapshot(self):
        with self._lock:
            return dict(self.player_info)

class Lobby:
    max_capacity : int = 10
    current_game : AvalonGame
    def __init__(self, host_uuid : str, name : str):
        self.id = secrets.token_urlsafe(6)
        self.host_uuid = host_uuid
        self.name = name
        self.last_active = time.time()
        self._players : dict[str,str] = {}
        self._lock = threading.Lock()
        self.current_game = AvalonGame()
    def touch(self):
        self.last_active = time.time()
    def __setitem__(self, uuid : str, name : str):
        with self._lock:
            if uuid in self._players:
                self._players[uuid] = name
                return 
            if name in self._players.values():
                return
            if len(self._players) >= self.max_capacity:
                return
            self._players[uuid] = name
    def get(self, uuid : str, default = None):
        with self._lock:
            return self._players.get(uuid, default)
    def pop(self, uuid : str):
        with self._lock:
            self._players.pop(uuid, None)
    def snapshot(self):
        with self._lock:
            return dict(self._players)
    def __len__(self):
        with self._lock:
            return len(self._players)
    def __contains__(self, uuid : str):
        with self._lock:
            return uuid in self._players
    def restart_game(self, roles : list[Role], settings : GameSettings):
        with self._lock:
            self.current_game.restart(roles, self._players, settings)
        self.touch()

class Lobbies:
    """All open games. Each host (browser session) has at most one."""
    max_idle_seconds = 12 * 60 * 60

    def __init__(self):
        self._lock = threading.Lock()
        self._by_id : dict[str, Lobby] = {}
    def _prune(self):
        cutoff = time.time() - self.max_idle_seconds
        for lobby_id in [i for i, l in self._by_id.items() if l.last_active < cutoff]:
            del self._by_id[lobby_id]
        events.bus.prune(self.max_idle_seconds)
    def get(self, lobby_id : str | None) -> Lobby | None:
        with self._lock:
            self._prune()
            return self._by_id.get(lobby_id) if lobby_id else None
    def hosted_by(self, host_uuid : str) -> Lobby | None:
        with self._lock:
            self._prune()
            return next((l for l in self._by_id.values() if l.host_uuid == host_uuid), None)
    def open(self, host_uuid : str, name : str | None = None) -> tuple[Lobby, bool]:
        """The host's lobby, created if needed. Returns (lobby, created).
        A new lobby is called `name`, or a random unused Avalon name."""
        with self._lock:
            self._prune()
            lobby = next((l for l in self._by_id.values() if l.host_uuid == host_uuid), None)
            if lobby is not None:
                lobby.touch()
                return lobby, False
            taken = {l.name for l in self._by_id.values()}
            if not name or name in taken:
                name = random_game_name(taken)
            lobby = Lobby(host_uuid, name)
            self._by_id[lobby.id] = lobby
        for i in range(app.config.get('DEV_FAKE_PLAYERS', 0)):
            lobby[f'fake{i}'] = f'p{i}'
        return lobby, True
    def active(self) -> list[Lobby]:
        with self._lock:
            self._prune()
            return sorted(self._by_id.values(), key=lambda l: l.name.casefold())
    def leave_all(self, uuid : str, except_id : str | None = None):
        for lobby in self.active():
            if lobby.id != except_id:
                lobby.pop(uuid)

LOBBIES = Lobbies()

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
    return _prefs().get('roles', DEFAULT_ROLE_NAMES)

def default_quests(n : int) -> dict:
    return dict(sizes = DEFAULT_TEAM_SIZES[n],
                double_fail = default_double_fail_quest(n) or 0)

def pref_evils(n : int) -> int:
    return _prefs().get('evils', {}).get(str(n), default_num_evils(n))

def pref_quests(n : int, evils : int) -> dict:
    return _prefs().get('quests', {}).get(f'{n}-{evils}') or default_quests(n)

def save_prefs(roles : list[str], rules_used : dict):
    n, evils = rules_used['num_players'], rules_used['num_evils']
    prefs = _prefs()
    prefs['roles'] = roles
    prefs.setdefault('evils', {})[str(n)] = evils
    prefs.setdefault('quests', {})[f'{n}-{evils}'] = dict(
        sizes = rules_used['team_sizes'], double_fail = rules_used['double_fail'] or 0)
    session['host_prefs'] = prefs
    session.modified = True

# ---- request setup ----

@app.before_request
def assign_uuid():
    session.permanent = True
    if 'player_id' not in session:
        session['player_id'] = str(uuid_lib.uuid4())
    g.uuid = session['player_id']

@app.before_request
def require_registration():
    # Hosts don't need a player name; only players do.
    allowed_paths = ['/register', '/static', '/rules', '/events',
                     '/host', '/restart', '/donotread']
    if any(request.path.startswith(p) for p in allowed_paths):
        return  # allow through
    if 'name' not in session:
        next_page = request.full_path.rstrip('?') if request.method == 'GET' else None
        return flask.redirect(url_for('register_api', next = next_page))
    g.name = session['name']

def joined_lobby() -> Lobby | None:
    """The game this player has joined (or was last in)."""
    return LOBBIES.get(session.get('game_id'))

def join(lobby : Lobby):
    LOBBIES.leave_all(g.uuid, except_id = lobby.id)
    session['game_id'] = lobby.id
    if lobby.get(g.uuid) != g.name:
        lobby[g.uuid] = g.name
        lobby.touch()
        new_event('new-player', lobby.id)

# ---- player pages ----

@app.route("/")
def index():
    lobby = joined_lobby()
    if lobby is None:
        active = LOBBIES.active()
        if len(active) == 1:
            join(active[0])
            lobby = active[0]
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

def render_host(lobby : Lobby, error = None, form = None, rename_error = None):
    players = lobby.snapshot()
    n = len(players)
    ctx = dict(lobby = lobby,
               players = players,
               all_roles = all_roles,
               game_rules = lobby.current_game.rules,
               error = error,
               rename_error = rename_error,
               num_players = n,
               valid_count = n in DEFAULT_TEAM_SIZES)
    if form is not None:  # re-show what the host just submitted
        ctx['active_roles'] = form.getlist('items')
    else:
        ctx['active_roles'] = pref_roles()
    if ctx['valid_count']:
        evil_options = list(range(1, min(5, n - 1) + 1))
        quests = {e: pref_quests(n, e) for e in evil_options}
        evils = pref_evils(n)
        shown = quests.get(evils, default_quests(n))
        if form is not None:
            evils = form.get('evils', type=int, default=evils)
            shown = dict(sizes = [form.get(f'size{i}', '') for i in range(1, 6)],
                         double_fail = form.get('double_fail', type=int, default=0))
        ctx.update(evil_options = evil_options,
                   evils = evils,
                   shown = shown,
                   quest_prefs = quests,
                   defaults = dict(evils = default_num_evils(n), **default_quests(n)))
    g.channel = lobby.id
    return flask.render_template('host.html', **ctx)

class LobbyView(MethodView):
    def get(self):
        lobby, created = LOBBIES.open(g.uuid, session.get('game_name'))
        if created:
            new_event('new-lobby', LOBBIES_CHANNEL)
        return render_host(lobby)
    def post(self):
        lobby, _ = LOBBIES.open(g.uuid, session.get('game_name'))
        if 'player' in request.form:
            lobby.pop(request.form['player'])
        new_name = request.form.get('game_name', '').strip()[:40]
        if new_name and new_name != lobby.name:
            if any(l.name == new_name for l in LOBBIES.active()):
                return render_host(lobby, rename_error = f'"{new_name}" is already taken.'), 400
            lobby.name = new_name
            session['game_name'] = new_name
            new_event('new-lobby', LOBBIES_CHANNEL)
        return flask.redirect(url_for('lobby_api'))

app.add_url_rule('/host', view_func=LobbyView.as_view('lobby_api'))

@app.route("/restart", methods=["POST"])
def restart():
    lobby, _ = LOBBIES.open(g.uuid, session.get('game_name'))
    role_names = request.form.getlist('items')
    try:
        settings = GameSettings.from_form(request.form)
        lobby.restart_game(convert_strings_to_roles(role_names), settings)
    except ValueError as e:
        return render_host(lobby, error = str(e), form = request.form), 400
    save_prefs(role_names, lobby.current_game.rules)
    new_event('new-game', lobby.id)
    return flask.redirect(url_for('lobby_api'))

@app.route("/rules/")
@app.route("/rules/<slug>")
def rules_page(slug = "overview"):
    if slug not in rules.PAGES:
        flask.abort(404)
    return flask.render_template('rules/page.html',
                                 page = rules.BY_SLUG[slug],
                                 terms = rules.TERMS)

@app.route("/donotread")
def all_info():
    lobby = LOBBIES.hosted_by(g.uuid) or joined_lobby()
    if lobby is None:
        return flask.redirect(url_for('index'))
    current_game = lobby.current_game.snapshot()
    return flask.render_template('donotread.html', 
                                 game = current_game,
                                 names = lobby.snapshot(),
                                 num_players = len(current_game))

if __name__ == "__main__":
    # Development server only: every new lobby starts with 9 fake players.
    app.config['DEV_FAKE_PLAYERS'] = 9
    app.run(host="0.0.0.0", port=5000, debug=True)
