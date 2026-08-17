"""What Tokyo Drift looks like: wet, after midnight, lit by other people's signs.

**This is the pool's first night track**, and the first at street level in a
city - Jump City looks close and is neither, being a dusk track floating above a
`downtown` world you never actually drive in. So there is nothing here to copy a
mood from and every number below is set against the pool's own range rather than
against a track with the same weather.

The two that carry it, and both were wrong on the first pass in the same
direction - too bright, too saturated, and the renders came out as a pink dusk
rather than a wet midnight:

- **`light.intensity` at 0.45.** The pool runs 0.70 to 1.62. Night is not a dim
  day - it is a scene with almost no key light, where nearly everything visible
  is coming from the hemisphere and from things that emit. Lowering this without
  raising `hemi` gets you a black screen with a road in it.
- **`hemi.ground` at a dim ember.** The single highest-leverage number in any
  palette, because it is the bounce: sand makes a desert warm from underneath
  and snow lifts the shadows out of a winter scene. The instinct here is a
  sodium orange, since that is what streetlight on wet asphalt *is* - and at
  full saturation it lit every upward-facing surface on the track and turned the
  entire world brown. It has to be dim enough to be a bounce rather than a
  second key light.

Colours are packed RGB handed to three.js unconverted, so **everything here is
cooler than it looks** - a light's colour goes through sRGB-to-linear and a
vertex colour does not.
"""

