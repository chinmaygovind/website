"""What a bot's skill level means, and where the line it drives comes from.

`bot.js` is mechanism - it can follow a line, brake for what is coming, land a
jump and lean on somebody. None of it knows what "hard" is. That is here,
because this is also where a level is *measured*: `tools/calibrate_bots.py`
drives each level round each track and solves for the pace that lands on the
time the level is supposed to be worth, and the answers live in
`bots_pace.json` beside this file.

The four levels
---------------
Two things separate them and the first matters far more than the second.

**Which line they drive.** Easy and medium follow `laptime.py`'s relaxed
centreline: the minimum-curvature line through the road, which is what the medal
times are cut from and which never leaves the tarmac. Hard and max follow the
**record holder's actual lap**, read off the board by `tools/hotlap.py` and
stored in the track's own folder. That is where the shortcuts are - four tracks
in this pool are won by jumping clean across a loop, and no relaxation of a
centreline will ever find that, because the line it is relaxing goes round.

**How hard they try.** A pace multiplier on the reference speed, plus how much
they wander, how often they get something wrong, whether they will use the
handbrake to rotate a car that is not going to make the corner, and how long
they take to react to the lights.

What each is worth
------------------
Set against the times that are actually on the board rather than against the
medals alone, because the medals turned out to be the wrong yardstick: every
record on the site is between 0.74 and 0.89 of `ideal`, and gold is 0.92 - so a
"hard" bot pinned to gold would be beaten by anybody who has learned the track,
which is the opposite of hard.

    easy    bronze
    medium  silver
    hard    most of the way from gold to the record  (see HARD_MIX)
    max     the record

`max` is aimed at the record and not at some multiple of it on purpose: the
record is a lap a person actually drove on this exact geometry with this exact
car, so it is the one target that is known to be possible. Where the driver
cannot reach it, it drives flat out and the calibration reports the gap rather
than inventing a number.
"""

import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

import laptime                                            # noqa: E402
import tracks as tracks_mod                               # noqa: E402

# The file `tools/hotlap.py` writes into each track's folder. Read here rather
# than by importing that tool: `tools/` is dev scripts, the app must not depend
# on one, and this end of it is four lines.
HOTLAP_FILE = "hotlap.json"

LEVELS = ("easy", "medium", "hard", "max")
DEFAULT_LEVEL = "medium"

# The levels a room may actually pick. All four, and here is what each is worth,
# measured rather than intended - because two of them do not hit their targets.
#
# Easy and medium were exact - they drive the relaxed line and landed within
# ±0.14s of bronze and silver on all sixteen tracks - and **that measurement is
# stale, because the medals moved and the table did not.** `bots_pace.json` was
# solved before `tools/set_medals.py` re-cut every track's medals from its real
# board, which is what bronze and silver *are* to these two levels. Nothing
# re-solved for the new ones. Measured Aug 2026 with `--report`: easy comes in
# **+1.6s to +13.0s over bronze** and medium +0.8s to +10.8s over silver on the
# sixteen tracks calibrated before that change, and is on target only on Tokyo
# Drift and Shroom Street, which have been re-run since. A full
# `tools/calibrate_bots.py` is the fix; the run is ~20 minutes.
#
# **Shroom Street is also the one place a slow level drives the recorded line**,
# and that is a line rather than a pace: the relaxed line cannot cross its gorge
# at any pace. See `line_for`.
#
# Hard and max are aimed at gold+`HARD_MIX`·(record-gold) and at the record, and
# neither quite gets there, so on the five tracks whose recorded line still
# cannot be driven (`bigred`, `heights`, `pillars`, `twist`, `tokyo`) they
# saturate at the same lap and `enforce_order` gives max hard's settings. Only a
# *reachable* target produces an exactly-placed level, which is why easy and
# medium were to the tenth and these two are not.
#
# What they are worth, measured over the whole pool: **max averages 5.6% under
# gold and beats it on fifteen of the sixteen; hard averages 2.7% under and
# beats it on thirteen.** Max is 5.2% off the records, and on four tracks it is
# within a second of one - Mount Joy 61.52 against 61.24, Spa 60.70 against
# 60.14, Rainbow Road 49.00 against 48.44, Sunrise 16.50 against 16.27.
#
# **These numbers doubled overnight and nothing about the levels changed** -
# `TUNE.steer` went from 2.2 to 6.0. Before that max was 0.6% under gold and
# 11.5% off the records, and it read as a competence ceiling that only a better
# driver could lift. It was a bad constant. See `docs/bots.md`.
#
# They are offered anyway, because a level you cannot select cannot be raced or
# judged, and a field of eight with a spread of pace is the thing this feature
# was asked for. The way to make them genuinely hard is to make the *driver*
# better - see the pace-ceiling section of `docs/bots.md` - not to move a number
# in here.
OFFERED = LEVELS

