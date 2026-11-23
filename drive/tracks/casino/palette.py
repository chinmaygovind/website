"""What High Roller looks like: a windowless casino floor at no particular hour.

Deep red carpet, green felt, gold trim, warm chandeliers far overhead. The room
itself (walls, ceiling, chandeliers, tables) is drawn by `scenery.js`; the sky
here is only what shows if a wall is ever missed, so it is kept as dark as the
ceiling.
"""

PALETTE = {
    "road": 0x1e2130,
    "kerb": 0xd8b44a,
    "kerb2": 0x141418,
    "ground": 0x5a1420,
    "rail": 0x3a1810,
    "prop": 0x4a2418,
    "prop2": 0x3a1c14,
    "deco": 0xf0c040,
    "fog": 0x1a0f10,
    "pad": 0xffd24a,
    "padBase": 0x2a0c08,
    "density": 0,
    # The chip-stack pillars in scenery.js hold the raised road up instead.
    "legs": 0,
    "sky": {
        "stops": [
            [0.00, 0x1a0e0e], [0.20, 0x1c1010], [0.45, 0x1e1212],
            [0.55, 0x1a1010], [0.75, 0x140c0c], [1.00, 0x0c0808],
        ],
        "glow": 0xffc070, "glowStrength": 0.12, "glowMode": "horizon",
        "glowFocus": 12,
        "sun": {"az": 1.0, "el": 0.9, "color": 0xffe6c0, "size": 1},
        "light": {"color": 0xffe2b8, "intensity": 0.78,
                  "dir": [0.25, 0.92, 0.30]},
        "hemi": {"sky": 0x8a6a4a, "ground": 0x4a2020, "intensity": 0.95},
        "fog": 0x1a0f10, "fogNear": 260, "fogFar": 1100,
    },
}
