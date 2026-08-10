"""Ghost packing and best-effort validation of submitted times.

The car is simulated in the browser - it has to be, for the driving to feel like
anything - which means a submitted lap time is a claim, not a fact. Nothing here
can make it a fact. What it can do is insist the claim comes with a *replay that
holds up*: every run ships the ghost that will be raced against, and a run is
rejected unless that ghost is self-consistent - right duration, no teleports, no
impossible speeds, starting on the line, through every checkpoint in order.

**Being fast is not evidence of anything.** There used to be a floor here as
well: a time under `ideal * MIN_PLAUSIBLE` was rejected as physically
unreachable. But `ideal` is the lap `laptime.py` derives from a relaxed racing
line, and a person who knows the track beats it - so the floor was not measuring
cheating, it was measuring how conservative the estimate happened to be, and the
better you drove the more likely it was to throw the lap away. The replay checks
below are the ones that mean something, because they are about the run rather
than about the number.

So faking a time is not "send a small number", it is "synthesise a plausible
30-second replay" - and the fake ghost is then public on the leaderboard for
anyone to race.

**That was once the whole of it, and it was not enough.** Every check in here is
about whether a replay is self-consistent, and a browser running retuned physics
produces a replay that is perfectly consistent with itself: it is a real
recording of a real drive, it is just not this car. That is how a 12.288s Twin
Loop took a track record. So a lap quick enough to place near the top of a board
is now **re-driven on the server** through the game's own `Car.step` before it
goes up - see `verify.py`, which owns that, and the input stream and anchors
below, which are what it re-drives from. Everything here still runs first and on
the request path: it is cheap, it is synchronous, and it answers with a reason.
"""

import base64
import json
import zlib

import tuning as T

# Ghost sample rate the client records at, and the quantisation used on the way
# to the database. 15 Hz is plenty - ghosts are interpolated on playback.
GHOST_HZ = 15
POS_Q = 100.0     # positions to the centimetre
ROT_Q = 4096.0    # quaternion components

MAX_GHOST_FRAMES = GHOST_HZ * 60 * 6      # six minutes is beyond any track

# A hard ceiling on believable speed. The physics clamps velocity at
# `MAX_SPEED * 1.7` and nothing in the simulation can produce more, so anything
# past it is a car that was not running this game's physics.
#
# This used to be `MAX_SPEED * 2.2` - 110 against a simulation that cannot exceed
# 85 - and that 25 u/s of headroom was given away for nothing. It is what a
# retuned client drove a 12.288s Twin Loop through: the replay sat at a *median*
# of 83 and topped 91, passed every check here, and took the track record. The
# margin the other way is enormous: across the 82 honest laps on the board the
# fastest single frame is 62.5, so the ceiling below is still 24 u/s clear of the
# quickest thing anybody has actually driven.
#
# The small allowance over the clamp is for measurement, not for driving: a ghost
# is 15Hz with positions on a 1cm grid, so a frame pair can read slightly high.
SPEED_CEIL = T.MAX_SPEED * 1.75

# And a ceiling on the speed a *whole lap* can average.
#
# The one above is a single-frame test, which a cheat can simply sit underneath.
# This one cannot be dodged that way, because it is not about any one moment: a
# long descent lifts a car over `MAX_SPEED` for a few seconds - that is why the
# top speed alone is a blunt instrument - but nothing in the physics holds it
# there for a lap. Every honest lap on the board medians between 45 and **49.5**
# against a `MAX_SPEED` of 50, and the cheated one medianed 83.
#
# It is deliberately a **backstop and not a measurement**. Set just over the
# quickest honest median - 1.06 was tried, at 53 - it is `MIN_PLAUSIBLE` wearing
# a different hat: a bar calibrated against how fast people drive *today*, which
# the first person to drive 10% better walks into. The thing that makes this
# different from that mistake is that it bounds a *speed*, which the physics
# bounds too, rather than a *time*, which it does not - so it can be set from
# what the car can do instead of from what anybody has done. Half a lap spent
# 20% over `MAX_SPEED` already means half a lap of descent, and no track in the
# pool comes close. Precision here is not this check's job; the re-simulation is
# what says whether a lap is real, and this only has to make the blatant case a
# synchronous error with a message rather than a queued one.
MEDIAN_SPEED_CEIL = T.MAX_SPEED * 1.2


