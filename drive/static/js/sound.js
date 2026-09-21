// All audio *except the music* is synthesised in the browser.
//
// The music is the one exception and it is a recent one: it used to be four
// synthesised bars under every track alike, and it is now a song per track,
// streamed from `/static/audio/` and looped by crossfade. That lives in its own
// file - see `music.js` - and arrives here only as a bus and two calls.
//
// The engine is two detuned sawtooths through a lowpass whose pitch tracks wheel
// speed, plus a separate whine that only comes up under load, which is what makes
// throttle feel connected. Everything else (clanks, sparks, beeps) is a short
// envelope on an oscillator or a noise burst.
//
// **Your own car is in the mix; every other car is in the world.** Yours goes
// straight to the effects bus, because it is the thing you are sitting in and
// has no direction to come from. A rival is a `RivalVoice` through its own
// panner at its own position, with the listener riding the chase camera - see
// `listener` and `rivals` below.
//
// **There are two buses under the master and that is what makes two switches
// possible.** Everything the car and the world make goes through `sfx`; the
// music goes through its own (owned by `MusicPlayer`), beside it rather than
// under it. Muting is the
// sfx bus's gain and not the master's, so turning the sound off leaves the
// music playing and turning the music off leaves the car audible - which is
// the only reading of two separate switches that is not a lie about one of
// them.
//
// Nothing is created until the first user gesture, so no browser ever warns about
// autoplay.

import { MusicPlayer, loadManifest, entryFor } from './music.js';

// A car nobody is driving goes quiet.
//
// The engine is a loop, and a loop under a stationary car is a drone that lasts
// as long as the tab does: park on the line, go and read something in another
// window, and the hum is still there an hour later. So the moment the car stops
// doing anything the engine starts going away, and any of throttle, movement or
// air brings it back inside two frames - a fade-in is a key press being
// answered late, so the way back is not a fade at all.
//
// **The curve is the whole of the design, and it is a straight line in dB.**
// `setTargetAtTime` decays exponentially in amplitude, which is 8.7dB per time
// constant however loud it started - and since hearing is logarithmic, constant
// dB per second is what a fade has to be to sound like one steady movement.
// (The obvious alternative, a straight line in amplitude, is the one thing that
// audibly does not work: it is only -6dB at its own halfway point and -20dB at
// nine tenths, so it holds near full level and then falls off a cliff at the
// end.) At IDLE_TC = 2 that is -6dB by a second and a half, half gone by three
// seconds, and inaudible around nine.
//
// **There is no hold before it starts, because the head of the curve is one.**
// Stopping for half a second - a wall, a spin, the top of a hairpin - costs
// 2dB and comes straight back, so the grace period a hold used to provide is
// already in the shape. It used to sit at full volume for five seconds and then
// drop in under three, which is the same total time arranged the worst way
// round: nothing happens, and then something obviously happens.
//
// **And it darkens as it goes, rather than only getting smaller.** Distance
// eats high frequencies first, and an engine coming off the load loses its
// top end for real - so the lowpass closes to IDLE_HZ on the way down and the
// load whine, which is the highest thing in the car, is given half the time
// constant and leaves first. What is left at the end is the bottom of the
// engine going away, which is what a car settling actually sounds like; gain
// on its own reads as somebody turning a knob.
const IDLE_TC = 2.0;      // the fade: -8.7dB a second constant, gone by about 9s
const WAKE_TC = 0.02;     // and back inside a couple of frames
const IDLE_SPEED = 0.02;  // of top speed: one unit a second, which is parked
const IDLE_HZ = 260;      // where the lowpass ends up: the bottom of the engine
const SLEEP_TC = 0.35;    // a hidden tab is not a resting car - see `sleep`

/** Throttle, movement above a crawl, or air. Anything else is a parked car. */
function isDriving(throttle, speedFrac, air) {
  return !!throttle || speedFrac > IDLE_SPEED || !!air;
}

export class Sound {
  constructor() {
    this.ctx = null;
    this.enabled = true;
    // Off until asked for, unlike the sound. The engine is what the game
    // sounds like and music over the top of it is a preference, so it is one
    // you turn on rather than one you turn off.
    this.musicOn = false;
    // Which track's song, and the manifest it is looked up in. Both are held
    // here rather than in the graph because both are set before the first user
    // gesture has built a context - `start` applies whatever it finds.
    this.musicSlug = null;
    this.manifest = null;
    this.onsong = null;
    this.ready = false;
    this.voices = new Map();     // pid -> RivalVoice, while they are audible
    this.engQuiet = false;       // faded last frame, so the way back is quick
  }

