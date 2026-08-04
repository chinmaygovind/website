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
def test_the_car_is_mostly_on_the_road(rt, slug):
    """Flying is the point, but a lap is still a driving lap.

    An earlier version of the car was glued to every slope: the suspension held
    it down over crests and a normal-velocity term ate whatever launch was left,
    so a hill felt like a conveyor belt. That is gone. The upper bound here only
    guards the opposite failure - a track that has become a flight simulator.
    """
    r = _sim(rt, slug)
    limit = 0.40 if slug == "jumpcity" else 0.28
    assert r["airFraction"] < limit, \
        f"{slug} spent {r['airFraction'] * 100:.0f}% of the lap airborne"


@pytest.mark.parametrize("slug", SLUGS)
def test_every_track_actually_throws_the_car(rt, slug):
    """The other half of the same story, and the more important half.

    Every track in the pool has either a jump or a rolling crest on it, and
    arriving at one at speed has to put the car in the air. If a retune quietly
    re-glues the car to the road - lowering SNAP's effect, reinstating the
    normal-velocity scrub, softening the crests - this is what notices.
    """
    r = _sim(rt, slug)
    assert r["maxAir"] > 0.4, (
        f"{slug} never got more than {r['maxAir']:.2f}s of air - the car is stuck "
        f"to the road")
    assert r["landings"] > 0, f"{slug} recorded no landings"


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
    """Gold should be about as hard as the test driver or harder; bronze should
    be comfortable."""
    driven = _sim(rt, slug)["time"] / 1000.0
    m = rt.tracks.get(slug)["medals"]
    assert m["gold"] < driven * 1.20, f"{slug}: gold medal is too generous"
    assert m["bronze"] > driven, f"{slug}: bronze medal is not achievable"


def test_the_car_goes_all_the_way_through_a_corkscrew_upside_down(rt):
    """Straight-line run into a corkscrew: it has to invert and stay on the road.

    Steering is applied about the *surface* normal rather than world up, which is
    the whole reason a fully inverted section needs no special case anywhere in
    the car code.
    """
    rt.eval("""
    function screwRun(track, T) {
      const built = buildTrack(track, T);
      const course = new Course(built);
      const car = new Car(T, built);
      const idx = track.line.findIndex(e => e.fix && !e.air) - 3;
      const p = track.line[idx].p, tan = course.tangent(idx);
      car.placeAt(p, tan);
      car.vel.set(tan[0]*42, tan[1]*42, tan[2]*42);
      let minUp = 1, maxY = -1e9, airFrames = 0, frames = 0;
      for (let t = 0; t < 3; t += T.FIXED_DT) {
        const loc = course.locate(car.pos);
        const s = course.line[Math.min(loc.idx, course.line.length - 1)];
        const steer = (s.fix && !s.air)
          ? Math.max(-0.4, Math.min(0.4, -loc.lateral * 0.16)) : 0;
        car.step(T.FIXED_DT, {throttle: 1, brake: 0, steer, handbrake: false});
        frames++;
        if (!car.grounded) airFrames++;
        if (car.up.y < minUp) minUp = car.up.y;
        if (car.pos.y > maxY) maxY = car.pos.y;
      }
      return {minUp, maxY, airFraction: airFrames/frames, speed: car.speed,
              y: car.pos.y};
    }
    """)
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "twist")
    r = rt.call("screwRun(TRACKS[%d], T)" % i)
    assert r["minUp"] < -0.85, f"the car never went properly inverted (min up.y {r['minUp']:.2f})"
    assert r["maxY"] > 14, f"the car only reached {r['maxY']:.1f} up the corkscrew"
    assert r["airFraction"] < 0.30, "the car came off the corkscrew surface"
    assert r["speed"] > 5, "the car stalled in the corkscrew"


