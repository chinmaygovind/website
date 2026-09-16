"""What Playground looks like.

**A bright blue afternoon and a candy road, and the sky is doing a job.**

Every other floating track in the pool puts something under itself to read
height against - Big Red's drowned city, Cloudbreak's spires, Rickety Rails'
cave floor. This one is `below: void`, which draws no distant floor plate at
all, and that is a decision about the *geometry* rather than the art: most of
this track's set pieces rotate the road instead of moving it, and a wall of
death only reads if the road is the only thing in frame with an orientation.
Put a horizon of mesas behind one and the eye takes the world to be tilting
rather than the car.

Which leaves the sky as the only thing separating "sideways" from "level", so
it is graded hard from a deep zenith to a pale horizon - eight stops, more than
anything else in the pool - and the sun sits high with a tight radial halo. Roll
onto a wall and the gradient sweeps across the screen, which is the whole
feedback.
"""

import math

# The sun's bearing, used twice: once for the disc and once for the key light.
# A disc drawn low with its light coming from the same place lights nothing.
SUN_AZ = 2.35

PALETTE = {
    # Candy, and it took two passes. The first was `0xb8536e`, picked a step
    # cooler and darker on the usual advice that a warm key light multiplies a
    # vertex colour down - and it came out a dusty mauve, which is the advice
    # applied to the wrong quantity. What the key light eats is *value*, and the
    # thing that had to survive here was **saturation**: against a sky this
    # saturated, a road two-thirds of the way to grey reads as the grey. So this
    # is more saturated and only a little lighter.
    "road": 0xc93d63,
    # Cream and cyan rather than the usual white-and-red. Red kerbs against a
    # pink road are two neighbours on the wheel and the kerb stops being a
    # signal - which matters more here than anywhere, because on a wall the kerb
    # line is the only thing telling you how far up you are.
    "kerb": 0xf6ece0,
    "kerb2": 0x2f9ec4,
    # There is no ground on this track. The key is required, it is what a
    # `terrain` or a ground plate would be drawn in, and here it is only ever
    # seen as the value `plan.png` draws the world behind the road in - so it is
    # picked to be clearly darker than the road and nothing else.
    "ground": 0x2b3550,
    "rail": 0xf6ece0,
    # `prop` is the hoops. The rank of teal posts this used to colour is gone -
    # see `scenery.js`; the barrier is a beam at kerb height now, drawn in a
    # darker `kerb2` so it reads as the edge of the road rather than as a thing
    # standing beside it.
    "prop": 0x3f9c92,
    "prop2": 0x2f7a72,
    "deco": 0xe0b032,
    "fog": 0xa8d6ef,
    # No scatter: there is no ground for it to stand on, and a density here
    # would carpet the whole bounding box with trees hanging in the sky.
    "density": 0.0,
    # The pads. Bright against a pink road, which the pool's default dark base
    # is not.
    "pad": 0xffd34d,
    # Plum rather than the near-black the pool mostly uses. On a dark road a
    # black pad base is a shadow; on this one it is a hole in the road.
    "padBase": 0x5e2a48,
    # The one mushroom.
    "cap": 0xe2574f,
    "capSpot": 0xf6ece0,
    "sky": {
        # Eight stops. The pool runs six to nine and the reason to be at the top
        # of that here is the band just over the horizon: it is what the eye
        # measures roll against once the road is vertical and there is no ground
        # in frame to measure it against instead.
        "stops": [
            [0.00, 0xbfe4f6], [0.30, 0x9ed3f0], [0.44, 0x7cbfe9],
            [0.56, 0x5aa6e0], [0.68, 0x3f8ad6], [0.80, 0x2e6fc6],
            [0.90, 0x2456ac], [1.00, 0x1b4190],
        ],
        # High and small, with a tight halo. `radial` rather than `horizon`:
        # smearing the glow around the sun's azimuth is what makes a sunrise a
        # sunrise, and this is the middle of the afternoon.
        "glow": 0xfff8e4, "glowStrength": 0.42, "glowMode": "radial",
        "glowFocus": 7,
        "sun": {"az": SUN_AZ, "el": 0.92, "color": 0xfffdf4, "size": 260},
        "light": {"color": 0xfff4e4, "intensity": 1.45,
                  "dir": [math.sin(SUN_AZ) * 0.42, 0.87,
                          math.cos(SUN_AZ) * 0.42]},
        # **The bounce is the load-bearing number, as always, and here it is
        # bouncing off nothing - and it started twice as strong as it should
        # have been.** At 0.95 a pale blue hemisphere was landing on every
        # upward face in the world, which on a track that is mostly upward faces
        # is a second key light with no direction: the road came out a dusty
        # mauve in every flat shot and only looked like its own colour down
        # inside the half-pipe, where the walls shaded it. Dimming it is what
        # made the road candy, not the two goes at the road colour itself.
        #
        # Back up a little from 0.58, though, because on this track the bounce is
        # also **the only thing lighting a downward face**. The key light points
        # down and there are no shadow maps, so the underside of a loop, the
        # outside of three cylinders and the whole soffit of the ramp are lit by
        # this and nothing else - and at 0.58 a shot from under a wall came back
        # very nearly black, which `docs/track-defects.md` has as its own entry
        # from Rickety Rails. 0.72 with a lighter value is the trade.
        # There is no ground, so a green or a sand
        # `ground` value would be light arriving from a surface that is not
        # there. It is sky instead - a paler version of the dome - which is what
        # actually happens to a road suspended in open air, and it is the only
        # thing lighting the underside of the loop, the undersides of three walls
        # and the bottom of every pole.
        "hemi": {"sky": 0xd7e9f8, "ground": 0xa8c8e4, "intensity": 0.72},
        "fog": 0xa8d6ef, "fogNear": 420, "fogFar": 1600,
    },
    # **No trestle legs.** `buildTrack` draws a pair under a groundless road
    # every twenty-six units so an elevated track reads as built rather than
    # floating - which is right on Rickety Rails' mine-cart deck and wrong here,
    # where the road is *supposed* to be floating. What it actually looked like
    # was a rank of teal stilts descending into nothing under a track whose whole
    # subject is that there is nothing under it.
    "legs": 0,
    # Nothing underneath but weather. `void` draws no distant floor plate at all
    # - an open bottom fading into fog is what a long way up looks like, where a
    # plate reads unmistakably as grey water however it is coloured - and `haze`
    # hangs a cloud deck in that nothing. The combination is only possible
    # because `haze` is drawn *before* `kind` is dispatched on, so a world that
    # is nothing can still have cloud in it.
    #
    # **The numbers are Cloudbreak's, and they are about the viewing angle
    # rather than about taste.** A deck a little way under a long track is seen
    # almost edge-on, and then it reads as a sea with floes on it however good
    # the clumping is - so it goes 145 units below the lowest station, which here
    # is nearly four hundred under the highest, and `puff` deepens each blob so
    # it still reads as cloud from a shallow angle. `cover` at 0.34 is the other
    # half: cloud only works as clumps with sky between them, never as an even
    # coverage of anything.
    #
    # It also does a job the void could not. Falling off used to be a fall into
    # a flat gradient with no scale in it; now there is something a long way down
    # to fall *past*, which is the only thing on this track that says how high up
    # the road is.
    "below": {"kind": "void", "haze": {"deck": 145, "cover": 0.34,
                                       "cloud": 0xeef4fa, "puff": 2.1,
                                       "cloudStep": 13}},
}
