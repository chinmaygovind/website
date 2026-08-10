"""Solve Spa's two free straights so the ribbon closes on itself.

Spa is the one closed circuit in the pool: the last station has to land back on
station 0 with the heading it started with, or the join is a step in the road
and `self_proximity` reads it as the worst car trap on the track.

Its corner angles are fixed and sum to exactly 360, so the heading closes by
construction. That leaves the *position*, which is two equations - and so two
free lengths: the Kemmel straight and the run out of Stavelot. They are the two
long legs of the circuit's triangle and point in very different directions, so
the solve is well conditioned.

This drives the real ``tracks.Builder`` rather than a model of it. An earlier
version reimplemented the turtle in the plan view and got the handedness of
``_frame`` backwards, which closed perfectly in the model and left the actual
ribbon 66 units out. There is no second copy of the kinematics now.

Run it after changing ANY length or angle in ``_spa``, and paste the two numbers
it prints into that function's defaults::

    python tools/close_spa.py
"""
import math
import sys

sys.path.insert(0, __file__.rsplit("/", 2)[0])

import tracks  # noqa: E402


def residual(p):
    """(dx, dz) between where the ribbon ends and where it started."""
    b = tracks._spa(kemmel=p[0], stav=p[1])
    start = b.nodes[0]["p"]
    return [b.x - start[0], b.z - start[2]]


def solve(p0, tol=1e-7, iters=60):
    p = list(p0)
    for _ in range(iters):
        r = residual(p)
        if max(abs(v) for v in r) < tol:
            break
        # 2x2 finite-difference Jacobian, then Cramer.
        h = 1e-4
        cols = []
        for k in range(2):
            q = list(p)
            q[k] += h
            rq = residual(q)
            cols.append([(rq[i] - r[i]) / h for i in range(2)])
        det = cols[0][0] * cols[1][1] - cols[1][0] * cols[0][1]
        if abs(det) < 1e-12:
            raise SystemExit("singular Jacobian - the two free straights are parallel")
        b0, b1 = -r[0], -r[1]
        d0 = (b0 * cols[1][1] - cols[1][0] * b1) / det
        d1 = (cols[0][0] * b1 - b0 * cols[0][1]) / det
        p[0] += d0
        p[1] += d1
    return p


def report(p):
    b = tracks._spa(kemmel=p[0], stav=p[1])
    start = b.nodes[0]["p"]
    dx, dz = b.x - start[0], b.z - start[2]
    dy = b.y - start[1]
    dyaw = math.degrees(b.yaw) - 360.0
    ln = sum(math.dist(b.nodes[i]["p"], b.nodes[i + 1]["p"])
             for i in range(len(b.nodes) - 1))
    print(f"kemmel = {p[0]:.2f}")
    print(f"stav   = {p[1]:.2f}   (A {p[0] and p[1] * 0.55:.2f} / B {p[1] * 0.45:.2f})")
    print()
    print(f"seam    dx={dx:+.4f}  dy={dy:+.4f}  dz={dz:+.4f}")
    print(f"heading {dyaw:+.6f} deg off 360 (0 is closed)")
    print(f"length  {ln:.0f} units over {len(b.nodes)} stations")


if __name__ == "__main__":
    report(solve([220.80, 305.38]))