def pack_ghost(frames):
    """frames: [[x,y,z,qx,qy,qz,qw(,flags)], ...] -> compact base64 string.

    The eighth value is the car's flag byte at that instant, which is how a
    ghost knows to light its brake lamps and go amber in a slide. A pose says
    where a car was and nothing about what the driver was doing, so without it
    every replay is a car coasting silently round the lap.

    Laps recorded before it existed are seven wide and stay that way, so the
    stride is written into the blob rather than assumed: an old ghost still
    unpacks, it simply has no lamps.
    """
    stride = 8 if frames and len(frames[0]) >= 8 else 7
    ints = []
    for f in frames:
        ints.append(int(round(f[0] * POS_Q)))
        ints.append(int(round(f[1] * POS_Q)))
        ints.append(int(round(f[2] * POS_Q)))
        for k in range(3, 7):
            ints.append(int(round(f[k] * ROT_Q)))
        if stride == 8:
            ints.append(int(f[7] or 0) & 0xFF)
    raw = json.dumps({"hz": GHOST_HZ, "q": [POS_Q, ROT_Q], "n": stride, "d": ints},
                     separators=(",", ":")).encode()
    return base64.b64encode(zlib.compress(raw, 9)).decode()


def unpack_ghost(blob):
    """base64 string -> frames, or None if it is not a ghost we can read."""
    if not blob:
        return None
    try:
        obj = json.loads(zlib.decompress(base64.b64decode(blob)))
        d = obj["d"]
        pq, rq = obj.get("q", [POS_Q, ROT_Q])
        # Ghosts written before flags existed have no `n` and are seven wide.
        stride = int(obj.get("n", 7))
        if stride not in (7, 8):
            return None
        out = []
        for i in range(0, len(d) - stride + 1, stride):
            f = [d[i] / pq, d[i + 1] / pq, d[i + 2] / pq,
                 d[i + 3] / rq, d[i + 4] / rq, d[i + 5] / rq, d[i + 6] / rq]
            if stride == 8:
                f.append(d[i + 7])
            out.append(f)
        return out
    except Exception:
        return None


def ghost_hz(blob):
    try:
        return json.loads(zlib.decompress(base64.b64decode(blob))).get("hz", GHOST_HZ)
    except Exception:
        return GHOST_HZ


# ---------------------------------------------------------------------------
# The input stream
# ---------------------------------------------------------------------------
#
# A pose says where a car was; it does not say that the physics could have put it
# there. To answer that, the replay has to carry what the driver was *doing*, one
# entry per fixed physics step, so the run can be stepped again on the server
# against the real `Car.step` (see verify.py).
#
# `Car.step` reads four fields and they fit in a byte, so a step is one small
# integer and a lap is a few thousand of them - run-length encoded first, because
# a driver holds the throttle for seconds at a time and the raw stream is long
# runs of the same value.
#
# `FIXED_DT` is 1/120 and a ghost frame is 1/15, so **exactly 8 steps fall
# between consecutive frames**. That integer alignment is why the anchors are
# recorded every `STEPS_PER_FRAME` steps: anchor *i* is the state at step
# *i * 8*, which is what lets a window be re-driven with no interpolation in it.
#
# It is deliberately **not** in the ghost blob. A ghost is downloaded by everyone
# who races that lap, and none of them needs the driver's inputs; it also means
# no replay already on the board changes shape. It lives with the verification
# row instead, which is the only thing that reads it.

STEPS_PER_FRAME = 8      # FIXED_DT 1/120 against GHOST_HZ 15

# How far up the board a lap has to be for the re-simulation to be worth its
# seconds. The record is rank 1, so the record is always checked - which is the
# thing worth protecting - and times only ever improve, so a run outside the top
# N at submission can never rise into it later and the queue never needs
# revisiting. The one exception is a row being *deleted*, which promotes
# everybody below it.
VERIFY_TOP_N = 3

