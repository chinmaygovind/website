# Drive: the room's bots

Read this before changing `bot.js`, `botworld.js`, `botsim.py`, `bots.py`,
`tools/hotlap.py`, `tools/calibrate_bots.py`, or the bot seats in a room.

**The problem they exist for is not "single player".** A two-car race is decided
the moment somebody drops three seconds: from there both drivers are alone on
the road, and the slipstream and the catch-up boost - the two mechanics built
precisely to keep a race alive - have nothing to work with, because both of them
need a car in front. A field fixes that. With six cars of mixed ability on the
road there is always somebody's air to sit in, and a lap you lost is a lap you
can get back by picking your way through traffic. That is why the levels are
*mixed* rather than uniform, and why "fill the grid" exists.

- **A bot is an ordinary seat.** `DrivePlayer.is_bot`, a name, a colour, a place
  in the roster, a row in the standings, frames in the stored replay, and the
  same `×` next to it that kicks anybody else. Everything downstream of a pose
  treats it as a car because it *is* one - it is only the thing pressing the
  pedals that differs.
- **And an ordinary car.** Not a scripted mover: a real `Car` from `physics.js`
  stepped by the real `Car.step` at the real `FIXED_DT`, in a QuickJS runtime
  holding the same `trackmesh.js`, `course.js` and collider the browser has. So
  contact, walls, boost pads, the slipstream, the catch-up boost and respawning
  are not implemented here at all. They are what the car already does.
- **They run on the server, not in the host's tab**, and the first of the three
  reasons is fatal on its own: `requestAnimationFrame` is throttled to a stop in
  a background tab, so the whole field would freeze for everybody else the
  moment the host looked at something else - and the host is the one person who
  cannot be asked not to. The other two: bots would arrive on every other screen
  a round trip late *and* see everybody a round trip late, so an overtake would
  be aimed at where you were 60ms ago; and the host would be authoring the
  position of eight cars nobody can check. See `botsim.py`'s preamble.

## The line is the skill, not the throttle

The single most important thing in here. A level is mostly **which line it
drives**, and only secondarily how hard it pushes.

- **Easy and medium** drive `laptime.py`'s relaxed centreline - minimum
  curvature, clamped to the road, the same line the medal times are cut from.
- **Hard and max** drive a lap **a person actually set**, pulled off the board by
  `tools/hotlap.py` and stored in the track's own folder as `hotlap.json`.

That split exists because of a measurement. Driven flat out on the relaxed line,
the best the driver manages is a second or two *outside* gold on half the pool -
while the records sit at 0.74 to 0.89 of `ideal`, ten and eleven seconds inside
gold on Rainbow Road and Big Red. The difference is not throttle. It is which
kerb to stand on, how late to brake, what to do in the air - Big Red's record is
airborne for **28%** of the lap - and above all the four tracks whose records are
won by **jumping clean across a loop**. No relaxation of a centreline will ever
find that, because the line it is relaxing goes round.

### Which records the bots are allowed to copy

A judgement about the game, so it is a table a person edits
(`CUT_LIMIT`/`CUT_POLICY` in `tools/hotlap.py`) rather than something measured.
Most cuts in this pool are simply the quick way round and are kept - Twin Loop,
Rainbow Road and Cloudbreak are each won by jumping a loop, and those are worth
learning, so a rival that does them is a rival worth racing. Two are not, and
they want different treatment:

- **Gauntlet** rides the rail from the second checkpoint to the loop, cutting
  198 units out. The trick *is* the lap, so there is no keeping the rest of it:
  the tool walks down the board and takes the fastest lap that does not do it.
- **Big Red's loop skip** (202 units, the biggest of its four cuts) is the same
  kind of trick, but the rest of that lap is worth copying. So it is **spliced**:
  that one stretch is replaced by the ordinary way round off the relaxed line,
  the other three jumps - 61, 65 and 68 units - are kept, and the lap time is
  recomputed from the result, because the recorded one describes a lap this no
  longer is.

