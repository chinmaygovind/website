# The static site (`site/`)

The web root. `app.py` serves everything under here as static files with
GitHub-Pages-style directory indexes. No build step, no bundler — pages are
self-contained HTML with inline `<style>`/`<script>`.

**`site/index.html` carries no comments, and that is deliberate.** There is no
build step, so every comment is shipped to every visitor and is the first thing
anyone sees on view-source; a page explaining itself paragraph by paragraph
reads as machine-written. It had ~900 lines of them and they were deleted
wholesale (2026-08-17). Everything they said that was worth keeping is in this
file — **so put it here, not in the markup.** Name things well enough that the
comment would have been redundant, and if it would not have been, write it down
below.


- `site/index.html` is the landing page: big "hey!" left, welcome line
  and contact links across the top, all in the self-hosted xkcd Script font
  (white page, or near-black — see **Dark**)
  (`site/fonts/xkcd-script.woff2`, from ipython/xkcd-font — see **The font** below).
  Below it are **two
  labelled tile rows** — `<section class="tilerow">` each holding an
  `<h2 class="rowlabel">` and its tiles, `ABOUT ME` over resume, poker, whales,
  racing, music, settings and `GAMES` over drive, ttr, ers, kot. Each row is its
  own `repeat(6, --tile)` grid, so the two line up as they did when they shared
  one twelve-slot grid, and **six is still the row width**: a seventh tile in a
  row wraps *within that row* rather than into the row below. **Keep `settings`
  last in the top row** — it opens the panel, not a page about Chinmay, so it
  sits at the end (see **The settings panel**) — and add new games to the
  `GAMES` section so the split holds.
  **The labels cost the tiles nothing** — they were added without a single icon
  moving, and there is a check for that: shoot the page before and after and
  diff the pixels (`ImageChops.difference(...).getbbox()`), and the only band
  that differs is the strip the labels are in. That is what `position: absolute`
  on `.rowlabel` buys — it hangs in the margin left over beside six tiles rather
  than taking a column. Two things it needs: the row is `width: max-content;
  margin: 0 auto` so that `right: 100%` means "the left edge of the tiles", and
  the label needs an explicit `width: max-content`, because an absolute box
  positioned entirely outside its containing block gets no available width and
  shrink-to-fit collapses it to its longest word.
  **Below 900px the label goes above its row instead**, back in the flow and
  spanning the grid: `--tile` has bottomed out at its 110px floor there while
  the screen keeps shrinking, so six tiles are already most of the page and
  there is no margin to hang anything in. At 760 and below it stays above the
  row and the grid drops to two columns, which is the phone layout. Drive's tile was pulled for
  a while (Jul 2026) so Chinmay could draw the icon himself, and came back once he
  had — the steering wheel in `assets/icons/drive.{png,gif,xcf}` is his.
- **Adding a tile is one repeating pattern**, all inside `site/index.html` (no
  build step, so everything is inline):
  1. a `--<name>` accent colour in `:root` **and a lifted one in the
     `html[data-theme="dark"]` block below it** (see **Dark**), then **one**
     line wiring it up: `.modal-<name> { --accent: var(--<name>); }`;
  2. a `<button class="tile" data-modal="modal-<name>">` with a `.tile-img` whose
     `data-still`/`data-anim` are `assets/icons/<name>.png` / `.gif` — the script
     at the bottom swaps to the gif on hover and preloads it, so **every tile
     needs both files**;
  3. a `.modal` + `.modal-box .modal-<name>` block, left pane = `.pane-title` +
     `.pane-text` (+ `.modal-icon` gif top-right), right pane = `.media` frames
     holding a `.media-img` or a dashed `.placeholder` while art is pending.
  The generic script wires open/close (X, backdrop, Escape) off those classes —
  a new tile needs no JS. Icon sources are GIMP `.xcf` files kept next to the
  exported png/gif in `site/assets/icons/`.
- **`--accent` is the modal's colour and every rule that draws in it reads the
  variable** — the box's 7px edge, `.pane-title`, the picture frames, the dashed
  placeholders, the concert arrows and thumbs. It used to be the same hex named
  in three places per tile, which is how the frames drifted apart in the first
  place; now a tile cannot half-change colour.
