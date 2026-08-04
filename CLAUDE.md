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
  (`site/wii/index.html`). `/ttr`, `/ers` and `/kot` (each with and without the
  trailing slash) 302-redirect to `TTR_URL` / `ERS_URL` / `KOT_URL` (env; default
  `https://{ttr,ers,kot}.cgovind.com`). A 404 falls back to the `site/404.html`
  Mario game.
- `app.py` also proxies a few APIs the landing page calls same-origin, so no keys
  reach the client: `/api/duolingo-streak`, `/api/spotify/{login,callback,recent,
  top-artists}` (OAuth refresh token in the box `.env`), and `/api/roll/gemini`
  for the `site/games/roll/` game.
- **No build step, no bundler.** Pages are self-contained static HTML with inline
  `<style>`/`<script>`, same as the old GitHub Pages site this was derived from.
- Local: `python app.py` → http://localhost:5002 (`PORT` overrides). Prod:
  gunicorn behind nginx (see `deploy/`), auto-deploys from `main`.

## Layout (`site/` is the web root)

- `site/index.html` is the landing page: white page, big "hey!" left, welcome line
  and contact links across the top, all in the self-hosted xkcd Script font
  (`site/fonts/xkcd-script.woff`, from ipython/xkcd-font). Below it is a **tile
  grid** — `repeat(6, --tile)` × auto rows, so **12 slots** before it wraps to a
  third row (2 columns on <=760px). Currently 9: resume, poker, whales, racing,
  music, settings on the top row, then the three games — ttr, ers, kot — on the
  second. **Keep `settings` last in the top row** (it's a Wii-menu joke), and add
  new games to the second row so the split holds. **Drive has no tile on purpose**
  — it had one, and it was removed because Chinmay wants to draw the icon himself;
  `--drive` is still in `:root` waiting for it. Do not re-add it unasked.
- **Adding a tile is one repeating pattern**, all inside `site/index.html` (no
  build step, so everything is inline):
  1. a `--<name>` accent colour in `:root`, then `.modal-<name>` rules for
     `border-color`, `.pane-title` colour, and `.media-img` border;
  2. a `<button class="tile" data-modal="modal-<name>">` with a `.tile-img` whose
     `data-still`/`data-anim` are `assets/icons/<name>.png` / `.gif` — the script
     at the bottom swaps to the gif on hover and preloads it, so **every tile
     needs both files**;
  3. a `.modal` + `.modal-box .modal-<name>` block, left pane = `.pane-title` +
     `.pane-text` (+ `.modal-icon` gif top-right), right pane = `.media` frames
     holding a `.media-img` or a dashed `.placeholder` while art is pending.
  The generic script wires open/close (X, backdrop, Escape) off those classes —
  a new tile needs no JS. Icon sources are GIMP `.xcf` files kept next to the
  exported png/gif in `site/assets/icons/`.
- Two panes are live rather than static: the resume tile's fast facts patch in a
  computed age and the Duolingo streak, and the music tile fills recently-played
  and top-artists from the Spotify proxy, plus a concert carousel driven by
  `site/assets/music/concerts.json` (add a concert by appending to that JSON —
  no code change).
- `site/wii/index.html` is the Wii menu (was `public/wii/index.html`, briefly at
  root). Warning screen fades into a channel grid. The bottom-left gray slot is a
  **Ticket to Ride channel** (`#channel-ttr`) whose click handler navigates to `/ttr`.
  Its `../../images|audio|videos` paths assume it sits at root, so some break at `/wii/`.
- **`site/warning.html` is gone** (deleted in `d0a282b`) but `site/wii/index.html`
  still navigates to `warning.html`, so the Wii menu's "reset" path 404s into the
  Mario game. The `warning.png`/`warning.wav` assets are still there, so restoring
  the page (at `site/wii/warning.html`, since the link is relative) would fix it.
- `site/channels/{mii,music,codebusters}/` - the Wii channel pages. They
  reference shared assets with `../../images|audio|videos/…` (resolves to root).
- `site/home/index.html` - the **projects landing page** (was the site's old `/`).
  Its assets live in `site/home/{images,audio}/` and `Chinmay_Govind_Resume.pdf`.
- `site/{projects,games}/` - standalone project/game pages (astro, ibec, quickcal,
  robot-tour, bridge, flip, klotski, roll), copied unchanged.
- `site/{images,audio,videos}/` - shared media (Wii menu art + channel media).
- `site/404.html`, `favicon.ico`, `robots.txt` at the root.

## Unlinked pages (nothing on the site links to these)

The landing page's tiles only open modals or point off-site (ttr/ers/kot subdomains,
the resume PDF, YouTube, PennToday). **No internal HTML page is linked from `/` at
all**, so every page below is reachable only by typing its URL:

- **Orphaned outright:** `games/flip/` ("Flip - The Game"), `games/klotski/`
  ("Klotski"), `games/roll/` ("3D Ball Roll Game" — note this one has a live
  backend, `/api/roll/gemini`), `wii/`, `channels/mii/`, and the local
  `projects/ibec/` copy (7 leftover template pages: committees, contact, events,
  membership, left-/right-/no-sidebar).
- **Orphaned transitively:** `home/index.html` (the old projects page) has no
  inbound links either, so the things only *it* links to are also unreachable:
  `projects/astro/` (AstroGPT), `projects/quickcal/`, `projects/robot-tour/`,
  `games/bridge/` (Penn Bridge sim, plus the `projects/bridge/` redirect stub),
  `channels/music/` and `channels/codebusters/` (+ its `pattern.html`).
- `site/404.html` (Mario game) is by design only reachable via a bad URL.
- **Two stale links to fix if you re-link things:** `home/index.html:591`'s "Wii
  Channel" tile points at `../`, which was the Wii menu when it lived at `/` but is
  now the landing page — it should be `../wii/`. And the Wii menu itself only
  navigates for the TTR slot; the mii/music/codebusters channel pages are not
  wired to any channel tile.

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
  rules engine -- `scripts/tests.sh ers`), `ers/models.py` (shared
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

## King of Tokyo (`kot/`)

**Live at `https://kot.cgovind.com`.** The third game, same shape as ERS: Flask +
Flask-SocketIO, its own eventlet gunicorn `-w 1` on `127.0.0.1:5004`, its own venv
(`kot/venv`) and `.env` (both gitignored, hand-made on the box), sharing TTR's `users`
table for accounts. Stats live in `kot_stats`, games in `kot_games` / `kot_players`.

- **Layout:** `kot/game_logic.py` (pure rules engine), `kot/cards.py` (all 66 power
  cards), `kot/bot.py` (the bot brain, also pure), `kot/app.py` (auth, lobby, socket
  game loop, bot orchestration, ELO), `kot/models.py`, `kot/templates/` + `kot/static/`.
- **Tests:** `scripts/tests.sh kot` - `test_engine.py` covers the
  rules, `test_bot.py` covers the bot (liveness, legality, latency, strength).
- **A log line's `kind` is what makes the sound.** `LOG_SOUND` in `static/js/game.js`
  maps kinds to stings, and the same `kind` becomes the `.log-<kind>` CSS class, so
  the engine controls audio purely by how it labels a log line - which means adding
  or renaming a kind silently changes what the client plays. Kinds are `vp`, `energy`,
  `heal`, `attack`, `ko`, `buy`, `revive`, `win`, `sys`, `tokyo` and `tokyo_take`.
  **Only `tokyo_take` (actually moving in) is loud**; holding Tokyo, yielding it and
  being shoved out are `tokyo`, which shares the purple log styling but has no sound.
  `test_only_taking_tokyo_is_loud` pins that split; a separate test asserts every
  damaging/scoring one-shot card logs at least one loud kind.

### Bots

The host adds bots from the lobby ("+ Add bot"), same as ERS/TTR. They are ordinary
`KotPlayer` rows with `is_bot=True` and no `user_id`, so they take a monster and colour
like anyone else and are excluded from ELO. Names are drawn from `BOT_NAMES`
(Bot-zilla, Claw-de, Mechatron, The Terminator, Gloopy); **Bot-zilla gets 50% of the
weight on the first bot added**, the others split the rest.

- `bot.py` is pure decision-making - it never touches Flask, the DB or the clock.
  The dice choice is a memoized expectimax over the remaining rerolls, scoring every
  reachable tray with a context-aware utility. Everything else (yield, buys, hearts,
  Psychic Probe) is a policy in the same VP-equivalent units.
- **All strategic weights live in `bot.W`**, tuned by self-play. Re-run the sweep if
  you change one; `test_bot.py` has strength thresholds that will catch a regression.
- **Latency matters more than it looks.** One eventlet worker serves every live game,
  so a slow decision blocks *all* players' sockets, not just the bot's table. The
  search caches its reroll transition tables globally to stay ~3ms; a naive version
  measured 523ms. `test_dice_decision_is_fast` guards this.
- **Bots must always answer.** The engine parks the entire game in `yield`,
  `probe_window` or `token_choice` until the monster on the clock decides. Every bot
  step in `app.py` runs atomically under the game lock and is written to guarantee
  forward progress - the scheduler will not arm the same `(kind, seq)` twice, so an
  action the engine silently rejects would freeze the table. This is why the buy phase
  is one step ending in `end_turn`, and why `_bot_probe` always drains the queue.
- `_bot_kick(code)` is the single scheduler; it takes the per-game lock, so **never
  call it while holding that lock** (eventlet semaphores are not reentrant). Every
  state-mutating path ends by calling it.

### Replays

`kot_games.events_json` is the move-by-move replay: one entry per action (`roll`,
`resolve`, `yield`, `token_choice`, `buy`, `sweep`, `card_action`, `end_turn`,
`resign`, plus `start`/`end`), each with the choice made, a snapshot of every
monster's hp/vp/energy/cards, Tokyo occupancy, and the engine log lines that action
produced. Bot moves carry `"bot": true`. Note this only became true recently - games
before that have `start` and `end` and nothing in between, so any analysis has to skip
them.

## Drive (`drive/`)

**Live at `https://drive.cgovind.com`.** The fourth game, same shape as ERS/KoT:
Flask + Flask-SocketIO, its own eventlet gunicorn `-w 1` on `127.0.0.1:5005`, its own
venv (`drive/venv`) and `.env` (both gitignored, hand-made on the box), sharing TTR's
`users` table for accounts. A PolyTrack-style low-poly driving game: nine
point-to-point time-trial tracks, medal times, ghosts, and multiplayer rooms.

- **Guests can play, and a guest's times are not thrown away.** Driving alone needs
  no account at all (`/`, `/solo` and `/solo/<slug>` are open); sharing a room needs
  only a name (`/guest`). A guest's runs are kept *whole* - time, splits and replay -
  in `localStorage` by `static/js/pending.js`, best one per track, and submitted
  through the ordinary `/api/run` the moment the browser is logged in. That script is
  on **every** page via `base.html`, because the login that unlocks the times happens
  on `/login`, a page the game code never runs on. A rejected run is dropped (the
  server will not change its mind); a *failed request* is kept, so an offline lap
  goes up when you reconnect. `test_pending.js`-style coverage lives in
  `tests/test_pending.py`, which runs the real file in QuickJS against a stub browser.
- **Starts are counted as well as finishes**, because a board of finishes cannot
  say how many goes a track took out of you - and on a hard one that is most of
  the story. An attempt is *the clock starting*: `/api/start` is posted from the
  one place in `game.js` that calls `run.start()`, which is why a race counts
  too (the green light is a start like any other) and why loading the page does
  not. They live in their own `drive_starts` table, one row per (user, track) -
  `create_all` creates tables and not columns, so a new table lands on the live
  database by itself where a new column would need a migration, and a track you
  have started fifty times and never finished has no `drive_times` row to keep
  the count in. Finishes are not duplicated there; they stay in `DriveTime.runs`
  and `DriveStats.runs`. **A finish floors the start count in the row**
  (`_floor_starts`), because a finish implies a start but not that one was
  *recorded*: a guest posts none at all and their kept laps arrive at `/api/run`
  at login. Clamping only on the way out to the screen looks identical and is a
  trap - the next real start lands on a stored 0, disappears under the backlog of
  finishes, and goes on disappearing until it catches up, so the number looks
  right and stops moving. `tools/backfill_starts.py` is the same floor applied
  once to everything that was already there; **run it on the box right after the
  deploy that creates the table**, `--dry-run` first. It is a `max` per row, so
  it is safe to run twice. `_starts_for` still clamps on read, now only as cover
  for a database the backfill has not reached.
- **Being fast is not evidence of cheating.** There used to be a floor here:
  `tuning.MIN_PLAUSIBLE`, rejecting any time under 0.8 of `ideal`. But `ideal` is an
  estimate off a relaxed racing line and anyone who learns a track beats it, so the
  floor was measuring how conservative the estimate was, not dishonesty - and it
  punished exactly the people driving best. It is gone. What a run still has to
  survive is entirely about the *replay*: right duration, no teleports, starts on the
  line, through every checkpoint in order (`runcheck.validate`).
- **Layout:** `tuning.py` (every physics constant, in one place), `tracks.py` (the
  ribbon format + the pool, authored with a turtle `Builder`), `laptime.py` (racing-line
  relaxation + speed profile → medal times), `runcheck.py` (ghost packing, time
  validation), `models.py`, `app.py`, `static/js/` (`trackmesh.js`, `physics.js`,
  `course.js`, `render.js`, `sound.js`, `game.js`, `pending.js`, vendored
  `three.module.js`), `tools/shoot_tracks.py` (the preview pictures).
- **Three medals, and gold is the best one.** There used to be a fourth above it,
  `author`, at 0.94 of the ideal lap. The word names an authority rather than a
  standard, and it sat above the medal everybody already reads as the top one. The
  times did not move when it went, so nobody lost a medal - an old `author` row is
  shown as a gold by `DriveTime.medal_shown`, and `_MEDAL_FIELD` keeps the key so
  improving on one still decrements the right counter.
- **`MEDAL_MULT` is set against real times, not against the estimate.** It was
  1.04 / 1.18 / 1.42, calibrated off the simulated driver, and it was far too
  soft: every record actually set on the site sits between **0.77 and 0.90 of
  `ideal`** (mean 0.85), so a 1.04 gold was slower than what people were
  already driving and bronze at 1.42 could not be missed. The spread was the
  other half of it - gold to silver was 2.8-5.7s and silver to bronze 4.8-9.7s,
  three unrelated standards rather than three steps of one. Now **0.92 / 0.99 /
  1.07**: gold is beaten by the standing record on every track but only just on
  the tightest (Spiral Ascent, by 0.4s), and a step is a second and a half on
  the short tracks, three on the Gauntlet. Note `ideal` is a worse *per-track*
  predictor than the mean suggests (0.77 on Chicane Park against 0.90 on Spiral
  Ascent), so one global multiplier makes some golds harder than others - the
  fix for that is a better `laptime.py`, not per-track fudge factors. Two tests
  pin the intent (steps under 0.09 of the lap; gold under `ideal`), and
  `test_medals_bracket_the_simulated_driver` still requires the headless driver
  to manage a bronze. **Medals already earned do not move**: `DriveTime.medal`
  is written when the run is stored.
- **The record heads the medals card**, above gold/silver/bronze, as a green
  dot and a time laid out exactly like the three under it - the fourth time on
  the same list. Green because it is not a medal and cannot be won. **The
  holder's name is not on it**: whose lap it is belongs on the leaderboard, not
  on a card read at 200km/h with three other times on it, so `_track_payload`
  does not even send it. It rides along on the track payload (`_track_payload`,
  used by `/api/track/<slug>` *and* the play template) rather than in a request
  of its own, so it is right on the first paint and follows the switcher. That
  helper returns a **copy** - the dicts in `tracks_mod` are module-level and
  shared by every request.
- **`tuning.py` is the single source of truth for the simulation.** It is embedded in
  the play page as `window.DRIVE_TUNING` and read by the JS physics, and `laptime.py`
  uses the same numbers to derive medal times. There is deliberately no second copy of
  `ACCEL` in a .js file. Retuning the car retunes the medals.
- **A track is a ribbon of stations, not a grid of tiles.** Each station carries a
  centre `p`, a surface normal `n`, a road-right vector `lat` and a half-width `hw`,
  about 3.5 units apart; the road is the strip of quads between consecutive stations.
  That is the *whole* geometry - `trackmesh.js` is one loop over pairs. It replaced an
  8-unit grid of 90-degree corner tiles, which made every corner the same corner with a
  4-unit centreline radius no car could hold, and made a smooth elevation change
  impossible (a ramp was a crease between two flat tiles). Consequences worth knowing:
  corner radius and road width are free parameters, a gap is just stations flagged
  `air`, a barrier is a `wl`/`wr` flag on an edge, and a loop is a station list whose
  normal rotates.
- **The collision surface IS the render surface.** Every driveable quad goes into both
  the mesh and a spatial hash, so hills, banks, loops, crests and crossings all work
  through one closest-point query with no per-shape special cases - and nothing can look
  solid without being solid.
- **Steering rotates the car about the surface normal, not world up**, which is the
  whole reason a fully inverted loop needs no special case in the car code. Gravity is
  always applied and its normal component removed while grounded, so slope acceleration
  falls out for free.
- **Grass is meant to hurt.** `OFFROAD_DRAG` is a linear term, so the grass top speed
  is where `ACCEL - quadratic drag - OFFROAD_DRAG*v` hits zero: about half of
  `MAX_SPEED`. It was 0.55 (grass top speed ~36 against a road top speed of 44),
  which made a straight line across the infield simply the faster way round a corner.
  `test_grass_costs_you_the_corner` pins it as an acceleration budget rather than by
  driving anywhere, so it does not depend on where the grass happens to be.
- **Air pitch is deliberately lazy.** Holding the throttle pitches the nose down at
  `AIR_PITCH`, and `ALIGN_AIR` (which only runs when there is *no* pitch input) noses
  a car that took off from an uphill ramp down as well. At the original 1.5 and 2.6 a
  jump taken flat out - which is how every jump is taken - was pointing at the floor
  half a second off the lip. `test_the_car_does_not_nosedive_off_a_jump` bounds the
  drop over the first half second and still requires enough authority to aim.
- **Gate posts are walls, not scenery.** Every checkpoint's two posts go into the
  collider as well as the mesh, and sit just outside the kerb so the full road stays
  usable. `test_checkpoint_posts_are_solid_and_the_gate_is_not` pins both halves: the
  posts stop a car, and the mouth of the gate stays completely open.
- **The car is not glued to slopes.** `SNAP` is a 0.12-unit seam tolerance, nothing
  more, and there is no term scrubbing velocity along the surface normal - so a crest
  throws the car, as it should. `STICK_FORCE` only engages past `STICK_TILT` (about 32
  degrees off level), which in the pool means a loop's wall and roof and nothing else.
  Hills are *authored* smooth instead: `straight(l, rise=r)` smoothsteps its grade so it
  has no crease, and `crest`/`hump`/`jump` deliberately do, marking their stations
  `kick`. A hill needs `length >= sqrt(330 * rise)` or it becomes a jump by accident;
  `test_hills_are_eased_but_kickers_are_not` enforces it as a vertical curvature radius.
- **There are no vertical loops and no boost pads.** A plain vertical loop returns to
  exactly where it started, so its descent lands on its own climb - two surfaces a metre
  apart, which trapped cars. `Builder.loop` slides the exit sideways (smoothstepped, so
  both joins stay tangential) which fixes it completely. A helix about the direction of
  travel is the obvious alternative and does not work: its tangent sits ~55 degrees off
  its own axis, so it meets the road at a kink and the car drives into the barrier.
  Loop radius is bounded by physics - on the wall only `STICK_FORCE` opposes `v^2/R`, so
  radius 20 is about the minimum at racing speed.
- Tracks that float in the void (`ground: None`) are built with `rails=True`; tracks on
  the ground are not, so running wide there costs grass time instead of a respawn. The
  road sits ~1.2 above the grass plane, which is both why it reads as a raised ribbon
  and why the two never z-fight.
- **The ghost is a practice tool, so in a room it only exists in practice.** Solo it
  is the replay of your PB, fetched from the server. In a room it is your best lap of
  *that* practice session and nothing else - not your all-time PB, which was set on a
  different day against nobody - and it is not rendered at all from the countdown to
  the flag, whatever the setting says. A translucent car on a line nobody drove is one
  more thing to mistake for a rival.
- **A ghost frame is the pose at its own timestamp.** `Run._recordGhost` interpolates
  to exact multiples of `1/GHOST_HZ`. It used to accumulate dt and push a sample every
  time an interval had gone by, which meant the accumulator had to fill before frame 0
  was written - so frame 0 was the pose one interval *after* the start. Playback reads
  frame `t * GHOST_HZ` at run time `t`, so every ghost ever recorded played back 1/15s
  ahead of the lap it recorded: a couple of car lengths up the road, from the line to
  the flag, which is why the ghost appeared to start in front of you.
  `test_the_ghost_is_recorded_where_the_car_actually_was` drives a lap, notes where the
  car really was at each sample time and requires the two to agree.
- **Live races are in memory, not the DB.** A race ticks 20x/sec: clients are
  authoritative over their own car and emit `pose`, the server merges and fans out one
  snapshot per tick, and only the finished standings are written back. Cars are solid,
  resolved Mario-Kart-style (impulse + penetration spring, never positional snapping,
  tangential velocity preserved, per-pair bump cooldown) - see `Car.resolveCars`.
  `FLAG.BRAKE` rides along in the pose so a rival's brake lights work.
- **A room is a phase machine, and every way out of a phase is guarded.** The
  phases are `free` -> `qualifying` (90s) -> `countdown` (5s) -> `racing` ->
  `results` -> `free`. **A race must end**, and for a long time one could not:
  the only thing that armed the finish clock was somebody *finishing*
  (`FINISH_GRACE_MS`), so a race nobody finished never ended, and the room sat
  in `racing` for ever with the host unable to start another or change track -
  `set_track` and `start_race` both refuse mid-race, correctly, which is why
  the hang presented as "the host can't do anything". There are now four
  independent ways out, and `_maybe_close` is called from *every* path that can
  empty the road (finish, resign, disconnect, kick) rather than from the finish
  alone: "the last car is in" is not something only finishing can cause. Behind
  all of them is `_hard_race_ms` (8x a gold lap, clamped), which depends on
  nobody doing anything. **Every deferred close carries the `race_seq` it was
  armed for**, so a timer from one race can never close the next - which is
  live, because Rematch can fire inside the twelve seconds the results sheet is
  up.
- **Leaving mid-race is a DNF, not a disappearance.** `_drop` used to delete
  the car, and with it the loss, so the cheapest way to protect a rating was to
  close the tab - the one thing a rating system must never make the smart move.
  The car is now marked `gone` (excluded from `_snapshot` and `_live`, so it
  stops being drawn and stops holding the race open) but kept, so it is still
  in the standings and still rated. `_reset_race` is what finally drops it.
- **Two buttons for the two ways a race stops early**, both top centre with
  Start race, because they are the same kind of decision: start this, stop
  this, get out of this. Anyone can **Resign** (only while there is a race to
  resign from): a DNF, rated as one,
  and you drop straight back into practice without leaving the room. The host
  gets **End race**, which is a *cancellation*
  before the lights - `_abort_race`, nothing recorded - and the chequered flag
  after them, freezing the standings and rating them normally. Both arm on the
  first press and fire on the second, in place: they happen mid-drive, one
  press from the settings icon, and an "are you sure" overlay would cover the
  race you want to look at before answering it.
- **The grid is set by a 90-second qualifying session**, not by name. It was
  `sorted(fresh, key=name)`, which is both arbitrary *and stable* - so the same
  person started on pole every single race. Qualifying is ordinary practice
  with a clock on it: `qual_time` per improved lap, best one counts, a lap
  finishes into a toast and an automatic restart rather than the results sheet
  (covering the road while there are seconds left to improve is taking the
  session away). No lap at all means the back of the grid, shuffled. The host's
  Start race means "open qualifying" in `free` and "go now" during it, so
  ninety seconds never traps four people who are ready.
- **The grid is staggered and its sides alternate.** Ordering alone does not
  fix a two-by-two grid: cars level with each other reach the first corner
  together and the one on the inside of it simply gets there. So the odd slot
  of each row sits back 2.4 units (F1 style), and the server flips `flip` every
  race. **Nothing in the code knows which way the first corner goes** - not the
  server, not `placeOnGrid` - and nothing needs to: staggering stops the pair
  fighting for the same metre at the same instant, and flipping stops whichever
  side is the good one belonging to the same person twice running. Pole keeps
  its advantage; it was earned in qualifying, and taking it away would make the
  session pointless.
- **A split delta is measured against whatever that session is about**, which
  is three different laps - `splitRef` is the only thing that decides, and it
  returns null rather than comparing with the wrong one. **Racing: the
  leader**, specifically the quickest anybody *else* reached that checkpoint,
  which is by definition whoever led on the road at that point; if that is
  you, the same number read backwards is your gap to the nearest rival. Each
  client emits `split` and the server fans it straight back out rather than
  accumulating a table, because "the quickest anybody else" is a different
  number for every car and the server would have to send a different message
  per client. **Qualifying: your own best lap of the session**, kept whole as
  `qualRef` (a `lapTimeline`, the same distance-against-time table the ghost
  uses) rather than as a time, since a split needs the reference lap's shape.
  **Free practice: the ghost**, as before. The finish is the last split and
  follows the same rule.
- **The qualifying board is top right with the standings**, not top centre:
  it is the same kind of thing they are - who is where - and top centre is for
  the one button the room is waiting on, which a board above it pushed down
  into the road. The live standings are hidden during qualifying, since
  running order by distance means nothing when everyone is on their own lap
  and the board below already lists the same people in the order that counts.
- **On a phone the top-right stack does not slide out from under the drawer.**
  It does on a desktop, where the drawer is a 300px column. On a phone the
  drawer is most of the screen and hides the driving controls while it is
  open, so there is nothing left underneath to keep reachable, and sliding it
  only walked the icons into the top-centre buttons on the way past.
- **Guests are invisible to ELO.** They are in the room, on the grid and in the
  standings, but `_rate_race` ranks the logged-in players *among themselves*:
  beating a guest gains nothing, losing to one costs nothing. Anything else is
  a rating anybody can move by opening a second tab. The win and podium tallies
  were read off the overall standings, so a guest winning meant nobody was
  recorded as having won and a guest in the top three pushed an account off its
  own podium; they follow the rated order now, and retiring is never a win.
  **Two DNFs draw** (0.5), because their order is whichever they happened to
  give up in. Still needs two accounts - one has nobody to be rated against,
  and its race count no longer creeps up on races that were never rated.
- `?panel=qual|racing` pins a phase and fakes a session, for the same reason
  the other `?panel=` values exist: neither is a panel you can open, and
  getting a room into either takes two browsers and a stopwatch. Pinned rather
  than assigned - the room reports `free` the moment the socket connects, so a
  phase merely set at boot is gone before the shutter.

### Look: skies and worlds

Every track's art direction lives in one `PALETTES` entry in `trackmesh.js`.
Two optional fields do nearly all of it, and both are read by code that has no
idea which track it is looking at:

- **`sky`** - either a plain colour (the old two-tone dome) or a spec that
  `render.js` turns into a graded dome plus a sun, stars, and the track's own
  key light, hemisphere light and fog. `glowMode` matters: `horizon` smears the
  glow around the sun's *azimuth*, which is what makes a sunrise a sunrise;
  `radial` puts a halo around the disc, which is what any sun up in the sky
  wants. A sun drawn on the horizon must still have its *light* come from much
  higher, or nothing in the world gets lit.
- **`below`** - what is under a track that floats, dispatched on `kind`: a city
  drowned in cloud, a desert, a downtown, a lava field, or `void` (which also
  suppresses the distant floor plate). Ground tracks use `props`/`density`
  instead, which pick from the scenery vocabulary (conifer, bigpine, deadtree,
  rock, block) and `snow` turns on snow caps.

Rules learned the hard way, all from the same fact - **you look down on a world
below from a hundred units up, so you mostly read footprints**:

- dunes must be broad and very low, mesas narrow and tall, or both read as
  crates and pallets;
- cloud has to be clumps with sky between them, never an even coverage of
  anything, and it needs its own translucent mesh with `depthWrite` off so
  overlapping boxes accumulate into something dense in the middle and wispy at
  the rim. That is the whole difference between cloud and polystyrene;
- cloud only works when you look *down* on it. As a sky it reads as pale
  rectangles however it is shaded, which is why there is none in the dome.

**Nothing below is in the collider**, so the only thing keeping it out of the
track is the corridor test - and where scenery rises *above* road level (Jump
City) that test is load-bearing on its own, so it checks a whole footprint
rather than a centre point. Everything else also obeys a hard height cap under
the track's lowest station.

The single highest-leverage number in a palette is `hemi.ground`: it is the
bounce, so sand makes every underside warm over a desert, snow removes the dark
shadows from a winter scene, and molten orange is most of what separates a lava
field from a dark field.

### The HUD, the phone, and the type

- **The HUD is arranged the way Polytrack's is**, because it is the arrangement that
  keeps the middle of the screen empty: the clock is bottom centre, the split delta
  flashes directly above it at each checkpoint and fades, your personal best sits to
  its lower left and the speed to its lower right, with a speed bar under the lot.
  The corners are therefore free, which is the whole reason the touch controls fit.
- **Top left is where you are** - the track name, then what kind of session this is.
  Solo that is `Solo time trial`; in a room it is the room's *phase*, `Multiplayer -
  Free practice` / `Race about to start` / `Race in progress` / `Race finished`, which
  is the only place the phase is written down and is driven from one `PHASE_LABEL`
  table rather than a `setMode` call at each transition. **Top right is everything you
  can open**: the room drawer (rooms only), the track switcher, help, settings. Icon
  buttons and nothing else - plus, solo only, the medal times. In a room those are
  gone: a table of lap times floating over a race you are driving against other people
  relates to nothing on the screen. **Top centre is the host's Start race button**, and
  only that; it used to live in the room drawer, which closes itself, so the one thing
  everybody was waiting on was behind a panel.
- **Bottom left is the minimap with restart and last-checkpoint above it.** Those two
  used to head the settings sheet, which meant a menu you had to open to restart a run
  - which is the most common thing you do. They are hidden on touch, where the real
  buttons are under a thumb already. Note `@media (max-height: 460px)` moves `.hud-bl`
  to the *top* left under the track card, and has to release `bottom` as well as set
  `top`: an absolutely positioned box with both is stretched between them, which put
  the map on top of the track card on any screen short enough for that rule but too
  wide for the narrow one.
- **Solo is `/solo`, and the track is something you change from inside it.** There is
  no "pick a track" page any more: `/solo` opens whatever you were last driving (kept
  in the session, so the first paint is right) and the **track switcher** - the map
  icon, top right - swaps the world in place. `/solo/<slug>`
  still works for links and bookmarks and records itself as your last track; switching
  in-game posts to `/api/last-track` so coming back lands where you left off.
  **Everything that names the track has to follow the switcher**, and for a long
  time none of it did: you arrived from the home page on `/solo/<slug>`, changed
  track, and the leaderboard button still went to the board for the track you
  arrived on. `loadTrack` now repoints every `.board-link`, the page title and the
  help sheet's blurb, and `switchTrack` rewrites the URL with `history.replaceState`
  (not `pushState` - a switch is a setting inside one session, not somewhere to go
  Back out of; the query string is dropped because `?ghost=`/`?watch=` name a lap on
  the track you just left). **A room's URL is left alone** - it is the join code and
  has nothing to do with the current track. The same
  switcher is in a room, where only the host can pick - everyone else sees the same
  grid with the picking turned off, rather than a poorer version of it.
  **A card shows your time and not the record.** The record was on there too, and it
  made every card an argument: two times and two names, one of them somebody else's,
  on a menu whose only job is choosing where to drive. `_track_cards` therefore does
  not even send it. It is still on the board and the home page, which are for reading
  rather than picking.
- **The switcher's cards are photographs, not diagrams.** `tools/shoot_tracks.py`
  drives headless Chrome over every track with `?shot=1` (`S.shot` in game.js: HUD off,
  car hidden, camera behind the start line) and writes `static/img/tracks/<slug>.png`;
  the home page uses the same nine. **Re-run it after changing a track's geometry or
  sky** - a test asserts the files exist but nothing can notice that one is stale.
  Fitting the *whole* track in frame was tried first and is much worse: from far enough
  back to hold a point-to-point the road is a thread, and on Jump City it vanished into
  the towers entirely. Aiming level from 40 units up fails the same way - it photographs
  the horizon. Behind the start line, angled down at the road, is the shot.
- **Settings is only settings.** Title, an X, and the things you set. The session
  controls moved to the HUD, and it ends in one red **Leave**. The **Ghost** row is
  four states rather than a toggle, because "is there a ghost" is a dull question and
  "whose lap is it" is not: off / my best / world record / view others. In a room `my
  best` still means your best lap of *this* practice session, and `ghostOn()` still
  hides every ghost for the whole of a race. **`G` steps through the three**
  (`GHOST_CYCLE`: off, my best, world record) rather than toggling the last one
  back on - choosing between your own lap and the record is the choice worth
  having on a key. A lap chased off the board is deliberately not in the cycle,
  so pressing G leaves it. **Switching track turns the ghost off**: somewhere
  new is somewhere you are looking at rather than attacking, and a car you have
  never driven against on your first lap of it is in the way. That one is not
  remembered (`setGhostMode(..., {remember: false})`) - it is what the track
  starts as, not a preference, so the ghost you actually chose survives.
- **The world-record ghost has to be a lap that can be shown.** `?who=wr` took
  the fastest row and served whatever replay was on it, but a row keeps its
  time whether or not a ghost was stored beside it, so one old replay-less row
  made "world record" report that *nobody had set a time here* on a track with
  a full board. It now filters on `DriveTime.ghost`. Every other way in already
  only offered laps with a replay - the board sends `has_ghost` and hands back
  an id - which is exactly why "view others" worked where this did not. The
  message distinguishes the two facts now: no record at all, or a record with
  no replay.
- **The `?` sheet is Controls, and it is the controls and nothing else.** It
  used to open on the track blurb and close on two paragraphs about grass and
  crests, which is reading matter in front of somebody who pressed it to find
  out which key drifts. **The table follows the device** - `body.touch` swaps
  the keyboard rows for the gestures (`.keys-only` / `.touch-only`, the same
  mechanism as the start hint), so it never describes controls you do not have.
- **`/account` is two boxes and the second one is a table.** It was nine bordered
  stat tiles in a grid plus a tenth panel for the medal tally, which made ten pieces
  of furniture out of one thing - who you are and what you have done. Now one
  `.panel.profile` holds the figures (no border each; the panel is already the
  border) with the three medal counts under a hairline in the same box, since they
  are three more of the same kind of number. The standalone "Medals" total went with
  the redesign - it was the sum of three numbers sitting an inch below it. The track
  table uses `table-layout: fixed` with a `<colgroup>`, because on a 1080px page an
  auto table hands all the slack to the column that wants it least (the track name,
  two short words); under 700px it switches to auto with a `min-width` and scrolls
  inside `.tablewrap` rather than crushing six columns. The medal column carries the
  word as well as the swatch, and the row actions are icon+label buttons - a steering
  wheel for **Play** and a podium for **Leaderboard**, which used to read "drive" and
  "board" and nobody knew what a board was. Icons are inline SVG (`.icn`), never
  glyphs, for the reason the in-game ones are. **The rows are in the pool's
  order**, the same one the switcher, the home page and the leaderboard use.
  They used to be most-recent-PB first with the never-finished tracks in a
  block underneath, so the same track moved every time you drove and no two
  pages agreed on where to look for it; a track you started and never finished
  now sits in its own place in the list, muted and without a time or a medal.
- **`/leaderboard`'s track table is dated, not gold-timed.** The gold time used to be
  the fourth column; it is a property of the track rather than of the record, it is
  already on the track page and in the game, and sitting next to somebody's name it
  read as though they had won a gold rather than set the fastest lap on the site.
  `_records()` now carries the holder's `updated_at` (which is when *that lap* was
  set, since a better run replaces the row wholesale and stamps it). It is stored and
  rendered as UTC so the page is right with no JS, then rewritten into the reader's
  own timezone by the script at the foot of the template.
- **The board is in the game.** "View others" opens the leaderboard over the track;
  clicking a row opens that lap - its checkpoint splits against your own PB's, who set
  it, and **Watch it** / **Race this ghost**. Picking somebody to chase is something you
  do between runs on the track you are already on, so leaving the page for it would be
  the wrong shape. The public `/track/<slug>` page opens a lap the same way and links
  back in with `?ghost=<id>` / `?watch=<id>`; `/api/board` carries each row's id and
  splits so no second request is needed, and `/api/ghost/<slug>?who=<id>` serves one
  lap, **scoped to the track that asked** so a replay cannot be played against geometry
  it was never driven on.
- **Watching is not driving, so it takes the HUD away.** `body.watching` hides the
  clock, the map and the pedals - none of it is true during somebody else's lap - and
  leaves a bar with their name and the replay clock. The camera reads its speed and
  orientation back off the ghost's own motion, since a replay carries neither. It
  loops, and it refuses to start mid-race: it parks your car and stops your pose going
  out, which in a race would leave a stationary obstacle with your name on it.
- **`S.paused` is derived in one place** (`syncPaused`), from whether any panel is
  open, and only solo. Four panels each assigning it meant closing any one of them
  unpaused a game with another still open, and the car rolled away behind the sheet you
  were reading.
- **The start hint is shown once per session.** It tells a new player the one thing
  they cannot guess; by the second run it is a label floating over the road on every
  restart. Remembered in `sessionStorage`, so a reload does not restart the lecture,
  and the touch and keyboard wordings are two spans switched by `body.touch`.
- **`?panel=settings|help|tracks|board|qual|racing` (plus `&row=N`) opens a panel
  on load**, for the same reason `?touch=1` exists: there is no browser in CI and a
  screenshot cannot click, so it is the only way to look at a panel's layout.
  `qual` and `racing` also *pin* the phase and fake a session, since neither is a
  panel you can open and getting a room into either takes two browsers and a
  stopwatch.
- **The room drawer's button is a person, not a hamburger.** Three stacked bars sat
  next to the settings icon, which is three stacked sliders, and at a glance they were
  the same button. Chat is the last thing in the drawer so it takes the leftover height
  and the box you type into sits on the floor of the panel.
- **The room panel is a drawer at every screen size**, opened by that button. It
  used to be pinned open - a 274px column on a desktop, a 46vh slab across the bottom
  of a phone - so the multiplayer furniture sat on top of the road and the driving
  controls the entire time you were racing. It opens on arrival and closes itself when
  a race starts.
- **The two finish screens are deliberately different screens.** A time trial ends in
  a number, so `#results` is that number - big, centred, medal beside it, its rank
  under it - then `PB:` and `WR:` with their ranks, and Retry / Leaderboard / Exit.
  There are no sentences on it: "New personal best", "Ranked #3" and "That is the
  fastest time on this track" were all restating the numbers next to them. Only a
  *problem* gets a sentence (not logged in, offline). A race ends in an **order**, so
  `#raceOver` is the finishing order and the three things there are to do next -
  Practice, Quit, and Rematch for the host. Note that `/api/run`'s `medal`, `rank` and
  `is_record` all describe your stored PB row, not the lap you just drove: the lap's
  own medal is computed client-side and its own placing is the separate `run_rank`.
- **Touch controls: four driving buttons and no handbrake button.** Steering left,
  throttle and brake right, checkpoint and restart small above the steering. There
  is deliberately no fifth button, because there is nowhere a thumb can reach one:
  the right thumb is on a pedal essentially the whole lap and the left is on an
  arrow. The handbrake is **two gestures, one per thumb**, both handled in
  `bindInput`/`syncTouch` - so they are touch-input mappings and the physics and
  the keyboard are untouched, and either just adds `drift` to `touchKeys`.
  **Drag the throttle down** (`dragDrift`, threshold `DRAG_DRIFT`) and it comes
  on *without the thumb leaving the pedal*. That is the whole reason this thumb
  can carry a gesture after all: the objection was never the thumb but that every
  earlier candidate charged it a **release**, and coming off the power mid-corner
  is the one thing it must never do. A drag costs nothing, so the slide arrives
  under throttle, which is how the turn is actually driven. `DRAG_KEEP` is a
  second, lower threshold for letting off, so a thumb parked on the boundary
  cannot chatter the handbrake under itself. **Or double-tap and hold the arrow
  you are turning with**, so tap-tap-hold left is a handbrake turn to the left;
  the steering thumb arrives at a corner having just let go of the last arrow, so
  the second tap is the press it was going to make anyway. Letting go of either
  drops the handbrake, which is also how you catch the slide.
  **The two arrows share one double-tap timer, and a press on either voids the
  other's window**, so left-right-left is a correction rather than a double-tap of
  left. That sequence is fast and common, and it is exactly the moment - mid-corner,
  already saving it - when an unasked-for handbrake does the most damage.
  **`DOUBLE_TAP` is 50ms, which is far tighter than a normal double tap and is
  meant to be.** The other correction is coming off *the same* arrow and putting
  it straight back on, which is the exact shape of the gesture and cannot be told
  apart by anything except speed - at 320ms it fired on half of them. A gap this
  short is not something a thumb does while driving unless it means to.
  `test_touch.py` expresses its waits as fractions of `DOUBLE_TAP` rather than in
  milliseconds, so retuning the window retunes the tests instead of quietly
  invalidating them, and one test pins the intent directly: a 150ms re-grab is
  never a drift.
  The button that is drifting goes **amber** (`.tbtn.drifting`, `#ffd96b`) so it
  is obvious you asked for something different - that is the drift indicator, and
  it is on the on-screen button, *not* on the car. The car's tail lamps are
  two-state red (`BRAKE_ON`/`BRAKE_OFF` in `render.js`), and since `Car.braking`
  is `braking || handbrake` a handbrake slide lights them plain red like any
  other braking. `FLAG.DRIFT` is computed in `physics.js` and packed into the
  multiplayer pose but **consumed nowhere** - so amber tail lights on drifting
  cars, local and remote, are already wired for and just not drawn.
  Three earlier attempts are worth not repeating: a DRIFT button beside the pedals,
  which was literally unpressable; **brake-while-steering, which is unusable** -
  braking into a corner *is* steering, so it fired on essentially every corner and
  the car spent the lap sideways; and the same double-tap on the *brake*, which
  worked but charged the busy thumb a release mid-corner and could not be reached
  from the throttle at all. A handbrake has to be something you ask for, it cannot
  be a combination you were going to make anyway, and it should cost you nothing
  you were already holding.
  Touch state lives in its own `touchDown`/`touchKeys` sets rather than being poked
  into `keys`, since it is not a one-button-one-control mapping. Laid out with
  flexbox off the safe-area insets. `?touch=1` on a play URL forces the touch HUD on
  a desktop browser, which is the only way to look at the phone layout without one.
  **Checkpoint and restart sit above the pedals, not above the steering** - flag left,
  restart right, mirroring the pedals under them. You reach for them having just gone
  off, which is the moment the right thumb has stopped driving and the left one is
  still holding a corner.
- **Every icon is inline SVG, never a Unicode glyph.** A gear, a flag or a triangle
  from the symbol blocks renders as a full-colour emoji on some platforms and a
  hairline outline on others, so it can be neither styled nor trusted. The touch
  buttons are dark-fill/light-stroke for the same reason a white wash did not work:
  it vanishes against a bright sky or a sunlit kerb, and half of every track is one.
- `R` restarts the run; `T` (or Enter) goes back to the last checkpoint **with the
  clock still running** - the difference between "that lap is gone" and "I fell off".
- **The type is Titillium Web**, self-hosted in `static/fonts/` at four weights
  (~46KB total, no CDN). It replaced xkcd Script, which is a good joke on the landing
  page and the wrong voice entirely for a timing screen. Titillium is the closest
  freely licensable thing to Formula 1's own display face, which is proprietary.
  `--display` is headings and buttons, `--sans` is body text, both the same family.
  **This is Drive only** - the landing page and the other three games still use xkcd
  Script. Changing the font means changing `sw.js`'s precache list too.

### Tests

`scripts/tests.sh drive` - 301 tests, about 2:30. `test_tracks.py` and
`test_runcheck.py` are pure Python; `test_app.py` runs the real routes against a
throwaway SQLite file (the `/solo` memory, the board and ghost APIs, and a guest's run
being replayed after login). **`test_race.py` covers the room's race machine** -
the ways a race used to strand a room (no finisher, the last car leaving, a
stale timer closing the wrong race), the grid rules, and the rating rules. The
live room state is plain dicts, so it builds them directly rather than driving
a socket: what is under test is the bookkeeping, not the wire. **`test_sim.py` runs the game's real JavaScript
headlessly**: `tests/jsrt.py` strips the ES module syntax, swaps three.js for
`tests/three_stub.js` (real Vector3/Quaternion maths, inert graphics), and runs it in
QuickJS, then `tests/autopilot.js` *drives every track to the finish*. That is the test
that matters. Between them these have caught: road and grass being coplanar (the car
thought it was on grass for whole laps); wall collision geometry being double-sided so
contacts cancelled velocity twice per step; loops folding back onto themselves tightly
enough to trap a car forever, and later meeting the road at a 55-degree kink; checkpoint
planes being tracked across the whole map so real passes went unnoticed; the spawn point
having no road under it; a loop built with `self.x` for all three coordinates; and
several tracks that simply could not be finished. Needs `quickjs`, which lives in
`drive/requirements-test.txt` rather than `requirements.txt` so a plain deploy install
is unaffected. Without it these tests skip, which reads as a pass - `scripts/tests.sh`
and CI both install it.

**Two other files run browser JavaScript the same way, against a stub DOM instead of a
stub three.js.** `test_touch.py` lifts the touch bindings straight out of `game.js` and
drives them with synthetic touches (the handbrake gesture, and that left-right-left is a
correction rather than a double-tap); `test_pending.py` runs `pending.js` against a fake
`localStorage` and a `fetch` whose answers the test chooses. Both extract by marker
rather than line number, and `test_touch.py`'s stub deliberately lists every function
`bindInput` reaches for - if a new one appears the slice throws instead of quietly
testing nothing.

There is no browser in CI, so **check rendering by hand** before shipping a geometry
change: run the app on a spare port and screenshot it with headless Chrome
(`google-chrome --headless=new --use-gl=swiftshader --enable-unsafe-swiftshader
--virtual-time-budget=9000 --screenshot=out.png http://127.0.0.1:5055/solo/twist`). That
is how the forest of bridge piers and the dark undersides were found - both invisible to
every test. `?panel=`, `?touch=1` and `?shot=1` make the panels, the phone layout and a
clean preview shot reachable the same way. Note `app.py` runs with the reloader on, so a
backgrounded dev server needs `debug=False` or it forks and the port looks dead.

**Drive deploy:** the usual Action also (when `drive/.env` exists) builds/updates
`drive/venv` and `sudo systemctl restart drive`. nginx has a `drive.cgovind.com` vhost
proxying `:5005` with WebSocket upgrade, its own Let's Encrypt cert, and a Route 53 A
record. `/drive` on the main site 302-redirects there (`DRIVE_URL`). As with the others,
nginx/TLS/DNS/`.env` are hand-managed on the box.

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
`pip install -r requirements.txt`, and `sudo systemctl restart website`. That is
all it does: it ships `site/` and `app.py` but does NOT touch nginx, TLS, or the
box `.env`, and does NOT run `deploy/setup.sh`. Apply nginx/TLS/`.env` changes by
hand over SSH (`ssh ubuntu@54.157.20.148`; nginx config at
`/etc/nginx/sites-available/website`). `deploy/setup.sh` is the one-time bring-up.

Say "push" (or run `/push`) to commit, push, watch the Action, and verify the
live site in one go. If the SSH step fails with `dial tcp :22 i/o timeout`, the
`EC2_HOST` secret is stale: `gh secret set EC2_HOST --body 54.157.20.148`.

## Tests: run only what changed

The full suite is about five minutes (drive ~2:10, kot ~2:00, ers and the root
import check a few seconds each) and nearly every change is to exactly one game,
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
  `drive/`, `ers/` and `kot/` map to themselves; `app.py`/`site/` (and anything
  unrecognised, deliberately) map to `site`, whose "suite" is `import app` - the
  same check the deploy used to be. Docs, `deploy/` and `.claude/` map to
  nothing; **`scripts/` and `.github/workflows/` map to everything**, because a
  change to the selection itself is a change you cannot trust the selection about.
  `ttr/` maps to nothing: it is a submodule with its own repo and its own CI.
- **The venvs are gitignored, so a module you have never tested locally has
  none.** `tests.sh` builds it rather than reporting `No module named pytest`,
  which is not a test result. It also installs `requirements-test.txt` if there
  is one - that is where drive's `quickjs` lives, kept out of `requirements.txt`
  so the box never compiles a JS engine it has no use for. **Without quickjs,
  `test_sim.py` skips itself, which reads as a pass**, which is why CI installs
  it explicitly.
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
