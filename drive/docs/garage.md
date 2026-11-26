# Drive: the garage, liveries and badges

Read this before changing `garage.py`, `garage.js`, `CarView`, the car
model, decals or badges.

## The garage

**`/garage` is a turntable and a set of slots**, and `drive/garage.py` owns the
whole vocabulary - the palette, every slot, every gate and the sentence shown on
a locked one. One module because a locked row promising "a gold on every track"
over a rule that actually wants three is worse than no text at all.

- **Each body has its own seat and its own engine.** `eye: [up, fwd]` on a
  body's entry puts the first-person camera just behind its own windscreen
  at head height; further back and the bottom of the screen looks through the
  cabin floor (invisible from inside) at the road. The engine is `ENGINES` in
  `sound.js`: a waveform built from the body's firing order (cylinder angles,
  each one's loudness, pulse width), played at rpm/120 through its own rev
  range and gears, so a cross-plane V8 burbles and a flat-plane one screams
  rather than one sawtooth at different pitches. The car goes silent
  (`Sound.hush`) while paused, in the garage, or when the window loses focus.
- **Four earned finishes** past matte and gloss, each different in a way flat
  shading keeps (`FINISH` in render.js): rusted (drive 20,000 km), chrome,
  glow and radiant (set 25, 50, 100 track records). **Records set, not held**:
  `DriveStats.record_tracks` is every pool track the account has ever held the
  record on, added by `_note_record` the moment a lap goes on the board and
  never removed, so a record somebody later beats still counts. It was
  backfilled once from lap timestamps (`tools/backfill_records.py`, which can
  miss a record held with a lap later improved on); records held now are the
  floor. Radiant is a fragment-shader hue shift by viewing angle, one
  colour per facet. Bots only ever get matte or gloss (`BOT_FINISHES`), which
  also keeps every bot's existing paint.
- **`bface: [z, y]`** on a body's panel stands its badge upright on a front
  face (the box truck's grille, the bubble car's door) instead of on a bonnet.
- **It is not in the nav any more; it is a button in the game's settings**
  (Nov 2026). "Customize Car" opens `/garage?embed=1` in a frame over the
  track: the same page without the nav or the menu music. Every save posts
  the server-resolved livery to the game (`postMessage`, same origin only),
  which rebuilds `S.view` and the engine voice on the spot, so closing the
  garage is getting back in the new car. The frame is unloaded 2.5s after
  closing, not at once, because the garage's save is debounced 700ms. Solo
  and an account only: a room's car travels with the seat.
- **It took `Log out`'s slot in the nav, and `Log out` moved next to your own
  name on your own account page.** That makes logging out two clicks instead of
  one, which is the trade: the nav slot buys a garage, and logging out is a
  thing you do once a session from a page that is already about you. It is
  `is_me` only, so it is not on a stranger's page. It also cost a CSS fix worth
  knowing about: **`.btn.danger` used to set `width: 100%`** as well as the
  colour. That was redundant where it was used - both of its buttons are inside
  a `.btn-grid`, which sets it already - and it outranks anything a caller sets
  at the same specificity from earlier in the file, so the first `danger` button
  outside a grid came out as a full-width red bar across the page. A variant
  that silently decides layout is not a variant, so the width is gone from it.
- **A car with no garage row renders exactly as it did before any of this.**
  Every default is today's value and `trim`/`rim`/`glass`/`stripe` default to
  `None` meaning "whatever the renderer already did" rather than to a colour
  that happens to match - a literal would be indistinguishable on the day and
  would stop following the body the first time somebody repainted. Pinned from
  both sides: `test_garage.py` on the resolve, and `test_garage_js.py` on the
  built car costing exactly 14 meshes and 7 materials.
