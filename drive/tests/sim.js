// Headless test harness: build a track, drive it with the autopilot, report what
// happened. Runs the production physics, collider and run logic unchanged.

function simulate(track, T, opts) {
  opts = opts || {};
  const rl = opts.rl || RL[track.slug];
  const built = buildTrack(track, T);
  const course = new Course(built);
  const run = new Run(course, track);
  const car = new Car(T, built);
  car.placeAt(track.spawn.p, track.spawn.fwd);

  let respawns = 0, landings = 0, bumps = 0, wallHits = 0;
  car.onRespawned = () => { respawns++; };
  car.onLand = () => { landings++; };
  car.onWall = () => { wallHits++; };
  car.onBump = () => { bumps++; };

  const drive = autopilot(car, course, T, rl);
  const dt = T.FIXED_DT;
  const maxT = opts.maxT || 180;
  let t = 0, stuck = 0, maxAir = 0, topSpeed = 0, airFrames = 0, frames = 0;
  let sumSpeed = 0;

  run.start(0);
  while (t < maxT) {
    const inp = drive(dt);
    if (inp.stuck > 4) { stuck = 1; break; }
    car.step(dt, inp);
    run.update(car, t * 1000, dt);
    frames++;
    sumSpeed += car.speed;
    if (car.speed > topSpeed) topSpeed = car.speed;
    if (!car.grounded) { airFrames++; if (car.airTime > maxAir) maxAir = car.airTime; }
    if (run.state === 'done') break;
    t += dt;
  }

  return {
    finished: run.state === 'done',
    time: run.time,
    simSeconds: t,
    respawns, landings, bumps, wallHits, stuck,
    cps: run.nextCp,
    needCps: run.cps.length,
    progress: course.total ? run.bestS / course.total : 0,
    topSpeed,
    avgSpeed: frames ? sumSpeed / frames : 0,
    airFraction: frames ? airFrames / frames : 0,
    maxAir,
    triangles: built.collider.k.length,
    gates: built.gates.length,
    ghostFrames: run.ghost.length,
    splits: run.splits,
    killY: built.killY,
  };
}

// Drop the car onto a point and report the surface it finds - used to test that
// the collider agrees with the geometry, including upside down inside a loop.
function probe(track, T, x, y, z, ux, uy, uz, maxDist) {
  const built = buildTrack(track, T);
  const g = built.collider.ground(x, y, z, ux, uy, uz, maxDist || 4);
  return { hit: g.hit, dist: g.dist, kind: g.kind,
           n: [g.nx || 0, g.ny || 0, g.nz || 0] };
}

// Two cars driven into each other, to measure what the bump rules actually do.
function bumpTest(track, T, closingSpeed) {
  const built = buildTrack(track, T);
  const a = new Car(T, built);
  const b = new Car(T, built);
  const sp = track.spawn;
  a.placeAt(sp.p, sp.fwd);
  b.placeAt(sp.p, sp.fwd);
  // Put b alongside a right at the point of contact, closing sideways. Starting
  // deeply interpenetrated would measure the recovery from an impossible state,
  // and starting clear would not touch at all at low closing speeds - grip kills
  // a few u/s of sideways velocity inside a tenth of a second.
  b.pos.copy(a.pos);
  b.pos.addScaledVector(a.right, T.CAR_RADIUS * 2 - 0.05);
  a.vel.copy(a.fwd).multiplyScalar(30);
  b.vel.copy(a.fwd).multiplyScalar(30).addScaledVector(a.right, -closingSpeed);

  const dt = T.FIXED_DT;
  let contacts = 0, maxSep = 0, minSep = 999, jitter = 0, lastSep = null;
  const other = { pos: b.pos, vel: b.vel, fwd: b.fwd, mass: 1, id: 'b' };
  const mine = { pos: a.pos, vel: a.vel, fwd: a.fwd, mass: 1, id: 'a' };
  a.id = 'a'; b.id = 'b';
  let signChanges = 0, prevDelta = 0;
  // Just long enough for the contact to resolve. Running for seconds would
  // mostly measure two cars with no steering driving off the first corner.
  const STEPS = Math.round(0.6 / dt);
  for (let i = 0; i < STEPS; i++) {
    a.step(dt, { throttle: 1 });
    b.step(dt, { throttle: 1 });
    a.resolveCars([other], dt);
    b.resolveCars([mine], dt);
    const dx = a.pos.x - b.pos.x, dy = a.pos.y - b.pos.y, dz = a.pos.z - b.pos.z;
    const sep = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (sep < T.CAR_RADIUS * 2) contacts++;
    if (sep > maxSep) maxSep = sep;
    if (sep < minSep) minSep = sep;
    if (lastSep != null) {
      const delta = sep - lastSep;
      // count how often the cars switch between approaching and separating:
      // a smooth resolution does this once or twice, a jittery one every frame
      if (prevDelta !== 0 && Math.sign(delta) !== Math.sign(prevDelta) && Math.abs(delta) > 1e-4) {
        signChanges++;
      }
      prevDelta = delta;
      jitter = Math.max(jitter, Math.abs(delta) / dt);
    }
    lastSep = sep;
  }
  return { contacts, minSep, maxSep, signChanges, peakSepRate: jitter,
           aSpeed: a.vel.length(), bSpeed: b.vel.length(),
           aUpright: a.up.y, bUpright: b.up.y,
           aY: a.pos.y, bY: b.pos.y };
}
