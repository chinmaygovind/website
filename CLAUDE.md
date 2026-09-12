# CLAUDE.md

Chinmay Govind's personal website: a **Flask** server that serves a static site
and redirects to four games and a poker trainer. `/` is the landing page.
`/ttr`, `/ers`, `/kot`, `/drive` and `/gto` redirect to the subdomains.

## Where the documentation is

**This repo is six near-independent services, each documenting itself in its own
directory. Read the one for the thing you are changing; do not read the others.**

| you are working on | read |
|---|---|
| the landing page, `site/`, any static page | `site/CLAUDE.md` |
| the shared profile, login, flags, avatars, presence, `/admin` | `accounts/CLAUDE.md` |
| Egyptian Rat Screw | `ers/CLAUDE.md` |
| King of Tokyo | `kot/CLAUDE.md` |
| Drive | `drive/CLAUDE.md`, then **one** file from `drive/docs/` |
| the GTO poker trainer | `gto/CLAUDE.md` |
| `app.py`, deploy, CI, test selection | this file |

`drive/docs/` is 360KB across thirteen files - more than the rest of the repo put
together - so `drive/CLAUDE.md` is an index that says which single one to read.

`ttr/` is a **submodule**: edit TTR in its own repo, then bump the pointer here.
It has its own CI and is not tested from this repo.

## What this is / how it runs

- **`app.py` is the whole server, at 667 lines.** It serves `site/` as static
  files with GitHub-Pages-style directory indexes (`/foo/` → `site/foo/index.html`,
  `/foo` → `/foo/`), path-safe via `werkzeug.utils.safe_join`. **That redirect is
  a 302 where Pages sends a 301**, which this file used to claim it sent; keep the
  302, because a path that is a directory today can be a bare file tomorrow and a
  301 somebody's browser has cached cannot be taken back.
  **`site/ese2100/` is what exercises the directory-index branch**, and for a
  year nothing did - `site/index.html` was the only `index.html` left, and the
  branch was kept anyway because it is ten lines and it is what makes the next
  `site/foo/index.html` simply work. Three coursework pages later that is exactly
  what happened: they needed no server change at all. `site/CLAUDE.md` →
  **`/ese2100`**.
- **`/cobweb` 301s to `/ese2100/cobweb/` and is the only redirect here that is
  not a service hand-off.** The cobweb page lived at `/cobweb` for a fortnight
  and the URL had been given out, so it keeps working; the 301 is right here
  because the new address is canonical and there is no plan to move back. It has
  to be a route: a static tree cannot answer 301.
