# Drive: the badge case

Read this before adding, changing or recolouring a badge. The rest of the
garage is in `garage.md`; badges share its `MeshBuf` and its decal rules,
so read that one too if you are touching the shared machinery.


**Eight badges, each a shape on the bonnet**, and each **free**: they go into the
same `MeshBuf` as the stripes, so a badge costs no mesh and no material. It used to
be its own mesh with its own material - a whole draw call for a shape the size of a
hand, on every car on the grid - and that is what made a case of eight affordable
rather than a choice between them. A fully loaded car went from 20 meshes to 19.

| | earns it | shape |
|---|---|---|
| `laurel` | set a track record | a scalloped ring around a **1**, record green |
| `checkers` | win a multiplayer race | a 4x4 board, black and white |
| `chevrons` | Ace rating (elo 1250) | three stacked V's, record green |
| `crown` | top the Time Trials board | an arched circlet and a 3-point crest, curved, split by a gap, green |
| `podium` | 10 podiums | three bars, tallest in the middle, bronze |
| `sunburst` | a gold on every track | 12 rays and a hub, gold |
| `ribbon` | 100 km driven | a road's markings opening out toward you, grey |
| `shield` | a gold on any 3 tracks | a crest, chief and field split by a gap, steel |

- **Every badge has a default colour and every badge can be recoloured.**
  `BADGE_COLOR` is the default per badge, because a bronze podium and a gold
  sunburst are part of what those two *are*; `badge_color` overrides it, and
  `null` (the `Auto` chip) means "whatever this badge normally is" rather than a
  literal, so a default that moves later moves everybody who never chose.
- **`checkers` is the one badge with two colours in it**, and that is why it is not
  simply "the badge colour": a chequered flag is black *and* white or it is a grid.
  So the dark squares take the badge colour (black by default) and the light ones
  are a fixed near-white `CHECKER_LIGHT`. Recolouring it therefore recolours half
  the badge, which is the right half - a red-and-white chequer still reads as a
  chequered flag where a red-and-pink one would not.
- **It is spelled `checkers`.** It was `chequers` first, which is the flag's British
  spelling and is what a chequered flag is called - but the value is also the word
  on the chip, and nobody looking for the chequered-flag badge types it that way.

**The thing to know before adding one: the bonnet is squashed, not flat.** What the
icons call height is length along the car, and it arrives on screen at about **0.4 of
its width** - measured off a screenshot, from the front camera at its own pitch. So
anything drawn as tall as it is wide comes out wide and shallow. That is a scale
factor, though, and for a long time it was written down here as something stronger:
"a decal lying flat has no *up* in it", and the podium was built around that. It was
tried as three separated bars and called a bar chart, then as a staircase, then as
three discs of different *sizes* on the reasoning that size is the one thing
foreshortening keeps. The discs read as three dots. **It is bars now**, which is
where it started: three bars sharing a baseline are compared by their tops, that
comparison survives being squashed, and a podium and a bar chart are the same
picture. The rule that actually holds is the weaker one - draw it taller and
narrower than looks right, and check it in a screenshot.

**And there is only one right way round, in both axes.** Every badge is read by
somebody standing in front of the car, so an icon's tail has to point at the
windscreen and its head at
the nose - `P` maps icon-space `+v` to `BADGE_Z + v * STRETCH`, i.e. *away* from
the camera. It was `BADGE_Z - v` first, which put every chevron pointing at the
driver and every crown upside down, and **it looks perfectly fine in the garage
from three of the four `?view=` angles** - a symmetric ring like the laurel is
identical either way, and from the side you cannot tell. It was found by
photographing `?view=front`, which is the check to make when adding one.

**And `u` is mirrored for the same reason `v` is**, which is the half that was
missed first time. The front camera sits at negative z looking toward +z, so its
screen-right is world **-x** - meaning a shape drawn with `+u` as "right" comes out
back-to-front. Only one badge in the case can show it: the laurel's numeral, which
appeared as a mirrored **1**, since the other seven are symmetric about their own
centreline and a mirrored symmetric shape is the same shape. `P` negates `u`, so
inside `badgeShape` **+u is right and +v is up, from the reading position** - a new
icon can be described the way it would be drawn on paper. One consequence to know:
the `checkers` parity carries a `+ 1` to cancel the mirror, or its light and dark
squares swap.

