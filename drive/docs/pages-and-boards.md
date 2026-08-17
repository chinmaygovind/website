# Drive: the pages and the boards

Read this before changing the home page, `/solo` and its track switcher,
the track cards, `/account`, `/leaderboard`, the nav, or the in-game board panel.

- **The nav is two shapes, and the phone one is a tab bar.** `_nav.html` is a
  wordmark, the Discord invite, who you are, and the row of places
  (`.nav-right`). Above 620px that is one line of words. Below it the whole
  thing is more than a phone is wide - the five links alone are ~310px of text -
  so it becomes a brand row and, under it, `.nav-right` as a **grid with
  `grid-auto-flow: column`**: equal columns, icon over a small caps label, which
  fits five destinations across 320px and *cannot* wrap, because a single-row
  grid has nowhere to wrap to. It used to wrap as words, which is how a
  signed-in nav ended up three rows deep on a 390px screen with the row of
  places breaking in a different place at every width.
  Three things this asks of anybody editing the nav, each of which looks
  perfectly fine in a desktop browser while being broken on a phone:
  - **Only destinations go in `.nav-right`.** Anything else in there becomes a
    column of the tab bar. The name and rating used to live at the head of that
    row and now sit beside the wordmark instead.
  - **Every link in it carries an `.icn`** (`display: none` until the
    breakpoint). Without one it is a bald column.
  - **The brand row must not wrap**, so only the name may shrink, and it does it
    with `flex: 1 1 0` rather than a `min-width` - a *wrapping* flex row breaks
    the line before it shrinks anything, so a 30 character username sized by its
    content pushes the invite onto a row of its own. Sized from zero it never
    causes the break and ellipsises into what is left.

  `tests/test_app.py` pins the first two and the invite's two labels. Nothing
  can test the layout itself: there is no browser in CI, so **shoot the nav at
  320/360/390 before shipping a change to it**.
- **The home page is a headline, two doors and how to play.** "Race online!", then
  a red **Drive now** (`/solo`) beside a yellow **Race your friends** (`/lobbies`) -
  two halves of the game rather than a primary and a fallback, which is why the
  second one is a colour of its own rather than the white secondary. **They stay
  side by side on a phone** (`.cta`), because stacked they stop reading as a pair
  and start reading as a first choice and a second one. At 1.3rem they cannot
  share a 360px line, so below 620px they come down to 1rem and grow into the
  row. Not `.btn-grid.two`: equal columns would size both buttons to whatever
  "Race your friends" needs, and half a 320px screen is not enough for it at any
  size worth tapping. There is no
  grey standfirst under the headline: it restated the three paragraphs below it.
  Those are one each - what a run is, what Solo is, what Multiplayer is - and the
  track cards follow, so the page is read once and clicked from thereafter.
- **Solo is `/solo`, and the track is something you change from inside it.** There is
  no "pick a track" page any more: `/solo` opens whatever you were last driving (kept
  in the session, so the first paint is right) and the **track switcher** - the map
  icon, top right - swaps the world in place. `/solo/<slug>`
  still works for links and bookmarks and records itself as your last track; switching
  in-game posts to `/api/last-track` so coming back lands where you left off.
  **Everything that names the track has to follow the switcher**, and for a long
  time none of it did: you arrived from the home page on `/solo/<slug>`, changed
  track, and the leaderboard button still went to the board for the track you
  arrived on. `loadTrack` now repoints every `.board-link`, the page title and the
  name on the corner card, and `switchTrack` rewrites the URL with `history.replaceState`
  (not `pushState` - a switch is a setting inside one session, not somewhere to go
  Back out of; the query string is dropped because `?ghost=`/`?watch=` name a lap on
  the track you just left). **A room's URL is left alone** - it is the join code and
  has nothing to do with the current track. The same
  switcher is in a room, where only the host can pick - everyone else sees the same
  grid with the picking turned off, rather than a poorer version of it.
  **A card shows your time and not the record.** The record was on there too, and it
  made every card an argument: two times and two names, one of them somebody else's,
  on a menu whose only job is choosing where to drive. `_track_cards` therefore does
  not even send it. It is still on the board and the home page, which are for reading
  rather than picking.