- **Every picture, clip and PDF is framed the same way: a 2px `--accent` line
  with 6px corners, on the *frame* and never on the media inside it.** One rule
  covers `.media-frame`, `.pdf-frame`, `.pdf-shot`, `.video-wrap` and
  `.concert-stage`, and `.media-img` explicitly carries no border and no radius
  of its own. **The border has to be on the frame** because the frame is also
  the `.fit-frame`: a shot that does not match its slot is centred on a blurred
  blow-up of itself, so a border on the image traced the shot and left the
  filler outside the line — two rectangles, worst in racing, where a wide
  screenshot in a tall slot drew a small red box floating in grey. `overflow:
  hidden` on the frame is what makes the corners real, clipping both the shot
  and its backdrop. Drive was the only modal that already did this; it is now
  the rule and drive's own block is just the 16:9 sizing.
- **Drive's pane is the demo clip over a Rainbow Road still**, and both frames
  are `aspect-ratio: 16/9` rather than stretching to the pane, because a 16:9
  picture in a full-height slot is a small image between two tall bars of its
  own backdrop. `flex: 0 1 auto; min-height: 0` lets the pair give way on a
  short screen (landscape phone) instead of overflowing — they pillarbox
  against the backdrop, which still reads as one rectangle.
- **The blue name in the `<h1>` is a `<button>`, and it opens `#modal-about`.**
  It is the only opener on the page that is not a tile, which is why the click
  handler binds `[data-modal]` rather than `.tile` — a tile needs no JS and
  neither does this. It grows (`translateY(-4px) scale(1.04)`) on hover and on
  `:focus-visible`, the same "this is clickable" language the tiles use.
  **Turning the `<span>` into a `<button>` moved nothing**: the rule restates
  `margin`/`padding`/`border`/`background`/`font` that the span got for free, and
  the landing page is pixel-identical before and after at 1440x900 and 390x844
  (shoot both, `ImageChops.difference(...).getbbox()` is `None`). Keep it that way.
- **`openModal` closes whatever is already open before it opens.** Nothing could
  reach two modals at once until the resume pane grew a link *into* the whales
  modal; without the close, both boxes stack and only one `Escape` reaches the
  one underneath.
- Two panes are live rather than static: the about modal's fast facts patch in a
  computed age and the Duolingo streak, and the music tile fills recently-played
  and top-artists from the Spotify proxy, plus a concert carousel driven by
  `site/assets/music/concerts.json` (add a concert by appending to that JSON —
  no code change).
- **The resume modal's left pane is the work history, not the fast facts** (Aug
  2026). The facts were a list of Clash Royale wins and a Bedwars star count
  sitting beside a resume, which is not what somebody who opened `RESUME` came
  for; they moved to `#modal-about` behind the name. Three `.exp-item`s, each a
  logo, org, role, dates and one sentence, joined by a **dotted connector that is
  a `::after` on every item but the last** — `border-left: 4px dotted` hung under
  the mark, `bottom` reaching into the flex `gap` so it lands on the next logo.
  It is keyed off `--exp-mark` and `--exp-gap`, so changing either size keeps the
  line attached; a fourth job is one `<li>` and nothing else.
- **All three orgs are clickable and none of them is styled as a link, which was
  asked for in those words.** Whales is a `<button data-modal="modal-whale">`
  (the same handler as every tile), Shopify and Susquehanna are `<a>`s to
  `shopify.com` / `sig.com`, and `.exp-open` styles all three identically:
  `color: inherit`, a 2px underline in `--faint` at rest, and on hover/focus the
  underline goes to `--accent` while the title lifts 2px and the logo beside it
  grows 8%. **Do not give these `--link`** — a blue underlined title was the
  first attempt and was rejected. `.exp-inline` is the same treatment for a
  phrase inside a sentence (SIG's "2026 Susquehanna Showdown", which opens the
  poker modal) and differs in exactly one way: **no `display: inline-block` and
  no `transform`**, because a multi-word phrase inside a paragraph has to be
  allowed to wrap, and `transform` does nothing to an inline box anyway.
- **The three logos are the brands' own marks and none of them needs a dark-mode
  rule**, which is the whole reason these three files were chosen: the whale is
  the existing tile icon, `assets/experience/shopify.svg` is the official
  two-tone bag lifted out of the wordmark SVG (viewBox cropped to the bag, the
  wordmark path dropped), and `assets/experience/sig.png` is Susquehanna's own
  square favicon mark — white waves on their blue — rebuilt at 256px from the
  high-res wordmark, because the shipped favicon is only 100px and the
  `SUSQUEHANNA` wordmark is 3.5:1 and vanishes in a square slot. All three read
  on white and on #101114 as they are. **Do not add them to the
  `filter: invert(1)` rule** — that one is for the resume line art alone and
  would wreck all three.