### Jumps have a speed *floor*, not a target

This is what makes a pace multiplier safe at all. Those loop-crossing jumps all
launch at 47-49 u/s. Scale a record down by the 7% that separates it from a gold
and the car arrives at the lip at 44, does not reach the other side, and the
"hard" bot spends the race respawning. So `hotlap.json` carries a `vmin` per
point: over the last 45 units before any takeoff the recorded speed is a floor
the pace is not allowed to scale, and the pace only applies above it. The wander
is switched off there too - at a lip the takeoff velocity is the only thing that
decides where you land, and two units off the line came out **9 degrees** off the
record's velocity vector, which over 1.5s of flight is the far side of the gap.

## The handbrake is how a corner is taken, not a last resort

The largest single thing separating the quick levels from the records, and it
came from the person who set most of them: *tap the handbrake once or twice
through a corner*. Jump City and Cloudbreak are the clearest examples.

It is not a style choice, it is the physics. The car yaws at exactly
`steerRate(speed) * steer` and the handbrake multiplies that by
`DRIFT_STEER_BONUS` - **35% more yaw authority** - while `DRIFT_GRIP` lets the
rear step out so the car rotates while it keeps its speed. So a corner that
needs more yaw than `steerRate(v)` can give is one the car **cannot** hold at
that speed on steering alone, whatever it is asked for. That is a computable
condition and it is the trigger:

    need = v * curvature   against   have = steerRate(v)

Which is also the answer to a question that had been open all day: why a bot
copying a record's *speeds* washed out to the kerb in every corner while
matching it on every straight. It was being asked for a radius the front axle
cannot produce, because the lap it was copying was driven with a technique it
did not have.

Two details matter. It is a **tap** (`TAP_MAX`, then `TAP_GAP` before another) -
held down, `DRIFT_GRIP` is 2.4 against a normal 13.5 and the corner is lost the
other way. And it **does not touch the pedals**: the first version zeroed the
brake while the handbrake was down, on the theory that braking mid-drift spins
the car, which nothing in `Car.step` does - so all it achieved was removing the
braking at the exact moment a corner needs it, with the grip gone too. Every
track DNF'd.

### It was dead for its whole first life, and nothing said so

`BotLine._curvature()` was called from the constructor **three lines before
`this.total` was assigned**. `span` is `this.total / (n - 1)`, so it was `NaN`,
so `stride` was `NaN`, so `for (let i = stride; i < n - stride; i++)` was false
on its first evaluation and the loop never ran once. `kap` kept the zeroes it
was filled with. Every corner on every track read as dead straight, `wantsDrift`
returned 0 always, and **the handbrake never fired - on any level, on any track,
for the entire time it existed.**

It cost nothing and crashed nothing, which is exactly why it survived: the only
symptom was the quick levels running wide in corners while matching on the
straights, and that is also just what a mediocre driver looks like. The tell was
an A/B of four drift thresholds - one of them set impossibly high to mean *off* -
coming back **identical to the digit**. That is the third bug in this file found
by that same signature, the others being a profile key that silently overwrote a
`prof.tune` override one line after the merge, and a renamed gain still read
under its old name. **When a knob measures identically across its whole range,
the finding is not "this makes no difference" - it is "this is not connected".**

With it connected, the threshold matters more than it looks. `need > 1.0` is the
principled line, because that is where the front axle physically cannot produce
the radius and grip spent below it is grip wasted. Measured over the hot laps,
demand runs p50 ≈ 0.4, p90 ≈ 1.0, p97 ≈ 1.2-1.6, max ≈ 1.3-2.2 - so the
originally-guessed `driftOn` of 0.92 fires *under* the tyres' own limit, roughly
one station in eight. That is not "once or twice through a corner", and on
Skyline it was worth eleven respawns in a lap.

## The steering gain was too low by a factor of three

