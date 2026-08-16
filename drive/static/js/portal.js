/* Drive inside somebody else's page: the CrazyGames SDK, and nothing else.
 *
 * **This used to live inline in play.html and only did half of this.** It moved
 * for one reason: signing in is not something the play page can own. The portal
 * build has no login form of its own (see `portal.py`), so who you are is
 * decided by a token this file fetches, on every page, before anything else
 * asks - and a copy of that on the play page alone would mean the leaderboard,
 * the lobbies and the account page were all still guests.
 *
 * **It is v3.** The inline version loaded `crazygames-sdk-v2.js` and used its
 * callback `getEnvironment(cb)`. v3 is the documented SDK now, it is what the
 * account integration is written against, and it is a breaking change rather
 * than an upgrade: initialisation is explicit and `await`ed, and what used to be
 * async getters are plain properties (`SDK.environment`,
 * `SDK.user.isUserAccountAvailable`). Mixing the two shapes fails quietly - a
 * property read as a function is `undefined` rather than an error - so both
 * halves moved together.
 *
 * **Four things about it are load-bearing and none is obvious.**
 *
 * *It is only loaded inside a frame.* On our own domain the SDK is useless and
 * it is a third-party script on somebody else's CDN: loading it for every
 * player here would put a request nobody needs in front of every lap, and would
 * make the privacy notice at /privacy untrue the day it shipped.
 *
 * *Off a CrazyGames domain the SDK "enters disabled mode" and every call to it
 * throws* - their words. So nothing here calls it directly: `call` is wrapped,
 * and `SDK` is only kept once the environment has said it is real. An unguarded
 * `gameplayStart()` would raise on drive.cgovind.com at the exact moment the
 * game became playable, which is to say on essentially every lap anybody drives.
 *
 * *The game becomes playable before a script off a CDN can be relied on to have
 * arrived*, so the state is held here (`playing`) and replayed when and if the
 * SDK turns up. The alternative is a race that resolves differently on a slow
 * connection, which is the kind of bug that only ever reproduces for other people.
 *
 * *Nothing here may cost somebody a lap.* Their CDN having a bad morning, an ad
 * blocker eating the script, a token that will not verify: every one of those
 * ends with a player who is a guest and a game that plays. There is no error
 * path to a screen.
 *
 * `?useLocalSdk=true` is their own flag for forcing local mode, which logs the
 * events to the console; it is honoured here so this can be watched without
 * being on their site.
 */
