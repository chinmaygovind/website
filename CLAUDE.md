# CLAUDE.md

Chinmay Govind's personal website: a small **Flask** server that serves a static
site. The **root (`/`) is a plain landing page**; the old **Wii-menu recreation now
lives at `/wii/`**. `/ttr` redirects to the **Ticket to Ride** app (bundled as a git
submodule); `/ers` redirects to **Egyptian Rat Screw** (the `ers/` subdir - a real-time
multiplayer card game that shares TTR's accounts).

## What this is / how it runs

- `app.py` is the whole server (~60 lines). It serves everything under `site/`
  as static files with **GitHub-Pages-style directory indexes**: a request to
  `/foo/` serves `site/foo/index.html`, and `/foo` 301-redirects to `/foo/` so
  relative links keep working. Path safety via `werkzeug.utils.safe_join`.
- `/` serves the landing page (`site/index.html`); the Wii menu is at `/wii/`
  (`site/wii/index.html`). `/ttr` (and `/ttr/`) 302-redirects to `TTR_URL` (env;
  default `https://ttr.cgovind.com`). A 404 falls back to the `site/404.html`
  Mario game.
- **No build step, no bundler.** Pages are self-contained static HTML with inline
  `<style>`/`<script>`, same as the old GitHub Pages site this was derived from.
- Local: `python app.py` → http://localhost:5002 (`PORT` overrides). Prod:
  gunicorn behind nginx (see `deploy/`), auto-deploys from `main`.

## Layout (`site/` is the web root)

- `site/index.html` is the landing page: a plain white page with a big "hey!" on
  the left and a welcome line on the right, set in the self-hosted xkcd Script
  font (`site/fonts/xkcd-script.woff`, from ipython/xkcd-font).
- `site/wii/index.html` is the Wii menu (was `public/wii/index.html`, briefly at
  root). Warning screen fades into a channel grid. The bottom-left gray slot is a
  **Ticket to Ride channel** (`#channel-ttr`) whose click handler navigates to `/ttr`.
  Its `../../images|audio|videos` paths assume it sits at root, so some break at `/wii/`.
- `site/warning.html` - the "reset" warning screen the menu loops back to.
- `site/channels/{mii,music,codebusters}/` - the Wii channel pages. They
  reference shared assets with `../../images|audio|videos/…` (resolves to root).
- `site/home/index.html` - the **projects landing page** (was the site's old `/`).
  Its assets live in `site/home/{images,audio}/` and `Chinmay_Govind_Resume.pdf`.
- `site/{projects,games}/` - standalone project/game pages (astro, ibec, quickcal,
  robot-tour, bridge, flip, klotski, roll), copied unchanged.
- `site/{images,audio,videos}/` - shared media (Wii menu art + channel media).
- `site/404.html`, `favicon.ico`, `robots.txt` at the root.

## Conventions / gotchas

- **Links are relative** and assume `site/`-as-root. When adding pages, keep paths
  relative; the only absolute paths are a couple that already encode the page's
  own location (e.g. astro's `/projects/astro/static/…`) and `site/404.html`'s
  `/home/audio/…` (absolute so the 404 game works at any URL).
- This site was lifted from `chinmaygovind.github.io/public`. The Wii menu briefly
  sat at `/` but now lives at `/wii/`; `/` is a simple landing page and the older
  projects page stayed at `/home/`. Dead Create-React-App refs (`%PUBLIC_URL%`,
  `logo192.png`, `manifest.json`) were removed.
- **TTR is never reverse-proxied** - its templates hardcode root-absolute paths
  (`/lobbies`, `/login`, `/static/…`) and connect Socket.IO at root, so it can
  only run at a host's root. `/ttr` just redirects to it. Change the target via
  `TTR_URL`, not by mounting TTR under a path.
- `ttr/` is a **submodule**; edit TTR in its own repo, then bump the pointer here.

## Egyptian Rat Screw (`ers/`)

**Live at `https://ers.cgovind.com`** (TLS via certbot). A second real-time game in the
`ers/` subdir (NOT a submodule) that **shares TTR's accounts**. Flask + Flask-SocketIO,
its own eventlet gunicorn `-w 1` on `127.0.0.1:5003` (single worker required: socket rooms
+ game state live in-process), its own venv (`ers/venv`) and `.env` (both gitignored,
hand-created on the box). The engine is server-authoritative; the first valid slap under a
per-game lock wins.

- **Shared accounts:** `ers/.env` sets `DATABASE_URL` to the SAME SQLite file the live TTR
  uses and reuses TTR's `SECRET_KEY` + `SESSION_COOKIE_DOMAIN=.cgovind.com`, so one login
  works on both sites. `users` is the shared account table; ERS creates `ers_stats` /
  `ers_games` / `ers_players` / `ers_slaps` in that same file (WAL + busy_timeout for
  concurrent access). ERS's `User` model maps only the account columns.
- **Prod DB path gotcha:** the live TTR does NOT run from this repo's `ttr/` submodule; it
  runs from a **separate clone `/home/ubuntu/TicketToRide`** (systemd `tickettoride`, port
  5001), whose db is `/home/ubuntu/TicketToRide/instance/tickettoride.db` -- that is the
  shared file `ers/.env`'s `DATABASE_URL` points at.
- **SSO is one-directional in prod:** a login on ERS carries into TTR (ERS sets a
  `.cgovind.com` cookie signed with the shared key), but TTR -> ERS auto-login is NOT wired
  because the live TTR clone still sets a host-only cookie. Same credentials work either way.
- **The `ttr_stats` refactor is NOT deployed.** This repo's `ttr/` submodule has edits that
  move TTR stats out of `users` into `ttr_stats` (+ cookie-domain SSO), but the running TTR
  is the separate clone, so in prod **TTR still uses the `users.elo` columns** and ERS uses
  `ers_stats`; both coexist in the one db. Deploying that refactor means committing it in the
  `github.com/chinmaygovind/TicketToRide` repo and `git pull` + restart on
  `/home/ubuntu/TicketToRide` (back up the db first).
- **Layout:** `ers/app.py` (auth + lobby routes ported from TTR, socket game loop, bots,
  ELO/stats finalize, ping, spectators, kick/leave), `ers/game_logic.py` (pure, unit-tested
  rules engine -- `cd ers && venv/bin/python -m pytest tests/`), `ers/models.py` (shared
  `User` + `ErsStats`/`ErsGame`/`ErsPlayer`/`ErsSlap`), `ers/templates/` + `ers/static/`
  (wooden oval table, xkcd Script font, gold, pyramid PWA icons, synth `flip.wav`/`slap.wav`).
- **Rules:** royalty tribute (A/K/Q/J owe 4/3/2/1); slaps = double, sandwich, top-matches-
  bottom, add-to-ten, King+Queen; a wrong slap burns 1 card + a 2s freeze; **one life** to
  slap back in after running out; last player holding all 52 wins. Bots (`is_bot` ErsPlayer
  rows) slap with `max(0.5s, Exponential(mean 2s))`, driven by eventlet timers.
- **Feel:** everyone is a seat (dot + count + name) around the table, your flip pile
  down-left and SLAP down-right of your seat; a card flies from a seat and flips into the
  pile in one motion; a colored hand smacks on every slap (red X on a wrong one); cards
  slide to whoever wins the pile; a wrong slap lifts the pile to slide the burned card
  under face-up; scrollable fading chat; live ping; spectators can watch playing games.
- **Full game history:** every game's move-by-move replay is in `ers_games.events_json`;
  each slap is also a row in `ers_slaps` (with `reaction_ms`) -- e.g. a reaction-time
  distribution is `SELECT reaction_ms FROM ers_slaps WHERE valid=1 AND reaction_ms IS NOT NULL`.

**ERS deploy:** pushes to `main` run the usual Action, which now also (when `ers/.env`
exists on the box) builds/updates `ers/venv` from `ers/requirements.txt` and
`sudo systemctl restart ers`. nginx has an `ers.cgovind.com` vhost (`sites-available/ers`,
proxy to `:5003` with WebSocket upgrade) with its own Let's Encrypt cert; Route 53 has the
`ers.cgovind.com` A record. `/ers` on the main site 302-redirects there (`ERS_URL`). nginx,
TLS, DNS and `ers/.env` are all hand-managed on the box (not shipped by the Action), same as
the rest of the deploy. See the `prod-infra` memory for the full box layout.

## Deploy

Prod is one Ubuntu EC2 box at the Elastic IP `54.157.20.148`, serving
`cgovind.com`/`www` (the website) and `ttr.cgovind.com` (TTR) over HTTPS through
nginx + certbot (Let's Encrypt, auto-renew). Route 53 hosts the `cgovind.com`
zone. The website runs as the `website` systemd service (gunicorn on
`127.0.0.1:5002`); TTR runs as its own service on `127.0.0.1:5001`.

Push to `main` triggers `.github/workflows/deploy.yml`: an import check, then an
SSH deploy (repo secrets `EC2_HOST`/`EC2_USER`/`EC2_SSH_KEY`, where `EC2_HOST` is
the Elastic IP) that runs `git reset --hard origin/main`, `git submodule update`,
`pip install -r requirements.txt`, and `sudo systemctl restart website`. That is
all it does: it ships `site/` and `app.py` but does NOT touch nginx, TLS, or the
box `.env`, and does NOT run `deploy/setup.sh`. Apply nginx/TLS/`.env` changes by
hand over SSH (`ssh ubuntu@54.157.20.148`; nginx config at
`/etc/nginx/sites-available/website`). `deploy/setup.sh` is the one-time bring-up.

Say "push" (or run `/push`) to commit, push, watch the Action, and verify the
live site in one go. If the SSH step fails with `dial tcp :22 i/o timeout`, the
`EC2_HOST` secret is stale: `gh secret set EC2_HOST --body 54.157.20.148`.