  start() {
    // Only when there is nothing at all to hear. It used to be `!this.enabled`
    // alone, which was the same thing when sound was the only switch and is
    // not now: somebody who drives muted with the music on still needs a
    // context built for it.
    if (this.ctx || (!this.enabled && !this.musicOn)) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = this.ctx = new AC();
    this.master = ctx.createGain();
    this.master.gain.value = 0.55;
    this.master.connect(ctx.destination);

    // Everything that is not music. Muting is this gain rather than the
    // master's, so the two switches in settings are actually two switches.
    this.sfx = ctx.createGain();
    this.sfx.gain.value = this.enabled ? 1 : 0;
    this.sfx.connect(this.master);

    // **The one recording in here**, fetched once the context exists and never
    // waited on. If it 404s or fails to decode, `thunder()` falls back to the
    // synthesised strike, so a checkout without it - or a box where the file
    // did not land - is quieter rather than broken. See
    // `static/audio/sfx/CREDITS.md` for what it is and whose it is.
    for (const [name, key] of [['thunder', 'thunderBuf'], ['ghost', 'ghostBuf']]) {
      fetch('/static/audio/sfx/' + name + '.ogg')
        .then(r => (r.ok ? r.arrayBuffer() : Promise.reject(r.status)))
        .then(b => ctx.decodeAudioData(b))
        .then(buf => { this[key] = buf; })
        .catch(() => { this[key] = null; });
    }

    // --- engine ----------------------------------------------------------
    this.engGain = ctx.createGain();
    this.engGain.gain.value = 0;
    this.engFilter = ctx.createBiquadFilter();
    this.engFilter.type = 'lowpass';
    this.engFilter.frequency.value = 900;
    this.engFilter.Q.value = 1.2;
    this.engGain.connect(this.engFilter).connect(this.sfx);

    this.osc = [];
    for (const detune of [0, 7, -11]) {
      const o = ctx.createOscillator();
      o.type = 'sawtooth';
      o.frequency.value = 60;
      o.detune.value = detune;
      const g = ctx.createGain();
      g.gain.value = detune === 0 ? 0.6 : 0.28;
      o.connect(g).connect(this.engGain);
      o.start();
      this.osc.push(o);
    }
    // load whine, an octave and a fifth up
    this.whine = ctx.createOscillator();
    this.whine.type = 'triangle';
    this.whine.frequency.value = 180;
    this.whineGain = ctx.createGain();
    this.whineGain.gain.value = 0;
    this.whine.connect(this.whineGain).connect(this.sfx);
    this.whine.start();

    // --- tyres -----------------------------------------------------------
    this.noise = ctx.createBufferSource();
    this.noise.buffer = whiteNoise(ctx, 2);
    this.noise.loop = true;
    this.tyreFilter = ctx.createBiquadFilter();
    this.tyreFilter.type = 'bandpass';
    this.tyreFilter.frequency.value = 1700;
    this.tyreFilter.Q.value = 2.2;
    this.tyreGain = ctx.createGain();
    this.tyreGain.gain.value = 0;
    this.noise.connect(this.tyreFilter).connect(this.tyreGain).connect(this.sfx);
    this.noise.start();

    // --- wind ------------------------------------------------------------
    this.wind = ctx.createBufferSource();
    this.wind.buffer = whiteNoise(ctx, 2);
    this.wind.loop = true;
    this.windFilter = ctx.createBiquadFilter();
    this.windFilter.type = 'lowpass';
    this.windFilter.frequency.value = 620;
    this.windGain = ctx.createGain();
    this.windGain.gain.value = 0;
    this.wind.connect(this.windFilter).connect(this.windGain).connect(this.sfx);
    this.wind.start();

    // --- slipstream ------------------------------------------------------
    // The tow has its own air, separate from the wind: a narrow band that opens
    // up as the charge fills, so you can hear it coming before it arrives.
    this.draftSrc = ctx.createBufferSource();
    this.draftSrc.buffer = whiteNoise(ctx, 2);
    this.draftSrc.loop = true;
    this.draftFilter = ctx.createBiquadFilter();
    this.draftFilter.type = 'bandpass';
    this.draftFilter.frequency.value = 500;
    this.draftFilter.Q.value = 3.2;
    this.draftGain = ctx.createGain();
    this.draftGain.gain.value = 0;
    this.draftSrc.connect(this.draftFilter).connect(this.draftGain).connect(this.sfx);
    this.draftSrc.start();

    // --- other cars ------------------------------------------------------
    // One bus for every rival, so the whole field can be pulled down against
    // your own car without touching eight voices. It sits under the sfx bus,
    // so muting still mutes the whole field.
    this.rivalBus = ctx.createGain();
    this.rivalBus.gain.value = RIVAL_BUS;
    this.rivalBus.connect(this.sfx);

    // --- music -----------------------------------------------------------
    // Beside the sfx bus rather than under it, so the two switches are two
    // switches. Built even when it is switched off: it is three nodes and two
    // `<audio>` elements that have not been given a `src`.
    this.music = new MusicPlayer(ctx, this.master, {
      onsong: (e) => { if (this.onsong) this.onsong(e); },
    });
    // The manifest is fetched once and may land after the context is built, so
    // the song is applied whenever both are ready rather than in either order.
    loadManifest().then((m) => {
      this.manifest = m;
      this._applySong();
    });
    this.music.enable(this.musicOn);

    this.ready = true;
  }

  resume() { if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume(); }

  /**
   * The tab went away, and took the frame loop with it.
   *
   * Every gain in here is moved by `engine`, `draft` and `rivals`, all three
   * of which are called from the frame loop - and rAF stops in a hidden tab
   * while the audio clock carries on. So an alt-tab at full speed used to
   * leave all of them frozen exactly where the last frame put them, and the
   * car you are no longer driving roared on behind whatever you had gone to
   * look at. The idle fade cannot cover this: it is driven from the same loop.
   *
   * Faded rather than muted, and the sfx bus is deliberately left alone - that
   * gain belongs to the mute switch, and two things writing one gain is how a
   * mute ends up stuck on.
   *
   * **Quicker than the idle fade** (SLEEP_TC against IDLE_TC), because the two
   * are not the same event. A resting car is still on the screen and settling
   * gently is what it should do; a hidden tab is somebody who has gone, and a
   * couple of seconds of the race they walked out of is enough.
   */
  sleep() {
    if (!this.ready) return;
    const t = this.ctx.currentTime;
    for (const p of [this.engGain.gain, this.whineGain.gain, this.tyreGain.gain,
                     this.windGain.gain, this.draftGain.gain, this.rivalBus.gain]) {
      p.setTargetAtTime(0, t, SLEEP_TC);
    }
    // So the first frame back opens up quickly rather than crossfading from
    // whatever was left of the fade.
    this.engQuiet = true;
  }

  /**
   * Frames again. Only the rival bus is put back by hand; everything else is
   * written every frame by the calls that faded, so the first frame restores
   * it - and restores it to what the car is doing *now* rather than to what it
   * was doing when the tab went away.
   */
  wake() {
    if (!this.ready) return;
    this.rivalBus.gain.setTargetAtTime(RIVAL_BUS, this.ctx.currentTime, 0.05);
  }

  mute(m) {
    this.enabled = !m;
    if (this.sfx) this.sfx.gain.value = m ? 0 : 1;
  }

  /**
   * The music switch, which is not the sound switch.
   *
   * Held on the instance rather than in the graph, because it is set from the
   * stored preference before the first user gesture has built a context at
   * all - `start` applies whatever it finds here.
   */
  setMusic(on) {
    this.musicOn = on;
    if (this.music) this.music.enable(on);
  }

  /**
   * Which track we are on, and so which song plays.
   *
   * Called on entering a track and again every time the switcher swaps worlds
   * without a navigation - the play page changes track underneath itself, so
   * this cannot be a page-load decision.
   */
  setSong(slug) {
    this.musicSlug = slug;
    this._applySong();
  }

  /** Both halves present? Then hand the song over. Either order is fine. */
  _applySong() {
    if (!this.music || !this.manifest) return;
    this.music.setSong(entryFor(this.manifest, this.musicSlug));
  }

  /**
   * What is playing, for the now-playing card. Null when there is no context
   * yet, no manifest yet, or no song for this track - all three of which are
   * "show nothing" rather than anything to report.
   */
  currentSong() {
    return (this.music && this.music.entry) || null;
  }

  /**
   * Wind the music on, from the frame loop.
   *
   * All this turns now is the crossfade: `MusicPlayer.tick` watches the active
   * deck's clock for the loop point. The thing already running at 60Hz is the
   * frame loop, so that is what turns the handle. It is called *before* the
   * early returns for a replay and a preview shot, since music is the one
   * thing that should not stop because you are watching somebody else's lap.
   */
  musicTick() {
    if (this.music) this.music.tick();
  }

