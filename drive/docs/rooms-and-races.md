# Drive: rooms, races and replays

Read this before changing the room phase machine, qualifying, the grid,
ELO, socket handlers, the race recorder or `/race/<id>`.

- **A room has its own anti-cheat, and it is a different question from the
  board's.** `racecheck.py`, and its preamble is the long version. The short
  one: `runcheck.validate` asks whether a submitted replay is self-consistent
  and `verify.py` re-drives it through the real `Car.step` to ask whether *this
  car* drove it - both of which need a whole lap in one POST, and the second of
  which needs the input stream. A race carries neither. What a room has instead
  is a live 30Hz stream of client-authoritative poses, and the question that
  allows is smaller: could the car have got from where it said it was to where
  it now says it is, and did the race stay anywhere near the road.
  - **The hole this closed was not subtle.** Every field of `on_pose` arrived
    unchecked, including the two the *server* then decided things from. `prog`
    orders the standings and was the only real tooth in `_finish_is_possible` -
    so `emit('pose', {prog: 99999})`, wait out the physics floor, `emit('finish')`
    was a win, its ELO, its win tally, its podium and its `checkers` badge,
    with the car never driven. The floor and the clock bound were doing nothing
    on their own, because the check they were guarding read a number the same
    client had just made up. `_finish_is_possible` now reads the server's own
    projection of where the car has been.
  - **The failure mode is the design.** A race is not a leaderboard - nothing
    set in a room reaches the board - so the stake is ELO, the tallies, the
    badges over them and everybody else's afternoon. That flips which mistake is
    expensive: refusing an honest lap costs a record, but penalising an honest
    driver costs them a race they are in the middle of. So a pose that fails is
    **dropped, not punished** - the car keeps the last position the server
    believed, which looks like a moment of rubber-banding - and only a car that
    fails steadily (`STRIKE_LIMIT`, twelve) loses anything.
  - **The budget is a bucket, and that is the whole reason it works.** The
    obvious rule - a step may not exceed `SPEED_CEIL` times the gap between two
    poses - does not survive a network: `dt` is measured on *arrival*, so two
    poses sent 33ms apart routinely land 5ms apart and that honest pair reads as
    six times the speed limit. Distance is spent from an allowance instead,
    refilled at `SPEED_CEIL` and capped at `BUCKET_MAX_S`. Jitter cancels,
    because it is jitter; a car genuinely going too fast drains it and keeps
    draining it. The cap is the other half - without it a car banks ten seconds
    of standing still and spends it on one hop to the line.
  - **`FLAG.RESPAWN` cannot buy a free teleport**, or setting one bit in a
    payload the client already writes *is* the cheat. A respawn is allowed
    because it is a real jump, but only to the grid or a checkpoint, and only
    one the car has **already reached** - measured by the server's own progress
    rather than by the car's `cp`, which is a client number: read off `cp`,
    `{cp: 99, flags: RESPAWN}` was a legal jump to the last gate on the track.
  - **`Watcher.prog` is monotone, and `_go_green` therefore has to reset it.**
    It must be monotone or a car that rolled backwards over its own line would
    be refused its finish; but that means a qualifying lap's progress is still
    sitting there when the lights go out, and the first finish claim of the race
    would be waved through on a lap driven before it. `_reset_race` clears them
    too, which is what covers a track change - a new track is a different ribbon,
    so a carried-over station hint measures a line the car is not on.
  - **The expensive half runs once, at the flag** (`racecheck.scan_race`), over
    the trace `_record_race` already samples off the server's own clock. No
    client sends anything new for it and there is no arrival jitter in it, which
    is what makes two things affordable that the live half cannot ask: a whole
    race's **median** frame-to-frame speed, which a cheat cannot sit underneath
    the way it can a single-frame ceiling, and the corridor over every frame
    rather than every fifth one.
  - **The verdict is silent and rating-shaped.** A flagged car keeps its place
    in the standings, nobody in the room is told, and what it loses is the
    rating - `_rate_race` skips it through the very same door a guest goes
    through, so beating one gains nothing either. Announcing it would put the
    server in the middle of an argument it cannot referee on evidence
    deliberately calibrated to be wrong in the harmless direction, and kicking
    on it would let a false positive end somebody's afternoon. The finding goes
    to `drive_cheat_flags`, which **nothing in Drive reads** - it is written for
    an admin page that does not exist yet, and that is its intended state.
  - **What it cannot do**, said plainly: it does not decide a *person* drove,
    and it cannot see a slightly richer engine. That is the class `verify.py`
    exists for and it needs the input stream. Carrying one through a live race
    would mean a new wire format, seconds of subprocess CPU per car, and a
    verdict that lands after the results sheet - so ELO would have to become
    provisional and revocable. Deliberately not done: the cheat that ruins a
    room is the visible one.
  - `on_qual_time` gets the corridor pass too, on the **pole lap only**. That
    replay is the one ghost a whole qualifying session chases, so a fabricated
    one is a car nobody can follow cutting a corner that is not there, with
    every driver in the room aiming at it. The gate and clock halves of
    `runcheck.validate` want splits a qualifying lap does not send. The grid
    slot itself is left on the physics floor it already had - the grid is not
    rated, and the pose checks are the real defence during the session.
  - **`_hot_track` exists because `_room_track` is a database query** and says
    so: it is for paths that run once per car per race, and `on_pose` is thirty
    times a second per car. So the answer is memoised on the room and dropped by
    `on_set_track`, the one handler that can change it. That is the second
    source of truth `_room_track` avoided; what makes it safe is that it is
    derived and single-writer, so a miss just re-queries.

