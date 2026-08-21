"""The first visit: the goal line, and the four coach marks over the first result.

A stranger who lands on Sunrise is told which key makes the car move and nothing
else. They are not told that the clock is the game, and they are not told that
the four 38px icons in the corner are the leaderboard, the other fourteen tracks,
the controls and the settings - which is most of what there is here.

So: a banner on the first visit, and arrows over the first results sheet. Both
are once-ever and both are easy to get wrong in ways that are invisible from
inside the browser you developed them in, because **you only get to be a new
player once**. That is what this file is for.

The three failures it exists to catch:

* **The marks in the checked-in pictures.** `tools/shoot_tracks.py` photographs
  every track through the real page, and `?panel=finish` exists so a screenshot
  can reach the results sheet. Either would have come back with the onboarding
  painted over it, and the previews are committed, so it would have shipped.
* **A tour that cannot be seen over its own scrim.** The results overlay is a
  z-index 60 sheet over a dark blur, and `.hud` is `position: fixed`, which makes
  it a stacking context - so the buttons being pointed at are capped underneath
  it however high a z-index they are given. It has to be `.hud` that lifts.
* **A lifted HUD that eats the click.** `.hud-tr` is a tall transparent column;
  raised over the sheet it sits in front of Retry.

There is no browser in CI, so most of this is read off the source. Where that is
a real limitation it is said so rather than papered over - the geometry of the
arrows was checked with `?tour=1` and a camera, which is what that parameter is
for.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from conftest import boot_app, close_app        # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.dirname(HERE)


@pytest.fixture()
def env():
    A, path = boot_app(verify="0")
    yield A
    close_app(path, verify="0")


def _read(*parts):
    with open(os.path.join(DRIVE, *parts), encoding="utf-8") as f:
        return f.read()


def _fn(src, name):
    """The body of a top-level `function name(...)`, to the closing brace.

    Braces are counted rather than matched on a regular expression, because
    every function here has objects and template strings in it and the first
    `\n}` is several lines early.
    """
    start = src.index("function %s(" % name)
    depth, i = 0, src.index("{", start)
    while True:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1


def _z(selector):
    """The z-index on the rule whose head matches `selector`.

    A named failure and not an `AttributeError`: the interesting way for this to
    break is the rule having been moved or renamed, and `NoneType has no attribute
    group` says nothing about which rule went missing.
    """
    m = re.search(selector + r"[^}]*z-index: (\d+)", CSS, re.M)
    assert m, "no z-index on a rule matching %s" % selector
    return int(m.group(1))


def _tip_ids():
    """The button ids `TOUR_TIPS` names, in the order it names them."""
    block = GAME[GAME.index("const TOUR_TIPS"):]
    return re.findall(r"\['(btn\w+)',", block[:block.index("];")])


GAME = _read("static", "js", "game.js")
CSS = _read("static", "css", "style.css")
PLAY = _read("templates", "play.html")


# --- it is there at all ----------------------------------------------------

def test_the_goal_banner_and_the_tour_layer_are_on_the_play_page(env):
    """Both boxes ship with the page, empty and hidden."""
    r = env.app.test_client().get("/solo/sunrise")
    body = r.get_data(as_text=True)
    assert 'id="firstBanner"' in body
    assert "Try to set your best time on this track!" in body
    assert 'id="tour"' in body
    # Hidden until asked for. A banner that is in the flow at load and then
    # hidden by script is a banner that flashes on every visit for everybody.
    assert re.search(r'id="firstBanner"[^>]*style="display:none"', body)
    assert re.search(r'id="tour"[^>]*style="display:none"', body)


def test_the_tour_layer_is_not_inside_the_hud(env):
    """Same trap the framed door fell into, and the same fix.

    `.hud` is `position: fixed`, which makes it a stacking context, so anything
    inside it is painted below the results overlay whatever z-index it asks for.
    The layer has to be a sibling of the overlay, not a descendant of the HUD.
    """
    body = env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    hud = body.index('<div class="hud">')
    # `</div>` closing the hud is not findable by string search, so measure
    # against something known to be the first thing *after* it: the aside/overlay
    # run at the foot of the page, of which the rotate notice is one.
    rotate = body.index('id="rotate"')
    tour = body.index('id="tour"')
    banner = body.index('id="firstBanner"')
    assert hud < banner < rotate, "the banner belongs in the HUD"
    assert tour > rotate, "the tour layer must be outside the HUD"


def test_the_marks_are_pointed_at_buttons_that_exist(env):
    """Four ids, and solo really does render all four.

    The room shows a people button where solo shows a podium, so `btnBoard` is
    not on every play page - `startTour` skips a tip whose button is missing,
    and this is the other half of that: on the page it actually runs on, none of
    them are missing.
    """
    body = env.app.test_client().get("/solo/sunrise").get_data(as_text=True)
    ids = _tip_ids()
    assert len(ids) == 4
    for i in ids:
        assert 'id="%s"' % i in body, i


# --- once, and only for a new player ---------------------------------------

def test_both_are_remembered_forever_rather_than_for_the_session(env):
    """`localStorage`, unlike the start hint's `sessionStorage`.

    A reload is a fresh pair of hands on the keys and worth telling which key
    drives; being told what a leaderboard is twice is being talked down to.
    """
    first = _fn(GAME, "firstTime")
    assert "localStorage" in first and "sessionStorage" not in first
    assert "setItem" in first, "reading the flag without writing it shows it forever"


def test_a_browser_that_cannot_remember_is_shown_neither(env):
    """The `catch` returns false, not true.

    Private browsing and a locked-down school profile both throw on
    `localStorage`. Returning true there would put the banner and the four marks
    in front of the same person on every single load - which is the one outcome
    worse than never showing them.
    """
    first = _fn(GAME, "firstTime")
    tail = first[first.index("catch"):]
    assert re.search(r"return false;", tail), tail


def test_the_goal_line_is_only_on_the_track_a_first_visit_lands_on(env):
    """Sunrise, and the app agrees that is where `/solo` sends a new player."""
    import tracks as T
    assert T.TRACKS[0]["slug"] == "sunrise"
    assert "'sunrise'" in _fn(GAME, "showFirstGoal")


def test_neither_fires_in_a_room_or_a_replay(env):
    """A race is somebody else's time and nobody is waiting to be taught."""
    for name in ("showFirstGoal", "startTour"):
        assert "CFG.mode !== 'solo'" in _fn(GAME, name), name


