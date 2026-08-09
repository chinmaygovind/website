// All audio is synthesised in the browser - there are no sound files to ship.
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
// music goes through its own, beside it rather than under it. Muting is the
// sfx bus's gain and not the master's, so turning the sound off leaves the
// music playing and turning the music off leaves the car audible - which is
// the only reading of two separate switches that is not a lie about one of
// them.
//
// Nothing is created until the first user gesture, so no browser ever warns about
// autoplay.

export class Sound {
  constructor() {
    this.ctx = null;
    this.enabled = true;
    // Off until asked for, unlike the sound. The engine is what the game
    // sounds like and music over the top of it is a preference, so it is one
    // you turn on rather than one you turn off.
    this.musicOn = false;
    this.ready = false;
    this.voices = new Map();     // pid -> RivalVoice, while they are audible
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
    this.rivalBus.gain.value = 0.9;
    this.rivalBus.connect(this.sfx);

    // --- music -----------------------------------------------------------
    // Beside the sfx bus rather than under it, so the two switches are two
    // switches. Built even when it is switched off: it is a handful of nodes
    // and it costs nothing until a note is scheduled through it.
    this.music = new Music(ctx, this.master);
    this.music.enable(this.musicOn);

    this.ready = true;
  }

  resume() { if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume(); }

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
   * Wind the music on, from the frame loop.
   *
   * Web Audio's clock is the only one accurate enough to place a note on, so
   * the loop is scheduled a little way ahead of it rather than played by a
   * timer - and the thing already running at 60Hz is the frame loop, so that
   * is what turns the handle. It is called *before* the early returns for a
   * replay and a preview shot, since music is the one thing that should not
   * stop because you are watching somebody else's lap.
   */
  musicTick() {
    if (this.music) this.music.tick();
  }

