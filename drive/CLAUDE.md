# Drive (`drive/`)

**Live at `https://drive.cgovind.com`.** The fourth game, same shape as ERS/KoT:
Flask + Flask-SocketIO, its own eventlet gunicorn `-w 1` on `127.0.0.1:5005`, its own
venv (`drive/venv`) and `.env` (both gitignored, hand-made on the box), sharing TTR's
`users` table for accounts. A PolyTrack-style low-poly driving game: twenty-two
tracks, medal times, ghosts, and multiplayer rooms. Eighteen are point-to-point;
**Spa-Francorchamps, Silverstone and Monaco are the three closed circuits** and
start and finish on the same line. **Costco Wholesale, Monaco and Railway
Raceway are the three that go under something** - the Costco's warehouse roof,
Monaco's tunnel and Rickety Rails' cave roof are the only solid geometry over
the road anywhere in the pool, and the last of those is over *all* of it.

## Read the one doc your change is about

**This file is the whole of what every Drive change needs. Everything else is in
`drive/docs/`, and you should read exactly the ones your task touches — not all of
them.** They come to ~360KB together, which is more context than the whole of the
rest of the repo; any one of them is 11-28KB.

| doc | read it before touching |
|---|---|
| `docs/track-defects.md` | **any track work at all.** The running list of what goes wrong in a track and what is already checked for you. Deliberately short - it is meant to be read every time, unlike the rest of this table |
| `docs/tracks-and-geometry.md` | `tracks/`, `trackmesh.js`, `course.js`, the collider, boost pads, a track's palette or sky |
| `docs/runs-and-scoring.md` | `/api/run`, `/api/start`, `/api/activity`, `runcheck.py`, `verify.py`, `laptime.py`, `pending.js`, medals, ghost recording, the anti-cheat |
| `docs/racing-physics.md` | car-to-car contact, the slipstream, catch-up, remote-car interpolation, rival sound |
| `docs/rooms-and-races.md` | the room phase machine, qualifying, the grid, ELO, socket handlers, `racecheck.py`, the race recorder, `/race/<id>` |
| `docs/bots.md` | `bot.js`, `botworld.js`, `botsim.py`, `bots.py`, the hot laps in each track folder, adding a bot to a room |
| `docs/garage.md` | `garage.py`, `garage.js`, `CarView`, the car model, liveries, decals |
| `docs/badges.md` | adding, changing or recolouring a badge |
| `docs/hud-and-controls.md` | the in-game HUD, the settings/help sheets, the keys, touch controls, `sound.js`, the type |
| `docs/pages-and-boards.md` | the home page, `/solo` and its track switcher, the track cards, `/account`, `/leaderboard` |
| `docs/portal.md` | `portal.py`, `static/js/portal.js`, `/api/portal/auth`, the sitelock, `login.html`, who a player is inside a frame |
| `docs/track-maker.md` | `/make`, `tracks/moves.py`, `tracks/starters.py`, `scenery_kit.js`, the scenery sandbox, the AI panel, saving and publishing a player's track, `tools/adopt_track.py` |
| `docs/testing.md` | adding or removing a test, a surprising test failure, shipping a rendering change |

If a change spans two of them, read two. If you are only reading code to answer a
question, you may well need none.

## The track pool

**Difficulty is a label, not a measurement**, and it is not length: the pool's
ratings were re-cut across all twenty tracks in Aug 2026 to run 1 to 5 roughly
in pool order, so the first three tracks are 1s and the hard ones are late.
Nothing derives from the number - it is five pips on a card, coloured green
through to red by `--diff-1`..`--diff-5` in `style.css` - so changing one is a
one-line edit in its `track.py`. It is deliberately *not* in the
`test_tracks_did_not_move` snapshot for that reason; see the note there.