PALETTE = {
    # Wet asphalt is nearly black, but not actually black: at 0.40 of key light
    # there is very little multiplying this down, and a road authored at the
    # value it should *appear* comes out as a hole in the world with kerbs
    # floating in it. This is a couple of stops brighter than it reads.
    "road": 0x2b3340,
    "kerb": 0xf6faff,
    "kerb2": 0xff3d9a,
    # The terrain colour, and it has to serve both halves of the track - the city
    # floor and the hillside the touge comes down.
    #
    # **It is deliberately a good deal lighter than the road**, which is both
    # true (wet tarmac is darker than the concrete and scrub beside it) and the
    # only thing making `plan.png` legible. The first pass had these two within a
    # few points of each other and the plan view came out as one solid dark blob
    # with the road completely invisible in it - on a night track the render is
    # the only check on layout there is, so the two surfaces have to separate by
    # value and not by hue.
    "ground": 0x262d38,
    # The armco, which on this track is the guardrail down the mountain rather
    # than a circuit backstop. Pale enough to pick out of a dark hillside, since
    # on the touge it is the only thing telling you where the road stops.
    "rail": 0xc2ccd8,
    "prop": 0x28303f,
    "prop2": 0x2f3846,
    "deco": 0x2ff3ff,
    "fog": 0x1e2836,
    "pad": 0x2ff3ff,
    "padBase": 0x101828,
    # **Real rain, and it has to be real.** Baked streaks slide past the car like
    # thin poles - the parallax gives it away instantly and it reads as scenery
    # rather than as weather. So this is the one animated thing in the game, and
    # it lives in `render.js` (see the `Rain` class) rather than in this track's
    # `scenery.js`, because nothing calls a scenery function twice.
    #
    # `wind` is a world-space drift and it is what sets the direction rain
    # falls in - deliberately, because weather should have one direction and
    # keep it. `rake` is how much the car's own speed leans the streaks on top
    # of that, derived per frame from the camera's velocity. **It is a fifth of
    # the physically correct value**: the honest number leans 25 degrees at
    # racing speed, which is right and reads as the rain flying at you.
    "rain": {"count": 3000, "color": 0xaecbe6, "opacity": 0.30,
             "speed": 95, "len": 2.4, "wind": [7, 3], "rake": 0.18,
             "box": 150, "high": 90},
    # Sparse, and weighted to the mountain. `block` is what stands in for a
    # building at this distance and it is the only one of these that belongs in
    # a city; the conifers are the hillside the back half of the lap is cut into.
    # **Sparse.** 0.10 carpeted the whole bounding box in identical small dark
    # boxes out to the horizon, which reads as a junkyard rather than as a city -
    # the same mistake Sandy Cove's first pass made in the other direction, where
    # a beach came out as a palm plantation. There is no building in the scatter
    # vocabulary (`block` is a crate at this scale), so the city cannot be made
    # out of props at all; what it can do is stay out of the way.
    "density": 0.02,
    # Weighted to `block`, which is the only one of these that reads as a
    # building. The first mix was 42% conifer and put pine forest through
    # downtown Tokyo - the scatter is one global mix with no idea which movement
    # of the track it is standing in, so the city half is what has to set the
    # weights and the mountain gets its character from being the only place the
    # road is cut into a slope.
    "props": {"block": 0.72, "rock": 0.28},
    # **There is no `terrain` block here, and there cannot be one.**
    #
    # This track was authored with one - a narrow shoulder and a guardrail, so
    # the touge would come down a real hillside instead of an elevated ribbon.
    # It renders wrong, and the reason is structural rather than a matter of
    # tuning the numbers.
    #
    # `buildTerrain` samples a height field over the (x, z) plane and fills each
    # cell with the height of the nearest road. That is single-valued by
    # construction, and **a helix is not**: three storeys of ramp stack three
    # different road heights over the same footprint, so every cell inside the
    # cylinder resolves to whichever turn happens to be nearest in plan and the
    # field fills the whole drum solid, up to the top deck. What that looks like
    # from the car is the ramp buried in a smooth mound with ground flush against
    # both kerbs - not an open-air car park, a road cut into a hill.
    #
    # No apron or blend setting reaches it: the conflict is between a height
    # field and road over road, and this track is 3 storeys of exactly that.
    # So it sits on one flat quad like every other ground track, which is also
    # what lets the helix read as a structure standing clear of the floor - the
    # same thing that makes Costco's rooftop deck work.
    "sky": {
        # Stop 0 is the horizon and stop 1 is the zenith. A city at night is lit
        # from *below* - all of this is light pollution coming back off the cloud
        # base - so the gradient runs the opposite way to every other track here:
        # warm and bright at the bottom, dead black overhead.
        # Darker at the bottom than the first pass by a long way. Light
        # pollution is a band close to the horizon, not a wash over the whole
        # dome, and the first version's 0x6e3a52 horizon with `glowStrength`
        # 0.85 and a broad `glowFocus` of 4 filled the entire sky pink - the
        # renders came out as a dusk track rather than a midnight one, which is
        # a different film.
        "stops": [
            [0.00, 0x332a2a], [0.10, 0x272430], [0.28, 0x1c2136],
            [0.52, 0x141a2c], [0.78, 0x0b1020], [1.00, 0x060912],
        ],
        "glow": 0xffb072, "glowStrength": 0.22, "glowMode": "horizon",
        "glowFocus": 15,
        # A moon rather than a sun: small, cold, and high enough that its light
        # can come from somewhere. A disc drawn on the horizon with its light
        # also on the horizon lights nothing at all.
        "sun": {"az": 2.4, "el": 0.30, "color": 0xdce6ff, "size": 90},
        "light": {"color": 0x9fb6e8, "intensity": 0.62,
                  "dir": [0.42, 0.78, -0.46]},
        # **The ground bounce is a deep ember, not a sodium lamp.** This is the
        # highest-leverage number in the palette and the first pass had it at a
        # saturated 0xff8c3a, which is what streetlight on wet asphalt looks like
        # and is far too strong as a hemisphere: it lit every upward-facing
        # terrain surface on the track and turned the whole shoulder and hillside
        # *brown*. Dim and desaturated keeps the warmth on the car's underside
        # without repainting the world.
        "hemi": {"sky": 0x35507a, "ground": 0x6e4a28, "intensity": 0.92},
        # Close and heavy. It rained an hour ago, and haze is most of what makes
        # a neon sign read as a neon sign rather than as a coloured box.
        "fog": 0x1e2836, "fogNear": 220, "fogFar": 980,
    },
}
