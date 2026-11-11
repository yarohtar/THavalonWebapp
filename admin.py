"""Admin pages: every lobby on this site, to inspect, change, close, and view
as any player or the host.

    /admin/                       all lobbies (close one, or all idle ones)
    /admin/lobby/<id>             one lobby: players, roles, game state, log
    /admin/lobby/<id>/as/<who>    view it as a player (their id) or "host"
    /admin/stop                   back to being yourself

Viewing as someone works like the dev site's "view as": this browser session
*becomes* that player (or the host), so the real pages are shown, and
anything done there really is done as them. A bar at the top of every page
says so and leads back. The admin's own identity is kept aside meanwhile.

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
import secrets

import flask
from flask import Blueprint, g, request, session, url_for
from markupsafe import Markup

from access import AccessCheck, email_from_any_team
from game import RuleError

# Session values that say who this browser is; kept aside while viewing as
# someone else and put back afterwards.
IDENTITY_KEYS = ("player_id", "game_id", "name", "game_name")


def ago(seconds : int | None) -> str:
    if seconds is None:
        return "?"
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


def init_app(app, web):
    """`web` is the webapp module (passed in to avoid a circular import)."""
    from dev import game_snapshot

    bp = Blueprint("admin", __name__, url_prefix="/admin")
    LOBBIES = web.LOBBIES

    access = AccessCheck(os.environ.get("CF_ACCESS_TEAM_DOMAIN", ""),
                         os.environ.get("ADMIN_ACCESS_AUD", ""))
    admins = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",")
              if e.strip()}

    @bp.before_request
    def check_access():
        if not app.config.get("ADMIN_NO_AUTH"):
            if access.configured:
                email = access.email(request)
            else:
                email = email_from_any_team(request)
            if not email or (admins and email not in admins):
                return flask.Response("Forbidden.", 403)
            g.admin_email = email
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
        lobby = web.close_lobby(lobby_id)
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
                if web.close_lobby(l.id) is not None:
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
        except (RuleError, web.Conflict) as e:
            error = e.args[0] if isinstance(e, RuleError) else "Conflict, try again."
            return flask.redirect(url_for("admin.lobby_page", lobby_id=lobby_id, error=error))
        if event:
            web.new_event(event, lobby.id if on_lobby else web.LOBBIES_CHANNEL)
        return flask.redirect(url_for("admin.lobby_page", lobby_id=lobby_id, msg=message))

    # ---- viewing as someone ----

    @bp.route("/lobby/<lobby_id>/as/<who>")
    def view_as(lobby_id, who):
        lobby = lobby_or_404(lobby_id)
        if who == "host":
            name = None
            uuid = lobby.host_uuid
        else:
            person = next((p for p in people(lobby) if p["uuid"] == who), None)
            if person is None:
                flask.abort(404)
            uuid, name = who, person["name"]
        if "admin_saved" not in session:
            session["admin_saved"] = {k: session.get(k) for k in IDENTITY_KEYS}
        session["player_id"] = uuid
        if name is None:
            session["game_name"] = lobby.name
        else:
            session["game_id"] = lobby.id
            session["name"] = name
        session["admin_as"] = dict(lobby=lobby.id, uuid=uuid, who=who, name=name or "host")
        return flask.redirect(url_for("lobby_api") if name is None else url_for("index"))

    @bp.route("/stop")
    def stop():
        viewing = session.pop("admin_as", None)
        saved = session.pop("admin_saved", None)
        if saved is not None:
            for k, v in saved.items():
                if v is None:
                    session.pop(k, None)
                else:
                    session[k] = v
        if viewing and LOBBIES.get(viewing["lobby"]) is not None:
            return flask.redirect(url_for("admin.lobby_page", lobby_id=viewing["lobby"]))
        return flask.redirect(url_for("admin.index"))

    def admin_bar() -> Markup:
        viewing = session.get("admin_as")
        if not viewing:
            return Markup("")
        lobby = LOBBIES.get(viewing["lobby"])
        return Markup(flask.render_template(
            "admin/bar.html", viewing=viewing, lobby=lobby,
            people=people(lobby) if lobby else []))

    @app.context_processor
    def inject_admin_bar():
        return dict(admin_bar=admin_bar)

    web.REGISTRATION_EXEMPT.append("/admin")
    app.register_blueprint(bp)
