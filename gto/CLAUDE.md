# gto/CLAUDE.md

**gto.cgovind.com** - a no-limit hold'em trainer that simulates one specific
home game, marks every decision you make in it, and tells you what you are
losing and how little anybody can know that from one evening.

One seat, five bots named after and tuned to Chinmay's actual friends. No
lobby: opening the page sits you down.

## Read this much and no more

Seventeen files, 7,400 lines, and they are a stack rather than a web - each
layer knows only the one below it. **Find your layer and read that file's
docstring before its code**; every one of them opens with what it is for and
what it deliberately refuses to do.

| you are changing | read |
|---|---|
| the rules of poker | `engine.py` |
| how a hand is ranked | `evaluator.py`, `cards.py` |
| equity, pot odds, EV | `equity.py` |
| what a bet size is worth | `rollout.py` |
| checking any of it against the outside world | `validate.py`, `/proof` |
| preflop charts | `ranges.py` |
| how a friend plays | `profiles.py`, then `bots.py` |
| what a board means | `texture.py` |
| the streak side game | `bounty.py` |
| a session, seats, stacks | `table.py` |
| **the marking** | `review.py` |
| **the second opinion** | `coach.py` |
| win rate, hourly, intervals | `stats.py` |
| routes, database, the page | `app.py`, `models.py`, `templates/`, `static/` |

## The one rule this whole thing turns on

**Every number the review prints says where it came from.** Five labels, defined
in `review.py` and rendered in every line:

- `solver` - read off a published equilibrium solution. Preflop only.
- `derived` - a solved range moved by a stated argument, and the argument is
  printed with it.
- `heuristic` - **no solve exists for this spot.** Today that is exactly one
  node, the equal-blind small blind.
- `model` - **exact against this table, not against equilibrium.** Every bot's
  strategy is a known function, so the range it is on after an action is
  computable by Bayes rather than guessable, and your equity against that is a
  real number. It says nothing at all about equilibrium.
- `arithmetic` - pot odds, break-even frequencies, minimum defence. True by
  definition.

**Nothing may ever be labelled better than it is, and adjusting something never
improves its label.** `ranges.apply_depth` used to stamp everything it touched
`derived`, which silently promoted the equal-blind small blind - the one
heuristic here - to "adjusted from a solved equilibrium" for anybody sitting
deeper than 150bb. A guess moved for stack depth is still a guess.

The corollary: **where there is no number, the review says so.** A raise cannot
be priced without solving the subgame after it, so a raise gets its sizing
arithmetic and the verdict `unpriced` rather than a score that came from
nowhere. Somebody learning from this has to be able to tell "this is wrong" from
"nobody knows", and the difference is in the label.

## The seven things that are not obvious

**The equal blinds change the game, and they are the reason published charts
are wrong here.** At 0.25/0.25 the small blind has already matched the big
blind, so *folding is strictly dominated by checking* - `EQUAL_BLIND_SB` has no
fold branch at all. And a 2.5bb open faces 2bb dead rather than 1.5bb, so it
needs to work 55.6% of the time rather than 62.5%: about a seat's worth of extra
position, which is why every opening range here is wider than the chart it came
from. This is the largest structural difference from anything published, and it
is `derived` with the argument attached, never `solver`.

**The bounty dominates the poker at these stakes, and it is priced into the pot
rather than bolted on.** Three wins in a row pays $1 from everyone, four pays
$2, five or more pays $3 - which at a 25-cent blind is 20bb, 40bb and 60bb.
On a streak of two, winning the pot is worth about 28.5bb *more* than the pot.
Folding breaks a streak exactly as surely as losing does, so `review.py` adds
the streak's value to the pot before computing what you need, rather than
treating it as a bonus for gambling. `bounty.streak_value` is where that number
comes from.