  /** Called every frame with the car's state. */
  engine(speedFrac, throttle, slip, airborne) {
    if (!this.ready) return;
    const t = this.ctx.currentTime;
    const set = (p, v, tc = 0.06) => p.setTargetAtTime(v, t, tc);
    // Stopped, nobody's foot down, wheels on the ground: the one state that is
    // making a noise for nothing, and so the one state that stops making it.
    const on = isDriving(throttle, speedFrac, airborne);
    const gTc = on ? (this.engQuiet ? WAKE_TC : 0.09) : IDLE_TC;
    this.engQuiet = !on;
    const rpm = 58 + speedFrac * 210 + (throttle ? 22 : 0);
    for (const o of this.osc) set(o.frequency, rpm, 0.05);
    set(this.engFilter.frequency,
        on ? 620 + speedFrac * 2400 + (throttle ? 500 : 0) : IDLE_HZ, on ? 0.08 : IDLE_TC);
    set(this.engGain.gain, on ? (airborne ? 0.08 : 0.15 + throttle * 0.1) : 0, gTc);
    set(this.whine.frequency, rpm * 3.02, 0.05);
    // Half the time constant, so the top of the car is gone while the bottom
    // of it is still going.
    set(this.whineGain.gain,
        on ? (throttle ? 0.034 : 0.009) * (0.4 + speedFrac) : 0,
        on ? 0.1 : IDLE_TC * 0.5);
    set(this.tyreGain.gain, airborne ? 0 : Math.min(0.3, slip * 0.34), 0.05);
    set(this.tyreFilter.frequency, 1300 + slip * 1400, 0.08);
    set(this.windGain.gain, Math.min(0.16, speedFrac * speedFrac * 0.2), 0.12);
    set(this.windFilter.frequency, 420 + speedFrac * 1500, 0.1);
  }

