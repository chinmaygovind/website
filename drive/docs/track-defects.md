# Things that go wrong in a track

**This is a running log, not a spec.** When you see something wrong in a render
or while driving, add a line. Do not try to generalise it, work out the rule, or
find the right section — one sentence in the right-ish place is the whole job.
The value is that it accumulates, not that any entry is well written.

It is short on purpose, so `/track` can read the whole thing before every render
and check the pictures against it. That is what this file is *for*: turning
"Chinmay will notice it eventually" into "the render step looks for it".

**Two ways an entry leaves the list below.** Either it turns out to be computable
and graduates into a real check — a test in `tests/`, or a function in
`tracks/checks.py` — in which case it moves up into **Caught automatically** with
the test named; or it turns out not to be a defect and gets deleted. Everything
else stays where it is and gets looked for by eye.

A graduating check has to **pass on all sixteen existing tracks on the day it
lands**. They are the definition of good here; a check they fail is a wrong check.

---

## Caught automatically

Listed so you do not waste a look on them. All of these fail in
`scripts/tests.sh drive` before you ever render.

- Road running too close to itself without clearing it (`self_proximity`).
- Every corner the same radius, or a corner tighter than 12 (`test_corner_radii_are_varied_and_drivable`).
- A hill so short it is really a kicker (`test_hills_are_eased_but_kickers_are_not`).
- A gap the car cannot clear (`test_every_gap_is_clearable`).
- Medals out of order, unreachable, or too far apart.
- A closed lap that does not close (`test_a_closed_lap_actually_closes`).
- Barriers on a ground track that did not ask for them (`test_barriers_are_opt_in`).
- A checkpoint creditable from a road passing above it.
- Pole starting on the outside of turn one.
- A track folder that fails to load (`test_every_track_folder_loads`).
- **The road buried in its own ground plane**
  (`test_the_road_is_never_buried_in_its_own_ground`). Graduated from the list
  below. Exempt if the palette has a `terrain` height field, which is why Spa
  can fall 63 units and stay above its ground.

## Measured against the pool

```bash
cd drive && venv/bin/python tools/pool_stats.py <slug>
```

A second net, and a different one. The checks above say *broken*; this says
*unlike the sixteen tracks that are already good*, on 26 numbers — length, corner
radii, longest straight, climb, gaps, loops, scatter density, fog distances, sky
stops, medal pace. It compares against the other fifteen, never against itself.

**It cannot tell you something is wrong**, and it flags Big Red's 223-unit drop
every time, because that is genuinely unlike everything else and is the whole
point of the track. What it is good at is the mistake with no visual signature:
a density of 3.5 where the pool runs 0 to 0.34, a `fogFar` of 60 where the pool
runs 780 to 2100, a two-stop sky where every good one has six to nine. Those are
typos and unit slips, and they look plausible in code.

Run it before the render, not after. Half of what it finds you would otherwise
find by looking at a bad picture.

## In the plan view

- **A leg that left the building.** Something ran further than it read in the
  code and the layout is now a different shape.
- **A hairpin bulging into the one beside it.** Legal by `self_proximity` and
  still wrong to look at.
- **A closing stretch half as long as it read in the code.** Straight lengths do
  not feel like their numbers until you see them against the rest.
- **A crossing that is not where you meant it to be.**
- **The whole track drifting off in one direction** instead of returning near
  where it started. Fine for a point-to-point, worth noticing anyway.

## In the road views

- **Geometry floating in the sky.** Buildings, racking, props standing at a Y
  that has nothing to do with the ground under them. The built-in scatter cannot
  do this — it stands things at `terrain.height()` or `gy` — so when it happens
  it is almost always hand-placed geometry in a `scenery.js`.
  *Mechanical: this should graduate, `test_scenery.py` already knows where every triangle is.*
- **A corner that arrives with no warning.** No sightline into it, nothing to
  brake against.
