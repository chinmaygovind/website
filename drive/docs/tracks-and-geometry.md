# Drive: tracks, geometry and look

Read this before changing `tracks.py`, `trackmesh.js`, `course.js`, the
collider, or any track palette/sky.

## Boost pads

- **A boost pad is a surface, not an object.** `Builder.boost(length)` flags the
  stations it lays, their road quads go into the collider as `KIND.BOOST`
  alongside `ROAD`/`WALL`/`OFFROAD`, and the ground query the car already runs
  finds it - so a pad needs no new collision code and would work upside down
  inside a loop for the same reason a half-pipe does. The chevrons are drawn
  into the `bright` (unlit) buffer, so a pad glows on Spiral Ascent's midnight
  road exactly as it does in daylight.
- **It is more engine, not a raised limit** (`PAD_ACCEL_MULT` 1.7, `PAD_BOOST`
  1.3s), which is the same term the slipstream and catch-up multiply. **But a
  pad and a tow take the larger of the two rather than the product**: three
  multipliers at once is 92 u/s against a hard clamp of 85, and then the clamp
  sets the top speed instead of the tuning - and a tow is earned where a pad is
  handed to everybody, so multiplying them makes a pad worth most to the car
  already being helped. Catch-up still stacks, landing at 75.
- **Touching a pad arms it; staying on re-arms it.** So a pad is a *place*
  rather than a distance, and the car crawling out of a slow corner gets the
  same second of engine as the one flying over it. `onBoostPad` is a callback
  rather than a flag on the car, like `onBump` and `onLand`: the physics steps
  at 1/120 and the frame loop reads the car at 1/60, so a flag would lose every
  other pad.
- **`Builder.boost` only lays straight road**, and that is the rule rather than
  a gap. A pad is worth about a second of unarguable speed, so it belongs where
  the speed is usable - out of a slow corner, down a straight, into a jump - and
  never mid-corner, where all it does is take away the decision the corner was
  for. `test_boost.py` checks it on every track in the pool.
- **`laptime.py` models the pads, or the medals would be soft.** It solves the
  speed profile, asks where the boost then reaches, and solves again; a track
  with no pads settles after one pass and is timed exactly as it always was.
  Finding this needed a fix in `_corner_speed`, which used to bisect up to a
  hard ceiling of `MAX_SPEED` - so a boosted station's raised cap was thrown
  away on anything straight, which is the only kind of road a pad is laid on,
  and four pads came out worth 0.29s instead of 1.8. Every other test passed.
- **A remote car's pad boost is not on the wire and does not need to be.** A tow
  is invisible, so a rival winding one up has to be drawn or nobody could answer
  it; a pad is a lit strip of road everybody can already see.
- The world under it needed a new hook. `below.haze` draws a cloud deck at its
  own depth *between* the road and whatever is beneath it, and any `kind` can
  carry one - the default world's deck is welded to the towers drowned in it, so
  "above the weather, with a city much further down" could not be said. Under a
  red sunset that came out as pale mesas standing on dark pillars, which is
  stone; `kind: 'downtown'` plus a thin haze is a city with lit windows and some
  cloud drifting over it.

## Closed circuits, terrain and trackside furniture

All three of these exist for Spa and nothing else uses them yet. They are
written to be general, but none of them has ever had a second caller, so treat
the second track that wants one as the thing that will find the bugs.

- **A closed lap is a ring whose finish gate is its start gate.** `tracks.CLOSED`
  is the set. `Builder.finish_at_start` copies the start gate rather than laying
  a new one, because on a ring the road under the line was already laid by
  `start` and `finish` would build a second pit straight on top of the first.
  Crossing that plane on lap zero is harmless *only* because `Run._advance` in
  course.js will not credit a finish until `nextCp >= cps.length`; if that guard
  ever goes, every closed track finishes the instant it starts.
  **Both halves of that branch need to know.** The guard stops the lap being
  *finished* on the grid, and then the `else` fell straight through to "you
  skipped one" - so Spa opened every attempt with **Missed a checkpoint!**
  before the car reached the first corner. `Run.closed` suppresses the warning
  at `nextCp === 0` only, which is the difference between not telling somebody
  off for starting and never telling them anything: come back round to the line
  having actually skipped a gate and it still fires. `test_closed_lap.py` walks
  a stub car through the line and pins all three.
- **The join has to be invisible to the proximity checks.** `self_proximity` and
  `crossings` decide "these two stations are neighbours, not a crossing" from
  the gap between their *indices*, which on a ring is wrong at exactly one
  place: station 0 and station n-1 are touching and maximally far apart by
  index. Both take the gap circularly when `track["closed"]`. Without it the
  seam is reported as the worst car trap on the track and `gate_ceiling`
  collapses to its 5.0 floor, which quietly costs you checkpoints.
- **Closing the ribbon is a solve, not authoring.** Fix the corner angles so
  they sum to exactly 360 and the heading closes for free; that leaves two
  equations for the position and so two free lengths. `tools/close_spa.py`
  Newtons on them **through the real `Builder`** and prints the answer to paste
  into the function's defaults. It drives the real builder on purpose: the first
  version reimplemented the turtle in the plan view, got `_frame`'s handedness
  backwards, closed perfectly in its own model and left the actual ribbon 66
  units out. Do not write a second copy of the kinematics.
