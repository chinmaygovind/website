# Drive: runs, scoring, medals and ghosts

Read this before changing `/api/run`, `/api/start`, `/api/activity`,
`runcheck.py`, `verify.py`, `laptime.py`, `pending.js`, medals, or ghost
recording.

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
  one place in `game.js` that calls `run.start()`, which is why loading the
  page does not count as one. A lap in a **room** is not counted at either end
  - see the leaderboard rule below. They live in their own `drive_starts` table, one row per (user, track) -
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
- **Minutes played and kilometres driven count every run, not the ones that
  finished.** Both numbers were written in exactly one place - inside `/api/run`,
  which the client posts *when a lap finishes* - so on the live database **8,134
  of 9,758 attempts (83%) were worth nought minutes and nought kilometres**, and
  all multiplayer driving was worth nothing at all, since `countsForTheBoard()`
  turns both `/api/run` and `/api/start` back before the request is made.
  `eobard` had 554 starts against 12 finishes, so their "4.0 min" was almost
  entirely missing. Room driving *does* count here, which is not a contradiction:
  these are play stats and not records, and the leaderboard rule is untouched -
  no room lap time reaches the board.
  - **`/api/activity` is the sibling route for driving that will never produce a
    board entry**: an abandoned run, or a room lap. It adds to `drive_time` and
    `distance` and touches nothing else - never `runs`, never a medal, never ELO -
    and it is honest to a guest (`stored: false`) rather than a 401, the rule
    `/api/start` already follows. It reuses `clamp_distance` and needed a new
    `clamp_run_ms` beside it: `/api/run` never had to clamp time because
    `validate` checks it against the replay's own frame count, and an
    *unfinished* run has no replay to check against - so without it the one
    number the whole "minutes played" figure is made of would be the only field
    with no ceiling.
  - **`reportActivity()` is the one funnel, and `run.counted` is the whole
    correctness of it.** A finished lap must not be counted twice, because
    `/api/run` already sends its time and distance and the two routes are
    additive on the server. So the solo finish path *claims* the run
    (`run.counted = true`) and the room path *reports* it, `Run.start` clears the
    flag, and every abandon path reads the run before the thing that destroys it -
    `resetToStart` zeroes it and `loadTrack` replaces it wholesale, so reporting
    after either banks nothing.
  - **`pagehide` only, and neither `visibilitychange` nor `blur`.** This looks
    over-cautious and is the opposite: both of those fire on an ordinary alt-tab
    or click-away *mid-lap*, which people come back from and then finish - and
    `/api/run` would bank the whole lap on top of the partial report. Only
    `pagehide` means the document is actually going. A back/forward-cache restore
    fires `pageshow` with the same already-banked `Run`, so that ends the run
    rather than continuing it. `T` is deliberately not a call site either: the
    clock keeps running, so it is the same run.
  - **What this deliberately misses**, since reporting on abandon was chosen over
    a heartbeat: a hard kill - crash, force-quit, lost power - loses that one run.
    Every ordinary ending is caught.
  - **`tools/backfill_race_activity.py` is the driving from before the route
    existed, and races are the only recoverable part.** `drive_races.cars_json`
    packs each car's replay exactly like a ghost, so this is *measurement*:
    `len(frames) / hz` is the seconds and the summed gaps between consecutive
    frames are the metres. The abandoned solo runs are the larger undercount and
    are gone - a run nobody finished left no replay and no row. Three things
    worth knowing. **A gap wider than `MAX_STEP` (12 units, the same threshold
    the client uses for a rival) is a respawn and is not distance driven** -
    including them credited 25.7 km across the field that nobody drove, which is
    the difference between the tool and the first estimate of it. Identity is
    matched on `name` against `users.username`, which is sound only because Drive
    has no display-name column of its own; a name with no account is a guest and
    is skipped, not guessed at. And it **adds** rather than recomputes, because
    `drive_times` keeps only the best lap per track, so the existing total is the
    only record the other finished laps ever happened. Idempotent by
    construction: a marker row in a `drive_backfill` table, made by the tool with
    plain SQL rather than mapped, since nothing in the app reads it.
    **Applied to the live database 2026-08-07**: 58 races, 113 cars, **+89.9
    minutes and +217.0 km across 6 accounts**, two guests skipped - identical to the
    dry run against a downloaded copy, and the marker now refuses a second pass. So
    it is done and there is nothing to re-run; it is described here because the
    *method* is the reusable part, and because the figures are the only record of
    what the totals were before.
