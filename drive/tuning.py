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
CAR_PUSH = 26.0            # how hard cars shove each other apart
CAR_BUMP_SCRUB = 0.93      # speed kept after a car-to-car hit

# --- simulation ------------------------------------------------------------
FIXED_DT = 1.0 / 120.0     # physics step; render interpolates between steps
MAX_STEPS = 8              # catch-up cap so a tab-out cannot fast-forward you
RESPAWN_DELAY = 0.45       # pause after falling before you pop back

# --- timing / medals ------------------------------------------------------
# Medal thresholds are multipliers on the calibrated ideal lap from laptime.py,
# which is tuned to be about what the headless test driver achieves. Author is
# therefore a little quicker than that driver - a lap you have to work at -
# while bronze should fall out of a careful first attempt.
MEDAL_MULT = {
    "author": 0.94,
    "gold": 1.04,
    "silver": 1.18,
    "bronze": 1.42,
}
# A submitted time below ideal * this is not physically reachable and is
# rejected. It has to sit safely below the author time or a genuine author lap
# would be thrown away.
MIN_PLAUSIBLE = 0.80

_EXPORT = [
    "CELL", "ROAD_W", "LEVEL", "CAR_LEN", "CAR_WID", "CAR_HEI", "RIDE_HEIGHT",
    "MAX_SPEED", "ACCEL", "BRAKE", "COAST", "DRAG", "REVERSE_MAX",
    "REVERSE_ACCEL", "STEER_RATE_LOW", "STEER_RATE_HIGH", "STEER_SMOOTH",
    "STEER_RETURN", "DRIFT_STEER_BONUS", "GRIP", "DRIFT_GRIP", "AIR_GRIP",
    "GRAVITY", "AIR_STEER", "AIR_PITCH", "AIR_ROLL", "ALIGN_GROUND",
    "ALIGN_AIR", "COYOTE", "STICK_TILT", "STICK_SPEED", "STICK_FORCE",
    "SNAP", "SUSP", "OFFROAD_DRAG", "OFFROAD_GRIP", "WALL_BOUNCE", "WALL_SCRUB",
    "PROBE", "CAR_RADIUS", "CAR_PUSH", "CAR_BUMP_SCRUB", "FIXED_DT",
    "MAX_STEPS", "RESPAWN_DELAY",
]


def as_dict():
    g = globals()
    return {k: g[k] for k in _EXPORT}


def as_json():
    return json.dumps(as_dict(), separators=(",", ":"))
