import flask
from flask import Flask, render_template, request, session, url_for, g
from flask_sse import sse
import threading
from THavalon import AvalonBuilder, Role, convert_strings_to_roles, all_roles
import os
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = "secret"

# auto refresh enabled by default
auto_refresh ='DISABLE_AUTO_REFRESH' not in os.environ

if auto_refresh:
    app.config["REDIS_URL"] = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    app.register_blueprint(sse, url_prefix='/events')

def new_event(event_name, data = None):
    if auto_refresh:
        sse.publish(data, type=event_name, channel = session['game_id'])

@app.context_processor
def inject_events_url():
    if not auto_refresh:
        return dict(auto_refresh = False)
    return dict(auto_refresh = True, 
                events_url = url_for('sse.stream', channel = session['game_id']))

class ThreadSafeList:
    max_capacity : int
    def __init__(self, max_capacity):
        self._data = []
        self._lock = threading.Lock()
        self.max_capacity=max_capacity

    def append(self, item):
        with self._lock:
            if item in self._data:
                return True
            if len(self._data) < self.max_capacity:
                self._data.append(item)
                return True
            return False

    def remove(self, item):
        with self._lock:
            self._data.remove(item)

    def snapshot(self):
        with self._lock:
            return list(self._data)

    def __contains__(self, player : str):
        return player in self.snapshot()

players = ThreadSafeList(10)

class RoleInfo:
    info : dict
    def __init__(self, role : Role, game : AvalonBuilder):
        self.info = role.get_info(game)
        self.info['role'] = str(role)
    def __getitem__(self, key : str):
        return self.info[key]
    def __contains__(self, key : str):
        return key in self.info

class ThreadSafeGame:
    active : bool = False
    player_info : dict[str, RoleInfo] = {}
    roles_in_game : list[Role]
    proposers : list[str] = []

    def __init__(self):
        self._lock = threading.Lock()
        self.roles_in_game = all_roles[:]
    def restart(self, roles_in_game : list[str]):
        with self._lock:
            self.active = True
            self.player_info = {}
            self.roles_in_game = convert_strings_to_roles(roles_in_game)
            new_game = AvalonBuilder(players.snapshot(), self.roles_in_game)
            for role in new_game:
                self.player_info[new_game[role]] = RoleInfo(role, new_game)
            proposers = new_game.get_first_mission_proposers()
            proposers.append(new_game.get_second_mission_starter())
            self.proposers = proposers
    def is_active(self):
        with self._lock:
            return self.active
    def __getitem__(self, player : str) -> RoleInfo:
        with self._lock:
            return self.player_info[player]
    def __contains__(self, player : str):
        with self._lock:
            return player in self.player_info
    def render_html_info(self, player : str):
        with self._lock:
            player_info = self.player_info[player]
            filename = player_info['role'] + '.html'
            return render_template(filename, 
                                   info = player_info.info,
                                   proposers = self.proposers,
                                   image = 'round_table.jpg',
                                   num_players = len(self.player_info))
    def snapshot(self):
        with self._lock:
            return dict(self.player_info)
    def get_current_roles(self):
        with self._lock:
            return self.roles_in_game[:]



game = ThreadSafeGame()


@app.route("/")
def index():
    import uuid
    session.permanent = True
    if 'player_id' not in session:
        session['player_id'] = str(uuid.uuid4())
    if 'name' not in session:
        return render_template("registration.html")
    player = session['name']

    if player not in game or not game.is_active():
        return flask.render_template('wait.html', 
                                     message="Wait for host to start the game, then refresh.")

    return game.render_html_info(player)

@app.route("/register", methods=["POST"])
def register():
    player = request.form["player"]
    if players.append(player):
        session['name'] = player.strip()
        session['game_id'] = "1"
        new_event('new-player')
    return flask.redirect(url_for('index'))

@app.route("/restart", methods=["POST"])
def restart():
    roles = request.form.getlist('items')
    game.restart(roles)
    new_event('new-game')
    return flask.redirect(url_for('host'))

@app.route("/delete_player", methods=["POST"])
def delete_player():
    player = request.form["player"]
    players.remove(player)
    return flask.redirect(url_for('host'))

@app.route("/host")
def host():
    return flask.render_template('host.html', 
                                 players = players.snapshot(),
                                 current_roles = game.get_current_roles(),
                                 all_roles = all_roles)

@app.route("/donotread")
def all_info():
    if game.is_active():
        current_game = game.snapshot()
        return flask.render_template('donotread.html', 
                                     game = current_game,
                                     num_players = len(current_game))
    else:
        return flask.redirect(url_for('host'))




if __name__ == "__main__":
    # Development server only
    for i in range(9):
        players.append(f"p{i}")
    app.run(host="0.0.0.0", port=5000, debug=True)