Three of the pool are the long ones, all roughly twice The Gauntlet: **Sandy
Cove** (`cove`, difficulty 4, a ground track - a coast road down
onto the beach and out along a pier over open water), **Cloudbreak** (`pillars`,
difficulty 5, threaded between rock spires above an overcast) and **Rainbow
Road** (`rainbow`, difficulty 4,
half-pipes in deep space with almost no barriers). Cloudbreak, Rainbow Road
and Big Red are all in `tracks.EXPOSED`.

**Big Red** (`bigred`, difficulty 5, 3335 units - now the longest track in
the pool) is the descent: about 220 units of near-monotone fall through a red
sunset, over a city drowned a long way below it, with the one loop as the only
climb. Four full-size jumps and one small one break the fall up. A pad-fed
kicker off a hairpin sends the car over a gap it clears the better part of two
seconds later, well below where it left, and the back third of the lap is a
closing run of hairpin-into-jump repeated twice more - a hairpin resets the
speed, a pad feeds the next jump - so the last stretch is hairpin, jump,
hairpin, jump, flag. Every jump is kept short of what looks dramatic on paper -
`AIR_PITCH` noses the car down at a constant rate for as long as the throttle
is held in the air, so a longer flight just means landing further past level,
not further downrange; a shallow kicker buys drop and distance back without
spending more of that budget. It is in `tracks.EXPOSED` and keeps barriers in
only five places - the loop and each big jump's landing straight, where a car
arrives with no steering - everywhere else, including every closing hairpin,
the edge is just the edge. It has six **boost pads** on it, and it was the only
track in the pool with any until the Costco's two travelators.

**Spa-Francorchamps** (`spa`, difficulty 3, 3167 units, ~71s - second only to
Big Red) is a compressed recreation of the real circuit, and it is the odd one
out in the pool in four ways that all cost something to get right. Read
`docs/tracks-and-geometry.md` before touching any of them.

- **It is a closed lap** (Silverstone and Monaco are the others). The ribbon is a ring: the last station lands
  back on station 0 and the finish gate *is* the start gate
  (`Builder.finish_at_start`). That works only because `course.js` refuses to
  credit the finish until every checkpoint is behind you, so the car crossing
  the line at t=0 is ignored. `closed = True` in its `track.py` is what says so,
  and `self_proximity`/`crossings` measure station gaps **circularly** for such a
  track - a linear gap reads the join as the worst car trap on the track.
- **It closes itself.** `tracks/solver.py` adjusts a leg or two at import until
  the ribbon meets itself in position, heading *and* height, and reports what it
  changed. It costs 16-32ms and only closed tracks pay it. Spa nominates which
  legs with `FREE()`, because every corner on it is a real place and a solver free
  to choose would sooner lengthen the pit straight by 12% - which closes the lap
  and stops it being Spa. **This used to be `tools/close_spa.py`**, run by hand
  with its two answers pasted into the builder and a docstring warning that
  changing any *other* length silently invalidated them. That tool is gone.
- **It is the only track with `pal.terrain`.** Every other ground track sits on one
  flat collidable quad at `track.ground`; Spa falls 63 units, which would put
  that quad through the road as an opaque ceiling. `pal.terrain` swaps it for a
  height field sampled off the ribbon itself (`buildTerrain`), and the same
  sampler places the trees, the gravel, the armco and the grandstands.
- **Its barriers are not `rail`.** A rail sits on the kerb; Spa's armco is a
  *backstop* set 26 units out, past the gravel, so running wide costs time
  rather than the lap. It is drawn off the ribbon in `addArmco` and skips itself
  wherever the circuit doubles back and there is no room.