- **Clearing `self_proximity` is not the same as having room.** Spa's Pouhon and
  Blanchimont legs first passed 6.5 units apart, which is a car trap; pushed to
  15 they passed the check, and their *kerbs were still touching*, so there was
  physically nowhere to put the run-off and the barrier. The check is a floor on
  safety, not on whether a circuit with furniture fits. Budget the room the
  scenery needs separately, and remember the tightest gap a track is allowed to
  have is whatever its own hairpins already do.
- **The run-off is swept along the ribbon, not sampled from the height field**,
  and that is not a preference. The field is an 8-unit grid whose vertices do
  not lie on the road edge, so a cell straddling the kerb interpolates across it
  and lands above the tarmac in some places and below it in others. What that
  looks like is gravel sawing in and out of the road, gravel lying *over* the
  road after a checkpoint, and a hole at the edge of a corner you drop through -
  all one bug. `addApron` builds from the same stations and the same `lat` the
  road does, so its inner edge *is* the road's edge.
- **Anything within the apron stands on its own road, never on
  `terrain.height`.** The field returns the height of whatever road is
  *nearest*, so beside a place where two legs pass close it flips from one leg
  to the other. Sample it for a barrier post and the barrier zigzags through
  forty units of height; sample it for the outer corner of a run-off quad and
  the quad becomes a skewed sheet thrown across the infield. Both of those
  shipped and both looked like "stray quads". The rule is: inside the apron use
  `station.p[1] - drop`, outside it use the field.
- **Two rules must never both decide who draws a piece of ground.** The apron
  clips itself back wherever another leg is nearer, and `drawTerrain` used to
  skip the cells the apron covers. Those two disagreed about the strip in
  between and neither drew it, which puts holes in the floor - and what you see
  through a hole in the floor is the sky, so it reads as pale grey shards lying
  in the infield rather than as a hole. They are coplanar where they overlap, so
  the fix is to let both draw and lift the apron to settle the depth test.
  Overlap costs a few thousand quads; a hole costs you the car.
- **Two surfaces a hair apart are only safe while they agree, and for a while
  these did not.** The lift was 0.03, which is plenty for two surfaces that
  really are coplanar - and the height field was not one of them, because it took
  its height from the nearest *station* while the apron interpolated between two
  of them. A station is 0.64 units of descent on Spa's steepest grade, so the
  field stepped where the sweep ramped and stood up to a third of a unit proud of
  the gravel: **19% of the run-off had grass standing above it**, and what that
  looks like is the run-off torn into patches with green wedges through it, worse
  the steeper the hill. It reads as bad texturing rather than as two surfaces
  fighting, which is why it survived being looked at. Three things fixed it and
  all three are worth keeping. The field takes its height from the nearest point
  **on the ribbon**, interpolated along the segment, which is exactly what the
  sweep does - so on a straight they now agree to the bit. The lift went to 0.15,
  an eighth of the drop and past the 99th percentile of what disagreement is
  left. And `drawTerrain` paints its own cells grit inside the gravel band, so
  anything that does poke through is already the right colour - which also covers
  the far side of the infield, where past about 450 units the depth buffer cannot
  resolve 0.15 either.
- **Furniture has to be drawn double-sided.** See the note further down about
  `MeshLambertMaterial` and mirrored placements - it is the same trap.
- **`pal.terrain` replaces the flat ground plate with a height field sampled off
  the ribbon.** Every other ground track keeps its road between 0 and 20 and
  sits on one collidable quad at `track.ground`; a track that falls 63 units
  would have that quad through the middle of it as an opaque ceiling. Near the
  ribbon it is the height of the closest point *on* it; further out it blends
  into an inverse-distance-squared average of the stations in reach. Built once
  at `CELL` and bilinear-sampled after that, and deliberately derived rather than
  authored so it cannot disagree with the road. One sampler then places the
  ground, the gravel, the trees, the armco and the grandstands, which is what
  stops any of them floating.
- **Gravel is a colour, not a surface.** It is the same `OFFROAD` quad at the
  same drag as grass, painted differently. A third surface would mean a new
  collider `KIND`, a constant in `tuning.py` and a term in `laptime.py` - which
  is to say it would move every medal time in the pool for the sake of one track.
  Both surfaces over that ground carry the colour: the swept apron draws the
  clean edge, and `drawTerrain` paints the cells under it to match, tested at
  each cell's *middle* rather than at any corner - erring a whole cell wide lays
  an eight-unit ring of grit outside the band, and every place the field stands
  proud out there is then a tan wedge lying in the grass.
- **An armco is not a `rail`.** A rail is a wall on the kerb and makes the
  run-off decorative. `addArmco` walks the ribbon at a fixed lateral offset past
  the gravel and stands a wall on the terrain, so going off costs time rather
  than the lap. Where the circuit doubles back there is no room for it, and
  nothing has to know which corners those are: if the nearest road centre to a
  post is closer than the barrier's own offset, some *other* part of the track
  is there and the run is cut. It draws both faces and adds **one** collision
  quad, for the reason `wallStrip` gives.
