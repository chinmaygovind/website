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

A second real-time game at `ers.cgovind.com`, in the `ers/` subdir (NOT a submodule),
that **shares TTR's accounts**. Flask + Flask-SocketIO, its own eventlet gunicorn on
`127.0.0.1:5003`, its own venv (`ers/venv`) and `.env`.

- **Shared accounts:** ERS points `DATABASE_URL` at TTR's SQLite file and uses the SAME
  `SECRET_KEY` + `SESSION_COOKIE_DOMAIN=.cgovind.com`, so one login works on both sites
  (single sign-on). Per-game stats are kept apart: TTR stats moved from the `users` table
  into `ttr_stats`; ERS stats live in `ers_stats`. `users` is now a shared account table.
  The stats split was an additive, reversible migration (old `users` stat columns kept as a
  dormant backup) that runs on `ttr` startup; `ers_stats`/`ers_games`/`ers_players`/
  `ers_slaps` are created by ERS. Two processes share one SQLite file via WAL + busy_timeout.
- **Layout:** `ers/app.py` (auth+lobby routes ported from TTR, socket game loop, bots,
  ELO/stats finalize), `ers/game_logic.py` (pure, unit-tested rules engine - `pytest ers/tests/`),
  `ers/models.py` (shared `User` + `ErsStats`/`ErsGame`/`ErsPlayer`/`ErsSlap`),
  `ers/templates/` + `ers/static/` (wooden-table UI, xkcd Script font, gold, pyramid PWA icons).
- **Full game history:** every game's move-by-move replay is in `ers_games.events_json`; each
  slap is also a row in `ers_slaps` (with `reaction_ms`) - e.g. a reaction-time distribution is
  `SELECT reaction_ms FROM ers_slaps WHERE valid=1 AND reaction_ms IS NOT NULL`.
- **Single gunicorn worker is required** (in-process socket rooms + game state), like TTR.
  The engine is server-authoritative; the first valid slap under a per-game lock wins.

## One-time ERS prod bring-up (the deploy pipeline won't do these)

Run once over SSH / AWS (deploy.yml afterwards handles venv + `systemctl restart ers`/`ttr`):
0. Back up first: `cp ttr/instance/tickettoride.db tickettoride.db.bak`.
1. Route 53: add `ers.cgovind.com` A record → Elastic IP `54.157.20.148`.
2. Create `ers/.env` (see `ers/.env.example`): `SECRET_KEY` = TTR's, `DATABASE_URL` = TTR's db
   absolute path, `SESSION_COOKIE_DOMAIN=.cgovind.com`, `SESSION_COOKIE_SECURE=1`, `PORT=5003`.
3. Add `SESSION_COOKIE_DOMAIN=.cgovind.com` to `ttr/.env` (keep its existing `SECRET_KEY`;
   TTR's `app.py` must also set the cookie domain from env - one-time TTR re-login).
4. Install `deploy/ers.service` (render `{{USER}}`/`{{APP_DIR}}`), `systemctl enable --now ers`.
5. Add the `ers.cgovind.com` nginx block (in `deploy/nginx.conf`), `nginx -t`, reload, then
   `certbot --nginx -d ers.cgovind.com` for TLS.
6. `sudo systemctl restart ttr` (runs the `ttr_stats` migration) and start `ers`.

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
