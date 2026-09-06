"""One panel in front of you, whichever way you opened it.

Settings, the controls sheet, the leaderboard and the track switcher are four
overlays over the same road, and there is no arrangement of two of them that
reads as anything but a mistake. They used to know about each other **in pairs**,
and only in the pairs somebody had happened to hit: settings closed controls,
controls closed settings, the board closed settings. Nothing closed the switcher
and the switcher closed nothing. So `P` over the board, or `L` over the controls
sheet, put two sheets up and left the one underneath to reappear when the top one
was dismissed - which reads as the game having lost track of what you pressed.

Driven rather than read. This lifts the four toggles and `closeOtherPanels` out
of `game.js` by name and runs them against a DOM stub, the same technique
`test_touch.py` uses on the input bindings, because "opening B closed A" is a
statement about what the code *does* and a source-reading test of it would be
pinning the current spelling of the fix instead.

The parametrised sweep is the point of the file: every ordered pair of panels, so
a new one added without a line in `closeOtherPanels` fails many times over rather
than passing quietly. **That is not hypothetical - it is what happened when the
save states panel landed**, which is why there are five here now: the code got its
line and this file did not, and thirty tests said so.
"""

import os
import re

import pytest

from jsrt import HAVE_QUICKJS, JS

pytestmark = pytest.mark.skipif(not HAVE_QUICKJS, reason="quickjs not installed")

PANELS = ("menu", "help", "board", "tracks", "saves")


def _fn(src, name):
    """One top-level `function name(...)`, to its column-0 closing brace.

    Every function in `game.js` closes in column 0, so this needs no brace
    matching - the same shortcut `test_touch.py` takes.
    """
    start = src.index("function %s(" % name)
    return src[start:re.compile(r"^\}$", re.M).search(src, start).end()]


def _toggles():
    src = open(os.path.join(JS, "game.js")).read()
    return "\n".join(_fn(src, n) for n in
                     ("closeOtherPanels", "toggleMenu", "toggleHelp",
                      "toggleBoard", "toggleTracks", "toggleSaves"))


# Enough DOM for four overlays and the buttons that light up with them.
STUB = r"""
var els = {};
function El(id) {
  this.id = id; this.cls = {}; this.style = {};
  this.textContent = ''; this.innerHTML = '';
  this.classList = {
    add: (c) => this.cls[c] = 1,
    remove: (c) => delete this.cls[c],
    toggle: (c, v) => { if (v) this.cls[c] = 1; else delete this.cls[c]; },
    contains: (c) => !!this.cls[c],
  };
}
function $(id) { if (!els[id]) els[id] = new El(id); return els[id]; }
// The two overlays are `style="display:none"` in the template, and the toggles
// read that string to decide which way they are going. Starting them undefined
// would make the first press of either a *close*.
$('boardOv').style.display = 'none';
$('tracksOv').style.display = 'none';
$('savesOv').style.display = 'none';
var S = { menuOpen: false, helpOpen: false, isHost: true,
          track: { name: 'Sunrise Circuit', slug: 'sunrise' } };
var CFG = { mode: 'solo' };
// Everything the four reach for that is not the opening and closing itself.
// A new one appearing throws here rather than quietly testing nothing.
var SYNCS = 0;
function syncPaused() { SYNCS++; }
function markActiveTrack() {}
function renderSaves() {}
// The save-states panel says what a save state is on its first open. It is not
// what this file is about, and it reaches for `localStorage`.
function showSavesIntro() {}
"""

HARNESS = r"""
function open_(p) {
  if (p === 'menu') toggleMenu(true);
  else if (p === 'help') toggleHelp(true);
  else if (p === 'board') toggleBoard(true);
  else if (p === 'tracks') toggleTracks(true);
  else if (p === 'saves') toggleSaves(true);
  else throw new Error('no panel ' + p);
}
function toggle_(p) {
  if (p === 'menu') toggleMenu();
  else if (p === 'help') toggleHelp();
  else if (p === 'board') toggleBoard();
  else if (p === 'tracks') toggleTracks();
  else if (p === 'saves') toggleSaves();
}
function isOpen(p) {
  if (p === 'menu') return !!S.menuOpen;
  if (p === 'help') return !!S.helpOpen;
  if (p === 'board') return $('boardOv').style.display !== 'none';
  if (p === 'tracks') return $('tracksOv').style.display !== 'none';
  if (p === 'saves') return $('savesOv').style.display !== 'none';
}
/* Every panel currently up, as a sorted comma-joined string, so a failure names
   what was on screen instead of saying False is not True. */
function upNow() {
  return ['board', 'help', 'menu', 'saves', 'tracks'].filter(isOpen).join(',');
}
"""


def run(script):
    import quickjs
    return quickjs.Context().eval(STUB + _toggles() + HARNESS + script)


@pytest.mark.parametrize("first", PANELS)
@pytest.mark.parametrize("second", PANELS)
def test_opening_one_panel_closes_whatever_was_in_front(first, second):
    """The whole file in one assertion, run over all sixteen ordered pairs.

    The four same-panel cases are in here on purpose rather than excluded: they
    are the check that `closeOtherPanels` does not close the panel that is
    opening, which is the obvious way to write this wrong.
    """
    up = run("open_('%s'); open_('%s'); upNow();" % (first, second))
    assert up == second, (
        "opened %s over %s and the screen has %r on it" % (second, first, up))


@pytest.mark.parametrize("p", PANELS)
def test_a_panel_still_toggles_itself_shut(p):
    """Exclusion must not cost the four keys their second press.

    `H`, `P`, `L` and Escape all close the sheet they opened, and the fix reaches
    into exactly the code path that does it.
    """
    assert run("toggle_('%s'); toggle_('%s'); upNow();" % (p, p)) == ""


@pytest.mark.parametrize("p", PANELS)
def test_closing_a_panel_opens_nothing(p):
    """Closing must not re-enter the exclusion.

    `closeOtherPanels` closes by calling the other toggles, so a version that ran
    on the way *shut* as well would recurse - and the shape that does not crash
    is the one that quietly reopens something.
    """
    assert run("open_('%s'); toggle_('%s'); upNow();" % (p, p)) == ""


def test_the_switcher_is_not_the_odd_one_out_any_more():
    """It was: nothing closed it and it closed nothing.

    Named separately from the sweep because it is the specific complaint - `P`
    over an open board, and both are on the screen.
    """
    assert run("open_('board'); open_('tracks'); upNow();") == "tracks"
    assert run("open_('tracks'); open_('board'); upNow();") == "board"


def test_settings_is_left_out_of_the_way_when_it_opens_the_board():
    """The View Others chip lives *inside* settings and opens the board.

    It is the one path where the panel being replaced is the one the press came
    from, and it went through `openBoard`'s own hand-wired `toggleMenu(false)` -
    the single pair anybody had got round to writing.
    """
    assert run("open_('menu'); open_('board'); upNow();") == "board"


@pytest.mark.parametrize("p", PANELS)
def test_the_pause_state_is_recomputed_every_time(p):
    """`syncPaused` is the one place that decides both `S.paused` and whether a
    portal is told the player is playing. Every open and every close has to
    reach it, or the game stays paused behind a panel that is no longer up."""
    assert run("var a = SYNCS; open_('%s'); SYNCS > a;" % p) is True
    assert run("open_('%s'); var a = SYNCS; toggle_('%s'); SYNCS > a;" % (p, p)) is True
