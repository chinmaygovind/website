# The track maker

`/make`. Anybody can build a track in a browser, drive it, and publish it; a
published one is a track in every sense the rest of this game means the word.

**The whole feature is one line.**

```python
tracks_mod.set_resolver(_resolve_user_track)          # maker.py
```

`tracks.get` is the single chokepoint `/solo`, `/api/track`, `/api/run`,
`/api/start`, `/api/ghost`, rooms, replays, share cards, `robots.txt`,
`sitemap.xml` and the switcher all go through. Teaching it to fall through to a
database row is what makes every one of those work on somebody's track without
being edited. Everything else in this document exists to make sure what comes
back out of that resolver is a real track.

So: **a user track is not a second kind of track.** A row holds the authored
*document*; `tracks.from_document` replays it through the same `Builder` that
builds Spa; and the same `_one()` derives the medals, the pole side, the gate
ceiling and the ideal lap. There is no parallel implementation of a track
anywhere in here — only a different way of storing one.

## What is where

| you are changing | read |
|---|---|
| the editor's UI, the camera, the live preview | `static/js/make.js`, `templates/make.html` |
| the move vocabulary | `tracks/moves.py` — `SPEC`, `HELP`, `Recorder`, `replay` |
| the palette editor and its warnings | `tracks/look.py` — `check` raises, `advise` speaks |
| the scenery library | `static/js/scenery_kit.js` |
| the code sandbox | `static/js/scenery_{host,worker}.js` |
| saving, the gate, the queue | `maker.py` |
| promoting one into the pool | `tools/adopt_track.py` |

Tests: `test_moves.py`, `test_make.py`, `test_user_tracks.py`,
`test_scenery_code.py`, `test_scenery_kit.py`, `test_publish.py`,
`test_no_js_name_clashes.py`.

## The document

A track is a **list of moves** — a turtle walking a road into existence. Fifteen
move types, in `moves.SPEC`, each described in one line in `moves.HELP` (the two
are asserted to cover the same set, because `HELP` is handed to somebody's AI and
a vocabulary described in a file somewhere else is one that will be described
wrongly).

`Builder.sections` is **not** the document format and never was. `width()`,
`rail()` and `bank()` append nothing to it; `crest()` records itself as an
ordinary `straight`, so a jump and a hill are indistinguishable; and checkpoints
live in `gates`, never in `sections`. It is a lossy positional index built for
the closure solver. The editor has its own complete schema and `sections` stays
exactly what it is.

**One deliberate difference from the turtle.** Every road-laying move carries its
own `w`, `rail` and `bank` rather than inheriting sticky state. In a text file
`b.width(13.0)` reads fine; in a list you can *reorder*, and sticky state means
deleting one move silently rewidens nine others. `replay` converts back, calling
`b.width()` only where the value changes — and `tools/adopt_track.py` does the
same thing when it writes a folder, which is why an adopted track reads like the
hand-written ones.

All nineteen pool tracks round-trip **byte-identically** through
`record → JSON → replay`, closed laps included: the `FREE` marks survive and the
solver picks the same legs with the same adjustments. That is
`test_user_tracks.py`, and it is the evidence that the schema is complete rather
than merely plausible.

## The editor

One screen: moves down the left, the world in the middle, the selected move's
numbers on the right, the height of the lap along the bottom. Four tabs on the
right — Move, Look, Scenery, AI.

**It does not build roads.** There is no second `Builder` in JavaScript, for the
same reason there is no second copy of `ACCEL` in a `.js` file. `/api/make/build`
replays the real one, throttled. Measured: a ribbon is ~4ms, `laptime.ideal_lap`
is ~550ms, so the editor asks for the road on every change and the lap time only
after you stop.

Three things in here were bugs first and are worth not reintroducing:

* **The camera holds its angle.** `aim(why)` takes a reason — `first`, `select`,
  `edit`, `frame` — and only a *deliberate* re-frame touches yaw or pitch. The
  first version re-framed on every rebuild, which makes a slider drag unusable:
  you lose the view you were judging the change against, which is the only
  reason to have a live preview. Distance expands but never contracts. `View all`
  and `F` are the way back out; removing auto-framing without them was a
  regression.
* **A throttle, not a debounce.** A debounce is cleared by every event, so a
  drag emitting a change per frame never reaches its own trailing edge and the
  road only moves once the pointer stops. That was the bug.
