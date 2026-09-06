/**
 * Guest times, kept until there is an account to put them on.
 *
 * Driving needs no account, which means the good lap usually happens *before*
 * anyone decides to sign up - and the old behaviour was to tell that lap it had
 * nowhere to go. So every run a guest finishes is kept here in full (time,
 * splits and the replay the leaderboard requires), best one per track, and the
 * moment the browser is logged in on any page they are submitted for real.
 *
 * This is a plain script rather than a module, and it is on every page, because
 * the login that unlocks the times happens on /login - a page the game code
 * never runs on. By the time you are back on a track they are already saved.
 *
 * The replay is stored at the quantisation the server would apply anyway
 * (centimetres, and quaternions to ~4dp), so nothing is lost by rounding and a
 * few laps stay comfortably inside a localStorage quota.
 */
(function () {
  const KEY = 'drive.pending';
  const SAVES = 'drive.saves';
  const POS = 100, ROT = 4096;

  function read() {
    try {
      const raw = localStorage.getItem(KEY);
      const obj = raw ? JSON.parse(raw) : {};
      return obj && typeof obj === 'object' ? obj : {};
    } catch (e) { return {}; }
  }

  /**
   * Store, and if there is no room for the evidence, store the times anyway.
   *
   * A kept run carries what the driver did at every physics step as well as the
   * replay (see Run.noteStep), which is most of its size and is only ever read
   * for a lap near the top of the board. So a quota that refuses the whole thing
   * is asked a second time without it: the alternative is dropping laps that
   * would have been accepted, to protect evidence that most of them never needed.
   */
  function write(obj) {
    try {
      if (!Object.keys(obj).length) { localStorage.removeItem(KEY); return; }
      localStorage.setItem(KEY, JSON.stringify(obj));
    } catch (e) {
      try {
        const lean = {};
        for (const k of Object.keys(obj)) {
          lean[k] = Object.assign({}, obj[k], { verify: null });
        }
        localStorage.setItem(KEY, JSON.stringify(lean));
      } catch (e2) { /* private mode, or full: the time is lost, not the lap */ }
    }
  }

  const round = (v, q) => Math.round(v * q) / q;

  function shrink(frames) {
    return (frames || []).map(f => [
      round(f[0], POS), round(f[1], POS), round(f[2], POS),
      round(f[3], ROT), round(f[4], ROT), round(f[5], ROT), round(f[6], ROT),
    ]);
  }

  /** Keep a finished run that had nowhere to go. Best per track wins. */
  function save(run) {
    if (!run || !run.track || !run.time_ms) return;
    const all = read();
    const cur = all[run.track];
    if (cur && cur.time_ms <= run.time_ms) return;
    all[run.track] = {
      track: run.track, time_ms: run.time_ms, splits: run.splits || [],
      distance: run.distance || 0, ghost: shrink(run.ghost), at: Date.now(),
      // Already quantised by `Run.verifyPayload`, and it has to survive whole:
      // a rounded input stream is not a smaller input stream, it is a different
      // lap. Null for a run kept before this existed, which the server answers
      // for by refusing only the laps that need checking.
      verify: run.verify || null,
    };
    write(all);
  }

  /**
   * Hand everything over, now that there is somewhere to put it.
   *
   * A rejected run is dropped rather than retried: the server has already
   * decided the replay does not hold up, and asking again on every page load
   * for the rest of time would not change its mind. A *failed request* is a
   * different thing entirely and keeps the run for the next page.
   */
  async function flush() {
    if (!window.DRIVE_USER) return [];
    const all = read();
    const slugs = Object.keys(all);
    if (!slugs.length) return [];
    const saved = [];
    for (const slug of slugs) {
      const run = all[slug];
      try {
        const r = await fetch('/api/run', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(run),
        });
        const d = await r.json().catch(() => ({}));
        if (d && d.ok && d.stored) {
          if (d.improved) saved.push({ slug, time_ms: run.time_ms, rank: d.rank });
          delete all[slug];
        } else if (r.status >= 400 && r.status < 500) {
          delete all[slug];
        }
      } catch (e) { /* offline: keep it and try again next page */ }
    }
    write(all);
    if (saved.length) announce(saved);
    return saved;
  }

  /**
   * Practice save states a guest built up, handed over with the laps.
   *
   * Here rather than in `game.js` for the reason the laps are: logging in
   * happens on `/login`, where the game code never runs, and this script is on
   * every page. Both stores hold the same shape, so it is a copy rather than a
   * conversion - see `savesKey` and `persistSaves`.
   *
   * **Merged, not replaced.** The account may already have states on a track
   * from another machine, and a guest session is not evidence that those are
   * finished with; the local ones fill the free slots after them and anything
   * past nine is dropped, which is the same ceiling every other path obeys.
   * Silent either way: a state is a convenience, and a note about nine of them
   * on top of the note about the lap is not worth the screen.
   */
  async function flushSaves() {
    if (!window.DRIVE_USER) return;
    let mine;
    try { mine = JSON.parse(localStorage.getItem(SAVES) || '{}') || {}; }
    catch (e) { return; }
    const keys = Object.keys(mine);
    if (!keys.length) return;
    let theirs = {};
    try {
      const r = await fetch('/api/saves');
      theirs = ((await r.json()) || {}).tracks || {};
    } catch (e) { return; }   // offline: keep them and try again next page
    for (const key of keys) {
      const merged = (theirs[key] || []).concat(mine[key] || []).slice(0, 9);
      try {
        const r = await fetch('/api/saves/' + encodeURIComponent(key), {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ saves: merged }),
        });
        // Only forget the local copy once the server has actually taken it. A
        // 4xx is the server declining for good (too big, no such track), so
        // that one is dropped rather than offered again for ever - the same
        // rule the laps above follow.
        if (r.ok || (r.status >= 400 && r.status < 500)) delete mine[key];
      } catch (e) { /* keep it */ }
    }
    try {
      if (Object.keys(mine).length) localStorage.setItem(SAVES, JSON.stringify(mine));
      else localStorage.removeItem(SAVES);
    } catch (e) { /* private mode */ }
  }

  const fmt = (ms) => {
    const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000);
    return m + ':' + String(s).padStart(2, '0') + '.' + String(ms % 1000).padStart(3, '0');
  };

  /** Times appearing on the board with no explanation would be a mystery. */
  function announce(saved) {
    const one = saved.length === 1;
    const names = (window.DRIVE_TRACK_NAMES || {});
    const el = document.createElement('div');
    el.className = 'pending-note';
    el.innerHTML = one
      ? 'Saved your <b>' + (names[saved[0].slug] || saved[0].slug) + '</b> time &middot; ' +
        fmt(saved[0].time_ms) + (saved[0].rank ? ' &middot; #' + saved[0].rank : '')
      : 'Saved <b>' + saved.length + '</b> times you set before logging in';
    document.body.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
      el.classList.remove('show');
      setTimeout(() => el.remove(), 500);
    }, 5200);
  }

  window.DrivePending = { save, flush, flushSaves,
                          count: () => Object.keys(read()).length };

  // The laps first and the save states after: a lap is somebody's record and a
  // save state is a convenience, so if only one of the two requests gets away
  // before the tab is closed it should be the one that matters.
  const go = () => { flush().then(flushSaves); };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', go);
  } else {
    go();
  }
})();
