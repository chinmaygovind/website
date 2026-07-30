// A driver, for tests.
//
// This exists so the test suite can *drive* every track through the real physics
// instead of asserting things about it from the outside. If a corner is too tight
// to get round, a jump too long to clear or a loop too big to complete, this finds
// out by failing to reach the finish - a far better regression test for a driving
// game than any unit test of the maths.
//
// It follows the racing line and speed profile that `laptime.py` computes for the
// medal times, which does double duty: it makes the driver competent (pure pursuit
// on a minimum-curvature line, rather than trying to track a 90-degree tile's
// centreline, which has a 4-unit radius no car could hold), and it checks that the
// line the medal times are derived from is a line a car can actually drive.
//
// It is still deliberately beatable by a human - it drives one fixed line and
// never uses the handbrake - so its times are a sanity check on the medals, not a
// definition of them.

function autopilot(car, course, T, rl) {
  const state = { stuckFor: 0, lastS: 0 };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  // Cumulative distance along the racing line, so lookahead is in metres.
  const P = rl.p, V = rl.v, n = P.length;
  const S = [0];
  for (let i = 1; i < n; i++) {
    S.push(S[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1],
                                 P[i][2] - P[i - 1][2]));
  }

  // Point on the racing line `look` metres past index i.
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
      // point "up the road" swings from side to side and overhead in plan view
      // and pure pursuit chases its own tail. Hold it centred and flat out and
      // let the geometry do the work - which is exactly what a human does here.
      steer = clamp(-loc.lateral * 0.16, -0.4, 0.4);
      throttle = 1;
    } else if (sample.air) {
      // Mid-flight: hold whatever attitude the lip gave us. Aiming in the air is
      // a real skill in this game, but a test driver that tries to and gets it
      // wrong would fail tracks for the wrong reason.
      steer = clamp(-loc.lateral * 0.05, -0.2, 0.2);
      throttle = 1;
    } else {
      // --- pure pursuit along the racing line ---------------------------
      const look = clamp(6.5 + car.speed * 0.26, 6.5, 16);
      const t = ahead(i, look);
      let dx = t[0] - car.pos.x, dz = t[2] - car.pos.z;
      const dl = Math.hypot(dx, dz) || 1;
      dx /= dl; dz /= dl;
      const fx = car.fwd.x, fz = car.fwd.z;
      const fl = Math.hypot(fx, fz) || 1;
      // cross > 0 means the target is off to our right (right = fwd x up)
      const cross = (fx / fl) * dz - (fz / fl) * dx;
      const dot = (fx / fl) * dx + (fz / fl) * dz;
      steer = clamp(Math.atan2(cross, dot) * 2.4, -1, 1);

      // --- match the profile's speed ------------------------------------
      // The profile already did the braking maths, so simply holding its target
      // speed reproduces its braking points.
      // A little under the profile: the profile assumes a perfectly placed line
      // and this driver has real tracking error to pay for.
      const want = (V[i] || T.MAX_SPEED) * 0.88;
      if (car.speed < want * 0.99) throttle = 1;
      else if (car.speed > want * 1.05) brake = 1;
      else throttle = 0.35;

      // recovery: a long way off line, slow down and get back on it
      if (loc.dist > 6) { throttle = car.speed > 20 ? 0 : 0.5; brake = 0; }
    }

    if (Math.abs(loc.s - state.lastS) < 0.25 && car.grounded) state.stuckFor += dt;
    else state.stuckFor = 0;
    state.lastS = loc.s;

    return { throttle, brake, steer, handbrake: false, stuck: state.stuckFor };
  };
}
