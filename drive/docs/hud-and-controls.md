# Drive: the HUD, the phone and the type

Read this before changing the in-game HUD, the settings/help sheets, the keys,
the touch controls, `sound.js`, or the type.

The site's own pages — the home page, `/solo`'s track switcher, `/account` and
`/leaderboard` — are in `pages-and-boards.md`.

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
- **Settings is only settings.** Title, an X, and the things you set. The
  session controls moved to the HUD. It is **Splits and the ghost car, then
  Sound and Music, then the two ways out** - a white *View Leaderboard* beside
  the red *Exit Solo* / *Exit Multiplayer*, the red one last because it is the
  only control on the sheet that pressing again does not undo (and it names what
  it is leaving for the same reason - see below). Every label on it is **Title Case**, down
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
  still hides every ghost for the whole of a race.
- **Two switches, two keys: `K` is which lap, `G` is whether it is drawn.** They
  shared `G`, which stepped through the laps and left the car reachable only from
  the settings sheet. `K` steps through `GHOST_CYCLE` (off, my best, world record;
  plus provisional pole in a room) rather than toggling the last one back on, and
  a lap chased off the board is deliberately not in the cycle, so pressing it
  leaves that lap. `G` is a plain toggle, because with two states landing on the
  one you meant should not depend on where you started. **`K` and not `P`** - `P`
  has always changed track, which is the more common thing to do and the harder
  muscle memory to move; `K` is admitted to have no mnemonic, and every letter
  with a claim on "splits" or "lap" is a driving key or already taken.
- **The defaults are your own best lap and no car**, for somebody who has never
  opened the sheet: `storedGhostMode()` falls back to `me` and `drive.ghostcar`
  to `false`. **The car used to default on.** A first lap of a track is one you
  are reading, and a translucent car driving the racing line through it is in
  front of the road rather than beside it - while the deltas, which are the half
  of a reference lap you can read at 200km/h, cost nothing to leave on. So the
  two halves of the old single switch now default differently, which is most of
  why splitting them was worth doing.
- **Nothing but you may write your splits choice, and four things used to.** All
  of them were the same shape - the *setting* said one thing and the road did
  another, with the setting telling the truth about what you had chosen and a lie
  about what you were chasing:
  - **A new PB.** `/api/run`'s handler called `loadGhost('me')` unconditionally, so
    setting a personal best swapped the ghost to your own lap while the row still
    read *World Record*. It never touched `S.ghostMode`, which is why it looked
    like a lost setting rather than a bug. Now it reloads only when the mode is
    `me`, plus the one genuine case: taking the record makes a `wr` ghost stale.
  - **Opening a lap off the leaderboard.** `run` is not a standing choice and
    `storedGhostMode` cannot restore it, so it was filed as `me` - which meant
    chasing one lap from the board permanently rewrote a `wr` preference. `run` is
    no longer written at all.
  - **Switching track.** It hid the ghost car with `remember: false`, so the stored
    preference still said *on* while the road had no car. That was defended as
    "somewhere new is somewhere you are looking at rather than attacking", which is
    a fair thing to want and the wrong way to get it: a setting that turns itself
    off when you go somewhere is not a setting. Gone.
  - **Arriving anywhere at all**, which is the one the account store found.
    `loadTrack` re-applies the mode it already has, and both landing on a page
    and switching track go through it, so the write there was your own setting
    being handed back to itself - harmless while it was a `localStorage` line and
    three wrong things once it was a request: a POST to `/api/prefs` on every
    page load, the `me` that a chased lap falls back to filed as a standing
    choice, and a `pole` picked in a room rewritten to `me` the next time you
    opened a time trial, since `storedGhostMode` filters `pole` out there. It is
    `remember: false` now, like the ghost car beside it.

  Five tests pin this group, and one of them is worth knowing about: the first
  version of the `run` test asserted `"mode !== 'run'" in body`, which **passed
  with the fix reverted**, because that comparison also appears three lines up
  clearing `S.ghostRun`. It now parses the guard on the `rememberPref` call
  itself. A source-reading test that cannot fail is worse than no test, and that
  one proved it by not failing.
