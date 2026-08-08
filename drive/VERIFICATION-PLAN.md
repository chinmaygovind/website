# Verifying solo records

Written after a 12.288s Twin Loop went on the board on 2026-08-07, set by a
browser running retuned physics. **Both holes below are now closed**; what is
left is the re-simulation, steps 3 onward.

## Why it got through

`runcheck.validate` checks a submitted lap for *self-consistency* and never
re-simulates it - its own docstring says so. A client with a raised `ACCEL`
produces a replay that passes every check there is: real checkpoints in order, a
frame count matching the clock, a start on the line. The lap sat at a **median**
of 83 u/s and topped 91, against a `MAX_SPEED` of 50 and a hard velocity clamp of
85, and nothing looked.

Two holes, and only the first was used:

1. **`SPEED_CEIL` was `MAX_SPEED * 2.2`** = 110, against a simulation that cannot
   produce more than 85. Twenty-five u/s of headroom given away.
2. **The replay was never compared to the track.** `validate` checked the
   *splits array* was monotonic and that frame 0 was near spawn, and never
   tested the ghost's positions against the checkpoint planes or the road at
   all - so a synthesised straight line at 49 u/s for the right duration passed.
   The splits were the half that mattered: the board draws its checkpoint
   comparison from them and nothing tied them to the frames they arrived with.

## Done

**1. The ceilings** (`runcheck.py`). `SPEED_CEIL` is now `MAX_SPEED * 1.75`, just
over the clamp; a new `MEDIAN_SPEED_CEIL` rejects a lap whose *median* speed is
over `MAX_SPEED * 1.2`. The median is the one that cannot be dodged by sitting
under a threshold - gravity lifts a car over `MAX_SPEED` briefly, nothing holds
it there for a lap. Replayed over the real board: **82 honest laps accepted, the
cheated one rejected.** This closes the attack that was used, synchronously, with
an error message.

The median started at `* 1.06`, which is 53 against a quickest honest median of
49.5 - and that is `MIN_PLAUSIBLE` in a new hat, a bar set by how fast people
drive *today* that the first person to drive 10% better walks into. What makes
this one different from that mistake is that it bounds a **speed**, which the
physics bounds too, rather than a **time**, which it does not; so it can be set
from what the car can do instead of from what anybody has done. It is a backstop,
and the re-simulation below is the instrument.

**2. The track check** (`runcheck.follows_the_track`). Every checkpoint crossed
in the mouth of the gate, each crossing where its split claims it is, and the
whole lap inside a corridor of the ribbon. The gate rule mirrors `course.js`
exactly - same `gateNear`, same lateral pad, same floor - and a test reads that
file so the two cannot drift, because a server that credits a gate differently
from the game is somebody's real lap refused.

Calibrated against the board rather than guessed: the worst honest lap sits
**31.9** units off the ribbon (Cloudbreak, which is mostly gaps) against a
corridor of 60, and the worst gate-vs-split disagreement is **1.0 frame** against
a tolerance of nine. Replayed over the real board: 82 accepted, the cheated one
rejected, 13.6ms a lap.

**3. The input codec** (`runcheck.py`). `input_byte`/`input_fields` pack the four
fields `Car.step` reads into one byte; `pack_verify`/`unpack_verify` carry the
per-step input stream (run-length encoded) plus per-anchor state. Deliberately
**not** in the ghost blob - a ghost is downloaded by everyone racing that lap and
none of them needs the driver's inputs, and keeping it out means no replay
already on the board changes shape.

## The design for the rest

**Anchored re-simulation, asynchronous, quarantined, top-N only.**

Measured: one lap costs **0.9-3.7s** in QuickJS. Drive runs one eventlet worker,
so verification on the request path would freeze every socket in every live race
for seconds. It has to be another process.

**Why anchored rather than free-running.** Bit-exact replay across engines is not
cheaply achievable: `Math.exp` (x6), `atan2` and `acos` are implementation-defined
in ECMAScript, and the browser runs real three.js while a verifier runs
`three_stub.js` - two independent divergence sources, amplified chaotically over
2400 steps of feedback. Free-running and comparing the final time would reject
honest laps, which is the worst failure this can have. So the verifier *walks* the
ghost instead: at each 15Hz frame it seeds the car from the recorded pose, steps
the real `Car.step` 8 times with the recorded inputs, and requires the prediction
to land within tolerance of the next recorded frame. Divergence is bounded to
1/15s, so float noise never compounds.