def test_the_collider_finds_the_road_not_the_grass(rt):
    """Road flush with the ground plane used to make this query a coin toss, so
    the car spent whole laps behaving as if it were on grass - and the two
    surfaces z-fought all over the screen. The road now sits above the grass."""
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "sunrise")
    rt.eval("""
    function surfaceUnderLine(track, T) {
      const built = buildTrack(track, T);
      let road = 0, other = 0, missing = 0;
      for (const e of track.line) {
        if (e.air) continue;
        const g = built.collider.ground(e.p[0] + e.n[0] * T.RIDE_HEIGHT,
                                        e.p[1] + e.n[1] * T.RIDE_HEIGHT,
                                        e.p[2] + e.n[2] * T.RIDE_HEIGHT,
                                        e.n[0], e.n[1], e.n[2], 3);
        if (!g.hit) missing++;
        else if (g.kind === KIND.ROAD) road++;
        else other++;
      }
      return {road, other, missing};
    }
    """)
    r = rt.call("surfaceUnderLine(TRACKS[%d], T)" % i)
    assert r["missing"] == 0, "part of the driving line has no surface under it"
    assert r["road"] > 100
    # The ribbon is continuous, so unlike the old grid there is no corner pivot
    # where the road narrows to a point. Every station should find tarmac.
    assert r["other"] == 0, \
        f"{r['other']} of {r['road'] + r['other']} line points report grass, not road"


@pytest.mark.parametrize("slug", SLUGS)
def test_a_real_lap_passes_the_anti_cheat(rt, slug):
    """Close the loop between the driver and the validator.

    `runcheck.validate` rejects times that are too fast, replays that do not last
    as long as the time claims, replays containing a teleport, and replays that do
    not start on the line. Every one of those is a judgement about what a real lap
    looks like, so the only honest test is to hand it a real lap - driven by the
    shipped physics, recorded by the shipped ghost recorder - and require it to be
    accepted.
    """
    import runcheck
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == slug)
    r = rt.call("simulate(TRACKS[%d], T, {maxT:120, withGhost:true})" % i)
    assert r["finished"]
    track = rt.tracks.get(slug)
    ok, why = runcheck.validate(track, int(round(r["time"])), r["splits"], r["ghost"])
    assert ok, f"{slug}: the anti-cheat rejected a genuine lap - {why}"
    # And the round trip through the wire format has to survive.
    frames = runcheck.unpack_ghost(runcheck.pack_ghost(r["ghost"]))
    assert len(frames) == len(r["ghost"])
    worst = max(abs(a[k] - b[k]) for a, b in zip(frames, r["ghost"]) for k in range(3))
    assert worst < 0.02, f"{slug}: ghost packing moved the car by {worst:.3f}"
    ok2, why2 = runcheck.validate(track, int(round(r["time"])), r["splits"], frames)
    assert ok2, f"{slug}: a lap fails validation after a pack/unpack round trip - {why2}"


@pytest.mark.parametrize("slug", ["sunrise", "twist"])
def test_the_ghost_is_recorded_where_the_car_actually_was(rt, slug):
    """A ghost frame has to be the pose at its own timestamp.

    The recorder used to accumulate dt and push a sample every time an interval
    had gone by, which meant the accumulator had to *fill* before frame 0 was
    written - so frame 0 was the pose one interval after the start, frame 1 two,
    and so on. Playback reads frame `t * GHOST_HZ` at run time `t`, so every
    ghost ever saved played back 1/15s ahead of the lap it recorded: a couple of
    car lengths up the road at racing speed, from the line to the flag. That is
    the whole "my ghost starts in front of me" bug, and nothing else caught it
    because the replay was still a perfectly valid drive - just the wrong one.

    So: drive a lap, note independently where the car was at each sample time,
    and require the recorded ghost to agree. The tolerance is one physics step
    of travel, which is an order of magnitude tighter than the bug.
    """
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == slug)
    r = rt.call("simulate(TRACKS[%d], T, {maxT:120, withGhost:true})" % i)
    assert r["finished"]
    ghost, probe = r["ghost"], r["ghostProbe"]
    assert abs(len(ghost) - len(probe)) <= 1, "the recorder skipped or doubled a sample"
    worst, where = 0.0, 0
    for k in range(min(len(ghost), len(probe))):
        g, p = ghost[k], probe[k]
        d = ((g[0] - p[0]) ** 2 + (g[1] - p[1]) ** 2 + (g[2] - p[2]) ** 2) ** 0.5
        if d > worst:
            worst, where = d, k
    limit = T.MAX_SPEED * T.FIXED_DT * 1.7
    assert worst < limit, (
        f"{slug}: ghost frame {where} is {worst:.2f} units from where the car was "
        f"at {where / 15:.2f}s - the ghost is out of sync with the lap it recorded")


