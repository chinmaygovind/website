// Main loop, input, HUD, and the netcode that makes other cars real.
//
// Layout of the frame: accumulate real time, step the car at a fixed 120Hz,
// resolve car-to-car contact, then render once with whatever time is left over
// interpolated. Fixed-step physics is not optional here - variable-dt arcade
// handling changes how the car feels depending on frame rate, which would make
// every time on the leaderboard depend on the machine that set it.
//
// Multiplayer is client-authoritative: your browser decides where your car is
// and says so thirty times a second, and the server fans out the merged
// snapshot. Nobody's position is ever corrected by anyone else, which is what
// keeps contact smooth (see Car.resolveCars for the bumping rules).

import * as THREE from './vendor/three.module.js';
import { buildTrack } from './trackmesh.js';
import { Car, Stepper, FLAG } from './physics.js';
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

/** The ghost you picked last time is the ghost you probably still want. */
function storedGhostMode() {
  try {
    const v = localStorage.getItem('drive.ghost');
    return ['off', 'me', 'wr'].includes(v) ? v : 'me';
  } catch (e) { return 'me'; }
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const S = {
  track: window.DRIVE_TRACK,
  built: null, course: null, run: null, car: null,
  renderer: null, sound: new Sound(), stepper: new Stepper(T),
  view: null, ghostView: null, ghost: null, ghostTimes: null,
  // Which lap the ghost is: off | me | wr | run (one picked off the board).
  ghostMode: storedGhostMode(),
  ghostRun: null,          // {id, who, time_ms} while chasing somebody's lap
  showGhost: true,
  board: null,             // the last board fetched, for the detail pane
  mySplits: [],            // your PB's splits, to compare somebody else's with
  watch: null,             // a replay playing instead of a run
  shot: false,             // taking a preview picture, not playing
  previewPhase: null,      // `?panel=qual|racing` pins a phase to look at it
  hintShown: false,
  sessionBest: null,       // rooms only: best practice lap since you arrived
  qualBest: null,          // your best lap of this qualifying session
  qualRef: null,           // and its distance/time table, for split deltas
  raceSplits: {},          // pid -> {checkpoint: ms} for the race being driven
  remotes: new Map(),
  paused: false, menuOpen: false, helpOpen: false,
  isHost: false,
  started: false,          // has the local run clock been started
  raceMode: false,         // are we in a synced race right now
  racePhase: 'free',
  raceT0: null,            // local perf-clock ms of the green light
  raceDone: false,         // finished or retired: out of the race, still in the room
  qualEnd: null,           // local perf-clock ms qualifying closes
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
const keys = new Set();          // keyboard

// Touch is derived from which buttons are held rather than poked into `keys`,
// because it is not a one-button-one-control mapping: there are only four
// driving buttons on a phone and five things to do.
//
// The missing one is the handbrake, and there is nowhere to put it. The right
// thumb is on a pedal for essentially the whole lap, so a fifth button on that
// side cannot be pressed without lifting off; and a button on the left is a
// button the steering thumb has to leave.
//
// So it is a gesture on the arrow you are about to press anyway:
// **double-tap and hold the way you are turning**. Tap-tap-hold left is a
// handbrake turn to the left, for as long as you keep the thumb down.
//
// The steering thumb is the one that can afford it. It arrives at a corner
// having just let go of the last arrow, so the second tap of the gesture is the
// press it was going to make; the pedal thumb, by contrast, is holding
// something all lap, and any gesture there costs a release you did not want to
// make. That the drift ends when you let go of the arrow is the point too - you
// catch a slide by coming off the steering, and that is exactly when a real
// handbrake comes off.
//
// Two earlier attempts are worth not repeating. A DRIFT button beside the
// pedals was literally unpressable. Brake-while-steering was unusable, because
// braking into a corner *is* steering, so it fired on essentially every corner
// and the car spent the lap sideways. This replaced a third, the same
// double-tap on the *brake*, which worked but charged the busy thumb a release
// mid-corner and could not be reached from the throttle at all.
// Deliberately tiny. At 320ms almost any mid-corner correction - come off the
// arrow, put it straight back on - landed inside the window and started a slide
// nobody asked for. A gap this short is not something your thumb does by
// accident while driving; it only happens when you mean it.
const DOUBLE_TAP = 50;           // ms from letting go to the second tap
//
// The second way in is **drag the throttle downwards**, which is the one gesture
// the pedal thumb can afford after all. The objection to putting anything on
// that thumb was never that it is the wrong thumb - it is the one already at the
// controls - but that every candidate charged it a *release*: a tap costs a lift,
// and lifting off mid-corner is the one thing the throttle thumb must never do.
// A drag costs nothing. The thumb stays down, the throttle stays open, and the
// slide comes on under power, which is how a handbrake turn is actually driven.
// Pulling down is the direction a real lever comes up, and there is nothing
// below the pedal to hit by accident.
//
// So there are two, and they are for different hands rather than alternatives:
// the arrow gesture is for a corner you are already turning into, the throttle
// drag for one you want to provoke. Either sets `drift`; both let go the moment
// the thumb does.
const DRAG_DRIFT = 26;           // px down the throttle before the handbrake bites
const DRAG_KEEP = 14;            // px it must come back above to let it off again
const touchDown = new Set();     // ids of touch buttons currently held
const touchKeys = new Set();
const TOUCH_KEYS = {
  tGas: ['up'], tBrake: ['down'], tLeft: ['left'], tRight: ['right'],
};
const drifting = new Set();      // buttons currently asking for the handbrake
function syncTouch() {
  touchKeys.clear();
  for (const id of touchDown) for (const k of TOUCH_KEYS[id] || []) touchKeys.add(k);
  if (drifting.size) touchKeys.add('drift');
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
function boot() {
  S.renderer = new Renderer($('gl'));
  loadTrack(S.track);
  bindInput();
  if (CFG.mode === 'room') connect();
  openRequestedLap();
  openPanelParam();
  requestAnimationFrame(frame);
}

/**
 * `?panel=settings|help|tracks|board|qual|racing` opens a panel on load.
 *
 * There is no browser in CI and a screenshot cannot click, so this is the only
 * way to look at a panel's layout without a person driving the mouse - the same
 * reason `?touch=1` exists.
 *
 * `qual` and `racing` are the odd ones out: neither is a panel you can open,
 * they appear because the room said so, and getting a room into either needs
 * two browsers and a stopwatch. So they pin the phase and fake a session,
 * which is enough to look at - and looking at it is the whole point here.
 * Pinned rather than assigned, because the room reports "free practice" the
 * moment the socket connects and a phase merely set here would be gone before
 * the shutter.
 */
async function openPanelParam() {
  const q = new URLSearchParams(location.search);
  const p = q.get('panel');
  if (p === 'settings') toggleMenu(true);
  else if (p === 'help') toggleHelp(true);
  else if (p === 'tracks') toggleTracks(true);
  else if ((p === 'qual' || p === 'racing') && CFG.mode === 'room') {
    S.previewPhase = p === 'qual' ? 'qualifying' : 'racing';
    S.isHost = true;
    // A session closes the room drawer on the way in, so a preview of one has
    // to as well or it photographs a screen that never happens.
    showSide(false);
    applyPhase();
    if (p === 'qual') renderQual({
      ends: serverNow() + 72000,
      rows: [{ pid: 'a', name: 'Chinmay', color: '#e8453c', ms: 42108 },
             { pid: CFG.me ? CFG.me.pid : 'b', name: 'You', color: '#ffd96b', ms: 44812 },
             { pid: 'c', name: 'Someone else', color: '#55e08a', ms: 45330 },
             { pid: 'd', name: 'Not out yet', color: '#8fd6ff', ms: null }],
    });
  } else if (p === 'board') {
    await openBoard();
    if (q.has('row')) showBoardRow(parseInt(q.get('row'), 10) || 0);
  }
}

/**
 * Arriving from the leaderboard with a lap already chosen.
 *
 * `?ghost=<id>` means race it, `?watch=<id>` means watch it. Both are how the
 * public board hands a lap to the game - it can list times but it cannot play
 * them, so it links here and the game does the rest.
 */
async function openRequestedLap() {
  const q = new URLSearchParams(location.search);
  const race = q.get('ghost'), watch = q.get('watch');
  const id = race || watch;
  if (!id) return;
  // `?ghost=` names a lap by id, but the three standing choices are worth
  // being able to link to as well - "open this track chasing the record" is a
  // sentence, and ids are digits so the two cannot be confused. It is also the
  // only way to look at a ghost setting without a browser to click in.
  if (race && ['off', 'me', 'wr'].includes(race)) { setGhostMode(race); return; }
  const d = await fetchGhost(id).catch(() => null);
  if (!d) { toast('That lap is no longer there'); return; }
  if (watch) { startWatching(d.ghost, d.hz || GHOST_RATE, d); return; }
  useGhost(d.ghost, d.hz || GHOST_RATE);
  S.ghostRun = { id: d.id, who: d.who, time_ms: d.time_ms };
  setGhostMode('run', { quiet: true });
  toast('Chasing ' + d.who + '  ' + fmt(d.time_ms));
}

function loadTrack(track, opts = {}) {
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
  // Everything else on the page that names the track. All of it was rendered by
  // the template for the track you *arrived* on, and the switcher changes the
  // world underneath it - so a leaderboard link left alone quietly sends you to
  // the board for a track you stopped driving several switches ago.
  document.title = track.name + ' | Drive';
  // The help sheet's blurb used to be repointed here too. It is gone: that
  // sheet is the controls table now, and the blurb is already on the track
  // card in the corner, where it does not have to be opened to be read.
  document.querySelectorAll('.board-link').forEach((a) => {
    a.href = '/track/' + track.slug;
  });
  // A guest has no server-side PB, but the one in localStorage is still theirs.
  S.bestTime = (CFG.pbs && CFG.pbs[track.slug]) || storedBest() || null;
  renderMedalTable();
  showPb();
  drawMinimapBase();
  // A new track is a new set of laps, so whoever you were chasing on the last
  // one is gone. Every reference lap belongs to the track it was driven on, so
  // switching throws all of them away rather than reading this track's splits
  // against the last one's.
  S.ghost = null; S.ghostTimes = null; S.sessionBest = null;
  S.qualBest = null; S.qualRef = null; S.raceSplits = {};
  S.ghostRun = null;
  S.mySplits = (CFG.pbSplits && CFG.pbSplits[track.slug]) || [];
  // **Arriving somewhere new means no ghost.** A track you have just switched
  // to is one you are looking at rather than attacking, and a car you have
  // never driven against appearing on your first lap of it is in the way. Not
  // remembered: it is what this track starts as, not a preference you set, so
  // the ghost you actually chose is still there next time you open the game.
  if (opts.switched) setGhostMode('off', { quiet: true, remember: false });
  else {
    if (S.ghostMode === 'run') S.ghostMode = 'me';
    setGhostMode(S.ghostMode, { quiet: true });
  }
  applyPhase();
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
  // The tow pays out on its own, with no button pressed, so it has to announce
  // itself: the bar under the speed bar has been filling, and this is it going.
  car.onSlipstream = () => {
    S.sound.slipstream();
    S.renderer.kick(0.35);
    toast('Slipstream!');
  };
}

function resetToStart() {
  const sp = S.track.spawn;
  S.car.placeAt(sp.p, sp.fwd);
  S.run.reset();
  S.started = false;
  S.finishedPayload = null;
  hideResults();
  if (S.ghost) S.ghost.t = 0;
  showStartHint();
  clearDelta();
}

/**
 * The "press up to go" line, once per session.
 *
 * It tells a new player the one thing they cannot guess. By the second run they
 * have already done it, and it becomes a label floating over the road on every
 * restart for the rest of the evening - so it is shown once and then never
 * again, remembered per tab so a reload does not start the lecture over.
 */
function showStartHint() {
  const el = $('startHint');
  let seen = S.hintShown;
  try { seen = seen || sessionStorage.getItem('drive.hint') === '1'; } catch (e) {}
  el.style.display = seen ? 'none' : '';
}

function markHintSeen() {
  S.hintShown = true;
  try { sessionStorage.setItem('drive.hint', '1'); } catch (e) {}
  $('startHint').style.display = 'none';
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
    // R starts the whole run again; T only puts you back on the road at the last
    // checkpoint and leaves the clock running, which is the difference between
    // "that lap is gone" and "I just fell off".
    if (e.code === 'KeyR') restartRun();
    if (e.code === 'KeyT' || e.code === 'Enter' || e.code === 'Backspace') {
      e.preventDefault(); backToCheckpoint();
    }
    // Escape means "close whatever is in front of me", innermost first - a
    // replay, then a panel opened from another panel, then the panel itself.
    if (e.code === 'Escape') {
      if (S.watch) stopWatching();
      else if ($('boardOv').style.display !== 'none') toggleBoard(false);
      else if ($('tracksOv').style.display !== 'none') toggleTracks(false);
      else toggleMenu();
    }
    if (e.code === 'KeyH') toggleHelp();
    if (e.code === 'KeyP') toggleTracks();
    if (e.code === 'KeyM') setSound(!S.sound.enabled);
    // G steps through the three ghosts there are rather than toggling the last
    // one back on: picking between your own lap and the record is the choice
    // worth having on a key, and it saves opening settings to make it. A lap
    // chased off the board is not in the cycle - it is not a mode you can
    // arrive at by pressing a key, so pressing one leaves it.
    if (e.code === 'KeyG') setGhostMode(nextGhostMode());
  });
  window.addEventListener('keyup', (e) => {
    const k = KEYMAP[e.code];
    if (k) keys.delete(k);
  });
  window.addEventListener('blur', () => {
    keys.clear();
    touchDown.clear(); drifting.clear(); syncTouch();
    document.querySelectorAll('.tbtn').forEach(el =>
      el.classList.remove('down', 'drifting'));
  });

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
  const hold = (id) => tb(id, () => { touchDown.add(id); syncTouch(); },
                              () => { touchDown.delete(id); syncTouch(); });
  for (const id of ['tGas', 'tBrake']) hold(id);
  // The throttle, dragged downwards, is the handbrake too - without ever coming
  // off the throttle, which is the whole reason this thumb can carry a gesture
  // at all (see DRAG_DRIFT). `hold` above keeps the pedal held throughout; this
  // only adds `drift` on top of it.
  //
  // Bound as its own listeners rather than folded into `tb`, because it is the
  // only control that cares *where* the thumb is rather than whether it is
  // down. A touch is delivered to the element it started on for its whole life,
  // so the drag keeps working past the bottom of the button - which it has to,
  // since the pedal is already near the floor of the screen.
  const dragDrift = (id) => {
    const el = $(id);
    if (!el) return;
    let originY = null, tid = null;
    const paint = () => el.classList.toggle('drifting', drifting.has(id));
    const mine = (e) => {
      const list = e.changedTouches || [];
      for (const t of list) if (t.identifier === tid) return t;
      return null;
    };
    el.addEventListener('touchstart', (e) => {
      const t = (e.changedTouches || [])[0];
      if (!t) return;
      tid = t.identifier;
      originY = t.clientY;
    }, { passive: false });
    el.addEventListener('touchmove', (e) => {
      const t = originY == null ? null : mine(e);
      if (!t) return;
      e.preventDefault();
      const dy = t.clientY - originY;
      // Two thresholds, so a thumb resting on the boundary does not chatter the
      // handbrake on and off underneath it.
      if (dy >= DRAG_DRIFT) drifting.add(id);
      else if (dy < DRAG_KEEP) drifting.delete(id);
      syncTouch();
      paint();
    }, { passive: false });
    // Lifting the thumb drops the drift with the throttle, and so does a touch
    // the system takes away - the car must never be left held sideways by a
    // gesture there is no longer a finger for.
    const end = () => {
      originY = null; tid = null;
      drifting.delete(id);
      syncTouch();
      paint();
    };
    el.addEventListener('touchend', end, { passive: false });
    el.addEventListener('touchcancel', end, { passive: false });
  };
  dragDrift('tGas');
  // An arrow is the one button with two meanings, so it is bound by hand: a
  // press is steering, and a press that lands within DOUBLE_TAP of that same
  // arrow's last release is the handbrake as well, for as long as you keep your
  // thumb down.
  //
  // The two arrows share the timer rather than keeping one each, because
  // **anything you touched in between ends the gesture**: left-right-left is a
  // correction, not a double-tap of left, and it is a fast one - exactly the
  // shape that would otherwise fire the handbrake in the middle of a corner
  // you were busy saving. So a press on either arrow voids the other's window,
  // and only left-nothing-left counts.
  const released = { tLeft: -1e9, tRight: -1e9 };
  const steer = (id) => {
    const el = $(id);
    if (!el) return;
    const other = id === 'tLeft' ? 'tRight' : 'tLeft';
    tb(id, () => {
      if (performance.now() - released[id] < DOUBLE_TAP) drifting.add(id);
      released[other] = -1e9;
      touchDown.add(id);
      syncTouch();
      el.classList.toggle('drifting', drifting.has(id));
    }, () => {
      released[id] = performance.now();
      drifting.delete(id);
      touchDown.delete(id);
      syncTouch();
      el.classList.remove('drifting');
    });
  };
  for (const id of ['tLeft', 'tRight']) steer(id);
  // These two fire on press and do nothing on release, so they are taps rather
  // than holds like the pedals are.
  tb('tCheck', () => backToCheckpoint(), () => {});
  tb('tRestart', () => restartRun(), () => {});
  // `?touch=1` forces the touch HUD on a desktop browser, which is the only way
  // to look at the phone layout without a phone.
  // Preview-picture mode: no HUD, no car, no controls - just the track.
  if (location.search.indexOf('shot=1') >= 0) {
    S.shot = true;
    S.car.frozen = true;
    S.view.setVisible(false);
    document.body.classList.add('shot');
  }
  if ('ontouchstart' in window || location.search.indexOf('touch=1') >= 0 ||
      (window.matchMedia && window.matchMedia('(pointer: coarse)').matches)) {
    S.touch = true;
    document.body.classList.add('touch');
  }

  $('btnSettings').onclick = () => toggleMenu();
  $('btnHelp').onclick = () => toggleHelp();
  $('btnHelpClose').onclick = () => toggleHelp(false);
  $('btnResume').onclick = () => toggleMenu(false);
  // Both of these are on the HUD now, so they close nothing and cost no clicks.
  $('btnRestart').onclick = () => restartRun();
  $('btnCheckpoint').onclick = () => backToCheckpoint();
  $('btnRetry').onclick = () => resetToStart();
  $('btnSound').onclick = () => setSound(!S.sound.enabled);
  setSound(S.sound.enabled);

  // Ghost source, track switcher and the in-game board.
  $('ghostOpts').querySelectorAll('[data-ghost]').forEach(b => {
    b.onclick = () => chooseGhost(b.dataset.ghost);
  });
  $('btnTracks').onclick = () => toggleTracks();
  $('btnTracksClose').onclick = () => toggleTracks(false);
  $('btnBoardClose').onclick = () => toggleBoard(false);
  $('btnWatchStop').onclick = () => stopWatching();
  renderTrackCards();          // loadTrack has already set the ghost up
  // Everything room-shaped lives behind the hamburger, at every screen size.
  if ($('side')) {
    $('btnRoom').onclick = () => showSide(!document.body.classList.contains('side-open'));
    $('btnRoomClose').onclick = () => showSide(false);
    showSide(true);           // you arrive in a lobby, so start with it open
  }
}

function showSide(on) {
  document.body.classList.toggle('side-open', on);
  $('btnRoom').classList.toggle('on', on);
}

// ---------------------------------------------------------------------------
// The ghost you are chasing
// ---------------------------------------------------------------------------
//
// Four states rather than a toggle, because "is there a ghost" and "whose lap is
// it" are different questions and only the second one is interesting: off, your
// own, the record, or a lap you picked off the board.
//
// In a room `me` keeps meaning what it has always meant there - your best lap of
// *this* practice session, not a PB from another day against nobody - so the
// same word means "the best I have driven here" in both places. The record and
// somebody else's lap are new, and they are still hidden for the whole of a
// race by ghostOn(), where a translucent extra car is just a fake rival.

const GHOST_LABEL = { off: 'Off', me: 'My best', wr: 'World record', run: 'Chasing' };

// What G steps through. `run` is deliberately not in it - see the key handler.
const GHOST_CYCLE = ['off', 'me', 'wr'];

function nextGhostMode() {
  const i = GHOST_CYCLE.indexOf(S.ghostMode);
  return GHOST_CYCLE[(i + 1) % GHOST_CYCLE.length];
}

function chooseGhost(mode) {
  if (mode === 'others') { openBoard(); return; }
  setGhostMode(mode);
}

function setGhostMode(mode, opts = {}) {
  S.ghostMode = mode;
  S.showGhost = mode !== 'off';
  if (mode !== 'run') S.ghostRun = null;
  // `remember: false` is for a mode the game chose rather than you - arriving
  // on a new track turns the ghost off, and that must not overwrite the ghost
  // you actually picked.
  if (opts.remember !== false) {
    try { localStorage.setItem('drive.ghost', mode === 'run' ? 'me' : mode); } catch (e) {}
  }
  $('ghostOpts').querySelectorAll('[data-ghost]').forEach(b => {
    // "View others" is a door, not a state - it lights up only while the lap you
    // are chasing is one you opened through it.
    const on = b.dataset.ghost === mode ||
               (b.dataset.ghost === 'others' && mode === 'run');
    b.classList.toggle('on', on);
  });
  if (mode === 'off') { S.ghost = null; S.ghostTimes = null; }
  else if (mode === 'me') { if (CFG.mode !== 'room') loadGhost('me'); }
  else if (mode === 'wr') loadGhost('wr');
  showGhostNow();
  if (!opts.quiet) toast('Ghost: ' + ghostDescription());
}

function ghostDescription() {
  if (S.ghostMode === 'run' && S.ghostRun) {
    return S.ghostRun.who + '  ' + fmt(S.ghostRun.time_ms);
  }
  if (S.ghostMode === 'me' && CFG.mode === 'room') return 'your best lap here';
  return GHOST_LABEL[S.ghostMode] || 'Off';
}

/** The one line under the ghost buttons that says what is actually loaded. */
function showGhostNow() {
  const el = $('ghostNow');
  if (!el) return;
  if (S.ghostMode === 'off') { el.textContent = 'No ghost car.'; return; }
  if (S.ghostMode === 'run' && S.ghostRun) {
    el.innerHTML = 'Chasing <b>' + esc(S.ghostRun.who) + '</b> &middot; ' +
                   fmt(S.ghostRun.time_ms);
    return;
  }
  if (S.ghostMode === 'me') {
    el.textContent = CFG.mode === 'room'
      ? 'Your best lap of this practice session.'
      : (S.bestTime ? 'Your personal best, ' + fmt(S.bestTime) + '.'
                    : 'Drive a lap and it becomes your ghost.');
    return;
  }
  // "Nobody has set a time" was said whenever no ghost loaded, which on a
  // track with a full board was simply untrue - the record was there, its
  // replay was not. The two are different facts and only one of them is your
  // problem.
  el.textContent = S.ghost ? 'The fastest lap on this track.'
    : (S.track.record_ms != null ? 'The record here has no replay stored.'
                                 : 'Nobody has set a time here yet.');
}

/**
 * Should the ghost car be on the road right now?
 *
 * In a room it belongs to free practice and nowhere else. A race is against the
 * cars that are actually there, and a translucent fourth car drifting through
 * the pack on a line nobody drove is just something else to mistake for a
 * rival - so the ghost is off for the whole race no matter what the setting
 * says. It comes back the moment the room is practising again.
 */
function ghostOn() {
  if (!S.showGhost || !S.ghost) return false;
  if (CFG.mode !== 'room') return true;
  return !S.raceMode && S.racePhase === 'free';
}

function setSound(on) {
  S.sound.mute(!on);
  $('btnSound').textContent = 'Sound: ' + (on ? 'on' : 'off');
}

// ---------------------------------------------------------------------------
// The board, in the game
// ---------------------------------------------------------------------------

/**
 * Stopped if anything is open on top of the track, and only when alone.
 *
 * Derived in one place from what is actually on screen rather than set by each
 * panel as it opens: with four panels each assigning it, closing any one of
 * them unpaused a game with another still open, and the car would start rolling
 * behind the sheet you were reading.
 *
 * In a room the world keeps turning whatever you have open - the other cars are
 * real people and they are not waiting for you.
 */
function syncPaused() {
  const anyOpen = S.menuOpen || S.helpOpen ||
                  $('boardOv').style.display !== 'none' ||
                  $('tracksOv').style.display !== 'none';
  S.paused = anyOpen && CFG.mode === 'solo';
}

function toggleBoard(force) {
  const on = force != null ? force : $('boardOv').style.display === 'none';
  $('boardOv').style.display = on ? '' : 'none';
  syncPaused();
  if (!on) return;
  $('boardTitle').textContent = S.track.name;
  $('boardDetail').innerHTML = '<p class="muted empty">Pick a time to see its splits.</p>';
}

async function openBoard() {
  toggleMenu(false);
  toggleBoard(true);
  const list = $('boardList');
  list.innerHTML = '<p class="muted empty">Loading…</p>';
  let rows = [];
  try {
    const r = await fetch('/api/board/' + S.track.slug);
    rows = (await r.json()).rows || [];
  } catch (e) {
    list.innerHTML = '<p class="muted empty">Could not load the board.</p>';
    return;
  }
  S.board = rows;
  if (!rows.length) {
    list.innerHTML = '<p class="muted empty">No times here yet. Set the first one.</p>';
    return;
  }
  list.innerHTML = rows.map((row, i) => `
    <button class="brow${row.me ? ' me' : ''}" data-row="${i}">
      <span class="brow-pos">${i + 1}</span>
      <span class="medal ${row.medal || 'none'}"></span>
      <span class="brow-name">${esc(row.name)}</span>
      <span class="brow-ms">${fmt(row.time_ms)}</span>
    </button>`).join('');
  list.querySelectorAll('[data-row]').forEach(b => {
    b.onclick = () => showBoardRow(parseInt(b.dataset.row, 10));
  });
}

/**
 * One lap, opened.
 *
 * The splits are the reason to open it: a time on its own says somebody was
 * faster, and the splits say *where*. They are shown against your own PB's
 * splits when you have them, since the gap per sector is the only part of
 * somebody else's lap you can actually do something with.
 */
function showBoardRow(i) {
  const row = (S.board || [])[i];
  if (!row) return;
  $('boardList').querySelectorAll('.brow').forEach((el, n) =>
    el.classList.toggle('open', n === i));
  const mine = S.mySplits || [];
  const splits = row.splits || [];
  const rows = splits.map((ms, n) => {
    const ref = mine[n];
    const d = ref != null ? ms - ref : null;
    return `<div class="sp">
      <span>CP ${n + 1}</span><b>${fmt(ms)}</b>
      <i class="${d == null ? '' : (d <= 0 ? 'ahead' : 'behind')}">${
        d == null ? '' : fmtDelta(d)}</i></div>`;
  }).join('');
  $('boardDetail').innerHTML = `
    <div class="bd-head">
      <div class="bd-time">${fmt(row.time_ms)}</div>
      <div class="bd-who"><span class="medal ${row.medal || 'none'}"></span>${esc(row.name)}</div>
    </div>
    <div class="bd-splits">${rows || '<p class="muted">No splits recorded.</p>'}</div>
    ${row.has_ghost ? `<div class="bd-actions">
      <button class="btn dark" data-race="${row.id}">Race this ghost</button>
      <button class="btn secondary" data-watch="${row.id}">Watch it</button>
    </div>` : '<p class="muted">This lap has no replay to watch.</p>'}`;
  const detail = $('boardDetail');
  const race = detail.querySelector('[data-race]');
  const watch = detail.querySelector('[data-watch]');
  if (race) race.onclick = () => raceGhost(row);
  if (watch) watch.onclick = () => watchGhost(row);
}

async function fetchGhost(id) {
  const r = await fetch('/api/ghost/' + S.track.slug + '?who=' + id);
  const d = await r.json();
  return d && d.ghost ? d : null;
}

async function raceGhost(row) {
  const d = await fetchGhost(row.id).catch(() => null);
  if (!d) { toast('Could not load that ghost'); return; }
  useGhost(d.ghost, d.hz || GHOST_RATE);
  S.ghostRun = { id: row.id, who: d.who, time_ms: d.time_ms };
  setGhostMode('run', { quiet: true });
  toggleBoard(false);
  toast('Chasing ' + d.who + '  ' + fmt(d.time_ms));
  resetToStart();
}

// ---------------------------------------------------------------------------
// Watching somebody's lap
// ---------------------------------------------------------------------------
//
// A replay is not a run: there is no car of yours in it, the clock is theirs and
// so is the speed. So watching takes the whole driving HUD away and gives the
// camera to the ghost, rather than trying to be both at once. It loops, because
// the interesting part of somebody's lap is rarely the first corner.

async function watchGhost(row) {
  // Watching parks your car and stops your pose going out, so in the middle of
  // a race it would leave a stationary obstacle on the track with your name on
  // it while everyone else is still driving.
  if (S.raceMode) { toast('Not while the race is on'); return; }
  const d = await fetchGhost(row.id).catch(() => null);
  if (!d) { toast('Could not load that lap'); return; }
  toggleBoard(false);
  startWatching(d.ghost, d.hz || GHOST_RATE, d);
}

function startWatching(frames, hz, meta) {
  stopWatching();
  const view = new CarView(S.renderer.scene, '#ffd96b');
  view.setLabel(meta.who || 'Replay', '#ffd96b');
  S.watch = {
    g: new Ghost(frames, hz), t: 0, view, meta,
    dur: frames.length / hz,
    subject: { pos: new THREE.Vector3(), fwd: new THREE.Vector3(0, 0, -1),
               up: new THREE.Vector3(0, 1, 0), speed: 0, grounded: true },
    prev: null,
  };
  S.car.frozen = true;
  S.view.setVisible(false);
  document.body.classList.add('watching');
  $('watchWho').textContent = 'Watching ' + (meta.who || 'a lap');
  $('watchBar').style.display = '';
}

function stopWatching() {
  if (!S.watch) return;
  S.watch.view.dispose();
  S.watch = null;
  S.car.frozen = false;
  S.view.setVisible(true);
  document.body.classList.remove('watching');
  $('watchBar').style.display = 'none';
  resetToStart();
}

/** Advance the replay and point the camera at it. */
function updateWatch(dt) {
  const w = S.watch;
  w.t += dt;
  if (w.t > w.dur) { w.t = 0; w.prev = null; }
  const f = w.g.at(w.t);
  if (!f) return;
  const p = new THREE.Vector3(f[0], f[1], f[2]);
  const q = new THREE.Quaternion(f[3], f[4], f[5], f[6]).normalize();
  const s = w.subject;
  // The camera wants a speed and a frame to orbit in, which a replay does not
  // carry - so both are read back off the motion itself.
  s.speed = w.prev ? p.distanceTo(w.prev) / Math.max(1e-3, dt) : 0;
  s.pos.copy(p);
  s.fwd.set(0, 0, -1).applyQuaternion(q);
  s.up.set(0, 1, 0).applyQuaternion(q);
  w.prev = p.clone();
  w.view.update(p, q, {});
  w.view.group.visible = true;
  $('watchClock').textContent = fmt(w.t * 1000);
}

// ---------------------------------------------------------------------------
// The track switcher
// ---------------------------------------------------------------------------

function toggleTracks(force) {
  const on = force != null ? force : $('tracksOv').style.display === 'none';
  $('tracksOv').style.display = on ? '' : 'none';
  $('btnTracks').classList.toggle('on', on);
  syncPaused();
  if (on) {
    // Only the host picks in a room, and saying so beats a grid of cards that
    // silently ignore you.
    const locked = CFG.mode === 'room' && !S.isHost;
    $('tracksNote').style.display = locked ? '' : 'none';
    $('tGrid').classList.toggle('locked', locked);
    markActiveTrack();
  }
}

function renderTrackCards() {
  const grid = $('tGrid');
  if (!grid) return;
  grid.innerHTML = (CFG.cards || []).map(c => `
    <button class="tcard2" data-track="${esc(c.slug)}">
      <span class="tcard2-img" style="background-image:url('${esc(c.image)}')">
        <span class="tcard2-live">Now</span>
      </span>
      <span class="tcard2-body">
        <span class="tcard2-top">
          <b>${esc(c.name)}</b>
          <span class="diff">${[0, 1, 2, 3, 4].map(i =>
            `<span class="pip${i < c.difficulty ? ' on' : ''}"></span>`).join('')}</span>
        </span>
        <span class="tcard2-blurb">${esc(c.blurb)}</span>
        <!-- Your time and nothing else. The record was here too and it made
             every card an argument: two times, two names, one of them somebody
             else's. This is a menu for choosing where to drive - what you have
             done on a track is what tells them apart at a glance. The record is
             still on the board and the home page, where you are reading rather
             than picking. -->
        <span class="tcard2-foot">
          <span class="medal ${c.pb_medal || 'none'}"></span>
          <span>${c.pb_ms ? fmt(c.pb_ms) + (c.pb_rank ? ' (#' + c.pb_rank + ')' : '')
                          : 'not driven'}</span>
        </span>
      </span>
    </button>`).join('');
  grid.querySelectorAll('[data-track]').forEach(el => {
    el.onclick = () => pickTrack(el.dataset.track);
  });
  markActiveTrack();
}

/**
 * Change track without going anywhere.
 *
 * Solo this swaps the world in place and leaves the URL alone: /solo is the
 * address of "driving on your own", and the track is a thing you change while
 * you are there. In a room it is the host's decision to make, so it goes to the
 * server and comes back to everyone at once.
 */
function pickTrack(slug) {
  if (slug === S.track.slug) { toggleTracks(false); return; }
  if (CFG.mode === 'room') {
    if (!S.isHost) { toast('Only the host can change the track'); return; }
    S.socket.emit('set_track', { code: CFG.room, track: slug });
    toggleTracks(false);
    return;
  }
  toggleTracks(false);
  switchTrack(slug);
}

/** Which kind of session this is, shown under the track name. */
function setMode(text, racing) {
  const el = $('modeLabel');
  el.textContent = text;
  el.className = 'mode' + (racing ? ' racing' : '');
}

/** The room's phase, said out loud in the top-left corner. */
const PHASE_LABEL = {
  free: ['Multiplayer - Free practice', false],
  qualifying: ['Multiplayer - Qualifying', true],
  countdown: ['Multiplayer - Race about to start', true],
  racing: ['Multiplayer - Race in progress', true],
  results: ['Multiplayer - Race finished', false],
};

/**
 * Everything that depends on the phase, in one place.
 *
 * The buttons in this room are mutually exclusive by phase and there are now
 * four of them, so they are derived from the phase rather than assigned at
 * each transition - the same reason `syncPaused` exists. Miss one transition
 * with the assigning version and the room offers you a race that has already
 * started.
 */
function applyPhase() {
  if (CFG.mode !== 'room') return;
  const p = S.previewPhase || S.racePhase;      // `?panel=qual|racing`
  const [text, racing] = PHASE_LABEL[p] || PHASE_LABEL.free;
  setMode(text, racing);

  const start = $('btnStartRace'), end = $('btnEndRace'), resign = $('btnResign');
  const live = p === 'qualifying' || p === 'countdown' || p === 'racing';
  // Only the host starts or stops one, so only the host is offered either.
  start.style.display = (S.isHost && (p === 'free' || p === 'qualifying')) ? '' : 'none';
  start.textContent = p === 'qualifying' ? 'Start race now' : 'Start race';
  end.style.display = (S.isHost && live) ? '' : 'none';
  // It cancels before the lights and flags the race after them. Saying which
  // matters: one of them throws a result away and the other records one.
  end.textContent = p === 'racing' ? 'End race' : 'Cancel race';
  disarm(end);

  // You can only retire from something you are in, and only if you are still
  // in it - a car already home or already out has nothing to resign from.
  const out = S.raceDone;
  resign.style.display = ((p === 'countdown' || p === 'racing') && !out) ? '' : 'none';
  if (resign.style.display === 'none') disarm(resign);

  $('qualCard').style.display = p === 'qualifying' ? '' : 'none';
  // The board takes the right-hand third of a phone screen, and the start hint
  // is centred across the whole of it, so the two need telling apart.
  document.body.classList.toggle('qualifying', p === 'qualifying');
  if (p !== 'qualifying') stopQualClock();
  showRematch();
}

// --- the two irreversible buttons -----------------------------------------
// Resigning and ending a race both happen mid-drive, one press away from the
// settings icon, and neither can be taken back. So both arm on the first press
// and fire on the second, in place: an "are you sure" overlay would cover the
// race you want to look at before answering it, and the answer is nearly
// always "no, I misclicked".

const ARM_MS = 3500;

function disarm(btn) {
  if (!btn) return;
  clearTimeout(btn._arm);
  btn._arm = null;
  btn.classList.remove('armed');
  if (btn._word) { setLabel(btn, btn._word); btn._word = null; }
}

/** The label lives in a span on the icon button and is the whole of the text one. */
function setLabel(btn, text) {
  const span = btn.querySelector('.hbtn-label');
  if (span) span.textContent = text; else btn.textContent = text;
}

function labelOf(btn) {
  const span = btn.querySelector('.hbtn-label');
  return span ? span.textContent : btn.textContent;
}

/** True once the second press lands; the first one only arms it. */
function armed(btn, prompt) {
  if (btn._arm) { disarm(btn); return true; }
  btn._word = labelOf(btn);
  setLabel(btn, prompt);
  btn.classList.add('armed');
  btn._arm = setTimeout(() => disarm(btn), ARM_MS);
  return false;
}

// ---------------------------------------------------------------------------
// Qualifying
// ---------------------------------------------------------------------------
// Ninety seconds of ordinary practice with a clock on it and everyone's best
// lap on the screen. Nothing about the driving changes - which is the point,
// since the grid should be set by the thing you were already doing - so this
// is all presentation plus one message per improved lap.

/** The provisional grid, exactly as the server ordered it. */
function renderQual(q) {
  if (!q) return;
  S.qualEnd = q.ends != null ? performance.now() + (q.ends - serverNow()) : null;
  const el = $('qualRows');
  el.innerHTML = (q.rows || []).map((e, i) => `
    <div class="qual-row${CFG.me && e.pid === CFG.me.pid ? ' me' : ''}">
      <span class="p">${i + 1}</span>
      <span class="st-dot" style="background:${esc(e.color || '#888')}"></span>
      <span class="nm">${esc(e.name)}</span>
      <span class="ms${e.ms == null ? ' none' : ''}">${e.ms != null ? fmt(e.ms) : '&mdash;'}</span>
    </div>`).join('');
  drawQualClock();
}

function drawQualClock() {
  const el = $('qualClock');
  if (!el || S.qualEnd == null) return;
  const left = Math.max(0, (S.qualEnd - performance.now()) / 1000);
  el.textContent = Math.floor(left / 60) + ':' + String(Math.floor(left % 60)).padStart(2, '0');
  el.classList.toggle('urgent', left <= 10);
}

function startQualClock() {
  stopQualClock();
  S.qualTimer = setInterval(() => {
    if (S.racePhase !== 'qualifying') { stopQualClock(); return; }
    drawQualClock();
  }, 250);
  drawQualClock();
}

function stopQualClock() {
  if (S.qualTimer) { clearInterval(S.qualTimer); S.qualTimer = null; }
}

function onQualStart(d) {
  S.racePhase = 'qualifying';
  S.raceMode = false;
  S.raceDone = false;
  S.standings = [];
  // A new session, so the lap its deltas are read against has not been driven
  // yet. Until it has, there is no delta - not one against last session's.
  S.qualBest = null;
  S.qualRef = null;
  // Qualifying is driving, so get the reading matter out of the way.
  if (S.watch) stopWatching();
  toggleBoard(false);
  toggleTracks(false);
  toggleMenu(false);
  showSide(false);
  $('raceOver').style.display = 'none';
  hideResults();
  applyPhase();
  renderQual(d.qual);
  startQualClock();
  // You have ninety seconds, so you start the one that counts now rather than
  // finishing whatever you happened to be part-way through.
  resetToStart();
  toast('Qualifying - fastest lap sets the grid');
}

/** R: throw the run away and line up again. */
function restartRun() { resetToStart(); toast('Restart'); }

/**
 * T: back to the last checkpoint with the clock still running.
 *
 * This is the same path a fall takes, so there is only ever one respawn rule -
 * `Run.update` keeps the car's respawn target pinned to the last gate reached.
 */
function backToCheckpoint() { S.car.requestRespawn(); }

function readInput() {
  const on = (k) => keys.has(k) || touchKeys.has(k);
  input.throttle = on('up') ? 1 : 0;
  input.brake = on('down') ? 1 : 0;
  input.steer = (on('right') ? 1 : 0) - (on('left') ? 1 : 0);
  input.handbrake = on('drift');
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

  // Shot mode: hold the whole track in frame and render nothing else. This is
  // how the switcher's pictures are taken (tools/shoot_tracks.py), so the
  // preview of a track is always the track as it is now rather than a drawing
  // of it that has to be kept in step.
  if (S.shot) {
    shotCamera();
    S.renderer.render(dt);
    return;
  }

  // A replay is somebody else's run, so none of the below applies to it: no
  // input, no physics, no clock of yours, and the camera belongs to them.
  if (S.watch) {
    updateWatch(dt);
    S.renderer.follow(S.watch.subject, dt);
    S.renderer.render(dt);
    return;
  }

  const inp = readInput();

  // In solo, the clock starts the moment you ask the car to move. In a race it
  // starts on the green light, which the server picks for everyone.
  if (!S.started && !S.raceMode && (inp.throttle || inp.brake || inp.steer)) {
    S.started = true;
    S.run.start(now);
    noteStart();
    markHintSeen();
  }
  if (S.raceMode && S.racePhase === 'racing' && !S.started && S.raceT0 != null && now >= S.raceT0) {
    S.started = true;
    S.car.frozen = false;
    S.run.start(S.raceT0);
    noteStart();
    markHintSeen();
  }

  // Rivals are brought up to now *before* the physics that has to hit them.
  // This used to run after, so every fixed substep in the frame resolved contact
  // against where the other cars were a frame ago - a car length of error at
  // racing speed, all of it in the direction of travel.
  updateRemotes(dt);

  // One list per frame rather than one per substep: the remote cars are
  // interpolated above and do not move again inside the fixed-step loop.
  const rivals = contactOn() ? collidables() : null;
  if (!S.paused) {
    S.stepper.run(dt, (h) => {
      S.car.step(h, inp);
      if (rivals) S.car.resolveCars(rivals, h);
      // Always called, even with nobody to tow off: that is what bleeds a
      // charge away when you drop out of the hole, or when the phase changes
      // under you and the other cars stop being there at all.
      S.car.draft(rivals, h);
    });
  }

  // run bookkeeping
  const events = S.run.update(S.car, now);
  for (const e of events) {
    if (e === 'cp') {
      S.sound.checkpoint();
      toast('Checkpoint ' + S.run.nextCp + '/' + S.run.cps.length + '  ' + fmt(S.run.time));
      // Shown at the checkpoint and then faded out, rather than ticking away
      // all lap: a number that only moves when something happened is a number
      // you read. What it is measured against is the whole question, and the
      // answer is different in each of the three sessions - see splitRef.
      const ref = splitRef(S.run.nextCp, S.run.s);
      if (ref != null) showDelta(S.run.time - ref);
    }
    if (e === 'missed') { S.sound.missed(); toast('Missed a checkpoint!'); }
    if (e === 'finish') onFinish();
  }

  drive(inp);
  render(dt, now);
  // The clock and the speed move every frame; everything else in the HUD is
  // cheap to look at but expensive to draw, so it stays on the slow tick.
  hudFast();
  if ((S.hudTick = (S.hudTick + 1) % 3) === 0) hud(now);
  sendPose(now);
}

function drive(inp) {
  const car = S.car;
  // Engine, tyres and wind, driven from the car's own state every frame.
  S.sound.engine(Math.min(1, car.speed / T.MAX_SPEED), inp.throttle, car.slip,
                 !car.grounded);
  // tyre smoke while sliding, dust when off the road
  if (car.grounded && (car.slip > 0.3 || (car.offroad && car.speed > 8))) {
    const back = new THREE.Vector3().copy(car.pos)
      .addScaledVector(car.fwd, -1.3).addScaledVector(car.up, -0.3);
    const jitter = new THREE.Vector3((Math.random() - 0.5) * 2, 0.9, (Math.random() - 0.5) * 2);
    S.renderer.smoke(back, jitter, car.offroad ? 'dust' : 'smoke');
  }
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
    braking: car.braking,
  });
  S.view.setVisible(car.respawnIn <= 0);

  // own-best ghost
  if (ghostOn() && S.started) {
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

/**
 * Frame a preview picture: over your shoulder on the start line.
 *
 * Fitting the whole track in frame was the obvious thing and it is the wrong
 * picture. From far enough away to hold a point-to-point, the road is a thread -
 * on Jump City it disappeared into the towers completely - and every track
 * became a photograph of its scenery with a track somewhere in it.
 *
 * So this stands behind the start line at a height that scales with the size of
 * the track, and looks along it. The road fills the bottom of the frame at a
 * width you can read, the layout recedes into the distance, and the sky and
 * whatever is underneath are still most of the picture, which is what makes one
 * track recognisably a different place from another.
 */
function shotCamera() {
  const sp = S.track.spawn;
  const pts = S.built.line.map(e => e.p);
  let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
  for (const p of pts) {
    x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]);
    z0 = Math.min(z0, p[2]); z1 = Math.max(z1, p[2]);
  }
  // How far back to stand grows with the track but nothing like as fast, or a
  // big track is shot from orbit and a small one from inside a hedge.
  const radius = Math.max(30, Math.hypot(x1 - x0, z1 - z0) / 2);
  const back = Math.min(70, 16 + radius * 0.22);
  const up = back * 0.62;
  const f = sp.fwd, p = sp.p;
  const cam = S.renderer.camera;
  cam.position.set(p[0] - f[0] * back, p[1] + up, p[2] - f[2] * back);
  // Aimed down at the road just ahead, not out at the horizon. Level from 40
  // units up is a picture of the skyline with a track somewhere under it - the
  // road has to be the thing in the frame, with the rest of the lap receding
  // behind it.
  cam.lookAt(new THREE.Vector3(p[0] + f[0] * back * 0.5, p[1],
                               p[2] + f[2] * back * 0.5));
  cam.updateProjectionMatrix();
}

