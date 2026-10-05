"""What Citadel looks like.

**The Gauntlet's world, because that was the brief.** The first pass was a
dark red ceiling over a bare lava plane, and next to The Gauntlet it looked
flat: an empty lake is one orange quad, and a one-colour sky has nothing to
read against. So the sky, light and cloud deck here are The Gauntlet's, and the
lake is mostly crust with the fire in the cracks - laid by `scenery.js` rather
than by `below`, see there. Gold and crimson are the only colours on the kerb.
"""

from tracks.citadel.track import LAVA_DECK

PALETTE = {
    "road": 0x50555e,
    "kerb": 0xd9b04a,
    "kerb2": 0x9e2219,
    "ground": 0x1a1617,
    "rail": 0x6a625f,
    "prop": 0x2e2a2b,
    "prop2": 0x3b3536,
    "deco": 0xff7a1a,
    "fog": 0x2a222a,
    "density": 0.0,
    "pad": 0xffc23a,
    "padBase": 0x3a1612,
    # A fortress stands on its own walls; the engine's steel trestles under
    # every groundless station would be a pier.
    "legs": 0,
    # The Gauntlet's sky, which is the look this was asked to match: a brown
    # horizon glowing off the lava and a near-black zenith, a cool key light so
    # the crust reads as stone, and the lava's own orange as the bounce.
    "sky": {
        "stops": [
            [0.00, 0x3d1c10], [0.40, 0x4a2314], [0.50, 0x5a2c18],
            [0.56, 0x3a3038], [0.66, 0x2b2831], [0.82, 0x1e1c25],
            [1.00, 0x14131b],
        ],
        "light": {"color": 0xa9b0c4, "intensity": 0.9, "dir": [0.32, 0.9, 0.28]},
        "hemi": {"sky": 0x39404f, "ground": 0xc2400f, "intensity": 1.0},
        "fog": 0x2a222a, "fogNear": 190, "fogFar": 780,
    },
    "below": {
        "kind": "lava", "deck": LAVA_DECK, "kill": True, "reach": 500,
        "crustCover": 0.0, "spireDensity": 0.0,
        "lava": 0xff5510,
        "above": {"deck": 120, "cover": 0.5, "cloud": 0x2a2731},
    },
}