- **The leaderboard is for laps driven alone against the clock, so nothing set
  in a room reaches it.** No time, no medal, no ghost, no distance, and no
  attempt either: `countsForTheBoard()` in `game.js` is the single answer, and
  both `/api/run` and `/api/start` read it, so the two halves of a lap counting
  cannot disagree and leave a track with more finishes than goes. It applies to
  a room's free practice as much as to a race, because there are other cars on
  the road in every phase of one - **a tow down a straight is worth the better
  part of a second**, contact moves you, and a race starts from a rolling grid
  rather than a standing lap. A time set that way is a record of the traffic
  rather than of the driving, and it was going on the board next to laps that
  were not. It cost a real record: a Jump City lap set in a race sat top of the
  board until the holder asked for it to be taken off. The room's own ghost is
  unaffected - your best lap *here, today* is what a room is for.
- **Being fast is not evidence of cheating.** There used to be a floor here:
  `tuning.MIN_PLAUSIBLE`, rejecting any time under 0.8 of `ideal`. But `ideal` is an
  estimate off a relaxed racing line and anyone who learns a track beats it, so the
  floor was measuring how conservative the estimate was, not dishonesty - and it
  punished exactly the people driving best. It is gone. What a run still has to
  survive is entirely about the *replay*: right duration, no teleports, starts on the
  line, through every checkpoint in order (`runcheck.validate`).
- **The clock is pinned to the frame count, and the two windows either side of it
  were worth 3.5 to 6.9 seconds a lap.** `validate` used to allow the duration a
  **±25% band** against the replay's length and a checkpoint **600ms** of slack
  against the crossing it claims. Neither number was ever calibrated: shift every
  split down by the tolerance, claim a finish a millisecond after the last one,
  and an entirely honest replay came back several seconds faster on every track
  in the pool - the two long ones by most of the gap between first and last on the
  board. Stacked on a replay downloaded from `/api/ghost`, which is public and
  answers with the record's own frames and splits, that was a **world record for
  two HTTP requests** by somebody who had never loaded the game.
  - The band was never needed, because the frame count is not approximately the
    duration, it **is** the duration. `Run._recordGhost` writes a frame while
    `_ghostN / GHOST_HZ <= t` and `Run.update` stamps `this.time` on the same
    frame that spots the finish, so `len(frames) == floor(time_ms/1000*15) + 1`
    exactly, whatever the browser's frame rate. `runcheck.time_window` inverts
    that; `FRAME_SLACK` widens it by a frame either way for a lap `pending.js`
    has been holding since before the start-line fix, and becomes redundant once
    a run token is required.
  - `SPLIT_TOL_MS` is **250**. An honest disagreement is one render frame (the
    split is stamped when the crossing is spotted) plus the 15Hz grid the
    crossing is found on - about 120ms of theoretical worst case, and when it
    was measured across the pool it was never worse than **59ms**, always on
    the same side. (That measurement came from the headless autopilot, which is
    gone - so re-checking it now means driving the tracks by hand.)
  - Both numbers are pinned by mutation-checked tests, which is worth saying
    because the *old* split test could not see this: it moved a checkpoint by
    three seconds, which is refused at 600ms as easily as at 250, so the
    constant went nine frames wide with a green suite over it.
  - What is left is **one frame of quantisation** - a worst case of 0.130s across
    the pool, against 6.9s. It cannot go lower without the run token, and a
    stolen replay is only fully answered by the re-simulation, since
    `/api/ghost` serves poses and has never served the input stream behind them.
## The lap is re-driven on the server

*(This section replaces `drive/VERIFICATION-PLAN.md`, which was the working plan
for it. Three things in that plan turned out differently once it was measured -
the tolerance, which is a median and not a per-window distance; the anchors,
which carry a pose and a clock rather than only a velocity; and the verifier,
which is a subprocess rather than a service - so keeping the plan next to the
built thing would only have been a way to be told the wrong answer.)*