- **A crest that hides the next braking point.**
- **A ceiling the camera is about to clip.** The chase camera rides ~4.3 above
  the car and trails ~11.6 behind, so it goes through an opening a beat after the
  car does. Cross walls square on a straight, keep openings full height, no lintel.
- **The road is not as wide as you meant.** The car is in frame deliberately —
  it is the only object with a known size.
- **A jump that is longer than it is good.** `AIR_PITCH` noses the car down at a
  constant rate for as long as the throttle is held, so a longer flight lands
  further past level, not further downrange. A shallower kicker buys drop and
  distance back more cheaply. See Big Red.

## Palette and sky

- **The sky washes the kerbs out.**
- **The glow has eaten the whole dome.** `glowStrength` with a low `glowFocus`
  smears a long way from the sun's azimuth. At 0.85/4 a midnight track rendered
  as a bright pink dusk - the mood was wrong and nothing else in the palette was
  at fault. Look at the *top* of the frame: the zenith stop should still be
  reaching the camera.
- **`hemi.ground` has repainted the world.** It is the bounce and it is the
  strongest number in any palette, so a saturated one is not a tint, it is a
  second key light: a sodium orange picked for wet asphalt turned every
  upward-facing surface on the track brown, shoulders and hillside included.
  Dim and desaturate until it reads on the car's underside and nowhere else.
- **The scatter has become a junkyard.** Density that looks reasonable in a
  number carpets the whole bounding box out to the horizon. 0.10 was far too
  much; Sandy Cove's beach is 0.035. There is no *building* in the vocabulary -
  `block` is a crate at any distance - so a city cannot be made out of scatter,
  and trying is what makes it look like a scrapyard.
- **The road and the ground are the same value, so `plan.png` is a solid blob.**
  Distinguish them by lightness rather than hue: the plan view is lit and
  shadowless, so two colours a few points apart in value are the same colour from
  above however different they look side by side. Costly on a dark track, where
  the render is the only check on layout there is.
- **The road has gone to mud.** A light's colour goes through sRGB-to-linear and
  a vertex colour does not, so a warm key light multiplies a neutral grey road
  down. Pick every base colour cooler than it looks.
- **Everything is black.** A missing required palette key reads as `undefined`,
  three.js turns it into NaN. `tracks/look.py:REQUIRED`.
- **A palette change that did nothing.** A misspelled optional key
  (`glowStrenth`) is not an error in either language. `look.py` refuses unknown
  keys now, so this should be caught — if it is not, that is a bug in the check.
- **Fog you cannot see the next corner through**, or fog so far it never reads.
  *Mechanical: comparable against the pool, see `tools/pool_stats.py`.*
- **Scatter density wrong for the place.** A beach is mostly empty sand; the
  first pass at Sandy Cove was a palm plantation.

## Closed laps

- **The seam is a kink** because the lap ended mid-corner. End on a straight.
- **The solver refused** because the ribbon was more than ~10% from closing. It
  will not stretch a straight past 15% or move a corner past 8 degrees.
- **`FREE()` silently lost.** `FREE(330) - CP` is an ordinary float by the time
  the Builder sees it. Wrap the whole expression: `FREE(330 - CP)`.

## Custom `scenery.js`

- **The collider is missing on one path and nowhere else.** Scenery reaches the
  game three ways — inlined by the play page, fetched by the switcher, bundled
  into QuickJS for the anti-cheat. Miss one and that path builds the track
  without its collider, silently.
- **`scenery = True` and no file, or a file and no flag.**
- **A quad wound the wrong way is invisible, and nothing says so.** `solid` is
  `MeshLambertMaterial`, which is `FrontSide`: reverse the vertex order and the
  face points away, gets drawn, gets costed, and cannot be seen from anywhere
  anybody stands. A tessellated ground built this way looked *identical* to not
  having written it. Copy the winding from the engine's own equivalent - its
  ground quad goes `(x0,z0) → (x0,z1) → (x1,z1) → (x1,z0)` - or use `bright`,
  which is `DoubleSide`. Same trap that made Spa's pit building an invisible
  shed with a roof floating in the sky.
