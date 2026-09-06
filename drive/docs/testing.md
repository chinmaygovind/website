# Drive: the test suite

Read this before adding or removing a Drive test, or when a test surprises
you. Also read it before shipping a rendering change — there is no browser
in CI.

`scripts/tests.sh drive` - **2,001 tests, about 23s** on an idle 8-core
laptop, as 49 pytest processes (nearer 50s with a browser running - these are
eight CPU-bound processes and they compete with whatever else is on the machine). It was 150s on one core in Aug 2026; what the 6x is made of is
below, and none of it was deleting a test. A third of the remaining time is the
anti-cheat: `test_verify.py` and `test_held_laps.py` drive real laps through the
real physics and then re-drive them, which is what it costs to have the one test
worth having there - a lap somebody actually drove is accepted.

**Drive runs as separate processes, not under xdist, and the reason is a bug
that took months to find.** `scripts/parallel_pytest.py` starts one `pytest` per
test file, several at a time. That is a worse scheduler than xdist - it cannot
split work inside a file except where it is told to, so the wall clock cannot go
below the slowest single unit - and it is used anyway, because **xdist cannot
work in this module at all**.

**The stall, explained.** `drive/docs/testing.md` used to record three of 34 CI
jobs hanging at 739s, 901s and 246s: the run reaches 93-98%, every test passes,
and then the controller and all four workers sit at 0.0% CPU until somebody
kills the job. It was written up as not understood. It is `eventlet`.
`app.py` calls `eventlet.monkey_patch()` on its second line - it has to, since
one eventlet worker serves every live race - and that **greens `threading`**.
xdist's workers talk to their controller over pipes using OS threads execnet
creates at start-up, *before* any test imports `app`. From the first import
onward the worker has real threads holding green primitives, and a real thread
signalling one of those does not wake eventlet's hub, so the worker's main
thread goes to sleep waiting for something that cannot arrive. In `/proc` it is
unmistakable: every worker's main thread in `hrtimer_nanosleep`, its pipe reader
in `anon_pipe_read`, the controller in `futex_do_wait`. At `-n 16` it reproduced
in two runs out of three, which is what made it findable at all.

So it is not a tuning problem and `-n 4` is not safer than `-n 16` - it is
rarer, which is worse. **`kot` monkey-patches too and still runs under xdist**;
that is the same bug, still live, and moving it to `run_parallel` is the fix.

An explicit `-n` after `--` still hands the run to xdist, so
`scripts/tests.sh drive -- -n 4` is there if you want to watch it hang. `-x`
also opts out, since "stop at the first failure" cannot mean "stop each of fifty
runs".

**Where the 150s went, in order of size.** Each of these is a thing that was
being done repeatedly and did not need to be:

- **`import tracks` was 3.97s, and every process paid it.** Building the pool is
  a pure function of the track folders and of the code that interprets them, and
  most of the cost is not the ribbons (0.9s for all 22) but what is derived from
  them - `laptime`'s racing line relaxes 320 iterations over every station.
  Each finished track is now pickled under `tracks/__pycache__/pool`, keyed on a
  hash of its two source files plus `builder`/`solver`/`checks`/`look`/`laptime`/
  `tuning`. A stale entry is not possible rather than unlikely: the key *is* the
  content. **0.04s warm**, and the cached pool was checked identical to a freshly
  built one down to float `repr` and key order.
- **`test_track_folders.py` was 13.1s and is 0.30s**, entirely from that cache -
  it calls `_assemble()` once per broken-folder case, and 21 of the 22 tracks
  are unchanged every time.
- **`buildTrack` in QuickJS is a second for Spa** and files were calling it once
  per test for the same three circuits. `conftest.memoize_build_track` makes a
  runtime build each track object once; `test_closed_lap.py` went 15.3s -> 10.0s.
  It is **keyed on the track object, not the slug** - a slug is not unique to a
  document, since the editor reuses `draft` - and it is **capped at four**,
  because holding the whole pool is an out-of-memory out of QuickJS's 512MB,
  which `test_a_point_to_point_track_is_unaffected` found immediately. It is
  opt-in per runtime and the verifier's runtime does not use it.

