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

/**
 * The lap you picked last time is the lap you probably still want.
 *
 * Provisional pole is only a thing in a room, so it is only remembered into
 * one: arriving alone on a time trial with the splits set against a session
 * that is not happening would be a setting that cannot come true.
 */
function storedGhostMode() {
  const ok = CFG.mode === 'room' ? ['off', 'me', 'pole', 'wr'] : ['off', 'me', 'wr'];
  try {
    const v = localStorage.getItem('drive.ghost');
    return ok.includes(v) ? v : 'me';
  } catch (e) { return 'me'; }
}

/** A remembered on/off, for the three switches in settings. */
function storedFlag(key, dflt) {
  try {
    const v = localStorage.getItem(key);
    return v == null ? dflt : v === '1';
  } catch (e) { return dflt; }
}

function rememberFlag(key, on) {
  try { localStorage.setItem(key, on ? '1' : '0'); } catch (e) {}
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const S = {
  track: window.DRIVE_TRACK,
  built: null, course: null, run: null, car: null,
  renderer: null, sound: new Sound(), stepper: new Stepper(T),
  view: null, ghostView: null, ghost: null, ghostTimes: null,
  // Whose lap the ghost is, and what colour the car drawing it currently is.
  // Two fields because the view is rebuilt only when the answer changes.
  ghostColor: null, ghostViewColor: null, ghostLivery: null,
  // Which lap you are driving against: off | me | wr | run (one picked off the
  // board) | pole. It is what the split deltas are measured against, and it is
  // the lap the ghost car drives if the ghost car is on - two questions, and
  // the second one is the line below.
  ghostMode: storedGhostMode(),
  ghostRun: null,          // {id, who, time_ms} while chasing somebody's lap
  // Whether that lap is *drawn* as a car. Nothing to do with which lap it is:
  // wanting the splits off a lap you do not want a translucent car driving in
  // front of you is an ordinary thing to want, and it used to be unaskable.
  showGhost: storedFlag('drive.ghostcar', true),
  // Both readouts default off: a number over the road is asked for, not given.
  showFps: storedFlag('drive.fps', false),
  showPing: storedFlag('drive.ping', false),
  // The slug the switcher is part-way through loading, or null. One at a time:
  // a second click during the (network + several hundred ms of building) that a
  // switch costs would race the first one into `loadTrack`.
  switching: null,
  board: null,             // the last board fetched, for the detail pane
  mySplits: [],            // your PB's splits, to compare somebody else's with
  watch: null,             // a replay playing instead of a run
  shot: false,             // taking a preview picture, not playing
  shotMode: '1',           // which picture: `1` (the switcher's), `plan`, `at:<f>`
  shotAt: null,            // `?shot=at:<f>`: where round the lap to park the car
  previewPhase: null,      // `?panel=qual|racing` pins a phase to look at it
  // And `?panel=racing` pins a *field* to go with it, because pinning the phase
  // alone was not enough to photograph the one thing that phase puts on screen:
  // the position card and the standings are shown when there are rivals on the
  // road, not when the phase says `racing`, so a pinned race drew neither. The
  // mobile HUD then had the minimap sitting on top of the position card in every
  // real race and looking correct in every screenshot anybody could take.
  previewOrder: null,
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
  pole: null,              // {pid,name,color,ms} of the provisional pole lap
  qualAgain: null,         // the "line up again" timer after a qualifying lap
  raceT0: null,            // local perf-clock ms of the green light
  cdT0: null,              // and what the lights on screen are counting down to
  raceDone: false,         // finished or retired: out of the race, still in the room
  catchupDemo: null,       // `?catchup=<s>` pins the gap, to look at the effect
  qualEnd: null,           // local perf-clock ms qualifying closes
  standings: [],
  order: [],               // the running order, off the last snapshot: see
                           // `orderFromSnapshot`. Derived and single-writer, so
                           // a stale one is a miss and never a disagreement.
  settings: { qualifying: false },  // rooms only: what the next race will be
                                    // (the server's `room_settings` is the
                                    // truth; this matches ROOM_DEFAULTS so the
                                    // switch does not flash the wrong way)
  lastPose: 0,
  socket: null,
  clockOffset: 0, bestRtt: Infinity,
  finishedPayload: null,
  hudTick: 0,
  bestTime: CFG.pbMs || null,
  touch: false,
};

// The one handle on the sound from outside this module, and it exists for one
// caller: the framed "Click to play" door in play.html. Everywhere else the
// audio context is built by the first keypress (`bindInput`), but inside a
// portal's iframe that click is the only user gesture we are promised, and the
// door is a classic inline script that runs long before this module does. Same
// shape as `window.DrivePending`, and deliberately just the sound - not `S`.
window.DriveSound = S.sound;

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
  if (CFG.mode === 'replay') {
    // Straight away, not when the cars arrive: the HUD is about a run of yours
    // that does not exist here, so it should never be on the screen at all.
    document.body.classList.add('watching');
    S.car.frozen = true;
    S.view.setVisible(false);
    openRaceReplay();
  }
  openRequestedLap();
  openPanelParam();
  // What the heartbeat in base.html should say about this page. A function and
  // not a value, because this is the one page that changes what it is without
  // navigating anywhere: the switcher swaps the world in place, and a track
  // name captured at boot would be the track you arrived on for the rest of
  // the session. Only the slug leaves the browser - the server looks the name
  // up, so nothing typed here can reach a public profile.
  window.driveWhere = () => ({
    where: CFG.mode === 'replay' ? 'replay' : (CFG.mode === 'room' ? 'room' : 'solo'),
    track: S.track.slug,
  });
  // The world is built and the first frame is about to be drawn: this is the
  // moment the player could press W, which is exactly what a portal means by
  // gameplay starting. It is measured from the start of loading, so it must not
  // be announced any earlier - a `gameplayStart` at the top of `init` would
  // report a download time with the track build left out of it.
  //
  // `syncPaused` says it again on every panel toggle and the call is idempotent,
  // so this is the first word rather than the only one. It is here and not in
  // `syncPaused` because arriving with a panel open (`?panel=`, or the room
  // drawer, which opens itself) would otherwise mean the game never reported
  // starting at all.
  if (window.DrivePortal && !S.menuOpen && !S.helpOpen) {
    window.DrivePortal.gameplayStart();
  }
  requestAnimationFrame(frame);
}

/**
 * `?panel=settings|help|tracks|board|finish|qual|racing` opens a panel on load.
 *
 * There is no browser in CI and a screenshot cannot click, so this is the only
 * way to look at a panel's layout without a person driving the mouse - the same
 * reason `?touch=1` exists.
 *
 * `qcount`, `qual`, `racing` and `result` are the odd ones out: none of them is
 * a panel you can open, they appear because the room said so, and getting a
 * room into any of them needs two browsers, a stopwatch and somebody willing to
 * lose a race. So they pin the phase and fake a session, which is enough to
 * look at - and looking at it is the whole point here. Pinned rather than
 * assigned, because the room reports "free practice" the moment the socket
 * connects and a phase merely set here would be gone before the shutter.
 */