- **A `scenery.js` that throws can leave the suite green.** `test_scenery.py`
  pins the *collider* triangle count, so scenery that is mesh-only - towers,
  trees, anything you cannot hit - has an unchanged count whether it ran or died
  on line one. A missing name in the `ctx` destructure took out this track's
  entire city and 58 tests still passed. What catches it is
  `tools/validate_track.py`, whose browser step reports `uncaught:` - so run the
  validator, not just pytest, after touching a scenery file. Same shape as the
  bug that left Spa rendering no frames at all with a green suite.
- **Hand-placed geometry that does not move when the road does.** Anything with a
  literal coordinate in it is a thing that will be wrong after the next layout
  change. Derive from the ribbon where you can; Costco's shell is authored
  because deriving it would be circular, and that is the exception.

---

## Things that only bite certain tracks

- **`pal.terrain` and road over road are mutually exclusive.** It samples one
  height per (x, z) cell taken from the *nearest* road, which is single-valued by
  construction - so over a helix, a stacked crossing or a rooftop deck it fills
  the whole volume solid and the upper road ends up buried in a mound with ground
  flush against both kerbs. No apron or blend setting reaches it. Found on Tokyo
  Drift, whose car-park helix is three storeys of exactly this.
  **This is a limit of `pal.terrain`, not of height fields.** Mount Joy stacks
  switchbacks a hundred units over each other and has ground under all of them,
  because its field is built in `scenery.js` on a different rule - a lower
  envelope of upward cones, one per station, which is at most `y - drop` at
  every station and therefore *arithmetically* cannot come up through any road,
  for any layout. That is the pattern to copy for a track that wants both.
- **On a helix, `gate_ceiling` is set by the road's *width*, not its climb.**
  Two stations count as overlapping while they are within `hw + hw` in plan, so a
  wider ramp overlaps the turn below it across a wider arc - and the far end of
  that arc is where the two are furthest apart in height. A 10-unit storey at
  width 11 measured 8.2 and pinned the whole track's ceiling to its floor of 5.
  Narrowing the ramp fixes it more cheaply than climbing higher.
- **A brand-new track fails `test_every_track_has_a_usable_hot_lap` until
  somebody drives it.** `hotlap.py` takes the line off the standing record via
  `/api/ghost/<slug>?who=wr`, so it cannot be generated for a track nobody has
  driven. Set a lap locally and run `tools/hotlap.py <slug> --site
  http://localhost:5005`. Not a defect in the track - but it is why the suite is
  red on the commit that adds one.

## Add here

New entries, unsorted, until somebody files them. One line is enough.

- A city track with nothing but scatter props on it does not read as a city. The
  scatter vocabulary has no building in it, so a city needs a `scenery.js` that
  stands real towers - there is no palette setting that gets there.
- Too dark to comfortably drive. A night palette can be atmospheric in a still
  render and still be unreadable in motion; judge the brightness by whether the
  *next corner* is legible, not by whether the screenshot looks moody.
- A height profile that dives and then climbs straight back up for no reason.
  Going up the helix to 39, falling to 13, and climbing again to 62 reads as two
  unrelated ideas; staying high between them is one.
- Long for the sake of it. Cutting the last movement off a track is almost always
  free - the closing stretch is the part nobody remembers.
- **Scenery standing on nothing past the edge of the ground.** The ground quad is
  only `bbox + CELL * 7` (56 units on a CELL-8 track), which is far smaller than
  it looks from inside the track. Anything a `scenery.js` scatters beyond that is
  over the void. Clamp placement to the plate and inset by the object's own
  footprint - it is the *corner* that hangs off. Visible from the parts of the
  track nearest the bounding box, so a long thin layout shows it worst.
