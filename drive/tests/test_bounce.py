"""Mushroom caps: what a cap does to a car, and who else has to know.

Written to the shape of `test_boost.py`, because a bounce surface is the same
*kind* of thing as a boost pad and the three places it can silently break are the
same three files.

The **rule** - a cap reflects the landing instead of absorbing it, hands back the
larger of a floor and a restitution, and then goes quiet for a moment - is in
physics.js, and it is run here for real in QuickJS on the real track. Like a pad
and unlike the slipstream, this cannot be tested on a car in a vacuum: a cap is
noticed by the ground query, so the car has to be on one.

The **authoring** - that `Builder.bounce` flags the stations it lays and that
those and only those come out of `buildTrack` as `KIND.BOUNCE` - is the join
between tracks/builder.py and trackmesh.js. A drift there is a mushroom you can
see and not bounce on, or one you bounce on and cannot see.

The **medals** - that laptime.py knows a cap is not ordinary road - is the part
that would fail silently, and it is the reason for the last group. A cap modelled
as tarmac gets a cornering limit and a full engine term over a disc the car is
airborne above, which is exactly the shape of the bug that made four of Big Red's
pads worth 0.29s instead of 1.8 while every other test passed.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import laptime
import tracks as tracks_mod
import tuning as T

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

HARNESS = """
// Shroom Street is the only track in the pool with caps on it, which is the
// point: these read the real thing rather than a fixture that could be right
// while the track is wrong.
var TRACK = TRACKS.find(t => t.slug === 'shroom');
var BUILT = buildTrack(TRACK, T);

function firstCap() {
  return TRACK.line.findIndex(e => e.bn);
}

// A car `up` units above station `si`, pointing down the road at `speed`, with
// `fall` of downward velocity already on it. `up` is how the arrival is staged:
// resting on the cap (0.05) is the "rolled onto one" case, and twenty units up
// is the "fell onto one" case.
function over(si, up, speed, fall) {
  const e = TRACK.line[si], f = TRACK.line[si + 1];
  const d = [f.p[0] - e.p[0], f.p[1] - e.p[1], f.p[2] - e.p[2]];
  const m = Math.hypot(d[0], d[1], d[2]);
  const fwd = [d[0] / m, d[1] / m, d[2] / m];
  const c = new Car(T, BUILT);
  c.placeAt(e.p, fwd);
  c.pos.y += up;
  c.vel.set(fwd[0] * speed, -(fall || 0), fwd[2] * speed);
  c.bounces = 0;
  c.lastOut = 0;
  c.onBounce = (out) => { c.bounces++; c.lastOut = out; };
  c.landed = 0;
  c.onLand = () => { c.landed++; };
  return c;
}

