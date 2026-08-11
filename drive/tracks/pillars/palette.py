"""What Cloudbreak looks like."""

import math

PALETTE = { "road": 0x4a4e5a, "kerb": 0xf4f2ee, "kerb2": 0xe07a3c,
"ground": 0x6d6154, "rail": 0xf6f2ea, "prop": 0x6a5c4c, "deco": 0xffc247,
"fog": 0xc2cdd8,
"sky": {
  "stops": [
    [0.00, 0x9aa8b6], [0.42, 0xc4d2de], [0.50, 0xdce7f0],
    [0.60, 0xa9c4de], [0.78, 0x6d97c2], [1.00, 0x3d6a9c],
  ],
  "glow": 0xfff0d8, "glowStrength": 0.5, "glowMode": 'radial', "glowFocus": 6,
  "sun": { "az": 0.7, "el": 0.5, "color": 0xfff2dc, "size": 240 },
  "light": { "color": 0xfff0dc, "intensity": 1.3,
           "dir": [math.sin(0.7) * 0.7, 0.78, math.cos(0.7) * 0.7] },
  # Bounce off cloud: bright and neutral, so undersides stay
  # readable instead of going black over a white floor.
  "hemi": { "sky": 0xdcebf8, "ground": 0xb8c4d0, "intensity": 1.0 },
  "fog": 0xc2cdd8, "fogNear": 380, "fogFar": 2000,
},
# Fewer and much bigger. The first pass was a thicket of thin
# poles: from road level a spire has to be wide enough to read as
# rock and tall enough to stand *beside* you rather than under
# you, or the track is not threaded between anything.
# The deck is a long way down so you look *onto* it rather than
# along it, and `cover` leaves real gaps - an even layer of
# anything is the one thing cloud can never be. `floor` is
# deliberately absent: see pillarsBelow.
"below": { "kind": 'pillars', "deck": 145, "reach": 900,
         "cover": 0.34, "cloud": 0xeef4fa,
         "puff": 2.1, "cloudStep": 13,
         "spireStep": 12, "spireDensity": 0.62, "rise": 104, "root": 110,
         "rock": 0x5f5244 } }
