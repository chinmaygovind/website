"""Every number that defines how the car feels, in one place.

This module is the **single source of truth** for the simulation constants. The
browser gets them verbatim (``tuning.as_json()`` is embedded in the play page as
``window.DRIVE_TUNING``), and ``laptime.py`` uses the same numbers to simulate an
ideal lap and derive each track's medal times. So retuning the car here
automatically retunes the medals, and there is never a second copy of ACCEL
sitting in a .js file drifting out of sync.

Units are "roughly metres and seconds": a road is 9 wide, a car is 3.4 long,
gravity is 30. Nothing is physically accurate - these are arcade numbers picked
so the car turns in fast and never feels floaty, which is the whole point of the
Polytrack driving model.
"""

import json

# --- world scale -----------------------------------------------------------
# CELL is no longer a grid the track is built on - tracks are continuous ribbons
# (see tracks.py). It survives as the world's unit of length: the collider's
# spatial-hash bucket size, and the scale scenery and the ground plane are laid
# out on.
CELL = 8.0
ROAD_W = 9.0      # default road width; every track section can override it
LEVEL = 3.2       # a convenient "one storey" for authoring heights

# --- car body --------------------------------------------------------------
CAR_LEN = 3.4
CAR_WID = 1.9
CAR_HEI = 1.0
RIDE_HEIGHT = 0.45    # body centre above the surface when resting

# --- longitudinal ----------------------------------------------------------
# Instant response is the single most important thing: full throttle authority
# from a standstill, no torque curve, no clutch. Top speed comes from ACCEL
# fighting DRAG, and BRAKE is deliberately much stronger than ACCEL so trail
# braking into a corner is quick and deliberate.
MAX_SPEED = 50.0
ACCEL = 62.0          # engine force / mass, u/s^2 (before drag)
BRAKE = 78.0          # braking deceleration
COAST = 9.0           # engine braking when off the throttle
DRAG = ACCEL / (MAX_SPEED * MAX_SPEED)   # quadratic drag that caps MAX_SPEED
REVERSE_MAX = 15.0
REVERSE_ACCEL = 30.0

# --- steering --------------------------------------------------------------
# Yaw rate falls off with speed so the car is darty in hairpins and stable flat
# out. STEER_SMOOTH is how fast the steering input itself moves, which is what
# keeps keyboard-only driving feeling analogue instead of binary.
STEER_RATE_LOW = 3.05      # rad/s of yaw at crawling speed
STEER_RATE_HIGH = 1.30     # rad/s of yaw at MAX_SPEED
STEER_SMOOTH = 11.0        # how fast steer input approaches the key state
STEER_RETURN = 15.0        # how fast it recentres when you let go
DRIFT_STEER_BONUS = 1.35   # extra yaw authority while handbraking

# --- grip ------------------------------------------------------------------
# GRIP is how hard sideways velocity is killed each second. High grip = the car
# goes exactly where it points (Polytrack's signature feel); the handbrake drops
# it to DRIFT_GRIP so the back end steps out, and slides recover fast.
GRIP = 13.5
DRIFT_GRIP = 2.4
AIR_GRIP = 0.6             # a little sideways damping in the air, mostly none

# --- air / gravity ---------------------------------------------------------
GRAVITY = 30.0
AIR_STEER = 0.62           # fraction of normal yaw authority while airborne
# Pitch authority and self-levelling in the air are both deliberately lazy. Both
# of them nose the car down: holding the throttle pitches it down directly, and
# levelling toward world up noses a car that took off from an uphill ramp down
# as well. At the old numbers (1.5 and 2.6) a jump taken flat out - which is how
# every jump is taken - was pointing at the floor within half a second of leaving
# the lip, which killed the long, floaty arc that makes a jump worth taking.
# At 0.7 rad/s the nose drops about 40 degrees a second under full throttle:
# plenty to aim a landing over a one-second flight, lazy enough that the car
# keeps the attitude the lip gave it.
AIR_PITCH = 0.7            # rad/s of pitch control in the air (up/down keys)
AIR_ROLL = 2.0             # rad/s of roll control in the air
ALIGN_GROUND = 14.0        # how fast the body snaps to the surface normal
ALIGN_AIR = 1.3            # how fast it levels out while airborne
COYOTE = 0.04              # seconds of grounded grace across a surface seam

