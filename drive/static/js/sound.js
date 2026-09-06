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
    set(this.engGain.gain, on ? (airborne ? 0.11 : 0.2 + throttle * 0.13) : 0, gTc);
    set(this.whine.frequency, rpm * 3.02, 0.05);
    // Half the time constant, so the top of the car is gone while the bottom
    // of it is still going.
    set(this.whineGain.gain,
        on ? (throttle ? 0.045 : 0.012) * (0.4 + speedFrac) : 0,
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
