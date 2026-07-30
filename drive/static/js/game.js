// Main loop, input, HUD, and the netcode that makes other cars real.
//
// Layout of the frame: accumulate real time, step the car at a fixed 120Hz,
// resolve car-to-car contact, then render once with whatever time is left over
// interpolated. Fixed-step physics is not optional here - variable-dt arcade
// handling changes how the car feels depending on frame rate, which would make
// every time on the leaderboard depend on the machine that set it.
//
// Multiplayer is client-authoritative: your browser decides where your car is
// and says so twenty times a second, and the server fans out the merged
// snapshot. Nobody's position is ever corrected by anyone else, which is what
// keeps contact smooth (see Car.resolveCars for the bumping rules).

import * as THREE from './vendor/three.module.js';
import { buildTrack } from './trackmesh.js';
import { Car, Stepper } from './physics.js';
import { Course, Run, Ghost, GHOST_RATE } from './course.js';
import { Renderer, CarView } from './render.js';
import { Sound } from './sound.js';

const T = window.DRIVE_TUNING;
const CFG = window.DRIVE_CFG;

const $ = (id) => document.getElementById(id);
const fmt = (ms) => {
  if (ms == null) return '--:--.---';
  const neg = ms < 0;
  ms = Math.abs(Math.round(ms));
  const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000);
  return (neg ? '-' : '') + m + ':' + String(s).padStart(2, '0') + '.' +
         String(ms % 1000).padStart(3, '0');
};
const fmtDelta = (ms) => (ms >= 0 ? '+' : '') + (ms / 1000).toFixed(3);

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const S = {
  track: window.DRIVE_TRACK,
  built: null, course: null, run: null, car: null,
  renderer: null, sound: new Sound(), stepper: new Stepper(T),
  view: null, ghostView: null, ghost: null, ghostTimes: null,
  showGhost: true,
  remotes: new Map(),
  paused: false, menuOpen: false,
  started: false,          // has the local run clock been started
  raceMode: false,         // are we in a synced race right now
  racePhase: 'free',
  raceT0: null,            // local perf-clock ms of the green light
  standings: [],
  lastPose: 0,
  socket: null,
  clockOffset: 0, bestRtt: Infinity,
  finishedPayload: null,
  hudTick: 0,
  bestTime: CFG.pbMs || null,
  touch: false,
};

const input = { throttle: 0, brake: 0, steer: 0, handbrake: false };
const keys = new Set();

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
function boot() {
  S.renderer = new Renderer($('gl'));
  loadTrack(S.track);
  bindInput();
  if (CFG.mode === 'room') connect();
  requestAnimationFrame(frame);
}

function loadTrack(track) {
  S.track = track;
  if (S.view) S.view.dispose();
  if (S.ghostView) { S.ghostView.dispose(); S.ghostView = null; }
  for (const r of S.remotes.values()) r.view.dispose();
  S.remotes.clear();

  S.built = buildTrack(track, T);
  S.renderer.setTrack(S.built);
  S.course = new Course(S.built);
  S.run = new Run(S.course, track);
  S.car = new Car(T, S.built);
  S.car.id = CFG.me ? CFG.me.pid : 'me';
  S.view = new CarView(S.renderer.scene, CFG.me ? CFG.me.color : '#e8453c');
  wireCarEvents();
  resetToStart();

  $('trackName').textContent = track.name;
  $('trackBlurb').textContent = track.blurb;
  S.bestTime = (CFG.pbs && CFG.pbs[track.slug]) || null;
  renderMedalTable();
  drawMinimapBase();
  loadGhost('me');
  markActiveTrack();
}

function wireCarEvents() {
  const car = S.car;
  car.onBump = (mag) => {
    S.sound.bump(mag);
    S.renderer.kick(Math.min(1.4, mag / 18));
    if (car.lastBump) {
      S.renderer.smoke(new THREE.Vector3(car.lastBump.x, car.lastBump.y, car.lastBump.z),
                       new THREE.Vector3(0, 1, 0), 'spark');
    }
  };
  car.onWall = (mag, pos) => {
    S.sound.wall(mag);
    S.renderer.kick(Math.min(1.0, mag / 26));
    S.renderer.smoke(pos.clone(), new THREE.Vector3(0, 2, 0), 'spark');
  };
  car.onLand = (airTime) => {
    S.sound.land(airTime);
    if (airTime > 0.5) S.renderer.kick(Math.min(0.8, airTime * 0.5));
  };
  car.onFall = () => { S.sound.fall(); toast('Off the track'); };
  car.onRespawned = () => S.sound.respawn();
}

