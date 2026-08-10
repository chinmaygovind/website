"""Re-drive a submitted lap through the real physics and see if it holds up.

`runcheck.validate` asks whether a replay is *self-consistent* - right duration,
no teleports, through every gate when its splits say, inside a corridor of the
road. All of that is about the shape of the recording. None of it asks the one
question that matters: **could this car have driven that?** A browser with a
raised `ACCEL` produces a replay that passes every check in `runcheck` and took a
Twin Loop record in 12.288s on 2026-08-07. This is the answer to that lap.

## Anchored, not free-running

The obvious version of this - start a car on the line, feed it the recorded
inputs, compare the finishing time - does not work, and it fails in the worst
direction: it refuses honest laps. `Math.exp` (used six times a step), `atan2`
and `acos` are implementation-defined in ECMAScript, and the browser runs real
three.js while this runs `three_stub.js`. Two independent sources of last-bit
divergence, amplified chaotically over a few thousand steps of feedback, and the
two runs part company somewhere in the second corner.

So the verifier **walks the recording** instead. At every anchor it seeds a real
`Car` from the recorded state, steps the real `Car.step` exactly
`STEPS_PER_FRAME` times with the recorded inputs, and requires the prediction to
land on the next anchor. Divergence can never compound past one window - a
fifteenth of a second - so float noise stays at the last bit, and what is left to
measure is whether the physics can account for the car's motion.

`FIXED_DT` is 1/120 and an anchor is every eighth step, so a window is exactly
1/15s and there is no interpolation anywhere in it. That is what
`Run.noteStep` is arranged around.

## What it actually decides

Three numbers, and every one of them is reported in the evidence whether the lap
passes or fails:

* **median** - how far the *typical* window lands from where it should. This is
  the instrument, and it is a median rather than a worst case because a retuned
  car does not diverge once, it diverges on every window it is on the throttle:
  an honest lap sits at 0.0006 units on every track in the pool at every frame
  rate, and a car with 2% more engine sits at 0.0026. See MEDIAN_TOL, which is
  the one number here that was measured rather than chosen.
* **slip** - the total distance the physics cannot account for, counting only
  windows past `SLIP_TOL`. The median cannot see divergence that is rare rather
  than typical, and this is what bounds what could be hidden in a handful of
  hand-built windows.
* **drift** - how far the anchors sit from the replay they were submitted with.
  Without this the two halves come apart: an honest lap of your own, with
  somebody else's faster ghost stapled to it, would pass the physics check and be
  timed off the stolen replay. `/api/ghost` is public and hands out the record's
  own frames, so this is not a theoretical pairing.
* **cover** - that the evidence spans the lap it claims, from the line to the
  flag, and that no more physics was run than there was time to run it in.

## What it does not decide

That a *person* drove it. Feed the real physics perfect inputs from a script and
this passes, because the car really did do that. What it ends is the whole class
of "my car accelerates faster than yours", which is every cheat anybody has
actually tried here.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import jsrt
import runcheck
import tuning as T


def available():
    """Can this process re-simulate at all? False means quickjs is not installed."""
    return jsrt.HAVE_QUICKJS


# ---------------------------------------------------------------------------
# The thresholds
# ---------------------------------------------------------------------------

# The typical window, and the number the verdict really turns on.
#
# **Anchoring makes the signal much smaller than it looks, and this is the whole
# calibration.** Because each window is seeded with the recorded *velocity* as
# well as the recorded pose, a retuned car does not arrive 2.2 units out - the
# difference in speed is handed back at every anchor and never accumulates. What
# is left is one window's worth of the difference in *acceleration*, which for a
# 40% richer engine is ½·a·dt² ≈ 0.06 units. So a per-window tolerance loose
# enough to be safe would be far too loose to see a cheat at all, and the useful
# measurement is not the worst window but the **middle** one.
#
# Measured, by driving all thirteen tracks through the real physics and re-driving
# them here (`tests/test_verify.py`):
#
#     honest, every track, 12-144fps, hitches, respawns   median 0.00055-0.00063
#     ACCEL x1.02                                         median 0.0026
#     ACCEL x1.05                                         median 0.0069
#     GRIP  x1.5                                          median 0.0054
#     DRAG  x0.7 (a 20% higher top speed)                 median 0.034
#     ACCEL x1.4 (about the lap that started all this)    median 0.042
#
# The honest floor is the quantisation of an anchor and nothing else - it does
# not move with frame rate, track, driving or how hard the car is being driven,
# because none of those changes how many millimetres a position is rounded to.
# That is what makes 0.002 a threshold rather than a guess: it is three times a
# floor that is the same everywhere, and under the smallest cheat measurable.
MEDIAN_TOL = 0.002

# The middle of a lap is not all of it, so the second rule is for divergence that
# is *isolated* rather than typical - a hand-built replay with a few free metres
# dropped into it, which a median would never see.
#
# A window is only counted past `SLIP_TOL`, which is well above every honest p99
# measured (0.0013) and above all but a handful of individual windows: across the
# thirteen laps above, 12 windows in 6,900 exceeded it, the worst at 0.17, and
# they are the genuinely discontinuous moments - `grounded` flips at a fixed
# probe distance and takes the whole grip term with it, `_resolveWalls` hands
# back a car's normal velocity with a `1 + WALL_BOUNCE` on it the instant a
# contact registers at all, and half a millimetre of seeding error is enough to
# land on the other side of either.
#
# The budget is 10-20x what those laps actually produced. What it concedes, said
# plainly rather than left to be found: somebody hand-building a replay could
# hide about this much free travel in it, which at racing speed is a few
# hundredths of a second - less than the quantisation `time_window` already
# allows - and it costs them an input stream that survives every other check
# here. The alternative is a budget tight enough to refuse a real lap for
# grazing a barrier, which is a far worse failure than a hundredth of a second.
SLIP_TOL = 0.02
SLIP_FLOOR = 1.0
SLIP_PER_SECOND = 0.05

# And no single window may miss by a metre, whatever the budget says. The worst
# honest window across thirteen laps was 0.17, and a lap with two falls and two
# respawns in it - the only moment a car is *put* somewhere rather than driven
# there - peaked at 0.008. This exists so that the blatant case is refused with
# something legible rather than as an accumulated total.
HARD_TOL = 1.0

# How far an anchor may sit from the replay's own pose at that anchor's clock.
#
# Deliberately loose, because these two are recorded on different clocks: an
# anchor is a step boundary stamped with the frame's time, so it is up to one
# render frame *earlier* than the replay pose it is compared with. Measured, that
# is 0.6 units at 144fps, 0.8 at 60, 1.6 at 30 and 3.1 at 12fps or with a
# stuttering frame - all of it the same fact, that a car at racing speed covers
# most of a metre in a frame.
#
# It is not trying to be a precise measurement. It asks whether these are the
# same lap, and the thing it is there to refuse - a replay downloaded from
# `/api/ghost`, which is public, stapled to an honest lap of your own - is a
# different lap by tens of units within a second or two and by hundreds by the
# end. The budget is per second for the same reason the other one is: a long
# track has more chances to be briefly odd.
BIND_TOL = 6.0
BIND_SLIP_PER_SECOND = 2.0
BIND_SLIP_FLOOR = 20.0

# The evidence has to reach both ends of the lap. The last anchor is the last
# step boundary before the flag, so it can be a whole window (67ms) plus the
# frame that spotted the finish behind the time being claimed. 250ms leaves room
# for a slow frame on top of that; what it concedes is the last fifth of a
# second of the lap, which the replay still has to get right on its own - the
# corridor, the gates and ending in the mouth of the finish all apply there.
COVER_SLACK_MS = 250

# Sim time may lag the clock - a frame longer than `MAX_STEPS` steps drops the
# rest, so a stutter puts the step count permanently behind - but it can never
# *lead* it: `Stepper` only ever runs the steps that real time has paid for. An
# anchor claiming to be at a lap time earlier than its own step index allows is
# a recording with more physics in it than the clock it is submitted with.
SIM_AHEAD_SLACK_MS = 150

WINDOW_S = runcheck.STEPS_PER_FRAME * T.FIXED_DT


# ---------------------------------------------------------------------------
# The bit that runs the game's own code
# ---------------------------------------------------------------------------

# `FIELDS` is handed in from `runcheck.input_fields` rather than decoded here, so
# there is one definition of what a byte means and the verifier cannot disagree
# with the packer about which bit is the handbrake.
HARNESS = """
var _BUILT = {};
function built(slug) {
  if (!_BUILT[slug]) {
    const t = TRACKS.find(x => x.slug === slug);
    if (!t) throw new Error('no such track: ' + slug);
    _BUILT[slug] = buildTrack(t, T);
  }
  return _BUILT[slug];
}