# Letting go of the road.
#
# The car is only held onto a surface steep enough that nothing else could hold
# it there: the wall and the roof of a corkscrew. STICK_TILT is that threshold as
# a dot product with world up. 0.85 is about 32 degrees, and it is chosen to sit
# *above* every hill and bank in the track pool (the steepest hill peaks near
# 0.94, the steepest bank at 0.96) and below a corkscrew's wall, so ordinary
# slopes get no help at all and the car flies off their crests exactly like
# Polytrack's does. Past the threshold the pull ramps in smoothly.
#
# On a corkscrew's wall, gravity contributes nothing toward the axis, so this
# force alone is the centripetal budget: it has to beat v^2/R. The pool's
# tightest loop is radius 20, so at MAX_SPEED that needs v^2/R = 125 - hence 150,
# which leaves a margin rather than sitting exactly on the limit. `laptime.py`
# caps corkscrew speed at sqrt(R * STICK_FORCE) so the medal times assume only
# what the car can actually hold.
STICK_TILT = 0.85
STICK_SPEED = 15.0         # below this the pull fades out - too slow, you fall
STICK_FORCE = 150.0        # centripetal budget on a wall or a roof

# Suspension. SNAP is the gap between the wheels and the road that still counts
# as grounded - a seam tolerance, nothing more. It used to be a full unit, which
# quietly glued the car to every crest; at 0.12 a crest throws you, which is the
# point. SUSP is the spring that closes that small gap, soft enough that it never
# yanks.
SNAP = 0.12
SUSP = 45.0

# --- surfaces --------------------------------------------------------------
# Grass has to cost you the corner, not just tickle it. OFFROAD_DRAG is a linear
# term, so the grass top speed is where ACCEL - quadratic drag - OFFROAD_DRAG*v
# reaches zero: at 1.8 that is about 24 u/s, half of MAX_SPEED. It used to be
# 0.55, which put the grass top speed at ~36 - close enough to the road's that
# cutting a corner across the infield was simply faster than driving round it.
OFFROAD_DRAG = 1.8         # linear speed scrubbed per second on grass
OFFROAD_GRIP = 5.0
WALL_BOUNCE = 0.22         # normal velocity kept when you clip a wall
WALL_SCRUB = 0.86          # tangential speed kept per wall hit

# --- collision -------------------------------------------------------------
PROBE = 2.6                # how far to look for a surface under the car
CAR_RADIUS = 1.25          # collision sphere for walls and other cars
CAR_PUSH = 32.0            # how hard cars shove each other apart
CAR_BUMP_SCRUB = 0.88      # speed kept after a car-to-car hit
CAR_REST = 0.35            # normal velocity returned by a hit; barely bouncy

# --- what a hit does -------------------------------------------------------
# Contact used to be decided by one number - a single `hit > 5` in
# `Car.resolveCars` - and that one number was doing two unrelated jobs. Below it
# a contact was *completely* silent: no clank, no sparks, no camera, no lean. So
# running wheel to wheel down a straight, which is most of what contact in a
# race actually is, both looked and sounded like driving alone. Above it a
# contact cost speed. Those are two questions and they want two answers:
#
# - **`BUMP_FEEL` is when you are told.** Low, because there is no such thing as
#   a touch that should not register on the driver. `Sound.bump(mag)` already
#   scales its pitch and level off the magnitude, so the same call covers a
#   scrape at 2 and a bang at 20 with nothing new written.
# - **`BUMP_COST` is when it hurts**, and it is deliberately today's number,
#   unmoved. The per-pair cooldown is 0.15s, so a second and a half of gentle
#   rubbing is about ten events; charging each of them speed compounds to a
#   tenth of it gone for touching somebody lightly, which is the trap the note
#   on CAR_BUMP_SCRUB is about. Rubbing is heard and free; a hit is heard and
#   expensive.
BUMP_FEEL = 1.5            # closing speed that is seen and heard
BUMP_COST = 5.0            # and that also costs speed, yaw and grip

