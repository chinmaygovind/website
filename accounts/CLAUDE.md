# Accounts (`accounts/`)


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

### Visits and presence (`visits.py`)

**Every request to anything on `cgovind.com` is logged, and every account has a
green dot.** Two tables in the shared database, both created by raw
`CREATE TABLE IF NOT EXISTS` so whichever service boots first makes them:
`site_visits` (one row per visit) and `user_presence` (one row per account).

- **`visits.py` is one file copied verbatim into all five services**, which is
  the strongest form of this repo's copy-per-service convention: not five files
  that must agree but five copies of one, so the check is a byte comparison and
  the fix is a copy rather than a merge (`test_every_service_carries_the_same_
  visits_module`). Nothing in it may be service-specific — it is handed the
  `db` to use and reads `flask.session` for the rest, so the text has no idea
  which service it is in. The one difference is the line that starts it:
  `visits.init_app(app, db, "<service>")`.
- **A visit is not every request.** Assets, `/static/`, the socket transport
  and the heartbeat itself are skipped, or the log is unreadable and mostly
  fonts. **A PDF is deliberately on the other side of that line** — the resume
  is the one file whose downloads are worth counting. A 404 is logged, with its
  status: somebody arriving on a dead link is exactly what you want in here.
- **Raw IPs, kept indefinitely, from `X-Forwarded-For`.** Every service listens
  on 127.0.0.1 behind nginx, so `remote_addr` is always the proxy; taking the
  first hop is right *here* and would be wrong on an internet-facing app, where
  the client can prepend anything. This is the first time the application has
  stored an address at all — before it, "who is this account" meant reading
  nginx's logs and matching timestamps by hand, which works and does not
  survive the fourteen days nginx keeps.
- **A `cgv` cookie identifies a browser, and a 30-minute gap ends a session.**
  Set on the parent domain, so reading the landing page and then driving is one
  visitor and not two. Session stitching reads an in-process cache and falls
  back to a query, which is what makes the answer survive a restart.
- **Crawlers are flagged, not filtered.** A bot the regex misses is a row with
  `is_bot = 0`, which is recoverable; a person it wrongly filters is a visit
  that never existed.
- **Presence is public, and it is `visits.py` that writes it.** `touch` says
  "still here" and `seen` says "here, doing this". Ordinary page loads only
  ever `touch`, so a detail set by the last heartbeat survives the pages
  between them — but **changing service clears it**, because "Sunrise Circuit"
  is false the moment somebody opens King of Tokyo. The throttle
  (`PRESENCE_EVERY`) skips a write only when the service is *also* unchanged;
  checking the clock alone was a bug where switching games within 20 seconds
  left the old game on the profile.
- **The status can only ever say what the game offers.** A browser sends a
  *key* to `/api/presence`, the game looks it up in its own `PRESENCE_WHERE`,
  and a miss is no detail rather than something to display. Drive's track is
  the one non-constant and it is still a slug looked up in the pool. A profile
  page is public, so a free-text status would be a billboard with a text box
  attached — `test_a_status_can_only_say_what_the_game_offers` is what stops a
  future heartbeat passing its payload through.
- **The heartbeat is a ping a minute while the tab is visible**, inline in each
  `base.html`. It is what keeps a two-minute solo lap — a stretch with no other
  requests in it at all — from reading as somebody who has left, and skipping
  hidden tabs is most of what makes the dot honest about a browser left open
  for three days. Drive's play page overrides it through `window.driveWhere`,
  because the switcher changes track with no navigation.
- **The wording lives in `accounts/presence.py`** and nowhere else: "Playing
  Drive - Sunrise Circuit", "Playing Ticket to Ride - In Lobby", "Browsing
  cgovind.com", "Offline - last online 5 hours ago". Offline is a *length of
  time* rather than a timestamp, in whole units, and a clock a second fast
  reads "just now" rather than a negative age.
- **The dot is on the profile, on the directory, and on each game's lobbies
  page.** The directory and the lobby lists only ever show people who *are* on
  — a red dot beside every one of sixteen names is a page of red dots, and the
  offline half of the sentence belongs on a profile. The lobby lists are
  cross-game on purpose: the question a lobby raises is "is there anybody
  around to play", and somebody in the middle of King of Tokyo is somebody you
  can ask.

### Tests

`scripts/tests.sh site` — 166 tests, about 15s, plus the `import app` check the
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

**That skip is also how the suite's one real miss happened, so `source()` no
longer allows it.** `test_track_names_match_drive` read `drive/tracks.py`; the
pool became the `drive/tracks/` package; the path stopped existing and `source`
skipped it, which reads as a pass. It stayed green through Spa, Costco
Wholesale and Mount Joy being added, and every one of them appeared on a profile
as its raw slug — `Race · mountjoy` — until somebody read their own page.
`source()` now skips only when the *service* is absent (no Python at its top
level, which is what an uninitialised `ttr/` looks like) and **fails** when a
file is missing from a service that is checked out, because that is a rename and
a rename should be loud. The track test reads the folders now, which is the same
thing the game reads.

