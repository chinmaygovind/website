"""Turn the standing record on each track into a line the bots can drive.

`laptime.py` relaxes the centreline toward minimum curvature and stops at the
kerb, which is the right line to cut medal times from and **not** the line a
record is set on. Measured against the sixteen records actually on the board:

    track      record   gold    record/ideal
    rainbow    48.4s    58.6s      0.761
    bigred     56.6s    68.0s      0.765
    twist      18.3s    22.6s      0.744

Ten and eleven seconds inside gold. No amount of extra throttle on the relaxed
line finds that - driven flat out it saturates a second or two *outside* gold on
half the pool and simply falls off Rainbow Road. What the records have that the
relaxation cannot is the part of a lap nobody can derive from the geometry: which
kerb to stand on, how late to brake, and above all what to do in the air - Big
Red's record is airborne for **28%** of the lap and Mount Joy's for 22%.

So the fast line is not computed, it is **taken off somebody's lap**. This
fetches `/api/ghost/<slug>?who=wr` from a running site, differentiates the
replay into a speed at every point, and writes the pair into the track's own
folder as `hotlap.json`. `bot.js` pursues that path; `botsim` loads it.

Only the two quick levels use it. Easy and medium drive `laptime.py`'s relaxed
line, deliberately: a record's line crosses gaps that need the speed the record
carried, and a bronze-pace car sent down it lands in the scenery.

Re-run it when records fall, the way `shoot_tracks.py` is re-run when geometry
moves - a stale hot lap is not an error, just a bot driving last month's record.
`test_hotlaps.py` is what notices a missing or unusable one.

    python tools/hotlap.py                    # every track, from the live site
    python tools/hotlap.py sunrise gauntlet   # just these
    python tools/hotlap.py --site http://localhost:5005
    python tools/hotlap.py --dry-run          # report, write nothing
"""

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.dirname(HERE)
sys.path.insert(0, DRIVE)

import laptime                                             # noqa: E402
import runcheck                                            # noqa: E402
import tracks as tracks_mod                                # noqa: E402

LIVE = "https://drive.cgovind.com"

# Which cuts the bots are allowed to copy, per track. Absent means "all of them".
#
# **A judgement about the game rather than something to measure**, which is why
# it is a table a person edits. Most of the cuts in this pool are simply the
# quick way round - Twin Loop, Rainbow Road and Cloudbreak are each won by
# jumping across a loop, and those are worth learning, so a rival that does them
# is a rival worth racing. Two are not, and they want different treatment:
#
#   `board`  - walk down the board and use the fastest lap that does not do it.
#              Right for Gauntlet, where the trick *is* the lap: the record
#              rides the rail from the second checkpoint to the loop, and there
#              is no way to keep the rest of it and drop that.
#   `splice` - keep the record and replace only the offending stretch with the
#              ordinary way round, taken off the relaxed line. Right for Big
#              Red, whose record is worth copying nearly everywhere - it is
#              airborne for 28% of the lap over four jumps, three of which are
#              ordinary kickers - and whose one 202-unit loop skip is the only
#              part of it nobody would do in a race.
#
# `limit` is how much ribbon a single cut may skip before it counts. A size
# rather than a flag, so Big Red's 61, 65 and 68-unit jumps survive and only the
# 202 is taken out.
CUT_POLICY = {
    "gauntlet": {"mode": "board", "limit": 40.0},
    "bigred": {"mode": "splice", "limit": 120.0},
}

# How far down a board to look before giving up and taking the record anyway.
BOARD_DEPTH = 8

# The file each track folder gets. Named for what it is rather than for where it
# came from: a hot lap is a hot lap whether it was fetched off the live board or
# driven by hand and pasted in.
FILENAME = "hotlap.json"

# The car's flag byte, from physics.js. Only AIR is read here.
FLAG_AIR = 2

# How many frames either side the speed is averaged over. Positions are stored
# to the centimetre and the frames are ~3 units apart, so differentiating them
# is already good to about 0.15 u/s - this is not noise reduction so much as
# taking the corner of a single-frame kerb strike off a number the bot is going
# to try to hold.
SMOOTH = 2