- **The resume pane is `site/assets/resume-preview.png` on every screen, and
  there is no iframe any more** (Aug 2026). It used to be a PDF in an `<iframe>`
  wide and the flat render only below 760px, because a phone draws a fixed,
  non-scrollable snapshot of the top of the page. The picture turned out to be
  the better thing on a desktop too: **the whole of page 1 at once**, rather than
  a viewer showing its top quarter behind a scrollbar and a toolbar. Deleting the
  iframe took its `data-src` dance with it — that existed only because
  `display: none` does not stop an iframe loading, and there is nothing left to
  defer. The `<a class="pdf-shot">` is still the link to the real PDF.
  **`.pdf-shot` is painted `#ffffff` on purpose**, a fifth deliberate literal
  alongside the four listed under **Dark**. The image is `object-fit: contain`
  inside a box whose shape is the pane's, so on a short screen (landscape phone
  is the worst, 348x246 against a 612:792 page) it letterboxes — and on dark the
  gap drew the panel as two bands inside the white frame, the same "two
  rectangles" fault `.fit-frame` exists to fix elsewhere. A blurred blow-up is
  wrong for a document, so the mat is simply paper-white and reads as the page.
  **Re-render the picture whenever the PDF changes** —
  `python3 tools/render_resume_preview.py` — and `tests/test_resume_preview.py`
  fails if you forget, by comparing a stamped sha256 of the PDF, because a stale
  preview does not look broken, it looks like last year's resume. That test now
  guards the only thing anybody sees.
- **The resume modal still reorders below 760px**: the preview comes *first* and
  the work history sits under it, because that is what the tile promised.
- **`#modal-about` is the fast facts plus a photo collage**, opened only by the
  name (see above) and by nothing else — it has no tile, because it is who
  Chinmay is rather than a thing he did. Its `--accent` is its own `--about`
  token — a sky blue, `#3a97d4` light and `#7cc4f0` dark — and **not**
  `--name-blue`. It was `--name-blue` at first, on the theory that the border
  should match the word you clicked; the literal `blue` that makes is far too
  loud for a 7px edge, so the two are deliberately different blues now. If you
  re-pick it, keep it over 3:1 on the panel — `.pane-title` paints in `--accent`
  and it is large text, not decoration.
- **The collage is 20 `.polaroid` buttons absolutely positioned from `--x`/`--y`/
  `--r`/`--z` written into each one's `style`.** Four columns by five rows of
  anchor points, jittered, deliberately overlapping — the pile fills the pane
  with **no scrolling**, which is the point of it. The jitter is allowed to go
  negative so the pile spills past the top and side edges and `.pane-right`'s
  `overflow: hidden` crops it; that bleed is intentional, not a fit bug.
  **The size is capped against the container's height, not just its width**
  (`width: min(24%, 19cqh)`, `container-type: size` on `.collage`), and that is
  load-bearing: at 24% alone the bottom row is fine at 1440x900 and hangs 51px
  out of the box at 760x1000 and 32px at 844x390, because a polaroid's height
  comes from its width and five rows of them do not care how short the modal got.
  Check a change by measuring, not by eye — every `.polaroid` rect against the
  `.collage` rect at 1440x900, 1280x720, 1024x600, 844x390 and 390x844. The bare
  `width: 24%` line above the `min()` is the fallback for a browser without
  container query units, where an invalid `width` would otherwise shrink-to-fit
  each polaroid to nothing.
- **Clicking a polaroid zooms it with a FLIP, and the clone is what animates.**
  The real polaroid stays in the pile (hidden with `visibility`, so its rect is
  still measurable for the flight home) and a `.zoom-card` is built in
  `#photo-zoom`, laid out at its final centred size, then transformed *back* onto
  the thumbnail's rect and released. Three details make it work: the box must be
  un-`hidden` **before** the final rect is measured or every offset reads 0; the
  scale uses `source.offsetWidth` and not the rect width, because the thumbnail
  is rotated and its bounding box is bigger than it is; and the start transform
  carries a `rotateY(-18deg)` against the stage's `perspective`, which is the
  entire reason it reads as 3D rather than as a slide.
  **`Escape` closes the zoom before it closes the modal** — one handler, and
  `closeZoom()` returning true is what stops it falling through, or the photo and
  the whole modal would vanish on one press.
