"""A broken track folder is reported, not fatal - proved by breaking one.

`test_tracks.py::test_every_track_folder_loads` is the pull-request gate: it fails
if any folder in `tracks/` did not make it into the pool. That test is only worth
anything if two things are true, and neither is obvious from reading it:

1. **The loader survives a broken folder.** If a contributor's typo took the whole
   import down, the gate would not fail - it would fail to *collect*, along with
   every other test in the suite, and the person fixing it could not run anything.
2. **The gate actually notices.** A `BROKEN` that is never populated is a green
   test over a broken pool.

So this writes deliberately broken folders into `tracks/`, reloads, and checks
both. It covers the three moments a folder can fail, because they are three
different code paths and for a while only the last was guarded: **importing**
`track.py`, **reading** its declarations, and **building** the ribbon.

The folders are created and removed inside a fixture, and the module cache is put
back afterwards, so a failure here cannot leave a broken track behind for the rest
of the session.
"""

import importlib
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tracks as tracks_mod

TRACKS_DIR = os.path.join(os.path.dirname(__file__), "..", "tracks")

# Enough of a track to load, so each case below differs in exactly one way.
GOOD = '''slug = "%s"
name = "Scratch"
difficulty = 2
ground = -1.2
order = 9000


def build(b):
    b.start(run=40)
    b.arc(70, 60).straight(60)
    b.cp()
    b.arc(-80, 40).straight(80)
    b.finish()
'''

SLUG = "zzscratch"

CASES = {
    # The likeliest thing a first-time contributor pushes.
    "syntax": ('slug = "zzscratch"\nthis is not python\n', "this"),
    # Forgetting one of the four required declarations. The expectation names the
    # missing field rather than just mentioning it, because the error also lists
    # every required declaration - so a bare "name" would pass whichever one had
    # actually been left out.
    "missing_field": ('slug = "zzscratch"\ndifficulty = 2\n'
                      'def build(b):\n    b.start()\n    b.finish()\n',
                      "missing `name`"),
    # Renaming the folder and not the slug, or the other way round.
    "slug_mismatch": ('slug = "somewhere_else"\nname = "S"\n'
                      'difficulty = 2\ndef build(b):\n    b.start()\n'
                      '    b.finish()\n', "folder name is the slug"),
    # A declaration that is present but wrong.
    "bad_difficulty": ('slug = "zzscratch"\nname = "S"\n'
                       'difficulty = 11\ndef build(b):\n    b.start()\n'
                       '    b.finish()\n', "difficulty"),
    # No `build` at all.
    "no_build": ('slug = "zzscratch"\nname = "S"\n'
                 'difficulty = 2\n', "build"),
    # Medal times in the wrong order. Slow-to-fast reads perfectly well as a
    # thing somebody would type, and a pool that accepted it would ship a card
    # where bronze is the hardest medal and nothing anywhere would say so.
    "medals_backwards": ('slug = "zzscratch"\nname = "S"\n'
                         'difficulty = 2\nmedals = (20.0, 18.0, 16.0)\n'
                         'def build(b):\n    b.start()\n    b.finish()\n',
                         "increasing"),
    # Two times where there must be three - the likeliest way to mistype the
    # tuple the tool writes.
    "medals_short": ('slug = "zzscratch"\nname = "S"\n'
                     'difficulty = 2\nmedals = (20.0, 22.0)\n'
                     'def build(b):\n    b.start()\n    b.finish()\n',
                     "three"),
    # Builds fine, but the loop cannot be closed inside the solver's guards.
    "unclosable": ('slug = "zzscratch"\nname = "S"\n'
                   'difficulty = 2\nclosed = True\n'
                   'def build(b):\n'
                   '    b.start(run=20)\n'
                   '    b.straight(300); b.arc(90, 30)\n'
                   '    b.straight(300); b.arc(90, 30)\n'
                   '    b.straight(20); b.arc(90, 30)\n'
                   '    b.straight(300); b.arc(90, 30)\n'
                   '    b.finish_at_start()\n', "close"),
}

class _Pool:
    """What `_reload` hands back: the tracks that loaded, and the ones that did not."""

    def __init__(self, built, broken):
        self.TRACKS = built
        self.BROKEN = dict(broken)
        self._by = {t["slug"]: t for t in built}

    def get(self, slug):
        return self._by.get(slug)


def _reload():
    """Re-run discovery over whatever is on disk now.

    Calls `_assemble` rather than re-importing the package, and the difference is
    the whole reason this file is not the slowest thing in the suite: a full
    import derives a racing line and medal times for every track and costs 2.4s,
    where `_assemble` builds the ribbons and stops, at 0.5s. Nothing here is about
    medal times - it is about which folders load - so the expensive half is waste.

    The scratch track's own modules are dropped from the cache first, or Python
    hands back the previous case's file and every scenario after the first
    silently tests the wrong source. `invalidate_caches` is for the folder itself,
    which did not exist when the process started.
    """
    for name in [m for m in sys.modules
                 if m == "tracks.%s" % SLUG or m.startswith("tracks.%s." % SLUG)]:
        del sys.modules[name]
    importlib.invalidate_caches()
    built = tracks_mod._assemble()
    return _Pool(built, tracks_mod.BROKEN)