Flipping either axis also **inverts the handedness of icon space**, so every triangle
wound correctly before comes out backwards after. Rather than reverse eight
hand-drawn shapes, `tri2` computes the *world* normal from the three corners it was
handed and emits whichever order faces up - so the winding is not something a caller
can get wrong, in any coordinate system, and the `u` mirror above cost nothing
because of it. Measured, since a green suite means little for a pair like this: flip
the `v` mapping alone and **3** tests fail; revert `tri2` alone and exactly **1**
does, the one that reads the source, because under the current mapping the two cross
products are proportional and no geometry can separate them; do both and **12** fail.
That is why the source-reading test is not padding - it is the only thing between a
future mapping change and eight silently dark badges.

Two more things that cost iterations:

- **`STRETCH` (1.28) stretches every icon along z, and it is nowhere near enough to
  make a shape square.** It used to be described as doing exactly that, which is
  wrong by a factor of two and a half: a square icon still lands on screen about 2.5
  times wider than it is deep, because most of the squash is the camera's own
  elevation and not the badge's proportions. It cannot simply be raised either - its
  ceiling is the bonnet, which is 1.88 across and only 0.95 long, so the length binds
  and a round badge tops out at about 0.87 long by 0.68 wide. Going wider is free;
  going longer runs under the windscreen. Treat it as a partial correction and draw
  the rest of the compensation into the shape, the way the crown does.
- **A gap is how a one-colour badge gets internal structure, and it is the tool to
  reach for.** Both badges that needed a line inside them got it this way. The
  shield was a single solid outline and was the only badge with nothing inside it -
  a grey blob, and one that looked perfectly fine as a *silhouette*, which is what
  a shape test measures; it is a chief and a field now. The crown is the sharper
  case: **a crown is only a crown because of the line between its band and its
  points**, and in one colour there is no line, so band-welded-to-points is a
  silhouette with three bumps on it, which is a row of hills. Two connected versions
  read exactly that way and narrowing them only made a narrower hill. It is a
  circlet, a gap, and a three-point crest.
  A second colour is `checkers`' exception rather than a tool: half a badge that
  does not follow the colour picker is half a badge somebody cannot customise.
- **Two deliberate pieces read as one object; four incidental ones read as a
  mistake.** The crown's first version *was* a band with three points, and the
  complaint about it was that it looked unconnected - which it was, as four separate
  shapes with their feet touching. The fix is not "connect everything": it is one
  band and one *zigzag block* whose notches stop halfway down, so the points share a
  continuous base. Then the only gap on the badge is the one that means something.
- **Straight lines were the last thing wrong with it, and curves are what fixed
  it.** Even with the gap right, three straight-sided triangles on a straight bar
  is heraldry drawn with a ruler. Two curves do the whole job and both are
  sampled, since everything here is triangles. **`arc`** lifts the middle of the
  badge and *everything* is built against it - both edges of the circlet, the
  crest's base and every tip - so a flat bar becomes something that goes round a
  head; it costs about `BOW` of height, which is what `HI` came down to pay for,
  and the ceiling is still the clear bonnet at v 0.35. And **the tines' flanks are
  concave**: each span of the top edge is eased with a square rather than a
  straight line, flat where it leaves a notch and steep as it reaches a tip, so a
  valley is a rounded scoop and a point is still a point. Straight spans between
  the same control points give a zigzag, and a zigzag with the tips foreshortened
  is a row of shark's teeth.
- **Gaps have to be wider than instinct says.** The crown's three points 0.005
  apart merged into a solid arrowhead; nine separate laurel leaves came out as a
  scatter of specks and had to become one continuous scalloped ring; three podium
  discs 0.235 apart overlapped into one blob. Fine articulation dissolves - the
  gaps *are* the shape.
- **A trapezoid whose short edge sits on the base line is a zero-area triangle
  waiting to happen.** The crown's crest is built one quad per sample of its top
  edge, dropped to the base - and the outer spans start (or finish) *on* that base,
  so the end sample of each collapses. Sampling a curve rather than stepping
  between control points did not make this go away, it only moved which quad it
  is, which is why the guard is an epsilon compare per sample and not a test
  against a named constant. A degenerate triangle has no normal, so it has no *facing*,
  and `test_every_decal_faces_away_from_the_car` is what said so rather than a
  screenshot: it draws nothing and looks perfect.
