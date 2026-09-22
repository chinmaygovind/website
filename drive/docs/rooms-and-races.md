# Drive: rooms, races and replays

Read this before changing the room phase machine, qualifying, the grid,
items, ELO, socket handlers, the race recorder or `/race/<id>`.

**If somebody says they were disconnected, read the deploy section of
`drive/CLAUDE.md` first.** Three different things have caused it and none of
them is visible from inside a room: the box OOM-killing the worker, a deploy
restarting the service under a live race, and the event loop stalling long
enough that every client timed the server out at once. The last one left no
trace at all until `_hub_watchdog` was written; it logs `event loop stalled`
with how late it was and what the rooms were doing.

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
- **`race_green` carries the grid, and that is the one fact the room states
  twice on purpose.** `race_start` is a single message, and a browser that is
  somewhere else when it lands sits the whole race out: `raceMode` stays false
  with the phase saying `racing`, so the car is frozen or in practice, the lap
  clock at `raceT0` never starts, `finish` is never emitted and the flag writes
  a DNF - while every other car on the screen drives away. Three ways to be
  somewhere else, all seen: a track still building (see below), a socket that
  blinked across the five seconds of lights, and an exception anywhere in
  `onRaceStart`. So `onRaceGreen` places a car that is on the grid and has not
  been placed. It has missed the countdown, which is the honest cost, and it
  has not missed the race. The usual answer here - "a second statement of the
  same fact is a second thing to be wrong" (see the lap count) - does not apply,
  because this one is a *repair*: it is read only when the first statement
  demonstrably never arrived.
  - **The track switch was the way in that had no excuse.** `switchTrack`
    cleared `raceMode`/`racePhase`/`raceT0` on the far side of its `await`,
    which is right for a switch and wrong for anything the room did while the
    fetch and the build were in flight - hundreds of milliseconds on the big
    tracks. A `race_start` inside that window was undone a moment later. It
    only clears the phase it went in on now.
- **Cars are solid through the countdown, not just after it.** `contactOn`'s
  list used to be free practice and `racing`. The field is already standing in
  the slots it will race from during the lights, so five seconds of driving
  through each other meant a grid that was interpenetrating at the green and a
  race whose first event was everybody being shoved apart. Qualifying and the
  results sheet stay outside it for the reasons in `game.js`.
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
- **Coming back mid-race is a client-side thing too, and for a long time only
  the server did its half.** Everything about a reload surviving is on the
  server - `_drop` marks the car `gone` rather than deleting it,
  `LOST_GRACE_MS` holds its place, `on_join_room` clears the mark - and then
  the browser arrived with `racePhase` 'racing' and `raceMode` **false**,
  because `raceMode` and `raceT0` are only ever set by `race_start` and
  `race_green` and both of those fired while the page was somewhere else. Every
  rule that reads the two together read the gap: `contactOn` was false so no car
  touched another, `canUseItem` is gated on it so items did nothing, the lap
  clock at `raceT0` never started so there was no time to finish with and
  `finish` was never emitted - making the DNF at the flag a certainty - and
  `restartCostsARace` was false, so `R` restarted on one press instead of
  asking twice. `resumeRace` is that half, off a new `in_race` in `room_hello`:
  the server's own answer to "are you in the race that is running", asked of
  the **grid** rather than of the phase, so somebody who walked in after the
  lights is still driving and still not scored. The clock is restored to the
  green light and not to now, so the time spent away is in the lap - what is
  lost is lost, and what is not lost is the race. `room_hello` also seeds
  `clockOffset` off its own `server_ms` when nothing better has been measured,
  because the five `clock` round trips are staggered 200ms apart from connect
  and the restored `t0` needs an offset before the first of them lands.
- **Who is still out on the circuit is asked of the socket, not of the
  poses.** `_pending` used to filter on `_live`, which is a pose inside
  `POSE_STALE_MS` - six seconds. A car whose browser is still sitting there but
  whose last pose landed seven seconds ago is not a car that has left the race;
  it is a car on a bad connection, which at a venue is most of them. It dropped
  out of `_pending`, `_maybe_close` read the road as empty and closed the race
  as "all in", and `_close_race` wrote them down as a DNF - while they were
  still driving, and forty-five seconds before the grace they were owed. `gone`
  is the honest question: `_drop` sets it when the socket ends, so it means
  "this browser is not here" rather than "this browser was quiet for a moment".
  Nothing is lost by waiting, because a race is still bounded by
  `FINISH_GRACE_MS` from the first car home and by `_hard_race_ms` from the
  green. **`_live` keeps its own rule**, because `_humans` measures whether a
  *room* is alive and a hung tab must not make one immortal.
