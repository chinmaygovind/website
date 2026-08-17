"""What Silverstone looks like.

Deliberately the inverse of Spa's palette in almost every choice, because the two
places genuinely are opposites and the pool has only one closed circuit in it so
far. Spa is a wet grey road through a dense pine forest, fogged at 1050 so you
cannot see the far side of the lap, lit by a diffuse overcast with **no sun disc
at all**. This is a July afternoon on a flat Northamptonshire airfield: a real
sun with a halo round it, fog pushed out to 1750 so you *can* see across the
infield, and a thin, sparse, hedgerow-and-copse scatter instead of a forest.

The one change with a geometric reason rather than an aesthetic one is the
run-off. Spa's is grit at 21 units with the armco 26 out past it; here the arena
section comes within **22.8 units of itself** between Village and The Loop, so
two 26-unit offsets do not fit between them. Which is also the authentic answer -
Silverstone's edge is acres of painted tarmac and sawtooth kerbing, not gravel
and a barrier. So `gravel` is recoloured to asphalt and the band is wider, and
the barrier sits outside it on grass rather than behind a trap.
"""

PALETTE = {
# Tarmac. Cooler and a touch lighter than Spa's, because the key light here is
# warm sunlight rather than a grey overcast: a warm light's colour goes through
# sRGB-to-linear and a vertex colour does not, so anything picked at the value it
# should look comes out as mud. Judged in a road view, never in the plan.
"road": 0x434952,
# The kerbs, which at Silverstone are the loud sawtooth ones everybody's
# suspension complains about.
"kerb": 0xf6f3ee, "kerb2": 0xcf3a30,
# Mown grass in July - lighter and yellower than the Ardennes, and far enough
# from `road` in *lightness* that the plan view is not one solid blob. Hue is no
# help there: the plan render is lit flat and shadowless.
"ground": 0x5c7d42,
"rail": 0xdadfe4,
# Hedgerow and copse green, not pine. There is no broadleaf in the scatter
# vocabulary, so the species is a lie the distance covers; the density is not.
"prop": 0x2f5730, "prop2": 0x24422a,
"deco": 0xe8b93c,
# **Not gravel.** The same OFFROAD quad at the same drag - nothing in the
# simulation knows the difference, and a third surface would mean a collider
# `KIND`, a constant in `tuning.py` and a term in `laptime.py`, which is to say
# every medal in the pool. All this does is paint it. A mid asphalt grey, well
# clear of both the road above it and the grass beyond it.
"gravel": 0x767b7d,
# Ground that follows the ribbon instead of one flat plate. The road falls 17
# units, which is a quarter of Spa's 63 and still four times more than a plate at
# `track.ground` could sit under without becoming a collidable ceiling.
#
# `apron` is how far the swept run-off reaches from the road centre before the
# height field takes over; `gravel` is how far out it stays asphalt inside that;
# `armco` is the barrier, which has to sit inside the apron so it stands on swept
# ground rather than on the grid; `clear` is how far out nothing may grow, which
# has to reach past the barrier or the trees come through it.
#
# Read against Spa (38 / 21 / 27 / 44): a *narrower* asphalt band with the
# barrier out past it and a strip of grass between the two - which is what a
# modern Grand Prix run-off looks like and what a gravel trap is not.
#
# The first pass had these at 36 / 24 / 30 / 40 and it was wrong in a way only the
# render showed: a 24-unit asphalt band each side of a 16-unit road paves the
# entire inside of every tight corner, so the arena came out as one grey plain
# with kerb lines painted across it - no visible edge to the track at all, and an
# open invitation to drive over the apex of an 18-radius hairpin. Twelve is a
# generous modern run-off and still leaves the corner a shape.
"terrain": { "apron": 27, "gravel": 12, "armco": 22, "clear": 31 },
# Everything beside the road. Positions are fractions of the lap rather than
# station indices, because the ribbon gets re-solved for closure and that changes
# how many stations there are - the corners stay where they are in the lap, so the
# stands do too. `side` is the road's own right (+1) or left (-1).
"furniture": {
  "armco": 22, "armcoH": 1.5,
  # Sunlit concrete, lighter than Spa's overcast grey.
  "concrete": 0xc0bdb4,
  "board": { "bg": '#12161c', "fg": '#f4f1ea' },
  # The advertising, dealt round the lap in this order. Same nine painters Spa
  # uses plus Costco, which Spa does not - and deliberately in a different order,
  # so nothing lands in the braking zone it lands in there. Every name has to be a
  # key in `SPONSORS` or it comes out as the plain fallback board.
  "sponsors": ['DRIVE', 'GO BIRDS', 'CGOVIND.COM', 'MARLBORO', 'KING OF TOKYO',
             'TACO BELL', 'TICKET TO RIDE', 'CGOVIND.COM', 'RAT SCREW',
             'PENN ENGINEERING', 'DRIVE', 'COSTCO WHOLESALE', 'GO BIRDS',
             'KING OF TOKYO', 'CGOVIND.COM', 'TACO BELL', 'RAT SCREW',
             'TICKET TO RIDE', 'MARLBORO', 'COSTCO WHOLESALE'],
  "boardEvery": 26,
  "boardH": 2.6,
  # Eleven stands against Spa's six, and that is the point rather than
  # excess: this place holds 175,000, the biggest crowd in Formula One, and
  # Village/The Loop/Aintree is *called* the arena because it has seating the
  # whole way round rather than one stand on one side. `stand` drops any of these
  # that turns out to sit across another part of the lap rather than drawing
  # through it, so a few of them may not survive the geometry - which is the
  # trade for asking for a ring.
  #
  # **`off` is set explicitly on every one, and that is the fix for the first
  # render.** It defaults to `armco + 5`, and this palette's armco is 22 against
  # Spa's 26 - so with eleven of them at ten tiers the default put a wall of
  # seating four units closer to the road than Spa's, at every corner. Looking down
  # the Hangar Straight, Stowe's read as a tunnel mouth across the track. Out at 37
  # and a couple of rows shorter, they are a crowd standing back from a circuit.
  "stands": [
    # The main stand down the Hamilton Straight, opposite the pits. The tallest
    # one, because it is the one you are parked in front of on the grid.
    { "at": [0.004, 0.040], "side": -1, "off": 37, "tiers": 8, "text": 'CGOVIND.COM',
      "seat": 0x1a56ff, "trim": 0xf5b301 },
    # Round the outside of Abbey, the fastest first corner in Formula One.
    { "at": [0.044, 0.070], "side": -1, "off": 38, "tiers": 6, "text": 'DRIVE',
      "seat": 0x2f333c, "trim": 0xc0182b },
    # --- the arena ---
    { "at": [0.118, 0.145], "side": -1, "off": 36, "tiers": 7, "text": 'KING OF TOKYO',
      "seat": 0x5c2678, "trim": 0xf2c94c },
    { "at": [0.156, 0.180], "side": 1, "off": 36, "tiers": 7, "text": 'RAT SCREW',
      "seat": 0xb8860b, "trim": 0x3f2311 },
    { "at": [0.200, 0.224], "side": 1, "off": 38, "tiers": 5, "text": 'TICKET TO RIDE',
      "seat": 0x6b4226, "trim": 0xc0182b },
    # Brooklands and Luffield, the slow left-right that ends the back section.
    { "at": [0.338, 0.364], "side": -1, "off": 37, "tiers": 6, "text": 'PENN ENGINEERING',
      "seat": 0x990000, "trim": 0x011f5b },
    # Woodcote, which was the final corner here from 1950 to 2009.
    { "at": [0.392, 0.418], "side": -1, "off": 39, "tiers": 5, "text": 'GO BIRDS',
      "seat": 0x004c54, "trim": 0xa5acaf },
    # Copse.
    { "at": [0.494, 0.520], "side": -1, "off": 38, "tiers": 6, "text": 'CGOVIND.COM',
      "seat": 0x1a56ff, "trim": 0xf5b301 },
    # Becketts, looking across the esses.
    { "at": [0.614, 0.640], "side": 1, "off": 39, "tiers": 5, "text": 'TACO BELL',
      "seat": 0x702082, "trim": 0xf9c72c },
    # Stowe, the big overtaking spot at the end of the Hangar Straight. Further out
    # than the rest: it is the one you look at down the whole Hangar Straight, and
    # at 27 it read as a tunnel mouth across the end of it.
    { "at": [0.826, 0.852], "side": -1, "off": 42, "tiers": 6, "text": 'DRIVE',
      "seat": 0x2f333c, "trim": 0xc0182b },
    # Club, the last corner.
    { "at": [0.928, 0.958], "side": -1, "off": 37, "tiers": 6, "text": 'TICKET TO RIDE',
      "seat": 0x6b4226, "trim": 0xc0182b },
  ],
  # The garages and the pit wall, on the infield side of the Hamilton Straight,
  # which is where they are. The sweeping roof that makes this building the Wing
  # rather than a shed is in `scenery.js` - `pits` draws one shape and it is
  # Spa's.
  "pits": { "at": [0.002, 0.042], "side": 1 },
  # Union flags, which are most of what says *Britain* from inside a corner. Spa
  # and this are otherwise the same kit - a closed lap with terrain, grandstands,
  # hoardings and a pit building - so the flags are doing real work rather than
  # decorating. Two runs: down the pit straight behind the main stand, which is
  # where a circuit actually lines them up, and round the outside of Stowe.
  "flags": [
    { "at": [0.006, 0.042], "side": -1, "off": 33, "every": 4, "h": 11.0,
      "design": 'gb' },
    { "at": [0.828, 0.856], "side": -1, "off": 38, "every": 4, "h": 9.5,
      "design": 'gb' },
  ],
  "spans": [
    { "at": 0.0035, "lights": True, "text": 'DRIVE', "clear": 9.5 },
    # Over the National Straight - the old pit straight, which really does have a
    # bridge across it.
    { "at": 0.455, "deck": True, "clear": 10.5, "text": 'CGOVIND.COM' },
  ],
},
"fog": 0xd3dde6,
# A former bomber airfield in farmland, so this is one of the *sparsest* scatters
# in the pool and the opposite of Spa's 0.34 of dense pine. What makes the place
# read is the runways and the hangars in `scenery.js`, not the planting.
"density": 0.045,
# Weighted away from `bigpine` after looking at a render: a fifteen-unit alpine
# canopy standing near an English airfield is the one thing in this mix that reads
# as the wrong country. `deadtree` is a bare trunk and is the closest this
# vocabulary comes to a hedgerow oak, so it carries more than it does anywhere else.
"props": { "conifer": 0.70, "bigpine": 0.10, "deadtree": 0.14, "rock": 0.06 },
"sky": {
  # u=0 is straight down, 0.5 is the horizon, 1.0 is the zenith. So: bright haze
  # at the horizon, real blue overhead. Spa's dome is grey at both ends.
  "stops": [
    [0.00, 0x9fb6c6], [0.42, 0xc6dae9], [0.50, 0xdcebf5],
    [0.60, 0xa6c8e8], [0.78, 0x6f9fd8], [1.00, 0x4174c0],
  ],
  # High summer cloud, kept faint on purpose. `clouds` is an *overcast* shader -
  # `amount` sets how shadowed the dome is and the docs are clear that discrete
  # cloud in a sky dome reads as pale rectangles however it is shaded - so this
  # is not cumulus and is not trying to be. It is a little texture over blue,
  # against Spa's 1.5 of genuinely broken grey. `lit` has to stay low: it lerps
  # toward white wherever the noise is *thin*, which on a low `amount` is
  # everywhere, and at Spa's 0.45 it would wash the blue out completely.
  "clouds": { "scale": 1.7, "amount": 0.55, "dark": 0xa9b8c6,
            "light": 0xf2f7fb, "lit": 0.16 },
  # A sun with a disc, which Spa deliberately has not got. High and a little
  # behind the pit straight, as a two-o'clock July sun is.
  "sun": { "az": 1.35, "el": 0.62, "color": 0xfff8ea, "size": 300 },
  "glow": 0xfff4dc, "glowStrength": 0.42, "glowMode": "radial", "glowFocus": 7,
  # Warm but not orange, and brighter than Spa's 0.7 without being blinding.
  #
  # **The direction is raking rather than overhead, and that is a render fix.** At
  # [0.42, 0.86, 0.29] the light was almost straight down: a `MeshLambertMaterial`
  # vertical face gets nothing from a light above it, so the pit garages came out
  # very nearly black and every grandstand back and hangar wall with them - the
  # same failure as the note about ceilings in `docs/tracks-and-geometry.md`, on a
  # wall instead of a roof. The disc stays where it is (`sun` below is authored
  # separately from the light, deliberately), only the lighting moved.
  "light": { "color": 0xfff4e4, "intensity": 1.15, "dir": [0.50, 0.72, 0.48] },
  # `hemi.ground` is the bounce and the strongest number in any palette, so this
  # is a *desaturated* green rather than the grass colour: a saturated one stops
  # being a tint and becomes a second key light, which is how a pale road once
  # came out olive-grey. It should read on the car's underside and nowhere else.
  "hemi": { "sky": 0xcfe0f0, "ground": 0x4a5442, "intensity": 1.0 },
  # Far, and that is the whole idea. Spa fogs at 1050 partly to hide the far side
  # of the circuit across the infield; here the far side - and the runways in it -
  # is what you are meant to see.
  "fog": 0xd3dde6, "fogNear": 320, "fogFar": 1750,
} }
