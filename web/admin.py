"""Admin pages: every lobby on this site, to inspect, change, close, and view
as any player or the host.

    /admin/                       all lobbies (close one, or all idle ones)
    /admin/lobby/<id>             one lobby: players, roles, game state, log
    /admin/as/<id>/<who>/...      the site as a player (their id) or "host" sees it

Viewing as someone: every page of the site, under the prefix
/admin/as/<lobby id>/<who>, is shown as that player (or the host) sees it.
Links on those pages keep the prefix (it is set as the app's SCRIPT_NAME), so
the admin can click around freely; the same pages without the prefix are the
admin's own. Nothing is kept from a view-as request: it gets a throwaway
session holding that person's identity (and, for the host, the current
game's settings), and changes to it are dropped. So the admin's own session
(name, game, host preferences) is never touched, and the person's own
preferences live in their own browser, out of reach. Game actions taken there
(votes, proposals, starting a new game as the host) are real, though.

Access: put a Cloudflare Access application on the path /admin of the site
(a self-hosted application with that path), with a policy that lets in only
the admin. That is all the setup needed: the app then only checks that each
request carries a valid Access token (see access.email_from_any_team), so
/admin stays closed if the Access rule is ever removed.

Optionally, to also pin the Access application and the admin's email:

    CF_ACCESS_TEAM_DOMAIN   e.g. myteam.cloudflareaccess.com
    ADMIN_ACCESS_AUD        the /admin Access application's audience tag
    ADMIN_EMAILS            comma-separated: who may use the admin pages
"""
from __future__ import annotations

import json
import os
import re
import secrets

import flask
from flask import Blueprint, g, request, session, url_for
from flask.sessions import SecureCookieSession, SecureCookieSessionInterface
from markupsafe import Markup

from thavalon import RuleError
from web import events
from web.access import AccessCheck, email_from_any_team
from web.dev import game_snapshot
from web.host_settings import evils_key
from web.lobbies import LOBBIES, LOBBIES_CHANNEL, close_lobby
from web.store import Conflict

VIEW_AS = re.compile(r"^/admin/as/([^/]+)/([^/]+)(/.*)?$")


class ViewAsMiddleware:
    """/admin/as/<lobby>/<who>/rest -> the app's /rest, with the prefix as
    SCRIPT_NAME (so url_for keeps it) and environ['avalon.view_as']."""
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        m = VIEW_AS.match(environ.get("PATH_INFO", ""))
        if m:
            lobby_id, who, rest = m.groups()
            environ["avalon.view_as"] = (lobby_id, who)
            environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "")
                                      + f"/admin/as/{lobby_id}/{who}")
            environ["PATH_INFO"] = rest or "/"
        return self.wsgi_app(environ, start_response)


def view_as_url(lobby_id : str, who : str) -> str:
    """Where viewing a lobby as someone starts (the host: their host page)."""
    return f"/admin/as/{lobby_id}/{who}/" + ("host" if who == "host" else "")