# How the levels read in the room, and to the person choosing one.
LABEL = {"easy": "Easy", "medium": "Medium", "hard": "Hard", "max": "Max"}

# Where "hard" sits between a gold lap and the record. **This is the one dial
# for how hard the game is**, so it is a named constant rather than a number in
# a table: 0 puts hard on gold, which most people who have learned a track
# already beat, and 1 puts it on the record and leaves nothing between it and
# max. 0.55 is a lap quicker than gold by more than the gold-to-silver step.
HARD_MIX = 0.55

# The shape of a level. `pace` here is the fallback used for a track that has
# never been calibrated - a brand new folder, or a pool somebody has just
# retuned the car under - and is deliberately conservative, because the failure
# it guards against is a bot that cannot get round at all.
#
# `paceMax` is the ceiling the calibrator may raise a level to, and the two
# quick levels have different ones **so that they stay different levels**. Both
# are aimed at times the driver cannot quite reach - max at the record itself -
# so without separate ceilings the search simply pins both at the top and hard
# and max come out identical on every track, which is two levels pretending to
# be four. Capping hard lower costs it its target on the handful of tracks where
# it could have hit it, and buys the thing a player can actually see: max is
# always the quickest car in the room.
PROFILES = {
    "easy": {
        "line": "relaxed", "pace": 0.80, "brakePlan": 0.70,
        "wander": 1.15, "paceNoise": 0.055, "lapse": 0.55,
        "drift": False, "race": 0.0, "reaction": 0.45,
    },
    "medium": {
        "line": "relaxed", "pace": 0.90, "brakePlan": 0.80,
        "wander": 0.70, "paceNoise": 0.035, "lapse": 0.30,
        "drift": False, "race": 0.35, "reaction": 0.32,
    },
    "hard": {
        "line": "hotlap", "pace": 0.93, "brakePlan": 0.90, "paceMax": 0.95,
        "wander": 0.30, "paceNoise": 0.015, "lapse": 0.10,
        "drift": True, "race": 0.8, "reaction": 0.22,
    },
    "max": {
        "line": "hotlap", "pace": 1.0, "brakePlan": 0.96, "paceMax": 1.02,
        "wander": 0.10, "paceNoise": 0.005, "lapse": 0.02,
        "drift": True, "race": 1.0, "reaction": 0.14,
    },
}

PACE_FILE = os.path.join(HERE, "bots_pace.json")
NAMES_FILE = os.path.join(HERE, "bot_names.txt")

_pace = None
_relaxed = {}
_names = None
_hot = {}


def hotlap(slug):
    """The recorded fast lap in this track's folder, or None.

    Cached including the misses, so a pool where half the tracks have no record
    does not stat the filesystem once per bot per race.
    """
    if slug not in _hot:
        try:
            with open(os.path.join(HERE, "tracks", slug, HOTLAP_FILE)) as f:
                _hot[slug] = json.load(f)
        except (OSError, ValueError):
            _hot[slug] = None
    return _hot[slug]


def paces():
    """What the calibrator measured, `{slug: {level: {...}}}`, or `{}`.

    Two things per entry: the `pace` that put this level on its target time, and
    the `line` it managed it on.

    **The line is in here because it is a measurement, not a policy.** A level
    asks for the recorded fast lap, and on some tracks the driver cannot yet
    hold it - it goes off at a cut and spends the race respawning, which is far
    worse than being a second slow. So `tools/calibrate_bots.py` drives it, and
    where the quick line does not get round it writes `relaxed` here and the bot
    drives the safe one instead. Re-running the calibrator after the driver
    improves is what takes the fallback away again.
    """
    global _pace
    if _pace is None:
        try:
            with open(PACE_FILE) as f:
                _pace = json.load(f)
        except (OSError, ValueError):
            _pace = {}
    return _pace