// ---------------------------------------------------------------------------
// HUD
// ---------------------------------------------------------------------------
/**
 * The parts of the HUD that are a live reading rather than a state: the clock
 * and the speed. Every frame, deliberately.
 *
 * These used to be inside `hud()`, which runs on every third frame. That is
 * 20Hz on a 60Hz screen, and because frames land on multiples of the refresh
 * interval it did not merely look choppy - the clock could only ever show
 * `start + k * 50ms`, so its last two digits alternated between two values all
 * lap and the milliseconds read as decoration rather than a time. A timer is
 * the one number on the screen whose job is to look continuous, so it is
 * sampled as often as the screen can show it.
 *
 * Everything here is a `textContent`/inline-style write on a handful of nodes,
 * which is why it can afford the frame rate; the minimap canvas and the
 * standings list cannot, and stay in `hud()`.
 */
function hudFast() {
  const car = S.car, run = S.run;
  $('speed').textContent = Math.round(car.speed * 3.1);
  $('speedFill').style.width = Math.min(100, (car.speed / T.MAX_SPEED) * 100) + '%';
  // Over MAX_SPEED means a descent is doing the work, which is worth showing.
  $('speedFill').classList.toggle('over', car.speed > T.MAX_SPEED);
  $('time').textContent = fmt(run.state === 'ready' ? 0 : run.time);
  const slip = $('slipBar');      // rooms only; solo has nobody to tow off
  if (slip) {
    slip.classList.toggle('on', contactOn());
    slip.classList.toggle('boost', car.slipBoost > 0);
    $('slipFill').style.width = (car.slipCharge * 100) + '%';
  }
}