- **`HASH_COLORS` is frozen at eight and `PALETTE` is ten**, and the split is the
  whole reason nobody was repainted. `color_for` is
  `HASH_COLORS[sha1(name) % len(HASH_COLORS)]`, so the *length of the list it
  indexes* is part of every answer - hashing over the wider palette would have
  changed the modulus and with it the default colour of every account that exists
  and of every ghost ever recorded. Whatever is offered beside those eight is
  choosable and nothing else.
- **The palette was eighteen and shrinking it needed `RETIRED`.** Eighteen
  swatches is two rows, which reads as a paint chart rather than as a choice, so
  eight came out. But a *body* colour is the one slot that is not free hex, so
  dropping a value from `PALETTE` alone would have made every car wearing one of
  the eight fail `validate` and be repainted to red on its owner's next visit -
  silently, and to a colour they did not pick. `RETIRED` holds those eight and
  `BODY_OK = PALETTE | RETIRED` is what `validate` checks, so a retired colour is
  **offered to nobody and taken off nobody**. `test_garage.py`'s palette checks
  run over `BODY_OK` rather than `PALETTE`, because a colour still being worn
  still has to be one you can pick out mid-pack. This is the shape any future
  palette change wants: `RETIRED` grows, and nothing in the wild moves.
- **The body is a curated palette and the detail slots are free hex.** The body
  is what rivals identify you by, so its separation is guaranteed rather than
  left to whoever is choosing: `test_garage.py` checks every pair at least
  `DELTA_E_MIN` apart in CIELAB, every entry at least `BACKDROP_MIN` from
  tarmac, kerb, grass, a bright sky, a dark sky and snow, and every L* inside a
  band so nothing is near-black or near-white. That check does real work - it
  threw out a forest green 14.3 from grass, a sand 10.8 from a bright sky and a
  gold 13.8 from the yellow already there. A trim or a window is not the thing
  you are picked out by, so those are anything you like.
- **Each detail slot offers its own swatches** (`garage.SWATCHES`), and they are a
  shortcut rather than a rule - `validate` still takes any hex there, which is
  what made trimming these lists free where trimming the body's was not. They all
  offered the *body's* eighteen at first, which is wrong for four slots and absurd
  for one: there was no white, black or grey anywhere in the garage, so a white
  stripe could not be had, and the glass tint could be pink. **Every list is now
  ten or under, which is one row**, because a swatch row that wraps is a block of
  colour the size of the car it is describing. Trim, stripe, roof and badge get
  three neutrals in front of a short bright set; the rim gets its metals first
  (silver, gunmetal, gold, bronze), since a wheel is usually a metal; **glass is
  the one list that replaces the palette rather than extending it**, because glass
  is dark and neutral or it is not glass. `test_garage.py` measures that - every
  glass swatch is L* 62 or under and none of them is a body colour. White is
  offered in the detail slots and still refused on the body, which is the whole
  point of splitting the lists.
- **A finish changes the paint and not only the lighting.** The car is
  `flatShading: true` boxes lit by one sun, so a Phong specular on a face is
  *constant across it* - nothing travels and nothing reflects, and the whole of
  what a shiny finish did was make a sunlit panel slightly lighter. Four finishes
  differing only in how much lighter are four nobody can tell apart, which is what
  they were. So `FINISH` has a `mat` half and a **`paint`** half, and gloss is a
  harder highlight *plus* a deeper, more saturated body colour - the same paint
  read as wet.
- **`FINISHES` is matte and gloss, and `FINISH` still has four entries.** That is
  not an oversight and it is the interesting half. Metallic and pearl were offered,
  and offering four finishes on a flat-shaded car meant two of them were "a bit
  lighter and slightly off-hue" and nobody could say which was which - so the
  vocabulary is two, which are the two that read as different *kinds* of paint
  rather than as two settings of one. But **a stored replay carries an unvalidated
  livery**: `_store_replay` writes what the driver wore on the day, so a race from
  before this change has `finish: 'metallic'` in it and the renderer must still
  know what that means. Deleting the entries would have quietly turned those cars
  matte. `validate` refuses metallic on a *live* car, so the only thing that can
  still reach them is a recording, which is exactly the case they are kept for.
  A pair of tests pins both halves: the two retired finishes still render, and an
  entirely unknown finish is a matte car rather than a crash.
