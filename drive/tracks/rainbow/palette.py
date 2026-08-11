"""What Rainbow Road looks like."""

import math

PALETTE = { "road": 0x6a4bd0, "kerb": 0xffffff, "kerb2": 0x2a2140,
"ground": 0x140a2e, "rail": 0xf2ecff, "prop": 0x3a2470, "deco": 0x62f0ff,
"fog": 0x120a28,
# Degrees of hue per station, and no banding. Hard bands were the
# fix for a per-station step that looked like a flat gradient
# carpet, but the real problem was the *rate*: at this much
# slower sweep the road is a long smooth wash of colour, and the
# shading across its width (see `roadColor`) is what stops it
# reading flat.
"rainbow": 2.2,
"sky": {
  # Purple rather than black. A true black dome makes the road
  # the only colour anywhere and the world around it reads as
  # nothing; a deep violet keeps it space while giving the stars
  # and the ribbon something to sit against.
  "stops": [
    [0.00, 0x0d0620], [0.42, 0x1a0c38], [0.50, 0x271252],
    [0.60, 0x22104a], [0.78, 0x150932], [1.00, 0x080418],
  ],
  # A tight halo, and it is a distant star rather than a sun -
  # big and warm here would read as a sunrise, which is the one
  # thing deep space is not.
  "glow": 0xb98cff, "glowStrength": 0.38, "glowMode": 'radial', "glowFocus": 10,
  "stars": { "count": 2200, "seed": 77, "size": 2.3 },
  "sun": { "az": 2.1, "el": 0.42, "color": 0xdfe8ff, "size": 150 },
  # Starlight: cold and weak, but not so weak that the car goes
  # black. The road is unlit and lights nothing by itself, so
  # everything solid in the scene is lit by these two alone.
  "light": { "color": 0xaebcff, "intensity": 1.0,
           "dir": [math.sin(2.1) * 0.7, 0.68, math.cos(2.1) * 0.7] },
  "hemi": { "sky": 0x8a6ad0, "ground": 0xc0308a, "intensity": 1.15 },
  "fog": 0x120a28, "fogNear": 300, "fogFar": 1500,
},
"below": { "kind": 'void' } }