function hud(now) {
  const run = S.run;
  $('cpCount').textContent = run.nextCp + '/' + run.cps.length;
  $('wrongWay').style.display = run.wrongWay ? '' : 'none';

  // Race positions - but not during qualifying, which is not a race: running
  // order by distance means nothing when everybody is on their own lap, and
  // the qualifying board directly below it already lists the same people in
  // the order that does mean something.
  const qualifying = S.racePhase === 'qualifying' || S.previewPhase === 'qualifying';
  if (!qualifying && (S.raceMode || S.remotes.size)) {
    const order = liveOrder();
    const me = order.findIndex(e => e.self) + 1;
    $('position').style.display = '';
    $('posNum').textContent = me || '-';
    $('posTot').textContent = order.length;
    renderStandings(order);
    $('standingsCard').style.display = '';
  } else {
    $('position').style.display = 'none';
    $('standings').innerHTML = '';
    // An empty card is just a dark smudge in the corner.
    $('standingsCard').style.display = 'none';
  }
  drawMinimap();
  void now;
}

/**
 * What this split should be measured against, which depends on the session.
 *
 * A delta is only worth reading if the thing on the other side of it is the
 * thing you are currently trying to beat, and in each of the three sessions
 * that is something different:
 *
 * - **Racing: the leader.** Not your own old lap - in a race the only number
 *   that matters is the gap to the car in front of everybody, and a lap you
 *   set alone on a quiet track is not what you are driving against. The
 *   reference is the quickest anyone *else* has reached this checkpoint, which
 *   is by definition whoever was leading on the road at this point. If you are
 *   the one leading, that is the gap back to your nearest rival and shows as a
 *   gain, which is the same number read the other way round.
 * - **Qualifying: your best lap of the session.** The one thing qualifying is
 *   about is improving on your own time here, today, on this track.
 * - **Free practice: the ghost**, whichever lap you have chosen to chase.
 *
 * Returns null when there is nothing honest to compare with - the first car to
 * a checkpoint, or your first qualifying lap - and the caller then shows no
 * delta at all rather than one measured against the wrong lap.
 */