**Two leaks were fixed on the way and neither was making tests fail.**
`close_app` unlinked the database and not SQLite's `-wal` and `-shm` sidecars,
and `/tmp` here is a **tmpfs** - so a full run left ~500 pairs of droppings *in
RAM*, and 8,000 of each had accumulated to **13GB of a 16GB `/tmp`**. And
`app.py`'s `eventlet.spawn(_stale_cleanup)` runs at import, which `boot_app`
does afresh for every test file, so a run left hundreds of immortal greenlets
each sleeping five minutes. Neither had a symptom you would chase; both are the
kind of thing that only shows up as the machine being slow.

**One test file gets the machine to itself, and `tests/EXCLUSIVE` is where that
is declared.** `test_track_folders.py` writes real folders into `tracks/` -
the only honest way to test that a broken folder cannot take the pool down -
and every other file does `import tracks` at module scope. A file that imports
while a scratch folder is on disk gets it **in the pool**, so `test_tracks.py`
then parametrizes its whole suite over a track called `zzscratch` and fails on
it. Filtering directory listings is not enough (`conftest.track_folders` does
that, for the four files that used to list `tracks/` themselves); this one
arrives through the assembled pool. The scratch folder also carries the worker
id now, so two processes cannot delete each other's.

**Nothing in this suite may sleep, and there is a test that enforces it.**
`tests/conftest.py` fails any test whose call phase exceeds `SLOW_TEST_BUDGET_S`
(10s; it was 5s until a loaded CI runner failed a test that was doing nothing
wrong) unless it is marked `@pytest.mark.slow`. That exists because of the bug that
prompted it: `_close_race` held an inline `eventlet.sleep(12)`, correct in
production (it runs in a greenlet) and twelve real seconds in the two tests that
called it synchronously - **24s of a 56s suite, and every test passed the whole
time**. There was no failure to chase, only a clock nobody reads. The sleep is now
`RESULTS_HOLD_S` and the tail of `_close_race` is `_clear_results`, scheduled with
`spawn_after`, which also stops the host's *End race* handler sitting on a greenlet
for twelve seconds after the flag. The guard **fails the offending test rather than
the session**, because under xdist `pytest_sessionfinish` runs per worker and its
exit status does not reliably reach the controller.
Note what it cannot do: it measures a test that *finished*, so it catches a sleep
and not a hang.

**Two of every three drive tests come from parametrisation, not from typing.** The
count is 894 functions - `test_tracks.py` is 30 functions x 19 tracks = 372
tests in 10s. So the count is a bad proxy for either cost or duplication: deleting
hand-written tests buys almost no time (`test_garage_js.py` is 141 tests in 3.6s),
and the per-track multiplication is where the value is. When the suite feels big,
**profile it** (`--durations=25`) rather than counting it.

**A test only comes out when a mutation proves another test still catches it.**
Break the behaviour, confirm at least one survivor goes red, then delete. Done this
way, four candidates picked by *name* turned into two real ones: the finish-material
values and the rim-lip radius each turned out to have a single guardian, and only
the badge-alone mesh count (8 other tests catch it) and metallic's paint direction
(the retired-finish test catches it) were genuinely redundant. Reading test names is
not evidence.

`test_tracks.py` and
`test_runcheck.py` are pure Python; `test_app.py` runs the real routes against a
throwaway SQLite file (the `/solo` memory, the board and ghost APIs, and a guest's run
being replayed after login). **`test_race.py` covers the room's race machine** -
the ways a race used to strand a room (no finisher, the last car leaving, a
stale timer closing the wrong race), the grid rules, the room's settings, the
rating rules, and the replay recorder. Most of it builds the live room state
directly, since it is plain dicts and what is under test is the bookkeeping
rather than the wire; the last group is different and drives the **real socket
handlers** from `free` all the way to the green light, with the emits captured
and the timers fired by hand, because the thing worth pinning about a phase
machine is the order it goes through them in.

