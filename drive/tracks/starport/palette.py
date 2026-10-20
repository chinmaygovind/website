"""What Starport looks like: a working station in low orbit over a blue planet.

Dark deck plating with white and orange edges, so the road reads as industrial
rather than neon. The planet is built in `scenery.js`; the sky only supplies
black space overhead and the atmosphere's rim glow, which sits in the band just
below the horizon where the planet's limb is seen from the track.
"""

import math

# The sun's bearing, shared by the disc, the key light and the planet's day side
# (`scenery.js` reads `sky.sun.az`).
SUN_AZ = 2.5

PALETTE = {
    "reentry": True,
    "road": 0x3e444f,
    "kerb": 0xeef1f4,
    "kerb2": 0xd8471c,
    "ground": 0x0b1020,
    "rail": 0x9aa2ae,
    # Hull plating, and its darker trim.
    "prop": 0xc4c9d0,
    "prop2": 0x5a6170,
    # Running lights.
    "deco": 0xe0841c,
    "fog": 0x0a1428,
    "density": 0.0,
    "pad": 0x6fe0ff,
    "padBase": 0x1a2a44,
    "legs": 0,
    "sky": {
        # Black space overhead, and a pale blue band under the horizon where the
        # planet's limb sits: the atmosphere seen edge-on.
        "stops": [
            [0.00, 0x0a1830], [0.30, 0x12325e], [0.38, 0x3f86c4],
            [0.42, 0x8cc8ee], [0.47, 0x24477a], [0.52, 0x0a1226],
            [0.70, 0x05070f], [1.00, 0x020308],
        ],
        "glow": 0xfff2d8, "glowStrength": 0.3, "glowMode": "radial",
        "glowFocus": 12,
        "stars": {"count": 2600, "seed": 310, "size": 2.1},
        "sun": {"az": SUN_AZ, "el": 0.32, "color": 0xfffaf0, "size": 120},
        "light": {"color": 0xfff6ea, "intensity": 1.35,
                  "dir": [math.sin(SUN_AZ) * 0.6, 0.8, math.cos(SUN_AZ) * 0.6]},
        # Planet-shine from below: a desaturated blue, enough to light the
        # undersides of the station and no more.
        "hemi": {"sky": 0x9aa8c8, "ground": 0x6f8db0, "intensity": 0.95},
        "fog": 0x0a1428, "fogNear": 700, "fogFar": 2500,
    },
    "below": {"kind": "void"},
}
