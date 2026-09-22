# King of Tokyo (`kot/`)


**Live at `https://kot.cgovind.com`.** The third game, same shape as ERS: Flask +
Flask-SocketIO, its own eventlet gunicorn `-w 1` on `127.0.0.1:5004`, its own venv
(`kot/venv`) and `.env` (both gitignored, hand-made on the box), sharing TTR's `users`
table for accounts. Stats live in `kot_stats`, games in `kot_games` / `kot_players`.

- **A guest is not signed in, and `/login` must stay reachable for one.** It
  used to redirect anybody with a `guest_name` to the lobbies, which made the
  nav's own link a loop: the one control offering an account was the one that
  did nothing. `login_page` now sends away only `get_current_user()`. The nav
  reads `is_guest` (a context-processor flag, not `effective_name != 'Guest'`,
  which a guest who types "Guest" defeats) and offers **Sign up** →
  `/login?signup=1`, which is what opens the register tab rather than the login
  one. `tests/test_login.py` pins both halves.
- **Layout:** `kot/game_logic.py` (pure rules engine), `kot/cards.py` (all 66 power
  cards), `kot/bot.py` (the bot brain, also pure), `kot/app.py` (auth, lobby, socket
  game loop, bot orchestration, ELO), `kot/models.py`, `kot/templates/` + `kot/static/`.
- **kot runs on `run_parallel`, not xdist, and that is not a preference.**
  `app.py` monkey-patches on line 2 exactly as drive's does, and this suite had
  drive's deadlock all along - the CI job that reaches 96%, passes every test
  and then hangs until it is cancelled. Adding `tests/test_login.py` beside
  `test_bot_integration.py` (a second file importing `app`) made it every run.
  Keeping them on one xdist worker with `--dist loadgroup` was tried and hung in
  CI anyway. So `scripts/tests.sh` sends kot to `scripts/parallel_pytest.py` -
  one pytest process per bundle of files - and `tests/TIMINGS` is committed
  because CI has no local timing table and without one `test_bot.py` is not
  split, which is 38s against 16s. **Never hand this suite an explicit `-n`**:
  that is `run_parallel` declining, and the fallback is serial, not xdist.
- **Tests:** `scripts/tests.sh kot` - 224 tests in about 16s. `test_engine.py` covers the
  rules, `test_bot.py` covers the bot (liveness, legality, latency, strength). The
  three **strength** tests are gated off the default run - see the deploy section's
  note - so a plain `scripts/tests.sh kot` does *not* check that the bot is any good.
  Run `scripts/tests.sh --all kot` after touching `bot.py`, or just leave the file
  dirty and the runner will do it for you.
- **A log line's `kind` is what makes the sound.** `LOG_SOUND` in `static/js/game.js`
  maps kinds to stings, and the same `kind` becomes the `.log-<kind>` CSS class, so
  the engine controls audio purely by how it labels a log line - which means adding
  or renaming a kind silently changes what the client plays. Kinds are `vp`, `energy`,
  `heal`, `attack`, `ko`, `buy`, `revive`, `win`, `sys`, `tokyo` and `tokyo_take`.
  **Only `tokyo_take` (actually moving in) is loud**; holding Tokyo, yielding it and
  being shoved out are `tokyo`, which shares the purple log styling but has no sound.
  `test_only_taking_tokyo_is_loud` pins that split; a separate test asserts every
  damaging/scoring one-shot card logs at least one loud kind.

### Bots

The host adds bots from the lobby ("+ Add bot"), same as ERS/TTR. They are ordinary
`KotPlayer` rows with `is_bot=True` and no `user_id`, so they take a monster and colour
like anyone else and are excluded from ELO. Names are drawn from `BOT_NAMES`
(Bot-zilla, Claw-de, Mechatron, The Terminator, Gloopy); **Bot-zilla gets 50% of the
weight on the first bot added**, the others split the rest.

- `bot.py` is pure decision-making - it never touches Flask, the DB or the clock.
  The dice choice is a memoized expectimax over the remaining rerolls, scoring every
  reachable tray with a context-aware utility. Everything else (yield, buys, hearts,
  Psychic Probe) is a policy in the same VP-equivalent units.
- **All strategic weights live in `bot.W`**, tuned by self-play. Re-run the sweep if
  you change one; `test_bot.py` has strength thresholds that will catch a regression.
- **Latency matters more than it looks.** One eventlet worker serves every live game,
  so a slow decision blocks *all* players' sockets, not just the bot's table. The
  search caches its reroll transition tables globally to stay ~3ms; a naive version
  measured 523ms. `test_dice_decision_is_fast` guards this.
- **Bots must always answer.** The engine parks the entire game in `yield`,
  `probe_window` or `token_choice` until the monster on the clock decides. Every bot
  step in `app.py` runs atomically under the game lock and is written to guarantee
  forward progress - the scheduler will not arm the same `(kind, seq)` twice, so an
  action the engine silently rejects would freeze the table. This is why the buy phase
  is one step ending in `end_turn`, and why `_bot_probe` always drains the queue.
- `_bot_kick(code)` is the single scheduler; it takes the per-game lock, so **never
  call it while holding that lock** (eventlet semaphores are not reentrant). Every
  state-mutating path ends by calling it.

### Replays

`kot_games.events_json` is the move-by-move replay: one entry per action (`roll`,
`resolve`, `yield`, `token_choice`, `buy`, `sweep`, `card_action`, `end_turn`,
`resign`, plus `start`/`end`), each with the choice made, a snapshot of every
monster's hp/vp/energy/cards, Tokyo occupancy, and the engine log lines that action
produced. Bot moves carry `"bot": true`. Note this only became true recently - games
before that have `start` and `end` and nothing in between, so any analysis has to skip
them.

### The install prompt

**`/install` and the bottom-sheet nudge that points at it are one pattern copied
into all four PWA games** (drive, ers, kot, ttr), each in its own colours. The
prompt is a `{% block install_prompt %}` in `base.html`, so the in-game
templates (`game.html`) blank it - a fixed bar over a
game in progress is a way of losing the game, and the block is the same gate
`_nav.html`'s absence already is on those pages.

It shows only on `(pointer: coarse)` and only when the page is not already the
installed app. **All three display modes are tested**, not just `standalone`:
a manifest's `display` decides which one an installed copy matches, and
kot is `standalone` today but a manifest edit must not
quietly switch the prompt back on inside the app. `navigator.standalone` covers iOS, which
matches no display-mode query at all. A dismissal goes in `localStorage` behind
a try/catch, because private mode throws on access rather than returning null.

`/install` ships **both** sets of steps and picks between them in JS rather than
off the User-Agent, so a link pasted into a group chat is right for whoever
opens it. iOS step 1 is **Open in Safari** (`x-safari-` + the current URL) -
only Safari can add to the home screen, and an in-app webview is where that link
matters. On Android the page also captures `beforeinstallprompt` **in `<head>`**,
because Chrome fires it once, early, and never replays it; the manual steps stay
visible, so a browser that never fires it loses nothing.
