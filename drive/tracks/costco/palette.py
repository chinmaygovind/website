"""What Costco Wholesale looks like."""

import math

# The shell, from the track itself. The road is authored to pass *through* these
# walls - in at the front doors, out past the checkouts - so deriving them from the
# road would be circular, and they cannot simply be repeated here either: that is
# what they used to be, once in Python and once in JavaScript, pinned by a test
# that read this file with a regular expression.
from tracks.costco.track import SHELL_CEIL, SHELL_X, SHELL_Z

PALETTE = { "road": 0x585e66, "kerb": 0xf4f4f2, "kerb2": 0xe31837,
"ground": 0x6b6e74, "rail": 0xd8dde2,
# `prop` is the trestle under raised road, and on this track that
# is the rooftop deck - so the deck comes to stand on steel
# columns for free, which is what a rooftop car park stands on.
"prop": 0x9aa0a8, "prop2": 0x7d838b, "deco": 0x0071ce,
# No scatter. The vocabulary is conifer/bigpine/deadtree/palm/
# rock/block and not one of them belongs in a Costco car park, so
# everything outside the walls is placed by `addBuilding` instead.
"density": 0,
"fog": 0xc9d3dc,
"building": {
  "x": list(SHELL_X), "z": list(SHELL_Z), "ceil": SHELL_CEIL,
  # Half-width of a doorway, on the wall. It has to be generously
  # wider than the road: the chase camera trails the car by up to
  # 11.6 units and swings with it, so it comes through the same
  # hole a moment later and from slightly off to one side.
  "door": 24,
  # Concrete outside, painted block inside, and the steel that the
  # frame, the roof joists and the racking are all made of.
  "wall": 0xdcd8d0, "inner": 0xcfcbc4, "steel": 0x8e949c,
  "floor": 0x74777d,
  # Drawn unlit, so they read as lit rather than as pale grey
  # panels: the daylight panels in the roof, the fluorescent
  # battens under it, and the glow off the refrigerated cases.
  "skylight": 0xeef6ff, "strip": 0xfff2d8, "chill": 0xbfe4f2,
  # Racking. Laid at half an aisle either side of every straight
  # aisle station, which is the midpoint between two aisles - so
  # it is derived from the road rather than authored beside it and
  # cannot drift when a leg changes length. `bay` is how long one
  # bay of shelving is, `h` how tall it stands.
  "rack": { "off": 14, "h": 9.5, "pallet": 0xb08657 },
  # The wordmark. Positions are not authored: a facade sign goes
  # over each doorway the road cuts, so it is always over the door
  # however the layout moves, and one more stands on the roof
  # parapet where the deck can read it.
  "sign": { "facade": 'COSTCO WHOLESALE', "roof": 'COSTCO WHOLESALE',
          "food": '$1.50 HOT DOG' },
  "lot": { "line": 0xe8e8e4 },
},
"sky": {
  # A big flat afternoon over a big flat car park. The sun is well
  # up, so the glow is `radial` - a halo round the disc - and not
  # the horizon smear a sunrise wants.
  "stops": [
    [0.00, 0xa8bccb], [0.42, 0xc8dae7], [0.50, 0xdcebf5],
    [0.60, 0xa9c9e6], [0.78, 0x74a5da], [1.00, 0x4478c4],
  ],
  "glow": 0xfff6e0, "glowStrength": 0.6, "glowMode": 'radial', "glowFocus": 5,
  "sun": { "az": 1.15, "el": 0.52, "color": 0xfffaf0, "size": 330 },
  "light": { "color": 0xfff6e8, "intensity": 1.34,
           "dir": [math.sin(1.15) * 0.62, 0.78, math.cos(1.15) * 0.62] },
  # The bounce, and the single highest-leverage number here: over
  # concrete and asphalt it is a neutral grey, which is what keeps
  # the undersides of the car and the roof steel from picking up a
  # colour the site does not have.
  "hemi": { "sky": 0xdfe9f2, "ground": 0x6a6d72, "intensity": 0.95 },
  # Far enough out that the warehouse is never hidden by haze from
  # the far side of its own car park.
  "fog": 0xc9d3dc, "fogNear": 300, "fogFar": 1400,
} }