# A flight this long or longer is a jump rather than a crest, and gets a speed
# floor on its run-up. Below it the car is skipping over a seam and arriving a
# little slow costs nothing.
JUMP_S = 0.45

# How far back along the path a jump's takeoff speed is enforced as a **floor**.
#
# This is the whole reason the quick bots can be given a pace multiplier at all.
# Four tracks in the pool are won by jumping a gap that misses out a large piece
# of the ribbon - Twin Loop's record clears 189 units of road in 1.13s, the
# Gauntlet's 198, Rainbow Road's two cuts 175 and 192, and Big Red has four - and
# every one of those launches at 47-49 u/s. Scale a lap like that down by the 7%
# that turns a record into a gold and the car arrives at the lip at 44, does not
# reach the other side, and the "hard" bot spends the race respawning.
#
# So the recorded speed at a takeoff is not a target the pace is allowed to scale.
# It is a floor over the last stretch of the approach, and the pace only applies
# to whatever is above it. 45 units is comfortably longer than any braking zone
# in the game (78 u/s^2 stops the car from full speed in 16), so a bot that has
# been going slower has room to be back on the power before the lip.
JUMP_RUNUP = 45.0


def fetch(site, slug, who="wr", timeout=30):
    """One replay off the board: the record, or a row by id."""
    url = "%s/api/ghost/%s?who=%s" % (site.rstrip("/"), slug, who)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def board(site, slug, timeout=30):
    """The board for one track, quickest first, replays only."""
    url = "%s/api/board/%s" % (site.rstrip("/"), slug)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        rows = json.load(r).get("rows") or []
    return [x for x in rows if x.get("has_ghost")]


def choose(site, slug, track, policy):
    """The fastest lap on this track the bots are allowed to copy.

    Walks the board from the record down until it finds one whose cuts are all
    inside `limit`. Returns `(ghost, data, why)`.

    With no limit the first row is taken immediately and this costs one extra
    request, which is the ordinary case for fourteen of the sixteen tracks.
    """
    limit = None if not policy or policy["mode"] != "board" else policy["limit"]
    rows = board(site, slug)[:BOARD_DEPTH]
    if not rows:
        return None, None, "no lap with a replay"
    skipped = []
    for row in rows:
        ghost = fetch(site, slug, who=str(row["id"]))
        if not ghost.get("ghost"):
            continue
        data = build(ghost, track)
        cuts = describe_cuts(data, track)
        worst = max([c["gained"] for c in cuts], default=0.0)
        if limit is None or worst <= limit:
            why = ("record" if row is rows[0] else
                   "board #%d; %s skipped for cutting %.0f units"
                   % (rows.index(row) + 1, "the record" if len(skipped) == 1
                      else "%d laps" % len(skipped), skipped[0]))
            return ghost, data, why
        skipped.append(worst)
    # Nothing on the board respects the limit. Take the record rather than
    # leaving the quick levels with no line at all - they fall back to the
    # relaxed one, which is slower than a lap with a trick in it is unfair.
    ghost = fetch(site, slug, who="wr")
    return ghost, (build(ghost, track) if ghost.get("ghost") else None), \
        "no lap on the board is inside the %.0f-unit limit; using the record" % limit


def speeds_from(frames, hz):
    """Speed at every frame, by central difference, lightly smoothed.

    Central rather than forward, or every speed is reported half a frame late
    and the bot brakes half a frame late with it - which at 48 u/s is a metre
    and a half of braking zone given away at every corner on the track.
    """
    n = len(frames)
    if n < 2:
        return [0.0] * n
    raw = []
    for i in range(n):
        a = frames[max(0, i - 1)]
        b = frames[min(n - 1, i + 1)]
        span = (min(n - 1, i + 1) - max(0, i - 1)) or 1
        raw.append(math.dist(a[:3], b[:3]) * hz / span)
    out = []
    for i in range(n):
        lo, hi = max(0, i - SMOOTH), min(n, i + SMOOTH + 1)
        out.append(sum(raw[lo:hi]) / (hi - lo))
    return out