Its grandstands, pit building, start gantry and sponsor boards are the pool's
only trackside furniture, configured in the `spa` palette by **fraction of the
lap** so they survive the ribbon being re-solved. The boards are also the only
textured geometry in the whole game: nine sponsors, each drawing its own canvas
in `SPONSORS`, two in three of them this site's own games and the rest what a
circuit actually carries. **Every mark on them is a file** in
`static/img/sponsors/` - three from inside this repo, four the brands' own off
Wikipedia - and none is drawn in code any more. Only one board needs type for
its name (`GO BIRDS`, which is a fan phrase and so exists as no artwork
anywhere); the other three outside brands ship their own lettering inside the
artwork, which is the only correct version of it, since all of them use
commissioned faces no font will give you. They need four fonts nothing else here
is set in, and both the fonts and the logos land *after* the track is built -
see `docs/tracks-and-geometry.md` before touching any of it, because every way
of getting this wrong is silent, and three of them have been.

**Costco Wholesale** (`costco`, difficulty 3, 2106 units, ~50s) is the one that
goes indoors, and it is the only track in the pool with solid geometry *over* the
road. You start in the car park, drive in through the front doors, run four
warehouse aisles with pallet racking either side, take a travelator up onto the
rooftop car park, cross back over the aisles on the deck, come down, and go out
through the checkouts past the food court. Read `docs/tracks-and-geometry.md`
before touching it.

- **The shell is authored, not derived, and it is now authored once.**
  `SHELL_X`/`SHELL_Z`/`SHELL_CEIL` live in `tracks/costco/track.py` and
  `tracks/costco/palette.py` imports them. Deriving them from the road would be
  circular - the wall position would depend on which stations you used to decide
  where the wall goes. **They used to exist twice**, once in Python and once in a
  JavaScript palette, pinned by a test that scraped trackmesh.js with a regular
  expression; the palettes are Python now and both that test and Sandy Cove's
  equivalent are deleted. Everything else - the doorways, the holes the
  travelators punch in the roof, where the racking stands - **is** derived, and
  `test_the_warehouse_fits_inside_its_own_walls` is what fails when a leg grows
  past a wall.
- **The building lives in `tracks/costco/scenery.js`**, not in trackmesh.js. It is
  a sibling of `addScenery` rather than a use of Spa's furniture: `addFurniture`
  is only reachable from inside the terrain branch, and a flat track has no height
  field for it.
- **The rooftop deck is the only crossing**, and it clears the floor by the whole
  of `DECK` (19), which is why `gate_ceil` comes out at its full 14. Both
  travelators climb along the one row of the building with no aisle under it, so
  nothing is ever over anything else part-way up.
- **`SHELL_CEIL` and `DECK` move together.** The roof-hole test needs a real gap
  between them, so the roof cannot be raised without raising the deck over it, and
  raising the deck lengthens both travelators (`length >= sqrt(330 * rise)`) - which
  moves where the ramp ends, which is what the containment test is watching.
- **The deck's parapet is collider geometry, not a ribbon `rail`**, because a
  ground track has to carry zero walled stations.
- Two things about the camera set numbers here. It rides ~4.3 units over the car,
  so the 15-unit ceiling clears it easily; and it trails ~11.6 units *behind*, so
  it goes through a doorway a beat after the car does - which is why every wall is
  crossed square on a straight, the openings are full height with no lintel, and
  the entrance header's underside is held at 9.5.

**Monaco** (`monaco`, difficulty 5, 2436 units, ~58s) is the third closed
circuit, and the only one in the pool with **no run-off anywhere**: a ribbon
`rail` sits on the kerb for the whole lap, so 216 of the chords that would pay as
a shortcut are all blocked and none is open. Read
`docs/tracks-and-geometry.md` before touching it.

- **It is the only track with no ground at all that is not floating in the void.**
  `ground = None`, and the hillside, quays, harbour and city are built in
  `tracks/monaco/scenery.js`. That is forced rather than chosen: **the circuit
  crosses over itself** - Beau Rivage climbs directly above the harbour front,
  the two roads' tarmac overlapping in plan with nine units of air between them -
  and a `pal.terrain` height field is single-valued, so it drew the upper road as
  a solid slab over the lower one. It is Mount Joy's pattern (a lower envelope of
  upward cones, which arithmetically cannot come up through a road), built as a
  chamfer sweep so it has no reach cutoff.
