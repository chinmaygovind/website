// The car. Fixed-timestep arcade physics, tuned for the Polytrack feel: full
// throttle authority from a standstill, steering that is darty at low speed and
// calm flat out, and sideways velocity killed hard enough that the car goes
// exactly where it points until you ask it not to.
//
// Three decisions do most of the work:
//
// 1. **Steering rotates the car about the surface normal, not about world up.**
//    That single choice is what makes banks, hills and a fully inverted
//    corkscrew drive normally instead of needing special cases.
// 2. **Gravity is always applied, then its component along the surface normal is
//    removed while grounded.** Slope acceleration then falls out for free - no
//    "am I on a hill" logic anywhere.
// 3. **Grip is a velocity filter, not a force.** Lateral speed decays toward zero
//    at GRIP per second, so cornering is immediate and predictable, and dropping
//    to DRIFT_GRIP on the handbrake makes the back end step out without any of
//    the usual slip-angle machinery.
//
// Everything reads its numbers from the tuning object handed in by the server, so
// there is exactly one copy of ACCEL in the project.

import * as THREE from './vendor/three.module.js';
import { KIND } from './trackmesh.js';

const _v1 = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3();
const _q1 = new THREE.Quaternion();
const UP = new THREE.Vector3(0, 1, 0);

export const FLAG = { DRIFT: 1, AIR: 2, RESPAWN: 4, BRAKE: 8, SLIP: 16 };

export class Car {
  constructor(T, world) {
    this.T = T;
    this.world = world;
    this.pos = new THREE.Vector3();
    this.vel = new THREE.Vector3();
    this.quat = new THREE.Quaternion();
    // Local frame: forward -Z, right +X, up +Y - the three.js convention, and a
    // right-handed triple (right = forward x up), which every sign below assumes.
    this.up = new THREE.Vector3(0, 1, 0);
    this.fwd = new THREE.Vector3(0, 0, -1);
    this.right = new THREE.Vector3(1, 0, 0);
    this.groundN = new THREE.Vector3(0, 1, 0);
    this.grounded = false;
    this.coyote = 0;
    this.airTime = 0;
    this.steer = 0;
    this.braking = false;      // rear lights, and a netcode flag
    this.offroad = false;
    this.surface = KIND.ROAD;
    this.speed = 0;
    this.slip = 0;             // how sideways we are, 0..1, for tyre smoke
    this.bumpLean = 0;         // visual roll from the last car contact
    this.bumpTimer = 0;
    this.bumpSlip = 0;         // seconds of let-go tyres left after a hit
    this.lastBump = null;      // {x,y,z,mag} for sparks, consumed by the renderer
    this.respawnIn = 0;
    this.frozen = false;       // held on the grid during a countdown
    this.wheelSpin = 0;
    this.towed = false;        // in another car's hole right now
    this.slipCharge = 0;       // 0..1, how full the tow is
    this.slipBoost = 0;        // seconds of boost left
    this.padBoost = 0;         // seconds of boost-pad left
    this.bounceLock = 0;       // seconds a cap stays spent after throwing us
    this.catchupBoost = 0;     // 0..1, how much help for being down the road
    this._bumpCooldown = new Map();
    this._wallHit = 0;
  }

  placeAt(p, fwd) {
    this.pos.set(p[0], p[1] + this.T.RIDE_HEIGHT + 0.05, p[2]);
    this.vel.set(0, 0, 0);
    // Local forward is -Z, so the yaw that points it at `fwd` is atan2(-x, -z).
    this.quat.setFromAxisAngle(UP, Math.atan2(-fwd[0], -fwd[2]));
    this._syncAxes();
    this.grounded = false;
    this.coyote = 0;
    this.steer = 0;
    this.speed = 0;
    this.braking = false;
    this.respawnIn = 0;
    // A tow does not survive being picked up and put down: whatever you were
    // chasing, you are not behind it any more.
    this.towed = false;
    this.slipCharge = 0;
    this.slipBoost = 0;
    // Nor does a pad's boost. Being placed is a respawn or a grid slot, and
    // arriving at either with a second of engine left over from a pad you drove
    // over before you fell off is speed you were not going to keep.
    this.padBoost = 0;
    // Nor does the help for being behind: a car being placed is a car on the
    // grid or one that has just been picked up, and neither is a moment to hand
    // out engine. It is derived from the gap every frame, so it is back inside
    // half a second if the gap is still there.
    this.catchupBoost = 0;
    // Nor do the tyres a hit let go of. A car being placed has been picked up
    // and put down; arriving on the grid halfway through somebody else's shunt
    // would be a slide nobody caused.
    this.bumpSlip = 0;
  }

