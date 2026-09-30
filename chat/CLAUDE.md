# Chat (`chat/`)

**chat.cgovind.com**: DMs, group chats and game invites across the whole site.
One Flask + Flask-SocketIO service (eventlet, `-w 1`, port **5007**) and one
script, `static/dock.js`, that every logged-in page on every host loads.

## Shape

- **Every action is HTTP; the socket only pushes.** The dock calls the JSON API
  (`/api/...`) with `credentials: 'include'`; the server pushes `chat_message`,
  `read` and `typing` down the socket to room `u<user_id>`. The one thing a
  client emits is `typing`. That split is why every rule is testable with a plain
  test client (`tests/test_chat.py`).
- **The event is `chat_message`, not `message`.** `message` is Socket.IO's own
  `send()` channel and the test client mangles it.
- **Login is the shared session cookie.** Same `SECRET_KEY` and
  `SESSION_COOKIE_DOMAIN` as the games, so `session["user_id"]` set by any game
  is a login here. Guests get a 401 and the dock never draws.
- **CSRF is the origin list plus JSON bodies.** `CHAT_ORIGIN_RE` (default: any
  `https://*.cgovind.com`) is what CORS echoes and what writes are checked
  against, and every write must be `application/json`, which no cross-site
  form can send without a preflight the list refuses. Locally set it to
  `^http://localhost(:[0-9]+)?$`.
- **Tables are all `chat_*`, made by `create_all`.** `users`, `user_profiles`,
  `user_presence` and the four games' room tables are *read* with raw SQL
  (`people.py`, `rooms.py`), never mapped.

## Rules worth knowing

- **Anyone can DM by default**; `chat_prefs.dm_policy = 'following'` limits new
  threads, group adds and invites to people you have added. An existing thread
  is exempt from the policy (switching it on must not cut a friend off
  mid-chat) but never from blocks.
- **A block is silent.** The blocked person gets the same "You can't message
  this person" a policy refusal gives, and in a group their messages simply
  vanish for the blocker - filtered from history and never pushed.
- **Follows are one-way** and are the Friends tab. Conductor has its own mutual
  `friendships` table; it is Conductor's and this does not use it.
- **An invite is a game and a room code, never a URL.** You can only invite
  into a room `rooms.is_in` says you are seated in. The card's state (players,
  started, gone) is read live from that game's own tables on every draw, and the
  link is always `https://<game host>/j/<code>` - which exists in all four games
  now (Conductor's lives in its own repo).
- **Rate limits are in-process** (`LIMITS`): 20 messages a minute, 20 new
  threads a day. Fine on one worker; a second worker needs them in the database.
- **The admin can read every chat** at `/admin/chats` (in `accounts/admin.py`,
  read-only like the rest of the console), and the dock says so in its footer.

## The dock (`static/dock.js`)

- **Shadow DOM, so no game's CSS can reach it** - and so the one real trap:
  a key typed in it reaches `window` retargeted to the shadow *host*, not an
  `<input>`, so Drive's "ignore keys typed into inputs" check would not fire and
  WASD in a message would drive the car. The shadow root stops `keydown` and
  `keypress`; `keyup` is let through so a key held when focus arrived still
  releases.
- **A host page can move the tab** with two custom properties on the shadow
  host, which inherit through `:host{all:initial}` because `all` does not reset
  custom properties: `#cgv-chat { --cgv-tab-top: auto; --cgv-tab-bottom: 24px; }`.
  Unset, it is two thirds of the way down the right edge (`top: 67%`), on every
  host. Drive uses it only on touch, to lift it back to 42% off the throttle.
- **That chats are readable by the admin is said in Drive's privacy policy**, not
  in the dock's footer, which holds the full-chat link and the sound toggle (an SVG bell, not an
  emoji, so it matches the site's line icons).
- **`/` is the dock as a whole page** (`static/index.html`). `dock.js` goes
  full-page when `location.origin` is its own host: no tab, no close button,
  mounted in `<main>`, and `#c<id>` opens that thread. Everywhere else the
  footer's "Open full chat" links there (new tab, so a game is not left).
- **Toasts never take focus.** Mid-race the throttle stays held.
- `window.cgvChat` (`open`, `invite`, `person`, `follow`, `block`, `prefs`) is
  how the profile buttons and the settings "Messages" box drive it. Both stay
  `hidden` until `cgvchat:ready` fires, so a page without chat shows nothing
  broken.
- It is included by each game's `base.html` when `current_user and chat_url`
  (not in Drive's CrazyGames build), by `accounts/templates/accounts/base.html`,
  and by `site/index.html` unconditionally (static; guests just get a 401).
  `CHAT_URL=` (empty) in a service's `.env` turns it off there.

## Running it

```bash
scripts/tests.sh chat                       # ~2s, serial
cd chat && PORT=5007 venv/bin/python app.py # local; set CHAT_ORIGIN_RE for localhost
```

`CHAT_HOST_<GAME>=localhost:5004` points invite links at a laptop.

## Bring-up on the box (one time)

The deploy skips `game chat` until `chat/.env` exists, so none of this happens
by itself:

1. **DNS**: an A record `chat.cgovind.com → 54.157.20.148` in Route 53 (by hand).
2. `chat/.env`: copy `kot/.env`'s `SECRET_KEY`, `SESSION_COOKIE_DOMAIN`,
   `SESSION_COOKIE_SECURE` and `DATABASE_URL`.
3. `python3 -m venv chat/venv && chat/venv/bin/pip install -r chat/requirements.txt`
4. `deploy/chat.service` → `/etc/systemd/system/chat.service` (fill `{{APP_DIR}}`,
   `{{USER}}`), `systemctl enable --now chat`.
5. The `chat.cgovind.com` block from `deploy/nginx.conf` into
   `/etc/nginx/sites-available/website`, then `certbot --nginx -d chat.cgovind.com`.

Until then every logged-in page asks for a script from a host that does not
resolve, which fails quietly and draws nothing.
