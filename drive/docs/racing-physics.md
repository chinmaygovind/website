# Drive: racing physics — contact, slipstream, catch-up, rivals

Read this before changing `physics.js` car-to-car code, the draft, the
catch-up boost, remote-car interpolation, or rival sound.

- **Live races are in memory, not the DB.** A race ticks 30x/sec: clients are
  authoritative over their own car and emit `pose`, the server merges and fans out one
  snapshot per tick, and only the finished standings are written back. Cars are solid,
  resolved Mario-Kart-style (impulse + penetration spring, never positional snapping,
  tangential velocity preserved, per-pair bump cooldown) - see `Car.resolveCars`.
  `FLAG.BRAKE` rides along in the pose so a rival's brake lights work.
- **A hit only moves a car if the tyres let go, and that is not what anybody
  reaches for first.** Contact felt weightless, and the obvious fix - a bigger
  `CAR_REST`, a stiffer `CAR_PUSH` - does nothing at all: `GRIP` kills lateral
  velocity at `1 - exp(-GRIP*dt)` per step, so a sideways impulse is gone inside
  a tenth of a second *however large it is*. Measured, raising both of those
  moved a 14 u/s side-swipe from 0.26 units of displacement to 0.25. The car is
  bolted to its heading and no impulse gets to argue. So a firm hit briefly
  unsettles the car instead: grip falls to `BUMP_SLIP_GRIP` (4, about halfway to
  the handbrake's own 2.4) and recovers over `BUMP_SLIP_TIME`, which takes the
  same swipe to 0.99 and a 20 u/s punt to 1.57 - against a 1.9-wide car on a
  9-wide road, a place lost rather than a noise. **Neither number is scaled by
  how hard the hit was**, though every instinct says they should be: the impulse
  they are letting through already is, so scaling the window on top of it squares
  the relationship and an ordinary firm shunt comes out moving the car *less*
  than the same shunt on full grip would suggest. The timer is decayed with the
  other per-step timers rather than in the grounded branch that reads it, or a
  car knocked into the air holds the whole of it frozen for the flight and lands
  on a slide a second after the hit that caused it.
- **Two thresholds, because there were two questions behind one number.** A
  single `hit > 5` decided both whether a contact was *reported* and whether it
  *cost* anything, so every touch under it was completely silent - no clank, no
  sparks, no camera kick, no lean - and running wheel to wheel down a straight,
  which is most of what contact in a race actually is, looked and sounded like
  driving alone. `BUMP_FEEL` (1.5) is when you are told and `BUMP_COST` (5, the
  old number, unmoved) is when it hurts. The gap between them is where racing
  side by side lives: heard, and free. Lowering one gate instead would have
  walked straight back into the compounding `CAR_BUMP_SCRUB`'s own note is
  about - the per-pair cooldown is 0.15s, so a second and a half of rubbing is
  about ten events, and charging speed for each of them is a tenth of your speed
  gone for touching somebody gently. **Everything a hit does now happens once**,
  on the event rather than per step of contact: that was already true of the
  scrub and quietly false of the other two, so the body lean climbed to its own
  clamp inside a tenth of a second (a car rubbing alongside somebody drove along
  at 29 degrees of roll) and the yaw - an angle with no `dt` on it - was worth
  radians a second for as long as the cars touched, which is the spin it is
  explicitly not supposed to be able to cause. `test_bump.py` pins all of it,
  and pins the grip release against *its own absence* rather than against a
  figure in a comment, since that comparison is the whole surprise.
- **Contact and the slipstream belong to free practice and the race, and to
  nothing else.** They are the same question - are the cars around you cars you
  are driving against - so they are one answer, `contactOn()` in `game.js`.
  Qualifying is the exception on purpose: everybody is alone on their own lap on
  a road they are all using at different points of it, so being punted by
  somebody a corner behind would take away the one thing the session is for, and
  a tow off a car you are not racing would hand out a grid slot nobody drove
  for. For those ninety seconds the rivals are drawn **see-through**
  (`CarView.setGhostly`, the same opacity the ghost uses) and you go through
  them: a solid-looking car you cannot touch is a bug until somebody explains
  it. Countdown and the results sheet are outside it too - there is nothing to
  race there. `test_slipstream.py` pins the phase table.
- **The slipstream is Mario Kart Wii's draft: it charges, then it pays.**
  `Car.draft` measures the tow in the *following* car's own frame - ahead along
  your forward axis, inside a narrow corridor either side of and above/below it,
  and pointing roughly the way you are - so it works upside down in a loop and up
  a banking with no special case, and you cannot tow off somebody crossing at a
  junction or coming the other way. Sitting in it pays **nothing** for
  `SLIP_CHARGE` seconds and then hands over the whole of it at once: a trickle of
  speed for following somebody is invisible and unearned, a boost you spent a
  second and a half lining up is a move you decided to make. **The boost is more
  engine, not a raised limit** - top speed is where `ACCEL` fights the quadratic
  `DRAG`, so `SLIP_ACCEL_MULT` 1.5 lifts it by its square root (about a fifth,
  50 -> 61) and you have to accelerate up to it. Nothing accumulates while a
  boost runs, so the cadence is charge, fire, charge rather than a permanent tow
  behind a car you cannot pass. `FLAG.SLIP` rides along in the pose - wired for,
  and like `FLAG.DRIFT` not drawn on a rival.
- **The slipstream is drawn round the car, not on the HUD.** `Draft` in
  `render.js`: streaks of air running past you, one camera-facing quad each,
  **thickening with the charge** - the same number the bar under the speed bar
  used to show, so you watch the boost coming without looking away from the
  road - and then going amber and flat out when it pays, petering out with the
  boost rather than being switched off. A bar said the same thing in a corner
  you cannot look at while you are two car lengths off somebody's bumper, and a
  "Slipstream!" toast said it a third time over the middle of the screen. The
  effect *is* the announcement now, with a whoosh, a camera kick and 7 degrees
  of FOV. Four things keep it a suggestion of air rather than a curtain: the
  streaks' long axis is the car's **own** forward (so a loop needs no special
  case) with only what is left over turned to the camera - turn them to it the
  ordinary way and they spin on screen and stop reading as motion, leave them
  and they vanish edge-on; the ring is an **arc over the top and round the
  sides, never underneath**, because the air under a car is the road and a
  streak drawn there is a bright bar lying on the tarmac; it is a **cone** -
  wide off the nose, drawn in tight against the flank, spilling out behind -
  which is both what air does around a body and what keeps it off the bodywork;
  and it **stops well short of the chase camera**, since air blowing through
  the lens is a windscreen. They are additive, so they stack: the fade envelope
  is deliberately steeper than a sine so each one is only briefly at full.
  **`?draft=charge|boost` pins the tow** so the whole thing can be
  photographed - same reason as `?panel=` and `?touch=1`, since otherwise it
  takes two browsers and somebody driving eight car lengths ahead of the
  shutter. The sound is the same story: `Sound.draft` opens a band of rushing
  air as the charge fills, so you can *hear* the boost coming.
- **Every car's tow is drawn, not just yours.** A `Draft` belongs to each remote
  as well, because the driver winding up behind your gearbox is the only person
  on the track who cannot see it - watching somebody else's air thicken is the
  whole of what makes a tow a move you can answer. It cost **one number on the
  wire**: `sl` in the pose, 0..1, with the `FLAG.SLIP` bit that was already
  there for the tail lamps saying whether it is the charge or what is left of
  the boost. Field 14 of the snapshot, appended like the age before it, and the
  client guards on the array's length, so a page open across a deploy loses the
  tow rather than reading a car's velocity as its position. `Draft` needed no
  idea any of this exists: a remote carries `pos`/`fwd`/`right`/`up`/`speed` and
  the two tow numbers, which is what a car is as far as the effect is concerned.
- **A car behind the leader gets a little more engine, in proportion to how far
  behind it is.** A race in which somebody drops three seconds is decided, and
  everybody in it then drives the rest of it alone - which is most of what a
  four-car room actually looks like, since one mistake or one respawn is all it
  takes. `Car.catchup(gapS, dt)` in physics.js is the curve and `gapToLeader` in
  game.js is the number it reads. Six decisions:
  - **The gap is measured in distance and reported in time.** What the room
    knows about every car is `prog` - it is on the wire, it is what the
    standings are ordered by - but the same 100 units is half a lap of Chicane
    Park and a corner of Sandy Cove. Dividing by `MAX_SPEED` gives the one
    number that means the same on every track: how long that ground would take
    flat out. Nobody averages `MAX_SPEED`, so it is a *floor* on the real gap,
    which is the right direction for a number deciding how much to hand out.
  - **The leader is the leader on the road, not the winner.** A car already home
    is not being caught, so a finisher is skipped and whoever is furthest round
    of those still driving sets the mark - otherwise the whole field gets full
    help the instant somebody crosses the line. Lead the cars still out there
    and the gap is zero, which is the same statement.
  - **Nothing inside `CATCHUP_DEAD`** (1.5s, about two seconds of real driving),
    then a linear ramp to all of it at `CATCHUP_FULL` (5s). Under the deadzone
    you are still racing them and a handout is the last thing that should settle
    it; a step change at a threshold is a car that surges every time the gap
    wobbles across it.
  - **More engine, not a raised limit**, the same term the tow multiplies, so
    `CATCHUP_ACCEL_MULT` is worth its square root in top speed and only while
    you are on the power. They **stack** - a car a long way down that has
    finally caught somebody is exactly the one that should be able to come
    past - and the pair of them still lands under the `MAX_SPEED * 1.7` clamp
    (71 against 85), or the clamp would be setting the top speed instead of the
    tuning.
  - **Full help is 180 on the speedo, and that is the form the number is kept
    in.** The HUD draws `speed * 3.1`, so 1.3486 puts the top of the ramp on
    exactly that, and `test_full_help_reaches_a_hundred_and_eighty_on_the_dial`
    pins the figure on the dial rather than a band around the multiplier -
    changing how fast the game is should have to be said twice. It was 1.22,
    which read 171 against a base of 155: about a tenth, which is not something
    you can feel from inside the car, and a mechanic nobody notices is not
    doing its job. That makes it worth about **three quarters of a tow**, where
    it used to be pinned deliberately under half on the grounds that being
    handed the bigger of the two would make dropping back the fast way round.
    The pin is gone and the fear does not survive the arithmetic: collecting
    the whole of this means actually *being* `CATCHUP_FULL` seconds down, and
    no amount of extra top end buys five seconds back inside a lap. What is
    still pinned is the direction - a tow has to remain the larger prize, or
    lifting off and waiting genuinely would be a tactic.
  - **Nothing is taken off the leader.** A rubber band that slows the car in
    front takes away the race it is trying to make, and the driver in the lead
    is driving the car they qualified.
  - **It follows the gap rather than tracking it** (`CATCHUP_SMOOTH`), because
    `prog` arrives 30 times a second, rounded to 0.1, off a car whose position
    is being extrapolated. Half a second of lag on a number describing the last
    ten seconds costs nothing and is the difference between more engine and a
    car that hunts. The tail of the ramp *down* snaps to zero; **only the way
    down**, and that is not a detail - every ramp up starts at zero and climbs
    through the same hundredth, so a snap that did not check the direction pins
    the help at nothing for ever. A test pins it, having caught it.
  **`catchupOn()` is the race and only the race**, which makes it deliberately
  narrower than `contactOn` - the only other phase gate here, and the difference
  is the justification. Free practice has solid cars and tows, because they are
  cars on a road with you, but there is no such thing as first place in it;
  qualifying is the one session whose whole job is deciding the grid; a
  countdown and a results sheet have nobody driving. It cannot reach the
  leaderboard by two independent rules - no room lap counts, and no lap outside
  a race gets this at all. **Nothing new goes on the wire**: unlike a tow it is
  not a move anybody makes or can answer, so a rival knowing you have it would
  change nothing they would do, and the gap that produced it is already on the
  standings board everybody can read.
- **Catching up is drawn on the speed bar, and the tow is not.** Opposite
  answers to the same question, for the same reason: the tow is aimed at the car
  in front, so it belongs in the air out on the road where that car can see it,
  and this one is aimed at nobody. It is a change in the engine, the bar is
  where the engine already is, and a car that is quietly faster than it was a
  lap ago and cannot say why is a bug report. Gold (the colour the HUD already
  uses for the row that is you), and it **wins over `over`**, which is on at the
  same time nearly always - more engine overruns `MAX_SPEED` on its own - and is
  the less useful of the two things to be told. `?catchup=<seconds>` pins the
  gap the way `?draft=` pins a tow: it is the only visible part, and
  photographing it otherwise takes two browsers and somebody five seconds up the
  road.
- **Other cars are heard as well as seen, and a rival is a place rather than a
  channel.** Engine, tyres and tow all go through one `PannerNode` at that car's
  position (`RivalVoice` in `sound.js`), with the listener riding the **chase
  camera** - the only frame in which "on my left" is the same statement on
  screen and in the headphones, and one that rolls through a loop with no
  special case. **HRTF, not equalpower**: on a chase camera the question that
  matters is in front or behind, which a left/right pan cannot answer. Your own
  car stays out of it, on the master, because it is the thing you are sitting in
  and has no direction to arrive from. A rival is deliberately less machine than
  yours (two sawtooths, no load whine) and what it is *doing* is read off the
  flags already in its pose - there is no throttle on the wire and there does
  not need to be one, since a car that is not braking and is not crawling is on
  the power. `Sound.rivals(list)` takes the whole state in one call, so a car
  that drops out of the list loses its voice: that is what makes the phase rule
  free, and why qualifying, a replay and an empty room all cost one call.
- **You only hear the cars you are driving among, and it is `contactOn` that
  says so** - free practice and the race, the same answer contact and your own
  tow read, so a rival cannot be seen winding up a boost in a session where
  nobody can get one. In qualifying a car howling past your ear is somebody a
  corner behind you on an out lap: a rival you are not racing, arriving as
  though you were. `?panel=qual` is **not** a way to check this - it pins the
  HUD label and not `S.racePhase` - so the by-hand check needs a real session
  (a scratch harness plus a socket client that emits poses; see **Tests**).
- **Only `FLAG.RESPAWN` takes a rival off the track.** Both the visibility line
  and `collidables()` used to test `flags & 8`, which is `FLAG.BRAKE` - copied
  off the brake-light line directly above them, and commented "respawning". So
  every rival went invisible *and* intangible for the length of every braking
  zone: they blinked out on the way into each corner and you drove through them
  at the one moment you were closest. Braking is the flag that must change
  nothing except the lamps. `FLAG` is imported into `game.js` now rather than
  the bits being written by hand.
- **A car you cannot hit does not look like one you can.** `contactOn()` is read
  by the drawing as well as by `collidables()`, so what you can hit and what you
  can see through can never disagree: where there is no contact the rivals go
  translucent at the ghost's `GHOST_OPACITY`, keeping their own colour and their
  name at full strength, since colour is the whole of how you tell one from
  another. That is `CarView.setGhostly`, and it early-returns when nothing has
  changed because `transparent` is part of a material's program key in three.js
  - flipping it recompiles a shader, and this is called from the frame loop for
  an answer that moves about twice a race.
- **A remote car chases its target, except when no car could have driven it.**
  `updateRemotes` extrapolates the last packet forward on its velocity and
  chases exponentially, which is right for the small corrections between
  packets and wrong for everything else. A respawn, a grid placement or a
  packet gap moves the target further than a car can travel in a frame, and
  smoothing that streaked the rival across the map at an impossible speed,
  solid the whole way. Past `REMOTE_SNAP` (12 units), or on `FLAG.RESPAWN`, the
  jump is taken whole - and a respawning car is hidden, so the cut is not seen.
- **And the chase has to be *led*, or it never arrives.** An exponential ease
  never catches a target that is itself moving: each frame closes a fraction `k`
  of the gap while the target opens `v*dt` of new one, so it comes to rest
  `v*dt*(1-k)/k` short - **about three units at `MAX_SPEED`, most of a car
  length, on a perfect connection**. It ran that way for a long time and it was
  **the larger half of the reason two friends racing saw opposite results**:
  every rival is drawn most of a car back on every screen, the errors point
  opposite ways, so two cars genuinely level each looked ahead to their own
  driver. **None of it was ping** - `test_the_lag_is_a_filter_and_not_the_network`
  measures it identical at 2ms and at 200. `chaseLead` cancels it by aiming that
  far up the road: solving the filter's fixed point for zero error gives
  `dt*(1-k)/k`, which is bounded above by the filter's own time constant
  (`1/CHASE_RATE`, 62ms) however long a frame runs, so a hitch cannot turn it
  into a lunge. It is added to the packet's age rather than applied separately,
  because both are the same quantity - time this car has spent driving since the
  position in hand - though **only the age is clamped**, since that clamp is
  about not flinging a stale packet across the map and a lead is not staleness.
  Exact for a car going in a straight line; a braking or turning car is left
  wrong by the same amount and in the same direction as the constant-velocity
  extrapolation it rides on, which is the residue nothing short of putting
  acceleration on the wire can remove. `test_netcode.py` pins it, and pins it
  **against its own absence** rather than against a figure in a comment, since
  that comparison is the whole surprise.
- **Each car in a snapshot carries its own age.** `snap.t` is when the
  *snapshot* went out; the pose inside it is whatever last arrived and can be a
  full pose-interval older. Extrapolating every car from `snap.t` left them all
  short by a different amount every tick - jitter that reads as the network and
  is arithmetic. `_snapshot` sends `now - c["ts"]` per car (field 13) and the
  client measures from there. Trailing fields are appended rather than inserted
  and the client guards on array length, so a cached old client meeting a new
  server degrades rather than computing `NaN` positions.
- **But that age is only half the trip, and the other half is field 15.** A pose
  is stamped when it *lands*, so field 13 is the wait since arrival and says
  nothing about the journey the pose made getting here - while a pose describes
  where the car was when it was **sent**. So every car was drawn short by its own
  upstream leg on every screen but its own: ~1.5 units at 60ms of ping, always
  backwards, mirrored, the smaller half of the same disagreement the chase lag
  caused. The server cannot time that leg itself, so **the client measures its
  own round trip and reports it** on the `clock` handshake it was already making,
  and `_note_upstream` keeps half of the **shortest** one seen. The pings land
  while the page is still loading, so the first is the worst measurement of the
  session, and a running minimum is the only thing that stops it setting the
  number for the rest of it.
  - **It is a client number, so it is capped** (`UPSTREAM_CAP_MS`, 80ms one
    way). All it feeds is how far *other* browsers extrapolate this car, so
    inflating it draws you a little further up the road on screens that are not
    yours; it reaches neither `racecheck`, nor `prog`, nor the result. At the cap
    that is worth about four units, and a test pins that against `CAR_LEN` - the
    trade only holds while the most a liar gains stays under what every honest
    driver was already losing.
  - **And it is a separate field on purpose, not added into 13.** The two have
    different owners: 13 is what the server timed, 15 is what the car being
    measured said about itself. `updateRemotes` adds them, because drawing wants
    the whole journey. `orderFromSnapshot` uses 13 alone, because the standings
    must not be movable by a claim - fold them together and overstating your ping
    is worth four units of projected road on everybody's board, a cheat invented
    by the fix for something else and landing on the one number the order exists
    to make trustworthy. `test_claiming_a_terrible_connection_does_not_buy_a_place`
    is what holds the two apart.
- **Rivals are brought up to now before the physics that has to hit them.**
  `updateRemotes` ran after the fixed-step loop, so every substep resolved
  contact against a frame-old position - about a car length at racing speed,
  all of it in the direction of travel.
