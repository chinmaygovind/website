"""What Monza looks like.

The pool's fourth closed circuit, and the problem is that it is the *third* one
carrying Spa's kit. Spa, Silverstone and Monza all have terrain, gravel,
grandstands, hoardings and a pit building, so from inside a corner the palette is
the only thing telling them apart - which is exactly the note Spa's own `flags`
entry records about Silverstone. Every number below is chosen against those two
rather than in isolation.

What the references actually said, written down before any colour was picked:

- **Monza is not a circuit in a landscape, it is a circuit inside a wood.** In
  the road-level shots the horizon is *trees*, not sky - sky is about 15% of the
  frame, against Silverstone's airfield where it is most of it. So the fog comes
  in and the scatter is dense.
- **There are two greens and they are far apart.** Closed-canopy woodland is four
  or five values darker than the mown verge at the road edge. One green for both
  is what makes a forest read as a golf course.
- **The gravel is enormous and bone-pale.** It is the opposite of Monaco, where
  there is no run-off at all, and it is bigger here than at Spa - which is why
  `terrain.gravel` is 26 against Spa's 21.
- **The road is warm-grey, not blue-grey.** Spa is wet tarmac under an overcast;
  this is a dry street in hard September sun and it reads a step warmer and
  lighter. Still written cooler than it looks, for the usual reason.
- **One thing it would be wrong to copy:** the sunset. The endurance-race
  references are beautiful and Big Red already owns a red sky. Monza is the
  bright one, and that is most of what separates it from Spa.
"""

