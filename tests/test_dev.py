"""Tests for the dev site's test scenarios (web/dev.py).  Run: python -m pytest

Each check runs in a fresh Python process, because whether dev features
exist is decided when web.app is imported (AVALON_DEV)."""
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(code, **env):
    env = {**{k: v for k, v in os.environ.items()
              if k not in ("AVALON_DEV", "CF_ACCESS_AUD", "CF_ACCESS_TEAM_DOMAIN",
                           "DEV_ALLOWED_EMAILS")}, **env}
    prelude = "import sys; sys.path.insert(0, '.'); from web.app import app\n" \
              "from web.lobbies import LOBBIES\n" \
              "app.config.update(TESTING=True)\nc = app.test_client()\n" \
              "LOBBIES.store.redis.flushdb()\n" \
              "def dev_lobby(slug):\n" \
              "    return next(l for l in LOBBIES.active() if l.id.endswith('-' + slug))\n"
    r = subprocess.run([sys.executable, "-c", prelude + textwrap.dedent(code)],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout


def test_normal_site_has_no_dev_features():
    run("""
        c.post('/register', data={'player': 'Ann'})
        assert c.get('/dev/').status_code == 404
        assert c.get('/dev/assassination').status_code == 404
        assert 'dev-bar' not in c.get('/').get_data(as_text=True)
        assert 'dev-bar' not in c.get('/host').get_data(as_text=True)
    """)


def test_dev_site_refuses_everything_without_access_settings():
    run("""
        for path in ('/dev/', '/', '/host', '/static/style.css', '/events/x'):
            assert c.get(path).status_code == 403, path
    """, AVALON_DEV="1")


def test_dev_site_accepts_valid_access_tokens_only():
    """A token signed by the team's key for this app gets in, whatever the
    email (the Access policy decides that), unless DEV_ALLOWED_EMAILS limits it."""
    code = """
        import json, time, jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from web import dev
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk['kid'] = 'k1'
        # Serve our test key instead of fetching Cloudflare's.
        jwt.PyJWKClient.fetch_data = lambda self: {'keys': [jwk]}
        def token(**claims):
            base = dict(aud=['aud'], iss='https://example.cloudflareaccess.com',
                        email='player@example.com', exp=time.time() + 60)
            return jwt.encode({**base, **claims}, key, 'RS256', headers={'kid': 'k1'})
        def status(t):
            return c.get('/dev/', headers={'Cf-Access-Jwt-Assertion': t}).status_code
        print(status(token()), status(token(aud=['other-app'])),
              status(token(iss='https://evil.cloudflareaccess.com')),
              status(token(exp=time.time() - 60)))
    """
    env = dict(AVALON_DEV="1", CF_ACCESS_TEAM_DOMAIN="example.cloudflareaccess.com",
               CF_ACCESS_AUD="aud")
    assert run(code, **env).split() == ["200", "403", "403", "403"]
    limited = run(code, DEV_ALLOWED_EMAILS="someone@example.com", **env).split()
    assert limited[0] == "403"


def test_dev_site_refuses_bad_tokens():
    run("""
        c.set_cookie('CF_Authorization', 'not-a-token')
        assert c.get('/dev/').status_code == 403
        assert c.get('/dev/', headers={'Cf-Access-Jwt-Assertion': 'x.y.z'}).status_code == 403
    """, AVALON_DEV="1", CF_ACCESS_TEAM_DOMAIN="example.cloudflareaccess.com",
        CF_ACCESS_AUD="aud", DEV_ALLOWED_EMAILS="someone@example.com")


def test_every_scenario_starts_in_its_situation():
    out = run("""
        from web import dev
        app.config['DEV_NO_AUTH'] = True
        expected = {
            'start': ('first_round_proposing', 'Ann', 'propose_first_round'),
            'first-round-vote': ('first_round_voting', 'Cat', 'vote_first_round'),
            'proposal-vote': ('voting', 'Dan', 'vote'),
            'quest-cards': ('quest', 'Gus', 'play_card'),
            'hammer': ('team_announced', 'Gus', 'changeling'),
            'sorceress': ('proposing', 'Cat', 'sorceress'),
            'weak-inquisition': ('inquisition', 'Cat', 'inquisition'),
            'strong-inquisition': ('inquisition', 'Cat', 'inquisition'),
            'gawain': ('reveal', 'Dan', 'gawain'),
            'betrayal': ('result', 'Eve', 'betray'),
            'proclamation': ('proposing', 'Bob', 'proclaim'),
            'lady': ('lady', 'Bob', 'lady'),
            'questing-beast': ('quest', 'Hal', 'play_card'),
            'pellinore-guess': ('pellinore_guess', 'Gus', 'pellinore_guess'),
            'assassination': ('assassination', 'Eve', 'assassinate'),
            'evil-wins': ('game_over', None, None),
            'changed-rules': ('assassination', 'Eve', 'assassinate'),
            'gareth-evil': ('first_round_proposing', 'Ann', 'propose_first_round'),
            'gareth-good': ('first_round_proposing', 'Ann', 'propose_first_round'),
            'gareth-assassination': ('assassination', 'Fay', 'assassinate'),
            'gareth-changed-rules': ('lady', 'Bob', 'lady'),
            'host-votes': ('proposing', 'Cat', 'propose'),
        }
        assert set(expected) == set(dev.BY_SLUG)
        for slug, (phase, player, action) in expected.items():
            r = c.get('/dev/' + slug)
            assert r.status_code == 302, slug
            page = c.get(r.headers['Location'])
            assert page.status_code == 200 and 'dev-bar' in page.get_data(as_text=True), slug
            ctl = dev_lobby(slug).current_game.controller
            assert ctl.state.phase.value == phase, (slug, ctl.state.phase)
            if action:
                assert action in ctl.available_actions(player), (slug, player)
        print('ok')
    """, AVALON_DEV="1")
    assert "ok" in out


def test_strong_inquisition_and_beast_card():
    run("""
        app.config['DEV_NO_AUTH'] = True
        c.get('/dev/strong-inquisition')
        ctl = dev_lobby('strong-inquisition').current_game.controller
        assert ctl.available_actions('Cat')['inquisition']['can_remove']
        c.get('/dev/questing-beast')
        ctl = dev_lobby('questing-beast').current_game.controller
        assert ctl.available_actions('Hal')['play_card']['cards'] == ['Questing Beast Was Here']
    """, AVALON_DEV="1")


def test_switching_player_and_reset():
    run("""
        app.config['DEV_NO_AUTH'] = True
        c.get('/dev/sorceress')
        ctl = dev_lobby('sorceress').current_game.controller
        assert c.get('/dev/sorceress/as/Ann').headers['Location'] == '/'
        state = c.get('/game/state').get_json()
        assert state['you']['name'] == 'Ann' and state['you']['role'] == 'Merlin'
        # Ann can't act for Cat; Cat proposes, then a reset puts it back.
        c.get('/dev/sorceress/as/Cat')
        r = c.post('/game/action', data={'action': 'propose', 'team': ['Ann', 'Bob', 'Cat']})
        assert r.status_code == 200
        lobby = dev_lobby('sorceress')
        assert lobby.current_game.controller.state.phase.value == 'voting'
        r = c.get('/dev/sorceress?as=Cat')
        lobby = dev_lobby('sorceress')
        assert lobby.current_game.controller.state.phase.value == 'proposing'
        assert c.get('/game/state').get_json()['you']['name'] == 'Cat'
        assert c.get('/dev/sorceress/as/host').headers['Location'] == '/host'
        assert 'Game in progress' in c.get('/host').get_data(as_text=True)
        assert c.get('/dev/sorceress/as/Nobody').status_code == 404
    """, AVALON_DEV="1")


def test_testers_get_separate_games():
    run("""
        app.config['DEV_NO_AUTH'] = True
        a, b = app.test_client(), app.test_client()
        a.get('/dev/sorceress'); b.get('/dev/sorceress')
        a.get('/dev/sorceress/as/Cat')
        assert a.post('/game/action', data={'action': 'propose',
                                            'team': ['Ann', 'Bob', 'Cat']}).status_code == 200
        b.get('/dev/sorceress/as/Cat')
        assert a.get('/game/state').get_json()['phase'] == 'voting'
        assert b.get('/game/state').get_json()['phase'] == 'proposing'
        # Resetting one tester's game leaves the other's alone.
        b.get('/dev/sorceress')
        assert a.get('/game/state').get_json()['phase'] == 'voting'
        ids = {l.id for l in LOBBIES.active()}
        assert len([i for i in ids if i.endswith('-sorceress')]) == 2
    """, AVALON_DEV="1")


def test_feedback_email_has_scenario_and_full_state():
    out = run("""
        import json
        app.config['DEV_NO_AUTH'] = True
        sent = []
        app.config['DEV_SEND_EMAIL'] = lambda *a, **k: sent.append((a, k))
        c.get('/dev/quest-cards')
        c.get('/dev/quest-cards/as/Gus')
        c.post('/game/action', data={'action': 'play_card', 'card': 'Reversal'})
        assert 'Send feedback' in c.get('/dev/feedback?page=/').get_data(as_text=True)
        assert c.post('/dev/feedback', data={'description': ''}).status_code == 400
        r = c.post('/dev/feedback', data={'description': 'Reversal looks odd\\nmore', 'page': '/'})
        assert r.status_code == 200 and 'was sent' in r.get_data(as_text=True)
        (to, subject, body), kw = sent[0]
        assert to == 'dev@example.com' and kw['sender'] == 'dev@example.com'
        assert 'Choosing quest cards' in subject and 'Reversal looks odd' in subject
        report = json.loads(body.split('Full report (JSON):')[1])
        assert report['scenario']['slug'] == 'quest-cards' and report['viewing_as'] == 'Gus'
        g = report['game']
        assert g['phase'] == 'quest' and g['roles']['Gus'] == 'Maelegant'
        assert g['secret']['current_quest_cards'] == {'Gus': 'Reversal'}
        assert any(e['type'] == 'quest_started' for e in g['log'])
        # A page off this site isn't used as a link.
        r = c.get('/dev/feedback?page=https://evil.example')
        assert 'evil.example' not in r.get_data(as_text=True)
        print('ok')
    """, AVALON_DEV="1", DEV_FEEDBACK_EMAIL="dev@example.com")
    assert "ok" in out


def test_changed_rules_scenario_uses_its_rules():
    run("""
        app.config['DEV_NO_AUTH'] = True
        c.get('/dev/changed-rules')
        game = dev_lobby('changed-rules').current_game
        assert game.ruleset['Merlin.sees.Mordred'] and game.controller.state.rules == game.ruleset
        kinds = game.controller.available_actions('Eve')['assassinate']['kinds']
        assert kinds == ['merlin', 'nilrem', 'lovers', 'percival'], kinds
        c.get('/dev/changed-rules/as/Ann')
        page = c.get('/').get_data(as_text=True)
        # The Role tab shows the rules as they are in this game, changes marked.
        assert 'Rules for Merlin' in page and 'In this game' not in page
        assert 'class="rule-changed">Sees every Evil player.' in page
        # The rules page shows the usual rules, with the changes on top.
        rules_page = c.get('/rules/merlin').get_data(as_text=True)
        assert 'In your current game' in rules_page
        assert 'Sees every Evil player except' in rules_page and 'rule-changed' not in rules_page
        # The tap-preview sheet gets the game's changes.
        assert ' sees these roles as Evil' in page.split('const GAME_NOTES')[1]
    """, AVALON_DEV="1")


def test_feedback_without_email_setting_is_not_lost_silently():
    run("""
        app.config['DEV_NO_AUTH'] = True
        assert 'Send feedback' not in c.get('/dev/feedback').get_data(as_text=True)
        assert c.post('/dev/feedback', data={'description': 'x'}).status_code == 503
    """, AVALON_DEV="1")


def test_dev_gareth_has_a_knight_and_rival():
    run("""
        from web import dev
        nine = ["Merlin", "Percival", "Tristan", "Iseult", "Servant of Camelot",
                "Mordred", "Morgana", "Maelegant", "Gareth (Good)"]
        b = dev.make_builder(list("ABCDEFGHI"), nine)
        g = next(r for r in b.role_to_player if str(r) == "Gareth")
        assert (g.team, g.knight, g.rival) == ("Good", "A", "F"), (g.team, g.knight, g.rival)
        g = next(r for r in dev.make_builder(list("ABCDEFGHI"), nine[:-1] + ["Gareth"])
                 .role_to_player if str(r) == "Gareth")
        assert (g.team, g.knight, g.rival) == ("Evil", "F", "A")
        print('ok')
    """, AVALON_DEV="1")
