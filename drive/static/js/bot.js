// A driver for the car, good enough to be worth racing.
//
// This is the whole of the bot's skill. It is handed a real `Car`, the real
// `Course` and a line to follow, and every tick it returns the same
// `{throttle, brake, steer, handbrake}` a keyboard would have produced. It never
// touches the car's state directly, so a bot is not a special kind of car - it
// is the ordinary one with something other than a person deciding what to press.
// That is what makes a bot bumpable, tow-able, and able to be beaten.
//
// **The line is not computed here, it is given.** Two of them exist and which
// one a level gets is most of what separates the levels:
//
//   - `laptime.py`'s relaxed centreline, which stays on the road and is what the
//     medal times are cut from. Easy and medium drive this.
//   - the **record holder's actual lap**, read off the board and stored in the
//     track folder by `tools/hotlap.py`. Hard and max drive this, which is how
//     they inherit the things no relaxation can derive: the kerb to stand on,
//     the late brake, and the four tracks in this pool whose records are won by
//     jumping clean across a loop.
//
// Steering is **analogue**, unlike `tests/driver.js`, which deliberately drives
// on the keyboard so the input stream it records is lossless. Nothing a bot
// drives is ever recorded or verified - no room lap reaches a leaderboard - so
// there is no reason to throw away the precision, and a touch player's steering
// is analogue anyway. It is the single largest difference between this and the
// old test autopilot, and it is worth about a second a lap.
//
// Nothing in here allocates in the hot path: it runs eight times per tick inside
// QuickJS on a box with one core to spare, so the vector maths is scalars.

// How far ahead the car aims, as a base plus a slice of its speed. Pure pursuit
// is stable when the aim point is roughly the distance covered in a third of a
// second and unstable when it is much shorter - the car saws - so this is a
// floor and a ceiling around exactly that.
/**
 * The driver's gains, in one object so they can be measured.
 *
 * Every one of these was arrived at by driving the pool and reading the lap
 * times, not by taste, and a level may override any of them (`prof.tune`) -
 * which is what lets "hard" leave its braking later than "easy" rather than
 * simply multiplying a speed. `tools/calibrate_bots.py --sweep` is the harness
 * that measures a change to any of them.
 */
const TUNE = {
  // How far ahead the car aims, as a base plus a slice of its speed. Long
  // enough that the steering is not chasing noise, short enough that it turns
  // in rather than cutting the corner and running wide on the exit - which is
  // what put the car on the grass after every jump on Sunrise.
  lookBase: 6.0,
  lookPer: 0.30,
  lookMin: 6.0,
  lookMax: 15.0,
  // In the air there is `AIR_STEER` of the usual yaw authority and a whole
  // second of flight to use it in, so aiming further ahead stops the car
  // chasing a point it is about to fly over.
  lookAir: 26.0,
  // Radians of heading error per unit of steering.
  //
  // **A curvature feedforward was tried here and is not in the code**, which is
  // worth writing down because it is the obvious thing to reach for: the car
  // yaws at exactly `steerRate(speed) * steer`, so the lock a corner needs is
  // exactly `v * k / steerRate(v)` and can be computed rather than chased. It
  // was measured twice, once added to the aim point and once with the aim point
  // replaced by heading and cross-track feedback, and both were worse on nearly
  // every track - the first because pursuit toward a point on a curve is
  // already a request for that curve's lock, so the corner was being asked for
  // twice; the second because the aim point is what makes the car *converge* on
  // the line, and error feedback at any gain that was stable did not.
  // **6.0, and 2.2 was simply far too low.** The number was picked early, by
  // eye, and never swept - and because the failure it caused was "runs a bit
  // wide" rather than anything that crashes, it hid behind every other theory
  // for months. Swept over eight tracks it improves *monotonically* all the way
  // to 6.0 with no exceptions: Sunrise 19.33 -> 17.43, Eight 18.00 -> 17.38,
  // Jump City from a respawn to a clean lap. Past it the loop starts to
  // overshoot - at 8.0 Eight stops finishing and Sunrise turns back up - so 6.0
  // is the knee and not just the biggest value tried.
  //
  // It is also what made **Cloudbreak** unfinishable at any pace: on the pool's
  // narrowest track, with almost nothing at the edges, a car that converges on
  // the line this slowly simply runs out of road and falls into the void. Same
  // number, nineteen respawns and a DNF at 2.2, a clean 58s lap at 3.0.
  steer: 6.0,
  // Correcting the car onto the line, **only on the run-up to a jump** - see
  // `straighten`. Doing it everywhere was measured over 27 combinations of
  // gains across four tracks and was worse on all of them: the aim point and
  // the correction disagree about where to point in a corner, so the car saws.
  // The first closes the sideways gap to the line, the second kills the
  // sideways velocity, and the reason they are worth anything at all there is
  // that in the air the car can correct neither. **Both are small**: at 6.0 and
  // 0.10 they cost a second and a half on Sunrise and DNF'd Spiral Ascent,
  // because a run-up is not always as straight as the word suggests and a hard
  // correction into a lip is its own way of missing one.
  aimCross: 2.5,
  aimLat: 0.04,
  // Below this the division by speed stops stabilising and starts amplifying.
  crossFloor: 14.0,
  // Countersteer against a genuine slide. This is what catches a car that has
  // been hit, whose tyres are let go for `BUMP_SLIP_TIME`. Small, because
  // ordinary cornering carries a little lateral velocity too and this must not
  // fight it.
  counter: 0.035,
  // How much of `BRAKE` the planner assumes it will get. The real number is
  // reduced by a slope, by grass and by the car not being perfectly straight
  // when it arrives, so planning on all of it means running wide out of
  // everything.
  brakePlan: 0.82,
  // When to tap the handbrake, as a fraction of the yaw the corner *needs*
  // against the yaw the tyres will give. Over 1.0 means full lock is not enough
  // and the car is going to run wide whatever it does. Hysteresis, because a
  // drift that flickers on and off is slower than either state - though the two
  // being close together is what makes it a tap rather than a slide.
  //
  // **Measured, not guessed, and the first guess was well under the limit.**
  // Demand over the hot laps runs p50 0.4, p90 1.0, p97 1.2-1.6. The original
  // 0.92 therefore fired below what the tyres could already do, about one
  // station in eight, spending grip to no purpose: on Skyline that was eleven
  // respawns in a lap. Swept off/1.00/1.15/1.30/1.50 over eight tracks, **1.30
  // was the only value that finished all eight with no respawn and no DNF**,
  // while still taking 0.45s off Eight, 0.33s off Sunrise and 0.18s off Heights
  // and turning Spiral from a respawn into a clean lap. Above it the taps stop
  // happening at all and the times fall back to the no-handbrake baseline.
  driftOn: 1.30,
  driftOff: 1.01,
};