@pytest.fixture
def scratch():
    """Write a folder into `tracks/`, and take it away again whatever happens."""
    d = os.path.join(TRACKS_DIR, SLUG)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    was_broken = dict(tracks_mod.BROKEN)

    def write(track_py, palette_py=None):
        with open(os.path.join(d, "track.py"), "w") as f:
            f.write(track_py)
        if palette_py is not None:
            with open(os.path.join(d, "palette.py"), "w") as f:
                f.write(palette_py)
        return _reload()

    try:
        yield write
    finally:
        shutil.rmtree(d, ignore_errors=True)
        # Put `BROKEN` back rather than re-assembling to do it. `_assemble`
        # returns a fresh list and mutates only this one global, and the folder
        # is gone by now, so half a second of rebuilding fifteen ribbons would
        # buy nothing. `tracks_mod.TRACKS` was never touched.
        tracks_mod.BROKEN.clear()
        tracks_mod.BROKEN.update(was_broken)


def test_a_good_scratch_folder_just_works(scratch):
    """The control. Without it every test below could pass because the fixture
    never manages to add a track at all."""
    mod = scratch(GOOD % SLUG)
    assert not mod.BROKEN, mod.BROKEN
    t = mod.get(SLUG)
    assert t is not None, "a valid folder did not reach the pool"
    # `_reload` stops before medal times, so derive them here - once, in the one
    # test that is about a track working rather than about a track failing.
    #
    # This is also the assertion that a folder nobody has driven yet is still a
    # playable, medalled track. Every track in the shipped pool declares times
    # cut from its board, and if that were the *only* way to get medals then a
    # new track would arrive with no standard on it at all - which is the state
    # `tools/set_medals.py` cannot fix, because it needs laps that do not exist.
    import laptime
    assert t["medal_times"] is None, "a scratch folder declared medal times"
    assert laptime.medals(laptime.ideal_lap(t))["gold"] > 0


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_broken_folder_is_reported_and_not_fatal(scratch, case):
    """Import, read and build failures all land in `BROKEN` and nowhere else."""
    source, expect = CASES[case]
    mod = scratch(source)

    # 1. It did not take the pool down with it.
    assert len(mod.TRACKS) >= 8, (
        "%s broke the whole pool: only %d tracks loaded" % (case, len(mod.TRACKS)))
    assert mod.get("sunrise") is not None, \
        "%s stopped an unrelated track from loading" % case

    # 2. It is not in the game.
    assert mod.get(SLUG) is None, \
        "%s loaded anyway, which means it was not really broken" % case

    # 3. It is named, with a reason somebody can act on.
    assert SLUG in mod.BROKEN, (
        "%s is missing from the pool but not reported in BROKEN, so the pull "
        "request gate would pass over it" % case)
    assert expect in str(mod.BROKEN[SLUG]).lower() or expect in str(mod.BROKEN[SLUG]), (
        "%s reported %r, which does not mention %r - the message is what the "
        "contributor gets" % (case, str(mod.BROKEN[SLUG]), expect))


def test_a_broken_palette_is_reported_too(scratch):
    """The palette is a separate file and a separate import, so a separate case.

    `look.check` refuses a palette with a key nothing reads as well as one missing
    a colour, because the first fails by silently ignoring whatever you were
    trying to change.
    """
    mod = scratch(GOOD % SLUG, 'PALETTE = {"road": 0x112233}\n')
    assert mod.get(SLUG) is None
    assert SLUG in mod.BROKEN
    assert "missing" in str(mod.BROKEN[SLUG])

    mod = scratch(GOOD % SLUG,
                  'PALETTE = {"road": 0x112233, "kerb": 0xffffff, '
                  '"kerb2": 0xff0000, "ground": 0x338833, "rail": 0xffffff, '
                  '"prop": 0x224422, "deco": 0xffcc00, "fog": 0xccddee, '
                  '"glowStrenth": 3}\n')
    assert SLUG in mod.BROKEN, "a misspelled palette key was accepted"
    assert "glowStrenth" in str(mod.BROKEN[SLUG])


def test_the_gate_test_fails_when_a_track_is_broken(scratch):
    """The gate itself, run against a broken pool.

    Everything above checks that `BROKEN` is populated. This checks the thing that
    actually blocks a merge - that `test_every_track_folder_loads` goes red - and
    that its message names the folder, since that message is the entire output a
    contributor gets from CI.
    """
    mod = scratch(CASES["syntax"][0])

    # The gate's own assertion, against this reloaded pool.
    with pytest.raises(AssertionError) as e:
        assert not mod.BROKEN, "\\n".join(
            ["", "%d track folder(s) did not load and are NOT in the game:"
             % len(mod.BROKEN), ""]
            + ["  tracks/%s/\\n      %s" % (slug, exc)
               for slug, exc in sorted(mod.BROKEN.items())])
    assert SLUG in str(e.value), \
        "the failure does not name the folder that broke: %s" % e.value


def test_a_folder_without_a_track_py_is_caught_as_stray(scratch):
    """Naming the file `tracks.py` produces no error and no track.

    The one failure mode with no symptom, which is why
    `test_no_track_folder_is_silently_ignored` exists. Here it is happening.
    """
    d = os.path.join(TRACKS_DIR, SLUG)
    with open(os.path.join(d, "tracks.py"), "w") as f:      # note the plural
        f.write(GOOD % SLUG)
    mod = _reload()
    assert mod.get(SLUG) is None
    assert SLUG not in mod.BROKEN, (
        "a folder with no track.py should be skipped rather than reported as "
        "broken - it is usually somebody's scratch directory")

    # ...and the stray check is what notices.
    strays = [e for e in sorted(os.listdir(TRACKS_DIR))
              if os.path.isdir(os.path.join(TRACKS_DIR, e))
              and not e.startswith((".", "_"))
              and not os.path.exists(os.path.join(TRACKS_DIR, e, "track.py"))]
    assert SLUG in strays, "the stray-folder check would not have caught this"