- **A race is recorded off those same poses, and the recording outlives the
  room.** `_record_race` runs on the broadcast tick and writes one frame per car
  per `1/REPLAY_HZ` from the green light, so frame *n* of every car is the same
  instant and the whole thing plays back as one moment in time; a car that has
  stopped reporting repeats its last pose rather than leaving a hole, because a
  hole slides every frame after it and slews that car against everybody else's.
  It lands in **`drive_races`**, its own table - `drive_games` rows are deleted
  the moment a room empties or goes idle, which is right for a room and wrong
  for a replay, and a new table arrives on the live database by itself where a
  new column would need a migration. Each car's frames are packed exactly the
  way a ghost is, at the same rate and with the same flag byte, so a replay is
  not a new format: it is several ghosts sharing a clock. The newest
  `REPLAY_KEEP` are kept and the sweep drops the rest.
- **`/race/<id>` is the play page in a third mode.** A replay is a track, a set
  of cars and a clock, and the play page is the only thing that knows how to
  draw those - so `startReplay` generalises the single-lap watcher to N cars
  with one of them holding the camera, and the bar along the bottom is the
  drivers, clickable. The cars are fetched from `/api/race/<id>` rather than
  rendered into the page: eight replays of a two-minute race is most of a
  megabyte of numbers. It is offered from the results sheet (**Watch replay**),
  it is a plain URL, and it is public, so a race can be linked to afterwards.
- **The way out of a replay is the way back into the room**, when there is one.
  Watching your own race used to cost you the room you were racing in: both exits
  went to the lobby list, or to Drive's home page. You were never actually out of
  it - leaving a room's page is a socket disconnect and the *soft* kind, so the
  car comes off the road and the seat stays in the database - so `_seated_room`
  looks the seat up, the buttons say **Back to room**, and `on_join_room` clears
  the `gone` mark on the way in. Told by the seat rather than by `drive_races.code`
  or a query param, because codes are recycled once a room is swept and a seat
  resolves to the room that actually exists. `None` for somebody in no room (a
  shared link, the lobby list) and the buttons fall back to what they did before.
  If the room went while they were watching, `/room/<code>` sends them on to the
  lobby list by itself, which is why nothing here checks twice - a second opinion
  would be out of date by the time the page loaded.
- **R is two presses mid-race and one everywhere else.** R is next to T, T is the
  key you reach for the instant you fall off, and in a race the lap you are on is
  the only one you get - so one stray press put you back on the grid with the
  field gone. The first press arms and toasts, the second restarts, and it
  expires after `ARM_MS` so two accidents a corner apart are two accidents rather
  than a confirmation. `restartCostsARace()` is the gate and it is the race and
  nothing else, for the reason `catchupOn` gives about the same phase: free
  practice and solo are *nothing but* restarting, and a qualifying lap thrown
  away is one of the two or three that ninety seconds holds, so being asked would
  be in the way. The state is not the button's - R, the HUD button and the touch
  button are three doors into one rule and only one of them is under a cursor -
  but both buttons show it, since on a phone the pulse is the only thing that
  says the first tap landed once the toast has gone.