function resetToStart() {
  const sp = S.track.spawn;
  S.car.placeAt(sp.p, sp.fwd);
  S.run.reset();
  S.started = false;
  S.finishedPayload = null;
  hideResults();
  if (S.ghost) S.ghost.t = 0;
  $('startHint').style.display = '';
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------
const KEYMAP = {
  ArrowUp: 'up', KeyW: 'up',
  ArrowDown: 'down', KeyS: 'down',
  ArrowLeft: 'left', KeyA: 'left',
  ArrowRight: 'right', KeyD: 'right',
  Space: 'drift', ShiftLeft: 'drift',
};

function bindInput() {
  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    S.sound.start(); S.sound.resume();
    const k = KEYMAP[e.code];
    if (k) { keys.add(k); e.preventDefault(); }
    if (e.code === 'KeyR') { resetToStart(); toast('Restart'); }
    if (e.code === 'Enter' || e.code === 'Backspace') { e.preventDefault(); S.car.requestRespawn(); }
    if (e.code === 'Escape') toggleMenu();
    if (e.code === 'KeyM') { const m = !S.sound.enabled; S.sound.mute(m); toast(m ? 'Sound off' : 'Sound on'); }
    if (e.code === 'KeyG') { S.showGhost = !S.showGhost; toast(S.showGhost ? 'Ghost on' : 'Ghost off'); }
  });
  window.addEventListener('keyup', (e) => {
    const k = KEYMAP[e.code];
    if (k) keys.delete(k);
  });
  window.addEventListener('blur', () => keys.clear());

  // touch: hold-to-act buttons, and a drag anywhere on the left half to steer
  const tb = (id, on, off) => {
    const el = $(id);
    if (!el) return;
    const down = (e) => { e.preventDefault(); S.sound.start(); on(); el.classList.add('down'); };
    const up = (e) => { e.preventDefault(); off(); el.classList.remove('down'); };
    el.addEventListener('touchstart', down, { passive: false });
    el.addEventListener('touchend', up, { passive: false });
    el.addEventListener('touchcancel', up, { passive: false });
    el.addEventListener('mousedown', down);
    el.addEventListener('mouseup', up);
    el.addEventListener('mouseleave', up);
  };
  tb('tGas', () => keys.add('up'), () => keys.delete('up'));
  tb('tBrake', () => keys.add('down'), () => keys.delete('down'));
  tb('tLeft', () => keys.add('left'), () => keys.delete('left'));
  tb('tRight', () => keys.add('right'), () => keys.delete('right'));
  tb('tDrift', () => keys.add('drift'), () => keys.delete('drift'));
  if ('ontouchstart' in window) {
    S.touch = true;
    document.body.classList.add('touch');
  }

  $('btnResume').onclick = () => toggleMenu(false);
  $('btnRestart').onclick = () => { resetToStart(); toggleMenu(false); };
  $('btnMenu').onclick = () => toggleMenu();
  $('btnRetry').onclick = () => resetToStart();
  $('btnNextTrack').onclick = () => {
    // In a room the host owns the track, so this only moves you on when solo.
    if (CFG.mode === 'room') { toast('The host picks the track in a room'); return; }
    if (CFG.nextTrack) location.href = '/solo/' + CFG.nextTrack;
  };
  const gt = $('btnGhost');
  if (gt) gt.onclick = () => { S.showGhost = !S.showGhost; gt.classList.toggle('off', !S.showGhost); };
}

function readInput() {
  input.throttle = keys.has('up') ? 1 : 0;
  input.brake = keys.has('down') ? 1 : 0;
  input.steer = (keys.has('right') ? 1 : 0) - (keys.has('left') ? 1 : 0);
  input.handbrake = keys.has('drift');
  return input;
}