- **The photos in `site/assets/about/` are 560x560 JPEGs named `photo-01..20`,
  and they are Chinmay's own** (Aug 2026 — they were freely-licensed Super Mario
  pictures for about a day). The originals live in
  `~/GDrive/Z Malarkey/Website Photos`, with web-safe JPEG copies of each in its
  `converted/` and anything dropped from the set in its `unused/`.
  **`SOURCES.json` records which original each slot came from** and is rewritten
  by the tool below, so the mapping is never guesswork.
  **Slots are assigned by sorted filename**, which is worth knowing before you
  add or remove an original: pulling one out shifts every slot after it, and
  since each slot carries its own position and rotation in the pile, the whole
  collage reshuffles. That is harmless — it is a scattered heap either way — but
  it does mean "photo-04" is not a stable name for a particular picture.
  Swapping one picture without disturbing the rest is a Save into that slot in
  the cropper, not a re-run of `--auto`.
- **`tools/crop_photos.py` is how a photo becomes one of those squares**, and it
  exists because the polaroids are `aspect-ratio: 1/1` with `object-fit: cover`:
  drop a portrait phone photo in unedited and the browser centre-crops it, which
  on a picture of people is usually the wrong third. The tool serves a cropper on
  :5055, reads whatever the folder holds — **including HEIC straight off an
  iPhone, which needs `pillow-heif`** (deliberately not a site requirement;
  nothing at runtime reads one) — and on Save writes
  `site/assets/about/photo-NN.jpg` itself, so there is no download-and-move step
  and no chance of a mis-named file. It only touches the slots you save.
  **The server re-encodes what the canvas sends** rather than trusting
  `toDataURL`'s quality, which is what keeps a saved crop the same weight as the
  files already in the folder — and `--auto` and Save go through the same
  `write_slot`, so a hand crop and a default crop cannot come out weighing
  different amounts.
  **`--auto` fills all twenty with the centred cover crop and exits**, which is
  what the browser opens on and what `object-fit: cover` would have done anyway,
  just done once at 560px instead of on every visitor's machine. That is the
  usual path: run it, then open the cropper only for the few it framed badly.
- **The modals are height-bound before they are width-bound, and only the two
  width breakpoints (900/760) used to know it.** Every screen gets the same
  `min(780px, 90dvh)` box, so a 1280x720 laptop has 130px less than a desktop at
  the same width and a phone turned sideways has 400px less. The music modal is
  the one that notices, because its left pane stacks four things: at 720px tall
  the whole `top artists` row sat below the fold of a pane that scrolls without
  saying so, and in landscape the concert arrows and caption were cut off
  outright by `.pane-right`'s `overflow: hidden`. Two `max-height` queries at the
  foot of the stylesheet fix it — 800px compacts the Spotify side, 560px
  compacts the concert side and gives `.pane-right` an `overflow` so nothing in
  it can be unreachable. **They come after the width query on purpose**: a small
  phone matches both, and the height is the tighter constraint.
  `.spotify-tracks` is its own scroll box inside that pane, and **its
  `max-height` is always an exact number of rows** (`4 x 54 + 3 x 0.7rem`
  desktop, and each query re-does the sum with its own row height): cut between
  two rows it reads as a list that continues, cut through the middle of one it
  reads as a broken page. Check a change with a screenshot at 1024x600 and at
  844x390, not just at a phone width — width alone will not reproduce any of this.
- `site/404.html` is a small Mario platformer, served by the 404 handler and so
  reachable only by a bad URL. Its four sounds are in `site/audio/`, which holds
  nothing else; the paths are absolute (`/audio/...`) so the game works at any
  URL it is served under.
- `site/{robots.txt,sitemap.xml,favicon.ico,favicon.png}` at the root, and
  `site/images/` which is now one file, the custom cursor.

