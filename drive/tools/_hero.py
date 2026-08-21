"""The hero shot: a stretch of a track from up high, with a field of cars on it.

Every picture of a track this game ships is this one composition at a different
size. `shoot_tracks.py` writes it to `static/img/tracks/<slug>.png` and that is
the card art the home page and the switcher show, and the picture the share
cards are laid over; `shoot_covers.py` writes it at portal sizes with the
wordmark across the foot. **The framing lives here so those cannot disagree** -
a card and a cover of the same track are the same photograph.

**It is the real game, not a render of it.** The page is loaded at `?shot=1`
(HUD off, player car hidden, car frozen) and the scene then composed through
`window.DriveShot`, which that mode exposes. The cars are the game's own
`CarView` placed on the ribbon's own frame, so a car in a loop is upside down
because the road is.

**Two halves, and only one of them is a judgement.** *Where* to stand is
measured: `SCAN` walks the lap in windows and scores each on how far the road
rolls off level (a loop or a half-pipe), how much it climbs, and how much it
turns in plan, so a track whose corners move keeps a sensible window without
anybody re-measuring it. *Which way round* is not a thing a number knows, so the
azimuth and pitch in `FRAMES` were each chosen by eye off a contact sheet:

    python tools/_hero.py <slug>...      # eight candidate angles, as one sheet
    python tools/_hero.py --all

writes `tools/views/_hero/<slug>.png` (gitignored, like the rest of `views/`),
which is eight labelled thumbnails of the same window from four sides at two
heights. Pick one, put it in `FRAMES`, re-shoot. `--pad`/`--span` run the whole
grid at a different crop, and

    python tools/_hero.py --sweep <slug> --az 5.0 --pit 0.34

is the other axis: one angle at eight points round the lap, for when the scan's
window is not the picture (`SWEEP_AT`). `--port` lets several of these run at
once, which is worth doing - a whole pool of sheets is an hour of software GL.

**The field is half the picture.** Cars go out in *packs* rather than at even
spacing - a line of evenly spaced cars is a diagram of a road, and a race is
three or four groups with clear air between them. How many, how tightly, and how
many are airborne are all per track: fourteen through the Spa esses and eight in
a Costco car park, and nothing leaves the ground on a real circuit. A car over a
`gap` is airborne whatever the track asked for, because it is out in the middle
of a jump by construction. Every car wears a livery out of `garage.py`'s own
vocabulary, and each track starts at a different point in that list, so no two
covers open on the same red car.

**It needs Playwright**, not the Chrome CLI: composing the scene is a page
evaluation and the CLI backend can only load a URL and screenshot it. That is
why `shoot_tracks.py` refuses rather than falling back - a fallback here would
quietly write the old empty-road framing under the right filename, which is the
one failure this tooling cannot detect.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from _shots import GL_FLAGS, serving  # noqa: E402

# **Built cars, not painted blobs.** Every one of these is a livery
# `garage.py` would accept: a body from its own palette, and most of them
# wearing something else it offers - a stripe pattern, a finish, a set of rims,
# a badge on the bonnet. The point is that a cover shows the game somebody
# could actually turn up in, and a field of sixteen flat colours does not.
# Bodies are the palette's ten in order, then six of them again in a different
# build, so no two adjacent cars in any pack are the same colour.
LIVERIES = [
    dict(body="#e8453c", livery="centre",    stripe="#ffffff", finish="gloss",
         rim_style="spoke5"),
    dict(body="#3d8bfd", livery="twin",      stripe="#f2c94c", rim_style="mesh"),
    dict(body="#f2c94c", livery="band",      stripe="#101216", finish="gloss",
         rim_style="dish", badge="checkers"),
    dict(body="#27ae60", livery="none",      rim_style="spoke6", rim="#9aa3af"),
    dict(body="#bb6bd9", livery="hoop",      stripe="#ffffff", finish="gloss"),
    dict(body="#f2994a", livery="pinstripe", stripe="#101216", rim_style="forged",
         rim="#967440"),
    dict(body="#56ccf2", livery="halves",    roof="#101216", finish="gloss",
         rim_style="spoke5"),
    dict(body="#f178b6", livery="fade",      stripe="#ffffff", badge="ribbon"),
    dict(body="#17bfa8", livery="centre",    stripe="#101216", finish="gloss",
         rim_style="mesh"),
    dict(body="#8195b0", livery="twin",      stripe="#e8453c", rim_style="dish",
         badge="chevrons"),
    dict(body="#e8453c", livery="halves",    roof="#ffffff", rim_style="forged"),
    dict(body="#3d8bfd", livery="none",      finish="gloss", trim="#101216",
         rim="#c9ced6", badge="laurel"),
    dict(body="#f2c94c", livery="hoop",      stripe="#3d8bfd", rim_style="spoke6"),
    dict(body="#27ae60", livery="band",      stripe="#ffffff", finish="gloss",
         badge="crown"),
    dict(body="#bb6bd9", livery="pinstripe", stripe="#f2c94c"),
    dict(body="#f2994a", livery="twin",      stripe="#ffffff", finish="gloss",
         rim_style="spoke5", badge="sunburst"),
]

# What every track gets before its own entry is laid over it. `at` None lets the
# scan choose the window; `pad` is a fraction of the distance that would fit the
# whole of it, so under 1 crops in, which is what a cover wants; `span` is how
# much of the lap is in frame.
DEFAULT = dict(at=None, azimuth=2.05, pitch=0.38, pad=0.52, fov=50, span=0.16,
               cars=12, carFrom=0.10, carTo=0.86, seed=11,
               # How far apart two cars in the same pack sit, as a fraction of
               # the window; what fraction of the field is airborne; and where
               # in `LIVERIES` this track starts, which is the cheapest way to
               # stop nineteen covers opening with the same red car.
               packStep=0.022, air=0.22, liveryFrom=0)

# Per track, only what differs from `DEFAULT`. Every azimuth and pitch here was
# picked off a contact sheet from `python tools/_hero.py <slug>`; the notes say
# what the other seven were losing, because that is the part that is expensive
# to work out twice.
FRAMES = {
    # --- The three the storefront covers were cut from first -----------------
    # The loop, the hairpin under it, and the ribbon running out to the stars.
    # `at` is pinned because the scan would also accept the half-pipes either
    # side of it and the loop is the picture.
    "rainbow": dict(at=0.68, azimuth=2.05, pitch=0.44, pad=0.50,
                    cars=12, air=0.30, liveryFrom=5),
    # Down through the trees with the sponsor boards on the outside. Flatter
    # than Rainbow Road, so the camera sits lower - from the same height as the
    # loop shot this reads as a map.
    "spa": dict(azimuth=2.05, pitch=0.34, pad=0.50,
                cars=14, air=0.0, liveryFrom=8),
    # The sun is what this track is called after, so the angle is the one that
    # has it in frame. `pad` is looser than the other two: at 0.50 the nearest
    # cars were half out of the bottom corner.
    "sunrise": dict(azimuth=2.05, pitch=0.34, pad=0.58,
                    cars=12, air=0.12, liveryFrom=0),

    # --- Where only the side had to be chosen --------------------------------
    # The scan finds the corner on these and the four candidates differ only in
    # what is behind it.
    #
    # The double S dropping away into the pines, with the start gantry near
    # enough the camera to give the trees a scale.
    "chicane": dict(azimuth=2.05, pitch=0.34, cars=13, air=0.08, liveryFrom=3),
    # The hairpin up on its columns. From 0.60 or 5.00 the white city below
    # reads as fog; from here the drop under the road is legible.
    "skyline": dict(azimuth=2.05, pitch=0.34, cars=11, air=0.20, liveryFrom=6),
    # The crossover is what the name means, so it is the side that has the
    # bridge over the far end of the oval in it.
    "eight": dict(azimuth=0.60, pitch=0.34, cars=12, air=0.10, liveryFrom=7),
    # The loop in silhouette on the horizon, over the lava grid. The best
    # picture in the pool for how little had to be chosen.
    "gauntlet": dict(azimuth=2.05, pitch=0.34, pad=0.44,
                     cars=10, air=0.25, liveryFrom=10),
    # The helix, with the city lights through it.
    "tokyo": dict(azimuth=2.05, pitch=0.34, cars=11, air=0.12, liveryFrom=2,
              carFrom=0.0),
    # **The sun is the point of the name**, and 5.00 is the only side with the
    # disc behind the loop rather than behind the camera.
    "bigred": dict(azimuth=5.00, pitch=0.34, cars=11, air=0.35, liveryFrom=14),

    # --- Where the crop had to move as well ----------------------------------
    # The long S on stilts, with the haze doing the depth. 3.50 puts a slip road
    # across the bottom of the frame and 5.00 stacks two decks into something
    # nobody can read. Cropped in, because at the pool's the cars were specks.
    "heights": dict(azimuth=0.60, pitch=0.34, pad=0.42,
                    cars=9, air=0.15, liveryFrom=12),
    # **The only shot in the pool taken from straight above.** Cloudbreak is a
    # road on stilts between rock spires, and from an establishing height the
    # spires are in front of it - the shape of the hairpin, which is the reason
    # to look, only reads looking down on it.
    "pillars": dict(azimuth=3.50, pitch=0.85, pad=0.55,
                    cars=11, air=0.18, liveryFrom=2),
    # The hairpin, with the pit building and a grandstand behind it. A real
    # circuit is flat, so from the pool's distance it photographs as a diagram;
    # this stands close enough that the cars in the hairpin are cars. No air:
    # nothing at Silverstone leaves the ground.
    "silverstone": dict(azimuth=0.60, pitch=0.34, pad=0.34,
                        cars=14, air=0.0, liveryFrom=9),
    # **Both loops, which is what the name promises.** At the pool's `span` only
    # one is in the window and the crop is inside it, so this frames a quarter
    # of the lap and stands well back to hold the pair.
    "twist": dict(azimuth=2.05, pitch=0.45, span=0.26, pad=0.72,
                  cars=10, air=0.30, liveryFrom=9),

    # --- Where the window had to be pinned by hand ---------------------------
    # The scan scores roll, climb and bend. That is a good answer to "where is
    # this track interesting" and no answer at all to "what is this track known
    # for", so these five say where to stand.
    #
    # The banked sweep in the last third, which is the only stretch with a ramp
    # and a full field in one frame; the scan's own pick is a straight between
    # towers.
    "jumpcity": dict(at=0.74, azimuth=2.05, pitch=0.34,
                     cars=14, air=0.35, liveryFrom=1),
    # **The spiral, which is the name.** The scan picks the longest bend, and
    # the one place the road climbs over itself scores no higher for it than any
    # other corner does.
    "spiral": dict(at=0.38, azimuth=0.60, pitch=0.52, pad=0.55,
                   cars=9, air=0.10, liveryFrom=4),
    # **The harbour, which the scan will never find either.** Monaco is scored
    # on roll, climb and bend like everything else, so the scan picks the
    # hairpin - which is a tight corner between towers and is a picture of any
    # city, not of this one. The window is pinned on the harbour front, where the
    # water and the moored fleet are on one side and Monte Carlo stacks up behind
    # the road on the other, and narrowed because a sixth of a lap this dense is
    # a thicket of buildings. No air: nothing here leaves the ground.
    # 5.00 off the contact sheet: the only side with the road and its kerbs down
    # one edge of the frame and the harbour along the other. 0.60 puts the water
    # in a corner, 2.05 and 3.50 are mostly water with the road lost behind the
    # front rank of buildings.
    # **The pitch is the whole difference here, for the reason Cloudbreak's is.**
    # Monaco is a canyon: at the pool's 0.34 the camera stands among the towers
    # and the front rank simply blocks the shot - one terracotta slab filled two
    # thirds of the frame and the harbour behind it was gone. From higher up you
    # look down *into* the streets and across the water, which is the only angle
    # where the road, the city and the port are all in one picture.
    "monaco": dict(at=0.68, azimuth=5.00, pitch=0.62, span=0.10, pad=0.50,
                   cars=12, air=0.0, liveryFrom=11),
    # **The water, which the scan will never find.** Sandy Cove is scored on
    # bend and climb like everything else, and its switchbacks inland beat the
    # coast road every time - so the window is pinned on the run along the
    # lagoon, and narrowed, because a sixth of a track this long is a map.
    "cove": dict(at=0.38, azimuth=0.60, pitch=0.34, span=0.09, pad=0.44,
                 cars=9, air=0.08, liveryFrom=13),
    # **The storefront, from out in the car park.** Costco is the only track
    # with solid geometry over the road, so from an establishing height the
    # scan's own window photographs its roof - a grey rectangle, whichever of
    # the four sides you stand on. This is the arrival instead: the sign, the
    # doors, and the road curving in past the parking bays. Nothing is airborne
    # in a car park.
    "costco": dict(at=0.07, azimuth=3.50, pitch=0.25, pad=0.42, span=0.10,
                   cars=8, air=0.0, liveryFrom=11),
    # **Square onto the ski jump, with the field climbing it.** Mount Joy is one
    # enormous ramp and then the whole way back down, so the scan spends its
    # score on the descent and never looks here at all.
    #
    # `azimuth` is not a taste: 3.14 is the ramp's own heading, measured off the
    # ribbon, so the camera stands directly behind the run and the chevrons face
    # the lens. Every other side is worse for a reason particular to this track -
    # a mountain with a slot cut into it. From 0.60 and 2.05 the ramp is a thread
    # on a white slope; 3.50 is a grey rock wall; and 4.25, which looked like the
    # compromise between the two, puts the camera *inside* the mountain and
    # photographs a snowfield, which is the one failure this composition can have
    # that does not look like an error.
    #
    # **The cost of square-on is the flight**, and it is unavoidable rather than
    # a thing left untuned. The car leaves the lip travelling directly away from
    # a head-on camera, so the whole jump happens behind the crest. Shot from
    # 5.00 the cars are visibly in the air and the ramp is edge-on, a dark line
    # up a rock face. The ramp is the picture.
    "mountjoy": dict(at=0.11, azimuth=3.14, pitch=0.16, pad=0.50, span=0.10,
                     cars=14, packStep=0.016, air=0.15, liveryFrom=15),
    # The three toadstools on the outcrop, with the climb past them. Pinned and
    # cropped tight: they are one landmark on a long green hillside and the
    # scan has no idea they are there.
    "shroom": dict(at=0.26, azimuth=0.60, pitch=0.38, pad=0.42, span=0.10,
                   cars=10, air=0.12, liveryFrom=6),
}


def frame_for(slug):
    """The framing for one track: the defaults with its own entry over them."""
    return dict(DEFAULT, **FRAMES.get(slug, {}))


# ---------------------------------------------------------------------------
# In the page
# ---------------------------------------------------------------------------

SCAN = r"""
(span) => {
  const S = window.DriveShot.S, L = S.built.line, sA = S.built.s;
  const total = sA[sA.length - 1];
  const idxAt = (f) => { const t = total * f; let i = 1;
    while (i < sA.length - 1 && sA[i] < t) i++; return i; };
  const rows = [];
  for (let f = 0; f < 1; f += 0.02) {
    const i0 = idxAt(f), i1 = idxAt(Math.min(0.999, f + span));
    if (i1 <= i0) continue;
    let minY = 1e9, maxY = -1e9, roll = 0, inverted = 0, bend = 0;
    let prev = null, prevH = null;
    for (let i = i0; i <= i1; i++) {
      const st = L[i];
      minY = Math.min(minY, st.p[1]); maxY = Math.max(maxY, st.p[1]);
      // How far the road has rolled off level: 0 flat, 1 on its side, 2
      // inverted. A half-pipe and a loop both show up here and nowhere else.
      roll += 1 - st.n[1];
      if (st.n[1] < 0) inverted++;
      // And how much it turns in plan, which is the only thing a flat track
      // has to offer a camera.
      if (prev) {
        const h = Math.atan2(st.p[0] - prev[0], st.p[2] - prev[2]);
        if (prevH != null) {
          let d = h - prevH;
          while (d > Math.PI) d -= 2 * Math.PI;
          while (d < -Math.PI) d += 2 * Math.PI;
          bend += Math.abs(d);
        }
        prevH = h;
      }
      prev = st.p;
    }
    const n = i1 - i0 + 1;
    rows.push({ f: +f.toFixed(3), i0, i1,
                rise: +(maxY - minY).toFixed(1),
                roll: +(roll / n).toFixed(3),
                bend: +bend.toFixed(2),
                inverted: +(inverted / n).toFixed(2) });
  }
  return rows;
}
"""

SHOOT = r"""
async (a) => {
  const C = window.DriveShot, S = C.S, THREE = C.THREE, L = S.built.line;

  // **Stop the loop, then let the frame already in flight land.** Without the
  // wait that pending frame runs after this returns, calls the game's own
  // `shotCamera()` and repaints - so the screenshot is the game's framing with
  // our cars as specks in it.
  window.requestAnimationFrame = () => 0;
  await new Promise(r => setTimeout(r, 150));

  (window.__coverCars || []).forEach(v => v.dispose());
  window.__coverCars = [];

  const pts = [];
  for (let i = a.i0; i <= a.i1; i++) pts.push(new THREE.Vector3(...L[i].p));
  const box = new THREE.Box3().setFromPoints(pts);
  const centre = box.getCenter(new THREE.Vector3());
  const radius = box.getSize(new THREE.Vector3()).length() / 2;

  let s = a.seed || 1;
  const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;

  // **The field goes out in packs.** Cars at even spacing along the window are
  // a diagram of a road with dots on it; a race is three or four groups with
  // clear air between them and the cars inside a group staggered across the
  // width. Both the sizes and the gaps come off the same seeded generator as
  // everything else here, so a given `seed` is a given picture.
  const packs = [];
  for (let left = a.cars; left > 0; ) {
    const n = Math.min(left, 1 + Math.floor(rnd() * 3.4));
    packs.push(n);
    left -= n;
  }
  const gaps = packs.map(() => 0.55 + rnd());
  const span = gaps.reduce((x, y) => x + y, 0);
  const slots = [];
  let cursor = 0;
  for (let g = 0; g < packs.length; g++) {
    const t0 = a.carFrom + (a.carTo - a.carFrom) * (cursor / span);
    for (let j = 0; j < packs[g]; j++) {
      // Inside a pack: a short stagger down the road and alternating sides, so
      // three cars read as three cars and not as one wide one.
      slots.push({ t: Math.min(a.carTo, t0 + j * a.packStep),
                   lane: (j % 2 ? 1 : -1) * (0.20 + 0.42 * rnd()) });
    }
    cursor += gaps[g];
  }

  for (let k = 0; k < slots.length; k++) {
    const sl = slots[k];
    const i = Math.max(0, Math.min(L.length - 1,
                                   Math.round(a.i0 + (a.i1 - a.i0) * sl.t)));
    const st = L[i];
    const p = L[Math.max(0, i - 2)], q = L[Math.min(i + 2, L.length - 1)];
    const fwd = new THREE.Vector3(q.p[0]-p.p[0], q.p[1]-p.p[1], q.p[2]-p.p[2]).normalize();
    const up = new THREE.Vector3(...st.n).normalize();
    const lat = new THREE.Vector3(...st.lat).normalize();
    // Some of the field is in the air. All four wheels down everywhere reads as
    // a diagram; one car off the road reads as a race. `air` is a fraction so a
    // track with nothing to jump off can ask for none.
    //
    // **A car over a gap is airborne by construction and does not get a vote.**
    // `builder.gap` keeps emitting stations across a hole and flags them `air`,
    // following a rough ballistic bow, so a car placed on one is already out in
    // the middle of the jump - nose up on the way out, nose down on the way in,
    // because `fwd` is read off its neighbours. All it needs is to be told not
    // to lay a shadow on a surface that is not there. This is what puts the
    // field over Mount Joy's ski jump rather than parked at the lip.
    const overGap = !!st.air;
    const flying = overGap || rnd() < a.air;
    const lift = flying && !overGap ? 1.4 + rnd() * 4.5 : 0.55;
    const pos = new THREE.Vector3(...st.p)
      .addScaledVector(lat, sl.lane * st.hw)
      .addScaledVector(up, lift);
    const back = fwd.clone().negate();
    const right = new THREE.Vector3().crossVectors(up, back).normalize();
    const rot = new THREE.Quaternion().setFromRotationMatrix(
      new THREE.Matrix4().makeBasis(right, up, back));
    rot.multiply(new THREE.Quaternion().setFromAxisAngle(
      new THREE.Vector3(0, 1, 0), (rnd() * 2 - 1) * 0.16));
    const view = new C.CarView(S.renderer.scene,
      a.liveries[(k + (a.liveryFrom || 0)) % a.liveries.length]);
    view.update(pos, rot, { steer: (rnd()*2-1)*0.3, lean: (rnd()*2-1)*0.22,
                            spin: 2 + rnd()*2 });
    // No contact shadow for a car in the air - it would be a disc on a surface
    // the car is nowhere near.
    if (flying) view.shadow.visible = false;
    window.__coverCars.push(view);
  }

  // **Fitted against whichever angle is tighter, which is what lets the sizes
  // share a composition.** A three.js `fov` is the *vertical* angle, so at one
  // distance a portrait canvas shows no more vertically and much less
  // horizontally - the 800x1200 cover would have cut the subject in half.
  const vFov = a.fov * Math.PI / 180;
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * S.renderer.camera.aspect);
  const dist = radius / Math.sin(Math.min(vFov, hFov) / 2) * a.pad;
  const cam = S.renderer.camera;
  cam.position.set(
    centre.x + dist * Math.cos(a.pitch) * Math.cos(a.azimuth),
    centre.y + dist * Math.sin(a.pitch),
    centre.z + dist * Math.cos(a.pitch) * Math.sin(a.azimuth));
  cam.up.set(0, 1, 0);        // a high establishing shot is level with the world
  cam.lookAt(centre);
  cam.fov = a.fov;
  // The sky dome and the fog are built for a camera on the road; from up here
  // the far plane has to reach whatever we backed off to.
  cam.far = Math.max(2600, dist * 3);
  cam.updateProjectionMatrix();

  // **Bring the sky and the key light with the camera**, which the game does
  // every frame in `updateCamera` and this composition was not doing at all.
  // The dome is a 1800-unit sphere that has to be centred on the eye or you are
  // looking at the inside of a ball parked somewhere else - and the sun is a
  // sprite pinned to it, so flying a camera two hundred units out turned Big
  // Red's sunset into a mauve disc hanging in the middle distance like a
  // planet. The light is kept on the *window* rather than on the frozen car for
  // the same reason: the car is on the start line and the picture usually is
  // not, so half a lap away the stretch in frame was outside the lit region.
  if (S.renderer.sky) S.renderer.sky.position.copy(cam.position);
  if (S.renderer.sun) {
    S.renderer.sun.position.copy(centre).add(S.renderer.lightDir);
    S.renderer.sun.target.position.copy(centre);
    S.renderer.sun.target.updateMatrixWorld();
  }

  // **Keep drawing, or the screenshot is of a frame nobody composed.**
  // three.js takes the WebGL default `preserveDrawingBuffer: false`, so the
  // drawing buffer is not guaranteed to survive being composited - and a
  // screenshot is a fresh composite some milliseconds after the render. One
  // `render()` and a wait produced, on Spa, a picture of the framing the page
  // had *before* this function ran, with none of the cars in it, while the
  // camera and the cars were provably right when queried afterwards. Redrawing
  // on an interval means whatever moment the screenshot lands on, a current
  // frame is there to be taken. `requestAnimationFrame` is not available for
  // this - stopping it is what stops the game repainting over us.
  clearInterval(window.__coverTick);
  window.__coverTick = setInterval(() => S.renderer.render(0.016), 40);
  S.renderer.render(0.016);
  return { radius: +radius.toFixed(1), dist: +dist.toFixed(1) };
}
"""


def pick_window(rows, at, span):
    """Which stretch of the lap is in frame."""
    # `at` is where the window *starts*, not its centre. It reads worse and it
    # is what the chosen framings were picked against - centring instead slides
    # Rainbow Road's loop a twelfth of a lap to the left and out of the shot.
    if at is not None:
        return min(rows, key=lambda r: abs(r["f"] - at))
    # Geometry first (a loop or a pipe beats everything), then a climb, then
    # how much the road turns in plan - which is all a flat track has.
    return max(rows, key=lambda r: r["roll"] * 2 + r["rise"] / 40 + r["bend"] / 6)


# How long to give the track mesh, the sky, the scenery below and the shader
# precompile before anything is composed on top of them. Software GL, and the
# longest tracks in the pool are three times the size of the shortest.
BUILD_MS = 7000


class Hero:
    """One browser for a run; one page per track and size.

    Worth the class for the same reason `_shots.Shooter` is: launching the
    browser and building a track are most of the cost, and every caller here
    wants several pictures of the same world.
    """

    def __init__(self, base):
        self.base = base
        self._pw = self._browser = None
        self.errors = []

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(args=GL_FLAGS)
        return self

    def __exit__(self, *exc):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        return False

    def open(self, slug, size):
        """A built, settled `?shot=1` page for `slug` at `size`."""
        page = self._browser.new_page(
            viewport={"width": size[0], "height": size[1]})
        page.on("console", lambda m: (self.errors.append((slug, m.text))
                                      if m.type == "error" else None))
        page.on("pageerror", lambda e: self.errors.append((slug, "uncaught: %s" % e)))
        page.goto("%s/solo/%s?shot=1" % (self.base, slug),
                  wait_until="load", timeout=90000)
        page.wait_for_function("window.DriveShot && window.DriveShot.S.built",
                               timeout=90000)
        page.wait_for_timeout(BUILD_MS)
        return page

    def compose(self, page, cfg, **over):
        """Put the cars out and point the camera. Returns the fitted distance."""
        a = dict(cfg, **over)
        rows = page.evaluate(SCAN, a["span"])
        win = pick_window(rows, a["at"], a["span"])
        a = dict(a, i0=win["i0"], i1=win["i1"], liveries=LIVERIES)
        for k in ("at", "span"):
            a.pop(k, None)
        res = page.evaluate(SHOOT, a)
        # Let the redraw interval land at least one frame after the compose
        # before anything is captured.
        page.wait_for_timeout(400)
        return dict(res, f=win["f"])


# ---------------------------------------------------------------------------
# Taking the picture
# ---------------------------------------------------------------------------

# 16:9, to match the card it is shown in. Big enough to look sharp on a dense
# screen and to upscale into the 1200x630 share card, small enough that
# nineteen of them are not a burden in the repo.
CARD = (960, 540)


def shoot(slugs, out_dir, size=CARD, port=5097):
    """One hero shot per slug, written to `out_dir/<slug>.png`.

    Returns `(written, failed, errors)`. A track whose scenery throws still
    renders a plausible picture of the road with nothing on it, so the errors
    matter more than the file sizes.
    """
    written, failed = [], []
    os.makedirs(out_dir, exist_ok=True)
    with serving(port) as base, Hero(base) as hero:
        for slug in slugs:
            out = os.path.join(out_dir, slug + ".png")
            # Before the shot, not after: a browser that fell over leaves the
            # old file in place and its size then reads as a picture taken.
            if os.path.exists(out):
                os.remove(out)
            page = hero.open(slug, size)
            try:
                res = hero.compose(page, frame_for(slug))
                page.screenshot(path=out)
            finally:
                page.close()
            if os.path.exists(out):
                written.append(slug)
                print("  %-12s %6.1f kB   f=%.2f dist=%.0f"
                      % (slug, os.path.getsize(out) / 1024.0, res["f"], res["dist"]))
            else:
                failed.append(slug)
                print("  %-12s FAILED" % slug)
        errors = list(hero.errors)
    return written, failed, errors


# ---------------------------------------------------------------------------
# Choosing an angle
# ---------------------------------------------------------------------------

# Four sides at two heights. The sides are a quarter-turn apart starting off
# axis, because a camera on an axis of a track laid out on a grid looks at the
# road end-on.
EXPLORE_AZ = (0.6, 2.05, 3.5, 5.0)
EXPLORE_PIT = (0.34, 0.52)
EXPLORE_TILE = (640, 360)
VIEWS = os.path.join(HERE, "views", "_hero")


def _sheet(tiles, out, cols):
    """Labelled thumbnails as one picture, because eight files is eight looks."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = EXPLORE_TILE
    bar = 26
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, (h + bar) * rows), "#12131a")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=17)
    except TypeError:                                    # pragma: no cover
        font = ImageFont.load_default()
    for k, (label, path) in enumerate(tiles):
        x, y = (k % cols) * w, (k // cols) * (h + bar)
        sheet.paste(Image.open(path).convert("RGB"), (x, y))
        draw.text((x + 8, y + h + 4), label, font=font, fill="#dfe4ea")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    return out


def _shots_to_sheet(hero, slug, shots, out, cols):
    """Compose and capture each of `shots`, then lay them out as one sheet."""
    import tempfile

    page = hero.open(slug, EXPLORE_TILE)
    tiles = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for label, over in shots:
                hero.compose(page, frame_for(slug), **over)
                p = os.path.join(tmp, label.replace(" ", "") + ".png")
                page.screenshot(path=p)
                tiles.append((label, p))
            return _sheet(tiles, out, cols)
    finally:
        page.close()


def explore(slugs, port=5098, **over):
    """Four sides at two heights, one sheet per track."""
    out = []
    with serving(port) as base, Hero(base) as hero:
        for slug in slugs:
            # The grid is the angles, so it wins over anything passed in - what
            # `over` is for here is trying the whole grid at a different `pad`.
            # A `pitch` is the exception and narrows the grid to one row, which
            # is the only way to look round a track from a height the two
            # standard ones cannot reach: the Costco's aisles are under a roof,
            # so every candidate for it is below 0.2 and the default pair
            # photograph the roof twice.
            pitches = (over["pitch"],) if "pitch" in over else EXPLORE_PIT
            shots = [("az=%.2f  pit=%.2f" % (az, pit),
                      dict(over, azimuth=az, pitch=pit))
                     for pit in pitches for az in EXPLORE_AZ]
            out.append(_shots_to_sheet(hero, slug, shots,
                                       os.path.join(VIEWS, slug + ".png"),
                                       len(EXPLORE_AZ)))
            print("  %-12s -> %s" % (slug, os.path.relpath(out[-1], ROOT)))
        for slug, msg in hero.errors:
            print("  ! %s: %s" % (slug, msg))
    return out


# Where the scan's answer is not the picture: the Costco's roof beats its own
# storefront on bend alone, and Sandy Cove's pier over open water loses to the
# switchbacks inland. Neither is a scoring bug - "the thing this track is known
# for" is not in the ribbon - so the answer is to look along the lap and pin
# `at` by hand.
SWEEP_AT = (0.02, 0.14, 0.26, 0.38, 0.50, 0.62, 0.74, 0.86)


def sweep(slugs, port=5098, **over):
    """The same angle at eight points round the lap, one sheet per track."""
    out = []
    with serving(port) as base, Hero(base) as hero:
        for slug in slugs:
            shots = [("at=%.2f" % at, dict(over, at=at)) for at in SWEEP_AT]
            out.append(_shots_to_sheet(hero, slug, shots,
                                       os.path.join(VIEWS, slug + "-at.png"), 4))
            print("  %-12s -> %s" % (slug, os.path.relpath(out[-1], ROOT)))
        for slug, msg in hero.errors:
            print("  ! %s: %s" % (slug, msg))
    return out


def main(argv):
    sys.path.insert(0, ROOT)
    import tracks as tracks_mod

    # A whole pool of contact sheets is an hour of software GL and the tracks
    # are independent, so `--port` is here to let several runs of this go at
    # once, each with its own app and its own browser.
    args, opt = argv[1:], {}
    for name, cast in (("--port", int), ("--az", float), ("--pit", float),
                       ("--pad", float), ("--span", float), ("--at", float)):
        if name in args:
            i = args.index(name)
            opt[name[2:]] = cast(args[i + 1])
            args = args[:i] + args[i + 2:]

    slugs = [a for a in args if not a.startswith("-")]
    if "--all" in args:
        slugs = [t["slug"] for t in tracks_mod.TRACKS]
    if not slugs:
        print(__doc__.strip().splitlines()[0])
        print("usage: python tools/_hero.py [--sweep] [--port N] "
              "[--az A --pit P --pad F --span F] <slug>... | --all")
        return 1
    unknown = [s for s in slugs if not tracks_mod.get(s)]
    if unknown:
        print("no such track: " + ", ".join(unknown))
        return 1

    port = opt.pop("port", 5098)
    over = {k: v for k, v in (("azimuth", opt.get("az")),
                              ("pitch", opt.get("pit")),
                              ("pad", opt.get("pad")),
                              ("span", opt.get("span")),
                              ("at", opt.get("at"))) if v is not None}
    (sweep if "--sweep" in args else explore)(slugs, port=port, **over)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
