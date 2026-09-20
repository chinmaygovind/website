"""What BOO! looks like.

**One rule, taken from every reference: the road is the brightest thing in
frame.** In the Twisted Mansion hall and in a real chapel photographed at
night, the floor is the light of the composition and everything around it falls
to near-black. So the road here is pale limestone, the masonry is a cold slate
four or five values under it, and the churchyard is darker again.

**The warm/cold split is the other half.** Everything lit is warm - the
flagstones, the candles, the gold on the altarpiece; everything structural is
cold - the walls, the lead, the sky. That is what stops a dark track reading as
a grey one.

**What is deliberately not copied is the murk.** The Luigi's Mansion ballroom
puts its floor and its walls at the same value, which is atmospheric in a
screenshot and a listed defect here: two colours a few points apart in value
are one colour from above, `plan.png` goes to a blob, and the only check on
layout stops working. Road and ground are separated by lightness, not hue.
"""

import math

from .track import (AISLE_CEIL, AISLE_HW, BACK_X, COL_HW, CRYPT_Y, DOOR_H,
                    DOOR_HW, EAST_X, EAVES, FLOOR_Y, NARTHEX_X, NAVE_CEIL,
                    NAVE_HW, RIDGE, SPIRE_TOP, TOWER_TOP, TRIF_Y, WALL_T,
                    WEST_X)

# The moon's bearing, used twice: once for the disc and once for the key light.
# A disc drawn low with its light coming from the same place lights nothing, so
# the light is lifted well above it - which is the difference between a moonlit
# track and a black one.
MOON_AZ = 4.05