# --- the thing that would have shipped -------------------------------------

def test_the_onboarding_stays_out_of_every_photograph(env):
    """`?shot=` and `?panel=` are cameras, and their output is committed.

    `tools/shoot_tracks.py` drives the real page to make the switcher's previews
    and the share cards, and `?panel=finish` is how the results sheet is reached
    without driving. Nothing detects a stale or spoiled preview, so a banner in
    one of them is a banner that ships.
    """
    photo = _fn(GAME, "beingPhotographed")
    assert "shot" in photo and "panel" in photo
    for name in ("showFirstGoal", "startTour"):
        body = _fn(GAME, name)
        assert "beingPhotographed()" in body, name


def test_looking_at_it_does_not_spend_a_real_first_visit(env):
    """`?tour=1` forces both on without writing the seen flag.

    Otherwise the only way to see either is to clear site data and drive a lap,
    which is a thing you have to remember to do and therefore a thing that stops
    being done. The guard has to be shaped so that the forced path skips
    `firstTime` rather than calling it - calling it and ignoring the answer would
    still burn the flag.
    """
    assert "tour=1" in _fn(GAME, "tourForced")
    for name in ("showFirstGoal", "startTour"):
        body = _fn(GAME, name)
        assert "tourForced()" in body, name
        # Every mention of the flag is behind `forced`, wherever in the function
        # it happens to sit - the goal line spends its own inside the door's
        # callback, several lines below the guard that decides.
        for call in re.findall(r".*firstTime\(.*", body):
            assert "!forced" in call, "%s: unguarded %s" % (name, call.strip())


# --- the stacking context and the click ------------------------------------

def test_the_buttons_are_lifted_by_the_hud_and_not_by_themselves(env):
    """`.hud` is the stacking context, so `.hud` is what has to move.

    `body.tour .hud-tr { z-index }` reads like the obvious fix and does nothing
    at all: the parent is `position: fixed`, which caps every z-index inside it.
    """
    lifted = _z(r"body\.tour \.hud \{")
    overlay = _z(r"^\.overlay \{")
    assert lifted > overlay, "%d is not over the results sheet at %d" % (lifted, overlay)
    assert not re.search(r"body\.tour \.hud-tr \{[^}]*z-index", CSS), \
        "a z-index on .hud-tr is capped by .hud and does nothing"


def test_the_labels_are_drawn_over_the_lifted_buttons(env):
    assert _z(r"^#tour \{") > _z(r"body\.tour \.hud \{")


def test_the_rest_of_the_lifted_hud_stops_taking_clicks(env):
    """Two boxes, both invisible and both in front of the Retry button.

    `.hud-bc` is the clock, 340px wide across the bottom centre; `.hud-tr` is a
    tall transparent column down the right. Fading them to `opacity: 0` leaves
    both hit-testable, and once the HUD is above the sheet they are the things a
    click lands on.
    """
    rule = re.search(
        r"body\.tour \.hud > \*:not\(\.hud-tr\),\s*"
        r"body\.tour \.hud-tr > \*:not\(\.btnbar\) \{([^}]*)\}", CSS)
    assert rule, "the fade rule is not where this test can read it"
    assert "opacity: 0" in rule.group(1)
    assert "pointer-events: none" in rule.group(1)
    assert re.search(r"body\.tour \.hud-tr \{[^}]*pointer-events: none", CSS)
    assert re.search(r"body\.tour \.hud-tr \.btnbar \{[^}]*pointer-events: auto", CSS)
    assert re.search(r"^#tour \{[^}]*pointer-events: none", CSS, re.M), \
        "the label layer would block the buttons it is pointing at"


