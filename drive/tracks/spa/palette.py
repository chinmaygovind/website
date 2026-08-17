"""What Spa-Francorchamps looks like."""

import math

PALETTE = { "road": 0x3e444e, "kerb": 0xf5f2ee, "kerb2": 0xd23b32,
"ground": 0x4a6b3f, "rail": 0xd8dde2,
"prop": 0x22482f, "prop2": 0x1b3a28, "deco": 0xe8b93c,
# Gravel run-off. Cosmetic only - it is the same OFFROAD surface
# the grass is, at the same drag, and nothing in the simulation
# knows the difference. See `runoff` in buildTrack.
"gravel": 0xc7b48c,
# Ground that follows the ribbon instead of one flat plate. Spa
# is the only track that needs it and the only one that has it:
# its road falls 63 units, and a plate at `track.ground` would be
# a collidable ceiling over the whole second half of the lap.
# `gravel` is how far from the road centre the run-off stays grit
# before it turns to grass; `clear` is how far out nothing may
# grow, which has to reach past the barrier or the forest comes
# through it. `armco` is the backstop: far enough out that going
# off costs you time on the gravel rather than the lap, close
# enough that you never reach the trees.
# `apron` is how far the swept run-off reaches from the road
# centre before the height field takes over; `gravel` is where it
# stops being grit inside that; `armco` is the barrier, which has
# to sit inside the apron so it stands on swept ground rather
# than on the grid; `clear` is how far out nothing may grow.
"terrain": { "apron": 38, "gravel": 21, "armco": 27, "clear": 44 },
# Everything beside the road. Positions are fractions of the lap
# rather than station indices, because the ribbon gets re-solved
# for closure and that changes how many stations there are - the
# corners stay where they are in the lap, so the stands do too.
# `side` is the road's own right (+1) or left (-1).
"furniture": {
  "armco": 26, "concrete": 0xb9b6ae,
  "board": { "bg": '#12161c', "fg": '#f4f1ea' },
  # The advertising, dealt round the lap in this order. Two in
  # three are this site's own games and the rest are the ones a
  # circuit actually carries; the list is long enough, and shuffled
  # enough, that no brand lands twice in the same braking zone.
  # Every name here has to be a key in SPONSORS or it comes out as
  # the plain fallback board.
  "sponsors": ['CGOVIND.COM', 'TICKET TO RIDE', 'TACO BELL', 'RAT SCREW',
             'KING OF TOKYO', 'MARLBORO', 'DRIVE', 'CGOVIND.COM',
             'GO BIRDS', 'TICKET TO RIDE', 'RAT SCREW',
             'PENN ENGINEERING', 'KING OF TOKYO', 'DRIVE', 'TACO BELL',
             'CGOVIND.COM', 'RAT SCREW', 'MARLBORO', 'TICKET TO RIDE',
             'GO BIRDS'],
  "boardEvery": 26,
  # How tall a hoarding on the barrier stands. Width follows, at
  # the 4:1 the sign canvas is drawn to - so this is the only
  # number that sets how big the advertising is.
  "boardH": 2.6,
  # Each stand wears its sponsor's colours - see SPONSORS. Any of
  # these that turns out to sit across another part of the lap is
  # dropped by `stand` rather than drawn through it, which is what
  # happened to the one that used to be behind the pits: twenty
  # units of seating laid over the exit of La Source.
  "stands": [
    # The main stand down the pit straight, opposite the pits.
    { "at": [0.006, 0.068], "side": -1, "tiers": 9, "text": 'CGOVIND.COM',
      "seat": 0x1a56ff, "trim": 0xf5b301 },
    # Round the outside of La Source.
    { "at": [0.080, 0.101], "side": -1, "tiers": 7, "text": 'PENN ENGINEERING',
      "seat": 0x990000, "trim": 0x011f5b },
    # The hillside at Eau Rouge and Raidillon, which is where
    # everybody actually stands.
    { "at": [0.136, 0.172], "side": -1, "tiers": 10, "text": 'DRIVE',
      "seat": 0x2f333c, "trim": 0xc0182b },
    { "at": [0.322, 0.352], "side": -1, "tiers": 6, "text": 'KING OF TOKYO',
      "seat": 0x5c2678, "trim": 0xf2c94c },
    { "at": [0.680, 0.712], "side": -1, "tiers": 6, "text": 'TICKET TO RIDE',
      "seat": 0x6b4226, "trim": 0xc0182b },
    # The Bus Stop, the last corner before the line.
    { "at": [0.938, 0.962], "side": -1, "tiers": 8, "text": 'RAT SCREW',
      "seat": 0xb8860b, "trim": 0x3f2311 },
  ],
  "pits": { "at": [0.004, 0.072], "side": 1 },
  # Belgian tricolours, added when Silverstone joined the pool: the two are the
  # only closed laps and they carry the same kit - terrain, grandstands, hoardings,
  # a pit building - so from inside a corner the only thing telling them apart was
  # the palette. Down the pit straight, and on the hillside at Raidillon where
  # everybody actually stands. Mesh only, so nothing on this track's board moved.
  "flags": [
    # 29 and not 34, and only the render says why. These stands declare no `off`,
    # so they take the default `armco + 5` = 31 - and a flag line at 34 stands
    # *behind* the seating, where from the car it is a row of poles nobody can see.
    # In front of the stand and just outside the armco at 26 is both visible and
    # where a circuit really lines them up. Silverstone's read well at 33 by luck
    # rather than judgement, because its stands are pushed out to 37.
    { "at": [0.008, 0.064], "side": -1, "off": 29, "every": 4, "h": 11.0,
      "design": 'be' },
    { "at": [0.140, 0.170], "side": -1, "off": 40, "every": 5, "h": 10.0,
      "design": 'be' },
  ],
  "spans": [
    { "at": 0.0045, "lights": True, "text": 'DRIVE', "clear": 9.5 },
    { "at": 0.250, "deck": True, "clear": 10.5, "text": 'CGOVIND.COM' },
  ],
},
"fog": 0xc2cbd2,
# The Ardennes is a pine forest, so this is the densest scatter
# in the pool and almost all of it is big.
"density": 0.34,
"props": { "bigpine": 0.5, "conifer": 0.34, "deadtree": 0.06, "rock": 0.10 },
"sky": {
  "stops": [
    [0.00, 0x8d959c], [0.42, 0xb6bfc6], [0.50, 0xcdd4d9],
    [0.58, 0xbcc4cb], [0.74, 0xa2acb6], [1.00, 0x7f8b97],
  ],
  # Broken cloud, shaded onto the dome rather than built out of
  # boxes - see skyDome. Without it a flat grey dome reads as an
  # empty background rather than as weather.
  "clouds": { "scale": 2.9, "amount": 1.5, "dark": 0x67727f,
            "light": 0xe9eef3, "lit": 0.45 },
  # No `sun`, and so no `glow` either - there is nothing for the
  # glow to sit around, and a halo with no disc under it reads as
  # a smudge on the dome.
  "light": { "color": 0xdfe6ec, "intensity": 0.7, "dir": [0.3, 0.94, 0.16] },
  "hemi": { "sky": 0xd2dae0, "ground": 0x3f5236, "intensity": 1.2 },
  # Closer than the sunny tracks. Mist in the trees is the point,
  # and on a 3167-unit circuit it also keeps the far side of the
  # lap from being visible across the infield.
  "fog": 0xc2cbd2, "fogNear": 240, "fogFar": 1050,
} }