// ---------------------------------------------------------------------------
// Frame
// ---------------------------------------------------------------------------
let lastFrame = performance.now();

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (now - lastFrame) / 1000);
  lastFrame = now;

  const inp = readInput();

  // In solo, the clock starts the moment you ask the car to move. In a race it
  // starts on the green light, which the server picks for everyone.
  if (!S.started && !S.raceMode && (inp.throttle || inp.brake || inp.steer)) {
    S.started = true;
    S.run.start(now);
    $('startHint').style.display = 'none';
  }
  if (S.raceMode && S.racePhase === 'racing' && !S.started && S.raceT0 != null && now >= S.raceT0) {
    S.started = true;
    S.car.frozen = false;
    S.run.start(S.raceT0);
    $('startHint').style.display = 'none';
  }

  if (!S.paused) {
    S.stepper.run(dt, (h) => {
      S.car.step(h, inp);
      S.car.resolveCars(collidables(), h);
    });
  }

  updateRemotes(dt);

  // run bookkeeping
  const events = S.run.update(S.car, now, dt);
  for (const e of events) {
    if (e === 'cp') { S.sound.checkpoint(); toast('Checkpoint ' + S.run.nextCp + '/' + S.run.cps.length + '  ' + fmt(S.run.time)); }
    if (e === 'missed') { S.sound.missed(); toast('Missed a checkpoint!'); }
    if (e === 'finish') onFinish();
  }

  drive();
  render(dt, now);
  if ((S.hudTick = (S.hudTick + 1) % 3) === 0) hud(now);
  sendPose(now);
}

function drive() {
  const car = S.car;
  // tyre smoke while sliding, dust when off the road
  if (car.grounded && (car.slip > 0.3 || (car.offroad && car.speed > 8))) {
    const back = new THREE.Vector3().copy(car.pos)
      .addScaledVector(car.fwd, -1.3).addScaledVector(car.up, -0.3);
    const jitter = new THREE.Vector3((Math.random() - 0.5) * 2, 0.9, (Math.random() - 0.5) * 2);
    S.renderer.smoke(back, jitter, car.offroad ? 'dust' : 'smoke');
  }
  if (car.boost > 0 && Math.random() < 0.5) S.renderer.kick(0.05);
}

function render(dt, now) {
  const car = S.car;
  S.renderer.follow(car, dt);
  S.view.update(car.pos, car.quat, {
    lean: car.bumpLean + (-car.steer * Math.min(1, car.speed / T.MAX_SPEED) * 0.06),
    steer: car.steer,
    spin: car.wheelSpin,
    groundY: car.groundY,
    groundN: car.grounded ? car.groundN : null,
    boost: car.boost,
  });
  S.view.setVisible(car.respawnIn <= 0);

  // own-best ghost
  if (S.ghost && S.showGhost && S.started) {
    if (!S.ghostView) S.ghostView = new CarView(S.renderer.scene, '#9aa7b8', { ghost: true });
    const t = (S.run.state === 'running' ? S.run.time : 0) / 1000;
    const f = S.ghost.at(t);
    if (f) {
      S.ghostView.group.visible = true;
      const q = new THREE.Quaternion(f[3], f[4], f[5], f[6]).normalize();
      S.ghostView.update(new THREE.Vector3(f[0], f[1], f[2]), q, {});
      S.ghostView.shadow.visible = false;
    } else if (S.ghostView) {
      S.ghostView.group.visible = false;
      S.ghostView.shadow.visible = false;
    }
  } else if (S.ghostView) {
    S.ghostView.group.visible = false;
    S.ghostView.shadow.visible = false;
  }

  S.renderer.render(dt);
  void now;
}

// ---------------------------------------------------------------------------
// HUD
// ---------------------------------------------------------------------------
function hud(now) {
  const car = S.car, run = S.run;
  const kph = Math.round(car.speed * 3.1);
  $('speed').textContent = kph;
  $('speedFill').style.width = Math.min(100, (car.speed / T.MAX_SPEED) * 100) + '%';
  $('speedFill').classList.toggle('boosting', car.boost > 0);

  $('time').textContent = fmt(run.state === 'ready' ? 0 : run.time);
  $('cpCount').textContent = run.nextCp + '/' + run.cps.length;
  $('wrongWay').style.display = run.wrongWay ? '' : 'none';

  // live delta against your own best run
  const d = $('delta');
  if (S.ghostTimes && run.state === 'running') {
    const gt = ghostTimeAt(run.s);
    if (gt != null) {
      const diff = run.time - gt;
      d.textContent = fmtDelta(diff);
      d.className = 'delta ' + (diff <= 0 ? 'ahead' : 'behind');
      d.style.display = '';
    }
  } else { d.style.display = 'none'; }

  // race positions
  if (S.raceMode || S.remotes.size) {
    const order = liveOrder();
    const me = order.findIndex(e => e.self) + 1;
    $('position').style.display = '';
    $('posNum').textContent = me || '-';
    $('posTot').textContent = order.length;
    renderStandings(order);
  } else {
    $('position').style.display = 'none';
    $('standings').innerHTML = '';
  }
  drawMinimap();
  void now;
}

