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
//
// **Which is why there is a switch here at all.** Music is off by default and
// the only control for it used to live in the play page's settings sheet, so a
// menu page had a song it would never play and no way to ask for one: the
// gesture the browser wants and the setting the player wants were never both
// satisfied in the same place. The button in the corner is both at once - the
// click that turns it on is the click that is allowed to build the context -
// and it carries the credit card with it, because a song arriving unannounced
// is somebody else's work going uncredited.

import { MusicPlayer, loadManifest, entryFor } from './music.js';

const KEY = 'drive.music.at';    // where the song had got to, and when
const SLUG = 'menu';
const TICK_MS = 250;             // the crossfade watch; a frame loop's job elsewhere
const CARD_MS = 6500;            // the credit's dwell, as the play page's
/**
 * How gently the menu song arrives - four times the game's 0.3, so it is most
 * of the way up after about three and a half seconds rather than one.
 *
 * The play page's fade is short on purpose: you turned the music on from a
 * settings sheet with a car in front of you, and a song that takes four seconds
 * to appear reads as the switch not having worked. A menu has none of that.
 * Nothing is happening, the song is the only thing that changes, and arriving
 * at the game's speed is an entrance. Only the arrival is slowed - pressing the
 * button off still answers at `ENABLE_TC`.
 */
const FADE_IN_TC = 1.2;

/** The play page owns its own music. Anything else is a menu. */
function isMenuPage() {
  return !window.DRIVE_TRACK;
}

/** The switch, shared with the game and written by it. */
function musicWanted() {
  try { return localStorage.getItem('drive.music') === '1'; } catch (e) { return false; }
}

/**
 * The same switch, written the way the game writes it.
 *
 * `'1'`/`'0'` and `localStorage` only, which is `rememberPref` in `game.js`
 * minus the account round trip - `drive.music` is deliberately not in
 * `ACCOUNT_PREFS`, because sound is a thing about the room you are in rather
 * than about you.
 */
function setMusicWanted(on) {
  try { localStorage.setItem('drive.music', on ? '1' : '0'); } catch (e) {}
}

/**
 * Where to come in.
 *
 * The stored position is advanced by the wall-clock gap since it was written,
 * so a navigation costs the song nothing, and then wrapped back into the song's
 * own window - without which a long gap resumes past the end of the file and
 * the element simply refuses to play.
 *
 * **The end of that window is `out` or the file's own duration, and it used to
 * be only `out`.** The menu song has no `in`/`out` - it is the whole file, and
 * most of the manifest is - so `end` was null for exactly the song this module
 * plays, the wrap never ran, and a resume was `pos + gap` with nothing holding
 * it down. Come back to a menu page after five minutes away and it seeks past
 * the end of a three-minute file, which is silence that looks like the switch
 * being off. It went unnoticed while the only way in was a page load; the mute
 * button takes this path every time it is pressed. `el` is passed rather than
 * read from the entry because a duration exists only once the element has
 * metadata, which is why the caller waits for it.
 */
