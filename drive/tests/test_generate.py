"""The daily generator: what it proposes has to be a real track.

**One test that drives the whole loop**, rather than a suite per function. The
generator's only contract is "what survives `judge` is something the editor
would have accepted from a person", and the cheapest honest way to assert that
is to run it and check the survivors against the same battery the pool's own
tests apply.

It is deliberately a *small* sample. Pricing a lap is ~550ms and a keeper costs
two builds, so twelve candidates is about four seconds - enough to catch a
generator that has stopped producing anything, or one whose output stopped being
drivable, and not enough to be the reason anybody stops running the suite.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tracks as tracks_mod                                     # noqa: E402
from tracks import checks, generate                             # noqa: E402

import gen_daily                                                # noqa: E402


# A fixed seed, so a failure is reproducible and a passing run is not luck.
SEED = 20260920
WANT = 3


@pytest.fixture(scope="module")
def kept():
    return gen_daily.propose(WANT, SEED, verbose=False)


def test_it_proposes_something_at_all(kept):
    """The whole loop, end to end. A generator that has quietly stopped
    producing anything raises `SystemExit` out of `propose`, which is a louder
    failure than this assert - so reaching here at all is most of the test."""
    assert len(kept) == WANT


def test_every_keeper_is_the_length_it_was_asked_for(kept):
    """30-40 seconds is the feature, not a nicety: a daily is one run before
    work, and the window is the reason this is a generator and not a track."""
    for seed, _doc, track in kept:
        assert generate.TARGET_LOW <= track["ideal"] <= generate.TARGET_HIGH, (
            "seed %d prices at %.1fs, outside the %g-%g the daily promises"
            % (seed, track["ideal"], generate.TARGET_LOW, generate.TARGET_HIGH))


def test_no_keeper_is_buried_in_its_own_ground(kept):
    """The defect that shipped first and was found in a render, not a test.

    `track.ground` is one flat collidable quad; a ribbon dipping below it does
    not clip or warn, the quad just draws through the road. The generator's walk
    cannot know where its own floor is until the road is laid, so the document
    carries a placeholder and `generate.settle_ground` corrects it. This is the
    assertion that says it still does - the pool's own
    `test_the_road_is_never_buried_in_its_own_ground` cannot see these, because
    they are not folders.
    """
    for seed, _doc, track in kept:
        if track["ground"] is None:
            continue                      # a stunt track floats
        low = min(e["p"][1] for e in track["line"])
        assert low >= track["ground"] - 0.01, (
            "seed %d drops %.1f below its ground plane" % (seed, track["ground"] - low))


def test_a_keeper_rebuilds_from_its_document(kept):
    """What is stored is the document, so the document is what has to build.

    The keeper's track came out of `judge`, which mutates the document as it
    goes (`settle_ground`). If what got stored were the *pre*-settle version,
    every daily would be buried and the test above would still pass - so this
    replays the stored document from scratch, which is exactly what the site
    does on every request for one.
    """
    for seed, doc, track in kept:
        again = tracks_mod.from_document(doc.get("slug") or "daily-x", doc,
                                         timed=False)
        assert again["ground"] == track["ground"]
        if again["ground"] is None:
            continue
        low = min(e["p"][1] for e in again["line"])
        assert low >= again["ground"] - 0.01, \
            "seed %d rebuilds buried: the stored document is not the settled one" % seed


def test_the_same_seed_makes_the_same_track():
    """Reproducibility is what makes a bad daily reportable: a seed is enough
    to get the exact track back, without it having to exist anywhere."""
    looks = gen_daily.pool_looks()
    a = generate.generate(77, looks)
    b = generate.generate(77, looks)
    assert a == b
    assert generate.generate(78, looks) != a


def test_the_palette_is_borrowed_whole():
    """Hue-rotating a borrowed palette was tried and is why this asserts.

    It kept every relation between the colours and still made Figure Eight's
    snow lavender under a green sun. Only `density` may differ from the source,
    because density is per unit of area and the borrowed track is a different
    size - see `generate.borrow`.
    """
    looks = gen_daily.pool_looks()
    by_slug = {l["slug"]: l["pal"] for l in looks}
    for seed in range(12):
        doc = generate.generate(seed, looks)
        src = by_slug[doc["generated"]["look"]]
        for k, v in doc["pal"].items():
            if k == "density":
                continue
            assert src.get(k) == v, \
                "seed %d altered %r, which borrowing must not do" % (seed, k)


def test_no_keeper_has_a_shortcut(kept):
    """Nothing reaches the queue with road a car can leave and rejoin further
    on without passing a checkpoint - across the grass or off a higher stretch
    onto a lower one. `judge` repairs what it can and drops the rest."""
    for seed, _doc, track in kept:
        assert checks.shortcuts(track) == [], "seed %d has a shortcut" % seed


def test_the_shortcut_check_sees_playgrounds_drops():
    """Every top Playground time goes through the checkpoint at station 746,
    high on the Climb, leaves the road just after it and lands on the road
    past station 840 - a flight of over a hundred units in plan, not a fall. If
    the check cannot see that, it cannot see the thing it was written for."""
    cuts = checks.shortcuts(tracks_mod.get("playground"))
    assert any(c["kind"] == "drop" and 746 < c["i"] <= 800 and 830 <= c["j"] <= 880
               for c in cuts)
    assert checks.shortcuts(tracks_mod.get("sunrise")) == []


def test_a_drop_is_closed_with_a_checkpoint_between():
    """`repair` puts a gate between take-off and landing, which kills the drop
    because a lap that misses a gate is not a lap."""
    looks = gen_daily.pool_looks()
    doc = generate.generate(3, looks)
    n = len(doc["moves"])
    track = tracks_mod.from_document("daily-x", doc, timed=False)
    i, j = 40, len(track["line"]) - 60
    assert gen_daily.repair(doc, {"kind": "drop", "i": i, "j": j, "gain": 99})
    assert len(doc["moves"]) == n + 1
    after = tracks_mod.from_document("daily-x", doc, timed=False)
    assert any(i < g["si"] <= j for g in after["gates"] if g["kind"] == "cp")


def test_walls_of_death_only_climb():
    """A wall that descends puts its own exit under its wrap, so the whole
    corner can be dropped off - one of the two places every top Playground time
    skips. The generator never lays one."""
    looks = gen_daily.pool_looks()
    void = [l for l in looks if generate.is_void(l)]
    walls = [m for seed in range(60)
             for m in generate.generate(seed, looks, look=void[seed % len(void)])["moves"]
             if m["t"] == "wall"]
    assert walls and all(m["rise"] > 0 for m in walls)


def test_neighbouring_days_get_different_looks():
    """The queue is approved in order into consecutive days, and "same theme as
    daily #1" was a review note - so no two neighbours share a look, and the
    first few avoid the ones already scheduled."""
    looks = gen_daily.pool_looks()
    order = [l["slug"] for l in gen_daily.look_order(looks, 60, avoid=["tokyo", "suzuka"])]
    assert all(a != b for a, b in zip(order, order[1:]))
    assert "tokyo" not in order[:5] and "suzuka" not in order[:5]
    assert set(order[:len(looks)]) == {l["slug"] for l in looks}
