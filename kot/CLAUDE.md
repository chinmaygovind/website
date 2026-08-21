# King of Tokyo (`kot/`)


**Live at `https://kot.cgovind.com`.** The third game, same shape as ERS: Flask +
Flask-SocketIO, its own eventlet gunicorn `-w 1` on `127.0.0.1:5004`, its own venv
(`kot/venv`) and `.env` (both gitignored, hand-made on the box), sharing TTR's `users`
table for accounts. Stats live in `kot_stats`, games in `kot_games` / `kot_players`.

- **Layout:** `kot/game_logic.py` (pure rules engine), `kot/cards.py` (all 66 power
  cards), `kot/bot.py` (the bot brain, also pure), `kot/app.py` (auth, lobby, socket
  game loop, bot orchestration, ELO), `kot/models.py`, `kot/templates/` + `kot/static/`.
- **Tests:** `scripts/tests.sh kot` - 221 tests in about 30s. `test_engine.py` covers the
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

