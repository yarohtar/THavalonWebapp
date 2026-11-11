# THavalon web app — handover notes for Claude

A Flask app for playing THavalon (an extended Resistance: Avalon) **in person**:
everyone sits at a table with their phone; the app deals roles, runs proposals,
votes, quest cards and abilities, and shows public state. The owner hosts games
for friends and playtests alone with bots (`tools/bots.py`).

- Live site: https://avalon.iammerlin.fyi
- Dev site (test scenarios, behind Cloudflare Access): https://avalon-dev.iammerlin.fyi/dev/
- Repo: github.com/yarohtar/THavalonWebapp, branch `master` (pushing deploys!)

## Code map

| File | What it is |
|---|---|
| `thavalon/` | **The game engine** (no web code; `tests/test_engine_independent.py` checks it). Overview in `thavalon/__init__.py`. |
| `thavalon/ruleset.py` | `RuleSet`: host-changeable rules (`SETTINGS` registry: player counts, lonely counts, who sees whom, Gareth, cards/abilities, Assassination). Stores only changes from the defaults. |
| `thavalon/roles.py` | Roles (identified by `name`) and the info each is told (`get_info(deal)`); lonely transformations. |
| `thavalon/dealing.py` | Defaults (Evil count, team sizes, double-Fail quest), `generate_roles`, `AvalonBuilder` (a deal; `AvalonBuilder.with_roles({...})` for a fixed deal). Randomness from `rng` (default: the `random` module). |
| `thavalon/cards.py`, `assassination.py`, `scoring.py`, `errors.py` | Quest results (Reversal, QBWH); assassin ranking and guesses; Neutral scores; `RuleError`/`NotAllowed`. |
| `web/` | **The website** (overview in `web/__init__.py`). Templates and static files are in `web/templates/`, `web/static/`. |
| `web/app.py` | The Flask app: secret key, session identity (`g.uuid`, `g.name`), registration check, template globals, blueprints, dev/admin. `wsgi.py` imports it; `python -m web.app` runs it locally. |
| `web/routes/` | Blueprints: `player` (start page, join, register, `/donotread`), `host` (host page, create/close, restart, save, host game commands), `play` (`/game/*` JSON: panels, state, actions, host votes), `rules` (rules pages). Endpoints are `blueprint.name`, e.g. `url_for('host.page')`. |
| `web/lobbies.py` | `Lobby`, `Lobbies` (Redis-backed; `LOBBIES`), `close_lobby`, lobby names. |
| `web/games.py` | `AvalonGame` (a lobby's game: deal, role info, controller, host votes), `RoleInfo`, `GameSettings` (host's game settings, `resolve()`). |
| `web/panels.py` | Rendering: `role_page()`, `panels()` (Game/Role/Vote tabs, host panel), `vote_status()` (drives the Vote tab). |
| `web/visitor.py` | This browser's lobby/game: `joined_lobby`, `join`, `my_lobby`, `playing_lobby`, `viewer_game`. |
| `web/host_settings.py` | Host preferences in the cookie (`pref_*`, `save_*`) and the rules editor: `HOST_GROUPS` lists every setting once under its role with its wording (`entry()`), `ruleset_from_form`. |
| `web/host_votes.py` | `HostVote`: votes the host starts by hand as a fallback when the game flow breaks. Never touch `GameState`. |
| `web/rules/` | `pages.py`: the term registry (`TERMS`, one per role/rule; each term's page), `[[Term]]` link markup and `expand()`; `notes.py`: a `RuleSet`'s changes as sentences tagged with rules pages (also the preview sheet's JSON); `role_text.py`: helpers for role rules templates rendered under a game's `RuleSet` (Role tab); `wording.py`: shared phrasing helpers. |
| `web/store.py` | Redis connection + `Store` (pickled objects, optimistic `WATCH` transactions); `MOVED` maps old pickled class homes. |
| `web/events.py` | Live updates: Server-Sent Events over Redis Streams (`events.publish(channel, event)`). |
| `web/dev.py` | Dev-site-only features: test scenarios, "view as" switching, Access login check, feedback emails. |
| `web/admin.py` | Admin pages `/admin` (all sites): list/inspect/change/close lobbies, close idle ones, "view as" any player or host under `/admin/as/<lobby>/<who>/…` (WSGI middleware sets the prefix as SCRIPT_NAME; those requests get a throwaway session, nothing saved). |
| `web/access.py` | `AccessCheck`: verifies Cloudflare Access JWTs (dev site and admin). |
| `web/templates/role.html` | Player page: **Game / Role / Vote** tabs, tab switching and Vote-tab auto-open logic. |
| `web/templates/game/` | Live panels: `panel.html` (Game tab), `abilities.html` (Role tab, private), `vote.html` (Vote tab), `host_panel.html`, shared `_now.html` / `_macros.html`. |
| `web/static/game.js` | Fetches/re-renders panels on `game-update`, submits `form.game-action`, keeps ticked players across re-renders, fires `panels-rendered`. |
| `web/static/events.js` | SSE client (`Events.on`, `Events.reloadOn`). |
| `tools/bots.py` | Bot players (also vote in host votes). `python tools/bots.py 6 --url https://avalon.iammerlin.fyi --game NAME` |

## How things work (and rules to keep)

- **Storage is Redis.** `LOBBIES.get()/active()/hosted_by()` return *copies*. Change a lobby
  only with `LOBBIES.update(lobby_id, fn)`; `fn` may run several times (retries on conflict),
  so it must be side-effect free — publish events (`new_event(...)`) *after* it returns.
  Idle lobbies expire after 12 h.
- **Pickles depend on class code.** If a change makes old stored games unloadable, bump
  `SCHEMA` in `web/store.py` (old games are then ignored, not crashing). Adding a new attribute to
  a stored class usually needs a class-level default so old pickles still work. Renaming a
  stored class's attributes breaks old pickles. A module that moves goes into
  `web.store.MOVED` (the old top-level engine and web modules are there;
  `tests/test_old_pickles.py` loads a game and a lobby pickled before the moves).
- **Engine behaviour is pinned** by `tests/test_golden.py`: digests of deals, role info and
  every step of 150 random games (`tests/golden_engine.json`). A refactor must keep it green;
  for an intended behaviour change, regenerate with
  `PYTHONHASHSEED=0 python tests/golden_engine.py --write` and say so in the commit.
- **redis-py 8 has a hidden 5 s default read timeout.** `store.connect()` sets
  `socket_timeout=60`; it must stay above `events.HEARTBEAT_SECONDS` (15) or every quiet
  live-update stream errors out. (This broke production once.)
- **Without `REDIS_URL`** the app uses in-process `fakeredis` (local runs, tests); then only
  one process.
- **Session key:** `SECRET_KEY` signs session cookies (they hold player id / host identity).
  Each site has its own random key in its root-only env file on the server (never print or
  read it; generate with `secrets.token_hex(32)` piped straight into the file). With
  `REDIS_URL` set the app refuses to start without it; locally a random per-run key is used.
  Changing a key logs everyone out (and they lose their seat in running games).
- **Secrets:** views must never leak cards, votes before a vote completes, or roles. Abilities
  live on the Role tab so nobody sees them over a shoulder. Card buttons on the Vote tab sit in a
  collapsed `<details>` because the allowed cards reveal the role.
- **Vote tab:** `vote_status()` gives each player a key for the votes they're in (prefixed with
  the game number) and whether they still must vote; `role.html` opens the Vote tab once per new
  key and returns to the Game tab when their votes end. Game votes and host votes use the same
  screen; host votes don't change the game and offer every card (Success/Fail/Reversal, plus
  QBWH if the Beast is possible) to everyone — players are trusted.