function splitRef(cp, s) {
  if (S.raceMode && S.racePhase === 'racing') {
    if (S.socket) S.socket.emit('split', { cp, ms: S.run.time });
    return bestRivalSplit(cp);
  }
  if (S.racePhase === 'qualifying') {
    return S.qualRef ? timeAlong(S.qualRef, s) : null;
  }
  return ghostTimeAt(s);
}

/** The quickest anybody else has got round, of those already home. */
function bestRivalFinish() {
  const me = CFG.me ? CFG.me.pid : null;
  let best = null;
  for (const e of S.standings) {
    if (e.pid === me || e.ms == null) continue;
    if (best == null || e.ms < best) best = e.ms;
  }
  return best;
}

/** The quickest anybody else has reached this checkpoint in this race. */
function bestRivalSplit(cp) {
  const me = CFG.me ? CFG.me.pid : null;
  let best = null;
  for (const pid in S.raceSplits) {
    if (pid === me) continue;
    const ms = S.raceSplits[pid][cp];
    if (ms != null && (best == null || ms < best)) best = ms;
  }
  return best;
}

/** Flash a split delta above the clock, then fade it out. */
function showDelta(diff) {
  const d = $('delta');
  const cls = 'delta ' + (diff <= 0 ? 'ahead' : 'behind');
  d.textContent = fmtDelta(diff);
  d.className = cls + ' show';
  clearTimeout(d._t);
  d._t = setTimeout(() => { d.className = cls; }, 2800);
}