- **`rails = True` is the point rather than a concession.** A floating track
  carries barriers by default and `test_barriers_are_opt_in` *requires* them,
  which is the opposite of the fight a ground track has - and walls on both kerbs
  for a whole lap is exactly what Monaco is. It is the only circuit in the pool
  where that is correct.
- **The tunnel is found, not authored.** The stations the hill closes over are the
  longest run with another part of the circuit above them, so the bore moves if
  the ribbon is re-solved. Those stations are excluded from the height field -
  include them and the envelope is pulled down to the tunnel floor and the hill
  above it vanishes, leaving an open cutting.
- **The harbour is a flood fill, and the obvious rule does not work here.**
  Point-in-polygon on the ribbon fails because a self-crossing ribbon flips
  even-odd parity, so half the port reads as outside. Port Hercule is instead the
  low ground inside the circuit, seeded at the centroid of the lowest quarter of
  the lap and bounded by the road corridor and by land rising out of it.
- **Every road edge is carried down to the field on a retaining wall.** Two roads
  nine units apart in height cannot both have ground snug under them, so the
  lower one wins the gap and the upper is left with a drop - which is what a
  hillside city is, but it has to be built or the road floats and the engine's
  trestles (a flat 15.7 units under every station of a groundless track) hang in
  the open air under it.
- The geometry is off OSM relation 148194 and a DEM, the same method as
  Silverstone; the docstring in `track.py` is the whole account, including the
  three things it got wrong first.

**Dino Park** (`dino`, difficulty 4, 2797 units, ~59s ideal) is the jungle, and
it is the only track in the pool with anything on it that **moves**. Read
`docs/tracks-and-geometry.md` before touching it.

- **It has the pool's only moving obstacles, and their clock is an integer.** A
  herd of eight hadrosaurs walks across the road - three on the opening flicks,
  five on the wide floor before the canyon - and they are solid: `Movers` in
  `trackmesh.js` poses each one as a pure function of the **physics step index**,
  which the browser takes from `Run.stepIndex()` and `verify.py` names `i * S +
  k`. Two names for one number, so a re-driven lap meets the herd in exactly the
  same place; a wall-clock mover would drift, and a missed contact is binary.
  They are `walls()` only, never ground, so the racing line, `laptime.py` and
  every medal are untouched by them.
- **The canyon crossing has no road on it.** The stations are flagged by
  `Builder.skin`, which makes `trackmesh.js` draw no surface, no kerb and no slab
  - only the collider quad - and `scenery.js` builds a sauropod's back *through*
  those same station points, with the upper flank added to the collider as
  `KIND.ROAD`. So the drivable surface is three times the width of the road it
  replaced, it is what you can see, and running wide is a slide down a shoulder.
  No barriers, for the same reason.
- **The three set pieces are found, not told.** The falls hang on the lap's
  highest stations, the herd walks the widest, the animal is the `skin` run and
  the creek is under the ribbon's own `air`. There is no pair of fractions in two
  languages to drift apart, and `track.py` states the rule the layout has to keep.
- **`ground = None` with the world in `scenery.js`**, Mount Joy's pattern for
  Monaco's reason: a `pal.terrain` field is single-valued and would fill the
  gorge in under the animal. The floor is a lower envelope of upward cones as a
  chamfer sweep, collided as `KIND.OFFROAD` within 120 units - which is why the
  track is `exposed` with rails in one place only.

**Rickety Rails** (`railway`, difficulty 5, 3006 units, ~70s ideal - the
longest lap in the pool) is the mine, and it is the pool's first track with a
roof over the whole lap. The road is a mine-cart trestle over a ravine:
`ground = None`, with the bents drawn in `scenery.js` because the engine's own
legs are a flat `p[1] - 16` and the floor is forty units down. Read
`docs/tracks-and-geometry.md` before touching it.