- Too much straight before the first real feature. A long intro reads as the
  track not having started yet.
- One boost pad on a track that has slow corners everywhere is a wasted lever.
- **A base colour checked against the swatch and not against the bounce.** The
  palette note says pick colours cooler than they look; this is the next step of
  it. A pale sand road read as *correct* in `plan.png` and as olive-grey from the
  car, because the plan view is lit flat and shadowless while in the world a sage
  `hemi.ground` lands on every upward face. Judge a road colour in a road view,
  never in the plan, and if it has gone grey suspect the bounce before the road.
- **A height field that treats a free-standing surface as ground.** Shroom
  Street's mushroom caps are road, so the first field built ground from them -
  which filled the gorge in under the one thing the gorge exists for, and every
  cap came out sitting in a shallow green bowl with its stalk buried. Anything
  that is deliberately over a void (`bn`, and `air` already) has to be excluded
  from the station list the field is derived from.
- **A terrain carve whose depth is measured off one global floor.** `minY - DEPTH`
  is the right depth only where the road is at `minY`. Thirty units higher up the
  same track it is thirty units too deep and reaches a hundred units further out
  before its wall climbs back to the surface - so two compact canyons came out as
  long diagonal trenches across the plan view, with roads elsewhere standing on
  trestles over ground dug from under them. Measure it off the nearest station of
  the feature being carved.
- **A carve switched on at a distance threshold instead of blended over one.**
  One cell at meadow height beside one cell at full carve depth is a single
  near-vertical quad falling seventy units, and a ring of those reads as grey
  shards thrown across the infield rather than as a cliff. Ramp the carve in over
  40-odd units.
- **On a void track, every station gets a trestle.** `base` is a flat
  `p[1] - 16` with no terrain, so `drop` clears the 1.5 threshold everywhere and
  supports are drawn under the whole ribbon. Fine where a height field buries
  them; anything genuinely free-standing has to opt out, or it wears steel piers.
- **A painted mark built from four vertices reads as a diamond.** Mushroom spots
  as single quads looked stencilled on. Six vertices as two trapezoids is the
  cheapest thing that reads as round, and it is worth the extra quads on a mark
  that is the signature of the track.
- **A corner you can simply leave out.** Found on Silverstone by Chinmay, before a
  single lap was driven: the arena and the Brooklands-Luffield loop each sat
  entirely between two checkpoints, so the chord across them was a legal lap. Grass
  tops out near half the road's top speed, so **a cut pays once the road distance
  is more than about twice the chord** - the arena was 2.35x and Luffield 3.42x,
  worth three or four seconds each. Two things fix it and they fix different
  cases: a **checkpoint inside the loop** kills anything that spans it, and a
  **barrier** kills a chord across one apex. A barrier alone was not enough here -
  the big cuts go round the outside of a whole complex, not over an apex - and a
  ribbon `rail` is not available on a ground track (`test_barriers_are_opt_in`), so
  the barrier is collider geometry in `scenery.js` like the Costco's parapet.
  *Not mechanical, and worth knowing why: the obvious check flags loops, walled
  interiors and hairpins on seven existing tracks, because a chord in plan says
  nothing about whether anything stands across it. `tools/cut_check.py` asks the
  collider too, which is what makes the answer real.*
- **The run-off so wide the corner stops being a shape.** Silverstone's first pass
  had a 24-unit asphalt band each side of a 16-unit road, which paves the entire
  inside of an 18-radius hairpin: the arena rendered as one grey plain with kerb
  lines painted across it, with no visible track edge and every apex open. Judge a
  run-off width against the *tightest* corner it has to sit beside, not the fastest.
- **Trackside furniture sized off the wrong palette.** `stand`'s `off` defaults to
  `armco + 5`, so a palette that moves its barrier in moves every grandstand in
  with it. Silverstone's armco is 22 against Spa's 26, and eleven ten-tier stands at
  the default put a wall of seating closer to the road than Spa's - Stowe's read as
  a tunnel mouth across the end of the Hangar Straight. Set `off` explicitly when
  the barrier is not where Spa's is.
