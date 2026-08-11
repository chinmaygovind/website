"""What Spiral Ascent looks like."""

import math

PALETTE = { "road": 0x2c3040, "kerb": 0xf6f2ff, "kerb2": 0xbb6bd9,
"ground": 0x14121f, "rail": 0xd9d2ea, "prop": 0x3a3550, "deco": 0xd88ce8,
"fog": 0x171a30,
"sky": {
  "stops": [
    [0.00, 0x05060e], [0.44, 0x0a0d1e], [0.50, 0x121a35],
    [0.58, 0x101632], [0.72, 0x0b0f26], [1.00, 0x040611],
  ],
  # Tight halo. A wide one at this brightness stops being a moon
  # and becomes an evenly lit sky, which is the opposite of night.
  "glow": 0x9db2e0, "glowStrength": 0.42, "glowMode": 'radial', "glowFocus": 9,
  "stars": { "count": 1100, "seed": 31, "size": 2.1 },
  "sun": { "az": 1.15, "el": 0.2, "color": 0xe4ecff, "size": 190 },
  "light": { "color": 0xa8bbe8, "intensity": 0.72,
           "dir": [math.sin(1.15) * 0.8, 0.6, math.cos(1.15) * 0.8] },
  "hemi": { "sky": 0x3a4570, "ground": 0x0d0f1c, "intensity": 0.55 },
  "fog": 0x171a30, "fogNear": 220, "fogFar": 1100,
},
"below": { "kind": 'void' } }