- **A switch has to carry the track's scenery with it, and for a long time it did
  not.** `tracks/<slug>/scenery.js` registers itself on `globalThis.DRIVE_SCENERY`
  and the play page inlines it - for the track you *arrive* on, and only that one.
  `switchTrack` fetched the payload and built straight from it, so switching to the
  Costco built a warehouse with no walls and switching to Mount Joy built a road with
  no mountain and, since it declares `ground = None`, nothing under it at all. **Not
  a cosmetic difference**: those are 2834 and 14744 collider triangles, most of each
  track's solid geometry, so the lap you then drove was a lap on a different track
  and it went to `/api/run` as a time on this one. It hit rooms hardest - the host
  picking the Costco broke it for everybody, since `track_change` lands in the same
  function. The fix is `ensureScenery` in game.js against `/scenery/<slug>.js`
  (`track_scenery` in app.py), fetched **in parallel with** the payload rather than
  after it: the `scenery` flag rides down with `summaries()`, so the switcher knows
  before the click. **A scenery it cannot get abandons the switch** rather than
  building without it, and the payload's own flag is re-checked after the fetch so a
  stale card list cannot skip the load silently. `test_the_scenery_flag_and_the_
  scenery_url_agree` is what holds the two halves together.
- **The sheet stays open until the new world is up.** It used to close on the click,
  which left you looking at the track you were trying to leave for as long as the
  switch took - and on Mount Joy or the Costco that is a request plus several hundred
  milliseconds of *synchronous* `buildTrack`, during which the page cannot paint at
  all. The honest reading of that screen is that the click did not land, which is
  what "the picker is slow" turned out to mean. Now the card you pressed carries a
  `Loading` badge in the same corner as `Now`, `.tgrid.busy` dims the rest and stops
  it taking clicks, and the sheet closes at the moment there is something new behind
  it; a failed switch leaves it open, because the next thing you want is to pick
  something else. `switchTrack` waits a **double `requestAnimationFrame`** after the
  network and before the build - without it a warm cache goes from click to frozen
  frame with the badge never drawn. In a room the host's sheet still closes on the
  click, because the room answers for everybody at once over `track_change`; that
  path and the join path pass `quiet: false` and get a toast instead, since nothing
  else on their screen would explain the pause.
- **The switcher's cards are photographs, not diagrams.** `tools/shoot_tracks.py`
  drives headless Chrome over every track with `?shot=1` (`S.shot` in game.js: HUD off,
  car hidden, camera behind the start line) and writes `static/img/tracks/<slug>.png`;
  the home page uses the same set. **Re-run it after changing a track's geometry
  or sky** - a test asserts the files exist but nothing can notice that one is stale.
  **It must run on ANGLE's software GL** (`--use-gl=angle --use-angle=swiftshader`),
  which is what `GL_FLAGS` is for: plain `--use-gl=swiftshader` is *rejected* by
  current Chrome rather than ignored, the GPU process dies, and Chrome still
  writes a PNG - of a half-built frame, which in practice was a photograph of
  some other track. Nothing downstream can tell a wrong picture from a right one,
  so this is the worst failure the tool has. The same flags are what to use for
  any by-hand screenshot check.
  Fitting the *whole* track in frame was tried first and is much worse: from far enough
  back to hold a point-to-point the road is a thread, and on Jump City it vanished into
  the towers entirely. Aiming level from 40 units up fails the same way - it photographs
  the horizon. Behind the start line, angled down at the road, is the shot.
