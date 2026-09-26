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
from tracks import generate                                     # noqa: E402

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