  _blip({ freq = 660, type = 'square', dur = 0.12, gain = 0.22, to = null, delay = 0 }) {
    if (!this.ready) return;
    const ctx = this.ctx, t = ctx.currentTime + delay;
    const o = ctx.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(freq, t);
    if (to) o.frequency.exponentialRampToValueAtTime(Math.max(30, to), t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(this.sfx);
    o.start(t);
    o.stop(t + dur + 0.02);
  }

  _burst({ dur = 0.14, gain = 0.3, freq = 2200, q = 1.1, type = 'bandpass' }) {
    if (!this.ready) return;
    const ctx = this.ctx, t = ctx.currentTime;
    const s = ctx.createBufferSource();
    s.buffer = whiteNoise(ctx, Math.max(0.2, dur + 0.05));
    const f = ctx.createBiquadFilter();
    f.type = type; f.frequency.value = freq; f.Q.value = q;
    const g = ctx.createGain();
    g.gain.setValueAtTime(gain, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    s.connect(f).connect(g).connect(this.sfx);
    s.start(t);
    s.stop(t + dur + 0.05);
  }

  // A car-to-car hit: a metallic clank whose pitch and level scale with how hard
  // it was, so a light rub and a proper punt sound like different events.
  bump(mag) {
    const f = Math.min(1, mag / 26);
    this._blip({ freq: 420 - f * 110, to: 120, type: 'square', dur: 0.1 + f * 0.1,
                 gain: 0.09 + f * 0.2 });
    this._burst({ freq: 2600, q: 0.8, dur: 0.07 + f * 0.07, gain: 0.1 + f * 0.16 });
  }

  /**
   * The tow itself, every frame: rushing air that fills with the charge.
   *
   * The point of it is that you can *hear* the boost coming - the band opens
   * and rises as the tow fills, so sitting behind somebody is a sound that goes
   * somewhere rather than a bar you have to look down at. While the boost pays
   * it is wide open, and it falls away with the boost rather than stopping.
   */
  draft(charge, boostFrac) {
    if (!this.ready) return;
    const t = this.ctx.currentTime;
    const set = (p, v, tc = 0.09) => p.setTargetAtTime(v, t, tc);
    const boosting = boostFrac > 0;
    const a = boosting ? Math.pow(boostFrac, 0.45) : Math.min(1, charge);
    set(this.draftGain.gain, a * (boosting ? 0.15 : 0.075), 0.08);
    set(this.draftFilter.frequency, 420 + a * (boosting ? 2600 : 1500), 0.1);
    set(this.draftFilter.Q, boosting ? 1.3 : 3.4, 0.12);
  }

  // The tow letting go: a rising whoosh with a bright top on it. It has to be
  // unmistakable, because the boost arrives without anybody pressing anything.
  slipstream() {
    this._blip({ freq: 260, to: 1000, type: 'sawtooth', dur: 0.34, gain: 0.13 });
    this._blip({ freq: 520, to: 1560, type: 'square', dur: 0.3, gain: 0.09, delay: 0.03 });
    this._burst({ freq: 1900, q: 0.5, dur: 0.3, gain: 0.12 });
  }

  /**
   * A boost pad. Deliberately not `slipstream()`, though both are a boost.
   *
   * A tow is something you built up and were finally paid for, so it rises -
   * you hear it coming and then it lets go. A pad is something the road did to
   * you the instant you touched it, so this drops instead: a hard bright hit
   * that falls away, and short enough to land inside the moment you crossed the
   * chevrons rather than trailing over the road after them. Two sounds that
   * both mean "faster" have to be told apart in the half second you have.
   */
  boostPad() {
    this._blip({ freq: 1180, to: 300, type: 'square', dur: 0.22, gain: 0.13 });
    this._blip({ freq: 590, to: 160, type: 'sawtooth', dur: 0.26, gain: 0.1 });
    this._burst({ freq: 3200, q: 0.7, dur: 0.16, gain: 0.14 });
  }

  /**
   * A mushroom cap throwing the car.
   *
   * Sweeps **up** where every other event here sweeps down, which is the whole
   * of what makes it read as a launch rather than as an impact - a landing, a
   * bump and a wall are all falling pitches, and a rising one is the only thing
   * in the mix that says the car went somewhere good. `mag` is the launch speed,
   * so a hard arrival onto a cap is both higher and louder than a gentle one,
   * the same way `bump` scales off its magnitude.
   */
  bounce(mag) {
    const k = Math.min(1, (mag || 21) / 30);
    this._blip({ freq: 240, to: 760 + 260 * k, type: 'sine', dur: 0.2,
                 gain: 0.11 + 0.05 * k });
    this._blip({ freq: 120, to: 380, type: 'triangle', dur: 0.26, gain: 0.09 });
  }

  /**
   * Where the ears are.
   *
   * They ride the **chase camera**, not the car, because the camera is where you
   * are watching the race from - and it is the only frame in which "on my left"
   * is the same statement on screen and in the headphones. It follows the car
   * through a loop, so this needs no special case for being upside down either:
   * the listener's up vector rolls with it and a rival above you stays above you.
   *
   * Taken off the camera's own quaternion rather than its world matrix, since
   * `lookAt` writes the quaternion immediately and the matrix is not recomputed
   * until the scene is drawn - a frame later than this is called.
   */
  listener(camera) {
    if (!this.ready || !camera) return;
    const L = this.ctx.listener, t = this.ctx.currentTime;
    const p = camera.position, q = camera.quaternion;
    const f = _rot(q, 0, 0, -1), u = _rot(q, 0, 1, 0);
    if (L.positionX) {
      // Smoothed, because a camera that is itself smoothing can still step on a
      // respawn, and a listener that jumps clicks.
      const set = (prm, v) => prm.setTargetAtTime(v, t, 0.02);
      set(L.positionX, p.x); set(L.positionY, p.y); set(L.positionZ, p.z);
      set(L.forwardX, f[0]); set(L.forwardY, f[1]); set(L.forwardZ, f[2]);
      set(L.upX, u[0]); set(L.upY, u[1]); set(L.upZ, u[2]);
    } else if (L.setPosition) {
      L.setPosition(p.x, p.y, p.z);
      L.setOrientation(f[0], f[1], f[2], u[0], u[1], u[2]);
    }
  }

  /**
   * Every other car that is making a noise right now, in one call.
   *
   * The list is the whole state: a car in it gets a voice (built on the spot the
   * first time), a car that drops out of it loses one. That is what makes the
   * phase rule free - the caller hands over nothing at all in qualifying and the
   * field goes quiet on its own, and the same happens when the room empties, the
   * track is switched, or a replay takes the screen.
   *
   * Capped, and the caller sorts by distance, so a full grid seen from the back
   * spends its voices on the cars close enough to be worth hearing.
   */
  rivals(list) {
    if (!this.ready) return;
    const t = this.ctx.currentTime;
    const seen = new Set();
    for (const r of (list || []).slice(0, MAX_RIVAL_VOICES)) {
      seen.add(r.id);
      let v = this.voices.get(r.id);
      if (!v) { v = new RivalVoice(this.ctx, this.rivalBus); this.voices.set(r.id, v); }
      v.update(r, t);
    }
    for (const [id, v] of this.voices) {
      if (!seen.has(id)) { v.dispose(); this.voices.delete(id); }
    }
  }

  wall(mag) {
    const f = Math.min(1, mag / 26);
    this._burst({ freq: 900, q: 0.6, dur: 0.12 + f * 0.1, gain: 0.1 + f * 0.15 });
    this._blip({ freq: 150, to: 70, type: 'triangle', dur: 0.16, gain: 0.06 + f * 0.1 });
  }

  land(airTime) {
    const f = Math.min(1, airTime / 1.4);
    this._burst({ freq: 400 + f * 300, q: 0.5, dur: 0.1 + f * 0.1, gain: 0.09 + f * 0.16 });
  }

  checkpoint() {
    this._blip({ freq: 880, type: 'square', dur: 0.1, gain: 0.2 });
    this._blip({ freq: 1320, type: 'square', dur: 0.12, gain: 0.16, delay: 0.07 });
  }

  /**
   * Driving through an item box: a bright rising pair, and it is the same
   * shape as `checkpoint` on purpose - both are "you got the thing" - but a
   * fifth up and softer, so hearing them together on a track where a box sits
   * near a gate is two events rather than one loud one.
   */
  itemBox() {
    this._blip({ freq: 720, to: 1080, type: 'triangle', dur: 0.09, gain: 0.16 });
    this._blip({ freq: 1440, type: 'sine', dur: 0.14, gain: 0.1, delay: 0.05 });
  }

  /** The slot filling: one short note under the box's own, so a full queue is
      audibly different from driving through with both hands occupied. */
  itemGot() {
    this._blip({ freq: 990, to: 1320, type: 'square', dur: 0.1, gain: 0.12 });
  }

  /**
   * The items, one voice each, because an item you cannot tell apart by ear is
   * an item you have to look at the HUD to know you fired.
   *
   * The two shells share theirs on purpose - they *are* the same object thrown
   * two ways, and the difference between them is who it goes after, which the
   * sound cannot say anyway. The blue gets its own because it is the one
   * everybody in the room has an opinion about.
   */
  itemShell() {
    this._blip({ freq: 520, to: 980, type: 'square', dur: 0.12, gain: 0.15 });
    this._burst({ freq: 2400, q: 1.2, dur: 0.07, gain: 0.07 });
  }

  itemBlue() {
    this._blip({ freq: 180, to: 520, type: 'sawtooth', dur: 0.5, gain: 0.16 });
    this._blip({ freq: 90, to: 260, type: 'triangle', dur: 0.55, gain: 0.12, delay: 0.02 });
  }

  itemBanana() {
    this._blip({ freq: 320, to: 180, type: 'sine', dur: 0.14, gain: 0.16 });
    this._burst({ freq: 900, q: 0.7, dur: 0.06, gain: 0.05 });
  }

  itemShield() {
    this._blip({ freq: 420, to: 840, type: 'sine', dur: 0.28, gain: 0.14 });
    this._blip({ freq: 630, to: 1260, type: 'sine', dur: 0.32, gain: 0.08, delay: 0.06 });
  }

  /**
   * The star, which is the only item that gets a *tune* rather than a noise -
   * and it plays over and over for as long as the star lasts, so it has to be
   * a bar rather than a flourish: eight notes, a run up and a skip back down,
   * with a fifth under the first half to give it some weight. Loud on purpose.
   * It is the one moment in this game where you are untouchable and everybody
   * else can hear that you are.
   */
  itemStar() {
    const bar = [[784, 0], [1047, 0.075], [1319, 0.15], [1568, 0.225],
                 [1319, 0.3], [1568, 0.375], [2093, 0.45], [1568, 0.525]];
    for (const [f, t] of bar) {
      this._blip({ freq: f, type: 'square', dur: 0.1, gain: 0.2, delay: t });
      if (t < 0.3) this._blip({ freq: f / 2, type: 'triangle', dur: 0.12,
                                gain: 0.12, delay: t });
    }
  }

  /** Lobbing a bomb: a heavy underarm thunk, nothing like a shell's snap. */
  itemBomb() {
    this._blip({ freq: 260, to: 150, type: 'triangle', dur: 0.18, gain: 0.17 });
    this._burst({ freq: 700, q: 0.5, dur: 0.1, gain: 0.06 });
  }

  /** And it going off, which everybody in earshot hears. */
  bombBlast() {
    this._burst({ freq: 180, q: 0.3, dur: 0.45, gain: 0.32 });
    this._burst({ freq: 900, q: 0.4, dur: 0.16, gain: 0.16 });
    this._blip({ freq: 140, to: 40, type: 'sawtooth', dur: 0.5, gain: 0.2 });
  }

  /** A held item taking a hit for you: a solid knock, and then nothing. */
  itemBlocked() {
    this._burst({ freq: 520, q: 0.5, dur: 0.14, gain: 0.2 });
    this._blip({ freq: 880, to: 620, type: 'square', dur: 0.1, gain: 0.1 });
  }

  /**
   * Something hit you, in three layers, because one burst was a door closing.
   *
   * The impact itself is the low thump; over it a bright metallic crack, which
   * is what makes it read as *hit by a thing* rather than as driving into
   * scenery; and under both a note that slides down and away, which is the
   * part that says the next two seconds are not yours. A wall gets a shorter,
   * duller version of the first two - the difference has to be audible, since
   * one of them is your own fault and the other is somebody's shell.
   */
  itemHit() {
    this._burst({ freq: 190, q: 0.3, dur: 0.3, gain: 0.34 });
    this._burst({ freq: 2600, q: 2.0, dur: 0.12, gain: 0.2 });
    this._blip({ freq: 520, to: 70, type: 'sawtooth', dur: 0.45, gain: 0.2 });
    this._blip({ freq: 260, to: 40, type: 'triangle', dur: 0.5, gain: 0.14,
                 delay: 0.03 });
  }

  /**
   * A shell is closing on you: one ping, pitched by how close it is.
   *
   * The *rate* is the caller's - see `shellWarning` in game.js - because what
   * makes this readable is the gaps getting shorter, and only the caller knows
   * how far away the thing is on any given frame.
   */
  shellNear(closeness) {
    const k = Math.min(1, Math.max(0, closeness));
    this._blip({ freq: 700 + k * 700, type: 'square', dur: 0.07,
                 gain: 0.05 + k * 0.13 });
  }

  missed() {
    this._blip({ freq: 300, to: 180, type: 'sawtooth', dur: 0.3, gain: 0.16 });
  }

  fall() {
    this._blip({ freq: 500, to: 90, type: 'triangle', dur: 0.55, gain: 0.18 });
  }

  respawn() {
    this._blip({ freq: 400, to: 800, type: 'square', dur: 0.14, gain: 0.14 });
  }

  countdown(n) {
    if (n > 0) this._blip({ freq: 520, type: 'square', dur: 0.16, gain: 0.24 });
    else {
      this._blip({ freq: 1040, type: 'square', dur: 0.4, gain: 0.3 });
      this._blip({ freq: 1560, type: 'square', dur: 0.4, gain: 0.16, delay: 0.02 });
    }
  }

  finish(medal) {
    // Gold is the top medal, so it gets the top of the fanfare.
    const notes = medal === 'gold' ? [523, 659, 784, 1047, 1319]
                : medal ? [523, 659, 784] : [523, 659];
    notes.forEach((f, i) => this._blip({ freq: f, type: 'triangle', dur: 0.26,
                                        gain: 0.22, delay: i * 0.1 }));
  }

  record() {
    [784, 988, 1175, 1568].forEach((f, i) =>
      this._blip({ freq: f, type: 'square', dur: 0.3, gain: 0.2, delay: i * 0.09 }));
  }

  /**
   * A candle catching, as you come up on it.
   *
   * **The quietest thing on this bus by a distance**, and it has to be: BOO!
   * has a hundred and sixty candles on it and the pool lights eight of them at
   * a time, so at racing speed this fires two or three times a second down the
   * nave. Anything with a transient you could name would be a machine gun. What
   * is left is a breath of noise with no click on the front of it - 25ms of
   * attack, which is slow enough that the ear takes it as air rather than as an
   * event - and a tap of resonance under it for the wick.
   *
   * Quiet, but **measured quiet rather than assumed quiet** - about half the
   * RMS of the checkpoint chime, where the first pass was a fifth of it and
   * inaudible under the engine.
   *
   * Rate limiting lives in `Lamps`, not here: this is a sound, and how often a
   * sound is allowed is a fact about the candles.
   */
  candle() {
    if (!this.ready) return;
    const ctx = this.ctx, t = ctx.currentTime, DUR = 0.34;
    const src = ctx.createBufferSource();
    src.buffer = whiteNoise(ctx, DUR);
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass'; bp.Q.value = 0.8;
    bp.frequency.setValueAtTime(2600, t);
    bp.frequency.exponentialRampToValueAtTime(900, t + DUR);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.24, t + 0.025);
    g.gain.exponentialRampToValueAtTime(0.0001, t + DUR);
    src.connect(bp).connect(g).connect(this.sfx);
    src.start(t); src.stop(t + DUR);

    // The wick: one soft partial, detuned a little each time so a row of
    // candles down one wall is a row of different candles.
    const o = ctx.createOscillator();
    o.type = 'triangle';
    o.frequency.value = 430 + Math.random() * 120;
    const og = ctx.createGain();
    og.gain.setValueAtTime(0.0001, t);
    og.gain.exponentialRampToValueAtTime(0.13, t + 0.03);
    og.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
    o.connect(og).connect(this.sfx);
    o.start(t); o.stop(t + 0.24);
  }

  /**
   * A ghost, as you go by it: the high staccato giggle a Boo has.
   *
   * **The reference is Nintendo's and the sound is not.** That laugh cannot be
   * shipped - it is their recording on a public site - so what is copied is its
   * *shape*, which is not ownable and is anyway most of what makes it read:
   *
   *  * **High.** A Boo is a pitched-up voice, about an octave over a talking
   *    one. This sits at 520-660Hz where the first attempt sat at 300, and that
   *    single number is the difference between a giggle and a man chuckling in
   *    a cellar.
   *  * **Fast and staccato.** Five or six bursts about 85ms apart, each one
   *    ~55ms long with almost no tail. Three slow ones read as a laugh being
   *    described rather than a laugh.
   *  * **Bright and nasal.** Three formants, not two: 520 / 2400 / 3300. The
   *    third is what gives it the cartoon edge - two alone is a vowel, three is
   *    a *voice*, and a nasal one because the second and third sit close.
   *  * **Bouncy, then gone.** Each burst lifts about 8% in pitch across itself,
   *    which is the "heh" rather than "hunh", and the last one falls away
   *    instead of ending flat.
   *
   * The formant bank costs most of what goes into it - see the gains, which
   * look enormous and measure at about the level of the record fanfare.
   */
  ghost() {
    if (!this.ready) return;
    const ctx = this.ctx, t = ctx.currentTime;
    const rnd = (a, b) => a + Math.random() * (b - a);

    // **A recording, and it is Chinmay laughing into a phone with the speed
    // wound up.** Which is how this kind of sound has always been made: a Boo
    // is a person going "hehehe" played fast, and every synthesised attempt
    // below - three of them, each measured and each louder than the last -
    // sounded like a synthesiser going "hehehe". The file is trimmed, denoised,
    // resampled to 1.45x (so it is higher *and* quicker, which is the whole
    // trick) and normalised; see `static/audio/sfx/CREDITS.md`.
    //
    // A little rate jitter per ghost, because two of them passing within a few
    // seconds should not be the same laugh twice.
    if (this.ghostBuf) {
      const src = ctx.createBufferSource();
      src.buffer = this.ghostBuf;
      src.playbackRate.value = rnd(0.95, 1.1);
      const g = ctx.createGain();
      g.gain.value = rnd(0.85, 1.0);
      src.connect(g).connect(this.sfx);
      src.start(t);
      return;
    }
    const f0 = rnd(520, 660);
    const n = 4 + (Math.random() < 0.5 ? 1 : 2);   // five or six "heh"s
    const gap = rnd(0.078, 0.095);
    const HE = rnd(0.05, 0.062);
    const end = n * gap + 0.28;

    const osc = ctx.createOscillator();
    osc.type = 'sawtooth';
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, t);

    // Three formants in parallel. The third is the cartoon in it.
    const bank = [[520, 6, 1.0], [2400, 9, 0.75], [3300, 11, 0.45]].map(([f, q, g]) => {
      const bp = ctx.createBiquadFilter();
      bp.type = 'bandpass'; bp.frequency.value = f; bp.Q.value = q;
      const lvl = ctx.createGain(); lvl.gain.value = g;
      osc.connect(bp).connect(lvl).connect(env);
      return bp;
    });

    for (let i = 0; i < n; i++) {
      const at = t + i * gap;
      const last = i === n - 1;
      const base = f0 * (1 - 0.02 * i);
      // Up across the burst - "heh" - and the last one drops away instead.
      osc.frequency.setValueAtTime(base, at);
      osc.frequency.exponentialRampToValueAtTime(last ? base * 0.72 : base * 1.08,
                                                 at + (last ? 0.26 : HE));
      env.gain.setValueAtTime(0.0001, at);
      env.gain.exponentialRampToValueAtTime(last ? 1.15 : 0.95, at + 0.012);
      env.gain.exponentialRampToValueAtTime(0.0001, at + (last ? 0.27 : HE));
      if (last) {
        // The vowel opens on the way out, which is the "haw" at the end of it.
        bank[0].frequency.setValueAtTime(520, at);
        bank[0].frequency.exponentialRampToValueAtTime(700, at + 0.22);
        bank[1].frequency.setValueAtTime(2400, at);
        bank[1].frequency.exponentialRampToValueAtTime(1500, at + 0.22);
      }
    }

    env.connect(this.sfx);
    osc.start(t); osc.stop(t + end + 0.05);

    // A breath on each burst, quiet and high - the "h", and the only thing
    // keeping it from sounding like a synthesiser playing a tune.
    const src = ctx.createBufferSource();
    src.buffer = whiteNoise(ctx, end + 0.1);
    const bf = ctx.createBiquadFilter();
    bf.type = 'bandpass'; bf.Q.value = 1.0; bf.frequency.value = 2800;
    const bg = ctx.createGain();
    bg.gain.setValueAtTime(0.0001, t);
    for (let i = 0; i < n; i++) {
      const at = t + i * gap;
      bg.gain.setValueAtTime(0.0001, at);
      bg.gain.exponentialRampToValueAtTime(0.09, at + 0.008);
      bg.gain.exponentialRampToValueAtTime(0.0001, at + HE * 0.8);
    }
    src.connect(bf).connect(bg).connect(this.sfx);
    src.start(t); src.stop(t + end + 0.05);
  }

