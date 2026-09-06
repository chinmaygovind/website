"""A document has to rebuild a track exactly, or it is not a document.

`tracks/moves.py` claims to be a complete record of what an author asked for.
The only way to believe that is to take the tracks that already exist, record
them, replay them, and demand the ribbon come back **station for station** the
same. Anything the schema cannot express shows up here as a divergence rather
than as a track that is subtly wrong months later.

`sections` would fail every one of these, which is the point: it drops
`width()`, records `crest` as a `straight`, and holds no gates at all.
"""

import inspect
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tracks import moves, solver
from tracks.builder import Builder
from tuning import ROAD_W

from conftest import track_folders  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TRACKS_DIR = os.path.join(HERE, "..", "tracks")

# Via `conftest`, so a scratch folder another worker is part way through
# writing is not mistaken for a track. See `track_folders`.
SLUGS = track_folders()


def _module(slug):
    import importlib
    return importlib.import_module("tracks.%s.track" % slug)


def _decl(mod):
    """The declarations `tracks/__init__.py` reads, as `record` wants them."""
    return {
        "width": getattr(mod, "width", ROAD_W),
        "rails": bool(getattr(mod, "rails", False)),
        "origin": tuple(getattr(mod, "origin", (0.0, 0.0, 0.0, 0.0))),
        "closed": bool(getattr(mod, "closed", False)),
    }


def _authored(mod):
    """The ribbon the folder builds, with no document involved."""
    d = _decl(mod)
    o = d["origin"]
    b = Builder(o[0], o[1], o[2], yaw=o[3], width=d["width"], rails=d["rails"])
    return ((mod.build(b) or b)).build()


def _document(mod):
    """The same track as a stored document, through JSON exactly as a row is."""
    doc = moves.record(mod.build, **_decl(mod))
    return json.loads(json.dumps(doc))


# -- the load-bearing test ---------------------------------------------------
@pytest.mark.parametrize("slug", SLUGS)
def test_a_recorded_track_replays_identically(slug):
    mod = _module(slug)
    want = _authored(mod)
    got = moves.build(_document(mod)).build()

    assert len(got["line"]) == len(want["line"]), (
        "%s: replay produced %d stations, the folder produces %d"
        % (slug, len(got["line"]), len(want["line"])))
    for i, (a, b) in enumerate(zip(want["line"], got["line"])):
        assert a == b, ("%s: station %d differs.\n  folder:   %s\n  document: %s"
                        % (slug, i, a, b))
    assert got["gates"] == want["gates"], "%s: the gates moved" % slug
    assert got["spawn"] == want["spawn"], "%s: the spawn moved" % slug
    # `sections` is what the closure solver keys substitutions on, so a document
    # that produced the same road by a different route would still break a
    # closed lap. Same shape, same order, or the solver is not safe to run.
    assert ([s["t"] for s in got["sections"]]
            == [s["t"] for s in want["sections"]]), "%s: section shape differs" % slug


@pytest.mark.parametrize("slug", [s for s in SLUGS
                                  if getattr(_module(s), "closed", False)])
def test_a_closed_document_solves_the_way_its_folder_does(slug):
    """The solver has to make the same choices through a document.

    It picks which legs to adjust from `sections` and the `FREE()` marks, and
    keys its substitutions on **position in that list**. So this asserts more
    than "it closes": it asserts the solver reached for the same legs and moved
    them by the same amounts, which is what says the marks survived storage.
    """
    mod = _module(slug)
    doc = _document(mod)
    want_b, want_c = solver.close(mod.build, lambda: moves.builder_for(doc))
    got_b, got_c = solver.close(lambda b: moves.replay(doc, b),
                                lambda: moves.builder_for(doc))
    assert got_b.build()["line"] == want_b.build()["line"], (
        "%s: the solved ribbon differs" % slug)
    assert ([(c["leg"], c["was"], c["now"]) for c in got_c]
            == [(c["leg"], c["was"], c["now"]) for c in want_c]), (
        "%s: the solver adjusted different legs" % slug)


def test_the_marks_the_solver_needs_survive_storage():
    """A `FREE()` is a float subclass, and JSON has no such thing.

    It has to come back as a mark rather than as an ordinary number, or the
    solver silently picks its own legs - which for Spa means lengthening the
    pit straight and producing a circuit that closes and is not Spa.
    """
    marked = [s for s in SLUGS if "FREE" in open(
        os.path.join(TRACKS_DIR, s, "track.py")).read()]
    assert marked, "no track uses FREE(); this test has stopped testing anything"
    for slug in marked:
        doc = _document(_module(slug))
        assert any(m.get("free") for m in doc["moves"]), (
            "%s uses FREE() and its document carries no marks" % slug)
        b = moves.build(doc)
        assert b._free, "%s: the marks did not reach the Builder" % slug


# -- the specific things `sections` loses ------------------------------------
def test_a_width_change_is_recorded():
    """`Builder.width()` appends nothing to `sections`. It must reach a document."""
    doc = moves.record(lambda b: b.start(run=20).straight(30)
                       .width(20.0).straight(30).finish(), width=11.0)
    widths = [m["w"] for m in doc["moves"] if "w" in m]
    assert 11 in widths and 20 in widths, widths
    line = moves.build(doc).build()["line"]
    assert {e["hw"] for e in line} == {5.5, 10.0}, "the road did not change width"


def test_a_barrier_is_recorded():
    """`Builder.rail()` appends nothing to `sections` either."""
    doc = moves.record(lambda b: b.start(run=20).straight(30)
                       .rail("lr").straight(30).finish())
    line = moves.build(doc).build()["line"]
    assert any("wl" in e for e in line), "no barrier was built"
    assert any("wl" not in e and not e.get("air") for e in line), "all walled"