- **`tri2` fixes its own winding** rather than asking the caller to get it right.
  Seven hand-drawn shapes made of arcs and fans is a lot of chances to reverse an
  order for no gain, and the failure is silent (a decal lit from underneath).
  Describing the corners is the interesting part; their order is not.
- **A guest is hashed off the name they typed**, not `GUEST_COLOR`, and that is
  what let the first-free colour rule go. `_livery_for(user, holders, name)`
  needs that `name` for exactly this: resolve a guest against nothing and four
  guests in a room are four identical red cars, which is the bug the deleted
  rule existed to prevent, arriving from the other end.
- **Two people choosing one colour both keep it.** `_add_player`'s "your colour
  if free, else first-free" rule is gone. It was the right trade while nobody
  had chosen - a hashed colour is not yours in any sense worth protecting - and
  is exactly the wrong one now: being handed a stranger's colour without being
  told is worse than sharing one, and the cars have names over them precisely so
  colour is not the only way to tell them apart.
- **A ghost wears the car its driver drives now; a replay wears what they wore
  on the day.** Opposite answers, and deliberately: a ghost is a lap you are
  chasing now and turning up in last month's paint would read as somebody else,
  where a race is a thing that happened. So `/api/ghost` looks the livery up and
  `_store_replay` writes it into `drive_races.cars_json`.
- **Storage is `drive_garage`, two columns.** A new table because `create_all`
  makes tables and not columns, so it lands on the live database by itself; a
  JSON blob because every cosmetic after this needs no migration. `livery_json`
  keeps **only the slots that differ from the defaults**, so a default that moves
  later moves the car of everybody who never touched that slot. `earned_json` is
  a second column rather than a key in the blob because the two are different
  kinds of fact - folding a server decision into something the client POSTs is
  how a gate gets bypassed.
- **The page is a viewport, not a document.** The whole of the screen under the
  nav is the car and the controls float on it: `body.garage-page` is a **flex
  column** (nav `flex: none`, `.gstage` `flex: 1`) rather than
  `height: calc(100dvh - <nav height>)`, because the nav wraps to two lines on a
  narrow phone so its height is not a number - and a hardcoded one is the exact
  bug `.hud-l` was rewritten to stop being able to express. It began as a 4:3
  canvas in the left column of a `.wrap` with seven cards down the right, which
  had the proportions of the screen backwards: almost none of a page about
  looking at a car was car.
- **The controls are the game's HUD, not the site's paper.** Drive already has a
  language for controls floating over the 3D world - `--hud`, `--hud-line`,
  `backdrop-filter` - and it is what the track card, the minimap and the settings
  icons are made of. White paper cards with hard drop shadows are right on a
  document and wrong on a dark studio, and a third look for one page would be
  worse than either. `.gtop` and `.gfoot` need `pointer-events: none` with `auto`
  on their children, the same pair `.hud-l` needs: a full-width bar over the
  canvas otherwise swallows every drag along that edge, and on this page
  dragging *is* the interface.
- **Seven tabs and one option row**, so only the active category is on screen and
  the car keeps the rest of it: **Body, Detail, Livery, Wheels, Glass, Finish,
  Badge**. The option row has a `min-height` so switching tabs does not walk the
  car up and down behind the bar. Two things about the order. **Finish is second to
  last**, because it is the thing you settle once the paint is chosen rather than a
  category you browse; and **Badge is last** because it is the only tab that is
  about you rather than about the car.
- **A tab is one line at desktop, and that is a constraint on the vocabulary.**
  Every list wraps rather than clipping, so a long one is not *broken* - it is a
  block of swatches as tall as the car it is describing, on a page whose entire
  subject is looking at the car. That is what set the palette at ten and each
  swatch list at ten or under, and it is checked by measuring `#gopts` at 1280,
  820 and 430 rather than by counting entries: the row is `flex-wrap`, so how many
  fit is a fact about the rendered width and not about the length of a Python list.