# The same six-minute bound `MAX_GHOST_FRAMES` puts on the poses, at step rate.
MAX_INPUT_STEPS = 120 * 60 * 6

_IN_THROTTLE = 1
_IN_BRAKE = 2
_IN_HANDBRAKE = 4
_IN_RIGHT = 8
_IN_LEFT = 16


def input_byte(throttle, brake, steer, handbrake):
    """The four fields `Car.step` reads, as one byte."""
    b = 0
    if throttle:
        b |= _IN_THROTTLE
    if brake:
        b |= _IN_BRAKE
    if handbrake:
        b |= _IN_HANDBRAKE
    if steer > 0:
        b |= _IN_RIGHT
    elif steer < 0:
        b |= _IN_LEFT
    return b


def input_fields(b):
    """A byte back into the dict `Car.step` takes."""
    return {"throttle": 1 if b & _IN_THROTTLE else 0,
            "brake": 1 if b & _IN_BRAKE else 0,
            "steer": (1 if b & _IN_RIGHT else 0) - (1 if b & _IN_LEFT else 0),
            "handbrake": bool(b & _IN_HANDBRAKE)}


def pack_inputs(bytes_):
    """[byte, ...] -> run-length pairs. Cheap, and it shrinks a lap ~50x."""
    out = []
    for b in bytes_:
        b = int(b) & 0xFF
        if out and out[-1][0] == b and out[-1][1] < 0xFFFF:
            out[-1][1] += 1
        else:
            out.append([b, 1])
    return [v for pair in out for v in pair]


def unpack_inputs(rle):
    """Run-length pairs back to [byte, ...], or None if it is not readable.

    Total, because `/api/run` hands it whatever was in the request body: this
    used to be reached only through `unpack_verify`, which catches everything,
    and a bare list of anything at all reached the `int()` calls below.
    """
    try:
        if not rle or len(rle) % 2:
            return None
        out = []
        for i in range(0, len(rle), 2):
            b, n = int(rle[i]) & 0xFF, int(rle[i + 1])
            if n < 0 or len(out) + n > MAX_INPUT_STEPS:
                return None
            out.extend([b] * n)
        return out
    except (TypeError, ValueError):
        return None


# An anchor is the whole of a solo car's carried state at one step boundary:
#
#     [t_ms, x, y, z, qx, qy, qz, qw, vx, vy, vz, steer]
#
# **The pose is in here as well as in the ghost, and that is not duplication.** A
# ghost frame is the pose at a moment of the *lap clock*, interpolated between
# two render frames by `Run._recordGhost`; an anchor is the exact state the
# simulation held at a step boundary. Seeding a re-simulation from an
# interpolated pose - a state the physics was never actually in - and comparing
# where it lands against another one puts a whole render frame of error in the
# only measurement this makes. The ghost keeps the job it has (playback, at the
# clock's own rate) and the anchors keep this one.
#
# `t_ms` is the lap clock at that step, and it is what ties the two together.
# `Stepper` runs 8 steps per ghost frame *when it keeps up*: a frame longer than
# 66ms hits `MAX_STEPS` and drops the rest, so after a hitch the step count is
# behind the clock for the remainder of the lap. Anchor *i* is therefore not
# always ghost frame *i*, and pinning them to each other by index would refuse an
# honest lap for one stutter. Carrying the clock costs one integer and says
# exactly which instant of the replay each anchor is.
#
# Everything else a solo car holds either re-derives itself inside a step
# (`grounded`, `coyote`, `surface` come off the collider at the top of
# `Car.step`) or is race-only and therefore always zero here (`bumpSlip`,
# `slipCharge`, `catchupBoost` - contact and the tow are both gated on
# `contactOn`, which solo never is). `padBoost` is neither: it is carried across
# windows and it is worth engine, so the verifier keeps **its own** rather than
# being told - a number a client can set is a number a client can set to
# `PAD_BOOST` for the whole lap.
#
# Positions are held to the millimetre rather than the ghost's centimetre. It is
# a few bytes, and it is the largest term in the seeding error - and 5mm is
# enough to land on the other side of the "am I touching the ground" threshold,
# which is the one difference in a step that is not small.
A_POS_Q = 1000.0
A_ROT_Q = 32768.0
A_VEL_Q = 1000.0
A_STEER_Q = 100000.0