  _syncAxes() {
    this.fwd.set(0, 0, -1).applyQuaternion(this.quat);
    this.up.set(0, 1, 0).applyQuaternion(this.quat);
    this.right.set(1, 0, 0).applyQuaternion(this.quat);
  }

  /** Rotate about a world axis without disturbing the rest of the orientation. */
  _spin(axis, angle) {
    if (!angle) return;
    _q1.setFromAxisAngle(axis, angle);
    this.quat.premultiply(_q1);
    this._syncAxes();
  }

  /** Turn the body so its up approaches `target`, at `rate` per second. */
  _alignUp(target, rate, dt) {
    const dot = Math.min(1, Math.max(-1, this.up.dot(target)));
    if (dot > 0.99995) return;
    _v1.crossVectors(this.up, target);
    if (_v1.lengthSq() < 1e-12) return;
    _v1.normalize();
    const angle = Math.acos(dot) * (1 - Math.exp(-rate * dt));
    this._spin(_v1, angle);
  }

  steerRate(speed) {
    const T = this.T;
    const t = Math.min(1, Math.max(0, speed / T.MAX_SPEED));
    return T.STEER_RATE_LOW + (T.STEER_RATE_HIGH - T.STEER_RATE_LOW) * t;
  }

  /**
   * One fixed step. `input` is {throttle, brake, steer, handbrake} with steer in
   * -1..1 (already includes any analogue/touch source).
   */
  step(dt, input) {
    const T = this.T;

    if (this.respawnIn > 0) {
      this.respawnIn -= dt;
      if (this.respawnIn <= 0) this._doRespawn();
      return;
    }

    let { throttle = 0, brake = 0, steer = 0, handbrake = false } = input || {};
    if (this.frozen) { throttle = 0; brake = 0; steer = 0; handbrake = false; }
    this.braking = (brake > 0 && this.vel.dot(this.fwd) > 0.5) || handbrake;

    // --- smooth the steering input ---------------------------------------
    // Keyboard steering is binary; this is what makes it feel analogue.
    const rate = (steer === 0) ? T.STEER_RETURN : T.STEER_SMOOTH;
    this.steer += (steer - this.steer) * (1 - Math.exp(-rate * dt));

    // --- where is the ground ---------------------------------------------
    const probe = T.PROBE + Math.min(1.2, this.vel.length() * dt * 2);
    const q = this.world.collider.ground(
      this.pos.x, this.pos.y, this.pos.z, this.up.x, this.up.y, this.up.z, probe);
    // The collider returns a shared scratch object; copy what we need out of it
    // before anything else can query.
    const g = { hit: q.hit, dist: q.dist, kind: q.kind, nx: q.nx, ny: q.ny, nz: q.nz };
    this.groundY = q.hit ? q.py : null;

    const wasGrounded = this.grounded;
    if (g.hit && g.dist <= T.RIDE_HEIGHT + T.SNAP) {
      this.grounded = true;
      this.coyote = T.COYOTE;
      this.groundN.set(g.nx, g.ny, g.nz);
      this.surface = g.kind;
    } else {
      this.coyote -= dt;
      this.grounded = this.coyote > 0 && g.hit;
      if (this.grounded) { this.groundN.set(g.nx, g.ny, g.nz); this.surface = g.kind; }
    }
    this.offroad = this.grounded && this.surface === KIND.OFFROAD;

    // A boost pad is armed by touching it and paid out over the seconds after,
    // so driving across one at an angle, or clipping the corner of one, is
    // worth the same as driving down it - the pad is a place, not a distance.
    // Re-arming while still on it is what makes a long pad hold the boost open
    // rather than starting a timer at the near end of it.
    // `onBoostPad` is a callback rather than a flag left on the car for
    // somebody to notice, for the same reason `onBump` and `onLand` are: this
    // runs once per *substep* and the frame loop reads the car once per frame,
    // so a flag set at 1/120 and read at 1/60 loses every other one - and a pad
    // taken at speed can easily be wholly inside a single frame.
    this.padBoost = Math.max(0, this.padBoost - dt);
    if (this.grounded && this.surface === KIND.BOOST) {
      if (this.padBoost <= 0) this.onBoostPad && this.onBoostPad();
      this.padBoost = T.PAD_BOOST;
    }
    // A cap is spent for a moment after it fires, which is the opposite rule to
    // a pad's. A pad *re-arms* while you stay on it, because a long pad should
    // hold the engine open all the way up Mount Joy's ramp. A cap must not:
    // `grounded` stays true across COYOTE and the ground probe still finds the
    // surface 2.6 units up, so a cap that re-armed every step would keep topping
    // the car's normal velocity back up to BOUNCE_VEL for as long as it could
    // still see the cap - which is a car pinned to a launch speed rather than
    // one thrown by it, and it fires the callback about eight times per hop.
    this.bounceLock = Math.max(0, this.bounceLock - dt);

    // --- gravity, always -------------------------------------------------
    this.vel.y -= T.GRAVITY * dt;

    if (this.grounded) {
      const prevAir = this.airTime;
      this.airTime = 0;
      const n = this.groundN;

      // Ride height. Penetrating is corrected positionally (we are inside the
      // road and have to come out); drooping is corrected by the suspension
      // spring, as a force, so cresting a ramp pulls the car back down over a
      // few frames instead of yanking it.
      const pen = T.RIDE_HEIGHT - g.dist;
      if (pen > 0) {
        this.pos.addScaledVector(n, pen * Math.min(1, dt * 42));
      } else if (pen < 0) {
        this.vel.addScaledVector(n, T.SUSP * pen * dt);
      }
      // Cancel motion into the surface (this is also the landing impact) -
      // unless the surface is a mushroom cap, which reflects it instead.
      //
      // The bounce is deliberately *this* line rather than a term added after
      // it. Cancelling the landing and then launching would spend one step with
      // the car resting on the cap, and a step on the ground is a step of grip,
      // of the suspension spring and of ALIGN_GROUND - which came out as a
      // visible squash before the throw, and read as the cap catching the car
      // rather than rejecting it.
      const vn = this.vel.dot(n);
      let bounced = false;
      if (this.surface === KIND.BOUNCE && this.bounceLock <= 0) {
        // `-vn` is how fast we are going *into* the cap, so it is positive on
        // any real arrival and zero for a car that merely rolled onto one. The
        // larger of the floor and the reflection, never the sum - see
        // BOUNCE_VEL in tuning.py.
        const out = Math.max(T.BOUNCE_VEL, -vn * T.BOUNCE_REST);
        // Guarded rather than assigned, so a cap can never *slow* a car that is
        // already leaving faster than it would have thrown it.
        if (out > vn) this.vel.addScaledVector(n, out - vn);
        this.bounceLock = T.BOUNCE_LOCK;
        bounced = true;
        this.onBounce && this.onBounce(out);
      } else if (vn < 0) {
        this.vel.addScaledVector(n, -vn);
      }

      // Hold the car onto a surface only where nothing else could hold it: past
      // STICK_TILT (about 32 degrees) and on into fully inverted, which in
      // practice means a corkscrew and nothing else. Ordinary hills, ramps and
      // banked corners get no help whatsoever - go over a crest and you fly,
      // which is the whole point.
      //
      // Nothing is needed on the *concave* parts of a corkscrew either: there
      // the road curves up to meet the car, so travelling in a straight line
      // puts it inside the surface and the ride-height term does the work. The
      // pull is only ever paying for the convex half.
      const along = n.dot(UP);
      if (along < T.STICK_TILT) {
        const sp = this.vel.length();
        const f = Math.min(1, (T.STICK_TILT - along) / 0.45) *
                  Math.min(1, sp / T.STICK_SPEED);
        this.vel.addScaledVector(n, -T.STICK_FORCE * f * dt);
      }

      // Steering: yaw about the surface normal.
      const sp = this.vel.length();
      let yaw = this.steerRate(sp) * this.steer;
      if (handbrake) yaw *= T.DRIFT_STEER_BONUS;
      // Ease off when nearly stopped so the car cannot pirouette on the spot.
      yaw *= Math.min(1, sp / 3.5);
      this._spin(n, -yaw * dt);

      // --- longitudinal -------------------------------------------------
      let vLong = this.vel.dot(this.fwd);
      let a = 0;
      if (throttle > 0 && brake > 0) {
        a = -T.BRAKE * 0.45;                       // both pedals: hold it there
      } else if (throttle > 0) {
        // The slipstream is more engine, not a raised limit: top speed is where
        // ACCEL fights DRAG, so the multiplier lifts it by its square root and
        // the car has to accelerate up to the new one. On the throttle only -
        // a tow is a bigger top end, not free speed while you coast.
        //
        // Being down the road is the same kind of help and so it is the same
        // kind of term, and the two multiply: a car that spent the last minute
        // alone and has finally caught somebody is precisely the one that
        // should have enough to come past. See `catchup` below for the gap it
        // is read off, and tuning.py for why it is much the smaller of the two.
        // A pad is the same kind of help and so it is the same kind of term -
        // but the pad and the tow take the **larger** of the two rather than
        // multiplying. Three multipliers at once is 92 u/s against a clamp of
        // 85, which would leave the clamp setting the top speed instead of the
        // tuning; and a tow is earned where a pad is handed to everybody who
        // drives over it, so stacking them would make a pad worth most to the
        // car that was already being helped. See tuning.py.
        const help = Math.max(this.slipBoost > 0 ? T.SLIP_ACCEL_MULT : 1,
                              this.padBoost > 0 ? T.PAD_ACCEL_MULT : 1);
        let eng = T.ACCEL * help;
        if (this.catchupBoost > 0) {
          eng *= 1 + this.catchupBoost * (T.CATCHUP_ACCEL_MULT - 1);
        }
        a = (vLong < -0.5 ? T.BRAKE : eng) * throttle;
      } else if (brake > 0) {
        a = vLong > 0.5 ? -T.BRAKE * brake
                        : -T.REVERSE_ACCEL * brake * (vLong > -T.REVERSE_MAX ? 1 : 0);
      } else {
        a = -Math.sign(vLong) * Math.min(T.COAST, Math.abs(vLong) / dt);
      }
      a -= Math.sign(vLong) * T.DRAG * vLong * vLong;
      if (this.offroad) a -= Math.sign(vLong) * T.OFFROAD_DRAG * Math.abs(vLong);
      this.vel.addScaledVector(this.fwd, a * dt);

      // --- grip ----------------------------------------------------------
      let grip = handbrake ? T.DRIFT_GRIP : T.GRIP;
      // A hit lets the tyres go for a moment, and this is the only reason
      // contact moves a car at all: grip kills lateral velocity at
      // `1 - exp(-grip*dt)` per step, so a sideways impulse on full grip is
      // gone inside a tenth of a second however large it is. Ramped out with
      // the timer rather than switched off, so the car is caught back rather
      // than snapping straight. See BUMP_SLIP_GRIP in tuning.py.
      if (this.bumpSlip > 0) {
        const k = Math.min(1, this.bumpSlip / T.BUMP_SLIP_TIME);
        grip += (T.BUMP_SLIP_GRIP - grip) * k;
      }
      // Grass wins, and it has to be applied after the two above rather than
      // among them: it is the *worst* surface you are on, not one opinion of
      // several, so a hit on the grass cannot hand back grip the grass took.
      if (this.offroad) grip = Math.min(grip, T.OFFROAD_GRIP);
      const vLat = this.vel.dot(this.right);
      this.vel.addScaledVector(this.right, -vLat * (1 - Math.exp(-grip * dt)));
      this.slip = Math.min(1, Math.abs(vLat) / 12);

      // Note what is deliberately *not* here: a term that scrubs off velocity
      // along the surface normal. There used to be one, to stop the car skipping
      // over ramp seams, and it was what made the car feel glued to every slope
      // - it ate the launch a crest had just given it. Hills are eased in
      // tracks.py so they have no seam to skip on, and the suspension spring
      // above covers what is left.

      this._alignUp(n, T.ALIGN_GROUND, dt);
      // A cap does not thud. `onBounce` has already fired for this contact, and
      // letting the landing fire as well is two sounds and two camera kicks for
      // one event - and the louder of the two is the impact, so a hop off the
      // biggest drop on the track reads as hitting the mushroom rather than as
      // being thrown by it.
      if (!wasGrounded && prevAir > 0.15 && !bounced) {
        this.onLand && this.onLand(prevAir);
      }
    } else {
      // --- airborne -------------------------------------------------------
      this.airTime += dt;
      this.slip = 0;
      // Yaw with steering, pitch with the pedals - Trackmania's air control,
      // which is what makes a long jump something you can actually aim.
      this._spin(this.up, -this.steerRate(this.vel.length()) * T.AIR_STEER * this.steer * dt);
      const pitch = (brake > 0 ? 1 : 0) - (throttle > 0 ? 1 : 0);
      if (pitch) this._spin(this.right, pitch * T.AIR_PITCH * dt);
      else this._alignUp(UP, T.ALIGN_AIR, dt);
      const vLat = this.vel.dot(this.right);
      this.vel.addScaledVector(this.right, -vLat * (1 - Math.exp(-T.AIR_GRIP * dt)));
    }

    // --- integrate --------------------------------------------------------
    this.pos.addScaledVector(this.vel, dt);

    // --- walls ------------------------------------------------------------
    this._resolveWalls(dt);

    // Absolute safety cap; drag does the real speed limiting. It sits above
    // MAX_SPEED because a long descent legitimately overspeeds the car.
    const hard = T.MAX_SPEED * 1.7;
    if (this.vel.lengthSq() > hard * hard) this.vel.setLength(hard);

    this.speed = this.vel.length();
    this.wheelSpin += (this.vel.dot(this.fwd) / 0.45) * dt;
    this.bumpLean *= Math.exp(-7 * dt);
    if (this.bumpTimer > 0) this.bumpTimer -= dt;
    // Out here with the other timers rather than in the grounded branch that
    // reads it: a car knocked into the air would otherwise hold the whole of
    // its let-go tyres frozen for the length of the flight and land on them.
    if (this.bumpSlip > 0) this.bumpSlip = Math.max(0, this.bumpSlip - dt);

    // --- fell off ---------------------------------------------------------
    if (this.pos.y < this.world.killY) this.requestRespawn();
  }