- **A slot label is only drawn when a tab has more than one slot.** `Detail` is the
  only one that does (Spoiler and Roof), so it is the only place `SPOILER` / `ROOF`
  appear. Wheels, Livery and Glass each had a label too - `RIM`, `STRIPE`, `TRIM` -
  captioning the single row on a tab already named for it, three words saying what
  the tab said one line above.
- **Detail is two slots because a spoiler and a roof are two things.** It was one
  `trim` colour plus a `two_tone` boolean that put the roof in *that* colour, so a
  white roof over a black wing could not be asked for at all. `roof` is its own
  slot; `two_tone` is gone rather than aliased, and a stored `two_tone: true` is
  inert (there is a test that it paints nothing and does not throw). The roof is
  **the only slot on the car that costs a material**, since a differently painted
  cabin cannot share `bodyMat` - no colour means it does, which is the common case
  and the free one.
- **A locked chip is greyed and pressable, not disabled and captioned.** The
  requirement used to be printed *inside* the chip, which made one chip in a row
  three times the height of its neighbours and turned a row of names into a row of
  paragraphs. Now a locked chip is the same size as every other chip with just the
  name on it, at `opacity: .45` with a dashed border, and **pressing it** puts the
  requirement in the line under the row for four seconds. It is deliberately not
  `disabled`: a disabled button takes no pointer events, so the natural way to ask
  what a greyed-out thing needs would do nothing at all.
- **That line is a reply, not a status.** `S.said` is set by a press and cleared by
  the next render that has something of its own to say, so it cannot sit there
  being true about a chip you have moved on from. Its other job is the opposite
  direction: on the Badge tab, a badge you are *wearing* says **"Laurel: unlocked
  for setting a track record"** - `garage.GATES` carries a `done` phrase beside the
  `text` one for exactly this, because "Set a track record" and "unlocked for set a
  track record" are not the same sentence and deriving one from the other would get
  half of them wrong. Only the badge tab, and only for a badge you have: it is a
  caption on the thing you are looking at, and it would be a caption on nothing
  anywhere else.
- **There is no "9 of 10 unlocked" line.** The row used to report the count and
  which gate was nearest. A tally over a car is a completion meter on a page about
  choosing paint, and the dot on a tab already says where there is something to
  find; `garage.progress` still exists and still feeds the `(3/10)` in a pressed
  chip's answer, which is the one place a number is an answer to a question
  somebody asked.
- **Every colour slot is swatches**, not an `<input type="color">`. The browser
  draws that as a ~38px grey rectangle that says nothing about what it is or
  what colour is in it. Instead: a first chip that writes `null` (which is what
  the server already means by a missing key - labelled `Auto`, or `Body` on the
  roof and `None` on a stock wheel, where the absence is really "the body colour"
  and "no lip"), then **that slot's own swatches** as a shortcut, and last a
  **conic-gradient tile**, which reads as "any colour" at 26px where a plus sign
  reads as "add one".
- **Every colour slot is swatches**, not an `<input type="color">`. The browser
  draws that as a ~38px grey rectangle that says nothing about what it is or
  what colour is in it. Instead: a first chip that writes `null` (which is what
  the server already means by a missing key - labelled `Auto`, or `None` on a
  stock wheel where the absence is really "no lip"), then **that slot's own
  swatches** as a shortcut, and last a **conic-gradient tile**, which reads as
  "any colour" at 26px where a plus sign reads as "add one".
- **The picker behind that tile is ours**, and the native one is gone. It needed a
  pixel-perfect hit on a 26px target, opened wherever the OS felt like, and on a
  phone is a modal sheet over the car you are trying to look at. This is a panel in
  the garage's own glass: a saturation/value square, a hue strip, the hex, and a
  small `x`. It closes on the `x`, on `Escape`, and on a `pointerdown` anywhere
  outside - `pointerdown` and not `click`, so it goes on the press rather than
  waiting for a release that may land somewhere else.
- **`#gpick` lives under `.gstage` and not in `#gopts`, and that is the only place
  it can be.** `set()` calls `render()`, which rewrites `#gopts`'s innerHTML on
  every change - a picker inside it would be destroyed by its own first drag,
  halfway through the gesture driving it. So the panel sits outside, remembers what
  it is editing in `S.pick`, and **re-finds its tile by slot** after each redraw,
  because the element that opened it has been replaced and its rect is nonsense.