PALETTE = {
    # **Pale, and warmer than the rest of the world.** Worn limestone with the
    # damp in it. It has to survive being multiplied by a cold key light, which
    # is the opposite of the usual warning: the light here is blue, so a road
    # picked blue comes out dead.
    "road": 0x9a9489,
    # Cream and a cold slate. The usual white-and-red is wrong twice - red is
    # the one hue this palette has nowhere else, and against warm stone it reads
    # as a racetrack rather than as a floor.
    "kerb": 0xdcd8cc,
    "kerb2": 0x434f5c,
    # The churchyard. **Five values under the road, and that is the number that
    # matters** rather than the hue: it is what keeps the plan view readable.
    "ground": 0x2c352f,
    "rail": 0x767c84,
    # Dead trees, nearly black. At night a bare tree is a silhouette and nothing
    # else, which is what the Twisted Mansion exterior does with its hedges.
    "prop": 0x232a25,
    "prop2": 0x3b4450,
    # The gold on the altarpiece frame - the one warm accent, and small on
    # purpose.
    "deco": 0xb8912f,
    "fog": 0x201829,
    # **Zero, and that is not "no scenery" - it is "the engine plants none of
    # it".** `addScenery` bails with `if (!onGround) continue`, because there is
    # nothing to stand a tree on in a void, and `ground` here is None. Leaving a
    # density set would have been dead config that reads as a working knob.
    #
    # It is also the fix for the floating rocks. The engine stands its props at
    # `track.ground`; everything here is planted by `scenery.js` on the churchyard
    # apron it draws itself, at the apron's own height, so nothing can hover.
    "density": 0.0,
    # Cold white rather than the usual amber: a warm pad on warm stone is a
    # stain, and this one wants to read as something left on the lane.
    "pad": 0xcfe4ee,
    "padBase": 0x1c2630,
    # **No mushroom over either bounce pad.** The engine dresses a `bn` run as a
    # spotted toadstool on a forty-six unit stalk, which is right for Shroom
    # Street and absurd on a chapel floor - and the colours cannot save it, since
    # the crown is lit and the spots are not, so any pair of numbers is two
    # different brightnesses on screen. `caps: 0` draws none of it. The bounce
    # itself is untouched: the cap is only ever `solid` and `bright`, and the one
    # thing a car meets over the run is the road's own quad. Nothing is drawn
    # over a pad at all now: a figure standing on one was the brightest object
    # on the track sitting exactly where you are trying to look.
    "caps": 0,
    "sky": {
        # **Violet, and the bottom half of the dome is nothing at all.**
        #
        # `u` is 0 straight down, 0.5 the horizon and 1 straight up, so the
        # first three stops here are what you see when you look *below* the
        # churchyard wall - and on a track with no ground under it that is meant
        # to be the void the crypt hangs in, not a paler grey. Black to 0.46,
        # and the horizon itself is only a hint brighter than the black.
        #
        # Above it the band at 0.58 is the moon's own light in the cloud, and it
        # is the brightest thing in the sky by a long way: everything a driver
        # sees of the churchyard silhouette is read against that band, so it
        # carries the same job the old blue-green one did. From there it closes
        # to a deep violet overhead rather than to a blue - which is the whole
        # of "purpler", and it costs nothing because a gradient is six numbers.
        # A shade under three quarters of the first purple all the way up. The
        # band still carries the silhouette - that is its job - but at the first
        # values the sky was the brightest thing on a track whose whole subject
        # is what you cannot see.
        "stops": [
            [0.00, 0x000000], [0.46, 0x030207], [0.50, 0x130c22],
            [0.58, 0x402c59], [0.72, 0x27193c], [0.86, 0x18102c],
            [1.00, 0x0d081a],
        ],
        # A moon, so the halo is tight and `radial`. **`glowStrength` is the
        # number that goes wrong here**: at a daylight value with a low
        # `glowFocus` the glow smears round the azimuth and a midnight track
        # renders as a bright dusk, which is its own entry in the defect list.
        "glow": 0xcbb9e4, "glowStrength": 0.22, "glowMode": "radial",
        "glowFocus": 11,
        "sun": {"az": MOON_AZ, "el": 0.20, "color": 0xf0e9fa, "size": 190},
        # The key comes from much higher than the disc is drawn, or nothing is
        # lit at all. Cold, and not as weak as the instinct says: there are no
        # shadow maps here, so every bit of the darkness has to come out of the
        # palette's values rather than out of anything the light fails to reach.
        "light": {"color": 0xc3bce0, "intensity": 0.98,
                  "dir": [math.sin(MOON_AZ) * 0.40, 0.84,
                          math.cos(MOON_AZ) * 0.40]},
        # **The bounce, which is always the strongest number in a palette.** Wet
        # grass under a blue sky, and it is the *only* thing lighting a downward
        # face: the key points down and there are no shadows, so the soffit of
        # the gallery, the underside of the aisle roofs and the whole vault are
        # lit by this and nothing else. Too low and they render black, which is
        # Rickety Rails' entry in the defect list; too saturated and it is a
        # second key light repainting every upward face in the world.
        # Violet sky bounce now, and the *same* luminance as the blue it
        # replaced - this is the only thing lighting a downward face on the
        # whole track, so a hue change here is free and a value change is not.
        "hemi": {"sky": 0x483c60, "ground": 0x2a332c, "intensity": 0.72},
        # **Tight, and it is doing the horror rather than the darkness.** Far
        # enough to see the next corner, which is what stops it being the "fog
        # you cannot see through" defect, and near enough that the chapel is a
        # shape before it is a building.
        "fog": 0x201829, "fogNear": 190, "fogFar": 780,
    },
    # Rain, which is why the lap opens and closes outdoors. Tokyo Drift is the
    # only other caller; it is the one animated thing in the game, so it lives
    # in `render.js` rather than in any track's scenery. **The key names are
    # Tokyo Drift's and they matter**: `look.py` refuses an unknown key at the
    # top level but does not read inside a block, so a `len` written as `length`
    # is not an error in either language - it is rain of the default length,
    # which is the "palette change that did nothing" defect.
    "rain": {"count": 2400, "color": 0x9fb4c2, "opacity": 0.26,
             "speed": 108, "len": 3.0, "wind": [9, 2], "rake": 0.20,
             "box": 165, "high": 70},
    # **The candles, and they are why `lamps` exists.**
    #
    # `scenery.js` already draws a sconce as an unlit `bright` box, which glows
    # and lights nothing - that is what `bright` is for, and it is what every
    # other glowing thing in this game is. In a black nave it is not enough:
    # the reference is a hall with *pools* of light in it, and a self-lit box on
    # a pier is a bright speck in a uniformly dark room.
    #
    # These are real point lights, moved every frame to the nearest emitters -
    # see `Lamps` in `render.js` for why the count is fixed and why this is
    # visual only, never in the collider. `runs` lays them off the stations
    # rather than at coordinates, so they follow the nave if a leg changes.
    "lamps": {
        "count": 8, "color": 0xffc07a, "intensity": 2.5, "range": 62,
        # Down the nave and back up the aisle, a pool of light every two bays.
        # Sparse enough that the dark between them is the point.
        # **The fractions are measured off the ribbon, not guessed.** Every one
        # of these was wrong by ten to twenty percent of a lap on the first
        # pass, which puts a pool of light in the next room - and the symptom is
        # not a misplaced lamp, it is a section that renders black while the
        # empty stretch before it glows.
        # **Re-measured against the 973-station ribbon**, and this is the second
        # time: they were 0.140 / 0.372 / 0.560 on the 916 the track had before
        # the crypt was rebuilt and 0.131 / 0.352 / 0.532 on the 952 it had
        # before the closing stretch was. Every fraction on a track shifts when
        # any leg of it changes length, wherever that leg is - the closing
        # corners are the last thing on the lap and they still moved the lamps
        # in the nave. Anything authored as a fraction has to be re-measured
        # after a layout change, and nothing will tell you: a stale one is not
        # an error, it is a pool of light in the next room.
        "runs": [
            # **Every 8 stations, not every 22, and that is about the candles
            # rather than about the light.** `Lamps` now builds a real candle at
            # every emitter and lights a flame on the nearest few - so how far
            # apart these are is how far apart the candles are, and at 22 (~75
            # units) the nearest one was usually behind the camera and the nave
            # looked lit by nothing at all. At 8 there is always one alongside
            # and a row of dark ones ahead waiting to catch. The pool is still
            # eight lights however many hundred candles that makes, and the
            # intensity came down to match, or a dozen candles within range of
            # each other add up to daylight.
            # **`off` is 18, not 16, because a candle needs the wall.** The
            # nave's clear half-width is 19, `Lamps` hangs a sconce only where
            # its probe finds masonry within 2.6 units, and at 16 every one of
            # these was three units short - a light with no candle under it.
            {"from": 0.126, "to": 0.330, "every": 8, "off": 18, "up": 7},
            # The gallery, otherwise the darkest stretch above ground: a narrow
            # deck with a balustrade one side and a wall the other, and neither
            # of them catches the moon.
            {"from": 0.343, "to": 0.492, "every": 7, "off": 11, "up": 6},
            # And the crypt, where there is no moon at all - and **`bare`, so
            # this run is light with no candles on it at all.** Thinning them
            # from every 8 to every 18 was not enough: down here a candle is a
            # floor stand rather than a sconce flat to a wall, so it is five
            # units of iron in the open beside the road, and `scenery.js`
            # already stands a pricket on a third of the sarcophagi. Two sets
            # made the crypt a lit avenue. The pools stay exactly as they were -
            # nothing about the lighting changes - and what is lighting them is
            # the crypt's own candles, which are the ones you drive past.
            {"from": 0.519, "to": 0.824, "every": 18, "off": 12, "up": 9,
             "bare": True},
        ],
        # Two on the altarpiece, which is the one thing here meant to be looked
        # at rather than driven past.
        "at": [
            # Two on the altarpiece, on the wall either side of it.
            {"f": 0.243, "off": 18, "up": 7}, {"f": 0.243, "off": -18, "up": 7},
            # **And two standing in front of the great door**, which is the one
            # place on this lap where a candle is the whole point: you come off
            # the churchyard straight at the west front, and two flames either
            # side of the opening are what say the place is occupied. They are
            # outside the building, so there is no wall for a bracket - `Lamps`
            # finds the churchyard under them and stands them on it.
            {"f": 0.121, "off": 11, "up": 5}, {"f": 0.121, "off": -11, "up": 5},
        ],
    },
    # **The lightning, and it is the thing the opening section was missing.**
    #
    # The churchyard is 432 units of the fastest, most open road on the lap with
    # the building sitting in the middle of the windscreen the whole way, and
    # nothing in it happened: four corners, a boost pad and a view. What it
    # wanted was not another corner - it is the approach, and an approach should
    # build - so this is a strike over the chapel about sixty units short of the
    # great door, with the crack arriving four tenths of a second after the
    # light, which is the distance doing what distance does.
    #
    # `f` is a fraction of the ribbon: 0.105 of 952 stations is station 100, and
    # the door is 123. `near` is how close the *camera* has to come, so it goes
    # off around station 88 - far enough out that the chapel is lit by it rather
    # than you being inside the flash.
    #
    # It fires on every lap because it re-arms at `rearm`, and the crypt passes
    # nowhere near it. Second strike on the way out of the cutting, where the
    # road climbs back into the churchyard and the building is behind you.
    #
    # **And the third spot is the jumpscare**, at the lip of the gable, and what
    # it fires is not only light: `onThunder('scare')` in `game.js` is what
    # throws the face up the screen and plays the shriek, so this entry is the
    # trigger for the whole thing. Nothing in the world is drawn for it - see
    # the note where the gable geometry used to be in `scenery.js`.
    #
    # White rather than blue and half the gain, because it is a foot from your
    # face rather than over the roof: a five-times flash at that range is a
    # white screen on the one jump where you need to see where the ground is.
    # `boom: 0` because there is no distance for the sound to cross. `near` is
    # 20, not 45 - it has to go off as the wheels leave, and forty-five units
    # earlier is on the gallery.
    "storm": {
        "at": [{"f": 0.103},
               {"f": 0.489, "kind": "scare", "near": 20, "gain": 2.4,
                "boom": 0.0, "color": 0xffffff},
               {"f": 0.885}],
        "near": 45, "rearm": 95,
        # Five times the key light for a few frames. The palette's own sun is
        # dim on purpose - this is a midnight track - so a flash has to be a
        # multiple of it rather than a fixed level, and the colour is the cold
        # blue-white that a sodium-free sky goes.
        "gain": 5.0, "color": 0xdfe8ff, "boom": 0.42,
    },
    # The chapel. **Stated once, in `track.py`, because the layout is written
    # against it** - this block is only what carries those numbers across to the
    # JS, so there is one copy of the plan rather than the two-in-two-languages
    # this repo has been bitten by before.
    # **Three separate things, and only one of them is under the track.**
    #
    # `kind: void` is what stops `buildTrack` drawing its distant floor plate.
    # It lays one across the whole bounding box at `minY - 34` so that a void
    # has something to look at, which on a track with a crypt in it is a grey
    # lid eight units under the crypt road. Nothing about it looks like a floor,
    # which is why it took three renders to find the first time - and this whole
    # block went missing once already on a careless edit, with no error in
    # either language and the plate quietly back.
    #
    # `above` is the overcast, and it is the only way to get weather *on top* of
    # a track: the sky dome is a gradient and cannot have clouds in it, so a
    # heavy deck is drawn as geometry a long way up. `deck` is measured from the
    # ribbon's own `maxY`.
    #
    # There is **no `haze`** any more. It was a second deck of cloud *below* the
    # track, between the crypt and the nothing, so a fall went into weather
    # rather than into a flat colour - and on a purple sky with a black lower
    # dome it was the one thing stopping the void being a void. What is under
    # the chapel now is nothing, which is what a crypt hanging in the dark
    # wants, and the fall reads as further because there is no scale in it.
    "below": {
        "kind": "void",
        # **Heavy on purpose, and it costs the plan view.** At cover 0.74 this
        # is a lid rather than weather - Cloudbreak, which is a track *about*
        # cloud, uses 0.34 - so `tools/track_views.py` shoots `plan.png`
        # straight into the top of it and the layout cannot be checked from
        # above any more. That is a cost to authoring and not to the game, which
        # is the right way round, and Rickety Rails already has no usable plan
        # view for the same kind of reason.
        #
        # **`deck` is measured off the ribbon's `maxY` (24 here), but it is
        # not where the cloud *is*.** `cloudDeck` scatters each puff at
        # `deckY + (rnd-0.5)*26 + t*10 +- 2.5` with a half-height of
        # `(4+11t)*(0.7+rnd*0.6)*puff`, so at `puff` 2.6 the underside reaches
        # **56 units below `deckY`** - here, y=76. The steeple's cross is at
        # 162, so the top of it is inside this deck and that is deliberate:
        # raising the deck far enough to clear it (205) put its own rim in
        # frame from a camera four units off the floor, and no `reach` or
        # `cover` made that look better than the low lid does. The lid is the
        # track; a spire in cloud on a midnight churchyard is not a defect.
        #
        # **The check for anything else built up there is `maxY + deck - 56`,
        # not `maxY + deck`.** Nothing warns you either way.
        "above": {"deck": 108, "cover": 0.74, "cloud": 0x372a4d,
                  "puff": 2.6, "cloudStep": 12},
    },
    # **No trestle legs.** `buildTrack` stands a pair under a groundless road
    # every twenty-six units so an elevated track reads as built rather than
    # floating. Here the road is on a floor for nearly all of its length -
    # churchyard, chapel, crypt - and that floor is drawn by `scenery.js`, so a
    # rank of posts descending out of the flagstones is the one thing that would
    # give the game away.
    "legs": 0,
    "building": {
        "cryptY": CRYPT_Y,
        "westX": WEST_X, "narthexX": NARTHEX_X, "eastX": EAST_X,
        "backX": BACK_X, "naveHW": NAVE_HW, "colHW": COL_HW,
        "aisleHW": AISLE_HW, "floorY": FLOOR_Y,
        "naveCeil": FLOOR_Y + NAVE_CEIL, "aisleCeil": FLOOR_Y + AISLE_CEIL,
        "trifY": FLOOR_Y + TRIF_Y, "eaves": FLOOR_Y + EAVES,
        "ridge": FLOOR_Y + RIDGE, "wallT": WALL_T,
        "towerTop": FLOOR_Y + TOWER_TOP, "spireTop": FLOOR_Y + SPIRE_TOP,
        "doorHW": DOOR_HW, "doorH": DOOR_H,
        # One bay is a pier, an arch under it and a triforium opening over it.
        # Eight of them down a 326-unit arcade is 41 units each, which at a road
        # width of 16 is about two and a half car lengths between piers - close
        # enough that the arcade is a rhythm at speed rather than a fence.
        "bay": 41.0,
        # Wet stone outside, dry stone inside, and the lead everything
        # structural is roofed in.
        "wall": 0x555f63, "inner": 0x626c6e, "stone": 0x4a5458,
        "lead": 0x3c444a, "floor": 0x8b867c,
        # Drawn unlit, so they read as *lit* rather than as pale panels: the
        # lancets down the aisles, the candles on the piers, and the great east
        # window the moon is behind.
        "glass": 0x8fb6c4, "candle": 0xffd9a0, "east": 0xd8e8f0,
        # **The glass is coloured now, and it is the altarpiece's own palette.**
        # Every lancet used to be one pane of `glass`, which from the nave read
        # as a row of grey slabs - the building's only ornament and it had no
        # colour in it. These five are the sheets the window over the altar is
        # cut from, so the glazing down both aisles and the rose over the loft
        # belong to the same workshop as the one thing the lap is aimed at.
        #
        # They are `lit`, and an unlit colour is lifted hard at the dark end on
        # the way to the screen - so these are authored deeper than they look,
        # and a value that reads right in a swatch comes out as a lamp.
        # **Deeper than they look here, twice over.** An unlit colour is lifted
        # hard at the dark end on the way to the screen, so the first set - which
        # looked like glass in a swatch - rendered as pink, green, blue and
        # yellow poster paint. These are roughly half those values.
        "jewel": [0x141d42, 0x45101d, 0x5e410f, 0x0f2c31, 0x221436],
        # A banner hangs on the nave face of every other pier: the one soft
        # thing in a building made of stone, and the only red in it.
        "banner": 0x5e1524, "bannerTrim": 0x9a7b2a,
        # The pews, and they are solid: the nave is 38 units wide with a 16-unit
        # road down it, so there is room to run wide and something there to
        # regret it with.
        "pew": 0x2e2a24,
        # **The altarpiece.** It hangs on the east wall on the axis, which means
        # it is what you are driving at for the whole length of the nave, and
        # you see it again from the gallery on the way back. `art` is the file;
        # `aspect` is its width over its height, and the quad is authored in
        # world units, so a picture of different proportions needs both changed
        # or it comes out stretched.
        "altarpiece": {"w": 21.0, "h": 29.0, "frame": 0x6b5a2e,
                       "art": "/static/img/art/boo-altarpiece.jpg",
                       "aspect": 620 / 856},
    },
}