`TUNE.steer` is radians of heading error per unit of steering, it was set to
**2.2** by eye when the driver was first written, and it was never swept. It
should be **6.0**. Swept across eight tracks, lap time improves *monotonically*
all the way there with no exceptions:

    steer     sunrise  chicane    eight   spiral    twist  jumpcity
    2.2         19.33    15.42    18.00    22.42    22.67    respawn
    3.5         17.63    15.27    17.60    21.98    22.40      22.65
    6.0         17.43    15.08    17.38    21.65    22.17      22.44
    8.0         17.50    14.97      DNF    21.42    22.07      22.38

6.0 is the knee rather than just the largest value tried: at 8.0 Eight stops
finishing and Sunrise turns back up, which is the pursuit loop starting to
overshoot.

**This one constant was most of the difference between the bots being adequate
and being quick.** Over the pool it moved `max` from 0.6% under gold to **5.6%
under**, from beating gold on nine tracks to fifteen, and from 11.5% off the
records to **5.2%**. Hard went from 1.6% over gold to 2.7% under.

It also made **Cloudbreak** finishable. That track is the pool's narrowest with
almost nothing at its edges, and a car that converges on the line this slowly
simply runs out of road: at 2.2 it fell into the void at the same place every
lap, nineteen respawns and a DNF at any pace on either line; at 3.0 it went
round clean in 58s. It had been the worst track in the pool by a distance
(+19.8% over gold) and is now +1.2%.

**Why it hid for so long.** The failure it caused was "runs a bit wide", which
is indistinguishable from a merely mediocre driver, and it never crashed
anything. Every other theory got tested first - the reference lines, the jump
speed floors, the handbrake, the pace ceiling, the brake planner. The diagnosis
that finally landed came from tracing one car's state per tick rather than
reasoning about it: grounded at 48 u/s at station 82 of Cloudbreak, airborne at
83, then falling continuously to y = -63.5 while the station index crept from 83
to 105 and the line stayed level at y ≈ 9. Not a missed jump - driving off the
edge. `botLap` returns `gaveUp`, `fell` and an optional `trace` now so the next
one of these is one run instead of five guesses.

## Sandy Cove, and why one track needed its own gain

Cove was the last track whose recorded line could not be driven, and it is worth
writing down because the cause was nothing like Cloudbreak's and three plausible
theories were wrong before the right one.

The bot tracked the descent **perfectly** - inside half a unit of the line, 1.3
units laterally - and then, at the bottom, kept going:

    station   carY   lineY     dY    off      v   grounded
    88        10.3     9.8   +0.5    1.4   51.6   AIR      <- reference lands at 91
    90         8.1     7.6   +0.5    1.5   52.8   AIR
    91         6.5     8.4   -1.9    2.1   53.7   AIR      <- shelf is at 8.4; bot is under it
    95         0.4     8.4   -8.0    8.2   57.0   AIR
    96        -0.7     8.4   -9.1    9.2   47.3   grnd     <- the beach
    102       -0.7     8.4   -9.1    9.3   29.0   grnd     <- off-road drag, and falling

The reference is airborne for stations 82-90 and lands on the shelf. The bot flew
82-**96**, half again as long, and put itself nine units below the road on the
sand, where `OFFROAD_DRAG` bled it from 57 u/s to 26 and `FELL_BELOW` respawned
it - **36 times, always at station 100**.

The cause is `lookAir`, how far up the road it aims while flying. At the pool
default of 26 the aim point on a descent is a long way *below* the car, and
`AIR_PITCH` holds that as nose-down for the whole flight, so it glides out flat
and overshoots what it was coming down onto. At 8 it lands with the record:
**56.25s, no respawns**, against 58.48s on the safe line - and +2.3% on the
record where the fallback was +6.4%.

**It is in `bots.TRACK_TUNE` rather than in `TUNE`, and that was measured.** Big
Red is 28% airborne over four long jumps and picks up a respawn at any `lookAir`
below 26; there the long aim is the point. Cove is the only track in the pool
that wants the short one.