ANCHOR_STRIDE = 12

# Six minutes of anchors, the bound `MAX_GHOST_FRAMES` puts on the poses.
MAX_ANCHORS = MAX_GHOST_FRAMES


def pack_verify(inputs, anchors):
    """The evidence a re-simulation needs, beyond the replay already submitted.

    ``inputs``  one byte per fixed step, from the step the clock started.
    ``anchors`` one 12-value row per `STEPS_PER_FRAME` steps - see above.
    """
    d = []
    for a in anchors:
        d.append(int(round(a[0])))
        for k in (1, 2, 3):
            d.append(int(round(a[k] * A_POS_Q)))
        for k in (4, 5, 6, 7):
            d.append(int(round(a[k] * A_ROT_Q)))
        for k in (8, 9, 10):
            d.append(int(round(a[k] * A_VEL_Q)))
        d.append(int(round(a[11] * A_STEER_Q)))
    raw = json.dumps({"v": 2, "q": [A_POS_Q, A_ROT_Q, A_VEL_Q, A_STEER_Q],
                      "i": pack_inputs(inputs), "a": d},
                     separators=(",", ":")).encode()
    return base64.b64encode(zlib.compress(raw, 9)).decode()


def unpack_verify(blob):
    """-> {"inputs": [byte,...], "anchors": [[t,x,y,z,qx,qy,qz,qw,vx,vy,vz,st],...]}.

    ``None`` for anything this cannot read, which is the same answer it gives for
    a blob that is merely absent: a run with unreadable evidence is a run with no
    evidence, and the caller has one case to handle rather than two.
    """
    if not blob:
        return None
    try:
        obj = json.loads(zlib.decompress(base64.b64decode(blob)))
        pq, rq, vq, sq = obj.get("q", [A_POS_Q, A_ROT_Q, A_VEL_Q, A_STEER_Q])
        inputs = unpack_inputs(obj.get("i"))
        if inputs is None:
            return None
        d = obj.get("a") or []
        if len(d) % ANCHOR_STRIDE or len(d) // ANCHOR_STRIDE > MAX_ANCHORS:
            return None
        anchors = []
        for i in range(0, len(d), ANCHOR_STRIDE):
            anchors.append([float(d[i])] +
                           [d[i + k] / pq for k in (1, 2, 3)] +
                           [d[i + k] / rq for k in (4, 5, 6, 7)] +
                           [d[i + k] / vq for k in (8, 9, 10)] +
                           [d[i + 11] / sq])
        return {"inputs": inputs, "anchors": anchors}
    except Exception:
        return None


def medal_for(track, time_ms):
    """Best medal a time earns on a track, or None."""
    secs = time_ms / 1000.0
    best = None
    for name in MEDAL_ORDER:
        if secs <= track["medals"][name]:
            best = name
    return best


MEDAL_ORDER = ["bronze", "silver", "gold"]


def medal_rank(medal):
    return MEDAL_ORDER.index(medal) + 1 if medal in MEDAL_ORDER else 0


# How many frames the recorder is allowed to be out by. See `time_window`.
FRAME_SLACK = 1