**`test_sim.py` and the headless autopilot are gone, deliberately, and it is
worth knowing what went with them.** `jsrt.py` (then in `tests/`) bundled the
real modules into QuickJS against `three_stub.js` and then `tests/autopilot.js`
*drove every track to the finish*, and a group of tests asked questions about that lap:
did it finish, did it respawn, how much air, how long. It was removed because
those questions are a **ceiling on how mean a track is allowed to be** - a
track that cannot be driven cleanly by a simulated driver following a relaxed
racing line is not thereby a bad track - and that is a decision for the track.

What it caught, and what nothing catches now: road and grass being coplanar (the
car thought it was on grass for whole laps); wall collision geometry being
double-sided so contacts cancelled velocity twice per step; loops folding back
onto themselves tightly enough to trap a car forever, and later meeting the road
at a 55-degree kink; checkpoint planes tracked across the whole map so real
passes went unnoticed; a spawn point with no road under it; a loop built with
`self.x` for all three coordinates; and several tracks that simply could not be
finished. It was also the only thing pinning `laptime.CALIBRATION`, from which
every medal time is derived. **So a new track has to be driven by hand before it
ships** - there is no longer any automatic answer to "can this be finished at
all".

`jsrt.py` itself is very much alive, and it has **moved out of `tests/` into
`drive/`** (along with `three_stub.js`), because `verify.py` runs it in
production: the anti-cheat re-drives a submitted lap through the real
`static/js` files rather than a Python port of them, since a port is a thing
that can disagree with the game. Eight test files still build a runtime with it
(`test_bump`, `test_slipstream`, `test_catchup`, `test_boost`, `test_start_line`,
`test_garage_js`, `test_rules_js`, `test_sound`) and nothing about how they use
it changed. `quickjs` has moved the same way, into `requirements.txt`, so the
box installs it now. Without it those tests skip, which reads as a pass.

**A driver came back, and it is not the old autopilot.** `tests/driver.js` is
that pursuit controller - the same one, off `laptime.py`'s racing line - plus the
frame loop out of `game.js` - `Stepper`,
`Run.noteStep`, `Run.update`, in that order - so what it produces is a lap
recorded exactly as a browser would record one. Two differences from the thing
that was deleted are load-bearing: it **drives on the keyboard** (the car is
stepped with the decoded input *byte*, never with the steering angle that
produced it, because a lap driven on an angle it did not record would be
evidence of a lap nobody drove), and it is a **frame** loop rather than a step
loop, so the tests can ask what 12fps or a stuttering frame does to the
recording. It is only there to make laps for `test_verify.py` and
`test_held_laps.py`, and it makes no claim about how mean a track is allowed to
be - which is why it did not bring `test_sim.py` back with it.

`test_verify.py` is where the anti-cheat's numbers come from: it drives real laps
and re-drives them, both for the case that matters (an honest lap is accepted,
with the honest floor pinned well under the threshold) and for the cases it is
for (2% more engine, more grip, a stolen replay, evidence that stops early).
`test_held_laps.py` is the other half - what `/api/run` does with the verdict -
and it turns the re-simulation **on**, which is why `test_app.py`'s fixture turns
it off and says so: `test_app.py`'s replays drive the track but were never driven
by a car, so with the anti-cheat live none of them would reach the board.

