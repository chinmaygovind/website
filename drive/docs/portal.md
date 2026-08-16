# Drive on a game portal (CrazyGames)

Read this before touching `portal.py`, `static/js/portal.js`, `/api/portal/auth`,
the sitelock header, `login.html`, or anything about who a player is inside a
frame.

Drive is submitted to CrazyGames as an **iframe game**: they do not host the
files, they put `<iframe src="https://drive.cgovind.com/solo?portal=crazygames">`
on a page of their own. So there are two builds of Drive, from one codebase and
one server, and the difference is not cosmetic - one of them contains a
username-and-password login and the other one may not.

## The one flag everything hangs off

`?portal=crazygames` on the entry URL, stored in the session by
`app._remember_the_portal`, read everywhere through `app.portal_mode()` and
handed to every template as `portal`.

**It has to be the server, and it has to be on the first byte.** `html.framed`
in `base.html` is a client-side check and it is the right answer for the two
things it already does - the door, and links that would navigate the frame away.
It is the wrong answer here, because the question is whether a page *contains* a
password field, and by the time a script could remove one it has been sent to a
reviewer's browser.

**It sticks, because a portal only ever gets to set the entry URL.** Every link,
form and Socket.IO handshake after that is ours and none of them would carry the
parameter.

Typing `?portal=crazygames` on drive.cgovind.com puts you in the portal build -
deliberate, and the only way to look at it without a portal, the same way
`?framed=1` and `?touch=1` already work. It can only ever take login UI *away*.
`?portal=none` is the way back, and so is any unrecognised value: a stale flag
would be a session with no login page and no way to reach one.

## What the portal build does not have

CrazyGames' rule is **"external login options (e.g. Facebook, Google, email) are
not allowed"**. Drive's login is a username and a password over an email
address, so in the portal build:

- `POST /login`, `POST /register` and `/logout` **404** (`app.portal_only_404`).
  A 404 and not a 403 or a redirect: the rule is that the game does not offer
  these, and "we took the link away" is not that. It is the same argument
  `/admin` makes on the main site.
- `login.html` renders its other half - *Sign in with CrazyGames*, plus the
  guest name form. The sign-in is deliberately **not** the accent button: their
  rule for a login offered to guests is that it must not be the primary
  call-to-action and must not block play.
- the nav says *Sign in*, the account page has no *Log out*, and `/privacy`
  grows a section about their SDK that the cgovind.com build does not have -
  because on this domain none of it is loaded.

**Guest names stay.** Typing a name to race under is not a login and no rule
touches it; taking it away would cost the portal build the whole of multiplayer
for anybody not signed in to CrazyGames.

`test_portal.py::test_no_page_in_the_portal_build_carries_a_password_field` is
the sweep that keeps this true of pages nobody thought of as login pages.

## Signing in

```
portal.js  getUserToken()  ->  POST /api/portal/auth  ->  verify_token()
                                                      ->  resolve_user()
                                                      ->  session["user_id"]
```

- **The token is verified on the server and never read on the client**, which is
  their instruction and the only version that means anything: the claims say who
  the player is, and a client that decoded its own token could say anybody.
  RS256 against the key at `sdk.crazygames.com/publicKey.json`, cached a day.
- Their key is **PKCS#1** (`BEGIN RSA PUBLIC KEY`). Which of the two PEM shapes
  a given PyJWT accepts has moved between releases, so `portal.py` loads the key
  with `cryptography` itself and hands PyJWT an object.
- **`CRAZYGAMES_GAME_ID` is worth setting once the game has an id.** Unset, a
  token from any *other* CrazyGames game verifies here too - the signature is
  theirs either way. It is not in the code because the deploy never touches the
  box `.env` and the id does not exist until submission.
- **A token that does not verify leaves you a guest**, with a 200 and the same
  answer shape. Their CDN having a bad morning is not worth a screen and
  resolves itself on the next load.
- `/api/portal/auth` **404s outside the portal build**. Left open it would be a
  way to make an account on this site, from anywhere, with no email and no
  password.

### The account it lands on

An ordinary row in the shared `users` table - the same leaderboard as everybody
else, unmarked, and usable in Ticket to Ride and King of Tokyo. Two things mark
it out and both are deliberate:

- **The username is a hash** (`cg-` + 12 hex of `sha256(portal:userId)`). A
  username here is the login and the address of a public profile and can never
  be changed. A CrazyGames player never asked for one, so minting `nick2` out of
  their portal name would hand somebody a permanent public address they did not
  choose - and would put a name a stranger picked into the namespace real
  accounts are named from, where `chinmay` is already taken.
- **The display name is theirs**, cleaned by `app.clean_display_name` and
  suffixed `(2)`, `(3)`… if it collides. Two collisions are checked, not one: a
  display name may not equal another profile's *or* anybody's username. A portal
  is the first place names arrive that nobody on this site vetted.

`drive_portal_users` is **Drive's table, not a column on `users`**. `google_id`
sits on the shared row and would have been the obvious neighbour, but that row
is defined five times, once per service - a column means five model edits, the
drift tests moved, and an `ALTER` on the live database by hand. A portal is
something Drive is submitted to; the account is an ordinary shared account that
the other four games can use without knowing where it came from.

The `last_username` / `last_avatar_url` columns are what make the ordinary page
load a read: CrazyGames ask that a rename or a new picture is reflected here, and
these are what stop that being two queries and a download every time.

### Pictures

Fetched from their CDN, decoded, cropped, resized and **re-encoded** by Pillow,
and only Pillow's bytes are stored - the same rule the upload path at
cgovind.com/accounts follows, for the same reason, and it matters no less for
coming from a CDN than from a form.