**Equilibrium and this table disagree, and when they do that is the most useful
thing on the screen.** Charts assume the opponent is also playing equilibrium.
Sanjay is not. A call no chart makes can be a clear profit against a 45% opening
range, and marking it `error` would teach exactly the wrong lesson - so there is
a sixth verdict, `exploit`, for a line the chart folds and the model prices as
positive. What it may **not** say is what that line would be worth against
somebody else: nothing computed that, and at four to one a call is a profit
against everybody.

**`exploit` reads in both directions, and the order of the checks is what keeps
it honest.** The disagreement is just as real when you *fold* a spot the chart
folds and the model prices as a call - and that case used to come out
`correct`, four lines above the model line saying the call was worth +0.58bb,
the review contradicting itself inside one panel. So a fold is checked for it
too. **The check sits inside the branch where the chart approved**, because an
exploit requires the chart to actually disagree: run any earlier it also
swallowed folds the chart *calls* - JTo in the big blind, which equilibrium
calls 100% of the time - and reported a plain error as a read, with a "but"
joining two clauses that agreed. `EXPLOIT_FLOOR` is the same 0.05bb in both
directions. Against a hero that folds everything, 27% of folds come out
`exploit` and 24% `error`, medians 0.49bb and 0.17bb passed up.

**A bet size can now be priced, and the thing that makes that honest is that
the bots are functions.** `review.py` used to refuse: "a bet cannot be priced
without solving what happens after it". That is still true against equilibrium
and `rollout.py` does not claim otherwise - but `Bot.postflop_action` decides by
rolling `self.rng.random()` against known expressions, so **evaluating those
expressions instead of rolling them gives the exact fold, call and raise
frequency against any size**, hand by hand through the range the bot is on. Run
over each candidate size that gives a curve, and - because calling is selective -
the exact range left *after* a call, which is why a bigger bet shows worse
equity when it gets there. Four things it does not see, all stated on the page:
it stops at showdown on this street, so it understates a small bet that sets up
a bigger one; it assumes the hero best-responds to a raise; it is **heads-up
only**, because two opponents' calling ranges are not independent and there is
no honest product to take; and it is against these five, not against
equilibrium. `SIZING_FLOOR` is 0.25bb before the curve may call a size wrong,
which is deliberately wider than the curve's own precision, because the
one-street horizon biases it in a known direction. **Preflop is refused for a
different reason**: `Bot.preflop_action` never reads a raise size, so the model
cannot tell 2.5bb from 4bb and a curve there would be a flat line pretending to
have an opinion.

**The equity number is now shown taken apart, and the decomposition is the
teaching.** Heads-up, `equity.combo_equities` gives the hero's equity against
each of the opponent's combinations rather than one pooled sample, so the
weighted average can be printed as the sum it is: how many combinations you are
already ahead of and what you are worth against them, how many beat you that you
can still outdraw, how many have you dead. That is exactly the count somebody can
do at the table - 6 combinations to a pair, 4 to a suited hand, 12 to an offsuit
one - which is what makes it worth the screen space. Its arithmetic is printed
with `≈` rather than `=` **on purpose**: every term in it is rounded for
reading and the equity above it is not, so a reader doing the sum lands half a
point away and an equals sign would make the page look like it cannot add up.

**The win rate is mostly noise and the page says so.** Every rate carries a 95%
interval, and the interval is usually embarrassing - which is the point. It is a
*t* interval, not a normal one, because the variance is estimated from the same
few hands the mean is; using 1.96 anyway is 42% too narrow at ten hands. It is
still optimistic, because hand results are a spike at minus one big blind with a
long right tail. Below 25 hands `headline()` refuses to state a rate at all.

## Checking this against somebody else's work

`validate.py` and `/proof` exist because **every test in `tests/` checks this
code against this code**, which catches a regression and cannot catch a mistake
that was there from the first commit: a misread chart, an equity function that
has always been half a percent out.