def ago(seconds : int | None) -> str:
    if seconds is None:
        return "?"
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def init_app(app, registration_exempt : list[str]):
    """Add the admin pages to the app; `registration_exempt`: the app's paths
    that need no player name."""
    bp = Blueprint("admin", __name__, url_prefix="/admin")

    access = AccessCheck(os.environ.get("CF_ACCESS_TEAM_DOMAIN", ""),
                         os.environ.get("ADMIN_ACCESS_AUD", ""))
    admins = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",")
              if e.strip()}

    def is_admin() -> bool:
        if app.config.get("ADMIN_NO_AUTH"):
            return True
        if access.configured:
            email = access.email(request)
        else:
            email = email_from_any_team(request)
        if not email or (admins and email not in admins):
            return False
        g.admin_email = email
        return True

    @bp.before_request
    def check_access():
        if not is_admin():
            return flask.Response("Forbidden.", 403)
        if request.method == "POST":
            token = request.form.get("csrf", "")
            if not secrets.compare_digest(token, session.get("admin_csrf", "")):
                return flask.Response("Stale form: reload the page and try again.", 400)
        return None

    def csrf_token() -> str:
        if "admin_csrf" not in session:
            session["admin_csrf"] = secrets.token_hex(16)
        return session["admin_csrf"]

    def lobby_or_404(lobby_id):
        return LOBBIES.get(lobby_id) or flask.abort(404)

    def people(lobby) -> list[dict]:
        """Everyone in the lobby or its game: id, name, role, flags."""
        game = lobby.current_game
        names = dict(lobby.snapshot())
        for uuid in game.player_info:                 # left the lobby, still in the game
            names.setdefault(uuid, game.names.get(uuid, "?"))
        waiting = set(game.controller.view()["waiting_for"]) if game.controller else set()
        return [dict(uuid=uuid, name=name, in_lobby=uuid in lobby,
                     role=game[uuid]["role"] if uuid in game else None,
                     waiting=name in waiting and uuid in game)
                for uuid, name in names.items()]

    def summary(lobby) -> dict:
        game = lobby.current_game
        ctl = game.controller
        out = dict(phase=None, round=None, players=len(lobby), in_game=len(game.player_info))
        if ctl is not None:
            out.update(phase=ctl.state.phase.value, round=ctl.state.round)
        return out

    # ---- pages ----

    @bp.route("/")
    def index():
        lobbies = LOBBIES.active()
        idle = LOBBIES.idle_seconds([l.id for l in lobbies])
        rows = sorted(({"lobby": l, "idle": idle.get(l.id), "ago": ago(idle.get(l.id)),
                        **summary(l)} for l in lobbies),
                      key=lambda r: -(r["idle"] or 0))
        return flask.render_template("admin/index.html", rows=rows, csrf=csrf_token(),
                                     closed=request.args.get("closed"),
                                     max_idle=ago(LOBBIES.max_idle_seconds))

    @bp.route("/lobby/<lobby_id>")
    def lobby_page(lobby_id):
        lobby = lobby_or_404(lobby_id)
        game = lobby.current_game
        idle = LOBBIES.idle_seconds([lobby.id])[lobby.id]
        ctx = dict(lobby=lobby, people=people(lobby), csrf=csrf_token(),
                   idle=ago(idle), expires=ago(None if idle is None
                                               else LOBBIES.max_idle_seconds - idle),
                   message=request.args.get("msg"), error=request.args.get("error"),
                   game=game, summary=summary(lobby))
        if game.controller is not None:
            snap = game_snapshot(game)
            ctx.update(snapshot=json.dumps(snap, indent=2, default=str),
                       log=snap.get("log") or [], undo=game.controller.undo_label(),
                       host_vote_open=bool(game.host_vote and game.host_vote.open),
                       waiting=game.controller.view()["waiting_for"])
        return flask.render_template("admin/lobby.html", **ctx)

    # ---- closing ----

    @bp.route("/lobby/<lobby_id>/close", methods=["POST"])
    def close(lobby_id):
        lobby = close_lobby(lobby_id)
        return flask.redirect(url_for("admin.index",
                                      closed=lobby.name if lobby else None))

    @bp.route("/close-idle", methods=["POST"])
    def close_idle():
        try:
            hours = float(request.form.get("hours", ""))
        except ValueError:
            flask.abort(400)
        lobbies = LOBBIES.active()
        idle = LOBBIES.idle_seconds([l.id for l in lobbies])
        names = []
        for l in lobbies:
            if idle.get(l.id) is not None and idle[l.id] >= hours * 3600:
                if close_lobby(l.id) is not None:
                    names.append(l.name)
        return flask.redirect(url_for("admin.index",
                                      closed=", ".join(names) or "nothing"))

    # ---- changing a lobby ----

    def remove_player(lobby, uuid):
        lobby.pop(uuid)

    def rename(lobby, name):
        if not name:
            raise RuleError("Give a name.")
        lobby.name = name

    def require_game(lobby):
        if lobby.current_game.controller is None:
            raise RuleError("No game is being played.")
        return lobby.current_game

    COMMANDS = {
        # command: (change(lobby, form) -> message, event, channel is the lobby?)
        "rename": (lambda l, f: rename(l, f.get("name", "").strip()[:40]) or "Renamed.",
                   "new-lobby", False),
        "remove": (lambda l, f: remove_player(l, f.get("uuid", "")) or "Removed from the lobby.",
                   "new-player", True),
        "keep-alive": (lambda l, f: "Idle time reset.", None, True),
        "undo": (lambda l, f: "Undid: " + require_game(l).host_undo(), "game-update", True),
        "skip": (lambda l, f: require_game(l).host_skip() or "Skipped the pause.",
                 "game-update", True),
        "end-vote": (lambda l, f: require_game(l).end_host_vote(cancel=True)
                     or "Host vote cancelled.", "game-update", True),
    }

    @bp.route("/lobby/<lobby_id>/<command>", methods=["POST"])
    def change(lobby_id, command):
        if command not in COMMANDS:
            flask.abort(404)
        fn, event, on_lobby = COMMANDS[command]
        form = request.form
        try:
            lobby, message = LOBBIES.update(lobby_id, lambda l: fn(l, form))
        except KeyError:
            flask.abort(404)
        except (RuleError, Conflict) as e:
            error = e.args[0] if isinstance(e, RuleError) else "Conflict, try again."
            return flask.redirect(url_for("admin.lobby_page", lobby_id=lobby_id, error=error))
        if event:
            events.publish(lobby.id if on_lobby else LOBBIES_CHANNEL, event)
        return flask.redirect(url_for("admin.lobby_page", lobby_id=lobby_id, msg=message))

    # ---- viewing as someone ----

    def host_prefs_of(lobby) -> dict:
        """Host preferences matching the lobby's current game, so the host
        page shows the settings it was started with."""
        game = lobby.current_game
        rules = game.rules
        if not rules:
            return {}
        n, evils = rules["num_players"], rules["num_evils"]
        return dict(roles=[str(r) for r in game.roles_in_game], gareth_offered=True,
                    lady=rules["lady"], rules=game.game_ruleset.to_json(),
                    evils={evils_key(n, rules.get("extras", rules.get("gareth"))): evils},
                    quests={f"{n}-{evils}": dict(sizes=rules["team_sizes"],
                                                 double_fail=rules["double_fail"] or 0)})

    def viewed(lobby_id, who) -> dict | None:
        """Who a view-as request is for, and their session values."""
        lobby = LOBBIES.get(lobby_id)
        if lobby is None:
            return None
        if who == "host":
            return dict(lobby=lobby.id, lobby_name=lobby.name, who=who, uuid=lobby.host_uuid,
                        name="Host", session=dict(player_id=lobby.host_uuid, name="Host",
                                                  game_name=lobby.name,
                                                  host_prefs=host_prefs_of(lobby)))
        person = next((p for p in people(lobby) if p["uuid"] == who), None)
        if person is None:
            return None
        return dict(lobby=lobby.id, lobby_name=lobby.name, who=who, uuid=who,
                    name=person["name"], session=dict(player_id=who, name=person["name"],
                                                      game_id=lobby.id))

    class Sessions(SecureCookieSessionInterface):
        """View-as requests get a throwaway session; nothing is saved."""
        def open_session(self, app_, req):
            target = req.environ.get("avalon.view_as")
            if target is None:
                return super().open_session(app_, req)
            info = viewed(*target)
            req.environ["avalon.viewed"] = info
            return SecureCookieSession(dict(info["session"]) if info else {})

        def save_session(self, app_, sess, response):
            if request.environ.get("avalon.view_as") is None:
                super().save_session(app_, sess, response)

    app.jinja_env.globals["view_as_url"] = view_as_url
    app.session_interface = Sessions()
    app.wsgi_app = ViewAsMiddleware(app.wsgi_app)

    def check_view_as():
        """Before everything else: view-as requests are for the admin only,
        same-site only (they can act), and never reach admin pages."""
        if request.environ.get("avalon.view_as") is None:
            # Sessions from before view-as had its own URLs: give the admin
            # their own identity back.
            saved = session.pop("admin_saved", None)
            session.pop("admin_as", None)
            for k, v in (saved or {}).items():
                if v is None:
                    session.pop(k, None)
                else:
                    session[k] = v
            return None
        if not is_admin():
            return flask.Response("Forbidden.", 403)
        if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
            return flask.Response("Forbidden.", 403)
        if request.environ.get("avalon.viewed") is None or request.path.startswith("/admin"):
            flask.abort(404)
        g.view_as = request.environ["avalon.viewed"]
        return None

    app.before_request_funcs.setdefault(None, []).insert(0, check_view_as)

    def admin_bar() -> Markup:
        viewing = g.get("view_as")
        if not viewing:
            return Markup("")
        lobby = LOBBIES.get(viewing["lobby"])
        return Markup(flask.render_template(
            "admin/bar.html", viewing=viewing, lobby=lobby,
            people=people(lobby) if lobby else [], view_as_url=view_as_url))

    @app.context_processor
    def inject_admin_bar():
        return dict(admin_bar=admin_bar)

    registration_exempt.append("/admin")
    app.register_blueprint(bp)
