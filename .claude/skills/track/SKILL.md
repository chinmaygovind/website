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

## Steps

Work through these in order. Do not stop between them to ask permission.

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

### 3. Render it, and look

```bash
cd drive && venv/bin/python tools/track_views.py <slug>
```

Writes `drive/tools/views/<slug>/plan.png` plus five along the road. **Read every
one with the Read tool.**

- **`plan.png`** is what catches layout mistakes: a leg that left the building, a
  hairpin that bulged into the one beside it, a crossing that is not where you
  meant it, a closing stretch half as long as it read in the code.
- **the road views** catch feel and look: a corner that arrives with no warning, a
  crest hiding the next braking point, a sky that washes the kerbs out, a ceiling
  the camera is about to clip. The car is in frame deliberately - it is the only
  object with a known size, so it is what tells you the road is as wide as you
  meant.

Fix what you can see, and re-render. This loop is the point of the skill.

### 4. Validate

```bash
cd drive && venv/bin/python tools/validate_track.py <slug>
```

Geometry, seam closure, medal times, the preview, the track tests, and the
browser console. Everything must be `ok`.

### 5. Take the switcher preview

```bash
cd drive && venv/bin/python tools/shoot_tracks.py <slug>
```

Nothing in the suite can notice a stale preview, so this is a step and not an
afterthought. Only commit this track's PNG - if others come back modified, that is
antialiasing noise from a different browser build, so `git checkout` them.

### 6. Serve it and hand over the link

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
