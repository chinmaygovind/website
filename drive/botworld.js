// The room's bots, as cars on a track, stepped by the server.
//
// This is the piece that makes a bot a *car* rather than a moving dot: it builds
// the same track the browsers built, puts real `Car`s on it, and runs the real
// `Car.step` at the real `FIXED_DT` with a `Bot` deciding what to press. Contact,
// the slipstream, boost pads, walls, respawns and the catch-up boost all come
// free, because none of them is bot code - they are what the car already does.
//
// It lives beside `botsim.py` rather than in `static/js` because no browser ever
// loads it. `bot.js` is in static/js, because it is game logic and could one day
// drive a car in one.
//
// **One stepper for the whole world, not one per bot.** Every car has to advance
// through the same instants or `resolveCars` is resolving contact between two
// cars that are at different times, which is how a shunt comes out asymmetric
// and cars start passing through each other.

const BOT_AI_EVERY = 2;      // decide at 60Hz while the physics runs at 120

class BotWorld {
  /**
   * `built` is an already-built track to share. The collider is by far the
   * largest thing here - 30-50MB - and it is read-only once built, so two rooms
   * on the same track use one. It must be passed in rather than assigned
   * afterwards: `Course` and every `Car` are constructed against it, and a world
   * whose course and cars disagree about which copy they are on is a world where
   * the walls are in a different place from the road.
   */
  constructor(track, T, built) {
    this.T = T;
    this.track = track;
    this.built = built || buildTrack(track, T);
    this.course = new Course(this.built);
    this.stepper = new Stepper(T);
    this.bots = [];
    this.humans = [];
    this.phase = 'free';
    this.since = null;         // seconds since the green light
    this._k = 0;
    this._others = [];
  }

  /**
   * Seat a bot.
   *
   * `line` is the path it will drive - the relaxed centreline for the slow
   * levels, the record holder's own lap for the quick ones - and `prof` is the
   * level. Both are handed in by `bots.py`, which is where a level *means*
   * something; nothing in JS knows what "hard" is.
   */
  add(pid, line, prof) {
    const car = new Car(this.T, this.built);
    // `resolveCars` skips `o.id === this.id` and keys its per-pair bump cooldown
    // off it, and a bare Car has no id at all - so without this every bot is
    // "undefined" to every other bot, they share one cooldown slot and a whole
    // grid of them registers one hit between them.
    car.id = pid;
    car.placeAt(this.track.spawn.p, this.track.spawn.fwd);
    const run = new Run(this.course, this.track);
    const bot = {
      pid, car, run,
      brain: new Bot(car, this.course, run, new BotLine(line), prof),
      input: { throttle: 0, brake: 0, steer: 0, handbrake: false },
      started: false, finished: null, splits: [], events: [],
    };
    bot.brain.reset();
    this.bots.push(bot);
    return bot;
  }

  remove(pid) {
    this.bots = this.bots.filter(b => b.pid !== pid);
  }

  get(pid) {
    for (const b of this.bots) if (b.pid === pid) return b;
    return null;
  }

  /** Put one on its grid slot. The same arithmetic `placeOnGrid` does in game.js. */
  placeGrid(pid, slot) {
    const b = this.get(pid);
    if (!b) return;
    const g = this.course.startGate();
    if (!g) return;
    const row = Math.floor(slot / 2);
    const back = 4 + row * 5.5 + (slot % 2 ? 2.4 : 0);
    const inside = this.track.pole_side || -1;
    const side = (slot % 2 ? -inside : inside);
    const lat = side * 2.1;
    b.car.placeAt([g.p[0] - g.f[0] * back + g.r[0] * lat,
                   g.p[1] + 0.3,
                   g.p[2] - g.f[2] * back + g.r[2] * lat], g.f);
    b.car.frozen = true;
    b.run.reset();
    b.started = false;
    b.finished = null;
    b.splits = [];
    b.brain.reset();
  }

  /**
   * Send one back out for another lap.
   *
   * What a bot does at the end of a lap in practice and in qualifying, because
   * the alternative is a car that finishes once and then sits at the side of
   * the road for the rest of the session. Placed on a grid slot rather than all
   * on the same spot, so a field of them going round does not pile up on the
   * line every ninety seconds.
   */
  restart(pid, slot, nowMs) {
    this.placeGrid(pid, slot);
    const b = this.get(pid);
    if (!b) return;
    b.car.frozen = false;
    b.run.start(nowMs);
    b.started = true;
  }

  /** Back to practice: everyone loose on the road again, nothing timed. */
  release() {
    for (const b of this.bots) {
      b.car.frozen = false;
      b.run.reset();
      b.started = false;
      b.finished = null;
      b.splits = [];
      b.brain.reset();
    }
  }

