"""What Singapore looks like.

**Every number here was checked against a picture**: the 2025 pole lap a frame
a second, the race's helicopter shots, and Commons photographs of the bay at
night. What they said, and what it changed:

- **Floodlit, not dark.** The road is the brightest thing in every frame of the
  onboard - an even, near-daylight grey under ~1,600 lamps - and the sky is
  black. So the key light is high, white and strong, and the night is in
  everything *else*: the sky, the fog, and the city, which `scenery.js` authors
  dark and lights with its own windows. Tokyo's night is the opposite (a dim key
  and a road that is barely there), and copying it made this a wet midnight.
- **White light, not sodium.** Metal-halide floodlights: the kerbs read red and
  white, the walls read in their sponsors' real colours. Only the expressways
  overhead carry orange lamps.
- **A humid haze.** Thirty degrees and eighty percent at ten at night: the
  towers across the bay soften into a dark, faintly warm murk rather than
  standing sharp against black.
- **The painted edge line is white** and the red-and-white kerbs are only at
  the corners, so `kerb`/`kerb2` - which the engine stripes down every edge - are
  both the line's white; `scenery.js` lays the corner kerbs.
- **`legs` 0**: the engine's trestles under a groundless road would stand in the
  river under both bridges. The ground is `scenery.js`'s, and so are the piers.
"""

PALETTE = {
"road": 0x6a6e74,
"kerb": 0xb8b8b2, "kerb2": 0xb8b8b2,
"ground": 0x3a3c40,
"rail": 0x8a8a86,
"prop": 0x3a3d42, "prop2": 0x2a2d32,
"deco": 0xf2c94c,
"gravel": 0x6a6660,
"fog": 0x0d1424,
"legs": 0,
"sky": {
  # u=0 is straight down, 0.5 the horizon, 1.0 the zenith. **One blue, top to
  # bottom.** A warm light-pollution band under a blue dome was tried and
  # rejected outright: two-tone skies read as cheap. Chosen from four
  # one-family variants: midnight navy, a touch
  # lighter at the horizon, and a few stars through the haze.
  "stops": [
    [0.00, 0x05070d], [0.44, 0x0b1220], [0.50, 0x1a2640], [0.54, 0x131d33],
    [0.62, 0x0d1528], [0.78, 0x070c1a], [1.00, 0x03060f],
  ],
  "stars": {"count": 380, "seed": 65, "size": 1.6},
  "sun": {"az": 2.4, "el": 0.55, "color": 0xdfe6f0, "size": 40},
  # Straight down and white: the floodlights are over the road, so the road and
  # the tops of the walls take it and the faces of the buildings mostly do not.
  "light": {"color": 0xf4f6ff, "intensity": 1.15, "dir": [0.16, 0.97, 0.18]},
  "hemi": {"sky": 0x5a6274, "ground": 0x2a2a2e, "intensity": 0.72},
  "fog": 0x0d1424, "fogNear": 260, "fogFar": 1500,
},
}
