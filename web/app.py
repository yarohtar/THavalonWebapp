"""The Flask app: settings, the session identity of each browser, page
templates' helpers, and every part of the site plugged in.

    gunicorn wsgi:app                 (the server; wsgi.py imports this)
    python -m web.app                 (local development server, port 5000)
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid as uuid_lib

import flask
from dotenv import load_dotenv
from flask import Flask, g, request, session, url_for

load_dotenv()

from thavalon.ruleset import ASSASSINATION_TARGETS      # noqa: E402
from web import admin, dev, events                       # noqa: E402
from web.routes import host, play, player, rules         # noqa: E402
from web.rules import notes as rule_notes, pages as rule_pages, role_text  # noqa: E402

# Templates and static files live in the web package.
app = Flask("web")


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
    logging.getLogger(__name__).warning(
        "SECRET_KEY is not set: using a random key (sessions end on restart).")
    return secrets.token_hex(32)


app.secret_key = _secret_key()

# ---- templates ----

rule_pages.init_app(app)
role_text.init_app(app)
app.jinja_env.globals.update(
    rule_notes_for = rule_notes.notes_for,
    rule_summary_notes = rule_notes.summary_notes,
    expand_note = rule_notes.expand,
    assassination_label = lambda kind: ASSASSINATION_TARGETS[kind][1],
    assassination_size = lambda kind: len(ASSASSINATION_TARGETS[kind][0]))


@app.context_processor
def inject_events_url():
    """Pages that set g.channel get live updates from that channel."""
    channel = g.get('channel')
    if channel is None:
        return dict(events_url = None)
    return dict(events_url = url_for('events.stream', channel = channel,
                                     last_id = events.bus.current_id(channel)))


# ---- who is asking ----

# Paths anyone may open without a player name (hosts don't need one).
REGISTRATION_EXEMPT = ['/register', '/static', '/rules', '/events',
                       '/host', '/restart', '/donotread']


@app.before_request
def assign_uuid():
    """Every browser gets a permanent random id (g.uuid)."""
    session.permanent = True
    if 'player_id' not in session:
        session['player_id'] = str(uuid_lib.uuid4())
    g.uuid = session['player_id']


@app.before_request
def require_registration():
    """Players need a name (g.name) before anything else."""
    if any(request.path.startswith(p) for p in REGISTRATION_EXEMPT):
        return None
    if 'name' not in session:
        next_page = request.full_path.rstrip('?') if request.method == 'GET' else None
        return flask.redirect(url_for('player.register', next = next_page))
    g.name = session['name']
    return None


# ---- the site ----

app.register_blueprint(events.blueprint)
for blueprint in (player.bp, host.bp, play.bp, rules.bp):
    app.register_blueprint(blueprint)

# Test scenarios, only on the dev site (AVALON_DEV=1). See dev.py.
if dev.enabled():
    dev.init_app(app, REGISTRATION_EXEMPT)

# Admin pages (/admin), behind Cloudflare Access. See admin.py.
admin.init_app(app, REGISTRATION_EXEMPT)


if __name__ == "__main__":
    # Development server only: every new lobby starts with 9 fake players.
    app.config['DEV_FAKE_PLAYERS'] = 9
    # Local dev scenarios skip the Cloudflare Access login check.
    app.config['DEV_NO_AUTH'] = True
    # And the admin pages too.
    app.config['ADMIN_NO_AUTH'] = True
    app.run(host="0.0.0.0", port=5000, debug=True)