- **A door, a sign or an apron on the face pointing away from the road.** Anything
  placed at `lat * (out * side)` has the road in the `-side` direction along `lat`,
  so a feature authored at a fixed `-D/2` faces the road on one side of the circuit
  and the empty infield on the other. Both of Silverstone's hangars came out as
  blank grey walls. Same family as the mirrored-winding trap and just as silent.
- **The floor is dead.** A ground track's plate is one flat quad in one colour,
  and however good the scenery standing on it is, half of every frame is that
  quad. Anything laid on it - street grid, light spill, puddles - is a handful of
  quads and buys more than the same effort spent on the things standing up.
  Sit them ~0.12 above `groundY`, above both the engine's plate and any the
  scenery added under it.
- **A circuit that crosses over itself cannot have `pal.terrain`, and the symptom
  is a ceiling rather than a mound.** Monaco's Beau Rivage climbs directly over
  its own harbour front - the two roads' *tarmac* overlapping in plan, 12 units of
  combined width across a 9.3-unit gap, 9.2 units apart in height. The height
  field is single-valued, so it drew the upper road's surface and run-off as a
  solid slab across the lower road, which from the car is a wall you drive into at
  speed. **No `apron` setting reaches it** - the note further up about `pal.terrain`
  and road over road reads as being about helixes and rooftop decks, and this is
  the cheaper case that looks survivable and is not: it is the road surfaces
  themselves that overlap, not their aprons. Check for it before writing a
  palette, not after rendering one: cluster the station pairs closer in plan than
  `hw + hw + 2` and look at the height gaps. The fix is Mount Joy's pattern -
  `ground = None`, the world built in `scenery.js` off a lower envelope - and on a
  street circuit it is the better architecture anyway, because a floating track
  *wants* rails and walls-on-the-kerb is what the place is.
- **A checkpoint hosted inside a corner has to keep the corner's angle.** Splitting
  an arc into two either side of a gate by holding the *radius* and shortening
  both halves silently drops the angle the gate's own straight road now occupies.
  Two such gates on Monaco cost 9 degrees of a closed lap's 360: the heading then
  does not close, the position comes out a hundred units off, and the solver
  refuses with a message about a straight it wants to lengthen by 85% - which
  points at the wrong leg entirely. Split by holding the **angle** and letting the
  radius take it.
- **A surveyed circuit's tightest corner may not fit the engine.** Monaco's
  hairpin is 16 m in real life, which at any scale that keeps the lap a sensible
  length lands under the hard 12-unit radius floor. Scale is the lever worth
  pulling first (Silverstone's 0.4586 units/m would have made this track 1531
  units long and the hairpin radius 8); past that, open the one corner and say in
  the docstring that it is the one thing on the track that was authored rather
  than measured.
- **A height field whose flank starts at the station centre buries the road.** A
  cone rising at Mount Joy's 0.62 is back at road level 2.6 units out and 2.1
  units *over* it at the kerb, so the car drives in a trench with its kerbs
  swallowed and pale scree closing over both sides. Hold the field flat for
  `hw + 4` and then rise, and pick the gradient for the place - 0.62 is a scree
  slope, 0.10 is a town.
- **A city one building deep reads as a street with desert behind it.** One rank
  of blocks along the ribbon looks right from inside the canyon and wrong from
  every spot with a sightline - the climb, a hairpin, across the water. Deal two
  or three ranks at falling density and rising height; it is the same loop and it
  is the difference between a street and a city.
- **Window bands can repaint a whole city.** Unlit bands 1.24 units tall every
  4.2 are a third of every facade, so at dark blue-grey they averaged Monaco's
  cream and terracotta to concrete in every render, and going pale to fix that
  turned the same buildings into multi-storey car parks. Thin, and *darker* than
  the wall. They also have to protrude a hair - a band inset into a wall is
  inside the building and invisible.