function clearDelta() {
  const d = $('delta');
  clearTimeout(d._t);
  d.className = 'delta';
  d.textContent = '';
}

function ghostTimeAt(s) { return timeAlong(S.ghostTimes, s); }

/** When a recorded lap had got this far. `arr` is a `lapTimeline`. */
function timeAlong(arr, s) {
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
  const el = $('medals');
  if (!el) return;                  // rooms do not show medal times at all
  const m = S.track.medals;
  const rows = [['gold', 'Gold'], ['silver', 'Silver'], ['bronze', 'Bronze']];
  // The record heads the list, because it is the fourth time on it: the medals
  // say what the track asks of you and this says what has actually been done
  // here. Just the time, laid out exactly like the three under it - whose lap
  // it is belongs on the leaderboard, not on a card you read at 200km/h.
  // Green, and not a medal colour: it is not a medal and cannot be won.
  const wr = S.track.record_ms;
  // Your own best is not in here - it lives under the clock, bottom left of
  // it, where you look for it while you are driving.
  el.innerHTML =
    `<div class="mrow"><span class="medal wr"></span><span>WR</span>` +
    `<b>${wr != null ? fmt(wr) : '&mdash;'}</b></div>` +
    rows.map(([k, label]) =>
      `<div class="mrow"><span class="medal ${k}"></span><span>${label}</span>` +
      `<b>${fmt(m[k] * 1000)}</b></div>`).join('');
}

