"""Drive: is this car doing something the car can do?

The anti-cheat a **room** gets. It is a different question from the two that
already exist, and the difference is worth stating before any of the numbers:

  * `runcheck.validate` asks whether a submitted replay is self-consistent.
    It has a whole lap in front of it, sent in one POST, and all the time in
    the world to look at it.
  * `verify.py` re-drives that lap through the game's own `Car.step` and asks
    whether *this car* drove it. It costs 0.5-6s of CPU in a subprocess and it
    needs the input stream, which only a solo lap carries.
  * This module asks the much smaller question that a **live** 30Hz stream of
    client-authoritative poses allows: could the car have got from where it
    said it was to where it now says it is, and did the whole race stay
    anywhere near the road.

It cannot see a 2% richer engine - nothing without the input stream can, and a
race deliberately does not carry one. What it ends is the class of cheat that
actually ruins a room: the car that teleports to the line, the car doing three
times `MAX_SPEED` in front of five people who came to race it, and the win that
was claimed without driving at all.

**Why a room needs its own module rather than a stricter `on_pose`.** A race is
not a leaderboard. Nothing set in a room reaches the board - no time, no medal,
no ghost - so the stake here is ELO, the win and podium tallies, the badges over
them, and the afternoon of everybody else in the room. That changes which
mistake is the expensive one: refusing an honest lap costs a record, but
*penalising an honest driver* costs them a race they were in the middle of. So
every rule in here is built to be wrong in the harmless direction - a car that
fails a check has its pose dropped and keeps racing, and only a car that fails
them steadily loses its rating.

## The bucket, which is the whole reason this works at all

The obvious rule - "the step between two poses may not exceed `SPEED_CEIL` times
the gap between them" - does not survive contact with a network. `dt` here is
measured on *arrival*, not on send: two poses sent 33ms apart routinely arrive
5ms apart behind a bit of jitter or a Nagle-ish coalescing, and that honest pair
reads as a car doing six times the speed limit. Written that way the check would
spend its life accusing anybody on hotel wifi.

So distance is spent from a **budget** instead. Every pose adds `SPEED_CEIL *
dt` to an allowance and the step's length is taken out of it; the allowance is
capped at `BUCKET_MAX_S` seconds' worth. Jitter cancels, because it is jitter -
the arrival times average out to the send times over any window longer than the
jitter itself - while a car genuinely travelling faster than the car can travel
drains the bucket and keeps draining it. The cap is what stops the other
direction: without it, a car could sit still for ten seconds banking allowance
and spend it all on one jump to the finish line.

The bucket is therefore a bound on **average speed over the last half second**,
which is exactly the bound the physics justifies and exactly the one arrival
jitter cannot fake.
"""

import runcheck
import tuning as T


# The flag byte's bits, copied from `static/js/physics.js`, which is the source
# of truth for them (`export const FLAG`). Only RESPAWN is read here; it is
# copied rather than imported because Python cannot read the module and a
# three-bit constant is not worth a build step. `test_flag_bits_match_the_js`
# reads the .js and pins them together.
FLAG_DRIFT = 1
FLAG_AIR = 2
FLAG_RESPAWN = 4
FLAG_BRAKE = 8
FLAG_SLIP = 16


# How many seconds of travel the budget may hold. Half a second: long enough
# that any plausible burst of arrival jitter cancels inside it, short enough
# that what it buys - about 44 units at `SPEED_CEIL` - is a car length or three
# rather than a shortcut.
BUCKET_MAX_S = 0.5

# A gap longer than this and the check simply has no opinion. The car has not
# been heard from for most of a second, so the server has been redrawing a stale
# pose for everybody and whatever arrives next is a resynchronisation rather
# than a measurement. Refilled to full and waved through: a rule that fires on a
# reconnect is a rule that punishes a bad connection.
BUCKET_GAP_S = 1.5