// Pedal control.
//
// **Below the target the throttle is wide open**, and the first version of this
// was a proportional controller that held 0.3 inside a deadband instead. That
// cannot work, and the reason is worth writing down: the reference speed down a
// straight is whatever the reference lap *reached* there, which is the speed
// where `ACCEL` balances `DRAG` - so holding it takes full throttle, and
// anything less means falling below the target, catching it, falling below it
// again. It was worth a second a lap and it made the quick bots 13% slower than
// the record they were copying.
//
// Above the target there is a small band of coasting before the brakes, because
// drag alone covers a tenth of a unit of overshoot and a car that stabs the
// brakes every time it is a hair fast is both slower and visibly twitchy.
const PEDAL_BAND = 0.6;
const BRAKE_GAIN = 0.22;
// The slowest a target may ever be. See where it is used.
const CRAWL = 8.0;
const DRIFT_MIN_SPEED = 14.0;
// How long one tap of the handbrake lasts, and the least time before another.
const TAP_MAX = 0.28;
const TAP_GAP = 0.22;

// Recovery. All three are generous on purpose: a bot that respawns when it did
// not need to has thrown the race away far more thoroughly than one that spent
// an extra second in the gravel, and it looks broken while it does it.
const STUCK_SPEED = 1.5;          // units/s of progress that still counts as moving
const STUCK_NUDGE_S = 1.4;        // back up and try again
const STUCK_GIVE_UP_S = 3.2;      // take the checkpoint
const WRONG_WAY_DOT = -0.4;
const WRONG_WAY_GIVE_UP_S = 3.0;
const LOST_DIST = 15.0;           // this far off the line is not a wide moment
const LOST_GIVE_UP_S = 2.5;
// **Beside the road is a wide moment; under it is a fall.**
//
// Distance alone cannot tell those apart, and the gap it leaves is not a small
// one: on Sandy Cove the bot dropped off the coast road onto the beach, carried
// on down the sand, and was never more than nine units from the line it should
// have been on - well inside `LOST_DIST`, so nothing fired. It drove the whole
// remaining lap down there, missing nine of the ten checkpoints, and finished
// with 100% of the ribbon covered and no lap to show for it. The symptom was a
// DNF with no crash in it, which reads like a slow bot rather than a broken one.
//
// Nothing legitimate puts the car this far below the point on the line it is
// nearest to - a loop or a half-pipe wall moves it sideways and above, never
// under - so it is the one unambiguous signal that the road being driven is not
// the road at all.
const FELL_BELOW = 4.0;
const FELL_GIVE_UP_S = 1.2;
const RELOCK_DIST = 30.0;         // past this, stop walking the line and re-find it

const NEUTRAL = { throttle: 0, brake: 0, steer: 0, handbrake: false };

/** Deterministic per-bot randomness. Same seed, same mistakes, every time. */
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

/**
 * A path through the world with a speed at every point.
 *
 * Either line arrives in the same shape, so the driver below has no idea which
 * of the two it is following - the only difference a level sees is that one of
 * them is quicker and jumps things.
 *
 * `vmin` is the part that makes a pace multiplier safe. See `tools/hotlap.py`:
 * four of the records in this pool are won by clearing a gap that misses out a
 * couple of hundred units of road, every one of them launches at 47-49 u/s, and
 * a lap scaled down by the 7% between a record and a gold arrives at the lip too
 * slow to reach the other side. On the run-up to a jump the recorded speed is a
 * floor and the pace only scales what is above it.
 */
class BotLine {
  constructor(data) {
    this.p = data.p;
    this.v = data.v;
    this.air = data.air || null;
    this.vmin = data.vmin || null;
    this.closed = !!data.closed;
    this.n = this.p.length;
    this._unLaunch();
    // Cumulative arc length, so "12 units further on" is a lookup rather than a
    // walk with a running total in it.
    this.s = new Array(this.n);
    this.s[0] = 0;
    for (let i = 1; i < this.n; i++) {
      const a = this.p[i - 1], b = this.p[i];
      this.s[i] = this.s[i - 1] + Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
    }
    this.total = this.s[this.n - 1];
    // **After `total`, and that is not a detail.** This used to run three lines
    // up, where `this.total` was still undefined, so `span` was NaN, `stride` was
    // NaN, and `for (i = NaN; NaN < n - NaN; ...)` fell straight through - leaving
    // `kap` at the zeroes it was filled with. The handbrake reads `kap` and asks
    // for a tap when the corner wants more yaw than the tyres give, so with every
    // corner reading as dead straight it never once fired, on any level, on any
    // track. It cost nothing and broke nothing, which is exactly why it survived:
    // the only visible symptom was the quick levels running wide in corners while
    // matching on the straights, which is also what a merely mediocre driver does.
    // What gave it away was an A/B of four drift thresholds - including one set
    // impossibly high to mean *off* - coming back identical to the digit.
    this._curvature();
  }