- The reference is `eval7`, an independent C evaluator, and it is a **test-only
  dependency** - production has no use for a second hand evaluator, so it is in
  `requirements-test.txt` and the suite is gated on a `validation` marker for
  that reason rather than for speed. The whole thing is four seconds.
- **`eval7.py_hand_vs_range_exact` is broken in 0.1.11** - it returns 1.0 for
  every input, AA against KK included - so it is not used. The exact reference
  is an enumeration written in `validate.py` itself, scored by eval7's
  evaluator, sharing no code with `equity.py`. That is stronger than borrowing
  their solver would have been, and it is why there is a check called **"The
  reference itself"**: a hand-written reference can be wrong, so it is measured
  against eval7's own sampler. If that row ever fails, every row under it is
  wrong in the same direction and all of them still say `pass`.
- What it found: hand-versus-hand and per-holding equity agree with an
  independent enumeration **to the last place a float has**, and the evaluator
  orders every one of 20,000 random pairs the way eval7 does, ties included.
  The opening charts are within 2.4 points of the frequencies the solutions they
  claim to be are published at - UTG and HJ are the wide ones, CO and BTN are
  within half a point.
- **The postflop comparison is not written and the page says `not run`.** It
  needs a solver binary this repository does not ship.
  `test_the_postflop_comparison_reports_itself_as_not_run` is there so that the
  day somebody makes that row green they have to come here and say so.
- The page renders `validation.json`, regenerated by
  `tools/validate_report.py`, because the checks need a dependency the box does
  not have and four seconds is not a page load. A stale file cannot turn a
  failing check green: `test_the_committed_report_matches_what_the_checks_say_now`
  runs them live and compares.

## The coach, which is the one thing here that spends money

`coach.py` sends **one decision** to a model and prints what comes back under
the review, behind a button. It is Chinmay's alone and it is off until a key
exists.

**It runs on Gemini's free tier** - `gemini-3.5-flash`, one POST of JSON over
`urllib`, no dependency. There is an Anthropic path behind the same seam
(`provider()` picks whichever key is set, Anthropic winning if both are); it
needs `pip install anthropic`, which the box does not do.

**Flash, not Pro, and not an alias - both of those were tried against the real
API and both fail.** The free tier has *no* Pro quota: every Pro model, and the
`gemini-pro-latest` alias, returns 429 before reading the prompt. And
`gemini-flash-latest` is worse than a pin rather than better, which is the
counter-intuitive half: the aliases track whatever is newest, newest is
busiest, and both it and `gemini-3.7-flash` answer 503 "high demand" on the
same request this model answers. A pin can go stale, but it goes stale
*loudly* - Google's 404 names the model to move to, and `_ask_gemini` passes
that message straight through to the panel rather than flattening it.

**Model names here are not durable and nothing should keep a list of them.**
The name this was first written against was retired between writing it and
running it. That is why `is_free` is a `gemini-` prefix test and not a set: a
stale entry in a set does not fail, it quietly prices a free answer at Opus
rates. `PRICES` holds only the models that actually cost something.

**It is given none of this repo's analysis, and that is the whole design.**
`review.py` has already computed the equity, the pot odds, the range and the
verdict for that spot, and none of it goes in the prompt - what is sent is the
situation only: cards, seats, stacks, blinds, the bounty rules, every action so
far with its size, and each opponent's tendencies. Claude does its own
arithmetic from there.

The trade is worth stating both ways round, because it is the opposite of the
choice every other file here makes:

- What it buys is a **second opinion**. Where the two agree, that is two
  independent readings. Where they disagree, one of them is wrong, and those are
  the spots worth an evening.