# Where a respawn may put you.
#
# `FLAG.RESPAWN` cannot simply buy a car a free teleport, because then setting
# the flag *is* the cheat - it is one bit in a payload the client already
# writes. What makes it checkable is that a respawn is not a jump to anywhere:
# `Run.update` keeps the car's respawn target pinned to the last gate it
# reached, so a legal one lands on a gate the server can name. This is how far
# from that gate's centre the car may come back, and it is loose on purpose -
# the gate is a plane across the ribbon and the spawn is offset back along it.
RESPAWN_NEAR = 45.0

# How far ahead of the server's own projection a client's `prog` may claim to
# be. The standings are ordered by `prog`, so an unbounded one is first place
# for free. The server re-derives it, but only every `PROG_SAMPLE_MS`, so the
# client is legitimately ahead by up to one sample's worth of travel - this is
# that, with room over it, since being roughly right about running order costs
# nothing and being strict about it would shuffle the standings on a hiccup.
PROG_LEAD = T.MAX_SPEED * 0.5

# How often a car's position is projected back onto the ribbon. The projection
# is a windowed walk (`runcheck.nearest_station`) and cheap with a warm hint,
# but Drive is one eventlet worker and this would otherwise run 30 times a
# second per car - every millisecond of it is a millisecond of every other live
# race's sockets. At 5Hz a car at `MAX_SPEED` moves 10 units between samples,
# which is nothing against the tolerances anything here is compared with.
PROG_SAMPLE_MS = 200

# How far off the ribbon a *live* pose may sit before it counts against the car.
# Deliberately wider than `runcheck.CORRIDOR`: this fires during a race, where
# the cost of being wrong is somebody's afternoon rather than a rejected POST,
# and the thorough version of this question is asked once at the flag by
# `scan_race` where being sure is affordable.
LIVE_CORRIDOR = runcheck.CORRIDOR * 1.5

# How many strikes a car may take before its result stops being rated.
#
# One is far too few - a genuine network event can produce a short burst of
# them, and the whole design of this module is that a single false positive
# costs nothing. A cheat, on the other hand, does not produce twelve strikes and
# then stop: a raised speed drains the bucket on every pose for as long as it is
# raised, so a real one is hundreds. There is a wide, empty gap between the two
# and this sits in it.
STRIKE_LIMIT = 12


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def finite(vals):
    """Are these all real numbers?

    Worth its own function because JSON has `NaN` and `Infinity` and Python's
    `json` parses both by default, so `float(x)` is not the guard it looks like.
    A pose is fanned straight back out to everybody else in the room, so a NaN
    here is a rival's car at coordinates that are not numbers in five other
    browsers - which is the reason `_sane_frames` exists for the pole ghost, and
    the live stream had no equivalent.
    """
    for v in vals:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        if v != v or v in (float("inf"), float("-inf")):
            return False
    return True


def respawn_points(track):
    """Where a respawn can put a car: the grid, and every checkpoint's centre.

    Each carries the distance along the ribbon at which it sits, because "have
    you been past this one yet" is a question about progress and not about
    ordering. A gate's `si` is its own station on the line, so the arc length is
    already known and nothing has to be projected to find it.
    """
    key = track.get("slug") or id(track)
    pts = _RESPAWN.get(key)
    if pts is None:
        gates = sorted((g for g in (track.get("gates") or [])
                        if g.get("kind") == "cp" and g.get("p")),
                       key=lambda g: g.get("gi", 0))
        spawn = (track.get("spawn") or {}).get("p")
        pts = ([(spawn, 0.0)] if spawn else []) + \
              [(g["p"], station_arc(track, g.get("si", 0))) for g in gates]
        _RESPAWN[key] = pts
    return pts


