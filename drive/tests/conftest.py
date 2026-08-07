"""A budget on how long one test may take.

This exists because of a bug that cost nothing but time and was therefore invisible.
`_close_race` had an inline `eventlet.sleep(12)` - correct in production, where it
runs in a greenlet, and twelve real seconds in the two tests that called it
synchronously. That was **24s of a 56s suite**, so most of why a deploy felt slow,
and *every test passed the whole time*. There was no failure to chase: the only
symptom was the clock, and nobody reads the clock.

So the clock gets an assertion. A test that suddenly takes seconds is nearly always
one of two things - a real sleep, or a loop that grew - and both are worth being told
about at the moment they land rather than a month later.

**Failing the offending test rather than the session** is deliberate: `drive` runs
under `pytest-xdist` (`-n 4 --dist loadfile`), where `pytest_sessionfinish` runs once
per worker and an exit status set there does not reliably reach the controller. A
failed report does, and it names the culprit instead of just the total.

Mark a test `@pytest.mark.slow` to opt out. Nothing in drive needs it today - the
slowest legitimate test is `test_a_real_lap_passes_the_anti_cheat[rainbow]` at about
1.6s, so the 5s budget leaves 3x headroom - and that is the point: if something needs
the marker, that is a decision somebody should make on purpose.
"""

import pytest

# Six times the slowest honest test (`test_a_real_lap_passes_the_anti_cheat[rainbow]`,
# ~1.6s) and still under the 12s sleep that prompted this.
#
# **It was 5s, and 5s produced a false failure.** A wall-clock budget is sensitive to
# whatever else the machine is doing: with a stuck earlier run competing for cores,
# the rainbow sim went from 1.6s to over 5s and this guard failed it. Nothing was
# wrong with the test. CI runners are noisy in exactly that way, and a guard that
# fails a deploy for load is worse than the slow suite it was added to prevent.
#
# 10s keeps the thing it was for - a real sleep is a second or more, and the one that
# started this was twelve - while leaving enough room that ordinary contention cannot
# trip it. If it ever false-fails again, raise it rather than deleting it, or mark the
# offending test `slow`.
SLOW_TEST_BUDGET_S = 10.0


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: this test is allowed to exceed the per-test time budget")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    if report.when != "call" or not report.passed:
        return                       # a failure already has something to say
    if item.get_closest_marker("slow"):
        return
    if report.duration > SLOW_TEST_BUDGET_S:
        report.outcome = "failed"
        report.longrepr = (
            f"{item.nodeid} took {report.duration:.2f}s, over the "
            f"{SLOW_TEST_BUDGET_S:.0f}s per-test budget.\n\n"
            "Almost always a real sleep on a code path a test calls synchronously "
            "(see _close_race / RESULTS_HOLD_S in app.py for the one that prompted "
            "this budget), or a loop that grew.\n"
            "If the test genuinely needs the time, mark it @pytest.mark.slow and "
            "say why."
        )