  /**
   * Where the people are.
   *
   * `[{pid, x, y, z, qx..qw, vx, vy, vz, prog, done}]`, straight off the poses
   * the room already has. They are given to the bots as things to hit, tow off
   * and race, and their `prog` is what the catch-up boost is measured against.
   * A human's pose is up to a tick old and half a ping older than that, which is
   * exactly as stale as every other car in this game is to every other browser.
   */
  setHumans(list) {
    this.humans = list || [];
  }

  /** Everything solid, in the shape `resolveCars` and `draft` want. */
  _rebuildOthers() {
    const out = [];
    for (const b of this.bots) {
      out.push({ pos: b.car.pos, vel: b.car.vel, fwd: b.car.fwd, mass: 1, id: b.pid });
    }
    for (const h of this.humans) {
      out.push({
        pos: { x: h.x, y: h.y, z: h.z },
        vel: { x: h.vx || 0, y: h.vy || 0, z: h.vz || 0 },
        // A pose carries a quaternion, not axes. Forward is -Z through it, which
        // is the one axis contact and the tow both need.
        fwd: quatFwd(h.qx, h.qy, h.qz, h.qw),
        mass: 1, id: h.pid,
      });
    }
    this._others = out;
  }

  /**
   * The gap to whoever is leading on the road, in seconds, for one bot.
   *
   * The same rule `gapToLeader` uses in game.js: distance along the ribbon,
   * divided by MAX_SPEED so it means the same thing on a short track and a long
   * one, and measured against the leader **still driving** - a car already home
   * is not being caught, and counting it would hand the whole field full help
   * the moment somebody crossed the line.
   */
  _gapFor(bot) {
    if (this.phase !== 'racing') return null;
    let lead = -1;
    for (const b of this.bots) {
      if (b.finished != null) continue;
      if (b.run.bestS > lead) lead = b.run.bestS;
    }
    for (const h of this.humans) {
      if (h.done) continue;
      if ((h.prog || 0) > lead) lead = h.prog || 0;
    }
    if (lead < 0) return null;
    const gap = lead - bot.run.bestS;
    return gap > 0 ? gap / this.T.MAX_SPEED : 0;
  }

  _think(nowMs) {
    this._rebuildOthers();
    for (const b of this.bots) {
      if (b.finished != null) {
        // Home. Off the throttle and out of everybody's way, but still a solid
        // car - a finisher parked on the racing line is a hazard, and slowing
        // to a stop where you crossed the line is what a person does too.
        b.input = { throttle: 0, brake: 0.4, steer: b.input.steer * 0.5, handbrake: false };
        continue;
      }
      const rivals = [];
      for (const o of this._others) {
        if (o.id === b.pid) continue;
        rivals.push({ x: o.pos.x, y: o.pos.y, z: o.pos.z });
      }
      b.input = b.brain.drive(BOT_AI_EVERY * this.T.FIXED_DT,
                              { rivals, since: this.since, phase: this.phase });
    }
  }

  /**
   * Advance every bot by `dt` real seconds and report where they are.
   *
   * Returns one row per bot in the same order as `_snapshot`'s fields, plus the
   * events the room has to act on - a checkpoint split, a finish - because those
   * are decisions only the server can take and it has no other way to hear about
   * them.
   */
  tick(dt, nowMs, phase, since) {
    // Set here rather than by the caller poking at fields, so the phase a tick
    // runs under and the tick itself can never be a message apart. `since` is
    // seconds from the green light and is what the reaction time is measured
    // against, so it has to arrive every tick rather than once at the lights.
    if (phase != null) this.phase = phase;
    this.since = (since == null ? null : since);
    const contact = (this.phase === 'free' || this.phase === 'racing');
    this.stepper.run(dt, (h) => {
      if (this._k % BOT_AI_EVERY === 0) this._think(nowMs);
      this._k++;
      const others = contact ? this._others : null;
      for (const b of this.bots) {
        // One clock for the whole room, so every bot sees the herd where every
        // human sees it. A bot's lap never reaches the leaderboard, so this does
        // not have to match a recording - only to advance once per step.
        b.car.tick = this._k;
        b.car.step(h, b.input);
        if (others) b.car.resolveCars(others, h);
        // Always called, with `null` included: that is what bleeds a charge away
        // when the car drops out of the hole or the phase changes under it.
        b.car.draft(others, h);
        b.car.catchup(this._gapFor(b), h);
      }
    });

    const out = [];
    for (const b of this.bots) {
      const events = b.run.update(b.car, nowMs);
      for (const e of events) {
        if (e === 'cp') b.events.push(['cp', b.run.nextCp, Math.round(b.run.time)]);
        if (e === 'finish' && b.finished == null) {
          b.finished = Math.round(b.run.time);
          b.events.push(['finish', b.finished, 0]);
        }
      }
      const c = b.car;
      out.push([b.pid, c.pos.x, c.pos.y, c.pos.z,
                c.quat.x, c.quat.y, c.quat.z, c.quat.w,
                c.vel.x, c.vel.y, c.vel.z,
                b.run.bestS, b.run.nextCp, c.flags(),
                c.slipBoost > 0 ? c.slipBoost / this.T.SLIP_BOOST : c.slipCharge]);
    }
    return out;
  }

