# CLAUDE.md

Chinmay Govind's personal website: a small **Flask** server that serves a static
site. The **root (`/`) is a plain landing page**; the old **Wii-menu recreation now
lives at `/wii/`**. `/ttr` redirects to the **Ticket to Ride** app (bundled as a git
submodule); `/ers` redirects to **Egyptian Rat Screw** (the `ers/` subdir - a real-time
multiplayer card game that shares TTR's accounts).

## What this is / how it runs

- `app.py` is the whole server (~60 lines). It serves everything under `site/`
  as static files with **GitHub-Pages-style directory indexes**: a request to
  `/foo/` serves `site/foo/index.html`, and `/foo` 301-redirects to `/foo/` so
  relative links keep working. Path safety via `werkzeug.utils.safe_join`.
- `/` serves the landing page (`site/index.html`); the Wii menu is at `/wii/`
  (`site/wii/index.html`). `/ttr`, `/ers` and `/kot` (each with and without the
  trailing slash) 302-redirect to `TTR_URL` / `ERS_URL` / `KOT_URL` (env; default
  `https://{ttr,ers,kot}.cgovind.com`). A 404 falls back to the `site/404.html`
  Mario game.
- `app.py` also proxies a few APIs the landing page calls same-origin, so no keys
  reach the client: `/api/duolingo-streak`, `/api/spotify/{login,callback,recent,
  top-artists}` (OAuth refresh token in the box `.env`), and `/api/roll/gemini`
  for the `site/games/roll/` game.
- **`/accounts` is the one thing here that is not static** — the shared profile
  for all four games. It lives in the `accounts/` package and is attached by
  `accounts.init_app(app)` at the foot of `app.py`, **only when `DATABASE_URL`
  is set**, so a checkout that just wants to serve the static tree boots with no
  database and no database driver. See **Accounts** below.
- **No build step, no bundler.** Pages are self-contained static HTML with inline
  `<style>`/`<script>`, same as the old GitHub Pages site this was derived from.
  The one exception is `accounts/`, which is a normal Flask blueprint with
  templates and a stylesheet, because it is a real application rather than a page.
- Local: `python app.py` → http://localhost:5002 (`PORT` overrides). Prod:
  gunicorn behind nginx (see `deploy/`), auto-deploys from `main`.

## Layout (`site/` is the web root)

- `site/index.html` is the landing page: white page, big "hey!" left, welcome line
  and contact links across the top, all in the self-hosted xkcd Script font
  (`site/fonts/xkcd-script.woff`, from ipython/xkcd-font). Below it is a **tile
  grid** — `repeat(6, --tile)` × auto rows, so **12 slots** before it wraps to a
  third row (2 columns on <=760px). Currently 9: resume, poker, whales, racing,
  music, settings on the top row, then the three games — ttr, ers, kot — on the
  second. **Keep `settings` last in the top row** (it's a Wii-menu joke), and add
  new games to the second row so the split holds. **Drive has no tile on purpose**
  — it had one, and it was removed because Chinmay wants to draw the icon himself;
  `--drive` is still in `:root` waiting for it. Do not re-add it unasked.
- **Adding a tile is one repeating pattern**, all inside `site/index.html` (no
  build step, so everything is inline):
  1. a `--<name>` accent colour in `:root`, then `.modal-<name>` rules for
     `border-color`, `.pane-title` colour, and `.media-img` border;
  2. a `<button class="tile" data-modal="modal-<name>">` with a `.tile-img` whose
     `data-still`/`data-anim` are `assets/icons/<name>.png` / `.gif` — the script
     at the bottom swaps to the gif on hover and preloads it, so **every tile
     needs both files**;
  3. a `.modal` + `.modal-box .modal-<name>` block, left pane = `.pane-title` +
     `.pane-text` (+ `.modal-icon` gif top-right), right pane = `.media` frames
     holding a `.media-img` or a dashed `.placeholder` while art is pending.
  The generic script wires open/close (X, backdrop, Escape) off those classes —
  a new tile needs no JS. Icon sources are GIMP `.xcf` files kept next to the
  exported png/gif in `site/assets/icons/`.
- Two panes are live rather than static: the resume tile's fast facts patch in a
  computed age and the Duolingo streak, and the music tile fills recently-played
  and top-artists from the Spotify proxy, plus a concert carousel driven by
  `site/assets/music/concerts.json` (add a concert by appending to that JSON —
  no code change).
- `site/wii/index.html` is the Wii menu (was `public/wii/index.html`, briefly at
  root). Warning screen fades into a channel grid. The bottom-left gray slot is a
  **Ticket to Ride channel** (`#channel-ttr`) whose click handler navigates to `/ttr`.
  Its `../../images|audio|videos` paths assume it sits at root, so some break at `/wii/`.
- **`site/warning.html` is gone** (deleted in `d0a282b`) but `site/wii/index.html`
  still navigates to `warning.html`, so the Wii menu's "reset" path 404s into the
  Mario game. The `warning.png`/`warning.wav` assets are still there, so restoring
  the page (at `site/wii/warning.html`, since the link is relative) would fix it.
- `site/channels/{mii,music,codebusters}/` - the Wii channel pages. They
  reference shared assets with `../../images|audio|videos/…` (resolves to root).
- `site/home/index.html` - the **projects landing page** (was the site's old `/`).
  Its assets live in `site/home/{images,audio}/` and `Chinmay_Govind_Resume.pdf`.
- `site/{projects,games}/` - standalone project/game pages (astro, ibec, quickcal,
  robot-tour, bridge, flip, klotski, roll), copied unchanged.
- `site/{images,audio,videos}/` - shared media (Wii menu art + channel media).
- `site/404.html`, `favicon.ico`, `robots.txt` at the root.

## Unlinked pages (nothing on the site links to these)

The landing page's tiles only open modals or point off-site (ttr/ers/kot subdomains,
the resume PDF, YouTube, PennToday). **No internal HTML page is linked from `/` at
all**, so every page below is reachable only by typing its URL:

- **Orphaned outright:** `games/flip/` ("Flip - The Game"), `games/klotski/`
  ("Klotski"), `games/roll/` ("3D Ball Roll Game" — note this one has a live
  backend, `/api/roll/gemini`), `wii/`, `channels/mii/`, and the local
  `projects/ibec/` copy (7 leftover template pages: committees, contact, events,
  membership, left-/right-/no-sidebar).
- **Orphaned transitively:** `home/index.html` (the old projects page) has no
  inbound links either, so the things only *it* links to are also unreachable:
  `projects/astro/` (AstroGPT), `projects/quickcal/`, `projects/robot-tour/`,
  `games/bridge/` (Penn Bridge sim, plus the `projects/bridge/` redirect stub),
  `channels/music/` and `channels/codebusters/` (+ its `pattern.html`).
- `site/404.html` (Mario game) is by design only reachable via a bad URL.
- **Two stale links to fix if you re-link things:** `home/index.html:591`'s "Wii
  Channel" tile points at `../`, which was the Wii menu when it lived at `/` but is
  now the landing page — it should be `../wii/`. And the Wii menu itself only
  navigates for the TTR slot; the mii/music/codebusters channel pages are not
  wired to any channel tile.

## Conventions / gotchas

- **Links are relative** and assume `site/`-as-root. When adding pages, keep paths
  relative; the only absolute paths are a couple that already encode the page's
  own location (e.g. astro's `/projects/astro/static/…`) and `site/404.html`'s
  `/home/audio/…` (absolute so the 404 game works at any URL).
- This site was lifted from `chinmaygovind.github.io/public`. The Wii menu briefly
  sat at `/` but now lives at `/wii/`; `/` is a simple landing page and the older
  projects page stayed at `/home/`. Dead Create-React-App refs (`%PUBLIC_URL%`,
  `logo192.png`, `manifest.json`) were removed.
- **TTR is never reverse-proxied** - its templates hardcode root-absolute paths
  (`/lobbies`, `/login`, `/static/…`) and connect Socket.IO at root, so it can
  only run at a host's root. `/ttr` just redirects to it. Change the target via
  `TTR_URL`, not by mounting TTR under a path.
- `ttr/` is a **submodule**; edit TTR in its own repo, then bump the pointer here.

## Accounts (`accounts/`)

**Live at `cgovind.com/accounts`.** One profile per person, spanning all four
games — a blueprint on the website app (port 5002, no service of its own),
reading the same SQLite file everything else does. It is not a fifth account
system: `users` and the session cookie were always shared, and these are the
pages that were missing from the system that already existed.

- **`/accounts/<username>` is public**, and the username in it is **permanent** —
  it is the login and the address of the profile, so a link to somebody keeps
  working. The name every screen *shows* is the **display name**, which is
  editable, unique case-insensitively, and may not collide with anybody else's
  username either: two rows reading "chinmay" on one leaderboard is the
  impersonation the constraint exists to stop. It reaches the games through
  `get_effective_name()`, which now returns `user.display` — one line per game,
  so a name set here follows somebody into every lobby, table and grid.
- **The page is a hero, a strip and tabs.** Picture, display name, flag, where
  they're from and `joined on 9/22/2024`; then all four games as chips whether
  or not they have been played (a chip that vanishes when it is empty is a chip
  you go looking for); then one panel per game with that game's own figures and
  its last few results. Tabs are **links** (`?game=ers`), so a panel is
  shareable and works with no JavaScript; the script only saves the round trip,
  and uses `replaceState` — which game you are reading is a setting inside one
  visit, not somewhere to press Back out of.
- **The look is the landing page's, not Drive's.** xkcd Script on white with
  thick drawn borders and the per-game accent colours already in
  `site/index.html`'s `:root`. Drive's account page is a lovely timing screen,
  but it is *Drive's*: a page spanning four games cannot wear one of their four
  faces. Every box's corners are four slightly different radii (`--wobble`), and
  panels alternate between two of them, so no two outlines repeat.
- **The settings cog is the only thing that marks your own profile.** It goes to
  `/accounts/settings`, which is two boxes: who you are (picture, display name,
  country, state, flag) and how you log in (password, email). Changing a
  password or an email needs the **current password typed again** — a session
  cookie gets left behind on shared machines.
- **Recent games are read four different ways**, because the games record four
  different things. TTR keeps a row per player per game (`game_results`), so
  that is the list. ERS and KoT keep a whole-game replay whose finishing order
  is `state_json['standings']`, keyed by pid — a game with no standings was
  abandoned rather than finished and is skipped, since reporting it would be
  inventing a result. Drive's is personal bests interleaved with races, because
  most of Drive is solo and a history that left the laps out would be a strange
  one.
- **A recent row is dated to the second**, `8/2 · 14:23:05`, not just to the
  day. A date on its own puts two games from the same evening on the same row
  twice, and "when did I actually set that" is the question the list is read
  for. Served in **UTC**, because that is what the database holds and what is
  right before any script runs, then rewritten into the reader's own timezone
  by the script at the foot of `profile.html` — the same trick Drive's records
  table uses, and the `title` keeps the year and the zone. 24-hour on purpose:
  it is the same width before and after that script lands, where an AM/PM
  stamp is wider and makes the column jump as the page settles. The column is
  a **fixed** `9.4rem` rather than `auto` because every row is its own grid,
  so nothing lines them up except that number.
- **`accounts/gamestats.py` reads the games with raw SQL on purpose.** Mapping
  four more schemas here would be duplication kept in step with four other
  repos' columns, and worse, a mapped table that does not exist is an error at
  query time — a game not installed on this box, or a fresh dev database with
  only `users` in it, is an ordinary state a profile must *render*, not crash
  on. `_table_exists` makes a missing game a game with no stats.

### Flags

- **Country flags are SVG, US state flags are PNG**, and that is not an
  oversight. `site/assets/flags/country/` is 254 flags from flag-icons (MIT):
  most national flags are a few rectangles, so they are 4KB and crisp at any
  size. State flags are a seal on a blue field — Kansas is 246KB of SVG,
  California 165KB, and neither survives being drawn 20px wide — so
  `site/assets/flags/us/` is 56 PNGs rasterised once by Wikimedia at ~330px.
- **The picker is generated from the directories** (`tools/build_places.py` →
  `accounts/places.py`), so a code can never be offered without art behind it,
  and a test asserts both directions. Offered: ISO 3166-1, plus England,
  Scotland, Wales, Northern Ireland and Kosovo. Not offered: the EU, the UN,
  ASEAN, Catalonia and the pseudo-codes — flags, but not nationalities.
- **A US profile can fly its state's flag instead**, and the three conditions
  (in the US, a state chosen, asked for it) are checked in exactly one place,
  `places.flag_of`. A stale `flag_pref` left behind by somebody moving country
  therefore cannot fly a state flag over another country's name.
- **The art is one copy, on the main site**, and the games reference it by
  absolute URL through `MAIN_SITE_URL`. That name is deliberately **not**
  `SITE_URL`: on the box `SITE_URL` already means *this service's own* address
  (`drive/.env` sets it to `https://drive.cgovind.com`), and borrowing it would
  point every flag at a host that does not serve them.

### Getting back in

`/accounts/forgot` is what the four login screens link to. **There is no table
of outstanding tokens**: a link carries a fingerprint of the thing it is allowed
to change, so *using it destroys it*. A reset link is signed over the current
password hash — set the password and the link stops validating, which is what
"single use" has to mean — and an email-change link is signed over the address
it replaces. That also survives a restore from backup, where a table of spent
tokens would not.

- **The forgot box answers the same way whatever happens** — sent, not sent, no
  such account, mail server down. Anything else turns it into a way of asking
  which addresses have accounts here.
- **An email change waits for the new address** to open a link before anything
  moves, so a typo cannot lock somebody out of their own future resets, and the
  **old** address is told afterwards — a takeover changes the address first, so
  that notice is the only warning the owner would get.
- Mail goes over the box's existing Gmail app password (the same account TTR has
  been sending from). **Unconfigured is a supported state**: with no `SMTP_HOST`
  the letter is printed to the log, link and all, which is how the flow stays
  walkable locally and how the tests read it.
- **TTR's `/account/update` used to change a username or an email outright** — no
  password, no confirmation. Both branches now refuse and point here. It had to
  be the *route*, not just the form: leaving it would have been a way round both
  rules, one page over.

### Pictures

Uploads are decoded, centre-cropped, resized and **re-encoded** by Pillow, and
only the bytes Pillow writes are kept — an image that survives that round trip
is not still carrying a payload, and a file that was never an image does not
survive it at all. The **stored name is ours** (`7-9f3a1c2b.webp`, hashed over
the finished bytes), because an uploader who picks the filename picks the URL,
the extension and the content type. That hash is also the whole cache strategy:
a new picture is a new URL, so nothing is ever invalidated. Files live in
`AVATAR_DIR`, which in prod is **outside the repo** (`/home/ubuntu/avatars`) so
the deploy's `git reset --hard` can never be near them.

**No picture is a look, not a gap**: an initial in the site's own font on a
colour hashed from the username, drawn *in the page* rather than served as an
image — an `<img>` cannot load a webfont, and the initial is the whole picture.

### Tests

`scripts/tests.sh site` — 122 tests, about 15s, plus the `import app` check the
deploy used to be. `tests/test_no_drift.py` is the one to know about: five
services each own a copy of `User` and now of `UserProfile`, which is this
repo's convention and the right one for five things that deploy separately, but
a drifted copy is worse than no copy. So every deliberate duplication —
the rating tiers, Drive's track names, the reserved usernames, the profile
columns, the display-name wiring, the forgot link, the route from a board to a
profile, `MAIN_SITE_URL` — has a test that **reads the other file** and fails
when the two stop agreeing.

**Its TTR checks skip unless the submodule is checked out**, which it is not in
CI (nor in a plain clone), so six of them read as passes there. That is on
purpose — `ttr/` is a separate repo with its own CI and the deploy never builds
it — but it means the TTR half of the agreement is only actually checked on a
machine that has run `git submodule update --init ttr`, i.e. when somebody is
changing TTR anyway. If you touch the shared profile columns, run it there.

## Egyptian Rat Screw (`ers/`)

**Live at `https://ers.cgovind.com`** (TLS via certbot). A second real-time game in the
`ers/` subdir (NOT a submodule) that **shares TTR's accounts**. Flask + Flask-SocketIO,
its own eventlet gunicorn `-w 1` on `127.0.0.1:5003` (single worker required: socket rooms
+ game state live in-process), its own venv (`ers/venv`) and `.env` (both gitignored,
hand-created on the box). The engine is server-authoritative; the first valid slap under a
per-game lock wins.

- **Shared accounts:** `ers/.env` sets `DATABASE_URL` to the SAME SQLite file the live TTR
  uses and reuses TTR's `SECRET_KEY` + `SESSION_COOKIE_DOMAIN=.cgovind.com`, so one login
  works on both sites. `users` is the shared account table; ERS creates `ers_stats` /
  `ers_games` / `ers_players` / `ers_slaps` in that same file (WAL + busy_timeout for
  concurrent access). ERS's `User` model maps only the account columns.
- **Prod DB path gotcha:** the live TTR does NOT run from this repo's `ttr/` submodule; it
  runs from a **separate clone `/home/ubuntu/TicketToRide`** (systemd `tickettoride`, port
  5001), whose db is `/home/ubuntu/TicketToRide/instance/tickettoride.db` -- that is the
  shared file `ers/.env`'s `DATABASE_URL` points at.
- **SSO:** every service signs the same `.cgovind.com` cookie with the shared `SECRET_KEY`,
  so one login covers all of them and the accounts pages. This was one-directional for a
  long time -- TTR's `.env` was missing `SESSION_COOKIE_DOMAIN`, so a login there set a
  host-only cookie and did not carry out. If TTR logins stop carrying again, that line in
  `/home/ubuntu/TicketToRide/.env` is the first thing to check.
- **The `ttr_stats` refactor IS deployed** (this used to say the opposite). The live clone
  is on the same commit as this repo's submodule pointer and `ttr_stats` is the fresher
  table -- the legacy `users.elo` columns are still there but stopped being written, so
  anything reading them is reading a snapshot from whenever the refactor shipped. Read
  `ttr_stats`.
- **Layout:** `ers/app.py` (auth + lobby routes ported from TTR, socket game loop, bots,
  ELO/stats finalize, ping, spectators, kick/leave), `ers/game_logic.py` (pure, unit-tested
  rules engine -- `scripts/tests.sh ers`), `ers/models.py` (shared
  `User` + `ErsStats`/`ErsGame`/`ErsPlayer`/`ErsSlap`), `ers/templates/` + `ers/static/`
  (wooden oval table, xkcd Script font, gold, pyramid PWA icons, synth `flip.wav`/`slap.wav`).
- **Rules:** royalty tribute (A/K/Q/J owe 4/3/2/1); slaps = double, sandwich, top-matches-
  bottom, add-to-ten, King+Queen; a wrong slap burns 1 card + a 2s freeze; **one life** to
  slap back in after running out; last player holding all 52 wins. Bots (`is_bot` ErsPlayer
  rows) slap with `max(0.5s, Exponential(mean 2s))`, driven by eventlet timers.
- **Feel:** everyone is a seat (dot + count + name) around the table, your flip pile
  down-left and SLAP down-right of your seat; a card flies from a seat and flips into the
  pile in one motion; a colored hand smacks on every slap (red X on a wrong one); cards
  slide to whoever wins the pile; a wrong slap lifts the pile to slide the burned card
  under face-up; scrollable fading chat; live ping; spectators can watch playing games.
- **Full game history:** every game's move-by-move replay is in `ers_games.events_json`;
  each slap is also a row in `ers_slaps` (with `reaction_ms`) -- e.g. a reaction-time
  distribution is `SELECT reaction_ms FROM ers_slaps WHERE valid=1 AND reaction_ms IS NOT NULL`.

**ERS deploy:** pushes to `main` run the usual Action, which now also (when `ers/.env`
exists on the box) builds/updates `ers/venv` from `ers/requirements.txt` and
`sudo systemctl restart ers`. nginx has an `ers.cgovind.com` vhost (`sites-available/ers`,
proxy to `:5003` with WebSocket upgrade) with its own Let's Encrypt cert; Route 53 has the
`ers.cgovind.com` A record. `/ers` on the main site 302-redirects there (`ERS_URL`). nginx,
TLS, DNS and `ers/.env` are all hand-managed on the box (not shipped by the Action), same as
the rest of the deploy. See the `prod-infra` memory for the full box layout.

## King of Tokyo (`kot/`)

**Live at `https://kot.cgovind.com`.** The third game, same shape as ERS: Flask +
Flask-SocketIO, its own eventlet gunicorn `-w 1` on `127.0.0.1:5004`, its own venv
(`kot/venv`) and `.env` (both gitignored, hand-made on the box), sharing TTR's `users`
table for accounts. Stats live in `kot_stats`, games in `kot_games` / `kot_players`.

- **Layout:** `kot/game_logic.py` (pure rules engine), `kot/cards.py` (all 66 power
  cards), `kot/bot.py` (the bot brain, also pure), `kot/app.py` (auth, lobby, socket
  game loop, bot orchestration, ELO), `kot/models.py`, `kot/templates/` + `kot/static/`.
- **Tests:** `scripts/tests.sh kot` - `test_engine.py` covers the
  rules, `test_bot.py` covers the bot (liveness, legality, latency, strength).
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

## Drive (`drive/`)

**Live at `https://drive.cgovind.com`.** The fourth game, same shape as ERS/KoT:
Flask + Flask-SocketIO, its own eventlet gunicorn `-w 1` on `127.0.0.1:5005`, its own
venv (`drive/venv`) and `.env` (both gitignored, hand-made on the box), sharing TTR's
`users` table for accounts. A PolyTrack-style low-poly driving game: twelve
point-to-point time-trial tracks, medal times, ghosts, and multiplayer rooms.

The last three in the pool are the long ones, all difficulty 5 and all roughly
twice The Gauntlet: **Sandy Cove** (`cove`, a ground track - a coast road down
onto the beach and out along a pier over open water), **Cloudbreak** (`pillars`,
threaded between rock spires above an overcast) and **Rainbow Road** (`rainbow`,
half-pipes in deep space with almost no barriers). Cloudbreak and Rainbow
Road are both in `tracks.EXPOSED`.

- **Guests can play, and a guest's times are not thrown away.** Driving alone needs
  no account at all (`/`, `/solo` and `/solo/<slug>` are open); sharing a room needs
  only a name (`/guest`). A guest's runs are kept *whole* - time, splits and replay -
  in `localStorage` by `static/js/pending.js`, best one per track, and submitted
  through the ordinary `/api/run` the moment the browser is logged in. That script is
  on **every** page via `base.html`, because the login that unlocks the times happens
  on `/login`, a page the game code never runs on. A rejected run is dropped (the
  server will not change its mind); a *failed request* is kept, so an offline lap
  goes up when you reconnect. `test_pending.js`-style coverage lives in
  `tests/test_pending.py`, which runs the real file in QuickJS against a stub browser.
- **Starts are counted as well as finishes**, because a board of finishes cannot
  say how many goes a track took out of you - and on a hard one that is most of
  the story. An attempt is *the clock starting*: `/api/start` is posted from the
  one place in `game.js` that calls `run.start()`, which is why loading the
  page does not count as one. A lap in a **room** is not counted at either end
  - see the leaderboard rule below. They live in their own `drive_starts` table, one row per (user, track) -
  `create_all` creates tables and not columns, so a new table lands on the live
  database by itself where a new column would need a migration, and a track you
  have started fifty times and never finished has no `drive_times` row to keep
  the count in. Finishes are not duplicated there; they stay in `DriveTime.runs`
  and `DriveStats.runs`. **A finish floors the start count in the row**
  (`_floor_starts`), because a finish implies a start but not that one was
  *recorded*: a guest posts none at all and their kept laps arrive at `/api/run`
  at login. Clamping only on the way out to the screen looks identical and is a
  trap - the next real start lands on a stored 0, disappears under the backlog of
  finishes, and goes on disappearing until it catches up, so the number looks
  right and stops moving. `tools/backfill_starts.py` is the same floor applied
  once to everything that was already there; **run it on the box right after the
  deploy that creates the table**, `--dry-run` first. It is a `max` per row, so
  it is safe to run twice. `_starts_for` still clamps on read, now only as cover
  for a database the backfill has not reached.
- **The leaderboard is for laps driven alone against the clock, so nothing set
  in a room reaches it.** No time, no medal, no ghost, no distance, and no
  attempt either: `countsForTheBoard()` in `game.js` is the single answer, and
  both `/api/run` and `/api/start` read it, so the two halves of a lap counting
  cannot disagree and leave a track with more finishes than goes. It applies to
  a room's free practice as much as to a race, because there are other cars on
  the road in every phase of one - **a tow down a straight is worth the better
  part of a second**, contact moves you, and a race starts from a rolling grid
  rather than a standing lap. A time set that way is a record of the traffic
  rather than of the driving, and it was going on the board next to laps that
  were not. It cost a real record: a Jump City lap set in a race sat top of the
  board until the holder asked for it to be taken off. The room's own ghost is
  unaffected - your best lap *here, today* is what a room is for.
- **Being fast is not evidence of cheating.** There used to be a floor here:
  `tuning.MIN_PLAUSIBLE`, rejecting any time under 0.8 of `ideal`. But `ideal` is an
  estimate off a relaxed racing line and anyone who learns a track beats it, so the
  floor was measuring how conservative the estimate was, not dishonesty - and it
  punished exactly the people driving best. It is gone. What a run still has to
  survive is entirely about the *replay*: right duration, no teleports, starts on the
  line, through every checkpoint in order (`runcheck.validate`).
- **Layout:** `tuning.py` (every physics constant, in one place), `tracks.py` (the
  ribbon format + the pool, authored with a turtle `Builder`), `laptime.py` (racing-line
  relaxation + speed profile → medal times), `runcheck.py` (ghost packing, time
  validation), `models.py`, `app.py`, `static/js/` (`trackmesh.js`, `physics.js`,
  `course.js`, `render.js`, `sound.js`, `game.js`, `pending.js`, vendored
  `three.module.js`), `tools/shoot_tracks.py` (the preview pictures). The play
  page has three modes - `solo`, `room` and `replay` - and they are one template
  and one `game.js`, because a replay is a track, some cars and a clock and that
  is what the game already draws.
- **Three medals, and gold is the best one.** There used to be a fourth above it,
  `author`, at 0.94 of the ideal lap. The word names an authority rather than a
  standard, and it sat above the medal everybody already reads as the top one. The
  times did not move when it went, so nobody lost a medal - an old `author` row is
  shown as a gold by `DriveTime.medal_shown`, and `_MEDAL_FIELD` keeps the key so
  improving on one still decrements the right counter.
- **`MEDAL_MULT` is set against real times, not against the estimate.** It was
  1.04 / 1.18 / 1.42, calibrated off the simulated driver, and it was far too
  soft: every record actually set on the site sits between **0.77 and 0.90 of
  `ideal`** (mean 0.85), so a 1.04 gold was slower than what people were
  already driving and bronze at 1.42 could not be missed. The spread was the
  other half of it - gold to silver was 2.8-5.7s and silver to bronze 4.8-9.7s,
  three unrelated standards rather than three steps of one. Now **0.92 / 0.99 /
  1.07**: gold is beaten by the standing record on every track but only just on
  the tightest (Spiral Ascent, by 0.4s), and a step is a second and a half on
  the short tracks, three on the Gauntlet. Note `ideal` is a worse *per-track*
  predictor than the mean suggests (0.77 on Chicane Park against 0.90 on Spiral
  Ascent), so one global multiplier makes some golds harder than others - the
  fix for that is a better `laptime.py`, not per-track fudge factors. Two tests
  pin the intent (steps under 0.09 of the lap; gold under `ideal`), and
  `test_medals_bracket_the_simulated_driver` still requires the headless driver
  to manage a bronze. **Medals already earned do not move**: `DriveTime.medal`
  is written when the run is stored.
- **The record heads the medals card**, above gold/silver/bronze, as a green
  dot and a time laid out exactly like the three under it - the fourth time on
  the same list. Green because it is not a medal and cannot be won. **The
  holder's name is not on it**: whose lap it is belongs on the leaderboard, not
  on a card read at 200km/h with three other times on it, so `_track_payload`
  does not even send it. It rides along on the track payload (`_track_payload`,
  used by `/api/track/<slug>` *and* the play template) rather than in a request
  of its own, so it is right on the first paint and follows the switcher. That
  helper returns a **copy** - the dicts in `tracks_mod` are module-level and
  shared by every request.
- **`tuning.py` is the single source of truth for the simulation.** It is embedded in
  the play page as `window.DRIVE_TUNING` and read by the JS physics, and `laptime.py`
  uses the same numbers to derive medal times. There is deliberately no second copy of
  `ACCEL` in a .js file. Retuning the car retunes the medals.
- **A track is a ribbon of stations, not a grid of tiles.** Each station carries a
  centre `p`, a surface normal `n`, a road-right vector `lat` and a half-width `hw`,
  about 3.5 units apart; the road is the strip of quads between consecutive stations.
  That is the *whole* geometry - `trackmesh.js` is one loop over pairs. It replaced an
  8-unit grid of 90-degree corner tiles, which made every corner the same corner with a
  4-unit centreline radius no car could hold, and made a smooth elevation change
  impossible (a ramp was a crease between two flat tiles). Consequences worth knowing:
  corner radius and road width are free parameters, a gap is just stations flagged
  `air`, a barrier is a `wl`/`wr` flag on an edge, and a loop is a station list whose
  normal rotates.
- **A station can also carry a cross-section, and that is how half-pipes work.**
  `pf` is a list of `[u, rise]` samples across the road - `u` from -1 to +1 as a
  fraction of `hw`, `rise` along that station's own normal - and the road there
  is the quads between one station's samples and the next one's. Still the same
  loop, so **the collider, the mesh and the car need no idea a pipe exists**: the
  ground query finds the closest surface and steering is applied about its
  normal, which is the identical reason a loop needs no special case. Authored
  with `Builder.pipe(depth, floor, side)` / `.flat()`, which blend the depth in
  and out over `PROF_BLEND` units - a pipe at full height in one station is a
  wall you hit rather than one you ride. `side='l'`/`'r'` gives a one-sided
  banked wall on a corner's outside, and **that is the shape the pool mostly
  uses**: Rainbow Road has exactly one full trough and two one-sided banks, on
  the outside of the corner each time. A V taking up the whole road is a thing
  you sit in rather than a line you pick, so one of them is a feature and three
  of them is a bobsleigh run. Two things to know: **the samples are baked
  in Python** and the JS only reads them, so there is no second copy of the
  curve to drift; and **a gate may not sit on a profiled station** (`_gate`
  raises), because a gate is a flat plane of fixed width and hanging one across
  a trough puts its posts up the walls and its mouth out of reach.
- **The collision surface IS the render surface.** Every driveable quad goes into both
  the mesh and a spatial hash, so hills, banks, loops, crests and crossings all work
  through one closest-point query with no per-shape special cases - and nothing can look
  solid without being solid.
- **Steering rotates the car about the surface normal, not world up**, which is the
  whole reason a fully inverted loop needs no special case in the car code. Gravity is
  always applied and its normal component removed while grounded, so slope acceleration
  falls out for free.
- **Grass is meant to hurt.** `OFFROAD_DRAG` is a linear term, so the grass top speed
  is where `ACCEL - quadratic drag - OFFROAD_DRAG*v` hits zero: about half of
  `MAX_SPEED`. It was 0.55 (grass top speed ~36 against a road top speed of 44),
  which made a straight line across the infield simply the faster way round a corner.
  `test_grass_costs_you_the_corner` pins it as an acceleration budget rather than by
  driving anywhere, so it does not depend on where the grass happens to be.
- **Air pitch is deliberately lazy.** Holding the throttle pitches the nose down at
  `AIR_PITCH`, and `ALIGN_AIR` (which only runs when there is *no* pitch input) noses
  a car that took off from an uphill ramp down as well. At the original 1.5 and 2.6 a
  jump taken flat out - which is how every jump is taken - was pointing at the floor
  half a second off the lip. `test_the_car_does_not_nosedive_off_a_jump` bounds the
  drop over the first half second and still requires enough authority to aim.
- **Gate posts are walls, not scenery.** Every checkpoint's two posts go into the
  collider as well as the mesh, and sit just outside the kerb so the full road stays
  usable. `test_checkpoint_posts_are_solid_and_the_gate_is_not` pins both halves: the
  posts stop a car, and the mouth of the gate stays completely open.
- **How high a checkpoint counts is the track's business, not a constant.** A gate
  is credited on a plane crossing inside a window, and the roof of that window
  used to be a flat 5 units on every track - lower than the car actually gets, so
  landing a jump long or coming over a crest in a tow flew you *over* a
  checkpoint without being credited for it, losing a lap you had driven. It
  cannot simply be raised: the roof is what stops a car on a bridge triggering
  the gate on the road underneath it. So `tracks.gate_ceiling` derives it per
  track from the one number that decides the answer - the closest this track ever
  passes over itself. Tracks that never cross themselves (most of them, including
  the one made of jumps) get the full 14; Spiral Ascent, whose helix stacks 10
  units above itself, gets 6.4 and stays honest. A test asserts the ceiling is
  below every crossing on every track, which is what makes the generous number
  safe.
- **The car is not glued to slopes.** `SNAP` is a 0.12-unit seam tolerance, nothing
  more, and there is no term scrubbing velocity along the surface normal - so a crest
  throws the car, as it should. `STICK_FORCE` only engages past `STICK_TILT` (about 32
  degrees off level), which in the pool means a loop's wall and roof and nothing else.
  Hills are *authored* smooth instead: `straight(l, rise=r)` smoothsteps its grade so it
  has no crease, and `crest`/`hump`/`jump` deliberately do, marking their stations
  `kick`. A hill needs `length >= sqrt(330 * rise)` or it becomes a jump by accident;
  `test_hills_are_eased_but_kickers_are_not` enforces it as a vertical curvature radius.
- **There are no vertical loops and no boost pads.** A plain vertical loop returns to
  exactly where it started, so its descent lands on its own climb - two surfaces a metre
  apart, which trapped cars. `Builder.loop` slides the exit sideways (smoothstepped, so
  both joins stay tangential) which fixes it completely. A helix about the direction of
  travel is the obvious alternative and does not work: its tangent sits ~55 degrees off
  its own axis, so it meets the road at a kink and the car drives into the barrier.
  Loop radius is bounded by physics - on the wall only `STICK_FORCE` opposes `v^2/R`, so
  radius 20 is about the minimum at racing speed.
- Tracks that float in the void (`ground: None`) are built with `rails=True`; tracks on
  the ground are not, so running wide there costs grass time instead of a respawn. The
  road sits ~1.2 above the grass plane, which is both why it reads as a raised ribbon
  and why the two never z-fight.
- **A floating track can opt out of rails, and Rainbow Road is the one that
  does.** `tracks.EXPOSED` is the set where falling off is the point rather than
  a gap in the barriers, and `test_barriers_are_opt_in` then checks the claim in
  *both* directions - a track wearing the flag with rails all down it fails just
  as loudly as a normal floating track without them, which is the more likely
  mistake, since the flag outlives whoever railed the track for safety. Loops
  keep their rails even there: a loop without them is a fall at the top rather
  than a corner, which is not exposure, it is a broken corner. Cloudbreak is in
  the set for the same reason it was worth building: railing every corner of a
  track whose whole subject is how far down the ground is takes the height away
  and leaves a bobsleigh run. The rails it keeps are for where going off is not
  an avoidable mistake - the two jump landings, where you arrive with no
  steering, and the narrow bridge. **Pulling rails off is a change the autopilot
  has to survive**: Cloudbreak went from 98% walled to 9%, and
  `test_a_clean_lap_needs_no_respawns` is what says the line was always
  drivable rather than being held in by the barriers.
- **The three long tracks are ~2500-2800 units and 56-64s of ideal lap**, against
  The Gauntlet's 1667 and 40s. Two ceilings bound that: `test_tracks` caps an
  ideal lap at 120s, and `test_sim` caps the *simulated driver* at 90s - and the
  autopilot runs about 1.04x ideal, so ~64s ideal is roughly the practical limit.
  Every one of them still has to be driven to the finish with **zero respawns**
  (`test_a_clean_lap_needs_no_respawns`), so "easy to fall off" has to mean
  punishing when you leave the line, never that the line itself is marginal.
- **The ghost is a practice tool, so in a room it belongs to the phases you drive
  alone in** - free practice and qualifying - and to neither of the others. It is
  not rendered at all from the countdown to the flag, whatever the setting says:
  a translucent car on a line nobody drove is one more thing to mistake for a
  rival. Qualifying is the opposite case and used to be lumped in with the race,
  which was wrong for the same reason - it is the session where you are alone
  against a clock, which is exactly what a ghost is for.
- **A room's four ghosts are not solo's four.** Off, **your best lap of this
  practice session** (not your all-time PB, which was set on a different day
  against nobody), **provisional pole**, and the world record. "View others" is
  not offered in a room: everybody there is on the road with you, and the board
  is a list of people who are not. `G` steps through all four.
- **Provisional pole is a live ghost of the lap that is currently taking pole.**
  A qualifying lap goes up with its replay attached (`qual_time` carries the
  frames), the server keeps **only the leader's** and throws the rest away, and
  a change of pole is broadcast as one line - who, and what they did. The lap
  itself is tens of kilobytes and most of the room is not chasing it, so it is
  fetched by the people who are (`qual_pole_req`). Chasing yourself is not
  chasing anybody, so if pole is yours no ghost is loaded - your own best lap of
  the session is already what `me` means there, and it is the same lap. It is
  dropped when the session ends: after the flag it is the grid, not a target.
- **Every ghost is the colour of whoever drove it**, and so is every car that
  person turns up in. There was no per-person colour at all before - a room
  handed them out by seat and solo was always red - so `color_for(username)`
  hashes one out of `garage.HASH_COLORS`, the same trick the accounts pages use
  for the initial on a profile with no picture. That is still the answer for
  anybody who has not chosen; what a car looks like once they have is **The
  garage** below.
- **A ghost lights its own brake lights**, because the flag byte is recorded
  with the pose. A ghost frame is eight values now, not seven, and `pack_ghost`
  writes the stride into the blob: every lap already on the board is seven
  wide, still unpacks, and simply has no lamps until it is driven again.
- **A ghost frame is the pose at its own timestamp.** `Run._recordGhost` interpolates
  to exact multiples of `1/GHOST_HZ`. It used to accumulate dt and push a sample every
  time an interval had gone by, which meant the accumulator had to fill before frame 0
  was written - so frame 0 was the pose one interval *after* the start. Playback reads
  frame `t * GHOST_HZ` at run time `t`, so every ghost ever recorded played back 1/15s
  ahead of the lap it recorded: a couple of car lengths up the road, from the line to
  the flag, which is why the ghost appeared to start in front of you.
  `test_the_ghost_is_recorded_where_the_car_actually_was` drives a lap, notes where the
  car really was at each sample time and requires the two to agree.
- **Live races are in memory, not the DB.** A race ticks 30x/sec: clients are
  authoritative over their own car and emit `pose`, the server merges and fans out one
  snapshot per tick, and only the finished standings are written back. Cars are solid,
  resolved Mario-Kart-style (impulse + penetration spring, never positional snapping,
  tangential velocity preserved, per-pair bump cooldown) - see `Car.resolveCars`.
  `FLAG.BRAKE` rides along in the pose so a rival's brake lights work.
- **A hit only moves a car if the tyres let go, and that is not what anybody
  reaches for first.** Contact felt weightless, and the obvious fix - a bigger
  `CAR_REST`, a stiffer `CAR_PUSH` - does nothing at all: `GRIP` kills lateral
  velocity at `1 - exp(-GRIP*dt)` per step, so a sideways impulse is gone inside
  a tenth of a second *however large it is*. Measured, raising both of those
  moved a 14 u/s side-swipe from 0.26 units of displacement to 0.25. The car is
  bolted to its heading and no impulse gets to argue. So a firm hit briefly
  unsettles the car instead: grip falls to `BUMP_SLIP_GRIP` (4, about halfway to
  the handbrake's own 2.4) and recovers over `BUMP_SLIP_TIME`, which takes the
  same swipe to 0.99 and a 20 u/s punt to 1.57 - against a 1.9-wide car on a
  9-wide road, a place lost rather than a noise. **Neither number is scaled by
  how hard the hit was**, though every instinct says they should be: the impulse
  they are letting through already is, so scaling the window on top of it squares
  the relationship and an ordinary firm shunt comes out moving the car *less*
  than the same shunt on full grip would suggest. The timer is decayed with the
  other per-step timers rather than in the grounded branch that reads it, or a
  car knocked into the air holds the whole of it frozen for the flight and lands
  on a slide a second after the hit that caused it.
- **Two thresholds, because there were two questions behind one number.** A
  single `hit > 5` decided both whether a contact was *reported* and whether it
  *cost* anything, so every touch under it was completely silent - no clank, no
  sparks, no camera kick, no lean - and running wheel to wheel down a straight,
  which is most of what contact in a race actually is, looked and sounded like
  driving alone. `BUMP_FEEL` (1.5) is when you are told and `BUMP_COST` (5, the
  old number, unmoved) is when it hurts. The gap between them is where racing
  side by side lives: heard, and free. Lowering one gate instead would have
  walked straight back into the compounding `CAR_BUMP_SCRUB`'s own note is
  about - the per-pair cooldown is 0.15s, so a second and a half of rubbing is
  about ten events, and charging speed for each of them is a tenth of your speed
  gone for touching somebody gently. **Everything a hit does now happens once**,
  on the event rather than per step of contact: that was already true of the
  scrub and quietly false of the other two, so the body lean climbed to its own
  clamp inside a tenth of a second (a car rubbing alongside somebody drove along
  at 29 degrees of roll) and the yaw - an angle with no `dt` on it - was worth
  radians a second for as long as the cars touched, which is the spin it is
  explicitly not supposed to be able to cause. `test_bump.py` pins all of it,
  and pins the grip release against *its own absence* rather than against a
  figure in a comment, since that comparison is the whole surprise.
- **A race is recorded off those same poses, and the recording outlives the
  room.** `_record_race` runs on the broadcast tick and writes one frame per car
  per `1/REPLAY_HZ` from the green light, so frame *n* of every car is the same
  instant and the whole thing plays back as one moment in time; a car that has
  stopped reporting repeats its last pose rather than leaving a hole, because a
  hole slides every frame after it and slews that car against everybody else's.
  It lands in **`drive_races`**, its own table - `drive_games` rows are deleted
  the moment a room empties or goes idle, which is right for a room and wrong
  for a replay, and a new table arrives on the live database by itself where a
  new column would need a migration. Each car's frames are packed exactly the
  way a ghost is, at the same rate and with the same flag byte, so a replay is
  not a new format: it is several ghosts sharing a clock. The newest
  `REPLAY_KEEP` are kept and the sweep drops the rest.
- **`/race/<id>` is the play page in a third mode.** A replay is a track, a set
  of cars and a clock, and the play page is the only thing that knows how to
  draw those - so `startReplay` generalises the single-lap watcher to N cars
  with one of them holding the camera, and the bar along the bottom is the
  drivers, clickable. The cars are fetched from `/api/race/<id>` rather than
  rendered into the page: eight replays of a two-minute race is most of a
  megabyte of numbers. It is offered from the results sheet (**Watch replay**),
  it is a plain URL, and it is public, so a race can be linked to afterwards.
- **Contact and the slipstream belong to free practice and the race, and to
  nothing else.** They are the same question - are the cars around you cars you
  are driving against - so they are one answer, `contactOn()` in `game.js`.
  Qualifying is the exception on purpose: everybody is alone on their own lap on
  a road they are all using at different points of it, so being punted by
  somebody a corner behind would take away the one thing the session is for, and
  a tow off a car you are not racing would hand out a grid slot nobody drove
  for. For those ninety seconds the rivals are drawn **see-through**
  (`CarView.setGhostly`, the same opacity the ghost uses) and you go through
  them: a solid-looking car you cannot touch is a bug until somebody explains
  it. Countdown and the results sheet are outside it too - there is nothing to
  race there. `test_slipstream.py` pins the phase table.
- **The slipstream is Mario Kart Wii's draft: it charges, then it pays.**
  `Car.draft` measures the tow in the *following* car's own frame - ahead along
  your forward axis, inside a narrow corridor either side of and above/below it,
  and pointing roughly the way you are - so it works upside down in a loop and up
  a banking with no special case, and you cannot tow off somebody crossing at a
  junction or coming the other way. Sitting in it pays **nothing** for
  `SLIP_CHARGE` seconds and then hands over the whole of it at once: a trickle of
  speed for following somebody is invisible and unearned, a boost you spent a
  second and a half lining up is a move you decided to make. **The boost is more
  engine, not a raised limit** - top speed is where `ACCEL` fights the quadratic
  `DRAG`, so `SLIP_ACCEL_MULT` 1.5 lifts it by its square root (about a fifth,
  50 -> 61) and you have to accelerate up to it. Nothing accumulates while a
  boost runs, so the cadence is charge, fire, charge rather than a permanent tow
  behind a car you cannot pass. `FLAG.SLIP` rides along in the pose - wired for,
  and like `FLAG.DRIFT` not drawn on a rival.
- **The slipstream is drawn round the car, not on the HUD.** `Draft` in
  `render.js`: streaks of air running past you, one camera-facing quad each,
  **thickening with the charge** - the same number the bar under the speed bar
  used to show, so you watch the boost coming without looking away from the
  road - and then going amber and flat out when it pays, petering out with the
  boost rather than being switched off. A bar said the same thing in a corner
  you cannot look at while you are two car lengths off somebody's bumper, and a
  "Slipstream!" toast said it a third time over the middle of the screen. The
  effect *is* the announcement now, with a whoosh, a camera kick and 7 degrees
  of FOV. Four things keep it a suggestion of air rather than a curtain: the
  streaks' long axis is the car's **own** forward (so a loop needs no special
  case) with only what is left over turned to the camera - turn them to it the
  ordinary way and they spin on screen and stop reading as motion, leave them
  and they vanish edge-on; the ring is an **arc over the top and round the
  sides, never underneath**, because the air under a car is the road and a
  streak drawn there is a bright bar lying on the tarmac; it is a **cone** -
  wide off the nose, drawn in tight against the flank, spilling out behind -
  which is both what air does around a body and what keeps it off the bodywork;
  and it **stops well short of the chase camera**, since air blowing through
  the lens is a windscreen. They are additive, so they stack: the fade envelope
  is deliberately steeper than a sine so each one is only briefly at full.
  **`?draft=charge|boost` pins the tow** so the whole thing can be
  photographed - same reason as `?panel=` and `?touch=1`, since otherwise it
  takes two browsers and somebody driving eight car lengths ahead of the
  shutter. The sound is the same story: `Sound.draft` opens a band of rushing
  air as the charge fills, so you can *hear* the boost coming.
- **Every car's tow is drawn, not just yours.** A `Draft` belongs to each remote
  as well, because the driver winding up behind your gearbox is the only person
  on the track who cannot see it - watching somebody else's air thicken is the
  whole of what makes a tow a move you can answer. It cost **one number on the
  wire**: `sl` in the pose, 0..1, with the `FLAG.SLIP` bit that was already
  there for the tail lamps saying whether it is the charge or what is left of
  the boost. Field 14 of the snapshot, appended like the age before it, and the
  client guards on the array's length, so a page open across a deploy loses the
  tow rather than reading a car's velocity as its position. `Draft` needed no
  idea any of this exists: a remote carries `pos`/`fwd`/`right`/`up`/`speed` and
  the two tow numbers, which is what a car is as far as the effect is concerned.
- **A car behind the leader gets a little more engine, in proportion to how far
  behind it is.** A race in which somebody drops three seconds is decided, and
  everybody in it then drives the rest of it alone - which is most of what a
  four-car room actually looks like, since one mistake or one respawn is all it
  takes. `Car.catchup(gapS, dt)` in physics.js is the curve and `gapToLeader` in
  game.js is the number it reads. Six decisions:
  - **The gap is measured in distance and reported in time.** What the room
    knows about every car is `prog` - it is on the wire, it is what the
    standings are ordered by - but the same 100 units is half a lap of Chicane
    Park and a corner of Sandy Cove. Dividing by `MAX_SPEED` gives the one
    number that means the same on every track: how long that ground would take
    flat out. Nobody averages `MAX_SPEED`, so it is a *floor* on the real gap,
    which is the right direction for a number deciding how much to hand out.
  - **The leader is the leader on the road, not the winner.** A car already home
    is not being caught, so a finisher is skipped and whoever is furthest round
    of those still driving sets the mark - otherwise the whole field gets full
    help the instant somebody crosses the line. Lead the cars still out there
    and the gap is zero, which is the same statement.
  - **Nothing inside `CATCHUP_DEAD`** (1.5s, about two seconds of real driving),
    then a linear ramp to all of it at `CATCHUP_FULL` (5s). Under the deadzone
    you are still racing them and a handout is the last thing that should settle
    it; a step change at a threshold is a car that surges every time the gap
    wobbles across it.
  - **More engine, not a raised limit**, the same term the tow multiplies, so
    `CATCHUP_ACCEL_MULT` is worth its square root in top speed and only while
    you are on the power. They **stack** - a car a long way down that has
    finally caught somebody is exactly the one that should be able to come
    past - and the pair of them still lands under the `MAX_SPEED * 1.7` clamp
    (71 against 85), or the clamp would be setting the top speed instead of the
    tuning.
  - **Full help is 180 on the speedo, and that is the form the number is kept
    in.** The HUD draws `speed * 3.1`, so 1.3486 puts the top of the ramp on
    exactly that, and `test_full_help_reaches_a_hundred_and_eighty_on_the_dial`
    pins the figure on the dial rather than a band around the multiplier -
    changing how fast the game is should have to be said twice. It was 1.22,
    which read 171 against a base of 155: about a tenth, which is not something
    you can feel from inside the car, and a mechanic nobody notices is not
    doing its job. That makes it worth about **three quarters of a tow**, where
    it used to be pinned deliberately under half on the grounds that being
    handed the bigger of the two would make dropping back the fast way round.
    The pin is gone and the fear does not survive the arithmetic: collecting
    the whole of this means actually *being* `CATCHUP_FULL` seconds down, and
    no amount of extra top end buys five seconds back inside a lap. What is
    still pinned is the direction - a tow has to remain the larger prize, or
    lifting off and waiting genuinely would be a tactic.
  - **Nothing is taken off the leader.** A rubber band that slows the car in
    front takes away the race it is trying to make, and the driver in the lead
    is driving the car they qualified.
  - **It follows the gap rather than tracking it** (`CATCHUP_SMOOTH`), because
    `prog` arrives 30 times a second, rounded to 0.1, off a car whose position
    is being extrapolated. Half a second of lag on a number describing the last
    ten seconds costs nothing and is the difference between more engine and a
    car that hunts. The tail of the ramp *down* snaps to zero; **only the way
    down**, and that is not a detail - every ramp up starts at zero and climbs
    through the same hundredth, so a snap that did not check the direction pins
    the help at nothing for ever. A test pins it, having caught it.
  **`catchupOn()` is the race and only the race**, which makes it deliberately
  narrower than `contactOn` - the only other phase gate here, and the difference
  is the justification. Free practice has solid cars and tows, because they are
  cars on a road with you, but there is no such thing as first place in it;
  qualifying is the one session whose whole job is deciding the grid; a
  countdown and a results sheet have nobody driving. It cannot reach the
  leaderboard by two independent rules - no room lap counts, and no lap outside
  a race gets this at all. **Nothing new goes on the wire**: unlike a tow it is
  not a move anybody makes or can answer, so a rival knowing you have it would
  change nothing they would do, and the gap that produced it is already on the
  standings board everybody can read.
- **Catching up is drawn on the speed bar, and the tow is not.** Opposite
  answers to the same question, for the same reason: the tow is aimed at the car
  in front, so it belongs in the air out on the road where that car can see it,
  and this one is aimed at nobody. It is a change in the engine, the bar is
  where the engine already is, and a car that is quietly faster than it was a
  lap ago and cannot say why is a bug report. Gold (the colour the HUD already
  uses for the row that is you), and it **wins over `over`**, which is on at the
  same time nearly always - more engine overruns `MAX_SPEED` on its own - and is
  the less useful of the two things to be told. `?catchup=<seconds>` pins the
  gap the way `?draft=` pins a tow: it is the only visible part, and
  photographing it otherwise takes two browsers and somebody five seconds up the
  road.
- **Other cars are heard as well as seen, and a rival is a place rather than a
  channel.** Engine, tyres and tow all go through one `PannerNode` at that car's
  position (`RivalVoice` in `sound.js`), with the listener riding the **chase
  camera** - the only frame in which "on my left" is the same statement on
  screen and in the headphones, and one that rolls through a loop with no
  special case. **HRTF, not equalpower**: on a chase camera the question that
  matters is in front or behind, which a left/right pan cannot answer. Your own
  car stays out of it, on the master, because it is the thing you are sitting in
  and has no direction to arrive from. A rival is deliberately less machine than
  yours (two sawtooths, no load whine) and what it is *doing* is read off the
  flags already in its pose - there is no throttle on the wire and there does
  not need to be one, since a car that is not braking and is not crawling is on
  the power. `Sound.rivals(list)` takes the whole state in one call, so a car
  that drops out of the list loses its voice: that is what makes the phase rule
  free, and why qualifying, a replay and an empty room all cost one call.
- **You only hear the cars you are driving among, and it is `contactOn` that
  says so** - free practice and the race, the same answer contact and your own
  tow read, so a rival cannot be seen winding up a boost in a session where
  nobody can get one. In qualifying a car howling past your ear is somebody a
  corner behind you on an out lap: a rival you are not racing, arriving as
  though you were. `?panel=qual` is **not** a way to check this - it pins the
  HUD label and not `S.racePhase` - so the by-hand check needs a real session
  (a scratch harness plus a socket client that emits poses; see **Tests**).
- **Only `FLAG.RESPAWN` takes a rival off the track.** Both the visibility line
  and `collidables()` used to test `flags & 8`, which is `FLAG.BRAKE` - copied
  off the brake-light line directly above them, and commented "respawning". So
  every rival went invisible *and* intangible for the length of every braking
  zone: they blinked out on the way into each corner and you drove through them
  at the one moment you were closest. Braking is the flag that must change
  nothing except the lamps. `FLAG` is imported into `game.js` now rather than
  the bits being written by hand.
- **A car you cannot hit does not look like one you can.** `contactOn()` is read
  by the drawing as well as by `collidables()`, so what you can hit and what you
  can see through can never disagree: where there is no contact the rivals go
  translucent at the ghost's `GHOST_OPACITY`, keeping their own colour and their
  name at full strength, since colour is the whole of how you tell one from
  another. That is `CarView.setGhostly`, and it early-returns when nothing has
  changed because `transparent` is part of a material's program key in three.js
  - flipping it recompiles a shader, and this is called from the frame loop for
  an answer that moves about twice a race.
- **A remote car chases its target, except when no car could have driven it.**
  `updateRemotes` extrapolates the last packet forward on its velocity and
  chases exponentially, which is right for the small corrections between
  packets and wrong for everything else. A respawn, a grid placement or a
  packet gap moves the target further than a car can travel in a frame, and
  smoothing that streaked the rival across the map at an impossible speed,
  solid the whole way. Past `REMOTE_SNAP` (12 units), or on `FLAG.RESPAWN`, the
  jump is taken whole - and a respawning car is hidden, so the cut is not seen.
- **Each car in a snapshot carries its own age.** `snap.t` is when the
  *snapshot* went out; the pose inside it is whatever last arrived and can be a
  full pose-interval older. Extrapolating every car from `snap.t` left them all
  short by a different amount every tick - jitter that reads as the network and
  is arithmetic. `_snapshot` sends `now - c["ts"]` per car and the client
  measures from there. It is the last field, and the client guards on array
  length, so a cached old client meeting a new server degrades rather than
  computing `NaN` positions.
- **Rivals are brought up to now before the physics that has to hit them.**
  `updateRemotes` ran after the fixed-step loop, so every substep resolved
  contact against a frame-old position - about a car length at racing speed,
  all of it in the direction of travel.
- **A room is a phase machine, and every way out of a phase is guarded.** The
  phases are `free` -> `qual_countdown` (5s) -> `qualifying` (90s) ->
  `countdown` (5s) -> `racing` -> `results` -> `free`, with the two qualifying
  phases skipped entirely when the host has switched qualifying off.
  **A race must end**, and for a long time one could not:
  the only thing that armed the finish clock was somebody *finishing*
  (`FINISH_GRACE_MS`), so a race nobody finished never ended, and the room sat
  in `racing` for ever with the host unable to start another or change track -
  `set_track` and `start_race` both refuse mid-race, correctly, which is why
  the hang presented as "the host can't do anything". There are now four
  independent ways out, and `_maybe_close` is called from *every* path that can
  empty the road (finish, resign, disconnect, kick) rather than from the finish
  alone: "the last car is in" is not something only finishing can cause. Behind
  all of them is `_hard_race_ms` (8x a gold lap, clamped), which depends on
  nobody doing anything. **Every deferred close carries the `race_seq` it was
  armed for**, so a timer from one race can never close the next - which is
  live, because Rematch can fire inside the twelve seconds the results sheet is
  up.
- **Leaving mid-race is a DNF, not a disappearance.** `_drop` used to delete
  the car, and with it the loss, so the cheapest way to protect a rating was to
  close the tab - the one thing a rating system must never make the smart move.
  The car is now marked `gone` (excluded from `_snapshot` and `_live`, so it
  stops being drawn and stops holding the race open) but kept, so it is still
  in the standings and still rated. `_reset_race` is what finally drops it.
- **Every socket handler takes `data=None`.** Not a style choice: every button
  that leaves a room emits `leave` with no payload, so Socket.IO called
  `on_leave(data)` with no arguments and it raised before doing anything -
  pressing Leave took you to the lobbies page and left your name in the room
  behind you until the sweep noticed. They all already cope with `(data or {})`,
  so the default costs nothing and makes a payload-less emit a non-event rather
  than a line in the log.
- **Two buttons for the two ways a race stops early**, both top centre with
  Start race, because they are the same kind of decision: start this, stop
  this, get out of this. Anyone can **Resign** (only while there is a race to
  resign from): a DNF, rated as one,
  and you drop straight back into practice without leaving the room. The host
  gets **End race**, which is a *cancellation*
  before the lights - `_abort_race`, nothing recorded - and the chequered flag
  after them, freezing the standings and rating them normally. Both arm on the
  first press and fire on the second, in place: they happen mid-drive, one
  press from the settings icon, and an "are you sure" overlay would cover the
  race you want to look at before answering it.
- **The grid is set by a 90-second qualifying session**, not by name. It was
  `sorted(fresh, key=name)`, which is both arbitrary *and stable* - so the same
  person started on pole every single race. Qualifying is ordinary practice
  with a clock on it: `qual_time` per improved lap, best one counts, a lap
  finishes into a toast and an automatic restart rather than the results sheet
  (covering the road while there are seconds left to improve is taking the
  session away). That automatic restart is cancelled by any restart of your
  own - `resetToStart` clears the timer - or it threw away the lap you had
  already begun a second later, which looked like the game restarting you at
  random. No lap at all means the back of the grid, shuffled. The host's Start
  race means "open qualifying" in `free` and "go now" during it, so ninety
  seconds never traps four people who are ready, and **Enter** is that button
  on the keyboard.
- **Qualifying starts on lights, like the race does.** `qual_countdown` is five
  seconds with the same overlay, the same sounds and the cars held still. It
  used to simply begin, so the first anyone knew of it was a toast saying they
  were already in it and a lap in progress that no longer counted. Nobody is
  *placed* for it, though: a session has no start line - everyone leaves when
  they like, on their own lap - so it counts down over wherever you are sitting.
- **Qualifying can be switched off, and then the grid is the last race
  reversed.** It is the room's one setting so far (`ROOM_DEFAULTS`, on by
  default) and it lives in the live room state rather than on `DriveGame`: it is
  about the next few minutes, and `create_all` makes tables and not columns, so
  a column would need a hand migration on the live database for something a room
  forgets anyway. With it off, `_open_race` sends the room straight to
  `countdown` and the order comes from `_reverse_grid` - whoever was beaten
  starts ahead of whoever beat them, which is the arbitrary ordering that is at
  least *about* the racing, so a room of mixed ability keeps having close races
  instead of one procession after another. Anyone who was not in that race lines
  up behind it, shuffled, and a room's first race is shuffled entirely. The host
  moves the switch from the room drawer, the server refuses it mid-session
  (`LIVE_PHASES`, same as the track), and the whole set is fanned back out as
  `room_settings` so nobody is reading a switch that says something different
  from the host's.
- **The grid is staggered and pole starts on the inside of the first corner.**
  Ordering alone does not fix a two-by-two grid: cars level with each other
  reach the first corner together and the one on the inside of it simply gets
  there. The stagger deals with "at the same instant" - the odd slot of each row
  sits back 2.4 units, F1 style. The side used to be dealt with by alternating
  it every race, on the grounds that nothing knew which way the track turned
  first, which meant half the time the car that qualified fastest lined up on
  the *outside* of turn one and lost the place it had earned. The track knows
  perfectly well: `tracks.pole_side` integrates the ribbon's own `curv` from the
  start line until the heading has committed one way (`FIRST_TURN_DEG`), and a
  loop contributes nothing to it because a loop is pitch rather than yaw. So
  pole gets that side, every race, on every track, and `flip` is gone. Pole
  keeps its advantage; it was earned, and taking it away would make earning it
  pointless.
- **A split delta is measured against whatever that session is about**, which
  is three different laps - `splitRef` is the only thing that decides, and it
  returns null rather than comparing with the wrong one. **Racing: the
  leader**, specifically the quickest anybody *else* reached that checkpoint,
  which is by definition whoever led on the road at that point; if that is
  you, the same number read backwards is your gap to the nearest rival. Each
  client emits `split` and the server fans it straight back out rather than
  accumulating a table, because "the quickest anybody else" is a different
  number for every car and the server would have to send a different message
  per client. **Qualifying: your own best lap of the session**, kept whole as
  `qualRef` (a `lapTimeline`, the same distance-against-time table the ghost
  uses) rather than as a time, since a split needs the reference lap's shape.
  **Free practice: the ghost**, as before. The finish is the last split and
  follows the same rule.
- **The qualifying board is top right with the standings**, not top centre:
  it is the same kind of thing they are - who is where - and top centre is for
  the one button the room is waiting on, which a board above it pushed down
  into the road. The live standings are hidden during qualifying, since
  running order by distance means nothing when everyone is on their own lap
  and the board below already lists the same people in the order that counts.
- **On a phone the top-right stack does not slide out from under the drawer.**
  It does on a desktop, where the drawer is a 300px column. On a phone the
  drawer is most of the screen and hides the driving controls while it is
  open, so there is nothing left underneath to keep reachable, and sliding it
  only walked the icons into the top-centre buttons on the way past.
- **Guests are invisible to ELO.** They are in the room, on the grid and in the
  standings, but `_rate_race` ranks the logged-in players *among themselves*:
  beating a guest gains nothing, losing to one costs nothing. Anything else is
  a rating anybody can move by opening a second tab. The win and podium tallies
  were read off the overall standings, so a guest winning meant nobody was
  recorded as having won and a guest in the top three pushed an account off its
  own podium; they follow the rated order now, and retiring is never a win.
  **Two DNFs draw** (0.5), because their order is whichever they happened to
  give up in. Still needs two accounts - one has nobody to be rated against,
  and its race count no longer creeps up on races that were never rated.
- `?panel=qcount|qual|racing|result` pins a phase and fakes a session, for the
  same reason the other `?panel=` values exist: none of them is a panel you can
  open, and getting a room into any of them takes two browsers, a stopwatch and
  somebody willing to lose a race. Pinned rather than assigned - the room
  reports `free` the moment the socket connects, so a phase merely set at boot
  is gone before the shutter. **`racing` pins a field as well as the phase**, and
  it has to: the position card and the standings are shown when there are rivals
  on the road rather than when the phase says `racing`, so a pinned race drew
  neither of the two things that phase is *for* - and that is how the minimap
  came to be sitting on top of the position card on every phone with nobody able
  to photograph it. `S.previewOrder` is six cars, the same trick `qual` already
  used with `renderQual`, and `hud` reads it in place of `liveOrder()`.
- **The room drawer holds the invitation.** A share field with
  `<origin>/j/<CODE>` in it and a copy button, and `/j/<CODE>` joins whoever
  opens it - asking for a login or a guest name first if they have none. The
  link opens a *private* room without its passcode: the passcode is there to
  keep a room out of a stranger's hands and a stranger does not have the link.
  The field is readable as well as copyable, because the clipboard needs a
  permission the browser can refuse and a link you can read off the screen
  cannot fail. The URL is built from `location.origin` in the browser rather
  than from `request.url_root`, which is http on a laptop and does not
  necessarily know it is https behind nginx.
- **The results sheet is five equal buttons**: Practice, Watch replay, Change
  track (host), Rematch (host), Quit - Quit last, because leaving is the last
  thing to offer. One size for all of them, wrapping rather than shrinking, and
  `auto-fit` columns so the three a non-host sees fill the row instead of
  leaving two holes where somebody else's buttons would be. The top-centre race
  buttons are one size as well now: they are the same kind of decision taken at
  the same moment, and a row of three heights read as three unrelated controls.

### The garage

**`/garage` is a turntable and a set of slots**, and `drive/garage.py` owns the
whole vocabulary - the palette, every slot, every gate and the sentence shown on
a locked one. One module because a locked row promising "a gold on every track"
over a rule that actually wants three is worse than no text at all.

- **It took `Log out`'s slot in the nav, and `Log out` moved next to your own
  name on your own account page.** That makes logging out two clicks instead of
  one, which is the trade: the nav slot buys a garage, and logging out is a
  thing you do once a session from a page that is already about you. It is
  `is_me` only, so it is not on a stranger's page. It also cost a CSS fix worth
  knowing about: **`.btn.danger` used to set `width: 100%`** as well as the
  colour. That was redundant where it was used - both of its buttons are inside
  a `.btn-grid`, which sets it already - and it outranks anything a caller sets
  at the same specificity from earlier in the file, so the first `danger` button
  outside a grid came out as a full-width red bar across the page. A variant
  that silently decides layout is not a variant, so the width is gone from it.
- **A car with no garage row renders exactly as it did before any of this.**
  Every default is today's value and `trim`/`rim`/`glass`/`stripe` default to
  `None` meaning "whatever the renderer already did" rather than to a colour
  that happens to match - a literal would be indistinguishable on the day and
  would stop following the body the first time somebody repainted. Pinned from
  both sides: `test_garage.py` on the resolve, and `test_garage_js.py` on the
  built car costing exactly 14 meshes and 6 materials.
- **`HASH_COLORS` is frozen at eight and `PALETTE` is eighteen**, and the split
  is the whole reason nobody was repainted. `color_for` is
  `HASH_COLORS[sha1(name) % len(HASH_COLORS)]`, so the *length of the list it
  indexes* is part of every answer - hashing over the wider palette would have
  changed the modulus from 8 to 18 and with it the default colour of every
  account that exists and of every ghost ever recorded. The ten new ones are
  choosable and nothing else.
- **The body is a curated palette and the detail slots are free hex.** The body
  is what rivals identify you by, so its separation is guaranteed rather than
  left to whoever is choosing: `test_garage.py` checks every pair at least
  `DELTA_E_MIN` apart in CIELAB, every entry at least `BACKDROP_MIN` from
  tarmac, kerb, grass, a bright sky, a dark sky and snow, and every L* inside a
  band so nothing is near-black or near-white. That check does real work - it
  threw out a forest green 14.3 from grass, a sand 10.8 from a bright sky and a
  gold 13.8 from the yellow already there. A trim or a window is not the thing
  you are picked out by, so those are anything you like.
- **Brake lamps are deliberately not customisable.** They are the only thing a
  rival reads off your car, and the amber drift state was removed for exactly
  that reason; a lamp somebody can recolour is the same mistake with a settings
  page in front of it. Glass, tyres and the lamps also stay matte whatever
  finish the paint is wearing.
- **Nothing here may touch the simulation** - not ride height, not
  `CAR_RADIUS`, not the wheel radius, not a gram of mass. A cosmetic that
  changed how the car drives would make every time on the board mean something
  different depending on what its driver was wearing.
- **Four gates, and the fourth is past tense.** Pearl at three golds, pinstripe
  at a gold on every track, split-five rims at finishing every track - all three
  recomputed from counters that cannot go down, so storing them would be a
  second copy of something the database already knows. The laurel badge is
  "**set** a track record", earned once and kept: it is the only one anybody can
  take off you, so it is written into `earned_json` the moment it is true. That
  is also why it needs no backfill - every current holder qualifies the first
  time anything asks about them.
- **`validate` and `resolve` are two functions on purpose.** `validate` stores
  what was asked for, gates and all, so earning an item later puts it on without
  having to ask twice; `resolve` decides what may be *worn* and runs on every
  path that sends a livery anywhere. A client can POST `finish: pearl` all day.
  `validate` also never raises: an unknown key is a client from after the next
  deploy, and a bad value falls back to the default rather than to black.
- **Rims are one merged `BufferGeometry` per style, shared by four wheels.**
  Five spokes as separate meshes is 24 extra meshes on one car and nearly 200
  across a grid, which is real draw-call cost on a phone. Built with `MeshBuf`,
  the project's own triangle accumulator - `mergeGeometries` is a three.js addon
  and is not vendored. The *style* is what turns a rim on, never the colour:
  gating on the colour gave `stock` five spokes, which triangle counts caught.
- **Decals are quads `LIFT` (0.01) above the panel, wound anticlockwise seen
  from above.** The obvious winding is the other one and is silently wrong - the
  stripe still draws and is lit from underneath, so a bright stripe comes out as
  a dark smear on the one surface the sun is hitting. `fade` is why they all go
  through `MeshBuf`: a per-vertex colour makes a gradient a lerp written into
  the attribute, in a renderer whose whole look is having no textures.
- **`color` is answered from the livery everywhere it is sent.** The car is
  drawn from `livery`, but the minimap dot, the standings row, the chat name and
  the *nameplate over the car* are all drawn from `color` - so reporting the
  seat's stored column raw put somebody's chosen colour on the bodywork and
  their hashed one on everything pointing at them. `DrivePlayer.to_dict`,
  `/api/ghost` and `car_color` all take it off the resolved livery; the column
  is the seed and the guest fallback. **The nameplate over a car is the one
  thing that is the car's own business**, and `setLabel` is called with no
  colour so it falls back to `CarView.plateColor` - the body colour for almost
  everybody, and the record green for whoever is wearing the laurel. Both call
  sites used to pass the roster's colour, which is indistinguishable for
  everybody except the one driver it matters on: the only car that had earned a
  green nameplate was the only one that could never show it.
  `test_rules_js.py` reads the calls out of the file and fails on a second
  argument, because building a remote to check it needs a renderer, a socket and
  a track.
- **A guest is hashed off the name they typed**, not `GUEST_COLOR`, and that is
  what let the first-free colour rule go. `_livery_for(user, holders, name)`
  needs that `name` for exactly this: resolve a guest against nothing and four
  guests in a room are four identical red cars, which is the bug the deleted
  rule existed to prevent, arriving from the other end.
- **Two people choosing one colour both keep it.** `_add_player`'s "your colour
  if free, else first-free" rule is gone. It was the right trade while nobody
  had chosen - a hashed colour is not yours in any sense worth protecting - and
  is exactly the wrong one now: being handed a stranger's colour without being
  told is worse than sharing one, and the cars have names over them precisely so
  colour is not the only way to tell them apart.
- **A ghost wears the car its driver drives now; a replay wears what they wore
  on the day.** Opposite answers, and deliberately: a ghost is a lap you are
  chasing now and turning up in last month's paint would read as somebody else,
  where a race is a thing that happened. So `/api/ghost` looks the livery up and
  `_store_replay` writes it into `drive_races.cars_json`.
- **Storage is `drive_garage`, two columns.** A new table because `create_all`
  makes tables and not columns, so it lands on the live database by itself; a
  JSON blob because every cosmetic after this needs no migration. `livery_json`
  keeps **only the slots that differ from the defaults**, so a default that moves
  later moves the car of everybody who never touched that slot. `earned_json` is
  a second column rather than a key in the blob because the two are different
  kinds of fact - folding a server decision into something the client POSTs is
  how a gate gets bypassed.
- **The viewer builds no track.** `Renderer` starts with `trackGroup` and `sky`
  null and `render(dt)` is only particles plus a draw, so a studio costs one
  canvas and the page opens instantly. There is no `OrbitControls` - it is a
  three.js addon and is not vendored, and what this needs is thirty lines of
  drag. Two numbers were wrong first time and are worth not re-deriving: the
  camera is 66 degrees vertical so `dist` 5.9 (not the chase camera's ~9) is
  what makes the car a third of the frame rather than a tenth, and the studio
  floor has to be **clearly lighter than the backdrop** or the contact shadow has
  nothing to be a shadow on and the car floats in a void with a smudge under it.
  The scene also needs a dim cool fill opposite the sun: the track's rig is one
  hard key plus a hemisphere, which is right outdoors and in a black room leaves
  every face turned away from the key at the same flat shadow, so a flat-shaded
  car reads as a paper cut-out of itself.
- **The selected option's highlight outranks its hover, and that took a
  `:not`.** `.gopt:hover:not(:disabled)` is three simple selectors against
  `.gopt.on`'s two, so a chosen option went pale the moment the cursor was over
  it - which is where the cursor is, having just clicked it. It looked like
  every press deselecting itself.
- Every list on the page is built from the payload the server rendered into it,
  so there is no second copy of the vocabulary in the JS to drift from
  `garage.py`'s - including the words on a locked row.

### Look: skies and worlds

Every track's art direction lives in one `PALETTES` entry in `trackmesh.js`.
Two optional fields do nearly all of it, and both are read by code that has no
idea which track it is looking at:

- **`sky`** - either a plain colour (the old two-tone dome) or a spec that
  `render.js` turns into a graded dome plus a sun, stars, and the track's own
  key light, hemisphere light and fog. `glowMode` matters: `horizon` smears the
  glow around the sun's *azimuth*, which is what makes a sunrise a sunrise;
  `radial` puts a halo around the disc, which is what any sun up in the sky
  wants. A sun drawn on the horizon must still have its *light* come from much
  higher, or nothing in the world gets lit.
- **`below`** - what is under a track that floats, dispatched on `kind`: a city
  drowned in cloud, a desert, a downtown, a lava field, `pillars` (rock spires
  through an overcast, Cloudbreak) or `void` (which also suppresses the distant
  floor plate). Ground tracks use `props`/`density` instead, which pick from the
  scenery vocabulary (conifer, bigpine, deadtree, palm, rock, block) and `snow`
  turns on snow caps.
- **`shore`** - Sandy Cove only. It cuts the sea out of the ground plane, so the
  beach stops at the waterline and past it there is *nothing*: the water is
  drawn and never collided, and driving off the sand is a fall rather than a
  slow patch. `at` is an absolute world coordinate rather than a fraction of the
  bounding box, because **the track is authored against the waterline** and it
  has to stay put when the layout moves; `SHORE_Z`/`SHORE_AMP`/`SHORE_WAVE` in
  tracks.py are the other copy, and two tests hold them together -
  `test_the_waterline_agrees_with_the_track` and
  `test_only_the_pier_is_over_the_water`, which requires the crossing to be a
  single run (the pier) and the coast road to keep 25 units of clearance. Drift
  those apart and the sea floods a road that was authored to be dry.
- **`rainbow`** - degrees of hue per station, and it moves the road into the
  *unlit* buffer so it glows. **Two gradients, not one.** Along the road the hue
  sweeps slowly; across it the lightness falls toward the kerbs, the saturation
  rises, and the hue skews slightly either side. The cross-road half is the one
  that matters - a hue sweep on its own reads as a flat carpet, because a
  gradient with no shading across it has no shape. Hard bands were the first fix
  for that and are too loud. A quad has one colour, so the flat road is split
  into `rainbowLanes` lateral strips purely to have something to shade; profiled
  stations already have their samples. An unlit road lights nothing by itself,
  so the colour in the scene comes from `hemi.ground` - a saturated magenta
  there is what puts rainbow on the car's underside and the pipe walls. The sky
  is deep violet rather than black: against true black the road is the only
  colour anywhere and the world around it reads as nothing.

Rules learned the hard way, all from the same fact - **you look down on a world
below from a hundred units up, so you mostly read footprints**:

- dunes must be broad and very low, mesas narrow and tall, or both read as
  crates and pallets;
- cloud has to be clumps with sky between them, never an even coverage of
  anything, and it needs its own translucent mesh with `depthWrite` off so
  overlapping boxes accumulate into something dense in the middle and wispy at
  the rim. That is the whole difference between cloud and polystyrene;
- cloud only works when you look *down* on it. As a sky it reads as pale
  rectangles however it is shaded, which is why there is none in the dome;
- and the corollary, learned on Cloudbreak: **a cloud deck that is only a little
  way below a long track is seen almost edge-on**, and then it reads as a sea
  with floes on it however good the clumping is. The fix was to put the deck
  145 units down so you look onto it, deepen the puffs (`puff`), and **draw no
  floor plate at all** - an open bottom fading into fog is what being a long way
  up looks like, where a plate was unmistakably grey water. `pillars` spires
  therefore grow from `root`, just under the deck, rather than up off a floor.

**Nothing below is in the collider**, so the only thing keeping it out of the
track is the corridor test - and where scenery rises *above* road level (Jump
City) that test is load-bearing on its own, so it checks a whole footprint
rather than a centre point. Everything else also obeys a hard height cap under
the track's lowest station.

The single highest-leverage number in a palette is `hemi.ground`: it is the
bounce, so sand makes every underside warm over a desert, snow removes the dark
shadows from a winter scene, and molten orange is most of what separates a lava
field from a dark field.

### The HUD, the phone, and the type

- **The HUD is arranged the way Polytrack's is**, because it is the arrangement that
  keeps the middle of the screen empty: the clock is bottom centre, the split delta
  flashes directly above it at each checkpoint and fades, your personal best sits to
  its lower left and the speed to its lower right, with a speed bar under the lot.
  The corners are therefore free, which is the whole reason the touch controls fit.
- **Top left is where you are** - the track name, then what kind of session this is.
  Solo that is `Solo time trial`; in a room it is the room's *phase*, `Multiplayer -
  Free practice` / `Race about to start` / `Race in progress` / `Race finished`, which
  is the only place the phase is written down and is driven from one `PHASE_LABEL`
  table rather than a `setMode` call at each transition. **Top right is everything you
  can open**: the room drawer (rooms only), the track switcher, help, settings. Icon
  buttons and nothing else - plus, solo only, the medal times. In a room those are
  gone: a table of lap times floating over a race you are driving against other people
  relates to nothing on the screen. **Top centre is the host's Start race button**, and
  only that; it used to live in the room drawer, which closes itself, so the one thing
  everybody was waiting on was behind a panel.
- **Bottom left is the minimap with restart and last-checkpoint above it.** Those two
  used to head the settings sheet, which meant a menu you had to open to restart a run
  - which is the most common thing you do. They are hidden on touch, where the real
  buttons are under a thumb already.
- **The whole left-hand side is one flex column (`.hud-l`), and where the map goes
  is a `margin-top`.** `.hud-tl` and `.hud-bl` used to be two separately anchored
  boxes sharing that edge, so neither could know how tall the other was - and
  every layout that brings the map up out of the steering thumb's corner (touch,
  and `@media (max-height: 460px)`) had to clear the cards above it with a
  hardcoded `top`. **84px cleared the track card, and the Position card
  underneath it did not exist when that number was written**, so the map sat
  squarely on top of your race position on every phone, in every race. It
  survived because the position card is only shown once there are rivals on the
  road, so every screenshot anybody could take of the phone HUD was of a solo
  session and looked perfect. Now the map is simply the last item in the column:
  `margin-top: auto` puts it on the floor for a desktop and `margin-top: 0` lets
  it follow the last card everywhere else, both magic numbers are gone, and the
  overlap has stopped being a thing that can be expressed. Two things to know.
  **`.hud-bl` has to sit next to `.hud-tl` in the template**, not where it reads
  naturally in top-left/top-right/bottom-left order - `.hud-tr` was between them,
  and a wrapper spanning both makes `.hud-l` the containing block for its
  `right: 14px`, which puts the top-right stack 14px from the right of a 200px
  column. And `.hud > *` is what turns pointer events back on, so the wrapper is
  now that child rather than the cards: without `pointer-events: none` on it and
  `auto` on its children, a full-height column swallows every click down the left
  of the screen.
- **The home page is a headline, two doors and how to play.** "Race online!", then
  a red **Drive now** (`/solo`) beside a yellow **Race your friends** (`/lobbies`) -
  two halves of the game rather than a primary and a fallback, which is why the
  second one is a colour of its own rather than the white secondary. There is no
  grey standfirst under the headline: it restated the three paragraphs below it.
  Those are one each - what a run is, what Solo is, what Multiplayer is - and the
  track cards follow, so the page is read once and clicked from thereafter.
- **Solo is `/solo`, and the track is something you change from inside it.** There is
  no "pick a track" page any more: `/solo` opens whatever you were last driving (kept
  in the session, so the first paint is right) and the **track switcher** - the map
  icon, top right - swaps the world in place. `/solo/<slug>`
  still works for links and bookmarks and records itself as your last track; switching
  in-game posts to `/api/last-track` so coming back lands where you left off.
  **Everything that names the track has to follow the switcher**, and for a long
  time none of it did: you arrived from the home page on `/solo/<slug>`, changed
  track, and the leaderboard button still went to the board for the track you
  arrived on. `loadTrack` now repoints every `.board-link`, the page title and the
  help sheet's blurb, and `switchTrack` rewrites the URL with `history.replaceState`
  (not `pushState` - a switch is a setting inside one session, not somewhere to go
  Back out of; the query string is dropped because `?ghost=`/`?watch=` name a lap on
  the track you just left). **A room's URL is left alone** - it is the join code and
  has nothing to do with the current track. The same
  switcher is in a room, where only the host can pick - everyone else sees the same
  grid with the picking turned off, rather than a poorer version of it.
  **A card shows your time and not the record.** The record was on there too, and it
  made every card an argument: two times and two names, one of them somebody else's,
  on a menu whose only job is choosing where to drive. `_track_cards` therefore does
  not even send it. It is still on the board and the home page, which are for reading
  rather than picking.
- **The switcher's cards are photographs, not diagrams.** `tools/shoot_tracks.py`
  drives headless Chrome over every track with `?shot=1` (`S.shot` in game.js: HUD off,
  car hidden, camera behind the start line) and writes `static/img/tracks/<slug>.png`;
  the home page uses the same twelve. **Re-run it after changing a track's geometry
  or sky** - a test asserts the files exist but nothing can notice that one is stale.
  **It must run on ANGLE's software GL** (`--use-gl=angle --use-angle=swiftshader`),
  which is what `GL_FLAGS` is for: plain `--use-gl=swiftshader` is *rejected* by
  current Chrome rather than ignored, the GPU process dies, and Chrome still
  writes a PNG - of a half-built frame, which in practice was a photograph of
  some other track. Nothing downstream can tell a wrong picture from a right one,
  so this is the worst failure the tool has. The same flags are what to use for
  any by-hand screenshot check.
  Fitting the *whole* track in frame was tried first and is much worse: from far enough
  back to hold a point-to-point the road is a thread, and on Jump City it vanished into
  the towers entirely. Aiming level from 40 units up fails the same way - it photographs
  the horizon. Behind the start line, angled down at the road, is the shot.
- **Settings is only settings.** Title, an X, and the things you set. The
  session controls moved to the HUD. It is **Splits and the ghost car, then
  Sound and Music, then the two ways out** - a white *View Leaderboard* beside
  the red *Leave*, the red one last because it is the only control on the sheet
  that pressing again does not undo. Every label on it is **Title Case**, down
  to the state a switch is in (*Ghost: On*). It is also the one sheet wider
  than `.sheet.wide` (`.sheet.wide.settings`, 720px): its top row is four
  choices *and* a switch beside them, and in a room the four include
  *Provisional Pole*, which cannot be said in fewer words - at 620 they wrapped
  and left a hole under the switch.
- **Which lap you drive against and whether it is drawn are two switches.** They
  were one - the "Ghost" row, where picking a lap turned the car on and `Off`
  turned both off together - so the only way to stop a translucent car driving
  the line in front of you was to give up the split deltas as well, and the
  deltas are the half of a reference lap you actually read at 200km/h. Now the
  row is **Splits** (off / my best / world record / view others, and
  *provisional pole* in a room), named for what it is for, with a **Ghost:
  on/off** button to the right of it. `S.ghostMode` is the lap and
  `S.showGhost` is the car; `setGhostMode` no longer touches the second one and
  a test asserts it (`test_picking_a_lap_does_not_turn_the_ghost_car_back_on`).
  Both are remembered, under `drive.ghost` and `drive.ghostcar`. In a room `my
  best` still means your best lap of *this* practice session, and `ghostOn()`
  still hides every ghost for the whole of a race. **`G` steps through the
  three** (`GHOST_CYCLE`: off, my best, world record) rather than toggling the
  last one back on - choosing between your own lap and the record is the choice
  worth having on a key, and it is the *lap* rather than the car, since "whose
  lap" is the interesting question and the other is one press in a sheet. A lap
  chased off the board is deliberately not in the cycle, so pressing G leaves
  it. **Switching track hides the ghost car**: somewhere new is somewhere you
  are looking at rather than attacking, and a car you have never driven against
  on your first lap of it is in the way. It is the car and *not* the reference
  lap that goes - how far off the pace you are is precisely the number you want
  on a track you have never driven, and turning the lap off used to take that
  with it - and it is not remembered (`setGhostCar(false, {remember: false})`),
  so the setting you chose survives.
- **Sound and Music are two switches because they are two buses.** `Sound.sfx`
  carries the car and the world, `Music`'s own bus sits beside it under the
  master, and `mute` is the sfx gain rather than the master's - so muting the
  game leaves the music playing and vice versa, which is the only reading of
  two switches that is not a lie about one of them. Both are remembered
  (`drive.sound`, `drive.music`), which the mute never used to be. **Sound
  defaults on and music defaults off**: the engine is what the game sounds
  like, and a loop over the top of it is something you ask for. `start` now
  declines to build a context only when *both* are off, since somebody driving
  muted with the music on still needs one.
- **The music is synthesised, like everything else here.** There are no audio
  files on the site and a loop long enough not to wear out is a megabyte of
  them, so `Music` in `sound.js` is four bars of i - VI - III - VII in A minor
  under a rolling sixteenth arpeggio, played on the same oscillators the clanks
  and beeps are. Two things about it are load-bearing. **It is scheduled ahead
  against `ctx.currentTime`, never played by a timer**: a note placed by a
  `setTimeout` lands wherever the main thread is, which on the frame that
  builds a track mesh is tens of milliseconds late and audibly so - `musicTick`
  books everything due in the next `M_LOOK` and is called from the frame loop,
  above its early returns, so a replay keeps its music and being called
  irregularly moves nothing. A tab that stopped getting frames skips forward
  rather than playing the backlog. And **the chords are inverted rather than
  stacked from each root** (F is played A-C-F): written the obvious way, each
  bar starts higher than the last and the figure ratchets up an octave and a
  half across the loop instead of going round.
- **The world-record ghost has to be a lap that can be shown.** `?who=wr` took
  the fastest row and served whatever replay was on it, but a row keeps its
  time whether or not a ghost was stored beside it, so one old replay-less row
  made "world record" report that *nobody had set a time here* on a track with
  a full board. It now filters on `DriveTime.ghost`. Every other way in already
  only offered laps with a replay - the board sends `has_ghost` and hands back
  an id - which is exactly why "view others" worked where this did not. The
  message distinguishes the two facts now: no record at all, or a record with
  no replay. **There were two bugs wearing the same message**, and the second
  outlived the first: `loadGhost` clears the ghost and then *awaits* the
  request, while `setGhostMode` writes the line under the buttons
  synchronously - so the line was always written during the half second when
  there was reliably no ghost, and said so however good the answer turned out
  to be. It is written again when the request settles, guarded on the mode and
  the track still being the ones that asked (click two ghosts quickly and the
  slower reply must not land on the newer choice). `?ghost=off|me|wr` picks a
  standing choice by name - ids are digits, so the two cannot collide - which
  makes a ghost setting linkable and, with `--dump-dom`, checkable without a
  browser to click in.
- **Escape closes what is in front of you before it opens anything.** It works
  innermost first - a replay, then a panel opened from another panel, then the
  panel itself - and *then* means "open settings". The controls sheet was
  missing from that list, so pressing Escape while reading it opened the
  settings sheet on top: the one key everybody presses to get out of something
  put something else in the way.
- **The `?` sheet is Controls, and it is the controls and nothing else.** It
  used to open on the track blurb and close on two paragraphs about grass and
  crests, which is reading matter in front of somebody who pressed it to find
  out which key drifts. **The table follows the device** - `body.touch` swaps
  the keyboard rows for the gestures (`.keys-only` / `.touch-only`, the same
  mechanism as the start hint), so it never describes controls you do not have.
- **`/account` is two boxes and the second one is a table.** It was nine bordered
  stat tiles in a grid plus a tenth panel for the medal tally, which made ten pieces
  of furniture out of one thing - who you are and what you have done. Now one
  `.panel.profile` holds the figures (no border each; the panel is already the
  border) with the three medal counts under a hairline in the same box, since they
  are three more of the same kind of number. The standalone "Medals" total went with
  the redesign - it was the sum of three numbers sitting an inch below it. The track
  table uses `table-layout: fixed` with a `<colgroup>`, because on a 1080px page an
  auto table hands all the slack to the column that wants it least (the track name,
  two short words); under 700px it switches to auto with a `min-width` and scrolls
  inside `.tablewrap` rather than crushing six columns. The medal column carries the
  word as well as the swatch, and the row actions are icon+label buttons - a steering
  wheel for **Play** and a podium for **Leaderboard**, which used to read "drive" and
  "board" and nobody knew what a board was. Icons are inline SVG (`.icn`), never
  glyphs, for the reason the in-game ones are. **The rows are in the pool's
  order**, the same one the switcher, the home page and the leaderboard use.
  They used to be most-recent-PB first with the never-finished tracks in a
  block underneath, so the same track moved every time you drove and no two
  pages agreed on where to look for it; a track you started and never finished
  now sits in its own place in the list, muted and without a time or a medal.
- **A name on a board opens that driver's Drive page, and that page is the way
  out to the rest of the site.** `_player.html` used to link straight to
  `cgovind.com/accounts/<username>`, which is the right page for "who is this
  across four games" and the wrong one for the question a lap time actually
  raises, which is how they go round *here*. So it points at `/account/
  <username>` - the same page as your own, public, no login - and that page
  carries one link on to the shared profile (`.elsewhere`, the only link on it
  that leaves Drive). It rides on the **end of the rating line** rather than a
  line of its own, because it is who this is and that line already says so; a
  row to itself made a one-link paragraph out of a page whose next line is a
  panel. There is no standfirst under it either - "all four games, in one
  place" restated the destination the link already names. Three things fall out
  of making the page public: your own name redirects to plain `/account`, so
  there is one address for your own record
  rather than a second copy of it that quietly cannot be edited; the nav's
  "Account" tab only lights on your own; and `_stats(user, create=False)` hands
  back an unattached row for a stranger, since the creating version would leave
  a `drive_stats` row behind for every account a passer-by ever looked at.
  `tests/test_no_drift.py` checks *both* halves - the board links by username,
  and Drive's account page still links on - because the second one is now the
  only route from a Drive leaderboard to the shared profile.
- **`/leaderboard`'s track table is dated, not gold-timed.** The gold time used to be
  the fourth column; it is a property of the track rather than of the record, it is
  already on the track page and in the game, and sitting next to somebody's name it
  read as though they had won a gold rather than set the fastest lap on the site.
  `_records()` now carries the holder's `updated_at` (which is when *that lap* was
  set, since a better run replaces the row wholesale and stamps it). It is stored and
  rendered as UTC so the page is right with no JS, then rewritten into the reader's
  own timezone by the script at the foot of the template.
- **`/leaderboard` is three boards, named for what they rank**: **Track Records**,
  **Time Trials Leaderboard**, **Multiplayer Leaderboard**. The last was "Race
  ratings" and was the only heading on the page carrying a line of explanation
  under it; three boards on one page are a set, and one of them dressed
  differently reads as a different kind of thing, so none of them has a subtitle
  now. **Every column heading on a `table.board` is the display face**, which it
  was not: `th.num` was handed `var(--mono)` along with the cells under it, so a
  heading row came out in two fonts with the left-hand labels looking pasted in
  from another table. The cells keep mono, where it does the work - figures line
  up under each other. `.acct-tracks` had already undone this for itself; that
  override is gone, since the fix is now in the one rule.
- **The Time Trial Score is golf scoring: your placing on each of the twelve
  tracks, added up**, so low is good and a clean sweep of the pool is 12. Ten
  firsts and two thirds is 16. Three rules make the sum well defined, all of them
  in `_time_trial_board`. A **tie shares a place**, the answer `_my_rank_map`
  already gives for one track (strictly faster, plus one). A **track never driven
  counts as one worse than last on it** - the place you would take by turning up
  and being slowest - because adding up only the tracks somebody *has* driven
  makes driving fewer of them the way to a better score, and one lonely first
  place would beat a full sweep; the `Tracks` column (`9/12`) is what keeps a big
  score from being a mystery. And it is **derived on every render and stored
  nowhere**: a personal best does not only change your own score, it demotes
  everybody it overtook, so a number kept per driver would have to rewrite most
  of the board on every lap and would be wrong for as long as one write path was
  missed. Twelve tracks is one query. Bots and accounts with no times are off it
  (the join is what drops them), and since only laps driven alone are in
  `drive_times` at all, nothing set in a room reaches this board either.
  **The `Score` heading explains itself where it stands** - a dotted rule, a
  raised `?` and a `title` (`.whatsthis`) - rather than the board carrying a
  line of small print neither of the other two has, which is the thing the
  multiplayer board just had taken away. A `title` because that is how every
  hover on Drive works, from the HUD buttons to the record dates: one
  convention, no script. Its limit is the usual one - a `title` does nothing on
  a touchscreen - which is why the mark sits next to a column whose figures are
  still ordered top to bottom, and is not the only place the rule is written
  down.
- **The board is in the game.** "View others" opens the leaderboard over the track;
  clicking a row opens that lap - its checkpoint splits against your own PB's, who set
  it, and **Watch it** / **Race this ghost**. Picking somebody to chase is something you
  do between runs on the track you are already on, so leaving the page for it would be
  the wrong shape. The public `/track/<slug>` page opens a lap the same way and links
  back in with `?ghost=<id>` / `?watch=<id>`; `/api/board` carries each row's id and
  splits so no second request is needed, and `/api/ghost/<slug>?who=<id>` serves one
  lap, **scoped to the track that asked** so a replay cannot be played against geometry
  it was never driven on.
- **Watching is not driving, so it takes the HUD away.** `body.watching` hides the
  clock, the map and the pedals - none of it is true during somebody else's lap - and
  leaves a bar with their name and the replay clock. The camera reads its speed and
  orientation back off the ghost's own motion, since a replay carries neither. It
  loops, and it refuses to start mid-race: it parks your car and stops your pose going
  out, which in a race would leave a stationary obstacle with your name on it.
- **`S.paused` is derived in one place** (`syncPaused`), from whether any panel is
  open, and only solo. Four panels each assigning it meant closing any one of them
  unpaused a game with another still open, and the car rolled away behind the sheet you
  were reading.
- **The start hint is shown once per session.** It tells a new player the one thing
  they cannot guess; by the second run it is a label floating over the road on every
  restart. Remembered in `sessionStorage`, so a reload does not restart the lecture,
  and the touch and keyboard wordings are two spans switched by `body.touch`.
- **`?panel=settings|help|tracks|board|qual|racing` (plus `&row=N`) opens a panel
  on load**, for the same reason `?touch=1` exists: there is no browser in CI and a
  screenshot cannot click, so it is the only way to look at a panel's layout.
  `qual` and `racing` also *pin* the phase and fake a session, since neither is a
  panel you can open and getting a room into either takes two browsers and a
  stopwatch. **`?draft=charge|boost`** is the same idea for the slipstream: it
  pins the tow so the air round the car can be photographed without a rival.
- **The room drawer's button is three people, not a hamburger and not one
  person.** Three stacked bars sat next to the settings icon, which is three
  stacked sliders, and at a glance they were the same button. A single figure
  replaced it and was wrong in the other direction: one head is the icon every
  site on the internet uses for *your own account*, so on the one screen where
  the button means "everybody else who is here" it was saying the opposite of
  what it opens. It is a head and shoulders with two smaller ones behind, run
  off the edges of the 24-unit box so it reads as a crowd rather than as three
  buttons. The drawer reads top to bottom as who is here, what the next
  race will be, the way out, and then the talking: **chat is last and the box you
  type into is on the floor of the panel**, which is `#chatLog` stretching rather
  than the block being pushed down - capping the log left the input floating half
  way up with a hole under it.
- **Race settings are in the drawer, drawn for everybody and pressable by the
  host.** One switch so far (Qualifying), not a host-only panel: what the next
  race will be is something everyone is about to drive, so it cannot be a rule
  only one person can read. `renderSettings` is called from `applyPhase`, so it
  follows both the phase (a live session locks it) and the host changing
  mid-room, rather than being assigned at either event.
- **The room panel is a drawer at every screen size**, opened by that button. It
  used to be pinned open - a 274px column on a desktop, a 46vh slab across the bottom
  of a phone - so the multiplayer furniture sat on top of the road and the driving
  controls the entire time you were racing. It opens on arrival and closes itself when
  a race starts.
- **The two finish screens are deliberately different screens.** A time trial ends in
  a number, so `#results` is that number - big, centred, medal beside it, its rank
  under it - then `PB:` and `WR:` with their ranks, and Retry / Leaderboard / Exit.
  There are no sentences on it: "New personal best", "Ranked #3" and "That is the
  fastest time on this track" were all restating the numbers next to them. Only a
  *problem* gets a sentence (not logged in, offline). A race ends in an **order**, so
  `#raceOver` is the finishing order and the three things there are to do next -
  Practice, Quit, and Rematch for the host. Note that `/api/run`'s `medal`, `rank` and
  `is_record` all describe your stored PB row, not the lap you just drove: the lap's
  own medal is computed client-side and its own placing is the separate `run_rank`.
- **The touch buttons are sized off the height of the screen**, not off a
  breakpoint: `clamp(76px, 19.5vh, 124px)` (and the two small ones above the
  pedals `clamp(46px, 11.5vh, 72px)`), with the glyph a percentage of the
  button so it needs no sizes of its own. A phone in landscape is about 390px
  tall and a tablet nearly 800, and both land in "not a desktop", so one fixed
  76px was a thumb-sized button on the phone and a postage stamp held at arm's
  length on the iPad. The bottom-left corner belongs to the steering thumb
  whenever there is one - `body.touch`, not a width, since a tablet is 1180px
  wide and still drives with its thumbs - so the minimap moves up under the
  track card there and the blurb goes with it.
- **Touch controls: four driving buttons and no handbrake button.** Steering left,
  throttle and brake right, checkpoint and restart small above the steering. There
  is deliberately no fifth button, because there is nowhere a thumb can reach one:
  the right thumb is on a pedal essentially the whole lap and the left is on an
  arrow. The handbrake is **two gestures, one per thumb**, both handled in
  `bindInput`/`syncTouch` - so they are touch-input mappings and the physics and
  the keyboard are untouched, and either just adds `drift` to `touchKeys`.
  **Drag the throttle down** (`dragDrift`, threshold `DRAG_DRIFT`) and it comes
  on *without the thumb leaving the pedal*. That is the whole reason this thumb
  can carry a gesture after all: the objection was never the thumb but that every
  earlier candidate charged it a **release**, and coming off the power mid-corner
  is the one thing it must never do. A drag costs nothing, so the slide arrives
  under throttle, which is how the turn is actually driven. `DRAG_KEEP` is a
  second, lower threshold for letting off, so a thumb parked on the boundary
  cannot chatter the handbrake under itself. **Or double-tap and hold the arrow
  you are turning with**, so tap-tap-hold left is a handbrake turn to the left;
  the steering thumb arrives at a corner having just let go of the last arrow, so
  the second tap is the press it was going to make anyway. Letting go of either
  drops the handbrake, which is also how you catch the slide.
  **The two arrows share one double-tap timer, and a press on either voids the
  other's window**, so left-right-left is a correction rather than a double-tap of
  left. That sequence is fast and common, and it is exactly the moment - mid-corner,
  already saving it - when an unasked-for handbrake does the most damage.
  **`DOUBLE_TAP` is 50ms, which is far tighter than a normal double tap and is
  meant to be.** The other correction is coming off *the same* arrow and putting
  it straight back on, which is the exact shape of the gesture and cannot be told
  apart by anything except speed - at 320ms it fired on half of them. A gap this
  short is not something a thumb does while driving unless it means to.
  `test_touch.py` expresses its waits as fractions of `DOUBLE_TAP` rather than in
  milliseconds, so retuning the window retunes the tests instead of quietly
  invalidating them, and one test pins the intent directly: a 150ms re-grab is
  never a drift.
  The button that is drifting goes **amber** (`.tbtn.drifting`, `#ffd96b`) so it
  is obvious you asked for something different - that is the drift indicator,
  and it is on the on-screen button, *not* on the car. **The car's tail lamps
  are two-state red** (`BRAKE_ON`/`BRAKE_OFF`), and an amber drift state was
  tried and taken out again: `Car.braking` is `braking || handbrake`, so a
  slide does not *light* the lamps, it changes the colour of lamps that are
  already lit - and a car that goes yellow every time it steps out reads as a
  fault rather than as a driver. `FLAG.DRIFT` is still computed and still
  packed into the pose and the ghost; nothing draws it. What `lampsOf` answers
  is braking and only braking, for your car, every rival, a ghost and a
  replay.
  Three earlier attempts are worth not repeating: a DRIFT button beside the pedals,
  which was literally unpressable; **brake-while-steering, which is unusable** -
  braking into a corner *is* steering, so it fired on essentially every corner and
  the car spent the lap sideways; and the same double-tap on the *brake*, which
  worked but charged the busy thumb a release mid-corner and could not be reached
  from the throttle at all. A handbrake has to be something you ask for, it cannot
  be a combination you were going to make anyway, and it should cost you nothing
  you were already holding.
  Touch state lives in its own `touchDown`/`touchKeys` sets rather than being poked
  into `keys`, since it is not a one-button-one-control mapping. Laid out with
  flexbox off the safe-area insets. `?touch=1` on a play URL forces the touch HUD on
  a desktop browser, which is the only way to look at the phone layout without one.
  **Checkpoint and restart sit above the pedals, not above the steering** - flag left,
  restart right, mirroring the pedals under them. You reach for them having just gone
  off, which is the moment the right thumb has stopped driving and the left one is
  still holding a corner.
- **Every icon is inline SVG, never a Unicode glyph.** A gear, a flag or a triangle
  from the symbol blocks renders as a full-colour emoji on some platforms and a
  hairline outline on others, so it can be neither styled nor trusted. The touch
  buttons are dark-fill/light-stroke for the same reason a white wash did not work:
  it vanishes against a bright sky or a sunlit kerb, and half of every track is one.
- `R` restarts the run; `T` goes back to the last checkpoint **with the clock
  still running** - the difference between "that lap is gone" and "I fell off".
  **Neither does anything until the clock is running**, and silently: before you
  have set off there is no run to throw away and no checkpoint to go back to, so
  refusing costs nothing - and it closes a hole that was worth real time. On a
  grid, a respawn puts the car on the *start gate*, which is in front of every
  slot on it, so pressing either during the countdown walked you up the road; a
  world record was set that way. A message would turn a non-event into an event,
  so there is none. `P` opens the track switcher, which is the most common thing
  there is to do that is not driving. **Enter is the host's start button** in a
  room, which is why it is no longer a third way to press T, along with
  Backspace - and inside the chat box it still sends the message.
- **`Q` looks behind you and `F` puts you in the driver's seat, and both are held
  rather than pressed.** A glance is a glance: it ends when you let go, so there is
  no camera state to arrive at a corner still in. They are entries in `KEYMAP`
  beside the throttle rather than tests beside `R` and `T`, because that is the set
  that gets emptied on blur and on opening the chat box - a keyup swallowed by a
  message box would otherwise leave you driving the rest of the lap backwards.
  `readInput` takes the five names it wants out of that set, so the physics never
  sees these two. **There are no touch rows to match**: four buttons is everything
  the thumbs reach, and a view a phone could not let go of would be a fault rather
  than a feature. They work on a replay as well - somebody else's lap is exactly
  where seeing what the driver could see is worth something.
- **Two questions, not three cameras.** `F` is where the eye sits and `Q` is which
  way it looks, so holding both is a glance over your shoulder from the seat, which
  is the only thing both at once could sensibly mean - and `Renderer.follow` takes
  them as two booleans rather than as the name of a view. All of them orbit in the
  *car's* frame, exactly as the chase camera does, so a view can be taken up
  mid-loop without the horizon doing anything. Three things are deliberately not
  the chase camera's, though. **Looking back moves the camera to the far side of
  the car** rather than turning it where it stands: reversed in place it would be
  pointing away from your own car, which is the thing everything back there is
  closing on. **A change of view is a cut**, because the views are metres apart and
  easing between them drags the camera through the car and out through the road,
  for a glance that is over before it arrives. And **the driver's seat is not
  smoothed at all**: the eye is a fixed point in the car, and the position
  smoothing that absorbs kerbs for the chase camera sits a couple of metres behind
  its target at speed, which from in there is a couple of metres behind the driver.
  The eye is *inside* the cabin, which is what keeps that view clear for nothing: a
  box is invisible from within, so the roof, the glass and the pillars are simply
  not there. It sits at the windscreen rather than at the cabin's middle because a
  bonnet 1.9 wide seen from 0.4 above it takes a third of the screen from back
  there, and the view you asked for would be mostly of the car you are sitting in.
  **The ears ride the camera**, so a look back also swaps the side a rival arrives
  from - correctly, since you are looking at them when it happens.
- **`M` is the one key that means two things, and it is the right two.** Solo it
  mutes; in a room it puts the cursor in the chat box (opening the drawer), and
  Enter sends and hands the keyboard straight back to the car - staying in the box
  is what a chat window does, and this is a driving game. Muting is still in
  settings with every other preference, and the Controls sheet lists whichever M
  you have (`.room-only` / `.solo-only`, the same mechanism as `.touch-only`).
  Opening it clears `keys`: the keyup for anything you were holding is delivered
  to the input and swallowed, so without that the car drives itself into the
  barrier at full throttle for as long as the sentence takes. Escape is bound on
  the input itself, because the window handler ignores keystrokes aimed at an
  input - which is exactly what stops WASD steering while you type.
- **The type is Titillium Web**, self-hosted in `static/fonts/` at four weights
  (~46KB total, no CDN). It replaced xkcd Script, which is a good joke on the landing
  page and the wrong voice entirely for a timing screen. Titillium is the closest
  freely licensable thing to Formula 1's own display face, which is proprietary.
  `--display` is headings and buttons, `--sans` is body text, both the same family.
  **This is Drive only** - the landing page and the other three games still use xkcd
  Script. Changing the font means changing `sw.js`'s precache list too.

### Tests

`scripts/tests.sh drive` - 690 tests, about 1:25 (four workers, split by file). `test_tracks.py` and
`test_runcheck.py` are pure Python; `test_app.py` runs the real routes against a
throwaway SQLite file (the `/solo` memory, the board and ghost APIs, and a guest's run
being replayed after login). **`test_race.py` covers the room's race machine** -
the ways a race used to strand a room (no finisher, the last car leaving, a
stale timer closing the wrong race), the grid rules, the room's settings, the
rating rules, and the replay recorder. Most of it builds the live room state
directly, since it is plain dicts and what is under test is the bookkeeping
rather than the wire; the last group is different and drives the **real socket
handlers** from `free` all the way to the green light, with the emits captured
and the timers fired by hand, because the thing worth pinning about a phase
machine is the order it goes through them in. **`test_sim.py` runs the game's real JavaScript
headlessly**: `tests/jsrt.py` strips the ES module syntax, swaps three.js for
`tests/three_stub.js` (real Vector3/Quaternion maths, inert graphics), and runs it in
QuickJS, then `tests/autopilot.js` *drives every track to the finish*. That is the test
that matters. **Each track is driven once and the lap kept** (`_sim` caches on the
`rt` runtime): seven tests ask questions about the same lap - did it finish, did it
respawn, how much air, how long - and the autopilot has no randomness anywhere in it,
so driving it seven times bought seven identical answers and three quarters of the
suite's runtime. Two things follow: a test must **read** that result rather than
mutate it, since its neighbours are handed the same dict; and test_sim.py has to stay
on one worker, which is why drive is split by file. Between them these have caught: road and grass being coplanar (the car
thought it was on grass for whole laps); wall collision geometry being double-sided so
contacts cancelled velocity twice per step; loops folding back onto themselves tightly
enough to trap a car forever, and later meeting the road at a 55-degree kink; checkpoint
planes being tracked across the whole map so real passes went unnoticed; the spawn point
having no road under it; a loop built with `self.x` for all three coordinates; and
several tracks that simply could not be finished. Needs `quickjs`, which lives in
`drive/requirements-test.txt` rather than `requirements.txt` so a plain deploy install
is unaffected. Without it these tests skip, which reads as a pass - `scripts/tests.sh`
and CI both install it.

**Two other files run browser JavaScript the same way, against a stub DOM instead of a
stub three.js.** `test_touch.py` lifts the touch bindings straight out of `game.js` and
drives them with synthetic touches (the handbrake gesture, and that left-right-left is a
correction rather than a double-tap); `test_pending.py` runs `pending.js` against a fake
`localStorage` and a `fetch` whose answers the test chooses. Both extract by marker
rather than line number, and `test_touch.py`'s stub deliberately lists every function
`bindInput` reaches for - if a new one appears the slice throws instead of quietly
testing nothing. `test_slipstream.py` does both halves: `Car.draft` runs for real
in QuickJS (it only reads the body's own frame and the rivals it is handed, so it
needs no world and no lap), and `contactOn` is lifted out of `game.js` by name and
run against a stubbed phase. **`test_catchup.py` is the same file for the
catch-up boost**, in the same two halves: `Car.catchup` run for real for the
deadzone, the ramp and the smoothed follow, and `catchupOn`/`gapToLeader` lifted
by name for the phase gate and for the gap - that a finisher is not somebody you
are still catching, that leading is worth nothing, and that the two are one call
so a caller cannot get a gap it should not have. Three of its tests are only
about the *numbers*, since how big this is is the whole design: full help has to
read **exactly 180 on the speedo** (pinned on the dial rather than as a band
round the multiplier, so making the game faster has to be said twice), a tow has
to stay the larger of the two prizes or lifting off and waiting becomes a tactic,
and the pair of them stacked must still land under the hard velocity clamp, or
the clamp is what sets the top speed. **`test_bump.py` is that file again for
car-to-car contact**, and it needs a world where those two do not - contact
happens between cars on a road, and the grip term the whole thing turns on only
exists while a car is grounded. It pins the two thresholds (nothing below
`BUMP_FEEL`, heard-and-free between the two, charged past `BUMP_COST`), that ten
events of sustained rubbing still cost under 2% of your speed, that the body is
not leaned over by held contact, that a hit is never a spin or a rollover at any
closing speed, that the let-go tyres come back on their own clock - and the one
that is the actual finding, that the displacement comes from `BUMP_SLIP_GRIP` and
from nothing else, asserted against *the same hit with that one number pinned
back to `GRIP`* rather than against a figure in a comment that would rot.

**The garage has two test files because it has two halves that fail
differently.** `test_garage.py` is Python: it checks the palette's claim about
itself in both directions (every pair far enough apart in CIELAB, every entry
far enough from every backdrop, every L* inside the band), that `validate` never
raises on anything, each gate against a stats row that does and does not
qualify, `resolve` replacing an ungranted item however it arrived, the record
badge persisting and surviving losing the record, and the two deliberate
duplications of `RECORD_GREEN` read out of `render.js` and `style.css` rather
than trusted. **`test_garage_js.py` builds `CarView` for real in QuickJS**, the
way `test_sim.py` runs the physics, because almost everything that can go wrong
with assembling a car out of a livery is invisible to both of the checks this
project otherwise leans on: the autopilot never draws, and a screenshot of one
car either photographs "the fifth rim style is 24 meshes instead of one"
correctly or photographs it as something you would have to already suspect. So
it pins the *construction* - the mesh and material budget (14 and 6 plain, 20
and 9 fully loaded), that no material escapes `_mats` and therefore
`setGhostly`, that a rim style is one geometry shared by four wheels, that every
decal clears its panel and faces up (the cross product taken from the raw
positions, since the stub's `computeVertexNormals` does nothing), and that
nothing a livery does moves any part of the car that was already there.
**Both of them exist mainly to say the same thing**: an account with no garage
row is byte-identical to one from before the garage existed. Note this is also
what pushed `three_stub.js`'s materials from one shared `noop` to three real
classes that keep their options - with all of them the same class,
`instanceof MeshPhongMaterial` was true of everything on the car and no test
could tell gloss from matte, which is the entire subject of the finish slot.

`test_rules_js.py` is the same lift-by-name trick on
rules that were each a bug or a contract between two files: that `R` and `T` do
nothing (and say nothing) until the clock is running, that `placeOnGrid` puts
pole on the track's own `pole_side` and the row behind it on the other, that
`lampsOf` reads a recorded flag byte with drift winning over brake, that the
tow goes out of `sendPose` as one number the flag disambiguates and comes back
out of `rivalSound` as the two it is drawn and heard from, and that the two words
the camera keys are held under travel from `KEYMAP` through `viewKeys` to the
`opts` that `Renderer.follow` reads in the other file - a rename at either end is
a key that quietly does nothing, which no screenshot and no lap can catch.

**`test_sound.py` is the one file a screenshot cannot stand in for.**
`sound.js` builds a graph of nodes and then only moves numbers about inside it,
so a wrong `connect`, or a voice rebuilt every frame, is completely silent to
look at and completely wrong to listen to. It runs the real module in QuickJS
against a fake `AudioContext` that records what was connected to what, and pins
the wiring and the bookkeeping: one voice per car and kept, a car dropped from
the list torn down rather than forgotten, everything a rival makes going through
its own panner and the panner through the bus under the effects bus (so muting
still mutes the field), and the listener's forward and up coming off the
camera's own quaternion - including rolled upside down, which is a loop. It
also pins the two switches being two - muting leaves the music's gain alone and
vice versa - and the music scheduler: nothing booked twice, nothing booked at
all when it is off, and a tab that was in the background for ten minutes
picking up rather than firing ten minutes of notes at once.

There is no browser in CI, so **check rendering by hand** before shipping a
geometry change - and a *room* needs one more step than a solo track does,
because `/room/<code>` redirects anyone who is not already a player in it. The
cheapest way in is a scratch harness that imports the real app and adds a
login-and-join route, so headless Chrome can reach a room in one navigation;
`/j/<CODE>` then does the joining for real. Set `session.permanent` in that
route or the cookie dies with the headless run and the second navigation lands
on the login page. A persistent `--user-data-dir` keeps the session across
shots, which is what makes `?panel=` reachable afterwards.

**Anything about a second car needs a second car**, and the cheapest one is a
`python-socketio` client: log in as a guest with `requests`, `POST /create`,
`GET /j/<CODE>`, then connect with the same cookie, `join_room_`, and emit
`pose` 30 times a second with whatever position and flags the shot needs. That
is how the rival slipstream was checked. It is also the only way to see a phase
rule, since **`?panel=qual` pins the HUD label and not `S.racePhase`** - the bot
is the host, so it can emit `start_race` and open a real qualifying session.
Templates are cached, so restart the dev server after editing one.

Run the app on a spare port and screenshot it with headless Chrome
(`google-chrome --headless=new --use-gl=swiftshader --enable-unsafe-swiftshader
--virtual-time-budget=9000 --screenshot=out.png http://127.0.0.1:5055/solo/twist`). That
is how the forest of bridge piers and the dark undersides were found - both invisible to
every test. `?panel=`, `?touch=1` and `?shot=1` make the panels, the phone layout and a
clean preview shot reachable the same way. Note `app.py` runs with the reloader on, so a
backgrounded dev server needs `debug=False` or it forks and the port looks dead.

**Drive deploy:** the usual Action also (when `drive/.env` exists) builds/updates
`drive/venv` and `sudo systemctl restart drive`. nginx has a `drive.cgovind.com` vhost
proxying `:5005` with WebSocket upgrade, its own Let's Encrypt cert, and a Route 53 A
record. `/drive` on the main site 302-redirects there (`DRIVE_URL`). As with the others,
nginx/TLS/DNS/`.env` are hand-managed on the box.

## Deploy

Prod is one Ubuntu EC2 box at the Elastic IP `54.157.20.148`, serving
`cgovind.com`/`www` (the website) and `ttr.cgovind.com` (TTR) over HTTPS through
nginx + certbot (Let's Encrypt, auto-renew). Route 53 hosts the `cgovind.com`
zone. The website runs as the `website` systemd service (gunicorn on
`127.0.0.1:5002`); TTR runs as its own service on `127.0.0.1:5001`.

Push to `main` triggers `.github/workflows/deploy.yml`: pick the changed modules,
run those tests (see **Tests** below), then an
SSH deploy (repo secrets `EC2_HOST`/`EC2_USER`/`EC2_SSH_KEY`, where `EC2_HOST` is
the Elastic IP) that runs `git reset --hard origin/main`, `git submodule update`,
`pip install -r requirements.txt`, and `sudo systemctl restart website`. That is
all it does: it ships `site/` and `app.py` but does NOT touch nginx, TLS, or the
box `.env`, and does NOT run `deploy/setup.sh`. Apply nginx/TLS/`.env` changes by
hand over SSH (`ssh ubuntu@54.157.20.148`; nginx config at
`/etc/nginx/sites-available/website`). `deploy/setup.sh` is the one-time bring-up.

Say "push" (or run `/push`) to commit, push, watch the Action, and verify the
live site in one go. If the SSH step fails with `dial tcp :22 i/o timeout`, the
`EC2_HOST` secret is stale: `gh secret set EC2_HOST --body 54.157.20.148`.

## Tests: run only what changed

The full suite is about three minutes (drive ~1:35, kot ~1:10, site ~15s, ers a
couple of seconds) and nearly every change is to exactly one game, so **never
reach for the whole thing by hand**:

```bash
scripts/tests.sh              # only the modules the working tree touches
scripts/tests.sh drive        # one module: site | drive | ers | kot
scripts/tests.sh --all        # everything
scripts/tests.sh --list       # what would run, without running it
scripts/tests.sh drive -- -k ghost -x     # after --, straight to pytest
```

- **`scripts/changed-modules.sh` is the one place a path becomes a module**, and
  both the runner and CI call it, so a laptop and the Action can never disagree.
  `drive/`, `ers/` and `kot/` map to themselves; `app.py`/`site/` (and anything
  unrecognised, deliberately) map to `site`, whose "suite" is `import app` - the
  same check the deploy used to be. Docs, `deploy/` and `.claude/` map to
  nothing; **`scripts/` and `.github/workflows/` map to everything**, because a
  change to the selection itself is a change you cannot trust the selection about.
  `ttr/` maps to nothing: it is a submodule with its own repo and its own CI.
- **The venvs are gitignored, so a module you have never tested locally has
  none.** `tests.sh` builds it rather than reporting `No module named pytest`,
  which is not a test result. It also installs `requirements-test.txt` if there
  is one - that is where drive's `quickjs` lives, kept out of `requirements.txt`
  so the box never compiles a JS engine it has no use for. **Without quickjs,
  `test_sim.py` skips itself, which reads as a pass**, which is why CI installs
  it explicitly. A venv is rebuilt when its requirements move, keyed on a
  `.requirements-stamp` of the two files: they are long lived and gitignored, so
  otherwise a dependency added to `requirements-test.txt` reaches CI and a fresh
  clone but never the venv you have been using for months - and a *test-only*
  dependency going missing does not fail, it quietly stops doing its job.
- **`parallel_for` in `tests.sh` splits each suite across four cores**, which is
  most of the difference between a three minute full run and a ten minute one.
  Two things about it are not arbitrary. **drive is split by file, not by test**:
  `test_sim.py` drives each track once and keeps the lap, so handing those tests
  to separate workers makes every one of them re-drive it - measured slower than
  no parallelism at all. And it is **four workers rather than every core**, since
  past four the critical path is one long file either way, while on a 16 core
  laptop kot's self-play tests contend badly enough that the suite stops
  finishing. `ers` opts out (18 tests in 0.05s - workers cost more than they
  save), an explicit `-n` after `--` wins, and a venv without `pytest-xdist`
  runs serially rather than refusing to run.
- **In the Action, `pick` asks the GitHub compare API which files moved rather
  than cloning to find out.** This repo's `.git` is ~484MB of committed media and
  `site/` is ~513MB on disk, so a full-history checkout would cost more than the
  tests it is trying to save. Every job is a sparse checkout of just its own
  module (for `site` that is the root files only, since `import app` never reads
  `site/`). The suites then run as a parallel matrix, so a two-game change costs
  one game's wall time.
- If nothing testable changed the `test` job is skipped, and `deploy` treats
  skipped as fine - hence its `always() && ...` guard, since a skipped need would
  otherwise skip the deploy too. A **failed** suite does block the deploy.
- `workflow_dispatch` on the Action has a `test_all` box (default on) for
  re-running everything without a commit.