/**
 * Re-drive every window of a lap.
 *
 * `A` is the anchors, `IN` the input byte per step, `RESP` an index per anchor
 * into `GATES` - where a car that falls off at that point in the lap is put
 * back, which is the last checkpoint it had credited. Without it a lap with a
 * respawn in it re-simulates the fall correctly and then puts the car back in
 * the wrong place, and two honest windows read as teleports.
 *
 * Returns one distance per window, plus the speed the car was doing, which is
 * only ever used to describe a failure.
 */
function walk(slug, A, IN, RESP, GATES) {
  const b = built(slug);
  const car = new Car(T, b);
  const dt = T.FIXED_DT, S = %(steps)d;
  const err = [], spd = [];
  for (let i = 0; i + 1 < A.length; i++) {
    const a = A[i], nx = A[i + 1];
    // Seed the state a step carries forward, and only that. Everything else is
    // either recomputed at the top of `Car.step` from the collider or is carried
    // by this same car from the window before - `padBoost` above all, which is
    // worth engine and is therefore never taken from the recording.
    car.pos.set(a[1], a[2], a[3]);
    car.quat.set(a[4], a[5], a[6], a[7]);
    car.quat.normalize();
    car._syncAxes();
    car.vel.set(a[8], a[9], a[10]);
    car.steer = a[11];
    const g = GATES[RESP[i]];
    car.setRespawn(g[0], g[1]);
    for (let k = 0; k < S; k++) car.step(dt, FIELDS[IN[i * S + k]]);
    err.push(Math.hypot(car.pos.x - nx[1], car.pos.y - nx[2], car.pos.z - nx[3]));
    spd.push(car.vel.length());
  }
  return { err: err, spd: spd };
}
""" % {"steps": runcheck.STEPS_PER_FRAME}


class Verifier:
    """A QuickJS runtime with the game in it, and the tracks it has built.

    Worth holding on to: building a track's collider is most of the cost of the
    first lap on it and none of the cost of the second.
    """

    # A quarter of the default, because this runs on a box with five services on
    # it and a gigabyte between them. Measured, the whole process peaks around
    # 110MB on the longest track in the pool, so this is a ceiling on a runaway
    # rather than a budget anything normal comes near - and a runtime that hits
    # it throws, which is filed as an `error` and retried, rather than being
    # taken out by the kernel along with whatever else was running.
    MEMORY_MB = 256

    def __init__(self):
        self.rt = jsrt.Runtime(memory_mb=self.MEMORY_MB)
        self.rt.load_tuning_and_tracks()
        self.rt.eval("var FIELDS = %s;" %
                     json.dumps([runcheck.input_fields(b) for b in range(256)]))
        self.rt.eval(HARNESS)

    def walk(self, slug, anchors, inputs, resp_ix, gates):
        self.rt.eval("var _A = %s, _IN = %s, _R = %s, _G = %s;" % (
            json.dumps(anchors), json.dumps(inputs),
            json.dumps(resp_ix), json.dumps(gates)))
        out = self.rt.call("walk(%s, _A, _IN, _R, _G)" % json.dumps(slug))
        self.rt.eval("_A = _IN = _R = _G = null;")
        return out


# ---------------------------------------------------------------------------
# The check itself
# ---------------------------------------------------------------------------

def _respawn_points(track, splits, anchors):
    """Where a fall puts the car back, at each anchor. Mirrors `Run.update`.

    The run's respawn target is the last checkpoint it credited and the start
    gate before it has credited any, lifted 0.4 above the gate - all three of
    those are copied from `Run` rather than inferred, because a verifier that
    puts a fallen car back somewhere else reads two honest windows as teleports.
    """
    cps, _ = runcheck._gates_of(track)
    start = next((g for g in track["gates"] if g["kind"] == "start"), None)
    if start is not None:
        gates = [[[start["p"][0], start["p"][1] + 0.4, start["p"][2]], list(start["f"])]]
    else:
        gates = [[list(track["spawn"]["p"]), list(track["spawn"]["fwd"])]]
    for g in cps:
        gates.append([[g["p"][0], g["p"][1] + 0.4, g["p"][2]], list(g["f"])])
    ix = [min(len(gates) - 1, sum(1 for s in splits if s <= a[0])) for a in anchors]
    return gates, ix


def _ghost_at(frames, t_s):
    """The replay's pose at `t_s` seconds - `Ghost.at`, for the binding check."""
    f = t_s * runcheck.GHOST_HZ
    i = int(math.floor(f))
    if i < 0:
        return frames[0]
    if i >= len(frames) - 1:
        return frames[-1]
    a, b, u = frames[i], frames[i + 1], f - i
    return [a[k] + (b[k] - a[k]) * u for k in range(3)]


