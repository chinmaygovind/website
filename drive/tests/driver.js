// A driver and a frame loop, for the tests that need a lap that was actually
// driven.
//
// `verify.py` is only worth anything if an honest lap passes it, and there is no
// browser in CI to produce one. So this drives the real `Car` round the real
// track through the real `Run`, in the same order `game.js`'s frame loop does
// it, and hands back exactly what the client would have submitted: the replay,
// the input stream and the anchors.
//
// Two things about it are deliberate and load-bearing.
//
// **It drives on the keyboard.** `readInput` produces -1, 0 or 1 and nothing in
// between, so `runcheck.input_byte` is lossless - and a test driver holding an
// analogue steering angle would be recording an input stream that does not
// describe the lap it drove. The pursuit controller below therefore ends in a
// deadband and a sign, and the car is stepped with the *decoded byte*, never
// with the angle that produced it.
//
// **It is a frame loop, not a step loop.** The whole shape of the recording -
// which step an anchor lands on, what the lap clock reads there, what happens
// when a frame runs long - comes from the fixed-step accumulator being driven by
// a variable frame time. Driving one step per frame would test a client nobody
// has.
//
// The pursuit itself follows `laptime.py`'s racing line, which does double duty:
// the line the medal times are cut from is a line a car has to be able to drive.

function autopilot(car, course, T, rl, opts) {
  opts = opts || {};
  const state = { stuckFor: 0, lastS: 0 };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const pace = opts.pace || 0.88;

  const P = rl.p, V = rl.v, n = P.length;
  const S = [0];
  for (let i = 1; i < n; i++) {
    S.push(S[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1],
                                 P[i][2] - P[i - 1][2]));
  }

  function ahead(i, look) {
    const target = S[Math.min(i, n - 1)] + look;
    let j = Math.min(i, n - 1);
    while (j < n - 1 && S[j] < target) j++;
    return P[j];
  }

  return function drive(dt) {
    const loc = course.locate(car.pos);
    const i = Math.min(loc.idx, n - 1);
    const sample = course.line[i];

    let steer, throttle = 0, brake = 0;

    if (sample.fix && !sample.air) {
      // Inside a corkscrew the road spirals about the direction of travel, so a
      // point up the road swings from side to side in plan view and pure
      // pursuit chases its own tail. Hold it centred and flat, which is what a
      // person does here too.
      steer = clamp(-loc.lateral * 0.16, -0.4, 0.4);
      throttle = 1;
    } else if (sample.air) {
      // Mid-flight: hold the attitude the lip gave us. Aiming in the air is a
      // real skill in this game and a driver that tries and misses would fail a
      // track for the wrong reason.
      steer = clamp(-loc.lateral * 0.05, -0.2, 0.2);
      throttle = 1;
    } else {
      const look = clamp(6.5 + car.speed * 0.26, 6.5, 16);
      const t = ahead(i, look);
      let dx = t[0] - car.pos.x, dz = t[2] - car.pos.z;
      const dl = Math.hypot(dx, dz) || 1;
      dx /= dl; dz /= dl;
      const fx = car.fwd.x, fz = car.fwd.z;
      const fl = Math.hypot(fx, fz) || 1;
      const cross = (fx / fl) * dz - (fz / fl) * dx;   // >0: target is to our right
      const dot = (fx / fl) * dx + (fz / fl) * dz;
      steer = clamp(Math.atan2(cross, dot) * 2.4, -1, 1);

      // The profile already did the braking maths, so holding its speed
      // reproduces its braking points. A little under it, because the profile
      // assumes a perfect line and this has real tracking error to pay for.
      const want = (V[i] || T.MAX_SPEED) * pace;
      if (car.speed < want * 0.99) throttle = 1;
      else if (car.speed > want * 1.05) brake = 1;
      else throttle = 0.35;

      if (loc.dist > 6) { throttle = car.speed > 20 ? 0 : 0.5; brake = 0; }
    }

    // A keyboard has three steering positions. Below the deadband, hands off:
    // without it every hundredth of a radian of tracking error is full lock,
    // and the car saws its way down the straight.
    steer = Math.abs(steer) < 0.12 ? 0 : Math.sign(steer);

    if (Math.abs(loc.s - state.lastS) < 0.25 && car.grounded) state.stuckFor += dt;
    else state.stuckFor = 0;
    state.lastS = loc.s;

    return { throttle: throttle > 0 ? 1 : 0, brake: brake > 0 ? 1 : 0,
             steer: steer, handbrake: false, stuck: state.stuckFor };
  };
}

/**
 * Drive one lap and record it exactly as a browser would.
 *
 * `opts.fps` is the frame rate, `opts.hitchEvery` drops a long frame in every
 * so often (which is how the fixed-step accumulator falls behind the lap clock,
 * and the reason an anchor carries its own time), and `opts.pace` is how hard
 * the driver tries.
 */
function driveLap(slug, opts) {
  opts = opts || {};
  const track = TRACKS.find(t => t.slug === slug);
  const built = buildTrack(track, T);
  const course = new Course(built);
  const run = new Run(course, track);
  const car = new Car(T, built);
  car.placeAt(track.spawn.p, track.spawn.fwd);

  const drive = autopilot(car, course, T, RL[slug], opts);
  const stepper = new Stepper(T);
  const fps = opts.fps || 60;
  const maxT = opts.maxT || 180;
  const hitch = opts.hitchEvery || 0;

  let now = 12345;             // performance.now() is not zero-based either
  let t = 0, frames = 0, started = false, respawns = 0;
  car.onRespawned = () => { respawns++; };

  while (t < maxT) {
    let dt = 1 / fps;
    if (hitch && frames && frames % hitch === 0) dt = 0.1;   // game.js caps dt here
    now += dt * 1000;
    t += dt;
    frames++;

    const inp = drive(dt);
    if (inp.stuck > 4) break;
    // Drive off on purpose, for the tests that need a lap with a fall and a
    // respawn in it - the one moment in a run where the car is put somewhere
    // rather than driven there, and the one thing a re-simulation has to be
    // told about (see `_respawn_points`).
    if (opts.crash && run.state === 'running' &&
        run.time >= opts.crash[0] && run.time < opts.crash[1]) {
      inp.throttle = 1; inp.brake = 0; inp.steer = opts.crash[2] || 1;
    }
    // What the recorder will write down, and therefore what the car must be
    // driven with. Decoding the byte rather than using `inp` is the point.
    const byte = inputByte(inp);
    const use = FIELDS[byte];

    // The clock starts on the first input, the accumulator is dropped, and this
    // one frame's physics is skipped - the three lines of game.js that put the
    // car and the clock on the same zero.
    let clockStarting = false;
    if (!started && (use.throttle || use.brake || use.steer)) {
      started = true;
      stepper.reset();
      run.start(now);
      clockStarting = true;
    }
    if (!clockStarting) {
      stepper.run(dt, (h) => {
        run.noteStep(car, use, now);
        car.step(h, use);
      });
    }
    run.update(car, now);
    if (run.state === 'done') break;
  }

  return {
    finished: run.state === 'done',
    time: run.time,
    splits: run.splits,
    ghost: run.ghost,
    verify: run.verifyPayload(),
    frames: frames,
    respawns: respawns,
    cps: run.nextCp,
    needCps: run.cps.length,
    progress: course.total ? run.bestS / course.total : 0,
  };
}
