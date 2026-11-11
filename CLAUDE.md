# THavalon webapp — handover notes for Claude

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
| `THavalon.py` | Roles and `AvalonBuilder` (deals roles, lonely-role transformations, Gareth). Roles read `builder.rules`. |
| `ruleset.py` | `RuleSet`: host-changeable rules (`SETTINGS` registry: player counts, lonely counts, who sees whom, Gareth, cards/abilities, Assassination). Stores only changes from the defaults. |
| `rule_notes.py` | Turns a `RuleSet`'s changes into sentences tagged with rules pages ("In your current game"). |
| `game.py` | `GameState`: the rules engine (phases, teams, cards, Inquisition, pauses, scoring). Does **not** check who is acting. |
| `actions.py` | `GameController`: who may act (`available_actions`), `act()`, per-player `view()` that hides secrets, and host **undo** (snapshots; cleared after anything that reveals information). |
| `votes.py` | `HostVote`: votes the host starts by hand as a fallback when the game flow breaks. Never touch `GameState`. |
| `webapp.py` | Flask routes; `AvalonGame` (a lobby's game), `Lobby`, `Lobbies` (Redis-backed), `vote_status()` (drives the Vote tab), `GameSettings`. |
| `store.py` | Redis connection + `Store` (pickled objects, optimistic `WATCH` transactions). |
| `events.py` | Live updates: Server-Sent Events over Redis Streams. |
| `dev.py` | Dev-site-only features: test scenarios, "view as" switching, Access login check, feedback emails. |
| `admin.py` | Admin pages `/admin` (all sites): list/inspect/change/close lobbies, close idle ones, "view as" any player or host (swaps the session's identity keys, restored by `/admin/stop`). |
| `access.py` | `AccessCheck`: verifies Cloudflare Access JWTs (dev site and admin). |
| `rules.py` | Rules pages and `[[Term]]` link markup used in templates. |
| `templates/role.html` | Player page: **Game / Role / Vote** tabs, tab switching and Vote-tab auto-open logic. |
| `templates/game/` | Live panels: `panel.html` (Game tab), `abilities.html` (Role tab, private), `vote.html` (Vote tab), `host_panel.html`, shared `_now.html` / `_macros.html`. |
| `static/game.js` | Fetches/re-renders panels on `game-update`, submits `form.game-action`, keeps ticked players across re-renders, fires `panels-rendered`. |
| `static/events.js` | SSE client (`Events.on`, `Events.reloadOn`). |
| `tools/bots.py` | Bot players (also vote in host votes). `python tools/bots.py 6 --url https://avalon.iammerlin.fyi --game NAME` |

## How things work (and rules to keep)

- **Storage is Redis.** `LOBBIES.get()/active()/hosted_by()` return *copies*. Change a lobby
  only with `LOBBIES.update(lobby_id, fn)`; `fn` may run several times (retries on conflict),
  so it must be side-effect free — publish events (`new_event(...)`) *after* it returns.
  Idle lobbies expire after 12 h.
- **Pickles depend on class code.** If a change makes old stored games unloadable, bump
  `SCHEMA` in `store.py` (old games are then ignored, not crashing). Adding a new attribute to
  a stored class usually needs a class-level default so old pickles still work.
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
  `RuleSet.from_form`); saved in the host's cookie (`host_prefs['rules']`, only changes).
  A game's `RuleSet` lives on `AvalonGame.ruleset`, `AvalonBuilder.rules` and
  `GameState.rules` (class-level defaults keep old pickles loading). **Default rules must
  behave exactly as before**: checked by comparing deals/role info/random-game logs over many
  seeds with `PYTHONHASHSEED=0` (see the commit adding `ruleset.py`), and by
  `tests/test_rule_settings.py`. New setting = entry in `ruleset._settings()`, the engine/role
  code reading it, a note in `rule_notes.game_notes`, and a place in `webapp.HOST_GROUPS`
  (tests check every setting is on the host page once and produces a note).
- **Rules pages** show the viewer's current game's rule changes at the top (`viewer_game()`);
  the Role tab shows them under the role's rules; the game summary lists them.

## Admin pages (`admin.py`)

- Protected by a Cloudflare Access self-hosted application on `avalon.iammerlin.fyi/admin`
  (the owner's policy). No server settings needed: the app only checks each request carries a
  validly signed Access token (`access.email_from_any_team`). Optionally `CF_ACCESS_TEAM_DOMAIN`
  + `ADMIN_ACCESS_AUD` pin the application and `ADMIN_EMAILS` the emails. POST forms carry a
  session CSRF token. Locally (`python webapp.py`) `ADMIN_NO_AUTH` skips the check.
- Closing a lobby (`webapp.close_lobby`, also the host page's "Close lobby") deletes it and
  publishes `new-game`/`new-player` on its channel and `new-lobby` on `lobbies`.
- `/host` no longer creates a lobby by itself: it shows a "Create lobby" form (`host_create.html`)
  with a free random name; `/host/create` creates it.

## Dev site (`dev.py`)

- Only active with `AVALON_DEV=1`. The live site must not expose it (`/dev` → 404; tested).
- `/dev/` lists ~18 scenarios (one, `changed-rules`, uses changed rules) (`SCENARIOS`), each a game driven to a situation by `Drive`.
  Opening one (or ↺ Reset) rebuilds it. The purple bar switches "view as" any player or host —
  it literally makes the browser session that player. Each tester (session id `dev_tester`)
  gets their own copies, so testers never share games.
- `make_builder` deals roles exactly as listed (no lonely transformations), so pick valid
  combos. Player-count limits: Guinevere 7+, Gareth / Pellinore / Questing Beast exactly 9,
  Gawain 10. Inquisition depends on Evil count (proposals = Evil + 1: 4 → weak, 5 → strong).
- Access: Cloudflare Access decides who gets in (the owner adds playtesters in the Access
  policy). The app additionally verifies the Access JWT for this application's audience, and
  refuses everything if `CF_ACCESS_*` aren't set. `DEV_ALLOWED_EMAILS` is optional (empty).
- Feedback (✎ in the bar) emails the description plus the scenario, viewer, page and the game's
  full state (incl. secrets) via SES. Recipient/sender come from env, not the repo.
- Local: `AVALON_DEV=1 python webapp.py` → http://127.0.0.1:5000/dev/ (no login check locally).

## Running and testing locally

- Conda env `avalon` (Python 3.14): `conda run -n avalon python -m pytest -q` (243 tests).
- `tests/test_dev.py` runs each check in a fresh subprocess (dev features are decided at import).
- `tests/test_store.py` also runs against a real Redis if `TEST_REDIS_URL` is set (no Redis
  server is installed locally; a throwaway one can be made with conda-forge `redis-server`).
- Node is installed via nvm but isn't on non-login shells' PATH:
  `~/.nvm/versions/node/v26.13.0/bin/node --check static/game.js`. Inline scripts in templates
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

- Admin pages (`/admin`); hosts create lobbies explicitly and can close them.
- Host-changeable rules (`ruleset.py`), host page rules editor, changes shown on rules pages.
- Redis storage + Redis Streams events; 2 workers; fixed redis-py 5 s timeout.
- Dev site: per-tester games, feedback form (SES), Access-policy-only access.
- Inquisition/Gawain results shown immediately; dev test scenarios (`dev.py`).
- Vote tab (game votes moved there) + host-started fallback votes.
- Earlier: Gareth, Lady of the Lake, Good may play Fail, deploy via Cloudflare tunnel.
