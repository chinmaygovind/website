"""What Sandy Cove looks like."""

import math

# The waterline, from the track itself. **This import is the point of the whole
# palette move.** The coast road is authored to run in a band just inland of this
# line and the pier is the one thing that crosses it, so the number belongs to the
# geometry - and while the palette was a JavaScript object it existed twice, in two
# languages, held together by a test that scraped trackmesh.js with a regex.
from tracks.cove.track import SHORE_AMP, SHORE_WAVE, SHORE_Z

PALETTE = { "road": 0x6b6f78, "kerb": 0xfffaf0, "kerb2": 0x2ab7c8,
"ground": 0xffe87a, "rail": 0xfff6e8, "prop": 0x3f7d4a, "deco": 0xffb03a,
"fog": 0xcfe4ea,
# Sparse. A beach is mostly empty sand, and the first pass was a
# palm plantation. No `block` either - a green crate on a beach
# reads as a crate on a beach.
"density": 0.035,
"props": { "palm": 0.56, "rock": 0.32, "deadtree": 0.12 },
# Kept in step with SHORE_Z / SHORE_AMP / SHORE_WAVE in tracks.py
# by test_the_waterline_agrees_with_the_track: the road is
# authored against this line, so a drift inland floods it.
"shore": { "axis": 'z', "at": SHORE_Z, "amp": SHORE_AMP,
         "wave": SHORE_WAVE, "reach": 900,
         "sea": 0x1f7fa8, "deep": 0x11527a, "foam": 0x9fe0ea, "drop": 3.0 },
"sky": {
  "stops": [
    [0.00, 0x8fb6c4], [0.40, 0xbfe0e8], [0.50, 0xd8eef2],
    [0.58, 0xa8d6ee], [0.74, 0x6fb0e4], [1.00, 0x2f7ac4],
  ],
  "glow": 0xfff0c8, "glowStrength": 0.55, "glowMode": 'radial', "glowFocus": 7,
  "sun": { "az": 1.9, "el": 0.62, "color": 0xfff3d2, "size": 260 },
  "light": { "color": 0xfff4de, "intensity": 1.5,
           "dir": [math.sin(1.9) * 0.6, 0.86, math.cos(1.9) * 0.6] },
  # Bounce off pale sand, which is what makes everything here
  # look hot rather than merely bright.
  "hemi": { "sky": 0xd6efff, "ground": 0xffdc72, "intensity": 1.08 },
  "fog": 0xcfe4ea, "fogNear": 320, "fogFar": 1600,
} }
