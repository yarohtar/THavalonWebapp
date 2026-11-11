"""Files browsers and search engines ask for at fixed paths: /favicon.ico,
/apple-touch-icon.png, /robots.txt and /sitemap.xml. Exempt from registration.

Only the start page and the rules pages are worth indexing; game, host and
admin pages are private to a lobby. The dev site is never indexed.
"""
from __future__ import annotations

import flask
from flask import Blueprint, url_for
from markupsafe import escape

from web import dev
from web.rules import pages

bp = Blueprint('site', __name__)

PRIVATE = ['/admin', '/dev', '/host', '/restart', '/game', '/events', '/join',
           '/games', '/donotread']


@bp.route("/favicon.ico")
def favicon():
    return flask.current_app.send_static_file('favicon.png')


@bp.route("/apple-touch-icon.png")
def apple_touch_icon():
    return flask.current_app.send_static_file('apple-touch-icon.png')


@bp.route("/robots.txt")
def robots():
    if dev.enabled():
        lines = ["User-agent: *", "Disallow: /"]
    else:
        lines = ["User-agent: *", "Allow: /",
                 *(f"Disallow: {p}" for p in PRIVATE),
                 "", f"Sitemap: {url_for('site.sitemap', _external=True, _scheme='https')}"]
    return flask.Response("\n".join(lines) + "\n", mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap():
    urls = [url_for('player.register', _external=True, _scheme='https')]
    urls += [url_for('rules.page', slug=slug, _external=True, _scheme='https') for slug in pages.PAGES]
    body = "".join(f"  <url><loc>{escape(u)}</loc></url>\n"
                   for u in urls)
    return flask.Response(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{body}</urlset>\n', mimetype="application/xml")