  /**
   * Throw away the reference lap's standing start.
   *
   * Both lines are recordings of a lap that began from rest, so `v` opens at
   * zero and climbs. Read as a speed *limit* - which is the only way the driver
   * uses it - that says "you may do 0 u/s on the start line", and a bot that
   * believes it brakes, sits still, is declared stuck, takes the checkpoint,
   * arrives back on the line and does the whole thing again. Forty-one times a
   * lap, measured, on every level at once.
   *
   * The launch is not a constraint, it is a consequence of where the reference
   * lap happened to begin. So the leading climb is flattened to the speed it
   * reaches: on the start straight the only real limit is the first corner, and
   * the lookahead in `speedLimit` is what finds that.
   */
  _unLaunch() {
    let m = 0;
    while (m + 1 < this.n && this.v[m + 1] >= this.v[m]) m++;
    // A whole lap of monotonically rising speed is not a launch, it is a track
    // with one straight on it, and flattening the lot would be wrong.
    if (m === 0 || m > this.n * 0.5) return;
    for (let i = 0; i < m; i++) this.v[i] = this.v[m];
  }

  /**
   * How tightly the line turns at each point, as 1/radius.
   *
   * Used for one thing: deciding when the corner needs the handbrake. See
   * `Bot.wantsDrift`.
   *
   * **Measured over about eight units, not between neighbouring points.** The
   * lesson is `laptime.py`'s, which says it plainly - a three-point circumradius
   * over a short baseline "is dominated by the relaxation's own residual wobble"
   * and reports hairpin radii on straights. A recorded lap is worse, not better:
   * its samples are a fifteenth of a second apart and carry the driver's own
   * small corrections, and differentiating those twice turns a ten-centimetre
   * wobble into a demand for a third of full lock.
   */
  _curvature() {
    const n = this.n;
    const span = this.total / Math.max(1, n - 1);
    const stride = Math.max(1, Math.round(8.0 / Math.max(0.5, span)));
    const kap = new Array(n).fill(0);
    const kx = new Array(n).fill(0);
    const ky = new Array(n).fill(0);
    const kz = new Array(n).fill(0);
    for (let i = stride; i < n - stride; i++) {
      const a = this.p[i - stride], b = this.p[i], c = this.p[i + stride];
      const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
      const vx = c[0] - b[0], vy = c[1] - b[1], vz = c[2] - b[2];
      const ul = Math.hypot(ux, uy, uz), vl = Math.hypot(vx, vy, vz);
      if (ul < 1e-6 || vl < 1e-6) continue;
      const cxx = uy * vz - uz * vy;
      const cyy = uz * vx - ux * vz;
      const czz = ux * vy - uy * vx;
      const cl = Math.hypot(cxx, cyy, czz);
      if (cl < 1e-9) continue;
      const dot = (ux * vx + uy * vy + uz * vz) / (ul * vl);
      const ang = Math.atan2(cl / (ul * vl), Math.max(-1, Math.min(1, dot)));
      kap[i] = ang / ((ul + vl) / 2);
      kx[i] = cxx / cl; ky[i] = cyy / cl; kz[i] = czz / cl;
    }
    this.kap = kap;
    this.kx = kx; this.ky = ky; this.kz = kz;
  }

  /**
   * The point on the path nearest a position, searched forward from a hint.
   *
   * Forward-biased and narrow, because half the pool runs beside itself
   * somewhere and a global search snaps to the piece of road the car will reach
   * a minute later. The caller re-locks with a full scan when the answer stops
   * being credible, which is a respawn, a grid placement or a genuine crash.
   */
  near(x, y, z, hint) {
    let bi = hint, bd = Infinity;
    const lo = Math.max(0, hint - 6), hi = Math.min(this.n, hint + 90);
    for (let i = lo; i < hi; i++) {
      const q = this.p[i];
      const dx = x - q[0], dy = y - q[1], dz = z - q[2];
      const d = dx * dx + dy * dy + dz * dz;
      if (d < bd) { bd = d; bi = i; }
    }
    return { i: bi, d: Math.sqrt(bd) };
  }

  /** The same thing over the whole path, for when the hint has gone bad. */
  relock(x, y, z) {
    let bi = 0, bd = Infinity;
    for (let i = 0; i < this.n; i++) {
      const q = this.p[i];
      const dx = x - q[0], dy = y - q[1], dz = z - q[2];
      const d = dx * dx + dy * dy + dz * dz;
      if (d < bd) { bd = d; bi = i; }
    }
    return { i: bi, d: Math.sqrt(bd) };
  }

  /** Index of the point `look` units further along, clamped to the end. */
  aheadOf(i, look) {
    const want = this.s[i] + look;
    let j = i;
    while (j < this.n - 1 && this.s[j] < want) j++;
    return j;
  }

  /** Unit tangent at a point, pointing the way the lap goes. */
  tangent(i, out) {
    const a = this.p[Math.max(0, i - 1)];
    const b = this.p[Math.min(this.n - 1, i + 1)];
    let dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
    const l = Math.hypot(dx, dy, dz) || 1;
    out[0] = dx / l; out[1] = dy / l; out[2] = dz / l;
    return out;
  }
}

/**
 * The driver.
 *
 * `prof` is the level: how hard it tries, how tidy it is, how often it makes a
 * mess of something, and whether it knows about the shortcut. The numbers live
 * in `bots.py` because that is also where they are calibrated against each
 * track's medal times - there is no second copy of a level in here.
 */