- What it costs is **verification**. `validate.py` checks `equity.py` against an
  independent enumeration to the last place a float has. Nothing checks this. An
  equity a model worked out in its head is a sixth kind of number - unchecked -
  and it may **never** be given one of the five labels. **This weighs more on a
  free model than it would on a frontier one**: 2.5 Pro is good and it is still
  doing the sums in its head. Read the disagreements, not the digits. It renders below every
  labelled line, in grey, with a header saying whose numbers they are. If the
  panel ever grows a `solver` or `model` tag, the thing this trainer is for is
  gone. `test_the_prompt_carries_none_of_this_repos_analysis` is the guard on
  the input half of that, because the leak would be silent - the panel would
  fill with plausible prose either way.

**The four guards, and none of them is optional.** This is the only route in the
repo that spends on an outside account, so: an `is_owner` check that **404s**
rather than 403s, because a 403 confirms there is an endpoint here that spends;
one `gto_coach` row per decision ever, so a second click calls nothing; two
daily ceilings checked *before* the call, not after; and a `GET` that never
starts one, so a drawer left open cannot spend. All four are tested in
`tests/test_coach_api.py`, which is the only thing here that boots the app - a
guard that has never been run is a guess.

**The call runs on a thread and the browser polls.** Three sync workers, and a
route that blocks half a minute is a third of the trainer gone while it thinks -
the same reason the bots' pauses are paced out by the browser rather than slept
through on the server. The row is written `pending`, the thread fills it in. A
worker restarted mid-call leaves a `pending` row nothing will finish, which is
what `started_at` and `COACH_STALE` are for.

**Two ceilings, because the scarce thing depends on who answers.** On a paid
provider money runs out and requests never will; on the free tier it is exactly
the other way round. Both are checked, and `usage.free` tells the page which one
to show - "$0.00 of $1.00" to somebody whose real limit is requests per day is a
meter that reassures instead of informing. `GTO_COACH_DAILY_USD` (1.00) and
`GTO_COACH_DAILY_CALLS` (100).

**Cost is in micro-dollars**, not the integer cents money uses everywhere else
here: a paid answer is a few hundredths of a dollar and cents would round most
of them - and a quiet day of them - to zero, which is the one thing a spend
meter may not do. A Gemini answer prices to zero **because this is the free
tier, not because Google is free**; a key on a billed Cloud project costs real
money per token and would be reported here as costing nothing.

`max_tokens` is only a runaway stop on Anthropic, where `effort` is what moves
the bill. **On Gemini it is load-bearing**, and the real numbers say why: a
typical answer here is **123 tokens written against 1,990 spent thinking**.
Flash always thinks, cannot be told not to, and its thinking counts against
`maxOutputTokens` - so a ceiling sized for the visible answer is spent entirely
before a word is written and the response comes back `MAX_TOKENS` with an
*empty* text part. A 200, with usage, and nothing to show. Hence 8000. `_gemini_read` reads for that case by name, because letting it
through prints a blank panel and looks like the button is broken. It is also why
`thoughtsTokenCount` is added to the output count: it is not in
`candidatesTokenCount`, and leaving it out under-reports every answer by most of
what it used.

**It needs `GEMINI_API_KEY` in `gto/.env`, added by hand.** The deploy does not
touch that file. Without any key the button does not render at all - so a page
served to anybody else carries no sign the endpoint exists - and the route says
it is unconfigured rather than half-working. The other knobs, all optional:
`GTO_COACH_PROVIDER` (forces one when both keys are present),
`GTO_COACH_MODEL`, `GTO_COACH_EFFORT` (Anthropic only; `medium`, and `low` is
roughly half the spend), `GTO_COACH_MAX_TOKENS` (8000 on Gemini, 3000 on
Anthropic), `GTO_COACH_DAILY_USD`, `GTO_COACH_DAILY_CALLS`,
`GTO_COACH_TIMEOUT` (120).

**Nothing caches the prompt, on purpose.** The system prompt is well under the
shortest prefix any model will cache, so a breakpoint on it would report zero
reads forever and look broken. `cost_micros` prices the cache fields anyway,
because both providers report them and a longer prompt may one day earn them.