- **`runcheck.validate` cannot ask the only question that matters, and
  `verify.py` is the answer to it.** Everything in `runcheck` is about whether a
  replay is *self-consistent*: right duration, no teleports, through every gate
  when the splits say, inside a corridor of the road. A browser with a raised
  `ACCEL` satisfies all of it - the replay is a real recording of a real drive,
  it is just not this car - and that is exactly what took a **12.288s Twin Loop
  record on 2026-08-07**. So a lap that would place in the **top 3** on its track
  is now re-driven through the game's own `Car.step` before it goes on the board.
  - **Anchored, not free-running.** Starting a car on the line, feeding it the
    recorded inputs and comparing the finishing time does not work, and it fails
    in the worst direction - it refuses honest laps. `Math.exp` (six times a
    step), `atan2` and `acos` are implementation-defined in ECMAScript, and the
    browser runs real three.js while the server runs `three_stub.js`; over a few
    thousand steps of feedback the two part company somewhere in the second
    corner. Instead the verifier **walks the recording**: at each anchor it seeds
    a car from the recorded state, steps `Car.step` exactly eight times with the
    recorded inputs, and requires the prediction to land on the next anchor.
    Divergence can never compound past 1/15s.
  - **`FIXED_DT` is 1/120 and an anchor is every eighth step**, so a window is
    exactly one ghost frame and there is no interpolation anywhere in it. That
    integer alignment is what `Run.noteStep` is arranged around and what
    `test_a_frame_is_exactly_eight_steps` pins.
- **What a run carries now**: one input byte per physics step (run-length
  encoded; a driver holds the throttle for seconds) and, every eighth step, the
  car's whole carried state - pose, velocity, smoothed steer, and the lap clock.
  It is deliberately **not** in the ghost blob: a ghost is downloaded by everyone
  racing that lap and none of them needs the driver's inputs, and keeping it out
  means no replay already on the board changes shape.
  - **The pose is in the anchor as well as in the ghost, and that is not
    duplication.** A ghost frame is interpolated to a moment of the lap clock by
    `_recordGhost`; an anchor is the exact state at a step boundary. Seeding from
    an interpolated pose - a state the physics was never in - puts a whole render
    frame of error into the only measurement this makes.
  - **The anchor carries its own clock**, because steps and the lap clock do not
    tick together. A frame longer than `MAX_STEPS` steps drops the rest, so one
    stutter puts the step count permanently behind the clock; matching anchor *i*
    to ghost frame *i* by index would then refuse an honest lap. 12fps drops
    steps on every frame and is the case that proves it.
  - **`padBoost` is the one thing the verifier will not be told.** It is carried
    across windows and it is worth engine, so the verifier keeps its own: a
    number a client can set is a number a client can set to `PAD_BOOST` for the
    whole lap. Everything else either re-derives itself inside a step
    (`grounded`, `coyote`, `surface`) or is race-only and therefore always zero
    in a solo lap (`bumpSlip`, `slipCharge`, `catchupBoost`).
- **The verdict is a median, and that is the whole calibration.** Because a
  window is seeded with the recorded *velocity* as well as the pose, a retuned
  car never accumulates: the extra speed is handed back at every anchor, and what
  is left is one window of the difference in *acceleration* - about 0.06 units
  for a 40% richer engine, not the 2.2 the original plan assumed. So the useful
  measurement is not the worst window but the middle one. Measured by driving all
  fourteen tracks through the real physics and re-driving them
  (`tests/test_verify.py`): an honest lap sits at **0.00055-0.00063 units** on
  every track, at every frame rate from 12 to 144, with hitches, with respawns,
  driven gently or hard - because the floor is the quantisation of an anchor and
  nothing else. `ACCEL x1.02` sits at 0.0026, `GRIP x1.5` at 0.0054, `ACCEL x1.4`
  at 0.042. The threshold is 0.002. Two other rules cover what a median cannot
  see: a per-lap budget for divergence that is isolated rather than typical, and
  a check that the anchors are the same lap as the replay they arrived with -
  without which an honest lap of your own plus a replay downloaded from
  `/api/ghost` (which is public) would pass both halves separately.
- **What it does not decide is that a *person* drove it.** Feed the real physics
  perfect inputs from a script and this passes, because the car really did do
  that. What it ends is the class of "my car accelerates faster than yours",
  which is every cheat anybody has actually tried here.
