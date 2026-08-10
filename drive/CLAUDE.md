# Drive (`drive/`)

**Live at `https://drive.cgovind.com`.** The fourth game, same shape as ERS/KoT:
Flask + Flask-SocketIO, its own eventlet gunicorn `-w 1` on `127.0.0.1:5005`, its own
venv (`drive/venv`) and `.env` (both gitignored, hand-made on the box), sharing TTR's
`users` table for accounts. A PolyTrack-style low-poly driving game: thirteen
point-to-point time-trial tracks, medal times, ghosts, and multiplayer rooms.

## Read the one doc your change is about

**This file is the whole of what every Drive change needs. Everything else is in
`drive/docs/`, and you should read exactly the ones your task touches — not all of
them.** They come to ~175KB together, which is more context than the whole of the
rest of the repo; any one of them is 11-28KB.

| doc | read it before touching |
|---|---|
| `docs/tracks-and-geometry.md` | `tracks.py`, `trackmesh.js`, `course.js`, the collider, boost pads, a track's palette or sky |
| `docs/runs-and-scoring.md` | `/api/run`, `/api/start`, `/api/activity`, `runcheck.py`, `verify.py`, `laptime.py`, `pending.js`, medals, ghost recording, the anti-cheat |
| `docs/racing-physics.md` | car-to-car contact, the slipstream, catch-up, remote-car interpolation, rival sound |
| `docs/rooms-and-races.md` | the room phase machine, qualifying, the grid, ELO, socket handlers, `racecheck.py`, the race recorder, `/race/<id>` |
| `docs/garage.md` | `garage.py`, `garage.js`, `CarView`, the car model, liveries, decals |
| `docs/badges.md` | adding, changing or recolouring a badge |
| `docs/hud-and-controls.md` | the in-game HUD, the settings/help sheets, the keys, touch controls, `sound.js`, the type |
| `docs/pages-and-boards.md` | the home page, `/solo` and its track switcher, the track cards, `/account`, `/leaderboard` |
| `docs/testing.md` | adding or removing a test, a surprising test failure, shipping a rendering change |

If a change spans two of them, read two. If you are only reading code to answer a
question, you may well need none.

## The track pool

The last three in the pool are the long ones, all difficulty 5 and all roughly
twice The Gauntlet: **Sandy Cove** (`cove`, a ground track - a coast road down
onto the beach and out along a pier over open water), **Cloudbreak** (`pillars`,
threaded between rock spires above an overcast) and **Rainbow Road** (`rainbow`,
half-pipes in deep space with almost no barriers). Cloudbreak and Rainbow
Road are both in `tracks.EXPOSED`.

**Big Red** (`bigred`, difficulty 4, 2405 units) is the descent: about 160 units
of near-monotone fall through a warm sunset, over a city drowned a long way below
it, with the one loop as the only climb. A pad-fed kicker off the slow hairpin
sends the car over a gap it clears the better part of two seconds later, well
below where it left; a second, smaller gap repeats the idea further on; a third,
the same size as the first, closes the lap in the air off the very last pad.
All three are kept short of what looks dramatic on paper - `AIR_PITCH` noses the
car down at a constant rate for as long as the throttle is held in the air, so a
longer flight just means landing further past level, not further downrange; a
shallow kicker buys drop and distance back without spending more of that
budget. It is in `tracks.EXPOSED` and keeps barriers in only four places - the
loop and each jump's landing straight, where a car arrives with no steering -
everywhere else the edge is just the edge. It is the only track in the pool
with **boost pads** on it.

## Layout

- **Layout:** `tuning.py` (every physics constant, in one place), `tracks.py` (the
  ribbon format + the pool, authored with a turtle `Builder`), `laptime.py` (racing-line
  relaxation + speed profile → medal times), `runcheck.py` (ghost packing, time
  validation), `verify.py` + `jsrt.py` + `three_stub.js` (the anti-cheat: a lap
  near the top of a board is re-driven through the game's own `Car.step` in
  QuickJS before it goes up), `racecheck.py` (the *room's* anti-cheat, which is
  a different question - see below), `models.py`, `app.py`, `static/js/` (`trackmesh.js`, `physics.js`,
  `course.js`, `render.js`, `sound.js`, `game.js`, `pending.js`, vendored
  `three.module.js`), `tools/shoot_tracks.py` (the preview pictures). The play
  page has three modes - `solo`, `room` and `replay` - and they are one template
  and one `game.js`, because a replay is a track, some cars and a clock and that
  is what the game already draws.