- **The lights can go out over an empty road, and `_maybe_close` is asked once
  more at the green because of it.** That function only acts while the phase is
  `racing`, which is correct - it is called from finish, resign, disconnect and
  kick, and none of those ends a race that has not started. But the last two can
  both happen *during the five seconds of lights*: close the tab or press Resign
  while counting down and the car is `gone` or `dnf` before there is a race to
  close, so the call they make does nothing and the phase change that follows
  has nobody left to notice. The room then sat in `racing` until `hard_end` -
  150s on the short tracks, **596s on Playground** - with the host unable to
  change track or start another, because `set_track` and `start_race` both
  refuse mid-race and are right to. `_go_green` now asks again on the far side
  of the phase change; at an ordinary green every car is pending and it returns
  at once.
- **`LOST_GRACE_MS` has to outlast the client's own reload, and at 25s it did
  not.** `game.js` retries for as long as Socket.IO will and then reloads the
  page at `DEAD_MS` (twenty seconds), because a session the server has forgotten
  comes back as a connection with no room behind it. So the reload does not
  *begin* until 20s and then has to fetch the page, build the track and rejoin
  inside the remaining five - on Spa or Suzuka, whose colliders are the two
  biggest in the pool, on venue wifi, with the un-tokened modules cold because a
  deploy has just landed. Miss it and you come back to a race you have been
  retired from. It is 45s now. The old comment's second half was simply wrong:
  this has never been what holds a race up, since `_pending` excludes a `gone`
  car either way - all `_tick_lost` decides is when the DNF is written, and
  `_close_race` writes it at the flag regardless.
- **Leaving mid-race is a DNF, not a disappearance.** `_drop` used to delete
  the car, and with it the loss, so the cheapest way to protect a rating was to
  close the tab - the one thing a rating system must never make the smart move.
  The car is now marked `gone` (excluded from `_snapshot` and `_live`, so it
  stops being drawn and stops holding the race open) but kept, so it is still
  in the standings and still rated. `_reset_race` is what finally drops it.
- **The host leaving closes the room.** The seat used to pass to whoever was
  next in seat order, which sounds generous and is not: everything about a room
  that anybody else was waiting on is the host's - the track, the settings,
  whether qualifying runs, which bots are on the grid, when a race starts - so
  handing it over gives a room to somebody who did not ask for it, in the middle
  of a session somebody else set up, and what actually happened is that nothing
  started again until the sweep took it. The session's points go with it, which
  is the other half of the same argument: a championship is a thing that room was
  running, and a room under new ownership is a new room.
  - **Only a hard leave.** A disconnect is the soft kind - the seat stays and the
    car comes off the road - so a closed tab, a reload or a phone going through a
    tunnel does not take everybody's race with it. `_drop(hard=True)` is the
    Leave button, and `_leave_other_rooms` is the same rule through the other
    door, because creating or joining a room elsewhere is leaving this one. Two
    call sites, one rule: otherwise the way to keep a room you have walked out of
    is to walk out of it sideways.
  - **The reason is carried out with the reader.** `room_closed` has always had
    one and the client threw it away, so a room ending looked exactly like a bug
    - you were simply somewhere else. It goes to `/lobbies?closed=…` and is said
    there, in the error box without the red, since nothing has gone wrong.
  - The "nothing but bots is an empty room" branch in `_drop` is now unreachable:
    anybody who is not the host leaves the host behind, and a host is a person.
    Kept anyway - it is two lines, and the room of four bots it prevents would
    otherwise sit in the lobby list until the 45-minute sweep.