  /**
   * Thunder: a strike that is close, and then a roll that takes six seconds to
   * get out of the churchyard.
   *
   * **This is built off what a real close strike does, because the first
   * version was built off what thunder is imagined to do** - one crack, one
   * three-second hiss under it, both smooth. Smooth is what gives a synthesised
   * strike away: nothing in the real event has a clean envelope on it.
   *
   * What a recording of a strike a few hundred metres away actually has in it,
   * in order, and every one of them is here:
   *
   *  * **A rip, not a crack.** The return stroke is a channel kilometres long
   *    and its sound does not arrive all at once - the near part of the channel
   *    reaches you before the far part, so the front of it is a burst of three
   *    or four separate cracks tens of milliseconds apart. One crack is a
   *    gunshot; three is lightning.
   *  * **A thump you feel.** A sine falling to the high twenties under the
   *    rip. This is most of what "close" means, and it is the part a laptop
   *    speaker will not give you at all - which is fine, it is for the people
   *    on headphones.
   *  * **A roll that wanders.** The tail is not a decay, it is a sequence of
   *    arrivals off cloud base and terrain, so its level goes *up* as often as
   *    down for the first few seconds. That is done here as a random walk
   *    written into the gain a step at a time, and it is the single thing that
   *    makes this read as a recording rather than as a filter closing.
   *  * **No two the same.** Every number below is jittered per strike. A
   *    repeated identical crack is the other thing that gives a synth away, and
   *    this track fires the same spot every lap.
   *
   * The filter still closes over the tail - 700Hz down to 55 - because that is
   * air, and it is the one part of the old version that was right.
   *
   * Loudest thing on the bus, deliberately, but on `sfx` like everything else,
   * so the mute switch covers it and the music's path is untouched.
   */
  thunder() {
    if (!this.ready) return;
    const ctx = this.ctx, t = ctx.currentTime;

    // **A real strike, when we have one.** Everything else this game plays is
    // synthesised and thunder is the one place that does not work: the whole
    // character of a close strike is in how ragged it is - the rip, the slap
    // back off the ground, the roll wandering as it goes - and the synth below
    // is an imitation of that shape rather than the thing. Three passes of
    // tuning it got nowhere, which is the tell.
    //
    // Pitched down a little and varied per strike, so the same file fired every
    // lap is not the same sound every lap: a semitone of drift is inaudible as
    // pitch and completely audible as "that is the recording again".
    if (this.thunderBuf) {
      const src = ctx.createBufferSource();
      src.buffer = this.thunderBuf;
      src.playbackRate.value = 0.88 + Math.random() * 0.1;
      const g = ctx.createGain();
      g.gain.value = 0.9 + Math.random() * 0.2;
      src.connect(g).connect(this.sfx);
      src.start(t);
      return;
    }
    const rnd = (a, b) => a + Math.random() * (b - a);
    const DUR = rnd(5.4, 6.6);
    const src = ctx.createBufferSource();
    src.buffer = whiteNoise(ctx, DUR + 0.3);

    // The rip: three or four cracks, each shorter and duller than the last,
    // because the far end of the channel is further away through more air.
    const rip = ctx.createBiquadFilter();
    rip.type = 'highpass'; rip.frequency.value = 700; rip.Q.value = 0.7;
    const rg = ctx.createGain();
    rg.gain.setValueAtTime(0.0001, t);
    let at = 0;
    const n = Math.random() < 0.5 ? 3 : 4;
    for (let i = 0; i < n; i++) {
      const peak = (i === 0 ? 0.62 : 0.42) * Math.pow(0.72, i) * rnd(0.85, 1.15);
      rg.gain.exponentialRampToValueAtTime(peak, t + at + 0.006);
      rg.gain.exponentialRampToValueAtTime(peak * 0.06, t + at + rnd(0.05, 0.13));
      at += rnd(0.035, 0.11);
    }
    rg.gain.exponentialRampToValueAtTime(0.0001, t + at + 0.9);
    src.connect(rip).connect(rg).connect(this.sfx);

    // The thump. Not through any filter and not through the rip's gain: it is
    // the pressure step, and it arrives with the first crack.
    const sub = ctx.createOscillator();
    sub.type = 'sine';
    sub.frequency.setValueAtTime(rnd(72, 88), t);
    sub.frequency.exponentialRampToValueAtTime(rnd(26, 32), t + 0.55);
    const sg = ctx.createGain();
    sg.gain.setValueAtTime(0.0001, t);
    sg.gain.exponentialRampToValueAtTime(0.55, t + 0.02);
    sg.gain.exponentialRampToValueAtTime(0.0001, t + 1.5);
    sub.connect(sg).connect(this.sfx);
    sub.start(t); sub.stop(t + 1.6);

    // The roll. The filter closes smoothly; the level does not - it is walked
    // in steps of about a fifth of a second, each one up to half again or half
    // as loud as the one before, under an overall decay. Ramped rather than
    // stepped, or the steps themselves are audible as a tremolo.
    const body = ctx.createBiquadFilter();
    body.type = 'lowpass'; body.Q.value = 0.9;
    body.frequency.setValueAtTime(700, t);
    body.frequency.exponentialRampToValueAtTime(55, t + DUR);
    const bg = ctx.createGain();
    bg.gain.setValueAtTime(0.0001, t);
    bg.gain.exponentialRampToValueAtTime(0.5, t + rnd(0.12, 0.2));
    let lvl = 0.5;
    for (let s2 = 0.35; s2 < DUR - 0.4; s2 += rnd(0.16, 0.3)) {
      // The decay is on the *ceiling*, not on the level, so the walk can climb
      // and the roll still ends.
      const ceil = 0.5 * Math.pow(0.5, s2 / (DUR * 0.45));
      lvl = Math.max(0.012, Math.min(ceil * 1.25, lvl * rnd(0.6, 1.5)));
      bg.gain.exponentialRampToValueAtTime(lvl, t + s2);
    }
    bg.gain.exponentialRampToValueAtTime(0.0001, t + DUR);
    src.connect(body).connect(bg).connect(this.sfx);

    src.start(t);
    src.stop(t + DUR + 0.2);
  }