Three things that were tried first and did nothing, all disproved by an A/B that
came back identical to the digit: exempting flight from the `lost` respawn check;
lifting the throttle when already below the road ahead (the pedals in the air are
pitch, but the pitch follows the *aim*, not the pedal); and every value of
`brakePlan`. The trace in `botLap` is what ended it - `opts.trace` returns
station, speed, target speed, height, line height and off-line distance per tick
up to the first respawn, and the answer was visible in one run.

## Pace is exhausted as a lever, and that is the ceiling on `max`

**Measured before `TUNE.steer` was fixed, and the conclusion it reached - that
`max` was at a competence ceiling no calibration could lift - was wrong.** It
was a real measurement of a badly-steered car: too lazy on the line to hold a
corner, so extra speed only ran it wider. The mechanism below is still true and
still worth knowing (a pace above what the car can hold is slower, not faster),
but the ceiling it found was an artefact and moved a long way when the constant
above changed. Re-measure before quoting any number in this section.


`pace` scales the speed target off the reference trace, and the obvious way to
make `max` quicker is to raise it. **It does not work, and it is worth knowing
why before trying it again.** Swept over six tracks at 1.02, 1.10, 1.20, 1.35 and
1.50, asking for more speed made the bot *slower*:

    pace      chicane  skyline    eight  heights      spa mountjoy
    1.02        15.55    19.03    19.13    20.75    61.67    62.20
    1.10        16.30    19.02      DNF    20.53    61.43    62.17
    1.20        17.30    19.02      DNF    20.65    61.30      DNF
    1.50        18.85    19.02      DNF    20.75    61.25      DNF

Chicane degrades monotonically - a full 3.3 seconds worse at 1.50 - because the
extra speed is carried into corners the car then cannot hold, and every corner
exit starts further off line than the last. Skyline does not move at all, which
is the benign case: the bot is already flat out there, so a higher target changes
no input. Eight and Mount Joy simply stop finishing.

So `max` at pace ~1.02 is **at the driver's competence ceiling, not at a tuning
limit**, and the ~11.5% it still gives up to the records is a driving problem.
The calibrator cannot close it and neither can `paceMax`. The levers that remain
are the ones that make the car go round a corner better - the handbrake above
being the first of them - and the lines themselves on the tracks where the hot
lap is still undrivable.

## Things learned the hard way in the driver

Each of these was a real failure and each is cheap to reintroduce.

- **The reference lap's standing start is not a speed limit.** Both lines are
  recordings of a lap that began from rest, so `v[0]` is zero. Read as a limit -
  which is the only way the driver uses it - that says "you may do 0 u/s on the
  start line", and the bot brakes, sits still, is declared stuck, takes the
  checkpoint, arrives back on the line and does it again. Forty-one times a lap,
  on every level at once, in complete silence. `BotLine._unLaunch` flattens the
  leading climb; `CRAWL` is the belt-and-braces floor underneath it.
- **Below the target the throttle is wide open.** A proportional controller that
  eased off near the target cannot hold it: the reference speed down a straight
  is the speed where `ACCEL` balances `DRAG`, so *holding* it takes full
  throttle. That one was worth a second a lap and left the quick levels 13%
  slower than the record they were copying.
- **A curvature feedforward is the obvious idea and it is not in the code.**
  The car yaws at exactly `steerRate(speed) * steer`, so the lock a corner needs
  is exactly `v * k / steerRate(v)` - computable rather than chased, with no
  lag. Measured twice: added on top of the aim point it was worse on five tracks
  of seven (pursuit toward a point on a curve is *already* a request for that
  curve's lock, so the corner was asked for twice and Spiral Ascent went from
  23s to two minutes); and with the aim point replaced entirely by heading and
  cross-track feedback it was worse again, because the aim point is what makes
  the car *converge* on the line and error feedback at any stable gain did not.
  The curvature is still computed - it is what the handbrake trigger reads.