- **`/account` is two boxes and the second one is a table.** It was nine bordered
  stat tiles in a grid plus a tenth panel for the medal tally, which made ten pieces
  of furniture out of one thing - who you are and what you have done. Now one
  `.panel.profile` holds the figures (no border each; the panel is already the
  border) with the three medal counts under a hairline in the same box, since they
  are three more of the same kind of number. The standalone "Medals" total went with
  the redesign - it was the sum of three numbers sitting an inch below it. The track
  table uses `table-layout: fixed` with a `<colgroup>`, because on a 1080px page an
  auto table hands all the slack to the column that wants it least (the track name,
  two short words); under 700px it switches to auto with a `min-width` and scrolls
  inside `.tablewrap` rather than crushing six columns. The medal column carries the
  word as well as the swatch, and the row actions are icon+label buttons - a steering
  wheel for **Play** and a podium for **Leaderboard**, which used to read "drive" and
  "board" and nobody knew what a board was. Icons are inline SVG (`.icn`), never
  glyphs, for the reason the in-game ones are. **The rows are in the pool's
  order**, the same one the switcher, the home page and the leaderboard use.
  They used to be most-recent-PB first with the never-finished tracks in a
  block underneath, so the same track moved every time you drove and no two
  pages agreed on where to look for it; a track you started and never finished
  now sits in its own place in the list, muted and without a time or a medal.
- **A name on a board opens that driver's Drive page, and that page is the way
  out to the rest of the site.** `_player.html` used to link straight to
  `cgovind.com/accounts/<username>`, which is the right page for "who is this
  across four games" and the wrong one for the question a lap time actually
  raises, which is how they go round *here*. So it points at `/account/
  <username>` - the same page as your own, public, no login - and that page
  carries one link on to the shared profile (`.elsewhere`, the only link on it
  that leaves Drive). It rides on the **end of the rating line** rather than a
  line of its own, because it is who this is and that line already says so; a
  row to itself made a one-link paragraph out of a page whose next line is a
  panel. There is no standfirst under it either - "all four games, in one
  place" restated the destination the link already names. Three things fall out
  of making the page public: your own name redirects to plain `/account`, so
  there is one address for your own record
  rather than a second copy of it that quietly cannot be edited; the nav's
  "Account" tab only lights on your own; and `_stats(user, create=False)` hands
  back an unattached row for a stranger, since the creating version would leave
  a `drive_stats` row behind for every account a passer-by ever looked at.
  `tests/test_no_drift.py` checks *both* halves - the board links by username,
  and Drive's account page still links on - because the second one is now the
  only route from a Drive leaderboard to the shared profile.
- **`/leaderboard`'s track table is dated, not gold-timed.** The gold time used to be
  the fourth column; it is a property of the track rather than of the record, it is
  already on the track page and in the game, and sitting next to somebody's name it
  read as though they had won a gold rather than set the fastest lap on the site.
  `_records()` now carries the holder's `updated_at` (which is when *that lap* was
  set, since a better run replaces the row wholesale and stamps it). It is stored and
  rendered as UTC so the page is right with no JS, then rewritten into the reader's
  own timezone by the script at the foot of the template.
- **`/leaderboard` is three boards, named for what they rank**: **Track Records**,
  **Time Trials Leaderboard**, **Multiplayer Leaderboard**. The last was "Race
  ratings" and was the only heading on the page carrying a line of explanation
  under it; three boards on one page are a set, and one of them dressed
  differently reads as a different kind of thing, so none of them has a subtitle
  now. **Every column heading on a `table.board` is the display face**, which it
  was not: `th.num` was handed `var(--mono)` along with the cells under it, so a
  heading row came out in two fonts with the left-hand labels looking pasted in
  from another table. The cells keep mono, where it does the work - figures line
  up under each other. `.acct-tracks` had already undone this for itself; that
  override is gone, since the fix is now in the one rule.