  /**
   * Push out of walls once per step.
   *
   * A wall is many triangles and the car has two collision spheres, so a single
   * contact can be reported several times. Responding to each report separately
   * multiplies the speed penalty and can fight itself between neighbouring
   * triangles, so every contact this step is accumulated into one
   * depth-weighted direction and answered with a single push, one reflection and
   * one speed scrub.
   */
  _resolveWalls(dt) {
    const T = this.T;
    const R = T.CAR_RADIUS;
    const offs = [(T.CAR_LEN / 2 - R), -(T.CAR_LEN / 2 - R)];
    let ax = 0, ay = 0, az = 0, deepest = 0, hits = 0;
    for (const o of offs) {
      _v1.copy(this.pos).addScaledVector(this.fwd, o);
      this.world.collider.walls(_v1.x, _v1.y, _v1.z, R, (nx, ny, nz, depth) => {
        ax += nx * depth; ay += ny * depth; az += nz * depth;
        if (depth > deepest) deepest = depth;
        hits++;
      });
    }
    if (hits) {
      const len = Math.hypot(ax, ay, az);
      if (len > 1e-6) {
        _v2.set(ax / len, ay / len, az / len);
        this.pos.addScaledVector(_v2, deepest);
        const vn = this.vel.dot(_v2);
        if (vn < 0) {
          // keep the tangential part, reverse a little of the normal part
          this.vel.addScaledVector(_v2, -vn * (1 + T.WALL_BOUNCE));
          this.vel.multiplyScalar(1 - (1 - T.WALL_SCRUB) * Math.min(1, -vn / 18));
          if (-vn > 8 && this._wallHit <= 0) {
            this._wallHit = 0.18;
            this.onWall && this.onWall(-vn, this.pos);
          }
        }
      }
    }
    if (this._wallHit > 0) this._wallHit -= dt;
  }

