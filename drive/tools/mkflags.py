#!/usr/bin/env python3
"""The flag designs in `FLAGS` (trackmesh.js), as character grids.

    cd drive && python3 tools/mkflags.py

Prints each design twice: once as ASCII art to check by eye, once as the JS
literal to paste into `FLAGS`. Nothing reads this at runtime - it is here so the
next flag is derived rather than drawn by hand, and so the grids that *are* in
trackmesh.js can be re-checked against the rules that produced them.

Derived from the real construction rules once, here, then pasted in as a literal,
so what ships is inspectable in the source and cannot drift from a rule nobody can
see. Every cell is one colour and no two cells overlap - which is the whole point,
because layering a saltire over a field would be coplanar quads in one mesh and
that is a depth-buffer coin toss.

Union flag geometry, the parts that matter:
 * 1:2, so the grid is exactly twice as wide as it is tall;
 * the George cross is 1/5 of the height in red with 1/15 of white fimbriation
   either side, so red+white is 1/3 of the height, and the vertical arm is the
   same *absolute* width as the horizontal one, not the same fraction;
 * the St Patrick red saltire is **counterchanged** against the white St Andrew:
   white above red on the arm running to the top-left, red above white on the arm
   to the top-right, and the whole thing has 2-fold rotational symmetry rather
   than mirror symmetry. Getting that backwards is the classic upside-down flag,
   and it is why the offset below is signed off `v` rather than absolute.
"""

def union_jack(W=36, H=18):
    g = [['B'] * W for _ in range(H)]
    cx, cy = (W - 1) / 2, (H - 1) / 2
    hw, hh = W / 2, H / 2
    # Band half-widths, in units of half-height, then converted for the vertical
    # arm so both arms come out the same number of cells across.
    WHITE_V, RED_V = 1 / 3, 1 / 5          # fractions of the full height
    SALT_W = 0.15                           # half-width of the white saltire arm
    SALT_R = 0.052                          # ...and of the red inside it
    for y in range(H):
        for x in range(W):
            u = (x - cx) / hw               # -1..1 across
            v = (y - cy) / hh               # -1..1 down
            d1, d2 = abs(u - v), abs(u + v)
            s = 1 if v > 0 else -1          # the counterchange, per half
            if d1 < SALT_W * 2:
                g[y][x] = 'R' if (u - v) * s > SALT_R else 'W'
            if d2 < SALT_W * 2:
                if (u + v) * s > SALT_R:
                    g[y][x] = 'R'
                elif g[y][x] == 'B':
                    g[y][x] = 'W'
            # The cross last, so it reads over the saltire. Widths in cells, so
            # the two arms match: `hh` cells is one v-unit, `hw` is one u-unit.
            wv, rv = WHITE_V * H / 2, RED_V * H / 2      # in cells, half-width
            if abs(x - cx) < wv or abs(y - cy) < wv:
                g[y][x] = 'W'
            if abs(x - cx) < rv or abs(y - cy) < rv:
                g[y][x] = 'R'
    return [''.join(r) for r in g]

def tricolour(bands, W=18, H=12):
    return [''.join(bands[min(len(bands) - 1, int(x * len(bands) / W))]
                    for x in range(W)) for _ in range(H)]


def hinomaru(W=36, H=24):
    """The Japanese flag: a red disc on white, centred, 3/5 of the height across.

    The only two ways to get this wrong are the proportion and the centring, and
    both are law rather than custom: the 1999 Act puts the disc dead centre at
    three fifths of the hoist. Before it, the disc sat a hundredth of the length
    towards the hoist and was 7/10 - which is the version most clip art still
    draws, and it reads as slightly too big and slightly off to the left.

    A disc on a square grid is the one design here whose cell count depends on
    the resolution rather than on the construction, so W:H is held at 3:2 to
    keep the cells square - on a non-square cell the disc comes out an ellipse.
    """
    assert W * 2 == H * 3, "the grid has to be 3:2 or the disc is an ellipse"
    r = (3.0 / 5.0) * H / 2.0
    g = []
    for y in range(H):
        row = []
        for x in range(W):
            dx, dy = (x + 0.5) - W / 2.0, (y + 0.5) - H / 2.0
            row.append('R' if dx * dx + dy * dy <= r * r else 'W')
        g.append(''.join(row))
    return g

def runs(grid):
    n = 0
    for r in grid:
        n += 1 + sum(1 for i in range(1, len(r)) if r[i] != r[i - 1])
    return n

for name, grid in (('gb', union_jack()), ('be', tricolour('KYR')), ('jp', hinomaru())):
    art = {'B': '·', 'W': '#', 'R': '+', 'K': ' ', 'Y': ':'}
    print('%s  %dx%d  %d merged quads' % (name, len(grid[0]), len(grid), runs(grid)))
    for r in grid:
        print('   ', ''.join(art[c] for c in r))
    print()
for name, grid in (('gb', union_jack()), ('be', tricolour('KYR')), ('jp', hinomaru())):
    print("    %s: [" % name)
    for r in grid:
        print("      '%s'," % r)
    print("    ],")