- **A room is a phase machine, and every way out of a phase is guarded.** The
  phases are `free` -> `qual_countdown` (5s) -> `qualifying` (90s) ->
  `countdown` (5s) -> `racing` -> `results` -> `free`, with the two qualifying
  phases skipped entirely when the host has switched qualifying off.
  **A race must end**, and for a long time one could not:
  the only thing that armed the finish clock was somebody *finishing*
  (`FINISH_GRACE_MS`), so a race nobody finished never ended, and the room sat
  in `racing` for ever with the host unable to start another or change track -
  `set_track` and `start_race` both refuse mid-race, correctly, which is why
  the hang presented as "the host can't do anything". There are now four
  independent ways out, and `_maybe_close` is called from *every* path that can
  empty the road (finish, resign, disconnect, kick) rather than from the finish
  alone: "the last car is in" is not something only finishing can cause. Behind
  all of them is `_hard_race_ms` (8x a gold lap, clamped), which depends on
  nobody doing anything. **Every deferred close carries the `race_seq` it was
  armed for**, so a timer from one race can never close the next - which is
  live, because Rematch can fire inside the twelve seconds the results sheet is
  up.
- **Leaving mid-race is a DNF, not a disappearance.** `_drop` used to delete
  the car, and with it the loss, so the cheapest way to protect a rating was to
  close the tab - the one thing a rating system must never make the smart move.
  The car is now marked `gone` (excluded from `_snapshot` and `_live`, so it
  stops being drawn and stops holding the race open) but kept, so it is still
  in the standings and still rated. `_reset_race` is what finally drops it.
- **Every socket handler takes `data=None`.** Not a style choice: every button
  that leaves a room emits `leave` with no payload, so Socket.IO called
  `on_leave(data)` with no arguments and it raised before doing anything -
  pressing Leave took you to the lobbies page and left your name in the room
  behind you until the sweep noticed. They all already cope with `(data or {})`,
  so the default costs nothing and makes a payload-less emit a non-event rather
  than a line in the log.
- **Two buttons for the two ways a race stops early**, both top centre with
  Start race, because they are the same kind of decision: start this, stop
  this, get out of this. Anyone can **Resign** (only while there is a race to
  resign from): a DNF, rated as one,
  and you drop straight back into practice without leaving the room. The host
  gets **End race**, which is a *cancellation*
  before the lights - `_abort_race`, nothing recorded - and the chequered flag
  after them, freezing the standings and rating them normally. Both arm on the
  first press and fire on the second, in place: they happen mid-drive, one
  press from the settings icon, and an "are you sure" overlay would cover the
  race you want to look at before answering it.
- **The grid is set by a 90-second qualifying session**, not by name. It was
  `sorted(fresh, key=name)`, which is both arbitrary *and stable* - so the same
  person started on pole every single race. Qualifying is ordinary practice
  with a clock on it: `qual_time` per improved lap, best one counts, a lap
  finishes into a toast and an automatic restart rather than the results sheet
  (covering the road while there are seconds left to improve is taking the
  session away). That automatic restart is cancelled by any restart of your
  own - `resetToStart` clears the timer - or it threw away the lap you had
  already begun a second later, which looked like the game restarting you at
  random. No lap at all means the back of the grid, shuffled. The host's Start
  race means "open qualifying" in `free` and "go now" during it, so ninety
  seconds never traps four people who are ready, and **Enter** is that button
  on the keyboard.
- **Qualifying starts on lights, like the race does.** `qual_countdown` is five
  seconds with the same overlay, the same sounds and the cars held still. It
  used to simply begin, so the first anyone knew of it was a toast saying they
  were already in it and a lap in progress that no longer counted. Nobody is
  *placed* for it, though: a session has no start line - everyone leaves when
  they like, on their own lap - so it counts down over wherever you are sitting.