- **Furniture is placed by fraction of the lap, not station index**, because the
  ribbon gets re-solved for closure and that changes how many stations there
  are. The corners stay where they are in the lap, so the stands do too.
- **A stand and a shed are both extrusions along the ribbon, so both need ends
  and a bottom, and neither had them.** Every face was authored per *segment* -
  treads, roof, back wall, front skirt - which builds a tube: from anywhere but
  square on you look straight into it and see the inside of its own roof, and
  because the seating in there is lit the eye reads it as a room rather than as a
  missing face. Each stand now closes with one slab from the ground to the roof
  at each end. Stepping that slab to follow the seating was the first go and is
  wrong: it leaves the triangle between the top row and the roof open, which is
  precisely the hole you were looking through.
- **The kerb lip has to reach the kerb, and on a banked station that is not
  `drop` above the run-off.** The apron is one horizontal band at the station's
  *centre* height, so a roll puts one kerb above it and the other below - 1.17
  units either way through Pouhon's eight degrees, against a drop of 1.2. The lip
  under the kerb was a fixed `drop` tall, which through there built a wall
  standing 1.19 units *over* the road it was supposed to be holding up: from the
  car, the left-hand edge of the track lifted into the air for the length of the
  corner, with the kerb hidden behind it. The outside had the same bug the other
  way, a lip 1.16 too short to meet a kerb left hanging. It takes the road edge's
  own height (`e.lat[1] * hw`) instead. Two related things follow. The apron's
  lift has to be **squeezed to nothing on a banked station** - the whole gap
  between the run-off and the low kerb there is 0.03, so a flat 0.15 lays gravel
  over the last metre of tarmac. And `drop` is now the *ceiling* on how far a
  ground track may be banked: past `drop / hw` in radians the run-off surfaces
  through the road and no lift can save it.
- **A building stands on the highest ground under it, and has to be carried down
  to the ground everywhere else.** A grandstand did that already (`foot`, the
  skirt under the front and back walls); the pit building did not, so it was a
  flat-bottomed box at the La Source height with its far end eleven units off the
  ground - and that end is the first thing on your right on the grid, which is
  where it was reported from. Anything level laid along a slope needs the same
  plinth. It is not a rounding error you can shim away: the pit straight climbs
  eleven units, and this is the only track in the pool where trackside furniture
  has to cope with a grade at all.
- **A long building is truncated by the circuit, not by its authored end.** The
  pit building is 13 units deep standing 35 out, and La Source turns the whole
  thing back through 170 degrees a hundred units later - so the authored range
  ran its back wall across the road down to Eau Rouge and finished it three
  quarters of a unit from that road's centreline. `pits` now walks its own
  footprint and stops at the first station where `toRoad` says another leg is
  under it, which is the same signal the armco, the run-off and `stand` all read.
  The difference from `stand` is what to do about it: a grandstand is dropped
  whole, a building down the pit straight is shortened, because most of it is
  where it belongs. Clearance is twice a road's half width - enough to keep it
  off the tarmac with run-off still showing between, and no more, because Spa's
  own legs pass as close as 43 units and there is not room to clear the armco.
- **Draw trackside furniture double-sided.** The world mesh is
  `MeshLambertMaterial`, which is `FrontSide`. Furniture is placed by a signed
  `side`, and flipping that sign mirrors the geometry and therefore reverses
  every quad's winding - so a stand authored on the left renders and the
  identical one on the right is invisible from the track. This is not
  hypothetical: it is how the pit building spent an afternoon as an invisible
  shed with a roof floating in the sky, and it is only findable by looking.
- **The sponsor boards are the only textured geometry in the game.** Everything
  else is flat-shaded vertex colour. A hoarding has to be readable and letters
  built out of boxes stop being letters at about forty units, which is where you
  see them from, so boards get a `CanvasTexture` - the same trick render.js uses
  for the name tags. They are batched by word, so the whole circuit's
  advertising is nine or ten draw calls.
- **A board is one flat quad and nothing it stands on is flat.** Both halves of
  that cost something. A hoarding on the barrier takes `r` from the *3D* chord
  and its up vector from `n x r`, so it leans with the ground the way the armco
  beside it always has; a horizontal board on a slope has to choose a height,
  and whichever it chooses one end is buried and the other is flying - Spa falls
  up to 0.64 a station and a board spans five of them, so that alone is +/-1.6.
  It then clears every post *under* it rather than the two it is hung from,
  because the chord cuts beneath the polyline over a crest and it is the middle
  that surfaces. Before this, **61 of Spa's 67 boards had their bottom edge
  underground**, by a median of 1.8 units and as much as 4.3.
  - **`n x r` points at the ground down one side of the circuit.** `n` faces
    the road rather than following from `r`, so it is `r` turned a quarter turn
    one way along the left-hand barrier and the other way along the right. Take
    it as up and every board on one side is built upside down, printed
    mirrored, and 2.9 units into the earth. Force the sign.
  - **Size a hoarding, do not derive it.** `hw = L/2, hh = L/8` made a board as
    wide as whatever five stations happened to span and four times taller than
    the armco it hung on, which is most of how it got underground. It is
    `boardH` in the palette now, with the width following at the 4:1 the canvas
    is drawn to.
