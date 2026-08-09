# Egyptian Rat Screw (`ers/`)


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

