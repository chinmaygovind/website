"""What Dino Park looks like.

A hot, high, humid noon. The sky is the one thing taken straight from the
reference and not softened: pale and slightly green at the horizon where the
haze off the canopy sits, and **properly deep cobalt at the zenith**, because a
jungle sky photographed from the floor of a gorge is exactly that - and a
pale-all-over dome would have made the same scene read as overcast, which is the
one weather this track must not have. The lit half of the ledge is a waterfall,
and a waterfall in flat light is a grey smear.

The other decision worth writing down is the **bounce**. `hemi.ground` is the
only thing lighting a downward-facing surface, and this track has more of those
than anything else in the pool: the underside of the ledge the falls run past,
both walls of the gorge, and the whole belly and throat of the animal. So it is
green rather than neutral - light coming back off a jungle floor is green, and
here that is not a tint but the actual fill on a third of what you look at.

Colours are packed RGB handed to three.js unconverted, so they are picked cooler
and darker than they read - see `tracks/look.py`.
"""

PALETTE = {
    # Wet red dirt. Warm and saturated on purpose: the one road in the pool that
    # is not asphalt of some kind, and it has to hold its own against a floor
    # that is green from edge to edge.
    "road": 0x6d4832,
    # Weathered white and a park red, off the signage in the reference rather
    # than off a race kerb - this is a road through an attraction, not a circuit.
    "kerb": 0xf2e6d2, "kerb2": 0xb8402c,
    # The jungle floor. Kept a long way lighter than the road in *value* and not
    # only in hue, because the plan view and the share card are lit flat and
    # shadowless, and hue does not survive that.
    "ground": 0x4f9a3e,
    # Weathered timber. The rails are the park's fence, and they are only in the
    # two places the floor genuinely is not there - the ledge and the animal - so
    # they want to read as handrail rather than as barrier.
    "rail": 0xd9c4a0,
    # Canopy, and the darker leaf under it. `scenery.js` plants this track's
    # trees itself (nothing floating gets the built-in scatter, which stops at
    # `if (!onGround) continue`), so it reads both of these directly.
    "prop": 0x2f6b34, "prop2": 0x1e4a26,
    # Amber. Every sign, gate and marker on the track, and the light in the
    # ranger station's windows - one warm colour repeated is what makes a park
    # read as a park rather than as a jungle with furniture in it.
    "deco": 0xf2b23a,
    "fog": 0xbcd6da,
    # There is a whole jungle under this track, built by `scenery.js`, so the
    # void needs no floor of its own. Without *some* `below`, `buildTrack` draws
    # a distant grey plate at `minY - 34` for any floating track - which here
    # would be a second, lower, differently-coloured ground showing through the
    # gorge. Any `below` at all suppresses it; `void` is the one that then draws
    # nothing.
    "below": {"kind": "void"},
    # Dense, because a jungle is - and now the second-densest in the pool behind
    # Mushroom Grove's 0.34, which is the number that says how far this can go.
    # 0.22 was a jungle you could count the trees in: it stands one about every
    # 25 units, and once the canopy went up over the road the gaps between the
    # crowns were the thing left saying "parkland" - green hillside showing
    # through a colonnade in the middle distance. A ceiling needs the trees
    # closer together, not only taller.
    "density": 0.30,
    "props": {"palm": 0.56, "conifer": 0.20, "rock": 0.16, "deadtree": 0.08},
    # This track's own numbers, arriving in `scenery.js` as `ctx.cfg`. They are
    # here rather than in `track.py` because every one of them is a fact about
    # how the place looks, and none of them changes where the car can go.
    "building": {
        # The gorge: how far down the river is from the road that crosses it,
        # and how wide the cut is at the top.
        "gorge": 46, "gorgeW": 120,
        "water": 0x2f7f8c, "deepWater": 0x14495c, "foam": 0xd8f0f2,
        # The rock the whole place is cut out of. Two tones, lighter above.
        "rock": 0x8a6a4e, "rock2": 0x5c4433,
        # The animal. Cornflower over a cream throat, straight off the second
        # reference - and deliberately not a green or a grey, because the one
        # thing it must never be mistaken for is more scenery.
        "hide": 0x3160cc, "belly": 0xe4d6a8, "eye": 0x141018,
        # The herd, which is a different species and a different colour, so that
        # "something is moving on the road" and "the road goes over that one"
        # never have to be told apart at speed. Redder than the first pass's
        # brown, which sat inside the range the boulders and the road already
        # occupy - a moving obstacle that shares a hue with the scatter is one
        # you read late - and the first two passes at this were both browns
        # inside it. Gold is the one warm colour on this track that neither the
        # road nor the rock nor the boulders are already using.
        "herd": 0xc47a1c, "herd2": 0x5a3a14,
    },
    "sky": {
        "stops": [
            [0.00, 0xa6c6bc], [0.30, 0xc4dfd8], [0.44, 0xd8eef0],
            [0.56, 0x8ec2e6], [0.72, 0x3f86d4], [0.88, 0x1d55bc],
            [1.00, 0x0e3596],
        ],
        "glow": 0xfff2cf, "glowStrength": 0.5, "glowMode": "radial",
        "glowFocus": 7,
        # Nearly overhead. A low sun would put the gorge in its own shadow for a
        # third of the lap, and the falls are the thing you came to see.
        "sun": {"az": 2.1, "el": 0.66, "color": 0xfff6dc, "size": 280},
        "light": {"color": 0xfff2d8, "intensity": 1.45,
                  "dir": [0.52, 0.80, -0.30]},
        # See the docstring: the bounce is green because the floor is, and it is
        # the whole of the light on the gorge walls and the animal's belly. It is
        # also *bright*, which is the correction rather than the first guess -
        # at 0x6f9a52 the underside of the waterfall's overhang, which is a
        # forty-unit slab you look up at for a fifth of the lap, came out near
        # black and read as a hole in the cliff rather than as rock.
        "hemi": {"sky": 0xcfe9ff, "ground": 0x93c46a, "intensity": 1.02},
        "fog": 0xbcd6da, "fogNear": 300, "fogFar": 1500,
    },
}
