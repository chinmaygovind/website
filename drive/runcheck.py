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

So faking a time is no longer "send a small number", it is "synthesise a
plausible 30-second replay", and the fake ghost is then public on the
leaderboard for anyone to race. That is the right amount of effort for a driving
game on a personal site. It is deliberately not a replay re-simulation.
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
# A hard ceiling on believable speed: the car's own top speed, plus what a long
# descent can add on top of it (the physics caps that at 1.7x), plus slack.
SPEED_CEIL = T.MAX_SPEED * 2.2


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

    # The replay has to last about as long as the time claims it did.
    expected = time_ms / 1000.0 * GHOST_HZ
    if not (expected * 0.75 - 3 <= len(frames) <= expected * 1.25 + 3):
        return False, "replay does not match the time"

    # And it has to be a drive, not a sequence of teleports.
    dt = 1.0 / GHOST_HZ
    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        d = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2) ** 0.5
        if d / dt > SPEED_CEIL:
            return False, "replay contains a teleport"

    # It has to start at the start line and end at the finish.
    spawn = track["spawn"]["p"]
    f0 = frames[0]
    if ((f0[0] - spawn[0]) ** 2 + (f0[2] - spawn[2]) ** 2) ** 0.5 > T.CELL * 3:
        return False, "replay does not start on the line"
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