**The prompt names Chinmay's actual friends**, alongside their tendencies and
the blurb describing each of them, and on a free tier that is content the
provider may train on. That is a decision taken with the trade in front of it,
not an oversight: the answers are far more use when they say "Sanjay" than when
they say "the CO". If it is ever revisited, the change is one line in
`_players` - drop `name` and let the positions carry it - and nothing else in
the file needs to know.

**`gto_decisions.context_json` is the only hand-run migration this service has
ever needed**, and `models.ensure_columns` is what runs it - in code, because a
mapped column the live table lacks makes *every* query against `gto_decisions`
fail, so a forgotten ALTER would not be a coach that does not work, it would be
the review and the stats page down. A hand played before that column existed
cannot get one retroactively and the route says so.

## Money, and the two ways it used to be wrong

Integer cents everywhere, as in the engine. Two accounting bugs are worth
knowing about because both produced a *plausible* wrong number:

- **The bounty is settled into `stacks`**, so `stacks - bought_in` includes it.
  The poker win rate must have it subtracted back out or it is measuring a side
  game. `Table._hand_summary` is the single place the two are separated, and
  `stats.py` keeps them apart from there on.
- **`result_cents` is per-hand, not cumulative.** It used to be stored as the
  hero's running profit and differenced on read, which charged the whole of the
  previous session to the first hand of the next one - profit restarts at zero
  at every fresh sit-down.

`sum(stacks) == sum(bought_in)` is an invariant of the whole session: bots
rebuy, and a rebuy that is not recorded in `bought_in` is money created.

`ev_cents` is the same hand with an all-in runout replaced by its equity, paid
out per pot within each pot's own eligible set. It only fires when money went in
with cards still to come - the street of the last action says how much of the
board was out - and is `None` otherwise, because nothing was gambled and the
observed result is already exact.

## Not like the other four services

- **Plain synchronous gunicorn, `-w 3`.** TTR, ERS, KoT and Drive each keep game
  state and socket rooms in process and so are one eventlet worker and can never
  be more. Nothing here is pushed to the browser: you act, the server answers.
  **The whole table lives in the database as JSON**, so any worker can serve any
  request and a deploy does not end anybody's session mid-hand.
- **The bots never sleep on the server.** Think time comes back as a `delay` on
  each event for the browser to pace. A worker held for nine seconds while Bell
  tanks is a worker not serving anybody, and there are three of them.
- **No registration, no login page, no leaderboard.** It signs you in with the
  cookie the rest of cgovind.com already set. That is why it is not in
  `tests/test_no_drift.py`'s `GAMES` - it has no `UserProfile`, no
  `get_effective_name`, no `_player.html` for those checks to compare. It *does*
  carry `visits.py`, byte-identical like the other four, so `VISIT_SERVICES`
  covers it.
- **It has no Elo, and the profile page says so rather than borrowing one.**
  Elo measures you against other people; this is one seat and five bots.
  `accounts/gamestats.py`'s `_gto` returns `elo: None` and a headline of hands
  and bb/100 instead.

## The page, and what it does without asking the server

- **Chips move before the round trip lands.** `applyChips` in `gto.js` does to
  the local state what the engine is about to do to the real one - stack down,
  chips in front, pot up - for the hero the instant they act and for each bot as
  its paced event plays. The server's state overwrites all of it on arrival, so
  a wrong guess lives for one paint and cannot accumulate. **Nothing in there
  may decide anything**: it mirrors an action the server has already been sent,
  it never invents one.
- **A deal is rewound before it is played.** `/api/hand` answers with the table
  *after* every bot up to the hero has acted, so pacing it out over the previous
  hand's table showed a stale felt for as long as the bots took to think.
  `dealt()` reconstructs the moment the cards landed - stack plus what that seat
  has since put in, less its blind - and the events play forward from there. It
  is derived from the answer rather than remembered because the answer is the
  only thing that knows a bot rebought.