**Two other files run browser JavaScript the same way, against a stub DOM instead of a
stub three.js.** `test_touch.py` lifts the touch bindings straight out of `game.js` and
drives them with synthetic touches (the handbrake gesture, and that left-right-left is a
correction rather than a double-tap); `test_pending.py` runs `pending.js` against a fake
`localStorage` and a `fetch` whose answers the test chooses. Both extract by marker
rather than line number, and `test_touch.py`'s stub deliberately lists every function
`bindInput` reaches for - if a new one appears the slice throws instead of quietly
testing nothing. `test_slipstream.py` does both halves: `Car.draft` runs for real
in QuickJS (it only reads the body's own frame and the rivals it is handed, so it
needs no world and no lap), and `contactOn` is lifted out of `game.js` by name and
run against a stubbed phase. **`test_catchup.py` is the same file for the
catch-up boost**, in the same two halves: `Car.catchup` run for real for the
deadzone, the ramp and the smoothed follow, and `catchupOn`/`gapToLeader` lifted
by name for the phase gate and for the gap - that a finisher is not somebody you
are still catching, that leading is worth nothing, and that the two are one call
so a caller cannot get a gap it should not have. Three of its tests are only
about the *numbers*, since how big this is is the whole design: full help has to
read **exactly 180 on the speedo** (pinned on the dial rather than as a band
round the multiplier, so making the game faster has to be said twice), a tow has
to stay the larger of the two prizes or lifting off and waiting becomes a tactic,
and the pair of them stacked must still land under the hard velocity clamp, or
the clamp is what sets the top speed. **`test_bump.py` is that file again for
car-to-car contact**, and it needs a world where those two do not - contact
happens between cars on a road, and the grip term the whole thing turns on only
exists while a car is grounded. It pins the two thresholds (nothing below
`BUMP_FEEL`, heard-and-free between the two, charged past `BUMP_COST`), that ten
events of sustained rubbing still cost under 2% of your speed, that the body is
not leaned over by held contact, that a hit is never a spin or a rollover at any
closing speed, that the let-go tyres come back on their own clock - and the one
that is the actual finding, that the displacement comes from `BUMP_SLIP_GRIP` and
from nothing else, asserted against *the same hit with that one number pinned
back to `GRIP`* rather than against a figure in a comment that would rot.