# **A hit has to let the tyres go, or it does not move the car at all.**
#
# This is the whole of why bumping felt weightless, and it is not a number that
# was too small - it is that GRIP kills lateral velocity at
# `1 - exp(-GRIP*dt)` per step, so *any* sideways impulse is gone inside a tenth
# of a second. Measured: a 14 u/s side-swipe moved the car 0.26 units, and
# raising the restitution and the push spring moved it 0.25. The car is bolted
# to its heading and no impulse gets to argue with that.
#
# So a firm hit briefly unsettles the car instead, which is also what a shunt
# does to a real one: grip falls toward BUMP_SLIP_GRIP - about halfway to
# DRIFT_GRIP, the handbrake's own - and recovers over BUMP_SLIP_TIME. The same
# 14 u/s swipe now moves the car 0.84 units and a 20 u/s punt 1.47, which
# against a 1.9-wide car and a 9-wide road is a place lost rather than a noise.
#
# **Neither number is scaled by how hard the hit was**, and the instinct to
# scale them is wrong twice over. The impulse the let-go tyres are letting
# through is already proportional to the hit, so scaling the window on top of it
# squares the relationship and a firm-but-ordinary shunt comes out moving the car
# less than the same shunt would on full grip - which is the opposite of the
# point. One window, one depth, and the physics does the scaling: 0.39 units of
# displacement at 6 u/s, 0.84 at 14, 1.47 at 20.
#
# Yaw authority is deliberately **not** part of this. A whisper of it is applied
# on a side hit so contact reads as a nudge, and it stays a whisper: a car that
# spins because somebody leaned on it turns the race into a demolition derby,
# and everything above is about being moved off your line, not off the track.
BUMP_SLIP_GRIP = 4.0       # grip while the tyres are let go (GRIP is 13.5)
BUMP_SLIP_TIME = 0.45      # seconds to recover it, scaled by the hit

# --- slipstream ------------------------------------------------------------
# Sit in the hole another car is punching through the air and, after a moment,
# you are fired out of it - Mario Kart Wii's draft, which is the version of this
# everybody already knows how to use. Two decisions matter:
#
# - **It charges, then it pays.** Being in the tow gives you nothing at all
#   while SLIP_CHARGE seconds go by; then the whole of it arrives at once as a
#   burst of engine force. A trickle of extra speed for following somebody is
#   invisible and unearned; a boost you waited for is a move you planned.
# - **The boost is more engine, not a higher speed limit.** Top speed is where
#   ACCEL fights the quadratic DRAG, so multiplying the throttle term by 1.5
#   raises it by sqrt(1.5) - about 22%, MAX_SPEED 50 -> 61 - and gets you there
#   with a shove rather than teleporting the needle. It applies on the throttle
#   only: a tow is a bigger top end, not free speed while you coast.
#
# The corridor is deliberately narrow and short. A tow that reaches half the
# straight makes following the correct way to drive; at 26 units (about eight
# car lengths) you have to be committed to the car in front.
SLIP_RANGE = 26.0          # how far back the tow reaches
SLIP_HALF_W = 3.6          # half-width (and half-height) of the tow corridor
SLIP_ALIGN = 0.65          # min dot(my fwd, their fwd): you must be following them
SLIP_MIN_SPEED = 22.0      # no tow at a crawl - there is no hole to sit in
SLIP_CHARGE = 1.5          # seconds in the tow before it pays out
SLIP_DECAY = 1.6           # seconds for a full charge to bleed away once you leave
SLIP_BOOST = 1.6           # seconds the boost lasts
SLIP_ACCEL_MULT = 1.5      # engine force while boosting; top speed x sqrt(1.5)

