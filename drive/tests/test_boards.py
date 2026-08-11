"""Spa's sponsor boards, painted for real against a stub canvas.

These are the only textured geometry in the game, and they are the one part of
`trackmesh.js` that **nothing else in the suite can reach**. `buildTrack` guards
the whole sign block with `if (signs.length && typeof document !== 'undefined')`,
which is what lets the anti-cheat run the real file in QuickJS - and it also
means `test_every_track_can_be_built_without_a_browser` walks straight past every
board painter. So the sweep that exists to catch "this reached for a browser API"
cannot see inside the one block that actually uses one.

What that blindness cost, and the reason this file exists: the four non-site
sponsors used to draw their marks as canvas paths, the paths were replaced with
real artwork, the four helpers were deleted - and three call sites were left
calling them. `SPONSORS['PENN ENGINEERING']` threw `ReferenceError: pennShield is
not defined` inside `buildTrack`, which took `boot()` with it, so Spa did not
render a single frame. **The suite was green the whole time.**

Two things are pinned here and they fail in different ways, which is the point:

 * a board that *throws* takes the whole track down, and is loud once you look;
 * a board whose mark is scaled to `NaN` or `0` is silent. You get the layout you
   designed with a hole where the logo goes, on a track whose preview picture is
   taken by a headless browser nobody is watching. That is how `mark`'s six-
   argument call sites survived against its seven-argument signature, with the
   tint landing in `maxH` and every one of the seven logos never drawn.

Run against `jsrt.bundle()` like `test_sound.py` and `test_touch.py`: the real
module, a stub small enough to read, and no browser. `SPONSORS` and `signTexture`
are not exported, but the bundle strips `export` and concatenates, so everything
at the top level of the file is reachable here.
"""

import json
import os
import re
import struct

import pytest

import jsrt

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

SPONSOR_DIR = os.path.join(os.path.dirname(__file__), "..",
                           "static", "img", "sponsors")

# The board canvas, straight out of `signTexture`. 4:1, and the ratio is load
# bearing: the artwork is sized against it.
W, H = 1024, 256


def intrinsic(path):
    """A file's natural size, the way the browser would report it.

    The stub `Image` has to hand `mark` real dimensions or the aspect maths is
    not exercised at all - and a square placeholder would hide exactly the bug
    that a very wide mark (Penn's lockup is 2.9:1) is the one that overflows.
    """
    if path.endswith(".png"):
        with open(path, "rb") as f:
            head = f.read(24)
        return list(struct.unpack(">II", head[16:24]))
    svg = open(path).read(2000)
    box = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', svg)
    if not box:                                        # pragma: no cover
        raise AssertionError("%s has no viewBox" % path)
    return [float(box.group(1)), float(box.group(2))]


# Enough DOM for a board to be painted and inspected, and nothing else. Every
# canvas call is a no-op except `drawImage`, which is recorded - the mark is the
# only thing here that can fail silently, so it is the only thing worth logging.
STUB = r"""
var DRAWN = [];

function Ctx() {
  this.fillStyle = ''; this.strokeStyle = ''; this.lineWidth = 0;
  this.font = ''; this.textAlign = ''; this.textBaseline = '';
  this.globalCompositeOperation = '';
}
Ctx.prototype.save = function () {};
Ctx.prototype.restore = function () {};
Ctx.prototype.beginPath = function () {};
Ctx.prototype.closePath = function () {};
Ctx.prototype.fill = function () {};
Ctx.prototype.stroke = function () {};
Ctx.prototype.moveTo = function () {};
Ctx.prototype.lineTo = function () {};
Ctx.prototype.arc = function () {};
Ctx.prototype.quadraticCurveTo = function () {};
Ctx.prototype.bezierCurveTo = function () {};
Ctx.prototype.fillRect = function () {};
Ctx.prototype.strokeRect = function () {};
Ctx.prototype.clearRect = function () {};
Ctx.prototype.translate = function () {};
Ctx.prototype.rotate = function () {};
Ctx.prototype.scale = function () {};
Ctx.prototype.transform = function () {};
Ctx.prototype.setTransform = function () {};
Ctx.prototype.fillText = function () {};
Ctx.prototype.strokeText = function () {};
Ctx.prototype.clip = function () {};
// A glyph is about half its point size wide, which is close enough for `word`'s
// squeeze to engage on the long names the way it does in a browser.
Ctx.prototype.measureText = function (s) {
  var px = parseFloat((this.font.match(/([\d.]+)px/) || [0, 16])[1]);
  return { width: s.length * px * 0.55 };
};
Ctx.prototype.drawImage = function (im) {
  var a = Array.prototype.slice.call(arguments, 1);
  DRAWN.push({ src: (im && im.src) || null, args: a });
};

function Canvas() { this.width = 0; this.height = 0; }
Canvas.prototype.getContext = function () { return new Ctx(); };

// Loaded the instant it is asked for. `mark` bails on `!im.complete`, so an
// Image that never loads would make every assertion below vacuously pass.
function Image() { this.complete = true; this.onload = null; this.onerror = null; }
Object.defineProperty(Image.prototype, 'src', {
  get: function () { return this._src; },
  set: function (v) {
    this._src = v;
    var n = NATURAL[v];
    if (!n) throw new Error('no artwork registered for ' + v);
    this.naturalWidth = n[0];
    this.naturalHeight = n[1];
  },
});

var document = {
  createElement: function () { return new Canvas(); },
  fonts: { load: function () { return Promise.resolve(); } },
};

/** Paint one board and hand back what it drew. */
function paint(name) {
  DRAWN = [];
  var g = new Ctx();
  var f = SPONSORS[name];
  if (!f) throw new Error('no such sponsor: ' + name);
  f(g, BW, BH);
  return DRAWN;
}
"""