def respawn_is_plausible(track, p, prog):
    """Did this jump land somewhere a respawn could have put it?

    Only somewhere the car has already *got to*, so the flag cannot be used to
    skip forward - which it could if this took the client's word for how far
    round it was. `prog` is the server's own projection (`Watcher.prog`), so
    reaching a gate to be allowed to respawn at it means having driven there.

    `PROG_LEAD` of slack, because that projection is sampled at
    `PROG_SAMPLE_MS` and the honest case is tight: you cross a checkpoint and
    fall off a moment later, so the gate can be a few metres further along the
    ribbon than the last sample saw you.
    """
    pts = respawn_points(track)
    if not pts:
        return True             # nothing to check against: no opinion
    for pt, arc in pts:
        if arc <= prog + PROG_LEAD and _dist(p, pt) <= RESPAWN_NEAR:
            return True
    return False


def clamp_cp(claimed):
    """The car's own checkpoint counter, kept an integer and kept sane.

    Nothing on the server decides anything from this - it is fanned out so a
    rival's HUD knows where that car is up to, and the respawn check that used
    to read it now asks `Watcher.prog` instead, which is the server's own
    measurement rather than the client's claim. So it is bounded rather than
    policed: rate-limiting it would have made a car whose poses were dropped
    crawl its way back up, and a lagging counter can only make a *legal*
    respawn look illegal, which is the mistake this module is built not to make.
    """
    try:
        want = int(claimed)
    except (TypeError, ValueError):
        return 0
    return max(0, min(want, 999))


class Watcher:
    """The rolling per-car state the live checks need. One per car per room.

    Kept off the car dict deliberately. That dict is packed into `_snapshot`
    thirty times a second and read by `_store_replay`; a watcher is bookkeeping
    that nothing outside this module has any business seeing, and putting it
    there would mean every reader of a car learning to skip it.
    """

    def __init__(self):
        self.bucket = BUCKET_MAX_S * runcheck.SPEED_CEIL
        self.hint = 0            # last ribbon station, so the walk stays local
        self.prog = 0.0          # what the server thinks this car has covered
        self.next_prog_ms = 0
        self.strikes = 0
        self.reasons = {}        # reason -> how many times, for the record

    def reset(self):
        """A new race, or a car put back on the grid. Forget everything.

        The grid is a teleport by any measure this module has, and so is the
        respawn every car does at the lights, so carrying a bucket across one
        would open every race with a strike for everybody.
        """
        self.__init__()

    def strike(self, why):
        self.strikes += 1
        self.reasons[why] = self.reasons.get(why, 0) + 1
        return why

    @property
    def flagged(self):
        return self.strikes >= STRIKE_LIMIT


def check_pose(w, track, prev_p, p, dt_ms, flags):
    """The live check, run on every pose. Returns a reason, or None to accept.

    `prev_p` is where this car last credibly was - the pose the server kept, not
    the one it may have just refused, or a refused jump would set the baseline
    for the next one and a cheat would only have to be refused once.
    """
    dt = max(0.0, dt_ms / 1000.0)
    if dt > BUCKET_GAP_S or prev_p is None:
        w.bucket = BUCKET_MAX_S * runcheck.SPEED_CEIL
        return None
    w.bucket = min(BUCKET_MAX_S * runcheck.SPEED_CEIL,
                   w.bucket + runcheck.SPEED_CEIL * dt)
    step = _dist(prev_p, p)
    if step <= w.bucket:
        w.bucket -= step
        return None
    # Over budget. The one honest way that happens is a respawn, which really is
    # a jump - so it is allowed, but only to somewhere a respawn goes, and the
    # bucket is refilled rather than left in debt for the corner afterwards.
    if (flags & FLAG_RESPAWN) and track and respawn_is_plausible(track, p, w.prog):
        w.bucket = BUCKET_MAX_S * runcheck.SPEED_CEIL
        return None
    w.bucket = 0.0
    return w.strike("moved %.0f units in %.0fms" % (step, dt_ms))


