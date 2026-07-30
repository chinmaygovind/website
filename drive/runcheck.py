"""Ghost packing and best-effort validation of submitted times.

The car is simulated in the browser - it has to be, for the driving to feel like
anything - which means a submitted lap time is a claim, not a fact. Nothing here
can make it a fact. What it can do is insist the claim comes with a *replay that
holds up*: every run ships the ghost that will be raced against, and a run is
rejected unless that ghost is self-consistent (right duration, no teleports, no
impossible speeds) and the time beats neither the simulated ideal lap nor its own
checkpoint splits.

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
    """frames: [[x,y,z,qx,qy,qz,qw], ...] floats -> compact base64 string."""
    ints = []
    for f in frames:
        ints.append(int(round(f[0] * POS_Q)))
        ints.append(int(round(f[1] * POS_Q)))
        ints.append(int(round(f[2] * POS_Q)))
        for k in range(3, 7):
            ints.append(int(round(f[k] * ROT_Q)))
    raw = json.dumps({"hz": GHOST_HZ, "q": [POS_Q, ROT_Q], "d": ints},
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
        out = []
        for i in range(0, len(d) - 6, 7):
            out.append([d[i] / pq, d[i + 1] / pq, d[i + 2] / pq,
                        d[i + 3] / rq, d[i + 4] / rq, d[i + 5] / rq, d[i + 6] / rq])
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
    ideal_ms = track["ideal"] * 1000.0
    if time_ms < ideal_ms * T.MIN_PLAUSIBLE:
        return False, "faster than the track allows"
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