- **Storage is `localStorage` for everybody, and `drive_prefs` as well for an
  account.** The local copy is still the primary one and is written on every
  change, because Drive is playable with no account at all and a per-user table
  alone would leave every guest without a memory. What the table adds is the half
  `localStorage` cannot do: the settings follow the *person* rather than the
  browser, so they survive moving between machines and are the same on both sides
  of a login. The two stored that way are the splits mode and the ghost car -
  the two that change what the road looks like - and the allow-list saying so
  exists twice on purpose, as `ACCOUNT_PREFS` in `game.js` and `PREF_SPEC` in
  `app.py`, because the client decides what to send and the server decides what
  it will keep. Four things about it:
  - **The account answers first.** `accountPref()` is consulted ahead of
    `localStorage` in both `storedGhostMode` and `storedFlag`, so a machine you
    have never driven on - or one somebody else set up - is not the answer.
  - **`CFG.prefs` is `null` when the account has never chosen**, and that is a
    different thing from `{}`. It is the one case where the settings sitting in
    this browser are adopted as the account's (`adoptLocalPrefs`, once, at boot),
    which is what stops this landing as "everybody who was already playing lost
    their settings". An account with a row is never overwritten by the machine.
  - **`/api/prefs` is POST-only and merges.** The page embeds what it needs in
    `DRIVE_CFG.prefs`, so the settings are right on the first frame rather than a
    request later - the same reason the livery comes down with the page - and
    every one of the three play modes has to pass `prefs_json`, because a mode
    that forgot would render a Jinja blank into the config block and the game
    would not boot at all. A guest gets a 401, which is what stops the client
    posting into the void rather than a refusal to let them choose.
  - **Sound, music, FPS and ping stay local**, and that is a judgement rather
    than an oversight: muting a game is about the room you are sitting in, not
    about you. Adding one is a line in each allow-list.
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
- **There is one panel in front of you, and opening another replaces it.**
  Settings, the controls sheet, the board and the track switcher are four
  overlays over the same road, and no arrangement of two of them reads as
  anything but a mistake. They used to know about each other **in pairs**, and
  only in the pairs somebody had happened to hit: settings closed controls,
  controls closed settings, the board closed settings. Nothing closed the
  switcher and the switcher closed nothing - so `P` over the board, or `L` over
  the controls sheet, put two sheets up and left the one underneath to reappear
  when the top one was dismissed. `closeOtherPanels` is now the single answer and
  it lives **inside the four toggles**, which is what makes it true for every way
  in: the keys, the four buttons in the corner, `?panel=`, and the *View Others*
  chip inside settings, which opens the board from a sheet that then has to get
  out of the way. It only ever runs on the way *open*, or closing one would
  re-enter it. `tests/test_panels.py` drives the real functions through QuickJS
  over all sixteen ordered pairs, so a fifth panel added without a line in
  `closeOtherPanels` fails eight times rather than passing quietly.
- **The way out says what it is a way out of.** The red button at the foot of
  settings is *Exit Solo*, *Exit Multiplayer* or *Back to Room*, never a bare
  "Leave". It was the one label on that sheet that did not say where the press
  lands, and the three destinations are genuinely different places - the lobby
  list, the Drive home page, or back into a seat that was never given up.
  Somebody who opened settings mid-race to turn the music down was one ambiguous
  red button away from ending it.
- **Escape closes what is in front of you before it opens anything.** It works
  innermost first - a replay, then a panel opened from another panel, then the
  panel itself - and *then* means "open settings". The controls sheet was
  missing from that list, so pressing Escape while reading it opened the
  settings sheet on top: the one key everybody presses to get out of something
  put something else in the way.
- **`O` is Escape's second key, because in fullscreen Escape is not ours.** The
  browser takes it to leave fullscreen and the keydown never reaches the game, so
  the one key that gets you out of a panel goes missing exactly when the game
  fills the screen. `O` for Options, and it sits in the same right-hand cluster
  as every other panel key - H, K, L, O, P. It is a full alias rather than a
  "just open settings" key: it runs the same `onEscape` chain, so somebody who
  never presses Escape still closes the board and the switcher with it. The
  controls sheet says `Esc / O` and so do the tooltips on the gear and on the
  settings sheet's X.