- **A `scenery.js` helper deleted by an edit to a different part of the file.**
  Rewriting Monaco's harbour removed the clamped grid read the ground loop used
  one section further down, so `props` threw `ReferenceError` and the track built
  with no city, no hillside and no collider. pytest did not move, for the reason
  already noted above (mesh-only scenery has no collider triangles to pin). What
  caught it was `test_closed_lap.py`, which builds the track in QuickJS - so on a
  closed track that suite is the cheap check, and `tools/validate_track.py` is the
  one everywhere else.
- **`toRoad` over a whole height field is the cost centre nobody measures.**
  12,210 cells against 695 stations is 8.5M distance tests, paid on every page
  load *and* every lap the anti-cheat re-drives in QuickJS. Bucket the stations:
  Monaco went to 1.27s a build, which is Spa's 1.35s rather than an outlier.
- **An unlit colour renders at full value, so `bright` needs picking two or three
  stops darker than `solid`.** The palette note says pick every base colour cooler
  than it looks; this is the other axis and it caught two things on Monaco at
  once. `bright` is `MeshBasicMaterial` and nothing multiplies it down, while the
  same hex in `solid` is scaled by a key light well under 1 - so a mid sea-blue
  chosen *darker than the track's own road* rendered as bright cyan plastic, and
  the window bands that had already been darkened once were still reading as pale
  belts on every facade. Judge anything unlit against the lit thing beside it in a
  render, never against the swatch.
- **Ramping a carve is wrong when the drop is short.** The advice further up - blend
  a carve in over 40-odd units rather than switching it on at a threshold - is
  about a seventy-unit cliff in open country. Monaco's harbour is a fifteen-unit
  drop and is supposed to be masonry, and ramping it over 30 units gave five
  visible terraces into the water, over 9 units still three: at a 7-unit grid every
  cell in a ramp lands at its own depth, so a short ramp *is* a staircase. One
  step, every wet cell at the same depth, draws the single near-vertical quad per
  cell that reads as a quay wall.
- **`node -e "require(scenery.js)"` proves it parses and nothing else.** The file
  registers a function; none of the geometry runs until `buildTrack` calls it. A
  refactor that split Monaco's one PRNG into four left two *call sites* still
  passing the deleted `rnd`, which parses perfectly and throws the moment the
  first building is placed - and the only symptom was `shoot_tracks.py` timing out
  after 90s on `DriveShot.S.built`, which reads as a slow track rather than a
  broken one. Run `pytest -k <slug>` after touching a scenery file, every time:
  the closed-lap and verify suites build it in QuickJS and say what threw.
- **"Road with something above it" defines a crossing, not a tunnel.** Monaco's
  bore was derived as the longest run of stations with another part of the circuit
  overhead, which sounds like a definition of a tunnel and picked the *harbour
  front* - the one place the circuit passes over itself. The bore was built along
  the quay, and its roof, set 10.5 units over that road, came up through Beau
  Rivage nine units above it: from the car, tunnel geometry cutting across the
  track just after turn one, a third of a lap from where the tunnel is supposed to
  be. **Which stretch is in a tunnel is a fact about the place, not something the
  ribbon implies** - author it as a fraction of the lap, the way Spa places its
  grandstands, so it still survives a re-solve. And cap any roof against the
  nearest road above it, so the same mistake cannot draw geometry through a road
  again whatever the span is set to.

- **Two boxes of the same footprint overlapping in height z-fight exactly like one
  box drawn twice.** Monaco's boats were a dark boot-topping and a white topside
  at identical length and beam whose height ranges overlapped by half a unit, so
  four exterior walls were coplanar over that band and the marina strobed at the
  waterline as the camera moved - the same symptom as the double-drawn faces
  `obox` was written to stop, from a different cause. Stack a two-tone solid, do
  not overlap it: the second box starts where the first ends.
