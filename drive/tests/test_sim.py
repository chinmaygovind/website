"""Drive the game, headlessly, through its own JavaScript.

These are the tests that matter most. The car, the collider and the run logic live
in .js because they have to run in a browser, so `jsrt` bundles the real modules
and runs them in QuickJS with a stubbed three.js (see `three_stub.js`). Nothing
here is a Python re-implementation - a failure means the code that ships is
broken.

Between them these caught: road and grass being coplanar so the car thought it was
on grass for whole laps; every ramp crest launching the car; wall collision
geometry being double-sided so contacts fired twice with opposing normals; loops
folding back onto themselves tightly enough to trap a car forever; checkpoint
planes being tracked across the whole map so legitimate passes went unnoticed; and
four tracks that simply could not be finished.

Requires the optional `quickjs` package (`pip install quickjs`); skipped without
it so a plain deploy install still works.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import laptime
import tuning as T

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.tracks = r.load_tuning_and_tracks()
    return r


def _sim(rt, slug, max_t=90):
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == slug)
    return rt.call("simulate(TRACKS[%d], T, {maxT:%d})" % (i, max_t))


def all_slugs():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import tracks
    return [t["slug"] for t in tracks.TRACKS]


SLUGS = all_slugs()


@pytest.mark.parametrize("slug", SLUGS)
def test_the_track_can_be_driven_to_the_finish(rt, slug):
    """The whole point: a track nobody can finish is a broken track."""
    r = _sim(rt, slug)
    assert r["finished"], (
        f"{slug} not finished: {r['cps']}/{r['needCps']} checkpoints, "
        f"{r['progress'] * 100:.0f}% of the way round, {r['respawns']} respawns")
    assert r["cps"] == r["needCps"]
    assert r["splits"] == sorted(r["splits"]) and len(r["splits"]) == r["needCps"]


@pytest.mark.parametrize("slug", SLUGS)
def test_a_clean_lap_needs_no_respawns(rt, slug):
    """Falling off is a mistake, not something the track should force on you."""
    r = _sim(rt, slug)
    assert r["respawns"] == 0, f"{slug} forced {r['respawns']} respawns"


@pytest.mark.parametrize("slug", SLUGS)
def test_the_car_stays_on_the_road_when_it_should(rt, slug):
    """Air time is for jumps. Anywhere else it means the car is being launched
    off ramp crests - the bug the suspension model exists to prevent."""
    r = _sim(rt, slug)
    limit = 0.40 if slug == "jumpcity" else 0.20
    assert r["airFraction"] < limit, \
        f"{slug} spent {r['airFraction'] * 100:.0f}% of the lap airborne"


@pytest.mark.parametrize("slug", SLUGS)
def test_lap_times_are_in_a_sane_range(rt, slug):
    r = _sim(rt, slug)
    secs = r["time"] / 1000.0
    assert 8 < secs < 90, f"{slug} took {secs:.1f}s"
    assert 12 < r["avgSpeed"] < T.MAX_SPEED, \
        f"{slug} averaged {r['avgSpeed']:.0f} u/s - crawling or teleporting"


def test_ideal_lap_matches_the_simulated_driver(rt):
    """Pins laptime.CALIBRATION against what the car actually does.

    The medal times are cut from `laptime.ideal_lap`, so if a retune moves the
    relationship between the quasi-static estimate and reality, that has to
    surface here rather than as silently wrong medals.
    """
    ratios = []
    for slug in SLUGS:
        driven = _sim(rt, slug)["time"] / 1000.0
        raw = laptime.raw_lap(rt.tracks.get(slug))
        ratios.append(driven / raw)
    mean = sum(ratios) / len(ratios)
    assert abs(mean - laptime.CALIBRATION) < 0.06, (
        f"the driver is now {mean:.2f} of the raw estimate but CALIBRATION is "
        f"{laptime.CALIBRATION} - retune it and the medals move with it")


@pytest.mark.parametrize("slug", SLUGS)
def test_medals_bracket_the_simulated_driver(rt, slug):
    """Author should be about as hard as the test driver or harder; bronze should
    be comfortable."""
    driven = _sim(rt, slug)["time"] / 1000.0
    m = rt.tracks.get(slug)["medals"]
    assert m["author"] < driven * 1.10, f"{slug}: author medal is too generous"
    assert m["bronze"] > driven, f"{slug}: bronze medal is not achievable"


def test_the_car_goes_all_the_way_round_a_loop_upside_down(rt):
    """Straight-line run into a loop: it has to inverta and stay on the road.

    Steering is applied about the *surface* normal rather than world up, which is
    the whole reason a loop needs no special case anywhere in the car code.
    """
    rt.eval("""
    function loopRun(track, T) {
      const built = buildTrack(track, T);
      const course = new Course(built);
      const car = new Car(T, built);
      // start on the boost pad before the first loop
      const idx = track.line.findIndex(e => e.loop) - 2;
      const p = track.line[idx].p, tan = course.tangent(idx);
      car.placeAt(p, tan);
      car.vel.set(tan[0]*45, tan[1]*45, tan[2]*45);
      let minUp = 1, maxY = -1e9, airFrames = 0, frames = 0;
      for (let t = 0; t < 3; t += T.FIXED_DT) {
        car.step(T.FIXED_DT, {throttle: 1, brake: 0, steer: 0, handbrake: false});
        frames++;
        if (!car.grounded) airFrames++;
        if (car.up.y < minUp) minUp = car.up.y;
        if (car.pos.y > maxY) maxY = car.pos.y;
      }
      return {minUp, maxY, airFraction: airFrames/frames, speed: car.speed};
    }
    """)
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "lagoon")
    r = rt.call("loopRun(TRACKS[%d], T)" % i)
    assert r["minUp"] < -0.85, f"the car never went properly inverted (min up.y {r['minUp']:.2f})"
    assert r["maxY"] > 15, f"the car only reached {r['maxY']:.1f} up the loop"
    assert r["airFraction"] < 0.15, "the car came off the loop surface"
    assert r["speed"] > 5, "the car stalled in the loop"


def test_the_collider_finds_the_road_not_the_grass(rt):
    """Level-0 road and the ground plane used to be coplanar, so this query was a
    coin toss and the car spent whole laps behaving like it was on grass."""
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "sunrise")
    rt.eval("""
    function surfaceUnderLine(track, T) {
      const built = buildTrack(track, T);
      let road = 0, other = 0, missing = 0;
      for (const e of track.line) {
        if (e.air || e.loop) continue;
        const g = built.collider.ground(e.p[0], e.p[1] + T.RIDE_HEIGHT, e.p[2], 0, 1, 0, 3);
        if (!g.hit) missing++;
        else if (g.kind === KIND.ROAD || g.kind === KIND.BOOST) road++;
        else other++;
      }
      return {road, other, missing};
    }
    """)
    r = rt.call("surfaceUnderLine(TRACKS[%d], T)" % i)
    assert r["missing"] == 0, "part of the driving line has no surface under it"
    assert r["road"] > 20
    # A handful of samples sit right on a corner's inside pivot, where the road
    # narrows to a point and the grass beside it is genuinely the nearest surface.
    # What matters is that the road wins essentially everywhere.
    assert r["other"] / (r["road"] + r["other"]) < 0.15, \
        f"{r['other']} of {r['road'] + r['other']} line points report grass, not road"


# ---------------------------------------------------------------------------
# Car-to-car contact
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("closing", [4, 12, 25])
def test_cars_separate_smoothly_without_jitter(rt, closing):
    """The Mario-Kart-style contact rules, measured.

    Two cars are driven into each other side-on and the separation between them is
    watched every step. Impulse-plus-spring resolution should push them apart in
    one smooth motion; positional snapping (the thing this deliberately avoids)
    shows up as the gap flip-flopping between growing and shrinking every frame.
    """
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "sunrise")
    r = rt.call("bumpTest(TRACKS[%d], T, %d)" % (i, closing))
    assert r["contacts"] > 0, "the cars never actually touched"
    # The spring holds them apart instead of letting them pass through each other.
    # It does not have to fling them apart - a gentle rub should stay a rub.
    assert r["minSep"] > T.CAR_RADIUS * 2 * 0.72, \
        f"cars interpenetrated to {r['minSep']:.2f} (contact starts at {T.CAR_RADIUS * 2:.2f})"
    # a smooth resolution reverses direction only a handful of times; positional
    # snapping shows up as the gap flip-flopping every frame
    assert r["signChanges"] < 12, \
        f"separation oscillated {r['signChanges']} times - that is jitter"


@pytest.mark.parametrize("closing", [4, 12, 25])
def test_a_bump_never_launches_or_flips_a_car(rt, closing):
    """Contact is a shove, not a catapult - vertical response is damped hard."""
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "sunrise")
    r = rt.call("bumpTest(TRACKS[%d], T, %d)" % (i, closing))
    assert r["aUpright"] > 0.8 and r["bUpright"] > 0.8, "a bump rolled a car over"
    assert abs(r["aY"] - r["bY"]) < 2.0, "a bump threw one car into the air"


def test_a_bump_costs_speed_but_not_the_race(rt):
    """A firm hit scrubs some speed; it must not stop the car dead."""
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "sunrise")
    r = rt.call("bumpTest(TRACKS[%d], T, 25)" % i)
    assert r["aSpeed"] > 12 and r["bSpeed"] > 12, "a bump nearly stopped a car"


def test_light_contact_is_quieter_than_a_punt(rt):
    """Rubbing along someone should not read as a crash."""
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "sunrise")
    light = rt.call("bumpTest(TRACKS[%d], T, 2)" % i)
    hard = rt.call("bumpTest(TRACKS[%d], T, 30)" % i)
    assert light["peakSepRate"] < hard["peakSepRate"], \
        "a gentle rub separates as violently as a full punt"