async function openPanelParam() {
  const q = new URLSearchParams(location.search);
  const p = q.get('panel');
  if (p === 'settings') toggleMenu(true);
  else if (p === 'help') toggleHelp(true);
  else if (p === 'tracks') toggleTracks(true);
  else if (p === 'finish' && CFG.mode !== 'room') {
    // The solo finish sheet, which otherwise costs a clean lap to look at - and
    // a *good* one, since the interesting version of this layout is the one with
    // a medal, a rank and a record on it. `share` is set because the Share
    // button spends nearly all its life armed, and an unarmed one is the state
    // that needs no checking.
    showResults({ time: 71234, medal: 'gold', rank: 3, pb: 71234, pbRank: 3,
                  wr: 68950, share: 1 });
  }
  else if (p === 'result' && CFG.mode === 'room') {
    // The sheet at the end of a race, which otherwise takes a race to look at.
    S.isHost = true;
    showSide(false);
    onRaceResult({
      standings: [
        { pid: 'a', name: 'Chinmay', color: '#e8453c', ms: 41208 },
        { pid: CFG.me ? CFG.me.pid : 'b', name: 'You', color: '#ffd96b', ms: 42980 },
        { pid: 'c', name: 'Someone else', color: '#55e08a', ms: 44117 },
        { pid: 'd', name: 'Gave up', color: '#8fd6ff', ms: null }],
      elo: CFG.me ? { [CFG.me.pid]: { before: 1000, after: 1012, delta: 12 } } : {},
      points: {
        a: { got: 4, total: 11 },
        [CFG.me ? CFG.me.pid : 'b']: { got: 3, total: 7 },
        c: { got: 2, total: 9 },
        d: { got: 0, total: 2 },
      },
      why: 'all in', race: 1,
    });
  } else if ((p === 'qual' || p === 'racing' || p === 'qcount') && CFG.mode === 'room') {
    S.previewPhase = p === 'qual' ? 'qualifying'
                   : (p === 'qcount' ? 'qual_countdown' : 'racing');
    S.isHost = true;
    // A session closes the room drawer on the way in, so a preview of one has
    // to as well or it photographs a screen that never happens.
    showSide(false);
    applyPhase();
    // A race with nobody in it puts nothing on screen, so the pinned one gets a
    // field - the same trick `qual` uses one line down. Six cars, because the
    // question a phone layout asks of this card is how wide the numbers get.
    if (p === 'racing') S.previewOrder = [
      { name: 'Chinmay', color: '#e8453c', s: 980, self: false, pid: 'a', ms: null },
      { name: 'Someone else', color: '#55e08a', s: 902, self: false, pid: 'c', ms: null },
      { name: CFG.name, color: myColor(), s: 861, self: true, ms: null },
      { name: 'Fourth', color: '#8fd6ff', s: 774, self: false, pid: 'd', ms: null },
      { name: 'Fifth', color: '#bb6bd9', s: 640, self: false, pid: 'e', ms: null },
      { name: 'Sixth', color: '#f2994a', s: 512, self: false, pid: 'f', ms: null },
    ];
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
  useGhost(d.ghost, d.hz || GHOST_RATE, d.color, d.livery);
  S.ghostRun = { id: d.id, who: d.who, time_ms: d.time_ms };
  setGhostMode('run', { quiet: true });
  toast('Chasing ' + d.who + '  ' + fmt(d.time_ms));
}

function loadTrack(track, opts = {}) {
  // Driving away mid-run: report it while `S.track` and `S.run` are still the ones
  // it happened on, because a few lines down `S.run` is replaced wholesale and the
  // time and distance go with it. Only on a *switch* - arriving is not abandoning.
  if (opts.switched) reportActivity('switched track');
  S.track = track;
  if (S.view) S.view.dispose();
  if (S.ghostView) { S.ghostView.dispose(); S.ghostView = null; S.ghostViewColor = null; }
  for (const r of S.remotes.values()) dropRemote(r);
  S.remotes.clear();

  S.built = buildTrack(track, T);
  S.renderer.setTrack(S.built);
  S.course = new Course(S.built);
  S.run = new Run(S.course, track);
  // A lap id belongs to the track it was set on - `?watch=` is scoped to the
  // track at the server, so a stale one survives the switch only to fail.
  S.shareId = null;
  S.car = new Car(T, S.built);
  S.car.id = CFG.me ? CFG.me.pid : 'me';
  // The car you built, from the garage. A room's seat carries its own copy so
  // that walking into one does not have to wait for a request, and everywhere
  // else it comes down with the page. The colour behind it is the fallback for
  // a guest, who has no garage row and drives whatever their name hashes to.
  S.view = new CarView(S.renderer.scene, myLivery());
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
  S.ghost = null; S.ghostTimes = null; S.ghostColor = null; S.sessionBest = null;
  S.qualBest = null; S.qualRef = null; S.raceSplits = {};
  // Pole belongs to a session on the track it was set on, so it does not follow
  // the room somewhere else.
  S.pole = null;
  S.ghostRun = null;
  S.mySplits = (CFG.pbSplits && CFG.pbSplits[track.slug]) || [];
  // **Arriving somewhere new means no ghost car.** A track you have just
  // switched to is one you are looking at rather than attacking, and a car you
  // have never driven against appearing on your first lap of it is in the way.
  // **Switching track no longer hides the ghost car.** It used to, on the
  // reasoning that somewhere new is somewhere you are looking at rather than
  // attacking - which is a fair thing to want and the wrong way to get it. The
  // car is a setting now, with its own key (G) and its own remembered value, and
  // a setting that turns itself off when you go somewhere is not a setting. It
  // was also invisible: the stored preference still said *on*, so the switch in
  // the sheet disagreed with the road, which is the same disagreement the PB bug
  // caused at the other end.
  //
  // A lap chased off the board does not survive the trip, though: `run` names a
  // specific lap on a specific track, so it cannot mean anything here.
  if (S.ghostMode === 'run') S.ghostMode = 'me';
  setGhostMode(S.ghostMode, { quiet: true });
  applyPhase();
  markActiveTrack();
}

function wireCarEvents() {
  const car = S.car;
  car.onBump = (mag) => {
    S.sound.bump(mag);
    // Harder than it was (`mag / 18`), because contact is now something that
    // moves you - see BUMP_SLIP_GRIP in tuning.py - and a shove you can feel in
    // the steering with a camera that barely notices reads as a fault.
    S.renderer.kick(Math.min(1.4, mag / 12));
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
  car.onBoostPad = () => {
    S.sound.boostPad();
    // A small kick, well under a wall or a hard landing. The pad is a good
    // thing happening to you, and a camera that lurches for it reads as an
    // impact - the FOV punch and the air round the car carry the rest.
    S.renderer.kick(0.35);
  };
  car.onLand = (airTime) => {
    S.sound.land(airTime);
    if (airTime > 0.5) S.renderer.kick(Math.min(0.8, airTime * 0.5));
  };
  car.onFall = () => { S.sound.fall(); toast('Off the track'); };
  car.onRespawned = () => S.sound.respawn();
  // The tow pays out on its own, with no button pressed, so it has to announce
  // itself - and it does that in the world rather than in words: the air round
  // the car goes amber and flat out (see Draft in render.js), the camera takes
  // a punch, and there is a whoosh. A toast said "Slipstream!" over the top of
  // all three, in the middle of the one moment you are looking at the road.
  car.onSlipstream = () => {
    S.sound.slipstream();
    S.renderer.kick(0.35);
  };
}

function resetToStart() {
  // Any reset cancels the automatic one queued after a qualifying lap. That was
  // "line up again in a moment", and this *is* lining up again - leaving it
  // armed threw away the lap you had already started: finish, press R, drive,
  // and a second later the session restarted you for no visible reason.
  if (S.qualAgain) { clearTimeout(S.qualAgain); S.qualAgain = null; }
  // **Before `reset()`**, which zeroes the time and distance being reported. This
  // is the common abandon: R, or the automatic line-up after a qualifying lap.
  // `T` is deliberately not here - the clock keeps running, so it is still the
  // same run and reporting it would count it twice.
  reportActivity('restart');
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
// Everything you hold rather than press: five actions for the car, and two for
// the camera. Q and F are in here rather than beside R and T because a held key
// has to be *let go of*, and this is the set that already knows how: it is
// emptied on blur and on opening the chat box, which is the difference between
// looking behind you and driving the rest of the lap backwards because the
// keyup went to a message. `readInput` reads the five it wants by name, so the
// physics never sees these two.
const KEYMAP = {
  ArrowUp: 'up', KeyW: 'up',
  ArrowDown: 'down', KeyS: 'down',
  ArrowLeft: 'left', KeyA: 'left',
  ArrowRight: 'right', KeyD: 'right',
  Space: 'drift', ShiftLeft: 'drift',
  KeyQ: 'rear', KeyF: 'first',
};

function bindInput() {
  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    S.sound.start(); S.sound.resume();
    const k = KEYMAP[e.code];
    if (k) { keys.add(k); e.preventDefault(); }
    // R starts the whole run again; T only puts you back on the road at the last
    // checkpoint and leaves the clock running, which is the difference between
    // "that lap is gone" and "I just fell off". Both do nothing until you have
    // actually set off - see restartRun.
    if (e.code === 'KeyR') restartRun();
    // T and only T. Enter and Backspace used to do this as well, and Enter is
    // worth more as the host's key than as a third way to press T: starting the
    // session is the one thing a room waits on, and it was a button in the top
    // corner and nothing else.
    if (e.code === 'KeyT') { e.preventDefault(); backToCheckpoint(); }
    if (e.code === 'Enter') { e.preventDefault(); hostStart(); }
    if (e.code === 'Escape') onEscape();
    if (e.code === 'KeyH') toggleHelp();
    // The track switcher, from the road. Changing track is the most common
    // thing there is to do that is not driving, and reaching for it should not
    // mean finding a small icon in the corner first.
    if (e.code === 'KeyP') toggleTracks();
    // The board, from the road, and solo only for the same reason the button is:
    // in a room the people whose times you would be reading are on the track
    // with you. Pressing it again closes it, like every other panel key.
    if (e.code === 'KeyL' && CFG.mode !== 'room') {
      if ($('boardOv').style.display === 'none') openBoard(); else toggleBoard(false);
    }
    // M is the one key that means two things, and it is the right two. Alone
    // there is nobody to talk to and the sound is worth a key; in a room the
    // chat is the thing you want without taking a hand off the wheel to find,
    // and muting is still in settings with every other preference.
    // preventDefault or the keypress that opened the box types an "m" into it.
    if (e.code === 'KeyM') {
      if (CFG.mode === 'room') { e.preventDefault(); openChat(); }
      else setSound(!S.sound.enabled);
    }
    // **K is which lap, G is whether it is drawn.** Two switches, two keys, and
    // the split is the whole point: they used to share G, which stepped through
    // the laps, and the car could only be turned off from the settings sheet.
    //
    // K rather than P because P has always changed track, which is the more
    // common thing to do and the harder muscle memory to move. K has no
    // mnemonic - every letter with a claim on "splits" or "lap" is either a
    // driving key or already spoken for.
    //
    // It steps through the laps there are to drive against rather than toggling
    // the last one back on: picking between your own lap and the record is the
    // choice worth having on a key. A lap chased off the board is not in the
    // cycle - it is not a mode you can arrive at by pressing a key, so pressing
    // one leaves it.
    if (e.code === 'KeyK') setGhostMode(nextGhostMode());
    // G is the car. A toggle rather than a cycle, because there are two states
    // and landing on the one you wanted should not depend on where you started.
    if (e.code === 'KeyG') setGhostCar(!S.showGhost);
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

  // The tab going away is the most common way a run ends, and the one that used to
  // be worth nothing.
  //
  // **`pagehide` only, and neither `visibilitychange` nor `blur`.** This looks
  // over-cautious and is not: reporting a run banks its time, but a *finished* lap
  // is banked again by `/api/run`, which sends the whole lap and knows nothing about
  // a partial report. So anything that fires on a run that might still be running
  // double-counts it. `visibilitychange` fires on an ordinary alt-tab and `blur` on
  // clicking another window, both of which people do mid-lap and come back from.
  // `pagehide` means the document is actually being torn down.
  window.addEventListener('pagehide', () => reportActivity('page hidden', { beacon: true }));
  // Except when it is not: a page restored from the back/forward cache fires
  // `pageshow` with the same `Run` object, already banked. Continuing it would let
  // the finish bank it a second time, so the run is over - which is honest, since
  // you left.
  window.addEventListener('pageshow', () => {
    if (S.started && S.run && S.run.counted) resetToStart();
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
  //
  // `?shot=1` is the switcher's picture and its framing must not drift -
  // `tools/shoot_tracks.py` takes all fifteen with it and nothing downstream can
  // tell a re-framed preview from a stale one. The other two are for authoring,
  // where the question is not "does this look like somewhere" but "is this
  // right", and they are read by `tools/track_views.py`:
  //
  //   ?shot=plan        straight down, whole track in frame, north up. What
  //                     catches a leg that left the building, a hairpin that
  //                     bulged into the next aisle, a lap that is really two.
  //   ?shot=at:<0..1>   the car parked on the road that far round the lap, with
  //                     the ordinary chase camera behind it. Deliberately the
  //                     real camera and not a copy of it: on Costco the whole
  //                     question is whether the lens clears a 15-unit ceiling
  //                     and follows the car through a doorway 11.6 units later,
  //                     and a bespoke authoring camera would answer about
  //                     itself instead.
  const sh = /[?&]shot=([A-Za-z0-9.:]+)/.exec(location.search);
  if (sh) {
    S.shot = true;
    S.shotMode = sh[1];
    S.car.frozen = true;
    document.body.classList.add('shot');
    const at = /^at:([0-9.]+)$/.exec(S.shotMode);
    if (at) {
      // The car stays visible here, and that is the point of this mode: it is
      // the only thing in frame with a known size, so it is what tells you
      // whether the road is as wide as it should be and whether the roof is as
      // low as it feels.
      S.shotAt = Math.max(0, Math.min(1, parseFloat(at[1])));
    } else {
      S.view.setVisible(false);
    }
  }
  // Read off `location.search` directly, like `shot=1` above and unlike the
  // panel params: this line is inside the slice `test_touch.py` lifts into a
  // stub DOM, which has a `location` and no `URLSearchParams`.
  const dm = /[?&]draft=(charge|boost)\b/.exec(location.search);
  S.draftDemo = dm ? dm[1] : null;
  // `?catchup=<seconds>` pins the gap to the leader, for the same reason: the
  // only thing catching up looks like is the speed bar, and photographing it
  // otherwise takes two browsers and somebody driving five seconds up the road.
  const cu = /[?&]catchup=([0-9.]+)\b/.exec(location.search);
  S.catchupDemo = cu ? parseFloat(cu[1]) : null;
  // Asked and answered in base.html's head, because the framed door needs the
  // same answer before this module exists. Two computations of it could drift;
  // one of them being in a template and the other here is exactly the kind of
  // drift nothing notices until a phone is holding it.
  if (window.DRIVE_TOUCH) {
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
  // Wrapped rather than passed by name, like every other line here: this
  // function is lifted whole into QuickJS by `test_touch.py`, where `shareLap`
  // is outside the slice - so naming it binds a reference that does not resolve,
  // while calling it from an arrow is only ever reached by a real click.
  if ($('btnShare')) $('btnShare').onclick = () => shareLap();
  $('btnSound').onclick = () => setSound(!S.sound.enabled);
  $('btnMusic').onclick = () => {
    setMusic(!S.sound.musicOn);
    // Pressing this is a user gesture, so it is allowed to be the thing that
    // builds the audio context - and it has to come after the flag is set,
    // since `start` declines to build one when there is nothing to hear.
    S.sound.start(); S.sound.resume();
  };
  // Quietly, both of them: the settings sheet is not open yet, so a toast
  // saying what the stored preference was would be an announcement of nothing
  // having happened.
  setSound(storedFlag('drive.sound', true), { remember: false });
  // Sound defaults on and music defaults off: the engine is what the game
  // sounds like, and a loop over the top of it is something you ask for.
  setMusic(storedFlag('drive.music', false), { remember: false });

  // Which lap you drive against, whether it is drawn as a car, the track
  // switcher and the in-game board.
  $('ghostOpts').querySelectorAll('[data-ghost]').forEach(b => {
    b.onclick = () => chooseGhost(b.dataset.ghost);
  });
  $('btnGhost').onclick = () => setGhostCar(!S.showGhost);
  setGhostCar(S.showGhost, { quiet: true, remember: false });
  // The two readouts, wired like the two audio switches above them.
  $('btnFps').onclick = () => setFpsOn(!S.showFps);
  $('btnPing').onclick = () => setPingOn(!S.showPing);
  setFpsOn(S.showFps, { remember: false });
  setPingOn(S.showPing, { remember: false });

  $('btnTracks').onclick = () => toggleTracks();
  $('btnTracksClose').onclick = () => toggleTracks(false);
  // Solo only - in a room this slot is the room button, and everybody in there
  // is on the road with you rather than on a board.
  if ($('btnBoard')) $('btnBoard').onclick = () => openBoard();
  $('btnBoardClose').onclick = () => toggleBoard(false);
  $('btnWatchStop').onclick = () => stopWatching();
  renderTrackCards();          // loadTrack has already set the ghost up
  // Everything room-shaped lives behind the hamburger, at every screen size.
  if ($('side')) {
    $('btnRoom').onclick = () => showSide(!document.body.classList.contains('side-open'));
    $('btnRoomClose').onclick = () => showSide(false);
    const qual = $('optQual');
    qual.onclick = () => {
      if (!S.isHost || !S.socket) return;
      S.socket.emit('set_setting', { code: CFG.room, key: 'qualifying',
                                     value: !S.settings.qualifying });
    };
    // Escape gets you out of the message box and back to the car. It never
    // reaches the window handler - that one ignores anything typed into an
    // input, which is what keeps WASD from driving while you write - so the
    // way out has to be bound here.
    $('chatInput').addEventListener('keydown', (e) => {
      if (e.code === 'Escape') { e.preventDefault(); closeChat(); }
    });
    renderSettings();
    showSide(true);           // you arrive in a lobby, so start with it open
  }
}

function showSide(on) {
  document.body.classList.toggle('side-open', on);
  $('btnRoom').classList.toggle('on', on);
  if (!on) closeChat();
}

/**
 * M: the cursor in the message box, without leaving the road.
 *
 * Anything held goes with it. The keyup for a key you were holding when you
 * started typing is delivered to the input and swallowed, so without this the
 * car would drive itself into the barrier at full throttle for as long as the
 * sentence took - and the window handler ignores keystrokes aimed at an input,
 * which is exactly what stops WASD steering while you write.
 */
function openChat() {
  const inp = $('chatInput');
  if (!inp) return;
  showSide(true);
  keys.clear();
  inp.focus();
}

function closeChat() {
  const inp = $('chatInput');
  if (inp) inp.blur();
}

/**
 * The room's race settings, as the server last described them.
 *
 * One switch so far. It is drawn for everybody and pressable only by the host,
 * rather than being the host's panel: what the next race will be is something
 * you are about to drive, so it cannot be a rule only one person can read.
 * Locked while a session is live for the same reason the track is - the server
 * refuses it there anyway, and a switch that moved under your finger without
 * changing anything would be worse than one that does not move.
 */
function renderSettings() {
  const b = $('optQual');
  if (!b) return;
  const on = !!S.settings.qualifying;
  b.classList.toggle('on', on);
  b.setAttribute('aria-checked', on ? 'true' : 'false');
  b.disabled = !S.isHost || livePhase();
  $('qualNote').textContent = on
    ? 'Ninety seconds of practice first - your fastest lap sets the grid.'
    : 'No qualifying: the grid is the last race, reversed.';
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

const GHOST_LABEL = { off: 'Off', me: 'My Best', wr: 'World Record',
                      pole: 'Provisional Pole', run: 'Chasing' };

// What G steps through, and it is not the same list in the two places. `run` is
// deliberately in neither - it is not a mode you can arrive at by pressing a
// key, so pressing one leaves it (see the key handler).
//
// In a room the lap worth chasing is the one that is about to take pole, and
// picking somebody off the leaderboard is not: everybody in the room is on the
// road with you and the board is a list of people who are not.
const GHOST_CYCLE = ['off', 'me', 'wr'];
const GHOST_CYCLE_ROOM = ['off', 'me', 'pole', 'wr'];

function nextGhostMode() {
  const cycle = CFG.mode === 'room' ? GHOST_CYCLE_ROOM : GHOST_CYCLE;
  const i = cycle.indexOf(S.ghostMode);
  return cycle[(i + 1) % cycle.length];
}

function chooseGhost(mode) {
  if (mode === 'others') { openBoard(); return; }
  setGhostMode(mode);
}

function setGhostMode(mode, opts = {}) {
  S.ghostMode = mode;
  if (mode !== 'run') S.ghostRun = null;
  // `remember: false` is for a mode the game chose rather than you - arriving
  // on a new track turns the ghost off, and that must not overwrite the ghost
  // you actually picked.
  // `run` is deliberately **not** written. It is a lap you opened off the board,
  // not one of the standing choices, and `storedGhostMode` cannot restore it - so
  // it used to be filed as `me`, which meant chasing one lap from the leaderboard
  // quietly and permanently rewrote a `wr` preference to `me`. Your setting is
  // what you chose, and only you choose it.
  if (opts.remember !== false && mode !== 'run') {
    try { localStorage.setItem('drive.ghost', mode); } catch (e) {}
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
  else if (mode === 'pole') loadPoleGhost();
  showGhostNow();
  if (!opts.quiet) toast('Splits: ' + ghostDescription());
}

/**
 * The ghost car, which is a different switch from which lap it is.
 *
 * It used to be the same one - picking a lap turned the car on and "Off"
 * turned both off together - so the only way to stop a translucent car
 * driving the line in front of you was to give up the split deltas as well,
 * and they are the half of a reference lap you read at racing speed.
 */
function setGhostCar(on, opts = {}) {
  S.showGhost = on;
  // `remember: false` is for a state the game chose rather than you - arriving
  // somewhere new hides the car without forgetting that you drive with one.
  if (opts.remember !== false) rememberFlag('drive.ghostcar', on);
  const b = $('btnGhost');
  if (b) {
    b.classList.toggle('on', on);
    $('btnGhostState').textContent = on ? 'On' : 'Off';
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  // Same shape as the splits toast ("Splits: World Record") so the two switches
  // read as a pair, and Title Case because every label on these sheets is.
  if (!opts.quiet) toast('Ghost Car: ' + (on ? 'On' : 'Off'));
}

function ghostDescription() {
  if (S.ghostMode === 'run' && S.ghostRun) {
    return S.ghostRun.who + '  ' + fmt(S.ghostRun.time_ms);
  }
  if (S.ghostMode === 'me' && CFG.mode === 'room') return 'your best lap here';
  if (S.ghostMode === 'pole' && S.pole) {
    return S.pole.name + '  ' + fmt(S.pole.ms);
  }
  return GHOST_LABEL[S.ghostMode] || 'Off';
}

/** The one line under the ghost buttons that says what is actually loaded. */
function showGhostNow() {
  const el = $('ghostNow');
  if (!el) return;
  if (S.ghostMode === 'off') { el.textContent = 'No lap to drive against.'; return; }
  if (S.ghostMode === 'run' && S.ghostRun) {
    el.innerHTML = 'Chasing <b>' + esc(S.ghostRun.who) + '</b> &middot; ' +
                   fmt(S.ghostRun.time_ms);
    return;
  }
  if (S.ghostMode === 'me') {
    el.textContent = CFG.mode === 'room'
      ? 'Your best lap of this practice session.'
      : (S.bestTime ? 'Your personal best, ' + fmt(S.bestTime) + '.'
                    : 'Drive a lap and it becomes the one to beat.');
    return;
  }
  if (S.ghostMode === 'pole') {
    // Three different facts, and only the last one is a shrug: somebody is on
    // pole and you have their lap, somebody is on pole and it is you, or the
    // session has not had a lap in it yet.
    if (S.pole && S.ghost) {
      el.innerHTML = 'The lap on provisional pole &middot; <b>' +
                     esc(S.pole.name) + '</b> ' + fmt(S.pole.ms);
    } else if (S.pole) {
      el.textContent = 'Provisional pole is yours - nobody to chase yet.';
    } else {
      el.textContent = 'Nobody has set a qualifying lap yet.';
    }
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
 * In a room it belongs to the two phases you drive alone in - free practice and
 * qualifying - and to neither of the others. A race is against the cars that
 * are actually there, and a translucent extra one drifting through the pack on
 * a line nobody drove is just something else to mistake for a rival, so the
 * ghost is off for the whole race no matter what the setting says.
 *
 * Qualifying is the opposite case and used to be lumped in with the race. It is
 * the session where you are alone against a clock, which is exactly what a
 * ghost is for - and the lap on provisional pole is only a ghost you can chase
 * if it is on the road while there is still time to beat it.
 */
function ghostOn() {
  if (!S.showGhost || !S.ghost) return false;
  if (CFG.mode !== 'room') return true;
  return !S.raceMode && (S.racePhase === 'free' || S.racePhase === 'qualifying');
}

/**
 * Fetch the lap currently on provisional pole.
 *
 * Who is on pole is pushed to the whole room the moment it changes, because it
 * is one line; the lap itself is tens of kilobytes and most of the room is not
 * chasing it, so it is asked for by the people who are.
 */
function loadPoleGhost() {
  S.ghost = null; S.ghostTimes = null;
  if (CFG.mode !== 'room' || !S.socket || !S.pole) return;
  // Chasing yourself is not chasing anybody. Your own best lap of the session
  // is already what `me` means here, and it is the same lap.
  if (CFG.me && S.pole.pid === CFG.me.pid) return;
  S.socket.emit('qual_pole_req', {});
}

/**
 * The two audio switches, which are two switches.
 *
 * Sound is the car and the world; music is the loop under it. They are
 * separate buses inside `Sound`, so one of them off leaves the other alone -
 * driving to your own music with the game muted, or with the engine and
 * nothing over the top of it, are both ordinary ways to play.
 *
 * Both are remembered. A preference you have to set again on every page is one
 * you stop setting, and muting a game is not a per-visit decision.
 */
function setSound(on, opts = {}) {
  S.sound.mute(!on);
  if (opts.remember !== false) rememberFlag('drive.sound', on);
  $('btnSoundState').textContent = on ? 'On' : 'Off';
  $('btnSound').classList.toggle('on', on);
  $('btnSound').setAttribute('aria-pressed', on ? 'true' : 'false');
}

function setMusic(on, opts = {}) {
  S.sound.setMusic(on);
  if (opts.remember !== false) rememberFlag('drive.music', on);
  $('btnMusicState').textContent = on ? 'On' : 'Off';
  $('btnMusic').classList.toggle('on', on);
  $('btnMusic').setAttribute('aria-pressed', on ? 'true' : 'false');
}

// ---------------------------------------------------------------------------
// Frame rate and ping
//
// Two readouts and two switches, because they answer two questions and only one
// of them is about the network. Both off unless asked for: a number over the road
// is something you go looking for, not something everybody should be given.
//
// The card is in the top-left column *above* the position card, which is the one
// placement nothing can push around - the position card appears when there are
// rivals on the road, so a readout under it would move at the green light.
// ---------------------------------------------------------------------------

/** Frames are counted over a window rather than taken from one gap.
 *
 *  `1 / dt` off a single frame is a number that flickers through a range of
 *  twenty even on a machine holding a steady rate, because it reports the jitter
 *  between two particular frames. Averaging over half a second reports what you
 *  would call the frame rate. */
const FPS_WINDOW_MS = 500;
let fpsFrames = 0;
let fpsSince = 0;

function fpsTick(now) {
  fpsFrames++;
  if (!fpsSince) { fpsSince = now; return; }
  const span = now - fpsSince;
  if (span < FPS_WINDOW_MS) return;
  const fps = Math.round(fpsFrames * 1000 / span);
  fpsFrames = 0;
  fpsSince = now;
  if (!S.showFps) return;
  // Amber under the 60 the car is stepped at twice over, red under 30 - the two
  // points where what you are seeing stops being what the physics is doing.
  setMeter('fps', fps, fps < 30 ? 'bad' : (fps < 55 ? 'warn' : ''));
}

/** How often the round trip is measured. Two seconds is often enough to watch a
 *  connection go bad and rare enough to be nothing: it is one request that does
 *  no work, and it only runs at all while the readout is switched on. */
const PING_EVERY_MS = 2000;
let pingTimer = null;

async function pingOnce() {
  const t0 = performance.now();
  try {
    // `cache: 'no-store'` matters more than it looks: a cached response is
    // answered by the browser in under a millisecond and the readout would
    // proudly report a 0ms connection to a server that is not there.
    const r = await fetch('/api/ping', { cache: 'no-store' });
    if (!r.ok) throw new Error('bad status');
  } catch (e) {
    setMeter('ping', null, 'bad');       // offline, or the server is gone
    return;
  }
  const ms = Math.round(performance.now() - t0);
  setMeter('ping', ms, ms > 250 ? 'bad' : (ms > 120 ? 'warn' : ''));
}

function startPinging() {
  if (pingTimer) return;
  pingOnce();
  pingTimer = setInterval(pingOnce, PING_EVERY_MS);
}

function stopPinging() {
  if (pingTimer) clearInterval(pingTimer);
  pingTimer = null;
}

/** One row of the card. `null` reads as `--`, which is what an unknown looks
 *  like - and it occupies the same width as a number, so nothing shifts. */
function setMeter(which, value, cls) {
  const el = $(which === 'fps' ? 'fpsVal' : 'pingVal');
  if (!el) return;
  el.textContent = value == null ? '--' : String(value);
  el.className = cls || '';
}

/** Whether the card is there at all, and which rows are in it.
 *
 *  The rows are hidden individually, so with one switch on it takes the top slot
 *  rather than leaving a gap where the other would have been. */
function syncMeters() {
  const card = $('meters');
  if (!card) return;
  $('meterFps').style.display = S.showFps ? '' : 'none';
  $('meterPing').style.display = S.showPing ? '' : 'none';
  card.style.display = (S.showFps || S.showPing) ? '' : 'none';
}

function setFpsOn(on, opts = {}) {
  S.showFps = on;
  if (opts.remember !== false) rememberFlag('drive.fps', on);
  $('btnFpsState').textContent = on ? 'On' : 'Off';
  $('btnFps').classList.toggle('on', on);
  $('btnFps').setAttribute('aria-pressed', on ? 'true' : 'false');
  if (!on) setMeter('fps', null, '');
  syncMeters();
}

function setPingOn(on, opts = {}) {
  S.showPing = on;
  if (opts.remember !== false) rememberFlag('drive.ping', on);
  $('btnPingState').textContent = on ? 'On' : 'Off';
  $('btnPing').classList.toggle('on', on);
  $('btnPing').setAttribute('aria-pressed', on ? 'true' : 'false');
  // Nothing is polled while nobody is reading it.
  if (on) startPinging(); else { stopPinging(); setMeter('ping', null, ''); }
  syncMeters();
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
  // A portal wants to know when the player is actually playing rather than
  // reading a sheet, and this is already the one place that question is
  // answered - deriving it a second time is how the two would come to disagree.
  // `anyOpen` and not `S.paused`: a panel open during a race does not pause the
  // game, but the player is still looking at a menu rather than at the road.
  // `DrivePortal` is a no-op everywhere except inside a portal's frame.
  if (window.DrivePortal) {
    if (anyOpen) window.DrivePortal.gameplayStop();
    else window.DrivePortal.gameplayStart();
  }
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
  useGhost(d.ghost, d.hz || GHOST_RATE, d.color, d.livery);
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

/**
 * One lap, watched: a replay of a single car.
 *
 * **The livery goes through, not just the colour.** It is somebody else's lap,
 * and `/api/ghost` answers with their whole car - so dropping it here put their
 * body colour on a car with stock wheels, no stripe and a matte finish, which is
 * nobody's car. The ghost you *chase* off the same endpoint never had this
 * problem, so the two ways of looking at one lap disagreed about whose car it
 * was.
 */
function startWatching(frames, hz, meta) {
  startReplay([{ frames, hz, name: meta.who || 'Replay', color: meta.color,
                 livery: meta.livery }]);
}

/**
 * Play these cars back together.
 *
 * One car is a lap off the leaderboard; several are a whole race, and they run
 * on one clock because that is what they were recorded on - frame *n* of every
 * car in a race is the same instant, so watching from inside the pack shows
 * the pack. The camera belongs to one of them at a time and you can move it,
 * which is the only thing "from all perspectives" needs to mean.
 */
function startReplay(cars, opts = {}) {
  stopWatching();
  const built = cars.filter(c => c.frames && c.frames.length > 1).map(c => {
    const color = c.color || '#ffd96b';
    // The livery is on the stored race, so a replay shows the cars as they were
    // that afternoon. A race recorded before the garage has none and falls back
    // to its colour, which is exactly the car it was driven in.
    const view = new CarView(S.renderer.scene, c.livery || color);
    view.setLabel(c.name || 'Driver', view.plateColor);
    return { g: new Ghost(c.frames, c.hz || GHOST_RATE), view, prev: null,
             name: c.name || 'Driver', color, ms: c.ms };
  });
  if (!built.length) { toast('That replay is empty'); return; }
  S.watch = {
    cars: built, at: 0, t: 0,
    dur: Math.max(...built.map(c => c.g.duration)),
    subject: { pos: new THREE.Vector3(), fwd: new THREE.Vector3(0, 0, -1),
               up: new THREE.Vector3(0, 1, 0), speed: 0, grounded: true },
    title: opts.title || null,
  };
  S.car.frozen = true;
  S.view.setVisible(false);
  document.body.classList.add('watching');
  renderWatchBar();
  $('watchBar').style.display = '';
}

/** Whose eyes you are watching through, and the buttons to change them. */
function renderWatchBar() {
  const w = S.watch;
  if (!w) return;
  const me = w.cars[w.at];
  $('watchWho').textContent = (w.title ? w.title + ' - ' : 'Watching ') + me.name;
  const bar = $('watchCars');
  if (!bar) return;
  // One car is not a choice of camera, so it is not offered as one.
  bar.style.display = w.cars.length > 1 ? '' : 'none';
  if (w.cars.length < 2) { bar.innerHTML = ''; return; }
  bar.innerHTML = w.cars.map((c, i) => `
    <button class="wcar${i === w.at ? ' on' : ''}" data-cam="${i}">
      <span class="st-dot" style="background:${esc(c.color)}"></span>
      <span>${esc(c.name)}</span>
      <i>${c.ms != null ? fmt(c.ms) : 'DNF'}</i>
    </button>`).join('');
  bar.querySelectorAll('[data-cam]').forEach(b => {
    b.onclick = () => watchFrom(parseInt(b.dataset.cam, 10));
  });
}

/** Move the camera to another car, without moving the clock. */
function watchFrom(i) {
  const w = S.watch;
  if (!w || !w.cars[i]) return;
  w.at = i;
  w.cars[i].prev = null;      // its speed is measured between frames, so restart it
  renderWatchBar();
}

function stopWatching() {
  if (!S.watch) return;
  for (const c of S.watch.cars) c.view.dispose();
  S.watch = null;
  S.car.frozen = false;
  S.view.setVisible(true);
  document.body.classList.remove('watching');
  $('watchBar').style.display = 'none';
  // On the replay page there is no run to go back to - the whole page is the
  // replay - so leaving it is leaving the page. Back to the room if the watcher
  // is still in one, which after watching a race from a room they are: leaving
  // for a replay is a soft disconnect and the seat outlives it (`_seated_room`).
  // If the room went while they watched, `/room/<code>` sends them on to the
  // lobby list by itself, so this needs no second opinion about whether it is
  // still there - which is just as well, since it would be out of date by the
  // time the page loaded anyway.
  if (CFG.mode === 'replay') {
    location.href = CFG.backRoom ? '/room/' + CFG.backRoom : '/lobbies';
    return;
  }
  resetToStart();
}

/** Advance the replay and point the camera at whoever it is following. */
function updateWatch(dt) {
  const w = S.watch;
  w.t += dt;
  if (w.t > w.dur) { w.t = 0; for (const c of w.cars) c.prev = null; }
  for (let i = 0; i < w.cars.length; i++) {
    const c = w.cars[i];
    const f = c.g.at(w.t);
    if (!f) { c.view.group.visible = false; continue; }
    const p = new THREE.Vector3(f[0], f[1], f[2]);
    const q = new THREE.Quaternion(f[3], f[4], f[5], f[6]).normalize();
    c.view.update(p, q, lampsOf(f[7]));
    c.view.group.visible = true;
    if (i === w.at) {
      const s = w.subject;
      // The camera wants a speed and a frame to orbit in, which a replay does
      // not carry - so both are read back off the motion itself.
      s.speed = c.prev ? p.distanceTo(c.prev) / Math.max(1e-3, dt) : 0;
      s.pos.copy(p);
      s.fwd.set(0, 0, -1).applyQuaternion(q);
      s.up.set(0, 1, 0).applyQuaternion(q);
    }
    c.prev = p.clone();
  }
  $('watchClock').textContent = fmt(w.t * 1000);
}

/**
 * The replay page: a whole race, from any car in it.
 *
 * The cars are fetched rather than rendered into the page because eight
 * replays of a two-minute race is most of a megabyte of numbers.
 */
async function openRaceReplay() {
  const id = CFG.race;
  if (!id) return;
  let d = null;
  try {
    const r = await fetch('/api/race/' + id);
    d = await r.json();
  } catch (e) { d = null; }
  if (!d || !d.cars || !d.cars.length) { toast('That replay is not there'); return; }
  startReplay(d.cars.map(c => ({
    frames: c.frames, hz: d.hz, name: c.name, color: c.color, ms: c.ms,
  })), { title: 'Race replay' });
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
        <!-- The one you have just clicked, while it loads. Same corner as "Now",
             because they are the same fact a moment apart. -->
        <span class="tcard2-busy">Loading</span>
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
 *
 * **The sheet stays open until the world is up.** It used to close on the click
 * and leave you looking at the track you were trying to leave for as long as the
 * switch took, which on Mount Joy or the Costco is a request plus several
 * hundred milliseconds of synchronous building - so the honest reading of the
 * screen was that the click had not registered. Now the card you pressed says
 * `Loading`, the grid stops taking clicks, and the sheet closes at the moment
 * there is something new behind it. A failed switch leaves it open, because the
 * next thing you want is to pick something else.
 */
async function pickTrack(slug) {
  if (slug === S.track.slug) { toggleTracks(false); return; }
  if (CFG.mode === 'room') {
    if (!S.isHost) { toast('Only the host can change the track'); return; }
    // The room answers this for everybody at once over `track_change`, so there
    // is nothing local to wait for and the sheet's work is done.
    S.socket.emit('set_track', { code: CFG.room, track: slug });
    toggleTracks(false);
    return;
  }
  if (S.switching) return;                 // one at a time; the grid is dimmed anyway
  S.switching = slug;
  setSwitchBusy(slug, true);
  const ok = await switchTrack(slug, { quiet: true });   // the card is the message
  S.switching = null;
  setSwitchBusy(slug, false);
  if (ok) toggleTracks(false);
}

/** The clicked card, mid-switch: it says `Loading` and the rest stops taking clicks. */
function setSwitchBusy(slug, on) {
  const grid = $('tGrid');
  if (!grid) return;
  grid.classList.toggle('busy', on);
  grid.querySelectorAll('[data-track]').forEach((el) => {
    el.classList.toggle('busy', on && el.dataset.track === slug);
  });
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
  qual_countdown: ['Multiplayer - Qualifying about to start', true],
  qualifying: ['Multiplayer - Qualifying', true],
  countdown: ['Multiplayer - Race about to start', true],
  racing: ['Multiplayer - Race in progress', true],
  results: ['Multiplayer - Race finished', false],
};

// The phases the lights belong to. `qual_countdown` uses the same overlay and
// the same sounds as the start of a race, because it is the same thing: five
// seconds, then something begins that everybody is in.
const COUNTDOWN_PHASES = ['qual_countdown', 'countdown', 'racing'];

/** A session is actually running, so nothing about the room may change. */
function livePhase() {
  const p = S.previewPhase || S.racePhase;
  return p === 'qual_countdown' || p === 'qualifying' ||
         p === 'countdown' || p === 'racing';
}

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
  // The bot controls are disabled while a session is live, so they follow the
  // phase as well as the roster.
  renderBotControls(S.roster || []);
  if (CFG.mode !== 'room') return;
  const p = S.previewPhase || S.racePhase;      // `?panel=qual|racing`
  const [text, racing] = PHASE_LABEL[p] || PHASE_LABEL.free;
  setMode(text, racing);

  const start = $('btnStartRace'), end = $('btnEndRace'), resign = $('btnResign');
  const live = livePhase();
  // Only the host starts or stops one, so only the host is offered either.
  // Not during `results`: the sheet covering the screen has Rematch on it, and
  // the same offer twice - once behind the sheet making it - is one too many.
  // Enter still works there, since it is that sheet's Rematch by another name.
  start.style.display = (S.isHost && (p === 'free' || p === 'qualifying'))
    ? '' : 'none';
  // The button says what pressing it does, which is three different things:
  // open the session, skip the rest of it, or - with qualifying switched off -
  // start the race itself. A button labelled "Start race" that opens ninety
  // seconds of practice is a button that lied.
  setLabel(start, p === 'qualifying' ? 'Start race now'
                : (S.settings.qualifying ? 'Start qualifying' : 'Start race'));
  end.style.display = (S.isHost && live) ? '' : 'none';
  // It cancels before the lights and flags the race after them. Saying which
  // matters: one of them throws a result away and the other records one.
  setLabel(end, p === 'racing' ? 'End race' : 'Cancel race');
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
  showHostOnly();
  // The host can change mid-room and a session locks the switch, so the
  // settings follow the phase rather than being set when either happens.
  renderSettings();
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

/**
 * Five seconds, then qualifying opens.
 *
 * The same lights and the same sounds as the start of a race, because it is
 * the same event: something everybody is in is about to begin, and everybody
 * should be sitting still and looking at the road when it does. Qualifying
 * used to simply start, which meant the first anyone knew of it was the toast
 * saying they were already in it and a lap in progress that no longer counted.
 *
 * Nobody is placed anywhere. A qualifying session has no start line - everyone
 * leaves when they like, on their own lap - so the countdown runs down over
 * wherever you were, with the car held still so it cannot be jumped.
 */
function onQualCountdown(d) {
  S.racePhase = 'qual_countdown';
  S.raceMode = false;
  S.raceDone = false;
  S.standings = [];
  S.qualBest = null;
  S.qualRef = null;
  if (S.watch) stopWatching();
  toggleBoard(false);
  toggleTracks(false);
  toggleMenu(false);
  showSide(false);
  $('raceOver').style.display = 'none';
  hideResults();
  applyPhase();
  resetToStart();
  S.car.frozen = true;
  S.cdT0 = performance.now() + (d.t0 - serverNow());
  countdownLoop();
  toast('Qualifying is about to start');
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
  // Released from the countdown that has just run out - see onQualCountdown.
  S.car.frozen = false;
  // Nobody is on pole yet, so a ghost of it is a ghost of nothing.
  S.pole = null;
  S.poleGhost = null;
  if (S.ghostMode === 'pole') { S.ghost = null; S.ghostTimes = null; showGhostNow(); }
  toast('Qualifying - fastest lap sets the grid');
}

/**
 * R: throw the run away and line up again.
 *
 * Both this and the checkpoint below do **nothing until the clock is running**,
 * silently. Before that there is no run to throw away and no checkpoint to go
 * back to, so nothing is lost by refusing - and it closes a hole that was worth
 * real time: on a grid, pressing either of them moved the car forward to the
 * start gate, which is ahead of every grid slot, so a driver could shuffle
 * themselves up the road while the lights were still counting down.
 *
 * No toast on the refusal. A message would make a non-event into an event, and
 * the answer to "why did nothing happen" is that you have not set off yet.
 */
function restartRun() {
  if (!S.started) return;
  if (restartCostsARace() && !armRestart()) return;
  disarmRestart();
  resetToStart();
  toast('Restart');
}

/**
 * Is a stray R about to throw away something that cannot be driven again?
 *
 * **The race and nothing else**, which is the same answer `catchupOn` gives and
 * for a related reason: a race is the only session where the lap you are on is
 * the only one you get. Everywhere else R is the most useful key on the board
 * and asking about it would be in the way - free practice and solo are nothing
 * but restarting, and a qualifying lap thrown away is one of the two or three
 * that ninety seconds holds. In a race it is your race, and R is next to T,
 * which is the key you actually want when you have just fallen off.
 */
function restartCostsARace() {
  return CFG.mode === 'room' && S.raceMode && S.racePhase === 'racing';
}

/**
 * The first press of two. True once the second one lands.
 *
 * Not the `armed()` helper the Resign and End race buttons use: that one arms a
 * *button* and says so by rewriting its label, and this is armed by a key that
 * has no label to rewrite. So the state is here and the button follows it -
 * which is the right way round anyway, since R and the two restart buttons are
 * three doors into one rule and only one of them is under a cursor.
 *
 * The toast is not decoration, it is the whole of the feedback for the key: a
 * first press that silently did nothing would read as a dropped keystroke, and
 * the second press would then be somebody pressing R harder.
 */
let restartArm = null;

/** Both restart buttons at once: the HUD one and the touch one. */
function showRestartArmed(on) {
  for (const id of ['btnRestart', 'tRestart']) {
    const el = $(id);
    if (el) el.classList.toggle('armed', on);
  }
}

function armRestart() {
  if (restartArm) return true;
  restartArm = setTimeout(disarmRestart, ARM_MS);
  showRestartArmed(true);
  toast(S.touch ? 'Tap again to restart' : 'Press R again to restart');
  return false;
}

function disarmRestart() {
  if (restartArm) clearTimeout(restartArm);
  restartArm = null;
  showRestartArmed(false);
}

/**
 * T: back to the last checkpoint with the clock still running.
 *
 * This is the same path a fall takes, so there is only ever one respawn rule -
 * `Run.update` keeps the car's respawn target pinned to the last gate reached.
 */
function backToCheckpoint() {
  if (!S.started) return;
  S.car.requestRespawn();
}

/**
 * Enter: whatever the host's button says right now.
 *
 * Deliberately routed through the same guard the button is behind rather than
 * emitting on its own - the server refuses a non-host anyway, and a key that
 * silently does nothing for everybody except one person is easier to explain
 * than one that sends a message nobody acts on. Silent for everyone else, and
 * silent mid-race: there is no third thing Enter could mean there.
 */
function hostStart() {
  if (CFG.mode !== 'room' || !S.isHost || !S.socket) return;
  if (S.racePhase !== 'free' && S.racePhase !== 'results' &&
      S.racePhase !== 'qualifying') return;
  $('raceOver').style.display = 'none';
  S.socket.emit('start_race', { code: CFG.room });
}

/**
 * Escape: close whatever is in front of me.
 *
 * Innermost first - a replay, then a panel opened from another panel, then the
 * panel itself - and only when there is nothing left does it mean "open
 * settings". The controls sheet was missing from that list, so pressing Escape
 * while reading it opened settings on top of it: the one key everybody presses
 * to get out of something put something else in the way.
 */
function onEscape() {
  if (S.watch) stopWatching();
  else if ($('boardOv').style.display !== 'none') toggleBoard(false);
  else if ($('tracksOv').style.display !== 'none') toggleTracks(false);
  else if (S.helpOpen) toggleHelp(false);
  else toggleMenu();
}

function readInput() {
  const on = (k) => keys.has(k) || touchKeys.has(k);
  input.throttle = on('up') ? 1 : 0;
  input.brake = on('down') ? 1 : 0;
  input.steer = (on('right') ? 1 : 0) - (on('left') ? 1 : 0);
  input.handbrake = on('drift');
  return input;
}

/**
 * Which camera the keyboard is asking for, in the two words the renderer reads.
 *
 * Held, not toggled, and that is the whole design: a look behind you is a glance
 * you take with a hand you need back, so it ends when you let go and there is no
 * state left to be stuck in. Nothing here reads `touchKeys` - a phone has four
 * driving buttons and nowhere for a fifth, and a view you cannot let go of on
 * the road is worse than no view.
 *
 * The names are a contract with `Renderer.follow`, and pinned in test_rules_js.
 */
function viewKeys() {
  return { rear: keys.has('rear'), first: keys.has('first') };
}

// ---------------------------------------------------------------------------
// Frame
// ---------------------------------------------------------------------------
let lastFrame = performance.now();

// Warming up: how many frames in a row have come back quickly. See `noteWarm`,
// which is what holds the framed door shut until they do.
let warmRun = 0;

/**
 * Tell the door when the renderer is genuinely smooth.
 *
 * Not "the world is built": a built world still has shader programs left to
 * link, and each one stalls the frame that first needs it. So the test is the
 * symptom rather than any of its causes - twelve consecutive frames under 34ms
 * means the thing is actually running, whatever machine it is on and whatever
 * was left to compile.
 *
 * Consecutive is the whole of it. A *mean* would be dragged under the line by
 * the good frames between the stalls, which is exactly the state we are waiting
 * to leave: 2fps for ten seconds is not uniformly slow, it is fast frames with
 * compilation spikes through them.
 *
 * There is no time limit in here on purpose. The promise that the door always
 * opens is a `setTimeout` owned by the door itself, because a limit checked from
 * inside the frame loop is not a limit at all: the case it exists for is frames
 * not arriving, and a page whose rAF is throttled - an iframe below the fold, a
 * portal still showing its own splash, a background tab - would sit on Loading
 * for ever waiting for the frame that was going to notice the wait was too long.
 */
function noteWarm(ms) {
  if (!window.DriveDoor || window.DriveDoor.isReady()) return;
  warmRun = ms < 34 ? warmRun + 1 : 0;
  if (warmRun >= 12) window.DriveDoor.ready();
}

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (now - lastFrame) / 1000);
  noteWarm(now - lastFrame);
  lastFrame = now;

  // Above the early returns, so the counter keeps counting in a replay and while
  // a panel has the game paused - a frame rate that stopped updating the moment
  // you opened something would look like the number itself had frozen.
  fpsTick(now);

  // The music books its next few notes against the audio clock, and this is
  // the only thing on the page running often enough to turn that handle. Above
  // the early returns on purpose: a replay is still the game, and a preview
  // shot has no sound at all, so neither is a reason for the loop to stop.
  S.sound.musicTick();

  // Shot mode: hold the whole track in frame and render nothing else. This is
  // how the switcher's pictures are taken (tools/shoot_tracks.py), so the
  // preview of a track is always the track as it is now rather than a drawing
  // of it that has to be kept in step.
  if (S.shot) {
    if (S.shotAt != null) {
      // Park the car and let the *ordinary* camera follow it. `render` is given
      // a real dt so its follow spring settles rather than trailing a car that
      // teleported, which otherwise leaves the camera at the origin looking at
      // nothing for the first second - and a screenshot is all first second.
      seatCarAlongLap(S.shotAt);
      S.renderer.follow(S.car, dt);
      // The mesh has to be moved as well as the body. `S.car` is the simulation
      // and `S.view` is the thing you can see, and the normal frame path updates
      // both - so without this the car is parked correctly on the road and drawn
      // at the origin, which reads as a view with no car in it.
      S.view.update(S.car.pos, S.car.quat, {
        groundY: S.car.groundY,
        groundN: S.car.grounded ? S.car.groundN : null,
      });
    } else if (S.shotMode === 'plan') {
      planCamera();
    } else {
      shotCamera();
    }
    S.renderer.render(dt);
    return;
  }

  // A replay is somebody else's run, so none of the below applies to it: no
  // input, no physics, no clock of yours, and the camera belongs to them.
  if (S.watch) {
    updateWatch(dt);
    // Your car is parked for the replay, so nothing is stepping it - and a tow
    // you were in when you pressed Watch would otherwise hang in the air over
    // somebody else's lap. Bleed it, and let the streaks fly themselves out.
    S.car.draft(null, dt);
    // Same for the help you had for being behind: the race you were in is not
    // the one on the screen, and nothing steps the car while a replay runs.
    S.car.catchup(null, dt);
    S.renderer.draft(S.car, dt);
    // And everybody else's, for the same reason: nothing steps a rival while a
    // replay is on, so a tow one of them was in would hang in the air over
    // somebody else's lap for as long as you watched it.
    for (const r of S.remotes.values()) {
      r.slipCharge = 0; r.slipBoost = 0;
      S.renderer.draft(r, dt, r.draftFx);
    }
    // The views work on a replay too, because there is nothing about them that
    // needs the car to be yours: a lap you are watching is exactly where you
    // want to see what the driver could see.
    S.renderer.follow(S.watch.subject, dt, viewKeys());
    // Watching is not driving, and it takes the field with it: the room is
    // still going round out there, but a camera on somebody else's lap is not
    // where any of it is happening, so hearing it from here would be noise.
    S.sound.rivals(null);
    S.renderer.render(dt);
    return;
  }

  const inp = readInput();

  // In solo, the clock starts the moment you ask the car to move. In a race it
  // starts on the green light, which the server picks for everyone.
  // Not while a countdown is running. The car is held still for those five
  // seconds either way, but the *clock* would start on the first press and post
  // an attempt that nobody drove. A race countdown is already excluded by
  // `raceMode`; qualifying's is not, because qualifying is not a race.
  //
  // **The clock and the car must share a zero, and for a long time they did
  // not.** The order in this function is: start the clock, step the physics,
  // then `run.update` - which reads `now - startedAt`, i.e. **0**, and records
  // the ghost's frame 0 there. So the car had already been accelerated by a
  // whole frame when the clock said it had not moved, and nobody was charged
  // for the distance. Worse, `Stepper.acc` carried up to one `FIXED_DT` across
  // the start, so the number of free substeps was 0 to 4 depending on frame
  // timing: measured on the real board, laps differed by up to ~33ms of
  // unrecorded run-up, and it rewarded a *low* frame rate.
  //
  // Two lines fix it. `stepper.reset()` drops the carried remainder, and
  // `clockStarting` skips this frame's physics so `run.update` samples a car
  // that is genuinely stationary on the line at t=0. The cost is one frame of
  // throttle (<=17ms) and everybody pays it.
  let clockStarting = false;
  if (!S.started && !S.raceMode && S.racePhase !== 'qual_countdown' &&
      (inp.throttle || inp.brake || inp.steer)) {
    S.started = true;
    S.stepper.reset();
    S.run.start(now);
    clockStarting = true;
    noteStart();
    markHintSeen();
  }
  if (S.raceMode && S.racePhase === 'racing' && !S.started && S.raceT0 != null && now >= S.raceT0) {
    S.started = true;
    S.car.frozen = false;
    // Reset for the same reason, but **no skipped frame**: the green light is
    // `raceT0`, which is already in the past by the time this runs, so the clock
    // is legitimately non-zero and the car is owed that motion. Everyone in the
    // room shares the one server timestamp, and no lap set in a room reaches the
    // leaderboard anyway.
    S.stepper.reset();
    S.run.start(S.raceT0);
    noteStart();
    markHintSeen();
  }

  // `?draft=charge|boost` pins the tow, for the same reason `?panel=` and
  // `?touch=1` exist: the air round the car is the whole of what a slipstream
  // looks like, and photographing it otherwise takes two browsers, two people
  // and somebody driving eight car lengths ahead of the shutter.
  if (S.draftDemo) {
    if (S.draftDemo === 'boost') S.car.slipBoost = T.SLIP_BOOST;
    else S.car.slipCharge = 1;
  }

  // Rivals are brought up to now *before* the physics that has to hit them.
  // This used to run after, so every fixed substep in the frame resolved contact
  // against where the other cars were a frame ago - a car length of error at
  // racing speed, all of it in the direction of travel.
  updateRemotes(dt);

  // One list per frame rather than one per substep: the remote cars are
  // interpolated above and do not move again inside the fixed-step loop.
  const rivals = contactOn() ? collidables() : null;
  // Same again for the gap to the leader: it is read off the poses that were
  // brought up to date above and cannot change between substeps. `?catchup=`
  // pins it, the way `?draft=` pins a tow.
  const gap = S.catchupDemo != null ? S.catchupDemo : gapToLeader();
  if (!S.paused && !clockStarting) {
    S.stepper.run(dt, (h) => {
      // Before the step, not after: an anchor is the state a step *starts*
      // from, so that the server can seed a car from it and run the same eight
      // steps. See Run.noteStep.
      S.run.noteStep(S.car, inp, now);
      S.car.step(h, inp);
      if (rivals) S.car.resolveCars(rivals, h);
      // Always called, even with nobody to tow off: that is what bleeds a
      // charge away when you drop out of the hole, or when the phase changes
      // under you and the other cars stop being there at all.
      S.car.draft(rivals, h);
      // And always called with the gap, `null` included, for the same reason:
      // taking the lead or the race ending has to bleed the help away rather
      // than leave the last value of it running.
      S.car.catchup(gap, h);
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
  // The tow's own air, on the same tick: it fills with the charge and falls
  // away with the boost, so the whole thing is audible without being looked at.
  // The tow's rushing air is the same air a pad's boost makes, so the band
  // opens for either - but only a tow has a charge to fill it with beforehand.
  S.sound.draft(car.slipCharge,
                Math.max(car.slipBoost / T.SLIP_BOOST, car.padBoost / T.PAD_BOOST));
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
  S.renderer.follow(car, dt, viewKeys());
  // The ears ride the camera, so they are moved the moment it has been - and
  // the field is spatialised against where it has just gone rather than where
  // it was last frame. Your own car stays out of this: it is the thing you are
  // sitting in, and it has no direction to arrive from.
  S.sound.listener(S.renderer.camera);
  S.sound.rivals(rivalSound());
  S.view.update(car.pos, car.quat, {
    lean: car.bumpLean + (-car.steer * Math.min(1, car.speed / T.MAX_SPEED) * 0.06),
    steer: car.steer,
    spin: car.wheelSpin,
    groundY: car.groundY,
    groundN: car.grounded ? car.groundN : null,
    // Read off the same flags the network and the ghost recorder use, so your
    // own car's lamps and the ones every rival sees are the same lamps.
    ...lampsOf(car.flags()),
  });
  S.view.setVisible(car.respawnIn <= 0);
  S.renderer.draft(car, dt);

  // the ghost you are chasing, in its owner's colour and showing its lamps
  if (ghostOn() && S.started) {
    const gv = ghostView();
    const t = (S.run.state === 'running' ? S.run.time : 0) / 1000;
    const f = S.ghost.at(t);
    if (f) {
      gv.group.visible = true;
      const q = new THREE.Quaternion(f[3], f[4], f[5], f[6]).normalize();
      // The eighth value is what the driver was doing at that instant, if the
      // lap is new enough to have been recorded with it (see Run._recordGhost).
      gv.update(new THREE.Vector3(f[0], f[1], f[2]), q, lampsOf(f[7]));
      gv.shadow.visible = false;
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

/**
 * `?shot=plan`: straight down on the whole track, north up.
 *
 * The authoring view, and the opposite trade from `shotCamera`. That one is a
 * photograph and gives up on showing the layout; this one gives up on looking
 * like anywhere and shows nothing but the layout. It is what a plan drawing
 * would be if the game could draw one, and it is the picture that answers the
 * questions authoring actually asks - is the last leg back inside the building,
 * did that hairpin bulge into the next aisle, does the road cross itself where
 * it was supposed to, is the closing stretch as long as it felt.
 *
 * Height is fitted rather than scaled: the frame has to hold the track's *bigger*
 * axis at the camera's aspect, and picking the wrong one silently crops the end
 * of a long track - which reads as a track that stops rather than as a camera
 * that is too low.
 */
function planCamera() {
  const pts = S.built.line.map(e => e.p);
  let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity, hi = -Infinity;
  for (const p of pts) {
    x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]);
    z0 = Math.min(z0, p[2]); z1 = Math.max(z1, p[2]);
    hi = Math.max(hi, p[1]);
  }
  const cam = S.renderer.camera;
  const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
  const w = Math.max(1, x1 - x0), d = Math.max(1, z1 - z0);
  // Vertical half-angle, and the horizontal one it implies at this aspect.
  const vf = (cam.fov * Math.PI / 180) / 2;
  const hf = Math.atan(Math.tan(vf) * cam.aspect);
  // 12% of margin, so nothing sits on the edge of the frame and a barrier at the
  // extreme of the track is still visibly inside it.
  const need = Math.max((d / 2) / Math.tan(vf), (w / 2) / Math.tan(hf)) * 1.12;
  cam.position.set(cx, hi + need, cz);
  // A camera looking straight down has no unique up vector, so three falls back
  // on its default and the track arrives at whatever rotation that implies.
  // Pinning it to -Z puts north up, which is the orientation every other tool
  // here reports in - `self_proximity` failures, the bbox, SHELL_X/SHELL_Z.
  cam.up.set(0, 0, -1);
  cam.lookAt(new THREE.Vector3(cx, hi, cz));
  cam.updateProjectionMatrix();
}

/**
 * `?shot=at:<f>`: park the car on the centreline a fraction of the way round.
 *
 * Placed with the same `placeAt` a respawn uses, so the car arrives on the road
 * at the road's own attitude - upside down inside a loop, banked on a wall - and
 * not merely at the right coordinates. The alternative was interpolating a pose
 * here, which is a second copy of something `Builder` already baked into every
 * station.
 */
function seatCarAlongLap(f) {
  const line = S.built.line;
  const s = S.built.s;
  const target = s[s.length - 1] * f;
  let i = 1;
  while (i < s.length - 1 && s[i] < target) i++;
  // Forward is the difference to the next station rather than a stored heading,
  // which is what `spawn.fwd` is too - the ribbon does not carry one, because
  // `n x lat` is it.
  const a = line[i - 1].p, b = line[Math.min(i, line.length - 1)].p;
  const fwd = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const len = Math.hypot(fwd[0], fwd[1], fwd[2]) || 1;
  S.car.placeAt(line[i].p, [fwd[0] / len, fwd[1] / len, fwd[2] / len]);
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
  // And being helped along for being behind is worth showing over the top of
  // it, because it is the one of the two you can do something about. A car that
  // is quietly faster than it was a lap ago and cannot say why is a bug report;
  // the bar is where the engine already is, so it is where this goes. (The tow
  // is drawn in the air round the car instead - it is a move somebody makes,
  // and it belongs out on the road where the car it is aimed at can see it.)
  $('speedFill').classList.toggle('catchup', car.catchupBoost > 0.05);
  $('time').textContent = fmt(run.state === 'ready' ? 0 : run.time);
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
  if (!qualifying && (S.raceMode || S.remotes.size || S.previewOrder)) {
    const order = S.previewOrder || liveOrder();
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

/**
 * The running order, off one snapshot, projected to one instant.
 *
 * This used to be settled locally by `liveOrder`, and it compared **your own
 * distance right now against everybody else's from a round trip ago**. At 60ms
 * of ping that is about three units of track, always in the reader's favour and
 * mirrored on the other screen, so two cars side by side were each shown ahead
 * on their own monitor - the board saying the opposite of the board next to it,
 * with no way to tell which had it right.
 *
 * The answer is one clock, and there is exactly one clock everybody shares: the
 * snapshot. It carries every car - *including the reader's own*, which the pose
 * loop otherwise skips - each with the server's copy of its progress and, since
 * the age field, its own staleness. So each is walked forward by its own age
 * and the whole field is sorted at `snap.t`. Every browser is handed the same
 * bytes and does the same arithmetic on them, so every browser reaches the same
 * order. Nobody is compared against a fresher copy of themselves.
 *
 * Derived from what is already in the message rather than sent alongside it. A
 * server-computed list would be a second statement of a fact the same packet
 * already carries twice over, and the interesting question would become which
 * of the two to believe when they disagreed.
 *
 * The projection uses speed rather than progress-per-second, which slightly
 * over-credits a car that is sliding: ages run to about a pose interval, so the
 * whole term is under two units and its error is a small fraction of that.
 * Doing nothing instead would hand the place to whichever car's packet happened
 * to land nearest the tick, which is a coin flip thirty times a second.
 *
 * **Field 13 only, and never the upstream leg beside it in field 15.** The
 * drawing adds the two, because it wants the whole journey; this must not,
 * because 15 is a number the car being ranked reported about itself. Add it in
 * and overstating your own ping is worth four units of projected road on
 * everybody's board - a cheat invented by the fix for something else, in the
 * one place this whole function exists to make trustworthy.
 */
function orderFromSnapshot(snap) {
  const out = [];
  for (const pid in snap.cars) {
    const a = snap.cars[pid];
    const age = (a.length > 13 ? a[13] : 0) / 1000;
    out.push({ pid, s: a[10] + Math.hypot(a[7], a[8], a[9]) * age });
  }
  // Ties broken by pid, not by enumeration order: `prog` is rounded to 0.1 on
  // the wire, so two cars genuinely abreast do tie, and the pair of screens has
  // to break it the same way or the whole point is lost on the one case the
  // whole thing is for.
  out.sort((x, y) => (y.s - x.s) || (x.pid < y.pid ? -1 : 1));
  return out;
}

function liveOrder() {
  const mine = CFG.me ? CFG.me.pid : null;
  // Where the server last saw everybody, all at the same instant. Empty in solo
  // and in a replay, where there is no snapshot and nobody to disagree with, and
  // then every line below falls back to what it did before.
  const rank = new Map(), prog = new Map();
  S.order.forEach((e, i) => { rank.set(e.pid, i); prog.set(e.pid, e.s); });
  // Your own row comes off the snapshot too, ~a round trip old like everyone
  // else's. That is the point rather than a cost: a gap is a difference, so
  // what it needs is one clock, and being the only car on the board reading
  // its own live number is precisely what made the two boards disagree.
  const at = (pid, live) => (prog.has(pid) ? prog.get(pid) : live);
  const out = [{ name: CFG.name, color: CFG.me ? CFG.me.color : '#e8453c', pid: mine,
                 s: at(mine, S.run.bestS), self: true,
                 ms: S.run.state === 'done' ? S.run.time : null }];
  for (const [pid, r] of S.remotes) {
    out.push({ name: r.name, color: r.color, s: at(pid, r.prog), self: false, pid,
               ms: (S.standings.find(x => x.pid === pid) || {}).ms || null });
  }
  out.sort((a, b) => {
    if (a.ms != null && b.ms != null) return a.ms - b.ms;
    if (a.ms != null) return -1;
    if (b.ms != null) return 1;
    const ra = rank.has(a.pid) ? rank.get(a.pid) : Infinity;
    const rb = rank.has(b.pid) ? rank.get(b.pid) : Infinity;
    // Compared rather than subtracted: two cars the snapshot has never heard of
    // are both Infinity, and `Infinity - Infinity` is a NaN comparator, which
    // sorts to whatever the engine feels like.
    if (ra !== rb) return ra - rb;
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
    if (d.ghost) useGhost(d.ghost, d.hz || GHOST_RATE, d.color, d.livery);
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

/**
 * Race against these frames from now on.
 *
 * The colour belongs to whoever drove them. A ghost used to be the same grey
 * whoever it was, which made "my best", the world record and somebody you
 * picked off the board three indistinguishable cars - and the one thing you
 * want to know about the car you are chasing is whose it is.
 */
function useGhost(frames, hz, color, livery) {
  if (!frames || frames.length < 2) return;
  S.ghost = new Ghost(frames, hz || GHOST_RATE);
  S.ghostTimes = lapTimeline(S.ghost.frames, S.ghost.hz);
  S.ghostColor = color || null;
  // Their whole car where the server sent one - `/api/ghost` does, the pole lap
  // does - and just the colour otherwise, which `CarView` reads as a livery of
  // its own. `ghostView` keys its rebuild on the colour, so this rides alongside
  // rather than replacing it.
  S.ghostLivery = livery || null;
}

// A lap with nobody attached to it - a guest's, or one from before colours
// belonged to people.
const GHOST_GREY = '#9aa7b8';

/** The colour of your own car: your seat's in a room, your own everywhere else. */
function myColor() {
  return (CFG.me && CFG.me.color) || CFG.carColor || '#e8453c';
}

/**
 * Your whole car, not just its colour.
 *
 * A room's seat carries its own copy so that arriving in one draws the right car
 * on the first frame rather than after the roster lands; everywhere else it came
 * down with the page. Falls back to the colour, which is what a guest has - and
 * a colour on its own is a complete livery as far as `CarView` is concerned, so
 * there is no branch anywhere downstream.
 */
function myLivery() {
  return (CFG.me && CFG.me.livery) || CFG.carLivery || myColor();
}

/**
 * The translucent car, in the car of whoever is being chased.
 *
 * Rebuilt when that changes rather than recoloured, because a CarView bakes its
 * livery into half a dozen materials and some geometry at construction, and this
 * happens once per ghost rather than once per frame.
 *
 * **Keyed on the whole livery and not just the colour.** It used to be the
 * colour alone, which was a complete description of a ghost when a colour was
 * all a car had. It is not one any more: two people on the same body colour with
 * different wheels would have handed the second one the first one's car, and it
 * would have been right about the only thing the key was checking.
 */
function ghostView() {
  const c = S.ghostColor || GHOST_GREY;
  // A ghost wears its owner's *current* car rather than a recorded one: a lap
  // does not store a livery, and your own ghost turning up in last month's paint
  // would be a stranger on your line.
  const spec = S.ghostLivery || c;
  const key = typeof spec === 'string' ? spec : JSON.stringify(spec);
  if (S.ghostView && S.ghostViewColor === key) return S.ghostView;
  if (S.ghostView) S.ghostView.dispose();
  S.ghostView = new CarView(S.renderer.scene, spec, { ghost: true });
  S.ghostViewColor = key;
  return S.ghostView;
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
  // A start is one half of "how many goes did this track take out of you", and
  // its other half is a finish that counts. In a room neither does.
  if (!countsForTheBoard()) return;
  try {
    fetch('/api/start', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track: S.track.slug }),
    }).catch(() => {});
  } catch (e) { /* no network, no counter, no interruption */ }
}

// Below this you rolled off the line and changed your mind. A POST per twitch is
// noise, and half a second of driving is not a minute played.
const MIN_REPORTED_MS = 500;

/**
 * Report the run in progress as driving that happened - once, and only once.
 *
 * `drive_time` and `distance` used to be written only by `/api/run`, which is
 * posted when a lap **finishes**. On the live database that meant 83% of attempts
 * counted for nothing, and a whole evening in a room counted for nothing at all,
 * because `countsForTheBoard()` gates the board APIs and a room lap fails it. So
 * every other way a run can end now reports what it was worth.
 *
 * **`run.counted` is the correctness of this whole feature.** A finished solo lap is
 * already counted by `/api/run`; if an abandon path reported it as well, every lap
 * would be worth double. So the flag is set by whichever path gets there first, and
 * cleared by `Run.start` - the one place a new run begins.
 */
function reportActivity(why, opts = {}) {
  const run = S.run;
  if (!CFG.loggedIn || !S.started || !run || run.counted) return;
  if (run.time < MIN_REPORTED_MS) return;
  run.counted = true;
  const body = JSON.stringify({ track: S.track.slug, ms: Math.round(run.time),
                                distance: Math.round(run.distance), why });
  // A tab that is going away cannot wait for `fetch`. `sendBeacon` hands the
  // request to the browser to deliver after the page is gone, which is the only
  // way a run abandoned *by closing the tab* survives - and that is how most runs
  // actually end.
  if (opts.beacon && typeof navigator !== 'undefined' && navigator.sendBeacon) {
    try { navigator.sendBeacon('/api/activity', body); return; } catch (e) { /* fall through */ }
  }
  if (typeof fetch !== 'function') return;
  try {
    fetch('/api/activity', {
      method: 'POST', keepalive: true,
      headers: { 'Content-Type': 'application/json' }, body,
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
  // the best of them - with its replay, because the lap on provisional pole is
  // the one ghost worth having in a session whose whole purpose is that lap.
  // The server throws away every replay but the leader's.
  if (qualifying && S.socket) {
    S.socket.emit('qual_time', { ms: run.time, ghost: run.ghost,
                                 hz: GHOST_RATE });
  }

  // In a room your ghost is the best lap of this practice session. Not your
  // all-time PB: the room is a place you turn up and learn a track together,
  // and a ghost from three weeks ago is not what you are chasing there.
  if (CFG.mode === 'room' && !racing &&
      (S.sessionBest == null || run.time < S.sessionBest)) {
    S.sessionBest = run.time;
    // Your lap, so your car - the same colour you are driving.
    useGhost(run.ghost.slice(), GHOST_RATE, myColor(), myLivery());
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
    S.qualAgain = setTimeout(() => {
      S.qualAgain = null;
      if (S.racePhase === 'qualifying') resetToStart();
    }, 1200);
  }
  else showResults({ time: run.time, medal, pb: improved ? run.time : prev });

  // Nothing from a room goes up: no time, no medal, no ghost, no distance, no
  // attempt - see countsForTheBoard. The session ghost above still gets it,
  // because that is what the room is for.
  if (!countsForTheBoard()) {
    // The lap does not go on the board, but it was still driven. This is the one
    // place a *finished* lap reports through `/api/activity` rather than
    // `/api/run`: a room lap never reaches `/api/run` at all, so without this an
    // entire evening of racing is nought minutes and nought kilometres.
    reportActivity('room lap');
    if (!racing && !qualifying) {
      showResults({ time: run.time, medal, pb: S.bestTime, wr: S.track.record_ms,
                    note: 'Practice lap - times set in a room stay in the room.' });
    }
    return;
  }
  // Past here `/api/run` adds the time and distance itself, so claim the run now:
  // whatever ends it afterwards (R, switching track, closing the tab) must not
  // report it a second time.
  run.counted = true;

  try {
    const r = await fetch('/api/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track: S.track.slug, time_ms: run.time,
                             splits: run.splits, ghost: run.ghost,
                             distance: Math.round(run.distance),
                             // What the driver did, step by step. A lap near the
                             // top of the board is re-driven on the server
                             // before it goes up, and this is what it is
                             // re-driven from - see Run.noteStep.
                             verify: run.verifyPayload() }),
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
        // `note` is nearly always absent. The one case that fills it is a lap
        // quick enough to be re-driven on the server before it goes up (see
        // /api/run): it is stored and it is yours, and the board has not got it
        // yet - which is worth a sentence rather than a PB that appears to have
        // been ignored.
        showResults({ time: run.time, medal, rank: d.run_rank,
                      pb: d.pb_ms, pbRank: d.rank, wr: d.record_ms,
                      share: d.time_id, note: d.note || null });
      }
      // Solo, a new PB is a new ghost - **but only if your own lap is the one
      // you asked to drive against.**
      //
      // This used to be an unconditional `loadGhost('me')`, which is the bug
      // behind "a PB switches my ghost off the record". It never touched
      // `S.ghostMode`, so the setting still read *World Record* while the car on
      // the road quietly became your own lap: the mode and the ghost disagreed,
      // and the setting was the one telling the truth about what you had chosen
      // and the lie about what you were chasing.
      //
      // Taking the record is the one case where a `wr` ghost does need
      // reloading, because the record it points at is now yours.
      if (d.improved && CFG.mode !== 'room') {
        if (S.ghostMode === 'me') loadGhost('me');
        else if (S.ghostMode === 'wr' && d.is_record) loadGhost('wr');
      }
    } else {
      if (improved) { S.bestTime = run.time; localBest(run.time); }
      // A guest's lap is kept whole - replay and all - so that logging in later
      // puts it on the board rather than asking them to drive it again.
      if (d.guest && window.DrivePending) {
        window.DrivePending.save({
          track: S.track.slug, time_ms: run.time, splits: run.splits,
          ghost: run.ghost, distance: Math.round(run.distance),
          verify: run.verifyPayload(),
        });
      }
      if (!racing) {
        showResults({ time: run.time, medal, rank: d.run_rank, pb: S.bestTime,
                      wr: d.record_ms, guest: !!d.guest,
                      note: d.note || d.error || null });
      }
    }
  } catch (e) {
    // The request never landed, so nobody has this lap but us. Keep it in the
    // same place a guest's laps go and it will be handed over on a later page.
    if (window.DrivePending) {
      window.DrivePending.save({
        track: S.track.slug, time_ms: run.time, splits: run.splits,
        ghost: run.ghost, distance: Math.round(run.distance),
        verify: run.verifyPayload(),
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

/**
 * The tail-lamp state packed into a recorded flag byte.
 *
 * One place, because three different things read one: the ghost, a replay, and
 * a rival's pose. Laps recorded before flags existed hand in `undefined` here,
 * which is a car with its lamps off rather than an error.
 *
 * Only braking. `FLAG.DRIFT` is in the byte and stays there, but the lamps are
 * red or dark and nothing else: the handbrake counts as braking, so an amber
 * drift state did not turn the lamps *on*, it changed the colour of lamps that
 * were already lit - and a car that goes yellow every time it steps out reads
 * as a fault rather than as a driver.
 */
function lampsOf(flags) {
  return { braking: !!((flags | 0) & FLAG.BRAKE) };
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
  setShare(r.share, r.guest);
}

/**
 * Arm (or disarm) the Share button for the lap the sheet is showing.
 *
 * Called from `showResults`, which runs twice per lap - once on the line with
 * nothing known and once when `/api/run` has answered - so the ordinary path is
 * disabled, then enabled a moment later with an id.
 *
 * A guest has no row on any board and therefore no lap anybody could be sent to,
 * which makes this the one place in the game where an account buys something
 * concrete and immediate. So the button stays lit and says what is missing,
 * rather than going grey with no explanation.
 */
function setShare(id, guest) {
  const b = $('btnShare');
  if (!b) return;                 // room and replay do not have one
  S.shareId = id || null;
  b.disabled = !id && !guest;
  b.textContent = id ? 'Share' : 'Log in to share';
}

/**
 * Hand over a link to the lap on the board: `/solo/<slug>?watch=<id>`.
 *
 * Deliberately not a new kind of page. That URL is how the public board has
 * always handed a lap to the game - `openRequestedLap` watches it, and the
 * ghost is then there to chase - so what this adds is a way to *get* the link
 * from the one screen where somebody has just done something worth sending. The
 * server gives it a share card naming the track and the time (`_track_og`), so
 * what lands in a chat window is the lap rather than the word "Drive".
 */
async function shareLap() {
  if (!S.shareId) {
    location.href = '/login?next=' + encodeURIComponent(location.pathname);
    return;
  }
  const url = location.origin + '/solo/' + S.track.slug + '?watch=' + S.shareId;
  try {
    // The phone answer and the desktop one. `navigator.share` opens the OS
    // sheet, which is what somebody on a phone means by sharing; everywhere it
    // does not exist, the clipboard is the whole of it.
    if (navigator.share) {
      await navigator.share({ title: 'Drive - ' + S.track.name, url });
      return;
    }
    await navigator.clipboard.writeText(url);
    toast('Link copied - it opens your lap as a ghost');
  } catch (e) {
    // Dismissing the OS share sheet rejects, and a share nobody wanted is not a
    // failure worth saying anything about.
    if (e && e.name === 'AbortError') return;
    toast(url);
  }
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
    for (let i = 0; i < 5; i++) {
      setTimeout(() => {
        const d = { c: Date.now() };
        // The round trip measured so far, which the server halves and hands to
        // everybody else as this car's *upstream* leg - the half of the path it
        // has no way to time for itself, since it stamps a pose when the pose
        // lands. See `on_clock`. Left off the first ping, which is the one with
        // nothing measured yet, and refined by the four behind it.
        if (isFinite(S.bestRtt)) d.rtt = Math.round(S.bestRtt);
        socket.emit('clock', d);
      }, 200 * i);
    }
  });
  socket.on('clock', (d) => {
    const now = Date.now(), rtt = now - d.c;
    // Keep the sample with the shortest round trip: it has the least ambiguity
    // about where in the trip the server timestamp was taken.
    if (rtt < S.bestRtt) { S.bestRtt = rtt; S.clockOffset = d.s + rtt / 2 - now; }
  });
  socket.on('room_hello', (d) => {
    renderRoster(d.players);
    if (d.settings) S.settings = d.settings;
    else if (d.race && d.race.settings) S.settings = d.race.settings;
    S.racePhase = d.race ? d.race.phase : 'free';
    S.pole = (d.race && d.race.pole) || null;
    applyPhase();
    // Walking in on a session already running: show it rather than pretending
    // the room is idle until the next message happens to arrive.
    if (S.racePhase === 'qualifying' && d.race && d.race.qual) {
      renderQual(d.race.qual);
      startQualClock();
      if (S.ghostMode === 'pole') loadPoleGhost();
    }
    (d.chat || []).forEach(addChat);
  });
  socket.on('roster', (d) => {
    renderRoster(d.players);
    if (d.track && d.track !== S.track.slug) switchTrack(d.track);
  });
  socket.on('poses', onPoses);
  socket.on('track_change', (d) => switchTrack(d.track));
  socket.on('qual_countdown', onQualCountdown);
  socket.on('qual_start', onQualStart);
  socket.on('qual_progress', (d) => { if (S.racePhase === 'qualifying') renderQual(d.qual); });
  // Pole changed hands. Everyone is told who; the lap itself is fetched by
  // whoever is chasing it.
  socket.on('qual_pole', (d) => {
    S.pole = d || null;
    if (S.ghostMode === 'pole') { loadPoleGhost(); showGhostNow(); }
  });
  socket.on('qual_pole_ghost', (d) => {
    if (S.ghostMode !== 'pole' || S.racePhase !== 'qualifying') return;
    if (d && d.ghost) useGhost(d.ghost, d.hz || GHOST_RATE, d.color, d.livery);
    showGhostNow();
  });
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
  // The host moved a switch. Said out loud as well as drawn, because the
  // drawer is usually shut and this changes what everybody is about to do.
  socket.on('room_settings', (d) => {
    const was = S.settings.qualifying;
    S.settings = d || S.settings;
    renderSettings();
    if (!!S.settings.qualifying !== !!was) {
      toast(S.settings.qualifying ? 'Qualifying on - a lap sets the grid'
                                  : 'Qualifying off - last race, reversed');
    }
  });
  socket.on('chat', addChat);
  socket.on('kicked', (d) => { if (CFG.me && d.pid === CFG.me.pid) location.href = '/lobbies'; });
  // The room ended under you - the host left, everybody left, or it expired.
  // The reason is carried to the lobby list and said there, because a page
  // that teleports you somewhere without a word is indistinguishable from a
  // bug, and "the host left" is the one thing that explains it.
  socket.on('room_closed', (d) => {
    const why = (d && d.reason) || '';
    location.href = '/lobbies' + (why ? '?closed=' + encodeURIComponent(why) : '');
  });
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
  // Somewhere else, chosen from the sheet that has just told you this race is
  // over. It is the same switcher as always - the host picks and everybody's
  // world changes - so this opens it rather than being a second way to choose.
  $('btnRaceTrack').onclick = () => {
    $('raceOver').style.display = 'none';
    S.racePhase = 'free';
    applyPhase();
    resetToStart();
    toggleTracks(true);
  };
  $('btnWatchRace').onclick = () => {
    if (S.lastRaceId) location.href = '/race/' + S.lastRaceId;
  };
  // The level rides on the button, so building a mixed field is one press per
  // car rather than a trip through a dialog each time.
  const botLevel = () => ($('botLevel') || {}).value || 'medium';
  if ($('btnAddBot')) {
    $('btnAddBot').onclick = () =>
      socket.emit('add_bot', { code: CFG.room, level: botLevel() });
  }
  if ($('btnFillBots')) {
    // Seating up to seven cars takes a round trip and, the first time a room is
    // on a track, a collider build behind it. Saying so on the button is the
    // whole fix for "it feels laggy": the press is acknowledged in the same
    // frame, and the control then disappears rather than sitting there inviting
    // a second fill of a grid that is already full.
    $('btnFillBots').onclick = () => {
      const b = $('btnFillBots');
      if (b.disabled) return;
      S.fillingBots = true;
      b.disabled = true;
      b.classList.add('busy');
      setLabel(b, 'Adding racers…');
      // If the server refuses - the room filled up from somewhere else between
      // the render and the press - no roster arrives and nothing would ever put
      // the button back. It is a stuck control either way; this way it unsticks.
      clearTimeout(S.fillTimer);
      S.fillTimer = setTimeout(() => {
        S.fillingBots = false;
        renderBotControls(S.roster || [], true);
      }, 5000);
      socket.emit('fill_bots', { code: CFG.room, level: botLevel() });
    };
  }
  $('optQual').onclick = (e) => {
    if (e.currentTarget.disabled) return;
    socket.emit('set_setting', { code: CFG.room, key: 'qualifying',
                                 value: !S.settings.qualifying });
  };
  $('shareLink').value = location.origin + '/j/' + CFG.room;
  $('btnShareCopy').onclick = async () => {
    const inp = $('shareLink');
    inp.select();
    try {
      await navigator.clipboard.writeText(inp.value);
      toast('Link copied');
    } catch (e) {
      // No clipboard permission, which is ordinary on a phone browser and over
      // plain http. The link is selected, so there is still something to do.
      toast('Press copy on your keyboard');
    }
  };
  // Enter sends it and hands the keyboard back to the car. Staying in the box
  // is what a chat window does; this is a driving game, and the next thing you
  // do after saying something is drive.
  $('chatForm').onsubmit = (e) => {
    e.preventDefault();
    const inp = $('chatInput');
    if (inp.value.trim()) socket.emit('chat', { text: inp.value.trim() });
    inp.value = '';
    inp.blur();
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
    // How full the tow is, 0..1 - and `FLAG.SLIP` in the byte above says which
    // of the two things that is: the charge while it fills, the fraction of the
    // boost left while it pays. One number rather than two, because the flag
    // that disambiguates it was already on the wire for the tail lamps. Without
    // it a rival's slipstream could only ever be drawn as on or off, and the
    // half of it worth watching is the second and a half it spends filling.
    sl: c.slipBoost > 0 ? c.slipBoost / T.SLIP_BOOST : c.slipCharge,
  });
}

function onPoses(snap) {
  // Settled here rather than in the HUD: it belongs to the snapshot, so it is
  // worked out once when one arrives instead of once a frame off whichever one
  // happens to be current.
  S.order = orderFromSnapshot(snap);
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
    //
    // Two ages, added: field 13 is the wait since the pose *landed*, which the
    // server timed itself, and field 15 is the trip it made getting here, which
    // only the client at the other end could measure. A pose describes where a
    // car was when it was sent, so the drawing wants the whole path - without
    // the second term every rival is short by its own upstream leg, on every
    // screen but its own. They stay separate on the wire because the running
    // order wants only the half the server owns: see `orderFromSnapshot`.
    r.packetT = snap.t - (a.length > 13 ? a[13] : 0) - (a.length > 15 ? a[15] : 0);
    r.px = a[0]; r.py = a[1]; r.pz = a[2];
    r.q.set(a[3], a[4], a[5], a[6]);
    r.vel.set(a[7], a[8], a[9]);
    r.prog = a[10]; r.cp = a[11]; r.flags = a[12];
    // The tow level, guarded the same way the age above it is: a client left
    // open across a deploy simply has no tow to draw rather than a NaN one.
    r.tow = a.length > 14 ? a[14] : 0;
    r.lastSeen = performance.now();
  }
  // drop anyone who stopped reporting
  for (const [pid, r] of S.remotes) {
    if (!(pid in snap.cars) && performance.now() - r.lastSeen > 3000) {
      dropRemote(r);
      S.remotes.delete(pid);
    }
  }
}

/** Everything a rival owns in the scene. Its voice goes when it leaves the list. */
function dropRemote(r) {
  r.view.dispose();
  r.draftFx.dispose();
}

function addRemote(pid) {
  const meta = (S.roster || []).find(p => p.pid === pid) || {};
  const r = {
    pid, name: meta.name || 'Driver', color: meta.color || '#8899aa',
    pos: new THREE.Vector3(), vel: new THREE.Vector3(), fwd: new THREE.Vector3(0, 0, -1),
    q: new THREE.Quaternion(), rq: new THREE.Quaternion(),
    px: 0, py: 0, pz: 0, prog: 0, cp: 0, flags: 0, tow: 0,
    packetT: 0, lastSeen: performance.now(), primed: false,
    view: new CarView(S.renderer.scene, meta.livery || meta.color || '#8899aa'),
    mass: 1, id: pid,
    // A remote car is a car as far as the tow effect is concerned, so it carries
    // the same fields the local one does and `Draft` needs no idea which is
    // which: the three axes it draws its ring about, how fast it is going, and
    // the two halves of the tow. All of them are filled in by updateRemotes.
    right: new THREE.Vector3(1, 0, 0), up: new THREE.Vector3(0, 1, 0),
    speed: 0, slipCharge: 0, slipBoost: 0, respawnIn: 0, T,
    draftFx: S.renderer.makeDraft(),
  };
  // No colour handed over, so the car answers. `plateColor` is the body colour
  // for almost everybody and the record green for whoever is wearing the laurel,
  // and that plate is most of what the badge is *for*: a decal on a low-poly car
  // is invisible at the distance you see rivals from, where the name over it is
  // legible from anywhere. Passing `r.color` here overrode it, so the one car on
  // the track that had earned a green nameplate was the only one that could
  // never show it.
  r.view.setLabel(r.name);
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
 *
 * **And the chase has to be led, or it never arrives.** See `CHASE_RATE`.
 */
const REMOTE_SNAP = 12;               // units; ~3.5 car lengths, well past a frame of driving
const CHASE_RATE = 16;                // 1/s; the exponential the position is chased at

/**
 * How far behind a moving target the chase settles, as time.
 *
 * An exponential filter never catches a target that is itself moving: each
 * frame closes a fraction `k` of the gap while the target opens `v*dt` of new
 * one, so it comes to rest `v*dt*(1-k)/k` short - at MAX_SPEED, about three
 * units, most of a car length, on every rival on every screen with no network
 * involved at all. **That was the larger half of this game's multiplayer
 * disagreement, and none of it was ping.** Each driver saw the other one most
 * of a car back, the two errors point opposite ways, and so two cars genuinely
 * level looked like a lead to each of them.
 *
 * Leading the target by exactly that lag cancels it. Solving the filter's fixed
 * point for zero error gives `dt*(1-k)/k`, which is bounded above by the
 * filter's own time constant (1/CHASE_RATE, 62ms) however long a frame runs, so
 * a hitch cannot turn it into a lunge. Exact for a car going in a straight
 * line; for one that is braking or turning it is wrong by the same amount and
 * in the same direction as the extrapolation it is added to, which is the
 * residue nothing short of sending acceleration can remove.
 *
 * It is *added to the packet age* rather than applied separately because they
 * are the same quantity - time this car has spent driving since the position in
 * hand - and the extrapolation does not care which is which.
 */
function chaseLead(dt, k) { return dt * (1 - k) / k; }

function updateRemotes(dt) {
  const nowS = serverNow();
  // The tow is drawn on a rival for exactly the phases it can happen in, and it
  // is the same answer contact and your own tow read - so a car cannot be seen
  // winding up a boost in a session where nobody can get one.
  const towOn = contactOn();
  const k = 1 - Math.exp(-CHASE_RATE * dt);
  const lead = chaseLead(dt, k);
  for (const r of S.remotes.values()) {
    // Only the age is clamped. That clamp is about not flinging a stale packet
    // across the map; the lead is not staleness and is bounded by its own maths.
    const ahead = Math.min(0.35, Math.max(0, (nowS - r.packetT) / 1000)) + lead;
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
      r.pos.x += (tx - r.pos.x) * k;
      r.pos.y += (ty - r.pos.y) * k;
      r.pos.z += (tz - r.pos.z) * k;
      r.rq.slerp(r.q, 1 - Math.exp(-18 * dt));
    }
    r.fwd.set(0, 0, -1).applyQuaternion(r.rq);
    // The other two axes, for the ring of air the tow is drawn as. Off the
    // smoothed rotation rather than the raw packet, so it is the frame the car
    // is actually being drawn in and the streaks cannot sit at an angle to it.
    r.right.set(1, 0, 0).applyQuaternion(r.rq);
    r.up.set(0, 1, 0).applyQuaternion(r.rq);
    r.speed = r.vel.length();
    // `FLAG.SLIP` says which of the two things `sl` is - see sendPose. Zeroed
    // outright where there is no tow to have, so a boost that was running when
    // the lights went out on practice does not hang in the air over qualifying.
    const boosting = towOn && !!(r.flags & FLAG.SLIP);
    r.slipBoost = boosting ? r.tow * T.SLIP_BOOST : 0;
    r.slipCharge = boosting || !towOn ? 0 : r.tow;
    // Remote cars show their brake lights too, which is most of what tells you a
    // rival is slowing. Braking is the one flag that changes nothing else about
    // them: it is what a rival does in every corner, so a car that stopped being
    // drawn or stopped being solid for the length of a braking zone would blink
    // out and be driven through at exactly the moment you are closest to it.
    // Only RESPAWN takes a car off the track.
    const off = !!(r.flags & FLAG.RESPAWN);
    r.respawnIn = off ? 1 : 0;
    r.view.update(r.pos, r.rq, Object.assign({ spin: 0 }, lampsOf(r.flags)));
    r.view.group.visible = !off;
    // Solid cars are solid-looking, and the same question decides both: being
    // able to see through a rival is the only warning that you are about to
    // drive through one.
    r.view.setGhostly(!towOn);
    // Their air, in their own frame. Always stepped, even with the tow zeroed
    // above: that is what lets streaks already flying finish their run rather
    // than blinking out, which is the same thing your own car does.
    S.renderer.draft(r, dt, r.draftFx);
  }
}

/**
 * The other cars, as things to hear.
 *
 * Every car out there is a voice at its own position - engine, tyres, and the
 * tow winding up - so where somebody is is something you know before you look.
 * That matters most for the one place you cannot look: the car sitting in your
 * gearbox filling a slipstream is directly behind you, and the sound of it
 * arriving is the only warning you get.
 *
 * **Bounded by the same rule contact is**, `contactOn`: free practice and the
 * race, and nothing else. In qualifying everybody is alone on their own lap on a
 * road they are all using at different points of it, so a car howling past your
 * ear is somebody a corner behind you on their out lap - a rival you are not
 * racing, arriving as though you were. Hand back nothing there and the field
 * goes quiet on its own (see `Sound.rivals`).
 *
 * What a rival is doing comes off the flags already in its pose. There is no
 * throttle on the wire and there does not need to be one: a car that is not
 * braking and is not crawling is on the power, which is what an engine note has
 * to know. Sorted near-to-far, because only the closest few get a voice.
 */
function rivalSound() {
  if (!contactOn()) return null;
  const cam = S.renderer.camera.position;
  const out = [];
  for (const r of S.remotes.values()) {
    if (r.flags & FLAG.RESPAWN) continue;   // not on the track: nothing to hear
    const dx = r.pos.x - cam.x, dy = r.pos.y - cam.y, dz = r.pos.z - cam.z;
    out.push({
      id: r.pid, x: r.pos.x, y: r.pos.y, z: r.pos.z,
      d2: dx * dx + dy * dy + dz * dz,
      speedFrac: r.speed / T.MAX_SPEED,
      throttle: !(r.flags & FLAG.BRAKE) && r.speed > 3,
      drift: !!(r.flags & FLAG.DRIFT),
      air: !!(r.flags & FLAG.AIR),
      charge: r.slipCharge, boost: r.slipBoost / T.SLIP_BOOST,
    });
  }
  out.sort((a, b) => a.d2 - b.d2);
  return out;
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

/**
 * Is anybody being helped along for being behind right now?
 *
 * **The race and nothing else** - which makes this a deliberately different
 * answer from `contactOn`, the only other phase gate here, and the difference
 * is the whole justification for the mechanic. Catching up is help with a
 * *result*: there has to be a leader, a position to lose and a race that a
 * three-second gap would otherwise have decided. In free practice there is no
 * such thing as first place, in qualifying everybody is alone on their own lap
 * and the grid is the one thing the session exists to decide, and a countdown
 * or a results sheet has nobody driving. Handing out engine in any of them
 * would be a car going faster for no reason it could name.
 *
 * It never touches a leaderboard lap either, and by two independent rules: no
 * lap driven in a room counts (`countsForTheBoard`), and no lap driven outside
 * a race gets this at all.
 */
function catchupOn() {
  if (CFG.mode !== 'room') return false;
  return S.raceMode && S.racePhase === 'racing';
}

/**
 * How far behind the leader you are, in seconds, or null if that is not a
 * question this session is asking.
 *
 * **Measured in distance and reported in time.** What the room knows about
 * every car is `prog`, how far round it has got - it is on the wire already,
 * it is what the standings are ordered by, and it is the same number for
 * everybody. What a *gap* means, though, is time, and dividing by MAX_SPEED is
 * the honest conversion: how long it would take to make that ground up flat
 * out. Nobody averages MAX_SPEED, so the answer is a floor on the real gap -
 * which is the right way for it to be wrong, since it is deciding how much help
 * to hand out.
 *
 * **The leader here is the leader on the road**, not the winner. A car that is
 * already home is not being caught, and once it has crossed the line the race
 * left out there is for the places behind it - so a finisher is skipped, and
 * whoever is furthest round of those still driving sets the mark. If that is
 * you, the gap is zero and you get nothing, which is the same thing said twice.
 *
 * A car that has fallen off keeps its place until it drives back past where it
 * was, because `prog` is the best distance reached and not the current one.
 * That is on purpose: it is the number the standings on the screen are built
 * from, and a gap that disagreed with the board would be unexplainable.
 */
function gapToLeader() {
  if (!catchupOn()) return null;
  const home = new Set();
  for (const e of S.standings) if (e.ms != null && e.pid) home.add(e.pid);
  let lead = S.run.bestS;
  for (const [pid, r] of S.remotes) {
    if (home.has(pid)) continue;
    if (r.prog > lead) lead = r.prog;
  }
  return Math.max(0, lead - S.run.bestS) / T.MAX_SPEED;
}

/**
 * Does a lap driven right now belong on the leaderboard?
 *
 * **No lap driven in a room does.** There are other cars on the road in every
 * phase of one: a tow down a straight is worth the better part of a second,
 * contact moves you, and a race starts from a rolling grid rather than a
 * standing lap. A time set that way is a record of the traffic rather than of
 * the driving, and it was going on the board next to laps driven alone against
 * the clock - which is what a time trial is, and what /solo is for.
 *
 * One answer in one place, like `contactOn` and `ghostOn`, because the two
 * halves of a lap counting - the attempt and the time - must never disagree
 * about it.
 */
function countsForTheBoard() {
  return CFG.mode === 'solo';
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
  // The room's championship, shown for everybody or for nobody. A column that
  // appears on some rows reads as "these people are in it and you are not",
  // and before the first race of a session there is no table to show - so it
  // arrives when the first points are scored and then covers the room,
  // including the zeroes, because a zero next to somebody's four is the whole
  // information.
  const scoring = players.some(p => p.points);
  $('roster').innerHTML = players.map(p => `
    <div class="pl${CFG.me && p.pid === CFG.me.pid ? ' me' : ''}">
      <span class="st-dot" style="background:${esc(p.color)}"></span>
      <span class="pl-name">${esc(p.name)}</span>
      ${p.is_host ? '<span class="tag">HOST</span>' : ''}
      ${p.guest ? '<span class="tag guest">GUEST</span>' : ''}
      ${p.bot ? `<span class="tag lv lv-${esc(p.level || '')}">${esc((p.level || 'bot').toUpperCase())}</span>` : ''}
      <span class="pl-tail">
        ${p.elo != null ? `<span class="pl-elo">${p.elo}</span>` : ''}
        ${scoring ? `<span class="pl-pts" title="Points this session">${p.points || 0}</span>` : ''}
      </span>
      ${isHost && !p.is_host ? `<button class="kick" data-kick="${esc(p.pid)}">&times;</button>` : ''}
    </div>`).join('');
  $('roster').querySelectorAll('[data-kick]').forEach(b => {
    b.onclick = () => S.socket.emit('kick', { code: CFG.room, pid: b.dataset.kick });
  });
  renderBotControls(players, true);
  for (const [pid, r] of S.remotes) {
    const meta = players.find(p => p.pid === pid);
    // Same as `addRemote`: the plate colour is the car's business, not the
    // roster's, or a laurel holder loses their green the first time somebody
    // changes their display name.
    if (meta && meta.name !== r.name) { r.name = meta.name; r.view.setLabel(meta.name); }
  }
}

/**
 * The host's bot controls, under the roster.
 *
 * Hidden entirely for everybody else rather than shown disabled, which is the
 * opposite of what the qualifying switch does one panel down - and the
 * difference is what the two things *are*. Qualifying is a rule of the room
 * that everybody is about to race under, so everybody should be able to read
 * it. This is a way of adding a car, and a control you cannot press is only
 * worth showing when the state it displays is worth knowing.
 *
 * Disabled rather than hidden mid-race, because then the reason is temporary
 * and worth saying.
 */
function renderBotControls(players, fromRoster) {
  const box = $('botAdd');
  if (!box) return;
  if (!S.isHost || !CFG.bots) { box.style.display = 'none'; return; }
  box.style.display = '';
  const bots = players.filter(p => p.bot).length;
  const full = players.length >= (CFG.maxRoom || 8);
  const capped = bots >= (CFG.maxBots || 7);
  const live = ['qual_countdown', 'qualifying', 'countdown', 'racing']
    .includes(S.racePhase);
  // A roster is the answer to the fill - the cars asked for are now in the list
  // being drawn. Only a roster clears it: `applyPhase` also calls this, and
  // clearing on that would put the button back mid-flight for no reason.
  if (fromRoster && S.fillingBots) {
    S.fillingBots = false;
    clearTimeout(S.fillTimer);
  }
  const fill = $('btnFillBots');
  if (!S.fillingBots) { fill.classList.remove('busy'); setLabel(fill, 'Fill the grid'); }
  // Gone once there is nothing left to fill, rather than sitting there disabled:
  // "+ Bot" one line up already carries the reason in `botNote`, and a dead
  // control under a full grid is just something else to read.
  fill.style.display = (full || capped) ? 'none' : '';
  $('btnAddBot').disabled = full || capped || live;
  fill.disabled = full || capped || live || S.fillingBots;
  $('botNote').textContent =
    live ? 'Bots can be added between races.'
    : capped ? 'That is as many bots as a room takes.'
    : full ? 'Every seat is taken.'
    : bots ? bots + (bots === 1 ? ' bot in the room.' : ' bots in the room.')
    : 'Add cars to race against. They practise, qualify and race.';
}

// ---------------------------------------------------------------------------
// A track's own scenery, on a switch
// ---------------------------------------------------------------------------
// `tracks/<slug>/scenery.js` registers itself on `globalThis.DRIVE_SCENERY` and
// `buildTrack` reads it back out of there - see the comment block in
// trackmesh.js for why it is a global rather than an import. The play page
// inlines the file for the track you *arrive* on, which is the whole story for
// a page load and none of it for a switch: the switcher swaps the world without
// navigating, so the second track's scenery has to be fetched.
//
// **It is not decoration and a switch may not proceed without it.** Costco's
// building is 2834 wall triangles and Mount Joy's mountain is 14744 offroad
// ones - most of each track's solid geometry, and Mount Joy has no `ground`
// under it at all. A track built without its scenery is not a plainer version
// of that track, it is a different one, and a lap driven on it would go to
// /api/run as a time on this one.
//
// Still a classic `<script>` and not `import()`: the file is written to run at
// parse time and assign a global, and `buildTrack` is synchronous.
const sceneryLoads = new Map();       // slug -> the promise for its <script>

const sceneryReady = (slug) => !!(globalThis.DRIVE_SCENERY || {})[slug];

const trackCard = (slug) => (CFG.cards || []).find((c) => c.slug === slug);

function ensureScenery(slug) {
  // Already here: inlined by the page we arrived on, or fetched by an earlier
  // switch. The registry is keyed by slug and never emptied, so switching away
  // from the Costco and back costs nothing.
  if (sceneryReady(slug)) return Promise.resolve();
  // `scenery` rides down with the track summaries, so this is answerable before
  // the click - which is what lets the switch ask for the scenery and the track
  // payload at the same time instead of one after the other. A slug this page
  // has never heard of is *tried* rather than skipped: skipping is the silent
  // failure this whole function exists to stop.
  const card = trackCard(slug);
  if (card && !card.scenery) return Promise.resolve();
  if (sceneryLoads.has(slug)) return sceneryLoads.get(slug);
  const p = new Promise((ok, fail) => {
    const s = document.createElement('script');
    s.src = '/scenery/' + encodeURIComponent(slug) + '.js';
    // Loaded is not the same as registered - a file that parses and assigns
    // nothing leaves `buildTrack` exactly as badly off as no file at all.
    s.onload = () => (sceneryReady(slug) ? ok() : fail(new Error(slug)));
    s.onerror = () => fail(new Error(slug));
    document.head.appendChild(s);
  }).catch((e) => { sceneryLoads.delete(slug); throw e; });   // so a retry can work
  sceneryLoads.set(slug, p);
  return p;
}

/** Wait for the frame the caller's last DOM change is on to actually be drawn. */
const painted = () => new Promise((ok) =>
  requestAnimationFrame(() => requestAnimationFrame(ok)));

/**
 * Change the world to `slug`.
 *
 * `quiet` is for the switcher, whose card carries its own busy state - anywhere
 * else (a room's host picking for everybody, arriving into a room already on
 * another track) nothing on screen would otherwise explain the pause.
 *
 * Resolves true only if the switch actually happened, which is what tells the
 * switcher whether to close.
 */
async function switchTrack(slug, opts = {}) {
  const card = trackCard(slug);
  if (!opts.quiet) toast('Loading ' + (card ? card.name : 'track') + '...');
  try {
    // Together, not in sequence. A rejection here is a scenery we could not get,
    // and it lands in the catch below with everything else that means "no".
    const [t] = await Promise.all([
      fetch('/api/track/' + slug).then((r) => r.json()),
      ensureScenery(slug),
    ]);
    if (!t || t.error) { toast('Could not load that track'); return false; }
    // The guard that actually decides, because it reads the payload rather than
    // what this page knew about the pool when it booted. `ensureScenery` skips a
    // track its card says ships none; if that card is stale, this is what
    // catches it before the world is built wrong.
    if (t.scenery && !sceneryReady(slug)) {
      toast('Could not load ' + t.name);
      return false;
    }
    // Everything below is synchronous and the build is most of it - hundreds of
    // milliseconds on the big tracks, with the main thread locked for all of it.
    // So give the browser a frame to paint whatever said this was happening
    // before it stops being able to paint anything. Awaiting the fetch is
    // usually enough on its own; this is what makes it always enough.
    await painted();
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
    return true;
  } catch (e) { toast('Could not load that track'); return false; }
}

function onRaceStart(d) {
  S.raceMode = true;
  S.racePhase = 'countdown';
  S.raceDone = false;
  S.standings = [];
  S.raceSplits = {};        // this race's checkpoint times, nobody else's
  stopQualClock();
  // Qualifying is over, so the lap that was on provisional pole is not
  // provisional or pole any more - it is the grid. Keeping it loaded would put
  // last session's ghost on the road the next time the room practises.
  S.pole = null;
  if (S.ghostMode === 'pole') { S.ghost = null; S.ghostTimes = null; }
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
  S.raceT0 = S.cdT0 = performance.now() + (d.t0 - serverNow());
  countdownLoop();
}

/**
 * Line up behind the start line, in qualifying order.
 *
 * Staggered rather than square, and **pole is always on the inside of the first
 * corner**. Two things were wrong with the old two-by-two grid and only one of
 * them was the ordering: cars side by side at the same distance reach the first
 * corner together, so the one on the inside of it simply gets there.
 *
 * The stagger fixes the "at the same instant" half - the odd slot of each row
 * sits a car length back, F1 style, so the pair are not fighting for the same
 * metre of road at the same moment. The side used to be dealt with by
 * alternating it every race, on the grounds that nobody knew which side was the
 * good one, which meant half the time the car that qualified fastest lined up
 * on the outside of turn one and lost the place it had earned. The track knows
 * perfectly well which way it turns first (`pole_side`, worked out from the
 * ribbon in tracks.py), so pole simply gets that side, every race, everywhere.
 *
 * Pole keeps its advantage. It was earned in qualifying - or by being beaten
 * last time, in a room that does not qualify - and taking it away would make
 * either pointless.
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
  const inside = S.track.pole_side || -1;
  const side = (slot % 2 ? -inside : inside);
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
    if (!COUNTDOWN_PHASES.includes(S.racePhase)) { el.style.display = 'none'; return; }
    const left = (S.cdT0 - performance.now()) / 1000;
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
    // Two numbers in one cell: what this race paid, and the session total in
    // the same pill the room list wears - so the pill is recognisably one thing
    // in two places rather than two numbers to work out. The sheet covers the
    // drawer, which is why the total is here at all: after a race the
    // interesting question is who is winning the evening, and the answer would
    // otherwise be behind the thing telling you the result.
    const pts = (d.points || {})[e.pid];
    return `<div class="res-row${CFG.me && e.pid === CFG.me.pid ? ' me' : ''}">
      <span class="p">${i + 1}</span>
      <span class="st-dot" style="background:${esc(e.color || '#888')}"></span>
      <span class="nm">${esc(e.name)}</span>
      <span class="ms">${e.ms != null ? fmt(e.ms) : 'DNF'}</span>
      <span class="pt">${pts ? `<i>${pts.got ? '+' + pts.got : '0'}</i><b>${pts.total}</b>` : ''}</span>
      <span class="el${delta ? (delta.delta >= 0 ? ' up' : ' down') : ''}">${
        delta ? (delta.delta >= 0 ? '+' : '') + delta.delta : ''}</span>
    </div>`;
  }).join('');
  const mine = CFG.me ? (d.elo || {})[CFG.me.pid] : null;
  const elo = $('raceElo');
  elo.style.display = mine ? '' : 'none';
  if (mine) elo.innerHTML = `Rating ${mine.before} &rarr; <b>${mine.after}</b>`;
  // One line naming the two numbers in the column above, by showing your own -
  // the same job the rating line does, and the reason both are worth the room
  // they take: a bare `+4  12` on a row is a puzzle the first time you see it.
  const myPts = CFG.me ? (d.points || {})[CFG.me.pid] : null;
  const ptsLine = $('racePoints');
  ptsLine.style.display = myPts ? '' : 'none';
  if (myPts) ptsLine.innerHTML = `Points <b>+${myPts.got}</b> this race &middot; ` +
                                 `<b>${myPts.total}</b> this session`;
  // The race that has just been driven, watchable from any car in it. There is
  // no replay if nobody was on the road long enough to record one, and a button
  // leading to an empty one is worse than no button.
  S.lastRaceId = d.race || null;
  $('btnWatchRace').style.display = S.lastRaceId ? '' : 'none';
  $('raceOver').style.display = '';
  showHostOnly();
}

/**
 * The two things on the results sheet only the host can do.
 *
 * Going again and changing where - both of them are the host's, and the host
 * can change mid-race if the old one leaves, so they are shown from the same
 * place everything else phase-dependent is.
 */
function showHostOnly() {
  for (const id of ['btnRematch', 'btnRaceTrack']) {
    const b = $(id);
    if (b) b.style.display = S.isHost ? '' : 'none';
  }
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
