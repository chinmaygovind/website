"""What Frost looks like.

Mount Joy's snow light (a bounce nearly as bright as the sky) on a pine
mountainside, under a sky that stays blue from the horizon to the zenith.
"""

PALETTE = {
    "road": 0x3a404c,
    "kerb": 0xf4f8fc, "kerb2": 0x2f78d6,
    "ground": 0xdbe6f2,
    "snow": 0xf6fbff,
    "gravel": 0xc4d4e6,
    "rail": 0xe8eef6,
    "prop": 0x1f4a36, "prop2": 0x183b2c,
    "deco": 0xf08a30,
    "pad": 0x6fd8ff, "padBase": 0x1c3d66,
    "fog": 0xcfdcea,
    "terrain": {"apron": 34, "gravel": 20, "armco": 26, "clear": 40},
    "density": 0.26,
    "props": {"bigpine": 0.45, "conifer": 0.4, "rock": 0.15},
    "sky": {
        "stops": [
            [0.00, 0xc6d6e8], [0.40, 0xd2e0ef], [0.50, 0xd8e5f2],
            [0.58, 0xb4cde8], [0.74, 0x7fa8db], [1.00, 0x3f6fb8],
        ],
        "glow": 0xf2f7ff, "glowStrength": 0.4, "glowMode": "radial",
        "glowFocus": 6,
        "sun": {"az": 2.1, "el": 0.55, "color": 0xfbfdff, "size": 280},
        "light": {"color": 0xf2f6ff, "intensity": 1.3, "dir": [-0.45, 0.8, 0.38]},
        "hemi": {"sky": 0xd8e7f8, "ground": 0xc2d4e8, "intensity": 1.05},
        "fog": 0xcfdcea, "fogNear": 280, "fogFar": 1500,
    },
}
