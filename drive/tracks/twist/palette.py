"""What Twin Loop looks like."""

import math

PALETTE = { "road": 0x515c6e, "kerb": 0xf7f1e6, "kerb2": 0xc75b3a,
"ground": 0xd9b478, "rail": 0xf7f1e6, "prop": 0xb5744a, "deco": 0xf2a03c,
"fog": 0xdfc79b,
"sky": {
  "stops": [
    [0.00, 0xb08a5c], [0.42, 0xdcbe8e], [0.50, 0xf4e3c0],
    [0.58, 0xd3dbdd], [0.70, 0x92b8dd], [0.86, 0x4b86cf],
    [1.00, 0x1d55a4],
  ],
  # Big, hot and low enough to be in frame from the grid. The
  # halo is wide (a small focus exponent) because that is what a
  # sun you have to squint at actually does to a sky.
  "glow": 0xfff9e8, "glowStrength": 0.95, "glowMode": 'radial', "glowFocus": 3.2,
  "sun": { "az": 1.9, "el": 0.32, "color": 0xfffdf2, "size": 940 },
  # The disc is low; the key light is not, or nothing gets lit.
  "light": { "color": 0xfff6e6, "intensity": 1.62,
           "dir": [math.sin(1.9) * 0.72, 0.69, math.cos(1.9) * 0.72] },
  # The ground colour is sand on purpose: over a desert the bounce
  # light really is warm, and it puts a glow on every underside.
  "hemi": { "sky": 0xdfeaf7, "ground": 0xd6ac78, "intensity": 0.78 },
  "fog": 0xdfc79b, "fogNear": 320, "fogFar": 1500,
},
"below": { "kind": 'desert', "deck": 108, "reach": 980,
         "duneDensity": 0.4, "mesaDensity": 0.55, "rockDensity": 0.18,
         "sand": 0xd9b478, "rock": 0xb26a44 } }