function showPb() { $('pbTime').textContent = S.bestTime ? fmt(S.bestTime) : '--:--.---'; }

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
  // Which ghost this request is for. Click "world record" and then "my best"
  // before the first answer arrives and the slower reply would otherwise land
  // on top of the newer choice.
  const want = S.ghostMode;
  const slug = S.track.slug;
  try {
    const r = await fetch('/api/ghost/' + slug + '?who=' + who);
    const d = await r.json();
    if (S.ghostMode !== want || S.track.slug !== slug) return;
    if (d.ghost) useGhost(d.ghost, d.hz || GHOST_RATE);
  } catch (e) { /* no ghost is fine */ }
  // **The line has to be written again here.** `setGhostMode` writes it the
  // instant you click, which is before this request has answered - and the
  // first thing above is to clear the ghost - so at that moment there is
  // reliably no ghost loaded and the line said so. That is why picking "world
  // record" reported that the record had no replay even when it plainly did
  // and the ghost car then appeared: the message was describing the half
  // second before the answer arrived, not the answer.
  if (S.ghostMode === want && S.track.slug === slug) showGhostNow();
}

/** Race against these frames from now on. */
function useGhost(frames, hz) {
  if (!frames || frames.length < 2) return;
  S.ghost = new Ghost(frames, hz || GHOST_RATE);
  S.ghostTimes = lapTimeline(S.ghost.frames, S.ghost.hz);
}

/**
 * Distance along the track against elapsed time, for one recorded lap.
 *
 * This is what a split delta is measured with: "how long did the reference lap
 * take to get this far", not "where is it now". Shared by the ghost and by the
 * qualifying reference, which are two different laps answering the same
 * question and must not be two copies of this loop.
 */
function lapTimeline(frames, hz) {
  const out = [];
  const tmp = new THREE.Vector3();
  const course = new Course(S.built);
  for (let i = 0; i < frames.length; i++) {
    const f = frames[i];
    tmp.set(f[0], f[1], f[2]);
    out.push({ s: course.locate(tmp).s, ms: (i / hz) * 1000 });
  }
  // enforce monotonic s so the binary search is valid
  for (let i = 1; i < out.length; i++) {
    if (out[i].s < out[i - 1].s) out[i].s = out[i - 1].s;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Starting and finishing
// ---------------------------------------------------------------------------

/**
 * Tell the server a run has begun.
 *
 * An attempt is the clock starting - not loading the page, not rolling about
 * behind the line - which is why this sits next to `run.start()` and nowhere
 * near setup, and why the race branch calls it too: a green light is a start
 * like any other, and a lap driven against other people is still a lap.
 *
 * Fire and forget, and quietly. A start is a tally rather than a result: there
 * is nothing to tell the player if it fails, nothing to show them if it works,
 * and unlike a lap there is nothing worth keeping on the device to hand over
 * later - a start that never lands is simply one that was not counted. Guests
 * have no row to count it in, so they do not send it at all; the clamp on the
 * way back out keeps their finishes from outnumbering their starts once they
 * log in and the laps their browser kept get replayed.
 */
function noteStart() {
  if (!CFG.loggedIn || typeof fetch !== 'function') return;
  try {
    fetch('/api/start', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track: S.track.slug }),
    }).catch(() => {});
  } catch (e) { /* no network, no counter, no interruption */ }
}

