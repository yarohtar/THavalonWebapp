import flask
from flask import Flask, Response, render_template, request, session, url_for
from flask_sse import sse
import threading
from THavalon import Avalon, Role
import queue

class ThreadSafeList:
    def __init__(self):
        self._data = []
        self._lock = threading.Lock()

    def append(self, item):
        with self._lock:
            if item in self._data:
                return True
            if len(self._data) < 10:
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

players = ThreadSafeList()

class RoleInfo:
    name : str
    game_infos : list[str]
    info : dict
    def __init__(self, role : Role, game : Avalon):
        self.name = str(role)
        self.game_infos = role.get_info_str(game).split('\n')
        self.info = role.get_info(game)

    def render_html_info(self):
        filename = self.name + '.html' if self.name != "The Questing Beast" else "Beast.html"
        return render_template(filename, 
                               name = self.name, 
                               info = self.info,
                               image = 'round_table.jpg')

class ThreadSafeGame:
    active : bool = False
    player_info : dict[str, RoleInfo] = {}
    def __init__(self):
        self._lock = threading.Lock()
    def restart(self):
        with self._lock:
            self.active = True
            self.player_info = {}
            new_game = Avalon(players.snapshot())
            for role in new_game:
                self.player_info[new_game[role]] = RoleInfo(role, new_game)
    def is_active(self):
        with self._lock:
            return self.active
    def __getitem__(self, player : str) -> RoleInfo:
        with self._lock:
            return self.player_info[player]
    def __contains__(self, player : str):
        with self._lock:
            return player in self.player_info

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

    return game[player].render_html_info()

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
    test_players = [f"p{i+1}" for i in range(6)]
    for p in test_players:
        players.append(p)
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
