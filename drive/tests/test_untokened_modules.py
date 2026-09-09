"""The six modules nothing can bust, and the one way they take the site down.

`game.js`, `style.css`, `garage.js` and `pending.js` are requested with a `?v=`
token derived from the newest mtime under `static/`, so a deploy busts them.
**The modules `game.js` reaches by bare `import` carry no token** - there is
nowhere in `import './course.js'` to put one - so nginx's map gives them an hour
and `sw.js` precaches them forever, until its `CACHE` string changes.

That asymmetry has exactly one fatal shape, and it shipped on 2026-09-09:

    game.js   busts, arrives new, says   import { IN } from './course.js'
    course.js does not bust, arrives from the cache, has never heard of `IN`

A missing named export is not a warning and not a broken feature - the module
graph fails to link, so **nothing runs at all**. The canvas stays black, the
page is a 200, no server log has anything in it and the Action is green. It is
the quietest failure this codebase can have, and a fresh browser cannot
reproduce it, which is why it needs a test rather than a look.

So this file pins the **export surface** of those modules. Adding an export is
not forbidden - it is a thing you have to say out loud, by editing `EXPORTS`
below, and the moment you are here you are being told the other half: bump
`CACHE` in `sw.js` in the same commit, or a returning player keeps the old file
indefinitely.

Two things this deliberately does *not* check, because they are safe:

* **Removing** an export. Old cached `game.js` with a new `course.js` is not a
  combination that happens - `game.js` busts, so the new one is always the one
  asking. (Removing one still needs the callers updated, which every other test
  in the suite is already watching.)
* Changing what an export *returns*. `Ghost.at` grew a ninth value in the same
  commit that caused the outage and was harmless: a cached `course.js` hands
  back eight, and the replay's pad says *Estimated* instead of lying.
"""

import os
import re

import pytest

JS = os.path.join(os.path.dirname(__file__), "..", "static", "js")

# The modules `game.js` reaches by bare `import`, and every name each one hands
# out. Sorted, so a diff is one line rather than a reshuffle.
#
# **Adding a name here is a promise that `sw.js`'s CACHE moved too.**
EXPORTS = {
    "course.js": ["Course", "GHOST_RATE", "Ghost", "Run", "inputByte"],
    "physics.js": ["Car", "FLAG", "Stepper"],
    "render.js": ["CarView", "Draft", "Renderer"],
    "sound.js": ["Sound"],
    "trackmesh.js": ["Collider", "KIND", "MeshBuf", "Movers", "buildTrack",
                     "mulberry", "palette", "sceneryContext", "shade"],
}

_EXPORT = re.compile(r"^export\s+(?:class|function|const|let|var)\s+"
                     r"([A-Za-z_$][A-Za-z0-9_$]*)", re.M)


def exports_of(name):
    with open(os.path.join(JS, name)) as f:
        return sorted(_EXPORT.findall(f.read()))


@pytest.mark.parametrize("name", sorted(EXPORTS))
def test_an_untokened_module_did_not_grow_an_export(name):
    """Nothing can bust these files, so a new name is a module that fails to
    link for everybody holding the old one - and a failed link takes the whole
    graph with it, so the game does not boot.

    If you meant to add one: put it in `EXPORTS` above **and** bump `CACHE` in
    `sw.js`, which is the only thing that drops the precached copy. Then check
    it the way the outage was found, since no fresh browser will show you:

        git show HEAD:drive/static/js/course.js > drive/static/js/course.js
        # load the page, read the console, put it back

    The safe alternative is usually to not add one at all. The fix for the
    2026-09-09 outage was to derive the constants in `game.js` from `inputByte`,
    which every cached copy already exports.
    """
    got = exports_of(name)
    want = sorted(EXPORTS[name])
    new = [n for n in got if n not in want]
    assert not new, (
        "%s gained %s. Nothing can bust this file - it is imported by name from "
        "game.js, so it carries no ?v= token and sw.js precaches it - and a "
        "browser holding the old copy cannot satisfy that import, which stops "
        "the whole game booting. Add it to EXPORTS here and bump CACHE in "
        "sw.js, or derive what you need from an export that is already there."
        % (name, ", ".join(new)))
    assert got == want, (
        "%s no longer exports %s. That direction is safe at the cache - old "
        "game.js never meets new course.js - so update EXPORTS here."
        % (name, ", ".join(n for n in want if n not in got)))


def test_the_service_worker_precaches_exactly_these():
    """The list above is only the right list if these are the files that get
    stuck. `sw.js` is what makes an hour into forever, so the two have to name
    the same modules - a seventh added to its precache and not to `EXPORTS`
    would be a file with the same trap and no test."""
    with open(os.path.join(JS, "sw.js")) as f:
        sw = f.read()
    cached = set(re.findall(r'"/static/js/(?:vendor/)?([a-z_.]+\.js)"', sw))
    missing = set(EXPORTS) - cached
    assert not missing, (
        "%s is pinned here but no longer precached by sw.js. Either it stopped "
        "being an untokened import (drop it from EXPORTS) or the precache lost "
        "it." % ", ".join(sorted(missing)))


def test_the_cache_name_is_versioned():
    """It is the only handle on the precached set, so it has to be something a
    deploy can move. A `CACHE` with no number in it is one nobody can bump."""
    with open(os.path.join(JS, "sw.js")) as f:
        m = re.search(r'const CACHE = "([^"]+)"', f.read())
    assert m, "sw.js has no CACHE constant"
    assert re.search(r"v\d+$", m.group(1)), (
        "sw.js's CACHE is %r, which has no version on the end - bumping it is "
        "the only way to drop a stale module." % m.group(1))
