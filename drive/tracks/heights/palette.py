"""What Hairpin Heights looks like."""

import math

PALETTE = { "road": 0x4f5460, "kerb": 0xf4f4f4, "kerb2": 0xf2994a,
"ground": 0x7a6a52, "rail": 0xfff2e2, "prop": 0x8a7358, "deco": 0xf2994a,
"fog": 0xc7dcee,
"sky": {
  # Clear high-altitude blue. Cold and bright, so the cloud sea
  # under it reads as white rather than as sand.
  "stops": [
    [0.00, 0x7d95ae], [0.44, 0xc4dcee], [0.50, 0xdcecf7],
    [0.54, 0xa6cbec], [0.62, 0x74a8e2], [0.74, 0x4785d2],
    [0.88, 0x2a63c0], [1.00, 0x113d92],
  ],
  "glow": 0xffffff, "glowStrength": 0.72, "glowMode": 'radial', "glowFocus": 5,
  "sun": { "az": 0.9, "el": 0.46, "color": 0xffffff, "size": 560 },
  "light": { "color": 0xfffaf2, "intensity": 1.5,
           "dir": [math.sin(0.9) * 0.66, 0.75, math.cos(0.9) * 0.66] },
  # Bounce off the cloud below is white, not warm.
  "hemi": { "sky": 0xd7e8fa, "ground": 0xc3cedb, "intensity": 0.8 },
  "fog": 0xc7dcee, "fogNear": 300, "fogFar": 1450,
},
"below": { "deck": 96, "depth": 120, "reach": 980,
         "towerDensity": 0, "cover": 0.6,
         "cloud": 0xfdfdff, "floor": 0x7f93a8 } }
