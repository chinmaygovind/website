"""Run the checks in ``validate.py`` and write the report the page renders.

Run from ``gto/``::

    venv/bin/python tools/validate_report.py

**This is deliberately offline rather than a live route.** The checks need
``eval7``, which is a test-only dependency and is not installed in production -
and the full run is four seconds, which is not a page load. So the numbers are
generated here, committed, and rendered from the file, with the commit they were
generated at printed beside them so a stale report is visible as a stale report
rather than as a current one.

The claims themselves do not rest on the file: ``tests/test_validation.py`` runs
the same checks live, so a chart edited into disagreement fails the suite whether
or not anybody regenerated this.
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import validate  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "validation.json")


def _commit():
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True,
            text=True, check=True).stdout.strip()
    except Exception:
        return ""


def main():
    checks = validate.run_all()
    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "commit": _commit(),
        "summary": validate.summary(checks),
        "checks": checks,
    }
    with open(OUT, "w") as fh:
        json.dump(report, fh, indent=1, sort_keys=False)
        fh.write("\n")
    s = report["summary"]
    print(f"{OUT}: {s['passed']} passed, {s['failed']} failed, "
          f"{s['not_run']} not run")
    return 1 if s["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