**Everything else that used to be here is gone** (Aug 2026): `home/` (the old
projects landing page), `wii/` (the Wii-menu recreation), `channels/`, `games/`
and `projects/`, plus `videos/` and most of `audio/` and `images/`, which only
those pages used. Nothing linked to any of it - the landing page's tiles open
modals or point off-site - so it was reachable only by typing the address. That
took `site/` from 615MB to 140MB. It is in git history if a page is ever wanted
back; the deleting commit is the one to read first, because the Mario game's
audio had to be moved out of `home/` on the way.

## The settings panel

The settings tile used to open a placeholder. It is now a device settings screen
— an **About** list down the left and **twelve controls** down the right, of
which **exactly one (appearance) is a real preference** and the other eleven
exist to be found. Aug 2026. It is not a Wii-menu joke; it is a phone's settings
app, and the About panel is the tell.

**No control may explain itself.** There is no subtext under any row and there
must not be: the whole point is that you do not know what `Temperature` or
`Cursor: master hand` is going to do until you do it.

### How state works

- **Every setting is a `data-` attribute on `<html>` or a custom property, and
  the stylesheet does the work.** `data-theme`, `data-crt`, `data-flipped`,
  `data-gravity`, `data-difficulty`, `data-cursor`, `data-power`, `data-frozen`,
  plus `--dim`, `--zoom`, `--frost`, `--heat`. The script's whole job is to set
  the attribute and remember it, which is why you can drive any of them by hand
  in devtools and why a reload is seamless.
- **There is a second `<script>` in the `<head>`, and it is the only script on
  the page that is not at the bottom.** It reads `localStorage` and puts those
  attributes on `<html>` before the first paint. Without it a returning
  dark-mode visitor watches the page render white and then turn black — the
  exact flash **The font** below is about, reintroduced through the back door.
  It duplicates two things with the main module (the storage key
  `cgovind:settings`, and the defaults) **on purpose**: the alternative is the
  whole page waiting on the settings module.
- **`cookies` and `saver` are `transient: true` and are never written.** Both
  put themselves back to off the moment they finish, so there is no state to
  keep, and a stored "on" would mean a reload restarts one — a cookie burst on
  load would also be a silent jump-scare, since autoplay policy blocks the sound
  without a click. The head script therefore does not read them at all.
- **Every `localStorage` touch is wrapped.** It *throws* — not returns null — in
  a browser with site data blocked and in Safari private mode, so unwrapped it
  takes the whole page's script down. Wrapped, the panel degrades to "works,
  forgets".
- **The rows are built from one spec array**, not written out in the markup —
  key, label, default, control kind, and what it does, each named once. The
  array's order is the display order. Adding a thirteenth is one object plus, if
  it needs one, a CSS rule keyed on its attribute.
- **Everything that moves a tile gets its own CSS custom property**: `--fx` (the
  drift a floating tile gets), `--gy` (the row's lift), `--dx`/`--dy` (the
  difficulty dodge), `--lift` (hover), `--rot`, `--sc`. One shared `transform`
  would mean the last writer wins and the rest silently stop. **They are
  registered with `@property`** and that is load-bearing, not decoration: an
  unregistered custom property does not interpolate, so the tiles would teleport
  instead of dodging.
- **The transitions are on the variables, not on `transform`.** The bob animates
  `--lift` every frame; a transition on `transform` would spend its life chasing
  a value that has already moved, which reads as mush.
- **One pointer handler for the whole panel**, rAF-throttled: the dodge, the
  drawn cursor and the trail all want the mouse, and mousemove fires far more
  often than the screen redraws. On the default difficulty nothing dodges, so it
  does a couple of assignments and schedules no frame.

### The four control kinds

- **Switch** — a real `role="switch"` `<button>`, not a checkbox: it is drawn
  from nothing, so a checkbox would only mean hiding a native widget.
- **Segmented** (appearance, difficulty) — the highlight is **one element the
  script moves**, not a background on whichever button is selected: sliding one
  box is a transition, repainting three is a flicker. It can only be measured
  **once the popup is on screen** — a hidden pane is `display: none` and every
  offset reads 0 — so `paint` runs on open and on resize and must be idempotent.
- **Stepper** (`< value >`, zoom and cursor) — **showing one position at a time
  is the point**: you cannot see what the next one is until you land on it,
  which is why cursor is a stepper and difficulty is not. It wraps at both ends,
  so there is no dead arrow.
- **Slider** (brightness, temperature) — the one native element, because a range
  input is a range input. It listens on `input`, not `change`, so the page
  responds as the knob moves.

### What each one does