class Bot {
  constructor(car, course, run, line, prof) {
    this.car = car;
    this.course = course;
    this.run = run;
    this.line = line;
    this.prof = prof || {};
    this.rnd = mulberry32((this.prof.seed | 0) || 1);
    // The level's gains over the defaults, resolved once. `prof.tune` is last
    // because it is the explicit override - the sweep in `tools/calibrate_bots.py`
    // passes it, and it used to be silently undone one line later by the level's
    // own `brakePlan`, so every value of that knob measured identically to the
    // digit and read as "this makes no difference" when it had never been tried.
    this.k = Object.assign({}, TUNE,
                           this.prof.brakePlan ? {brakePlan: this.prof.brakePlan} : {},
                           this.prof.tune || {});
    // Phases for the wander and the pace drift, drawn once so that two bots on
    // the same grid are never wrong in the same place at the same moment.
    this.ph = [this.rnd() * 6.283, this.rnd() * 6.283, this.rnd() * 6.283,
               this.rnd() * 6.283];
    this.hint = 0;
    this.t = 0;
    this.stuck = 0;
    this.lostFor = 0;
    // Why this bot has given up, by reason, and the last one in detail. Read by
    // `botLap` for the calibrator; nothing in a room looks at it.
    this.gaveUp = {};
    this.lastGiveUp = null;
    this.wrongFor = 0;
    this.fellFor = 0;
    this.drifting = false;
    this.tapLeft = 0;
    this.tapRest = 0;
    this.lapseLeft = 0;
    this.lapseKind = 0;
    this.lapseIn = 1 + this.rnd() * 6;
    this.lastS = 0;
    this.launched = false;
    // Scratch, so the hot path allocates nothing.
    this._t = [0, 0, 0];
    this._l = [0, 0, 0];
    this._c = [0, 0, 0];
  }

  /** Put the driver back to a known state: a respawn, a grid slot, a new race. */
  reset() {
    const p = this.car.pos;
    this.hint = this.line.relock(p.x, p.y, p.z).i;
    this.stuck = this.lostFor = this.wrongFor = this.fellFor = 0;
    this.drifting = false;
    this.lastS = this.line.s[this.hint];
    this.launched = false;
  }

  /**
   * What to press this tick.
   *
   * `ctx.rivals` is every other car as `{x, y, z, vx, vy, vz}` - bots and people
   * alike, because as far as racecraft is concerned there is no difference.
   * `ctx.since` is seconds since the green light, negative before it, or null
   * when this is not a race.
   */
  drive(dt, ctx) {
    ctx = ctx || {};
    const car = this.car;
    // Being put back on the road is not a moment with a decision in it, and the
    // timers must not run while it happens or the car respawns again on landing.
    if (car.respawnIn > 0) {
      this.stuck = this.lostFor = this.wrongFor = this.fellFor = 0;
      this.pendingReset = true;
      return NEUTRAL;
    }
    if (this.pendingReset) { this.pendingReset = false; this.reset(); }
    if (car.frozen) return NEUTRAL;
    this.t += dt;

    // Nobody's foot is down at exactly zero. A reaction time is also what stops
    // a grid of bots leaving the line as one machine.
    if (!this.launched) {
      if (ctx.since != null && ctx.since < (this.prof.reaction || 0)) return NEUTRAL;
      this.launched = true;
    }

    const p = car.pos;
    let loc = this.line.near(p.x, p.y, p.z, this.hint);
    if (loc.d > RELOCK_DIST) loc = this.line.relock(p.x, p.y, p.z);
    this.hint = loc.i;

    const rec = this.recover(dt, loc);
    if (rec) return rec;

    return car.grounded ? this.onRoad(dt, loc, ctx) : this.inAir(dt, loc);
  }

  // -- the two halves of driving -------------------------------------------

  onRoad(dt, loc, ctx) {
    const car = this.car;
    const prof = this.prof;
    const line = this.line;

    this.lapse(dt);

    // Where to aim. The lateral bias is everything that is not the line itself:
    // the wander that makes a bot imperfect, and whatever racecraft has decided
    // about the cars around it.
    // Lining up a jump: `vmin` is non-zero exactly on the approach to one (see
    // tools/hotlap.py). There, the line is the whole game - drift two units off
    // it and the car lands in the scenery - so the wander is switched off and
    // the cross-track correction switched on.
    this.aiming = !!(line.vmin && line.vmin[loc.i] > 0);
    const look = clamp(this.k.lookBase + car.speed * this.k.lookPer,
                       this.k.lookMin, this.k.lookMax);
    const j = line.aheadOf(loc.i, look);
    const bias = (this.aiming ? 0 : this.wander()) + this.racecraft(loc, ctx);
    const steer = this.steerOnPath(loc, bias, j);

    // How fast to be going. `vmin` is a floor the pace is not allowed to scale -
    // it is what gets the car over the gaps the quick line jumps.
    let want = this.speedLimit(loc.i);
    const floor = line.vmin ? line.vmin[loc.i] : 0;
    if (floor > want) want = floor;
    // Nowhere on any line is a place to be stationary - the tightest hairpin in
    // the pool is taken at three times this. So a target under it means the
    // reference data is wrong rather than the corner being slow, and crawling is
    // something a bot recovers from where standing still is not. Belt and
    // braces over `_unLaunch`, because that failure is completely silent: the
    // bot simply never sets off.
    if (want < CRAWL) want = CRAWL;

    const err = want - car.speed;
    let throttle = 0, brake = 0;
    if (err > 0) throttle = 1;
    else if (err < -PEDAL_BAND) brake = clamp(-err * BRAKE_GAIN, 0.15, 1);

    // The handbrake, and it is not a last resort - it is how a quick corner is
    // taken. See `wantsDrift` and `tap`.
    //
    // **It does not touch the pedals.** The first version zeroed the brake while
    // the handbrake was down, on the theory that braking mid-drift spins the
    // car. Nothing in `Car.step` does that - the handbrake sets `DRIFT_GRIP` and
    // `DRIFT_STEER_BONUS` and the brake is an independent longitudinal term -
    // so all it achieved was removing the braking at exactly the moment a corner
    // needs it, with the grip gone as well. Every track DNF'd.
    this.drifting = prof.drift && car.speed > DRIFT_MIN_SPEED &&
                    this.tap(dt, this.wantsDrift(loc.i, car.speed));

    return { throttle, brake, steer, handbrake: this.drifting };
  }