- **A room runs a championship, and it is nothing like the rating**
  (`_score_race`). N points for the winner down to 1 for last, where N is the
  size of the field, so what a win is worth is how many cars you beat. It is
  **per session**: it lives on the live room beside `settings` and `last_order`,
  survives a race and a track change, and is forgotten when the room is - no
  column, no migration, nothing to sweep, and a seat that leaves and comes back
  is a new seat starting from nothing.
  - **A DNF scores nothing**, and the places behind the finishers go unawarded.
    Scoring the DNF rows off their positions would pay out on the one part of a
    result that is noise - they are ordered by whichever they happened to give up
    in, the same reason `_rate_race` draws two of them rather than ranking them.
    The winner is still worth the full field either way: retiring costs you your
    own points, not everybody else's.
  - **Everyone scores, including guests and bots**, which is the exact opposite
    of the ELO rule one bullet down - and for the same underlying reason. A
    rating is farmable because it leaves the room; a table that is forgotten with
    the room is not, so the field can be the field. A bot taking third has to
    *take* third or the table is not about the racing. Nothing here is gated on
    the anti-cheat either: a flagged car keeps its place in the standings on the
    screen, and points are what that place is worth in this room for the next ten
    minutes.
  - **The roster is the only thing that carries the tally**, so `_close_race`
    re-broadcasts it rather than leaving the client to add the result sheet up.
    Two reasons that are the same reason twice: a browser that walked in after
    the lights never saw the result, and a reload has to land on the numbers
    everybody else is looking at. That is also why `_roster` takes the *game* and
    looks the points up itself - handed in, they would be an argument four call
    sites have to remember, and the one that forgot would draw a room where
    everybody's tally read zero.
  - **The sheet shows both numbers and the sidebar shows one.** The results sheet
    covers the drawer, so the question it has to answer is not only what the race
    paid but who is winning the evening - hence `+4` and the session total in the
    same gold pill the sidebar wears, one object in two places. On a phone the
    row is already spending everything it has on the name, so the delta is
    dropped there and the pill stays: the delta is the finishing position you are
    looking at, and the total is the number nothing else on the sheet carries.
    Your own pair is spelled out in words under the standings, next to the rating
    line and for the same reason - a bare `+4 11` is a puzzle the first time you
    meet it. The column appears for the whole room or for none of it, and only
    once something has been scored: a column on some rows reads as "these people
    are in it and you are not".
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
  reversed.** It is one of the room's three settings (`ROOM_DEFAULTS`, the others
  being **Powerups** and **Laps**) and it lives
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

