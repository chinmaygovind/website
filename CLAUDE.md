# CLAUDE.md

Chinmay Govind's personal website: a small **Flask** server that serves a static
site. The **root (`/`) is a plain landing page**; the old **Wii-menu recreation now
lives at `/wii/`**. `/ttr` redirects to the **Ticket to Ride** app (bundled as a git
submodule); `/ers` redirects to **Egyptian Rat Screw** (the `ers/` subdir - a real-time
multiplayer card game that shares TTR's accounts).

## Where the documentation is

**This repo is five near-independent services. Each one documents itself in its
own directory, and those files load only when you work in that directory.** Read
the one for the thing you are changing; do not read the others.

| you are working on | read |
|---|---|
| the landing page, the Wii menu, any static page | `site/CLAUDE.md` |
| the shared profile, login, flags, avatars, presence, `/admin` | `accounts/CLAUDE.md` |
| Egyptian Rat Screw | `ers/CLAUDE.md` |
| King of Tokyo | `kot/CLAUDE.md` |
| Drive | `drive/CLAUDE.md`, then **one** file from `drive/docs/` |
| `app.py`, deploy, CI, test selection | this file |

Drive is by far the largest and is split again inside `drive/docs/` — its
`CLAUDE.md` is an index that says which one file to read. Reading all of them
costs more context than the whole of the rest of the repo.

`ttr/` is a **submodule**; edit TTR in its own repo, then bump the pointer here.
It has its own CI and is not tested from this repo.

## What this is / how it runs

- `app.py` is the whole server (~60 lines). It serves everything under `site/`
  as static files with **GitHub-Pages-style directory indexes**: a request to
  `/foo/` serves `site/foo/index.html`, and `/foo` 301-redirects to `/foo/` so
  relative links keep working. Path safety via `werkzeug.utils.safe_join`.
- `/` serves the landing page (`site/index.html`); the Wii menu is at `/wii/`
  (`site/wii/index.html`). `/ttr`, `/ers` and `/kot` (each with and without the
  trailing slash) 302-redirect to `TTR_URL` / `ERS_URL` / `KOT_URL` (env; default
  `https://{ttr,ers,kot}.cgovind.com`). A 404 falls back to the `site/404.html`
  Mario game.
- `app.py` also proxies a few APIs the landing page calls same-origin, so no keys
  reach the client: `/api/duolingo-streak` and `/api/spotify/{login,callback,
  recent,top-artists}` (OAuth refresh token in the box `.env`). There used to be
  a third, `/api/roll/gemini`, and **it and the game it served are gone** (Aug
  2026): it forwarded the caller's body verbatim to Gemini with this box's API
  key, unauthenticated and unmetered, so it was a free Gemini endpoint for the
  internet on Chinmay's bill — and, at a 30s timeout against `-w 2` *sync*
  workers, two requests away from taking the site down. Nothing linked to the
  game, so the whole thing went rather than being put behind a login. **The
  `GEMINI_API_KEY` in the box `.env` should be removed and the key revoked.**
- **`/accounts` and `/admin` are the only things here that are not static** —
  the shared profile for all four games, and Chinmay's admin console. Both live
  in the `accounts/` package and are attached by `accounts.init_app(app)` at the
  foot of `app.py`, **only when `DATABASE_URL` is set**, so a checkout that just
  wants to serve the static tree boots with no database and no database driver.
  See `accounts/CLAUDE.md`.
- **`/admin` is Chinmay's read-only console** over what the box already records:
  new accounts, every visit session and its clickpath, and how much has been
  played across the four games. **Anybody who is not in `ADMIN_USERNAMES`
  (default `chinmay`) gets the ordinary 404**, logged in or not, because a 403
  would confirm the console exists. Nothing links to it. It writes nothing —
  every route is a GET. Details and the two traps in it are in
  `accounts/CLAUDE.md`.
- **No build step, no bundler.** Pages are self-contained static HTML with inline
  `<style>`/`<script>`, same as the old GitHub Pages site this was derived from.
  The one exception is `accounts/`, which is a normal Flask blueprint with
  templates and a stylesheet, because it is a real application rather than a page.
- Local: `python app.py` → http://localhost:5002 (`PORT` overrides). Prod:
  gunicorn behind nginx (see `deploy/`), auto-deploys from `main`.

## Conventions / gotchas

- **TTR is never reverse-proxied** - its templates hardcode root-absolute paths
  (`/lobbies`, `/login`, `/static/…`) and connect Socket.IO at root, so it can
  only run at a host's root. `/ttr` just redirects to it. Change the target via
  `TTR_URL`, not by mounting TTR under a path.
- **`visits.py` is one file copied verbatim into all five services** — the repo
  root, `accounts/`, `ers/`, `kot/`, `drive/`. Nothing in it may be
  service-specific, and a drifted copy fails `tests/test_no_drift.py`. Fix by
  copying, never by merging. What it does is in `accounts/CLAUDE.md`.


## Deploy

Prod is one Ubuntu EC2 box at the Elastic IP `54.157.20.148`, serving
`cgovind.com`/`www` (the website) and `ttr.cgovind.com` (TTR) over HTTPS through
nginx + certbot (Let's Encrypt, auto-renew). Route 53 hosts the `cgovind.com`
zone. The website runs as the `website` systemd service (gunicorn on
`127.0.0.1:5002`); TTR runs as its own service on `127.0.0.1:5001`.

Push to `main` triggers `.github/workflows/deploy.yml`: pick the changed modules,
run those tests (see **Tests** below), then an
SSH deploy (repo secrets `EC2_HOST`/`EC2_USER`/`EC2_SSH_KEY`, where `EC2_HOST` is
the Elastic IP) that runs `git reset --hard origin/main`, `git submodule update`,
`pip install`, and restarts the services that changed. It does NOT touch nginx,
TLS, or the box `.env`, and does NOT run `deploy/setup.sh`.

**Only the services whose own code moved are restarted**, which matters because
restarting a game service drops every live game in it — before this, one CSS
tweak on the landing page ended whatever was being played in ERS and KoT. What
moved is asked of git *on the box* (`git diff --name-only $BEFORE $AFTER` around
the reset) rather than passed in, so a box several commits behind still restarts
everything those commits touched. A hand-triggered re-run of the same commit
restarts everything, since there is nothing there to compare.

**TTR deploys from this repo's submodule pointer.** The live Ticket to Ride is
not the `ttr/` submodule but its own clone at `/home/ubuntu/TicketToRide`, and
the deploy now fetches and `reset --hard`s it to whatever commit `ttr/` names
here, then restarts `tickettoride`. So shipping TTR is: change it in its own
repo, `git -C ttr pull`, `git add ttr`, push. The pointer is the source of truth
on purpose — what this repo records is what prod runs, readable with one
`git ls-tree`. **Never `git clean` in that clone**: `instance/tickettoride.db`
is the SQLite file *all five services share* and `.env` is beside it, both
untracked, so a clean would delete the site's entire data. `reset --hard` is
safe precisely because neither is tracked. Apply nginx/TLS/`.env` changes by
hand over SSH (`ssh ubuntu@54.157.20.148`; nginx config at
`/etc/nginx/sites-available/website`). `deploy/setup.sh` is the one-time bring-up.

Say "push" (or run `/push`) to commit, push, watch the Action, and verify the
live site in one go. If the SSH step fails with `dial tcp :22 i/o timeout`, the
`EC2_HOST` secret is stale: `gh secret set EC2_HOST --body 54.157.20.148`.

## Tests: run only what changed

The full suite is about three minutes (drive ~1:40, kot ~1:10, site
~15s, ers a couple of seconds) and nearly every change is to exactly one game,
so **never reach for the whole thing by hand**:

```bash
scripts/tests.sh              # only the modules the working tree touches
scripts/tests.sh drive        # one module: site | drive | ers | kot
scripts/tests.sh --all        # everything
scripts/tests.sh --list       # what would run, without running it
scripts/tests.sh drive -- -k ghost -x     # after --, straight to pytest
```

- **`scripts/changed-modules.sh` is the one place a path becomes a module**, and
  both the runner and CI call it, so a laptop and the Action can never disagree.
  Note it maps *tests* and not deploys: `ttr/` maps to nothing here because TTR
  has its own CI, while the deploy step does its own path matching on the box
  and does ship TTR. The two answer different questions on purpose.
  `drive/`, `ers/` and `kot/` map to themselves; `app.py`/`site/` (and anything
  unrecognised, deliberately) map to `site`, whose "suite" is `import app` - the
  same check the deploy used to be. Docs, `deploy/` and `.claude/` map to
  nothing; **`scripts/` and `.github/workflows/` map to everything**, because a
  change to the selection itself is a change you cannot trust the selection about.
  `ttr/` maps to nothing: it is a submodule with its own repo and its own CI.
- **The venvs are gitignored, so a module you have never tested locally has
  none.** `tests.sh` builds it rather than reporting `No module named pytest`,
  which is not a test result. It also installs `requirements-test.txt` if there
  is one. **Drive's `quickjs` is no longer in it**: the anti-cheat re-drives a
  submitted lap through the game's own JavaScript (`drive/verify.py`), so the
  box needs a JS engine now and it is an ordinary requirement. Without quickjs
  the tests that need it **skip themselves, which reads as a pass**, which is
  why CI installs the requirements rather than trusting a venv.
  A venv is rebuilt when its requirements move, keyed on a
  `.requirements-stamp` of the two files: they are long lived and gitignored, so
  otherwise a dependency added to `requirements-test.txt` reaches CI and a fresh
  clone but never the venv you have been using for months - and a *test-only*
  dependency going missing does not fail, it quietly stops doing its job.
- **`parallel_for` in `tests.sh` splits kot across four cores**, which is most of
  the difference between a three minute full run and a much longer one.
  Four workers rather than every core, since on a 16 core laptop kot's self-play
  tests contend badly enough that the suite stops finishing. `ers` opts out (18
  tests in 0.05s - workers cost more than they save), an explicit `-n` after `--`
  wins, and a venv without `pytest-xdist` runs serially rather than refusing to
  run.
- **drive opts out too, which it did not used to**, and the trade is written down
  in `drive/docs/testing.md`. `-n 4 --dist loadfile` was worth 5:40 -> 1:35 when
  `test_sim.py` drove all thirteen tracks; that file is gone and what was left was
  66s serial against 42s parallel. Set against **three of the last 34 CI drive
  jobs hanging** - 94-98% done in under a minute, then the controller and all
  four workers at 0.0% CPU for 739s / 901s / 246s - the 24s is not worth it.
- **xdist occasionally deadlocks, and it is still not understood.** The run reaches
  93-98% in well under a minute and then sits with the controller **and all four
  workers at 0.0% CPU** until something kills it; every test has passed, the session
  just never ends. Measured on `drive` before it went serial: **three of 34 CI jobs**
  (~9%, one push in eleven), stalling 739s, 901s and 246s. The identical command
  passes on the next run, so it is **intermittent, not a bad commit** - the first CI
  stall was written off here as an infrastructure flake, which a local `kot`
  reproduction disproved. Three things follow. A stall reports **cancelled** rather
  than failed, so the deploy is skipped and the run does not look like a test
  failure. Its length is set by `cancel-in-progress` - the next push is what ends it
  - so it is bounded by when somebody notices, not by `timeout-minutes: 20`. And the
  per-test speed guard cannot see it: a deadlocked test never finishes, so it has no
  duration. **`drive` is out of range of this now** (it runs serially); `kot` is the
  one left exposed. The cheap mitigation there, still not applied, is
  `pytest-timeout` in its `requirements-test.txt` plus a step-level
  `timeout-minutes`, which turns an open-ended stall into a fast, legible failure.
- **kot's bot self-play tests are gated, because they were 24s of its 31s.** The
  three `@pytest.mark.strength` tests are deselected by `kot/pytest.ini`'s `addopts`
  and switched back on by `tests.sh` on `--all` or when `kot/bot.py`/`kot/cards.py`
  is dirty (`--override-ini=addopts=`, a single token because these args go through
  unquoted word splitting and an empty `-m ""` cannot survive that). The skip
  **prints a line**, since a skipped test otherwise reads as a pass. **The gap, said
  plainly:** the check reads the working tree, so it does not fire in CI, where the
  checkout is clean and one commit deep - there they run only on the manual
  "every module" dispatch. Closing it means `pick` passing its changed-file list
  through, which is a `.github/workflows/` edit, and the token cannot push those.
  Two of the three had their samples halved after measuring; **`test_wins_a_crowded_table`
  kept its full 200** because at n=100 it measures sd 0.079 with a worst run of 0.32
  against its own 0.35 threshold - halving it would have shipped a test that fails
  some nights. Winning a four-way game is a 1-in-4 event and needs the games a duel
  can spare.
- **In the Action, `pick` asks the GitHub compare API which files moved rather
  than cloning to find out.** This repo's `.git` is ~484MB of committed media and
  `site/` is ~513MB on disk, so a full-history checkout would cost more than the
  tests it is trying to save. Every job is a sparse checkout of just its own
  module (for `site` that is the root files only, since `import app` never reads
  `site/`). The suites then run as a parallel matrix, so a two-game change costs
  one game's wall time.
- If nothing testable changed the `test` job is skipped, and `deploy` treats
  skipped as fine - hence its `always() && ...` guard, since a skipped need would
  otherwise skip the deploy too. A **failed** suite does block the deploy.
- `workflow_dispatch` on the Action has a `test_all` box (default on) for
  re-running everything without a commit.