`FIXED_DT` is 1/120 and a ghost frame is 1/15, so **exactly 8 steps fall between
frames** - frame *i* is the state at step *i * 8*. That integer alignment is what
makes this possible and `test_a_frame_is_exactly_eight_steps` pins it.

**What an anchor carries.** Pose is in the ghost already. Velocity and the
smoothed `steer` are not, and are the only solo state that does not re-derive
itself: `grounded`/`coyote`/`surface` are recomputed from the collider at the top
of every step, and `bumpSlip`/`slipCharge`/`catchupBoost` are race-only (both are
gated on `contactOn`, which solo never is) and therefore always zero.

**Tolerance.** Quantisation gives ~0.0003 units of seeded error per anchor; the
cheat was off by ~2.2 units per anchor (33 u/s x 1/15s). A tolerance of ~0.15
units is 15x clear of measurement and still catches it everywhere.

### 4. Record the inputs (client)

`static/js/game.js` - the frame loop calls `Stepper.run(dt, fn)`, and every call
to `fn(FIXED_DT)` is one step. Push `runcheck.input_byte(...)` of the current
input there while `run.state === 'running'`, and push `[vx,vy,vz,steer]` per
ghost frame in `Run._recordGhost` (`course.js`). `Stepper.reset()` already fires
when the clock starts, so step 0 of the stream is the first step of the lap.

### 5. The queue (`models.py`)

A new **table**, `drive_run_checks` - a table and not a column on `drive_times`,
because `create_all` makes tables and not columns, so it lands on the live
database by itself where a column needs a hand migration (same reasoning as
`drive_starts` and `drive_races`).

    drive_time_id, status (pending|pass|fail), reason, evidence (the verify blob),
    queued_at, checked_at

**Absence of a row means verified.** That grandfathers the 82 existing laps with
no backfill at all - they have no input stream and never can, and all 82 measure
clean.

### 6. Enqueue, top-N only (`app.py`)

In `/api/run`, inside the existing `if improved:` branch - a lap slower than your
PB writes no time, so there is nothing to verify. Queue only when the run would
also place within `VERIFY_TOP_N` (3) on that track.

Two properties make the threshold safe. The **record is rank 1, so the record is
always verified**, which is the thing worth protecting. And **times only ever
improve**, so a run outside the top N at submission can never rise into it later -
the queue never needs revisiting. The one exception is a row being *deleted*,
which promotes everyone below it, so deletion should re-enqueue the newly-promoted.

The Time Trial Score board is safe by accident and worth not breaking: it rewards
placing, so cheating to 4th on all twelve tracks scores 48 against a real
driver's ~15. The placings that win it are exactly the ones that get checked.

### 7. Quarantine (`app.py`)

**Visible to its owner, not to others.** A pending row shows on your own
`/account`, your results sheet and your PB; the public board, the track record and
`/api/ghost` read the last *verified* time. You never see a lap you drove go
missing, and nobody else ever sees an unverified one.

### 8. The verifier (`drive/verify.py` + a `drive-verify` service)

Long-lived, so the 12 colliders are built once and amortised; polls the queue.
Reuses `tests/jsrt.py` wholesale - it already bundles `trackmesh.js`,
`physics.js` and `course.js` into QuickJS against `three_stub.js`, which is the
whole reason this needs no Python port of the physics and cannot drift from the
game.

Deploy: another systemd unit beside `drive`, restarted by the Action when
`drive/` moves. nginx/TLS untouched. `quickjs` moves from
`requirements-test.txt` into the drive service's own requirements, since the
verifier needs it in prod.

## Re-checking the board by hand

`tools/audit_times.py` measures the speeds inside every stored ghost and flags
laps past the clamp or over `MAX_SPEED` for a whole lap. It is what found this
one. It needs no inputs, so it works on the laps that predate all of the above.
