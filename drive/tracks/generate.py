"""A track, made up by a number.

`generate(seed)` returns a **document** - the same move-list-and-palette a
person builds in `/make` - so nothing downstream knows or cares that a machine
wrote it. It is replayed by `moves.replay` through the same `Builder` that
builds Spa, and it is judged by the same `checks` the editor's gate runs. There
is no second idea of what a track is in here.

The whole method is **propose and throw away**. A seeded walk lays a plausible
road; the caller builds it and runs the battery; anything that fails, or that
prices outside the length it was asked for, is discarded and the next seed is
tried. That is why this file has no cleverness about avoiding a crossing or
hitting a lap time: it does not need any. `tools/gen_daily.py` is the loop, and
at the numbers below it keeps roughly one candidate in four, which is nothing -
a candidate costs about 5ms to build and a few hundred more to price.

Rejection is also what keeps this honest. The alternative - a generator that
guarantees its output - is a second, weaker copy of `checks.py` that would drift
the day somebody adds a check. Here a new check simply lowers the accept rate.

What it deliberately will not make
----------------------------------
Void tracks, loops, walls of death, pipes, tunnels, anything with scenery of its
own. A daily is a **road**: corners, hills, a jump or two, over ground you can
run off onto. The pool is where the ideas live; this is where the practice laps
come from, and a practice lap nobody can finish is worth nothing. The palette is
borrowed whole from a real track rather than invented, for the same reason.
"""

import random

from tracks import look

# What a daily is worth, in seconds of `ideal` lap. The caller enforces it; it
# is here because it is the one number that decides every other number below.
TARGET_LOW = 30.0
TARGET_HIGH = 40.0

# Units of road per second of ideal lap, measured across the pool: twenty-five
# tracks run 40.3 to 50.3 with a mean of 43.4. So a walk is asked for length
# rather than for time - pricing a lap costs ~550ms and laying a ribbon ~5ms,
# and being roughly right before the expensive step is what makes the reject
# loop cheap.
UNITS_PER_SEC = 38.0   # measured on generated walks, not on the pool: a made-up
                      # track turns more often than a hand-cut one and prices
                      # slower per unit, so the pool mean of 43.4 overshot by 4s

# Corner radii, and the whole reason for a list rather than a range: `checks`
# wants at least RADII_DISTINCT different ones with a spread of RADII_SPREAD,
# and a uniform draw over a continuum satisfies that by accident. Drawing
# without replacement from a spread-out set satisfies it on purpose.
RADII = (14.0, 17.0, 21.0, 26.0, 32.0, 40.0, 50.0, 62.0)

# Two halves of a name. Not a theme - a label, so fifty of them in a queue can
# be told apart.
FIRST = ("Copper", "Harbour", "Ridgeway", "Saltmarsh", "Kingfisher", "Ember",
         "Thistle", "Larkspur", "Draycott", "Halfpenny", "Wintergreen",
         "Brackenfell", "Cinder", "Quarry", "Tanglewood", "Marlow", "Pennyroyal",
         "Foxglove", "Blackthorn", "Crowsnest", "Aldermoor", "Sandgate",
         "Hollowell", "Windrush", "Netherby", "Cairnwell", "Fernhead",
         "Ashbourne", "Milburn", "Greystoke", "Orchard", "Pipers")
SECOND = ("Reach", "Sweep", "Loop", "Rise", "Hollow", "Cross", "Mile", "Bend",
          "Chase", "Run", "Drop", "Gate", "Dash", "Climb", "Curve", "Leap",
          "Bank", "Way", "Vale", "Spur", "Circuit", "Park", "Traverse")


def name_for(rng):
    return "%s %s" % (rng.choice(FIRST), rng.choice(SECOND))


