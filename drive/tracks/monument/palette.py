"""What Monument looks like.

A humid green noon over a jungle river. The sky is one hue, pale jade at the
horizon deepening to a muted teal overhead, and the fog is the horizon colour so
the haze closes the distance. The river is `below: lava` recoloured: an unlit
jade plane with mossy boulders in it and karst pillars standing out of it,
which is the floor of the world and a respawn.
"""

from tracks.monument.track import WATER_DECK

PALETTE = {
    "road": 0x6a6758,
    "kerb": 0xd8b24c,
    "kerb2": 0x2f7a58,
    "ground": 0x3e5a3c,
    "rail": 0xb6a67c,
    "prop": 0x3a5a36,
    "prop2": 0x7a7058,
    "deco": 0xe2b84a,
    "fog": 0xb4cfc0,
    "density": 0.0,
    "pad": 0xf2cc4a,
    "padBase": 0x24402e,
    # Stone columns come from scenery.js; trestles under a temple would be a pier.
    "legs": 0,
    "sky": {
        "stops": [
            [0.00, 0x8fb2a2], [0.40, 0xa9c7b8], [0.50, 0xc2dccd],
            [0.58, 0xaccdbf], [0.72, 0x8cb9aa], [0.88, 0x6fa595],
            [1.00, 0x5c9484],
        ],
        "glow": 0xf2f6dc, "glowStrength": 0.35, "glowMode": "radial",
        "glowFocus": 6,
        "sun": {"az": 2.3, "el": 0.7, "color": 0xf6f8e2, "size": 260},
        "light": {"color": 0xf2f4e0, "intensity": 1.3,
                  "dir": [0.45, 0.82, -0.32]},
        "hemi": {"sky": 0xcfe6da, "ground": 0x7ea47a, "intensity": 1.0},
        "fog": 0xb4cfc0, "fogNear": 220, "fogFar": 1100,
    },
    "below": {
        "kind": "lava", "deck": WATER_DECK, "kill": True, "reach": 500,
        "lava": 0x0e3a31, "crust": 0x4a5e3c,
        "crustCover": 0.0, "spireDensity": 0.0,
    },
}
