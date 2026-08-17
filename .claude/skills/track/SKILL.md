---
name: track
description: Author a new track for the Drive game, or change an existing one. Use whenever the user wants a new Drive track, describes a track idea ("a foggy dockyard", "something with a big jump"), or asks to change a track's layout, palette or sky. Builds it, tests it, renders it, looks at the pictures, fixes what is wrong, then serves it on localhost for the user to drive.
---

# Author a Drive track

A track is **one folder**, `drive/tracks/<slug>/`. Nothing outside it needs
editing: the loader finds it, derives its medal times, and it appears on the home
page, in the switcher, on the leaderboard and in rooms.

```
drive/tracks/dockyard/
    track.py      required: what it is, and the geometry
    palette.py    optional: colours and sky. Without one it gets a neutral default.
    scenery.js    optional: mesh code only this track needs (a building, an interior)
```

## The one thing that makes this different

**You can see your work.** There is no browser in CI, and for most of this
project's life there was none on the laptop either - `shoot_tracks.py` looked for
`google-chrome` on PATH, found nothing on a Mac, and printed one line. So tracks
were authored blind: propose geometry, ship it, wait for someone to drive it and
describe what was wrong. That is what made a track take four or five rounds.

`tools/track_views.py` renders headlessly through Playwright's chromium and
writes PNGs. **Read them.** Fixing what you can see costs one tool call; asking
the user costs a round trip.

## What made the last one take four hours

Tokyo Drift cost about four hours and **roughly 80% of that was aesthetic
direction**, not geometry. The layout passed all seventeen track tests on the
first write. What ate the time was five separate rounds of Chinmay loading the
page, driving, and saying "it doesn't look like a city", "too purple", "the
floor is dead", "that's not rain". Each of those is a full round trip.

Two things caused it and both are avoidable:

- **The references were never looked at.** He said "Tokyo city, the Tokyo Drift
  garage scene, Neo Bowser City" and the whole palette got built from a mental
  image of those words instead. Pink dusk instead of midnight, brown terrain, a
  dead floor - all of it findable in ten seconds against one screenshot.
- **Changes went out one at a time, serially.** Three floor effects were once
  invented on a hunch, shipped together, and rejected together. That round
  bought nothing.

So: **references first, then a long list of questions, then build.** Steps 0 and
0.5 exist to spend ten cheap minutes buying back three expensive hours.

## Steps

Work through these in order. Do not stop between them to ask permission,
**except** for steps 0 and 0.5, whose entire job is to ask.

### 0. Get reference images, and actually look at them

**Ask for two or three pictures of the thing before writing a single colour.**

```
Before I start - drop me 2-3 reference images of the look you want
(paste them straight in, or save them somewhere and give me the path).
A screenshot of the game or film you have in mind is worth more than
any amount of me describing colours back to you.
```

**You can only see an image that is pasted into the conversation or that exists
on disk for the Read tool.** `WebFetch` returns text, so "let me go find a
reference" does not work - you will get a description of a picture, which is
exactly the mental-model problem that caused this. If he has no images to hand,
say so plainly and expect the palette to take an extra round.

Once you have them, **Read every one and write down what you took from it**
before touching a palette - three or four bullets, in the message:

- the two or three colours that dominate, and roughly how dark the darkest is
- what is emitting light and what is only reflecting it
- how much of the frame is sky, ground, and stuff
- one thing that would be wrong to copy

That written-down version is what you check renders against later. A reference
you looked at once and did not write down is a reference you have forgotten by
the third render.

### 0.5. Ask a lot of questions

**At least ten, before any code.** Use `AskUserQuestion` - it takes four at a
time, so this is three calls and about a minute of clicking for him. Every one
of these was a question that got answered *after* the track was built last time,
and each one cost a rebuild.

Ask about the place: setting; time of day and weather; a real place or invented;
and **how much bespoke geometry it deserves** - palette only, palette plus a
capability that already exists (`terrain`, `below`, `shore`, an interior, the
city, rain), or something new written for this track. That last one is the
single biggest driver of how long it takes, so ask it explicitly rather than
inferring it.

Ask about the driving: length tier; difficulty; the one signature feature you
would describe the track by; flowing or technical corners.

Ask about the shape: elevation profile (flat, climb, descent, up-then-down);
jumps (none, one big, several); boost pads; ground or floating.

Offer a recommendation as the first option in each - he will usually take it,
and the ones he does not are precisely the ones worth having asked.

### 1. Write `track.py`

