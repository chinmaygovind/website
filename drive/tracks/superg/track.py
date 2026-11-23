"""Super-G

Adopted from a community track by Brumm.

It was bouncy on the corners, for two reasons, and both fixes are here.

**The road is subdivided across its width** (`b.pipe(0.0)`, a pipe of no depth,
which is the flat nine-sample cross-section `Builder.wall` uses). A 26-wide road
falling through a 28-radius corner makes every quad between two stations a
twisted one, and the collider splits each into two flat triangles with a crease
down the diagonal - 456 of them, against about a hundred on most tracks. The
car hopped off one every few stations. Measured with the max bot, 76 flights a
lap totalling 13s in the air before; 8 to 11 after this alone.

**Each piece carries its grade into the next** (`ease=(g0, g1)`, see
`_profile`) instead of the default smoothstep, which is flat at both ends and so
made the descent a staircase - flat, steep, flat, steep - with a crest at every
join. With both, two flights a lap of about 0.15s. The plan, and the height at
every join, are as Brumm built them.
"""

slug = 'superg'
name = 'Super-G'
author = 'Brumm'
difficulty = 4
# Derived from the ribbon when this was adopted, not cut from a board.
# Re-cut with tools/set_medals.py once it has one worth cutting from.
medals = (43.6, 46.9, 50.6)
ground = -1.2
order = 375
width = 11

CP = None
# (kind, degrees or length, radius, rise, width); CP is a checkpoint, which is flat.
PIECES = [
    ('s', 64, None, -6.8, 22.5),
    ('a', -99, 43, -9.2, 26),
    ('a', 60, 40, -2.9, 21.5),
    ('a', 117, 35.5, -8.8, 26),
    ('a', -134, 28, -7.1, 26),
    CP,
    ('a', 99, 53.5, -14.2, 26),
    ('a', -125, 77, -30, 26),
    ('a', 126, 40, 10, 26),
    ('a', 36, 69.5, -3.2, 26),
    ('a', -121, 80, -26, 26),
    ('a', 156, 44.5, -24.5, 26),
    ('a', -29, 161, -11.1, 26),
    ('a', 60, 109.5, -21.6, 26),
    CP,
    ('a', 19, 211.5, -8.2, 26),
    ('a', -108, 53.5, -16.9, 26),
    ('s', 66, None, -7.3, 26),
    ('a', 125, 58, -26.7, 26),
    CP,
    ('a', -60, 106.5, -20.7, 26),
    ('a', 95, 52, -12.4, 26),
    ('a', -95, 49, -11, 26),
    ('a', -60, 40, -2.9, 26),
    ('a', 60, 77, -10.8, 26),
    ('a', -60, 66.5, -8.1, 26),
]


def _length(p):
    import math
    return p[1] if p[0] == 's' else math.radians(abs(p[1])) * p[2]


def _profile(pieces):
    """(rise, (g0, g1)) per piece: its own rise, with the grade carried across joins.

    A join between two falls takes the harmonic mean of their average grades
    (Fritsch-Carlson, which never overshoots either); a join beside a gate, or
    between a fall and a climb, is flat.
    """
    slope = [None if p is CP else p[3] / _length(p) for p in pieces]
    out = []
    for i, s in enumerate(slope):
        if s is None:
            out.append(None)
            continue
        ends = []
        for j in (i - 1, i + 1):
            o = slope[j] if 0 <= j < len(slope) else None
            ends.append(0.0 if o is None or o * s <= 0 else 2 * s * o / (s + o))
        out.append((pieces[i][3], tuple(ends)))
    return out


def build(b):
    """Super-G"""
    b.width(11)
    b.rail('lr')
    b.start(run=40)
    b.pipe(0.0)
    for p, prof in zip(PIECES, _profile(PIECES)):
        if p is CP:
            b.cp()
            continue
        b.width(p[4])
        if p[0] == 's':
            b.straight(p[1], rise=prof[0], ease=prof[1])
        else:
            b.arc(p[1], p[2], rise=prof[0], ease=prof[1])
    b.finish()