- **Landing off-line is worth more than cornering.** Traced down Sunrise, the
  bot matched the record within 1 u/s everywhere except twice, and both were
  immediately after a flight: cross error growing from 4.7 to 9.2 units *during*
  the jump, a landing on the grass, and 47 u/s becoming 24 - which is exactly
  the grass top speed. In the air the car is a thrown object, so whatever
  sideways velocity it left the lip with it keeps; `straighten` closes that on
  the run-up and nowhere else. **Small gains**: at 6.0/0.10 it cost 1.5s on
  Sunrise and DNF'd Spiral, because a hard correction into a lip is its own way
  of missing one.
- **Cross-track correction is measured harmful, and it is not in the code.**
  Pure pursuit does not hold a line, it holds a course toward a point on one, so
  a standing error of a couple of units is real and it is genuinely fatal at a
  jump. Correcting it everywhere is worse: 27 combinations of gains over four
  tracks, and every non-zero value lost time, with the largest DNF'ing two
  tracks outright - the aim point and the correction disagree in a corner and
  the car saws. It survives only on jump run-ups, where the car is straight.
- **Vectors are `Vector3`s, not arrays.** `car.up[2]` is `undefined`, which makes
  a lateral offset `NaN`, which makes the steering `NaN`, which makes the car
  cease to have a position. It was invisible for one tick because a car is
  briefly airborne at spawn and takes the other branch.
- **Everything is in the car's own frame.** Heading error is a dot product with
  the body's `right`, not an angle in plan view, which is why one line of code
  drives a loop, a corkscrew and a banked wall with no special case. The old
  test autopilot in `tests/driver.js` works in plan view and needs a hand-written
  exception for each.

## Levels, and what they are worth

`bots.py` owns the policy; `bot.js` knows nothing about what "hard" means.

    easy    bronze
    medium  silver
    hard    most of the way from gold to the record (HARD_MIX)
    max     the record

Set against times on the board rather than against the medals, because the
medals are the wrong yardstick for this: every record on the site is 0.74-0.89
of `ideal` and gold is 0.92, so a "hard" bot pinned to gold is beaten by anybody
who has learned the track.

**One pace multiplier cannot deliver that across the pool** - the same value is a
silver on one track and worse than bronze on another - so it is solved per track
per level by `tools/calibrate_bots.py` and stored in `bots_pace.json`. Re-run it
when the car is retuned, when a track's geometry moves, or when `hotlap.py`
picks up a new record. Nothing detects a stale table, exactly like the track
previews; what a stale one costs is a level being a second off the medal it is
named for.

**Hard and max have different pace ceilings, and that is what keeps them
different levels.** Both are aimed at times the driver cannot quite reach - max
at the record itself - so with one ceiling the search simply pins both at the
top and the two come out identical on every track: four levels pretending to be
four, and only three of them real. Capping hard lower (`paceMax` in `bots.py`)
costs it its target on the handful of tracks where it could have hit it, and
buys the only thing a player can actually see, which is that max is always the
quickest car in the room.

**And the ordering is a constraint, not a hope.** Each level is fitted to its own
target independently, so nothing in the solve stops one overtaking another - and
it did: Sunrise came out with max at 18.50 against hard at 17.88, and Cloudbreak
with hard five seconds slower than its own medium. `enforce_order` walks the
levels afterwards and gives any that is not quicker than the one below it more
pace until it is, or failing that its neighbour's settings - a tie reads as
"much the same", where an inversion reads as broken.

**The calibrator also records which line it managed it on**, and that is a
measurement rather than a policy: where the driver cannot hold the quick line on
a track, the entry says `relaxed` and the bot drives the safe one there. Getting
round is not the bar - Gauntlet's quick line "completed" in 51.88s against a
target of 36.23, which is a car crawling home after falling off - so a result
more than 5% out, or with a crash in it, sends the calibrator to the other line
and the closer of the two wins. Improving the driver and re-running is what takes
a fallback away again.