def borrow(rng, looks):
    """A palette off a real track, whole, with the slug it came from.

    **Borrowed verbatim rather than varied, and that was measured.** The first
    version rotated every colour round the wheel by one angle, on the reasoning
    that what makes a palette work is the *relations* between its colours and a
    single rotation preserves all of them. The relations do survive; the result
    still does not. Figure Eight's snow came out lavender under a green sun -
    every rule in `docs/track-defects.md` kept and the track ugly anyway,
    because a palette is a picture of a place and a rotated one is a picture of
    nowhere. Ten real palettes reused across fifty dailies beats fifty invented
    ones, and the variety a daily actually needs is in its road.

    `looks` is `[{"slug", "name", "pal"}]` - what `maker._pool_looks` already
    hands the editor's borrow-a-look list. Only grounded palettes are offered
    here; a void track's look has a `below` and no ground worth standing on.
    """
    src = rng.choice(looks)
    pal = dict(src["pal"] or {})
    pal.pop("terrain", None)      # a height field belongs to its own layout
    pal.pop("shore", None)        # so does a waterline
    pal.pop("furniture", None)    # Spa's grandstands stand where Spa's road is
    pal.pop("building", None)     # so does the Costco
    pal.pop("rainbow", None)
    pal.pop("rainbowLanes", None)
    # **The scatter density is overridden and not borrowed**, and it is the one
    # number here that has to be. Density is per unit of area, so a palette cut
    # for Figure Eight's small footprint carpets a track three times the size -
    # the pool runs 0 to 0.34 with a *median of 0.05*, and a borrowed 0.26 drew
    # the "scatter has become a junkyard" defect exactly as `docs/track-defects.md`
    # describes it. Nothing else in a palette scales with the layout, which is
    # why nothing else is touched.
    if pal.get("density"):
        pal["density"] = round(rng.uniform(0.03, 0.10), 3)
    return pal, src["slug"]