  /**
   * The jumpscare, and it is the one sound in here meant to hurt.
   *
   * Everything else on this bus is information - what the car just did, where a
   * rival is, whether that lap counted. This is the opposite: it exists to make
   * you flinch as the road runs out at the gable.
   *
   * **The first version was two clean sawtooths and it was a laser, not a
   * scream.** A synthesised glide is smooth, and smooth is the one thing a
   * scream never is - what a throat does is overblow, so the spectrum is full
   * of junk that is not a multiple of anything. So every layer here runs into
   * one hard clipper: clipping folds the layers into each other and fills the
   * gaps between their partials, which is the whole difference. The three
   * sawtooths are each frequency-modulated by a partner in the 20-50Hz range,
   * far too fast to hear as vibrato and far too slow to be a pitch - it is the
   * rate a voice cracks at, and it stops any of them sitting still long enough
   * to sound tuned.
   *
   * Under it a sine sweeping to 34Hz, which is the part you feel rather than
   * hear, and which **bypasses the clipper**: a clipped sine is a square, and a
   * square at 34Hz is a buzz rather than a thump.
   *
   * Down, not up: a rising glide is an alarm and you brace for the top of it,
   * and a falling one has its worst moment in the first fifty milliseconds,
   * before you can. It holds at full for half a second and then is *cut* - a
   * fade tells you it is over and lets you recover on the way out.
   *
   * No delay, unlike the thunder. The thunder is half a mile away and the light
   * beats the sound to you; this is in the car with you.
   */
  scare() {
    if (!this.ready) return;
    const ctx = this.ctx, t = ctx.currentTime, DUR = 0.95;

    const drive = ctx.createGain();
    drive.gain.value = 3.4;
    const clip = ctx.createWaveShaper();
    clip.curve = CLIP;
    clip.oversample = '4x';
    const out = ctx.createGain();
    out.gain.setValueAtTime(0.0001, t);
    out.gain.exponentialRampToValueAtTime(0.62, t + 0.005);
    out.gain.setValueAtTime(0.62, t + 0.5);
    out.gain.exponentialRampToValueAtTime(0.0001, t + DUR);
    drive.connect(clip).connect(out).connect(this.sfx);

    for (const [f0, f1, g, m] of [[1240, 250, 0.34, 37], [1870, 330, 0.26, 53],
                                  [610, 140, 0.30, 23]]) {
      const o = ctx.createOscillator();
      o.type = 'sawtooth';
      o.frequency.setValueAtTime(f0, t);
      o.frequency.exponentialRampToValueAtTime(f1, t + DUR * 0.8);
      const lfo = ctx.createOscillator();
      lfo.type = 'sawtooth';
      lfo.frequency.value = m;
      const depth = ctx.createGain();
      depth.gain.value = f0 * 0.42;
      lfo.connect(depth).connect(o.frequency);
      const vg = ctx.createGain();
      vg.gain.value = g;
      o.connect(vg).connect(drive);
      lfo.start(t); o.start(t);
      lfo.stop(t + DUR); o.stop(t + DUR);
    }

    const sub = ctx.createOscillator();
    sub.type = 'sine';
    sub.frequency.setValueAtTime(150, t);
    sub.frequency.exponentialRampToValueAtTime(34, t + 0.5);
    const sg = ctx.createGain();
    sg.gain.setValueAtTime(0.8, t);
    sg.gain.exponentialRampToValueAtTime(0.0001, t + DUR);
    sub.connect(sg).connect(this.sfx);
    sub.start(t); sub.stop(t + DUR);

    // The breath in it: noise falling from a hiss to a rasp, through the same
    // clipper so it tears rather than shushes.
    const src = ctx.createBufferSource();
    src.buffer = whiteNoise(ctx, DUR + 0.1);
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass'; bp.Q.value = 1.1;
    bp.frequency.setValueAtTime(3200, t);
    bp.frequency.exponentialRampToValueAtTime(680, t + DUR);
    const ng = ctx.createGain();
    ng.gain.setValueAtTime(0.5, t);
    ng.gain.exponentialRampToValueAtTime(0.02, t + DUR);
    src.connect(bp).connect(ng).connect(drive);
    src.start(t); src.stop(t + DUR);
  }
}

