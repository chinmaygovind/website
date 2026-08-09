# Drive: the pages and the boards

Read this before changing the home page, `/solo` and its track switcher,
the track cards, `/account`, `/leaderboard`, or the in-game board panel.

- **The home page is a headline, two doors and how to play.** "Race online!", then
  a red **Drive now** (`/solo`) beside a yellow **Race your friends** (`/lobbies`) -
  two halves of the game rather than a primary and a fallback, which is why the
  second one is a colour of its own rather than the white secondary. There is no
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
  help sheet's blurb, and `switchTrack` rewrites the URL with `history.replaceState`
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
  thirteen today. Eleven firsts and two thirds is 17. Three rules make the sum well defined, all of them
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
- **The board is in the game.** "View others" opens the leaderboard over the track;
  clicking a row opens that lap - its checkpoint splits against your own PB's, who set
  it, and **Watch it** / **Race this ghost**. Picking somebody to chase is something you
  do between runs on the track you are already on, so leaving the page for it would be
  the wrong shape. The public `/track/<slug>` page opens a lap the same way and links
  back in with `?ghost=<id>` / `?watch=<id>`; `/api/board` carries each row's id and
  splits so no second request is needed, and `/api/ghost/<slug>?who=<id>` serves one
  lap, **scoped to the track that asked** so a replay cannot be played against geometry
  it was never driven on.