(function () {
  'use strict';

  var SDK = null;      // the SDK, once initialised and known not to be disabled
  var playing = false; // what the game has told us, heard or not
  var known = null;    // the last identity the server gave us back

  function noop() {}

  function call(fn) {
    if (!SDK) return;
    try { fn(); } catch (e) { /* disabled, or a shape we do not know */ }
  }

  // Load when the server says we are in a portal, and *also* when we merely find
  // ourselves framed. The two are not the same question and both deserve a yes:
  // the server's answer is the one that shapes the page, but a portal that
  // embedded the bare URL without `?portal=` would otherwise never fire
  // `gameplayStart`, which is the one event the game is required to send.
  function wanted() {
    if (window.DRIVE_PORTAL) return true;
    if (location.search.indexOf('useLocalSdk=true') >= 0) return true;
    return document.documentElement.classList.contains('framed');
  }

  function load() {
    if (!wanted()) return;
    var s = document.createElement('script');
    s.src = 'https://sdk.crazygames.com/crazygames-sdk-v3.js';
    s.async = true;
    s.onload = function () {
      var api = window.CrazyGames && window.CrazyGames.SDK;
      if (!api || typeof api.init !== 'function') return;
      var started;
      try { started = api.init(); } catch (e) { return; }
      Promise.resolve(started).then(function () {
        // A property in v3, and the reason this check is here at all: on any
        // other domain every call below throws.
        if (api.environment === 'disabled') return;
        SDK = api;
        if (playing) call(function () { SDK.game.gameplayStart(); });
        identify();
        watch();
      }).catch(noop);
    };
    // Blocked by an extension, offline, or their CDN having a bad morning. None
    // of it is the game's problem and none of it may stop a lap.
    s.onerror = noop;
    document.head.appendChild(s);
  }

  // ---------------------------------------------------------------------
  // Who is driving
  // ---------------------------------------------------------------------

  function tell(token) {
    return fetch('/api/portal/auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // Same-origin, so the session cookie this sets comes straight back on
      // every later request - including the Socket.IO handshake, which is how a
      // signed-in player keeps their name in a room.
      credentials: 'same-origin',
      body: JSON.stringify({ token: token })
    }).then(function (r) { return r.json(); }).catch(function () { return null; });
  }

  /* The token, every time the game starts.
   *
   * Their instruction, and it is the right one: a token lives an hour, and the
   * same browser tomorrow may be a different person. The cost is one request
   * that usually changes nothing, because the server does no writes when the
   * session already holds this account.
   *
   * A rejection here is the ordinary case, not a failure - `userNotAuthenticated`
   * is what a guest gets, and a guest is a supported way to play.
   */
  function identify() {
    if (!SDK.user || !SDK.user.isUserAccountAvailable) return Promise.resolve(null);
    return SDK.user.getUserToken().then(function (token) {
      // The throttle only ever applies to a page that already knows who this
      // is. Rendered as a guest, we ask again whatever the clock says - a
      // session cookie a portal's partitioning quietly dropped would otherwise
      // leave somebody signed out for an hour with a valid token in hand.
      if (!token || (window.DRIVE_PORTAL_ME && fresh())) return null;
      return tell(token);
    }).then(function (d) {
      if (d) settle(d);
      return d;
    }).catch(function () { return null; });
  }

  /* Have we already told the server who this is, recently enough?
   *
   * A guest costs nothing either way - `getUserToken` rejects with
   * `userNotAuthenticated` before this is reached, so no request is made at all.
   * This is about the *signed-in* player, for whom the handshake would otherwise
   * be one POST per page load. `visits.py` logs a row per request and is the
   * same file in five services (TTR's copy lives in its own repo), so a skip
   * rule there is a change across all of them; throttling here costs nothing and
   * keeps a portal player's clickpath readable.
   *
   * An hour is their token's own lifetime, and the window is per tab, so a new
   * tab - a new game start by any reading - checks again immediately.
   */
  function fresh() {
    try {
      var at = +(sessionStorage.getItem('drive.portal.at') || 0);
      if (at && Date.now() - at < 3600e3) return true;
      sessionStorage.setItem('drive.portal.at', String(Date.now()));
    } catch (e) { /* no storage: ask every time, which is the safe direction */ }
    return false;
  }

  /* The page was rendered before we knew who this was. Now we do.
   *
   * A reload is the honest fix for a page whose nav, name and buttons were all
   * drawn for a guest - and a terrible one on the play page, where it means
   * building the track twice and would land in the middle of the loading the
   * portal is timing. So the play page opts out (`DrivePortalNoReload`) and
   * takes the news as an event instead; nothing on that screen except the name
   * depends on it, because `/api/run` reads the session on the server and not
   * whatever the page believed when it was drawn.
   *
   * Guarded to once a tab. If the browser will not keep our cookie at all -
   * which is a thing a portal's partitioning can do - the server would answer
   * "logged in" to a page that then renders logged out, for ever, one reload
   * apart.
   */
  function settle(d, quiet) {
    known = d;
    document.dispatchEvent(new CustomEvent('drive:identity', { detail: d }));
    if (!d.loggedIn || window.DRIVE_PORTAL_ME) return;
    // `quiet` is somebody pressing the sign-in button, where the page it is on
    // navigates itself the moment this resolves. Reloading underneath that is a
    // race between two ways of leaving the same page.
    if (quiet || window.DrivePortalNoReload) return;
    try {
      if (sessionStorage.getItem('drive.portal.reloaded') === '1') return;
      sessionStorage.setItem('drive.portal.reloaded', '1');
    } catch (e) { return; }
    location.reload();
  }

  // Somebody signing in through the portal's own furniture rather than ours.
  // Their docs note that signing *out* does not fire this, because the page is
  // refreshed instead - which is why nothing here tries to handle a sign-out.
  function watch() {
    if (!SDK.user || typeof SDK.user.addAuthListener !== 'function') return;
    call(function () { SDK.user.addAuthListener(function () { identify(); }); });
  }

  /* The sign-in button on the portal build's login page.
   *
   * `userAlreadySignedIn` is a success wearing an error: it means the prompt was
   * unnecessary, and the token is there for the asking. `userCancelled` is the
   * player saying no, which is not something to put an error on screen about.
   */
  function signIn() {
    if (!SDK || !SDK.user) return Promise.resolve({ loggedIn: false });
    return SDK.user.showAuthPrompt().catch(function (e) {
      if (e && e.code === 'userAlreadySignedIn') return null;
      throw e;
    }).then(function () {
      return SDK.user.getUserToken();
    }).then(tell).then(function (d) {
      if (d) settle(d, true);
      return { loggedIn: !!(d && d.loggedIn), name: d && d.name };
    }).catch(function (e) {
      return { loggedIn: false, cancelled: !!(e && e.code === 'userCancelled') };
    });
  }

  load();

  window.DrivePortal = {
    // Both are idempotent, because the callers are state changes rather than
    // events: `syncPaused` runs on every panel toggle and would otherwise
    // report a resume each time a sheet was closed on an already-running game.
    gameplayStart: function () {
      if (playing) return;
      playing = true;
      call(function () { SDK.game.gameplayStart(); });
    },
    gameplayStop: function () {
      if (!playing) return;
      playing = false;
      call(function () { SDK.game.gameplayStop(); });
    },
    signIn: signIn,
    identity: function () { return known; }
  };
})();