// ---------------------------------------------------------------------------
// Other cars
// ---------------------------------------------------------------------------
//
// A rival is a voice in the world rather than a voice in the mix: engine, tyres
// and its tow all go through one PannerNode at the car's own position. That is
// most of what it buys - somebody coming up your inside is a sound arriving on
// that side, and the tow is worth hearing precisely because the car about to
// pass you spends a second and a half winding up behind your shoulder.
//
// It is deliberately less machine than your own car - two sawtooths rather than
// three, and no load whine - because a full grid is eight of these playing at
// once and the engine that matters is the one you are sitting in. What a rival
// is *doing* comes off the flags it already puts in its pose (braking, sliding,
// airborne, boosting), so none of this needed anything new on the wire except
// how full the tow is.

const RIVAL_BUS = 0.9;        // the whole field against your own car
const MAX_RIVAL_VOICES = 7;   // a full grid minus you; the rest are too far to hear
const RIVAL_REF = 9;          // units: about two car lengths, where a rival is loudest
const RIVAL_ROLLOFF = 1.1;
const RIVAL_MAX = 240;

class RivalVoice {
  constructor(ctx, out) {
    this.ctx = ctx;
    const p = this.panner = ctx.createPanner();
    // HRTF rather than equalpower: on a chase camera the question that matters
    // most is *behind or in front*, which a left/right pan cannot answer at all.
    p.panningModel = 'HRTF';
    p.distanceModel = 'inverse';
    p.refDistance = RIVAL_REF;
    p.rolloffFactor = RIVAL_ROLLOFF;
    p.maxDistance = RIVAL_MAX;
    p.connect(out);

    this.engGain = ctx.createGain();
    this.engGain.gain.value = 0;
    this.engFilter = ctx.createBiquadFilter();
    this.engFilter.type = 'lowpass';
    this.engFilter.frequency.value = 900;
    this.engFilter.Q.value = 1.1;
    this.engGain.connect(this.engFilter).connect(p);
    this.osc = [];
    for (const detune of [0, 9]) {
      const o = ctx.createOscillator();
      o.type = 'sawtooth';
      o.frequency.value = 60;
      o.detune.value = detune;
      const g = ctx.createGain();
      g.gain.value = detune === 0 ? 0.6 : 0.3;
      o.connect(g).connect(this.engGain);
      o.start();
      this.osc.push(o);
    }

    this.tyreSrc = ctx.createBufferSource();
    this.tyreSrc.buffer = whiteNoise(ctx, 2);
    this.tyreSrc.loop = true;
    this.tyreFilter = ctx.createBiquadFilter();
    this.tyreFilter.type = 'bandpass';
    this.tyreFilter.frequency.value = 1700;
    this.tyreFilter.Q.value = 2.2;
    this.tyreGain = ctx.createGain();
    this.tyreGain.gain.value = 0;
    this.tyreSrc.connect(this.tyreFilter).connect(this.tyreGain).connect(p);
    this.tyreSrc.start();

    this.draftSrc = ctx.createBufferSource();
    this.draftSrc.buffer = whiteNoise(ctx, 2);
    this.draftSrc.loop = true;
    this.draftFilter = ctx.createBiquadFilter();
    this.draftFilter.type = 'bandpass';
    this.draftFilter.frequency.value = 500;
    this.draftFilter.Q.value = 3.2;
    this.draftGain = ctx.createGain();
    this.draftGain.gain.value = 0;
    this.draftSrc.connect(this.draftFilter).connect(this.draftGain).connect(p);
    this.draftSrc.start();

    this.boosting = false;
    this.placed = false;
    this.quiet = false;
  }

