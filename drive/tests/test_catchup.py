"""Catching up: how much engine a car behind gets, and when it gets any at all.

The same shape as `test_slipstream.py`, because it is the same shape of feature
and the parts live in the same two files.

The *curve* - a deadzone, a linear ramp, and a smoothed follow rather than an
exact one - is `Car.catchup` in physics.js, run here for real in QuickJS. It
touches nothing but the body's own state and the number it is handed, so it
needs no world, no lap and no rivals.

The *gate* and the *gap* are game.js: `catchupOn` says this is the race and not
practice, qualifying or a results sheet, and `gapToLeader` turns everyone's
distance round the track into the one number the curve reads. Both are lifted
out of the file by name and run against a stub, the trick `test_touch.py`,
`test_slipstream.py` and `test_rules_js.py` all use.

Two of these are about the mechanic being *small*: it multiplies the same
throttle term the tow does, so the two stack, and the pair of them still has to
land under the hard velocity clamp - otherwise the clamp is what sets the top
speed and the tuning is decoration.
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt
import tuning as T

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

HARNESS = """
// A car with nothing under it: `catchup` reads the gap it is handed and its own
// previous value, and touches neither the world nor any rival.
function behind() {
  const c = new Car(T, {});
  c.placeAt([0, 0, 0], [0, 0, -1]);
  return c;
}
// Hold a gap for `seconds` and report where the help settled.
function hold(car, gap, seconds) {
  const dt = T.FIXED_DT;
  const n = Math.round(seconds / dt);
  for (let i = 0; i < n; i++) car.catchup(gap, dt);
  return car.catchupBoost;
}
"""

# Long enough for the smoothing to have arrived: CATCHUP_SMOOTH is a rate, so
# five time constants is within a percent of the target.
SETTLED = 5.0 / T.CATCHUP_SMOOTH


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    r.eval(HARNESS)
    return r


def _hold(rt, gap, seconds=SETTLED):
    return rt.call("hold(behind(), %s, %s)" % (gap, seconds))


@pytest.mark.parametrize("gap,why", [
    ("null", "not a race"),
    ("0", "you are the leader"),
    ("T.CATCHUP_DEAD * 0.9", "close enough to still be racing them"),
    ("T.CATCHUP_DEAD", "exactly on the line"),
])
def test_nothing_at_all_inside_the_deadzone(rt, gap, why):
    """A gap you can still see is a gap you close yourself."""
    assert _hold(rt, gap) == 0, why


def test_it_ramps_with_the_gap_and_stops_at_full(rt):
    """Linear between the two, and no more past the far end of it."""
    half = (T.CATCHUP_DEAD + T.CATCHUP_FULL) / 2
    quarter = T.CATCHUP_DEAD + (T.CATCHUP_FULL - T.CATCHUP_DEAD) * 0.25

    assert _hold(rt, quarter) == pytest.approx(0.25, abs=0.02)
    assert _hold(rt, half) == pytest.approx(0.5, abs=0.02)
    assert _hold(rt, T.CATCHUP_FULL) == pytest.approx(1.0, abs=0.02)
    # A minute down the road is not worth more than the whole of it.
    assert _hold(rt, T.CATCHUP_FULL * 10) == pytest.approx(1.0, abs=0.02)


def test_a_gap_just_past_the_deadzone_still_gets_off_the_floor(rt):
    """The tail of the ramp-down is snapped to zero, and that snap is one
    character away from eating every ramp *up* as well - each of those starts at
    zero and climbs through the same hundredth, so a snap that did not check
    which way it was going pinned the help at nothing for ever."""
    just_past = T.CATCHUP_DEAD + (T.CATCHUP_FULL - T.CATCHUP_DEAD) * 0.05
    assert _hold(rt, just_past) == pytest.approx(0.05, abs=0.02)


def test_the_help_follows_the_gap_rather_than_tracking_it(rt):
    """The gap arrives 30 times a second, rounded, off an extrapolated car.

    Reading it exactly would put a step change in engine force every time it
    wobbled. It is smoothed instead, so a gap that appears is worth most of
    itself within about a second and none of itself instantly.
    """
    instant = _hold(rt, T.CATCHUP_FULL, T.FIXED_DT * 2)
    assert instant < 0.1
    soon = _hold(rt, T.CATCHUP_FULL, 1.0)
    assert 0.7 < soon < 1.0


def test_taking_the_lead_bleeds_it_away(rt):
    """And so does the race ending, which is the same call with null."""
    r = rt.call("""(() => {
      const c = behind();
      hold(c, T.CATCHUP_FULL, %s);
      const had = c.catchupBoost;
      hold(c, null, %s);
      return { had, left: c.catchupBoost };
    })()""" % (SETTLED, SETTLED * 2))
    assert r["had"] > 0.9
    assert r["left"] == 0


def test_being_put_back_on_the_track_takes_it_with_it(rt):
    """A car on the grid is a car with no help, whatever the last race left."""
    r = rt.call("""(() => {
      const c = behind();
      hold(c, T.CATCHUP_FULL, %s);
      const before = c.catchupBoost;
      c.placeAt([0, 0, 0], [0, 0, -1]);
      return { before, after: c.catchupBoost };
    })()""" % SETTLED)
    assert r["before"] > 0.9 and r["after"] == 0


def test_it_is_engine_on_the_throttle_and_not_free_speed(rt):
    """Off the power it is worth exactly nothing, the same as a tow is.

    Both cars coast from the same speed with the help pinned on for one and off
    for the other; a multiplier that had leaked out of the throttle branch would
    show up here as the boosted car coasting further.
    """
    r = rt.call("""(() => {
      // Flat ground under both, so the only difference is the coast term.
      const world = { collider: { ground: () => ({hit: true, dist: T.RIDE_HEIGHT,
                        kind: 0, nx: 0, ny: 1, nz: 0, py: 0}),
                      walls: () => {} }, killY: -50 };
      const run = (help) => {
        const c = new Car(T, world);
        c.placeAt([0, 0, 0], [0, 0, -1]);
        c.vel.set(0, 0, -30);
        for (let i = 0; i < 120; i++) {
          c.catchupBoost = help;                 // pinned, not derived
          c.step(T.FIXED_DT, { throttle: 0, brake: 0, steer: 0 });
        }
        return c.speed;
      };
      return { off: run(0), on: run(1) };
    })()""")
    assert r["on"] == pytest.approx(r["off"], abs=1e-9)


# --- the numbers, which are the whole of how big this feels ----------------


# What the HUD draws next to the word km/h, from `hudFast` in game.js. The
# target is a number on the dial rather than a multiplier, so the multiplier is
# derived from it and this is the only place the conversion is written down
# outside the file that draws it.
DIAL = 3.1
FULL_HELP_ON_THE_DIAL = 180


def test_full_help_reaches_a_hundred_and_eighty_on_the_dial():
    """Top speed is where the engine fights DRAG, so a multiplier is squared.

    The size of this is the whole design, and it is expressed as **the number on
    the speedo** rather than as a lift, because that is the only form of it a
    driver ever sees. It was 1.22, which read 171 against a base of 155 - about
    a tenth, which is not a thing you can feel from inside the car, and a
    mechanic nobody notices is a mechanic that is not doing its job.

    This is deliberately checked as an exact figure rather than a band: it is a
    round number chosen for the dial, so a change to it is a decision about how
    fast the game is and should have to be made here as well as in tuning.py.
    """
    full = (T.ACCEL * T.CATCHUP_ACCEL_MULT / T.DRAG) ** 0.5
    assert round(full * DIAL) == FULL_HELP_ON_THE_DIAL


def test_dropping_back_is_still_never_the_fast_way_round():
    """The rule this replaced, kept as the thing it was actually protecting.

    Catch-up used to be pinned under *half a tow*, on the grounds that being
    handed the bigger of the two would make dropping back a tactic. At 180 it is
    worth about three quarters of one, so that pin is gone - and the fear it
    encoded does not survive the arithmetic. Collecting the whole of this means
    being CATCHUP_FULL seconds down; the help is worth the difference between two
    top speeds, and no amount of it buys back five seconds inside a lap. The tow
    is still the better of the two and still the one you plan.

    What is worth pinning is the direction: a tow must remain the larger prize,
    or the fast way round genuinely would be to lift off and wait.
    """
    full = (T.ACCEL * T.CATCHUP_ACCEL_MULT / T.DRAG) ** 0.5
    tow = (T.ACCEL * T.SLIP_ACCEL_MULT / T.DRAG) ** 0.5
    assert full < tow, "a tow you lined up beats help you were handed"
    # What the deficit costs against what the help pays back, over the length of
    # one CATCHUP_FULL. Being that far down is worth several seconds; the extra
    # top end is worth a fraction of one, so the trade is never on.
    paid_back = (full - T.MAX_SPEED) * T.CATCHUP_FULL / T.MAX_SPEED
    assert paid_back < T.CATCHUP_FULL / 2, "the gap always costs more than it pays"


def test_the_two_stack_and_still_land_under_the_hard_clamp():
    """`step` clamps velocity at MAX_SPEED * 1.7 as a safety net.

    A tow and a full head of catch-up multiply, which is deliberate - the car
    that has spent a minute alone and finally caught somebody is the one that
    should be able to come past. But if the pair of them reached the clamp then
    the clamp would be setting the top speed and neither multiplier would mean
    what it says.
    """
    both = (T.ACCEL * T.SLIP_ACCEL_MULT * T.CATCHUP_ACCEL_MULT / T.DRAG) ** 0.5
    assert both > (T.ACCEL * T.SLIP_ACCEL_MULT / T.DRAG) ** 0.5, "they stack"
    assert both < T.MAX_SPEED * 1.7, "and the clamp is still only a safety net"


def test_the_deadzone_is_a_gap_you_can_still_see():
    """The whole justification is that a race is over once the gap is seconds.

    So the deadzone has to be about a corner's worth of road - long enough that
    an ordinary scrap is settled by driving - and full help has to arrive while
    the leader is still somewhere ahead rather than a lap up the road.
    """
    assert 1.0 <= T.CATCHUP_DEAD <= 2.5
    assert T.CATCHUP_FULL > T.CATCHUP_DEAD + 2
    # In metres, on the shortest track in the pool, full help must not need most
    # of a lap of deficit - by then there is no race left to save.
    import tracks
    shortest = min(_line_length(t) for t in tracks.TRACKS)
    assert T.CATCHUP_FULL * T.MAX_SPEED < shortest * 0.4


def _line_length(track):
    import math
    line = track["line"]
    return sum(math.dist(line[i - 1]["p"], line[i]["p"]) for i in range(1, len(line)))


# --- the gate and the gap, lifted out of game.js ---------------------------

GAME_JS = os.path.join(os.path.dirname(__file__), "..", "static", "js", "game.js")


def _fn(name):
    """One top-level function from game.js, exactly as it ships."""
    src = open(GAME_JS).read()
    m = re.search(r"^function %s\(.*?^\}" % re.escape(name), src, re.S | re.M)
    assert m, "%s is gone from game.js, or is no longer a plain function" % name
    return m.group(0)


@pytest.mark.parametrize("mode,phase,race,want", [
    ("room", "racing", True, True),          # the race, and only the race
    ("room", "free", False, False),          # practice has no first place
    ("room", "qualifying", False, False),    # everybody alone against the clock
    ("room", "qual_countdown", False, False),
    ("room", "countdown", True, False),      # nobody is driving yet
    ("room", "results", False, False),
    ("solo", "free", False, False),          # nobody to be behind
    ("solo", "racing", True, False),
])
def test_catching_up_belongs_to_the_race_and_nothing_else(mode, phase, race, want):
    """Deliberately narrower than `contactOn`, which also covers free practice.

    Practice is the interesting one: the cars are solid there and you can tow
    off them, because they are cars on a road with you. But there is no such
    thing as first place in it, so there is nothing to be behind.
    """
    ctx = jsrt.quickjs.Context()
    ctx.eval("var CFG = {mode: '%s'};" % mode)
    ctx.eval("var S = {racePhase: '%s', raceMode: %s};" % (phase, "true" if race else "false"))
    ctx.eval(_fn("catchupOn"))
    assert bool(ctx.eval("catchupOn()")) is want


GAP_STUB = """
var CFG = {mode: 'room'};
var T = {MAX_SPEED: %s};
var S = {raceMode: true, racePhase: 'racing', run: {bestS: 0},
         standings: [], remotes: new Map()};