function ghostTimeAt(s) {
  const arr = S.ghostTimes;
  if (!arr || !arr.length) return null;
  // arr[i] = {s, ms}; find the last sample at or before this distance
  let lo = 0, hi = arr.length - 1;
  if (s <= arr[0].s) return arr[0].ms;
  if (s >= arr[hi].s) return arr[hi].ms;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (arr[mid].s <= s) lo = mid; else hi = mid;
  }
  const a = arr[lo], b = arr[hi];
  const u = (s - a.s) / Math.max(1e-6, b.s - a.s);
  return a.ms + (b.ms - a.ms) * u;
}

function liveOrder() {
  const out = [{ name: CFG.name, color: CFG.me ? CFG.me.color : '#e8453c',
                 s: S.run.bestS, self: true, ms: S.run.state === 'done' ? S.run.time : null }];
  for (const [pid, r] of S.remotes) {
    out.push({ name: r.name, color: r.color, s: r.prog, self: false, pid,
               ms: (S.standings.find(x => x.pid === pid) || {}).ms || null });
  }
  out.sort((a, b) => {
    if (a.ms != null && b.ms != null) return a.ms - b.ms;
    if (a.ms != null) return -1;
    if (b.ms != null) return 1;
    return b.s - a.s;
  });
  return out;
}

function renderStandings(order) {
  const el = $('standings');
  el.innerHTML = order.map((e, i) => `
    <div class="st-row${e.self ? ' me' : ''}">
      <span class="st-pos">${i + 1}</span>
      <span class="st-dot" style="background:${esc(e.color)}"></span>
      <span class="st-name">${esc(e.name)}</span>
      <span class="st-gap">${e.ms != null ? fmt(e.ms) : gapLabel(order[0], e)}</span>
    </div>`).join('');
}

function gapLabel(leader, e) {
  if (e.self && leader.self) return '';
  const gap = (leader.s - e.s);
  if (gap <= 0.5) return '';
  return '-' + Math.round(gap) + 'm';
}

function renderMedalTable() {
  const m = S.track.medals;
  const rows = [['author', 'Author'], ['gold', 'Gold'], ['silver', 'Silver'], ['bronze', 'Bronze']];
  $('medals').innerHTML = rows.map(([k, label]) =>
    `<div class="mrow"><span class="medal ${k}"></span><span>${label}</span>` +
    `<b>${fmt(m[k] * 1000)}</b></div>`).join('') +
    (S.bestTime ? `<div class="mrow pb"><span>Your best</span><b>${fmt(S.bestTime)}</b></div>` : '');
}

function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), 1600);
}

const esc = (s) => (s + '').replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ---------------------------------------------------------------------------
// Minimap
// ---------------------------------------------------------------------------
let mmFit = null;
function drawMinimapBase() {
  const cv = $('minimap');
  const pts = S.built.line.map(e => e.p);
  let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
  for (const p of pts) {
    x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]);
    z0 = Math.min(z0, p[2]); z1 = Math.max(z1, p[2]);
  }
  const pad = 10;
  const w = cv.width, h = cv.height;
  const sc = Math.min((w - pad * 2) / Math.max(1, x1 - x0), (h - pad * 2) / Math.max(1, z1 - z0));
  mmFit = { x0, z0, sc, ox: (w - (x1 - x0) * sc) / 2, oy: (h - (z1 - z0) * sc) / 2 };
}
function mm(p) {
  return [mmFit.ox + (p[0] - mmFit.x0) * mmFit.sc, mmFit.oy + (p[2] - mmFit.z0) * mmFit.sc];
}
function drawMinimap() {
  const cv = $('minimap');
  if (!mmFit) return;
  const g = cv.getContext('2d');
  g.clearRect(0, 0, cv.width, cv.height);
  g.lineWidth = 5;
  g.strokeStyle = 'rgba(255,255,255,.34)';
  g.lineJoin = 'round';
  g.beginPath();
  S.built.line.forEach((e, i) => {
    const [x, y] = mm(e.p);
    i ? g.lineTo(x, y) : g.moveTo(x, y);
  });
  g.stroke();
  // checkpoints
  g.fillStyle = 'rgba(255,255,255,.55)';
  for (const gate of S.course.checkpoints()) {
    const [x, y] = mm(gate.p);
    g.fillRect(x - 2, y - 2, 4, 4);
  }
  const dot = (p, color, r) => {
    const [x, y] = mm(p);
    g.beginPath(); g.arc(x, y, r, 0, 7); g.fillStyle = color; g.fill();
  };
  for (const r of S.remotes.values()) dot([r.pos.x, 0, r.pos.z], r.color, 3);
  dot([S.car.pos.x, 0, S.car.pos.z], CFG.me ? CFG.me.color : '#fff', 4.2);
}