```python
"""Dockyard

Containers, cranes, and a long blast down the quay.
"""

slug = "dockyard"          # must equal the folder name
name = "Dockyard"
blurb = "Containers, cranes, and a long blast down the quay."
difficulty = 3             # 1-5
ground = -1.2              # world Y of the ground plane; None to float in the void
order = 160                # where it sits in the pool; existing tracks are 10..150
width = 12.0               # starting road width
rails = False              # default barriers; True for a floating track
closed = False             # True for a lap - see "Closed laps" below


def build(b):
    b.start(run=44)
    b.arc(72, 58).straight(30)
    b.cp()
    ...
    b.finish()
```

Read `drive/docs/tracks-and-geometry.md` for the `Builder` vocabulary before
writing anything real. The rules that catch people:

- **Corner radius is the whole character of a corner.** Under ~16 is a hairpin
  you brake hard for, 25-40 is third gear, over 60 barely slows you. Vary them -
  a test fails a track whose corners are all the same.
- **A hill needs length or it becomes a jump.** `length >= sqrt(330 * rise)`.
  40 units for a 5-unit climb, 77 for 18. Use `crest`/`jump` when you *want* the
  car thrown.
- **Barriers are opt-in.** On the ground, use them only where falling would be
  unrecoverable. A floating track needs `rails = True` or `exposed = True`.
- **Do not lay road back over road** without `CROSS_CLEAR` of vertical gap.

### 2. Run the track tests

```bash
cd drive && venv/bin/python -m pytest tests/test_tracks.py -q -k <slug>
```

Every failure here is a mistake somebody has already made. Fix them all.

**Only this, and only `-k <slug>`, until the very end.** It is four seconds. The
full `scripts/tests.sh drive` is eighty and tells you nothing extra about a
track you are still shaping - it was run six times during the last track, which
is seven minutes of watching tests about garage badges pass. Run the full suite
**once**, after step 6, before pushing. Same for `validate_track.py`: it boots a
browser *and* runs pytest, so it belongs at the end and not in the loop.

### 3. Measure it against the sixteen that are already good

```bash
cd drive && venv/bin/python tools/pool_stats.py <slug>
```

The pool is a labelled set of good tracks and this reads it back: 26 numbers,
compared against the other fifteen. It says *unlike the pool*, not *wrong* — Big
Red's 223-unit drop flags every time and is the point of the track. Go through
every `>>` and satisfy yourself it was deliberate. What it reliably catches is
the mistake with no visual signature: a scatter density ten times anything else,
a `fogFar` a tenth of anything else, a two-stop sky. Those are typos, and they
look fine in code.

### 4. Render it, and look

```bash
cd drive && venv/bin/python tools/track_views.py <slug>
cd drive && venv/bin/python tools/track_views.py <slug> --at 0.02,0.31,0.5,0.8
```

**Read `views/<slug>/sheet.png` and nothing else.** It tiles the plan view and
every road view into one picture, so a round is one Read instead of six - and it
puts the plan and the road side by side, where a leg that left the building and
the corner it wrecked are visible in the same glance.

**Batch the fractions.** A browser boot is most of what a picture costs, so
`--at 0.31` four times is four boots and about six minutes; `--at 0.02,0.31,0.5,0.8`
is one boot and ninety seconds. This is the biggest single difference between a
fast authoring round and a slow one.

**Read `drive/docs/track-defects.md` first and check the pictures against it.**
It is short, and it is the running list of everything that has gone wrong in a
track here — the road buried in the ground, geometry floating, a corner arriving
with no warning, a crest hiding the next braking point, a sky washing the kerbs
out. Looking *for* known failures finds far more than looking at a picture and
seeing what you happen to see.

**When Chinmay spots something you missed, add it to that file** before fixing
it. One line, no need to generalise it. That is how the list grows, and it is the
only mechanism that carries a lesson from one track to the next.

- **`plan.png`** is what catches layout mistakes: a leg that left the building, a
  hairpin that bulged into the one beside it, a crossing that is not where you
  meant it, a closing stretch half as long as it read in the code.
- **the road views** catch feel and look: a corner that arrives with no warning, a
  crest hiding the next braking point, a sky that washes the kerbs out, a ceiling
  the camera is about to clip. The car is in frame deliberately - it is the only
  object with a known size, so it is what tells you the road is as wide as you
  meant.

Fix what you can see, and re-render. This loop is the point of the skill.

