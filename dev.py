"""Test scenarios for the dev site: games set up in a particular state.

Only active when the app runs with AVALON_DEV=1 (the dev site's service);
the normal site never registers any of this.

    /dev/                     list of scenarios
    /dev/<slug>               reset the scenario's game, then view it
    /dev/<slug>/as/<who>      view it as a player (or "host")

Viewing as someone simply makes this browser session *be* that player: the
real pages (Game / Role / Vote tabs, host page) are used unchanged. A bar at
the top of every page switches player, resets the scenario and sends
feedback. Each tester (browser session) gets their own copy of every
scenario, so testers never see each other's games.

Feedback (/dev/feedback) is emailed through Amazon SES with the game's full
state, secrets included:

    DEV_FEEDBACK_EMAIL      where feedback goes (also the sender by default)
    DEV_FEEDBACK_FROM       optional: a different verified SES sender

Access: the dev site sits behind Cloudflare Access, whose policy decides who
gets in (add playtesters there). As a second lock, every request must carry
a valid Access token for this Access application (checked against the
team's keys), so the site stays closed if Access is ever switched off.
Without the first two settings below, everything is refused.

    CF_ACCESS_TEAM_DOMAIN   e.g. myteam.cloudflareaccess.com
    CF_ACCESS_AUD           the Access application's audience tag
    DEV_ALLOWED_EMAILS      optional, comma-separated: only these emails
                            (empty: whoever the Access policy lets in)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

import flask
from flask import Blueprint, request, session, url_for
from markupsafe import Markup

import THavalon as T
from game import Phase, PAUSES

PLAYER_NAMES = ["Ann", "Bob", "Cat", "Dan", "Eve", "Fay", "Gus", "Hal", "Ivy", "Jon"]


def enabled() -> bool:
    return os.environ.get("AVALON_DEV") == "1"


# ---------------------------------------------------------------- driving

class Drive:
    """Plays a game forward quickly (as the players would) to set up a scenario."""

    def __init__(self, ctl):
        self.ctl = ctl

    @property
    def s(self):
        return self.ctl.state

    def act(self, player, action, **params):
        self.ctl.act(player, action, **params)

    def first_round(self, team, other=None, winner=0):
        a, b = self.s.first_proposers
        self.act(a, "propose_first_round", team=team)
        self.act(b, "propose_first_round", team=other or team)
        for p in self.s.seating:
            self.act(p, "vote_first_round", proposer=(a, b)[winner])

    def propose(self, team, approve=True):
        """The current Leader proposes `team`; approve: True, False or a set of approvers."""
        self.act(self.s.leader, "propose", team=team)
        if self.s.phase == Phase.VOTING:
            for p in self.s.seating:
                yes = approve if isinstance(approve, bool) else p in approve
                self.act(p, "vote", approve=yes)

    def reject_until_hammer(self, team):
        while not self.s.is_hammer():
            self.propose(team, approve=False)

    def cards(self, fails=(), **special):
        """Team members play: Fail if in `fails`, a card named in `special`,
        otherwise Success (or the only card their role allows)."""
        q = self.s.current_quest
        for p in q.team:
            allowed = [c.value for c in self.s.allowed_cards(p)]
            card = special.get(p) or ("Fail" if p in fails else "Success")
            if card not in allowed:
                card = allowed[0]
            self.act(p, "play_card", card=card)

    def inquisition(self, pick=0):
        """The Leader reveals the card of team member number `pick`, if they have Inquisition."""
        s = self.s
        if s.phase == Phase.INQUISITION:
            q = s.current_quest
            self.act(q.leader, "inquisition", target=q.team[pick])

    def settle(self):
        """Finish Inquisition and pauses until the next decision (stops at the Lady)."""
        for _ in range(20):
            s = self.s
            if s.phase == Phase.INQUISITION:
                q = s.current_quest
                self.act(q.leader, "inquisition", target=q.team[0])
            elif s.phase in PAUSES:
                for p in s.seating:
                    if p not in s.ready:
                        self.act(p, "ready")
            else:
                return

    def quest(self, team, fails=(), **special):
        """A whole round: team chosen (round 1) or approved, cards, aftermath."""
        if self.s.round == 1:
            self.first_round(team)
        else:
            self.propose(team)
        self.cards(fails, **special)
        self.settle()


# ---------------------------------------------------------------- scenarios

@dataclass
class Scenario:
    slug : str
    title : str
    about : str
    roles : list[str]                   # dealt to Ann, Bob, ... in seating order
    setup : Callable[[Drive], None] = lambda d: None
    view : str | None = None            # who to show first; default: who acts
    sizes : list[int] | None = None
    double_fail : int | None = None     # None: default; 0: no quest needs 2 Fails
    lady : bool = False
    group : str = "Game flow"

    @property
    def players(self) -> list[str]:
        return PLAYER_NAMES[:len(self.roles)]


def P(*idx):
    """Players by seat number: P(0, 2) -> ['Ann', 'Cat']."""
    return [PLAYER_NAMES[i] for i in idx]


SEVEN = ["Merlin", "Percival", "Tristan", "Iseult", "Mordred", "Morgana", "Maelegant"]

SCENARIOS = [
    # Ann and Bob propose in round 1, Cat proposes first in round 2.
    Scenario("start", "Start of the game",
             "Round 1: Ann and Bob each propose a team.", SEVEN),
    Scenario("first-round-vote", "First round vote",
             "Both round-1 teams are in; everyone chooses one on their Vote tab.", SEVEN,
             lambda d: (d.act("Ann", "propose_first_round", team=P(0, 1)),
                        d.act("Bob", "propose_first_round", team=P(1, 2)))),
    Scenario("proposal-vote", "Proposal vote",
             "Round 2: Cat proposed a team; everyone approves or rejects.", SEVEN,
             lambda d: (d.quest(P(0, 1)), d.act("Cat", "propose", team=P(2, 3, 4)))),
    Scenario("quest-cards", "Choosing quest cards",
             "Round 2 quest with Merlin, Mordred and Maelegant: "
             "Maelegant may also play Reversal.", SEVEN,
             lambda d: (d.quest(P(0, 1)), d.propose(P(0, 4, 6))), view="Gus"),
    Scenario("hammer", "Hammer and Changeling",
             "Round 2: three proposals rejected, the Hammer goes without a vote. "
             "Oberon (Gus) isn't on it and may swap in.",
             ["Merlin", "Percival", "Servant of Camelot", "Servant of Camelot",
              "Mordred", "Morgana", "Oberon"],
             lambda d: (d.quest(P(0, 1)), d.reject_until_hammer(P(0, 1, 2)),
                        d.act(d.s.leader, "propose", team=P(0, 1, 2))),
             view="Gus", group="Abilities"),
    Scenario("sorceress", "Sorceress",
             "Round 2: Morgana (Cat) leads and may declare instead of proposing.",
             ["Merlin", "Percival", "Morgana", "Tristan", "Iseult", "Mordred", "Maelegant"],
             lambda d: d.quest(P(0, 1)), group="Abilities"),
    Scenario("weak-inquisition", "Weak Inquisition",
             "Round 2: the first proposal was approved, so Cat (the Leader) reveals a card.",
             SEVEN, lambda d: (d.quest(P(0, 1)), d.propose(P(0, 4, 5)), d.cards(fails=P(4))),
             group="Abilities"),
    Scenario("strong-inquisition", "Strong Inquisition",
             "10 players, 4 Evil: the first approved proposal of round 2 gives "
             "Cat Strong Inquisition (reveal or remove a card).",
             ["Merlin", "Percival", "Servant of Camelot", "Tristan", "Iseult", "Arthur",
              "Mordred", "Morgana", "Maelegant", "Minion of Mordred"],
             lambda d: (d.quest(P(0, 1, 2)), d.propose(P(0, 6, 7, 3)), d.cards(fails=P(6))),
             group="Abilities"),
    Scenario("gawain", "Gawain's Inquisition",
             "10 players. Round 2 cards are in; Gawain (Dan) isn't on the quest and "
             "may force a player to reveal their card before the reveal.",
             ["Merlin", "Percival", "Servant of Camelot", "Gawain", "Tristan", "Iseult",
              "Mordred", "Morgana", "Maelegant", "Agravaine"],
             lambda d: (d.quest(P(0, 1, 2)), d.propose(P(0, 6, 7, 2)),
                        d.cards(fails=P(6)), d.inquisition(pick=3)),
             view="Dan", group="Abilities"),
    Scenario("betrayal", "Betrayal",
             "Round 2 needs 2 Fails; Agravaine (Eve) played the only Fail, so the quest "
             "succeeded. Agravaine may Betray it.",
             ["Merlin", "Percival", "Tristan", "Iseult", "Agravaine", "Morgana", "Mordred"],
             lambda d: (d.quest(P(0, 1)), d.propose(P(0, 1, 4)), d.cards(), d.inquisition()),
             double_fail=2, view="Eve", group="Abilities"),
    Scenario("proclamation", "Proclamation",
             "Two quests failed: Arthur (Bob) may proclaim at any time.",
             ["Merlin", "Arthur", "Percival", "Servant of Camelot", "Mordred", "Morgana",
              "Maelegant"],
             lambda d: (d.quest(P(0, 4), fails=P(4)), d.quest(P(2, 4, 5), fails=P(4))),
             view="Bob", group="Abilities"),
    Scenario("lady", "Lady of the Lake",
             "After quest 2 the Lady's holder (Bob) sends her to another player "
             "and sees their team.", SEVEN,
             lambda d: (d.quest(P(0, 1)), d.quest(P(2, 3, 4), fails=P(4))),
             lady=True, group="Abilities"),
    Scenario("questing-beast", "Pellinore and the Questing Beast",
             "9 players. Round 2 quest with the Beast (Hal) and Pellinore (Gus): "
             "the Beast must play Questing Beast Was Here.",
             ["Merlin", "Percival", "Tristan", "Iseult", "Mordred", "Morgana", "Pellinore",
              "The Questing Beast", "Maelegant"],
             lambda d: (d.quest(P(0, 1, 2)), d.propose(P(6, 7, 0, 1))),
             view="Hal", group="Abilities"),
    Scenario("pellinore-guess", "Pellinore's guess",
             "9 players. Good won 3 quests; first Pellinore (Gus) names who they think "
             "is the Beast, then the Assassination.",
             ["Merlin", "Percival", "Tristan", "Iseult", "Mordred", "Morgana", "Pellinore",
              "The Questing Beast", "Maelegant"],
             lambda d: (d.quest(P(0, 1, 2)), d.quest(P(0, 1, 2, 3)), d.quest(P(0, 1, 2, 3))),
             group="End of game"),
    Scenario("assassination", "Assassination",
             "Good won 3 quests. Mordred (Eve) decides: Merlin, Nilrem, the Lovers, or no one.",
             SEVEN,
             lambda d: (d.quest(P(0, 1)), d.quest(P(0, 1, 2)), d.quest(P(0, 1, 2))),
             group="End of game"),
    Scenario("evil-wins", "Evil wins",
             "Three quests failed: the game is over.", SEVEN,
             lambda d: (d.quest(P(0, 4), fails=P(4)), d.quest(P(0, 1, 4), fails=P(4)),
                        d.quest(P(0, 1, 5), fails=P(5))),
             view="Ann", group="End of game"),
    Scenario("host-votes", "Host votes",
             "Round 2, Cat proposing. Use the host page to start votes by hand.", SEVEN,
             lambda d: d.quest(P(0, 1)), view="host", group="Host"),
]
BY_SLUG = {s.slug: s for s in SCENARIOS}


def make_builder(players : list[str], role_names : list[str]) -> T.AvalonBuilder:
    """Roles dealt exactly as listed (no shuffling, no lonely transformations)."""
    b = object.__new__(T.AvalonBuilder)
    b.players = list(players)
    b.role_to_player = {}
    soc = mom = 0
    for player, name in zip(players, role_names):
        if name == "Servant of Camelot":
            role = T.SoC(soc); soc += 1
        elif name == "Minion of Mordred":
            role = T.MoM(mom); mom += 1
        else:
            role = T.string_to_role[name]
        b[role] = player
    return b


# ---------------------------------------------------------------- feedback

def game_snapshot(game) -> dict:
    """Everything about a game, secrets included, for a feedback email."""
    ctl = game.controller
    if ctl is None:
        return {}
    s = ctl.state
    q = s.current_quest
    p = s.current_proposal
    hv = game.host_vote
    return dict(
        phase=s.phase.value, round=s.round, leader=s.leader,
        roles={pl: s.role(pl) for pl in s.seating},
        secret=dict(
            current_quest_cards={k: v.value for k, v in q.cards.items()} if q else None,
            current_proposal_votes=dict(p.votes) if p else None,
            first_round_votes=dict(s.first_round_votes),
            ready=sorted(s.ready),
            lady_uses=s.lady_uses,
            host_vote_ballots=dict(hv.ballots) if hv else None,
        ),
        host_vote=hv.view() if hv else None,
        undo=ctl.undo_label(),
        view=ctl.view(None, scoped=False),
        log=s.log,
    )


def send_email(to : str, subject : str, text : str, reply_to : str | None = None,
               sender : str | None = None):
    """Through Amazon SES with the server's instance role (aws CLI), like the
    maths site's feedback emails. Raises on failure."""
    import json
    import shutil
    import subprocess
    import tempfile
    # The service's PATH is only the app's virtualenv; the CLI is a system tool.
    aws = shutil.which("aws", path=os.environ.get("PATH", "") + ":/usr/local/bin:/usr/bin")
    if aws is None:
        raise RuntimeError("aws CLI not found")
    content = {"Simple": {"Subject": {"Data": subject[:200], "Charset": "UTF-8"},
                          "Body": {"Text": {"Data": text, "Charset": "UTF-8"}}}}
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
        json.dump(content, f)
        f.flush()
        cmd = [aws, "sesv2", "send-email",
               "--region", os.environ.get("AWS_REGION", "eu-west-2"),
               "--from-email-address", sender or to,
               "--destination", json.dumps({"ToAddresses": [to]}),
               "--content", f"file://{f.name}"]
        if reply_to:
            cmd += ["--reply-to-addresses", reply_to]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)


