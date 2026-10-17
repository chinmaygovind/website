"""What Starport looks like: a station in deep space, neon on dark hull."""

import math

PALETTE = {
    "road": 0x2a3042,
    "kerb": 0x2ef2ff,
    "kerb2": 0xff2fc8,
    "ground": 0x0a0c1a,
    "rail": 0x9fe8ff,
    "prop": 0x2b3146,
    "prop2": 0x3a4258,
    "deco": 0x2ef2ff,
    "fog": 0x0b0d24,
    "density": 0.0,
    "pad": 0x5cf6ff,
    "padBase": 0x18203a,
    # The station holds itself up; module hulls in scenery.js, no trestles.
    "legs": 0,
    # Navy at the bottom to indigo overhead, one family the whole way.
    "sky": {
        "stops": [
            [0.00, 0x04050f], [0.40, 0x080a1e], [0.50, 0x0d1030],
            [0.62, 0x110f38], [0.80, 0x0e0b2e], [1.00, 0x07061a],
        ],
        "glow": 0x8f9cff, "glowStrength": 0.2, "glowMode": "radial", "glowFocus": 10,
        "stars": {"count": 2400, "seed": 310, "size": 2.3},
        "sun": {"az": 2.6, "el": 0.38, "color": 0xdfe6ff, "size": 140},
        "light": {"color": 0xb4c2ff, "intensity": 1.0,
                  "dir": [math.sin(2.6) * 0.7, 0.68, math.cos(2.6) * 0.7]},
        "hemi": {"sky": 0x6a74c8, "ground": 0x8a2a9a, "intensity": 1.1},
        "fog": 0x0b0d24, "fogNear": 300, "fogFar": 1400,
    },
    "below": {"kind": "void"},
}