  /**
   * Mid-flight.
   *
   * Two things matter and neither of them is speed, which is now entirely
   * decided: point the car where the path goes, and put the nose where the car
   * is *actually* travelling so it lands on its wheels rather than on its face.
   *
   * The second is the one that is easy to get backwards. Holding the throttle
   * pitches the nose **down** (`AIR_PITCH`, see physics.js) and braking pitches
   * it up, so aligning the body with the velocity vector means throttle while
   * the nose is above the flight path and brake while it is below. Following the
   * arc down like that is what makes a 1.6s jump land flat, and Big Red's record
   * is airborne for 28% of the lap.
   */
  inAir(dt, loc) {
    const car = this.car;
    const j = this.line.aheadOf(loc.i, this.k.lookAir);
    const steer = this.aimAt(j, 0, false);

    const v = car.vel;
    const sp = Math.hypot(v.x, v.y, v.z) || 1;
    // How far the direction of travel sits off the body's own plane. Positive:
    // the car is heading upward relative to itself, so the nose is low.
    const upness = (v.x * car.up.x + v.y * car.up.y + v.z * car.up.z) / sp;
    // **Where it aims while flying is what decides where it lands**, and it is
    // the one gain here that is genuinely per-track (`lookAir`). Over a descent,
    // aiming a long way up the road picks a point far below the car, which
    // `AIR_PITCH` turns into nose-down for the whole flight, so the car glides
    // out long and flat and overshoots what it was coming down onto. Sandy Cove
    // is the case: at 26 the reference lands on the shelf at station 91 and the
    // bot was still airborne at 96, nine units lower, on the beach - 36
    // respawns at one station. At 8 it lands with the record and laps in 56.25s.
    //
    // It is not a global, which was measured rather than assumed: Big Red is 28%
    // airborne over four long jumps and picks up a respawn at anything under 26,
    // where its whole flight is the point and aiming at the near lip wobbles it.
    // See `bots.TRACK_TUNE`.
    //
    // Tried and does nothing: lifting the throttle when already below the road
    // ahead, on the theory that the nose-down was the cause. Identical to the
    // digit at every pace - the pitch follows where it is *aiming*, and the
    // pedals in the air are not the lever they look like.
    let throttle = 1, brake = 0;
    if (upness > 0.06) { brake = 1; throttle = 0; }
    else if (upness < -0.06) { throttle = 1; }
    return { throttle, brake, steer, handbrake: false };
  }

  // -- the pieces ------------------------------------------------------------

  /**
   * Steering to put the car at path point `j`, pushed `bias` units sideways.
   *
   * Worked in the **car's own frame** rather than in world X/Z, which is what
   * lets one line of code drive a loop, a corkscrew and a banked wall with no
   * special case: "to my right" is a dot product with the body's right vector
   * whichever way up the body is. The old test autopilot works in plan view and
   * needs a hand-written exception for every one of those.
   */
  aimAt(j, bias, counter) {
    const car = this.car;
    const t = this.line.p[j];
    let tx = t[0], ty = t[1], tz = t[2];
    if (bias) {
      // Sideways is the path's tangent crossed with the body's up, which points
      // to the right of travel - so a positive bias moves the aim right.
      const tan = this.line.tangent(j, this._t);
      const u = car.up;                        // a Vector3, not an array
      const lx = tan[1] * u.z - tan[2] * u.y;
      const ly = tan[2] * u.x - tan[0] * u.z;
      const lz = tan[0] * u.y - tan[1] * u.x;
      const l = Math.hypot(lx, ly, lz);
      // Degenerate where the road runs straight up the inside of a loop and the
      // tangent is the body's own up. There is no "sideways" there to speak of,
      // so the bias is simply not applied rather than applied in a direction
      // picked out of the air.
      if (l > 1e-4) {
        tx += (lx / l) * bias; ty += (ly / l) * bias; tz += (lz / l) * bias;
      }
    }
    const dx = tx - car.pos.x, dy = ty - car.pos.y, dz = tz - car.pos.z;
    const f = dx * car.fwd.x + dy * car.fwd.y + dz * car.fwd.z;
    const r = dx * car.right.x + dy * car.right.y + dz * car.right.z;
    const ang = Math.atan2(r, f);
    this.lastAngle = ang;
    let steer = ang * this.k.steer;
    // Being on the line rather than merely heading for it is `straighten`'s
    // job, and only on a jump run-up. It is deliberately not here.
    if (counter) {
      // The sideways motion the driver can feel. Catching it is the whole of
      // recovering from a shunt, and it costs one dot product.
      const v = this.car.vel;
      const lat = v.x * car.right.x + v.y * car.right.y + v.z * car.right.z;
      steer -= lat * this.k.counter;
    }
    return clamp(steer, -1, 1);
  }