def test_a_crest_is_not_recorded_as_a_hill():
    """In `sections` both are `{"t": "straight"}`. A jump is not a hill."""
    hill = moves.record(lambda b: b.start().straight(40, rise=4.0).finish())
    kick = moves.record(lambda b: b.start().crest(4.0, 40).finish())
    assert [m["t"] for m in hill["moves"]] != [m["t"] for m in kick["moves"]]
    # And the difference is real in the road: an un-eased grade marks `kick`.
    assert not any(e.get("kick") for e in moves.build(hill).build()["line"])
    assert any(e.get("kick") for e in moves.build(kick).build()["line"])


def test_checkpoints_are_in_the_document():
    """Gates live in `Builder.gates`, so `sections` has no idea where they are."""
    doc = moves.record(lambda b: b.start().straight(40).cp().straight(40).finish())
    assert [m["t"] for m in doc["moves"]].count("cp") == 1
    built = moves.build(doc).build()
    assert built["checkpoints"] == 1
    assert [g["kind"] for g in built["gates"]] == ["start", "cp", "finish"]


def test_reordering_moves_cannot_leak_a_width():
    """The whole reason width is per-move rather than sticky.

    Deleting the move that *set* a width, in a sticky model, silently rewidens
    every move after it. Here the later move carries its own width, so removing
    the earlier one changes only itself.
    """
    doc = moves.record(lambda b: b.start(run=20).straight(30)
                       .width(20.0).straight(30).finish(), width=11.0)
    wide = [m for m in doc["moves"] if m.get("w") == 20]
    assert wide, "nothing was recorded at the wider setting"
    doc["moves"] = [m for m in doc["moves"]
                    if not (m["t"] == "straight" and m.get("w") == 11)]
    line = moves.build(doc).build()["line"]
    assert 10.0 in {e["hw"] for e in line}, "the wide section lost its width"


# -- the schema cannot drift from the Builder -------------------------------
# Document field -> Builder argument, for the names that differ. `len` and
# `dir` are Python builtins/keywords as parameter names would go, and `deg`,
# `rad` and `w` are shortened because a stored document is read as JSON.
_FIELD_TO_ARG = {
    "straight": {"len": "length"},
    "crest": {"len": "length"},
    "hump": {"len": "length"},
    "gap": {"len": "length"},
    "boost": {"len": "length"},
    "bounce": {"len": "length"},
    "arc": {"deg": "degrees", "rad": "radius"},
    "loop": {"rad": "radius", "dir": "dir"},
    "jump": {},
}


@pytest.mark.parametrize("t", sorted(moves.SPEC))
def test_every_move_matches_the_builder_method_it_calls(t):
    """`SPEC` copies the Builder's defaults. Copies drift; this one cannot.

    Checked by introspection rather than by eye, so a default changed in
    `builder.py` fails here instead of quietly meaning something different in
    every stored track.
    """
    method = getattr(Builder, t)
    params = inspect.signature(method).parameters
    rename = _FIELD_TO_ARG.get(t, {})
    for field, default in moves.SPEC[t].items():
        arg = rename.get(field, field)
        assert arg in params, ("move %r has field %r, but Builder.%s takes no %r"
                              % (t, field, t, arg))
        real = params[arg].default
        if default is moves.REQ:
            assert real is inspect.Parameter.empty, (
                "%s.%s has a default (%r); SPEC says it is required"
                % (t, arg, real))
        else:
            assert real != inspect.Parameter.empty, (
                "%s.%s is required; SPEC gives it a default" % (t, arg))
            assert real == default, (
                "%s.%s defaults to %r in builder.py and %r in SPEC"
                % (t, arg, real, default))


def test_every_authored_call_a_track_uses_is_in_the_schema():
    """The vocabulary is whatever the pool actually writes, not what I remember.

    Greps the folders for `b.<call>(` and demands the schema know each one. A
    method a track uses and a document cannot express is a track that cannot be
    forked, and nothing else would say so.
    """
    import re
    used = set()
    for slug in SLUGS:
        src = open(os.path.join(TRACKS_DIR, slug, "track.py")).read()
        used.update(re.findall(r"\bb\.([a-z_]+)\(", src))
    state = {"width", "rail", "bank", "skin"}   # folded into the moves that follow
    missing = used - set(moves.SPEC) - state
    assert not missing, ("the pool uses %s, which no move expresses"
                         % ", ".join(sorted(missing)))


# -- a document from outside is not trusted ---------------------------------
def test_an_unknown_move_is_refused_by_name():
    with pytest.raises(moves.MoveError) as e:
        moves.build({"moves": [{"t": "wormhole"}]})
    assert "wormhole" in str(e.value) and "straight" in str(e.value)


def test_a_missing_required_field_is_refused():
    with pytest.raises(moves.MoveError) as e:
        moves.build({"moves": [{"t": "arc", "deg": 40}]})
    assert "rad" in str(e.value)


def test_a_field_nothing_reads_is_refused_rather_than_ignored():
    """The palette's lesson, applied here.

    `look.check` refuses an unknown key because a misspelling is not an error in
    either language - it is a setting that quietly does nothing. A move field is
    the same trap.
    """
    with pytest.raises(moves.MoveError) as e:
        moves.build({"moves": [{"t": "straight", "len": 40, "raduis": 30}]})
    assert "raduis" in str(e.value)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_number_that_is_not_a_number_is_refused(bad):
    """NaN reaches three.js as NaN and draws nothing, with no error anywhere."""
    with pytest.raises(moves.MoveError):
        moves.record(lambda b: b.start().straight(bad).finish())
