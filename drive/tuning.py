"""Every number that defines how the car feels, in one place.

This module is the **single source of truth** for the simulation constants. The
browser gets them verbatim (``tuning.as_json()`` is embedded in the play page as
``window.DRIVE_TUNING``), and ``laptime.py`` uses the same numbers to simulate an
ideal lap and derive each track's medal times. So retuning the car here
automatically retunes the medals, and there is never a second copy of ACCEL
sitting in a .js file drifting out of sync.

Units are "roughly metres and seconds": CELL is 8, a car is 3.4 long, gravity is
30. Nothing is physically accurate - these are arcade numbers picked so the car
turns in fast and never feels floaty, which is the whole point of the Polytrack
driving model.
"""

import json

# --- world scale -----------------------------------------------------------
CELL = 8.0        # grid cell size in XZ; also the road width
LEVEL = 3.2       # height of one elevation level (a 1-cell ramp is ~21.8 deg)

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
MAX_SPEED = 44.0
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
AIR_PITCH = 1.5            # rad/s of pitch control in the air (up/down keys)
AIR_ROLL = 2.0             # rad/s of roll control in the air
ALIGN_GROUND = 14.0        # how fast the body snaps to the surface normal
ALIGN_AIR = 2.6            # how fast it levels out while airborne
STICK_SPEED = 15.0         # above this, the car sticks to non-flat surfaces
STICK_FORCE = 34.0         # extra pull into the surface (what makes loops work)
COYOTE = 0.09              # seconds of grounded grace over crests and seams

# Suspension droop. The car counts as grounded while the road is up to SNAP
# below its resting height, and gets pulled back down over that gap by a spring
# rather than being teleported. This is what stops every ramp crest from
# launching the car: a ramp is a crease in the road, and a real car's wheels
# follow it. Jumps still launch you, because past a kicker's lip there is no road
# within reach at all - the launch comes from the geometry, not from a special
# case. SUSP has to beat the vertical velocity a ramp imparts (v * sin(slope))
# inside SNAP of travel, hence a stiff-looking number.
SNAP = 1.0
SUSP = 150.0

# --- surfaces --------------------------------------------------------------
OFFROAD_DRAG = 0.55        # fraction of speed scrubbed per second on grass
OFFROAD_GRIP = 6.0
BOOST_SPEED = 68.0         # speed a booster pad snaps you up to
BOOST_HOLD = 1.1           # seconds the over-speed cap lingers after a pad
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
    "CELL", "LEVEL", "CAR_LEN", "CAR_WID", "CAR_HEI", "RIDE_HEIGHT",
    "MAX_SPEED", "ACCEL", "BRAKE", "COAST", "DRAG", "REVERSE_MAX",
    "REVERSE_ACCEL", "STEER_RATE_LOW", "STEER_RATE_HIGH", "STEER_SMOOTH",
    "STEER_RETURN", "DRIFT_STEER_BONUS", "GRIP", "DRIFT_GRIP", "AIR_GRIP",
    "GRAVITY", "AIR_STEER", "AIR_PITCH", "AIR_ROLL", "ALIGN_GROUND",
    "ALIGN_AIR", "STICK_SPEED", "STICK_FORCE", "COYOTE", "SNAP", "SUSP", "OFFROAD_DRAG",
    "OFFROAD_GRIP", "BOOST_SPEED", "BOOST_HOLD", "WALL_BOUNCE", "WALL_SCRUB",
    "PROBE", "CAR_RADIUS", "CAR_PUSH", "CAR_BUMP_SCRUB", "FIXED_DT",
    "MAX_STEPS", "RESPAWN_DELAY",
]


def as_dict():
    g = globals()
    return {k: g[k] for k in _EXPORT}


def as_json():
    return json.dumps(as_dict(), separators=(",", ":"))
