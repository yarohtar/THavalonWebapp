import flask
from flask import Flask, render_template, request, session, url_for, g
from flask_sse import sse
import threading
from THavalon import AvalonBuilder, Role, convert_strings_to_roles, all_roles
import os
from dotenv import load_dotenv
load_dotenv()
from flask.views import MethodView
import rules

app = Flask(__name__)
app.secret_key = "secret"
rules.init_app(app)

# auto refresh enabled by default
auto_refresh ='DISABLE_AUTO_REFRESH' not in os.environ

if auto_refresh:
    app.config["REDIS_URL"] = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    app.register_blueprint(sse, url_prefix='/events')

def new_event(event_name, data = None):
    if auto_refresh and 'game_id' in session:
        sse.publish(data, type=event_name, channel = session['game_id'])

@app.context_processor
def inject_events_url():
    if not auto_refresh or 'game_id' not in session:
        return dict(auto_refresh = False)
    return dict(auto_refresh = True, 
                events_url = url_for('sse.stream', channel = session['game_id']))

class AvalonGame:
    player_info : dict[str, RoleInfo]
    roles_in_game : list[Role]
    proposers : list[str]
    def __init__(self):
        self._lock = threading.Lock()
        self.roles_in_game = all_roles[:]
        self.player_info = {}
    def restart(self, roles_in_game : list[Role], players : dict[str,str]):
        with self._lock:
            self.player_info = {}
            self.roles_in_game = roles_in_game
            player_names = list(players.values())
            builder = AvalonBuilder(player_names, self.roles_in_game)
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
                                   image = 'round_table.jpg',
                                   num_players = len(self.player_info))
    def snapshot(self):
        with self._lock:
            return dict(self.player_info)

class Lobby:
    max_capacity : int = 10
    current_game : AvalonGame
    def __init__(self):
        self._players : dict[str,str] = {}
        self._roles : list[Role] = []
        self._lock = threading.Lock()
        self.current_game = AvalonGame()
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
            self._players.pop(uuid)

    def remove(self, uuid : str):
        with self._lock:
            self._players.pop(uuid)

    def snapshot(self):
        with self._lock:
            return dict(self._players)
    def __contains__(self, uuid : str):
        with self._lock:
            return uuid in self._players
    def set_roles(self, roles : list[str]):
        with self._lock:
            self._roles = convert_strings_to_roles(roles)
    def get_roles(self):
        with self._lock:
            return self._roles[:]
    def restart_game(self):
        with self._lock:
            self.current_game.restart(self._roles, self._players)

class RoleInfo:
    info : dict
    def __init__(self, role : Role, game : AvalonBuilder):
        self.info = role.get_info(game)
        self.info['role'] = str(role)
    def __getitem__(self, key : str):
        return self.info[key]
    def __contains__(self, key : str):
        return key in self.info

def get_lobby(lobby = Lobby()):
    return lobby

@app.before_request
def set_lobby():
    session['game_id'] = '1'
    g.lobby = get_lobby()

@app.before_request
def assign_uuid():
    import uuid
    session.permanent = True
    if 'player_id' not in session:
        session['player_id'] = str(uuid.uuid4())
    g.uuid = session['player_id']

@app.before_request
def require_registration():
    allowed_paths = ['/host', '/register', '/static', '/rules']
    if any(request.path.startswith(p) for p in allowed_paths):
        return  # allow through
    if 'name' not in session:
        return flask.redirect(url_for('register_api'))
    g.name = session['name']

@app.route("/join-lobby", methods=["GET", "POST"])
def join_lobby():
    if g.lobby.get(g.uuid, "") != g.name:
        g.lobby[g.uuid] = g.name
        new_event('new-player')
    return flask.redirect(url_for('index'))


@app.route("/")
def index():
    if g.uuid not in g.lobby.current_game:
        return flask.render_template('wait.html', 
                                     name = g.name,
                                     in_lobby = g.uuid in g.lobby)

    return g.lobby.current_game.render_html_info(g.uuid)

class RegisterView(MethodView):
    def get(self):
        return flask.render_template('registration.html')
    def post(self):
        player_name = request.form['player'].strip()
        if len(player_name) == 0:
            return flask.redirect(url_for('register_api'))
        session['name'] = player_name
        return flask.redirect(url_for('join_lobby'))

app.add_url_rule('/register', view_func=RegisterView.as_view('register_api'))

class LobbyView(MethodView):
    def get(self):
        return flask.render_template('host.html', 
                                     players = g.lobby.snapshot(),
                                     current_roles = g.lobby.get_roles(),
                                     all_roles = all_roles)
    def post(self):
        player = request.form['player']
        g.lobby.pop(player)
        return flask.redirect(url_for('lobby_api'))

app.add_url_rule('/host', view_func=LobbyView.as_view('lobby_api'))

@app.route("/restart", methods=["POST"])
def restart():
    roles = request.form.getlist('items')
    g.lobby.set_roles(roles)
    g.lobby.restart_game()
    new_event('new-game')
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
    current_game = g.lobby.current_game.snapshot()
    return flask.render_template('donotread.html', 
                                 game = current_game,
                                 names = g.lobby.snapshot(),
                                 num_players = len(current_game))

if __name__ == "__main__":
    # Development server only
    lobby = get_lobby()
    for i in range(9):
        lobby[f'p{i}'] = f'p{i}'
    app.run(host="0.0.0.0", port=5000, debug=True)




