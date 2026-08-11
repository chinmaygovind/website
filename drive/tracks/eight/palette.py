"""What Figure Eight looks like."""

import math

PALETTE = { "road": 0x3f4653, "kerb": 0xffffff, "kerb2": 0x3d8bfd,
"ground": 0xdfe7f2, "rail": 0xf4f8ff,
"prop": 0x244a39, "prop2": 0x1f4434, "snow": 0xf4f9ff, "deco": 0x7fb6e8,
"fog": 0xcfdcea,
"density": 0.26,
"props": { "bigpine": 0.34, "conifer": 0.3, "deadtree": 0.22, "rock": 0.14 },
"sky": {
  # A low winter sun that never really warms anything: the horizon
  # is pale gold, but it is white and cold two-thirds of the way up.
  "stops": [
    [0.00, 0x9aa9bc], [0.44, 0xd8dfe8], [0.50, 0xf0ecdf],
    [0.56, 0xdde6f0], [0.68, 0xa8c4e2], [0.84, 0x6d9ed6],
    [1.00, 0x3b6fb8],
  ],
  "glow": 0xfff2d4, "glowStrength": 0.72, "glowMode": 'radial', "glowFocus": 4,
  "sun": { "az": 2.0, "el": 0.14, "color": 0xfff6e2, "size": 480 },
  "light": { "color": 0xfdf3e6, "intensity": 1.32,
           "dir": [math.sin(2.0) * 0.82, 0.56, math.cos(2.0) * 0.82] },
  # Bounce off snow is bright and slightly blue, which is most of
  # why a snowy scene has no dark shadows in it.
  "hemi": { "sky": 0xdae8fa, "ground": 0xc6d4e4, "intensity": 0.95 },
  "fog": 0xcfdcea, "fogNear": 260, "fogFar": 1200,
} }
