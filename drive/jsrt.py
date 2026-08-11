"""Run the game's own JavaScript from Python, with no browser.

The car, the collider and the course logic are the parts of this project most
likely to break, and they all live in .js because they have to run in the
browser. Rather than reimplement them in Python for testing (which would test
the copy, not the game), this bundles the real modules into one script and runs
it in QuickJS.

**It lives beside the app rather than under `tests/`, because `verify.py` runs
it in production.** The server re-drives a submitted lap through the same
`Car.step` the browser used, and the only way to do that without a second copy
of the physics in Python is to run the real file. Everything here was written
for the tests and none of it changed when the verifier started using it: a
Python port of the car would be a thing that could disagree with the game, which
is precisely what an anti-cheat must not have.

ES module `import`/`export` statements are stripped and the files concatenated in
dependency order, which works because the modules only import from each other and
from three.js - and three.js is swapped for `three_stub.js`, which provides real
Vector3/Quaternion maths and inert shells for anything graphical.

QuickJS comes from the optional `quickjs` pip package. If it is not installed the
tests that need it skip rather than fail, so `pip install -r requirements.txt`
stays enough to deploy.
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, "static", "js")

try:
    import quickjs
    HAVE_QUICKJS = True
except ImportError:                                   # pragma: no cover
    quickjs = None
    HAVE_QUICKJS = False

# The namespace `import * as THREE` would have provided.
_THREE_NAMES = [
    "Vector3", "Quaternion", "Group", "Mesh", "BufferGeometry",
    "Float32BufferAttribute", "Color", "MeshLambertMaterial", "MeshBasicMaterial",
    "MeshPhongMaterial",
    "SpriteMaterial", "Sprite", "CanvasTexture", "BoxGeometry", "CylinderGeometry",
    "ConeGeometry", "CircleGeometry", "PlaneGeometry", "SphereGeometry", "Fog",
    "Scene", "PerspectiveCamera", "WebGLRenderer", "DirectionalLight",
    "HemisphereLight", "AdditiveBlending", "DoubleSide", "BackSide",
]


def _strip_modules(src):
    """Remove import statements and the `export` keyword."""
    src = re.sub(r'^\s*import\s+[^;]*;\s*$', '', src, flags=re.M)
    src = re.sub(r'^export\s+', '', src, flags=re.M)
    return src


def _read(path):
    with open(path) as f:
        return f.read()


def bundle(extra=()):
    """The whole simulation as one script, ready to eval.

    **Every track's `scenery.js` is in here, and leaving one out is silent.**
    `verify.py` calls `buildTrack` to re-drive a submitted lap, so a track whose
    scenery adds collidable geometry - the Costco's walls and racking - has that
    geometry in the collider the anti-cheat measures against. A bundle without it
    still builds, still drives and still returns a time; it just re-drives the lap
    on a Costco with no building in it. The symptom is not an error, it is fast
    laps waiting in `drive_run_checks` forever, so `tests/test_scenery.py` counts
    collider triangles on both sides rather than trusting this loop.

    They go in *after* trackmesh.js and register on a global, which is the same
    shape the browser uses - a classic inline script above a deferred module. So
    there is one contract and it is exercised by both.
    """
    parts = [_strip_modules(_read(os.path.join(HERE, "three_stub.js")))]
    parts.append("const THREE = {%s};" % ",".join(_THREE_NAMES))
    parts.append("var globalThis = globalThis || this;")
    for name in ("trackmesh.js", "physics.js", "course.js"):
        parts.append(_strip_modules(_read(os.path.join(JS, name))))
    import sys
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import tracks as _tracks
    for slug, src in _tracks.all_scenery():
        parts.append("/* tracks/%s/scenery.js */\n%s" % (slug, src))
    for src in extra:
        parts.append(src)
    return "\n;\n".join(parts)


class Runtime:
    """A QuickJS context with the game code loaded."""

    def __init__(self, memory_mb=512, seconds=600):
        if not HAVE_QUICKJS:                          # pragma: no cover
            raise RuntimeError("quickjs is not installed")
        self.ctx = quickjs.Context()
        self.ctx.set_memory_limit(memory_mb * 1024 * 1024)
        self.ctx.set_time_limit(seconds)
        self.ctx.eval(bundle())

    def eval(self, code):
        return self.ctx.eval(code)

    def call(self, js_expression):
        """Evaluate an expression that returns JSON, and parse it."""
        import json
        return json.loads(self.ctx.eval("JSON.stringify(%s)" % js_expression))

    def load_tuning_and_tracks(self):
        """Push the tuning constants and the assembled tracks into JS.

        This is what lets a test build a real track with ``buildTrack`` and put a
        real ``Car`` on it, which is the only way to reach the parts of the
        physics that exist solely while the car is grounded - grip, the bump's
        released tyres, the slipstream's corridor.

        It used to push ``laptime``'s racing line alongside them, for a headless
        autopilot that drove every track. That is gone (see the note in
        laptime.py), and with it the only consumer of the line, so computing one
        here would be a speed profile per track per runtime that nothing reads.
        """
        import json
        import sys
        sys.path.insert(0, HERE)
        import tuning
        import tracks as tracks_mod
        self.ctx.eval("var T = %s;" % tuning.as_json())
        self.ctx.eval("var TRACKS = %s;" % json.dumps(tracks_mod.TRACKS))
        return tracks_mod

    def load_racing_line(self, slug):
        """Push `laptime`'s line and speed profile for one track, as `RL[slug]`.

        Opt-in and one track at a time, because it is a relaxation and a speed
        profile per track and only a test that actually *drives* wants one. That
        is what `load_tuning_and_tracks` used to do for all thirteen, for an
        autopilot that no longer exists.
        """
        import json
        import sys
        sys.path.insert(0, HERE)
        import laptime
        import tracks as tracks_mod
        pts, speeds, _ = laptime.speed_profile(tracks_mod.get(slug))
        self.ctx.eval("if (typeof RL === 'undefined') var RL = {};")
        self.ctx.eval("RL[%s] = %s;" % (json.dumps(slug), json.dumps(
            {"p": [[round(v, 4) for v in p] for p in pts],
             "v": [round(v, 4) for v in speeds]})))