- **A race on a closed circuit is three laps by default, and `_race_laps` is
  the one place the setting becomes an answer.** It is the third of
  `ROOM_DEFAULTS` and the only one that is not a switch - a count, stepped
  1..`LAPS_MAX` (10) by a - and + in the room drawer, so `on_set_setting` grew a
  second shape and clamps rather than refuses: nothing the buttons can send is
  out of range, so anything that arrives out of it is not a host pressing a
  button and there is nothing to tell them about.
  - **It means nothing on twenty-one of the twenty-six tracks**, whose finish
    line is not their start line, so `_race_laps` answers 1 for any track that
    is not `closed` whatever the setting says - the host may well have left it
    at three on the circuit they came from. The stepper is *hidden* rather than
    disabled there, because a greyed-out control is a thing to wonder about and
    this one has nothing to say.
  - **Everything that has to agree about how long the race is asks that one
    function**, because a race whose halves disagree is a race that does not
    end: the two track-shaped bounds in `_finish_is_possible` (both are
    statements about the road that had to be covered, so on three laps it is
    three times as much of it), `_hard_race_ms` (eight times a gold lap *times
    the laps*, or the backstop that exists to rescue a stranded room would
    guillotine a three-lap race a third of the way in), and the bots, which are
    handed it by `world.green(t0, laps)`.
  - **The browser is told by the settings and by nothing else.** `raceLaps()`
    in `game.js` is the same two questions in the same order - is this track
    closed, and what does the host's setting say - off `S.settings`, which
    `room_hello`, `room_settings` and `_race_state` all carry. There is
    deliberately no lap count on `race_green`: a second statement of the same
    fact is a second thing to be wrong, and the interesting question would
    become which to believe. `applyPhase` is where it reaches the car
    (`S.run.laps`), because every way into a race and out of one already goes
    through it - and only for a race you are *in*, since somebody who walked in
    after the lights is practising on the same road and drives one lap.
  - **`Watcher.prog` counts the laps too**, which is the part that is not
    cosmetic. The ribbon's arc is 0..length whichever lap the car is on, so a
    field spread over two would read as everybody bunched on one - and the
    standings are ordered by that number and a finish claim is measured against
    it. `sample_progress` finds the wrap from the arc moving nearly the whole
    lap between two samples, and **it is signed**: without the decrement, a car
    that crosses the line and rolls back over it banks a full lap of progress
    and the lead with it. The client's own `Run.bestS` does the same thing off
    `course.locate`, for the catch-up gap and its own pose.
    - **The threshold is `LAP_WRAP` (three quarters), not half a lap, and
      Suzuka is why.** Half is the obvious answer and it shipped, and it was
      wrong on the one track in the pool that crosses over itself: the bridge
      carries the back straight twelve units above the run down from Degner,
      and those two pieces of road are **1727 units apart on a 3422-unit lap**,
      sixteen units past half of it. A respawn there leaves the station hint on
      one branch and `w.arc` on the other - the pose that lands off the road
      returns early, after `nearest_station` has already moved the hint - and
      the next honest pose read as a lap.
      What that cost, measured off the replay of race 324: a mid-field bot led
      the standings for seventy seconds, the person who won by eleven seconds
      was shown second from half distance, the whole field's order was right
      67% of the time, and every blue shell went after the wrong car. At three
      quarters the same replay puts the standings in the finishing order from
      half distance on. **The client's `LAP_WRAP` in `course.js` is the same
      number for the same reason and the two have to move together.**
  - **The lap the *race* is on is a separate counter from the lap the
    *distance* is on**, and they must not be shared. `Run.lap` is scored - it
    only moves when the line is crossed with every checkpoint behind you, and
    crossing it resets `nextCp` and clears the remembered gate sides, or a gate
    whose side was last recorded a lap ago produces no sign change on the way
    past it and goes silently missing. `Run.sLap` is geometry. `Run.cpIndex()`
    is what a split is reported by, counted over the whole race rather than the
    lap, or `on_split` keeps lap one's time for lap two's gate and every delta
    after the first lap is measured against the wrong one.
  - **A reload comes back on the lap it left, and `_lap_progress` is rebuilt
    from what the room already keeps.** `resumeRace` restored the clock and the
    seat and never restored `nextCp`, so a reload had always meant re-crossing
    every checkpoint - which on three laps is two laps' worth of driving instead
    of part of one, and a lap counter back at 1/3 with the field on its last.
    Nothing new is stored for it: every gate a car takes during a race is
    already reported to `on_split`, so the largest index this car has reported
    *is* where it had got to, and it divides straight back into a lap and a
    checkpoint.
    - **The stride is `checkpoints + 1`, and the spare slot is the line.** At a
      stride of the checkpoint count, the crossing that opens lap two and the
      last checkpoint of lap one are the same number and this cannot tell them
      apart - so the line is reported as a gate like any other (`nextCp === 0`),
      which is also why a lap now gets a delta against the leader's lap. Bots
      report it through the same `cpIndex`, or their splits and a person's are
      not comparable.
    - **It is applied after `Run.start`, not instead of it.** A mid-race reload
      lands with `raceT0` in the past, so the race branch of the frame loop
      starts the run on the very next frame - and `start` is the one place a run
      begins, so it clears exactly the two counters this is putting back.
      `resumeRace` therefore only *keeps* the answer (`S.resumeAt`) and
      `Run.resumeAt` is called on the far side of that start, once.
    - `sLap` comes back with them, because it is the lap the *distance* is on:
      left at zero, the car reports itself most of a lap down and is handed the
      catch-up boost for a gap it does not have.
    - **The gate the car was between is still lost**: you come back at the last
      gate you actually crossed, never further on. The alternative is trusting
      the client's own count, which is the number the whole of `racecheck`
      exists not to trust, and the cost of the honest answer is at most one
      sector.
  - Nothing about the leaderboard changes, because nothing from a room ever
    reached it (`countsForTheBoard`). A three-lap time is not a lap time and is
    not offered as one: no medal, no PB, no ghost.

