"""What The Gauntlet looks like."""


PALETTE = { "road": 0x33363f, "kerb": 0xe8e4e2, "kerb2": 0xe8453c,
"ground": 0x1b1920, "rail": 0xd8d2cf, "prop": 0x2a2830, "deco": 0xff6a2a,
"fog": 0x2a222a,
"sky": {
  # No sun anywhere in it. The horizon is warm because the lava
  # is lighting the underside of the weather, not because there
  # is anything up there.
  "stops": [
    [0.00, 0x3d1c10], [0.40, 0x4a2314], [0.50, 0x5a2c18],
    [0.56, 0x3a3038], [0.66, 0x2b2831], [0.82, 0x1e1c25],
    [1.00, 0x14131b],
  ],
  "light": { "color": 0xa9b0c4, "intensity": 0.9, "dir": [0.32, 0.9, 0.28] },
  # Ground bounce is molten orange, so every underside in the
  # world glows. That single number is most of what makes this
  # look like a lava field rather than a dark field.
  "hemi": { "sky": 0x39404f, "ground": 0xc2400f, "intensity": 1.0 },
  "fog": 0x2a222a, "fogNear": 190, "fogFar": 780,
},
"below": { "kind": 'lava', "deck": 96, "reach": 700,
         "crustStep": 5, "crustCover": 0.86, "spireStep": 16, "spireDensity": 0.5,
         "lava": 0xff5510, "crust": 0x1b1920,
         "above": { "deck": 120, "cover": 0.5, "cloud": 0x2a2731 } } }
