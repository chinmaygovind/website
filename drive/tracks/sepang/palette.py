"""What Sepang looks like.

**Every number here was checked against a picture**, not written from the word
"Malaysia": Hamilton's 2017 pole lap a frame every three seconds, and about
thirty Commons photographs - the grandstand from the pit roof and from the
square behind it, the tower, the hairpins from above, the run-off, the kerbs,
the pit lane, and two aerials out of a plane landing at KLIA. What they said,
and what it changed:

- **A hazy tropical afternoon, and the main straight is driven into the sun.**
  The first and last ten seconds of the onboard are blown out white: the sun is
  low and dead ahead down the start straight, which runs +x here, so the disc
  sits at `az` pi/2. Everywhere else it is a bright humid haze with big
  cumulus towers standing over the palm oil - every photograph with sky in it
  has them.
- **The tarmac is pale and worn**, a light grey with the racing line darker,
  and the kerbs are flat red and white. Lighter than Silverstone's road, and
  cooler than it looks for the usual reason.
- **The grass is the greenest thing in the pool**, a wet tropical green, and
  the gravel traps are a pale sand that is nearly white in the sun.
- **The boards are teal and white.** Every barrier in every photograph is
  wrapped in the circuit owner's teal, alternating with white. The colour is
  taken and the logo is not; the words are this site's, as everywhere else.
- **Palm oil on every horizon.** Rows of oil palms on low green hills, with
  patches of rainforest. The rows are planted in `scenery.js`; the scatter
  here is the loose palms and the jungle between them.
"""

import math

# The sun, down the start straight. `sunDir` is (sin az, cos az) in x/z.
AZ, EL = math.pi / 2, 0.30