  /**
   * Steering, as a corner plus two errors.
   *
   * **Feedforward and feedback, and the feedback must not repeat the
   * feedforward.** The first attempt at this added the exact corner lock to a
   * pursuit term aimed at a point up the road, and got slower on five tracks
   * out of seven - because pursuit toward a point on a curve *is already* a
   * request for that curve's lock, so the two were asking for the corner twice
   * and the car turned in about half as far again as it should. Spiral Ascent
   * went from 23s to two minutes and eight respawns.
   *
   * So the aim point is gone from the road-going case entirely. What is left is
   * the shape of every path follower worth having:
   *
   *   lock for the corner  +  how wrong the heading is  +  how far off the line
   *
   * and each of those three answers exactly one question, which is what makes
   * them tunable independently.
   */
  steerOnPath(loc, bias, j) {
    const car = this.car;
    let steer = this.aimAt(j, bias, true);
    // Lining a jump up is the one place the aim point is not enough. See
    // `straighten`.
    if (this.aiming) steer += this.straighten(loc, bias);
    return clamp(steer, -1, 1);
  }

  /**
   * Extra correction on the run-up to a jump: be on the line, and be straight.
   *
   * **In the air the car is a thrown object.** Steering yaws the body and
   * changes nothing about where it is going; `AIR_GRIP` is 0.6, so whatever
   * sideways velocity it left the lip with, it keeps for the whole flight. That
   * is the single largest loss the quick levels have, and it is measurable:
   * traced down Sunrise, the bot matches the record's speed within 1 u/s
   * everywhere except twice, and both times it is **immediately after a
   * flight** - cross error growing from 4.7 to 9.2 units *during* the jump, a
   * landing on the grass, and the speed falling from 47 to 24, which is exactly
   * the grass top speed. Two of those is most of the deficit on that track.
   *
   * So on the approach, where `vmin` says a lip is coming, two things are worth
   * far more than they are anywhere else: closing the sideways gap to the line,
   * and killing the sideways *velocity* so the car leaves the ground going
   * where it is pointing. Neither destabilises anything, because a run-up is a
   * straight - which is precisely why the same correction is a liability
   * everywhere else and is not applied there.
   */
  straighten(loc, bias) {
    const car = this.car;
    const off = this.crossError(loc.i) - bias;
    const lat = car.vel.x * car.right.x + car.vel.y * car.right.y +
                car.vel.z * car.right.z;
    return -off * this.k.aimCross / Math.max(this.k.crossFloor, car.speed)
           - lat * this.k.aimLat;
  }

  /**
   * Turn a "this corner needs more yaw than I have" into an actual **tap**.
   *
   * Held down, the handbrake is a long slide: `DRIFT_GRIP` is 2.4 against a
   * normal 13.5, so the car stops going where it points at all and the corner
   * is lost the other way. What is quick is a short one - rotate the car, let
   * go, and let the grip snap the velocity onto the new heading - and through a
   * long corner that means one or two of them rather than one continuous one,
   * which is exactly how the fast laps in this game are driven.
   *
   * So the demand only ever buys `TAP_MAX` of handbrake, and then it has to be
   * off for `TAP_GAP` before it can have any more.
   */
  tap(dt, need) {
    if (this.tapLeft > 0) {
      this.tapLeft -= dt;
      if (this.tapLeft > 0) return true;
      this.tapRest = TAP_GAP;
      return false;
    }
    if (this.tapRest > 0) {
      this.tapRest -= dt;
      return false;
    }
    if (need > this.k.driftOn) {
      this.tapLeft = TAP_MAX;
      return true;
    }
    return false;
  }

  /**
   * How much more yaw this corner wants than the tyres are going to give.
   *
   * 1.0 means the corner needs exactly the yaw rate full lock provides at this
   * speed; above that the car cannot make it on steering alone and is going to
   * run wide however hard it is asked to turn.
   *
   * **This is why the quick levels could not hold the record's speeds.** The
   * reference lap is a person's, and a person taking a corner quickly here taps
   * the handbrake once or twice - which is worth `DRIFT_STEER_BONUS`, 35% more
   * yaw authority, plus a rear that steps out and rotates the car while it
   * keeps its speed. A bot copying that lap's *speeds* without copying that
   * technique is being asked for a radius the front axle physically cannot
   * produce, so it washes out to the kerb, and every corner exit starts further
   * off line than the last. Matching on the straights and running wide in the
   * corners was exactly the measured symptom.
   *
   * The curvature is read a little up the road, because the tap wants to be in
   * before the apex rather than after it.
   */
  wantsDrift(i, speed) {
    const line = this.line;
    if (!line.kap) return 0;
    const j = line.aheadOf(i, Math.max(4, speed * 0.14));
    const k = line.kap[j];
    if (!k) return 0;
    const have = this.car.steerRate(speed);
    return have > 1e-6 ? (speed * k) / have : 0;
  }

  /**
   * How far to the right of the line the car is sitting, in units.
   *
   * Signed the same way a steering input is, so it can be subtracted straight
   * off one. Measured against the body's up rather than the world's, which is
   * what keeps it meaning "sideways" inside a loop.
   */
  crossError(i) {
    const car = this.car;
    const tan = this.line.tangent(i, this._c);
    const u = car.up;
    const lx = tan[1] * u.z - tan[2] * u.y;
    const ly = tan[2] * u.x - tan[0] * u.z;
    const lz = tan[0] * u.y - tan[1] * u.x;
    const l = Math.hypot(lx, ly, lz);
    if (l < 1e-4) return 0;
    const p = this.line.p[i];
    const dx = car.pos.x - p[0], dy = car.pos.y - p[1], dz = car.pos.z - p[2];
    return (dx * lx + dy * ly + dz * lz) / l;
  }