- **A board on a grandstand roof has to be short enough to stay on it.** A stand
  round the outside of a 170-degree corner is curved and the board is not, so a
  straight board as long as the stand leaves the roof at both ends. `stand`
  walks out from the middle until the roof under the board has wandered off the
  tangent by more than the roof is deep, and stops there - full width on a
  straight stand, shorter at La Source. It also stands *on* the roof rather than
  hanging in front of and below the lip, which is what put three of the four
  through their own back rows.
- **Keeping off the road is not the same as keeping off the barrier.** A stand
  refuses to build where `toRoad` says another leg is under it, and can still
  be sat squarely on that leg's armco - it stands 31 out and Spa's own legs pass
  as close as 43. A board hung on that armco then comes out of the middle of a
  grandstand's end wall. `addFurniture` publishes a keep-out box per segment
  (not one round the whole building - the La Source stand's bounding rectangle
  is most of the infield) and `addHoardings` skips any board that lands in one.
- **The boards' fonts and logos arrive after the track is built, so the canvas
  is painted twice.** Four faces are self-hosted for the boards alone and
  nothing on the page is set in them, which means the browser never fetches
  them unless `document.fonts.load` asks by name - `document.fonts.ready`
  resolves perfectly happily having loaded nothing. The logos are `Image`s off
  the static tree. Both are awaited on **one shared promise**: giving each
  texture its own `onload` on the shared `Image` objects means the last
  board's handler replaces the previous one's, and the only board on the
  circuit that ever repaints is whichever was built last. All of this fails
  quietly - you get the layout you designed, in the wrong typeface, with
  nothing where the logo goes - and the preview picture is taken by a headless
  browser that owns almost no fonts at all.
- **Nothing in the suite could see a board at all, and three bugs lived there.**
  `buildTrack` guards the whole sign block with `typeof document !== 'undefined'`
  so the anti-cheat can run the real file in QuickJS, and that guard also walks
  `test_every_track_can_be_built_without_a_browser` straight past every painter.
  What grew behind it: the four outside marks were converted from canvas paths
  to real artwork, three call sites were left calling helpers that had been
  deleted, and `SPONSORS['PENN ENGINEERING']` threw `ReferenceError` inside
  `buildTrack` - **so Spa did not render a single frame, with a green suite**.
  `tests/test_boards.py` paints all nine against a stub canvas now. Anything
  added to a board painter has to stay reachable from there.
- **A mark that fails does it by leaving a gap, not by throwing.** `mark` fits
  artwork into a box and every call site passed six arguments to its seven, so
  the tint landed in `maxH`: `NaN` for a colour, `0` for a `null`, a degenerate
  rectangle into `drawImage`, and **not one of the seven logos ever drawn**. The
  boards still painted, correctly laid out, with holes where the marks go - which
  from the car is a white rectangle, and which nobody notices because that is
  roughly what a distant hoarding looks like anyway. The test checks the
  destination rectangle of every `drawImage`, which is the only way this is loud.
- **Crop off a rasterised copy, never off the SVG.** Two of the brand files stack
  the mark above the name and a hoarding is 4:1, so they are drawn as two source
  rectangles side by side - fitted whole, the Taco Bell lockup is a fifth of the
  board wide and the rest is plate. But a source rectangle on an `<img>` holding
  an SVG is measured against whatever the browser rasterised it at, which equals
  `naturalWidth` only if the file carries width and height attributes.
  `marlboro.svg` carries only a viewBox, so it reports the 249x150
  default-replaced-element size and then reads its crop against a much bigger
  bitmap: the roof came out a plain red bar and the wordmark came out as the
  right-hand slope of the roof with the tops of four letters beneath it. Every
  other file has intrinsic dimensions and cropped correctly, which is how it
  survived being looked at. `sheet()` rasterises once at a known size and the
  crop indexes into that, where a pixel is a pixel.
- **Three of the four outside brands need no font, and one cannot have one.**
  Penn, Taco Bell and Marlboro all ship their own lettering inside their
  artwork, and all three use commissioned faces with nothing public behind them
  - so the file *is* the correct wordmark and setting the name beside it in type
  would be both a guess and a second copy of the name. `GO BIRDS` is the
  exception and the reason the fourth font exists: it is a fan phrase, not a
  wordmark, so no artwork of it exists to draw.

## Interiors (`addBuilding`, Costco Wholesale only)

The Costco is the pool's only interior: the only track where solid geometry
surrounds *and covers* the road. Like closed laps, terrain and furniture, it is
written to be general and has exactly one caller, so treat the second track that
wants a building as the thing that will find the bugs.

- **It is a sibling of `addScenery`, not a use of the `furniture` block.**
  `addFurniture` is only reachable from inside `buildTrack`'s `else if (terrain)`
  branch, so borrowing it would mean giving a flat track a height field it has no
  use for - and its vocabulary is grandstands, pit buildings and gantries, which
  is not what a warehouse is made of. What it does borrow is the parts already
  proven: both faces on every quad, the `bright` buffer, and the `signs` contract.
