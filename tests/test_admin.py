"""Admin pages (admin.py) and the host's create / close lobby.  Run: python -m pytest"""
import os
import re
import subprocess
import sys
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def web():
    import webapp
    webapp.LOBBIES.store.redis.flushdb()
    webapp.app.config.update(TESTING=True, DEV_FAKE_PLAYERS=0, ADMIN_NO_AUTH=True)
    yield webapp
    webapp.app.config["ADMIN_NO_AUTH"] = False


def new_game(web, name="Camelot", players=("Ann", "Bob", "Cat", "Dan", "Eve"), start=True):
    host = web.app.test_client()
    assert host.post("/host/create", data={"game_name": name}).status_code == 302
    lobby = next(l for l in web.LOBBIES.active() if l.name == name)
    clients = {}
    for p in players:
        c = web.app.test_client()
        c.post("/register", data={"player": p})
        c.get(f"/join/{lobby.id}")
        clients[p] = c
    if start:
        r = host.post("/restart", data={"items": ["Merlin", "Percival", "Morgana", "Mordred",
                                                  "Tristan", "Iseult"]})
        assert r.status_code == 302
    return host, web.LOBBIES.get(lobby.id), clients


def csrf(client):
    page = client.get("/admin/").get_data(as_text=True)
    return re.search(r'name="csrf" value="([^"]+)"', page).group(1)


# ---- host: create and close ----

def test_host_page_offers_to_create_a_lobby_instead_of_making_one(web):
    host = web.app.test_client()
    page = host.get("/host").get_data(as_text=True)
    assert "Create lobby" in page and web.LOBBIES.active() == []
    name = re.search(r'name="game_name"[^>]*value="([^"]*)"', page).group(1)
    assert name in web.GAME_NAMES
    # Starting a game or renaming without a lobby doesn't make one either.
    host.post("/restart", data={"items": ["Merlin"]})
    host.post("/host", data={"game_name": "X"})
    assert web.LOBBIES.active() == []
    assert host.post("/host/create", data={"game_name": "My game"}).status_code == 302
    assert [l.name for l in web.LOBBIES.active()] == ["My game"]
    assert "Close lobby" in host.get("/host").get_data(as_text=True)


def test_creating_with_a_taken_name_fails(web):
    new_game(web, "Camelot", start=False)
    other = web.app.test_client()
    r = other.post("/host/create", data={"game_name": "Camelot"})
    assert r.status_code == 400 and "already taken" in r.get_data(as_text=True)
    assert other.post("/host/create", data={"game_name": "  "}).status_code == 400
    assert len(web.LOBBIES.active()) == 1


def test_host_closes_their_lobby(web):
    host, lobby, players = new_game(web)
    assert host.post("/host/close").status_code == 302
    assert web.LOBBIES.get(lobby.id) is None and web.LOBBIES.active() == []
    assert "Create lobby" in host.get("/host").get_data(as_text=True)
    # Players are back to choosing a game.
    assert "Nobody is hosting" in players["Ann"].get("/").get_data(as_text=True)


# ---- admin ----

def test_admin_lists_and_closes_lobbies(web):
    _, a, _ = new_game(web, "Camelot")
    _, b, _ = new_game(web, "Avalon", players=("Fay",), start=False)
    admin = web.app.test_client()
    page = admin.get("/admin/").get_data(as_text=True)
    assert "Camelot" in page and "Avalon" in page
    # Forms need the page's token.
    assert admin.post(f"/admin/lobby/{a.id}/close").status_code == 400
    assert web.LOBBIES.get(a.id) is not None
    r = admin.post(f"/admin/lobby/{a.id}/close", data={"csrf": csrf(admin)})
    assert r.status_code == 302 and web.LOBBIES.get(a.id) is None
    assert [l.name for l in web.LOBBIES.active()] == ["Avalon"]


def test_admin_closes_idle_lobbies(web):
    _, a, _ = new_game(web, "Camelot", start=False)
    _, b, _ = new_game(web, "Avalon", start=False)
    # Camelot was last touched 3 hours ago.
    web.LOBBIES.store.redis.expire(web.LOBBIES._key(a.id), web.LOBBIES.max_idle_seconds - 3 * 3600)
    admin = web.app.test_client()
    assert "3 h 00 min" in admin.get("/admin/").get_data(as_text=True)
    admin.post("/admin/close-idle", data={"csrf": csrf(admin), "hours": "2"})
    assert [l.name for l in web.LOBBIES.active()] == ["Avalon"]