def infer_air(p, hz):
    """Which frames were airborne, worked out from the trajectory itself.

    A ghost carries the car's flag byte, and `FLAG.AIR` in it is the exact
    answer - but **only laps recorded since that byte existed have one**.
    `pack_ghost` keeps older replays seven wide on purpose, and two of the laps
    this tool picks are old ones: the fastest lap on Big Red that does not cut
    the loop predates it, and Big Red is 28% airborne. Reading no flag as "never
    left the ground" put a speed floor on none of its jumps, which is the one
    thing the quick levels need there.

    So where there is no flag, ask the physics. A car in the air is the only
    thing in this game accelerating downward at exactly `GRAVITY`; on the ground
    the suspension and the road hold it, and the second difference of its height
    sits near zero. Positions are stored to the centimetre and the frames are
    1/15s apart, which leaves about 9 u/s^2 of quantisation noise in that second
    difference - well clear of the 30 being looked for.
    """
    n = len(p)
    out = [0] * n
    if n < 3:
        return out
    for i in range(1, n - 1):
        ay = (p[i + 1][1] - 2 * p[i][1] + p[i - 1][1]) * hz * hz
        if ay < -18.0:
            out[i] = 1
    # A single frame either side of a flight is the frame it left and the frame
    # it landed, and both read as grounded on a second difference that straddles
    # the transition. Close the runs up so a jump is one run rather than three.
    for i in range(1, n - 1):
        if not out[i] and out[i - 1] and out[i + 1]:
            out[i] = 1
    return out


def air_runs(air, hz):
    """Contiguous airborne stretches worth calling jumps, as (first, last) frames."""
    out, i, n = [], 0, len(air)
    while i < n:
        if not air[i]:
            i += 1
            continue
        j = i
        while j < n and air[j]:
            j += 1
        if (j - i) / hz >= JUMP_S:
            out.append((i, j - 1))
        i = j
    return out


def speed_floors(p, v, air, hz):
    """The minimum speed the bot must carry at each point, from the jumps.

    Zero nearly everywhere. On the `JUMP_RUNUP` units before each takeoff it is
    the speed the record itself left the ground at, so a bot running the same
    line at less than full pace still arrives at the lip able to reach the other
    side. See JUMP_RUNUP for why this exists at all.

    Taken from the last *grounded* frame rather than from the first airborne
    one: the first frame in the air is already past the lip and has had gravity
    on it, so it reads a shade slow, and a floor that is a shade slow is exactly
    the floor that does not clear the gap.
    """
    n = len(p)
    floors = [0.0] * n
    for (a, _b) in air_runs(air, hz):
        take = max(0, a - 1)
        want = v[take]
        if want <= 0:
            continue
        back = 0.0
        i = take
        while i >= 0 and back <= JUMP_RUNUP:
            if floors[i] < want:
                floors[i] = want
            if i == 0:
                break
            back += math.dist(p[i], p[i - 1])
            i -= 1
    return floors


def ribbon_walk(line, p):
    """Ribbon arc length under each path point, walking forward with a hint.

    Forward-biased on purpose. Half the pool runs beside itself somewhere - Spa
    has a pit straight parallel to the track, the Costco crosses its own aisles
    on a deck - and a global nearest-station search snaps to the wrong one and
    reports a 150-unit shortcut that is really a car driving past a piece of road
    it will reach a minute later. This is only used to *describe* the lap in the
    tool's output; nothing in the file depends on it.
    """
    total = [0.0]
    for i in range(1, len(line)):
        total.append(total[-1] + math.dist(line[i]["p"], line[i - 1]["p"]))
    out, hint = [], 0
    for q in p:
        best, bi = 1e18, hint
        for j in range(max(0, hint - 4), min(len(line), hint + 120)):
            e = line[j]["p"]
            d = (q[0] - e[0]) ** 2 + (q[1] - e[1]) ** 2 + (q[2] - e[2]) ** 2
            if d < best:
                best, bi = d, j
        hint = bi
        out.append(total[bi])
    return out