function resumeAt(entry, el) {
  let saved = null;
  try { saved = JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (e) {}
  if (!saved || typeof saved.pos !== 'number') return entry.in;
  const gap = Math.max(0, (Date.now() - (saved.t || 0)) / 1000);
  const dur = el && isFinite(el.duration) ? el.duration : null;
  const end = entry.out != null ? entry.out : dur;
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

/**
 * The switch and the credit, built here rather than in `base.html`.
 *
 * This module already decides for itself whether it belongs on the page, and
 * markup in the shared template would not - the play page would carry a second
 * music button under its own settings sheet, and a second `#nowPlaying` beside
 * the one in its HUD. Building the pair from the code that owns them keeps the
 * self-gating one decision in one place.
 */
function buildDock() {
  const dock = document.createElement('div');
  dock.className = 'menu-music';

  // The same card as the play page's, down to the class names: it is the same
  // credit for the same reason, and it should not be a second design of one.
  const card = document.createElement('a');
  card.className = 'now-playing menu-np';
  card.target = '_blank';
  card.rel = 'noopener noreferrer';
  card.innerHTML = '<svg class="np-icn" viewBox="0 0 24 24" aria-hidden="true">'
    + '<path d="M9 17.5V6.2l10-2v11.3"/>'
    + '<circle cx="6.6" cy="17.6" r="2.4"/>'
    + '<circle cx="16.6" cy="15.4" r="2.4"/>'
    + '</svg><span class="np-text">'
    + '<span class="np-title"></span><span class="np-artist"></span></span>';

  // A note with a stroke through it, not a speaker: a speaker is the icon for
  // the engine and the clanks, and this switch does not touch those.
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'mm-btn';
  btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">'
    + '<path d="M9 17.5V6.2l10-2v11.3"/>'
    + '<circle cx="6.6" cy="17.6" r="2.4"/>'
    + '<circle cx="16.6" cy="15.4" r="2.4"/>'
    + '<path class="mm-slash" d="M3.6 20.4 20.4 3.6"/>'
    + '</svg>';

  dock.append(card, btn);
  document.body.appendChild(dock);
  return {
    card, btn,
    title: card.querySelector('.np-title'),
    artist: card.querySelector('.np-artist'),
  };
}

function start() {
  if (!isMenuPage()) return;

  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;

  const ui = buildDock();
  let ctx = null;
  let player = null;
  let timer = null;
  let cardTimer = null;

  function paint() {
    const on = musicWanted();
    ui.btn.classList.toggle('off', !on);
    ui.btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    const label = on ? 'Music on' : 'Music off';
    ui.btn.title = label;
    ui.btn.setAttribute('aria-label', label);
  }

  function showCard(entry) {
    if (!entry) { hideCard(); return; }
    ui.title.textContent = entry.title || '';
    ui.artist.textContent = entry.artist || '';
    ui.artist.style.display = entry.artist ? '' : 'none';
    // A song with no link is still a credit; it just is not a link.
    if (entry.url) { ui.card.href = entry.url; ui.card.removeAttribute('aria-disabled'); }
    else { ui.card.removeAttribute('href'); ui.card.setAttribute('aria-disabled', 'true'); }
    ui.card.classList.add('show');
    clearTimeout(cardTimer);
    cardTimer = setTimeout(hideCard, CARD_MS);
  }

  function hideCard() {
    clearTimeout(cardTimer);
    ui.card.classList.remove('show');
  }

  /**
   * Put the active deck where the song would have got to.
   *
   * Deferred to `loadedmetadata` rather than handed straight to `_seek`,
   * because the wrap in `resumeAt` needs a duration and a cold element has
   * none - `_seek` would defer the seek but not the arithmetic that chose it.
   */
  function seekResume(entry) {
    if (!player || !player.decks) return;
    const el = player.decks[player.active].el;
    const go = () => player._seek(el, resumeAt(entry, el));
    if (el.readyState >= 1) { go(); return; }
    el.addEventListener('loadedmetadata', function once() {
      el.removeEventListener('loadedmetadata', once);
      go();
    });
  }

  /**
   * Start playing, from whatever gesture we are inside.
   *
   * Idempotent, and called from two places that cannot know about each other:
   * the first click anywhere on the page (for music already switched on) and
   * the button (for music being switched on now).
   *
   * **`fresh` is the difference between the two, and it is the whole point.**
   * Resuming exists so that walking from the leaderboard to the garage does not
   * restart the song - it is about navigation, and nothing else. Pressing the
   * switch on is not navigation: it is somebody asking for the song, and the
   * answer to that is the top of it. Sharing one path made the button inherit
   * the resume and open several seconds in, which reads as the music having
   * been playing silently the whole time - which is exactly what the stored
   * position claimed. `save()` only writes a position while the deck is
   * actually playing (`position()` is null when paused), so a mute freezes the
   * position and leaves its timestamp behind; `resumeAt` then bills the whole
   * muted stretch to the song as though it had run on.
   */
  function ensure(fresh) {
    if (!musicWanted()) return;

    if (player) {                 // built already, so this is an unmute
      player.enable(true);        // which seeks to `in` on its own
      if (!fresh) seekResume(player.entry);
      showCard(player.entry);
      return;
    }
    if (ctx) return;              // building; the manifest has not landed yet

    ctx = new AC();
    const master = ctx.createGain();
    master.gain.value = 0.55;     // as the game's master, so the two match in level
    master.connect(ctx.destination);

    loadManifest().then((m) => {
      const entry = entryFor(m, SLUG);
      if (!entry) return;
      player = new MusicPlayer(ctx, master, { onsong: null, enableTc: FADE_IN_TC });
      // Cued before it is switched on, so `enable` starts it where the last
      // page left off rather than at the top.
      player.setSong(entry);
      player.entry = entry;
      // The tick runs whether or not the song does: it returns immediately
      // while the player is off, and starting it here means an unmute has a
      // crossfade waiting for it rather than a loop that never comes round.
      timer = setInterval(() => player.tick(), TICK_MS);
      // The switch can have been turned off again while the manifest was in
      // flight, and a song that starts anyway is a song nobody asked for.
      if (!musicWanted()) return;
      player.enable(true);
      if (!fresh) seekResume(entry);
      showCard(entry);
    });
  }

  ui.btn.addEventListener('click', () => {
    const on = !musicWanted();
    setMusicWanted(on);
    paint();
    if (on) {
      ensure(true);               // asked for: start it at the top
    } else {
      // Off takes the card with it rather than leaving a panel naming music
      // that has stopped - the same rule the play page's switch follows.
      if (player) player.enable(false);
      hideCard();
    }
  });
  paint();

  // The first gesture is what is allowed to build a context. Once only, and
  // removed either way - a listener that stays is a listener that fires on
  // every click for the rest of the page. The button does its own building, so
  // this is only here for music that was already switched on when the page
  // loaded.
  const open = () => {
    document.removeEventListener('pointerdown', open);
    document.removeEventListener('keydown', open);
    ensure(false);                // already on: pick the song up where it was
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
