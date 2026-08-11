"""What Jump City looks like."""

import math

PALETTE = { "road": 0x434a58, "kerb": 0xf2f4f8, "kerb2": 0xf2c94c,
"ground": 0x5c6070, "rail": 0xeef2f8, "prop": 0x6b7180, "deco": 0xf2c94c,
"fog": 0x3f4a6b,
"sky": {
  "stops": [
    [0.00, 0x241d33], [0.42, 0x5b3f52], [0.48, 0xa85f57],
    [0.51, 0xd98a58], [0.55, 0xa96a6a], [0.64, 0x62537f],
    [0.78, 0x30356b], [1.00, 0x131a41],
  ],
  "glow": 0xffb478, "glowStrength": 0.95,
  "sun": { "az": -1.15, "el": 0.012, "color": 0xffc98a, "size": 300 },
  "light": { "color": 0xdfd4f0, "intensity": 0.72,
           "dir": [math.sin(-1.15) * 0.86, 0.5, math.cos(-1.15) * 0.86] },
  # Dusk is mostly sky light, and the sky is blue - so the ambient
  # does the work here and the key light barely does any.
  "hemi": { "sky": 0x6f7ec2, "ground": 0x1a1f38, "intensity": 1.05 },
  "fog": 0x3f4a6b, "fogNear": 260, "fogFar": 1250,
},
"below": { "kind": 'downtown', "deck": 118, "reach": 620, "step": 4,
         "coreX": 40, "coreZ": 150, "coreR": 330,
         "low": 46, "spread": 74, "rise": 165,
         "landmarkX": -30, "landmarkZ": 20, "landmarkH": 330,
         "tower": 0x36435c, "window": 0xffd79a, "floor": 0x141a2b } }