- **A held lap is not written into `drive_times` at all.** That table keeps one
  row per player per track and a better run overwrites it wholesale, ghost and
  all - so storing a lap now and disowning it later takes the time it replaced
  with it. It waits in `drive_run_checks` instead, which means the board, the
  record, the ghost and everybody's rank are untouched by an unchecked lap with
  no read path anywhere having to remember to exclude one. **Absence of a row
  means verified**, which grandfathers the 82 laps that predate all of this.
  - It runs in a **subprocess**, because one lap is one to four seconds of solid
    CPU and Drive is a single eventlet worker - doing it on the request path
    would freeze every socket in every live race for that long. Deliberately not
    the long-lived service the original plan called for: a daemon is a second
    thing to install on the box, a second thing to restart on deploy, and a
    second thing that can be quietly dead while the board waits for it. Measured
    on the pool: **0.5s and ~75MB for a short track, 6s and ~110MB for
    Rainbow Road**, `nice`d to 10, and the QuickJS heap capped at 256MB so a
    runaway is an `error` on a row rather than the kernel choosing which of the
    five services on the box to kill.
  - The child **judges and does not apply**. Writing a pass back into
    `drive_times` means medals and counters, which live in `app.py`; so it writes
    the verdict to its own row and `app.py` settles it the next time anything
    reads a board (`_settle_checks`, called from `_records` and `_track_payload`).
    Nothing in Drive runs on a timer and this does not add one. A check still
    pending long after it was queued - the process died, the box rebooted - is
    handed to a fresh one by the same path.
  - **Nothing is held when nothing can check it.** If `quickjs` is missing, or
    `DRIVE_VERIFY=0` in the box `.env`, `/api/run` stores laps exactly as it did
    before: a lap that would wait for ever is worse than one that was never
    checked.
  - **A quick lap that arrives with no evidence is refused, with a message
    asking for a reload.** It has to be, or leaving the field out is the cheat.
    The honest cause is a page open across the deploy that added the recording,
    and the cost is bounded: a lap `pending.js` has been holding since before
    this shipped is dropped if - and only if - it would have placed in the top 3.
- **What is still open, said plainly.** A hand-built replay could hide a few
  hundredths of a second inside the isolated-divergence budget, which is less
  than the quantisation `time_window` already allows and costs an input stream
  that survives everything else. Tightening it further would start refusing real
  laps for grazing a barrier, which is the worse failure. And a lap with a
  **respawn** in it is refused before any of this by `validate` - the jump back
  to the checkpoint is a teleport by the speed ceiling - so the verifier's
  respawn handling is defence for the day that changes rather than something
  live today.

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
  and `MEDAL_MULT` is calibrated against times people have actually set rather
  than against any simulation. **Medals already earned do not move**: `DriveTime.medal`
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
## Ghosts

- **The ghost is a practice tool, so in a room it belongs to the phases you drive
  alone in** - free practice and qualifying - and to neither of the others. It is
  not rendered at all from the countdown to the flag, whatever the setting says:
  a translucent car on a line nobody drove is one more thing to mistake for a
  rival. Qualifying is the opposite case and used to be lumped in with the race,
  which was wrong for the same reason - it is the session where you are alone
  against a clock, which is exactly what a ghost is for.
- **A room's four ghosts are not solo's four.** Off, **your best lap of this
  practice session** (not your all-time PB, which was set on a different day
  against nobody), **provisional pole**, and the world record. "View others" is
  not offered in a room: everybody there is on the road with you, and the board
  is a list of people who are not. `K` steps through all four (`G` is the car).
- **Provisional pole is a live ghost of the lap that is currently taking pole.**
  A qualifying lap goes up with its replay attached (`qual_time` carries the
  frames), the server keeps **only the leader's** and throws the rest away, and
  a change of pole is broadcast as one line - who, and what they did. The lap
  itself is tens of kilobytes and most of the room is not chasing it, so it is
  fetched by the people who are (`qual_pole_req`). Chasing yourself is not
  chasing anybody, so if pole is yours no ghost is loaded - your own best lap of
  the session is already what `me` means there, and it is the same lap. It is
  dropped when the session ends: after the flag it is the grid, not a target.