- **It is `exposed`, and the barrier is the timbering.** The first version was
  `rails = True` - the pool default for a floating track - which walled 96% of
  the lap and was boring to drive for the reason Cloudbreak's note gives: the
  rail answers the only question a corner asks, and here it also hides the drop
  that is the whole subject. Instead every portal-frame upright and lamp post is
  `KIND.WALL` collider geometry at `hw + 1.7`, so a wide moment hits timber and
  the racing line never touches one. It **has** to be scenery rather than a rail:
  `test_barriers_are_opt_in` counts walled *stations*, so railing the posts would
  cost the track its flag. Same pattern as the Costco's racking and Silverstone's
  anti-cut barriers, and it is pinned in `test_scenery.py` - if that `wall` count
  falls, the posts have stopped being solid.
- **The loop needed both shortcut fixes, and they fail differently.** `loop`
  slides its exit sideways so the descent misses the climb, and that is a chord
  you can drive: `tools/cut_check.py` found a 31-unit line skipping 161 units of
  road. A rail down the inside closes every version of it on the ground and none
  through the air - a car that falls off the climb still lands past the exit - so
  there is *also* a checkpoint on the loop's exit, which kills any span at any
  height. 384 open chords to 24.

- **The cave is two height fields and they are the same trick twice.** The floor
  is Mount Joy's lower envelope of upward cones (at most `y - DROP` at every
  station, so it cannot come up through the trestle for any layout); the roof is
  an **upper** envelope of downward cones, at least `y + head` over every
  station, so it cannot come down through the road either. Where the two cross,
  the cave is sealed - **the cavern wall is not geometry, it is the meeting
  line**, about 30 units out in the drifts and 36 in the vault. Both are chamfer
  sweeps, so they cost O(cells) and have no reach cutoff.
- **The gap stations are in the roof field and not the floor one**, and that is
  the whole of the winze: excluded from the floor, so the ground under the jump
  falls away into a pit; included in the roof, so there is headroom over the
  flight. Including them in the floor is Shroom Street's mistake with the sign
  flipped.
- **How much headroom the roof keeps is authored as fractions of the lap**, the
  way Spa places its grandstands and for Monaco's tunnel's reason: which stretch
  is a tight timbered drift and which is an open cavern is a fact about the
  place, not something the ribbon implies. It is also what tells the two kinds of
  place apart at speed, since the timbering only goes in where the roof is low.
- **None of it is in the collider**, because the track is 96% walled and the only
  way off is over the winze - which is a pit with no way out, so falling in
  should be a respawn. The cost is that `test_scenery.py` pins collider triangles
  and this file adds none, so a throw in it leaves the suite green:
  `tools/validate_track.py` is what actually checks it ran.
- **Two things about it fail silently and both already have.** Anything placed
  off the ribbon has to be checked against where the cave *closes*, not against
  how far away it looks - the daylight shaft at 52 units out was built five units
  below the road inside solid rock and simply never appeared. And an unlit colour
  is lifted linear→sRGB on the way out, hard, at the dark end: the roof at
  `0x201d22` measured `#605c62` on screen and read as an overcast sky. Both are
  in `docs/track-defects.md`.
- **It has no plan view**, since `plan.png` looks down and sees the roof. The
  corridor silhouette is what layout mistakes show in instead.
- Its cover needs a hand-picked `FRAMES` entry in `tools/_hero.py` for Costco's
  reason, doubled: from any establishing height every side of this track is roof.
  The camera has to be *inside* the corridor, which is what `span` 0.055 and
  `pad` 0.30 are for.
- **`hemi.ground` is load bearing here in a way it is nowhere else.** The key
  light points down and there are no shadow maps, so it is the only thing lighting
  a downward face - and this track has a loop, a trestle deck and a hundred bents
  whose undersides you look at from the ravine. At the first pass's 0x241c18 all
  of them were pure black and the loop read as a hole.

