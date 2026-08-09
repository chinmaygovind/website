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
| `docs/runs-and-scoring.md` | `/api/run`, `/api/start`, `/api/activity`, `runcheck.py`, `laptime.py`, `pending.js`, medals, ghost recording |
| `docs/racing-physics.md` | car-to-car contact, the slipstream, catch-up, remote-car interpolation, rival sound |
| `docs/rooms-and-races.md` | the room phase machine, qualifying, the grid, ELO, socket handlers, the race recorder, `/race/<id>` |
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

**Big Red** (`bigred`, difficulty 4, 1868 units) is the descent: about 75 units
of near-monotone fall through a red sunset, over a city drowned a long way below
it, with the one loop as the only climb. It is the only track in the pool with
**boost pads** on it.

## Layout

- **Layout:** `tuning.py` (every physics constant, in one place), `tracks.py` (the
  ribbon format + the pool, authored with a turtle `Builder`), `laptime.py` (racing-line
  relaxation + speed profile → medal times), `runcheck.py` (ghost packing, time
  validation), `models.py`, `app.py`, `static/js/` (`trackmesh.js`, `physics.js`,
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
- **Nothing cosmetic may touch the simulation** - not ride height, not `CAR_RADIUS`,
  not the wheel radius, not a gram of mass. A cosmetic that changed how the car
  drives would make every time on the board mean something different.
- **There is no browser in CI, so check rendering by hand** before shipping a
  geometry, livery or HUD change. `?panel=`, `?touch=1`, `?shot=1`, `?view=`,
  `?draft=` and `?catchup=` exist so a screenshot can reach a state a click
  otherwise would. See `docs/testing.md`.
- **Re-run `tools/shoot_tracks.py` after changing a track's geometry or sky.** A
  test asserts the preview files exist; nothing can notice that one is stale.
- Tests: `scripts/tests.sh drive` - about 853 tests in 70s, **run serially on
  purpose** (see `docs/testing.md`). Nothing in the suite may sleep;
  `tests/conftest.py` enforces it.

## Deploy

**Drive deploy:** the usual Action also (when `drive/.env` exists) builds/updates
`drive/venv` and `sudo systemctl restart drive`. nginx has a `drive.cgovind.com` vhost
proxying `:5005` with WebSocket upgrade, its own Let's Encrypt cert, and a Route 53 A
record. `/drive` on the main site 302-redirects there (`DRIVE_URL`). As with the others,
nginx/TLS/DNS/`.env` are hand-managed on the box.

