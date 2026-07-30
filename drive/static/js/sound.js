// All audio is synthesised in the browser - there are no sound files to ship.
//
// The engine is two detuned sawtooths through a lowpass whose pitch tracks wheel
// speed, plus a separate whine that only comes up under load, which is what makes
// throttle feel connected. Everything else (clanks, sparks, beeps) is a short
// envelope on an oscillator or a noise burst.
//
// Nothing is created until the first user gesture, so no browser ever warns about
// autoplay.

export class Sound {
  constructor() {
    this.ctx = null;
    this.enabled = true;
    this.ready = false;
  }

  start() {
    if (this.ctx || !this.enabled) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = this.ctx = new AC();
    this.master = ctx.createGain();
    this.master.gain.value = 0.55;
    this.master.connect(ctx.destination);

    // --- engine ----------------------------------------------------------
    this.engGain = ctx.createGain();
    this.engGain.gain.value = 0;
    this.engFilter = ctx.createBiquadFilter();
    this.engFilter.type = 'lowpass';
    this.engFilter.frequency.value = 900;
    this.engFilter.Q.value = 1.2;
    this.engGain.connect(this.engFilter).connect(this.master);

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
    this.whine.connect(this.whineGain).connect(this.master);
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
    this.noise.connect(this.tyreFilter).connect(this.tyreGain).connect(this.master);
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
    this.wind.connect(this.windFilter).connect(this.windGain).connect(this.master);
    this.wind.start();

    this.ready = true;
  }

  resume() { if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume(); }

  mute(m) {
    this.enabled = !m;
    if (this.master) this.master.gain.value = m ? 0 : 0.55;
  }

  /** Called every frame with the car's state. */
  engine(speedFrac, throttle, slip, airborne, boost) {
    if (!this.ready) return;
    const t = this.ctx.currentTime;
    const set = (p, v, tc = 0.06) => p.setTargetAtTime(v, t, tc);
    const rpm = 58 + speedFrac * 210 + (throttle ? 22 : 0);
    for (const o of this.osc) set(o.frequency, rpm, 0.05);
    set(this.engFilter.frequency, 620 + speedFrac * 2400 + (throttle ? 500 : 0), 0.08);
    set(this.engGain.gain, airborne ? 0.11 : 0.2 + throttle * 0.13, 0.09);
    set(this.whine.frequency, rpm * 3.02, 0.05);
    set(this.whineGain.gain, (throttle ? 0.045 : 0.012) * (0.4 + speedFrac) + (boost ? 0.05 : 0), 0.1);
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
    o.connect(g).connect(this.master);
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
    s.connect(f).connect(g).connect(this.master);
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

  wall(mag) {
    const f = Math.min(1, mag / 26);
    this._burst({ freq: 900, q: 0.6, dur: 0.12 + f * 0.1, gain: 0.1 + f * 0.15 });
    this._blip({ freq: 150, to: 70, type: 'triangle', dur: 0.16, gain: 0.06 + f * 0.1 });
  }

  land(airTime) {
    const f = Math.min(1, airTime / 1.4);
    this._burst({ freq: 400 + f * 300, q: 0.5, dur: 0.1 + f * 0.1, gain: 0.09 + f * 0.16 });
  }

  boost() {
    this._blip({ freq: 300, to: 1500, type: 'sawtooth', dur: 0.32, gain: 0.16 });
    this._burst({ freq: 1500, q: 0.7, dur: 0.3, gain: 0.12, type: 'highpass' });
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
    const notes = medal === 'author' ? [523, 659, 784, 1047, 1319]
                : medal === 'gold' ? [523, 659, 784, 1047]
                : medal ? [523, 659, 784] : [523, 659];
    notes.forEach((f, i) => this._blip({ freq: f, type: 'triangle', dur: 0.26,
                                        gain: 0.22, delay: i * 0.1 }));
  }

  record() {
    [784, 988, 1175, 1568].forEach((f, i) =>
      this._blip({ freq: f, type: 'square', dur: 0.3, gain: 0.2, delay: i * 0.09 }));
  }
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