def station_arc(line):
    """Cumulative arc length along the ribbon, one per station."""
    out = [0.0]
    for i in range(1, len(line)):
        out.append(out[-1] + math.dist(line[i]["p"], line[i - 1]["p"]))
    return out


def splice_cuts(data, track, limit):
    """Replace any cut bigger than `limit` with the ordinary way round.

    Keeps the recorded lap everywhere else, which is the point: Big Red's record
    is worth copying over four jumps and a long descent, and is not worth
    copying over the one place it skips the loop.

    The replacement comes from `laptime.py`'s relaxed line - the same path the
    slow levels drive - over exactly the stretch of ribbon the cut missed out,
    at that line's own speeds. So the bot goes round at a sane cornering pace
    and rejoins the record on the far side.

    The path is purely geometric to `BotLine` (it builds its own arc length and
    reads a speed per point; nothing downstream cares that the frames were once
    evenly spaced in time), so splicing in points at a different spacing is
    free. What does have to be redone is everything derived: which frames are
    airborne, the jump floors, and the lap time - the recorded one describes a
    lap that is no longer this one.
    """
    cuts = [c for c in describe_cuts(data, track) if c["gained"] > limit]
    if not cuts:
        return data, []
    pts, speeds, _ = laptime.speed_profile(track)
    S = station_arc(track["line"])
    s_of = ribbon_walk(track["line"], data["p"])
    done = []
    # Back to front, so the indices of the earlier cuts are still valid.
    for c in sorted(cuts, key=lambda c: c["lo"], reverse=True):
        lo, hi = c["lo"], c["hi"]
        s0, s1 = s_of[lo], s_of[hi]
        i0 = min(range(len(S)), key=lambda i: abs(S[i] - s0))
        i1 = min(range(len(S)), key=lambda i: abs(S[i] - s1))
        if i1 <= i0:
            continue
        seg_p = [[round(v, 2) for v in p] for p in pts[i0:i1 + 1]]
        seg_v = [round(v, 2) for v in speeds[i0:i1 + 1]]
        data["p"][lo:hi + 1] = seg_p
        data["v"][lo:hi + 1] = seg_v
        data["air"][lo:hi + 1] = [0] * len(seg_p)
        done.append({"at": c["at"], "gained": c["gained"], "points": len(seg_p)})
    data["vmin"] = [round(v, 2) for v in
                    speed_floors(data["p"], data["v"], data["air"], data["hz"])]
    # The recorded time described a lap with the skip in it. What this is now is
    # that lap going round, so its time is the one its own speeds imply.
    total = 0.0
    for i in range(len(data["p"]) - 1):
        d = math.dist(data["p"][i], data["p"][i + 1])
        v = max(0.5, (data["v"][i] + data["v"][i + 1]) / 2)
        total += d / v
    data["time_ms"] = int(round(total * 1000))
    data["spliced"] = done
    return data, done


def describe_cuts(data, track):
    """The shortcuts in this lap, for the operator reading the tool's output.

    A cut is a stretch that gains far more road than the car actually travelled -
    the jumps across a loop that four of the records in this pool are won with.
    Reported and not stored: the bot inherits every one of them simply by driving
    the path, and the only thing it needs written down is the speed floor.
    """
    p = data["p"]
    s = ribbon_walk(track["line"], p)
    cuts = []
    for (a, b) in air_runs(data["air"], data["hz"]):
        lo, hi = max(0, a - 1), min(len(p) - 1, b + 1)
        gained = s[hi] - s[lo]
        flew = math.dist(p[lo], p[hi])
        if gained > flew * 1.35 and gained > 40:
            cuts.append({"at": lo / data["hz"], "air": (b - a + 1) / data["hz"],
                         "takeoff": data["v"][lo], "gained": gained,
                         "lo": lo, "hi": hi})
    return cuts