  /** Whatever has happened since this was last asked, and clear it. */
  drainEvents() {
    const out = [];
    for (const b of this.bots) {
      if (!b.events.length) continue;
      out.push([b.pid, b.events]);
      b.events = [];
    }
    return out;
  }

  /** Start a timed lap for everybody, on the shared clock the room hands out. */
  green(nowMs) {
    for (const b of this.bots) {
      b.car.frozen = false;
      b.run.start(nowMs);
      b.started = true;
      b.finished = null;
    }
  }
}

/** Forward (-Z) through a quaternion, without allocating a Vector3 to do it. */
function quatFwd(x, y, z, w) {
  // The -Z column of the rotation matrix.
  return {
    x: -(2 * (x * z + w * y)),
    y: -(2 * (y * z - w * x)),
    z: -(1 - 2 * (x * x + y * y)),
  };
}

/**
 * Drive one bot round on its own, as fast as it can, with nobody else there.
 *
 * This is what `tools/calibrate_bots.py` measures a level against, and what the
 * tests use to assert every level gets round every track. It is the same world
 * and the same driver as a race - only the clock is different, because here it
 * is free to run as fast as the box can compute it.
 */
function botLap(track, T, line, prof, opts) {
  opts = opts || {};
  const world = new BotWorld(track, T, BUILT[track.slug]);
  const b = world.add('solo', line, prof);
  world.phase = 'racing';
  world.since = 999;                       // no reaction time in a time trial
  const dt = 1 / (opts.fps || 60);
  const maxT = opts.maxT || 240;
  let now = 12345, t = 0;
  b.run.start(now);
  b.started = true;
  let respawns = 0;
  // Where the car was when the *game* took it back, which is a different event
  // from the bot giving up (`Bot.recover`) and was being confused with it: on
  // Cloudbreak the bot's own counters were empty and there were still sixty
  // respawns a lap, because the car was falling off the track and `Car` was
  // recovering it. Keep the first few - they are all the same place.
  const fell = [];
  b.car.onRespawned = () => {
    respawns++;
    if (fell.length < 6) {
      // The driver is `b.brain`; `b` is the seat around it (car, run, input).
      const L = b.brain.line;
      const loc = L.near(b.car.pos.x, b.car.pos.y, b.car.pos.z, b.brain.hint);
      fell.push({ i: loc.i, off: +loc.d.toFixed(1),
                  y: +b.car.pos.y.toFixed(1),
                  lineY: +L.p[loc.i][1].toFixed(1),
                  v: +b.car.speed.toFixed(1),
                  want: L.v ? +L.v[loc.i].toFixed(1) : null,
                  air: L.air ? !!L.air[loc.i] : null,
                  why: b.brain.lastGiveUp ? b.brain.lastGiveUp.why : 'game' });
    }
  };
  // `opts.trace` records the run up to the first respawn - which is the only
  // part worth seeing, because everything after it is the same failure again
  // from the same checkpoint. Station, speed, what the line wanted there, and
  // whether the wheels were on anything.
  const trace = [];
  while (t < maxT) {
    now += dt * 1000;
    t += dt;
    world.tick(dt, now);
    if (opts.trace && !respawns && trace.length < 6000) {
      const L = b.brain.line;
      const loc = L.near(b.car.pos.x, b.car.pos.y, b.car.pos.z, b.brain.hint);
      trace.push([loc.i, +b.car.speed.toFixed(1), L.v ? +L.v[loc.i].toFixed(1) : 0,
                  b.car.grounded ? 1 : 0, +b.car.pos.y.toFixed(1),
                  +loc.d.toFixed(1), +L.p[loc.i][1].toFixed(1)]);
    }
    if (b.finished != null) break;
  }
  return {
    finished: b.finished != null,
    time: b.finished || 0,
    respawns,
    splits: b.run.splits,
    progress: world.course.total ? b.run.bestS / world.course.total : 0,
    wall: t,
    // What went wrong, for a lap that did not finish. See `Bot.recover`.
    gaveUp: b.brain.gaveUp,
    lastGiveUp: b.brain.lastGiveUp,
    fell: fell,
    trace: opts.trace ? trace : null,
  };
}