## Adding a track

**A track is one folder and nothing outside it needs editing.** Drop
`tracks/<slug>/track.py` in and it is in the game - home page, switcher,
leaderboard, rooms - with its medal times, pole side and checkpoint ceiling all
derived from the ribbon.

```
tracks/dockyard/
    track.py      required: slug, name, difficulty, build(b)
    palette.py    optional: PALETTE = {...}. Without one it gets a neutral default
                  that renders correctly on the first run.
    scenery.js    optional: mesh code only this track needs. Costco's is the
                  worked example. It reaches the game three ways and all three
                  matter: inlined by the play page for the track you arrive on,
                  fetched from `/scenery/<slug>.js` by the switcher (a switch
                  builds a new world without navigating), and bundled into
                  QuickJS for the anti-cheat. Miss any one and that path builds
                  the track without its collider, silently.
    hotlap.json   generated, not authored: the fast line the quick bots drive,
                  taken off a real lap on the board by `tools/hotlap.py`. Run it
                  once a record has been set here; without one the quick bots
                  drive the relaxed line and are slower. See `docs/bots.md`.
```

Optional declarations in `track.py`: `ground` (None floats in the void), `order`
(place in the pool), `width`, `rails`, `origin`, `closed`, `exposed`, `scenery`.
`tracks/__init__.py` documents each one and names the folder in every error.

**Use `/track`.** The skill runs the whole loop - write it, run the track tests,
measure it against the pool, render a plan view and five from the road, *look at
them* against `docs/track-defects.md`, fix what shows, check the medal times,
take the switcher preview, then serve it on `localhost:5005/solo/<slug>` for you
to drive. Authoring blind is what made a track cost four or five rounds; the
pictures are what removes them.

**The two things that make a round cheaper than looking.** `docs/track-defects.md`
is the running list of failure modes, so the render step looks *for* known
problems rather than at a picture; append to it whenever something new turns up,
one line, no need to work out the rule. And `tools/pool_stats.py <slug>` profiles
a track on 26 numbers against the other nineteen - the pool is a labelled set of
good tracks and this is the only thing that reads it back. It says *unlike the
pool*, never *wrong*: Big Red's 223-unit drop flags every run and is the point of
the track. What it catches is the mistake with no visual signature - a scatter
density ten times anything else, a `fogFar` a tenth of anything else - which is
the class you would otherwise find by rendering a bad picture.

**A folder that does not load is left out of the pool rather than being fatal**,
with a warning naming it. Raising would mean one bad contributor track stops the
server booting and stops pytest collecting *any* test - so the person fixing it
could not run anything, including the test that says what is wrong. All three
moments are guarded: importing `track.py`, reading its declarations, building the
ribbon.

**The pull-request gate is `test_every_track_folder_loads`**, which fails and
names every folder that did not make it into the game, with the loader's own
reason for each. Two tests stand behind it: `test_no_track_folder_is_silently_
ignored` catches the one failure with no symptom (a folder whose file is called
`tracks.py`, so it is skipped rather than reported), and
`tests/test_track_folders.py` writes deliberately broken folders and proves each
kind is contained rather than fatal - otherwise the gate could be green over a
pool that never loads anything.

**CI runs on pull requests now**, which it did not: `deploy.yml` triggered only on
push to `main`, so a PR ran nothing and the suite first fired *after* the merge.
The `deploy` job is guarded with `github.event_name != 'pull_request'` so a PR can
never ship - checked on the event and not the branch, because a PR's `github.ref`
is `refs/pull/<n>/merge` and would slip past a branch test.

**A closed lap closes itself** (`closed = True`); see Spa above. Two things the
solver cannot do for you: do not end the lap mid-corner, or the seam is a kink,
and get within about 10% of closing, because it will not stretch a straight more
than 15% or move a corner more than 8 degrees before refusing.

