import flask
from flask import Flask, Response, render_template, request, session, url_for
from flask_sse import sse
import threading
from THavalon import Avalon, Role
import queue
from dotenv import load_dotenv
load_dotenv()

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
    def __init__(self, role : Role, game : Avalon):
        self.info = role.get_info(game)
        self.info['role'] = str(role)
    def __getitem__(self, key : str):
        return self.info[key]

class ThreadSafeGame:
    active : bool = False
    player_info : dict[str, RoleInfo] = {}
    proposers : list[str] = []
    def __init__(self):
        self._lock = threading.Lock()
    def restart(self):
        with self._lock:
            self.active = True
            self.player_info = {}
            new_game = Avalon(players.snapshot())
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


game = ThreadSafeGame()
app = Flask(__name__)
app.secret_key = "secret"

app.config["REDIS_URL"] = "redis://localhost:6379/0"
app.register_blueprint(sse, url_prefix='/events')

@app.route("/")
def index():
    player = session.get('name', "")
    if player == "":
        return render_template("registration.html")
    if player not in players:
        return render_template("registration.html")
    if player not in game or not game.is_active():
        return flask.render_template('wait.html', 
                                     message="Wait for host to start the game, then refresh.")

    return game.render_html_info(player)

@app.route("/register", methods=["POST"])
def register():
    player = request.form["player"]
    if players.append(player):
        session['name'] = player.strip()
        sse.publish(True, type='new-player')
    return flask.redirect(url_for('index'))

@app.route("/restart", methods=["POST"])
def restart():
    game.restart()
    sse.publish(True, type= 'new-game')
    return flask.redirect(url_for('host'))

@app.route("/delete_player", methods=["POST"])
def delete_player():
    player = request.form["player"]
    players.remove(player)
    return flask.redirect(url_for('host'))


@app.route("/host")
def host():
    return flask.render_template('host.html', players = players.snapshot())



if __name__ == "__main__":
    # Development server only
    for i in range(9):
        players.append(f"p{i}")
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