- **Every ghost is the whole car of whoever drove it**, not only its colour, and
  so is every car that person turns up in. That distinction was worth a bug each
  way round. `/api/ghost` has always answered with the driver's livery, and the
  ghost you *chase* has always used it - but `startWatching` kept only
  `meta.color`, so the same lap **watched** came up in their paint on stock
  wheels with no stripe and a matte finish, which is nobody's car; and
  `qual_pole_req` sent no livery at all, so the one ghost a whole qualifying
  session is looking at had the same problem. Both send the livery now, and both
  answer `color` **off** that livery rather than beside it, which is the
  `to_dict` rule: it is one fact, and the copy on the live car dict is only as
  fresh as that driver's last connect. A ghost's livery is resolved *when it is
  asked for* (`_seat_livery`) and a **replay's** is stored *with the race* - the
  two rules disagree on purpose, and `_store_replay` says why.
- **Whose colour, when nobody chose one.** There was no per-person colour at all
  before - a room handed them out by seat and solo was always red - so `color_for(username)`
  hashes one out of `garage.HASH_COLORS`, the same trick the accounts pages use
  for the initial on a profile with no picture. That is still the answer for
  anybody who has not chosen; what a car looks like once they have is **The
  garage** below.
- **A ghost lights its own brake lights**, because the flag byte is recorded
  with the pose. A ghost frame is eight values now, not seven, and `pack_ghost`
  writes the stride into the blob: every lap already on the board is seven
  wide, still unpacks, and simply has no lamps until it is driven again.
- **A ghost frame is the pose at its own timestamp.** `Run._recordGhost` interpolates
  to exact multiples of `1/GHOST_HZ`. It used to accumulate dt and push a sample every
  time an interval had gone by, which meant the accumulator had to fill before frame 0
  was written - so frame 0 was the pose one interval *after* the start. Playback reads
  frame `t * GHOST_HZ` at run time `t`, so every ghost ever recorded played back 1/15s
  ahead of the lap it recorded: a couple of car lengths up the road, from the line to
  the flag, which is why the ghost appeared to start in front of you.
  `test_the_ghost_is_recorded_where_the_car_actually_was` drives a lap, notes where the
  car really was at each sample time and requires the two to agree.
- **The lap clock and the car share a zero, and for a long time they did not - a
  standing start was worth up to ~33ms of unrecorded run-up.** Found from the
  leaderboard, not from a failure: two drivers flat out from the line to the first
  checkpoint were finishing that split consistently ~26ms apart on Chicane Park and
  Sandy Cove. The frame loop ran `S.run.start(now)`, then the physics, then
  `S.run.update(S.car, now)` - which reads `now - startedAt`, i.e. **0**. So the car
  had already been accelerated when the clock recorded that it had not moved, and
  nobody was charged for the distance. `Stepper.acc` made it worse by carrying up to
  one `FIXED_DT` *across* the start, so the number of free substeps was a coin flip.
  - **It rewarded a low frame rate**, which is the part worth remembering: the
    longer your frame when you pressed the throttle, the more free acceleration.
    Measured on a software-GL browser, the car was doing 13 on the dial at
    `clock = 0:00.000`.
  - **It is not `FIXED_DT` per frame for everybody.** `FIXED_DT` is 1/120, so a
    perfect 1/60 frame is exactly two substeps and leaves nothing behind - at
    exactly 60Hz the carried remainder can never buy anything. It bites at every
    refresh rate that is not 60 or 120, and at 60 once vsync jitter is in it. The
    first version of the test asserting this was written at 60fps and failed.
  - The fix is `S.stepper.reset()` plus skipping that one frame's physics
    (`clockStarting`), so `run.update` samples a car that is genuinely stationary.
    It costs everybody one frame of throttle (<=17ms). The **race** path resets but
    does *not* skip: `raceT0` is a server timestamp already in the past, so the
    clock is legitimately non-zero and the car is owed that motion.
  - **The old times were kept**, deliberately. Every lap on the board predates the
    fix, so each carries up to ~33ms of run-up that a lap set today does not get -
    they are not comparable with new ones, and the records are correspondingly
    harder to beat. `tests/test_start_line.py` pins the mechanism (the real
    `Stepper` in QuickJS) and the two frame-loop lines.
