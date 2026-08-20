"""The scenery library: eighteen models, dropped in by name and by number.

This is the declarative half of scenery, and the reason it is better than a
hand-written file rather than merely safer is structural. Six live entries in
`docs/track-defects.md` stop being *reachable*:

* geometry that does not move when the road does - there is no way to write a
  world coordinate, every placement is a fraction of the lap;
* a quad wound the wrong way being invisible - nothing here is a quad, `obox` is
  built from `face`, which draws both windings;
* geometry floating in the sky - everything stands on `ground(i, off)`;
* scenery past the edge of the ground - the offset is clamped;
* a `scenery.js` that throws leaving the suite green - data does not throw, and
  an unknown model is refused by name;
* the collider missing on one path - one interpreter, four callers.

That last one is the test that matters most and it is the one run in QuickJS:
`placeAll` lives in `buildTrack`, so a player's barrier is in the collider the
anti-cheat re-drives submitted laps against. If `scenery_kit.js` ever falls out
of `jsrt.bundle`, the bundle still builds, still drives and still returns a
time - having measured the lap on a track with the barriers absent. The symptom
is not an error; it is fast laps sitting in `drive_run_checks` forever.
"""

import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))

JS = os.path.join(HERE, "..", "static", "js")


def _js(name):
    with open(os.path.join(JS, name)) as f:
        return f.read()


def _model_names():
    src = _js("scenery_kit.js")
    body = src[src.index("const MODELS = {"):src.index("\n};", src.index(
        "const MODELS = {"))]
    return re.findall(r"^  ([a-z]+): \{", body, re.M)


MODELS = _model_names()


def test_there_is_a_library_at_all():
    assert len(MODELS) >= 15, MODELS


# ----------------------------------------------------------------- in QuickJS

def _kit_runtime():
    import jsrt
    if not jsrt.HAVE_QUICKJS:
        pytest.skip("needs the optional quickjs package")
    harness = r"""
    var _out = null;
    function _spa() {
      for (var i = 0; i < TRACKS.length; i++)
        if (TRACKS[i].slug === 'spa') return TRACKS[i];
      throw new Error('spa is not in the pool');
    }
    // Every model, one at a time, on a real ribbon, counting what it drew and
    // refusing any collider kind the sandbox would refuse.
    function _drawOne(o) {
      var tris = 0, colTris = 0, kinds = {}, bad = [];
      function chk(p, where) {
        if (!p || p.length < 3 || !isFinite(p[0]) || !isFinite(p[1])
            || !isFinite(p[2])) bad.push(where + ' ' + JSON.stringify(p));
      }
      function Rec() {}
      Rec.prototype.tri = function (a, b, c) {
        chk(a, 'tri'); chk(b, 'tri'); chk(c, 'tri'); tris++;
      };
      Rec.prototype.quad = function (a, b, c, d, k) {
        this.tri(a, b, c, k); this.tri(a, c, d, k);
      };
      Rec.prototype.box = function (cx, cy, cz, hx, hy, hz, k) {
        if (![cx, cy, cz, hx, hy, hz].every(isFinite))
          bad.push('box ' + [cx, cy, cz, hx, hy, hz].join(','));
        for (var f = 0; f < 6; f++) this.quad([0,0,0],[0,0,0],[0,0,0],[0,0,0], k);
      };
      var solid = new Rec(), bright = new Rec();
      var col = { addQuad: function (a, b, c, d, kind) {
        chk(a, 'col'); chk(b, 'col'); chk(c, 'col'); chk(d, 'col');
        kinds[kind] = (kinds[kind] || 0) + 1; colTris += 2;
      } };
      var t = _spa();
      var ctx = sceneryContext(solid, t, t.pal, null, t.ground, 1.2);
      ctx.solid = solid; ctx.bright = bright; ctx.col = col;
      ctx.track = t; ctx.pal = t.pal; ctx.bbox = {x0:-1e3,x1:1e3,z0:-1e3,z1:1e3};
      ctx.KIND = { WALL: 1, OFFROAD: 2 };
      ctx.shade = shade; ctx.mulberry = mulberry;
      var problems = placeAll(ctx, [placementDefaults(o)]);
      _out = JSON.stringify({ tris: tris, col: colTris, kinds: kinds,
                              bad: bad, problems: problems });
    }
    function _drawList(list) {
      var t = _spa();
      var before = buildTrack(t, T).collider.k.length;
      t.placed = list;
      var b = buildTrack(t, T);
      t.placed = null;
      _out = JSON.stringify({ before: before, after: b.collider.k.length,
                              problems: b.sceneryProblems });
    }
    """
    rt = jsrt.Runtime(extra=(harness,))
    rt.load_tuning_and_tracks()
    return rt


@pytest.fixture(scope="module")
def kit():
    return _kit_runtime()


@pytest.mark.parametrize("o", MODELS)
def test_every_model_draws_something_finite(kit, o):
    """A model that draws nothing is a button that does nothing, and a model
    that draws a NaN is a mesh three.js renders black or not at all - neither of
    which reports itself."""
    kit.eval("_drawOne(%s);" % json.dumps(o))
    got = json.loads(kit.call("_out"))
    assert not got["problems"], got["problems"]
    assert not got["bad"], "%s produced points that are not points: %r" % (
        o, got["bad"][:3])
    assert got["tris"] > 0, "%s drew nothing at its own defaults" % o


