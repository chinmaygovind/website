"""No two bundled JavaScript files may declare the same top-level name.

`jsrt.py` concatenates the whole simulation into one script for QuickJS -
`three_stub.js`, `trackmesh.js`, `physics.js`, `course.js`, every track's
`scenery.js`, and whatever a caller appends (`bot.js` and `botworld.js` for the
bots). Module syntax is stripped, so every top-level `const`, `let`, `function`
and `class` lands in *one* scope.

Two files declaring the same name is therefore a `SyntaxError: invalid
redefinition of lexical identifier`, and it does not fail where you added it: a
`const clamp` in `scenery_kit.js` collided with `bot.js`'s and took out
seventeen bot tests with an error that named neither file. `var` would have been
worse - it redefines silently, so the second file's version wins and the first
file's callers get a function with the same name and different behaviour.

This is a whole-bundle check rather than a rule in a comment because the surface
grows: every new file in the bundle multiplies the chances, and the names most
likely to clash are exactly the ones everybody reaches for - clamp, lerp, frame,
anchor, defaults.
"""

import os
import re
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))

# Anything that can end up in a bundle, including the sources callers append.
EXTRA = ("static/js/bot.js", "botworld.js")

DECL = re.compile(r"^(?:const|let|function|class)\s+([A-Za-z_$][\w$]*)", re.M)


def _bundled_sources():
    import jsrt
    out = {}
    for name in ("scenery_kit.js", "trackmesh.js", "physics.js", "course.js"):
        with open(os.path.join(HERE, "..", "static", "js", name)) as f:
            out[name] = jsrt._strip_modules(f.read())
    for rel in EXTRA:
        with open(os.path.join(HERE, "..", rel)) as f:
            out[rel] = jsrt._strip_modules(f.read())
    return out


def test_no_two_bundled_files_declare_the_same_name():
    seen, clashes = {}, []
    for name, src in _bundled_sources().items():
        for m in DECL.finditer(src):
            n = m.group(1)
            if n in seen and seen[n] != name:
                clashes.append("%s: declared in both %s and %s"
                               % (n, seen[n], name))
            seen.setdefault(n, name)
    assert not clashes, (
        "these names collide once jsrt.py concatenates the bundle, which is a "
        "SyntaxError in QuickJS and does not name either file:\n  "
        + "\n  ".join(sorted(set(clashes))))


def test_the_bundle_actually_evaluates_with_the_bots_in_it():
    """The check above reads the sources; this one runs them.

    A name clash is the failure it is written for, but it is not the only way to
    break a bundle - a stripped `export` that leaves dangling syntax does it too,
    and only evaluation catches that.
    """
    import jsrt
    if not jsrt.HAVE_QUICKJS:
        pytest.skip("needs the optional quickjs package")
    with open(os.path.join(HERE, "..", "static", "js", "bot.js")) as f:
        bot = jsrt._strip_modules(f.read())
    with open(os.path.join(HERE, "..", "botworld.js")) as f:
        world = jsrt._strip_modules(f.read())
    rt = jsrt.Runtime(extra=(bot, world))
    rt.load_tuning_and_tracks()
    rt.eval("var _ok = typeof buildTrack === 'function' "
            "&& typeof placeAll === 'function';")
    assert rt.call("_ok") is True