- **The shell is the one thing authored twice, and that is deliberate.**
  `SHELL_X`/`SHELL_Z`/`SHELL_CEIL` in tracks.py and the `building` block in the
  palette are two copies of three numbers, pinned together by a test, exactly as
  Sandy Cove's waterline is. Deriving the box from whichever stations are indoors
  sounds tidier and is circular: the wall position would depend on the set of
  stations you are using to decide where the wall is, and a doorway then lands
  mid-descent or halfway round a corner depending on the margin. Everything else
  is derived - the doorways are where the road crosses a wall, the holes in the
  roof are where it crosses the roof plane, the racking stands half an aisle out
  from every straight aisle station.
- **A roof-hole test must ask "near the plane", not "above it".** The rooftop deck
  is road standing *over* the roof. A test for road above the ceiling therefore
  catches the deck too and carves its whole rectangular loop out of the roof it
  stands on - and what that looks like from the aisles is a moth-eaten ceiling
  with daylight coming through, which reads as a lighting bug rather than as
  missing geometry. It is also why `SHELL_CEIL` and `DECK` move together: the
  window needs a real gap between them to tell the two cases apart, so raising the
  roof means raising the deck, and raising the deck lengthens both travelators,
  because a hill needs `length >= sqrt(330 * rise)` before it stops being a hill.
- **A ceiling has to be drawn *unlit* or it is black.** A downward-facing quad
  gets nothing from a key light overhead and only the hemisphere's ground colour
  from below, and there are no shadow maps here - so a "correctly" lit ceiling
  over the car comes out very nearly black, which is the most obvious thing in the
  building. The roof's top goes in `solid` (it is the floor of the view from the
  deck) and its underside in `bright`.
- **The roof needs real thickness, and so does everything else laid on a face
  here.** Top and soffit at the same `y` are coplanar quads in two different
  meshes, which is a depth-buffer coin toss: the roof flickers between the two as
  the camera moves, and from inside that reads as the ceiling strobing. The same
  bug in miniature hit the shelf beams (long tan splinters shooting off down the
  aisle, which reads as stray geometry rather than as z-fighting) and the chiller
  glass. Give the slab depth and stand anything applied to a face off it. `0.05`
  is not enough: the run-off's own note puts the floor nearer `0.15`.
- **Racking, tills and the food court have to be told apart.** The racking rule -
  every straight floor-level station inside the shell - also catches the run out
  through the checkouts, and shelving that too leaves the last stretch indoors
  indistinguishable from the four aisles you just drove. The checkout run is found
  rather than authored: it is everything still at floor level after the travelator
  brings you back down, so it survives the lap being retimed.
- **`const` in a long function is not merely hoisted.** The food court hangs its
  board while it is building its counter, which means it uses the sign helper
  before the signage section declares it - and a `const` is in its temporal dead
  zone until its own line runs, so that throws rather than reading as undefined.
  Helpers used by more than one section go up with the rest of the helpers.
- **The rooftop railing cannot be a ribbon `rail`.** This is a ground track, and
  `test_barriers_are_opt_in` requires a ground track to carry *no* walled stations
  at all. So the parapet along the deck is collider geometry standing beside the
  road, the way the racking is - which also keeps it outside the kerb, so the
  racing line never touches it and no medal time moves. It takes its up vector
  from the station's own normal, so it leans with the banking.
- **A car park is paint, not posts.** Lamp columns were the first go at the lot and
  they are wrong twice over: from a car they are a field of grey posts with no cars
  under them, which reads as scaffolding, and being the only vertical thing out
  there they pull the eye off the building. What says "car park" at this scale is
  bays marked as `|_|` - two sides and a closed end, drawn as one unlit quad per
  line, in nose-to-nose rows sharing their head line.
- **`toRoad` needs a height window on a track with road over road.** The nearest
  road in *plan* is the right question for Spa, whose legs all lie in one sheet.
  Here a car park flies 14.5 units over the aisles, so a plan-only answer reports
  the deck as being "at" every point beneath it. What that cost, silently: the
  racking down one side of an aisle, because the deck's south leg passes 4.7 units
  from it in plan and three metres over its head. One aisle came out shelved on
  one side and nothing else was wrong.
- **A support may not stand on a road.** Until a track put a car park on its own
  roof, raised road was only ever over *ground*, so `buildTrack`'s trestles never
  had to ask. The deck flies over four aisles and its legs came down straddling
  roads you drive along - and they are drawn but never collided, so they were a
  pair of ghost pillars in the middle of an aisle. `overRoad` drops the pair
  rather than the run, because where the deck is over open floor the legs are
  right; the building's own column grid carries the look everywhere else.
- **Two camera numbers set most of the geometry, and both fail invisibly.** The
  chase camera rides `3.2 + min(1.1, speed*0.02)` above the car - about 4.3 - so a
  ceiling under about 7 is through the lens. And it trails up to 11.6 units
  *behind*, so it passes through a doorway about half a second after the car: a
  wall crossed square on a straight puts the camera through the same opening, and
  turning in a doorway puts a wall between the camera and the car. That is why the
  openings are full height with no lintel and the entrance header's underside is
  held at 9.5, well over the camera.
