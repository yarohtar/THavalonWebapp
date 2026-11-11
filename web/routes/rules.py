"""The rules pages, with the viewer's current game's rule changes on top."""
from __future__ import annotations

import flask
from flask import Blueprint

from web.rules import pages
from web.visitor import viewer_game

bp = Blueprint('rules', __name__)


@bp.route("/rules/")
@bp.route("/rules/<slug>")
def page(slug = "overview"):
    if slug not in pages.PAGES:
        flask.abort(404)
    lobby = viewer_game()
    ruleset = lobby.current_game.game_ruleset if lobby else None
    return flask.render_template('rules/page.html',
                                 page = pages.BY_SLUG[slug],
                                 terms = pages.TERMS,
                                 game_lobby = lobby,
                                 ruleset = ruleset,
                                 term_ruleset = ruleset)