@pytest.mark.parametrize("o", MODELS)
def test_no_model_emits_a_collider_kind_it_may_not(kit, o):
    """The library is engine code, so nothing forces it to obey the sandbox's
    whitelist - which is exactly why it is asserted. A pad or a drivable surface
    dropped in from a palette would be the same certified speed hack as one
    written in code, arriving by a route nobody was watching."""
    kit.eval("_drawOne(%s);" % json.dumps(o))
    got = json.loads(kit.call("_out"))
    assert set(got["kinds"]) <= {"1", "2"}, (o, got["kinds"])


# The models a lap time can feel. An allowlist and not a count, because the set
# is the claim: anything gaining a collider is a change to how every track using
# it drives, and it has to be a decision rather than a side effect of somebody
# adding a nice-looking barrier.
COLLIDES = {"wall", "tecpro"}


def test_only_the_declared_models_change_lap_times(kit):
    """`wall` and `tecpro` are how a corner stops being cuttable and how a fast
    corner gets an edge you can lean on. A `catchfence` that collided would be a
    wall the author thought was decoration."""
    collide = set()
    for o in MODELS:
        kit.eval("_drawOne(%s);" % json.dumps(o))
        if json.loads(kit.call("_out"))["col"]:
            collide.add(o)
    assert collide == COLLIDES, (
        "the set of models that affect lap times changed: %r" % (collide,))


def test_the_editor_marks_every_solid_model_as_solid(kit):
    """In the library, before it is placed - not discovered afterwards when a
    lap time moves."""
    src = _js("scenery_kit.js")
    declared = set(re.findall(r"^  ([a-z]+): \{[^}]*?collides: true", src,
                              re.M | re.S))
    # The regex above is greedy across models; check each one individually.
    declared = {o for o in MODELS
                if "collides: true" in src[src.index("\n  %s: {" % o):
                                           src.index("\n  },", src.index(
                                               "\n  %s: {" % o))]}
    assert declared == COLLIDES, declared


def test_a_placement_reaches_the_anti_cheats_collider(kit):
    """The whole architecture in one assertion.

    `placeAll` runs inside `buildTrack`, so the placement list rides the track
    dict exactly as the palette does and there is no per-path copy to miss. This
    is measured in the *verifier's own runtime*, because that is the path where
    being wrong is invisible: a bundle without the library still builds, still
    drives and still returns a time.
    """
    kit.eval("_drawList(%s);" % json.dumps(
        [{"o": "wall", "at": 0.60, "to": 0.66, "side": -1, "off": 13, "h": 1.6}]))
    got = json.loads(kit.call("_out"))
    assert not got["problems"], got["problems"]
    assert got["after"] > got["before"], (
        "a placed barrier is not in the collider the anti-cheat measures "
        "against, so it would be invisible to cut_check and to verify.py")


def test_an_invented_model_is_refused_by_name(kit):
    """Not silently skipped. An unknown `o` is a model the author or their AI
    invented, and the answer is its name and the ones that exist."""
    kit.eval("_drawList(%s);" % json.dumps([{"o": "gazebo", "at": 0.3}]))
    got = json.loads(kit.call("_out"))
    assert got["problems"], "an unknown model drew nothing and said nothing"
    assert "gazebo" in got["problems"][0]
    assert "stand" in got["problems"][0], "the message does not list the library"


def test_the_verifier_bundles_the_library():
    """If it ever falls out, laps are re-driven on a track with the player's
    barriers missing from the collider - and nothing fails."""
    import jsrt
    src = jsrt.bundle()
    assert "function placeAll(" in src, (
        "scenery_kit.js is not in the QuickJS bundle")
    assert src.index("function placeAll(") < src.index("function buildTrack("), (
        "the library has to come before trackmesh - its import is stripped, so "
        "the name must already be in scope")


# ------------------------------------------------------------------- the shape

def test_the_placement_list_does_not_collide_with_the_scenery_flag():
    """`track['scenery']` is already a boolean: does this track have a
    `scenery.js` next to it. Putting the list there would be read as
    `true.length` - undefined, falsy - so the scenery would never be drawn and
    nothing would say so."""
    import tracks as tracks_mod
    for t in tracks_mod.TRACKS:
        assert isinstance(t.get("scenery"), bool), t["slug"]
    assert "track.placed" in _js("trackmesh.js")
    assert "track.scenery" not in _js("trackmesh.js")


@pytest.mark.parametrize("o", MODELS)
def test_every_parameter_declares_a_range_its_default_sits_in(o):
    """The range is what the editor's slider offers and what `placeAll` clamps
    to, so a default outside it is a control that moves the moment it is
    touched."""
    src = _js("scenery_kit.js")
    i = src.index("\n  %s: {" % o)
    body = src[i:src.index("\n  },", i)]
    params = re.findall(r"(\w+): \[([-\d., ]+)\]", body)
    assert params, "%s declares no parameters" % o
    for name, nums in params:
        vals = [float(x) for x in nums.split(",")]
        assert len(vals) == 4, "%s.%s is not [min, max, step, default]" % (o, name)
        lo, hi, step, default = vals
        assert lo < hi, (o, name)
        assert step > 0, (o, name)
        assert lo <= default <= hi, (
            "%s.%s defaults to %g, outside %g..%g" % (o, name, default, lo, hi))


def test_the_editor_and_the_spec_are_driven_by_the_catalogue():
    """Neither may carry its own list. A model added to the library has to show
    up in the palette the author browses and in the spec their AI is handed,
    without either being edited."""
    make = _js("make.js")
    assert "catalogue()" in make, "the editor hand-lists the library"
    spec = make[make.index("L.push('## The library');"):
                make.index("L.push('## Worked examples');")]
    assert "for (const k of KIT)" in spec, "the spec hand-lists the library"
    # And the placement path is offered to the model at all.
    assert '"scenery": [{"o": "stand"' in make