- **Inquisition / Gawain results** show immediately in the reveal/result pauses
  (`inquisition_notes` macro).
- **Rule settings:** the host edits rules per role on the host page (fields `rule:<key>`,
  `web.host_settings.ruleset_from_form`); saved in the host's cookie (`host_prefs['rules']`, only changes).
  A game's `RuleSet` lives on `AvalonGame.ruleset`, `AvalonBuilder.rules` and
  `GameState.rules` (class-level defaults keep old pickles loading). **Default rules must
  behave exactly as before**: checked by comparing deals/role info/random-game logs over many
  seeds with `PYTHONHASHSEED=0` (now `tests/test_golden.py`), and by
  `tests/test_rule_settings.py`. New setting = entry in `thavalon/ruleset._settings()` (key,
  kind, default, choices: no wording), the engine/role code reading it, its entry with wording under its role in
  `web.host_settings.HOST_GROUPS` (checked at import), a note in
  `web.rules.notes.game_notes`, and the role's rules template if it changes that text (tests
  check every setting is on the host page once and produces a note).
- **Rules pages** show the usual (default) rules, with the viewer's current game's changes
  in a box at the top (`viewer_game()`). The **Role tab** instead renders the role's rules
  template with the game's `RuleSet` ("Rules for X", changed lines tagged "changed"): role
  templates in `web/templates/rules/` read `ruleset` (helpers in `web/rules/role_text.py` and
  `rules/_lines.html`) and must give exactly the usual text under the default rules (tested).
  The tap-preview sheet lists the game's changes for the term's page (`term_ruleset` passed by
  the role, rules and host pages → `game_notes_json`). The game summary lists them too.