def test_the_brake_light_means_braking(rt):
    """The lights are on the car, not the HUD, so a rival's are how you read that
    they are slowing - which only works if the flag means the obvious thing."""
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "sunrise")
    r = rt.call("brakeStates(TRACKS[%d], T)" % i)
    assert r["braking"] is True, "holding the brake does not light them"
    assert r["handbrake"] is True, "the handbrake does not light them"
    assert r["idle"] is False and r["coasting"] is False and \
        r["accelerating"] is False, "the lights are on when nothing is slowing down"
    assert r["reversing"] is False, \
        "reversing lights the brake lights - the key is held, but nothing is slowing"
    # FLAG.BRAKE is bit 3; game.js lights a rival's lamps off it and nothing
    # else - it once also hid them and stopped them being solid, which is what
    # made rivals vanish through every braking zone.
    assert r["flag"] & 8, "the brake flag is not in the pose sent to other players"


@pytest.mark.parametrize("slug", SLUGS)
def test_checkpoint_posts_are_solid_and_the_gate_is_not(rt, slug):
    """You can clip a checkpoint post, and only the post.

    The posts used to be scenery: drawn, but not in the collider, so a car drove
    straight through the thing it looked like it hit. They are walls now. The
    same test also pins the other half of that - the mouth of the gate has to
    stay completely open, or the checkpoint becomes a wall across the road.
    """
    rt.eval("""
    function gatePosts(track, T) {
      const built = buildTrack(track, T);
      const posts = [], mouths = [];
      const probe = (x, y, z) => {
        let n = 0;
        built.collider.walls(x, y, z, T.CAR_RADIUS, () => { n++; });
        return n;
      };
      for (const g of track.gates) {
        const n = track.line[g.si].n;
        // High enough up the post to be clear of any barrier along the kerb, so
        // a hit here can only be the post itself.
        const up = 2.6;
        for (const s of [-1, 1]) {
          const o = s * (g.hw + 0.44);
          posts.push(probe(g.p[0] + g.r[0]*o + n[0]*up,
                           g.p[1] + g.r[1]*o + n[1]*up,
                           g.p[2] + g.r[2]*o + n[2]*up));
        }
        // straight through the middle, at ride height
        mouths.push(probe(g.p[0] + n[0]*T.RIDE_HEIGHT,
                          g.p[1] + n[1]*T.RIDE_HEIGHT,
                          g.p[2] + n[2]*T.RIDE_HEIGHT));
      }
      return {posts, mouths};
    }
    """)
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == slug)
    r = rt.call("gatePosts(TRACKS[%d], T)" % i)
    assert r["posts"], f"{slug} has no gates"
    assert all(n > 0 for n in r["posts"]), \
        f"{slug}: {r['posts'].count(0)} gate posts are scenery, not walls"
    assert all(n == 0 for n in r["mouths"]), \
        f"{slug}: something solid is standing in the mouth of a gate"


