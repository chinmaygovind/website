"""A stored track has to be indistinguishable from a folder, everywhere.

`tracks.get` is the one place a slug becomes a track, and it is called from
twenty-odd places in `app.py`. The bet this whole feature rests on is that
teaching *that function* about stored documents is enough - that boards,
ghosts, rooms, replays, share cards and the sitemap then work with no second
implementation of what a track is. These tests are that bet, written down.
"""

import importlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conftest import boot_app, close_app        # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import tracks as tracks_mod
from tracks import moves

to_moves = importlib.import_module("to_moves")

# A document per shape that matters: an ordinary ground track, a lap that has to
# close itself, and one that floats in the void with barriers on.
SHAPES = {"chicane": "ground", "spa": "closed lap", "gauntlet": "void"}


@pytest.fixture
def resolved():
    """`tracks.get` wired to an in-memory table of documents, then unwired.

    Restores the resolver afterwards, because it is module-level state and a
    test that left one installed would change what every later test's `get`
    does - which is precisely the class of bug this hook is arranged to avoid.
    """
    rows = {}

    def resolve(slug):
        doc = rows.get(slug)
        return tracks_mod.from_document(slug, doc) if doc else None

    before = tracks_mod._resolver
    tracks_mod.set_resolver(resolve)
    try:
        yield rows
    finally:
        tracks_mod.set_resolver(before)


# -- the chokepoint ----------------------------------------------------------
def test_the_pool_is_untouched_by_the_hook(resolved):
    assert len(tracks_mod.TRACKS) == 19 or len(tracks_mod.TRACKS) == len(
        [d for d in os.listdir(os.path.join(os.path.dirname(__file__), "..",
                                            "tracks"))
         if os.path.exists(os.path.join(os.path.dirname(__file__), "..",
                                        "tracks", d, "track.py"))])
    assert tracks_mod.get("spa")["name"] == "Spa-Francorchamps"


def test_a_slug_in_neither_place_is_none(resolved):
    assert tracks_mod.get("no-such-track") is None


def test_no_resolver_means_no_user_tracks():
    """A checkout with no database has to behave exactly as it does today."""
    before = tracks_mod._resolver
    tracks_mod.set_resolver(None)
    try:
        assert tracks_mod.get("anything") is None
        assert tracks_mod.get("chicane") is not None
    finally:
        tracks_mod.set_resolver(before)


def test_the_pool_wins_a_collision(resolved):
    """Belt and braces behind `slug_is_available`.

    A player cannot claim `spa`, but if a row ever held that slug - a rename in
    the pool, a bad import - the folder has to win. The alternative is a stored
    row silently shadowing a real track, and every time on Spa's board pointing
    at somebody's draft.
    """
    resolved["spa"] = to_moves.document("chicane")[0]
    assert tracks_mod.get("spa")["name"] == "Spa-Francorchamps"


@pytest.mark.parametrize("src", sorted(SHAPES), ids=[SHAPES[s] for s in sorted(SHAPES)])
def test_a_document_assembles_into_the_same_shape_of_dict(resolved, src):
    """Everything a folder gets derived for it, a document gets too.

    `user` is the only key that may differ, and it exists to say whose track
    this is - read by the play page's by-line, the switcher shelf and `/admin`,
    and by nothing that touches geometry. `placed` used to be here too, and is
    not any more: a pool folder can declare `placed = [...]` as well, which is
    what makes `tools/adopt_track.py` lossless. The two shapes converging is the
    point of this test, so the exclusion list getting *shorter* is the direction
    it should move in.
    """
    doc, _ = to_moves.document(src)
    resolved["mine"] = doc
    got, pool = tracks_mod.get("mine"), tracks_mod.get(src)

    assert set(got) - {"user"} == set(pool), (
        "a stored track is missing, or has invented, a key")
    for k in ("pole_side", "gate_ceil", "checkpoints", "closed", "ideal"):
        assert got[k] == pool[k], "%s differs on %s" % (src, k)
    assert got["line"] == pool["line"], "the road differs"
    assert sorted(got["medals"].values()) == list(
        got["medals"][k] for k in ("gold", "silver", "bronze")), "medals out of order"
    assert got["user"] is True and "user" not in pool


def test_a_fork_does_not_inherit_hand_cut_medal_times(resolved):
    """A user track derives its medals. Always, on purpose.

    `tools/set_medals.py` cuts the three times from a track's own board, and
    that is why Chicane Park's gold is 14.4 rather than the 17.3 the simulation
    predicts - real records beat an estimate. A fork has none of that history,
    so inheriting the parent's numbers would hand a brand new track a gold
    nobody has ever driven on it. It gets the derivation instead, which is the
    same fallback a pool track gets before anybody has played it.
    """
    doc, _ = to_moves.document("chicane")
    resolved["mine"] = doc
    got, pool = tracks_mod.get("mine"), tracks_mod.get("chicane")
    assert pool["medal_times"], "chicane is supposed to declare its medals"
    assert got["medal_times"] is None
    assert got["medals"]["gold"] > pool["medals"]["gold"], (
        "the derivation is looser than a cut time; that is the whole reason "
        "`set_medals.py` exists")
    assert got["medals"] == tracks_mod.laptime.medals(got["ideal"])


def test_a_forked_palette_travels_with_the_document(resolved):
    """The strongest thing here for "as beautiful as mine".

    A fork of Spa has to arrive with Spa's nine hand-cut sky stops, not with the
    neutral default - which is what `_palette_for` would have handed it before
    it learned to look on the entry.
    """
    doc, _ = to_moves.document("spa")
    resolved["ardennes"] = doc
    got = tracks_mod.get("ardennes")
    assert got["pal"]["road"] == tracks_mod.get("spa")["pal"]["road"]
    assert len(got["pal"]["sky"]["stops"]) == len(
        tracks_mod.get("spa")["pal"]["sky"]["stops"]) >= 6
    assert got["pal"] != dict(tracks_mod.look.DEFAULT)