## The rules that hold everywhere in Drive

- **`tuning.py` is the single source of truth for the simulation.** It is embedded in
  the play page as `window.DRIVE_TUNING` and read by the JS physics, and `laptime.py`
  uses the same numbers to derive medal times. There is deliberately no second copy of
  `ACCEL` in a .js file. Retuning the car retunes the medals.
- **The leaderboard is for laps driven alone against the clock**, so nothing set in
  a room reaches it - no time, no medal, no ghost, no distance, no attempt.
  `countsForTheBoard()` in `game.js` is the single answer and both `/api/run` and
  `/api/start` read it. Details in `docs/runs-and-scoring.md`.
- **A lap that would place in the top 3 is re-driven on the server before it goes
  on the board**, through the real `Car.step` in QuickJS, against the input stream
  and the anchors the client recorded (`verify.py`). It waits in
  `drive_run_checks` rather than in `drive_times` while that happens, so nothing
  public shows a lap nobody has checked. Anything that changes the physics, the
  recording or `/api/run` has to keep that working: read
  `docs/runs-and-scoring.md` first, and note that `tests/test_verify.py` drives
  real laps and will tell you if the honest floor has moved.
- **A room is checked too, but for a different thing and with a different
  temper.** `racecheck.py` bounds the live pose stream and scans the recorded
  race at the flag: it catches teleports, speed hacks and a win claimed without
  driving, and it deliberately cannot see a slightly richer engine, which needs
  the input stream a race does not carry. A failed pose is **dropped, not
  punished**, and the only consequence a car can suffer is going unrated,
  silently. Read `docs/rooms-and-races.md` before touching `on_pose`,
  `on_finish`, `on_qual_time` or `_rate_race`.
- **Nothing cosmetic may touch the simulation** - not ride height, not `CAR_RADIUS`,
  not the wheel radius, not a gram of mass. A cosmetic that changed how the car
  drives would make every time on the board mean something different.
- **There is no browser in CI, so check rendering by hand** before shipping a
  geometry, livery or HUD change. `?panel=`, `?touch=1`, `?shot=1`, `?view=`,
  `?draft=` and `?catchup=` exist so a screenshot can reach a state a click
  otherwise would. See `docs/testing.md`.
- **Re-run `tools/shoot_tracks.py` after changing a track's geometry or sky.** A
  test asserts the preview files exist; nothing can notice that one is stale.
- Tests: `scripts/tests.sh drive` - about 889 tests in 100s, **run serially on
  purpose** (see `docs/testing.md`). A third of that is the anti-cheat driving
  real laps and re-driving them, which is the price of the one test that
  matters: a lap somebody actually drove has to be accepted. Nothing in the
  suite may sleep; `tests/conftest.py` enforces it.

## Deploy

**Drive deploy:** the usual Action also (when `drive/.env` exists) builds/updates
`drive/venv` and `sudo systemctl restart drive`. **`quickjs` is in
`requirements.txt` now, not `requirements-test.txt`** - the anti-cheat runs the
real `static/js` files in production, so the box needs a JS engine and the first
deploy after that change compiles one. Nothing else is new on the box: the
verifier is a subprocess `app.py` starts, so there is no service to install and
nothing to restart. If it ever needs turning off, `DRIVE_VERIFY=0` in the box
`.env` puts `/api/run` back to storing laps directly. nginx has a `drive.cgovind.com` vhost
proxying `:5005` with WebSocket upgrade, its own Let's Encrypt cert, and a Route 53 A
record. `/drive` on the main site 302-redirects there (`DRIVE_URL`). As with the others,
nginx/TLS/DNS/`.env` are hand-managed on the box.