- **The outermost aisle has no room for racking at half an aisle out**, because it
  runs closer to the shell than the aisles run to each other. Clamping those runs
  hard against the wall is both what a warehouse does there and the difference
  between an aisle with shelves on both sides and one with a blank wall down it.

## The ribbon, the collider and the car on it

- **A track is a ribbon of stations, not a grid of tiles.** Each station carries a
  centre `p`, a surface normal `n`, a road-right vector `lat` and a half-width `hw`,
  about 3.5 units apart; the road is the strip of quads between consecutive stations.
  That is the *whole* geometry - `trackmesh.js` is one loop over pairs. It replaced an
  8-unit grid of 90-degree corner tiles, which made every corner the same corner with a
  4-unit centreline radius no car could hold, and made a smooth elevation change
  impossible (a ramp was a crease between two flat tiles). Consequences worth knowing:
  corner radius and road width are free parameters, a gap is just stations flagged
  `air`, a barrier is a `wl`/`wr` flag on an edge, and a loop is a station list whose
  normal rotates.
- **A station can also carry a cross-section, and that is how half-pipes work.**
  `pf` is a list of `[u, rise]` samples across the road - `u` from -1 to +1 as a
  fraction of `hw`, `rise` along that station's own normal - and the road there
  is the quads between one station's samples and the next one's. Still the same
  loop, so **the collider, the mesh and the car need no idea a pipe exists**: the
  ground query finds the closest surface and steering is applied about its
  normal, which is the identical reason a loop needs no special case. Authored
  with `Builder.pipe(depth, floor, side)` / `.flat()`, which blend the depth in
  and out over `PROF_BLEND` units - a pipe at full height in one station is a
  wall you hit rather than one you ride. `side='l'`/`'r'` gives a one-sided
  banked wall on a corner's outside, and **that is the shape the pool mostly
  uses**: Rainbow Road has exactly one full trough and two one-sided banks, on
  the outside of the corner each time. A V taking up the whole road is a thing
  you sit in rather than a line you pick, so one of them is a feature and three
  of them is a bobsleigh run. Two things to know: **the samples are baked
  in Python** and the JS only reads them, so there is no second copy of the
  curve to drift; and **a gate may not sit on a profiled station** (`_gate`
  raises), because a gate is a flat plane of fixed width and hanging one across
  a trough puts its posts up the walls and its mouth out of reach.
- **The collision surface IS the render surface.** Every driveable quad goes into both
  the mesh and a spatial hash, so hills, banks, loops, crests and crossings all work
  through one closest-point query with no per-shape special cases - and nothing can look
  solid without being solid.
- **Steering rotates the car about the surface normal, not world up**, which is the
  whole reason a fully inverted loop needs no special case in the car code. Gravity is
  always applied and its normal component removed while grounded, so slope acceleration
  falls out for free.
- **Grass is meant to hurt.** `OFFROAD_DRAG` is a linear term, so the grass top speed
  is where `ACCEL - quadratic drag - OFFROAD_DRAG*v` hits zero: about half of
  `MAX_SPEED`. It was 0.55 (grass top speed ~36 against a road top speed of 44),
  which made a straight line across the infield simply the faster way round a corner.
  `test_grass_costs_you_the_corner` pins it as an acceleration budget rather than by
  driving anywhere, so it does not depend on where the grass happens to be.
- **Air pitch is deliberately lazy.** Holding the throttle pitches the nose down at
  `AIR_PITCH`, and `ALIGN_AIR` (which only runs when there is *no* pitch input) noses
  a car that took off from an uphill ramp down as well. At the original 1.5 and 2.6 a
  jump taken flat out - which is how every jump is taken - was pointing at the floor
  half a second off the lip. `test_the_car_does_not_nosedive_off_a_jump` bounds the
  drop over the first half second and still requires enough authority to aim.
- **A big drop needs an explicit `bow` on `gap`, or the lap model brakes for it
  like a corner.** `gap`'s default bow is a small, capped ballistic hint - fine
  for the pool's ordinary jumps, all of which drop under 12 units - but for a
  real fall the straight-line kicker exit and the shallow default bow meet at a
  real kink in the tangent, and `speed_profile`'s curvature-based cap (the same
  one that slows a car for a corner) reads that kink as a tight one and clamps
  speed hard right at the lip - independent of the kicker's own angle, since
  the kink is in the *seam*, not the ramp. `Builder.gap(length, drop, bow=...)`
  takes an explicit bow instead of the auto one; picking it so the curve's
  initial slope roughly matches the kicker's exit grade -
  `(drop + length * rise / kick) / pi` - removes the kink and lets the model
  see the same climb-then-fall arc the car actually flies. Big Red's main jump
  is the one in the pool that needs this.