- **`S.pick` holds h/s/v, not a hex.** Round-tripping through a colour on every
  move would make a drag along the top of the square silently reset the hue to red,
  because a fully desaturated colour has no hue to read back. `hexToHsv`/`hsvToHex`
  are the one part of `garage.js` with tests (`test_rules_js.py`), for the reason
  the rest has none: a page is checked by looking at it, and arithmetic is not -
  a hue three degrees off or a hex that loses its leading zero is invisible in a
  screenshot and permanent in somebody's saved car.
- **`setPointerCapture` on both controls**, so a drag that runs off the edge of the
  square pins to the edge and carries on instead of stopping dead, and so a mouse
  and a thumb are one code path. `touch-action: none` on both as well, or a drag on
  a phone scrolls the page - and the page it would scroll is a full-screen canvas.
  The panel is clamped inside the stage, because the tile can be at either end of a
  two-row swatch block and a picker half off the screen is unusable on that side.
- **The viewer builds no track.** `Renderer` starts with `trackGroup` and `sky`
  null and `render(dt)` is only particles plus a draw, so a studio costs one
  canvas and the page opens instantly. There is no `OrbitControls` - it is a
  three.js addon and is not vendored, and what this needs is forty lines of
  drag. Three things about it are worth not re-deriving:
  - **The distance is not a constant.** The camera is 66 degrees *vertical*, so
    the frame is `1.3 * dist` tall and `1.3 * dist * aspect` wide - a fixed
    distance frames a car by its height, and a car is a long low thing framed by
    its length. A value tuned on a laptop put the nose and tail off both sides of
    a portrait phone. `fitDist()` keeps the tuned figure for wide stages and
    backs off below a reference aspect, and the scroll wheel is a *multiplier* on
    it so a zoom survives a resize instead of becoming a distance that means
    something else.
  - **A vertex colour is not a hex colour.** three.js has colour management on
    (r169): a `THREE.Color` from a hex is converted sRGB to linear on the way in
    and encoded back on output, so it round-trips, but a raw colour *attribute*
    is assumed to be linear already and only gets the encode - so `MeshBuf` drew
    the studio floor about twice as bright as asked for, and its outer ring no
    longer matched `scene.background`, which put a hard disc rim across the
    screen. `garage.js` linearises its floor colours for that reason.
    **`MeshBuf` itself is deliberately left alone**: the twelve tracks' palettes
    were picked by eye against this exact pipeline, so "fixing" it there would
    restyle all of them.
  - **A pool of light wants to be tighter and dimmer than instinct says.** At a
    low camera the far half of a wide fade piles up against the horizon and
    becomes a pale wall behind the car with a hard line along the top. The floor
    is a large `MeshBuf` ring disc fading to *exactly* the backdrop, so there is
    no edge to see - but it still has to lift enough under the car for the
    contact shadow to have something to be a shadow on.
  The scene also needs a dim cool fill opposite the sun: the track's rig is one
  hard key plus a hemisphere, which is right outdoors and in a black room leaves
  every face turned away from the key at the same flat shadow, so a flat-shaded
  car reads as a paper cut-out of itself.
- **`?view=front|34|side|rear` puts the camera on a fixed angle at load**, the
  same idea as the play page's `?panel=` and `?draft=`: there is no browser in CI
  and a screenshot cannot drag. The four buttons that set it *ease* rather than
  cut, and the frame loop calls `render()` once the ease lands - which is the
  only place the controls are redrawn by the loop rather than by an event.
  Without it the highlight was computed at the moment of the press, when the
  answer is still "none of them", and no view button ever lit.
- **The selected option's highlight outranks its hover, and that took a
  `:not`.** `.gopt:hover:not(:disabled)` is three simple selectors against
  `.gopt.on`'s two, so a chosen option went pale the moment the cursor was over
  it - which is where the cursor is, having just clicked it. It looked like
  every press deselecting itself.
- Every list on the page is built from the payload the server rendered into it,
  so there is no second copy of the vocabulary in the JS to drift from
  `garage.py`'s - including the words on a locked row.

