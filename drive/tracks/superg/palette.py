"""What Super-G looks like: Brumm's piste down between glacier walls, bright noon."""

FOG = 0xd4e2f0
SKY = {
    "stops": [[0.00, 0xcfdcea], [0.40, 0xdbe7f3], [0.50, 0xe4eef8],
              [0.56, 0xa9cbee], [0.72, 0x5f97de], [1.00, 0x2459b0]],
    "glow": 0xffffff, "glowStrength": 0.5, "glowMode": "radial", "glowFocus": 6,
    "sun": {"az": 2.1, "el": 0.55, "color": 0xfbfdff, "size": 280},
    "light": {"color": 0xf2f6ff, "intensity": 1.35, "dir": [-0.45, 0.8, 0.38]},
    "hemi": {"sky": 0xd8e7f8, "ground": 0xc2d4e8, "intensity": 1.05},
    "fog": FOG, "fogNear": 280, "fogFar": 1500,
}

PALETTE = {
    "road": 0xffffff,
    "kerb": 0x52d6fc,
    "kerb2": 0x52d6fc,
    "ground": 0xe6eef7,
    "snow": 0xf6fbff,
    "gravel": 0xd2e0ee,
    "rail": 0xe8eef6,
    "prop": 0x1f4a36,
    "prop2": 0x183b2c,
    "deco": 0xf08a30,
    "pad": 0x6fd8ff,
    "padBase": 0x1c3d66,
    "fog": FOG,
    "terrain": {"apron": 34, "gravel": 20, "armco": 26, "clear": 40,
                "ice": 0x5ec8ff},
    "density": 0.26,
    "props": {"bigpine": 0.45, "conifer": 0.4, "rock": 0.15},
    "sky": SKY,
    "snowfall": {"count": 500, "speed": 3, "size": 0.7, "wind": [1.0, 0.4],
                 "sway": 1.0},
}