# --- boost pads ------------------------------------------------------------
# A strip of road that hands you speed for driving over it. It is the same kind
# of help the tow is, so it is the same kind of term: **more engine, not a
# raised limit**, on the throttle only. PAD_ACCEL_MULT 1.7 lifts top speed by
# its square root, 50 -> 65, and the car has to accelerate up to it.
#
# The interesting decision is what happens when a pad and a tow are on at once.
# They must **not** multiply. Pad x slip x catchup is 3.4 times the engine,
# which is 92 u/s against a hard velocity clamp of MAX_SPEED * 1.7 = 85 - and
# then the clamp is setting the top speed instead of the tuning, which is the
# exact failure the catch-up boost's own note is about. So the pad and the tow
# take **the larger of the two**: a tow is earned by sitting in somebody's air
# for a second and a half, a pad is the track's and is given to everybody who
# drives over it equally, and multiplying them makes a pad worth most to the car
# that was already being helped. Catch-up still stacks on top, as it does with a
# tow, which lands at 75 u/s - under the clamp with room to spare.
#
# PAD_BOOST is short on purpose. A pad is a moment, not a state: long enough to
# carry you down a straight or into a corner you would otherwise have lifted
# for, short enough that where the pad is remains a decision about the line.
PAD_BOOST = 1.3            # seconds the boost lasts after leaving the pad
PAD_ACCEL_MULT = 1.7       # engine force while boosting; top speed x sqrt(1.7)

# --- catching up -----------------------------------------------------------
# A race where somebody drops three seconds is over, and everyone still in it
# spends the rest of the lap driving alone. So a car behind the leader gets a
# little more engine, in proportion to how far behind it is. Four decisions:
#
# - **The gap is measured in seconds, not in metres.** Distance along the ribbon
#   is what the room actually knows about every car (it is `prog` on the wire),
#   but the same 100 units is half a lap of Chicane Park and a corner of Sandy
#   Cove. Dividing by MAX_SPEED turns it into the one thing that means the same
#   on every track: how long it would take you to make that ground up flat out.
#   It is a *floor* on the real gap - nobody averages MAX_SPEED - so 1.5 here is
#   about two seconds of driving, which is the point at which a race stops being
#   one.
# - **Nothing at all inside the deadzone.** Under CATCHUP_DEAD you are still
#   racing the car in front and the last thing that should decide it is a
#   handout. Past it the help ramps in linearly and reaches all of itself at
#   CATCHUP_FULL - about seven seconds of real driving, which on any track in
#   the pool is most of a corner and change.
# - **More engine, not a raised limit**, the same way the slipstream is: top
#   speed is where ACCEL fights the quadratic DRAG, so the multiplier lifts it
#   by its square root and the car has to accelerate up to the new one. It
#   stacks with a tow, because a car eight seconds down that has finally caught
#   somebody is exactly the car that should be able to make the pass, and the
#   pair of them still lands under the MAX_SPEED * 1.7 clamp (71 against 85) -
#   or the clamp would be setting the top speed and this would be decoration.
# - **Full help is 180 on the speedo**, which is where the number comes from:
#   the HUD draws speed x 3.1, so 1.3486 puts the top of the ramp on exactly
#   that. It was 1.22, which read 171 against a base of 155 - a lift you could
#   not feel from inside the car, which is a poor way to spend a mechanic.
#   That does make it worth **more than half a tow**, which it deliberately was
#   not before, on the grounds that being handed the bigger of the two would
#   make dropping back the fast way round. It does not: collecting the whole of
#   this means actually *being* five seconds down, and five seconds costs far
#   more than 8 u/s of top end pays back. The tow is still the better move and
#   still the one you plan; this is the one that keeps you in sight of it.
# - **Nothing is taken off the leader.** A rubber band that slows the car in
#   front takes away the race it is trying to create; this only ever gives, so
#   the driver in the lead is driving the same car they qualified.
CATCHUP_DEAD = 1.5         # seconds of gap that are worth nothing
CATCHUP_FULL = 5.0         # gap at which the whole of it is on
CATCHUP_ACCEL_MULT = 1.3486  # engine at full help; top speed 50 -> 58.1 (180 on the dial)
CATCHUP_SMOOTH = 2.5       # how fast the help follows the gap, per second

# --- simulation ------------------------------------------------------------
FIXED_DT = 1.0 / 120.0     # physics step; render interpolates between steps
MAX_STEPS = 8              # catch-up cap so a tab-out cannot fast-forward you
RESPAWN_DELAY = 0.45       # pause after falling before you pop back