- **Qualifying is off by default, and then the grid is the last race
  reversed.** It is the room's one setting so far (`ROOM_DEFAULTS`) and it lives
  in the live room state rather than on `DriveGame`: it is
  about the next few minutes, and `create_all` makes tables and not columns, so
  a column would need a hand migration on the live database for something a room
  forgets anyway. With it off, `_open_race` sends the room straight to
  `countdown` and the order comes from `_reverse_grid` - whoever was beaten
  starts ahead of whoever beat them, which is the arbitrary ordering that is at
  least *about* the racing, so a room of mixed ability keeps having close races
  instead of one procession after another. Anyone who was not in that race lines
  up behind it, shuffled, and a room's first race is shuffled entirely. The host
  moves the switch from the room drawer, the server refuses it mid-session
  (`LIVE_PHASES`, same as the track), and the whole set is fanned back out as
  `room_settings` so nobody is reading a switch that says something different
  from the host's. **It defaults off** because a session is ninety seconds plus
  five of lights before anybody races, which is longer than some of the races,
  and a room that has just filled up wants to be on the grid rather than
  spending its first two minutes alone on the road; a host who wants the grid
  earned turns it on. The client's own `S.settings` starts off to match, so the
  switch is not drawn one way and corrected by the first `room_settings`.
- **The grid is staggered and pole starts on the inside of the first corner.**
  Ordering alone does not fix a two-by-two grid: cars level with each other
  reach the first corner together and the one on the inside of it simply gets
  there. The stagger deals with "at the same instant" - the odd slot of each row
  sits back 2.4 units, F1 style. The side used to be dealt with by alternating
  it every race, on the grounds that nothing knew which way the track turned
  first, which meant half the time the car that qualified fastest lined up on
  the *outside* of turn one and lost the place it had earned. The track knows
  perfectly well: `tracks.pole_side` integrates the ribbon's own `curv` from the
  start line until the heading has committed one way (`FIRST_TURN_DEG`), and a
  loop contributes nothing to it because a loop is pitch rather than yaw. So
  pole gets that side, every race, on every track, and `flip` is gone. Pole
  keeps its advantage; it was earned, and taking it away would make earning it
  pointless.
- **A split delta is measured against whatever that session is about**, which
  is three different laps - `splitRef` is the only thing that decides, and it
  returns null rather than comparing with the wrong one. **Racing: the
  leader**, specifically the quickest anybody *else* reached that checkpoint,
  which is by definition whoever led on the road at that point; if that is
  you, the same number read backwards is your gap to the nearest rival. Each
  client emits `split` and the server fans it straight back out rather than
  accumulating a table, because "the quickest anybody else" is a different
  number for every car and the server would have to send a different message
  per client. **Qualifying: your own best lap of the session**, kept whole as
  `qualRef` (a `lapTimeline`, the same distance-against-time table the ghost
  uses) rather than as a time, since a split needs the reference lap's shape.
  **Free practice: the ghost**, as before. The finish is the last split and
  follows the same rule.
- **The running order is settled off the snapshot, because that is the one
  clock everybody shares.** `liveOrder` used to compare **your own distance right
  now against everybody else's from a round trip ago** - `S.run.bestS` live
  against each rival's `prog` as it last arrived. At 60ms of ping that is about
  three units of road, always in the reader's favour and mirrored on the other
  screen, so two cars side by side were each shown leading on their own monitor:
  the board saying the opposite of the board next to it, with nothing to say
  which had it right. The fix is not a better estimate, it is **one instant**.
  The snapshot carries every car - *including the reader's own*, which `onPoses`
  otherwise skips - each with the server's copy of its progress and its own age,
  so `orderFromSnapshot` walks each forward by that age and sorts the field at
  `snap.t`. Every browser is handed the same bytes and does the same arithmetic,
  so every browser reaches the same order, and the test that matters is not that
  some car leads but that **two readers of one snapshot agree**.
  - **Your own row goes stale with everyone else's, and that is the point.** A
    gap is a difference, so what it needs is one clock rather than the freshest
    possible number on each side; being the only car on the board reading itself
    live is exactly what made the two boards disagree.
  - **Derived from the message rather than sent alongside it.** The server could
    fan out a finished list, but the same packet already carries the progress
    and the age it would be computed from, so a list would be a second statement
    of it and the interesting question would become which to believe when they
    differed. This is the `_hot_track` rule from the other direction: derived and
    single-writer, so a stale one is a miss and never a contradiction.
  - **It projects on the pose age and never on the upstream leg beside it.**
    Field 15 is the trip in, and it is a number the car being ranked reported
    about itself (see `docs/racing-physics.md`). The drawing adds the two; this
    must not, or overstating your own ping is worth four units of projected road
    on everybody's board.
  - **Ties break by pid, not by enumeration order.** `prog` is rounded to 0.1 on
    the wire, so two cars genuinely abreast do reach the client tied - and that
    is the one case the whole change exists for, so it cannot be left to
    whichever way each browser happened to walk the object.
  - Finishers still sort ahead of the field by lap time, ordered by `ms` from
    `S.standings`: progress orders the road, a lap time orders the result, and a
    car already home has left the road. Solo and a replay have no snapshot, so
    `S.order` is empty there and every line falls back to what it did before.
  - **What this does *not* touch is who won.** `on_finish` sorts by the client's
    own `ms`, so the result was never decided by who claimed it first and is not
    decided by any of this either.