PALETTE = {
# Dry asphalt in hard sun. Lighter than Spa's wet grey, a touch warmer than
# Silverstone's, and still picked cool of where it should land - a warm key light
# multiplies a vertex colour that was chosen at its apparent value straight down
# into mud.
"road": 0x4b4f55,
# Red and white saw teeth. The reds are what you see of this circuit in every
# photograph of it, and they are the only saturated thing at ground level.
"kerb": 0xf2efe6, "kerb2": 0xc4362b,
# The mown verge, **not** the wood. This is the light green: the metre or so of
# cut grass between the white line and the gravel. The wood is `prop`, and the
# gap between the two is deliberate and large.
"ground": 0x5c7a3a,
# Galvanised steel, with the green debris fencing above it doing most of the
# colour work at ground level. Not Monaco's charcoal hoarding and not a white
# go-kart rail.
"rail": 0xc3c7bd,
# The wood. `prop` is closed-canopy broadleaf - oak and hornbeam, which is what
# the Parco di Monza is - and it is dark, because a forest the same value as its
# own verge reads as parkland.
#
# **`prop2` is the big pine's foliage, and that is not what `look.py` says it
# is.** It is listed there as "second structural colour: trestles, columns", so
# the first pass put the Sopraelevata's weathered concrete in it - and `bigpine`
# reads `pal.prop2` for every whorl, so a fifth of the wood came out as pale
# blue-grey spikes and the render looked snowed on. It is a second, lighter
# green now: the sunlit crowns over the dark mass of `prop`. The banking's
# concrete is a constant in `scenery.js`, where it belongs.
"prop": 0x2b3b1e, "prop2": 0x4a6b2c,
# Gantries, marshal posts, the painted apron inside the chicanes.
"deco": 0xe0b02a,
# The run-off, and there is a great deal of it. Warm and pale.
"gravel": 0xb6ac93,
"fog": 0xc6d2d8,
# See the docstring: the wood is close on both sides for most of the lap, so the
# distance is hazed harder than Silverstone's 1750 even though the day is
# brighter. Still inside the pool's 780..2100.
# Monza's run-off is enormous and this still is - `gravel` 26 against Spa's 21 -
# but the first pass ran it at 30 with `clear` at 52, and the render came back
# with a forty-unit band of empty mown grass between the road and the first
# tree. That is an airfield, and Silverstone already is one. Pulled in so the
# wood stands where it stands in every photograph of this place: at the fence.
# Judged against the *tightest* corner it sits beside - the 19-radius Rettifilo
# on a 13-wide road - rather than against the Parabolica.
"terrain": { "apron": 36, "gravel": 26, "armco": 30, "clear": 40 },
"furniture": {
  "armco": 30, "concrete": 0xcfcabc,
  "board": { "bg": '#13181f', "fg": '#f2efe6' },
  "sponsors": ['CGOVIND.COM', 'KING OF TOKYO', 'MARLBORO', 'RAT SCREW',
             'DRIVE', 'TICKET TO RIDE', 'TACO BELL', 'CGOVIND.COM',
             'PENN ENGINEERING', 'RAT SCREW', 'DRIVE', 'GO BIRDS',
             'KING OF TOKYO', 'TICKET TO RIDE', 'MARLBORO', 'CGOVIND.COM',
             'TACO BELL', 'DRIVE', 'RAT SCREW', 'TICKET TO RIDE'],
  "boardEvery": 26, "boardH": 2.6,
  # Monza's grandstands are bare aluminium rather than painted, so these run
  # cooler and lighter than Spa's - but they still wear a sponsor, because a row
  # of identical silver stands is what made the first pass read as one stand
  # repeated. Placed by fraction of the lap, so they survive a re-solve.
  "stands": [
    # The main stand down the Rettifilo, opposite the pits.
    { "at": [0.004, 0.072], "side": -1, "tiers": 10, "text": 'CGOVIND.COM',
      "seat": 0x1a56ff, "trim": 0xf5b301 },
    # Round the outside of the Variante del Rettifilo - the best seat here, and
    # the one the reference photograph was taken from.
    { "at": [0.166, 0.196], "side": -1, "tiers": 8, "text": 'DRIVE',
      "seat": 0x2f333c, "trim": 0xc0182b },
    # The inside of the Roggia.
    { "at": [0.372, 0.398], "side": 1, "tiers": 6, "text": 'RAT SCREW',
      "seat": 0xb8860b, "trim": 0x3f2311 },
    # Lesmo, in the trees.
    { "at": [0.432, 0.460], "side": -1, "tiers": 6, "text": 'KING OF TOKYO',
      "seat": 0x5c2678, "trim": 0xf2c94c },
    # Ascari.
    { "at": [0.690, 0.722], "side": -1, "tiers": 7, "text": 'TICKET TO RIDE',
      "seat": 0x6b4226, "trim": 0xc0182b },
    # The outside of the Parabolica, which is where the tifosi actually are.
    { "at": [0.892, 0.936], "side": -1, "tiers": 9, "text": 'PENN ENGINEERING',
      "seat": 0x990000, "trim": 0x011f5b },
  ],
  "pits": { "at": [0.002, 0.070], "side": 1 },
  # Italian tricolours down the Rettifilo, the way Spa carries Belgian ones and
  # Silverstone British ones - the three of them wear the same kit otherwise, so
  # from inside a corner the flags are part of what tells them apart.
  #
  # `off` 33 rather than the default `armco + 5` = 35, for the reason Spa's own
  # entry records: a flag line behind the seating is a row of poles nobody can
  # see. Just outside the armco at 30 is both visible from the car and where a
  # circuit really lines them up. Mesh only, so nothing on the board moved.
  "flags": [
    { "at": [0.006, 0.062], "side": -1, "off": 33, "every": 4, "h": 11.0,
      "design": 'it' },
  ],
  # **The deck span is at 0.55 because 0.362 put it inside a braking zone.**
  # That fraction is 1156 units into the lap and the Roggia's braking boards
  # stand at 1083, 1110, 1138 and 1165 - so a deck on two pillars landed in the
  # middle of them and hid the 100 and the 50, which are the two that matter.
  # 0.55 is the straight out of Lesmo 2: no pad, no boards, nothing to mask.
  # Any span added later has to be checked against `bp` the same way.
  "spans": [
    { "at": 0.0040, "lights": True, "text": 'DRIVE', "clear": 9.5 },
    { "at": 0.550, "deck": True, "clear": 10.5, "text": 'CGOVIND.COM' },
  ],
},
# The densest scatter in the pool after Spa's 0.34, and for the opposite reason:
# the Ardennes is a pine forest and this is a broadleaf one, but both of them
# close over the road. **`conifer` is doing duty as a broadleaf here and it is
# the weakest thing in this palette** - there is no broadleaf in the scatter's
# vocabulary (the kinds are conifer, bigpine, deadtree, palm, rock), so the
# shape is wrong even where the colour is right. `deadtree` is up against Spa's
# 0.06 because a bare crown is the closest thing available to a winter oak, and
# `rock` is down to almost nothing because there is no stone in this park.
# Denser than the first pass and weighted much harder to `bigpine`, which is the
# only tall thing in the scatter's vocabulary and so the only one that builds a
# wall of wood rather than a scrub. **`deadtree` is down from 0.14 to 0.04**: it
# is bare brown branches, and at any real weight it makes a winter forest out of
# a September one. `rock` is almost nothing, because there is no stone in this
# park.
#
# **`broadleaf` was added to the scatter for this track**, and it is the one
# thing here that needed a change outside the folder. The kinds were conifer,
# bigpine, deadtree, palm and rock - every tree in the game was a conifer, and a
# wood full of conifers is the Ardennes, which is Spa. The Parco di Monza is oak
# and hornbeam: a bare trunk that forks, with one wide crown on top and the
# bottom third clear. See `trackmesh.js`, and the note in `track.py` about what
# a cached copy of it does with a kind it has never heard of.
#
# **0.34 rather than 0.36, which is Spa's number and the pool's maximum.** The
# first pass went past it and `look.advise` warns at exactly that line - "this
# will be a junkyard" - which `test_no_palette_in_the_pool_is_told_it_is_wrong`
# turns into a failure, on the grounds that a threshold a shipped track trips is
# a threshold nobody believes the second time. It is the right guard: the two
# densest woods in the game should be the Ardennes and the Parco di Monza, and
# neither should be denser than the other by a rounding error.
#
# `bigpine` is kept at a fifth because it is the only *tall* thing in the
# vocabulary and the far treeline needs something standing above the canopy;
# `deadtree` is a seasoning at 0.04, down from a first pass at 0.14 that made a
# winter forest out of a September one; `rock` is almost nothing, because there
# is no stone in this park.
"density": 0.34,
"props": { "broadleaf": 0.60, "bigpine": 0.20, "conifer": 0.12,
         "deadtree": 0.05, "rock": 0.03 },
"sky": {
  # Hard September midday over Lombardy. Saturated overhead, and hazed hard and
  # low where the plain meets it - which is where the Alps are.
  "stops": [
    [0.00, 0x9db4c2], [0.42, 0xc6d8e4], [0.50, 0xdeecf4],
    [0.60, 0x9cc2e8], [0.78, 0x5b93dd], [1.00, 0x2b63c4],
  ],
  # A race weekend here is reliably clear, so this is barely more than Monaco's
  # 0.28 - enough to stop the dome reading as a flat background, not enough to
  # put an overcast over the one circuit in the pool that is supposed to be
  # bright.
  "clouds": { "scale": 2.4, "amount": 0.34, "dark": 0xb9c7d2,
            "light": 0xf7fbfd, "lit": 0.16 },
  "sun": { "az": 1.62, "el": 0.66, "color": 0xfffbf0, "size": 290 },
  "glow": 0xfff7e4, "glowStrength": 0.42, "glowMode": "radial", "glowFocus": 6,
  # Raking less than Monaco's and more than Silverstone's. This track has real
  # vertical faces - six grandstands, a pit building, and a banking - but it is
  # nothing like Monte Carlo's canyon, so the light can sit where a September
  # midday actually is without blacking them out.
  "light": { "color": 0xfff6e6, "intensity": 1.24, "dir": [0.44, 0.78, 0.45] },
  # The ground half is leaf-green rather than neutral, because on a bright day
  # in a wood that is genuinely what is bouncing up. Kept desaturated - a
  # saturated bounce stops being a tint and becomes a second key light.
  "hemi": { "sky": 0xdae8f2, "ground": 0x5a6440, "intensity": 0.98 },
  # Brought in hard from the first pass's 320/1500, which rendered the far side of
# the circuit at full contrast. In every reference of this place everything past
# the near trees is washed toward one pale value - it is a wood on a hot plain,
# and the Alps behind it are barely there.
  "fog": 0xc6d2d8, "fogNear": 260, "fogFar": 1150,
},
}