def setting(slug, level):
    """The calibrated entry for one level on one track, or `{}`."""
    got = paces().get(slug, {}).get(level)
    if isinstance(got, dict):
        return got
    if isinstance(got, (int, float)):
        return {"pace": got}          # an older table, which was a bare pace
    return {}


def target_ms(slug, level):
    """What this level is supposed to be worth on this track, in milliseconds.

    `None` where there is nothing to aim at - a level whose target is the record
    on a track with no record yet. The calibrator skips those and the bot keeps
    its fallback pace.
    """
    track = tracks_mod.get(slug)
    if not track:
        return None
    medals = track["medals"]
    if level == "easy":
        return int(medals["bronze"] * 1000)
    if level == "medium":
        return int(medals["silver"] * 1000)
    hot = hotlap(slug)
    record = (hot or {}).get("time_ms")
    gold = int(medals["gold"] * 1000)
    if not record:
        # No record to aim at. Gold is the only honest target left, and the
        # difference between hard and max collapses - which is right: without a
        # recorded lap neither of them has a fast line to drive either.
        return gold
    if level == "hard":
        return int(gold + (record - gold) * HARD_MIX)
    return int(record)


# A flight this long or longer is a jump rather than a crest, and its run-up
# gets a speed floor. Below it the car is skipping over a seam and arriving a
# little slow costs nothing.
JUMP_S = 0.45

# How far back along a line a jump's takeoff speed is enforced as a floor.
#
# **This is what makes a pace multiplier safe on a track that flies.** A level
# is a fraction of a reference lap's speed, and applying that fraction to the
# approach to a gap means arriving at the lip too slow to reach the other side -
# so the bot drops into the valley, respawns, and does it again. Measured: Mount
# Joy launches off its valley floor, and easy and medium spent fourteen
# respawns a lap there before this existed.
#
# 45 units is longer than any braking zone in the game (78 u/s^2 stops the car
# from full speed in 16), so a bot that has been going slower has room to be
# back on the power before the lip.
JUMP_RUNUP = 45.0


def air_runs(air, hz):
    """Contiguous airborne stretches worth calling jumps, as (first, last)."""
    out, i, n = [], 0, len(air)
    while i < n:
        if not air[i]:
            i += 1
            continue
        j = i
        while j < n and air[j]:
            j += 1
        if (j - i) / float(hz) >= JUMP_S:
            out.append((i, j - 1))
        i = j
    return out


def speed_floors(p, v, air, hz):
    """The minimum speed a bot must carry at each point on a line.

    Zero nearly everywhere; on the run-up to each jump it is the speed the
    reference lap left the ground at. See JUMP_RUNUP.

    Taken from the last *grounded* frame rather than the first airborne one: the
    first frame in the air is already past the lip and has had gravity on it, so
    it reads a shade slow - and a floor that is a shade slow is exactly the one
    that does not clear the gap.

    Lives here rather than in `tools/hotlap.py`, where it started, because it is
    a property of a *line* and both lines need it - the recorded one and
    `laptime.py`'s relaxed one, whose ribbon flies on four tracks in this pool.
    """
    n = len(p)
    floors = [0.0] * n
    for (a, _b) in air_runs(air, hz):
        take = max(0, a - 1)
        want = v[take]
        if want <= 0:
            continue
        back, i = 0.0, take
        while i >= 0 and back <= JUMP_RUNUP:
            if floors[i] < want:
                floors[i] = want
            if i == 0:
                break
            q, r = p[i], p[i - 1]
            back += math.dist(q, r)
            i -= 1
    return floors


def relaxed_line(slug):
    """`laptime.py`'s racing line and speed profile, in the shape `bot.js` wants.

    Cached: it is a 320-iteration relaxation over a thousand stations and the
    answer only changes when the track does.
    """
    if slug not in _relaxed:
        track = tracks_mod.get(slug)
        pts, speeds, _ = laptime.speed_profile(track)
        _relaxed[slug] = {
            "p": [[round(v, 3) for v in p] for p in pts],
            "v": [round(v, 3) for v in speeds],
            # The ribbon's own air stations, so this line says the same thing
            # about itself that a recorded one does. Without it the driver's
            # "am I under the road" check fires at every jump on a track whose
            # *ribbon* flies - Mount Joy launches off a valley floor - because
            # the point it is nearest to is a point in mid-air.
            "air": [1 if e.get("air") else 0 for e in track["line"]],
            "closed": bool(track.get("closed")),
        }
        # And the same jump floors a recorded lap carries. The ribbon's own
        # stations are ~3.5 units apart rather than a frame apart, so the
        # nominal rate here is only used to decide what counts as a jump.
        got = _relaxed[slug]
        air_hz = 4.0
        got["vmin"] = [round(x, 3) for x in
                       speed_floors(got["p"], got["v"], got["air"], air_hz)]
    return _relaxed[slug]


