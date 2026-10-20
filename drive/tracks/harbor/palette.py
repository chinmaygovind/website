"""What Harbor looks like.

Night in a haunted cove. Three lights and they do not mix: a cold moon low over
the open sea with a path of it lying across the water, warm lanterns on the
docks and the galleon, and ghost green in the gun ports, the skull's eyes and
the cannon pads. The sky is navy and the water is teal, so the two never read
as one value again. The water itself is drawn by scenery.js off `ground`
(trough colour, on screen), `below.lava` (the deep, past the drawn sea) and the
moon's colour; `below` is only here to make the surface a respawn.
"""

import math

from tracks.harbor.track import LAMP_EVERY, LAMP_OFF, LAMP_UP, WATER_DECK

MOON_AZ = 1.9

PALETTE = {
    "road": 0xa8703e,
    "kerb": 0xc4bba6,
    "kerb2": 0x2b2724,
    "ground": 0x0e3b4a,
    "rail": 0x8a6c54,
    "prop": 0x705a48,
    "prop2": 0xb4c4be,
    "deco": 0xffb35c,
    "fog": 0x1a2840,
    "density": 0.0,
    "pad": 0x7dffb4,
    "padBase": 0x12302a,
    # The pilings are drawn by scenery.js, down to the water.
    "legs": 0,
    "sky": {
        "stops": [
            [0.00, 0x04070f], [0.46, 0x14203a], [0.50, 0x2a3c5e],
            [0.55, 0x1c2a48], [0.66, 0x111b34], [0.82, 0x0a1126],
            [1.00, 0x050918],
        ],
        "stars": {"count": 900, "seed": 33, "size": 1.8},
        "glow": 0x8ea6d0, "glowStrength": 0.32, "glowMode": "radial",
        "glowFocus": 9,
        "sun": {"az": MOON_AZ, "el": 0.2, "color": 0xeef2ff, "size": 130},
        "light": {"color": 0xc4cde0, "intensity": 1.1,
                  "dir": [math.sin(MOON_AZ) * 0.5, 0.8, math.cos(MOON_AZ) * 0.5]},
        "hemi": {"sky": 0x46587c, "ground": 0x2c3a48, "intensity": 0.95},
        "fog": 0x1a2840, "fogNear": 240, "fogFar": 1250,
    },
    "water": {
        "deck": WATER_DECK, "chop": 0.8,
        "deep": 0x03141d, "shallow": 0x0f4a58, "glintPower": 90, "glint": 0x7a8498, "foam": 0,
    },
    "below": {
        "kind": "lava", "deck": WATER_DECK, "kill": True, "reach": 500,
        "crustCover": 0.0, "spireDensity": 0.0, "crust": 0x353d46,
        "lava": 0x01070b,
    },
    "lamps": {
        "count": 8, "color": 0xffb060, "intensity": 2.6, "range": 40,
        "runs": [
            {"from": 0.0, "to": 1.0, "every": LAMP_EVERY, "off": LAMP_OFF,
             "up": LAMP_UP, "bare": True},
        ],
    },
}
