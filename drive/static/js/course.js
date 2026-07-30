// Where you are on the track, and whether that counts.
//
// Two jobs:
//
// `Course` answers geometry questions about the centreline - how far along you
// are (which is what live race positions and the minimap are built from), which
// way the road is pointing (wrong-way warnings, respawn facing), and which
// checkpoint you last passed.
//
// `Run` owns a single timed attempt: gate crossings in order, splits, the
// finish, and the ghost recording that gets submitted with the time. It treats
// crossing a gate as a *plane crossing*, not a volume overlap, so it cannot be
// missed at speed - at 60 u/s a car moves a metre per physics step, and a
// trigger box would be a lottery.

const GHOST_HZ = 15;

export class Course {
  constructor(built) {
    this.line = built.line;
    this.s = built.s;
    this.total = built.total;
    this.gates = built.gates;
    this.killY = built.killY;
    this.collider = built.collider;
    this.hint = 0;
    // How close to a gate the car has to be, along the gate's own axis, before
    // its crossings are watched at all. Wide enough that even a boosted car
    // spends many physics steps inside it; narrow enough that a different part
    // of the track lying on the same line cannot trip it.
    this.gateNear = 20;
  }

  /** Put the hint back where we know the car is (after a respawn or a teleport). */
  resetHint(idx) { this.hint = Math.max(0, Math.min(this.line.length - 1, idx | 0)); }

  /**
   * Where the car is on the centreline: {idx, s, dist, lateral}.
   *
   * The search is **local and forward-biased**, and only falls back to a global
   * sweep if the local window finds nothing plausible. That matters more than it
   * sounds: a loop passes back over its own entry and a figure-eight crosses
   * itself, so the globally nearest centreline sample can belong to a completely
   * different part of the lap. Snapping to it would make race positions jump,
   * fire the wrong-way warning mid-loop and confuse the live split.
   *
   * `dist` is the true perpendicular distance to the road's centreline, not the
   * distance to the nearest sample - samples are a cell apart, so the naive
   * version reads several metres off even when the car is perfectly centred.
   */
  locate(pos, hint) {
    const line = this.line;
    const n = line.length;
    if (hint == null) hint = this.hint;

    let best = -1, bestD = Infinity;
    const scan = (from, to) => {
      const lo = Math.max(0, from), hi = Math.min(n - 1, to);
      for (let i = lo; i <= hi; i++) {
        const p = line[i].p;
        const d = (p[0] - pos.x) ** 2 + (p[1] - pos.y) ** 2 + (p[2] - pos.z) ** 2;
        if (d < bestD) { bestD = d; best = i; }
      }
    };
    scan(hint - 8, hint + 34);
    // Nothing within 26 units of the window means we really did move somewhere
    // else (respawn, race grid) rather than simply driving on.
    if (best < 0 || bestD > 26 * 26) { bestD = Infinity; best = -1; scan(0, n - 1); }
    if (best < 0) return { idx: 0, s: 0, dist: 0, lateral: 0 };
    this.hint = best;

    // Project onto whichever of the two adjoining segments is closer.
    let s = this.s[best], dist = Math.sqrt(bestD);
    for (const j of [best - 1, best + 1]) {
      if (j < 0 || j >= n) continue;
      const a = line[Math.min(best, j)].p, b = line[Math.max(best, j)].p;
      const sa = this.s[Math.min(best, j)];
      const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
      const len2 = dx * dx + dy * dy + dz * dz;
      if (len2 < 1e-9) continue;
      let t = ((pos.x - a[0]) * dx + (pos.y - a[1]) * dy + (pos.z - a[2]) * dz) / len2;
      t = Math.max(0, Math.min(1, t));
      const cx = a[0] + dx * t, cy = a[1] + dy * t, cz = a[2] + dz * t;
      const d = Math.hypot(pos.x - cx, pos.y - cy, pos.z - cz);
      if (d < dist) { dist = d; s = sa + t * Math.sqrt(len2); }
    }

    // Signed offset across the road, for anything that needs "how far wide am I".
    // In full 3D, not just XZ: inside a corkscrew the road's lateral axis has a
    // large vertical component (at the quarter turn it is vertical), and an
    // XZ-only projection reports nearly zero however far wide the car is.
    const lat = line[best].lat;
    const lp = line[best].p;
    const lateral = (pos.x - lp[0]) * lat[0] + (pos.y - lp[1]) * lat[1] +
                    (pos.z - lp[2]) * lat[2];

    return { idx: best, s: Math.max(0, Math.min(this.total, s)), dist, lateral };
  }

  /** Index of the centreline sample at (or just before) distance `s`. */
  indexAtS(s) {
    const arr = this.s;
    let lo = 0, hi = arr.length - 1;
    if (s <= 0) return 0;
    if (s >= arr[hi]) return hi;
    while (lo < hi - 1) {
      const mid = (lo + hi) >> 1;
      if (arr[mid] <= s) lo = mid; else hi = mid;
    }
    return lo;
  }

