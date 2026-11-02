"""Looks only the dailies wear.

Every daily used to borrow one of the pool's palettes whole (`generate.borrow`),
so after forty days every world had been seen several times over - "change the
theme" and "make the theme more interesting" were review notes. These are
places the pool does not have. They go through `generate.borrow` like any
other look, so the same keys are stripped and the scatter density redrawn.

Each sky stays in one hue family, lighter at the horizon and deeper overhead -
a blue dome over an orange horizon was tried on Drive and rejected.
A look with a `below` makes a stunt track over the void; one without makes a
circuit on the ground (`generate.is_void`).
"""

import math


def _sky(stops, glow, sun_az, sun_el, sun, light, hemi_sky, hemi_ground, fog,
         intensity=1.3, near=320, far=1500):
    return {
        "stops": stops,
        "glow": glow, "glowStrength": 0.6, "glowMode": "radial", "glowFocus": 5,
        "sun": {"az": sun_az, "el": sun_el, "color": sun, "size": 320},
        "light": {"color": light, "intensity": intensity,
                  "dir": [math.sin(sun_az) * 0.8, 0.6, math.cos(sun_az) * 0.8]},
        "hemi": {"sky": hemi_sky, "ground": hemi_ground, "intensity": 0.9},
        "fog": fog, "fogNear": near, "fogFar": far,
    }


LOOKS = [
    # Late October in a beech wood: rust and gold canopy on olive grass, under
    # a pale amber haze.
    {"slug": "autumn", "name": "Autumn", "pal": {
        "road": 0x4b5468, "kerb": 0xf2ece2, "kerb2": 0xc8502c,
        "ground": 0x7a8a3e, "rail": 0xefe6d8, "prop": 0xc4561e, "prop2": 0xd8961e,
        "deco": 0xe8a83a, "fog": 0xe3c9a0, "density": 0.08,
        "props": {"broadleaf": 0.6, "bigpine": 0.15, "deadtree": 0.1, "rock": 0.15},
        "sky": _sky([[0.00, 0xcdb79a], [0.40, 0xe3c9a0], [0.50, 0xf0d8b0],
                     [0.62, 0xe6c28e], [0.80, 0xd4a46c], [1.00, 0xb8864e]],
                    0xffe2b0, 2.0, 0.32, 0xffe6bc, 0xfff0dc,
                    0xf6e2c4, 0x6a6040, 0xe3c9a0),
    }},
    # Spring under cherry trees: pink canopy on fresh green, a soft blue sky.
    {"slug": "blossom", "name": "Blossom", "pal": {
        "road": 0x4d5669, "kerb": 0xf6f2f2, "kerb2": 0xe0607e,
        "ground": 0x6fb058, "rail": 0xf6eef0, "prop": 0xf2a0bc, "prop2": 0xf7c8d8,
        "deco": 0xf7d2de, "fog": 0xd8e4f0, "density": 0.09,
        "props": {"broadleaf": 0.75, "conifer": 0.1, "rock": 0.15},
        "sky": _sky([[0.00, 0xc4d4e4], [0.40, 0xd8e4f0], [0.50, 0xe6eef7],
                     [0.62, 0xbcd4ec], [0.80, 0x8cb6e2], [1.00, 0x5e92d2]],
                    0xfff4f6, 1.1, 0.55, 0xfffaf6, 0xfff6f2,
                    0xeef2f8, 0x5d6a52, 0xd8e4f0),
    }},
    # Midday on the savanna: straw-gold grass, flat-topped thorn trees and
    # boulders, under a bleached sky.
    {"slug": "savanna", "name": "Savanna", "pal": {
        "road": 0x4a5266, "kerb": 0xf4eee0, "kerb2": 0xd0602a,
        "ground": 0xc8a656, "rail": 0xf0e8d6, "prop": 0x5a6e2c, "prop2": 0x7a8236,
        "deco": 0xe8c050, "fog": 0xe8dcc0, "density": 0.04,
        "props": {"palm": 0.15, "deadtree": 0.35, "broadleaf": 0.2, "rock": 0.3},
        "sky": _sky([[0.00, 0xd8ccb0], [0.40, 0xe8dcc0], [0.50, 0xf2e8d0],
                     [0.62, 0xd8dcd8], [0.80, 0xa8c4dc], [1.00, 0x7aa6d2]],
                    0xfffae8, 0.6, 0.9, 0xfffcf0, 0xfffaf0,
                    0xf4ecdc, 0x7a6a48, 0xe8dcc0, intensity=1.4),
    }},
    # Synthwave night, floating: a violet dark with magenta and cyan edges.
    {"slug": "neon", "name": "Neon", "pal": {
        "road": 0x2a2440, "kerb": 0xff4fd8, "kerb2": 0x3ae8ff,
        "ground": 0x150c26, "rail": 0x3ae8ff, "prop": 0x6a2a9a, "prop2": 0x2a1840,
        "deco": 0xff4fd8, "fog": 0x1a0e30, "density": 0.0,
        "pad": 0x3ae8ff,
        "sky": _sky([[0.00, 0x2a1448], [0.40, 0x3c1a5e], [0.50, 0x5a2478],
                     [0.60, 0x3a1860], [0.80, 0x1e0e3c], [1.00, 0x0e0620]],
                    0xff6ad8, 3.4, 0.08, 0xff7ae0, 0xd8b8ff,
                    0x8a6ac8, 0x3a2060, 0x1a0e30, intensity=1.1, near=500,
                    far=1800),
        "below": {"kind": "void"},
    }},
]