- **The `?` sheet is Controls, and it is the controls and nothing else.** It
  used to open on a one-line description of the track and close on two
  paragraphs about grass and crests, which is reading matter in front of
  somebody who pressed it to find
  out which key drifts. **The table follows the device** - `body.touch` swaps
  the keyboard rows for the gestures (`.keys-only` / `.touch-only`, the same
  mechanism as the start hint), so it never describes controls you do not have.
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
- **The first visit gets two more things, and they are once-*ever* rather than once
  per session.** The start hint above says which key drives; neither of these is
  about the keys. `#firstBanner` is a pill at the top centre on the first visit to
  Sunrise - which `_last_track` makes the track a first visit lands on - saying
  what the clock is for, and it fades itself after nine seconds. **It had a third
  line naming the keys and that line is gone**, which is what this paragraph
  always claimed and briefly stopped being true of: the start hint says the same
  thing a few pixels lower and is timed to the moment it is wanted, on a touch
  device the two wordings were nearly the same sentence, and the key caps were
  what wrapped the pill to four lines on a phone. Keys have one home on the play
  page and it is the hint. `#tour` is four
  labels with elbow arrows over the first results sheet, pointing at the
  leaderboard, the switcher, the controls and settings: four 38px icons that carry
  most of the game and that nothing had ever pointed at. `localStorage`
  (`drive.seen.goal`, `drive.seen.tour`) and not `sessionStorage`, because a reload
  is a fresh pair of hands on the keys and worth telling twice, while being told
  what a leaderboard is twice is being talked down to. A browser that throws on
  storage is shown **neither**, which is the right side to be wrong on. Five things
  about them are load-bearing:
  - **`.hud` is what lifts over the results sheet, not `.hud-tr`.** The parent is
    `position: fixed`, so it is a stacking context and caps every z-index inside
    it - the obvious one-line fix does nothing at all. The same trap the framed
    door fell into, and why `#tour` itself is a sibling of `#rotate` at the foot of
    the page rather than a child of the HUD.
  - **Lifting the HUD means fading the rest of it and turning its clicks off.**
    `.hud-bc` is 340px across the bottom centre and `.hud-tr` is a tall
    transparent column: at `opacity: 0` both are still hit-testable, and once they
    are above the sheet they are what the click aimed at Retry lands on. Only
    `.btnbar` keeps `pointer-events`.
  - **The tips are one right-aligned column and the order is left button to top
    label.** Each arrow runs along its own line then turns up, so arrow *k* passes
    under every upright to its left; that ordering makes each of those uprights
    end above the line it would have crossed. Reverse `TOUR_TIPS` and the four
    tangle. Each one is measured off its own button's `getBoundingClientRect`,
    because the bar moves with the safe area, with the mode and with the drawer.
  - **The results sheet steps aside below 900px.** A phone in landscape is 812px
    against a 460px sheet, so the column lands on the player's own lap time.
  - **Both stay out of every photograph.** `?shot=` makes the switcher's previews
    and the share cards through the real page and `?panel=finish` reaches the
    results sheet without driving; `beingPhotographed()` is what keeps the marks
    out of files that are committed and that nothing can notice are spoiled.
    **`?tour=1` is the way to look at either** - it forces both on *without*
    writing the seen flag, so a look does not spend a real first visit, and
    `?panel=finish&tour=1` is the sheet with the marks over it.
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
  track card there. That used to have to hide the track's one-line description as
  well, to make the room; the card is the name and the session type now, so there
  is nothing left up there to drop.
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
  Two things bite at the size these are actually drawn (`.btn.toggle .icn` is
  17px). **A dot is a zero-length stroke with a round cap** (`M12 18.4h.01`), not
  a tiny arc back to its own start: `a2 2 0 1 0 0 -.1` puts the point you gave it
  on the *circle* and the centre a radius away, which is how the ping icon's dot
  spent its life 2 units to the left of the arcs it was supposed to be the middle
  of. And **nothing may touch anything it is not part of**: the FPS gauge's needle
  drawn out to the dial welded to it and the pair read as one filled triangle, so
  the needle stops short and the dial carries past horizontal at both ends -
  a clean semicircle with a line under it is a hump, not a gauge. It replaced a
  zigzag-over-a-baseline, which was the generic analytics mark and named nothing.
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