def build(ghost, track):
    """The hot lap as it is stored: positions, the speed carried at each, and air.

    `air` is kept because it changes what the driver is allowed to do rather
    than only how fast it goes. A car mid-flight has `AIR_STEER` of its yaw
    authority and no brakes at all, so a pursuit controller that keeps sawing at
    a target it cannot reach lands pointing the wrong way. `bot.js` reads this
    and holds the attitude instead, which is what the record did.
    """
    frames = ghost["ghost"]
    hz = ghost.get("hz") or runcheck.GHOST_HZ
    v = speeds_from(frames, hz)
    p = [[round(f[0], 2), round(f[1], 2), round(f[2], 2)] for f in frames]
    # The flag byte where the replay has one, the trajectory where it does not.
    if frames and len(frames[0]) > 7:
        air = [1 if int(f[7]) & FLAG_AIR else 0 for f in frames]
    else:
        air = infer_air(p, hz)
    return {
        # Where it came from, so a stale file can be recognised as one.
        "source": "record",
        "time_ms": ghost.get("time_ms"),
        "who": ghost.get("who"),
        "row": ghost.get("id"),
        "captured": date.today().isoformat(),
        # The track as it was when this was driven. A ribbon that has been
        # re-authored since is the one way a hot lap becomes actively wrong -
        # the path would cut through geometry that has moved - and comparing
        # this against the track's own number is how `test_hotlaps` says so.
        "ideal": track["ideal"],
        "hz": hz,
        "p": p,
        "v": [round(s, 2) for s in v],
        "air": air,
        # The one thing the pace multiplier is not allowed to scale. See
        # JUMP_RUNUP and `speed_floors`.
        "vmin": [round(s, 2) for s in speed_floors(p, v, air, hz)],
    }


def path_of(slug):
    return os.path.join(DRIVE, "tracks", slug, FILENAME)


def load(slug):
    """One track's hot lap, or None. The reader `botsim` uses."""
    try:
        with open(path_of(slug)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("slugs", nargs="*", help="tracks to do; default all of them")
    ap.add_argument("--site", default=LIVE, help="where the records live")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    slugs = args.slugs or [t["slug"] for t in tracks_mod.TRACKS]
    bad = 0
    for slug in slugs:
        track = tracks_mod.get(slug)
        if not track:
            print("%-10s no such track" % slug)
            bad += 1
            continue
        policy = CUT_POLICY.get(slug)
        try:
            ghost, data, why = choose(args.site, slug, track, policy)
        except (urllib.error.URLError, OSError, ValueError) as e:
            print("%-10s could not fetch: %s" % (slug, e))
            bad += 1
            continue
        if not ghost or not data:
            # Not a failure. A track nobody has set a stored lap on has no
            # record to learn from, and the quick bots fall back to the relaxed
            # line there - slower, but it gets round.
            print("%-10s no lap with a replay; skipped" % slug)
            continue
        if policy and policy["mode"] == "splice":
            data, done = splice_cuts(data, track, policy["limit"])
            for d in done:
                why = ("record, with the %.0f-unit skip at %.1fs replaced by the "
                       "way round" % (d["gained"], d["at"]))
        data["why"] = why
        secs = (data["time_ms"] or 0) / 1000.0
        cuts = describe_cuts(data, track)
        floored = sum(1 for x in data["vmin"] if x > 0)
        print("%-10s %7.3fs by %-16s %4d frames  %2.0f%% air  %2.0f%% floored  %s"
              % (slug, secs, data["who"], len(data["p"]),
                 100.0 * sum(data["air"]) / max(1, len(data["air"])),
                 100.0 * floored / max(1, len(data["vmin"])), why))
        for c in cuts:
            print("             cut at %5.1fs: %4.2fs of air off %.1f u/s, misses %.0f units of road"
                  % (c["at"], c["air"], c["takeoff"], c["gained"]))
        if args.dry_run:
            continue
        with open(path_of(slug), "w") as f:
            json.dump(data, f, separators=(",", ":"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
