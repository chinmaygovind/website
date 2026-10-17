"""What Harbor looks like.

Night in a cove: weathered wood under a deep teal sky that stays teal from the
horizon to the top, black water, and ghost green as the only light that is not
the moon. The water is Citadel's lava floor with the fire swapped for a
near-black teal and the crust taken off.
"""

import math

from tracks.harbor.track import WATER_DECK

MOON_AZ = 2.4

PALETTE = {
    "road": 0xc87a4c,
    "kerb": 0x56c890,
    "kerb2": 0x2e2018,
    "ground": 0x0a1616,
    "rail": 0x8a6448,
    "prop": 0x3a2e24,
    "prop2": 0x514234,
    "deco": 0x7dffb4,
    "fog": 0x081d1e,
    "density": 0.0,
    "pad": 0x8affc2,
    "padBase": 0x12302a,
    # The pilings are drawn by scenery.js, down to the water.
    "legs": 0,
    "sky": {
        "stops": [
            [0.00, 0x010607], [0.46, 0x061a1c], [0.50, 0x0e2f30],
            [0.56, 0x0c2a2b], [0.70, 0x0a2527], [0.86, 0x06191b],
            [1.00, 0x031012],
        ],
        "stars": {"count": 700, "seed": 33, "size": 1.8},
        "glow": 0xb8e8d8, "glowStrength": 0.2, "glowMode": "radial",
        "glowFocus": 11,
        "sun": {"az": MOON_AZ, "el": 0.32, "color": 0xdff5ec, "size": 170},
        "light": {"color": 0xc4ccd0, "intensity": 1.0,
                  "dir": [math.sin(MOON_AZ) * 0.4, 0.84, math.cos(MOON_AZ) * 0.4]},
        "hemi": {"sky": 0x3e4e52, "ground": 0x2e4a3e, "intensity": 0.85},
        "fog": 0x081d1e, "fogNear": 160, "fogFar": 700,
    },
    "below": {
        "kind": "lava", "deck": WATER_DECK, "kill": True, "reach": 500,
        "crustCover": 0.0, "spireDensity": 0.12, "crust": 0x1c2426,
        "lava": 0x020b0c,
    },
    "lamps": {
        "count": 6, "color": 0x7dffb4, "intensity": 2.2, "range": 55,
        "runs": [
            {"from": 0.0, "to": 1.0, "every": 14, "off": 10, "up": 5,
             "bare": True},
        ],
    },
}
