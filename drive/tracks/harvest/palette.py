"""What Harvest looks like.

Golden hour on a country lane in October. The sky is one warm family, amber at
the horizon to a dusky apricot overhead, because a blue dome over an orange
horizon is the two-tone sky this pool has already rejected. The colour is in
the trees: maple red and orange in the scatter, with a few evergreens and bare
trees as seasoning, and a run-off of fallen leaves either side of the road.
"""

import math

SUN_AZ = 2.4

PALETTE = {
    "road": 0x3c4558, "kerb": 0xf2ece0, "kerb2": 0xb23c1c,
    # The verge: grass going over, olive rather than green.
    "ground": 0x6f7a30,
    "rail": 0x6a4a30,
    # Maple red and maple orange: `broadleaf` takes one or the other per tree.
    "prop": 0xb8261a, "prop2": 0xe0701c,
    "deco": 0x8c3418,
    # Run-off is a carpet of fallen leaves.
    "gravel": 0xb8642a,
    "fog": 0xe6b48a,
    # No armco: the fence is posts and rails, drawn and collided in scenery.js.
    "terrain": {"apron": 30, "gravel": 12, "armco": 0, "clear": 30},
    "density": 0.30,
    "props": {"broadleaf": 0.78, "conifer": 0.10, "deadtree": 0.07, "rock": 0.05},
    "leaves": {
        "every": 55,
        "colors": [0xc8321e, 0xe0661c, 0xf0a020, 0x9a3a1a, 0xd84a1c],
        "drift": 10,
    },
    "sky": {
        "stops": [
            [0.00, 0xd89a6a], [0.42, 0xf2c48a], [0.50, 0xffdca0],
            [0.56, 0xf6c088], [0.72, 0xe0a070], [1.00, 0xb87a5a],
        ],
        "clouds": {"scale": 2.2, "amount": 0.30, "dark": 0xd08c66,
                   "light": 0xffe6bc, "lit": 0.22},
        "glow": 0xffe2a8, "glowStrength": 0.6, "glowMode": "radial",
        "glowFocus": 5,
        "sun": {"az": SUN_AZ, "el": 0.16, "color": 0xfff0c8, "size": 320},
        "light": {"color": 0xffdcaa, "intensity": 1.35,
                  "dir": [math.sin(SUN_AZ) * 0.92, 0.38, math.cos(SUN_AZ) * 0.92]},
        # Warm and bright enough underneath that the tunnel canopy's underside
        # reads as leaves, not as a black ceiling.
        "hemi": {"sky": 0xf4cc96, "ground": 0x9a6436, "intensity": 1.0},
        "fog": 0xe6b48a, "fogNear": 300, "fogFar": 1500,
    },
}