- **The Time Trial Score is golf scoring: your placing on every track in the
  pool, added up**, so low is good and a clean sweep scores one per track -
  fourteen today. Eleven firsts and two thirds is 17. Three rules make the sum well defined, all of them
  in `_time_trial_board`. A **tie shares a place**, the answer `_my_rank_map`
  already gives for one track (strictly faster, plus one). A **track never driven
  counts as one worse than last on it** - the place you would take by turning up
  and being slowest - because adding up only the tracks somebody *has* driven
  makes driving fewer of them the way to a better score, and one lonely first
  place would beat a full sweep; the `Tracks` column (`9/12`) is what keeps a big
  score from being a mystery. And it is **derived on every render and stored
  nowhere**: a personal best does not only change your own score, it demotes
  everybody it overtook, so a number kept per driver would have to rewrite most
  of the board on every lap and would be wrong for as long as one write path was
  missed. The whole pool is one query. Bots and accounts with no times are off it
  (the join is what drops them), and since only laps driven alone are in
  `drive_times` at all, nothing set in a room reaches this board either.
  **The `Score` heading explains itself where it stands** - a dotted rule, a
  raised `?` and a `title` (`.whatsthis`) - rather than the board carrying a
  line of small print neither of the other two has, which is the thing the
  multiplayer board just had taken away. A `title` because that is how every
  hover on Drive works, from the HUD buttons to the record dates: one
  convention, no script. Its limit is the usual one - a `title` does nothing on
  a touchscreen - which is why the mark sits next to a column whose figures are
  still ordered top to bottom, and is not the only place the rule is written
  down.
- **A lap is shareable, and the link is one that already existed.** The finish
  sheet's **Share** button hands over `/solo/<slug>?watch=<id>` - the same URL the
  public board has always used to hand a lap to the game, so there is no new kind
  of page behind it and `openRequestedLap` does the rest. The id comes back from
  `/api/run` as `time_id`, and it is the **row's** id rather than that run's:
  `drive_times` keeps one row per player per track, so the only shareable solo lap
  anybody has is their best one. `navigator.share` on a phone, the clipboard
  everywhere else. Three things fall out of it. The button is **solo only** - a
  room lap never reaches the board, so there would be nothing to point at - and it
  is rendered **disabled** rather than added when the answer arrives, because the
  sheet is drawn the instant you cross the line and a button that appears late
  moves the row under a finger already going for Retry. A **guest** has no row and
  so no lap, which makes this the one screen where an account buys something
  immediate: the button says *Log in to share* rather than going grey. And
  `?panel=finish` opens the sheet without driving a lap, the same way `?panel=`
  reaches every other panel.
- **What a link unfurls into is decided in Python, not in a Jinja block.**
  `og_title`, `og_description` and `og_image` are context variables with defaults
  in `inject_globals` (the site's one-liner and the wheel); `_track_og()` passes a
  track's own card and title over them on `/solo/<slug>` and `/track/<slug>`, and
  when the URL names a lap, the time and whose it is. `_shared_lap` is what
  resolves `?watch=`, and it insists on a row **on this track** that **has a
  replay** - the first for the reason `/api/ghost` scopes it, the second because a
  card promising a lap that then toasts "that lap is no longer there" is worse
  than the generic one. **It deliberately leaves `og_description` alone for a bare
  track link**, so the site's one-liner stands: a track used to declare a
  one-line description and this passed it over that default, and with the field
  gone the honest answer is the default rather than a sentence assembled out of
  the difficulty and the gold time.
- **The board is in the game.** "View others" opens the leaderboard over the track;
  clicking a row opens that lap - its checkpoint splits against your own PB's, who set
  it, and **Watch it** / **Race this ghost**. Picking somebody to chase is something you
  do between runs on the track you are already on, so leaving the page for it would be
  the wrong shape. The public `/track/<slug>` page opens a lap the same way and links
  back in with `?ghost=<id>` / `?watch=<id>`; `/api/board` carries each row's id and
  splits so no second request is needed, and `/api/ghost/<slug>?who=<id>` serves one
  lap, **scoped to the track that asked** so a replay cannot be played against geometry
  it was never driven on.