def test_a_track_with_no_palette_gets_the_neutral_default(resolved):
    resolved["bare"] = moves.record(
        lambda b: b.start(run=30).arc(-60, 40).straight(40).cp()
                   .arc(70, 34).straight(30).finish())
    got = tracks_mod.get("bare")
    assert got["pal"]["road"] == tracks_mod.look.DEFAULT["road"]


def test_a_broken_document_raises_rather_than_returning_a_bad_track(resolved):
    """The caller decides what to do; this must not hand back half a track."""
    resolved["broken"] = {"moves": [{"t": "arc", "deg": 40}]}
    with pytest.raises(moves.MoveError):
        tracks_mod.get("broken")


# -- slugs -------------------------------------------------------------------
@pytest.mark.parametrize("name,want", [
    ("Foggy Ridge", "foggy-ridge"),
    ("  Amber Vale!!  ", "amber-vale"),
    ("Dockyard -- Sprint", "dockyard-sprint"),
    ("Circuit de la Sarthe", "circuit-de-la-sarthe"),
    ("2 Fast", "2-fast"),
])
def test_slugify(name, want):
    assert tracks_mod.slugify(name) == want


@pytest.mark.parametrize("slug", ["spa", "costco", "bigred"])
def test_a_pool_slug_cannot_be_claimed(slug):
    ok, why = tracks_mod.slug_is_available(slug)
    assert not ok and "already a track" in why


@pytest.mark.parametrize("slug", sorted(tracks_mod.RESERVED)[:6])
def test_a_reserved_word_cannot_be_claimed(slug):
    ok, why = tracks_mod.slug_is_available(slug)
    assert not ok and "reserved" in why


@pytest.mark.parametrize("slug", ["Foggy-Ridge", "foggy ridge", "ab", "x" * 41,
                                  "-lead", "trail-", "double--dash", ""])
def test_a_slug_that_is_not_storable_is_refused_with_a_reason(slug):
    ok, why = tracks_mod.slug_is_available(slug)
    assert not ok and why, slug


def test_slugify_output_is_always_claimable():
    """The two have to agree, or the editor offers names it cannot save."""
    for name in ("Foggy Ridge", "!!!Amber!!! Vale!!!", "a" * 90, "Le Mans 24"):
        s = tracks_mod.slugify(name)
        if len(s) >= 3 and s not in tracks_mod.RESERVED and s not in tracks_mod.BY_SLUG:
            ok, why = tracks_mod.slug_is_available(s)
            assert ok, "slugify produced %r, which is not claimable: %s" % (s, why)


# -- the fingerprint --------------------------------------------------------
def _ribbon(doc):
    return moves.fingerprint(moves.build(doc).build())


def test_the_same_road_written_two_ways_has_one_fingerprint():
    """A no-op edit must not cost anybody their lap time."""
    terse = moves.record(lambda b: b.start(run=20).straight(30).finish())
    verbose = moves.record(lambda b: b.start(run=20).straight(30, rise=0.0,
                                                              ease=True).finish())
    assert _ribbon(terse) == _ribbon(verbose)


def test_moving_the_road_changes_the_fingerprint():
    a = moves.record(lambda b: b.start(run=20).arc(-60, 40).finish())
    b = moves.record(lambda b: b.start(run=20).arc(-60, 41).finish())
    assert _ribbon(a) != _ribbon(b)


def test_a_wall_changes_the_fingerprint_and_a_tower_does_not():
    """The split that lets a mesh-only edit keep its board.

    A wall is collider: it changes where the car may go, so every time on the
    board was set on a different road. A tower is scenery, and moving one has
    not invalidated anybody's record.
    """
    built = moves.build(moves.record(
        lambda b: b.start(run=20).straight(40).finish())).build()
    bare = moves.fingerprint(built)
    mesh = moves.fingerprint(built, {"mesh": [[0, 0, 0, 1, 1, 1]]})
    wall = moves.fingerprint(built, {"collider": [[0, 0, 0, 1, 1, 1]]})
    assert mesh == bare, "a mesh-only change must not wipe a board"
    assert wall != bare, "a collider change must wipe the board"


# -- the row ----------------------------------------------------------------
@pytest.fixture
def env():
    """A fresh app and database, the way the rest of the suite does it."""
    A, path = boot_app()
    import models as M
    A.models = M
    yield A
    close_app(path)


def test_a_row_round_trips_through_the_database(env):
    """`create_all` brings the table into being, so no hand migration."""
    A = env
    doc, _ = to_moves.document("chicane")
    doc["name"] = "Foggy Ridge"
    with A.app.app_context():
        row = A.models.DriveUserTrack(
            slug="foggy-ridge", name="Foggy Ridge", difficulty=3,
            doc_json=json.dumps(doc), status="draft",
            geom_hash=_ribbon(doc), forked_from="chicane")
        A.db.session.add(row)
        A.db.session.commit()

        got = A.models.DriveUserTrack.query.filter_by(slug="foggy-ridge").one()
        assert got.doc["moves"] == doc["moves"]
        assert got.status == "draft" and not got.is_live
        assert got.forked_from == "chicane"
        # And the stored document still builds the road it was recorded from.
        assert (moves.build(got.doc).build()["line"]
                == tracks_mod.get("chicane")["line"])


def test_a_row_with_unreadable_json_is_empty_rather_than_an_exception(env):
    """Same posture as `tracks.BROKEN`: one bad row is not an outage."""
    A = env
    with A.app.app_context():
        row = A.models.DriveUserTrack(slug="bad", name="Bad", doc_json="{not json")
        assert row.doc == {}