- **Appearance** — light/dark, the only honest preference. See **Dark**.
- **Brightness** — `--dim` on a full-page black layer, **capped at 0.88**. A page
  you can make genuinely black is a trap, not a joke.
- **Temperature** — a −100..100 slider whose track is a blue→white→red gradient.
  Cold snows (`620ms` between flakes at the first hint, `45ms` at the end — the
  ramp is what makes dragging it feel like weather rather than like switching
  something on), then frosts the edges from 60% on, then at >92% sets
  `data-frozen`, which pauses every animation on the page. **A frozen page never
  fires `animationend`**, so flakes are also swept on a timeout or they would
  never clean themselves up. Hot warms the room (`--heat`, a wash blended
  `multiply` on light and `screen` on dark, over the fire rather than under it)
  and then lights **the PlayStation Doom fire** on `#fire-layer`: the canonical
  37-colour palette, 5 screen pixels per fire pixel, `image-rendering: pixelated`.
  **Intensity is how hot the bottom row is held**, nothing else — turning it down
  makes the flames die out lower on their own, which is what the original did and
  is much better than cropping or fading a full-height fire. **The alpha ramp goes
  opaque within three steps** (`index * 110`): a gentle ramp leaves the low,
  dark-red indices half-transparent, and dark red at 25% over a white page is
  grey, so the flames read as smoke.
- **Low power mode** — greyscale plus everything crawling (5s animations, 0.9s
  transitions) plus a battery readout draining ~1% per 900ms. The `filter` goes
  on `<html>` because `body`'s is taken by CRT. Falling things are exempt: their
  timing is the joke. It **stops at 1%, never 0** — a page that has run out of
  battery and carried on is a worse joke than one that is permanently about to.
- **Zoom** — `zoom` on `.top, .tiles` only, never the root, so the panel you
  would use to undo it does not shrink with everything else.
- **Cursor** — seven positions; four draw their own picture and hide the real
  one (`invisible` hides it and draws nothing, `trail` and `default` keep it).
  `CURSORS` holds the hotspot as a fraction of the drawn size, because the
  height is unknown until the image loads. **Master hand's sprite points left**,
  so its hotspot is the leftmost fingertip, and it lags deliberately (`lag: 0.14`).
  **Flipped rotates `body` and the drawn cursor lives inside it**: a cursor
  placed at (a, b) appears at (W−a, H−b), so the coordinates are pre-inverted and
  the sprite gets an extra half-turn to come back up the right way — which costs
  no accuracy, because the origin is the hotspot.
- **Cookies** — rain, with **gravity acceleration, not constant velocity**
  (constant reads as drifting), and the switch returns to off once the last one
  lands. Emoji, so there is nothing to fetch. Scheduled even under reduced
  motion, where none are drawn, so the switch behaves the same either way.
- **CRT** — three layers plus a `filter` on the picture itself, because a tube is
  grainy, not just scanlined. The flicker is **not a smooth pulse**; a tube's
  brightness wanders.
- **Gravity** — off does not remove the tiles, it *floats* them. **The lift is on
  the two `.tilerow`s, not the ten tiles**, and by the distance the *top* row
  needs: lifting each tile to the ceiling individually puts six and four at the
  same height, interleaved into one heap, and strands `.rowlabel`, which is
  absolutely positioned against a row that never moved. The drift and tilt stay
  per-tile, and each gets a **negative animation delay** so ten tiles bob
  independently rather than pulsing as one object.
- **Flipped** — the transform goes on `body`. See the cursor note above.
- **Difficulty** — easy grows the tiles and leans them *toward* the cursor, hard
  shoves them away; **the sign is the entire difference**. Everything that
  measures a tile has to be redone when they physically move.
- **Screensaver** — enters immediately, and **any key or mouse move exits** back
  to exactly where you were. **The click that started it is itself an event**:
  without swallowing the mouseup, the very next mousemove closes it before
  anybody sees it and the switch looks broken.
- **Restore factory settings** — three presses that only change the label
  (`Are you sure?` → `really` → `absolutely`), then the real one: `#curtain`
  drops the screen to black, `restart.mp3` plays, storage is wiped and every
  control repainted from defaults, curtain up. **It does not reload** — a reload
  cuts the sound off.

### Things that must not move