* **A slider drag must not rebuild the inspector.** `drawInspector()` replaces
  the range input under the cursor and ends the drag one frame in — measured as
  exactly *one* preview across a twelve-step drag. Hence the `live` flag
  threaded through `setField`. And a pointer drag must not end on `change`:
  Chromium fires it the instant the pointer lands, because clicking the track
  *is* a commit.

The pending indicator is shown after 130ms and held for 320ms. Raised instantly
it strobes once per frame against a fast server; dropped instantly it flashes for
two frames and reads as a glitch.

## The look

Every palette key gets a control, for everyone — `look.check` already makes the
two silent failures impossible (a missing required key cannot ship, a misspelled
optional one is refused rather than ignored), so what is left is taste, and taste
gets warnings and not walls. `test_make.py` asserts every non-scenery key in
`look.KNOWN` has a control, so adding a key is a decision about the editor too.

`look.advise(pal)` is the eight taste warnings from `docs/track-defects.md`, and
every threshold is the **pool's own measured range**. Calibration matters in both
directions: a threshold nothing can reach is one nobody will believe, and a
threshold a shipped track trips is one nobody will believe *twice*. It currently
returns **0 warns and 7 notes** across the nineteen, all accurate — Chicane Park
and Skyline genuinely have no graded sky, Tokyo Drift's road and ground genuinely
are the same value from above.

A palette edit never goes to the server for its picture. The palette is read by
`buildTrack` and the renderer and by nothing else, so the world recolours locally
in about a millisecond. The server is asked for the *words*.

**`Ride it` (V)** flies the ribbon from the driver's seat using `render.js`'s own
chase geometry — same set-back, lift and look-ahead, all speed-dependent the same
way, pinned on both sides by a test. A palette is judged in motion or it is not
judged: a night palette can be beautiful in a still and unreadable at speed.

## Scenery

Two paths, one interpreter.

**The library** (`scenery_kit.js`) is 38 models you drop in by name and adjust by
number: `{o: 'stand', at: 0.1, side: -1, tiers: 9}`. `placeAll` runs inside
`buildTrack`, so the placement list rides the track dict exactly as the palette
does and reaches the editor's preview, the play page, the switcher **and the
QuickJS anti-cheat** with no new plumbing. Measured in the verifier's own
runtime: a placed barrier takes Spa's collider from 43,566 to 43,674 triangles.

Six entries in `docs/track-defects.md` stop being *reachable* rather than merely
warned about — there is no way to write a world coordinate, nothing is a
single-winding quad (`obox` is built from `face`), everything stands on
`ground(i, off)`, offsets are clamped, data cannot throw, and there is one
interpreter rather than a copy per path.

Models are built from an **oriented** box, so they line up with the road:
`solid.box` is axis-aligned, and a hangar sitting at whatever angle the world
happens to be at reads as a mistake because it is one. Colours come off the
palette through `shade`, and buildings key off `pal.rail` and **not** `pal.prop2`
— `prop2` is the *second structural* colour and a track whose second structure is
trees sets it to dark foliage green, which is how the first factory came out
olive.

Exactly two models collide: `wall` and `tecpro`. That is an allowlist in two
places — `collides: true` in the JS and `moves.COLLIDING_MODELS` in Python — held
in step by a test, because a model in one and not the other is either a wall that
never wiped a board or a board wiped by a tree.

**Code** is for when the library does not cover it. One sentence is the whole
security model: *code runs while you author, geometry ships.* Untrusted
JavaScript executes in a Worker inside an iframe created with
`sandbox="allow-scripts"` and deliberately **without** `allow-same-origin` — that
omission is the isolation, because a Worker started from the main page inherits
the page's origin and could fetch our own API with the reader's cookies. What
leaves the sandbox is numbers.

Three things make that hold:

1. **The kinds are whitelisted, on the output.** Scenery may emit `KIND.WALL` and
   `KIND.OFFROAD` and nothing else. `verify.py` re-drives submitted laps against
   this exact collider, so a user-emitted `BOOST` quad would be a speed hack that
   arrives with a certificate of authenticity. `ROAD` is worse in a quieter way:
   fake surface the ground probe picks up.