# --- timing / medals ------------------------------------------------------
# Medal thresholds are multipliers on the calibrated ideal lap from laptime.py,
# which is tuned to be about what the headless test driver achieves.
#
# **These are set against real times, not against the estimate.** They used to
# be 1.04 / 1.18 / 1.42, which was calibrated off the simulated driver and was
# far too soft: every record actually set on the site sits between 0.77 and
# 0.90 of `ideal` (mean 0.85), so a 1.04 gold was a quarter of a minute-lap
# slower than what people were already driving, and bronze at 1.42 could not be
# missed. The spread was the other half of the problem - gold to silver was
# 2.8-5.7s and silver to bronze 4.8-9.7s, so the three medals described three
# unrelated standards rather than three steps of the same one.
#
# Gold is now a lap you have to nail: beaten by the standing record on every
# track, but only just on the tightest (Spiral Ascent, by 0.4s). Silver and
# bronze follow about a second and a half behind it on the short tracks and
# three on the Gauntlet - the gap is a fraction of the lap rather than a fixed
# number of seconds, because a longer track has proportionally more places to
# lose the time.
#
# Note `ideal` is a *worse* per-track predictor than the mean suggests (0.77 on
# Chicane Park against 0.90 on Spiral Ascent), so one global multiplier makes
# some tracks' golds harder than others. Fixing that means improving
# `laptime.py`'s estimate, not adding per-track fudge factors here.
#
# **Gold is the best medal and there are three of them.** There used to be a
# fourth above it, "author", at 0.94 of the ideal lap. Nobody could tell what it
# meant from the game - the word names an authority, not a standard, and it sat
# above a medal everyone already reads as the top one. Three medals that
# everyone understands beat four where the best one needs explaining.
#
# A medal already earned is not taken away: `DriveTime.medal` is written when
# the run is stored, so tightening these only applies to laps driven from here
# on - the same way nobody's medal moved when `author` was retired.
MEDAL_MULT = {
    "gold": 0.92,
    "silver": 0.99,
    "bronze": 1.07,
}
# There is deliberately no lower bound on a submitted time. `ideal` is an
# estimate off a relaxed racing line, not a limit, and it is beatable by anyone
# who has learned the track - so a floor derived from it rejected good laps for
# being good. What a run has to survive is in `runcheck.validate`, and all of it
# is about the replay rather than the number.

_EXPORT = [
    "CELL", "ROAD_W", "LEVEL", "CAR_LEN", "CAR_WID", "CAR_HEI", "RIDE_HEIGHT",
    "MAX_SPEED", "ACCEL", "BRAKE", "COAST", "DRAG", "REVERSE_MAX",
    "REVERSE_ACCEL", "STEER_RATE_LOW", "STEER_RATE_HIGH", "STEER_SMOOTH",
    "STEER_RETURN", "DRIFT_STEER_BONUS", "GRIP", "DRIFT_GRIP", "AIR_GRIP",
    "GRAVITY", "AIR_STEER", "AIR_PITCH", "AIR_ROLL", "ALIGN_GROUND",
    "ALIGN_AIR", "COYOTE", "STICK_TILT", "STICK_SPEED", "STICK_FORCE",
    "SNAP", "SUSP", "OFFROAD_DRAG", "OFFROAD_GRIP", "WALL_BOUNCE", "WALL_SCRUB",
    "PROBE", "CAR_RADIUS", "CAR_PUSH", "CAR_BUMP_SCRUB", "CAR_REST",
    "BUMP_FEEL", "BUMP_COST", "BUMP_SLIP_GRIP", "BUMP_SLIP_TIME", "FIXED_DT",
    "MAX_STEPS", "RESPAWN_DELAY",
    "SLIP_RANGE", "SLIP_HALF_W", "SLIP_ALIGN", "SLIP_MIN_SPEED", "SLIP_CHARGE",
    "SLIP_DECAY", "SLIP_BOOST", "SLIP_ACCEL_MULT",
    "PAD_BOOST", "PAD_ACCEL_MULT",
    "CATCHUP_DEAD", "CATCHUP_FULL", "CATCHUP_ACCEL_MULT", "CATCHUP_SMOOTH",
]


def as_dict():
    g = globals()
    return {k: g[k] for k in _EXPORT}


def as_json():
    return json.dumps(as_dict(), separators=(",", ":"))