// ---------------------------------------------------------------------------
// Ghosts
// ---------------------------------------------------------------------------
async function loadGhost(who) {
  S.ghost = null; S.ghostTimes = null;
  try {
    const r = await fetch('/api/ghost/' + S.track.slug + '?who=' + who);
    const d = await r.json();
    if (!d.ghost) return;
    S.ghost = new Ghost(d.ghost, d.hz || GHOST_RATE);
    // Precompute distance-along-track per ghost frame so the live delta can be
    // "how long did the ghost take to get this far", not "where is it now".
    S.ghostTimes = [];
    const tmp = new THREE.Vector3();
    const course = new Course(S.built);
    for (let i = 0; i < S.ghost.frames.length; i++) {
      const f = S.ghost.frames[i];
      tmp.set(f[0], f[1], f[2]);
      const loc = course.locate(tmp);
      S.ghostTimes.push({ s: loc.s, ms: (i / S.ghost.hz) * 1000 });
    }
    // enforce monotonic s so the binary search is valid
    for (let i = 1; i < S.ghostTimes.length; i++) {
      if (S.ghostTimes[i].s < S.ghostTimes[i - 1].s) S.ghostTimes[i].s = S.ghostTimes[i - 1].s;
    }
  } catch (e) { /* no ghost is fine */ }
}

// ---------------------------------------------------------------------------
// Finishing
// ---------------------------------------------------------------------------
async function onFinish() {
  const run = S.run;
  const medal = medalFor(run.time);
  S.sound.finish(medal);
  S.car.frozen = false;
  const prev = S.bestTime;
  const improved = prev == null || run.time < prev;

  if (S.raceMode && S.socket) S.socket.emit('finish', { ms: run.time });

  showResults({ time: run.time, medal, prev, improved, pending: true });

  try {
    const r = await fetch('/api/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track: S.track.slug, time_ms: run.time,
                             splits: run.splits, ghost: run.ghost,
                             distance: Math.round(run.distance) }),
    });
    const d = await r.json();
    if (d.ok && d.stored) {
      if (d.is_record) S.sound.record();
      S.bestTime = d.pb_ms;
      if (CFG.pbs) CFG.pbs[S.track.slug] = d.pb_ms;
      showResults({ time: run.time, medal: d.medal, prev, improved: d.improved,
                    rank: d.rank, record: d.record_ms, isRecord: d.is_record });
      if (d.improved) loadGhost('me');
    } else {
      showResults({ time: run.time, medal, prev, improved,
                    note: d.note || d.error || null, guest: d.guest });
      if (improved) { S.bestTime = run.time; localBest(run.time); }
    }
  } catch (e) {
    showResults({ time: run.time, medal, prev, improved, note: 'Offline - time not saved.' });
  }
  renderMedalTable();
}

function medalFor(ms) {
  const m = S.track.medals, s = ms / 1000;
  if (s <= m.author) return 'author';
  if (s <= m.gold) return 'gold';
  if (s <= m.silver) return 'silver';
  if (s <= m.bronze) return 'bronze';
  return null;
}

function localBest(ms) {
  try {
    const k = 'drive.pb.' + S.track.slug;
    const cur = parseInt(localStorage.getItem(k) || '0', 10);
    if (!cur || ms < cur) localStorage.setItem(k, String(ms));
  } catch (e) { /* private mode */ }
}