def generate(seed, looks, secs=None):
    """A document, from a number. Same seed, same track, forever.

    `looks` is the borrow list (see `borrow`). `secs` is the ideal lap this is
    aiming at; the caller still has to *check* it, because length is only a
    proxy - a road full of hairpins prices slower per unit than a fast one.
    """
    rng = random.Random(seed)
    secs = secs or rng.uniform(TARGET_LOW + 2.0, TARGET_HIGH - 3.0)
    want = secs * UNITS_PER_SEC

    pal, from_slug = borrow(rng, looks)
    width = rng.choice((10.0, 11.0, 11.0, 12.0, 13.0))

    # Radii for this track: four to six of the eight, so the spread check is
    # met by construction and the track still has a character - a set drawn
    # from the tight end is a twisty one, from the wide end a fast one.
    radii = rng.sample(RADII, rng.randint(4, 6))

    moves = [{"t": "start", "run": round(rng.uniform(38.0, 64.0), 1)}]
    laid = moves[0]["run"]
    # Corner one has to turn far enough for `checks.pole_side` to know which
    # side of the road the grid goes on. FIRST_TURN_DEG is 25; 45 is clear of it
    # with room for the walk to wander.
    turn = rng.choice((-1, 1))
    first = True
    # How much height is in hand. A track that only ever climbs ends in orbit,
    # so the walk is pulled back towards zero rather than being free.
    y = 0.0
    feature_budget = rng.randint(1, 3)

    while laid < want:
        left = want - laid

        # A corner. The sign is mostly alternating - a road that turns the same
        # way ten times is a spiral, and a spiral is the fastest way to trip
        # `self_proximity`.
        if rng.random() < 0.72:
            turn = -turn
        rad = rng.choice(radii)
        deg = rng.uniform(45.0, 150.0) if first else rng.uniform(28.0, 165.0)
        # A hairpin needs a small radius and a fast sweep a big one; the other
        # two combinations are a corner nobody can see the end of and a kink.
        if deg > 110.0:
            rad = min(rad, 26.0)
        if deg < 45.0:
            rad = max(rad, 26.0)
        rise = 0.0
        if rng.random() < 0.3:
            rise = round(rng.uniform(-7.0, 7.0) - y * 0.18, 1)
        arc = {"t": "arc", "deg": round(deg * turn, 1), "rad": rad, "rise": rise}
        if rng.random() < 0.22:
            arc["bank"] = round(rng.uniform(4.0, 11.0) * (1 if turn > 0 else -1), 1)
        moves.append(arc)
        laid += abs(arc["deg"]) * 3.14159 / 180.0 * rad
        y += rise
        first = False

        # Then something to do down the straight that follows it.
        roll = rng.random()
        if feature_budget and roll < 0.16 and left > 220.0:
            feature_budget -= 1
            kind = rng.choice(("hump", "crest", "boost", "jump"))
            if kind == "hump":
                moves.append({"t": "hump", "rise": round(rng.uniform(3.0, 4.6), 1),
                              "len": round(rng.uniform(26.0, 34.0), 1)})
                laid += 30.0
            elif kind == "crest":
                # A crease rather than a hill: `ease` off is what launches the
                # car, and the drop after it is what makes that worth doing.
                rise = round(rng.uniform(4.0, 7.0), 1)
                moves.append({"t": "crest", "rise": rise,
                              "len": round(rng.uniform(22.0, 30.0), 1)})
                moves.append({"t": "straight", "len": round(rng.uniform(34.0, 56.0), 1),
                              "rise": -rise})
                laid += 80.0
            elif kind == "boost":
                moves.append({"t": "boost", "len": 12.0})
                moves.append({"t": "straight", "len": round(rng.uniform(40.0, 70.0), 1)})
                laid += 65.0
            else:
                drop = round(rng.uniform(0.0, 5.0), 1)
                moves.append({"t": "jump", "rise": round(rng.uniform(3.0, 5.5), 1),
                              "gap": round(rng.uniform(12.0, 22.0), 1), "drop": drop})
                laid += 40.0
                y -= drop

        # **Two draws and not one**, because the pool's median straight is 17
        # units and a uniform range cannot produce that without also giving up
        # the long ones. A real track is mostly short connectors between
        # corners with a few proper straights among them; one uniform draw is a
        # track of nothing but half-straights, which measured 41 against a pool
        # that tops out at 33.7. Three short to one long lands on the median.
        run = (rng.uniform(12.0, 26.0) if rng.random() < 0.72
               else rng.uniform(42.0, 88.0))
        run = min(run, max(18.0, left))
        rise = 0.0
        if rng.random() < 0.34:
            rise = round(rng.uniform(-9.0, 9.0) - y * 0.22, 1)
        moves.append({"t": "straight", "len": round(run, 1), "rise": rise})
        laid += run
        y += rise

    # Checkpoints, spread over the moves that were laid rather than over the
    # metres, because a `cp` between two corners is a checkpoint on a corner.
    # Three is what the pool uses; `checks.MIN_CHECKPOINTS` is two.
    spots = [i for i, m in enumerate(moves) if m["t"] == "straight"]
    n_cp = 3 if len(spots) >= 6 else 2
    if len(spots) >= n_cp:
        picks = sorted(spots[int(len(spots) * (k + 1) / (n_cp + 1))] for k in range(n_cp))
        for at in reversed(sorted(set(picks))):
            moves.insert(at + 1, {"t": "cp"})

    # End level and end straight: the flag on a corner is a lottery, and the
    # last thing a walk that has been pulled towards zero all lap needs is a
    # final climb.
    moves.append({"t": "straight", "len": round(rng.uniform(40.0, 70.0), 1),
                  "rise": round(-y, 1)})
    moves.append({"t": "finish"})

    return {
        "name": name_for(rng),
        "moves": moves,
        "width": width,
        # Always grounded. A void daily is a daily most people cannot finish,
        # and `checks` wants ground or barriers anyway.
        #
        # **A placeholder, and `settle_ground` replaces it once the ribbon
        # exists.** It cannot be right here: the walk climbs and falls, and how
        # far down it ends up is not known until the road has been laid. A fixed
        # value guessed in advance produced exactly the defect
        # `test_the_road_is_never_buried_in_its_own_ground` names - a flat quad
        # drawn straight through the tarmac, with only the three stretches that
        # happened to stay above it visible from the air.
        "ground": 0.0,
        "rails": rng.random() < 0.45,
        "difficulty": 2 if max(radii) >= 40 else 3,
        "pal": pal,
        "generated": {"seed": seed, "look": from_slug},
    }


def settle_ground(doc, track):
    """Drop the ground quad under the lowest point of the road it was built for.

    `track.ground` is one flat collidable quad at a world Y, and a ribbon that
    dips below it does not clip, warn or fail anything - the quad simply draws
    through the road (`test_the_road_is_never_buried_in_its_own_ground`). The
    walk cannot know where its own floor is until it has been laid, so the
    document carries a placeholder and this corrects it against the real ribbon.

    Mutates and returns `doc`; the caller rebuilds. Cheap enough to be worth it -
    an untimed build is ~5ms against the ~550ms `laptime.ideal_lap` costs, which
    is why the generator builds twice and prices once.
    """
    low = min(e["p"][1] for e in track["line"])
    # Far enough under that the kerbs sit proud of it rather than flush, which
    # is what every ground track in the pool looks like.
    doc["ground"] = round(low - 1.4, 1)
    return doc