  /**
   * Mario-Kart-style car-to-car contact.
   *
   * The two rules that make bumping feel smooth rather than sticky or jittery:
   *
   * - **Never move a car to fix an overlap.** Penetration is resolved by adding
   *   velocity along the contact normal, in proportion to how deep the overlap is
   *   (a spring). Position snapping is what makes networked bumping jitter,
   *   because every correction fights the next packet.
   * - **Only the normal component is touched.** Velocity along the contact is left
   *   alone, so two cars side by side slide along each other and separate
   *   naturally instead of snagging.
   *
   * The rule is symmetric and mass-weighted, so the other client computing the
   * same contact for its own car arrives at the mirrored result: both cars get
   * shoved apart by agreement, and nobody's position is ever overwritten.
   *
   * `others` is [{pos, vel, fwd, mass, id}] for the interpolated remote cars.
   */
  resolveCars(others, dt) {
    if (!others || !others.length) return;
    const T = this.T;
    const R = T.CAR_RADIUS;
    const half = T.CAR_LEN / 2 - R;
    const REST = T.CAR_REST;            // barely bouncy: one clean shove
    const myMass = 1;

    for (const o of others) {
      if (!o || o.id === this.id) continue;
      const mass = o.mass || 1;
      const share = mass / (myMass + mass);     // 0.5 for equal cars
      let hit = 0, hx = 0, hy = 0, hz = 0;

      for (const a of [half, -half]) {
        for (const b of [half, -half]) {
          const ax = this.pos.x + this.fwd.x * a, ay = this.pos.y + this.fwd.y * a,
                az = this.pos.z + this.fwd.z * a;
          const bx = o.pos.x + o.fwd.x * b, by = o.pos.y + o.fwd.y * b,
                bz = o.pos.z + o.fwd.z * b;
          let nx = ax - bx, ny = ay - by, nz = az - bz;
          const d = Math.hypot(nx, ny, nz);
          const min = R * 2;
          if (d >= min || d < 1e-6) continue;
          nx /= d; ny /= d; nz /= d;
          const depth = min - d;

          // 1. spring out of the overlap (a force, so it is frame-rate safe)
          const push = T.CAR_PUSH * depth * share * dt;
          this.vel.x += nx * push; this.vel.y += ny * push * 0.35; this.vel.z += nz * push;

          // 2. exchange momentum along the normal, if we are closing
          const rvx = this.vel.x - o.vel.x, rvy = this.vel.y - o.vel.y, rvz = this.vel.z - o.vel.z;
          const vn = rvx * nx + rvy * ny + rvz * nz;
          if (vn < 0) {
            const j = -(1 + REST) * vn * share;
            this.vel.x += nx * j; this.vel.y += ny * j * 0.4; this.vel.z += nz * j;
            if (-vn > hit) { hit = -vn; hx = nx; hy = ny; hz = nz; }
          }
        }
      }

      // **A hit is an event, and everything it does happens once.**
      //
      // The separation spring and the momentum exchange above are forces and
      // belong per step. Nothing below is: they are all reactions to a *hit*,
      // and applying them per step of contact compounds them - which was
      // already true of the speed scrub (0.88 a frame is nothing after half a
      // second, hence the cooldown) and quietly true of the other two as well.
      // The body lean climbed to its own clamp inside a tenth of a second of
      // rubbing, so a car in sustained contact drove along at 29 degrees of
      // roll; and the yaw is an angle with no `dt` on it, so at 120 steps a
      // second it was worth radians a second for as long as the cars touched -
      // which is the spin this is not supposed to be able to cause. One hit,
      // one cost, one clank, one nudge.
      if (hit > T.BUMP_FEEL) {
        const key = o.id || 'x';
        if ((this._bumpCooldown.get(key) || 0) <= 0) {
          this._bumpCooldown.set(key, 0.15);
          const side = hx * this.right.x + hy * this.right.y + hz * this.right.z;
          this.bumpLean = Math.max(-0.5, Math.min(0.5, this.bumpLean + side * hit * 0.02));
          // **Told about every touch, charged for the firm ones**, because they
          // are two questions: there is no contact a driver should not hear,
          // and a second and a half of gentle rubbing is about ten of these -
          // charging speed for each would bleed a car for touching somebody.
          // See BUMP_FEEL / BUMP_COST in tuning.py.
          if (hit > T.BUMP_COST) {
            this.vel.multiplyScalar(1 - (1 - T.CAR_BUMP_SCRUB) * Math.min(1, hit / 22));
            // a whisper of yaw so a side hit reads as a nudge, never a spin
            this._spin(this.up, -side * Math.min(hit, 20) * 0.0035);
            // And the tyres let go, which is the only thing here that actually
            // moves the car - grip eats a sideways impulse inside a tenth of a
            // second whatever its size.
            //
            // Deliberately *not* scaled by how hard the hit was, though every
            // instinct says it should be: the impulse it is letting through is
            // already proportional to the hit, so scaling the window as well
            // squares it, and a firm-but-not-huge shunt ends up moving the car
            // less than the same shunt on full grip would suggest. One window,
            // and the physics does the scaling - measured 0.39 units of
            // displacement at 6 u/s against 1.47 at 20.
            this.bumpSlip = T.BUMP_SLIP_TIME;
          }
          this.lastBump = { x: this.pos.x + hx * -1.0, y: this.pos.y, z: this.pos.z + hz * -1.0,
                            mag: hit };
          this.onBump && this.onBump(hit);
        }
      }
    }
    for (const [k, v] of this._bumpCooldown) {
      const nv = v - dt;
      if (nv <= 0) this._bumpCooldown.delete(k); else this._bumpCooldown.set(k, nv);
    }
  }