## Admin pages (`web/admin.py`)

- Protected by a Cloudflare Access self-hosted application on `avalon.iammerlin.fyi/admin`
  (the owner's policy). No server settings needed: the app only checks each request carries a
  validly signed Access token (`access.email_from_any_team`). Optionally `CF_ACCESS_TEAM_DOMAIN`
  + `ADMIN_ACCESS_AUD` pin the application and `ADMIN_EMAILS` the emails. POST forms carry a
  session CSRF token. Locally (`python -m web.app`) `ADMIN_NO_AUTH` skips the check.
- View-as pages must build links with `url_for` (keeps the prefix); the admin bar uses plain
  paths on purpose. Game actions there are real; host preferences changed there are dropped
  (the admin's own cookie is never touched). View-as POSTs need `Sec-Fetch-Site: same-origin`.
- Closing a lobby (`web.lobbies.close_lobby`, also the host page's "Close lobby") deletes it and
  publishes `new-game`/`new-player` on its channel and `new-lobby` on `lobbies`.
- `/host` no longer creates a lobby by itself: it shows a "Create lobby" form (`host_create.html`)
  with a free random name; `/host/create` creates it.

## Dev site (`web/dev.py`)

- Only active with `AVALON_DEV=1`. The live site must not expose it (`/dev` → 404; tested).
- `/dev/` lists ~22 scenarios (`changed-rules` and `gareth-changed-rules` use changed rules; a "Gareth" group) (`SCENARIOS`), each a game driven to a situation by `Drive`.
  Opening one (or ↺ Reset) rebuilds it. The purple bar switches "view as" any player or host —
  it literally makes the browser session that player. Each tester (session id `dev_tester`)
  gets their own copies, so testers never share games.
- `make_builder` deals roles exactly as listed (no lonely transformations), so pick valid
  combos. Gareth is listed as `"Gareth (Good)"`/`"Gareth (Evil)"`: Knight = first player of
  that team, Rival = first of the other. Player-count limits: Guinevere 7+, Gareth / Pellinore / Questing Beast exactly 9,
  Gawain 10. Inquisition depends on Evil count (proposals = Evil + 1: 4 → weak, 5 → strong).
- Access: Cloudflare Access decides who gets in (the owner adds playtesters in the Access
  policy). The app additionally verifies the Access JWT for this application's audience, and
  refuses everything if `CF_ACCESS_*` aren't set. `DEV_ALLOWED_EMAILS` is optional (empty).
- Feedback (✎ in the bar) emails the description plus the scenario, viewer, page and the game's
  full state (incl. secrets) via SES. Recipient/sender come from env, not the repo.
- Local: `AVALON_DEV=1 python -m web.app` → http://127.0.0.1:5000/dev/ (no login check locally).

## Running and testing locally

- Conda env `avalon` (Python 3.14): `conda run -n avalon python -m pytest -q` (~320 tests, ~80 s;
  the golden test takes half of that). Engine test helpers are in `tests/helpers.py`.
- `tests/test_dev.py` runs each check in a fresh subprocess (dev features are decided at import).
- `tests/test_store.py` also runs against a real Redis if `TEST_REDIS_URL` is set (no Redis
  server is installed locally; a throwaway one can be made with conda-forge `redis-server`).
- Node is installed via nvm but isn't on non-login shells' PATH:
  `~/.nvm/versions/node/v26.13.0/bin/node --check web/static/game.js`. Inline scripts in templates
  can be extracted and checked the same way.
- The Vote-tab switching has been checked with a fake-DOM simulation in node, not yet in a
  real browser.

## Deploying and the server

- **Push to `master` = deploy.** GitHub Actions (`.github/workflows/deploy.yml`) SSHes through
  the Cloudflare tunnel with a key restricted to `server-update.sh`, which does
  `git reset --hard origin/master`, `pip install -r requirements.txt`, restarts `avalon` and
  `avalon-dev`. Takes ~1 min; watch with `gh run list --workflow deploy.yml -L 1`.
  Games survive deploys now (Redis).
- Server: EC2, Amazon Linux 2023, 916 MB RAM. SSH alias `merlin` (`ssh merlin '...'`, goes
  through `cloudflared access`). Checkout `/var/www/avalon/THavalonWebapp`, venv
  `/var/www/avalon/venv`.
- Services (systemd):
  - `avalon`: port 8000, `REDIS_URL=redis://localhost:6379/0`, 2 workers (from `gunicorn.conf.py`),
    `EnvironmentFile=/etc/avalon.env` (SECRET_KEY).
  - `avalon-dev`: port 8001, `AVALON_DEV=1`, `REDIS_URL=…/1`, 1 worker,
    `EnvironmentFile=/etc/avalon-dev.env` (SECRET_KEY, CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD,
    DEV_ALLOWED_EMAILS, DEV_FEEDBACK_EMAIL, DEV_FEEDBACK_FROM). Restart after editing it.
  - `redis6`: localhost only, append-only file on. Inspect with `redis6-cli -n 0 --scan`.
  - Also on this server (not ours): `maths.iammerlin.fyi` (nginx :80) and `maths-feedback`.
- **The Cloudflare tunnel is managed from the dashboard**, not `/etc/cloudflared/config.yml`
  (its local `ingress` is ignored). New hostnames: Zero Trust → Networks → Tunnels → `merlin`
  → Public Hostname. Cloudflare free SSL covers one subdomain level only
  (`avalon-dev.iammerlin.fyi`, not `dev.avalon.…`). There is no Cloudflare API access from
  here — ask the owner to do dashboard steps.
- **Email:** SES through the `aws` CLI with the instance role `maths-feedback-ses` (can send,
  can't list/inspect). Domain `iammerlin.fyi` is verified; dev feedback comes from
  `avalon-feedback@iammerlin.fyi`. Services' PATH is only the venv, so code locates `aws`
  explicitly. New senders may land in Gmail spam at first.
- Permissions in this environment: creating systemd units / large server setup scripts and
  reading local credential/token files have been blocked by the auto-mode classifier; small
  `sudo` edits and restarts have worked. When blocked, write a script for the owner to run
  (`! ssh merlin 'bash -s' < script.sh`).

## Working with the owner

- Pushing to `master` deploys to the live site — fine when they ask to upload/deploy; check
  `/games` on the live site for players in a game before restarting anything.
- Never commit the owner's email or other personal details (the repo is on GitHub); keep such
  values in server env files.
- Role-design ideas must suit in-person play and small (5–6) games; see the
  `role-design-constraints` memory.

## Open items / known loose ends

- Old service backups on the server: `/etc/systemd/system/avalon*.service.bak` (deletable).
- SELinux logs AVC "denied name_connect … redis_port_t" (permissive=1, harmless noise).
- Vote-tab auto-switching not yet verified in a real phone browser.

## Recent history (newest first)

- Web app moved into the `web/` package (routes as blueprints; no behaviour change).
- Engine moved into the `thavalon/` package (no behaviour change; golden test, more engine tests).
- Admin pages (`/admin`); hosts create lobbies explicitly and can close them.
- Host-changeable rules (`ruleset.py`), host page rules editor, changes shown on rules pages.
- Redis storage + Redis Streams events; 2 workers; fixed redis-py 5 s timeout.
- Dev site: per-tester games, feedback form (SES), Access-policy-only access.
- Inquisition/Gawain results shown immediately; dev test scenarios (`dev.py`).
- Vote tab (game votes moved there) + host-started fallback votes.
- Earlier: Gareth, Lady of the Lake, Good may play Fail, deploy via Cloudflare tunnel.
