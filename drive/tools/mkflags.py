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

def runs(grid):
    n = 0
    for r in grid:
        n += 1 + sum(1 for i in range(1, len(r)) if r[i] != r[i - 1])
    return n

for name, grid in (('gb', union_jack()), ('be', tricolour('KYR'))):
    art = {'B': '·', 'W': '#', 'R': '+', 'K': ' ', 'Y': ':'}
    print('%s  %dx%d  %d merged quads' % (name, len(grid[0]), len(grid), runs(grid)))
    for r in grid:
        print('   ', ''.join(art[c] for c in r))
    print()
for name, grid in (('gb', union_jack()), ('be', tricolour('KYR'))):
    print("    %s: [" % name)
    for r in grid:
        print("      '%s'," % r)
    print("    ],")