async function onFinish() {
  const run = S.run;
  const medal = medalFor(run.time);
  S.sound.finish(medal);
  S.car.frozen = false;
  const prev = S.bestTime;
  const improved = prev == null || run.time < prev;
  // A race ends with the standings sheet, not this one - and it ends when the
  // last car is in, not when you cross the line.
  const racing = S.raceMode;
  const qualifying = S.racePhase === 'qualifying';

  if (racing && S.socket) {
    S.socket.emit('finish', { ms: run.time });
    S.raceDone = true;
    applyPhase();
  }
  // A qualifying lap is an ordinary practice lap that also counts for the
  // grid, so it goes up the same way any other lap does and the server keeps
  // the best of them.
  if (qualifying && S.socket) S.socket.emit('qual_time', { ms: run.time });

  // In a room your ghost is the best lap of this practice session. Not your
  // all-time PB: the room is a place you turn up and learn a track together,
  // and a ghost from three weeks ago is not what you are chasing there.
  if (CFG.mode === 'room' && !racing &&
      (S.sessionBest == null || run.time < S.sessionBest)) {
    S.sessionBest = run.time;
    useGhost(run.ghost.slice(), GHOST_RATE);
  }

  // The finish is the last split, so it is measured the same way the others
  // were: against the leader in a race, against your best lap of the session
  // in qualifying, and against your personal best the rest of the time.
  if (racing) {
    const lead = bestRivalFinish();
    if (lead != null) showDelta(run.time - lead);
  } else if (qualifying) {
    if (S.qualBest != null) showDelta(run.time - S.qualBest);
  } else if (prev != null) {
    showDelta(run.time - prev);
  }
  // Your best lap of the qualifying session is the reference every split in it
  // is read against, so it is kept whole - the lap, not just its time.
  if (qualifying && (S.qualBest == null || run.time < S.qualBest)) {
    S.qualBest = run.time;
    S.qualRef = lapTimeline(run.ghost, GHOST_RATE);
  }
  // The full-screen sheet is for a session that has ended. Neither of these
  // has: a race ends on the standings when the last car is in, and qualifying
  // ends when the clock does - and covering the road with a results overlay
  // while there are seconds left to improve is taking the session away.
  if (racing) toast('Finished ' + fmt(run.time));
  else if (qualifying) {
    // Straight back out for another. Ninety seconds is two or three laps on
    // most of these tracks, and making each one cost a keypress on a screen
    // with a running clock on it is making you spend the session on the menu.
    toast('Qualifying lap ' + fmt(run.time) + ' - going again');
    setTimeout(() => { if (S.racePhase === 'qualifying') resetToStart(); }, 1200);
  }
  else showResults({ time: run.time, medal, pb: improved ? run.time : prev });

  try {
    const r = await fetch('/api/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track: S.track.slug, time_ms: run.time,
                             splits: run.splits, ghost: run.ghost,
                             distance: Math.round(run.distance) }),
    });
    const d = await r.json();
    if (d.ok && d.stored) {
      // `is_record` and `medal` both describe the stored PB row, which is not
      // this run unless this run beat it - so a slow lap by the record holder
      // is neither a record nor worth the record's medal.
      if (d.is_record && d.improved) S.sound.record();
      S.bestTime = d.pb_ms;
      if (CFG.pbs) CFG.pbs[S.track.slug] = d.pb_ms;
      if (!racing) {
        showResults({ time: run.time, medal, rank: d.run_rank,
                      pb: d.pb_ms, pbRank: d.rank, wr: d.record_ms });
      }
      // Solo, a new PB is a new ghost. In a room the practice ghost is this
      // session's, and it has already been set above.
      if (d.improved && CFG.mode !== 'room') loadGhost('me');
    } else {
      if (improved) { S.bestTime = run.time; localBest(run.time); }
      // A guest's lap is kept whole - replay and all - so that logging in later
      // puts it on the board rather than asking them to drive it again.
      if (d.guest && window.DrivePending) {
        window.DrivePending.save({
          track: S.track.slug, time_ms: run.time, splits: run.splits,
          ghost: run.ghost, distance: Math.round(run.distance),
        });
      }
      if (!racing) {
        showResults({ time: run.time, medal, rank: d.run_rank, pb: S.bestTime,
                      wr: d.record_ms, note: d.note || d.error || null });
      }
    }
  } catch (e) {
    // The request never landed, so nobody has this lap but us. Keep it in the
    // same place a guest's laps go and it will be handed over on a later page.
    if (window.DrivePending) {
      window.DrivePending.save({
        track: S.track.slug, time_ms: run.time, splits: run.splits,
        ghost: run.ghost, distance: Math.round(run.distance),
      });
    }
    if (improved) { S.bestTime = run.time; localBest(run.time); }
    if (!racing) {
      showResults({ time: run.time, medal, pb: improved ? run.time : prev,
                    note: 'Offline - saved, and sent when you reconnect.' });
    }
  }
  renderMedalTable();
  showPb();
}

function medalFor(ms) {
  const m = S.track.medals, s = ms / 1000;
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

function storedBest() {
  try {
    const v = parseInt(localStorage.getItem('drive.pb.' + S.track.slug) || '0', 10);
    return v > 0 ? v : null;
  } catch (e) { return null; }
}

const rankLabel = (n) => (n ? '#' + n : '—');

/**
 * The finish sheet: your time, then your PB, then the record, with ranks.
 *
 * Called twice per run - once the instant you cross the line, and again when
 * the server has said where the time places - so anything it does not know yet
 * shows a dash rather than moving the layout around when the answer arrives.
 */
function showResults(r) {
  $('results').style.display = '';
  $('resTime').textContent = fmt(r.time);
  const med = $('resMedal');
  med.className = 'medal-big ' + (r.medal || 'none');
  med.textContent = r.medal ? r.medal.toUpperCase() : 'FINISHED';
  $('resRank').textContent = rankLabel(r.rank);
  $('resPb').textContent = r.pb != null ? fmt(r.pb) : '--:--.---';
  $('resPbRank').textContent = rankLabel(r.pbRank);
  $('resWr').textContent = r.wr != null ? fmt(r.wr) : '--:--.---';
  // Only ever a problem, never a summary - the numbers above are the summary.
  $('resNote').innerHTML = r.note ? `<div>${esc(r.note)}</div>` : '';
}

function hideResults() { $('results').style.display = 'none'; }

function toggleMenu(force) {
  S.menuOpen = force != null ? force : !S.menuOpen;
  if (S.menuOpen) toggleHelp(false);
  $('menu').style.display = S.menuOpen ? '' : 'none';
  $('btnSettings').classList.toggle('on', S.menuOpen);
  syncPaused();
}

function toggleHelp(force) {
  S.helpOpen = force != null ? force : !S.helpOpen;
  if (S.helpOpen) toggleMenu(false);
  $('help').style.display = S.helpOpen ? '' : 'none';
  $('btnHelp').classList.toggle('on', S.helpOpen);
  syncPaused();
}

function markActiveTrack() {
  document.querySelectorAll('[data-track]').forEach(el => {
    el.classList.toggle('active', el.dataset.track === S.track.slug);
  });
}

// ---------------------------------------------------------------------------
// Netcode
// ---------------------------------------------------------------------------
const POSE_HZ = 30;

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
    applyPhase();
    // Walking in on a session already running: show it rather than pretending
    // the room is idle until the next message happens to arrive.
    if (S.racePhase === 'qualifying' && d.race && d.race.qual) {
      renderQual(d.race.qual);
      startQualClock();
    }
    (d.chat || []).forEach(addChat);
  });
  socket.on('roster', (d) => {
    renderRoster(d.players);
    if (d.track && d.track !== S.track.slug) switchTrack(d.track);
  });
  socket.on('poses', onPoses);
  socket.on('track_change', (d) => switchTrack(d.track));
  socket.on('qual_start', onQualStart);
  socket.on('qual_progress', (d) => { if (S.racePhase === 'qualifying') renderQual(d.qual); });
  // Everyone's checkpoint times, so a delta can be measured against the car in
  // front of the field rather than against a lap you drove on your own.
  socket.on('race_split', (d) => {
    (S.raceSplits[d.pid] || (S.raceSplits[d.pid] = {}))[d.cp] = d.ms;
  });
  socket.on('race_start', onRaceStart);
  socket.on('race_green', onRaceGreen);
  socket.on('race_progress', (d) => { S.standings = d.finish || []; });
  socket.on('race_result', onRaceResult);
  socket.on('race_reset', () => {
    S.raceMode = false; S.racePhase = 'free'; S.raceT0 = null;
    S.raceDone = false;
    S.standings = [];
    applyPhase();
    $('countdown').style.display = 'none';
  });
  // A race that stopped being a race: called off before the lights, or the
  // room emptied. Nothing was recorded, so there is no sheet - just the room
  // back, and a line saying why so it does not look like a glitch.
  socket.on('race_abort', (d) => {
    S.raceMode = false; S.racePhase = 'free'; S.raceT0 = null;
    S.raceDone = false;
    S.standings = [];
    S.car.frozen = false;
    applyPhase();
    $('countdown').style.display = 'none';
    $('raceOver').style.display = 'none';
    toast(d && d.why ? 'Race called off - ' + d.why : 'Race called off');
    resetToStart();
  });
  // Your own resignation, confirmed. Everyone else's shows up in the standings.
  socket.on('resigned', () => {
    S.raceMode = false;
    S.raceDone = true;
    S.car.frozen = false;
    applyPhase();
    toast('Retired - back to practice');
    resetToStart();
  });
  socket.on('chat', addChat);
  socket.on('kicked', (d) => { if (CFG.me && d.pid === CFG.me.pid) location.href = '/lobbies'; });
  socket.on('room_closed', () => { location.href = '/lobbies'; });
  socket.on('room_error', (d) => toast(d.error || 'Error'));

  $('btnStartRace').onclick = () => socket.emit('start_race', { code: CFG.room });
  $('btnEndRace').onclick = (e) => {
    const b = e.currentTarget;
    // "Cancel" throws a session away and "End race" writes a result, so the
    // confirmation says which one the second press is about to do.
    if (!armed(b, S.racePhase === 'racing' ? 'End it?' : 'Cancel it?')) return;
    socket.emit('end_race', { code: CFG.room });
  };
  $('btnResign').onclick = (e) => {
    if (!armed(e.currentTarget, 'Sure?')) return;
    socket.emit('resign', {});
  };
  $('btnLeave').onclick = () => { socket.emit('leave'); location.href = '/lobbies'; };
  // Every way out of a room is an ordinary link, so it navigates whatever
  // happens; this just gives the room a chance to hear about it first.
  for (const id of ['btnQuit', 'btnExit', 'btnRaceQuit']) {
    const el = $(id);
    if (el) el.addEventListener('click', () => socket.emit('leave'));
  }
  // After a race: practise the track again, or go round again.
  $('btnPractice').onclick = () => {
    $('raceOver').style.display = 'none';
    // The server drops the room back to free on its own a few seconds later;
    // doing it here too means Practice is instant rather than "instant, then
    // the ghost appears".
    S.racePhase = 'free';
    applyPhase();
    resetToStart();
  };
  $('btnRematch').onclick = () => {
    $('raceOver').style.display = 'none';
    socket.emit('start_race', { code: CFG.room });
  };
  $('chatForm').onsubmit = (e) => {
    e.preventDefault();
    const inp = $('chatInput');
    if (inp.value.trim()) socket.emit('chat', { text: inp.value.trim() });
    inp.value = '';
  };
  // Track picking is the switcher's job in both modes now - see pickTrack.
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
    // `snap.t` is when the *snapshot* went out, but a car's pose inside it can
    // be a whole pose-interval older than that - so each car carries its own
    // age, and how far it is extrapolated is measured from when it actually
    // reported. Reading them all as fresh under-extrapolates every car by a
    // different amount each tick, which is jitter no smoothing can remove.
    // (Guarded for a client that outlives a server without the field.)
    r.packetT = snap.t - (a.length > 13 ? a[13] : 0);
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
 * Packets arrive 30 times a second with a position and a velocity. Rendering the
 * raw positions would stutter, and rendering them delayed would mean bumping a
 * car where it *was*. So: extrapolate the last packet forward to the current
 * server time with its velocity, then chase that target exponentially. The car
 * you see and the car you hit are the same car, and the motion stays smooth
 * between packets - which is what keeps the contact spring quiet.
 *
 * Chasing is for the small corrections between packets and nothing else. A car
 * that respawns, is put on the grid, or simply goes quiet for a moment does not
 * *travel* to its new position - so a jump bigger than any car could have driven
 * is taken whole. Smoothing one is worse than useless: the car streaks across
 * the map at a speed nothing can do, through the middle of everybody, and is
 * solid the entire way.
 */
