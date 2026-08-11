"""What Sunrise Circuit looks like."""

import math

SUNRISE_AZ = 2.42

PALETTE = {
  # Bases are cooler than they look, because the key light is warm and a
  # neutral grey road mixes down to mud under it. Worth knowing why the
  # compensation has to be this strong: three converts a light's colour from
  # sRGB to linear, but MeshBuf writes vertex colours straight into the
  # buffer unconverted, so a light that reads as a gentle cream in hex is a
  # much deeper orange by the time it multiplies the geometry.
  "road": 0x4d5769, "kerb": 0xf2ece4, "kerb2": 0xe8453c,
  "ground": 0x4ea363, "rail": 0xf2eee8, "prop": 0x27664a, "deco": 0xf2c94c,
  "fog": 0xf0b98a,
  "sky": {
    # Straight down is haze, the horizon burns, and it cools all the way to a
    # deep blue overhead that still has night in it.
    "stops": [
      [0.00, 0x8a6a5e], [0.38, 0xd08a63], [0.46, 0xf0a469],
      [0.50, 0xffc98c], [0.55, 0xf3ab7d], [0.63, 0xd28f92],
      [0.72, 0x9d8bb4], [0.84, 0x5f76b8], [1.00, 0x27418c],
    ],
    "glow": 0xffd39a,
    "glowStrength": 0.92,
    "sun": { "az": SUNRISE_AZ, "el": 0.05, "color": 0xffd39a, "size": 430 },
    # No cloud here on purpose. Boxes seen from below at a shallow angle read
    # as pale rectangles no matter how they are shaded, and the graded dome,
    # the disc and the glow already carry the whole sky. `clouds` in
    # render.js is for the tracks that float, where you look *down* on it.
    # Low and warm, from the same bearing as the disc.
    "light": { "color": 0xfff1e0, "intensity": 1.45,
             "dir": [math.sin(SUNRISE_AZ) * 0.9, 0.44, math.cos(SUNRISE_AZ) * 0.9] },
    "hemi": { "sky": 0xffeadb, "ground": 0x50506a, "intensity": 0.7 },
    # Far enough out that the near field keeps its own colour and only the
    # distance dissolves into the haze.
    "fog": 0xf0b98a, "fogNear": 340, "fogFar": 1500,
  },
}
