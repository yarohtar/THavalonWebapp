"""Tests for the dev site's test scenarios (dev.py).  Run: python -m pytest

Each check runs in a fresh Python process, because whether dev features
exist is decided when webapp is imported (AVALON_DEV)."""
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(code, **env):
    env = {**{k: v for k, v in os.environ.items()
              if k not in ("AVALON_DEV", "CF_ACCESS_AUD", "CF_ACCESS_TEAM_DOMAIN",
                           "DEV_ALLOWED_EMAILS")}, **env}
    prelude = "import sys; sys.path.insert(0, '.'); import webapp\n" \
              "app = webapp.app; app.config.update(TESTING=True)\nc = app.test_client()\n"
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
        import dev
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
        import dev
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
            'host-votes': ('proposing', 'Cat', 'propose'),
        }
        assert set(expected) == set(dev.BY_SLUG)
        for slug, (phase, player, action) in expected.items():
            r = c.get('/dev/' + slug)
            assert r.status_code == 302, slug
            page = c.get(r.headers['Location'])
            assert page.status_code == 200 and 'dev-bar' in page.get_data(as_text=True), slug
            ctl = webapp.LOBBIES.get('dev-' + slug).current_game.controller
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
        ctl = webapp.LOBBIES.get('dev-strong-inquisition').current_game.controller
        assert ctl.available_actions('Cat')['inquisition']['can_remove']
        c.get('/dev/questing-beast')
        ctl = webapp.LOBBIES.get('dev-questing-beast').current_game.controller
        assert ctl.available_actions('Hal')['play_card']['cards'] == ['Questing Beast Was Here']
    """, AVALON_DEV="1")


def test_switching_player_and_reset():
    run("""
        app.config['DEV_NO_AUTH'] = True
        c.get('/dev/sorceress')
        ctl = webapp.LOBBIES.get('dev-sorceress').current_game.controller
        assert c.get('/dev/sorceress/as/Ann').headers['Location'] == '/'
        state = c.get('/game/state').get_json()
        assert state['you']['name'] == 'Ann' and state['you']['role'] == 'Merlin'
        # Ann can't act for Cat; Cat proposes, then a reset puts it back.
        c.get('/dev/sorceress/as/Cat')
        r = c.post('/game/action', data={'action': 'propose', 'team': ['Ann', 'Bob', 'Cat']})
        assert r.status_code == 200
        lobby = webapp.LOBBIES.get('dev-sorceress')
        assert lobby.current_game.controller.state.phase.value == 'voting'
        r = c.get('/dev/sorceress?as=Cat')
        lobby = webapp.LOBBIES.get('dev-sorceress')
        assert lobby.current_game.controller.state.phase.value == 'proposing'
        assert c.get('/game/state').get_json()['you']['name'] == 'Cat'
        assert c.get('/dev/sorceress/as/host').headers['Location'] == '/host'
        assert 'Game in progress' in c.get('/host').get_data(as_text=True)
        assert c.get('/dev/sorceress/as/Nobody').status_code == 404
    """, AVALON_DEV="1")