@pytest.fixture(scope="module")
def rt():
    """A runtime with the real module, a stub DOM and the real artwork sizes."""
    r = jsrt.Runtime()
    natural = {}
    for name in sorted(os.listdir(SPONSOR_DIR)):
        if name.startswith("."):
            continue
        natural["/static/img/sponsors/" + name] = intrinsic(
            os.path.join(SPONSOR_DIR, name))
    r.eval("var NATURAL = %s;" % json.dumps(natural))
    r.eval("var BW = %d, BH = %d;" % (W, H))
    r.eval(STUB)
    return r


def names(rt):
    return rt.call("Object.keys(SPONSORS)")


# ---------------------------------------------------------------------------
# The loud half: a board that throws takes the track with it
# ---------------------------------------------------------------------------

def test_every_sponsor_board_paints(rt):
    """No board may throw, because one that does costs the whole track.

    `signTexture` is called from `buildTrack`, which is called from `boot`, so
    there is nothing between a bad board and a page that never renders. This is
    the test that fails with `ReferenceError: pennShield is not defined`.
    """
    broken = []
    for name in names(rt):
        try:
            rt.eval("paint(%s)" % json.dumps(name))
        except Exception as e:                          # noqa: BLE001
            broken.append("%s: %s" % (name, e))
    assert not broken, "these boards throw, and each one is a dead track:\n" + \
        "\n".join(broken)


def test_the_fallback_board_paints_too(rt):
    """A name with no `SPONSORS` entry has to degrade, not explode."""
    rt.eval("signTexture('NOT A SPONSOR')")


# ---------------------------------------------------------------------------
# The silent half: a mark scaled to nothing
# ---------------------------------------------------------------------------

def test_every_logo_is_actually_drawn(rt):
    """A mark drawn at `NaN` or zero size is invisible and says nothing.

    `mark` fits artwork into a box, so a wrong argument does not throw - it
    computes a scale of `NaN` (a tint landing in `maxH`) or `0` (a `null`
    landing there) and hands `drawImage` a degenerate rectangle. The board still
    paints, the layout is still right, and the logo simply is not there.

    So every `drawImage` on a board has to be checked for a real destination
    rectangle. It is the last two arguments in both forms this file uses - the
    5-argument one for a whole mark and the 9-argument one for a lockup drawn a
    part at a time.
    """
    bad = []
    for name in names(rt):
        for call in rt.call("paint(%s)" % json.dumps(name)):
            args = call["args"]
            assert len(args) in (4, 8), \
                "%s: drawImage should be the 5- or 9-arg form, got %d args" % (
                    name, len(args) + 1)
            w, h = args[-2], args[-1]
            for label, v in (("w", w), ("h", h)):
                if not isinstance(v, (int, float)) or v != v or v <= 0:
                    bad.append("%s -> %s: %s=%r" % (name, call["src"], label, v))
    assert not bad, (
        "these marks are scaled to nothing, so the board paints without them:\n"
        + "\n".join(bad))


def test_a_marked_board_draws_its_mark(rt):
    """At least one board has to actually put artwork down.

    Without this the test above passes on a file where every `mark` call was
    deleted: no `drawImage`, no bad rectangle, nothing to complain about.
    """
    total = sum(len(rt.call("paint(%s)" % json.dumps(n))) for n in names(rt))
    assert total >= 4, "only %d marks drawn across every board" % total


# ---------------------------------------------------------------------------
# The board list and the files behind it
# ---------------------------------------------------------------------------

def test_every_logo_file_exists(rt):
    """`LOGOS` points at the static tree, and a 404 there is a silent gap."""
    missing = [(k, p) for k, p in rt.call("LOGOS").items()
               if not os.path.exists(os.path.join(
                   SPONSOR_DIR, os.path.basename(p)))]
    assert not missing, "LOGOS points at files that are not there: %r" % missing


def test_every_board_on_the_circuit_has_a_sponsor(rt):
    """A name in the palette with no painter falls back to a plain red board.

    That is a deliberate fallback rather than a crash, which is right - and it
    means a typo in the palette ships as a board that looks like a placeholder
    and nothing says so.
    """
    # Read from Python, because that is where a palette lives now. It used to be
    # `PALETTES.spa.furniture.sponsors` inside trackmesh.js; the object is gone
    # and the sponsors list is the same list in `tracks/<slug>/palette.py`.
    import tracks as tracks_mod
    listed = tracks_mod.get("spa")["pal"]["furniture"]["sponsors"]
    unknown = sorted(set(listed) - set(names(rt)))
    assert not unknown, "no SPONSORS entry for %r" % unknown


def test_every_board_font_is_self_hosted(rt):
    """`BOARD_FONTS` is the only reason these faces are ever downloaded.

    Nothing on any page is *set* in them, so a `@font-face` nobody asks for by
    name is never fetched - `document.fonts.ready` resolves happily having
    loaded nothing. A face used by a board and missing from this list renders in
    whatever the machine had lying around, and the screenshot box has almost
    nothing.
    """
    css = open(os.path.join(os.path.dirname(__file__), "..",
                            "static", "css", "style.css")).read()
    declared = set(re.findall(r'font-family:\s*"?([^";]+)"?;', css))
    for spec in rt.call("BOARD_FONTS"):
        fam = re.sub(r'^.*?\d+px\s+', '', spec).strip('"\' ')
        assert fam in declared, \
            "%s is asked for by a board but not @font-face'd in style.css" % fam