function showResults(r) {
  $('results').style.display = '';
  $('resTime').textContent = fmt(r.time);
  const med = $('resMedal');
  med.className = 'medal-big ' + (r.medal || 'none');
  med.textContent = r.medal ? r.medal.toUpperCase() : 'FINISHED';
  const bits = [];
  if (r.prev != null) {
    const diff = r.time - r.prev;
    bits.push(r.improved ? `New personal best, ${fmtDelta(diff)}s`
                         : `Personal best ${fmt(r.prev)} (${fmtDelta(diff)}s)`);
  } else if (r.improved) bits.push('First time on this track!');
  if (r.isRecord) bits.push('That is the fastest time on this track.');
  else if (r.record != null) bits.push('Record ' + fmt(r.record));
  if (r.rank) bits.push('Ranked #' + r.rank);
  if (r.note) bits.push(r.note);
  $('resNote').innerHTML = bits.map(b => `<div>${esc(b)}</div>`).join('');
  $('resPending').style.display = r.pending ? '' : 'none';
}

function hideResults() { $('results').style.display = 'none'; }

function toggleMenu(force) {
  S.menuOpen = force != null ? force : !S.menuOpen;
  $('menu').style.display = S.menuOpen ? '' : 'none';
  // Pausing only makes sense alone; in a room the world keeps turning.
  S.paused = S.menuOpen && CFG.mode === 'solo';
}

function markActiveTrack() {
  document.querySelectorAll('[data-track]').forEach(el => {
    el.classList.toggle('active', el.dataset.track === S.track.slug);
  });
}

// ---------------------------------------------------------------------------
// Netcode
// ---------------------------------------------------------------------------
const POSE_HZ = 20;

function serverNow() { return Date.now() + S.clockOffset; }

function connect() {
  const socket = S.socket = window.io();
  socket.on('connect', () => {
    socket.emit('join_room_', { code: CFG.room });
    for (let i = 0; i < 5; i++) setTimeout(() => socket.emit('clock', { c: Date.now() }), 200 * i);
  });
  socket.on('clock', (d) => {
    const now = Date.now(), rtt = now - d.c;
    // Keep the sample with the shortest round trip: it has the least ambiguity
    // about where in the trip the server timestamp was taken.
    if (rtt < S.bestRtt) { S.bestRtt = rtt; S.clockOffset = d.s + rtt / 2 - now; }
  });
  socket.on('room_hello', (d) => {
    renderRoster(d.players);
    S.racePhase = d.race ? d.race.phase : 'free';
    (d.chat || []).forEach(addChat);
  });
  socket.on('roster', (d) => {
    renderRoster(d.players);
    if (d.track && d.track !== S.track.slug) switchTrack(d.track);
  });
  socket.on('poses', onPoses);
  socket.on('track_change', (d) => switchTrack(d.track));
  socket.on('race_start', onRaceStart);
  socket.on('race_green', onRaceGreen);
  socket.on('race_progress', (d) => { S.standings = d.finish || []; });
  socket.on('race_result', onRaceResult);
  socket.on('race_reset', () => {
    S.raceMode = false; S.racePhase = 'free'; S.raceT0 = null;
    S.standings = [];
    $('countdown').style.display = 'none';
    $('raceResult').style.display = 'none';
  });
  socket.on('chat', addChat);
  socket.on('kicked', (d) => { if (CFG.me && d.pid === CFG.me.pid) location.href = '/lobbies'; });
  socket.on('room_closed', () => { location.href = '/lobbies'; });
  socket.on('room_error', (d) => toast(d.error || 'Error'));

  $('btnStartRace').onclick = () => socket.emit('start_race', { code: CFG.room });
  $('btnLeave').onclick = () => { socket.emit('leave'); location.href = '/lobbies'; };
  $('chatForm').onsubmit = (e) => {
    e.preventDefault();
    const inp = $('chatInput');
    if (inp.value.trim()) socket.emit('chat', { text: inp.value.trim() });
    inp.value = '';
  };
  document.querySelectorAll('[data-track]').forEach(el => {
    el.onclick = () => socket.emit('set_track', { code: CFG.room, track: el.dataset.track });
  });
}

function sendPose(now) {
  if (!S.socket || now - S.lastPose < 1000 / POSE_HZ) return;
  S.lastPose = now;
  const c = S.car;
  S.socket.emit('pose', {
    p: [c.pos.x, c.pos.y, c.pos.z],
    q: [c.quat.x, c.quat.y, c.quat.z, c.quat.w],
    v: [c.vel.x, c.vel.y, c.vel.z],
    prog: S.run.bestS, cp: S.run.nextCp, flags: c.flags(),
  });
}

