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
            'six-players': ('first_round_voting', 'Fay', 'vote_first_round'),
            'five-players': ('voting', 'Eve', 'vote'),
            'hammer-morgana': ('proposing', 'Fay', 'propose'),
            'lonely-roles': ('first_round_proposing', 'Ann', 'propose_first_round'),
            'guinevere-court': ('first_round_proposing', 'Ann', 'propose_first_round'),
            'colgrevance-oberon': ('first_round_proposing', 'Ann', 'propose_first_round'),
            'balin-agravaine': ('first_round_proposing', 'Ann', 'propose_first_round'),
            'sorceress-reversed': ('proposing', 'Fay', 'propose'),
            'changeling-used': ('team_announced', 'Ann', 'ready'),
            'strong-remove-reversal': ('inquisition', 'Cat', 'inquisition'),
            'inquisition-order': ('inquisition', 'Dan', 'inquisition'),
            'reversal-results': ('proposing', 'Fay', 'propose'),
            'reversal-betrayal': ('result', 'Eve', 'betray'),
            'gawain-exiled': ('inquisition', 'Dan', 'inquisition'),
            'gawain-after-removal': ('reveal', 'Dan', 'gawain'),
            'beast-late-game': ('quest', 'Gus', 'play_card'),
            'lady-chain-gareth': ('lady', 'Ivy', 'lady'),
            'pellinore-evil-wins': ('pellinore_guess', 'Gus', 'pellinore_guess'),
            'assassin-without-mordred': ('assassination', 'Eve', 'assassinate'),
            'good-wins': ('game_over', None, None),
            'evil-wins-assassination': ('game_over', None, None),
            'changed-abilities': ('quest', 'Eve', 'play_card'),
            'changed-info': ('quest', 'Ann', 'play_card'),
            'host-pause': ('reveal', 'Dan', 'gawain'),
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


def test_every_scenario_says_what_to_check():
    run("""
        from web import dev
        app.config['DEV_NO_AUTH'] = True
        assert len(dev.SCENARIOS) <= 50
        for sc in dev.SCENARIOS:
            assert len(sc.about) > 20 and len(sc.expect) > 40, sc.slug
        page = c.get('/dev/').get_data(as_text=True)
        assert page.count('Check:') == len(dev.SCENARIOS)
        c.get('/dev/gawain')
        assert 'What to check' in c.get('/').get_data(as_text=True)
    """, AVALON_DEV="1")