def test_grass_costs_you_the_corner(rt):
    """Cutting across the infield has to be slower than driving round.

    OFFROAD_DRAG used to put the grass top speed within a whisker of the road's,
    which made a straight line through the middle of a corner simply the quicker
    way round - the one thing a racing line must never be. Measured as an
    acceleration budget rather than by driving somewhere, so the test does not
    depend on how much grass happens to be next to the track.
    """
    rt.eval("""
    function grassBudget(track, T, frac) {
      const built = buildTrack(track, T);
      const car = new Car(T, built);
      const st = track.line[2];
      // well out on the grass, pointing along the road
      const p = [st.p[0] + st.lat[0]*26, track.ground, st.p[2] + st.lat[2]*26];
      const f = [st.lat[2], 0, -st.lat[0]];
      car.placeAt(p, f);
      const inp = {throttle: 1, brake: 0, steer: 0, handbrake: false};
      for (let i = 0; i < 20; i++) car.step(T.FIXED_DT, {throttle:0, brake:0, steer:0});
      const settled = {offroad: car.offroad, grounded: car.grounded};
      car.vel.copy(car.fwd).multiplyScalar(T.MAX_SPEED * frac);
      const before = car.vel.dot(car.fwd);
      for (let i = 0; i < 12; i++) car.step(T.FIXED_DT, inp);
      const after = car.vel.dot(car.fwd);
      return Object.assign(settled, {accel: (after - before) / (12 * T.FIXED_DT)});
    }
    """)
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "sunrise")
    slow = rt.call("grassBudget(TRACKS[%d], T, 0.35)" % i)
    fast = rt.call("grassBudget(TRACKS[%d], T, 0.62)" % i)
    assert slow["offroad"] and fast["offroad"], "the test car is not on the grass"
    # Below about a third of MAX_SPEED the grass still pulls; above about
    # 60 per cent it cannot, so that is the ceiling out there.
    assert slow["accel"] > 0, "the car cannot even accelerate on grass"
    assert fast["accel"] < 0, (
        f"the car still accelerates at {0.62 * T.MAX_SPEED:.0f} u/s on grass "
        "- cutting the corner is faster than driving round it")


def test_the_car_does_not_nosedive_off_a_jump(rt):
    """A jump should hang, not pitch straight into the ground.

    Two things nose the car down in the air and they compound: holding the
    throttle pitches it down at AIR_PITCH, and levelling toward world up noses
    down whatever the take-off ramp raised. At the old values a jump taken flat
    out - which is how every jump is taken - was pointing at the floor within
    half a second of leaving the lip.
    """
    rt.eval("""
    function flight(track, T, seconds) {
      const built = buildTrack(track, T);
      const car = new Car(T, built);
      const st = track.line[2];
      // High above everything, so this is pure flight with no ground under it.
      car.placeAt([st.p[0], st.p[1] + 120, st.p[2]], track.spawn.fwd);
      // Launched off a lip: nose up 20 degrees, and travelling that way.
      car._spin(car.right, 0.35);
      car.vel.copy(car.fwd).multiplyScalar(T.MAX_SPEED);
      const out = [];
      let t = 0;
      while (t < seconds) {
        car.step(T.FIXED_DT, {throttle: 1, brake: 0, steer: 0, handbrake: false});
        t += T.FIXED_DT;
        out.push(Math.asin(Math.max(-1, Math.min(1, car.fwd.y))) * 180 / Math.PI);
      }
      const at = (s) => out[Math.min(out.length - 1, Math.round(s / T.FIXED_DT) - 1)];
      return {start: at(0.02), half: at(0.5), full: at(1.0), grounded: car.grounded};
    }
    """)
    i = next(k for k, t in enumerate(rt.tracks.TRACKS) if t["slug"] == "jumpcity")
    r = rt.call("flight(TRACKS[%d], T, 1.0)" % i)
    assert not r["grounded"], "the test car found the ground - it is meant to be flying"
    assert r["start"] > 15, "the car did not leave the lip nose-up"
    # Half a second is about a short jump, and the nose should still be near
    # where the lip put it.
    drop = r["start"] - r["half"]
    assert drop < 25, \
        f"the nose drops {drop:.0f} degrees in the first half-second of a jump"
    # But it does come down: this is lazy, not frozen. You can still aim.
    assert r["full"] < r["half"] - 15, "there is not enough pitch authority to aim a landing"


def test_the_road_is_clear_of_the_ground_plane(rt):
    """The z-fighting fix, measured rather than eyeballed: no part of a
    ground-level track may come within a hair of the grass."""
    for slug in ("sunrise", "chicane", "eight"):
        t = rt.tracks.get(slug)
        gy = t["ground"]
        assert gy is not None
        lowest = min(e["p"][1] - e["hw"] * abs(e["lat"][1]) for e in t["line"])
        assert lowest - gy > 0.8, \
            f"{slug}: the road comes within {lowest - gy:.2f} of the grass"


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
