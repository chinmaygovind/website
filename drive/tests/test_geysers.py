"""Geysers: Citadel's lava columns, run for real in QuickJS on the real track.

A geyser is a mover that throws rather than shoves (`Movers.lift` in
trackmesh.js, asked by `Car.step`), on the same integer clock as Dino Park's
herd so the anti-cheat meets every eruption where the browser did. These check
the three things the track is authored around: that a column throws you only
while it is erupting, that the Hall's throw actually lands you on the rampart
past the hole - the shortcut is the whole point of it - and that the lake is a
respawn on contact rather than a fall through it.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jsrt

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

HARNESS = """
var TRACK = TRACKS.find(t => t.slug === 'citadel');
var BUILT = buildTrack(TRACK, T);
var GEYSERS = BUILT.movers.list.filter(m => m.geyser);

// A car on the road at geyser `g`, heading along the Hall at `speed`, with the
// world's clock at step `k`.
function atGeyser(g, k, speed) {
  const m = GEYSERS[g];
  let best = 0, bd = 1e9;
  TRACK.line.forEach((e, i) => {
    const d = Math.hypot(e.p[0] - m.x, e.p[2] - m.z) + Math.abs(e.p[1] - m.y - m.reach + 3);
    if (d < bd) { bd = d; best = i; }
  });
  const e = TRACK.line[best], f = TRACK.line[best + 1];
  const d = [f.p[0] - e.p[0], 0, f.p[2] - e.p[2]];
  const n = Math.hypot(d[0], d[2]);
  const fwd = [d[0] / n, 0, d[2] / n];
  const c = new Car(T, BUILT);
  c.placeAt([m.x, e.p[1], m.z], fwd);
  c.vel.set(fwd[0] * speed, 0, fwd[2] * speed);
  c.tick = k;
  c.throws = 0;
  c.onBounce = () => { c.throws++; };
  return c;
}

function drive(c, secs) {
  const dt = T.FIXED_DT, n = Math.round(secs / dt);
  let up = -Infinity, top = -Infinity, respawned = false;
  for (let i = 0; i < n; i++) {
    c.step(dt, { throttle: 1 });
    up = Math.max(up, c.vel.y);
    top = Math.max(top, c.pos.y);
    if (c.respawnIn > 0) respawned = true;
  }
  return { up, top, y: c.pos.y, grounded: c.grounded, throws: c.throws,
           respawned, period: GEYSERS[0].period, burst: GEYSERS[0].burst,
           vel: GEYSERS[0].vel };
}
"""


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.load_tuning_and_tracks()
    r.eval(HARNESS)
    return r


def test_citadel_has_geysers(rt):
    assert rt.call("GEYSERS.length") >= 3


def test_an_erupting_geyser_throws_you(rt):
    r = rt.call("drive(atGeyser(0, 10, 30), 0.3)")
    assert r["throws"] == 1
    assert r["up"] > r["vel"] * 0.95


def test_a_quiet_geyser_does_nothing(rt):
    burst = rt.call("GEYSERS[0].burst")
    r = rt.call("drive(atGeyser(0, %d, 30), 0.3)" % (burst + 20))
    assert r["throws"] == 0
    assert r["up"] < 5


@pytest.mark.parametrize("speed", [22, 32, 42])
def test_the_halls_geyser_lands_you_on_the_rampart(rt, speed):
    """The shortcut: up through the hole and down on the deck past its far lip.

    Across the speeds a car actually arrives at the end of the Hall with - it
    is braking for a hairpin - so it is a timing gamble and not a speed trick.
    """
    r = rt.call("drive(atGeyser(0, 10, %d), 4.0)" % speed)
    assert not r["respawned"], "fell back into the lava"
    assert r["grounded"] and r["y"] > 20, \
        "at %d u/s the geyser should land you up on the rampart, ended at y=%.1f" \
        % (speed, r["y"])


def test_the_lava_is_a_respawn_on_contact(rt):
    """Off the side of the Hall: the lake is seven units down and kills."""
    r = rt.call("""(function () {
        const c = atGeyser(0, 200, 0);
        const m = GEYSERS[0];
        c.placeAt([m.x - 40, m.y + 8, m.z], [1, 0, 0]);
        c.tick = 200;
        return drive(c, 1.2);
    })()""")
    assert r["respawned"]


SKIP = """
var CP = TRACK.gates.filter(g => g.kind === 'cp');
function nearestStation(p) {
  let b = 0, bd = 1e9;
  TRACK.line.forEach((e, i) => {
    const d = Math.hypot(e.p[0] - p[0], e.p[1] - p[1], e.p[2] - p[2]);
    if (d < bd) { bd = d; b = i; }
  });
  return b;
}
// Every jump from the road between the second and third gates' wall to the
// exit road before the third gate, at a spread of speeds, with and without a
// hop. Returns how many of them land on that exit road.
function keepSkips() {
  const L = TRACK.line, a = nearestStation(CP[1].p), z = nearestStation(CP[2].p);
  let n = 0;
  for (let i = a + 2; i < a + 16; i += 4) for (let j = z - 14; j < z - 1; j += 5)
    for (const v of [38, 50]) for (const hop of [0, 8]) {
      const e = L[i], t = L[j];
      const dx = t.p[0] - e.p[0], dz = t.p[2] - e.p[2], m = Math.hypot(dx, dz);
      const f = [dx / m, 0, dz / m];
      const c = new Car(T, BUILT);
      c.placeAt([e.p[0], e.p[1] + 0.6, e.p[2]], f);
      c.vel.set(f[0] * v, hop, f[2] * v);
      for (let k = 0; k < 240; k++) {
        c.step(T.FIXED_DT, { throttle: 1 });
        if (c.respawnIn > 0) break;
        if (c.grounded && Math.hypot(c.pos.x - t.p[0], c.pos.z - t.p[2]) < 14 &&
            Math.abs(c.pos.y - t.p[1]) < 3) { n++; break; }
      }
    }
  return n;
}
"""


def test_the_keep_cannot_be_skipped(rt):
    """The wall of death turns 270 degrees, and the quarter it leaves open lies
    between the rampart and the exit road. Jumping across it skipped the keep
    and landed before the next gate - so it is filled with solid stone, and
    nothing thrown across it may land on the exit road."""
    rt.eval(SKIP)
    assert rt.call("keepSkips()") == 0
