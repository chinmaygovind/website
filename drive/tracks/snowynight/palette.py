"""What Snowy Night looks like: Brumm's pine forest under fresh snow, at night."""

import math

MOON_AZ = 0.05
FOG = 0x1a2a48
SKY = {
    "stops": [[0.00, 0x050a18], [0.46, 0x1c2c50], [0.50, 0x3a5288],
              [0.56, 0x22366a], [0.70, 0x111d3e], [1.00, 0x040818]],
    "stars": {"count": 1100, "seed": 7, "size": 1.8},
    "glow": 0xbcd0f4, "glowStrength": 0.45, "glowMode": "radial", "glowFocus": 7,
    "sun": {"az": MOON_AZ, "el": 0.32, "color": 0xf2f6ff, "size": 200},
    "light": {"color": 0xb8c8ec, "intensity": 0.9,
              "dir": [math.sin(MOON_AZ) * 0.5, 0.8, math.cos(MOON_AZ) * 0.5]},
    "hemi": {"sky": 0x9fb4dc, "ground": 0x6a7c9c, "intensity": 0.95},
    "fog": FOG, "fogNear": 240, "fogFar": 1200,
}

PALETTE = {
    "road": 0x3f4653,
    "kerb": 0xffffff,
    "kerb2": 0x3d8bfd,
    "ground": 0xdfe7f2,
    "rail": 0xf4f8ff,
    "prop": 0x244a39,
    "prop2": 0x1f4434,
    "snow": 0xf4f9ff,
    "deco": 0x7fb6e8,
    "fog": FOG,
    "density": 0.26,
    "props": {"bigpine": 0.34, "conifer": 0.3, "deadtree": 0.22, "rock": 0.14},
    "sky": SKY,
    "snowfall": {"count": 1400, "speed": 4, "size": 0.9, "wind": [1.5, 0.6],
                 "sway": 1.2},
}