- **A seat is rebuilt on every event, so an entrance animation must be earned.**
  `shown`/`shownStack`/`shownCards` exist only to tell a redraw what actually
  changed; without them every card on the table re-deals itself each time
  anybody acts, which reads as a flicker.
- **Once the hero folds, the rest of the hand is rushed.** The server plays the
  whole hand out and answers with every event at once, and the browser used to
  pace all of them at the bot's real think time - so a fold cost a median 10.4s
  and up to 23.4s of watching a pot you are not in (Bell alone tanks for nine
  seconds). `pace()` caps a paced action at `RUSH_MS` once the hero's seat is
  folded, and `drawActions` puts a live **Next hand** button up for the whole
  rush - built enabled rather than through `button`'s `busy`, since the request
  it interrupts is still in flight. Taking it sets `skipRest` and `dealPending`,
  which drain the remaining events at zero delay and deal without opening the
  review drawer just to close it again. **The cap is a ceiling, never a floor**:
  somebody who has already turned the speed slider below it must not find that
  folding made the table slower.
- **The review opens as one row per decision.** Every decision used to print its
  whole ladder - hand, equilibrium, who is in, equity, pot odds, EV, sizing,
  defence - whether or not it was interesting, so three folds in a row were
  three walls of the same arithmetic. Each mark is a `<details>` whose summary
  is what you would sort by: street, what you did, what it cost, the verdict.
  The ladder is unchanged underneath. The provenance `note` on a line is a
  second `<details>` inside that, because the notes are the point of this
  trainer *and* are six sentences about stack depth on a hand that just folded.
- **The bet slider carries chips, not a percentage, and that was a real bug.**
  It used to be a 0-100 range mapped onto `[minimum raise, your whole stack]`,
  which is not a poker size and cannot be made into one: with a 200bb stack the
  100 notches were ~2bb apart, so **2.5bb was not a selectable open**, and the
  hard-coded default of 35 opened for **72bb into a 4bb pot** - $18 at a 25-cent
  blind. The slider is now `min`/`max`/`step` in cents (a quarter blind), the
  pot-fraction chips land on the fraction they name, and `defaultRaiseTo` picks
  the opening number: **2.5bb plus a blind per limper** unopened, **3x the
  current level plus one more per cold caller** facing a raise, and **two thirds
  of the pot** postflop. 2.5bb is not a taste: it is the size every opening
  chart in `ranges.py` is transcribed at, so any other default marks the hero
  against a chart for a raise they did not make.
  - **The limper count excludes the small blind, and that is the equal blinds
    again.** At 0.25/0.25 the SB has already matched the big blind, so
    `committed >= bb` is true of it in a pot nobody has entered - which read as
    one limper and opened every unopened pot to 3.5bb.
  - `dataset.touched` is cleared when the spot changes. It used to persist for
    the life of the page, so one drag pinned *that fraction of min-to-stack* to
    every later decision, which is meaningless across spots.
- **A line may carry a chart, and the line's own text always says the same
  thing.** `Line.chart` is drawn by `chartHtml` - a sizing curve or a bucket
  split - and every number in it is also in the sentence above it, so a chart
  that fails to render cannot take the finding with it. The bucket boxes are
  `flex: <combos> 1 96px`: sized by how many combinations are in each group, but
  never below a width the label fits in, because a bucket holding 11 of 140
  combinations otherwise collapsed to four wrapped lines of unreadable text. The
  chart and the sentence drop an empty group **on the same rule**; kept apart,
  an empty middle bucket vanished from the text and drew a box reading "0
  combinations, 0%".
- **Every keyboard shortcut is a button.** The handler looks the button up by
  `data-key` and clicks it, so a key can never fire an action the table is not
  offering, and the badge on the button cannot drift from the binding. F fold,
  C call (or check, when there is nothing to call), K check, B bet/raise, A and
  1-4 the sizes, N or space to move on, R the review, Escape closes a panel.
  The settings panel takes the keyboard while it is open; the review does not.