  /** Point on the centreline at distance `s` along it. */
  pointAtS(s) {
    const i = this.indexAtS(s);
    const j = Math.min(this.line.length - 1, i + 1);
    const a = this.line[i].p, b = this.line[j].p;
    const seg = this.s[j] - this.s[i];
    const u = seg > 1e-6 ? Math.max(0, Math.min(1, (s - this.s[i]) / seg)) : 0;
    return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
  }

  /** Unit tangent of the road at centreline index i. */
  tangent(i) {
    const line = this.line;
    const a = line[Math.max(0, i - 1)].p, b = line[Math.min(line.length - 1, i + 1)].p;
    const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
    const len = Math.hypot(dx, dy, dz) || 1;
    return [dx / len, dy / len, dz / len];
  }

  startGate() { return this.gates.find(g => g.kind === 'start') || null; }
  checkpoints() { return this.gates.filter(g => g.kind === 'cp'); }
  finishGate() { return this.gates.find(g => g.kind === 'finish') || null; }
}

export class Run {
  /**
   * @param course Course
   * @param track  the raw track dict (for slug/checkpoint count/medals)
   */
  constructor(course, track) {
    this.course = course;
    this.track = track;
    this.cps = course.checkpoints();
    this.finish = course.finishGate();
    this.reset();
  }

  reset() {
    this.state = 'ready';        // ready -> running -> done
    this.startedAt = 0;          // ms on the caller's clock
    this.time = 0;               // ms
    this.splits = [];
    this.nextCp = 0;
    this.missed = false;
    this.distance = 0;
    this.ghost = [];
    this._ghostN = 0;
    this._prevPose = null;
    this._sides = new Map();     // gate -> which side of its plane we were on
    this._lastPos = null;
    this.respawnGate = this.course.startGate();
    this.wrongWay = false;
    this.bestS = 0;
    this.course.resetHint(0);
  }

  /** Begin timing. In a race the caller passes the shared green-light time. */
  start(nowMs) {
    if (this.state === 'running') return;
    this.state = 'running';
    this.startedAt = nowMs;
    this.time = 0;
    this.splits = [];
    this.nextCp = 0;
    this.missed = false;
    this.distance = 0;
    this.ghost = [];
    this._ghostN = 0;
    this._prevPose = null;
    this._sides.clear();
  }

  /**
   * Record ghost frame `i` as the pose at exactly `i / GHOST_HZ` seconds.
   *
   * This used to be a dt accumulator - add the frame time, push a sample every
   * time a sixteenth of a second had gone by - which quietly recorded frame 0
   * one whole interval *after* the start, because the accumulator has to fill
   * before it fires. Playback reads frame `t * GHOST_HZ` at run time `t`, so
   * every ghost ran 1/15s ahead of the lap it was recording: a car and a half
   * up the road at racing speed, from the line to the flag. That is the "the
   * ghost starts ahead of me" bug, and it applied to every ghost ever saved.
   *
   * Interpolating to the sample time rather than pushing the pose we happen to
   * be holding also takes the frame rate out of it, so a ghost recorded at
   * 30fps lines up with the same lap replayed at 144.
   */
  _recordGhost(pos, quat) {
    const t = this.time / 1000;
    const cur = [pos.x, pos.y, pos.z, quat.x, quat.y, quat.z, quat.w];
    while (this._ghostN / GHOST_HZ <= t) {
      const want = this._ghostN / GHOST_HZ;
      const prev = this._prevPose;
      if (!prev || want >= t || t <= prev.t) {
        this.ghost.push(cur.slice());
      } else {
        const u = Math.max(0, Math.min(1, (want - prev.t) / (t - prev.t)));
        const p = prev.f;
        // Quaternions are lerped, not slerped: 1/15s of yaw is a few degrees,
        // and playback normalises anyway. The sign fix matters more than the
        // arc does - without it a quaternion that flipped sign between samples
        // interpolates the long way round and the ghost snaps.
        const dot = p[3] * cur[3] + p[4] * cur[4] + p[5] * cur[5] + p[6] * cur[6];
        const sgn = dot < 0 ? -1 : 1;
        this.ghost.push([
          p[0] + (cur[0] - p[0]) * u, p[1] + (cur[1] - p[1]) * u, p[2] + (cur[2] - p[2]) * u,
          p[3] + (cur[3] * sgn - p[3]) * u, p[4] + (cur[4] * sgn - p[4]) * u,
          p[5] + (cur[5] * sgn - p[5]) * u, p[6] + (cur[6] * sgn - p[6]) * u,
        ]);
      }
      this._ghostN++;
    }
    this._prevPose = { t, f: cur };
  }

  _side(gate, pos) {
    return (pos.x - gate.p[0]) * gate.f[0] + (pos.y - gate.p[1]) * gate.f[1] +
           (pos.z - gate.p[2]) * gate.f[2];
  }