- **The finish applies to the whole body, and its two halves reach different
  things.** The **material** half (`spec.mat` - the harder highlight, and Phong
  rather than Lambert) is what `mat(..., painted = true)` switches on, and that is
  every painted surface on the car: the body, the cabin, the spoiler and its stays,
  the rims and the decals. The **paint** half (`paintOf` - the deeper, more
  saturated colour) is applied at three call sites only: `bodyMat`, `cabinMat` and
  `darkMat`. So a glossy car is glossy everywhere, and a *repainted* one is
  repainted on the three surfaces whose colour somebody chose. Both halves stop at
  the glass, the tyres and either set of lamps, which stay Lambert for the reason
  below. `paintOf` is deliberately not inside `mat`: the decal material is
  `0xffffff` with `vertexColors`, so a paint transform there would multiply every
  stripe and badge on the car by it. `L.body` itself is never touched either, so
  the swatch, the minimap dot and the nameplate still show the colour that was
  chosen rather than the colour the finish made of it.
- **No lamp is customisable, at either end.** They are the only thing a rival
  reads off your car, and the amber drift state was removed for exactly that
  reason; a lamp somebody can recolour is the same mistake with a settings page
  in front of it. That is why the headlights have no slot and are a fixed pale
  white. Glass, tyres and both sets of lamps also stay matte whatever finish the
  paint is wearing - a shiny tyre is not a thing, and a glossy lens fights the
  one signal on the car that has to be unambiguous.

- **Nothing here may touch the simulation** - not ride height, not
  `CAR_RADIUS`, not the wheel radius, not a gram of mass. A cosmetic that
  changed how the car drives would make every time on the board mean something
  different depending on what its driver was wearing.
