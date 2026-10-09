"""A track, made up by a number.

`generate(seed, looks)` returns a **document** - the same move-list-and-palette a
person builds in `/make` - so nothing downstream knows or cares that a machine
wrote it. It is replayed by `moves.replay` through the same `Builder` that
builds Spa, and it is judged by the same `checks` the editor's gate runs. There
is no second idea of what a track is in here.

The whole method is **propose and throw away**. A seeded walk lays a plausible
road; the caller builds it, runs the battery, sends a bot round it and prices
it; anything that fails is discarded and the next seed is tried.
`tools/gen_daily.py` is the loop.

Two kinds of daily, and the look decides which
----------------------------------------------
* **A circuit** sits on a ground plane under one of the pool's grounded looks:
  corners, hills, and a few tricks - jumps, crests, banked sweepers, a boost
  pad, now and then a half-pipe or a loop. Tight chicanes get barriers, because
  a chicane you can drive straight through on the grass is not a chicane.
* **A stunt track** floats under one of the pool's void looks (void, lava,
  desert, downtown, pillars), open-edged like Playground (`exposed`), and is
  built from its vocabulary: loops, walls of death, gaps, drops, half-pipes.

Neither kind has barriers by default. They go round loops, through chicanes,
and wherever a shortcut has to be closed - nowhere else.

**Walls of death only ever climb.** One that descends puts its own exit under
its wrap, so dropping off the top lands on it and the whole corner is optional -
the Playground wall that does that is one of the two places every top time
there skips. And every loop and wall is followed by a checkpoint, which kills
any drop that would land past it. `checks.shortcuts` is what is asked
afterwards, and `gen_daily.repair` fixes what it finds or the seed is dropped.
"""

