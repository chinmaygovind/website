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