  /**
   * The slipstream: charge up behind somebody, then get fired past them.
   *
   * Mario Kart Wii's draft, because that is the version of this everybody has
   * already played. Sitting in the hole another car is punching through the air
   * pays **nothing** while it fills - and then the whole of it arrives at once
   * as `slipBoost` seconds of extra engine. A trickle of speed for following
   * somebody would be invisible and unearned; a boost you spent a second and a
   * half lining up is a move you decided to make.
   *
   * What counts as "in the tow" is measured in the *following* car's own frame,
   * so it works upside down in a loop and up the wall of a bank exactly as it
   * does on the flat: they must be ahead along your forward axis, inside a
   * narrow corridor either side of it and above/below it, and pointing roughly
   * the way you are - you tow off a car you are chasing, never one coming the
   * other way or crossing at a junction.
   *
   * Nothing accumulates while the boost is running, so the cadence is charge,
   * fire, charge again rather than a permanent tow behind a car you cannot pass.
   * Call it with a falsy `others` (which is what the phases with no contact in
   * them do) and it bleeds both the charge and the boost away.
   */
  draft(others, dt) {
    const T = this.T;
    let towed = false;
    if (others && others.length && this.grounded && this.respawnIn <= 0
        && this.speed > T.SLIP_MIN_SPEED) {
      for (const o of others) {
        if (!o || o.id === this.id) continue;
        const dx = o.pos.x - this.pos.x, dy = o.pos.y - this.pos.y, dz = o.pos.z - this.pos.z;
        const ahead = dx * this.fwd.x + dy * this.fwd.y + dz * this.fwd.z;
        if (ahead <= T.CAR_LEN || ahead > T.SLIP_RANGE) continue;
        const lat = dx * this.right.x + dy * this.right.y + dz * this.right.z;
        if (Math.abs(lat) > T.SLIP_HALF_W) continue;
        const vert = dx * this.up.x + dy * this.up.y + dz * this.up.z;
        if (Math.abs(vert) > T.SLIP_HALF_W) continue;
        if (o.fwd && this.fwd.dot(o.fwd) < T.SLIP_ALIGN) continue;
        towed = true;
        break;
      }
    }
    this.towed = towed;

    if (this.slipBoost > 0) {
      this.slipBoost = Math.max(0, this.slipBoost - dt);
    } else if (towed) {
      this.slipCharge += dt / T.SLIP_CHARGE;
      if (this.slipCharge >= 1) {
        this.slipCharge = 0;
        this.slipBoost = T.SLIP_BOOST;
        this.onSlipstream && this.onSlipstream();
      }
    } else if (this.slipCharge > 0) {
      this.slipCharge = Math.max(0, this.slipCharge - dt / T.SLIP_DECAY);
    }
  }