## Layout

- **Layout:** `tuning.py` (every physics constant, in one place), `tracks/` (one
  folder per track - `track.py`, optional `palette.py`, optional `scenery.js` -
  plus `builder.py` for the turtle, `checks.py` for what must be true of any
  ribbon, `solver.py` for closing a lap and `look.py` for the palette contract),
  `laptime.py` (racing-line
  relaxation + speed profile → medal times), `runcheck.py` (ghost packing, time
  validation), `verify.py` + `jsrt.py` + `three_stub.js` (the anti-cheat: a lap
  near the top of a board is re-driven through the game's own `Car.step` in
  QuickJS before it goes up), `racecheck.py` (the *room's* anti-cheat, which is
  a different question - see below), `models.py`, `app.py`, `maker.py` (the
  track maker and publishing, split out of `app.py`), `static/js/` (`trackmesh.js`, `physics.js`,
  `course.js`, `render.js`, `sound.js`, `game.js`, `pending.js`, vendored
  `three.module.js`), `tools/_hero.py` (the cover composition every picture of a
  track is), `tools/shoot_tracks.py` (each track's cover art, and its share card
  via `tools/shoot_og_cards.py`), `tools/shoot_covers.py` (the same shot at
  portal sizes, wordmarked),
  `tools/track_views.py` (a plan view and several from the road, for authoring),
  `tools/validate_track.py` (one track, every check, one report),
  `tools/snapshot_tracks.py` (proof that a refactor moved no geometry). The play
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
- **There are two builds of Drive and the server decides which one you get.**
  A portal (CrazyGames) frames the game rather than hosting it, and its rules
  forbid a game offering any login of its own - so `?portal=crazygames` on the
  entry URL sticks in the session, `app.portal_mode()` is the one thing that
  reads it, and in that build `/login`, `/register` and `/logout` **404** while
  the CrazyGames SDK signs people in against the shared `users` table. Every
  response also carries a `frame-ancestors` sitelock. Anything touching login,
  the nav, `/privacy` or who a player is has to work in both. Read
  `docs/portal.md`.
- **Nothing cosmetic may touch the simulation** - not ride height, not `CAR_RADIUS`,
  not the wheel radius, not a gram of mass. A cosmetic that changed how the car
  drives would make every time on the board mean something different.
- **There is no browser in CI, so check rendering by hand** before shipping a
  geometry, livery or HUD change. `?panel=`, `?touch=1`, `?shot=1`, `?view=`,
  `?draft=` and `?catchup=` exist so a screenshot can reach a state a click
  otherwise would. See `docs/testing.md`.
- **Every picture of a track is one composition, and it lives in
  `tools/_hero.py`.** A stretch of the lap from up high with a field of cars on
  it: `shoot_tracks.py` writes it to `static/img/tracks/<slug>.png` for the home
  page, the switcher and the share cards, and `shoot_covers.py` writes it at
  portal sizes with the wordmark over the foot. **The framing lives in one place
  on purpose** - it used to exist twice, and a cover and a card of the same track
  could disagree about where you stand to photograph it.
  - *Where* to stand is measured: `SCAN` walks the lap in windows and scores each
    on roll, climb and bend, so a track whose corners move keeps its framing.
    *Which way round* is not a thing a number knows, and every azimuth in
    `FRAMES` was picked by eye off a contact sheet - `python tools/_hero.py
    <slug>` prints one, `--sweep` looks along the lap instead. Five tracks needed
    the window pinned by hand, because "where is this track interesting" and
    "what is this track known for" are different questions: the scan will never
    find Sandy Cove's water, and the Costco's roof beats its own storefront.
  - **It needs Playwright**, and `shoot_tracks.py` now refuses rather than
    falling back to the Chrome CLI: composing the scene is a page evaluation, so
    a fallback would write the old empty-road framing under the right filename,
    which is the one failure nothing downstream can detect.