- **Ten gates, and two of them are past tense.** Pinstripe at a gold on every
  track, split-five rims at finishing every track, and eight badges. Most are
  counters that cannot go down, so storing them would
  be a second copy of something the database already knows. The **laurel** ("set a
  track record") and the **crown** ("top the Time Trials leaderboard") are the
  two anybody can have taken off them, so they are earned once and kept - written
  into `earned_json` the moment they are true. `garage.KEPT` is that pair; `app.py`
  used to carry the literal `{"laurel"}`, and the vocabulary belongs with the
  vocabulary. That is also why neither needs a backfill: every current holder
  qualifies the first time anything asks about them.
- **Retiring the pearl freed a gate, and it went to a badge rather than being
  deleted.** Pearl was "three golds", which is the most achievable gate on the
  list and the one most people meet first, so removing the finish would have taken
  away the first thing the garage ever gives you. `shield` inherited it. There is
  no rule that the number of gates is fixed - the point is that a gate somebody
  has already met should keep paying out something, and moving it onto a new item
  is cheaper than inventing a threshold nobody has tested.
- **A gate can only ask about something already recorded**, and that is what chose
  the badge set. `DriveStats` already has `wins`, `podiums`, `races`, `elo` and
  `distance`, all written today, so none of the eight needed a column - which
  matters because `create_all` makes *tables* and not columns, and a new column is
  a migration by hand on the live box. The thresholds are named
  (`ACE_ELO`, `PODIUMS_NEEDED`, `RIBBON_METRES`) rather than
  buried in the predicates, because they are the numbers most likely to want
  moving once somebody has actually played.
- **`earned` and `progress` are one function read two ways.** `_counts` returns
  every gate's `(have, need)`; `earned` asks whether have >= need and `progress`
  hands both numbers to the chip. They were two lists of predicates, which is a
  shape where a threshold and the count shown beside it can disagree while both
  look right.
- **`records_held()` counts rather than collects.** It returns `{user_id: n}`,
  and a dict answers the only question anybody asks of it unchanged, since
  `user.id in records_held()` reads exactly as it did when this was a set. One
  query for everybody, for the reason it always was: "does this user hold a
  record" asked per person is thirteen queries, and a room broadcasting its
  roster would ask it eight times.
- **The crown moved from three records at once to topping the Time Trial board**,
  and the point of the move is that it used to be the laurel's achievement three
  times over - so the two best badges on the list were about the same thing, and a
  driver quick on three tracks and nowhere else outranked one who was second on
  all of the others. Being first over the whole pool is what a crown should mean. The
  scoring therefore moved too: `garage.time_trial_board()` is the board and
  `_time_trial_board` in app.py is now that plus the ordinals the page prints. It
  had to be one implementation - a gate that computed "who is first" for itself
  is the exact drift `tests/test_no_drift.py` exists for, and this one would show
  as a badge on somebody who is not top of the board people can read.
  `time_trial_leaders()` is a **set**, because the board shares a position on an
  equal score and breaking that tie here would hand the badge out on
  `display.lower()`. Both it and `records_held()` are one answer for a whole room,
  so `_roster` and `_store_replay` ask each once and pass them down - which is why
  `earned`/`progress`/`_livery_for` take a `leaders` beside the `holders` they
  already took.
- **`sunburst` shares `pinstripe`'s condition on purpose.** A gold on every track
  is the thing that badge was asked for, and two items are allowed to want the
  same achievement; giving it a different bar to keep the list tidy would be
  tidiness deciding what the game rewards.
- **`validate` and `resolve` are two functions on purpose.** `validate` stores
  what was asked for, gates and all, so earning an item later puts it on without
  having to ask twice; `resolve` decides what may be *worn* and runs on every
  path that sends a livery anywhere. A client can POST `finish: pearl` all day.
  `validate` also never raises: an unknown key is a client from after the next
  deploy, and a bad value falls back to the default rather than to black.
- **Rims are one merged `BufferGeometry` per style, shared by four wheels.**
  Five spokes as separate meshes is 24 extra meshes on one car and nearly 200
  across a grid, which is real draw-call cost on a phone. Built with `MeshBuf`,
  the project's own triangle accumulator - `mergeGeometries` is a three.js addon
  and is not vendored. Gating a rim on the *colour* once gave `stock` five spokes,
  which triangle counts caught - so the rule was "the style turns a rim on, never
  the colour". It is now **the style, or a colour on stock**: stock has its own
  branch that draws the outer ring alone, no boss and no spokes, so its edge can be
  painted. Drawn only when a colour was actually chosen (`L.rimSet`, which the
  resolved `L.rim` cannot answer because it has a default baked into it), so an
  untouched car is byte-identical to the car it was and a plain car is still 14
  meshes. Two tests: unpainted stock is census-identical to the default car, and a
  painted one grows a ring whose every vertex is at radius 0.35 or more - which is
  what "a lip and not five spokes" means, measured.
- **Decals are quads `LIFT` (0.01) above the panel, wound to face out of the
  car.** The obvious winding is the other one and is silently wrong - the stripe
  still draws and is lit from behind, so a bright stripe comes out as a dark smear
  on the one surface the sun is hitting. `fade` is why they all go through
  `MeshBuf`: a per-vertex colour makes a gradient a lerp written into the
  attribute, in a renderer whose whole look is having no textures.
- **There are three panels, not two.** The bonnet, the roof, and now the car's
  **flanks** - added because two liveries could not be themselves without them.
  `hoop` was a full-width band on the deck at z 0.35-0.85 plus the whole roof, and
  the cabin stands on the deck from -0.15 to 0.9 and is 1.55 wide against the
  body's 1.9, so all that band ever showed was two strips 0.175 wide either side of
  the roof: a painted roof with a pair of tabs beside it. It is now a band up one
  flank, over the roof and down the other. `halves` painted the bonnet full-width
  to z 0.05, putting the join under the windscreen where nothing could see it; it
  is now the front half including the sides, split at the middle of the car,
  because "halves" is a claim about proportion and at the windscreen's foot it was
  28%. Not the front *face* for either - the headlights sit 0.01 proud of it and a
  decal there would z-fight their lenses.
- **The two flanks are mirror images, so one winding cannot serve both.** The order
  that lights the right one correctly lights the left one from inside the bodywork.
  The old facing test could not see either: it asked about the *y* of the normal,
  which a vertical quad has none of however it is wound. Both decal tests are
  panel-aware now, and they classify **per triangle** rather than per vertex -
  a vertex alone is ambiguous, since the widest deck stripes reach x ±0.94 against
  a flank plane at ±0.96, and the flanks run to y 0.53 against a deck plane at
  0.565. Every decal quad is axis-aligned, so the flat axis *is* the panel.
- **`test_a_livery_is_on_the_panels_its_name_needs` is the one that caught `hoop`.**
  Every geometric assertion passed on the old one - valid, wound right, properly
  lifted - and it still was not a hoop, because a hoop goes round something and
  that one only touched the top of the car. There is also a strict "not entirely
  under the cabin" check, which is a real rule and which would *not* have caught
  `hoop`; that is said in its docstring rather than left to be assumed.
- **Car decals are linearised and `MeshBuf` is not.** three.js has colour
  management on, so a `Color` round-trips while a raw colour *attribute* is assumed
  already-linear and gets only the encode out - writing `0x55e08a` into one draws
  it as roughly `0x9cf0c0`. Stripe colours were written raw and drew about twice as
  bright as the chip they came from; that was liveable until a badge had to be
  recognisably *bronze* rather than tan. So `decalMesh` puts every colour through
  `linear()` and **a stripe now matches its swatch**. `MeshBuf` itself is
  deliberately untouched: the twelve track palettes were picked by eye against the
  unmanaged pipeline, and the car's decals are the only consumer that has to match
  a managed colour.
- **`color` is answered from the livery everywhere it is sent.** The car is
  drawn from `livery`, but the minimap dot, the standings row, the chat name and
  the *nameplate over the car* are all drawn from `color` - so reporting the
  seat's stored column raw put somebody's chosen colour on the bodywork and
  their hashed one on everything pointing at them. `DrivePlayer.to_dict`,
  `/api/ghost` and `car_color` all take it off the resolved livery; the column
  is the seed and the guest fallback. **The nameplate over a car is the one thing
  that is the car's own business**, and `setLabel` is called with no colour so it
  falls back to `CarView.plateColor` - which is now **always the body colour**. It
  used to go record green for the laurel, and that was worth it while the badge was
  a bar on the bumper nothing could see. With eight badges, green would mean
  "wearing one of the three green ones", which is not a fact worth a colour; and a
  plate per badge takes away the one thing a plate is good at, which is being that
  driver's colour. The badge is on the bonnet now and says what it says by itself.
  `test_rules_js.py` still reads the calls out of the file and fails on a second
  argument, because building a remote to check it needs a renderer, a socket and a
  track.

## The badge case

Eight badges, each a shape on the bonnet, each free (they go into the same
`MeshBuf` as the stripes). **They have their own file: `docs/badges.md`.**
Read it before adding or changing one — the bonnet is squashed, there is only
one right way round in both axes, and both facts cost iterations.

## The front of the car, and four attempts at it

The rear was always right - a wing, two stays, two brake lamps give it a
silhouette. The front was a plain box face with a narrow dark bumper slab under
it and no lights, and it took four goes to land. The three that were reverted are
worth writing down, because each one failed for a reason the next one repeated:

1. **A sloped snout in the body colour, a full-width splitter blade, headlights.**
   The snout was 1.84 inside a 1.9 body - a 0.03 step down each flank, which reads
   as a part bolted on - and the blade put a second silhouette in front of the
   first. And the cabin was still a plain box, so its front was a dead-vertical
   wall out of the bonnet, which turned out to be what actually looked wrong.
2. **A raked windscreen, and one flush sloped nose.** The screen was right and
   survives. The nose was not: sloping it put a fold across the widest, flattest,
   best-lit surface on the car, and the two sides of a fold catch the light
   differently however well the pieces line up.
3. **No nose piece at all**, the body box run the full length so there was no
   join. That removes the line and leaves a flat slab with a flat face.

**What is there now: nothing.** The body's own front face *is* the front of the
car, the bumper is gone with the overhang it carried, and the only things on the
face are the two lamps, sitting flush in it. The front is about as short as the
rear already was, so the car reads as symmetrical rather than as a long nose with
no tail. The raked windscreen from attempt 2 stays, with the shortened cabin it
needs.

The lessons, in case there is a fifth:

- **A separate panel meeting the bonnet always draws a line across it.** Sloped
  it is a crease, flat it is a step, inset it is a step down the flanks too. And
  deleting the join removes the line without making the car look better, so the
  line was a symptom. The answer in the end was to put nothing there at all.
- **"Flush" means 0.01 proud, not 0.** A lens whose face is exactly coplanar with
  the body's z-fights into a flicker; one a thousandth behind it vanishes inside
  the bodywork. A hundredth is what the livery decals use, for the same reason.
- **`MeshBuf.box` takes half extents and `BoxGeometry` takes full ones.** The
  same-looking z that puts the lamps 0.01 proud of the face puts a `BoxGeometry`
  of the same depth 0.01 *behind* it. That is how the record badge ended up inside
  the bodywork - invisible, and silent about it.
- **The record badge has to be re-checked every time the front moves.** It sits at
  a fixed z, and two of these four rebuilds turned that z from clear air into
  solid body. Nothing errors, nothing looks wrong from any angle, and the badge is
  simply absent. Its test asks "is this box enclosed by another one", found by
  diffing the badged car against the plain one rather than by matching a
  dimension - matching "1.5 wide" caught the windscreen too.
- **The panels' lengths must be named, not written out at each use.** The bonnet's
  length and the roof's each changed twice across the four attempts, and every
  stripe range with the old number baked in ran off the end of the panel it
  decorates - the roof stripes hung half a unit past the front of the roof,
  floating in the air over the windscreen. `liveryMesh` has `NOSE`/`TAIL`/`RF`/`RB`
  and a test walks every livery's vertices against them.

A plain car is **14 meshes and 7 materials** and a fully loaded one 19 and 10.
Fourteen is the count the car has always had, which is not a coincidence: the
windscreen replaced the glass box it was made from, and the headlights replaced
the bumper that came off. The seventh material is the lamps' own and is the only
thing this front costs that the old one did not.


## The bodies

**Ten cars, and the simulation drives one of them.** `model` is a garage slot
like the rims: `classic` (the box car above, and the default, so every account
with no row, every ghost and every stored replay is unchanged) plus `kart`,
`van`, `pickup`, `gt`, `sixties`, `rally`, `muscle`, `proto` and `f1`. The physics car
under all nine is the same 3.4-long box, and nothing in `CAR_BODIES` is read by
`Car`: a time set in the van is a time set in the classic car.

- **Bodies fill the hitbox, on purpose.** Contact is two 1.25 spheres along the
  box, so about 3.8 x 2.4 is as big as a body can be before rivals visibly sink
  into each other ahead of the bump. The classic car is 1.9 wide; the new ones
  are about 2.4, which makes running wide *look* like what it is. It does not
  change the rule: the ground probe is one ray from the centre, so half the car
  is over the edge when it falls whatever the body. `test_a_body_fills_the_
  hitbox_and_stands_on_the_road` pins the size and that the tyres touch y = -0.02.
  The kart is the exception in the other direction, a comedy car in the same box.
- **A body is lofted, and its first version was prisms and was rejected.**
  Side profiles extruded across the car gave slabs with fender blocks stacked on
  the bonnet and tyres half-buried in the sides - "super ass". Now a body is a
  list of cross-sections down the car (`[z, y0,w0, y1,w1, yb,wb, yf,wf, yt,wt]`,
  five points up each side) joined face to face, plus a greenhouse loft whose
  segment flags say glass, roof colour or body colour. Over a wheel `arch()`
  tucks the sill in under the tyre and flares the shoulder out over it, so the
  tyre sits fully visible in a real arch. The reference is real cars in low
  poly: a 911, a Group B hatch, a '69 fastback, a GT40, a hypercar, an F1 car,
  a pickup, a panel van. `parts` keeps convex prisms for wings, mirrors, lamps.
- **Loft faces are wound from the edge, not from a centre.** A bonnet sitting
  down between its wings is concave, and winding against the loft's axis got
  those faces backwards, so every bonnet drew hollow. Each edge's outward side
  is its own direction turned clockwise, the ring being anticlockwise.
- **A tyre's outer face must not be coplanar with a fender's**, or it strobes
  through the paint; `arch()` puts the lip 0.03 outboard of the tread.
- **Liveries follow the loft** (`loftDecals`): deck stripes ride the bonnet and
  deck from station to station, roof stripes every non-glass greenhouse top, flank
  stripes the face between sill and shoulder, cut round every arch. A badge
  takes its height from the bonnet at each point, so it lies on a slope. The
  classic car keeps `CLASSIC_PANEL` and the flat path, byte-identical.
- **Gates are the harder ladder**: kart 100 km, van 5 tracks finished, pickup 1,000 km,
  beetle 2,500 km, GT 3 golds, 60s racer 5,000 km, bubble 8 tracks finished, rally every
  track finished, muscle 10 golds,
  prototype 15 golds, F1 20 golds. **No gate asks for anything multiplayer**,
  badges included, because almost nobody plays it: checkers, podium and
  chevrons moved to solo counters in Nov 2026, and `_or_already` keeps them on
  anybody who met the old condition. All are counters the database
  already keeps. Bots drive everything below the top two (`BOT_MODELS`):
  a prototype or F1 on the grid still means a person earned it, but a grid of
  box cars beside players in vans looked like a different game. The model is
  drawn last in `bot_livery`, so no bot's paint moved.
- Named `CAR_BODIES` rather than `MODELS` because `scenery_kit.js` already has
  a `MODELS`, and the JS tests load both into one QuickJS context.
- **The garage is a showroom.** Every body is parked on its own plinth in a
  row (`carX`), each a `CarView` in your livery, the way Rocket League's Chinese
  build shelves its cars; a column of thumbnails came first and was rejected.
  The arrows, the arrow keys or a click on a car roll the camera along to it,
  and landing on an earned one equips it - a locked one is a ghost with its
  requirement under its name. The camera stays square in front of the row and
  the *car* turns (drag, the view buttons, the idle turntable), so the row is
  always a row across the screen; a neighbour the camera backs into hides.
  Each tab frames the part it edits (`PARTS`: wheels to the front hub, badge
  over the bonnet), Forza's trick. The focused car rebuilds on every change and
  the other nine 220ms later, so a colour drag repaints one car, not ten.
  Randomize rolls paint, pattern, wheels and finish out of what you have earned.
- **Nothing in the garage changes shape when its content does.** `.gopts` is a
  fixed box that centres one row or two; a row that only applies to some
  choices (stripe colour, badge colour) is greyed in place by `.gslot.off`
  rather than added and removed; the Reset button is as wide armed as not; and
  the yellow "something locked in this tab" dot is gone. Asked for in so many
  words, Nov 2026.
