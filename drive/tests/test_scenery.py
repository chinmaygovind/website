"""A track's own mesh code reaches the browser *and* the anti-cheat.

`tracks/<slug>/scenery.js` is how a track ships geometry nothing else needs - the
Costco's walls, its racking, its roof. It is not decoration: `addBuilding` puts
`KIND.WALL` triangles in the collider, so it changes how the car drives.

**Which makes leaving it out of the QuickJS bundle the worst bug available here,
because it is silent.** `verify.py` re-drives a submitted lap through the same
`buildTrack` the browser used. If the bundle is missing the scenery, the server
re-drives the lap on a Costco with no building in it: no error, no exception, a
plausible time, and a verdict about a different track. Per `drive/CLAUDE.md` the
symptom is fast laps waiting in `drive_run_checks` forever.

So this counts collider triangles rather than trusting the loop in
`jsrt.bundle`, and `test_a_bundle_without_the_scenery_is_a_different_track` proves
the count is actually sensitive to the thing it is watching.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import tracks as tracks_mod

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="quickjs is not installed")

TRACKS_DIR = os.path.join(os.path.dirname(__file__), "..", "tracks")

# Collider triangles per track, by surface kind.
#
# Recorded from `git archive HEAD` - the tree *before* the palettes moved to
# Python and before `addBuilding` moved into `tracks/costco/scenery.js` - and every
# one of them matched after. That is what makes this a regression test rather than
# a description: these are the numbers the game had when the laps on the
# leaderboard were driven.
#
# A change here is not automatically wrong, but it is never incidental. If you
# meant it, re-record it in the same commit and say what moved.
EXPECTED = {
    "sunrise":   {"total":    598, "road":   496, "wall":   100, "off":     2, "boost":  0},
    "chicane":   {"total":    534, "road":   432, "wall":   100, "off":     2, "boost":  0},
    "skyline":   {"total":   1620, "road":   500, "wall":  1120, "off":     0, "boost":  0},
    "twist":     {"total":   1876, "road":   592, "wall":  1284, "off":     0, "boost":  0},
    "heights":   {"total":   1680, "road":   520, "wall":  1160, "off":     0, "boost":  0},
    "jumpcity":  {"total":   1638, "road":   506, "wall":  1132, "off":     0, "boost":  0},
    "spiral":    {"total":   1890, "road":   590, "wall":  1300, "off":     0, "boost":  0},
    "eight":     {"total":    592, "road":   490, "wall":   100, "off":     2, "boost":  0},
    "gauntlet":  {"total":   2940, "road":   920, "wall":  2020, "off":     0, "boost":  0},
    "cove":      {"total":   1930, "road":  1542, "wall":   240, "off":   148, "boost":  0},
    "pillars":   {"total":   1878, "road":  1398, "wall":   480, "off":     0, "boost":  0},
    "rainbow":   {"total":  13188, "road": 12608, "wall":   580, "off":     0, "boost":  0},
    "spa":       {"total":  43566, "road":  1810, "wall":  3542, "off": 38214, "boost":  0},
    "costco":    {"total":   4044, "road":  1188, "wall":  2834, "off":     2, "boost": 20},
    "bigred":    {"total":   2848, "road":  1582, "wall":  1188, "off":     0, "boost": 78},
}

COUNTER = """
function tris(slug) {
  var t = TRACKS.filter(function (x) { return x.slug === slug; })[0];
  var b = buildTrack(t, T);
  var k = b.collider.k, out = {total: k.length, road: 0, wall: 0, off: 0, boost: 0};
  for (var i = 0; i < k.length; i++) {
    if (k[i] === KIND.WALL) out.wall++;
    else if (k[i] === KIND.ROAD) out.road++;
    else if (k[i] === KIND.OFFROAD) out.off++;
    else out.boost++;
  }
  return out;
}
"""


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    r.eval(COUNTER)
    return r


def _folders_with_scenery():
    if not os.path.isdir(TRACKS_DIR):
        return []
    return sorted(d for d in os.listdir(TRACKS_DIR)
                  if os.path.exists(os.path.join(TRACKS_DIR, d, "scenery.js")))


def test_there_is_at_least_one_scenery_file():
    """Otherwise every test below passes by having nothing to check.

    Not hypothetical: the hook, the bundling and the inlining are three separate
    mechanisms, and a refactor that dropped the file would leave all of them
    working and all of these green.
    """
    assert _folders_with_scenery(), (
        "no tracks/*/scenery.js at all - if that is deliberate, this whole file "
        "and the hook in trackmesh.js have nothing left to do")


@pytest.mark.parametrize("slug", _folders_with_scenery())
def test_scenery_registers_under_its_own_folder_name(rt, slug):
    """The folder name is the slug, and the registry is keyed by slug.

    A file that registers under the wrong name is the quiet version of not
    registering at all: it loads, it defines its geometry, and `buildTrack` never
    looks it up.
    """
    keys = rt.call("Object.keys(globalThis.DRIVE_SCENERY || {})")
    assert slug in keys, (
        "tracks/%s/scenery.js did not register as %r (registry has %r). It should "
        "set globalThis.DRIVE_SCENERY.%s" % (slug, slug, keys, slug))


@pytest.mark.parametrize("slug", _folders_with_scenery())
def test_the_registered_hooks_are_ones_buildtrack_calls(rt, slug):
    """A hook named something nothing calls does nothing, and says nothing."""
    hooks = rt.call("Object.keys(globalThis.DRIVE_SCENERY[%s])" % json.dumps(slug))
    known = set(rt.call("SCENERY_HOOKS"))
    unknown = sorted(set(hooks) - known)
    assert not unknown, (
        "tracks/%s/scenery.js registers %r, which buildTrack never calls. The "
        "hooks it does call are %r (SCENERY_HOOKS in trackmesh.js)."
        % (slug, unknown, sorted(known)))
    assert hooks, "tracks/%s/scenery.js registers no hooks at all" % slug


def test_the_bundle_carries_every_scenery_file():
    """`verify.py` builds whichever track a lap claims, so all of them ship."""
    b = jsrt.bundle()
    for slug in _folders_with_scenery():
        assert "DRIVE_SCENERY.%s" % slug in b, (
            "tracks/%s/scenery.js is not in jsrt.bundle(). The anti-cheat would "
            "re-drive laps on that track with its scenery missing, and nothing "
            "about that failure is loud." % slug)


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_the_collider_is_the_one_the_leaderboard_was_driven_on(rt, slug):
    got = rt.call("tris(%s)" % json.dumps(slug))
    assert got == EXPECTED[slug], (
        "%s: the collider changed.\n  was %s\n  now %s\nEvery time on this "
        "track's board was driven against the old one. If you meant this, "
        "re-record EXPECTED in the same commit and say what moved."
        % (slug, EXPECTED[slug], got))


def test_a_bundle_without_the_scenery_is_a_different_track():
    """The check above has to be able to fail, so here it is failing.

    Builds the Costco in a runtime whose bundle deliberately omits the scenery -
    which is exactly what a broken `jsrt.bundle` would produce - and asserts the
    collider comes out smaller. Without this, `EXPECTED` could be a table of
    numbers that happens to match a game with no buildings in it.
    """
    ctx = jsrt.quickjs.Context()
    ctx.set_memory_limit(512 * 1024 * 1024)
    ctx.set_time_limit(600)
    # The same bundle, minus the per-track scenery.
    parts = [jsrt._strip_modules(jsrt._read(
                 os.path.join(jsrt.HERE, "three_stub.js")))]
    parts.append("const THREE = {%s};" % ",".join(jsrt._THREE_NAMES))
    parts.append("var globalThis = globalThis || this;")
    for name in ("trackmesh.js", "physics.js", "course.js"):
        parts.append(jsrt._strip_modules(
            jsrt._read(os.path.join(jsrt.JS, name))))
    ctx.eval("\n;\n".join(parts))

    import tuning
    ctx.eval("var T = %s;" % tuning.as_json())
    ctx.eval("var TRACKS = %s;" % json.dumps(tracks_mod.TRACKS))
    ctx.eval(COUNTER)
    got = json.loads(ctx.eval("JSON.stringify(tris('costco'))"))

    assert got["wall"] < EXPECTED["costco"]["wall"], (
        "a bundle with no scenery produced the same %d wall triangles as one "
        "with it, so test_the_collider_is_the_one_the_leaderboard_was_driven_on "
        "is not measuring the building at all" % got["wall"])
    # And say how much of the track it is: the building is most of the Costco's
    # collidable geometry, which is why re-driving a lap without it is not a
    # detail.
    lost = EXPECTED["costco"]["wall"] - got["wall"]
    assert lost > 1000, (
        "only %d wall triangles came from the scenery - either the building "
        "shrank or something else is now supplying it" % lost)


@pytest.mark.parametrize("slug", sorted(EXPECTED))
def test_a_track_that_ships_scenery_says_so(slug):
    """`scenery = True` in `track.py` and the file on disk must agree.

    Both directions. A declaration with no file is a track that silently renders
    without its building; a file with no declaration works today and is a trap
    for the next person, who will read `track.py` and conclude there is none.

    Skipped for tracks still living in `pool.py`, which have no `track.py` to
    declare anything in yet.
    """
    mod = None
    p = os.path.join(TRACKS_DIR, slug, "track.py")
    if not os.path.exists(p):
        pytest.skip("%s has not moved to a folder yet" % slug)
    import importlib
    mod = importlib.import_module("tracks.%s.track" % slug)
    declared = bool(getattr(mod, "scenery", False))
    present = os.path.exists(os.path.join(TRACKS_DIR, slug, "scenery.js"))
    assert declared == present, (
        "tracks/%s: track.py says scenery = %r but scenery.js is %s"
        % (slug, declared, "present" if present else "absent"))