PALETTE = {
"road": 0x5a6068,
"kerb": 0xf3f1ec, "kerb2": 0xa81d18,
"ground": 0x4f8a36,
"rail": 0xd9dde0,
# Palm fronds and the canopy crown; `prop2` is the darker jungle broadleaf.
"prop": 0x3f7d2f, "prop2": 0x2c5e2a,
"deco": 0xf2c230,
# The gravel traps: pale sand, near-white in the sun.
"gravel": 0xcdbf9e,
# Sepang's run-off is enormous - gravel at every corner, then grass, then the
# barrier a long way back - and the two straights are 77 units apart centre to
# centre with the umbrella grandstand between them, which is what caps `armco`.
"terrain": { "apron": 30, "gravel": 16, "armco": 24, "clear": 34 },
"furniture": {
  "armco": 24, "armcoH": 1.5,
  "concrete": 0xc9c6bd,
  "board": { "bg": '#00a19a', "fg": '#ffffff' },
  "sponsors": ['CGOVIND.COM', 'DRIVE', 'KING OF TOKYO', 'CONDUCTOR', 'RAT SCREW',
             'GO BIRDS', 'CGOVIND.COM', 'TACO BELL', 'DRIVE', 'PENN ENGINEERING',
             'MARLBORO', 'KING OF TOKYO', 'CONDUCTOR', 'COSTCO WHOLESALE',
             'RAT SCREW', 'DRIVE', 'GO BIRDS', 'CGOVIND.COM'],
  "boardEvery": 26,
  "boardH": 2.6,
  # The main grandstand is not here: it is the umbrella-roofed double stand
  # between the two straights, built in `scenery.js`. These line the outside
  # of the lap, the way Sepang's do - and every one of them was checked against
  # `stand`'s footprint test before it went in, because **a stand that fails it
  # is dropped without a word**: the first pass had five here and four of them
  # never drew, which is how the circuit came back "missing grandstands".
  # Fractions are by station index, which is what the kit reads.
  "stands": [
    # K1, round the outside of Turn 1.
    { "at": [0.110, 0.132], "side": -1, "off": 30, "tiers": 7, "text": 'CGOVIND.COM',
      "seat": 0x2f7d46, "trim": 0xf2c230 },
    # C1, on the exit of the Turn 2 hairpin.
    { "at": [0.165, 0.187], "side": 1, "off": 30, "tiers": 7, "text": 'DRIVE',
      "seat": 0x1d4fa6, "trim": 0xc0261f },
    # Along the outside of the long Turn 3 right.
    { "at": [0.180, 0.240], "side": -1, "off": 30, "tiers": 7, "text": 'KING OF TOKYO',
      "seat": 0xc0261f, "trim": 0xf3f1ec },
    # K2, the braking zone and outside of Turn 4.
    { "at": [0.262, 0.318], "side": -1, "off": 30, "tiers": 7, "text": 'CONDUCTOR',
      "seat": 0xf2c230, "trim": 0x1d4fa6 },
    # The esses, Turns 5 and 6, from both sides.
    { "at": [0.341, 0.384], "side": -1, "off": 30, "tiers": 7, "text": 'RAT SCREW',
      "seat": 0x2f7d46, "trim": 0xf2c230 },
    { "at": [0.385, 0.418], "side": 1, "off": 30, "tiers": 7, "text": 'GO BIRDS',
      "seat": 0x004c54, "trim": 0xa5acaf },
    { "at": [0.388, 0.430], "side": -1, "off": 30, "tiers": 7, "text": 'TACO BELL',
      "seat": 0x702082, "trim": 0xf9c72c },
    # Turns 7 and 8, the double right.
    { "at": [0.462, 0.517], "side": -1, "off": 30, "tiers": 7, "text": 'CGOVIND.COM',
      "seat": 0x1d4fa6, "trim": 0xf2c230 },
    # Turn 9, the hairpin at the top of the hill.
    { "at": [0.594, 0.627], "side": 1, "off": 30, "tiers": 7, "text": 'PENN ENGINEERING',
      "seat": 0x990000, "trim": 0x011f5b },
    # Turns 10 and 11.
    { "at": [0.627, 0.671], "side": -1, "off": 30, "tiers": 7, "text": 'DRIVE',
      "seat": 0xc0261f, "trim": 0xf3f1ec },
    # Turn 14, onto the back straight.
    { "at": [0.726, 0.768], "side": -1, "off": 30, "tiers": 7, "text": 'MARLBORO',
      "seat": 0x2f7d46, "trim": 0xf2c230 },
    # The exit of Turn 15. Five rows at 27 is all that fits: the hairpin's own
    # outside is the start straight's run-off and the T9 straight.
    { "at": [0.952, 0.976], "side": 1, "off": 27, "tiers": 5, "text": 'KING OF TOKYO',
      "seat": 0xf2c230, "trim": 0xc0261f },
  ],
  # The pit garages down the right of the start straight, opposite the
  # grandstand. The truss roof and the control tower are in `scenery.js`.
  "pits": { "at": [0.003, 0.070], "side": 1 },
  "flags": [
    { "at": [0.004, 0.068], "side": 1, "off": 52, "every": 4, "h": 12.0,
      "design": 'my' },
    { "at": [0.118, 0.140], "side": -1, "off": 50, "every": 5, "h": 10.0,
      "design": 'my' },
  ],
  "spans": [
    { "at": 0.0035, "lights": True, "text": 'DRIVE', "clear": 10.0 },
    { "at": 0.060, "text": 'CGOVIND.COM', "clear": 10.0 },
  ],
},
"fog": 0xdfe4e3,
"density": 0.22,
"props": { "palm": 0.55, "broadleaf": 0.38, "rock": 0.07 },
"sky": {
  # u=0 is straight down, 0.5 the horizon, 1.0 the zenith. A bright white haze
  # at the horizon - it is ninety per cent humidity - into a deep clean blue.
  "stops": [
    [0.00, 0x9aa8a8], [0.44, 0xd8e0e0], [0.50, 0xf1f2ec],
    [0.55, 0xc4d9ec], [0.64, 0x8ab6e3], [0.80, 0x4f8ad2], [1.00, 0x2d69c2],
  ],
  # Baku's cumulus recipe: `dark` is the cloud itself, a high `amount` breaks
  # it into clumps, `lit` 0 keeps the blue between them blue, and `fade` brings
  # them down to the tree line where the towers are.
  "clouds": { "scale": 3.4, "amount": 2.6, "dark": 0xf8f8f4,
              "light": 0xf8f8f4, "lit": 0.0, "fade": 5.0 },
  "sun": { "az": AZ, "el": EL, "color": 0xfff6de, "size": 360 },
  "glow": 0xfff0cc, "glowStrength": 0.50, "glowMode": "radial", "glowFocus": 5,
  # From the sun's side, higher than the disc so the grandstand's faces are
  # not left black.
  "light": { "color": 0xfff3dc, "intensity": 1.25,
             "dir": [math.sin(AZ) * 0.70, 0.66, math.cos(AZ) * 0.70 + 0.26] },
  "hemi": { "sky": 0xd6e2ea, "ground": 0x4c5a44, "intensity": 1.0 },
  "fog": 0xdfe4e3, "fogNear": 340, "fogFar": 1800,
},
}