- **Static files revalidate on every request** (Flask's `no-cache` default). One
  exception: `fonts/` gets a year's `max-age`, because every page blocks on one
  font file and the revalidation round trip showed as a flash of the fallback
  face. Read `site/CLAUDE.md` → **The font** before extending that to anything
  else; `index.html` must not have it.
- A 404 falls back to `site/404.html`, a small Mario game. Its four sounds live
  in `site/audio/`, which holds nothing else.
- `app.py` proxies the APIs the landing page calls, so no keys reach the client:
  `/api/duolingo-streak` and `/api/spotify/{login,callback,recent,top-artists}`
  (OAuth refresh token in the box `.env`).
- **This server proxies no model API, and should not.** Those two are here
  because Duolingo and Spotify need a key kept off the client. A model endpoint
  behind `-w 2` *sync* workers is a different thing: unmetered spending on this
  box's account, and a 30s call two requests from holding every worker. `gto`
  does talk to a model - see `gto/CLAUDE.md`, where it is one service, one
  account, its own key and its own ceilings.
- **`/accounts` and `/admin` are the only non-static things here.** Both live in
  `accounts/` and are attached by `accounts.init_app(app)` at the foot of
  `app.py`, **only when `DATABASE_URL` is set**, so a checkout that just wants to
  serve the static tree boots with no database and no driver.
- **`/admin` is Chinmay's read-only console** over what the box already records:
  new accounts, every visit session and its clickpath, play counts across the
  four games. **Anybody not in `ADMIN_USERNAMES` (default `chinmay`) gets the
  ordinary 404**, logged in or not, because a 403 would confirm it exists.
  Nothing links to it; every route is a GET. The two traps are in
  `accounts/CLAUDE.md`.
- **No build step, no bundler.** Pages are self-contained static HTML with inline
  `<style>`/`<script>`, inherited from the GitHub Pages site this came from. The
  exception is `accounts/`, a normal Flask blueprint with templates and a
  stylesheet, because it is an application rather than a page.
- Local: `python app.py` → http://localhost:5002 (`PORT` overrides). Prod:
  gunicorn behind nginx (see `deploy/`), auto-deploys from `main`.

## Conventions / gotchas

- **TTR is never reverse-proxied.** Its templates hardcode root-absolute paths
  (`/lobbies`, `/login`, `/static/…`) and connect Socket.IO at root, so it only
  runs at a host's root. `/ttr` redirects. Change the target via `TTR_URL`, never
  by mounting TTR under a path.
- **`visits.py` is one file copied verbatim into five places** - the repo root,
  `ers/`, `kot/`, `drive/`, `gto/`. `accounts/` has no copy; it is a blueprint on the
  root app and uses that one. Nothing in it may be service-specific, and a
  drifted copy fails `tests/test_no_drift.py`. **Fix by copying, never by
  merging.** What it does is in `accounts/CLAUDE.md`.
- **`site/` was 615MB and is 140MB.** August 2026 deleted the entire unlinked
  tree - `home/` (the old projects page), `wii/`, `channels/`, `games/`,
  `projects/` - which nothing linked to, the sitemap omitted and robots
  disallowed, plus 88MB of demo-video cuts `index.html` never referenced. **`.git`
  is still 640MB**, because the history was deliberately not rewritten, which is
  why CI uses sparse checkouts.

## Deploy

Prod is one Ubuntu EC2 box at the Elastic IP `54.157.20.148`, serving
`cgovind.com`/`www`, the four game subdomains and `gto.` over HTTPS through
nginx + certbot (auto-renew). Route 53 hosts the zone. The website is the `website`
systemd service (gunicorn on `127.0.0.1:5002`); each game is its own service.

Push to `main` triggers `.github/workflows/deploy.yml`: pick the changed modules,
run those suites, then an SSH deploy (secrets `EC2_HOST`/`EC2_USER`/`EC2_SSH_KEY`)
that runs `git reset --hard origin/main`, `git submodule update`, `pip install`,
and restarts the services that changed. It does **not** touch nginx, TLS, or the
box `.env`, and does not run `deploy/setup.sh`.

**Only services whose own code moved are restarted**, which matters because
restarting a game drops every live game in it - before this, one CSS tweak on the
landing page ended whatever was being played in ERS and KoT. What moved is asked
of git *on the box* (`git diff --name-only $BEFORE $AFTER` around the reset)
rather than passed in, so a box several commits behind still restarts everything
those commits touched. A hand-triggered re-run of the same commit restarts
everything, since there is nothing to compare.

**The list of services is written out by hand, and `gto` was missing from it**
from the day that service was set up until Aug 2026. The deploy reset the code
on the box and then restarted `ers`, `kot` and `drive` only - so every gto
deploy was green, changed the checkout, and left gunicorn serving the previous
version. It is the quietest failure this workflow can have: the Action passes,
the box is up to date, the site is not, and the only thing that catches it is
loading the page and looking for what you shipped. **Verify a deploy by looking
at the live page, never by looking at the Action.** A new service needs a
`game <name>` line adding here, and nothing will tell you if you forget.

**TTR deploys from this repo's submodule pointer.** The live TTR is not the
`ttr/` submodule but its own clone at `/home/ubuntu/TicketToRide`; the deploy
fetches and `reset --hard`s it to whatever commit `ttr/` names here. So shipping
TTR is: change it in its own repo, `git -C ttr pull`, `git add ttr`, push. The
pointer is the source of truth on purpose - what this repo records is what prod
runs, readable with one `git ls-tree`. **Never `git clean` in that clone**:
`instance/tickettoride.db` is the SQLite file *all five services share* and
`.env` is beside it, both untracked, so a clean would delete the site's entire
data. `reset --hard` is safe precisely because neither is tracked.

Apply nginx/TLS/`.env` changes by hand over SSH (`ssh ubuntu@54.157.20.148`;
config at `/etc/nginx/sites-available/website`). `deploy/setup.sh` is the
one-time bring-up.

Say "push" (or run `/push`) to commit, push, watch the Action and verify live in
one go. If the SSH step fails with `dial tcp :22 i/o timeout`, `EC2_HOST` is
stale: `gh secret set EC2_HOST --body 54.157.20.148`.

## Tests: run only what changed

The full suite is about 3,025 tests in a bit over a minute (drive 2,016 in ~23s
on an idle machine,
kot 224 in ~16s, gto 495 in ~22s, site 266 in ~5s, ers 24 in ~1s), and nearly
every change is to one service, so **never reach for the whole thing by hand**:

```bash
scripts/tests.sh              # only the modules the working tree touches
scripts/tests.sh drive        # one module: site | gto | drive | ers | kot
scripts/tests.sh --all        # everything
scripts/tests.sh --list       # what would run, without running it
scripts/tests.sh drive -- -k ghost -x     # after --, straight to pytest
```

- **`scripts/changed-modules.sh` is the one place a path becomes a module**, and
  both the runner and CI call it, so a laptop and the Action cannot disagree. It
  maps *tests*, not deploys: `ttr/` maps to nothing here because TTR has its own
  CI, while the deploy does its own path matching on the box and does ship TTR.
  `drive/`, `ers/`, `kot/`, `gto/` map to themselves; `app.py`/`site/` (and
  anything unrecognised, deliberately) map to `site`. Docs, `deploy/` and `.claude/` map
  to nothing. **`scripts/` and `.github/workflows/` map to everything**, because
  a change to the selection is one you cannot trust the selection about.
- **The `site` module runs two things**: `import app` (what the deploy used to
  check, and the only thing available when there is no pytest) and then the
  245-test `tests/` suite, which is the real one.
- **The venvs are gitignored, so a module you have never tested locally has
  none.** `tests.sh` builds it rather than reporting `No module named pytest`,
  which is not a test result. A venv is rebuilt when its requirements move, keyed
  on a `.requirements-stamp`: they are long lived and gitignored, so otherwise a
  dependency added to `requirements-test.txt` reaches CI and a fresh clone but
  never the venv you have used for months - and a *test-only* dependency going
  missing does not fail, it quietly stops doing its job.
- **Drive's `quickjs` is an ordinary requirement, not a test one**: the
  anti-cheat re-drives a submitted lap through the game's own JavaScript
  (`drive/verify.py`), so the box needs a JS engine. Without it the tests that
  need it **skip themselves, which reads as a pass** - which is why CI installs
  requirements rather than trusting a venv.
- **`parallel_for` is what is left of xdist here, and only `site` still uses
  it.** `ers` opts out (18 tests in 0.05s), `gto` runs serially by measurement,
  and `drive` and `kot` are on `run_parallel` because xdist deadlocks them. An
  explicit `-n` after `--` wins, and a venv without `pytest-xdist` runs serially
  rather than refusing.
- **drive and kot do not use xdist at all**; `scripts/parallel_pytest.py` runs
  them as one pytest process per bundle of test files, several at a time - drive
  130s → 23s, kot 38s → 16s. It also owns `drive/tests/EXCLUSIVE`, for the one
  file that writes into `tracks/` and so cannot run beside anything that imports
  the pool, and reads a committed `tests/TIMINGS` per module because CI never
  has a local timing table. Full account, including what drive's 6x is made of,
  in `drive/docs/testing.md`.
- **The xdist deadlock is understood now, and it is `eventlet`.** The stall this
  file used to describe as not understood - the run reaches 93-98%, every test
  passes, then the controller and all four workers sit at 0.0% CPU until
  something kills it - is `eventlet.monkey_patch()`, which `drive/app.py` and
  `kot/app.py` both call on line 2 and which **greens `threading`**. xdist's
  workers talk to their controller over pipes on OS threads execnet creates at
  start-up, before any test imports the app; from that import on, a real thread
  is holding green primitives, and signalling one does not wake eventlet's hub.
  The worker's main thread sleeps for something that cannot arrive. In `/proc`:
  workers in `hrtimer_nanosleep`, their pipe readers in `anon_pipe_read`, the
  controller in `futex_do_wait`. At `-n 16` it reproduces about two runs in
  three, which is what made it findable.
  **So it is not a tuning problem - `-n 4` is rarer, not safer.** Both
  monkey-patching modules are out of range now: **`kot` followed `drive` onto
  `run_parallel` in Sep 2026**, which is what this entry always said the fix
  was.
  **Containment was tried first and is written down because it does not work.**
  Adding a second kot test file that imports `app` turned the 3-in-34 stall into
  a hang on every local run, so the split became `--dist loadgroup` with kot's
  app-importing files marked `xdist_group("app")` to keep them on one worker.
  That passed locally and **still hung in CI** - 224 tests, 96%, every one
  passed, then twenty minutes of nothing and a cancel. One patched worker is not
  safe either; it is just luckier. Nothing green should be built on it.
  The consequences that made it hard to see are unchanged:
  a stall reports **cancelled** rather than failed, its length is set by
  `cancel-in-progress` rather than by `timeout-minutes: 20`, and the per-test
  speed guard cannot see it because a deadlocked test never finishes.
- **Two silent leaks came out of that hunt and both cost the machine, not the
  suite.** `drive`'s test fixture unlinked its throwaway SQLite file but not
  SQLite's `-wal`/`-shm` sidecars, and `/tmp` here is a **tmpfs** - 8,000 of each
  had built up to **13GB of a 16GB `/tmp`**, i.e. 13GB of RAM. And
  `eventlet.spawn(_stale_cleanup)` runs at `app.py` import, which the fixture
  does afresh per test file, leaving hundreds of immortal greenlets each sleeping
  five minutes. Neither failed a test; both just made everything slow.
- **gto gates two suites the same way**, for the same reason and with the same
  CI gap: `exhaustive` is the evaluator's proof over all 2,598,960 five-card
  hands (~90s) and `calibration` measures each bot's actual VPIP and PFR against
  the numbers on its profile (~100s). Both are what make the thing they cover
  trustworthy, and both are longer than the rest of that suite. `gated_wanted`
  in `tests.sh` is now the shared implementation, and it also catches
  **untracked** files - without which a module whose first commit has not landed
  would never run its own proofs. `gto` runs serially for the xdist reason
  below: 47s against 14s is a 33s win, less than the ~63s expected stall.
- **kot's bot self-play tests are gated, because they were 24s of its 31s.** The
  three `@pytest.mark.strength` tests are deselected by `kot/pytest.ini` and
  switched back on by `tests.sh` on `--all` or when `kot/bot.py`/`kot/cards.py`
  is dirty (`--override-ini=addopts=`, a single token because these args go
  through unquoted word splitting and an empty `-m ""` cannot survive it).
  Now that kot runs on `run_parallel`, that token is passed to it as its third
  argument and forwarded to every child process - a selection flag the child
  never saw would silently leave the strength tests out on `--all`. The
  skip **prints a line**, since a skipped test otherwise reads as a pass. **The
  gap, plainly:** the check reads the working tree, so it does not fire in CI,
  where the checkout is clean and one commit deep - there they run only on the
  manual "every module" dispatch. Closing it means `pick` passing its changed-file
  list through, which is a `.github/workflows/` edit, and the token cannot push
  those. `test_wins_a_crowded_table` kept its full 200 samples because at n=100 it
  measures sd 0.079 with a worst run of 0.32 against its own 0.35 threshold;
  winning a four-way game is a 1-in-4 event and needs the games a duel can spare.
- **In the Action, `pick` asks the GitHub compare API which files moved** rather
  than cloning to find out, because `.git` is ~640MB of committed media. Every
  job is a sparse checkout of just its own module, and the suites run as a
  parallel matrix, so a two-game change costs one game's wall time.
  - **`site` gets `scripts`, `accounts`, `tests` and `site/assets/flags`, and
    that last one is not the whole story.** `actions/checkout`'s sparse mode is a
    **cone**, which also takes the *files of every parent directory* on the way
    to a pattern - so `site/assets/flags` quietly drags in `site/`'s own files
    (`index.html`, `robots.txt`, `sitemap.xml`) and `site/assets/`'s. A test that
    reads a page out of `site/` therefore passes locally and fails in CI, and one
    that guards itself on the wrong sentinel (`site/assets`, which *is* there)
    fails twice. `tests/test_seo.py` uses `site/fonts` and says why.
- If nothing testable changed the `test` job is skipped, and `deploy` treats
  skipped as fine - hence its `always() && ...` guard, since a skipped need would
  otherwise skip the deploy. A **failed** suite does block it.
- `workflow_dispatch` has a `test_all` box (default on) for re-running everything
  without a commit.