def test_scenarios_lead_where_they_say():
    """Plays each chain scenario on and checks what its "expect" text promises."""
    run("""
        import copy
        from web import dev
        app.config['DEV_NO_AUTH'] = True
        def fresh(slug):
            c.get('/dev/' + slug)
            ctl = dev_lobby(slug).current_game.controller
            return ctl, ctl.state
        def info_of(slug):
            game = dev_lobby(slug).current_game
            return {i['role']: i.info for i in game.player_info.values()}

        ctl, s = fresh('six-players')
        b = copy.deepcopy(ctl); b.act('Fay', 'vote_first_round', proposer='Bob')
        assert b.state.current_quest.team == ['Bob', 'Cat'] and b.state.proposals_per_round == 3
        assert b.state.double_fail_quest is None

        ctl, s = fresh('five-players')
        for p in s.seating: ctl.act(p, 'vote', approve=True)
        assert ctl.state.current_quest.inquisition is None

        ctl, s = fresh('hammer-morgana')
        assert 'sorceress' not in ctl.available_actions('Fay') and s.is_hammer()
        ctl.act('Fay', 'propose', team=['Ann', 'Bob', 'Cat'])
        assert ctl.state.phase.value == 'quest' and ctl.state.current_quest.inquisition is None

        ctl, s = fresh('sorceress-reversed')
        for leader in ('Fay', 'Eve'):
            assert ctl.state.leader == leader
            ctl.act(leader, 'propose', team=['Ann', 'Bob', 'Cat'])
            for p in s.seating: ctl.act(p, 'vote', approve=False)
        assert ctl.state.leader == 'Dan' and ctl.state.is_hammer()

        ctl, s = fresh('changeling-used')
        assert s.current_proposal.team == ['Ann', 'Bob', 'Gus'] and not s.ready
        assert 'changeling' not in ctl.available_actions('Gus')

        ctl, s = fresh('strong-remove-reversal')
        def outcome(target, remove):
            b = copy.deepcopy(ctl); b.act('Cat', 'inquisition', target=target, remove=remove)
            return b.state.quests[-1].succeeded
        assert outcome('Ivy', True) is False and outcome('Gus', True) is False
        assert outcome('Ann', True) is True and outcome('Gus', False) is True

        ctl, s = fresh('inquisition-order')
        assert s.current_quest.inquisition == 'weak' and not s.strong_used

        ctl, s = fresh('reversal-results')
        assert [q.succeeded for q in s.quests] == [True, True, False, False]
        assert s.round == 5 and s.leader == 'Fay'

        ctl, s = fresh('reversal-betrayal')
        ctl.act('Eve', 'betray'); ctl.state.advance()
        assert ctl.state.phase.value == 'game_over' and ctl.state.outcome['winner'] == 'Evil'

        ctl, s = fresh('gawain-exiled')
        assert s.gawain_exiled and s.current_quest.inquisition == 'weak'
        ctl.act('Dan', 'inquisition', target='Ann')
        assert ctl.state.quests[-1].succeeded is False and ctl.state.round == 4

        ctl, s = fresh('gawain-after-removal')
        assert ctl.available_actions('Dan')['gawain']['choices'] == ['Ann', 'Hal', 'Cat']
        ctl.act('Dan', 'gawain', target='Hal')
        assert ctl.state.gawain_exiled
        ctl.state.advance()
        assert ctl.state.phase.value == 'result'      # Agravaine (Jon) might betray

        ctl, s = fresh('beast-late-game')
        assert ctl.available_actions('Gus')['play_card']['cards'] == ['Fail']
        dev.Drive(ctl).cards()
        assert ctl.state.quests[-1].qbwh_counts_as == 'Success'
        assert ctl.state.phase.value == 'pellinore_guess'

        ctl, s = fresh('lady-chain-gareth')
        assert s.lady_uses[0]['team'] == 'Good' and s.allegiance('Ivy') == 'Evil'
        assert 'Bob' not in s.lady_choices() and 'Ivy' not in s.lady_choices()

        ctl, s = fresh('pellinore-evil-wins')
        for guess, pell, beast in (('Hal', True, False), ('Ann', False, True)):
            b = copy.deepcopy(ctl); b.act('Gus', 'pellinore_guess', target=guess)
            n = b.state.outcome['neutrals']
            assert b.state.phase.value == 'game_over' and b.state.assassination is None
            assert (n['Pellinore']['won'], n['The Questing Beast']['won']) == (pell, beast)

        ctl, s = fresh('assassin-without-mordred')
        assert s.assassin() == 'Eve'
        b = copy.deepcopy(ctl); b.act('Eve', 'assassinate', kind='none')
        assert b.state.outcome['winner'] == 'Evil'
        b = copy.deepcopy(ctl); b.act('Eve', 'assassinate', kind='merlin', targets=['Ann'])
        assert b.state.outcome['winner'] == 'Good'

        assert fresh('good-wins')[1].outcome['winner'] == 'Good'
        assert fresh('evil-wins-assassination')[1].outcome['winner'] == 'Evil'

        ctl, s = fresh('changed-abilities')
        assert ctl.available_actions('Eve')['play_card']['cards'] == ['Success', 'Fail']
        assert ctl.available_actions('Gus')['play_card']['cards'] == ['Success', 'Fail']
        assert 'proclaim' in ctl.available_actions('Bob')

        ctl, s = fresh('changed-info')
        dev.Drive(ctl).cards()
        assert ctl.state.phase.value == 'game_over' and ctl.state.outcome['winner'] == 'Good'
        info = info_of('changed-info')
        assert 'nilrem' not in info['Guinevere'] and info['Guinevere']['seen'] == ['Dan']
        assert 'Hal' in info['Mordred']['other_evils'] and not info['Mordred']['oberon']
        assert info['Oberon']['other_evils'] == []

        fresh('lonely-roles')
        info = info_of('lonely-roles')
        assert info['Galahad']['nilrem'] == 'Ann' and 'nilrem' not in info['Mordred']
        assert info['Uther']['stalked_good'] in ('Bob', 'Dan')
        assert info['Ygraine']['stalked_evil'] in ('Fay', 'Gus')

        fresh('guinevere-court')
        info = info_of('guinevere-court')
        assert sorted(info['Guinevere']['seen']) == ['Dan', 'Eve', 'Hal']
        assert sorted(info['Merlin']['seen']) == ['Dan', 'Gus', 'Hal']

        fresh('colgrevance-oberon')
        info = info_of('colgrevance-oberon')
        assert {p: str(r) for p, r in info['Colgrevance']['evil_roles'].items()} == \\
            {'Gus': 'Mordred', 'Ivy': 'Oberon', 'Jon': 'Morgana'}
        assert 'Ivy' not in info['Mordred']['other_evils'] and info['Mordred']['oberon']

        fresh('balin-agravaine')
        info = info_of('balin-agravaine')
        assert info['Balin the Savage']['agravaine'] == 'Hal' and info['Agravaine']['balin'] == 'Cat'
        assert 'Cat' in info['Merlin']['seen']

        ctl, s = fresh('host-pause')
        assert ctl.undo_label() == 'Jon pressed ready'
        print('ok')
    """, AVALON_DEV="1")


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


def test_round2_starter_shown_all_through_round_1():
    """Who proposes first in round 2 is public and matters for the round-1 vote."""
    run("""
        from web import dev
        app.config['DEV_NO_AUTH'] = True
        for slug in ('start', 'first-round-vote'):
            c.get('/dev/' + slug + '?as=Dan')
            panels = c.get('/game/panels').get_json()
            text = ' '.join(v for v in panels.values() if isinstance(v, str))
            assert 'proposes first in round 2' in text, slug
        # Everyone votes (as themselves) for Ann's team: the round-1 quest starts.
        for p in dev.PLAYER_NAMES[:7]:
            c.get('/dev/first-round-vote/as/' + p)
            assert c.post('/game/action', data={'action': 'vote_first_round',
                                                'proposer': 'Ann'}).status_code == 200
        assert dev_lobby('first-round-vote').current_game.controller.state.phase.value == 'quest'
        text = ' '.join(v for v in c.get('/game/panels').get_json().values() if isinstance(v, str))
        assert 'proposes first in round 2' in text
    """, AVALON_DEV="1")