def time_window(n_frames):
    """[lo, hi) - the times a replay of `n_frames` frames is allowed to claim.

    This used to be a **±25% band** on the frame count, and that width was the
    whole of a hole worth 3.5 to 6.9 seconds on every track in the pool. Nothing
    else pins the clock: the splits are checked against the replay's own gate
    crossings, but `time_ms` itself only had to be larger than the last split and
    somewhere inside that band - so an entirely honest lap, relabelled, was
    accepted several seconds faster than it was driven. Stack it on a ghost
    downloaded from `/api/ghost` and it was a world record for two HTTP requests.

    The band was never necessary, because the frame count is not approximately
    the duration - it *is* the duration. `Run._recordGhost` pushes a frame while
    ``_ghostN / GHOST_HZ <= t``, and `Run.update` sets `this.time` and records on
    the same frame that detects the finish, so there is no interpolation between
    them and no dependence on the browser's frame rate:

        n_frames == floor(time_ms / 1000 * GHOST_HZ) + 1

    exactly. Inverted, that is a window one frame wide - 66.7ms - which is the
    quantisation of the recorder and nothing more.

    Measured against the twelve tracks driven by `tests/autopilot.js` through the
    real shipped physics, ``len(frames) - time_ms / 1000 * GHOST_HZ`` lands
    between **0.12 and 0.88** - inside a window of [0, 1) every time, with no
    value near either edge. `FRAME_SLACK` widens it by a frame either way anyway,
    for a lap that `pending.js` has been holding in a browser since before the
    start-line fix changed where frame 0 sits.
    """
    return ((n_frames - 1 - FRAME_SLACK) / GHOST_HZ * 1000.0,
            (n_frames + FRAME_SLACK) / GHOST_HZ * 1000.0)