def test_the_medal_table_is_faded_with_everything_else(env):
    """It lives inside `.hud-tr`, which is the box being kept lit.

    A `:not(.hud-tr)` on its own leaves the whole right-hand column at full
    brightness, and the medal times then sit underneath the four labels. This is
    the second selector, and it is the reason there are two.
    """
    assert "body.tour .hud-tr > *:not(.btnbar)" in CSS
    assert 'class="card medals" id="medalsCard"' in PLAY


# --- taking it down again --------------------------------------------------

def test_the_class_comes_off_before_the_button_opens_anything(env):
    """Order, inside `endTour`.

    The click that ends the tour is usually the click that opens a panel. If the
    HUD is still lifted when that panel arrives at z-index 60, the button bar
    floats on top of the sheet it just opened.
    """
    body = _fn(GAME, "endTour")
    assert body.index("classList.remove('tour')") < body.index("layer.style.display")


def test_there_are_three_ways_out_and_they_all_reach_endTour(env):
    """A click, a key, and a clock. None of them may be the only one.

    A tour with no timer is a tour that stays up forever on a device with no
    keyboard and a player who is reading; a tour with only a timer cannot be
    dismissed by somebody who has finished reading in two seconds.
    """
    body = _fn(GAME, "startTour")
    assert "addEventListener('click', endTour, true)" in body
    assert "addEventListener('keydown', endTour, true)" in body
    assert "setTimeout(endTour" in body
    # And the sheet closing takes it down too, since the marks point at buttons
    # the sheet is what lit up.
    assert "endTour();" in _fn(GAME, "hideResults")


def test_the_dismiss_listeners_are_armed_late(env):
    """The sheet appears the instant the car crosses the line.

    A finger already on its way down to Retry would otherwise dismiss four
    labels before anybody had a chance to read one.
    """
    body = _fn(GAME, "startTour")
    arm = body.index("addEventListener('click', endTour")
    delay = re.search(r"setTimeout\(\(\) => \{.*?\}, (\d+)\);", body[:arm + 400], re.S)
    assert delay and int(delay.group(1)) >= 400, "listeners armed too early"


def test_everything_it_added_is_removed_again(env):
    """The resize listener especially: it is the one that is not on `document`.

    A tour that leaves `placeTour` bound keeps measuring four buttons for tips
    that no longer exist, for the rest of the session, on every resize.
    """
    body = _fn(GAME, "endTour")
    for line in ("removeEventListener('click', endTour, true)",
                 "removeEventListener('keydown', endTour, true)",
                 "removeEventListener('resize', placeTour)",
                 "clearTimeout(S.tourTimer)"):
        assert line in body, line


# --- the geometry ----------------------------------------------------------

def test_every_tip_is_measured_off_its_own_button(env):
    """Not off a corner offset.

    The bar moves with the safe area, with the mode, and with the room drawer
    sliding it sideways, so a hardcoded position is wrong on a phone, in a room
    and mid-animation. It is also the only reason the marks survive somebody
    adding a fifth button.
    """
    body = _fn(GAME, "placeTour")
    assert "getBoundingClientRect()" in body
    assert "t.btn" in body


def test_the_arrows_are_drawn_in_real_pixels(env):
    """A viewBox that matches the pixel size, not a fixed one scaled to fit.

    The four boxes are anything from 37x26 to 170x116. Stretching one viewBox
    across all of them gives four arrowheads of four different shapes and four
    strokes of four different weights.
    """
    body = _fn(GAME, "placeTour")
    assert "`0 0 ${w} ${h}`" in body
    assert "setAttribute('width', w)" in body and "setAttribute('height', h)" in body


def test_the_tips_run_left_to_right(env):
    """The order is load-bearing rather than cosmetic.

    Each arrow runs along its own line and then turns up, so arrow *k* passes
    under every upright standing to its left. Pairing the leftmost button with
    the topmost - and so the shortest - label makes every one of those uprights
    end above the line it would have crossed. Reversed, the four tangle.
    """
    assert _tip_ids() == ["btnBoard", "btnTracks", "btnHelp", "btnSettings"]


def test_the_results_sheet_steps_aside_on_a_small_screen(env):
    """812px of phone against a 460px sheet leaves no column beside it.

    Without this the labels land on the player's own lap time, which is the one
    number they just earned. Desktop is untouched: there is a whole screen of
    scrim between the two there and moving anything would be fidgeting.
    """
    m = re.search(r"@media \(max-width: 900px\) \{(.*?)\n\}", CSS, re.S)
    assert m and "body.tour .sheet.result" in m.group(1)
    assert "translateX" in m.group(1)
    assert "transition: transform" in CSS[CSS.index(".sheet.result"):][:120]


# --- the door --------------------------------------------------------------

def test_the_banner_waits_for_the_framed_door(env):
    """Inside a portal the game opens behind an opaque card.

    It stays up until the renderer is warm, which is as much as eight seconds -
    so a banner shown at boot spends its whole life behind it and is gone before
    the road is visible. Every player arriving through CrazyGames is in exactly
    that case, which makes it the path that matters most rather than an edge one.
    """
    assert "whenPlayable(" in _fn(GAME, "showFirstGoal")
    body = _fn(GAME, "whenPlayable")
    assert "framed" in body and "frameStart" in body
    assert "clearInterval" in body, "a poll that never stops is a leak"