# ---------------------------------------------------------------- the app

def init_app(app, web):
    """`web` is the webapp module (passed in to avoid a circular import)."""
    import json
    import secrets
    from datetime import datetime, timezone
    from flask import g

    bp = Blueprint("dev", __name__, url_prefix="/dev")

    # Every tester (browser session) gets their own copy of each scenario,
    # kept on the server under a random id stored in their session.
    def tester() -> str:
        if "dev_tester" not in session:
            session["dev_tester"] = secrets.token_hex(4)
        return session["dev_tester"]

    def uuid_of(slug, who):
        return f"dev-{tester()}-{slug}-{who}"

    def lobby_id(slug):
        return f"dev-{tester()}-{slug}"

    def build(sc : Scenario):
        """A fresh lobby with the scenario's game, replacing this tester's earlier one."""
        players = {uuid_of(sc.slug, n): n for n in sc.players}
        lobby = web.Lobby(uuid_of(sc.slug, "host"), f"Test: {sc.title}")
        lobby.id = lobby_id(sc.slug)
        lobby._players = dict(players)
        old = web.LOBBIES.get(lobby.id)
        if old is not None:      # keep counting games, so vote keys never repeat
            lobby.current_game.game_number = old.current_game.game_number
        roles = [r for r in make_builder(sc.players, sc.roles)]
        settings = web.GameSettings()
        settings.num_evils = sum(r.allegiance() == "Evil" for r in roles)
        settings.team_sizes = sc.sizes
        settings.double_fail = sc.double_fail
        settings.lady = sc.lady
        rules = settings.resolve(len(players), roles)
        lobby.current_game.install(make_builder(sc.players, sc.roles), roles, players, rules)
        sc.setup(Drive(lobby.current_game.controller))
        web.LOBBIES.add(lobby)
        web.new_event("new-game", lobby.id)
        web.new_event("game-update", lobby.id)
        return lobby

    def current():
        """(scenario, lobby, who) this session is looking at, or Nones."""
        sc = BY_SLUG.get(session.get("dev_slug"))
        if sc is None:
            return None, None, None
        return sc, web.LOBBIES.get(lobby_id(sc.slug)), session.get("dev_as")

    def view_as(sc : Scenario, lobby, who : str):
        session["dev_slug"] = sc.slug
        session["dev_as"] = who
        session["player_id"] = uuid_of(sc.slug, who)
        session["game_id"] = lobby.id
        if who != "host":
            session["name"] = who
        return flask.redirect(url_for("lobby_api") if who == "host" else url_for("index"))

    @bp.route("/")
    def index():
        groups = {}
        for sc in SCENARIOS:
            groups.setdefault(sc.group, []).append(sc)
        return flask.render_template("dev/index.html", groups=groups)

    @bp.route("/<slug>")
    def start(slug):
        sc = BY_SLUG.get(slug) or flask.abort(404)
        lobby = build(sc)
        who = request.args.get("as") or sc.view
        if who is None:
            waiting = lobby.current_game.controller.view()["waiting_for"]
            who = waiting[0] if waiting else sc.players[0]
        return view_as(sc, lobby, who)

    @bp.route("/<slug>/as/<who>")
    def switch(slug, who):
        sc = BY_SLUG.get(slug) or flask.abort(404)
        if who != "host" and who not in sc.players:
            flask.abort(404)
        lobby = web.LOBBIES.get(lobby_id(slug)) or build(sc)
        return view_as(sc, lobby, who)

    @bp.route("/bar")
    def bar():
        return dev_bar()

    def dev_bar() -> Markup:
        sc, lobby, who = current()
        ctx = dict(scenario=sc, who=who, seats=[], waiting=[])
        if sc and lobby and lobby.current_game.controller:
            state = lobby.current_game.controller.state
            ctx["seats"] = [(p, state.role(p)) for p in state.seating]
            ctx["waiting"] = lobby.current_game.controller.view()["waiting_for"]
        return Markup(flask.render_template("dev/bar.html", **ctx))

    @app.context_processor
    def inject_dev_bar():
        return dict(dev_bar=dev_bar)

    # ---- feedback, emailed with the game's full state ----

    feedback_to = os.environ.get("DEV_FEEDBACK_EMAIL", "").strip()
    feedback_from = os.environ.get("DEV_FEEDBACK_FROM", "").strip() or feedback_to

    @bp.route("/feedback", methods=["GET", "POST"])
    def feedback():
        sc, lobby, who = current()
        page = request.values.get("page") or ""
        if not page.startswith("/") or page.startswith("//"):
            page = ""          # only pages on this site (it's used as a link)
        if request.method == "GET":
            return flask.render_template("dev/feedback.html", scenario=sc, who=who,
                                         page=page, configured=bool(feedback_to))
        text = request.form.get("description", "").strip()
        if not text:
            return flask.render_template("dev/feedback.html", scenario=sc, who=who, page=page,
                                         configured=bool(feedback_to),
                                         error="Describe what happened first."), 400
        tester_email = g.get("dev_email")
        report = dict(
            time=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            tester=tester_email, tester_id=session.get("dev_tester"),
            scenario=dict(slug=sc.slug, title=sc.title, about=sc.about) if sc else None,
            viewing_as=who, page=page,
            user_agent=request.headers.get("User-Agent"),
            game=game_snapshot(lobby.current_game) if lobby else None,
        )
        where = f"{sc.title} as {who}" if sc else "no scenario"
        body = (f"{text}\n\n"
                f"-- \nFrom: {tester_email or 'unknown tester'}\n"
                f"Scenario: {where}\nPage: {page or '?'}\n"
                f"Phase: {(report['game'] or {}).get('phase', '-')}\n\n"
                f"Full report (JSON):\n{json.dumps(report, indent=2, default=str)}\n")
        subject = f"[Avalon dev] {where}: {text.splitlines()[0][:80]}"
        if not feedback_to:
            app.logger.warning("Feedback not sent (DEV_FEEDBACK_EMAIL unset):\n%s", body)
            return flask.render_template("dev/feedback.html", scenario=sc, who=who, page=page,
                                         configured=False,
                                         error="Feedback isn't set up on this server."), 503
        try:
            app.config.get("DEV_SEND_EMAIL", send_email)(
                feedback_to, subject, body, reply_to=tester_email, sender=feedback_from)
        except Exception as e:
            app.logger.error("Feedback email failed: %s\n%s", e, body)
            return flask.render_template("dev/feedback.html", scenario=sc, who=who, page=page,
                                         configured=True, description=text,
                                         error="Sending failed. Try again in a moment."), 502
        return flask.render_template("dev/feedback.html", scenario=sc, who=who, page=page,
                                     configured=True, sent=True)

    # ---- access check: runs before everything else ----

    team = os.environ.get("CF_ACCESS_TEAM_DOMAIN", "").strip()
    aud = os.environ.get("CF_ACCESS_AUD", "").strip()
    allowed = {e.strip().lower() for e in os.environ.get("DEV_ALLOWED_EMAILS", "").split(",")
               if e.strip()}
    jwks = None
    if team and aud:
        import jwt
        jwks = jwt.PyJWKClient(f"https://{team}/cdn-cgi/access/certs", cache_keys=True)

    def check_access():
        if app.config.get("DEV_NO_AUTH"):
            return None
        if jwks is None:
            return flask.Response("Dev site is not configured.", 403)
        import jwt
        token = (request.headers.get("Cf-Access-Jwt-Assertion")
                 or request.cookies.get("CF_Authorization"))
        if not token:
            return flask.Response("Forbidden.", 403)
        try:
            key = jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=aud,
                                issuer=f"https://{team}")
        except Exception:
            return flask.Response("Forbidden.", 403)
        email = str(claims.get("email", "")).lower()
        if allowed and email not in allowed:
            return flask.Response("Forbidden.", 403)
        g.dev_email = email or None
        return None

    app.before_request_funcs.setdefault(None, []).insert(0, check_access)
    # The dev pages don't need a player name.
    web.REGISTRATION_EXEMPT.append("/dev")
    app.register_blueprint(bp)