- **Re-run `tools/shoot_tracks.py` after changing a track's geometry or sky.** A
  test asserts the picture files exist; nothing can notice that one is stale.
  It also re-makes that track's **share card** (`static/img/og/<slug>.png`,
  1200x630), which is a layout over the cover and so goes stale with it -
  `tools/shoot_og_cards.py` is that step alone, for when the layout changed and
  the tracks did not. A card is what a pasted link to a track unfurls into, so a
  stale one is only ever seen in somebody else's feed.
- **`/robots.txt` and `/sitemap.xml` are routes, not files**, because the track
  pool is what says which pages exist and a file on disk would be a second list
  to keep in step. The sitemap is every track twice (the game and its board);
  the disallows are the pages that are gone tomorrow - a room code, a join link,
  a race replay - which are also `noindex` at the page via `NOINDEX_ENDPOINTS`,
  since the two catch different crawlers. **Every page carries
  `<link rel="canonical">` built from `request.path`**, which is what stops the
  share links (`/solo/<slug>?watch=<id>`) making one duplicate page per lap on
  the board.
- **`static/img/icon.svg` is the only drawing of the mark, and everything else
  in `static/img` that is a picture of it is output.** The seven rasters and the
  1200x630 share card are all rendered from it by `tools/shoot_icon.py`, so edit
  the SVG and re-run the tool - never touch a PNG. Same failure mode as the track
  previews: nothing detects a stale one. The split in that tool is deliberate -
  the SVG, the two small PNGs and the `.ico` are transparent so the mark can sit
  on the nav's paper untiled, while the app icons are painted over `--paper`
  because iOS mattes a transparent apple-touch-icon onto black and Android crops
  a maskable icon to a circle.
- Tests: `scripts/tests.sh drive` - 1,841 tests in about two and a half minutes, **run
  serially on purpose** (see `docs/testing.md`). A third of that is the anti-cheat driving
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

**nginx serves `static/` off disk now, and that lives only on the box.** Three
things there are load-bearing and nothing in this repo would recreate them, so
they are written down here: a `location /static/ { alias …/drive/static/; expires
$static_expires; }` block in the drive vhost, the `$static_expires` **map** and a
real `gzip_types` list in `/etc/nginx/nginx.conf`, and `/home/ubuntu` being `o+x`
so www-data can traverse to the files (without it every asset 403s). It is worth
the drift: the worker that serves `static/` is the same single eventlet worker
that relays every live race pose at 30Hz, and it was spending ~26ms of that box's
CPU and 1.9MB per cold page load on files nginx can hand out for nothing.
Measured after: **1.90MB → 0.47MB** on the wire.

**The cache lifetime is short on purpose, and `immutable` is wrong here.** Only
`style.css`, `game.js`, `garage.js` and `pending.js` are requested with a `?v=`
token; `three.module.js`, `trackmesh.js`, `physics.js`, `render.js`, `course.js`
and `sound.js` are reached by bare `import` from inside `game.js` and carry no
token, so nothing can bust them. The map gives a tokened URL 30 days and an
un-tokened one an hour. Version those imports before raising the second number.
The token itself is derived from the newest mtime under `static/`
(`_derive_asset_version`) rather than the old hand-bumped `ASSET_VERSION`, which
is commented out in the box `.env`.

**`certbot --nginx` rewrites the drive vhost in place, so check the `/static/`
block survived a cert renewal** - a lost block is not an error, just Python
quietly serving 1.9MB again. `curl -sI https://drive.cgovind.com/static/js/game.js`
and look for `Cache-Control: max-age=` and *no* `Set-Cookie`: Flask sets a cookie
on everything it serves and nginx sets none, so that header is the tell for which
one answered. Backups of every file touched are on the box as
`*.bak-<timestamp>`, and the stamp is in `/etc/nginx/.stage0-stamp`.