  update(r, t) {
    const set = (prm, v, tc = 0.06) => prm.setTargetAtTime(v, t, tc);
    this._moveTo(r, t);

    const sf = Math.min(1, r.speedFrac || 0);
    // The same rule as your own car, for the same reason: a parked rival is a
    // drone that happens to have a position. A room where nobody has pressed
    // anything is seven of them.
    const on = isDriving(r.throttle, sf, r.air);
    const gTc = on ? (this.quiet ? WAKE_TC : 0.09) : IDLE_TC;
    this.quiet = !on;
    const rpm = 58 + sf * 210 + (r.throttle ? 22 : 0);
    for (const o of this.osc) set(o.frequency, rpm, 0.05);
    set(this.engFilter.frequency, on ? 620 + sf * 2400 : IDLE_HZ, on ? 0.08 : IDLE_TC);
    set(this.engGain.gain, on ? (r.air ? 0.1 : 0.17 + (r.throttle ? 0.09 : 0)) : 0, gTc);
    set(this.tyreGain.gain, r.drift && !r.air ? 0.2 : 0, 0.06);

    // The same band as your own tow, a little hotter because the panner is about
    // to take most of it back: this air is happening at their car, not at yours.
    const boosting = r.boost > 0;
    const a = boosting ? Math.pow(r.boost, 0.45) : Math.min(1, r.charge || 0);
    set(this.draftGain.gain, a * (boosting ? 0.26 : 0.12), 0.08);
    set(this.draftFilter.frequency, 420 + a * (boosting ? 2600 : 1500), 0.1);
    set(this.draftFilter.Q, boosting ? 1.3 : 3.4, 0.12);
    // The moment it pays, in their direction - which is the whole warning you
    // get that the car behind you is about to not be behind you.
    if (boosting && !this.boosting) this._whoosh(t);
    this.boosting = boosting;
  }

  _moveTo(r, t) {
    const p = this.panner;
    if (p.positionX) {
      // A car that has just appeared is put where it is; after that the position
      // is smoothed, because a panner stepped every packet crackles.
      const tc = this.placed ? 0.03 : 0.001;
      p.positionX.setTargetAtTime(r.x, t, tc);
      p.positionY.setTargetAtTime(r.y, t, tc);
      p.positionZ.setTargetAtTime(r.z, t, tc);
    } else if (p.setPosition) {
      p.setPosition(r.x, r.y, r.z);
    }
    this.placed = true;
  }

  _whoosh(t) {
    const ctx = this.ctx;
    const o = ctx.createOscillator();
    o.type = 'sawtooth';
    o.frequency.setValueAtTime(260, t);
    o.frequency.exponentialRampToValueAtTime(1000, t + 0.34);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.16, t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.34);
    o.connect(g).connect(this.panner);
    o.start(t);
    o.stop(t + 0.37);
  }

  dispose() {
    for (const s of this.osc.concat([this.tyreSrc, this.draftSrc])) {
      try { s.stop(); } catch (e) { /* already stopped */ }
      s.disconnect();
    }
    this.panner.disconnect();
  }
}

/** Rotate a vector by a quaternion. Saves importing three.js into the audio. */
function _rot(q, x, y, z) {
  const tx = 2 * (q.y * z - q.z * y);
  const ty = 2 * (q.z * x - q.x * z);
  const tz = 2 * (q.x * y - q.y * x);
  return [x + q.w * tx + q.y * tz - q.z * ty,
          y + q.w * ty + q.z * tx - q.x * tz,
          z + q.w * tz + q.x * ty - q.y * tx];
}

// The jumpscare's clipper, built once. `tanh` rather than a clamp: a clamp has
// a corner in it and every signal through it gets the same corner, so a chord
// of them aliases into one fizz. This one saturates.
const CLIP = (() => {
  const c = new Float32Array(1024);
  for (let i = 0; i < c.length; i++) c[i] = Math.tanh(((i / 1023) * 2 - 1) * 4);
  return c;
})();

let _noiseCache = new Map();
function whiteNoise(ctx, seconds) {
  const key = Math.round(seconds * 10);
  if (_noiseCache.has(key)) return _noiseCache.get(key);
  const len = Math.floor(ctx.sampleRate * seconds);
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  _noiseCache.set(key, buf);
  return buf;
}
