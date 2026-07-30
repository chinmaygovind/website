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

## King of Tokyo (`kot/`)

**Live at `https://kot.cgovind.com`.** The third game, same shape as ERS: Flask +
Flask-SocketIO, its own eventlet gunicorn `-w 1` on `127.0.0.1:5004`, its own venv
(`kot/venv`) and `.env` (both gitignored, hand-made on the box), sharing TTR's `users`
table for accounts. Stats live in `kot_stats`, games in `kot_games` / `kot_players`.

- **Layout:** `kot/game_logic.py` (pure rules engine), `kot/cards.py` (all 66 power
  cards), `kot/bot.py` (the bot brain, also pure), `kot/app.py` (auth, lobby, socket
  game loop, bot orchestration, ELO), `kot/models.py`, `kot/templates/` + `kot/static/`.
- **Tests:** `cd kot && venv/bin/python -m pytest tests/` - `test_engine.py` covers the
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

- **Guests can play.** Driving alone needs no account at all (`/` and `/solo/<slug>`
  are open); sharing a room needs only a name (`/guest`). Times only reach the
  leaderboard when logged in - guests keep a PB in `localStorage`.
- **Layout:** `tuning.py` (every physics constant, in one place), `tracks.py` (the
  ribbon format + the pool, authored with a turtle `Builder`), `laptime.py` (racing-line
  relaxation + speed profile → medal times), `runcheck.py` (ghost packing, time
  validation), `models.py`, `app.py`, `static/js/` (`trackmesh.js`, `physics.js`,
  `course.js`, `render.js`, `sound.js`, `game.js`, vendored `three.module.js`).
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
- **Live races are in memory, not the DB.** A race ticks 20x/sec: clients are
  authoritative over their own car and emit `pose`, the server merges and fans out one
  snapshot per tick, and only the finished standings are written back. Cars are solid,
  resolved Mario-Kart-style (impulse + penetration spring, never positional snapping,
  tangential velocity preserved, per-pair bump cooldown) - see `Car.resolveCars`.
  `FLAG.BRAKE` rides along in the pose so a rival's brake lights work.

### The HUD, the phone, and the type

- **The HUD is arranged the way Polytrack's is**, because it is the arrangement that
  keeps the middle of the screen empty: the clock is bottom centre, the split delta
  flashes directly above it at each checkpoint and fades, your personal best sits to
  its lower left and the speed to its lower right, with a speed bar under the lot.
  The corners are therefore free, which is the whole reason the touch controls fit.
- **Top left is where you are** (track name, then `Solo time trial` /
  `Multiplayer lobby` / `Race in progress`); **top right is everything you can open**:
  the room drawer (rooms only), help, settings. Three icon buttons and nothing else.
- **The room panel is a drawer at every screen size**, opened by the hamburger. It
  used to be pinned open - a 274px column on a desktop, a 46vh slab across the bottom
  of a phone - so the multiplayer furniture sat on top of the road and the driving
  controls the entire time you were racing. It opens on arrival and closes itself when
  a race starts.
- **Touch controls: four driving buttons and no handbrake button.** Steering left,
  throttle and brake right, checkpoint and restart small above the steering. There
  is deliberately no fifth button, because there is nowhere a thumb can reach one:
  the right thumb is on a pedal essentially the whole lap and the left is on an
  arrow. **Brake plus steer is the handbrake instead** - derived in `syncTouch`, so
  it is a touch-input mapping and the physics and the keyboard are untouched. (A
  DRIFT button on the right was tried first and was literally unpressable; a
  steer-and-drift second row on the left worked but was not worth the clutter.)
  Touch state lives in its own `touchDown`/`touchKeys` sets rather than being poked
  into `keys`, since it is not a one-button-one-control mapping. Laid out with
  flexbox off the safe-area insets. `?touch=1` on a play URL forces the touch HUD on
  a desktop browser, which is the only way to look at the phone layout without one.
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

`cd drive && venv/bin/python -m pytest tests/` - 217 tests. `test_tracks.py` and
`test_runcheck.py` are pure Python. **`test_sim.py` runs the game's real JavaScript
headlessly**: `tests/jsrt.py` strips the ES module syntax, swaps three.js for
`tests/three_stub.js` (real Vector3/Quaternion maths, inert graphics), and runs it in
QuickJS, then `tests/autopilot.js` *drives every track to the finish*. That is the test
that matters. Between them these have caught: road and grass being coplanar (the car
thought it was on grass for whole laps); wall collision geometry being double-sided so
contacts cancelled velocity twice per step; loops folding back onto themselves tightly
enough to trap a car forever, and later meeting the road at a 55-degree kink; checkpoint
planes being tracked across the whole map so real passes went unnoticed; the spawn point
having no road under it; a loop built with `self.x` for all three coordinates; and
several tracks that simply could not be finished. Needs the optional `quickjs` package;
those tests skip without it, so a plain deploy install is unaffected.

There is no browser in CI, so **check rendering by hand** before shipping a geometry
change: run the app on a spare port and screenshot it with headless Chrome
(`google-chrome --headless=new --use-gl=swiftshader --enable-unsafe-swiftshader
--virtual-time-budget=9000 --screenshot=out.png http://127.0.0.1:5055/solo/twist`). That
is how the forest of bridge piers and the dark undersides were found - both invisible to
every test.

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
