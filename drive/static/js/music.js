// The music, which is the one thing in this game that is a file rather than
// arithmetic.
//
// Everything else in `sound.js` is synthesised, and the music used to be too -
// four bars of A minor under a sixteenth-note arpeggio, the same four bars on
// all twenty-two tracks. That is the version this replaces. A track now has a
// song, and a song is a recording.
//
// **Two decks, ping-ponged, rather than one element with `loop = true`.**
// A looping `<audio>` restarts at a hard cut, and a song trimmed to an `in`/`out`
// pair almost always has an audible seam there - the tail is still ringing when
// the head arrives. So there are two elements and the loop is a crossfade
// between them: the idle deck is cued to `in` and faded up over the last `fade`
// seconds of the active one, which is then faded down and parked. The seam
// becomes an overlap, and an overlap is the one thing that reliably does not
// click.
//
// **Streamed, not decoded.** `decodeAudioData` on a five-minute song is fifty
// megabytes of float32 and several seconds of main thread; a
// `MediaElementAudioSourceNode` is neither. The cost is that we cannot see the
// samples - which is exactly why the loop points are hand-written in the
// manifest rather than found by analysis.
//
// **An element may be attached to a MediaElementAudioSourceNode once, ever.**
// Attaching a second time throws, and the throw is unrecoverable for that
// element. So the two decks are built once and keep their nodes for the life of
// the page; changing song sets `src` on a deck that already has its graph.

/** Where the manifest lives. One file, so adding a song is not a code change. */
export const MANIFEST_URL = '/static/audio/music.json';

const FADE = 1.2;      // default crossfade, seconds - overridable per song
const LEVEL = 0.5;     // the music bus, under the master with the sfx bus
const ENABLE_TC = 0.3; // switching the music on is a fade, not a cut

/**
 * Fetch the manifest, once per page.
 *
 * Resolves to `null` rather than rejecting when there is no manifest or it is
 * unreadable: no music is a quiet game, and a game that fails to start because
 * a JSON file moved would be a much worse trade than silence.
 */
let _manifest = null;
export function loadManifest(url = MANIFEST_URL) {
  if (!_manifest) {
    _manifest = fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
  }
  return _manifest;
}

/**
 * One song's worth of manifest, normalised.
 *
 * `in`/`out` are optional and default to the whole file - `out` cannot be
 * resolved until the element has metadata, so it stays null here and is read
 * off `duration` at the point the loop is scheduled.
 */
function entryFor(manifest, slug) {
  const e = manifest && manifest.tracks && manifest.tracks[slug];
  if (!e || !e.file) return null;
  return {
    slug,
    src: '/static/audio/' + e.file,
    artist: e.artist || null,
    title: e.title || null,
    url: e.url || null,
    in: typeof e.in === 'number' ? e.in : 0,
    out: typeof e.out === 'number' ? e.out : null,
    fade: typeof e.fade === 'number' ? e.fade
          : (manifest.fade != null ? manifest.fade : FADE),
  };
}

export class MusicPlayer {
  /**
   * @param ctx   an AudioContext, already built on a user gesture
   * @param out   the node to play into - the master, beside the sfx bus
   * @param opts  `level`, and `onsong(entry|null)` for the now-playing popup
   */
  constructor(ctx, out, opts = {}) {
    this.ctx = ctx;
    this.level = opts.level != null ? opts.level : LEVEL;
    this.onsong = opts.onsong || null;

    // Beside the sfx bus rather than under it, so the two switches in settings
    // are two switches: muting the game leaves the song playing, and turning
    // the song off leaves the car audible.
    this.bus = ctx.createGain();
    this.bus.gain.value = 0;
    this.bus.connect(out);

    this.on = false;
    this.entry = null;
    this.decks = null;    // built on first use, because they are DOM elements
    this.active = 0;
    this.fading = false;
  }

  /** Two `<audio>` elements and their permanent graph. Built once. */
  _build() {
    if (this.decks) return this.decks;
    this.decks = [0, 1].map(() => {
      const el = new Audio();
      el.preload = 'auto';
      el.crossOrigin = 'anonymous';
      // Never the element's own loop: the whole point is that the seam is a
      // crossfade between two decks, which one element cannot do to itself.
      el.loop = false;
      const gain = this.ctx.createGain();
      gain.gain.value = 0;
      const src = this.ctx.createMediaElementSource(el);
      src.connect(gain).connect(this.bus);
      return { el, gain, src };
    });
    return this.decks;
  }

  /**
   * Which song. Called on entering a track and again whenever the track
   * switcher swaps worlds without a navigation.
   *
   * A slug with no manifest entry - Figure Eight, a user-made track, a draft
   * out of the editor - stops the music rather than leaving the last track's
   * song playing over a different one.
   */
  setSong(entry) {
    const same = entry && this.entry && entry.src === this.entry.src;
    this.entry = entry || null;
    if (same) return;          // the three circuits share one file; do not restart it
    this._stopAll();
    if (this.on) this._startActive(this.entry ? this.entry.in : 0);
    if (this.onsong) this.onsong(this.entry);
  }