  /**
   * A little more engine for being behind, in proportion to how far behind.
   *
   * A race in which somebody drops a few seconds is decided, and everybody in
   * it drives the rest of the lap alone - so a car down the road gets some of
   * the deficit back as engine, and the gap that was going to end the race
   * closes into a fight instead. `gapS` is how far behind the leader you are,
   * in seconds; the caller decides who the leader is and whether there is a
   * race at all, and hands `null` when there is not.
   *
   * Three things this deliberately is not:
   *
   * - **Not a cliff.** Nothing at all inside `CATCHUP_DEAD`, then a linear ramp
   *   to the whole of it at `CATCHUP_FULL`. A step change in engine force at a
   *   threshold is a car that surges every time the gap wobbles across it.
   * - **Not instant.** The gap arrives 30 times a second, rounded, off a car
   *   whose own position is being extrapolated - so the help *follows* it at
   *   `CATCHUP_SMOOTH` rather than tracking it exactly. Half a second of lag on
   *   a number that is meant to describe the last ten seconds costs nothing and
   *   is the difference between more engine and a car that hunts.
   * - **Not a raised limit.** Like the tow, it multiplies the throttle term in
   *   `step`, so it is worth its square root in top speed and only while you
   *   are actually on the power.
   *
   * Call it every frame, `null` included: that is what bleeds the help away
   * when the race ends or you take the lead, rather than leaving the last value
   * live on a car nobody is racing.
   */
  catchup(gapS, dt) {
    const T = this.T;
    let want = 0;
    if (gapS != null && gapS > T.CATCHUP_DEAD) {
      want = Math.min(1, (gapS - T.CATCHUP_DEAD) / (T.CATCHUP_FULL - T.CATCHUP_DEAD));
    }
    this.catchupBoost += (want - this.catchupBoost) * (1 - Math.exp(-T.CATCHUP_SMOOTH * dt));
    // An exponential approach never actually arrives, so the last hundredth of
    // the way *down* is snapped off: below that it is a fifth of a percent of
    // engine - not a thing anybody could drive - and without the snap the
    // multiplier in `step` is live for ever on a car that stopped being helped
    // minutes ago. Only on the way down, and that is not a detail: every ramp
    // up starts at zero and passes through the same hundredth, so snapping it
    // in both directions pins the help at nothing and it never climbs at all.
    if (want === 0 && this.catchupBoost < 0.01) this.catchupBoost = 0;
  }