**The garage has two test files because it has two halves that fail
differently.** `test_garage.py` is Python: it checks the palette's claim about
itself in both directions (every pair far enough apart in CIELAB, every entry
far enough from every backdrop, every L* inside the band), that `validate` never
raises on anything, each gate against a stats row that does and does not
qualify, `resolve` replacing an ungranted item however it arrived, the record
badge persisting and surviving losing the record, and the two deliberate
duplications of `RECORD_GREEN` read out of `render.js` and `style.css` rather
than trusted. **`test_garage_js.py` builds `CarView` for real in QuickJS**, the
way `test_verify.py` runs the physics, because almost everything that can go wrong
with assembling a car out of a livery is invisible to both of the checks this
project otherwise leans on: the autopilot never draws, and a screenshot of one
car either photographs "the fifth rim style is 24 meshes instead of one"
correctly or photographs it as something you would have to already suspect. So
it pins the *construction* - the mesh and material budget (14 and 7 plain, 19
and 10 fully loaded, 18 and 8 once a stock wheel is painted, and the roof alone
worth the one material any of this costs), that no material escapes `_mats` and therefore
`setGhostly`, that a rim style is one geometry shared by four wheels, that every
decal - stripe *and* badge, since they share a buffer - lies on one of the three
panels, clears it, and faces out of the car (the cross product taken from the raw
positions, since the stub's `computeVertexNormals` does nothing), and that nothing
a livery does moves any part of the car that was already there. Two of those had to
be rewritten when the flanks arrived: "faces up" is a rule a vertical quad cannot
satisfy, and a panel has to be worked out **per triangle** rather than per vertex,
because the widest deck stripes reach x ±0.94 against a flank plane at ±0.96.
The front has its own group: that the headlights are one mesh and never the
driver's colour, that the car never outgrows the collision radius, that every
livery's stripes stay on the panel they are drawn on, and that the car did not get
longer. The badge is checked for being on the *clear* stretch of bonnet ahead of
the windscreen and for being a readable size - it used to be a bar on the bumper
line, checked for not being enclosed by the bodywork, which it silently was for as
long as it took to look at a screenshot. **Its orientation is pinned twice, and only
one of the two can speak for every badge.** The direct one reads the `BADGE_Z + v`
mapping out of the source *and* checks a shield's single point is its most nose-ward
vertex. The other counts where the ink is - which half of the icon holds more of its
vertices - and that only works on the **two** badges that are lopsided by vertex
count: the crown, whose band must be furthest from the windscreen, and the shield,
whose flat top must be nearest it. The chevrons and the ribbon point clearly one way
to the eye and have as many corners at each end, and the laurel, sunburst, checkers
and podium are symmetric outright, so listing them here would be six cases that
cannot fail. The mapping and `tri2`'s world-space winding are only safe *together*
and each is caught by a different test - the numbers are in **The badge case** above,
measured rather than assumed.

Two more tests say why `FINISH` outlives `FINISHES`: metallic and pearl still render
(for the replays that carry them), and an entirely unknown finish is a matte car.
**Both of them exist mainly to say the same thing**: an account with no garage
row wears the car everybody else's account does. Note this file is also what
pushed `three_stub.js` twice - materials from one shared `noop` to three real
classes that keep their options, since with all of them the same class
`instanceof MeshPhongMaterial` was true of everything on the car and no test
could tell gloss from matte; and `BoxGeometry` to carrying `parameters` the way
real three.js does, since without it the constructor arguments are thrown away
and a test about the *shape* of the car can only count meshes. That is how "the
splitter is as wide as the body" first got written as "there are two things near
the front", which is not the same claim and would not have caught anything.

`test_rules_js.py` is the same lift-by-name trick on
rules that were each a bug or a contract between two files: that `R` and `T` do
nothing (and say nothing) until the clock is running, that `placeOnGrid` puts
pole on the track's own `pole_side` and the row behind it on the other, that
`lampsOf` reads a recorded flag byte with drift winning over brake, that the
tow goes out of `sendPose` as one number the flag disambiguates and comes back
out of `rivalSound` as the two it is drawn and heard from, and that the two words
the camera keys are held under travel from `KEYMAP` through `viewKeys` to the
`opts` that `Renderer.follow` reads in the other file - a rename at either end is
a key that quietly does nothing, which no screenshot and no lap can catch.

**`test_sound.py` is the one file a screenshot cannot stand in for.**
`sound.js` builds a graph of nodes and then only moves numbers about inside it,
so a wrong `connect`, or a voice rebuilt every frame, is completely silent to
look at and completely wrong to listen to. It runs the real module in QuickJS
against a fake `AudioContext` that records what was connected to what, and pins
the wiring and the bookkeeping: one voice per car and kept, a car dropped from
the list torn down rather than forgotten, everything a rival makes going through
its own panner and the panner through the bus under the effects bus (so muting
still mutes the field), and the listener's forward and up coming off the
camera's own quaternion - including rolled upside down, which is a loop. It
also pins the two switches being two - muting leaves the music's gain alone and
vice versa - and the music scheduler: nothing booked twice, nothing booked at
all when it is off, and a tab that was in the background for ten minutes
picking up rather than firing ten minutes of notes at once.

There is no browser in CI, so **check rendering by hand** before shipping a
geometry change.

For a **track**, that is now three commands and not a manual job:

```bash
cd drive && venv/bin/python tools/track_views.py <slug>     # plan + 5 road views
cd drive && venv/bin/python tools/validate_track.py <slug>  # geometry, medals, console
cd drive && venv/bin/python tools/shoot_tracks.py <slug>    # its cover art + share card
```

`track_views.py` writes to `tools/views/<slug>/` (gitignored) and is the one that
changes how authoring feels: `plan.png` finds layout mistakes - a leg outside its
building, a hairpin bulging into the next aisle - and the road views find the ones
only a driver would. They use the **real chase camera** with the car parked on the
centreline, which is the point: on Costco the question is whether the lens clears a
15-unit ceiling and follows the car through a doorway 11.6 units later, and a
camera written for the tool would answer that about itself.

`track_views.py` goes through Playwright's chromium if `drive/venv` has it and
falls back to a Chrome on PATH or in `/Applications`. **That fallback is the fix
for authoring blind**: these tools used to look only on PATH, find nothing on a
Mac, print one line and do nothing - so tracks were designed, shipped, and only
then looked at. **`shoot_tracks.py` no longer has it and refuses instead**, because
its picture is composed by a page evaluation the CLI backend cannot run: falling
back would write a plain snapshot of an empty road under the right filename, and
nothing downstream can tell one picture of a track from another. Note also that
switching browser re-renders every cover with tiny antialiasing differences
(measured: 1.68% of pixels, max channel delta 1 of 255), so pictures coming back
"modified" after a backend change means nothing - check them out again.

A *room* needs one more step than a solo track does,
because `/room/<code>` redirects anyone who is not already a player in it. The
cheapest way in is a scratch harness that imports the real app and adds a
login-and-join route, so headless Chrome can reach a room in one navigation;
`/j/<CODE>` then does the joining for real. Set `session.permanent` in that
route or the cookie dies with the headless run and the second navigation lands
on the login page. A persistent `--user-data-dir` keeps the session across
shots, which is what makes `?panel=` reachable afterwards.

**Anything about a second car needs a second car**, and the cheapest one is a
`python-socketio` client: log in as a guest with `requests`, `POST /create`,
`GET /j/<CODE>`, then connect with the same cookie, `join_room_`, and emit
`pose` 30 times a second with whatever position and flags the shot needs. That
is how the rival slipstream was checked. It is also the only way to see a phase
rule, since **`?panel=qual` pins the HUD label and not `S.racePhase`** - the bot
is the host, so it can emit `start_race` and open a real qualifying session.
Templates are cached, so restart the dev server after editing one.

**Anything driven by a key, a click or a tab closing needs a browser that can send
one**, which a screenshot cannot - so `tools/_scratch_activity_check.py` drives the
abandon paths with Playwright (installed into `drive/venv` by hand; deliberately
**not** in `requirements-test.txt`, since it is a by-hand check and not a test, and
the box has no use for a browser driver). It is kept because five separate things
about it are not guessable and each cost a run:

- **There is nothing on `window` to read.** `game.js` is an ES module, so `S` is
  module-scoped - `page.evaluate("S.run")` throws and `wait_for_function("window.S")`
  simply times out. Watch the **network and the database** instead, which is the
  better question anyway: what left the browser and what row moved.
- **Log the requests server-side, not in Playwright.** `page.on("request")` delivers
  asynchronously under the sync API, and a request whose effect was already in the
  database turned up in the *next* step's list - which reads exactly like the wrong
  path having fired. A `before_request` hook appending JSONL is exact.
- **`eventlet.monkey_patch()` hangs the app's import here**, so the scratch server
  is a plain `app.run(threaded=True)`. Solo mode needs no live socket, so that
  costs nothing.
- **`#tGrid`'s track cards are attached but not visible** - the switcher overlay is
  `display:none` until opened - so `wait_for_selector` needs `state="attached"`.
- **Click the page before sending keys.** Keystrokes go to `window`, but a fresh
  headless tab is not reliably the thing receiving them, and this failed
  intermittently until a `mouse.click` went in first. For the same reason the
  harness holds the throttle in a **loop until `/api/start` actually lands** rather
  than sleeping a guessed number of seconds: under swiftshader how long the track
  takes to build is not a constant.

One thing it cannot check, and says so rather than implying otherwise: that a
*finished* solo lap is not banked twice. Finishing a lap needs the car driven a
whole lap, which swiftshader is far too slow for. That half is pinned by
`test_activity_does_not_count_a_finished_lap_twice` on the server and by the
`run.counted` rules in `test_rules_js.py`, both mutation-checked.

Run the app on a spare port and screenshot it with headless Chrome
(`google-chrome --headless=new --use-gl=swiftshader --enable-unsafe-swiftshader
--virtual-time-budget=9000 --screenshot=out.png http://127.0.0.1:5055/solo/twist`). That
is how the forest of bridge piers and the dark undersides were found - both invisible to
every test. `?panel=`, `?touch=1` and `?shot=1` make the panels, the phone layout and a
clean preview shot reachable the same way. Note `app.py` runs with the reloader on, so a
backgrounded dev server needs `debug=False` or it forks and the port looks dead.
