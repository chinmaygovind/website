// The menu music: the same song across the leaderboard, the garage, a track
// page and the lobbies, carrying on rather than restarting at each one.
//
// **These are separate page loads, not an SPA**, so "carrying on" has to be
// reconstructed: there is no object that survives a navigation. What survives
// is `sessionStorage`, so each page writes down where the song had got to and
// when, and the next one resumes at that point plus however long the
// navigation took. A fast click is inaudible; coming back after ten minutes in
// another tab lands wherever the song would have been.
//
// **Self-gating, like `portal.js`.** It is on every page via `base.html` and
// decides for itself whether it belongs: the play page has its own music -
// per-track, through `sound.js` - and two AudioContexts on one page is two
// songs at once. `window.DRIVE_TRACK` is what only the play page defines.
//
// **Nothing happens until the page is clicked.** Every browser refuses to start
// an AudioContext otherwise, and a rejected `play()` on load is a console
// warning on every page for a feature that is off by default anyway.

import { MusicPlayer, loadManifest, entryFor } from './music.js';

const KEY = 'drive.music.at';    // where the song had got to, and when
const SLUG = 'menu';
const TICK_MS = 250;             // the crossfade watch; a frame loop's job elsewhere

/** The play page owns its own music. Anything else is a menu. */
function isMenuPage() {
  return !window.DRIVE_TRACK;
}

/** The switch, shared with the game and written by it. */
function musicWanted() {
  try { return localStorage.getItem('drive.music') === '1'; } catch (e) { return false; }
}

/**
 * Where to come in.
 *
 * The stored position is advanced by the wall-clock gap since it was written,
 * so a navigation costs the song nothing, and then wrapped back into the song's
 * own `in`..`out` window - without which a long gap resumes past the end of the
 * file and the element simply refuses to play.
 */
function resumeAt(entry) {
  let saved = null;
  try { saved = JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (e) {}
  if (!saved || typeof saved.pos !== 'number') return entry.in;
  const gap = Math.max(0, (Date.now() - (saved.t || 0)) / 1000);
  const end = entry.out != null ? entry.out : null;
  if (end == null) return saved.pos + gap;      // length unknown until metadata
  const span = Math.max(1, end - entry.in);
  return entry.in + (((saved.pos - entry.in + gap) % span) + span) % span;
}

function remember(pos) {
  if (pos == null) return;
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ pos, t: Date.now() }));
  } catch (e) {}
}

function start() {
  if (!isMenuPage() || !musicWanted()) return;

  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;

  let player = null;
  let timer = null;

  // The first gesture is what is allowed to build a context. Once only, and
  // removed either way - a listener that stays is a listener that fires on
  // every click for the rest of the page.
  const open = () => {
    document.removeEventListener('pointerdown', open);
    document.removeEventListener('keydown', open);
    // The switch can have been turned off between load and the first click.
    if (!musicWanted()) return;

    const ctx = new AC();
    const master = ctx.createGain();
    master.gain.value = 0.55;     // as the game's master, so the two match in level
    master.connect(ctx.destination);

    loadManifest().then((m) => {
      const entry = entryFor(m, SLUG);
      if (!entry) return;
      player = new MusicPlayer(ctx, master, { onsong: null });
      // Cued before it is switched on, so `enable` starts it where the last
      // page left off rather than at the top.
      player.setSong(entry);
      player.entry = entry;
      player.enable(true);
      if (player.decks) player._seek(player.decks[player.active].el, resumeAt(entry));
      timer = setInterval(() => player.tick(), TICK_MS);
    });
  };
  document.addEventListener('pointerdown', open);
  document.addEventListener('keydown', open);

  // `pagehide` rather than `unload`: `unload` is ignored on iOS and disables the
  // back/forward cache everywhere else. `visibilitychange` covers the tab being
  // switched away from and then closed, which fires no navigation event at all.
  const save = () => { if (player) remember(player.position()); };
  window.addEventListener('pagehide', save);
  document.addEventListener('visibilitychange', () => { if (document.hidden) save(); });
  // Cheap insurance against a browser that fires neither: a quarter of a
  // second of drift is not audible and this costs one number every 5s.
  setInterval(save, 5000);
}

start();