  requestRespawn() {
    if (this.respawnIn > 0) return;
    this.respawnIn = this.T.RESPAWN_DELAY;
    this.vel.set(0, 0, 0);
    this.onFall && this.onFall();
  }

  /** Where to reappear: supplied by the run logic (last checkpoint). */
  setRespawn(p, fwd) {
    this._respawn = { p: [p[0], p[1], p[2]], fwd: [fwd[0], fwd[1], fwd[2]] };
  }

  _doRespawn() {
    const r = this._respawn || { p: [this.world.line[0].p[0], this.world.line[0].p[1],
                                     this.world.line[0].p[2]], fwd: [0, 0, 1] };
    this.placeAt(r.p, r.fwd);
    this.onRespawned && this.onRespawned();
  }

  flags() {
    let f = 0;
    if (this.slip > 0.35) f |= FLAG.DRIFT;
    if (!this.grounded) f |= FLAG.AIR;
    if (this.respawnIn > 0) f |= FLAG.RESPAWN;
    if (this.braking) f |= FLAG.BRAKE;
    if (this.slipBoost > 0) f |= FLAG.SLIP;
    return f;
  }
}

/**
 * Steps the car with a fixed timestep and reports how far into the next step we
 * are, so rendering can interpolate and never judder.
 */
export class Stepper {
  constructor(T) { this.T = T; this.acc = 0; }
  /**
   * Throw away the part-accumulated step.
   *
   * Called when a lap clock starts, and it is a fairness fix rather than
   * housekeeping. `acc` holds up to one `FIXED_DT` of time carried over from the
   * previous frame; left alone across the start it buys a **whole extra substep**
   * of throttle before the clock reads zero, on a coin-flip. Measured on the real
   * board that was worth up to ~33ms of unrecorded distance, and the drivers it
   * favoured were the ones whose frame happened to be long - so a stutter was an
   * advantage. See `_recordGhost` and the note in `drive/docs/runs-and-scoring.md`.
   */
  reset() { this.acc = 0; }
  run(realDt, fn) {
    const T = this.T;
    this.acc += Math.min(realDt, 0.25);
    let steps = 0;
    while (this.acc >= T.FIXED_DT && steps < T.MAX_STEPS) {
      fn(T.FIXED_DT);
      this.acc -= T.FIXED_DT;
      steps++;
    }
    if (steps === T.MAX_STEPS) this.acc = 0;   // do not fast-forward a tabbed-out car
    return this.acc / T.FIXED_DT;
  }
}