- **A jump's hang time has a real ceiling, and it is not about the ballistics.**
  `AIR_PITCH` pitches the car's nose down at a constant *rate* for as long as
  the throttle is held in the air, which is how every jump in the pool is
  actually flown (the test driver holds it, and so does everyone's instinct).
  That means the nose keeps rotating for as long as the car is airborne,
  whatever the drop or the distance - so hang time, not span, is what decides
  how far past level it has rotated by touchdown. Built for a two-and-a-half
  second flight, Big Red's main jump landed nose-down hard enough to punch
  through the road on contact; dialled back to under two seconds - still the
  longest in the pool by a clear margin - it lands clean. Sanity-check a new
  jump's hang time against the pool's existing ones (`~1-1.5s`) before making
  it much longer, and check by actually flying it - `test_every_gap_is_clearable`
  only asks whether the ballistics reach the far side, not what the car is
  pointed at when they do.
- **The authored landing zone has to absorb *real* speed, not `laptime`'s ideal
  line.** `speed_profile` models one theoretical racing line; a real lap - the
  test driver's or a person's - carries a different amount of speed off the
  lip depending on how the corner before the jump was actually taken, so it
  lands at a different point every time. Big Red's landing straight used to be
  46 units and the next gate right after it; a faster entry landed past the
  gate while still airborne, which a gate cannot credit at any height (see
  `gate_ceiling` below), and past *that* the car was landing on whatever
  happened to be next rather than on flat road, which is the other way a fast
  landing goes wrong. The fix was distance, not tuning: a 100-unit landing
  straight and the gate pushed out past where even a full-throttle, no-braking
  approach lands. `test_every_gap_is_clearable`'s margin (reach over the
  authored span) tells you the jump is *reachable*, not that the landing zone
  is generous enough for the range of real speed a lip actually sees - budget
  the room separately.
- **Gate posts are walls, not scenery.** Every checkpoint's two posts go into the
  collider as well as the mesh, and sit just outside the kerb so the full road stays
  usable. `test_checkpoint_posts_are_solid_and_the_gate_is_not` pins both halves: the
  posts stop a car, and the mouth of the gate stays completely open.
- **How high a checkpoint counts is the track's business, not a constant.** A gate
  is credited on a plane crossing inside a window, and the roof of that window
  used to be a flat 5 units on every track - lower than the car actually gets, so
  landing a jump long or coming over a crest in a tow flew you *over* a
  checkpoint without being credited for it, losing a lap you had driven. It
  cannot simply be raised: the roof is what stops a car on a bridge triggering
  the gate on the road underneath it. So `tracks.gate_ceiling` derives it per
  track from the one number that decides the answer - the closest this track ever
  passes over itself. Tracks that never cross themselves (most of them, including
  the one made of jumps) get the full 14; Spiral Ascent, whose helix stacks 10
  units above itself, gets 6.4 and stays honest. A test asserts the ceiling is
  below every crossing on every track, which is what makes the generous number
  safe.
- **The car is not glued to slopes.** `SNAP` is a 0.12-unit seam tolerance, nothing
  more, and there is no term scrubbing velocity along the surface normal - so a crest
  throws the car, as it should. `STICK_FORCE` only engages past `STICK_TILT` (about 32
  degrees off level), which in the pool means a loop's wall and roof and nothing else.
  Hills are *authored* smooth instead: `straight(l, rise=r)` smoothsteps its grade so it
  has no crease, and `crest`/`hump`/`jump` deliberately do, marking their stations
  `kick`. A hill needs `length >= sqrt(330 * rise)` or it becomes a jump by accident;
  `test_hills_are_eased_but_kickers_are_not` enforces it as a vertical curvature radius.
- **There are no vertical loops.** A plain vertical loop returns to
  exactly where it started, so its descent lands on its own climb - two surfaces a metre
  apart, which trapped cars. `Builder.loop` slides the exit sideways (smoothstepped, so
  both joins stay tangential) which fixes it completely. A helix about the direction of
  travel is the obvious alternative and does not work: its tangent sits ~55 degrees off
  its own axis, so it meets the road at a kink and the car drives into the barrier.
  Loop radius is bounded by physics - on the wall only `STICK_FORCE` opposes `v^2/R`, so
  radius 20 is about the minimum at racing speed.
- Tracks that float in the void (`ground: None`) are built with `rails=True`; tracks on
  the ground are not, so running wide there costs grass time instead of a respawn. The
  road sits ~1.2 above the grass plane, which is both why it reads as a raised ribbon
  and why the two never z-fight.
- **A floating track can opt out of rails, and Rainbow Road is the one that
  does.** `tracks.EXPOSED` is the set where falling off is the point rather than
  a gap in the barriers, and `test_barriers_are_opt_in` then checks the claim in
  *both* directions - a track wearing the flag with rails all down it fails just
  as loudly as a normal floating track without them, which is the more likely
  mistake, since the flag outlives whoever railed the track for safety. Loops
  keep their rails even there: a loop without them is a fall at the top rather
  than a corner, which is not exposure, it is a broken corner. Cloudbreak is in
  the set for the same reason it was worth building: railing every corner of a
  track whose whole subject is how far down the ground is takes the height away
  and leaves a bobsleigh run. The rails it keeps are for where going off is not
  an avoidable mistake - the two jump landings, where you arrive with no
  steering, and the narrow bridge. Cloudbreak went from 98% walled to 9%, and
  at the time that was checked by driving it: `test_a_clean_lap_needs_no_respawns`
  required a headless autopilot to get round with no respawns at all. That test
  and the autopilot behind it are **gone** (see **Tests**), so pulling rails off
  a track is now something to check by driving it yourself.