def test_admin_lobby_page_and_changes(web):
    host, lobby, players = new_game(web)
    admin = web.app.test_client()
    token = csrf(admin)
    page = admin.get(f"/admin/lobby/{lobby.id}").get_data(as_text=True)
    assert "Merlin" in page and "Full state" in page and "Ann" in page
    admin.post(f"/admin/lobby/{lobby.id}/rename", data={"csrf": token, "name": "Tintagel"})
    assert web.LOBBIES.get(lobby.id).name == "Tintagel"
    ann = next(u for u, n in lobby.snapshot().items() if n == "Ann")
    admin.post(f"/admin/lobby/{lobby.id}/remove", data={"csrf": token, "uuid": ann})
    assert ann not in web.LOBBIES.get(lobby.id)
    assert "left the lobby" in admin.get(f"/admin/lobby/{lobby.id}").get_data(as_text=True)
    # Undo with nothing to undo is an error message, not a crash.
    r = admin.post(f"/admin/lobby/{lobby.id}/undo", data={"csrf": token})
    assert r.status_code == 302
    assert admin.post(f"/admin/lobby/nope/rename", data={"csrf": token, "name": "x"}).status_code == 404


def test_admin_views_as_a_player_and_comes_back(web):
    host, lobby, players = new_game(web)
    admin = web.app.test_client()
    admin.post("/register", data={"player": "Boss"})
    with admin.session_transaction() as s:
        me = s["player_id"]
    roles = {n: lobby.current_game[u]["role"] for u, n in lobby.snapshot().items()}
    cat = next(u for u, n in lobby.snapshot().items() if n == "Cat")
    r = admin.get(f"/admin/lobby/{lobby.id}/as/{cat}")
    assert r.status_code == 302
    page = admin.get("/").get_data(as_text=True)
    assert "admin-bar" in page and "Back to admin" in page
    state = admin.get("/game/state").get_json()
    assert state["you"]["name"] == "Cat" and state["you"]["role"] == roles["Cat"]
    # As the host.
    admin.get(f"/admin/lobby/{lobby.id}/as/host")
    assert "Game in progress" in admin.get("/host").get_data(as_text=True)
    assert admin.get(f"/admin/lobby/{lobby.id}/as/nobody").status_code == 404
    # Back to being yourself.
    admin.get("/admin/stop")
    with admin.session_transaction() as s:
        assert s["player_id"] == me and s["name"] == "Boss" and "admin_as" not in s
    assert "admin-bar" not in admin.get("/").get_data(as_text=True)


# ---- access (decided at import, so in a fresh process) ----

def run(code, **env):
    env = {**{k: v for k, v in os.environ.items()
              if k not in ("AVALON_DEV", "CF_ACCESS_TEAM_DOMAIN", "ADMIN_ACCESS_AUD",
                           "ADMIN_EMAILS")}, **env}
    prelude = "import sys; sys.path.insert(0, '.'); import webapp\n" \
              "app = webapp.app; app.config.update(TESTING=True)\nc = app.test_client()\n"
    r = subprocess.run([sys.executable, "-c", prelude + textwrap.dedent(code)],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout


def test_admin_without_settings_needs_a_cloudflare_access_token():
    """No settings: any validly signed Access token gets in (Cloudflare's
    policy decides who), nothing else does."""
    out = run("""
        import json, time, jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk['kid'] = 'k1'
        fetched = []
        def fetch(self):
            fetched.append(self.uri)
            return {'keys': [jwk]}
        jwt.PyJWKClient.fetch_data = fetch
        def token(signer=key, **claims):
            base = dict(aud=['whatever'], iss='https://myteam.cloudflareaccess.com',
                        email='boss@example.com', exp=time.time() + 60)
            return jwt.encode({**base, **claims}, signer, 'RS256', headers={'kid': 'k1'})
        def status(t):
            return c.get('/admin/', headers={'Cf-Access-Jwt-Assertion': t}).status_code
        print(c.get('/admin/').status_code,
              c.post('/admin/close-idle', data={'hours': '0'}).status_code,
              status('x.y.z'), status(token()), status(token(signer=other)),
              status(token(iss='https://evil.example.com')),
              status(token(exp=time.time() - 60)))
        assert set(fetched) == {'https://myteam.cloudflareaccess.com/cdn-cgi/access/certs'}
    """)
    assert out.split() == ["403", "403", "403", "200", "403", "403", "403"]


def test_admin_needs_a_valid_token_with_an_admin_email():
    out = run("""
        import json, time, jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk['kid'] = 'k1'
        jwt.PyJWKClient.fetch_data = lambda self: {'keys': [jwk]}
        def token(**claims):
            base = dict(aud=['aud'], iss='https://example.cloudflareaccess.com',
                        email='boss@example.com', exp=time.time() + 60)
            return jwt.encode({**base, **claims}, key, 'RS256', headers={'kid': 'k1'})
        def status(t):
            return c.get('/admin/', headers={'Cf-Access-Jwt-Assertion': t}).status_code
        print(status(token()), status(token(email='Boss@Example.com')),
              status(token(email='player@example.com')), status(token(aud=['other'])),
              status(token(exp=time.time() - 60)), c.get('/admin/').status_code)
        # The rest of the site doesn't need a token.
        assert c.get('/host').status_code == 200
    """, CF_ACCESS_TEAM_DOMAIN="example.cloudflareaccess.com", ADMIN_ACCESS_AUD="aud",
        ADMIN_EMAILS="boss@example.com, other@example.com")
    assert out.split() == ["200", "200", "403", "403", "403", "403"]