  /**
   * Is the car actually passing *through* the gate, rather than merely crossing
   * the infinite plane it sits in?
   *
   * The vertical window has to be tight. A track that crosses over itself (the
   * figure-eight's bridge is two levels up) would otherwise let a car on the
   * bridge trigger the checkpoint on the road underneath it - which is exactly
   * what happened before this was clamped. It still has to be tall enough to
   * credit a car that flies through a gate slightly airborne.
   */
  _withinGate(gate, pos) {
    const lx = (pos.x - gate.p[0]) * gate.r[0] + (pos.z - gate.p[2]) * gate.r[2];
    const dy = pos.y - gate.p[1];
    // Laterally generous by a bit more than a car's width past the kerb, so
    // running two wheels onto the grass through a gate still counts.
    return Math.abs(lx) <= gate.hw + 2.5 && dy > -2.5 && dy < 5.0;
  }

  /**
   * Advance the run. Returns a list of event strings for sound/HUD:
   * 'cp', 'finish', 'missed'.
   */
  update(car, nowMs) {
    const events = [];
    const pos = car.pos;

    const loc = this.course.locate(pos);
    this.s = loc.s;
    if (loc.s > this.bestS) this.bestS = loc.s;

    // wrong way: are we pointing against the road?
    const t = this.course.tangent(loc.idx);
    const dot = car.fwd.x * t[0] + car.fwd.y * t[1] + car.fwd.z * t[2];
    this.wrongWay = this.state === 'running' && car.speed > 6 && dot < -0.4;

    if (this.state === 'running') {
      this.time = nowMs - this.startedAt;
      if (this._lastPos) {
        this.distance += Math.hypot(pos.x - this._lastPos[0], pos.y - this._lastPos[1],
                                    pos.z - this._lastPos[2]);
      }
      // Record the ghost at a fixed rate regardless of frame rate.
      this._recordGhost(pos, car.quat);

      // Gate crossings.
      //
      // The side of a gate is only tracked while the car is actually in that
      // gate's mouth and within a couple of cells of it. Tracking it everywhere
      // is subtly broken: a gate's plane is infinite, so a car crossing it
      // somewhere else on the track flips the remembered side to "past it", and
      // the real pass later produces no sign change and never counts. That is
      // exactly how two of three checkpoints silently went missing.
      const NEAR = this.course.gateNear;
      const check = (gate, onCross) => {
        const side = this._side(gate, pos);
        if (Math.abs(side) > NEAR || !this._withinGate(gate, pos)) {
          this._sides.delete(gate);
          return;
        }
        const prev = this._sides.get(gate);
        this._sides.set(gate, side);
        if (prev !== undefined && prev < 0 && side >= 0) onCross();
      };

      // Crossing the checkpoint you are due counts. Crossing any other one is
      // simply ignored - a track that runs back past its own gates, or a car
      // that clips a later gate's plane while cutting a corner, must not be able
      // to spoil a run that is otherwise legitimate. Validity is only ever "did
      // you cross all of them before the finish", checked at the finish.
      for (let i = 0; i < this.cps.length; i++) {
        const gate = this.cps[i];
        check(gate, () => {
          if (i !== this.nextCp) return;
          this.nextCp++;
          this.splits.push(Math.round(this.time));
          this.respawnGate = gate;
          this.missed = false;      // went back and got it: run is live again
          events.push('cp');
        });
      }
      if (this.finish) {
        check(this.finish, () => {
          if (this.nextCp >= this.cps.length) {
            this.state = 'done';
            this.time = Math.round(nowMs - this.startedAt);
            events.push('finish');
          } else {
            // Not a failed run - just go back and get the ones you skipped.
            this.missed = true;
            events.push('missed');
          }
        });
      }
    }

    this._lastPos = [pos.x, pos.y, pos.z];

    // Keep the car's respawn target up to date (last checkpoint reached).
    if (this.respawnGate) {
      const g = this.respawnGate;
      car.setRespawn([g.p[0], g.p[1] + 0.4, g.p[2]], g.f);
    }
    return events;
  }

  progress01() {
    return this.course.total ? Math.min(1, this.bestS / this.course.total) : 0;
  }
}

export const GHOST_RATE = GHOST_HZ;

/** Plays back a recorded run as a ghost car, interpolating between samples. */
export class Ghost {
  constructor(frames, hz) {
    this.frames = frames || [];
    this.hz = hz || GHOST_HZ;
    this.t = 0;
  }
  get duration() { return this.frames.length / this.hz; }
  /** Sample at time t seconds. Returns null past the end. */
  at(t) {
    if (!this.frames.length) return null;
    const f = t * this.hz;
    const i = Math.floor(f);
    if (i < 0) return this.frames[0];
    if (i >= this.frames.length - 1) return this.frames[this.frames.length - 1];
    const a = this.frames[i], b = this.frames[i + 1], u = f - i;
    return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u,
            a[3] + (b[3] - a[3]) * u, a[4] + (b[4] - a[4]) * u,
            a[5] + (b[5] - a[5]) * u, a[6] + (b[6] - a[6]) * u];
  }
}
