"""What Baku looks like.

**Every number here was checked against a picture**, not written from the word
"Baku": the 2026 pole lap frame by frame, the track-build documentary's aerials,
a 2018 track walk, a twenty-minute street walk through the same blocks, and
Commons photographs of the landmarks. What they said, and what it changed:

- **Late afternoon, and the sun is low in the west-south-west.** The race runs
  at four, and in every frame of the onboard the Turn 2 to Turn 3 avenue is
  driven straight into a low sun - flare, long shadows across the road, the
  tops of the buildings lit and the street in shade. That avenue runs -x here,
  so the sun sits at `az` -1.25 and low.
- **The city is one colour family: honey sandstone.** Beaux-Arts blocks of
  four to seven storeys in ashlar, cream surrounds, dark glass. The facades are
  textured (see `tools/make_baku_facades.py`); `prop` is the stone the
  untextured sides and back ranks are built in.
- **The asphalt is pale and worn**, a mid grey with the racing line lighter
  still - lighter than Monaco's, and cooler than it looks for the usual reason.
- **The painted edge line is white on every straight and the kerbs are only at
  the corners.** The engine stripes `kerb`/`kerb2` down both edges of every
  station, so both are white here and makes it the city's edge line; the
  red-and-white corner kerbs are drawn in `scenery.js` where there is a corner.
- **The walls are a colour per section, and `rail` is not one of them.** Every
  block in Baku is wrapped in vinyl - maroon down the start straight, yellow
  down the Turn 2-3 avenue, navy through the castle, red down the hill - so
  `scenery.js` wraps the rail section by section, and `rail` is only the bare
  concrete you see from behind.
- **Haze, not fog.** A dry, dusty late afternoon on the Caspian: everything past
  the near buildings goes to one warm pale value.
"""

PALETTE = {
"road": 0x5a616b,
"kerb": 0x2e3134, "kerb2": 0x2e3134,
"ground": 0xa89d8a,
"rail": 0xc9c2b2,
"prop": 0xd2bf98, "prop2": 0x2f5a35,
"deco": 0xc9a13e,
"gravel": 0x8a8478,
"fog": 0xd9d3c4,
# Trestles every 26 units under a groundless road are Monaco's to bury as well;
# the field here sits 1.2 under the road, so they never show.
"sky": {
  # u=0 is straight down, 0.5 the horizon, 1.0 the zenith. A dusty warm haze at
  # the horizon going to a soft blue overhead - never the Riviera's cobalt.
  "stops": [
    [0.00, 0x9aa3a6], [0.44, 0xcfd2cb], [0.50, 0xefe6d2],
    [0.56, 0xc9d8e2], [0.66, 0x93b6d6], [0.82, 0x6c98c8], [1.00, 0x4f80bb],
  ],
  # Fair-weather cumulus. **`dark` is the cloud itself**: the shader lerps the
  # dome toward it wherever the noise is high, and the first pass picked a pale
  # grey there that was the colour of the haze - so the clouds were in the sky
  # and invisible. White puffs, a high `amount` so they break into distinct
  # clumps rather than a mottle, and `lit` 0 so the blue between them stays blue.
  # `fade` 6 brings them down to just above the rooftops: at the shader's
  # default the chase camera only ever sees a quarter of any cloud.
  "clouds": { "scale": 3.1, "amount": 2.2, "dark": 0xf7f4ee,
              "light": 0xf7f4ee, "lit": 0.0, "fade": 6.0 },
  # Low in the west-south-west, and the disc is drawn where it really is: the
  # T2-T3 avenue is driven straight at it.
  "sun": { "az": -1.25, "el": 0.26, "color": 0xfff0d2, "size": 300 },
  "glow": 0xffdca8, "glowStrength": 0.42, "glowMode": "horizon", "glowFocus": 6,
  # The light rakes from the same side as the disc but higher, because every
  # building here is a vertical face and a light at the disc's own 15 degrees
  # would leave the east faces black and burn the west ones.
  "light": { "color": 0xffe4bc, "intensity": 1.30, "dir": [-0.74, 0.58, 0.34] },
  "hemi": { "sky": 0xd3dde6, "ground": 0xab9c80, "intensity": 0.98 },
  "fog": 0xd9d3c4, "fogNear": 380, "fogFar": 1900,
},
}