  /** Called every frame with the car's state. */
  engine(speedFrac, throttle, slip, airborne) {
    if (!this.ready) return;
    const t = this.ctx.currentTime;
    const set = (p, v, tc = 0.06) => p.setTargetAtTime(v, t, tc);
    const rpm = 58 + speedFrac * 210 + (throttle ? 22 : 0);
    for (const o of this.osc) set(o.frequency, rpm, 0.05);
    set(this.engFilter.frequency, 620 + speedFrac * 2400 + (throttle ? 500 : 0), 0.08);
    set(this.engGain.gain, airborne ? 0.11 : 0.2 + throttle * 0.13, 0.09);
    set(this.whine.frequency, rpm * 3.02, 0.05);
    set(this.whineGain.gain, (throttle ? 0.045 : 0.012) * (0.4 + speedFrac), 0.1);
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
// Music
// ---------------------------------------------------------------------------
//
// Synthesised like everything else here, for the same reason: a loop long
// enough not to wear out is a megabyte of audio and this is a few hundred
// bytes of arithmetic, on a page that already ships no sound files at all.
//
// **The clock is the audio context's, not the browser's.** A note placed by a
// `setTimeout` lands wherever the main thread happens to be, which on a frame
// that is building a track mesh is tens of milliseconds late and audibly so.
// So the pattern is *scheduled ahead* against `ctx.currentTime` - `tick` looks
// `LOOK` seconds into the future and books everything due before then, and
// being called irregularly (or a couple of frames late) changes nothing about
// where the notes actually fall. That is also why it needs no timer of its
// own: the frame loop is already running, and one `while` there is the whole
// scheduler.
//
// The loop is four bars of i - VI - III - VII in A minor, which is the
// progression every driving game has been built on since about 1985, under a
// rolling sixteenth-note arpeggio. It is mixed deliberately low: this plays
// under an engine, and music you notice while braking for a corner is music
// you turn off.

const M_BPM = 124;
const M_STEP = 60 / M_BPM / 4;      // one sixteenth
const M_LOOK = 0.25;                // schedule this far ahead of the clock
const M_BARS = 4;
const M_LEVEL = 0.34;

// Semitones above the key note, four bars of one chord each. Four notes per
// chord so the arpeggio has a shape rather than a triad it keeps landing on.
//
// **Voiced to sit still, which means inverted rather than stacked from each
// root.** Written the obvious way - every chord climbing from its own root -
// the four bars start higher and higher and the figure ratchets up an octave
// and a half across the loop instead of going round. So F is played as A-C-F
// and G as G-B-D over the same handful of notes, and the whole thing stays
// inside one octave and a half however long you drive.
const M_CHORDS = [
  [0, 3, 7, 10],       // Am7:  A  C  E  G
  [-4, 0, 3, 8],       // F:    F  A  C  F
  [3, 7, 10, 15],      // C:    C  E  G  C
  [-2, 2, 5, 10],      // G:    G  B  D  G
];
// One bar of sixteenths as indices into the bar's chord, where 4 and up is the
// same note an octave higher - so the figure climbs and falls across two
// octaves out of four numbers.
const M_ARP = [0, 2, 3, 2, 4, 2, 3, 5, 0, 2, 3, 5, 4, 3, 2, 1];
// Where the bass falls. Syncopated rather than on every beat, which is what
// stops the whole thing sitting square on top of the kick.
const M_BASS = [0, 3, 6, 8, 11, 14];

/** Hz of a note this many semitones above A1. */
function mhz(semi) { return 55 * Math.pow(2, semi / 12); }

class Music {
  constructor(ctx, out) {
    this.ctx = ctx;
    this.bus = ctx.createGain();
    this.bus.gain.value = 0;
    this.bus.connect(out);
    // The arpeggio and the bass share one lowpass, so the whole loop sits
    // behind the engine rather than beside it.
    this.tone = ctx.createBiquadFilter();
    this.tone.type = 'lowpass';
    this.tone.frequency.value = 2600;
    this.tone.Q.value = 0.7;
    this.tone.connect(this.bus);
    // One buffer for every hat there will ever be. They come four to the bar
    // for as long as the game is open, and filling a fresh one each time is
    // the only part of this loop that would cost anything.
    this.hiss = whiteNoise(ctx, 0.2);
    this.on = false;
    this.step = 0;      // which sixteenth of the loop comes next
    this.next = 0;      // and when it is due, on the context clock
  }

  enable(on) {
    if (on === this.on) return;
    this.on = on;
    const t = this.ctx.currentTime;
    // Faded rather than switched: a bus cut to zero mid-note is a click.
    this.bus.gain.setTargetAtTime(on ? M_LEVEL : 0, t, on ? 0.25 : 0.12);
    // Picked up from the top of a bar rather than from wherever the loop had
    // got to, so turning it back on is a phrase starting and not a fragment.
    if (on) { this.step = 0; this.next = t + 0.08; }
  }

  tick() {
    if (!this.on) return;
    const t = this.ctx.currentTime;
    // A tab left in the background stops getting frames, so the clock can be
    // a long way past the next note when one arrives again. Skipping forward
    // beats playing a minute of backlog at once.
    if (this.next < t - M_LOOK) { this.next = t; this.step = 0; }
    while (this.next < t + M_LOOK) {
      this._step(this.step, this.next);
      this.step = (this.step + 1) % (M_BARS * 16);
      this.next += M_STEP;
    }
  }

  _step(i, t) {
    const beat = i % 16;
    const chord = M_CHORDS[Math.floor(i / 16) % M_BARS];

    // Four on the floor, with the backbeat a little softer.
    if (beat % 4 === 0) this._kick(t, beat === 0 ? 1 : 0.82);
    if (beat % 2 === 1) this._hat(t, beat % 8 === 5 ? 0.05 : 0.03);

    if (M_BASS.includes(beat)) {
      this._bass(t, mhz(chord[0] + 12));
    }

    const n = M_ARP[beat];
    // Accented on the beat and lighter off it, which is most of what makes a
    // string of even sixteenths sound played rather than clocked.
    this._pluck(t, mhz(chord[n % 4] + 12 * Math.floor(n / 4) + 36),
                beat % 4 === 0 ? 0.1 : 0.062);
  }

  _kick(t, gain) {
    const ctx = this.ctx;
    const o = ctx.createOscillator();
    o.type = 'sine';
    o.frequency.setValueAtTime(132, t);
    o.frequency.exponentialRampToValueAtTime(44, t + 0.1);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.5 * gain, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
    o.connect(g).connect(this.bus);
    o.start(t);
    o.stop(t + 0.26);
  }

  _hat(t, gain) {
    const ctx = this.ctx;
    const s = ctx.createBufferSource();
    s.buffer = this.hiss;
    const f = ctx.createBiquadFilter();
    f.type = 'highpass';
    f.frequency.value = 7200;
    const g = ctx.createGain();
    g.gain.setValueAtTime(gain, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.045);
    s.connect(f).connect(g).connect(this.bus);
    s.start(t);
    s.stop(t + 0.08);
  }

  _bass(t, freq) {
    const ctx = this.ctx;
    const o = ctx.createOscillator();
    o.type = 'sawtooth';
    o.frequency.setValueAtTime(freq, t);
    const f = ctx.createBiquadFilter();
    f.type = 'lowpass';
    // The filter opens and shuts on every note, which is the whole of what
    // makes a sawtooth sound plucked rather than held.
    f.frequency.setValueAtTime(1400, t);
    f.frequency.exponentialRampToValueAtTime(320, t + 0.18);
    f.Q.value = 3;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.24, t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
    o.connect(f).connect(g).connect(this.bus);
    o.start(t);
    o.stop(t + 0.24);
  }

  _pluck(t, freq, gain) {
    const ctx = this.ctx;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
    g.connect(this.tone);
    // Two oscillators a few cents apart, which is the cheapest way to make one
    // note sound like an instrument rather than a test tone.
    for (const detune of [-6, 6]) {
      const o = ctx.createOscillator();
      o.type = 'triangle';
      o.frequency.setValueAtTime(freq, t);
      o.detune.value = detune;
      o.connect(g);
      o.start(t);
      o.stop(t + 0.2);
    }
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
  }

  update(r, t) {
    const set = (prm, v, tc = 0.06) => prm.setTargetAtTime(v, t, tc);
    this._moveTo(r, t);

    const sf = Math.min(1, r.speedFrac || 0);
    const rpm = 58 + sf * 210 + (r.throttle ? 22 : 0);
    for (const o of this.osc) set(o.frequency, rpm, 0.05);
    set(this.engFilter.frequency, 620 + sf * 2400, 0.08);
    set(this.engGain.gain, r.air ? 0.1 : 0.17 + (r.throttle ? 0.09 : 0), 0.09);
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
