"""What Monaco looks like.

The pool's third closed circuit, and deliberately not a third version of the same
picture. Spa is a wet grey road through pine, fogged at 1050 with no sun disc at
all; Silverstone is a soft July afternoon on a flat airfield, fogged at 1750 over
mown grass. Both are *circuits in a landscape*, and their whole vocabulary -
gravel, armco set back past it, trees, a crowd standing well back - is about a
place with room. Monaco has no room, and every number below follows from that.

- **There is no run-off.** The barrier is a ribbon `rail` sitting on the kerb for
  the whole lap, so `gravel` here only ever paints the strip of painted road edge
  under it. Spa's armco is 26 units out past a 21-unit gravel trap.
- **There is no grass, and there is no `terrain` or `furniture` block.** Both are
  ground-track machinery and this track has no ground - see `track.py`, where the
  reason is that the circuit crosses over itself. Everything that would have come
  from them, and everything Spa's `furniture` would have given, is built in
  `scenery.js`: the hillside, the quays, the harbour, the city, the tunnel.
  `ground` below is the stone the hillside is painted in.
- **There is no scatter.** `density`/`props` only apply to a ground track, and a
  thin one across an empty plain is most of what made the first render read as a
  quarry. The palms are planted along the harbour by `scenery.js` instead.
- **The sky is the most saturated in the pool**, because a Monaco Grand Prix
  weekend is reliably cloudless and the water needs something to be blue *about*.

**The one number that matters most here is `light.dir`, and it is raking rather
than overhead on purpose.** This is meant to read as high Mediterranean midday,
and the instinct is to put the light overhead to match - which is wrong in a way
that is invisible until you look at a wall. The world is
`MeshLambertMaterial` with no shadow maps, so a vertical face gets almost nothing
from a light above it. Silverstone learned this on its pit garages and hangars.
Monaco is a canyon of apartment blocks: it is *mostly* vertical faces, so an
overhead light would black out the whole city and leave a lit road running
through it. The `sun` disc is authored separately from the light, which is what
lets the disc sit high and the lighting rake in from the side.
"""

PALETTE = {
# Sun-bleached asphalt, and picked cool for the usual reason - a warm key light
# multiplies a vertex colour that was chosen at the value it should look, and the
# road comes out as mud. Lighter than Spa's wet grey and a touch lighter than
# Silverstone's, because this is a dry street in hard overhead sun.
"road": 0x4c525c,
# Monaco's kerbs are red and white, and the reds are what you see of the circuit
# in every photograph of it.
"kerb": 0xf4f1e9, "kerb2": 0xd0392e,
# **Not grass.** Warm pale stone - pavement, quay and terrace. Kept well clear of
# `road` in *lightness* rather than in hue, because the plan view is lit flat and
# shadowless and two colours a few points apart in value read as one from above.
"ground": 0xb3a385,
# **The barrier, and it is charcoal rather than white.** Monaco's armco is
# hoarded over its whole length with dark sponsor boards, and that continuous
# dark band at the road edge is the most recognisable thing about the circuit -
# it is in every photograph and every frame of every onboard. White rails read as
# a go-kart track. The catch fencing above it is in `scenery.js`.
"rail": 0x2b2f3a,
# The city: Monte Carlo cream, and the terracotta of the older roofs and
# shutters. Read `scenery.js` - these are the two colours the whole city is
# dealt from, varied per building off a seeded hash.
# Warmer and lighter than the first pass, and the reason is the window bands
# rather than these: at a third of every facade in dark blue-grey they averaged
# the whole city to concrete, so the cream never read. See `block` in scenery.js.
"prop": 0xf0c89a, "prop2": 0xc4543a,
"deco": 0xdfae37,
# The strip of tarmac between kerb and barrier. Not gravel and not grass - there
# is none of either here - so this is only ever a metre or so of painted road
# edge, and it is coloured as one.
"gravel": 0x8a8478,
"fog": 0xd2dbdc,
"sky": {
  # u=0 is straight down, 0.5 the horizon, 1.0 the zenith. The most saturated
  # dome in the pool: real Mediterranean blue overhead falling to a bright,
  # slightly warm haze where the sea meets it.
  "stops": [
    [0.00, 0x93b3c6], [0.42, 0xc8dcea], [0.50, 0xe2f0f8],
    [0.60, 0x8ec4ee], [0.78, 0x3f86d8], [1.00, 0x1450b8],
  ],
  # Barely there. A race weekend here is cloudless, and `clouds` is an overcast
  # shader - at Spa's 1.5 it would put grey over the one sky in the pool that is
  # supposed to be blue.
  "clouds": { "scale": 2.1, "amount": 0.28, "dark": 0xb6c6d2,
            "light": 0xf6fafd, "lit": 0.12 },
  # High and out over the sea, which is where a midday sun is from the harbour.
  "sun": { "az": 2.25, "el": 0.74, "color": 0xfffcf2, "size": 270 },
  "glow": 0xfff8e6, "glowStrength": 0.36, "glowMode": "radial", "glowFocus": 8,
  # See the docstring: the disc is high and the *light* rakes, because every
  # building in this track is a vertical face and a light from overhead leaves
  # them all black.
  "light": { "color": 0xfff4e2, "intensity": 1.28, "dir": [0.54, 0.66, 0.52] },
  # The bounce, and the strongest single number in any palette.
  #
  # **Both halves were too cool and it greyed the whole city.** This track is
  # hundreds of vertical faces and most of them are turned away from a raking key
  # light, so what they are actually lit by is this - and at a near-neutral grey
  # ground and a cool blue sky, five shades of cream stucco all averaged out to
  # concrete. Every render up to this one had a grey city with a cream palette,
  # and the palette was not the thing at fault.
  #
  # So the ground half is warm sand rather than neutral: on a hillside town in
  # hard sun the bounce genuinely is warm stone coming back up. Kept desaturated,
  # because the note this replaces is still true - a saturated bounce stops being
  # a tint and becomes a second key light.
  "hemi": { "sky": 0xdce7ef, "ground": 0xa8977c, "intensity": 1.00 },
  # **Haze is what makes the distance read as distance.** At 1600 the far city
  # and the massif behind it came through at full contrast and the frame had no
  # depth in it; in every reference of this place everything past the near
  # buildings is washed toward one pale warm value. Brought in and warmed - still
  # inside the pool's 780..2100.
  "fog": 0xd2dbdc, "fogNear": 260, "fogFar": 1180,
},
}