  /**
   * The fastest this car may be going here, given what is coming.
   *
   * The reference speed at every point ahead, each turned into a speed it would
   * be legal to be doing *now* by asking how much braking fits in between, and
   * the smallest of those wins. This is `laptime.py`'s backward pass done one
   * corner at a time and online, which is what makes the pace multiplier honest:
   * a bot at 0.9 brakes for a 0.9 corner speed rather than braking for the
   * record's and then being slow everywhere else.
   */
  speedLimit(i) {
    const line = this.line;
    const pace = this.pace();
    const decel = this.car.T.BRAKE * this.k.brakePlan;
    const s0 = line.s[i];
    let best = line.v[i] * pace;
    const horizon = s0 + (this.car.speed * this.car.speed) / (2 * decel) + 12;
    for (let j = i + 1; j < line.n && line.s[j] < horizon; j++) {
      const d = line.s[j] - s0;
      const target = line.v[j] * pace;
      const allowed = Math.sqrt(target * target + 2 * decel * d);
      if (allowed < best) best = allowed;
    }
    return best;
  }

  /** How hard this bot is trying right now: its level, plus its imperfections. */
  pace() {
    let p = this.prof.pace || 1;
    const n = this.prof.paceNoise || 0;
    if (n) {
      p *= 1 + n * (Math.sin(this.t * 0.37 + this.ph[0]) * 0.6 +
                    Math.sin(this.t * 1.13 + this.ph[1]) * 0.4);
    }
    if (this.lapseLeft > 0 && this.lapseKind === 0) p *= 0.72;   // lifted
    if (this.lapseLeft > 0 && this.lapseKind === 1) p *= 1.1;    // braked too late
    return p;
  }

  /** A slow drift across the road, so a bot does not drive on rails. */
  wander() {
    const a = this.prof.wander || 0;
    if (!a) return 0;
    return a * (Math.sin(this.t * 0.61 + this.ph[2]) * 0.6 +
                Math.sin(this.t * 1.47 + this.ph[3]) * 0.4);
  }

  /**
   * Occasionally get something wrong, and get it wrong for a moment rather than
   * for a corner: a lift where there should not have been one, or a brake left
   * a beat too late. Poisson-ish, seeded, so the same bot makes the same mess of
   * the same lap and two bots never make it together.
   */
  lapse(dt) {
    if (this.lapseLeft > 0) { this.lapseLeft -= dt; return; }
    const rate = this.prof.lapse || 0;
    if (!rate) return;
    this.lapseIn -= dt * rate;
    if (this.lapseIn > 0) return;
    this.lapseIn = 0.6 + this.rnd() * 3.5;
    this.lapseLeft = 0.25 + this.rnd() * 0.7;
    this.lapseKind = this.rnd() < 0.6 ? 0 : 1;
  }

  /**
   * What the cars around it are worth, as a sideways bias in units.
   *
   * Deliberately small and deliberately about one car - the nearest one that
   * matters. Three things, in the order a driver would think of them:
   *
   *   - **Do not drive into the back of somebody.** Closing fast on a car a
   *     couple of lengths ahead, pick a side now.
   *   - **Take the tow first.** Sitting in the hole is worth `SLIP_ACCEL_MULT`
   *     once it has charged, so the pass is made *after* the boost lands rather
   *     than by pulling out early and spending the straight in clean air.
   *   - **Do not make it easy.** A quick bot with somebody on its gearbox leans
   *     on the inside line. One car width, once - anything more is blocking, and
   *     a bot that blocks is a bot nobody wants in the room.
   *
   * All of it is off entirely when there is nobody near, so it can never cost a
   * bot time on an empty track.
   */
  racecraft(loc, ctx) {
    const rivals = ctx.rivals;
    const aggr = this.prof.race || 0;
    if (!aggr || !rivals || !rivals.length) return 0;
    const car = this.car;
    const T = car.T;

    let ahead = null, aheadD = 1e9, behind = null, behindD = 1e9;
    for (let k = 0; k < rivals.length; k++) {
      const o = rivals[k];
      const dx = o.x - car.pos.x, dy = o.y - car.pos.y, dz = o.z - car.pos.z;
      const f = dx * car.fwd.x + dy * car.fwd.y + dz * car.fwd.z;
      const r = dx * car.right.x + dy * car.right.y + dz * car.right.z;
      const up = dx * car.up.x + dy * car.up.y + dz * car.up.z;
      // Somebody on the road below or above - which happens on the Costco's
      // deck and inside every loop in the pool - is not somebody to race.
      if (Math.abs(up) > 4) continue;
      if (Math.abs(r) > 5.5) continue;
      if (f > 0 && f < aheadD) { aheadD = f; ahead = { f, r }; }
      if (f < 0 && -f < behindD) { behindD = -f; behind = { f, r }; }
    }

    if (ahead) {
      const charged = car.slipCharge > 0.9 || car.slipBoost > 0;
      // Close enough to hit, or the tow has paid: commit to a side. Whichever
      // side of us they are on, we go the other way.
      if (aheadD < T.CAR_LEN * 2.2 || (charged && aheadD < T.SLIP_RANGE * 0.7)) {
        const side = ahead.r >= 0 ? -1 : 1;
        return side * 2.6 * aggr;
      }
      // Otherwise sit in it and let it fill.
      if (aheadD < T.SLIP_RANGE) return clamp(ahead.r, -1.2, 1.2) * aggr;
    }
    if (behind && behindD < 12 && aggr > 0.6) {
      const tan = this.line.tangent(loc.i, this._t);
      const j = this.line.aheadOf(loc.i, 22);
      const nxt = this.line.tangent(j, this._l);
      // Which way the road turns next, as a signed number about the body's up.
      const cx = tan[1] * nxt[2] - tan[2] * nxt[1];
      const cy = tan[2] * nxt[0] - tan[0] * nxt[2];
      const cz = tan[0] * nxt[1] - tan[1] * nxt[0];
      const turn = cx * car.up.x + cy * car.up.y + cz * car.up.z;
      if (Math.abs(turn) > 0.02) return (turn > 0 ? 1 : -1) * 1.2 * aggr;
    }
    return 0;
  }