def line_for(slug, level, force=None):
    """The path this level drives here, and which of the two it turned out to be.

    Returns `(line, source)`. Three things can send a quick level down the safe
    line instead of the recorded one, and all three are the same answer to the
    same question - is there a fast line here this bot can actually drive:

      * the track has no recorded lap at all;
      * the calibrator drove it and could not get round (`setting`'s `line`);
      * the caller said so, which is the calibrator itself trying the other one.

    Slower, and it gets round, which is the only outcome that matters: a bot
    that spends a race falling off a jump it cannot make is worse to race
    against than one that is simply not as quick.

    **The table wins over the profile, and that runs the other way too.** A slow
    level asks for the relaxed line, and on Shroom Street it cannot be driven at
    any pace - the gorge is crossed by hopping mushroom caps at 52-55 u/s and
    the relaxed line carries ~50 through there, so easy and medium dropped into
    the canyon at the third cap. The calibrator measures that and writes
    `hotlap` for them, and this is what honours it. See `solve` in
    `tools/calibrate_bots.py`.
    """
    want = force or setting(slug, level).get("line") or PROFILES[level]["line"]
    if want == "hotlap":
        hot = hotlap(slug)
        if hot and hot.get("p"):
            track = tracks_mod.get(slug)
            return {"p": hot["p"], "v": hot["v"], "air": hot.get("air"),
                    "vmin": hot.get("vmin"),
                    "closed": bool(track.get("closed"))}, "hotlap"
    return relaxed_line(slug), "relaxed"


# Driver gains that one track needs different from the rest of the pool.
#
# **The bar for putting something here is a measurement showing the pool-wide
# value is wrong for this track and right everywhere else**, because a per-track
# override is a thing that silently stops being true when the driver changes.
# Each one says what was measured.
TRACK_TUNE = {
    # Sandy Cove: how far up the road to aim while airborne. The pool default of
    # 26 picks a point far below the car on Cove's descent to the beach, which
    # `AIR_PITCH` holds as nose-down for the whole flight, so the car glides past
    # the shelf the record lands on and drops nine units onto the sand - where
    # off-road drag takes it from 57 u/s to 26 and it respawns, 36 times, always
    # at station 100. At 8 it lands with the record: 56.25s against 58.48s on the
    # safe line, and +2.3% on the record rather than +6.4%.
    #
    # Not global, and that was measured, not assumed: Big Red is 28% airborne
    # over four long jumps and picks up a respawn at anything below 26.
    "cove": {"lookAir": 8},
}


def profile(slug, level, seed=0, pace=None):
    """The level as `bot.js` receives it, with this track's calibrated pace in it."""
    prof = dict(PROFILES[level])
    if pace is None:
        pace = setting(slug, level).get("pace")
    if pace:
        prof["pace"] = pace
    tune = TRACK_TUNE.get(slug)
    if tune:
        prof["tune"] = dict(tune, **(prof.get("tune") or {}))
    prof["seed"] = int(seed) & 0x7FFFFFFF
    return prof


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

def names():
    """The generated pool, or a small hard-coded one if the file is missing.

    Missing is not an error worth failing a room over - a bot with a dull name
    is still a bot to race - but `tools/bot_names.py` writes the file and a test
    asserts it is there.
    """
    global _names
    if _names is None:
        try:
            with open(NAMES_FILE) as f:
                _names = [ln.strip() for ln in f if ln.strip()]
        except OSError:
            _names = []
        if not _names:
            _names = ["Bot_01", "Bot_02", "Bot_03", "Bot_04",
                      "Bot_05", "Bot_06", "Bot_07"]
    return _names


def pick_name(used, rng=None):
    """A name nobody in the room is already using."""
    rng = rng or random
    pool = [n for n in names() if n not in used]
    if not pool:
        n = 1
        while ("Bot_%d" % n) in used:
            n += 1
        return "Bot_%d" % n
    return rng.choice(pool)