- **The settings tile never dodges and gravity floats rather than throws.** The
  panel is the way back from every one of these; a setting you cannot reach the
  panel to undo is a locked door, not a joke. Same reason brightness stops at
  0.88 and `invisible` still leaves the arrows visible.

### The About panel

Ten rows, in the shape of a device's About screen. Four are the server's, from
**`/api/version` in `app.py`** (short commit, commit count, committer date,
`site/` byte total, and the Python/Flask string) — that endpoint shells out to
git once and caches, and returns live uptime on every call. The rest are the
client's: `Session` (counted from page load, which is always far larger than the
server's uptime), `Storage Used` (what this site has actually put on your
machine — the settings and nothing else, repainted on every write, so it grows
as you touch controls and drops to nothing when reset clears them), `Region`,
`Display`, `Browser`. **`Last Updated` is the exact instant in the visitor's own
zone**, which is what makes `Region` above it do some work. Uptime counts
*forward* from the one reading the server gave rather than being re-fetched.
Browser detection order matters: Edge and Opera both contain "Chrome", so the
most specific claimant is tested first.

### Assets (`site/assets/settings/`)

- `cookies.mp3` — the two binaural halves of one effect from Chinmay's sound
  library merged into a single stereo file: the left channel of the `_l_ear`
  render plus the right channel of the `_r_ear` one. They are a matched pair,
  not two sounds, so summing all four channels collapses the image instead of
  building it.
- `restart.mp3` — the Windows restart sound, for the factory reset.
- `dvd.png` — the favicon guy as an **alpha mask**, used as a CSS `mask-image`
  on a solid-coloured box: the screensaver changes colour on every bounce, and a
  `filter` cannot do that because the drawing is black and black has no hue to
  rotate. Its ground is thresholded to fully transparent and the generator
  watermark cropped off, or both show as a faint box on the black.
- `masterhand.png` — the Smash Bros sprite, background removed by flood-filling
  from the border and keeping the largest connected component (a colour
  threshold cannot work: the glove is white), then flipped to point left.
- `crosshair.svg`, `arrow.svg` — the two drawn cursors.

`prefers-reduced-motion` stops the cookies, the bob, the snow and the CRT
flicker. **The state each control sets is untouched** — only the animation.

## Dark

`html[data-theme="dark"]` and **nothing in that block is anything but `:root`** —
it redefines tokens and no selectors, so a rule added anywhere below inherits
the theme for free as long as it paints in a `var()`. First visit follows
`prefers-color-scheme`; the moment the control is touched, the stored value wins
and the OS is ignored.

- **Every colour on the page is a token now**, including the semi-transparent
  ones: `rgba(0, 0, 0, 0.12)` is a hairline on white and invisible on #101114,
  so `--hair`, `--wash`, `--wash-2`, `--faint` and `--thumb` all exist. Four
  literals are deliberately left: the modal backdrop and its shadow (a dimming
  layer over whatever is behind it), the blurred `.fit-frame` well, Spotify's
  green and the black triangle on it.
- **The tile accents are lifted, not inverted.** Poker's navy, ttr's brown,
  kot's purple and `--music`/`--settings` (literally `#000000`) were picked to
  read against white and are an invisible modal border on dark. They keep their
  hue and gain lightness, so a modal is still recognisably its own colour.
- **Nine of the ten tile icons already work on dark** — they are drawn with
  white fills. The resume is the one exception: pure black line art on a
  *transparent* page, so it gets `filter: invert(1)` in dark and nothing else
  does. A blanket invert wrecks the coloured ones.
- `color-scheme` is set on both, so the scrollbar and the pre-paint ground the
  browser draws match the parts the stylesheet owns.

## The font

The page is set entirely in xkcd Script, so how it loads *is* how the page loads.
It used to flash: every visitor, on every visit, saw a moment of Comic Sans before
it snapped into the right face. Three things caused that and all three are fixed —
if you touch one, know what the other two are doing.

- **The font was never cached.** `send_from_directory` defaults to
  `Cache-Control: no-cache`, which means "revalidate every time", so a returning
  visitor still paid a round trip to be told a 182KB file had not changed — and
  the page was drawn in the fallback until that 304 landed. `app.py` now serves
  anything under `fonts/` with a year's `max-age` (`_max_age()`), which is the
  single biggest part of the fix and the only one that helps repeat visits.
  **Nothing else on the site is cached like that**, deliberately: `index.html`
  under the same rule would take a year to update.