const REMOTE_SNAP = 12;               // units; ~3.5 car lengths, well past a frame of driving

function updateRemotes(dt) {
  const nowS = serverNow();
  for (const r of S.remotes.values()) {
    const ahead = Math.min(0.35, Math.max(0, (nowS - r.packetT) / 1000));
    const tx = r.px + r.vel.x * ahead;
    const ty = r.py + r.vel.y * ahead;
    const tz = r.pz + r.vel.z * ahead;
    // A respawning car is not on the track at all, so wherever it comes back is
    // a jump by definition - and it is hidden below, so the snap is never seen.
    const jump = !r.primed || (r.flags & FLAG.RESPAWN) ||
      (tx - r.pos.x) ** 2 + (ty - r.pos.y) ** 2 + (tz - r.pos.z) ** 2 > REMOTE_SNAP ** 2;
    if (jump) {
      r.pos.set(tx, ty, tz); r.rq.copy(r.q); r.primed = true;
    } else {
      const k = 1 - Math.exp(-16 * dt);
      r.pos.x += (tx - r.pos.x) * k;
      r.pos.y += (ty - r.pos.y) * k;
      r.pos.z += (tz - r.pos.z) * k;
      r.rq.slerp(r.q, 1 - Math.exp(-18 * dt));
    }
    r.fwd.set(0, 0, -1).applyQuaternion(r.rq);
    // Remote cars show their brake lights too, which is most of what tells you a
    // rival is slowing. Braking is the one flag that changes nothing else about
    // them: it is what a rival does in every corner, so a car that stopped being
    // drawn or stopped being solid for the length of a braking zone would blink
    // out and be driven through at exactly the moment you are closest to it.
    // Only RESPAWN takes a car off the track.
    const off = !!(r.flags & FLAG.RESPAWN);
    r.view.update(r.pos, r.rq, { braking: !!(r.flags & FLAG.BRAKE), spin: 0 });
    r.view.group.visible = !off;
  }
}

/**
 * Are the other cars real to you right now - solid, and worth towing off?
 *
 * Contact and the slipstream are the same question asked twice, so they are one
 * answer: both belong to the two phases where the cars around you are cars you
 * are actually driving against - **free practice and the race itself**.
 *
 * Qualifying is the exception, and the reason is the whole point of qualifying:
 * everybody is alone on their own lap against the clock, on a road they are all
 * using at different points of it. Being punted by somebody a corner behind you
 * on their out-lap would take away the one thing the session is for, and a tow
 * off a car you are not racing would hand out a grid slot nobody drove for. So
 * for those ninety seconds the rivals are still drawn - you want to know where
 * they are - and you go straight through them. Countdown and the results sheet
 * are outside it for the same reason there is nothing to race there.
 */
function contactOn() {
  if (CFG.mode !== 'room') return false;
  return S.racePhase === 'free' || (S.raceMode && S.racePhase === 'racing');
}

function collidables() {
  const out = [];
  for (const r of S.remotes.values()) {
    if (r.flags & FLAG.RESPAWN) continue;   // not on the track: nothing to hit
    out.push(r);
  }
  return out;
}

function renderRoster(players) {
  S.roster = players;
  const isHost = !!(CFG.me && players.some(p => p.pid === CFG.me.pid && p.is_host));
  S.isHost = isHost;
  // The host can change mid-race if the old one leaves, and every button that
  // is the host's has to follow them - which is all of them, so this is the
  // one call rather than four assignments.
  applyPhase();
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
    if (S.watch) stopWatching();
    S.raceMode = false; S.racePhase = 'free'; S.raceT0 = null;
    if ($('raceOver')) $('raceOver').style.display = 'none';
    loadTrack(t, { switched: true });
    toast('Track: ' + t.name);
    // Solo, the URL is one more thing naming the track, and the one people copy
    // out of the bar. `/solo/<slug>` stays a real link, so it has to name the
    // track actually on the screen.
    //
    // `replaceState`, not `pushState`: switching track is changing a setting
    // inside one session, not travelling somewhere you should be able to go
    // Back out of - Back belongs to the page you came in from. The query string
    // is dropped because it can only be stale by now: `?ghost=`/`?watch=` name a
    // lap on the track you have just left, and `?panel=` was consumed at boot.
    //
    // A room is left alone entirely. Its URL is the room code, which is what
    // people share to join, and it has nothing to do with the current track.
    if (CFG.mode !== 'room') history.replaceState(null, '', '/solo/' + slug);
    // So that "Solo" next time opens the track you were actually driving,
    // rather than the one you happened to arrive on.
    fetch('/api/last-track', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track: slug }),
    }).catch(() => {});
  } catch (e) { toast('Could not load that track'); }
}

function onRaceStart(d) {
  S.raceMode = true;
  S.racePhase = 'countdown';
  S.raceDone = false;
  S.standings = [];
  S.raceSplits = {};        // this race's checkpoint times, nobody else's
  stopQualClock();
  // Everything you might have open belongs to practice, and the lights are
  // about to go out.
  if (S.watch) stopWatching();
  toggleBoard(false);
  toggleTracks(false);
  toggleMenu(false);
  // Get the room drawer out of the way - the lights are about to go out.
  showSide(false);
  applyPhase();
  $('raceOver').style.display = 'none';
  placeOnGrid(d);
  S.run.reset();
  S.started = false;
  S.car.frozen = true;
  hideResults();
  // Convert the server's green-light time onto our own clock.
  S.raceT0 = performance.now() + (d.t0 - serverNow());
  countdownLoop();
}

/**
 * Line up behind the start line, in qualifying order.
 *
 * Staggered rather than square, and the sides alternate. Two things were wrong
 * with the old two-by-two grid, and only one of them was the ordering: cars
 * side by side at the same distance reach the first corner together, so the
 * one on the inside of it simply gets there, and which column that is never
 * changed. Nobody knows which way the first corner goes - not the server, not
 * this function - but nobody needs to: staggering means the two cars in a row
 * are not fighting for the same metre of road at the same instant, and the
 * server flipping `flip` every race means whichever side is the good one is
 * not the same person's side twice running.
 *
 * Pole keeps its advantage. It was earned in qualifying, and taking it away
 * would make the session pointless.
 */
function placeOnGrid(d) {
  const slot = (d.grid && CFG.me) ? (d.grid[CFG.me.pid] || 0) : 0;
  const g = S.course.startGate();
  if (!g) return;
  const row = Math.floor(slot / 2);
  // The odd slot of each row sits a little further back, F1 style, so the row
  // is a staircase rather than a rank - and starts its lap a car length behind
  // rather than alongside.
  const back = 4 + row * 5.5 + (slot % 2 ? 2.4 : 0);
  const side = (slot % 2 ? 1 : -1) * (d.flip ? -1 : 1);
  const lat = side * 2.1;
  S.car.placeAt([g.p[0] - g.f[0] * back + g.r[0] * lat,
                 g.p[1] + 0.3,
                 g.p[2] - g.f[2] * back + g.r[2] * lat], g.f);
  if (slot === 0) toast('Pole position');
  else toast('Starting ' + ordinal(slot + 1));
}

function ordinal(n) {
  const s = ['th', 'st', 'nd', 'rd'], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
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
  applyPhase();
  if (d && d.t0) S.raceT0 = performance.now() + (d.t0 - serverNow());
}

/**
 * The race is over, so put the race's own sheet up.
 *
 * Nothing like the solo one on purpose. A time trial ends in a time measured
 * against a medal and a record; a race ends in an *order*, and the only things
 * worth offering afterwards are the three ways to spend the next few minutes:
 * practise the track, go again, or leave.
 */
function onRaceResult(d) {
  S.racePhase = 'results';
  S.raceMode = false;
  S.raceDone = false;
  S.car.frozen = false;
  applyPhase();
  $('raceOverTitle').textContent =
    d.why === 'ended by the host' ? 'Race ended early' : 'Race result';
  hideResults();
  $('raceStandings').innerHTML = d.standings.map((e, i) => {
    const delta = (d.elo || {})[e.pid];
    return `<div class="res-row${CFG.me && e.pid === CFG.me.pid ? ' me' : ''}">
      <span class="p">${i + 1}</span>
      <span class="st-dot" style="background:${esc(e.color || '#888')}"></span>
      <span class="nm">${esc(e.name)}</span>
      <span class="ms">${e.ms != null ? fmt(e.ms) : 'DNF'}</span>
      <span class="el${delta ? (delta.delta >= 0 ? ' up' : ' down') : ''}">${
        delta ? (delta.delta >= 0 ? '+' : '') + delta.delta : ''}</span>
    </div>`;
  }).join('');
  const mine = CFG.me ? (d.elo || {})[CFG.me.pid] : null;
  const elo = $('raceElo');
  elo.style.display = mine ? '' : 'none';
  if (mine) elo.innerHTML = `Rating ${mine.before} &rarr; <b>${mine.after}</b>`;
  $('raceOver').style.display = '';
  showRematch();
}

/** Only the host can start one, so only the host is offered one. */
function showRematch() {
  const b = $('btnRematch');
  if (b) b.style.display = S.isHost ? '' : 'none';
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