def check(track, time_ms, splits, frames, blob, verifier=None):
    """Did this lap happen? -> {"ok", "reason", "stats"}.

    ``frames`` is the unpacked ghost and ``blob`` the packed evidence. The
    verifier is optional so that one runtime can do a queue's worth of laps.
    """
    stats = {}
    ev = runcheck.unpack_verify(blob)
    if not ev:
        return {"ok": False, "reason": "no evidence to re-drive", "stats": stats}
    anchors, inputs = ev["anchors"], ev["inputs"]
    n = len(anchors)
    stats["anchors"] = n
    stats["steps"] = len(inputs)
    if n < 2:
        return {"ok": False, "reason": "no evidence to re-drive", "stats": stats}
    need = (n - 1) * runcheck.STEPS_PER_FRAME
    if len(inputs) < need:
        return {"ok": False, "reason": "the input stream stops before the lap does",
                "stats": stats}

    # --- does the evidence cover the lap it is evidence for? -----------------
    if anchors[0][0] > COVER_SLACK_MS:
        return {"ok": False, "reason": "the evidence does not start at the line",
                "stats": stats}
    last = anchors[-1][0]
    stats["cover_ms"] = round(time_ms - last, 1)
    if last < time_ms - COVER_SLACK_MS:
        return {"ok": False, "reason": "the evidence stops %.1fs before the flag"
                                       % ((time_ms - last) / 1000.0), "stats": stats}
    for i in range(1, n):
        if anchors[i][0] < anchors[i - 1][0]:
            return {"ok": False, "reason": "the evidence runs backwards",
                    "stats": stats}
    # A step is a step of real time, so anchor i cannot claim a lap clock earlier
    # than the steps behind it took to run.
    worst = max(i * WINDOW_S * 1000.0 - a[0] for i, a in enumerate(anchors))
    stats["ahead_ms"] = round(worst, 1)
    if worst > SIM_AHEAD_SLACK_MS:
        return {"ok": False,
                "reason": "the evidence runs %.0fms more physics than the clock allows"
                          % worst, "stats": stats}

    # --- is it the same lap as the replay? -----------------------------------
    bind = [_dist(a[1:4], _ghost_at(frames, a[0] / 1000.0)) for a in anchors]
    bind_slip = sum(max(0.0, d - BIND_TOL) for d in bind)
    stats["drift_max"] = round(max(bind), 3)
    stats["drift_slip"] = round(bind_slip, 3)
    budget = max(BIND_SLIP_FLOOR, BIND_SLIP_PER_SECOND * time_ms / 1000.0)
    if bind_slip > budget:
        return {"ok": False,
                "reason": "the evidence is not the lap the replay shows "
                          "(%.0f units adrift)" % bind_slip, "stats": stats}

    # --- and could the car have driven it? -----------------------------------
    v = verifier or Verifier()
    gates, resp = _respawn_points(track, splits, anchors)
    out = v.walk(track["slug"], anchors, inputs[:need], resp, gates)
    err = out["err"]
    slip = sum(max(0.0, e - SLIP_TOL) for e in err)
    median = sorted(err)[len(err) // 2]
    worst_i = max(range(len(err)), key=lambda i: err[i])
    budget = max(SLIP_FLOOR, SLIP_PER_SECOND * time_ms / 1000.0)
    stats["windows"] = len(err)
    stats["median"] = round(median, 5)
    stats["slip"] = round(slip, 3)
    stats["budget"] = round(budget, 3)
    stats["worst"] = round(err[worst_i], 4)
    stats["worst_at_ms"] = int(anchors[worst_i][0])
    stats["worst_speed"] = round(out["spd"][worst_i], 2)

    if median > MEDIAN_TOL:
        return {"ok": False,
                "reason": "this car is not the one the game simulates: a typical "
                          "step misses by %.4f units, and the limit is %.4f"
                          % (median, MEDIAN_TOL), "stats": stats}
    if err[worst_i] > HARD_TOL:
        return {"ok": False,
                "reason": "the car is %.1f units from where it should be at %.1fs"
                          % (err[worst_i], anchors[worst_i][0] / 1000.0),
                "stats": stats}
    if slip > budget:
        return {"ok": False,
                "reason": "the physics cannot account for %.1f units of this lap "
                          "(budget %.1f)" % (slip, budget), "stats": stats}
    return {"ok": True, "reason": "", "stats": stats}


def _dist(a, b):
    return math.dist(a[:3], b[:3])


def check_run(track, time_ms, splits, ghost_blob, verify_blob, verifier=None):
    """`check`, from what a `drive_run_checks` row actually stores.

    It re-runs `runcheck.validate` first. `/api/run` has already done that
    synchronously, so this is belt and braces there - but it means running this
    by hand on a row is a complete answer rather than half of one.
    """
    frames = runcheck.unpack_ghost(ghost_blob)
    ok, why = runcheck.validate(track, time_ms, splits, frames)
    if not ok:
        return {"ok": False, "reason": why, "stats": {}}
    return check(track, time_ms, splits, frames, verify_blob, verifier=verifier)


# ---------------------------------------------------------------------------
# Running it against the queue
# ---------------------------------------------------------------------------
#
# **A process of its own, spawned per check, rather than a service.** A lap costs
# one to four seconds of solid CPU, and Drive is one eventlet worker - doing this
# on the request path would freeze every socket in every live race for as long as
# it took. The plan this was built from called for a long-lived daemon beside the
# `drive` service, and this is deliberately not that: a daemon is a second thing
# to install by hand on the box, a second thing to restart on deploy, and a
# second thing that can be quietly dead while the board waits for it. A
# subprocess cannot be out of date, cannot be missing, and needs nothing
# installed - `app.py` spawns `sys.executable`, which is the venv that just
# imported it.
#
# It judges and it does not apply. Writing the pass back into `drive_times` means
# medals and counters, which live in `app.py` and would have to be duplicated
# here to be run from another process; instead this writes the verdict to the row
# and `app.py` settles it the next time anything reads the board. One writer to
# the tables that matter, and this one only ever touches its own row.

def _bind():
    """A minimal Flask app on the same database, with none of `app.py` in it.

    Importing `app.py` would monkey-patch eventlet and start a socket server's
    worth of module-level work in a process that wants one row from one table.
    """
    from flask import Flask
    import models

    a = Flask(__name__)
    a.config["SQLALCHEMY_DATABASE_URI"] = models.database_url()
    a.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    models.db.init_app(a)
    return a, models


def run_check_row(row, tracks_mod, verifier=None):
    """Judge one queued row and write the verdict into it. -> the verdict dict."""
    from datetime import datetime
    track = tracks_mod.get(row.track)
    if not track:
        res = {"ok": False, "reason": "no such track", "stats": {}}
    else:
        try:
            res = check_run(track, row.time_ms, row.splits, row.ghost,
                            row.evidence, verifier=verifier)
        except Exception as e:                       # a broken runtime is not a cheat
            res = {"ok": None, "reason": "verifier error: %s" % e, "stats": {}}
    if res["ok"] is None:
        row.status = "error"
    else:
        row.status = "pass" if res["ok"] else "fail"
    row.reason = res["reason"][:200]
    row.stats_json = json.dumps(res["stats"])
    row.checked_at = datetime.utcnow()
    return res


def main(argv):
    import argparse
    p = argparse.ArgumentParser(
        description="Re-drive submitted laps.",
        epilog="A row that has already been applied is judged again if you name "
               "it, and the verdict is written - but nothing moves on the board, "
               "because applying a verdict happens once. Taking a lap back off "
               "the board is a hand edit, on purpose.")
    p.add_argument("--check", type=int, action="append", default=[],
                   help="a drive_run_checks id (repeatable)")
    p.add_argument("--pending", action="store_true",
                   help="every row still waiting, oldest first")
    p.add_argument("--again", action="store_true",
                   help="with --pending, re-judge rows that errored as well")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if not (args.check or args.pending):
        p.print_help()               # before anything opens a database
        return 2
    if not available():
        print("quickjs is not installed - nothing can be verified", file=sys.stderr)
        return 2

    import tracks
    app, models = _bind()
    with app.app_context():
        q = models.DriveRunCheck.query
        if args.check:
            rows = q.filter(models.DriveRunCheck.id.in_(args.check)).all()
        else:
            want = ["pending", "error"] if args.again else ["pending"]
            rows = (q.filter(models.DriveRunCheck.status.in_(want))
                     .order_by(models.DriveRunCheck.id.asc()).limit(50).all())
        if not rows:
            return 0
        try:
            v = Verifier()
        except Exception as e:
            # Left pending rather than failed, and said out loud: a runtime that
            # will not start is this box's problem, not the driver's, and the
            # rows are picked up again by the next sweep.
            print("could not start the verifier: %s" % e, file=sys.stderr)
            return 1
        for row in rows:
            res = run_check_row(row, tracks, verifier=v)
            models.db.session.commit()
            if not args.quiet:
                print("#%d %s %s %s" % (row.id, row.track, row.status,
                                        res["reason"] or json.dumps(res["stats"])))
    return 0


if __name__ == "__main__":                           # pragma: no cover
    # Background work on a box that is also serving the site: a check is allowed
    # to take a whole core and the race in the next room is not. Here rather
    # than in `main`, which the tests call in their own process.
    try:
        os.nice(10)
    except (AttributeError, OSError):                # not POSIX, or not permitted
        pass
    sys.exit(main(sys.argv[1:]))