**When the thing in doubt is a *look*, render variants and let him choose - do
not pick one and wait.** Geometry is worth iterating on, because he is attached
to a layout and wants it nudged. A palette is not: it is cheap, disposable, and
entirely a matter of taste, so the fast move is three of them in one message.
Copy the palette to `palette.py`, shoot the sheet, `git stash` it, try the next.
Three variants in one round beats three rounds of one variant every time, and it
is the difference between his taste being a slow feedback signal and a fast
filter.

The same rule kills the worst kind of round: **never invent several aesthetic
changes at once and ship them together.** Three floor effects once went out on a
hunch in one go and all three came back rejected, so nothing was learned about
any of them.

### 5. Validate

```bash
cd drive && venv/bin/python tools/validate_track.py <slug>
```

Geometry, seam closure, medal times, the preview, the track tests, and the
browser console. Everything must be `ok`.

### 6. Take the switcher preview

```bash
cd drive && venv/bin/python tools/shoot_tracks.py <slug>
```

Nothing in the suite can notice a stale preview, so this is a step and not an
afterthought. Only commit this track's PNG - if others come back modified, that is
antialiasing noise from a different browser build, so `git checkout` them.

### 7. Serve it and hand over the link

```bash
cd drive && PORT=5005 venv/bin/python app.py
```

Run it in the background and give the user
**`http://localhost:5005/solo/<slug>`**, with the plan view, a road view and the
medal times in your message. Leave the server up so their feedback lands on the
same URL after a reload.

## Palettes

`palette.py` defines `PALETTE = {...}`. Required keys are `road`, `kerb`, `kerb2`,
`ground`, `rail`, `prop`, `deco`, `fog`; `tracks/look.py` lists every optional
block and refuses a palette with a key nothing reads, which is the usual typo.

Colours are packed RGB integers written as hex. **Pick them cooler than they
look**: a light's colour goes through sRGB-to-linear and a vertex colour does not,
so a warm key light multiplies a neutral grey road down to mud. Copy a palette
from a track with a similar mood and adjust.

## Closed laps

Set `closed = True` and end the build with `finish_at_start()`. `tracks/solver.py`
makes the ribbon meet itself - position, heading and height - by adjusting one or
two legs, and reports what it changed. You do **not** have to make the corners sum
to 360 or the climbs cancel.

Two rules the solver cannot fix for you:

- **Do not end mid-corner.** The road either side of the seam has to be going the
  same way, or the join is a kink. End on a straight.
- **Get within about 10% of closing.** The solver will not stretch a straight more
  than 15% or move a corner more than 8 degrees; past that it refuses and tells
  you which leg and by how much. That guard exists because an early version of it
  turned Spa's Stavelot into a 179-degree hairpin.

Use `FREE(...)` to nominate which legs it may adjust, if its own choice is wrong:
`b.straight(FREE(330 - CP))`. Wrap the *whole* expression - `FREE(330) - CP` is an
ordinary float by the time the Builder sees it, and the mark is silently lost.

## Custom scenery

Only when a track needs geometry no palette can express - the Costco is an
interior with walls, racking and a roof. Set `scenery = True` in `track.py` and
add `scenery.js`:

```js
(function () {
  if (!globalThis.DRIVE_SCENERY) globalThis.DRIVE_SCENERY = {};
  globalThis.DRIVE_SCENERY.dockyard = { props: props };
  function props(ctx) {
    const { solid, bright, signs, col, track, pal, KIND, shade } = ctx;
    // ...
  }
})();
```

Copy `tracks/costco/scenery.js` for a worked example. **If it adds anything a car
can hit, it is in the anti-cheat's collider too** - `verify.py` re-drives
submitted laps through the same `buildTrack`. `tests/test_scenery.py` records the
collider triangle count per track and will tell you when it moves.

## When it is a change to an existing track

Same loop, minus step 1. Two extra things:

- **`tests/test_tracks_did_not_move.py` will fail, and that is correct.** It
  compares every station against a snapshot. If the change is deliberate, re-run
  `tools/snapshot_tracks.py` and commit the snapshot as part of the same change,
  saying which track moved and why.
- **Medal times move with geometry.** Every lap on that track's board was graded
  against the old ones. `tools/snapshot_tracks.py --check` prints the delta.

## Do not

- Edit `trackmesh.js` to add a track. Nothing outside the folder should need to
  change; if it does, say so rather than working around it.
- Touch `tuning.py`. It is the single source of truth for the simulation, and
  retuning the car retunes every medal on every track.
- Skip the render. The whole reason this skill exists is that the pictures are
  now available.
