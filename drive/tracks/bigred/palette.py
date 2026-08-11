"""What Big Red looks like."""

import math

PALETTE = { "road": 0x3a2530, "kerb": 0xffe4dc, "kerb2": 0xff2f42,
"ground": 0x3a1622, "rail": 0xffd6cf, "prop": 0x5c2432, "deco": 0xff4d5a,
"fog": 0xa8556a,
# Electric cyan on a red road, which is the one pair of colours
# nobody has to be told about. The panel under it is nearly black
# so the chevrons have something to be bright *against* - on bare
# tarmac they read as paint rather than as light.
"pad": 0x7df9ff, "padBase": 0x140710,
"sky": {
  # Down at the horizon it is nearly black - you are above the
  # weather and there is no ground to bounce anything back. It
  # burns through crimson to orange where the sun is, and cools
  # to a deep violet overhead that still has night in it.
  "stops": [
    [0.00, 0x2a0a12], [0.36, 0x7d1526], [0.46, 0xc42d2c],
    [0.50, 0xf25c34], [0.55, 0xc93650], [0.64, 0x8e2a5e],
    [0.76, 0x53215e], [0.88, 0x2c1546], [1.00, 0x140a28],
  ],
  "glow": 0xff9a5a, "glowStrength": 0.95,
  "sun": { "az": -0.62, "el": 0.03, "color": 0xff8f52, "size": 620 },
  # The disc is on the deck; the key light is not, or the road
  # and the cars are silhouettes. Warm, and strong enough that a
  # banked corner still shows which way it is banked.
  "light": { "color": 0xffd0b4, "intensity": 1.34,
           "dir": [math.sin(-0.62) * 0.86, 0.5, math.cos(-0.62) * 0.86] },
  "hemi": { "sky": 0xff9c86, "ground": 0x7a1428, "intensity": 0.95 },
  "fog": 0xa8556a, "fogNear": 280, "fogFar": 2100,
},
# A real city a long way down, and a thin layer of cloud between
# it and the road - which is two separate things and needed the
# `haze` hook to say so.
#
# The default `below` world was tried first and is the wrong
# world for this: it is *one* thing, a cloud deck sitting on top
# of the towers that are drowned in it, so the city can only ever
# be at the cloud's own depth. Under a red sunset that came out
# as a field of pale mesas standing on dark pillars - stone, not
# sky, and no amount of retuning the cloud fixed it because the
# problem was that the two layers were one. `downtown` puts a
# proper skyline down there with lit windows, which is the thing
# that actually reads as a city from 260 units up, and the haze
# is then free to be thin and broken because it is not holding
# anything up.
"below": { "kind": 'downtown', "deck": 300, "reach": 900, "step": 5,
         "coreX": 60, "coreZ": 120, "coreR": 380,
         "low": 34, "spread": 58, "rise": 115,
         "landmarkX": -40, "landmarkZ": -60, "landmarkH": 200,
         "tower": 0x2b1b33, "window": 0xffc98a, "floor": 0x160a16,
         "haze": { "deck": 72, "cover": 0.15, "cloudStep": 20, "puff": 1.2,
                 "cloud": 0xffe4dc } } }