def validate(track, time_ms, splits, frames):
    """(ok, reason). ``frames`` is the unpacked ghost, or None."""
    if not isinstance(time_ms, int) or time_ms <= 0:
        return False, "bad time"
    if time_ms > 1000 * 60 * 60:
        return False, "run too long"

    # Checkpoints: all of them, in order, each before the finish.
    want = track["checkpoints"]
    if not isinstance(splits, list) or len(splits) != want:
        return False, "missed a checkpoint"
    last = 0
    for s in splits:
        if not isinstance(s, int) or s <= last or s >= time_ms:
            return False, "checkpoint times out of order"
        last = s

    if frames is None:
        return False, "no replay"
    if len(frames) < 2 or len(frames) > MAX_GHOST_FRAMES:
        return False, "replay length implausible"

    # The replay has to last exactly as long as the time claims it did.
    lo, hi = time_window(len(frames))
    if not (lo <= time_ms < hi):
        return False, "replay does not match the time"

    # And it has to be a drive, not a sequence of teleports - nor a lap driven
    # by a car with more engine in it than this one has.
    dt = 1.0 / GHOST_HZ
    speeds = []
    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        d = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2) ** 0.5
        v = d / dt
        if v > SPEED_CEIL:
            return False, "replay contains a teleport"
        speeds.append(v)
    # A chord across a corner understates the distance travelled and never
    # overstates it, so this median is a floor on the real one - the right
    # direction for a number that refuses somebody's lap.
    if speeds:
        speeds.sort()
        if speeds[len(speeds) // 2] > MEDIAN_SPEED_CEIL:
            return False, "replay is faster than the car"

    # It has to start at the start line and end at the finish.
    spawn = track["spawn"]["p"]
    f0 = frames[0]
    if ((f0[0] - spawn[0]) ** 2 + (f0[2] - spawn[2]) ** 2) ** 0.5 > T.CELL * 3:
        return False, "replay does not start on the line"

    # And - the part that used to be missing - it has to have driven the track:
    # through the gates, when the splits say, without leaving the course.
    return follows_the_track(track, time_ms, splits, frames)


# ---------------------------------------------------------------------------
# Does the replay actually drive the track?
# ---------------------------------------------------------------------------
#
# Everything above asks whether a replay is self-consistent. None of it ever
# looked at the *track*: `validate` checked that the splits array was a list of
# increasing integers and that frame 0 was near the spawn, and that was all. So a
# replay was free to be a straight line into the void at 49 u/s for the right
# number of frames, with three plausible-looking split numbers beside it, and it
# would be accepted and go on the board.
#
# That is the second hole, and the splits were the half of it that mattered: they
# are what the leaderboard's checkpoint comparison is drawn from, and nothing tied
# them to the replay they arrived with. They are now the *claim* and the frames
# are the *evidence*, and the two have to agree.
#
# These constants mirror `Course`/`Run` in static/js/course.js. They are not
# independent choices: if the game credits a gate on one rule and the server
# insists on another, the disagreement is an honest lap thrown away.

GATE_NEAR = 20.0        # Course.gateNear - how close before a gate is watched
GATE_SIDE_PAD = 2.5     # Run._withinGate - lateral slack past the kerb
GATE_FLOOR = -2.5       # Run._withinGate - how far under a gate still counts

# How far a frame may sit from the nearest point on the track's own ribbon.
# Deliberately loose: running wide onto the grass, a jump, and the long way round
# a hairpin are all ordinary driving, and this is here to catch a replay that
# leaves the course altogether rather than to police a racing line. Measured
# against the 82 honest laps on the board, the worst frame is **31.9** units off
# (Cloudbreak, which is mostly gaps), so this is a little under twice the
# furthest anybody has legitimately been.
CORRIDOR = 60.0

# How far a gate crossing may sit from the split that claims it.
#
# Nine frames either way, which this was, is not loose - it is **six times the
# widest disagreement an honest lap can produce**, and a window that wide is a
# window a fabricated split fits inside. Shifting every split down by the
# tolerance and claiming a finish a millisecond after the last one was worth
# seconds a lap; with `time_window` now pinning the clock to the frame count,
# this is the other half of the same arithmetic and it is worth tightening for
# the same reason.
#
# What an honest lap actually produces is the sum of three quantisations:
#
#   * the split is stamped `Math.round(this.time)` on the *render* frame that
#     detects the crossing, so it is up to one frame of the browser's own loop
#     late - 50ms at 20fps, and less on anything healthier;
#   * the crossing this is compared against is found on the ghost's 15Hz grid,
#     so it is placed to within 66.7ms;
#   * and both are rounded to the millisecond.
#
# That is about 120ms of honest worst case. Measured on the twelve tracks driven
# through the real physics by `tests/autopilot.js`, every checkpoint on every
# track lands between **0 and 59ms** - inside one ghost frame, and all of it on
# the same side, since the crossing is always found on or after the split that
# claims it. 250 is twice the theoretical worst case and four times the measured
# one, and it takes what a shifted split is worth from 599ms to 249ms.
SPLIT_TOL_MS = 250


def _gates_of(track):
    cps = sorted((g for g in track["gates"] if g["kind"] == "cp"),
                 key=lambda g: g["gi"])
    fin = next((g for g in track["gates"] if g["kind"] == "finish"), None)
    return cps, fin


def _side(gate, f):
    return ((f[0] - gate["p"][0]) * gate["f"][0] +
            (f[1] - gate["p"][1]) * gate["f"][1] +
            (f[2] - gate["p"][2]) * gate["f"][2])


def _within_gate(gate, f, ceil):
    """`Run._withinGate`, in Python. Same rule, same numbers."""
    lx = ((f[0] - gate["p"][0]) * gate["r"][0] +
          (f[2] - gate["p"][2]) * gate["r"][2])
    dy = f[1] - gate["p"][1]
    return abs(lx) <= gate["hw"] + GATE_SIDE_PAD and GATE_FLOOR < dy < ceil


def _crossings(gate, frames, ceil):
    """Frame indices where the replay passes through `gate`, front to back.

    The side is only tracked while the car is in the gate's mouth and within
    `GATE_NEAR` of its plane - the same restriction `Run.update` needs, and for
    the same reason: a gate's plane is infinite, so a car crossing it somewhere
    else on the track would flip the remembered side and the real pass later
    would produce no sign change at all.
    """
    out = []
    prev = None
    for i, f in enumerate(frames):
        s = _side(gate, f)
        if abs(s) > GATE_NEAR or not _within_gate(gate, f, ceil):
            prev = None
            continue
        if prev is not None and prev < 0 <= s:
            out.append(i)
        prev = s
    return out


def follows_the_track(track, time_ms, splits, frames):
    """(ok, reason). Did this replay drive *this* track, past its gates, on time?

    Three questions, and the replay has to answer all of them:

      * did it go through every checkpoint, in order, through the mouth of the
        gate rather than across the infinite plane it sits in;
      * did each of those crossings happen when the matching split says it did;
      * and did the whole thing stay anywhere near the road.
    """
    cps, fin = _gates_of(track)
    ceil = track.get("gate_ceil") or 5.0
    hz = GHOST_HZ

    # --- every checkpoint, in order, at the time it claims -------------------
    at = 0                      # no crossing may be earlier than the last one
    for n, gate in enumerate(cps):
        hits = [i for i in _crossings(gate, frames, ceil) if i >= at]
        if not hits:
            return False, "replay never passes checkpoint %d" % (n + 1)
        want = splits[n] / 1000.0 * hz
        near = min(hits, key=lambda i: abs(i - want))
        if abs(near - want) > SPLIT_TOL_MS / 1000.0 * hz:
            return False, "checkpoint %d is not where the replay is" % (n + 1)
        at = near

    # --- and it ends at the finish ------------------------------------------
    #
    # Asked as "ends at" rather than "crosses", because a ghost stops at the
    # flag: `_recordGhost` only runs while the run is `running` and crossing the
    # line is what ends it, so the last frame is always on the *approach* and
    # there is never a frame on the far side to make a sign change out of.
    # Requiring a crossing here rejected 76 of the 82 honest laps on the board.
    if fin is not None:
        last = frames[-1]
        if not _within_gate(fin, last, ceil) or abs(_side(fin, last)) > GATE_NEAR:
            return False, "the replay does not end at the finish"

    # --- and it stayed on the course ---------------------------------------
    line = track.get("line") or []
    if line:
        lim = CORRIDOR * CORRIDOR

        def nearest(f, lo, hi):
            best, bi = None, lo
            for j in range(lo, hi):
                p = line[j]["p"]
                d = ((f[0] - p[0]) ** 2 + (f[1] - p[1]) ** 2 + (f[2] - p[2]) ** 2)
                if best is None or d < best:
                    best, bi = d, j
            return best, bi

        # The car goes forward, so the nearest station is a few past the last
        # one and a narrow window finds it. This runs on the request path, and
        # Drive has one eventlet worker - every millisecond here is a millisecond
        # of every live race's sockets - so the window is small on purpose and a
        # full scan happens only when the cheap answer looks like a refusal.
        # Being *sure* is worth 50ms; being sure 300 times a lap is not.
        idx = 0
        for f in frames:
            best, bi = nearest(f, max(0, idx - 10), min(len(line), idx + 40))
            if best is None or best > lim:
                best, bi = nearest(f, 0, len(line))
                if best is None or best > lim:
                    return False, "replay leaves the course"
            idx = bi
    return True, ""


def clamp_distance(track, claimed):
    """Distance-driven is a client stat; keep it in the realm of the possible."""
    try:
        d = float(claimed)
    except (TypeError, ValueError):
        return 0.0
    import laptime
    return max(0.0, min(d, laptime.line_length(track) * 4.0))


# One run cannot sensibly be longer than this. The longest ideal lap in the pool is
# about 64s and the simulated driver's hard ceiling is 90s, so ten minutes is a very
# loose bound on somebody pottering about - which is the point: it is not a judgement
# about driving, it is a ceiling on what one POST can claim.
MAX_RUN_MS = 10 * 60 * 1000


def clamp_run_ms(claimed):
    """How long a run may claim to have lasted.

    `clamp_distance` has existed since the first version of `/api/run` because
    distance is a client number. Time was never clamped there, because it was
    checked a stronger way: `validate` compares it against the replay's own frame
    count, so a lap that lied about its duration was rejected outright.

    `/api/activity` has no replay to check against - it is the *unfinished* runs,
    which is exactly the driving nothing was keeping - so the number that the whole
    "minutes played" figure is made of would be the one field with no ceiling at
    all. Hence this: the weaker check that the weaker evidence allows.
    """
    try:
        ms = float(claimed)
    except (TypeError, ValueError):
        return 0.0
    if ms != ms or ms in (float("inf"), float("-inf")):   # NaN and infinities
        return 0.0
    return max(0.0, min(ms, float(MAX_RUN_MS)))