def sample_progress(w, track, p, now_ms):
    """Project the car back onto the ribbon, at most every `PROG_SAMPLE_MS`.

    Two answers come out of the one walk, which is why they share a function:
    how far round the car actually is (`w.prog`, which is what a finish claim is
    measured against instead of the client's own number) and whether it is
    anywhere near the road at all. Returns a reason, or None.

    `w.prog` only ever goes up. It is progress, and the alternative - letting it
    fall when a car spins or reverses - would mean a car that crossed the line
    having its finish refused because it rolled backwards over it.
    """
    if not track or now_ms < w.next_prog_ms:
        return None
    w.next_prog_ms = now_ms + PROG_SAMPLE_MS
    best, w.hint = runcheck.nearest_station(track, p, w.hint)
    if best is None:
        return None
    if best > LIVE_CORRIDOR * LIVE_CORRIDOR:
        return w.strike("%.0f units off the course" % (best ** 0.5))
    w.prog = max(w.prog, station_arc(track, w.hint))
    return None


# Both keyed on the track's slug and built once. The dicts in `tracks` are
# module-level and shared by every request, so there is exactly one line per
# slug for the life of the process and nothing here can go stale.
_ARC = {}
_RESPAWN = {}


def station_arc(track, i):
    """Distance along the ribbon to station `i`.

    A prefix sum, built once per track and cached: `laptime.line_length` walks
    the whole line to get the total, and this is the same walk kept.
    """
    key = track.get("slug") or id(track)
    arc = _ARC.get(key)
    if arc is None:
        line = track.get("line") or []
        arc = [0.0] * len(line)
        for j in range(1, len(line)):
            arc[j] = arc[j - 1] + _dist(line[j - 1]["p"], line[j]["p"])
        _ARC[key] = arc
    if not arc:
        return 0.0
    return arc[max(0, min(int(i), len(arc) - 1))]


def scan_race(track, frames, hz):
    """The thorough pass, over one car's recorded race. Returns a list of reasons.

    This runs once, at the flag, over the trace **the server sampled itself** -
    `_record_race` writes one frame per car per `1/REPLAY_HZ` off the server's
    own clock, so unlike the live checks there is no arrival jitter in it at all
    and the timing is not a client's opinion. That is what makes the median
    affordable here and impossible up there.

    Two questions the per-pose bucket cannot ask:

      * **the median frame-to-frame speed**, which is the check a cheat cannot
        sit underneath. A single-frame ceiling is dodged by staying just below
        it; a lap's median is not, because no honest car spends half a race
        over `MEDIAN_SPEED_CEIL` - a long descent lifts one over `MAX_SPEED` for
        a few seconds and nothing in the physics holds it there. The reasoning
        and the measurement behind that number are in `runcheck`, where it was
        set for the same job on a solo lap.
      * **the corridor**, over every frame rather than every fifth one, at
        `runcheck.CORRIDOR` rather than the wider live figure.

    A respawn frame is skipped rather than counted, the same exception the live
    check makes, and for the same reason: it is a real jump. Here it is cheaper
    to spot, because the flag byte is recorded with the pose.
    """
    out = []
    if not frames or len(frames) < 2 or not hz:
        return out
    dt = 1.0 / hz
    speeds = []
    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        if (len(b) > 7 and (int(b[7]) & FLAG_RESPAWN)) or \
           (len(a) > 7 and (int(a[7]) & FLAG_RESPAWN)):
            continue
        speeds.append(_dist(a, b) / dt)
    if speeds:
        speeds.sort()
        median = speeds[len(speeds) // 2]
        if median > runcheck.MEDIAN_SPEED_CEIL:
            out.append("median speed %.0f over a whole race" % median)
        if speeds[-1] > runcheck.SPEED_CEIL:
            out.append("touched %.0f units/s" % speeds[-1])
    if track and runcheck.leaves_course(track, [f for f in frames
                                                if not (len(f) > 7 and int(f[7]) & FLAG_RESPAWN)]):
        out.append("left the course")
    return out