function onPoses(snap) {
  for (const pid in snap.cars) {
    if (CFG.me && pid === CFG.me.pid) continue;
    const a = snap.cars[pid];
    let r = S.remotes.get(pid);
    if (!r) r = addRemote(pid);
    r.packetT = snap.t;
    r.px = a[0]; r.py = a[1]; r.pz = a[2];
    r.q.set(a[3], a[4], a[5], a[6]);
    r.vel.set(a[7], a[8], a[9]);
    r.prog = a[10]; r.cp = a[11]; r.flags = a[12];
    r.lastSeen = performance.now();
  }
  // drop anyone who stopped reporting
  for (const [pid, r] of S.remotes) {
    if (!(pid in snap.cars) && performance.now() - r.lastSeen > 3000) {
      r.view.dispose();
      S.remotes.delete(pid);
    }
  }
}

function addRemote(pid) {
  const meta = (S.roster || []).find(p => p.pid === pid) || {};
  const r = {
    pid, name: meta.name || 'Driver', color: meta.color || '#8899aa',
    pos: new THREE.Vector3(), vel: new THREE.Vector3(), fwd: new THREE.Vector3(0, 0, -1),
    q: new THREE.Quaternion(), rq: new THREE.Quaternion(),
    px: 0, py: 0, pz: 0, prog: 0, cp: 0, flags: 0,
    packetT: 0, lastSeen: performance.now(), primed: false,
    view: new CarView(S.renderer.scene, meta.color || '#8899aa'),
    mass: 1, id: pid,
  };
  r.view.setLabel(r.name, r.color);
  S.remotes.set(pid, r);
  return r;
}

/**
 * Bring remote cars up to "now" and smooth them.
 *
 * Packets arrive 20 times a second with a position and a velocity. Rendering the
 * raw positions would stutter, and rendering them delayed would mean bumping a
 * car where it *was*. So: extrapolate the last packet forward to the current
 * server time with its velocity, then chase that target exponentially. The car
 * you see and the car you hit are the same car, and the motion stays smooth
 * between packets - which is what keeps the contact spring quiet.
 */
function updateRemotes(dt) {
  const nowS = serverNow();
  for (const r of S.remotes.values()) {
    const ahead = Math.min(0.35, Math.max(0, (nowS - r.packetT) / 1000));
    const tx = r.px + r.vel.x * ahead;
    const ty = r.py + r.vel.y * ahead;
    const tz = r.pz + r.vel.z * ahead;
    if (!r.primed) { r.pos.set(tx, ty, tz); r.rq.copy(r.q); r.primed = true; }
    const k = 1 - Math.exp(-16 * dt);
    r.pos.x += (tx - r.pos.x) * k;
    r.pos.y += (ty - r.pos.y) * k;
    r.pos.z += (tz - r.pos.z) * k;
    r.rq.slerp(r.q, 1 - Math.exp(-18 * dt));
    r.fwd.set(0, 0, -1).applyQuaternion(r.rq);
    r.view.update(r.pos, r.rq, { boost: (r.flags & 1) ? 0.5 : 0, spin: 0 });
    r.view.group.visible = !(r.flags & 8);
  }
}

function collidables() {
  const out = [];
  for (const r of S.remotes.values()) {
    if (r.flags & 8) continue;         // respawning: not on the track
    out.push(r);
  }
  return out;
}

function renderRoster(players) {
  S.roster = players;
  const isHost = CFG.me && players.some(p => p.pid === CFG.me.pid && p.is_host);
  $('btnStartRace').style.display = isHost ? '' : 'none';
  $('hostOnly').style.display = isHost ? '' : 'none';
  $('roster').innerHTML = players.map(p => `
    <div class="pl${CFG.me && p.pid === CFG.me.pid ? ' me' : ''}">
      <span class="st-dot" style="background:${esc(p.color)}"></span>
      <span class="pl-name">${esc(p.name)}</span>
      ${p.is_host ? '<span class="tag">HOST</span>' : ''}
      ${p.guest ? '<span class="tag guest">GUEST</span>' : ''}
      ${p.elo != null ? `<span class="pl-elo">${p.elo}</span>` : ''}
      ${isHost && !p.is_host ? `<button class="kick" data-kick="${esc(p.pid)}">&times;</button>` : ''}
    </div>`).join('');
  $('roster').querySelectorAll('[data-kick]').forEach(b => {
    b.onclick = () => S.socket.emit('kick', { code: CFG.room, pid: b.dataset.kick });
  });
  for (const [pid, r] of S.remotes) {
    const meta = players.find(p => p.pid === pid);
    if (meta && meta.name !== r.name) { r.name = meta.name; r.view.setLabel(meta.name, meta.color); }
  }
}

