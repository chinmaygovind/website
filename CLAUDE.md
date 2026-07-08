# CLAUDE.md

Chinmay Govind's personal website: a small **Flask** server that serves a static
site whose **root (`/`) is a Wii-menu recreation**, and redirects `/ttr` to the
**Ticket to Ride** app (bundled as a git submodule).

## What this is / how it runs

- `app.py` is the whole server (~60 lines). It serves everything under `site/`
  as static files with **GitHub-Pages-style directory indexes**: a request to
  `/foo/` serves `site/foo/index.html`, and `/foo` 301-redirects to `/foo/` so
  relative links keep working. Path safety via `werkzeug.utils.safe_join`.
- `/` serves the Wii menu (`site/index.html`). `/ttr` (and `/ttr/`) 302-redirects
  to `TTR_URL` (env; default is TTR's current prod IP). A 404 falls back to the
  `site/404.html` Mario game.
- **No build step, no bundler.** Pages are self-contained static HTML with inline
  `<style>`/`<script>`, same as the old GitHub Pages site this was derived from.
- Local: `python app.py` → http://localhost:5002 (`PORT` overrides). Prod:
  gunicorn behind nginx (see `deploy/`), auto-deploys from `main`.

## Layout (`site/` is the web root)

- `site/index.html` — the Wii menu (was `public/wii/index.html`). Warning screen
  fades into a channel grid. The bottom-left gray slot is a **Ticket to Ride
  channel** (`#channel-ttr`) whose click handler navigates to `/ttr`.
- `site/warning.html` — the "reset" warning screen the menu loops back to.
- `site/channels/{mii,music,codebusters}/` — the Wii channel pages. They
  reference shared assets with `../../images|audio|videos/…` (resolves to root).
- `site/home/index.html` — the **projects landing page** (was the site's old `/`).
  Its assets live in `site/home/{images,audio}/` and `Chinmay_Govind_Resume.pdf`.
- `site/{projects,games}/` — standalone project/game pages (astro, ibec, quickcal,
  robot-tour, bridge, flip, klotski, roll), copied unchanged.
- `site/{images,audio,videos}/` — shared media (Wii menu art + channel media).
- `site/404.html`, `favicon.ico`, `robots.txt` at the root.

## Conventions / gotchas

- **Links are relative** and assume `site/`-as-root. When adding pages, keep paths
  relative; the only absolute paths are a couple that already encode the page's
  own location (e.g. astro's `/projects/astro/static/…`) and `site/404.html`'s
  `/home/audio/…` (absolute so the 404 game works at any URL).
- This site was lifted from `chinmaygovind.github.io/public`. The Wii was promoted
  from `/wii/` to `/`, so the landing page moved to `/home/` and every relative
  path was repointed. Dead Create-React-App refs (`%PUBLIC_URL%`, `logo192.png`,
  `manifest.json`) were removed.
- **TTR is never reverse-proxied** — its templates hardcode root-absolute paths
  (`/lobbies`, `/login`, `/static/…`) and connect Socket.IO at root, so it can
  only run at a host's root. `/ttr` just redirects to it. Change the target via
  `TTR_URL`, not by mounting TTR under a path.
- `ttr/` is a **submodule**; edit TTR in its own repo, then bump the pointer here.

## Deploy

Push to `main` → `.github/workflows/deploy.yml` runs an import check, then SSHes
to EC2 (reusing TTR's `EC2_HOST/EC2_USER/EC2_SSH_KEY` secrets), `git reset --hard`,
`git submodule update`, `pip install`, and restarts the `website` systemd service.
`deploy/setup.sh` is the one-time bring-up. TTR runs as its own service and
`TTR_URL` points at it — see `deploy/nginx.conf` for the subdomain/host options.