  /**
   * Getting out of trouble, and knowing when to stop trying.
   *
   * Returns the input to use, or null to carry on driving normally. The order
   * matters: pointing the wrong way is worth backing out of, being wedged is
   * worth backing out of, and being a long way from the line with neither of
   * those true means the car is somewhere the path does not go and the only way
   * back is the checkpoint.
   *
   * Every threshold is slack. A bot that takes the checkpoint when it did not
   * have to has thrown away more than the two seconds it spends scrabbling out
   * of the gravel, and looks broken while it does it.
   */
  recover(dt, loc) {
    const car = this.car;
    const s = this.line.s[loc.i];
    const moved = Math.abs(s - this.lastS) / Math.max(dt, 1e-4);
    this.lastS = s;

    const tan = this.line.tangent(loc.i, this._t);
    const facing = tan[0] * car.fwd.x + tan[1] * car.fwd.y + tan[2] * car.fwd.z;

    if (car.grounded && moved < STUCK_SPEED && car.speed < 6) this.stuck += dt;
    else this.stuck = 0;
    if (car.grounded && facing < WRONG_WAY_DOT) this.wrongFor += dt;
    else this.wrongFor = 0;
    // **Not where the reference lap was airborne**, for the same reason as
    // `under` below and with a worse failure. Over a jump the line is overhead
    // or already behind, so the distance to it stops meaning "drifting off the
    // road"; and unlike a wide moment there is no input that would close it,
    // because the wheels are not on anything. Cloudbreak drops thirty units in
    // one flight, which is over two seconds - longer than `LOST_GIVE_UP_S`. So
    // the car respawned *in mid-air*, landed back at the checkpoint before the
    // jump, took it again, and did that **43 times without ever passing 62% of
    // the lap**, on every level and at every pace.
    //
    // The exemption is on the *line* rather than on `car.grounded`, which would
    // also exempt a car that has left the track entirely: on a track with no
    // ground under it that car is falling into the void, `grounded` is never
    // coming back, and this is the check that has to notice.
    const flying = this.line.air && this.line.air[loc.i];
    if (loc.d > LOST_DIST && !flying) this.lostFor += dt;
    else this.lostFor = 0;
    // Under the road rather than beside it. See FELL_BELOW - this is the case
    // distance alone cannot see, and it is the difference between a bot that
    // has a moment and a bot that drives the rest of the lap along the beach.
    //
    // **Only where the reference was on the ground**, and both halves of that
    // matter. A jump arcs the path overhead, so a car that came up short of one
    // is "below the line" by construction and the nearest point on it is a
    // point in mid-air - which had this rule respawning Sunrise's quickest bot
    // nineteen times a lap at the same kicker. Being under a piece of *road* is
    // the signal; being under a piece of *flight* is just gravity.
    const under = car.grounded && !(this.line.air && this.line.air[loc.i]) &&
                  this.line.p[loc.i][1] - car.pos.y > FELL_BELOW;
    if (under) this.fellFor += dt;
    else this.fellFor = 0;

    const giveUp = this.stuck > STUCK_GIVE_UP_S ||
                   this.wrongFor > WRONG_WAY_GIVE_UP_S ||
                   this.lostFor > LOST_GIVE_UP_S ||
                   this.fellFor > FELL_GIVE_UP_S;
    if (giveUp) {
      // **Why**, and where. A bot that respawns sixty times in a lap is always
      // doing it in one place for one reason, and without this the only way to
      // find out which is to guess a cause, change it, and see whether the
      // number moves - which costs a lap of simulation per guess and is wrong
      // most of the time. Four counters and the last station are free.
      const why = this.stuck > STUCK_GIVE_UP_S ? 'stuck'
                : this.wrongFor > WRONG_WAY_GIVE_UP_S ? 'wrong'
                : this.lostFor > LOST_GIVE_UP_S ? 'lost' : 'fell';
      this.gaveUp[why] = (this.gaveUp[why] || 0) + 1;
      this.lastGiveUp = { why: why, i: loc.i, d: loc.d, y: car.pos.y,
                          lineY: this.line.p[loc.i][1], speed: car.speed };
      // `Run.update` keeps the car's respawn point on the last checkpoint
      // reached, so this is the same thing a person pressing T gets.
      car.requestRespawn();
      this.stuck = this.wrongFor = this.lostFor = this.fellFor = 0;
      return NEUTRAL;
    }

    // Pointing backwards with room to turn: brake, then swing it round. Aiming
    // reverse at the *near* point rather than up the road, because what is
    // wanted is to be facing the right way, not to get anywhere.
    if (this.wrongFor > 0.5) {
      const steer = this.aimAt(this.line.aheadOf(loc.i, 10), 0, false);
      if (car.speed > 4 && facing > -0.9) {
        return { throttle: 0, brake: 1, steer, handbrake: false };
      }
      return { throttle: 0, brake: 1, steer: -steer, handbrake: false };
    }
    // Wedged against something: back off it and try again.
    if (this.stuck > STUCK_NUDGE_S) {
      const steer = this.aimAt(this.line.aheadOf(loc.i, 10), 0, false);
      return { throttle: 0, brake: 1, steer: -steer, handbrake: false };
    }
    return null;
  }
}