## What a bot must never touch

- **ELO, wins and podiums.** True by construction: a bot has no `user_id`, and
  `_rate_race` ranks the accounts among themselves - the same door a guest comes
  through. A test pins it anyway, because the property is inherited rather than
  written down in the rating code.
- **The leaderboard.** Two independent rules already say so: no room lap reaches
  a board, and a bot has no account to hang one on.
- **The anti-cheat.** `_judge_race` skips them. Every rule in `racecheck` asks
  whether a *client* could have driven what it claims, and there is no client -
  the poses are the server's own simulation of the server's own car. They would
  also fail it, because the quick levels drive a line that jumps across a loop,
  which is exactly the shape the corridor check is looking for.
- **A room's liveness.** Bots report a pose thirty times a second for as long as
  the pump runs, so `_pump` and `_stale_cleanup` both ask `_humans` and never
  `_live`. Without that a deserted room keeps its pump, its world and any race
  it was in the middle of alive for ever, and `_drop` closes a room the moment
  the last *person* leaves.

## Seats, and the room

- Host only, and **between races only** - the same gate the track and the
  qualifying switch use, for the same reason: adding a car to a grid that is
  already lit changes what everybody is in the middle of.
- `add_bot` seats one at the chosen level; `fill_bots` fills the grid. The level
  rides on the button so a mixed field is one press per car.
- **A person takes a bot's seat.** A room that has filled its grid with bots is
  not full in any sense that should keep somebody out - they are only there
  because nobody else was - so `join` stands the weakest one down. Weakest and
  not newest: the field is there to race and the easy one is the least of it.
- Bots are placed on the grid by the same `_start_grid`/`_reverse_grid` that
  orders everybody else, they set qualifying times, and **a bot on provisional
  pole hands its lap to the room as the ghost to chase** - which on a max bot is
  the most useful target in the room, since it is the record's own line, driven.
  `runcheck.leaves_course` is deliberately not applied to it: that check is there
  to stop a *client* fabricating a ghost, and this one came from the room's own
  simulation.

## What it costs, and the switches

Measured on a laptop, eight bots with contact, tows and the JSON crossing:
**4.6-7.0 ms per 30Hz tick** and about **30-50MB** of RSS for the runtime plus one
built track. Both land on the single eventlet worker that also relays every
pose, on a box with about a gigabyte across five services - so:

- `MAX_BOTS` (7) caps a room.
- **`DRIVE_BOTS=0`** in the box `.env` turns the whole thing off without a
  deploy, and the host's controls are not drawn where they would do nothing.
- Built tracks are shared between rooms on the same track; the collider is by
  far the biggest thing here and is read-only once built. **They are also
  dropped when no room needs them** (`forget_unused`, two kept in reserve): one
  is 20-40MB and `BUILT` is keyed by slug, so without that a service which has
  hosted a room on every track accumulates all sixteen. Not theoretical - the
  calibrator builds the whole pool in one runtime and was killed partway
  through, with no traceback, which is what being killed looks like.
- `botsim.tick_ms()` reports the rolling cost, so the box can be measured rather
  than guessed about.
- A world that throws is dropped rather than taking the room with it: the seats
  stay, the cars stop appearing, and the race carries on for the people in it.

## The tools

    python tools/hotlap.py                    # refresh the fast lines off the board
    python tools/bot_names.py                 # regenerate bot_names.txt
    python tools/calibrate_bots.py            # solve every level on every track
    python tools/calibrate_bots.py --report   # drive as configured, print the misses
    python tools/calibrate_bots.py --sweep    # grid over the driver's gains

`--sweep` is how a change to any gain in `bot.js` is judged: drive the pool, add
up the gap to each record, print it. The gains are not matters of taste - the
wrong lookahead runs the car wide out of corners and lands it on the grass after
every jump - so they are measured, and the numbers in `TUNE` are what the
measurement said.
