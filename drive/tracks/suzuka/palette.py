"""What Suzuka looks like: a grey circuit in a pink spring.

The brief was "cherry blossom, restrained" and the restraint is the whole
design. The tarmac, the kerbs and the barriers are the real circuit's and are
not tinted at all; the blossom is in the trees and in the sky, which is where
it is in April. Putting pink on the road surface was tried in the first pass
and the circuit stopped reading as a circuit - see `props` below for where the
colour actually lives.
"""

import math


PALETTE = {
# Japanese asphalt is darker and bluer than Spa's. Cooler than it looks on
# purpose: a vertex colour does not go through sRGB-to-linear the way a light
# does, so anything warm here comes out as mud once the key light multiplies it.
"road": 0x3f444b,
# Suzuka's kerbs are red and white, and they are the only saturated thing on
# the circuit itself - which is what lets the blossom stay a background.
"kerb": 0xf2efe8, "kerb2": 0xc9372f,
"ground": 0x5c8042,
"rail": 0xd6dbe0,
# The two crown colours `broadleaf` picks between, per tree, at random - so one
# scatter gives a wood that is half in blossom and half in new leaf rather than
# an orchard of identical pink lollipops. This is the only place the cherry
# blossom is stated, and it is why `density` can stay low: a pink crown carries
# much further than a green one, so the same number of trees reads as more.
"prop": 0xf4b2cd, "prop2": 0x4f7d3c,
"deco": 0xe8b93c,
"gravel": 0xbdb4a4,
# A height field rather than one flat plate, for Spa's reason: this road falls
# 27 units from Dunlop to the hairpin, and a plate at `track.ground` would be a
# collidable ceiling over the whole middle of the lap. It is also what makes
# the crossing possible at all - the road that goes under the bridge is nine
# units below the plane the rest of the circuit sits on.
"terrain": { "apron": 38, "gravel": 20, "armco": 27, "clear": 44 },
"furniture": {
  "armco": 26, "concrete": 0xb9b6ae,
  "board": { "bg": '#141a20', "fg": '#f4f1ea' },
  "sponsors": ['CGOVIND.COM', 'DRIVE', 'CONDUCTOR', 'RAT SCREW',
             'KING OF TOKYO', 'CGOVIND.COM', 'GO BIRDS', 'DRIVE',
             'CONDUCTOR', 'PENN ENGINEERING', 'RAT SCREW', 'CGOVIND.COM',
             'TACO BELL', 'KING OF TOKYO', 'DRIVE', 'MARLBORO',
             'CONDUCTOR', 'TACO BELL', 'CGOVIND.COM', 'MARLBORO'],
  "boardEvery": 26,
  "boardH": 2.6,
  # Fractions of the lap, not station indices, because the ribbon is re-solved
  # for closure at load and that changes how many stations there are.
  "stands": [
    # The main stand down the pit straight, opposite the pits.
    { "at": [0.004, 0.060], "side": -1, "tiers": 9, "text": 'CGOVIND.COM',
      "seat": 0x1a56ff, "trim": 0xf5b301 },
    # Round the outside of the First Turn.
    { "at": [0.068, 0.108], "side": -1, "tiers": 7, "text": 'DRIVE',
      "seat": 0x2f333c, "trim": 0xc0182b },
    # The bank along the S Curves, which is where everybody actually sits.
    { "at": [0.140, 0.205], "side": -1, "tiers": 10, "text": 'KING OF TOKYO',
      "seat": 0x5c2678, "trim": 0xf2c94c },
    # The hairpin, the one corner you can watch cars stop for.
    { "at": [0.428, 0.462], "side": -1, "tiers": 8, "text": 'RAT SCREW',
      "seat": 0xb8860b, "trim": 0x3f2311 },
    # Spoon.
    { "at": [0.592, 0.640], "side": -1, "tiers": 6, "text": 'CONDUCTOR',
      "seat": 0x6b4226, "trim": 0xc0182b },
    # The Casio Triangle, the last passing place on the lap.
    { "at": [0.858, 0.896], "side": -1, "tiers": 8, "text": 'TACO BELL',
      "seat": 0x5b2a86, "trim": 0xf2c94c },
    # Two more on the opening stretch, which was the bare part of the lap: the
    # inside of the pit straight opposite the main stand, and the bank on the
    # exit of the First Turn. Both are `side` 1, the infield, so they fill the
    # side of the road the pit building does not.
    { "at": [0.012, 0.050], "side": 1, "tiers": 6, "text": 'DRIVE',
      "seat": 0x2f333c, "trim": 0xc0182b },
    { "at": [0.074, 0.106], "side": 1, "tiers": 7, "text": 'GO BIRDS',
      "seat": 0x004c54, "trim": 0xa5acaf },
    # Dunlop, so the long left has something standing on the outside of it.
    { "at": [0.252, 0.292], "side": -1, "tiers": 6, "text": 'PENN ENGINEERING',
      "seat": 0x990000, "trim": 0x011f5b },
  ],
  "pits": { "at": [0.003, 0.064], "side": 1 },
  # Hinomaru down the pit straight and along the bank at the S Curves, which is
  # the pair of places a circuit really lines them up. `off` is 29 rather than
  # the default `armco + 5` for the reason Spa's note gives: these stands
  # declare no `off` of their own, so a flag line further out stands *behind*
  # the seating, where from the car it is a row of poles nobody can see.
  # `jp` was added to `FLAGS` in trackmesh.js for this - see the note there.
  "flags": [
    { "at": [0.006, 0.056], "side": -1, "off": 29, "every": 4, "h": 11.0,
      "design": 'jp' },
    { "at": [0.146, 0.200], "side": -1, "off": 40, "every": 5, "h": 10.0,
      "design": 'jp' },
    { "at": [0.066, 0.104], "side": 1, "off": 33, "every": 4, "h": 9.5,
      "design": 'jp' },
  ],
  "spans": [
    { "at": 0.004, "lights": True, "text": 'DRIVE', "clear": 9.5 },
    # Two more gantries over the opening stretch. A circuit carries these every
    # few hundred metres and they are the cheapest thing that stops a straight
    # reading as empty - they cross the sky, so they are furniture you cannot
    # drive past without noticing.
    { "at": 0.043, "text": 'CGOVIND.COM', "clear": 9.5 },
    { "at": 0.108, "text": 'CONDUCTOR', "clear": 9.5 },
  ],
},
"fog": 0xd3dde6,
# A circuit in a park, so the trees want to be something you see past rather
# than a wall - the Ferris wheel in `scenery.js` has to read from the far side
# of the lap or it is not doing its job, which is why this is still short of
# Spa's 0.34 pine forest. It started at 0.18 and the opening stretch came back
# looking bare, which is the number doing too good a job of getting out of the
# way: at 0.18 the far side of the pit straight is flat green.
"density": 0.27,
"props": { "broadleaf": 0.72, "conifer": 0.14, "bigpine": 0.08, "rock": 0.06 },
"sky": {
  "stops": [
    [0.00, 0x6b5a72], [0.44, 0xc99fb0], [0.50, 0xe8b9c2],
    [0.56, 0xc9a3c0], [0.72, 0x8c7fb0], [1.00, 0x4a4a86],
  ],
  "clouds": { "scale": 3.2, "amount": 1.10, "dark": 0x7a6485,
            "light": 0xffd9e4, "lit": 0.55 },
  "sun": { "az": 2.60, "el": 0.10, "color": 0xffd0c0, "size": 520 },
  "glow": 0xffc2cf, "glowStrength": 0.55,
  "light": { "color": 0xf0d8dc, "intensity": 0.92,
           "dir": [math.sin(2.60) * 0.80, 0.50, math.cos(2.60) * 0.80] },
  "hemi": { "sky": 0xdcc3d4, "ground": 0x4a5a38, "intensity": 1.05 },
  "fog": 0xd8bfc9, "fogNear": 240, "fogFar": 1400,
} }