- **`font-display: block`, not `swap`.** `swap` is an instruction to paint the
  wrong font first. `block` holds the text invisible instead and paints once.
  `optional` is the trap: it never swaps in late, so one slow first load leaves
  the whole page in Comic Sans until a reload.
- **`<link rel="preload">` in the head**, because otherwise the font is only
  discovered after the stylesheet is parsed and something using it is laid out.
  It needs `crossorigin` even though the font is same-origin — fonts fetch in
  CORS mode, and a preload whose mode does not match the real request is
  discarded and fetched twice.

Measured on a throttled link (50KB/s, 400ms RTT) the text is correct at 1.5s
while the tile icons are still arriving; the preload is what puts the font ahead
of them. `.woff2` is the same font 23% smaller (182KB → 139KB); the `.woff` stays
beside it as the second `src` and is what `accounts/`, `ers/` and `kot/` still
use — **those three are still on `swap` and still ask for the `.woff`**, so they
flash the way this page used to. `drive/` is already `block`, for its own reason.

## Being found

- **`site/sitemap.xml` lists the landing page and nothing else**, which is now
  simply the truth rather than a policy: it briefly listed all twelve reachable
  pages, those pages were unlinked, Chinmay did not want them found, and in Aug
  2026 they were deleted outright instead of hidden. `robots.txt` disallows
  nothing any more for the same reason - a 404 says it better than a rule about a
  page that is not there. The sitemap is hand-kept, so `tests/test_seo.py`
  resolves every URL in it against the tree, fails on a rename, and fails if it
  ever lists something robots.txt disallows.
- **The four games cannot be in that sitemap and do not need to be.** A sitemap
  may only list URLs on its own host, so a `drive.cgovind.com` entry would
  invalidate the file. They are found the better way: the landing page links to
  all four, and Drive serves its own sitemap from its own host, generated from
  the track pool.
- **The `<h1>` is the welcome line; "hey!" is a `<p>`** (2026-08-17). They render
  exactly as before — the stylesheet's bare `h1` rule became `.hey` and both it
  and `.welcome` now state the `margin`/`font-weight` the browser default used to
  supply, so neither depends on which tag it happens to be. The swap is only for
  search: the `<h1>` is the heading weighed most, and this page's was a greeting
  containing neither Chinmay's name nor anything anybody types, while the name
  sat in the `<p>` one element below it.
- **`alternateName: "cgovind"` is in the JSON-LD** because the page never says
  that string as a name — only as the domain, the HackerOne handle and the email
  prefix — and "cgovind" is a query Chinmay expects to land here.
- **`<link rel="canonical">` on the landing page is the www fix.**
  `www.cgovind.com` and `cgovind.com` both answer 200 with no redirect between
  them, so a crawler sees two whole copies of the site. Doing it properly is an
  nginx redirect and **the deploy never touches nginx**, so the canonical settles
  which address is real without a hand-applied config change, and stays right if
  a redirect is ever added.
- **`chinmaygovind.github.io` now redirects here** (2026-08-14). It was live,
  ranking for Chinmay's name, and never mentioned this domain, which was the
  biggest single reason searching his name did not land on `cgovind.com`. It is
  a different repo: GitHub Pages serves its **`gh-pages` branch**, published
  from `public/` by `npm run deploy`, so the redirect had to be committed to
  both or the next deploy there would put the old site back. Pages cannot serve
  a 301, so it is a canonical plus a zero-delay meta refresh plus a
  `location.replace`. Its old pages are left on disk and dropped from the index
  with robots.txt — **but its root is deliberately still crawlable**, because a
  crawler that cannot fetch the redirect cannot follow it either.

## Conventions / gotchas

- **Links are relative** and assume `site/`-as-root; keep new ones that way. The
  only absolute paths left are `site/404.html`'s four `/audio/...` sounds, which
  are absolute so the game works whatever URL served it.
- **Nothing on `/` links to another page on this host.** Every tile opens a modal
  or points off-site (the game subdomains, the resume PDF, YouTube, PennToday).
  That was already true before the unlinked tree was deleted, and it is why
  deleting it cost nothing.
- This site was lifted from `chinmaygovind.github.io/public`. Dead
  Create-React-App references (`%PUBLIC_URL%`, `logo192.png`, `manifest.json`)
  were removed then; the rest of the inheritance went in Aug 2026.