function catchupOn() { return S.raceMode && S.racePhase === 'racing'; }
function put(pid, prog) { S.remotes.set(pid, {prog: prog}); }
""" % T.MAX_SPEED


def _gap(setup):
    ctx = jsrt.quickjs.Context()
    ctx.eval(GAP_STUB)
    ctx.eval(_fn("gapToLeader"))
    ctx.eval(setup)
    return json.loads(ctx.eval("JSON.stringify(gapToLeader())"))


def test_the_gap_is_distance_reported_as_time():
    """Divided by MAX_SPEED: how long that ground would take flat out."""
    gap = _gap("S.run.bestS = 100; put('a', 100 + T.MAX_SPEED * 3);")
    assert gap == pytest.approx(3.0)


def test_leading_is_worth_nothing_and_never_goes_negative():
    assert _gap("S.run.bestS = 500; put('a', 100); put('b', 300);") == 0


def test_the_furthest_car_sets_the_mark_not_the_nearest():
    gap = _gap("S.run.bestS = 0; put('a', T.MAX_SPEED); put('b', T.MAX_SPEED * 4);")
    assert gap == pytest.approx(4.0)


def test_a_car_that_is_already_home_is_not_being_caught():
    """Once the winner is in, the race left on the road is for the places behind
    it - so the leader for this is the leader still driving."""
    gap = _gap("""
      S.run.bestS = 0;
      put('winner', T.MAX_SPEED * 9); put('rival', T.MAX_SPEED * 2);
      S.standings = [{pid: 'winner', ms: 61234}, {pid: 'rival', ms: null}];
    """)
    assert gap == pytest.approx(2.0)


def test_leading_the_cars_still_out_there_is_worth_nothing():
    """Second on the road behind a finisher is not owed anything: there is
    nobody in front to catch."""
    gap = _gap("""
      S.run.bestS = T.MAX_SPEED * 5;
      put('winner', T.MAX_SPEED * 9); put('back', T.MAX_SPEED);
      S.standings = [{pid: 'winner', ms: 61234}];
    """)
    assert gap == 0


def test_there_is_no_gap_outside_a_race():
    """The gate and the gap are one call, so a caller cannot ask for one
    without the other and get a number it should not have."""
    assert _gap("S.racePhase = 'free'; S.raceMode = false; put('a', 9999);") is None
