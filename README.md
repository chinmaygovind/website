# website

Chinmay Govind's personal site. A small **Flask** server that serves a Wii-menu
front page (and the rest of the static site) and hands off to **Ticket to Ride**
at `/ttr`.

## Layout

- `app.py` — the server. Serves `site/` at `/` (the Wii menu is the site root),
  re-implements GitHub-Pages-style directory indexes (`/foo/` → `site/foo/index.html`),
  and redirects `/ttr` → `TTR_URL`.
- `site/` — all static content. `site/index.html` is the Wii menu; `site/home/`
  is the old projects landing page; `site/{projects,games,channels}/` are the rest.
- `ttr/` — **git submodule** ([TicketToRide](https://github.com/chinmaygovind/TicketToRide)).
  TTR runs as its own service; `/ttr` redirects to it.
- `deploy/` — nginx, systemd units, and one-time `setup.sh`.
- `.github/workflows/deploy.yml` — SSH deploy on push to `main`.

## Run locally

```bash
git clone --recurse-submodules <this-repo> && cd website
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set TTR_URL (e.g. http://localhost:5001)
python app.py                   # http://localhost:5002
```

Visit `/` for the Wii menu; click the **Ticket to Ride** channel (bottom-left
slot) to hit `/ttr`. `/home/` is the projects landing page.

To also run TTR locally, in another terminal: `cd ttr && python app.py` (:5001),
and set `TTR_URL=http://localhost:5001`.

## Deploy

Deploys to EC2 over SSH, reusing the Ticket to Ride box. See
[deploy/README notes](deploy/) and `deploy/setup.sh`.

1. Add repo **secrets**: `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY` (same values TTR uses).
2. On the box: `git clone --recurse-submodules … ~/website && cd ~/website && sh deploy/setup.sh`.
3. Set `TTR_URL` in `~/website/.env` to wherever TTR is reachable (its current
   host, or a `ttr.` subdomain if you run it from the submodule here).
4. Push to `main` → GitHub Actions runs an import check, then SSH-deploys and
   restarts the `website` service.

Because this is a Flask server (not GitHub Pages), the site is served from the
EC2 host — point a domain at it or use the instance IP.