- **The qualifying board is top right with the standings**, not top centre:
  it is the same kind of thing they are - who is where - and top centre is for
  the one button the room is waiting on, which a board above it pushed down
  into the road. The live standings are hidden during qualifying, since
  running order by distance means nothing when everyone is on their own lap
  and the board below already lists the same people in the order that counts.
- **On a phone the top-right stack does not slide out from under the drawer.**
  It does on a desktop, where the drawer is a 300px column. On a phone the
  drawer is most of the screen and hides the driving controls while it is
  open, so there is nothing left underneath to keep reachable, and sliding it
  only walked the icons into the top-centre buttons on the way past.
- **Guests are invisible to ELO.** They are in the room, on the grid and in the
  standings, but `_rate_race` ranks the logged-in players *among themselves*:
  beating a guest gains nothing, losing to one costs nothing. Anything else is
  a rating anybody can move by opening a second tab. The win and podium tallies
  were read off the overall standings, so a guest winning meant nobody was
  recorded as having won and a guest in the top three pushed an account off its
  own podium; they follow the rated order now, and retiring is never a win.
  **Two DNFs draw** (0.5), because their order is whichever they happened to
  give up in. Still needs two accounts - one has nobody to be rated against,
  and its race count no longer creeps up on races that were never rated.
- `?panel=qcount|qual|racing|result` pins a phase and fakes a session, for the
  same reason the other `?panel=` values exist: none of them is a panel you can
  open, and getting a room into any of them takes two browsers, a stopwatch and
  somebody willing to lose a race. Pinned rather than assigned - the room
  reports `free` the moment the socket connects, so a phase merely set at boot
  is gone before the shutter. **`racing` pins a field as well as the phase**, and
  it has to: the position card and the standings are shown when there are rivals
  on the road rather than when the phase says `racing`, so a pinned race drew
  neither of the two things that phase is *for* - and that is how the minimap
  came to be sitting on top of the position card on every phone with nobody able
  to photograph it. `S.previewOrder` is six cars, the same trick `qual` already
  used with `renderQual`, and `hud` reads it in place of `liveOrder()`.
- **The room drawer holds the invitation.** A share field with
  `<origin>/j/<CODE>` in it and a copy button, and `/j/<CODE>` joins whoever
  opens it - asking for a login or a guest name first if they have none. The
  link opens a *private* room without its passcode: the passcode is there to
  keep a room out of a stranger's hands and a stranger does not have the link.
  The field is readable as well as copyable, because the clipboard needs a
  permission the browser can refuse and a link you can read off the screen
  cannot fail. The URL is built from `location.origin` in the browser rather
  than from `request.url_root`, which is http on a laptop and does not
  necessarily know it is https behind nginx.
- **The results sheet is five equal buttons**: Practice, Watch replay, Change
  track (host), Rematch (host), Quit - Quit last, because leaving is the last
  thing to offer. One size for all of them, wrapping rather than shrinking, and
  `auto-fit` columns so the three a non-host sees fill the row instead of
  leaving two holes where somebody else's buttons would be. The top-centre race
  buttons are one size as well now: they are the same kind of decision taken at
  the same moment, and a row of three heights read as three unrelated controls.