async function switchTrack(slug) {
  try {
    const r = await fetch('/api/track/' + slug);
    const t = await r.json();
    if (!t || t.error) return;
    S.raceMode = false; S.racePhase = 'free'; S.raceT0 = null;
    loadTrack(t);
    toast('Track: ' + t.name);
  } catch (e) { toast('Could not load that track'); }
}

function onRaceStart(d) {
  S.raceMode = true;
  S.racePhase = 'countdown';
  S.standings = [];
  $('raceResult').style.display = 'none';
  // Put everyone on a grid behind the start line, two by two.
  const slot = (d.grid && CFG.me) ? (d.grid[CFG.me.pid] || 0) : 0;
  const g = S.course.startGate();
  if (g) {
    const back = 4 + Math.floor(slot / 2) * 5.5;
    const lat = (slot % 2 ? 1 : -1) * 2.1;
    S.car.placeAt([g.p[0] - g.f[0] * back + g.r[0] * lat,
                   g.p[1] + 0.3,
                   g.p[2] - g.f[2] * back + g.r[2] * lat], g.f);
  }
  S.run.reset();
  S.started = false;
  S.car.frozen = true;
  hideResults();
  // Convert the server's green-light time onto our own clock.
  S.raceT0 = performance.now() + (d.t0 - serverNow());
  countdownLoop();
}

function countdownLoop() {
  const el = $('countdown');
  el.style.display = '';
  let lastShown = null;
  const tick = () => {
    if (S.racePhase !== 'countdown' && S.racePhase !== 'racing') { el.style.display = 'none'; return; }
    const left = (S.raceT0 - performance.now()) / 1000;
    if (left > 0) {
      const n = Math.ceil(left);
      el.textContent = n;
      el.className = 'countdown n' + n;
      if (n !== lastShown) { lastShown = n; S.sound.countdown(n); }
      requestAnimationFrame(tick);
    } else if (left > -1.2) {
      if (lastShown !== 0) { lastShown = 0; S.sound.countdown(0); }
      el.textContent = 'GO!';
      el.className = 'countdown go';
      requestAnimationFrame(tick);
    } else {
      el.style.display = 'none';
    }
  };
  tick();
}

function onRaceGreen(d) {
  S.racePhase = 'racing';
  if (d && d.t0) S.raceT0 = performance.now() + (d.t0 - serverNow());
}

function onRaceResult(d) {
  S.racePhase = 'results';
  S.raceMode = false;
  S.car.frozen = false;
  const el = $('raceResult');
  el.style.display = '';
  const mine = CFG.me ? (d.elo || {})[CFG.me.pid] : null;
  el.innerHTML = '<h3>Race result</h3>' + d.standings.map((e, i) => {
    const delta = (d.elo || {})[e.pid];
    return `<div class="st-row${CFG.me && e.pid === CFG.me.pid ? ' me' : ''}">
      <span class="st-pos">${i + 1}</span>
      <span class="st-dot" style="background:${esc(e.color || '#888')}"></span>
      <span class="st-name">${esc(e.name)}</span>
      <span class="st-gap">${e.ms != null ? fmt(e.ms) : 'DNF'}</span>
      ${delta ? `<span class="st-elo ${delta.delta >= 0 ? 'up' : 'down'}">${delta.delta >= 0 ? '+' : ''}${delta.delta}</span>` : ''}
    </div>`;
  }).join('') + (mine ? `<div class="elo-line">Rating ${mine.before} &rarr; <b>${mine.after}</b></div>` : '');
}

function addChat(m) {
  const log = $('chatLog');
  const d = document.createElement('div');
  d.className = 'cm';
  d.innerHTML = `<b style="color:${esc(m.color || '#fff')}">${esc(m.name)}</b> ${esc(m.text)}`;
  log.appendChild(d);
  while (log.children.length > 60) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}

// ---------------------------------------------------------------------------
boot();