**The stored name must be `<user id>-<8 hex>.webp`.** These files land in the
same directory `accounts/` writes to and are served by its route, which
re-checks the shape with `avatars.is_safe_name` rather than trusting a column
five services can write. A name of any other shape stores fine, records fine,
and then 404s for ever with nothing reporting it.
`tests/test_no_drift.py::test_a_portal_avatar_lands_on_a_name_the_site_will_serve`
holds the two ends together.

**`AVATAR_DIR` has to be set in `drive/.env` on the box** (`/home/ubuntu/avatars`),
by hand, because the deploy never touches a box `.env`. Unset, it falls back
inside the checkout and a portal player keeps the drawn initial everybody with
no picture gets - a supported state, not a broken one. Drive renders no avatars
anywhere, so the only screen this changes is the shared profile on cgovind.com.

### They are off the accounts directory

`accounts/routes.py::directory` excludes anybody with a `drive_portal_users`
row - raw SQL behind `gamestats.table_exists`, because a box without Drive has
to render that page rather than 500. Their profiles still work and a leaderboard
still links to them: it is the roll call they are off, not the site. If Drive
does well on a portal, an unfiltered directory is a page of `cg-` names with the
handful of people this site is for somewhere underneath.

**The per-game lobby lists are deliberately not filtered.** The question a lobby
raises is "is there anybody around to play", and somebody who arrived through
CrazyGames is somebody you can race. That list is also `visits.online_now`,
which lives in the file copied verbatim into five services and may not learn
about a Drive table.

## The sitelock

`Content-Security-Policy: frame-ancestors` on every response, from
`portal.frame_ancestors()`.

**Their own documentation offers `crazygames.*` and that is not valid CSP** -
the grammar has no TLD wildcard. A browser silently drops a source expression it
cannot parse, so the header would read as though it covered them and
www.crazygames.fr would get a blank frame. The ccTLD hosts are enumerated;
`https://*.crazygames.com` carries www, games (where their video ads run),
developer (where the QA preview frames it, so leaving it out fails the *review*
rather than the game) and the language subdomains.

`FRAME_ANCESTORS` in the box `.env` replaces the whole list, for the case a
domain has to be added without waiting for a release. `*` turns the lock off.

**Check it survived a cert renewal.** `certbot --nginx` rewrites the drive vhost
in place, and nginx serves `/static/` off disk there - so if a `Content-Security-Policy`
is ever added at the nginx level too, the two intersect and the most restrictive
wins. `curl -sI https://drive.cgovind.com/` and read the header that comes back.

## The SDK, and the version

`static/js/portal.js`, loaded by `base.html` on **every** page. It used to be
inline in `play.html` and only fired `gameplayStart`; it moved because signing
in is not something the play page can own - a copy there would leave the
leaderboard, the lobbies and the account page looking at a guest.

**It is v3** (`crazygames-sdk-v3.js`). The inline version was v2 and used its
callback `getEnvironment(cb)`. The difference fails *silently*: v3 turned the
async getters into plain properties (`SDK.environment`,
`SDK.user.isUserAccountAvailable`), so the v2 spelling against v3 calls
`undefined` and the v3 spelling against v2 reads `undefined` - neither raises,
and both end with the SDK looking absent. v3 also requires an explicit
`await SDK.init()` before anything works.

Four things in there are load-bearing:

- **It is only loaded inside a frame.** Off one it fetches nothing at all, which
  is what keeps `/privacy` true for every player on drive.cgovind.com.
- **Off a CrazyGames domain every SDK call throws** - their words - so nothing
  calls one directly. `call()` is the only place with the try/catch, and `SDK`
  is only kept once `environment` has said it is real.
- **The game is playable before a CDN script can be relied on to have arrived**,
  so `playing` is held locally and replayed when and if the SDK turns up.
- **Nothing here may cost somebody a lap.** Every failure ends with a guest and
  a game that plays.

`gameplayStart` / `gameplayStop` are still called from `game.js`, which may only
ever speak to the wrapper (`test_nothing_calls_the_sdk_without_a_guard`).

**The play page opts out of the post-sign-in reload** (`DrivePortalNoReload`).
Elsewhere a page rendered for a guest that turns out to be somebody is simply
reloaded, once a tab; on the play page that would mean building the track twice,
in the middle of the load the portal is timing. Nothing on that screen but the
name depends on it, because `/api/run` reads the session on the server rather
than what the page believed when it was drawn.

**The handshake is throttled to once an hour per tab** for a player who is
already signed in. Not for its own sake: `visits.py` logs a row per request and
is the file copied verbatim into five services (TTR's copy lives in its own
repo), so a skip rule there is a change across all of them, where this costs
nothing and keeps a portal player's clickpath readable. A page rendered as a
guest ignores the throttle - a session cookie a portal's partitioning quietly
dropped would otherwise leave somebody signed out for an hour with a valid token
in hand.

## What is still to do

- **`CRAZYGAMES_GAME_ID`** in `drive/.env` once the game has an id.
- **`AVATAR_DIR`** in `drive/.env`, or portal players keep the drawn initial.
- **Account linking** (`showAccountLinkPrompt`) for somebody who has both a
  CrazyGames account and a cgovind.com one. Not needed for the Basic
  implementation Drive is submitted against; `drive_portal_users` is shaped so it
  is a row pointing at a different `user_id` and needs no migration.
- **Progress for guests** through their Data module. Basic does not require it,
  and it would be a second source of truth for times the anti-cheat never saw.
- **Ads.** Basic implementation runs with them disabled, and Drive has no
  natural break to put one in.