// Step for `secs` and report the largest *upward* velocity seen, which is the
// only honest measure of what a cap gave the car - reading vel.y on some chosen
// step samples whatever gravity has already taken off it.
function fly(c, secs, inp) {
  const dt = T.FIXED_DT, n = Math.round(secs / dt);
  let up = -Infinity, top = -Infinity;
  const y0 = c.pos.y;
  for (let i = 0; i < n; i++) {
    c.step(dt, inp || { throttle: 1 });
    if (c.vel.y > up) up = c.vel.y;
    if (c.pos.y - y0 > top) top = c.pos.y - y0;
  }
  return { up, rise: top, bounces: c.bounces, out: c.lastOut,
           landed: c.landed, surface: c.surface };
}
"""


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    r.eval(HARNESS)
    return r


@pytest.fixture(scope="module")
def cap_i(rt):
    """The index of the first mushroom-cap station on Shroom Street."""
    return rt.call("firstCap()")


# ---------------------------------------------------------------------------
# What a cap does
# ---------------------------------------------------------------------------

def test_the_track_actually_has_caps_on_it(rt, cap_i):
    """Everything below reads the real track, so this is the load-bearing one."""
    assert cap_i > 0, "Shroom Street is supposed to be the track with the caps"


def test_a_cap_is_a_bounce_surface_underfoot(rt, cap_i):
    r = rt.call("fly(over(%d, 0.05, 30, 0), 0.02)" % cap_i)
    assert r["surface"] == 4, "KIND.BOUNCE is 4; the car should be standing on it"


def test_rolling_onto_a_cap_still_throws_you(rt, cap_i):
    """The floor, and the reason there are two numbers rather than one.

    A car arriving level has no normal velocity to reflect, so a pure
    restitution would hand it nothing at all - and the caps a player is slowest
    onto are precisely the ones they most need to leave.
    """
    r = rt.call("fly(over(%d, 0.05, 30, 0), 1.2)" % cap_i)
    assert r["bounces"] >= 1, "a car on a cap should be thrown by it"
    assert r["up"] > T.BOUNCE_VEL * 0.9, \
        "a level arrival should still get about the full BOUNCE_VEL"


def test_a_cap_throws_you_about_as_high_as_the_arithmetic_says(rt, cap_i):
    """v^2 / 2g off a flat cap, which is what the constant was sized against.

    Checked as *height* rather than as velocity because height is what the track
    is authored around - the gaps between caps are sized off this number.
    """
    r = rt.call("fly(over(%d, 0.05, 30, 0), 1.4)" % cap_i)
    want = T.BOUNCE_VEL ** 2 / (2 * T.GRAVITY)
    assert r["rise"] == pytest.approx(want, rel=0.35), \
        "a cap should peak near %.1f units up, got %.1f" % (want, r["rise"])


def test_falling_onto_a_cap_harder_throws_you_higher(rt, cap_i):
    """The restitution half. Past about a seven-unit fall the reflection beats
    the floor, which is what gives a chain of caps a rhythm instead of a pitch."""
    soft = rt.call("fly(over(%d, 3, 30, 6), 1.6)" % cap_i)
    hard = rt.call("fly(over(%d, 30, 30, 30), 2.2)" % cap_i)
    assert hard["out"] > soft["out"] * 1.2, \
        "a hard arrival (%.1f) should out-throw a gentle one (%.1f)" % (
            hard["out"], soft["out"])


def test_a_cap_hands_back_the_larger_of_the_two_and_never_the_sum(rt, cap_i):
    """Summing them makes the cap at the bottom of the biggest drop the one that
    fires you somewhere unrecoverable - which is the cap a player has the least
    control over arriving at. Same rule as a pad and a tow.

    Checked at both ends, because each end pins a different half of `max`. A
    gentle arrival must come out at **exactly** the floor with nothing added, and
    a hard one at **exactly** the reflection with no floor on top - and the
    impact speed for the second has to be worked out from the whole fall
    (`v^2 = v0^2 + 2gh`), not from the velocity the car was launched with. Doing
    that arithmetic the lazy way is what made this test wrong the first time,
    not the physics.
    """
    gentle = rt.call("fly(over(%d, 2, 30, 0), 1.5)" % cap_i)
    assert gentle["out"] == pytest.approx(T.BOUNCE_VEL, rel=0.02), \
        "a gentle arrival should be the bare floor, got %.2f" % gentle["out"]

    fall, drop = 34.0, 40.0
    hard = rt.call("fly(over(%d, %d, 30, %d), 2.4)" % (cap_i, drop, fall))
    impact = math.sqrt(fall * fall + 2 * T.GRAVITY * drop)
    assert hard["out"] == pytest.approx(impact * T.BOUNCE_REST, rel=0.08), \
        "a hard arrival should be the bare reflection of %.1f u/s, got %.2f" % (
            impact, hard["out"])
    assert hard["out"] < T.BOUNCE_VEL + impact * T.BOUNCE_REST * 0.9, \
        "the launch looks like a sum of the floor and the reflection"


def test_a_cap_goes_quiet_for_a_moment_rather_than_re_arming(rt, cap_i):
    """The opposite rule to a boost pad's, and it has to be.

    A pad re-arms while you stay on it, so a long pad holds the engine open all
    the way up Mount Joy's ramp. A cap must not: `grounded` survives COYOTE and
    the ground probe reaches PROBE units, so a re-arming cap would top the car's
    normal velocity back up every step for as long as it could still see the
    surface - a car pinned to a launch speed rather than thrown by it, and about
    eight callbacks for one hop.
    """
    r = rt.call("fly(over(%d, 0.05, 34, 0), 0.5)" % cap_i)
    assert r["bounces"] == 1, \
        "one contact should fire exactly one bounce, got %d" % r["bounces"]


def test_a_cap_does_not_also_report_a_landing(rt, cap_i):
    """Two sounds and two camera kicks for one event, and the louder of the two
    is the impact - so a hop off a real drop would read as hitting the mushroom
    rather than as being thrown by it."""
    r = rt.call("fly(over(%d, 30, 30, 26), 1.0)" % cap_i)
    assert r["bounces"] >= 1
    assert r["landed"] == 0, "a cap fired onLand as well as onBounce"


def test_a_cap_never_slows_a_car_that_is_already_leaving_faster(rt, cap_i):
    """The guard on the assignment. Without it a cap clipped on the way up is a
    brake, which is the one thing a mushroom must never be."""
    r = rt.call("fly(over(%d, 0.05, 30, -34), 0.4)" % cap_i)
    assert r["up"] >= 33, \
        "a car already climbing at 34 left the cap at %.1f" % r["up"]


# ---------------------------------------------------------------------------
# The authoring join
# ---------------------------------------------------------------------------

def test_a_flagged_station_is_a_bounce_surface_and_nothing_else_is(rt):
    """`Builder.bounce` and `KIND.BOUNCE` have to describe the same mushroom.

    Guards the same failure the boost test does - a cap you can see and cannot
    bounce on, or one you bounce on with no red disc under you - but **not** with
    the boost test's arithmetic, and the difference is a real fact about caps
    rather than a fudge to make a number line up.

    A pad's stations are `flagged * 2` triangles because a pad is laid in the
    middle of a road and every flagged station has road after it. A cap is
    followed by a *gap*, and `buildTrack` skips the quad between any pair where
    either end is `air` - so the last station of every cap lays no road at all
    and each run of k stations is k-1 quads. That is why the run count is in here:
    it pins the structure ("a cap ends at a hole") as well as the flagging.
    """
    r = rt.call("""(() => {
      const col = BUILT.collider || BUILT.col;
      const line = TRACK.line;
      let flagged = 0, runs = 0, tris = 0;
      for (let i = 0; i < line.length; i++) {
        if (!line[i].bn) continue;
        flagged++;
        if (i === 0 || !line[i - 1].bn) runs++;
      }
      for (let i = 0; i < col.k.length; i++) if (col.k[i] === KIND.BOUNCE) tris++;
      return { flagged, runs, tris };
    })()""")
    assert r["flagged"] > 0
    assert r["runs"] == 4, "Shroom Street has three caps over the gorge, then one"
    assert r["tris"] == (r["flagged"] - r["runs"]) * 2


def test_no_cap_is_also_a_boost_pad():
    """Both are `KIND`s of the same quad and a station carrying both flags would
    get whichever the ternary in `buildTrack` happens to test first - which is a
    silent, layout-dependent answer to "what is this surface"."""
    for t in tracks_mod.TRACKS:
        for i, e in enumerate(t["line"]):
            assert not (e.get("bn") and e.get("bp")), \
                "%s station %d is both a cap and a pad" % (t["slug"], i)


def test_a_cap_is_never_a_gate_and_never_profiled():
    """A gate is a flat plane of fixed width, and a cap is 20 wide where the road
    is 13 - so a checkpoint on one puts its posts out in the air off the side of
    the mushroom. `_gate` already refuses a profiled station; this is the same
    statement for a bounce surface, which it cannot see."""
    for t in tracks_mod.TRACKS:
        caps = {i for i, e in enumerate(t["line"]) if e.get("bn")}
        if not caps:
            continue
        for g in t["gates"]:
            assert g["gi"] not in caps, "%s has a gate on a cap" % t["slug"]
        for i in caps:
            assert not t["line"][i].get("pf"), \
                "%s station %d is a profiled cap" % (t["slug"], i)


# ---------------------------------------------------------------------------
# The medals
# ---------------------------------------------------------------------------

def test_laptime_does_not_drive_a_cap_like_tarmac():
    """A cap modelled as road gets a cornering limit and a full engine term over a
    disc the car is in contact with for one physics step out of roughly a hundred
    and seventy. Both of those are wrong, and they pull in opposite directions.

    **The cornering limit is the one that dominates, and it goes the way round
    that surprises you.** Modelled as road the lap comes out 3.6s *slower*, not
    faster - because the gaps either side of a cap are bowed, `_corner_speed`
    measures curvature on the 3D racing line, and the bow's **vertical** bend
    reads as a tight corner. So the model was braking hard at the entry to every
    mushroom for a bend that is the car going up and coming down, which is
    exactly the failure Big Red's main jump has a note about, arriving at a
    different place by the same route.

    Treating a cap as free flight fixes it, and is also just true: a ballistic car
    is not limited by cornering grip, because it has none. The test therefore
    asserts the flag *matters* and asserts the direction, since a change that
    made the lap slower would mean the curvature cap had crept back in.
    """
    t = next(x for x in tracks_mod.TRACKS if x["slug"] == "shroom")
    _, _, real = laptime.speed_profile(t)
    stripped = dict(t)
    stripped["line"] = [{k: v for k, v in e.items() if k != "bn"}
                        for e in t["line"]]
    _, _, as_road = laptime.speed_profile(stripped)
    assert abs(real - as_road) > 0.5, (
        "the caps changed the ideal lap by only %.3fs - laptime.py is probably "
        "not reading `bn` at all" % abs(real - as_road))
    assert real < as_road, (
        "modelling the caps as free flight made the lap slower (%.2f vs %.2f), "
        "which means something is still applying a cornering limit to them"
        % (real, as_road))


@pytest.mark.slow
def test_the_cap_model_changes_nothing_on_a_track_without_any():
    """The seventeen tracks that predate this have to be untouched, the same way
    the boost loop had to be a no-op on the twelve that predated pads.

    **Marked `slow`, and it is the first test in drive to need it.** This relaxes
    and speed-profiles the whole pool twice - 34 of the most expensive thing in
    `laptime.py` - so it costs 4.6s on a laptop and 11.7s on a slow CI runner,
    where it tripped the 10s per-test budget one run after passing on a runner
    that did the same suite 25% quicker. It is neither of the two things that
    budget is looking for: no sleep, and the loop is O(pool) on purpose. Raising
    the budget instead would have been the wrong lever - 10s is deliberately
    under the 12s sleep that prompted it, so a budget loose enough for this test
    could no longer catch that. See `tests/conftest.py`.
    """
    for t in tracks_mod.TRACKS:
        if any(e.get("bn") for e in t["line"]):
            continue
        _, _, before = laptime.speed_profile(t)
        stripped = dict(t)
        stripped["line"] = [{k: v for k, v in e.items() if k != "bn"}
                            for e in t["line"]]
        _, _, after = laptime.speed_profile(stripped)
        assert before == pytest.approx(after, abs=1e-9), \
            "%s moved and it has no caps on it" % t["slug"]


def test_every_cap_is_wide_enough_to_land_on():
    """Hang time is fixed by BOUNCE_VEL, so reach scales with the speed you leave
    with and the touchdown point moves nineteen units across the realistic range.
    A cap therefore has to be a *zone*, and the pool's own lesson about this is
    Big Red's 46-unit landing straight that a fast entry flew clean over.
    """
    for t in tracks_mod.TRACKS:
        line = t["line"]
        i = 0
        while i < len(line):
            if not line[i].get("bn"):
                i += 1
                continue
            j = i
            while j + 1 < len(line) and line[j + 1].get("bn"):
                j += 1
            span = math.dist(line[i]["p"], line[j]["p"])
            assert span > 18.0, \
                "%s: a cap only %.0f units long is a point, not a landing" % (
                    t["slug"], span)
            assert line[i]["hw"] * 2 >= 16.0, \
                "%s: a %.0f-wide cap is aimed at out of the air with AIR_STEER" % (
                    t["slug"], line[i]["hw"] * 2)
            i = j + 1