import math
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
FIRST = ("Copper", "Harbor", "Ridgeway", "Saltmarsh", "Kingfisher", "Ember",
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


# Keys that belong to one track's own layout, and are dropped from a borrowed
# look: a height field, a waterline, grandstands, a warehouse, lamps and
# lightning placed at that track's own points, a herd's voice.
LAYOUT_KEYS = ("terrain", "shore", "furniture", "building", "rainbow",
               "rainbowLanes", "snow", "lamps", "storm", "moverVoice")


def is_void(look):
    return bool((look.get("pal") or {}).get("below"))


def borrow(rng, look):
    """A palette off a real track, whole.

    **Borrowed verbatim rather than varied, and that was measured.** Rotating
    every colour round the wheel by one angle keeps the relations between the
    colours and still gives a picture of nowhere - Figure Eight's snow came out
    lavender under a green sun. The variety is in *which* of the pool's
    twenty-six worlds a daily gets, and in the road.

    **The scatter density is overridden**, because it is per unit of area: a
    palette cut for Figure Eight's small footprint carpets a track three times
    the size.
    """
    pal = dict(look["pal"] or {})
    for k in LAYOUT_KEYS:
        pal.pop(k, None)
    if pal.get("density"):
        pal["density"] = round(rng.uniform(0.03, 0.10), 3)
    return pal


def _arc(rng, turn, radii, first=False, deg=None):
    rad = rng.choice(radii)
    deg = deg or (rng.uniform(45.0, 150.0) if first else rng.uniform(28.0, 165.0))
    # A hairpin needs a small radius and a fast sweep a big one; the other two
    # combinations are a corner nobody can see the end of and a kink.
    if deg > 110.0:
        rad = min(rad, 26.0)
    if deg < 45.0:
        rad = max(rad, 26.0)
    return {"t": "arc", "deg": round(deg * turn, 1), "rad": rad, "rise": 0.0}


def _length(m):
    """Roughly how much road a move lays, for aiming the walk at a lap time."""
    t = m["t"]
    if t in ("straight", "boost", "bounce"):
        return m.get("len", 12.0)
    if t in ("arc", "wall"):
        return abs(m["deg"]) * math.pi / 180.0 * m["rad"]
    if t in ("crest", "hump"):
        return m["len"]
    if t == "jump":
        return 8.0 + m["gap"] + m.get("land", 14.0)
    if t == "gap":
        return m["len"]
    if t == "loop":
        return 2 * math.pi * m.get("rad", 20.0)
    if t == "cp":
        return 34.0
    return 0.0


# What each kind of daily may throw in down a straight, by weight. A stunt
# track is mostly set pieces; a circuit is mostly road with a few.
CIRCUIT_TRICKS = (("jump", 3), ("crest", 3), ("hump", 2), ("boost", 2),
                  ("sweeper", 3), ("pipe", 1), ("loop", 1), ("chicane", 3),
                  ("esses", 3), ("rollers", 2), ("wallride", 2), ("bounce", 1),
                  ("narrows", 2))
STUNT_TRICKS = (("loop", 3), ("wall", 3), ("jump", 3), ("gap", 3),
                ("pipe", 2), ("dive", 2), ("sweeper", 2), ("boost", 1),
                ("bounce", 3), ("helix", 2), ("stairs", 2), ("leap", 2),
                ("wallride", 2), ("esses", 1))

def _pick(rng, table):
    total = sum(w for _, w in table)
    r = rng.uniform(0, total)
    for name, w in table:
        r -= w
        if r <= 0:
            return name
    return table[-1][0]


# **Every daily is its own menu**: one signature set piece, weighted this many
# times, and two others drawn beside it - nothing else from the table. With
# every trick on offer at its base weight the dailies came out as the same even
# mix in a different order and all felt alike; a day that is mostly caps with a
# helix, and the next mostly esses with a wall-ride, are two different tracks.
SIGNATURE = 4
SIDES = 2


def _flavour(rng, table):
    sig = _pick(rng, table)
    rest = [kw for kw in table if kw[0] != sig]
    sides = rng.sample(rest, min(SIDES, len(rest)))
    return ((sig, dict(table)[sig] * SIGNATURE),) + tuple(sides), sig


def _trick(rng, kind, turn, radii, stunt):
    """The moves for one set piece. Returns `(moves, height_change, turn)`."""
    if kind == "jump":
        drop = round(rng.uniform(0.0, 8.0 if stunt else 4.0), 1)
        out = []
        if rng.random() < 0.5:
            out += [{"t": "boost", "len": 12.0},
                    {"t": "straight", "len": round(rng.uniform(24.0, 40.0), 1)}]
        out.append({"t": "jump", "rise": round(rng.uniform(3.0, 5.5), 1),
                    "gap": round(rng.uniform(14.0, 26.0 if stunt else 20.0), 1),
                    "drop": drop})
        return out, -drop, turn
    if kind == "gap":
        drop = round(rng.uniform(2.0, 14.0), 1)
        return ([{"t": "boost", "len": 14.0},
                 {"t": "straight", "len": round(rng.uniform(30.0, 46.0), 1)},
                 {"t": "gap", "len": round(rng.uniform(14.0, 28.0), 1),
                  "drop": drop},
                 {"t": "straight", "len": 24.0}], -drop, turn)
    if kind == "crest":
        rise = round(rng.uniform(4.0, 7.0), 1)
        return ([{"t": "crest", "rise": rise,
                  "len": round(rng.uniform(22.0, 30.0), 1)},
                 {"t": "straight", "len": round(rng.uniform(34.0, 56.0), 1),
                  "rise": -rise}], 0.0, turn)
    if kind == "hump":
        return ([{"t": "hump", "rise": round(rng.uniform(3.0, 4.6), 1),
                  "len": round(rng.uniform(26.0, 34.0), 1)}], 0.0, turn)
    if kind == "boost":
        return ([{"t": "boost", "len": 12.0},
                 {"t": "straight", "len": round(rng.uniform(40.0, 70.0), 1)}],
                0.0, turn)
    if kind == "sweeper":
        turn = -turn if rng.random() < 0.7 else turn
        deg = rng.uniform(70.0, 160.0)
        rad = rng.choice([r for r in radii if r >= 26.0] or [32.0])
        return ([{"t": "arc", "deg": round(deg * turn, 1), "rad": rad,
                  "rise": 0.0, "bank": round(rng.uniform(12.0, 26.0) * turn, 1)}],
                0.0, turn)
    if kind == "chicane":
        # Two tight corners of opposite hand, walled - see the module docstring.
        tight = [r for r in radii if r <= 26.0] or [21.0]
        a = {"t": "arc", "deg": round(rng.uniform(40.0, 75.0) * turn, 1),
             "rad": rng.choice(tight), "rise": 0.0, "rail": "lr"}
        link = {"t": "straight", "len": round(rng.uniform(6.0, 16.0), 1),
                "rail": "lr"}
        b = {"t": "arc", "deg": round(-rng.uniform(40.0, 75.0) * turn, 1),
             "rad": rng.choice(tight), "rise": 0.0, "rail": "lr"}
        return [a, link, b, {"t": "straight", "len": 12.0, "rail": None}], 0.0, -turn
    if kind == "pipe":
        turn = -turn
        inner = [{"t": "arc", "deg": round(rng.uniform(60.0, 140.0) * turn, 1),
                  "rad": rng.choice([r for r in radii if r >= 21.0] or [26.0]),
                  "rise": 0.0}]
        if rng.random() < 0.5:
            turn = -turn
            inner.append({"t": "arc",
                          "deg": round(rng.uniform(50.0, 110.0) * turn, 1),
                          "rad": rng.choice([r for r in radii if r >= 21.0] or [26.0]),
                          "rise": 0.0})
        return ([{"t": "pipe", "depth": round(rng.uniform(3.5, 6.0), 1),
                  "floor": round(rng.uniform(0.25, 0.4), 2), "side": "lr"}]
                + inner + [{"t": "flat"}, {"t": "straight", "len": 16.0}],
                0.0, turn)
    if kind == "loop":
        # Walled round the loop itself and nowhere else: coming off the inside
        # of a loop is falling, not driving.
        extra = {"rail": "lr"}
        return ([{"t": "boost", "len": 14.0},
                 {"t": "straight", "len": round(rng.uniform(30.0, 44.0), 1)},
                 dict({"t": "loop", "rad": round(rng.uniform(20.0, 25.0), 1),
                       "dir": rng.choice(("l", "r"))}, **extra),
                 dict({"t": "straight", "len": 20.0}, **extra),
                 {"t": "cp", "rail": None}], 0.0, turn)
    if kind == "wall":
        turn = -turn if rng.random() < 0.6 else turn
        rise = round(rng.uniform(8.0, 18.0), 1)
        # `Builder.wall` needs twice the ramp in arc, and a ramp under about
        # eighty units rolls the road out from under the car before it is
        # tilted far enough to stick - so the arc is sized to the ramp.
        deg = rng.uniform(250.0, 320.0)
        rad = rng.uniform(38.0, 44.0)
        ramp = min(90.0, deg * math.pi / 180.0 * rad / 2.0 - 1.0)
        return ([{"t": "boost", "len": 16.0},
                 {"t": "straight", "len": round(rng.uniform(34.0, 46.0), 1)},
                 {"t": "wall", "deg": round(deg * turn, 1), "rad": round(rad, 1),
                  "bank": round(rng.uniform(80.0, 88.0), 1),
                  "ramp": round(ramp, 1), "rise": rise, "w": 21.0},
                 {"t": "straight", "len": 26.0, "w": None},
                 {"t": "cp"}], rise, turn)
    if kind == "bounce":
        # A cap wants a wide zone to land on and road to come down onto: hang
        # time is fixed, so where you touch down moves with arrival speed. Boo's
        # numbers (26 of cap, 16 wide) - see its track.py.
        return ([{"t": "straight", "len": 18.0, "w": 16.0},
                 {"t": "bounce", "len": 26.0, "w": 16.0},
                 {"t": "straight", "len": round(rng.uniform(70.0, 100.0), 1),
                  "w": 16.0},
                 {"t": "straight", "len": 12.0, "w": None}], 0.0, turn)
    if kind == "esses":
        out = []
        for _ in range(rng.randint(3, 4)):
            turn = -turn
            out.append({"t": "arc", "deg": round(rng.uniform(35.0, 70.0) * turn, 1),
                        "rad": rng.choice([r for r in radii if r >= 21.0] or [26.0]),
                        "rise": 0.0, "bank": round(rng.uniform(4.0, 10.0) * turn, 1)})
        return out, 0.0, turn
    if kind == "rollers":
        out = []
        for _ in range(rng.randint(2, 3)):
            out.append({"t": "hump", "rise": round(rng.uniform(2.5, 4.0), 1),
                        "len": round(rng.uniform(24.0, 32.0), 1)})
        return out, 0.0, turn
    if kind == "wallride":
        # One wall, on the outside of a long corner: a high line to take.
        turn = -turn
        return ([{"t": "pipe", "depth": round(rng.uniform(5.0, 7.5), 1),
                  "floor": round(rng.uniform(0.3, 0.45), 2),
                  "side": "l" if turn > 0 else "r"},
                 {"t": "arc", "deg": round(rng.uniform(90.0, 170.0) * turn, 1),
                  "rad": rng.choice([r for r in radii if r >= 26.0] or [32.0]),
                  "rise": 0.0},
                 {"t": "flat"}, {"t": "straight", "len": 16.0}], 0.0, turn)
    if kind == "narrows":
        out = [{"t": "straight", "len": 14.0, "w": 8.0}]
        for _ in range(rng.randint(2, 3)):
            turn = -turn
            out.append({"t": "arc", "deg": round(rng.uniform(30.0, 60.0) * turn, 1),
                        "rad": rng.choice([r for r in radii if r >= 26.0] or [32.0]),
                        "rise": 0.0})
        out.append({"t": "straight", "len": 16.0, "w": None})
        return out, 0.0, turn
    if kind == "helix":
        # Climbing only, for the walls' reason: one that descends puts its exit
        # under itself and dropping off the top skips it.
        turn = -turn if rng.random() < 0.5 else turn
        rise = round(rng.uniform(20.0, 28.0), 1)
        return ([{"t": "boost", "len": 14.0},
                 {"t": "straight", "len": 30.0},
                 {"t": "arc", "deg": round(rng.uniform(330.0, 400.0) * turn, 1),
                  "rad": round(rng.uniform(34.0, 44.0), 1), "rise": rise,
                  "bank": round(rng.uniform(14.0, 22.0) * turn, 1)},
                 {"t": "straight", "len": 24.0}, {"t": "cp"}], rise, turn)
    if kind == "stairs":
        out, dy = [{"t": "boost", "len": 14.0},
                   {"t": "straight", "len": round(rng.uniform(26.0, 36.0), 1)}], 0.0
        for _ in range(rng.randint(2, 3)):
            drop = round(rng.uniform(4.0, 8.0), 1)
            out += [{"t": "gap", "len": round(rng.uniform(10.0, 16.0), 1),
                     "drop": drop},
                    {"t": "straight", "len": round(rng.uniform(22.0, 30.0), 1)}]
            dy -= drop
        return out, dy, turn
    if kind == "leap":
        # A big one: off a steep crease, over a long hole, well below. The bow
        # matches the kick so the racing line does not read the lip as a corner
        # (Rickety Rails' `_bow`).
        length = round(rng.uniform(40.0, 60.0), 1)
        drop = round(rng.uniform(14.0, 24.0), 1)
        grade = 0.12
        return ([{"t": "boost", "len": 14.0},
                 {"t": "straight", "len": round(rng.uniform(30.0, 40.0), 1)},
                 {"t": "straight", "len": 24.0, "rise": round(24.0 * grade, 1),
                  "ease": False},
                 {"t": "gap", "len": length, "drop": drop,
                  "bow": round((drop + length * grade) / math.pi, 3)},
                 {"t": "straight", "len": 34.0},
                 {"t": "cp"}], -drop + 24.0 * grade, turn)
    if kind == "dive":
        drop = round(rng.uniform(12.0, 24.0), 1)
        return ([{"t": "straight", "len": round(rng.uniform(50.0, 80.0), 1),
                  "rise": -drop}], -drop, turn)
    raise ValueError(kind)


def generate(seed, looks, secs=None, look=None):
    """A document, from a number. Same seed and look, same track, forever.

    `looks` is `[{"slug", "name", "pal"}]` - every pool track's look. `look`
    pins which one (the caller rotates them so neighbouring days differ);
    otherwise one is drawn. A look with a `below` makes a stunt track over the
    void, and one without makes a circuit on the ground.
    """
    rng = random.Random(seed)
    secs = secs or rng.uniform(TARGET_LOW + 1.0, TARGET_HIGH - 4.0)
    want = secs * UNITS_PER_SEC
    look = look or rng.choice(looks)
    stunt = is_void(look)
    pal = borrow(rng, look)
    width = rng.choice((12.0, 13.0, 14.0) if stunt else (10.0, 11.0, 11.0, 12.0, 13.0))
    # **No barriers by default, on either kind.** An edge you can go off is
    # what makes a stunt track a stunt track - Playground, Rainbow Road and
    # Cloudbreak are all `exposed` - and a circuit has grass to run onto.
    # Barriers go only where they do a job: round a loop, through a chicane,
    # and wherever `gen_daily.repair` closes a shortcut.
    rails = False

    # Four to six of the eight radii, so the spread check is met by
    # construction and the track still has a character.
    radii = rng.sample(RADII, rng.randint(4, 6))

    moves = [{"t": "start", "run": round(rng.uniform(38.0, 64.0), 1)}]
    laid = moves[0]["run"]
    turn = rng.choice((-1, 1))
    first = True
    # How much height is in hand. A track that only ever climbs ends in orbit,
    # so the walk is pulled back towards zero rather than being free.
    y = 0.0
    table, sig = _flavour(rng, STUNT_TRICKS if stunt else CIRCUIT_TRICKS)
    tricks = rng.randint(6, 8) if stunt else rng.randint(4, 6)
    gap_after = 1 if stunt else 2
    since = 0

    while laid < want:
        left = want - laid
        # Corner one has to turn far enough for `checks.pole_side` to know
        # which side of the road the grid goes on.
        if rng.random() < 0.72:
            turn = -turn
        arc = _arc(rng, turn, radii, first=first)
        if rng.random() < 0.3:
            arc["rise"] = round(rng.uniform(-7.0, 7.0) - y * 0.18, 1)
        if rng.random() < 0.22:
            arc["bank"] = round(rng.uniform(4.0, 11.0) * turn, 1)
        moves.append(arc)
        laid += _length(arc)
        y += arc["rise"]
        first = False
        since += 1

        # A set piece, spread over the lap rather than bunched: never two in a
        # row, and more likely the longer it has been since the last.
        if (tricks and since >= gap_after and left > 140.0
                and rng.random() < (0.55 if stunt else 0.3) + 0.12 * since):
            kind = _pick(rng, table)
            got, dy, turn = _trick(rng, kind, turn, radii, stunt)
            moves += got
            laid += sum(_length(m) for m in got)
            y += dy
            tricks -= 1
            since = 0
            continue

        # **Two draws and not one**, because the pool's median straight is 17
        # units: a real track is mostly short connectors with a few proper
        # straights among them.
        run = (rng.uniform(12.0, 26.0) if rng.random() < 0.72
               else rng.uniform(42.0, 88.0))
        run = min(run, max(18.0, left))
        rise = 0.0
        if rng.random() < (0.45 if stunt else 0.34):
            span = 14.0 if stunt else 9.0
            rise = round(rng.uniform(-span, span) - y * 0.22, 1)
        moves.append({"t": "straight", "len": round(run, 1), "rise": rise})
        laid += run
        y += rise

    # Checkpoints, spread over the straights, on top of the ones the set pieces
    # brought with them. Three is what the pool uses.
    have = sum(1 for m in moves if m["t"] == "cp")
    spots = [i for i, m in enumerate(moves)
             if m["t"] == "straight" and moves[min(i + 1, len(moves) - 1)]["t"] != "cp"]
    n_cp = max(0, (3 if len(spots) >= 6 else 2) - have)
    if n_cp and len(spots) >= n_cp:
        picks = sorted(spots[int(len(spots) * (k + 1) / (n_cp + 1))] for k in range(n_cp))
        for at in reversed(sorted(set(picks))):
            moves.insert(at + 1, {"t": "cp"})

    # End level and on a straight: the flag on a corner is a lottery.
    moves.append({"t": "straight", "len": round(rng.uniform(40.0, 70.0), 1),
                  "rise": round(-y, 1)})
    moves.append({"t": "finish"})

    # Width and barriers are sticky from the move that sets them, so a set
    # piece that changes either hands back `None`, meaning "the track's own".
    for m in moves:
        if "w" in m and m["w"] is None:
            m["w"] = width
        if "rail" in m and m["rail"] is None:
            m["rail"] = "lr" if rails else ""

    return {
        "name": name_for(rng),
        "moves": moves,
        "width": width,
        # A stunt track floats, open-edged; a circuit sits on a ground plane
        # whose height `settle_ground` fixes once the ribbon exists.
        "ground": None if stunt else 0.0,
        "exposed": stunt,
        "rails": rails,
        "difficulty": (4 if stunt else (2 if max(radii) >= 40 else 3)),
        "pal": pal,
        "generated": {"seed": seed, "look": look["slug"],
                      "kind": "stunt" if stunt else "circuit",
                      "signature": sig},
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
    if doc.get("ground") is None:
        return doc
    low = min(e["p"][1] for e in track["line"])
    # Far enough under that the kerbs sit proud of it rather than flush, which
    # is what every ground track in the pool looks like.
    doc["ground"] = round(low - 1.4, 1)
    return doc
