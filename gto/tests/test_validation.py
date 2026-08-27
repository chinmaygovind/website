"""The checks in ``validate.py``, run for real.

Marked ``validation`` and deselected by default for one reason: they need
``eval7``, which is a **test-only** dependency this box installs and production
does not. Everything else about them is cheap - the whole suite is four seconds.

They are the only tests in this directory that compare this code against
somebody else's, and that makes them the only ones that can catch a number that
has been wrong since the first commit. ``tests/`` otherwise checks this project
against itself, which cannot.
"""

import pytest

import validate

pytestmark = pytest.mark.validation


@pytest.fixture(scope="module")
def checks():
    if not validate.available():
        pytest.skip("eval7 is not installed")
    return {c["name"]: c for c in validate.run_all(quick=True)}


def test_nothing_disagrees_with_the_outside_world(checks):
    failed = [c for c in checks.values() if c["status"] == "fail"]
    assert not failed, "\n".join(f"{c['name']}: {c['detail']}" for c in failed)


def test_the_reference_this_file_checks_against_is_itself_right(checks):
    # If this one is wrong every row below it is wrong in the same direction and
    # all of them still say "pass", which is the worst failure mode a page
    # called "are these numbers right" could have.
    c = checks["The reference itself"]
    assert c["status"] == "pass", c["detail"]


def test_the_evaluator_orders_hands_the_way_eval7_does(checks):
    c = checks["Hand ranking"]
    assert c["status"] == "pass"
    assert c["worst"] == 0, f"{c['worst']} pairs ordered differently"


def test_exact_equity_is_exact_to_the_last_float(checks):
    for name in ("Hand versus hand", "Equity per holding"):
        c = checks[name]
        assert c["status"] == "pass", c["detail"]
        assert c["worst"] == 0.0, f"{name}: off by {c['worst']} points"


def test_the_sampler_lands_inside_the_error_bar_it_prints(checks):
    c = checks["Hand versus range"]
    assert c["status"] == "pass", c["detail"]
    assert c["worst"] <= 3.0


def test_a_chart_labelled_solver_opens_as_often_as_the_solve_it_names(checks):
    c = checks["Opening ranges"]
    assert c["status"] == "pass", (
        "an opening range labelled `solver` is off the published frequency by "
        f"{c['worst']:.1f} points: " + str(c["rows"]))


def test_the_postflop_comparison_reports_itself_as_not_run(checks):
    # It is not written and it must not read as passing. This test exists so
    # that the day somebody makes it green, they have to come here and say so.
    c = checks["Postflop strategy"]
    assert c["status"] == "not run"
    assert "TexasSolver" in c["detail"] or "TEXASSOLVER" in c["detail"]


def test_the_committed_report_matches_what_the_checks_say_now():
    """A stale report may be old; it may not be wrong about a pass."""
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "validation.json")
    if not os.path.exists(path):
        pytest.skip("no report generated")
    with open(path) as fh:
        report = json.load(fh)
    live = {c["name"]: c["status"] for c in validate.run_all(quick=True)}
    for c in report["checks"]:
        assert live.get(c["name"]) == c["status"], (
            f"{c['name']}: the page says {c['status']}, running it now says "
            f"{live.get(c['name'])}. Regenerate with "
            f"tools/validate_report.py.")