- **The three long tracks are ~2500-2800 units and 56-64s of ideal lap**, against
  The Gauntlet's 1667 and 40s. One ceiling bounds that now: `test_tracks` caps an
  ideal lap at 120s. There used to be a second and much tighter pair - a
  simulated driver capped at 90s, and a requirement that every track be driven to
  the finish with **zero respawns** - and both are gone with the autopilot. That
  was a deliberate trade: those two were a ceiling on how mean a track is allowed
  to be, which is a decision for the track and not for the test suite. What it
  costs is that "punishing when you leave the line" and "the line itself is
  marginal" are no longer told apart by anything except driving it.
## Look: skies and worlds

Every track's art direction lives in one `PALETTES` entry in `trackmesh.js`.
Two optional fields do nearly all of it, and both are read by code that has no
idea which track it is looking at:

- **`sky`** - either a plain colour (the old two-tone dome) or a spec that
  `render.js` turns into a graded dome plus a sun, stars, and the track's own
  key light, hemisphere light and fog. `glowMode` matters: `horizon` smears the
  glow around the sun's *azimuth*, which is what makes a sunrise a sunrise;
  `radial` puts a halo around the disc, which is what any sun up in the sky
  wants. A sun drawn on the horizon must still have its *light* come from much
  higher, or nothing in the world gets lit.
- **`below`** - what is under a track that floats, dispatched on `kind`: a city
  drowned in cloud, a desert, a downtown, a lava field, `pillars` (rock spires
  through an overcast, Cloudbreak) or `void` (which also suppresses the distant
  floor plate). Ground tracks use `props`/`density` instead, which pick from the
  scenery vocabulary (conifer, bigpine, deadtree, palm, rock, block) and `snow`
  turns on snow caps.
- **`shore`** - Sandy Cove only. It cuts the sea out of the ground plane, so the
  beach stops at the waterline and past it there is *nothing*: the water is
  drawn and never collided, and driving off the sand is a fall rather than a
  slow patch. `at` is an absolute world coordinate rather than a fraction of the
  bounding box, because **the track is authored against the waterline** and it
  has to stay put when the layout moves; `SHORE_Z`/`SHORE_AMP`/`SHORE_WAVE` in
  tracks.py are the other copy, and two tests hold them together -
  `test_the_waterline_agrees_with_the_track` and
  `test_only_the_pier_is_over_the_water`, which requires the crossing to be a
  single run (the pier) and the coast road to keep 25 units of clearance. Drift
  those apart and the sea floods a road that was authored to be dry.
- **`rainbow`** - degrees of hue per station, and it moves the road into the
  *unlit* buffer so it glows. **Two gradients, not one.** Along the road the hue
  sweeps slowly; across it the lightness falls toward the kerbs, the saturation
  rises, and the hue skews slightly either side. The cross-road half is the one
  that matters - a hue sweep on its own reads as a flat carpet, because a
  gradient with no shading across it has no shape. Hard bands were the first fix
  for that and are too loud. A quad has one colour, so the flat road is split
  into `rainbowLanes` lateral strips purely to have something to shade; profiled
  stations already have their samples. An unlit road lights nothing by itself,
  so the colour in the scene comes from `hemi.ground` - a saturated magenta
  there is what puts rainbow on the car's underside and the pipe walls. The sky
  is deep violet rather than black: against true black the road is the only
  colour anywhere and the world around it reads as nothing.

Rules learned the hard way, all from the same fact - **you look down on a world
below from a hundred units up, so you mostly read footprints**:

- dunes must be broad and very low, mesas narrow and tall, or both read as
  crates and pallets;
- cloud has to be clumps with sky between them, never an even coverage of
  anything, and it needs its own translucent mesh with `depthWrite` off so
  overlapping boxes accumulate into something dense in the middle and wispy at
  the rim. That is the whole difference between cloud and polystyrene;
- cloud only works when you look *down* on it. As a sky it reads as pale
  rectangles however it is shaded, which is why there is none in the dome;
- and the corollary, learned on Cloudbreak: **a cloud deck that is only a little
  way below a long track is seen almost edge-on**, and then it reads as a sea
  with floes on it however good the clumping is. The fix was to put the deck
  145 units down so you look onto it, deepen the puffs (`puff`), and **draw no
  floor plate at all** - an open bottom fading into fog is what being a long way
  up looks like, where a plate was unmistakably grey water. `pillars` spires
  therefore grow from `root`, just under the deck, rather than up off a floor.

**Nothing below is in the collider**, so the only thing keeping it out of the
track is the corridor test - and where scenery rises *above* road level (Jump
City) that test is load-bearing on its own, so it checks a whole footprint
rather than a centre point. Everything else also obeys a hard height cap under
the track's lowest station.

The single highest-leverage number in a palette is `hemi.ground`: it is the
bounce, so sand makes every underside warm over a desert, snow removes the dark
shadows from a winter scene, and molten orange is most of what separates a lava
field from a dark field.