- **Every item is the room's, not the browser's.** A pose is one client's
  opinion and is allowed to be wrong by a metre - that is the whole design of
  the netcode - but an item is a *discrete shared event*, and two browsers each
  rolling what came out of a box, or each deciding a shell hit, disagree
  permanently and there is nothing to reconcile them with. So the queue, the
  roll, the shells and the hits all live in `app.py`, and the browser's whole
  job is to ask and then to be told. A client cannot write its own slots, and a
  reconnect is handed the same two it had (`room_state` carries `items`).
  - **On by default**, which is the opposite of qualifying's default and for the
    same reason: qualifying costs a room two minutes before anybody races, and
    items cost it nothing. The host turns them off from the drawer for a room
    that wants a clean race, and the server refuses the change mid-session the
    way it refuses the track.
  - **`_powerups_live` is the gate, and it is `contactOn`'s rule twice over**:
    free practice and the race, never qualifying. A blue shell during the ninety
    seconds everybody is alone on their own lap against the clock would take away
    the one thing the session is for - which is exactly the argument that keeps
    contact and the slipstream out of it too.
  - **A box is the room's, not yours.** One car drives through it and it is
    gone from every screen at once, and back a second later
    (`BOX_RESPAWN_MS`) - so there is something to race each other to, which is
    the whole point of a box on a shared road. `on_item_box` says *which* box
    and `_claim_box` decides, on two facts the server owns: where that box is
    and where this car's last pose put it (`BOX_REACH`). A box already taken
    pays nothing, and a full queue turns it away **without taking it**, so it
    is still standing for the car behind. The pose is not a scoring authority
    and is not being asked to be one; it is only being asked to bound what a
    socket payload can say. Bots come through the same function from
    `_tick_bot_boxes`, against poses the server itself wrote, so a bot cannot
    take one from further away than you can.
  - **Where the boxes are is off the ribbon, not off the checkpoints**
    (`_boxes_for`). A checkpoint is where the *track* wants a gate - three on a
    twenty-second lap, none down a long straight - so hanging items off them
    made a short track a sweet shop and a long one a desert. Instead it is a
    row across the road every `BOX_SECONDS` (9) of the track's own ideal lap,
    at least one row, placed off a station's position, lateral and **surface
    normal**, so a row lies flat on a banked corner and stays inside the road
    on a narrow one without any of that being special-cased. A road under five
    units of half width gets the middle box only - three across a narrow
    shoulder is two boxes in the scenery. The list goes to the client with the
    track (`room_hello`, `track_change`): one source of truth, and the server
    needs it anyway to judge a claim.
  - **What every item does is counted**, in `drive_item_stats`: `given`,
    `used`, `hit` and `blocked`, one row per item. Four numbers rather than a
    row per shell thrown, because the questions anybody actually asks - is the
    odds table doing what it says, is an item being held and never used, does
    a shell ever land, is holding one worth the throw - are all ratios between
    those four, and a log of every event answers them with a GROUP BY over a
    table that grows for ever. Tallied in the worker and flushed once a minute
    (`_tick_item_stats`); a worker that dies loses up to a minute of counting,
    which is the right trade for something that must never be a transaction in
    the middle of a race. `/api/item-stats` is the read, and it adds the
    unflushed tally on top so the numbers do not stand still for a minute at a
    time. A boost counts once per *box*, on the tap that opens its window.
  - **What a box gives depends on where you are** (`ITEM_ODDS`, `_roll_item`,
    `_race_band`), which is the whole reason a field stays together. The bands
    are thirds of the running order: out in front you draw things to *defend*
    with - banana, shield, green, the occasional red - and **never a star or a
    blue**, because a leader who could draw one has nothing to fear and nothing
    to catch. Down the back is where those two live, along with the boost and
    the bomb. Practice is flat and has neither of them for the same reason it
    has no positions.
    **The green was a fifth of every box in the game and is not any more.** It
    is the worst item to be handed - forwards it needs a car in range and a
    straight, backwards it needs somebody sitting on you, and most of the time
    it is neither, so a box that pays a green pays nothing. 28/18/14 across the
    three bands became 18/12/8, and what it gave up went to what each band is
    *for*: bananas and a shield in front, a red in the pack, and a star, a
    boost or a bomb at the back, which is the only place the odds can make
    catching up possible.
  - **Two slots, and the front one is what `X` spends.** `PRACTICE_ITEMS` is the
    practice pool; a race adds the blue shell and the star, which are the two
    items that only mean anything when there is a leader and a last place.
  - **The bomb is thrown at a *place*, which is what makes it different from
    every other item here.** It is lobbed up the road at `BOMB_SPEED`, settles
    where it lands after `BOMB_FLY_MS`, and goes off `BOMB_FUSE_MS` later or
    the moment anybody touches it - and `_blast` catches **everybody** within
    `BOMB_BLAST`, **including whoever threw it**. That last part is the item:
    without it a bomb is just a slow shell, and with it, lobbing one into a
    pack you are in is a decision. Each victim gets the ordinary `item_hit`, so
    a shield still eats it and a star still ignores it - one rule for being
    hit, wherever the hit came from - and `item_blast` carries the flash and
    the bang, which belong to the place rather than to any car. It will not go
    off on contact with the car that just threw it, which is the same clause
    that stops a shell hitting its own nose.
  - **Nothing hits a car that has never been sent one frame of it.** `_fire`
    runs in a socket handler; `_tick_shots` runs at the top of the next tick
    and `_snapshot` at the bottom of the same one - so a shot thrown at
    anybody inside about nine units (the five it leaves the nose at plus the
    four of `SHOT_HIT_R2`) was born, moved and spent before it had ever been
    in a snapshot. No mesh, no dot on the minimap, no `shellWarning` ping:
    from the seat, being spun over by thin air, with only the toast afterwards
    to say what it had been. And nine units is not an edge - it is the range
    anybody actually throws one at. Every shot now sits still for
    `SHOT_ARM_TICKS` (two, 66ms) before it may move or hit.
    **Still, not merely unarmed**: a shell allowed to fly for those 66ms is
    five units past a point-blank target by the time it arms, which trades an
    invisible hit for a shell that goes through somebody, and that is not the
    better game. Frozen, it is in the same place when it arms, so every hit
    that landed before still lands - 66ms later, having been drawn, mapped and
    heard first. The expiry check is *above* the arming branch, so a shot
    whose clock has run out still dies rather than being kept alive by it.
  - **Every shot carries an id**, because the list it travels in changes order
    every time one is fired or hits something - a browser binding a mesh to a
    *list position* had shells swapping places with each other mid-flight. With
    an id a mesh belongs to one shell for its whole life, and the 30Hz position
    becomes somewhere for it to be going rather than somewhere to be put
    (`moveShots`). `SHOT_SPEED` is 75 against a `MAX_SPEED` of 50, and it used
    to be 42: a shell slower than the car it is chasing never arrives.
  - **A shell or a banana is a thing in the world, and it rides the pose
    snapshot.** `_fire` puts it in `r["shots"]`, `_tick_shots` advances it from
    `_pump` at the same 30Hz the poses go out at, and `_snapshot` carries the
    list - a shell nobody can see is a hit out of nowhere. A banana is the same
    object standing still, four units behind the car and lasting `BANANA_MS`
    rather than `SHELL_MS`. **Nothing ever hits the car that let it go**: a shell
    leaves three units off the nose against a four-unit hit radius, so without
    that clause every shot hit its own owner on the first tick - which is what
    `tests/test_powerups.py` pins.
  - **A red shell takes the nearest car ahead on `prog` and a blue one takes the
    leader**, re-aimed every tick, and a driver already in front has nothing to
    aim at and fires nothing.
  - **The blue's leader is the leader *on the road*, not the winner**, which is
    the same rule `gapToLeader` follows for the catch-up boost and for the same
    reason: a finisher keeps rolling and its `prog` keeps climbing past the
    flag, so the moment anybody was home every blue in the room went after a car
    parked on the far side of the line - most of a lap away, which `HOMING_MS`
    runs out long before, and from the seat that is a blue that simply got lost.
    A one-lap race hid it because the flag ended everything within seconds; a
    three-lap race leaves thirty of them. Cars that are home or retired are
    skipped, and if that leaves nobody it falls back to the whole field rather
    than firing at nothing.
  - **A shell runs round a closed circuit** (`track["closed"]`), because Spa,
    Silverstone, Monaco and Monza finish where they start: the leader a blue is
    sent after is regularly "ahead" only by going the long way, so a shell that
    stopped at the end of the station array died on the pit straight every
    time - a blue shell that got stuck and never arrived. On a ring the "past
    its man is a miss" rule is off too, since *past* is a lap of arithmetic
    away from *not there yet*; a shell's clock (`HOMING_MS`) bounds it instead.
  - **The blue is the quick one** (`BLUE_SPEED`, 115 against a shell's 75 and a
    car's 50). It is sent from the back of the field to the front, which on a
    long track is most of a lap of road, and at a shell's pace it arrived after
    the race it was meant to change had been decided.
  - **A homing shell follows the road** (`_steer_along_road`), because the car
    it is chasing is round a bend and the road is the only way there. Flying at
    the target in a straight line put it into the scenery on the first corner.
    So a red or a blue is launched *onto the ribbon* - `_ribbon_at` turns the
    firing car's position into a station index and an offset across the road,
    `_ribbon_point` turns those back into a point - and from then on it
    advances along the road and leans across it toward whatever it is chasing
    at `SHOT_LEAN`. It takes Monaco's tunnel, Rickety's cave and Playground's
    walls of death with none of them being a special case, and its life ends
    when the road does. A **green** deliberately still flies straight: it is
    the difference between the two items, one is aimed by you and one is sent
    after somebody. They also live for different lengths - `SHELL_MS` against
    `HOMING_MS` - because a shell sent after a car two corners ahead spends
    most of its life getting there.
  - **Bots play with items too, and through the same two functions.** A bot
    claims the box at a checkpoint from `_bot_events` (its `cp` event carries
    `Run.nextCp`, which is exactly what a browser sends) and spends it in
    `_tick_bot_items`, which is the whole of its judgement: it sits on an item
    for a second or three so a field of them does not fire in unison, and it
    **holds a shell it has nothing to aim at** rather than throwing it away -
    which is what a person does with one too. Everything after that is
    `_spend_item`, the same call the socket handler makes, because two versions
    of "what this item does" is how a bot's blue shell comes to behave
    differently from yours.
  - **A hit is announced, not applied - except to a bot.** `item_hit` names one
    car and that car's own browser gives itself the shove, because the browser is
    what simulates that car in this game and always has been. A bot has no
    browser, so the server does for it: `BotWorld.hit` is the same shove on the
    same `Car`, and without it a red shell homed perfectly onto a bot and nothing
    whatsoever happened.
  - **One direction rule, for every item.** A press throws forwards and `back`
    - the throttle released - throws behind, and `_fire` is that one sign. The
    banana used to be the exception: its ordinary direction was backwards and
    `back` lobbed it ahead, so the one control on the pad meant the opposite of
    itself for one item and there was no way to learn that but to be surprised
    by it. Thrown backwards it is now *dropped* - standing still on the road -
    which is what a banana is for and what anybody reaching for backwards
    wanted. A bomb is the one throw that adds the thrower's own speed to it
    (`BOMB_LOB`): `BOMB_SPEED` is 38 against a car's 50, so one lobbed at speed
    was left behind inside half a second and went off under its own thrower's
    back wheels. A bot passes `back` for its own bananas, since it is defending a
    place rather than aiming at one. The bug that hid inside the old rule: the
    shot's `until` asked `back` rather than the item, so a green thrown
    backwards lived `BANANA_MS` and bounced around the track for forty-five
    seconds.
  - **And what the shove is, in one place: `hitByItem`.** A hop, a tumble about
    the car's `right`, and then no speed: 15% of the velocity kept and 5.5
    units of air, down from 16, which was a launch that took the camera with
    it. **A flat spin about `up` was tried in between and is worse** - the
    chase camera lerps toward the car's own forward, so a car turning on the
    spot takes the camera round with it and you cannot see the road at all.
    **The camera keeps its own frame for the first second of it**
    (`opts.hold` in `Renderer.follow`, timed by the same `hitSmoke` call). The
    chase frame lerps toward the car's own forward and up, and a car flipped
    by a shell turns through 130 degrees in a third of a second - so the lens
    went through the road and then at the sky, and a hit was a second of
    brown. Held, the car tumbles inside the shot and you watch it happen. A
    cached `render.js` has never heard of the flag and simply follows, which
    is the old behaviour rather than a broken page.
    The car then smokes for 1.4s (`hitSmoke`), because the sparks are over in a
    tenth of a second and the slowdown lasts three - without it the car is
    crawling for no visible reason. That smoke is `soot`, a *normally* blended
    particle: everything else in `Particles` is additive, and additive black is
    nothing at all. `item_hit` also carries its `owner`, so the victim's toast
    names both halves - *Hit by Dana's red shell!* - and a shield that blocks
    one says whose it blocked.
  - **The boost is a window, not a press, and the room owns the clock.** It is
    the golden mushroom: the first `X` opens `BOOST_WINDOW_MS` (7s), every tap
    inside it is another short burst of engine, and the *slot keeps the item*
    until the window closes - which is why `_spend_item` has a branch and why
    `_tick_items` is what finally pops it. The slot has to be emptied from the
    clock rather than from the last press, because nobody knows which press was
    the last one. That `items` message carries a `pid`: it goes out to the room
    because the pump has no socket of its own to reply on, and every other
    browser drops it. A bot on an open window taps again every `BOT_BOOST_TAP`,
    a little slower than a person can, which is the difference between a bot
    and a bot that is better at pressing a button than you are.
  - **A starred car spins people out by touching them** (`_tick_stars`). The
    star already made you quick and unhittable; what it did not do was give you
    anything to *do* with either. Contact is read off `FLAG.STAR` in the pose
    flags rather than from a second list, so bots and people are on the same
    terms and nothing new goes on the wire; `STAR_AGAIN_MS` is what stops
    driving alongside somebody being a machine gun, and two stars pass through
    each other.
  - **The star wears the shield's bubble in gold** (`CarView.setShield`), and
    that is the whole of what makes it visible: it is otherwise a car that is
    quick and cannot be stopped, neither of which can be seen from behind.
    `FLAG.STAR` (bit 64) puts it on every screen the way `FLAG.SHIELD` does.
    One mesh serves both, because a car can never have both at once - a star
    ignores the hit a shield exists to eat.
  - **The star and the shield are answered where they are held**, which is the
    one place that knows: the star ignores a hit, and the shield spends itself on
    the first one rather than waiting out its thirty seconds. The shell is gone
    either way - the server has no idea it was wasted, and does not need one.
  - **A shield is drawn on the car, on every screen**, which is what
    `FLAG.SHIELD` (bit 32) is for: the pose byte already reaches everybody, so
    the bubble costs nothing extra on the wire - and the point of a visible
    shield is the driver *behind* you deciding not to waste a shell on it.
    `racecheck.py` carries the bit in its copy of the byte and reads nothing
    from it; `lampsOf` in `game.js` is where a byte becomes a bubble.
  - **The three held timers are cleared by `game.js` against its own deadline**
    (`ITEM_TIME`, `expireItems`), not only by `physics.js` counting them down.
    `physics.js` is imported bare and carries no cache token, so for the hour
    after a deploy a page can be running a copy that has never heard of `star` -
    it would set the field, nothing would decrement it, and a ten-second star
    would last the session. See the deploy notes in `drive/CLAUDE.md`.
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
- **A seat remembers who you were when you took it, and signing in changes
  that.** `session_key` deliberately survives a login - `login`, `register` and
  `portal_auth` pop `guest_name` and set `user_id` and touch nothing else -
  which is what lets a guest sign up without losing the seat they are sitting
  in. What it also did was leave the `drive_players` row saying guest: null
  `user_id`, the guest's typed name, the colour hashed off it. Everything
  downstream reads the row, so for the rest of that room's life the new account
  was a guest to `_rate_race` (no ELO, no win or podium tally, and beating them
  gained nobody anything either - see the bullet below), wore the hashed colour
  instead of the car out of its garage, and raced under the name it had just
  stopped using. A reload did not fix it, because a reload finds the same row.
  `_refresh_seat` brings the row up to date wherever this browser's seat is
  looked up - `_add_player`, the room page and `on_join_room`, which every way
  into a room passes through. It compares on `user_id` rather than on the name,
  because that is the fact the rating and the tallies turn on, and it covers
  logging *out* and carrying on as a guest for the same reason. A bot's seat has
  nobody behind it and is left alone.
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