2. **It is bounded.** 20,000 mesh triangles, 2,500 collider, a two-second
   deadline in the worker and a 2.5s kill in the host.
3. **`/make` declares `connect-src`.** With no `connect-src` and no `default-src`
   a browser permits every destination there is, so this is the backstop under
   the sandbox — verified by the browser reporting
   `connect-src -> https://evil.example/steal` blocked, with zero requests
   leaving.

`sceneryContext`, `shade` and `mulberry` are **injected into the sandbox as
source** off the live `trackmesh.js` exports, via
`Function.prototype.toString()`. Not fastidiousness: the first hand-written
`shade` in the worker had it as a multiplier instead of an amount, which is a
function that looks right and darkens everything it touches.

## Bring your own AI

The failure mode without this is easy to picture: somebody pastes *make me a
city* into a chat window and gets back `THREE.Mesh`, `document`, world
coordinates and single-winding quads, none of which exist here. So the deliverable
is not a button, it is **making the API legible to whatever model the player
already has**.

The key lives in `localStorage` and the request goes from the browser straight to
the provider. **This box never sees a prompt, a token or a bill.** Worth saying in
exactly those words, because the previous version of "Drive talks to a model" was
`/api/roll/gemini`, which forwarded anybody's body to Gemini with *this box's*
key, unauthenticated and unmetered. `test_scenery_code.py` asserts no route and
no key handling exists in `app.py` or `maker.py`.

Two halves, one assistant: the **layout** (generated from `moves.SPEC` +
`moves.HELP` + `checks`, because no model can guess `{"t": "arc", "deg": -150}`)
and the **scenery** API. The prompt is two blocks and the split is the whole
optimisation — all three providers cache on a *prefix*, so:

* `stat` — the vocabulary and the API. ~11.4KB, byte-identical every turn, with
  an explicit `cache_control: ephemeral` breakpoint after it.
* `live` — the track. Changes on every edit, so it can never be cached, and it
  sits *after* the breakpoint.

The document is sent as a **compact listing**, not JSON: `1 arc deg=-55 rad=42`,
defaults omitted. On a 190-move track that is 13.8KB → 4.4KB. Older turns have
their code blocks replaced with `[an earlier version, superseded]` — an old code
block is not history, it is a wrong answer, because the live block already says
what the code *is*.

Replies come back as an **edit script**, not a document: `{"ops": [{"op": "set",
"at": 6, "fields": {"rad": 24}}]}`, applied highest-index-first so an insert at 9
cannot shift a delete at 4. It says what was *meant* — "tighter turn three" is one
`set` — and it cannot rewrite four other corners on the way past. Nothing is
applied unseen: a layout is shown as a real LCS diff with an Apply button.

No `temperature`, `top_p` or `top_k`. On `claude-opus-5` and `claude-sonnet-5`
they are rejected with a 400 — gone, not deprecated — so a sampling knob here is
not a tuning choice, it is a panel that cannot send a message. `max_tokens` is
16000 because thinking is on by default and the cap covers thinking and reply
together.

## The gate

Structural checks block; taste warns. **And you cannot submit a track you have
not driven, start line to flag.**

That is the best of the four options considered, for a reason worth naming: it
proves finishability by *demonstration* rather than by inference, and it pays for
itself three times over — that lap is the track's first record, its first ghost,
and the line `tools/hotlap.py` needs, so a brand-new user track has bots that
drive it properly instead of following the relaxed line.

The proof is keyed on the **geometry fingerprint**, not the slug: driving it and
then moving a corner does not count, because what was proved was that *that road*
can be finished.

None of the checks are new logic. They are the battery `tracks/checks.py` and
`drive/tests/` already apply to the nineteen, run per document on demand instead
of at import, with the output written for a person. `checks.pole_side` and
`gate_ceiling` are *measurements* and not verdicts — the judging that used to live
only in `test_tracks.py` is now in `_run_checks`, and the drivability floors
(`MIN_RADIUS`, `MIN_LOOP_RADIUS`, `RADII_DISTINCT`, `RADII_SPREAD`) moved into
`checks.py` so the editor can say them.

## Lifecycle

Four states — `draft`, `queued`, `live`, `hidden` — and one rule that keeps a
leaderboard meaning something: **what you approved is what is live.**

Two hashes, because the board rule and the review rule are not the same rule:

| what changed | board | status |
|---|---|---|
| a colour, the name, the difficulty | kept | stays live |
| the scenery (mesh only) — `look_hash` | **kept** | back to `queued` |
| the road, or a collidable placement — `geom_hash` | **wiped** | back to `queued` |

A mesh-only edit re-queues but keeps the board: lap times do not depend on a
tree, but what was approved was a *particular* scene and an edit could replace it
with one that would not have been. `geom_hash` is taken over the **built ribbon**
and not the document, so a no-op edit — drag a slider and drag it back — costs
nobody their record, and a change that looks cosmetic but moves the road is caught
anyway.

The trade to accept out loud: a live track's author cannot fix a bad corner
without losing the board. That is correct — the alternative is somebody's record
silently becoming a time on a different road.

Review is a lap, not a form. `/admin/tracks` is a list with a Drive button,
because the only question worth asking about somebody's track is whether it is
any good and nothing on a page answers that. It 404s for anybody who is not in
`ADMIN_USERNAMES`, logged in or not, because a 403 would confirm it exists.

## Covers

Every track has a picture from the moment it is saved: `tracks/plan.py` draws the
shape of the lap from the ribbon, stored on the row in `plan_path` because a
gallery of sixty cards must not replay sixty documents to draw itself. It is
arguably the *better* picture — what tells one track from another is its shape,
not a three-quarter view of some tarmac.

A real render is `tools/shoot_user_tracks.py`, which is nearly empty: a published
track is resolved by `tracks.get` exactly as Spa is, so `_hero.shoot` can
photograph `/solo/<slug>` without knowing user tracks exist. Run by hand and not
by the approve button — approving happens on the one eventlet worker that is also
relaying live race poses at 30Hz, and starting a headless Chromium in there would
be a strange way to drop everybody's race.

## Adopting one into the pool

`tools/adopt_track.py <slug>` turns a live row into a `tracks/<slug>/` folder.
Not to make it *work* — it already works — but for the things only a folder gets:
it is in the repository, it can have hand-cut medal times, it gets a place in the
difficulty ramp, and it can be edited by hand afterwards.

Emitting `build(b)` source is a second implementation of what `replay` does, so
the tool does not trust itself: it writes the folder, imports it as the pool
would, builds the ribbon and compares `moves.fingerprint` against the row's.
Different road and the folder is **deleted** and the tool says so. A drift in the
generator is caught on the very track it would have broken, every time.

Placements survive adoption because a track module may declare `placed = [...]`,
read by `tracks._one` and drawn by the same `placeAll` — nothing is rewritten as
code. The row is left alone; the pool wins once the folder ships, because
`tracks.get` checks `BY_SLUG` before it asks the resolver.

## Traps

* **`track["scenery"]` is a boolean** — does this track have a `scenery.js`. The
  placement list is `track["placed"]`. Putting it on `scenery` reads as
  `true.length` in JavaScript, which is `undefined`, which is falsy: the scenery
  is never drawn and nothing says so.
* **`tracks.slug_is_available` returns `(ok, why)`**, not a bool. Reading it as
  one is a truthy tuple, which let every reserved and pool slug through —
  including `draft`, which is the slug every draft is driven under, so a row
  holding it would put draft laps on a real board.
* **Every top-level name in a bundled `.js` shares one scope.** `jsrt.py`
  concatenates `trackmesh.js`, `physics.js`, `course.js`, `scenery_kit.js`, every
  `scenery.js` and whatever a caller appends, with module syntax stripped. A
  `const clamp` in two files is `SyntaxError: invalid redefinition of lexical
  identifier`, and it does not name either file — it took out seventeen bot tests.
  `test_no_js_name_clashes.py` guards the whole bundle now. `var` would be worse:
  it redefines silently.
* **`moves.fingerprint` takes scenery in two shapes** — a placement *list* from
  the library or a baked-geometry *dict* from code. Reading one as the other is a
  500 on save.
* **A CSS `display` rule outranks the `hidden` attribute.** `#tabai { display:
  flex }` rendered the chat underneath whichever tab was open. Any tab with a
  `display` of its own needs `[hidden] { display: none }`.
* **`/make` and everything under it 404s in the portal build.** CrazyGames forbid
  a game offering its own login, and authorship without identity is not a thing.