- **The deck is drawn by `tools/make_cards.py`**, not downloaded - 52 faces and
  a back at exactly the 240 x 336 the table draws them at. `static/cards/README.md`
  says why the old one went. Do not hand-edit an SVG in there.

## The avatars are the one real hazard

`gto/avatars/` holds photographs of five real, private people. **This repository
is public.** They are gitignored, they must never be committed, and in
production they live at `/home/ubuntu/gto-avatars` - outside the checkout, where
neither a deploy's `git reset --hard` nor a `git clean` can reach them.

`/avatars/<key>` serves them to `GTO_OWNERS` (default `chinmay`) and returns a
**404 to everybody else, not a 403**, because a 403 confirms the file is there.
nginx must not be given a `location /avatars/` alias: that would put them on the
public internet.

## Tests

`scripts/tests.sh gto` - 428 in about 38 seconds, plus three gated suites:

- **`exhaustive`** is the evaluator's proof: all 2,598,960 five-card hands
  scored against an independent sort-and-group implementation *and* every
  textbook category count. ~90s. It is the reason `evaluate()` can be trusted.
- **`calibration`** deals thousands of hands and checks each bot's *measured*
  VPIP and PFR against the numbers written on its profile. A profile saying
  58/31 is a claim; this is the test of it. ~100s.

- **`validation`** is the one described above: `equity.py`, `evaluator.py` and
  `ranges.py` against `eval7` and against published charts. Gated because it
  needs a test-only dependency, not because it is slow.

All three run on `--all` or when the file they cover is dirty. **The runner prints a
line when they are left out**, because a skipped test reads as a pass. The same
CI gap as kot's `strength` marker applies: the check reads the working tree, so
in CI they run only on the manual "every module" dispatch.

`gto` runs **serially**, not under xdist - 47s against 14s on four workers, so
xdist is worth 33s, against ~63s expected cost from the intermittent xdist
deadlock documented in the root `CLAUDE.md`. Same arithmetic as drive, not a
different opinion. If that deadlock is ever fixed, this is the first module to
switch back: the win here is 70% of the runtime.

## Still to do

- **`solver.py` does not exist yet.** Background CFR over heads-up postflop
  subgames, which would replace `heuristic` on the equal-blind small blind and
  give the postflop marks something better than `model`.
- **The review costs about 250ms a hand now and it is on the acting request.**
  `/api/act` computes the marks in the same response that carries the events the
  browser is about to pace out, so the model layer's cost is a delay before the
  first bot moves: measured over 150 hands, a median of 90ms before this work and
  257ms after, with a worst case of 848ms. It is under one bot's think time and
  it is not free. The fix is a second endpoint - `/api/act` answering with the
  events and `/api/review` computing the marks while they play - and the reason
  it is not done yet is that `record_hand` writes the `GtoDecision` rows *from*
  the marks, and the fold rush lets the hero deal the next hand before a second
  request could land.
- **`rollout.py` is heads-up and only when nobody has bet.** Facing a bet, the
  raise sizes could be priced by the same machinery - `response` already handles
  the branch - but the pot geometry is different and it is not written. That is
  36% of postflop decisions covered; the other 64% still read `unpriced`.
- **Postflop ranges are still the preflop range.** `Table.opponent_ranges`
  narrows by preflop action only, so a bot that check-raised the turn is read as
  being on the range it called with. `review.py` labels the limitation; it does
  not fix it.

## Deploy

`deploy/gto.service`, gunicorn on `127.0.0.1:5006`, nginx block at the foot of
`deploy/nginx.conf`. Its `.env` shares TTR's `SECRET_KEY` and points
`DATABASE_URL` at the shared SQLite file, and must set `GTO_AVATAR_DIR` to the
directory outside the checkout. The bring-up is by hand over SSH, like the other
game subdomains - `deploy/setup.sh` only installs the website service.