  /** The music switch. Faded, because a bus cut to zero mid-bar is a click. */
  enable(on) {
    if (on === this.on) return;
    this.on = on;
    this.bus.gain.setTargetAtTime(on ? this.level : 0,
                                  this.ctx.currentTime, ENABLE_TC);
    if (on) {
      this._startActive(this.entry ? this.entry.in : 0);
    } else {
      // Paused after the fade rather than under it, so switching off is a song
      // going away and not a song being guillotined.
      const decks = this.decks || [];
      const at = ENABLE_TC * 4 * 1000;
      setTimeout(() => { if (!this.on) decks.forEach((d) => d.el.pause()); }, at);
    }
  }

  /**
   * Wind the loop on. Called from whatever is already running - the game's
   * frame loop, or a plain interval on the menu pages.
   *
   * All it does is watch the active deck's clock for the crossfade point.
   * There is no scheduling ahead here (unlike the synth this replaces) because
   * a crossfade is a ramp on a gain, and a ramp booked a frame late is a ramp
   * that starts a frame late - inaudible, where a *note* a frame late is not.
   */
  tick() {
    if (!this.on || !this.entry || !this.decks || this.fading) return;
    const d = this.decks[this.active];
    if (d.el.paused || !d.el.duration) return;
    const end = this.entry.out != null
      ? Math.min(this.entry.out, d.el.duration)
      : d.el.duration;
    if (d.el.currentTime >= end - this.entry.fade) this._crossfade(end);
  }

  /** Where the active deck has got to, for handing across a page navigation. */
  position() {
    if (!this.decks) return null;
    const d = this.decks[this.active];
    return d.el.paused ? null : d.el.currentTime;
  }

  /**
   * Give both decks the file, not just the one about to play.
   *
   * The idle deck is the one the crossfade brings in, and a deck handed its
   * `src` at that moment has no metadata yet - so its seek to `in` is deferred
   * to `loadedmetadata` while `play()` has already started it from 0:00. The
   * first loop of every song with an `in` came in at the top of the file.
   * Cueing both up front means the idle deck has metadata long before it is
   * needed and the seek is immediate. `preload = 'auto'` on the second one
   * costs a request the HTTP cache answers.
   */
  _cue() {
    this._build().forEach((d) => {
      if (d.el.getAttribute('src') !== this.entry.src) d.el.src = this.entry.src;
    });
  }

  _startActive(at) {
    if (!this.entry) return;
    this._cue();
    const d = this.decks[this.active];
    d.gain.gain.setTargetAtTime(1, this.ctx.currentTime, 0.05);
    this._seek(d.el, at);
    // Rejected play is the autoplay policy, and it is not an error worth
    // making noise about: the next user gesture builds a context and we are
    // called again.
    const p = d.el.play();
    if (p && p.catch) p.catch(() => {});
  }

  /**
   * Seeking an element that has no metadata yet throws away the seek, which is
   * how a song with `in: 20` ends up starting at zero on a cold load.
   */
  _seek(el, at) {
    if (!at) { try { el.currentTime = 0; } catch (e) {} return; }
    if (el.readyState >= 1) { try { el.currentTime = at; } catch (e) {} return; }
    el.addEventListener('loadedmetadata', function once() {
      el.removeEventListener('loadedmetadata', once);
      try { el.currentTime = at; } catch (e) {}
    });
  }

  _crossfade(end) {
    const t = this.ctx.currentTime;
    const fade = this.entry.fade;
    const from = this.decks[this.active];
    const to = this.decks[1 - this.active];
    this.fading = true;

    this._cue();
    this._seek(to.el, this.entry.in);
    to.gain.gain.cancelScheduledValues(t);
    to.gain.gain.setValueAtTime(0.0001, t);
    to.gain.gain.exponentialRampToValueAtTime(1, t + fade);
    const p = to.el.play();
    if (p && p.catch) p.catch(() => {});

    from.gain.gain.cancelScheduledValues(t);
    from.gain.gain.setValueAtTime(Math.max(from.gain.gain.value, 0.0001), t);
    from.gain.gain.exponentialRampToValueAtTime(0.0001, t + fade);

    this.active = 1 - this.active;
    // Parked only once it is silent. Pausing it now is the cut the crossfade
    // exists to avoid.
    setTimeout(() => {
      from.el.pause();
      this.fading = false;
    }, fade * 1000);
  }

  _stopAll() {
    if (!this.decks) return;
    this.decks.forEach((d) => {
      d.el.pause();
      d.gain.gain.value = 0;
    });
    this.active = 0;
    this.fading = false;
  }
}

export { entryFor };
