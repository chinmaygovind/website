"""What Rickety Rails looks like.

Three references, and what each one is actually for.

**Wario's Gold Mine, inside** is the structure: a plank deck with two bright
steel rails on it, on stilts, under heavy timbering, in a hole. Almost nothing
in that shot emits light - the road is simply the brightest thing in frame, and
everything else is a weak warm key falling on brown timber and grey rock. That
is the whole lighting model here.

**Wario's Gold Mine, outside** is the sky, which you see about four times a lap:
a low sun and bruised orange cloud. It is in the palette at all because the
vault has a hole in its roof, and what comes down that hole has to be daylight
rather than another lamp.

**New Super Mario Bros. Wii 1-2** is the one thing the Gold Mine does not have,
and it is the accent the rest of this needs: saturated violet crystal against
cold rock. Everything else here is brown, so the crystals, the boost pads and
nothing else are violet.

What was deliberately *not* copied: the Gold Mine interior's actual darkness.
`tracks/look.py` puts the drivable floor at 0.16 of lit road value and the
darkest track in the pool that works is Tokyo Drift; this sits at about 0.31,
which is dark enough to read as underground and still leaves the next corner
legible at speed. Judge it by whether you can see the corner, not by whether
the still looks moody.

Colours are packed RGB handed to three.js unconverted, so they are picked cooler
than they look - see `tracks/look.py`.
"""

import math

# The sun's bearing. The skylight in `scenery.js` and the key light both point
# along it, so the shaft of daylight in the vault and the shading everywhere
# else agree about where outside is.
SUN_AZ = -0.75

PALETTE = {
    # Sleepers and plank deck. Warm, because it is wood, and it stays the
    # brightest surface in the world on purpose - underground there is nothing
    # else for the eye to use.
    "road": 0x6d5f4e,
    # The rails, and the sleeper ends between them. Alternating pale steel and
    # dark creosote is both what a cart road looks like from above and the
    # strongest edge cue available in a place with no horizon.
    "kerb": 0xe4dccb,
    "kerb2": 0x3a2c1e,
    # The rock, and it is blue on purpose. The key light here is 0xffd9a8 and a
    # vertex colour does not go through sRGB-to-linear while a light's colour
    # does, so a *neutral* rock renders brown - the first pass picked 0x2e2a30,
    # which is cool in the swatch, and the cave came out the same warm brown as
    # the timber standing in it. Everything in the reference that is not wood is
    # cold; this is the axis that separates them.
    #
    # It is also what keeps `plan.png` legible: the plan view is lit flat, so
    # road and rock have to differ in *value*, and these are 0.38 against 0.18.
    "ground": 0x2c3042,
    # The side beams. This track is 96% walled and the beams are most of what
    # you see of the road ahead, so they are lighter than the rock and warmer
    # than it: at distance they are the line the corner is drawn with.
    "rail": 0x7a5f45,
    # The legs under the deck, and the timbering `scenery.js` stands on the
    # road. `buildTrack` draws a slim leg under every station of a groundless
    # track, which on this track is the point rather than something to bury - a
    # mine-cart line on stilts is what the reference is.
    #
    # Both are much lighter than they look like they should be, and that is the
    # second half of the note above. A vertical face gets almost nothing from a
    # key light pointing down, so timber picked at the brown it should *be*
    # renders as a black cut-out - the first pass had 0x33261a and every portal
    # frame on the track was a silhouette. Pick trackside timber by what a
    # vertical face does with it, not by the swatch.
    "prop": 0x7a5f3e,
    "prop2": 0x54402a,
    # Gates and markers: hazard amber, the one warm colour in the place that is
    # not timber.
    "deco": 0xffbe3d,
    "fog": 0x131522,
    # The pads, and the crystals share this violet. Complementary to every brown
    # in the world, which is why it is the only thing here that has to be
    # noticed from a distance. The panel under the chevrons is nearly black so
    # they read as light rather than as paint.
    "pad": 0x9d6bff,
    "padBase": 0x0e0a14,
    # No distant grey plate. `buildTrack` draws one at `minY - 34` for any
    # floating track with no `below`, and here that would be a second floor
    # under the cave floor this track builds itself. Any `below` suppresses it;
    # `void` is the one that then draws nothing.
    "below": {"kind": "void"},
    "sky": {
        # Sunset, seen through a hole in the roof. Eight stops, and the ones
        # that matter are the three near the horizon - that band is the only
        # part of the dome the skylight actually shows.
        "stops": [
            [0.00, 0x2a1410], [0.34, 0x6b2c18], [0.44, 0xb85526],
            [0.50, 0xe8823a], [0.58, 0xa8522f], [0.70, 0x5c2f38],
            [0.85, 0x2e1b32], [1.00, 0x140d1e],
        ],
        "glow": 0xffb066, "glowStrength": 0.62, "glowMode": "horizon",
        "glowFocus": 6,
        "sun": {"az": SUN_AZ, "el": 0.06, "color": 0xffa855, "size": 460},
        # The disc is on the deck and the light is not. Underground the key
        # light is standing in for a hole in the roof and a hundred work lamps
        # at once, so it comes from well above and it is weak - 0.72 against a
        # daylight track's 1.3.
        "light": {"color": 0xffd9a8, "intensity": 0.72,
                  "dir": [math.sin(SUN_AZ) * 0.55, 0.82, math.cos(SUN_AZ) * 0.55]},
        # The bounce. Rock, not snow: it returns almost nothing, so this is the
        # dimmest hemisphere in the pool. The sky half is a cold slate rather
        # than a blue, because in a cave "up" is more rock.
        #
        # **The ground half is what makes the loop visible**, and it was wrong.
        # `hemi.ground` lights *downward*-facing faces and nothing else here
        # does - the key light points down and there are no shadow maps - so at
        # 0x241c18 the underside of the loop, the underside of the deck and the
        # soffit of every trestle bent were all pure black, and from the floor of
        # the vault the loop read as a hole rather than as a structure. Lifted
        # and cooled rather than brightened: it is still under a tenth of the
        # sky half, and the note in `docs/track-defects.md` about a saturated
        # bounce repainting the world does not bite because this one is
        # desaturated and only ever lands on faces pointing at the ravine.
        "hemi": {"sky": 0x4a4258, "ground": 0x3a3040, "intensity": 0.62},
        # The closest fog in the pool, and it is doing a job no other track's
        # fog does: it is the dust and damp that stops you seeing where the
        # cavern ends. 800 is just inside the pool's own range and about the
        # length of the longest straight here.
        "fog": 0x131522, "fogNear": 190, "fogFar": 800,
    },
}
