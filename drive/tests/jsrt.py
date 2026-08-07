"""Run the game's own JavaScript from Python, with no browser.

The car, the collider and the course logic are the parts of this project most
likely to break, and they all live in .js because they have to run in the
browser. Rather than reimplement them in Python for testing (which would test
the copy, not the game), this bundles the real modules into one script and runs
it in QuickJS.

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
JS = os.path.join(HERE, "..", "static", "js")

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
    """The whole simulation as one script, ready to eval."""
    parts = [_strip_modules(_read(os.path.join(HERE, "three_stub.js")))]
    parts.append("const THREE = {%s};" % ",".join(_THREE_NAMES))
    for name in ("trackmesh.js", "physics.js", "course.js"):
        parts.append(_strip_modules(_read(os.path.join(JS, name))))
    parts.append(_strip_modules(_read(os.path.join(HERE, "autopilot.js"))))
    parts.append(_strip_modules(_read(os.path.join(HERE, "sim.js"))))
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
        """Push the tuning constants, the tracks and the racing lines into JS.

        The racing line and speed profile come from ``laptime.py`` - the same ones
        the medal times are derived from - so the test driver follows the line the
        medals assume, and a track whose medal time is undrivable fails the test.
        """
        import json
        import sys
        sys.path.insert(0, os.path.join(HERE, ".."))
        import tuning
        import laptime
        import tracks as tracks_mod
        self.ctx.eval("var T = %s;" % tuning.as_json())
        self.ctx.eval("var TRACKS = %s;" % json.dumps(tracks_mod.TRACKS))
        rl = {}
        for t in tracks_mod.TRACKS:
            pts, speeds, _ = laptime.speed_profile(t)
            rl[t["slug"]] = {"p": [[round(v, 3) for v in p] for p in pts],
                             "v": [round(v, 3) for v in speeds]}
        self.ctx.eval("var RL = %s;" % json.dumps(rl))
        return tracks_mod
