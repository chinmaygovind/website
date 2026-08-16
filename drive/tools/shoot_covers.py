"""Cover art: a stretch of a track from high up, with a field of cars on it.

    python tools/shoot_covers.py                 # every track in COVERS, every size
    python tools/shoot_covers.py rainbow         # one track
    python tools/shoot_covers.py rainbow --explore   # candidate angles, to choose from

These are **not** the switcher's preview pictures (`shoot_tracks.py`) or a share
card (`shoot_og_cards.py`). Those are of a track; these are of the game, for a
storefront - a portal wants a 1920x1080, an 800x1200 and an 800x800 of something
that looks like the game is worth playing, and a picture of an empty road is not
that. So this puts cars on the road, points a camera at the most interesting
piece of geometry the lap has, and lays the wordmark over the bottom.

**It is the real game, not a render of it.** The page is loaded at `?shot=1` -
HUD off, player car hidden, car frozen - and then the frame loop is stopped and
the scene composed through `window.DriveShot`, which that mode exposes. The cars
are the game's own `CarView` on the ribbon's own frame, so a car in a loop is
upside down because the road is.

**Two things here go stale silently**, the same way the track previews do:
change a track's geometry, palette or sky and its cover is of the old one, and
nothing will fail. Re-run this, look at the pictures, and commit them.

The framing per track is recorded in `COVERS` below and was chosen by running
`--explore` and looking at the results. It is not derived, because "which way
round is dramatic" is not a thing a number knows - but *where* is: the window is
picked by scanning the lap for geometry (a loop or a pipe rolls the road's
normal off vertical; a climb moves it in Y; a twisty bit turns it in plan), so
a track whose corners move keeps a sensible window without anybody re-measuring.
"""

import argparse
import base64
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shots import GL_FLAGS, serving

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.dirname(HERE)
OUT = os.path.join(DRIVE, "covers")

SIZES = [(1920, 1080), (800, 1200), (800, 800)]

# The garage's own paints, so every car on a cover is a car somebody could build.
PAINTS = ["#e8453c", "#3d8bfd", "#f2c94c", "#27ae60",
          "#bb6bd9", "#f2994a", "#56ccf2", "#f178b6"]

# Per track: where to stand, and how many cars to put out. `at` is a fraction of
# the lap to centre the window on, or None to let the scan choose; `pad` is a
# fraction of the distance that would fit the whole window, so under 1 crops
# into it, which is what a cover wants.
COVERS = {
    # The loop, the hairpin under it, and the ribbon running out to the stars.
    # `at` is pinned because the scan would also accept the half-pipes either
    # side of it and the loop is the picture.
    "rainbow": dict(at=0.68, azimuth=2.05, pitch=0.44, pad=0.50, fov=50,
                    cars=14, carFrom=0.10, carTo=0.86, seed=11),
    # Down through the trees with the sponsor boards on the outside. Flatter
    # than Rainbow Road, so the camera sits lower - from the same height as the
    # loop shot this reads as a map.
    "spa":     dict(at=None, azimuth=2.05, pitch=0.34, pad=0.50, fov=50,
                    cars=14, carFrom=0.10, carTo=0.86, seed=11),
    # The sun is what this track is called after, so the angle is the one that
    # has it in frame. `pad` is looser than the other two: at 0.50 the nearest
    # cars were half out of the bottom corner.
    "sunrise": dict(at=None, azimuth=2.05, pitch=0.34, pad=0.58, fov=50,
                    cars=14, carFrom=0.10, carTo=0.86, seed=11),
}


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
  for (let k = 0; k < a.cars; k++) {
    const t = a.carFrom + (a.carTo - a.carFrom) * (k / Math.max(1, a.cars - 1));
    const i = Math.max(0, Math.min(L.length - 1, Math.round(a.i0 + (a.i1 - a.i0) * t)));
    const st = L[i];
    const p = L[Math.max(0, i - 2)], q = L[Math.min(i + 2, L.length - 1)];
    const fwd = new THREE.Vector3(q.p[0]-p.p[0], q.p[1]-p.p[1], q.p[2]-p.p[2]).normalize();
    const up = new THREE.Vector3(...st.n).normalize();
    const lat = new THREE.Vector3(...st.lat).normalize();
    // One in four is in the air. A field of cars all glued to the tarmac reads
    // as a diagram; one car off the road reads as a race.
    const lift = k % 4 === 0 ? 1.4 + rnd() * 4.5 : 0.55;
    const pos = new THREE.Vector3(...st.p)
      .addScaledVector(lat, (rnd() * 2 - 1) * 0.62 * st.hw)
      .addScaledVector(up, lift);
    const back = fwd.clone().negate();
    const right = new THREE.Vector3().crossVectors(up, back).normalize();
    const rot = new THREE.Quaternion().setFromRotationMatrix(
      new THREE.Matrix4().makeBasis(right, up, back));
    rot.multiply(new THREE.Quaternion().setFromAxisAngle(
      new THREE.Vector3(0, 1, 0), (rnd() * 2 - 1) * 0.16));
    const view = new C.CarView(S.renderer.scene,
      { body: a.paints[k % a.paints.length], finish: 'gloss' });
    view.update(pos, rot, { steer: (rnd()*2-1)*0.3, lean: (rnd()*2-1)*0.22,
                            spin: 2 + rnd()*2 });
    // No contact shadow for a car in the air - it would be a disc on a surface
    // the car is nowhere near.
    if (lift > 1.2) view.shadow.visible = false;
    window.__coverCars.push(view);
  }

  // **Fitted against whichever angle is tighter, which is what lets the three
  // sizes share a composition.** A three.js `fov` is the *vertical* angle, so at
  // one distance a portrait canvas shows no more vertically and much less
  // horizontally - the 800x1200 would have cut the subject in half.
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


# ---------------------------------------------------------------------------
# The wordmark
# ---------------------------------------------------------------------------

def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _light_wheel(px):
    """`static/img/icon.svg`, recoloured for a dark ground, at `px` square.

    The shipped mark is a dark rim with light spokes, which is the way round
    that works on the nav's paper and a smudge on a night sky. This keeps the
    mark's own tonal structure and inverts it: rim brightest, spokes a step
    down so the Y still reads against it, boss dark.
    """
    svg = open(os.path.join(DRIVE, "static", "img", "icon.svg")).read()
    svg = re.sub(r"<title>.*?</title>", "", svg, flags=re.S)
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    svg = svg.replace('"#3d444d"', '"#ffffff"').replace('"#5c6672"', '"#ffffff"')
    svg = svg.replace('"#949ca8"', '"#d5dcea"')
    return re.sub(r'width="64" height="64"', 'width="%d" height="%d"' % (px, px),
                  svg, count=1)


TITLE_PAGE = """
<!doctype html><meta charset="utf-8">
<style>
  @font-face {{ font-family:"Titillium Web"; font-weight:900; font-display:block;
    src:url(data:font/woff2;base64,{font}) format("woff2"); }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{w}px; height:{h}px; overflow:hidden; }}
  .shot {{ position:relative; width:{w}px; height:{h}px;
           background:url(data:image/png;base64,{img}) center/cover no-repeat; }}
  /* A scrim, not a bar. The foot of these pictures is already dark, so this
     only buys the last of the contrast - anything heavier reads as a black
     band with a logo parked on it. */
  .scrim {{ position:absolute; left:0; right:0; bottom:0; height:44%;
            background:linear-gradient(to top, rgba(8,4,20,.82),
                       rgba(8,4,20,.45) 42%, rgba(8,4,20,0)); }}
  .mark {{ position:absolute; left:0; right:0; bottom:{bottom}px;
           display:flex; align-items:center; justify-content:center; gap:{gap}px;
           font-family:"Titillium Web",sans-serif; font-weight:900;
           text-transform:uppercase; color:#fff; line-height:.92;
           letter-spacing:.04em; font-size:{size}px;
           text-shadow:0 {sh}px {sh2}px rgba(0,0,0,.55); }}
  .mark svg {{ display:block; }}
</style>
<div class="shot"><div class="scrim"></div>
  <div class="mark">{wheel}<span>Drive</span></div>
</div>
"""


def _title(page, png, w, h):
    """Lay the wordmark over `png` and screenshot it back."""
    # Everything scales off the short edge, so the mark keeps its proportions
    # at 1920x1080 and at 800x800.
    k = min(w, h) / 1000.0
    html = TITLE_PAGE.format(
        w=w, h=h, img=_b64(png),
        font=_b64(os.path.join(DRIVE, "static", "fonts", "titillium-900.woff2")),
        wheel=_light_wheel(int(164 * k)),
        bottom=int(56 * k), gap=int(34 * k), size=int(158 * k),
        sh=max(1, int(3 * k)), sh2=max(2, int(14 * k)))
    page.set_content(html)
    page.wait_for_timeout(500)


# ---------------------------------------------------------------------------

def _pick_window(rows, at, span):
    # `at` is where the window *starts*, not its centre. It reads worse and it
    # is what the chosen framings were picked against - centring instead slides
    # Rainbow Road's loop a twelfth of a lap to the left and out of the shot.
    if at is not None:
        return min(rows, key=lambda r: abs(r["f"] - at))
    # Geometry first (a loop or a pipe beats everything), then a climb, then
    # how much the road turns in plan - which is all a flat track has.
    return max(rows, key=lambda r: r["roll"] * 2 + r["rise"] / 40 + r["bend"] / 6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tracks", nargs="*", default=None)
    ap.add_argument("--explore", action="store_true",
                    help="candidate angles at 1280x720, to choose from")
    ap.add_argument("--span", type=float, default=0.16,
                    help="how much of the lap is in frame")
    args = ap.parse_args()
    tracks = args.tracks or list(COVERS)

    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    with serving(5098) as base:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=GL_FLAGS)
            for slug in tracks:
                cfg = COVERS.get(slug)
                if cfg is None:
                    print("no cover config for %s" % slug)
                    continue
                sizes = [(1280, 720)] if args.explore else SIZES
                for (w, h) in sizes:
                    page = browser.new_page(viewport={"width": w, "height": h})
                    errs = []
                    page.on("pageerror", lambda e: errs.append(str(e)))
                    page.goto("%s/solo/%s?shot=1" % (base, slug),
                              wait_until="load", timeout=90000)
                    page.wait_for_function("window.DriveShot && window.DriveShot.S.built",
                                           timeout=90000)
                    # The track build and the shader precompile both have to be
                    # done, or the picture is of a half-built world.
                    page.wait_for_timeout(7000)
                    rows = page.evaluate(SCAN, args.span)
                    win = _pick_window(rows, cfg["at"], args.span)

                    shots = ([(az, pit) for az in (0.6, 2.05, 3.5, 5.0)
                                        for pit in (0.34, 0.55)]
                             if args.explore else [(cfg["azimuth"], cfg["pitch"])])
                    for az, pit in shots:
                        a = dict(cfg, i0=win["i0"], i1=win["i1"], azimuth=az,
                                 pitch=pit, paints=PAINTS)
                        a.pop("at")
                        res = page.evaluate(SHOOT, a)
                        # Let the redraw interval land at least one frame after
                        # the compose before anything is captured.
                        page.wait_for_timeout(400)
                        if args.explore:
                            out = os.path.join(OUT, "_explore",
                                               "%s-az%.2f-pit%.2f.png" % (slug, az, pit))
                            os.makedirs(os.path.dirname(out), exist_ok=True)
                            page.screenshot(path=out)
                        else:
                            plain = os.path.join(OUT, "%s_%dx%d.png" % (slug, w, h))
                            page.screenshot(path=plain)
                            _title(page, plain, w, h)
                            page.screenshot(path=os.path.join(
                                OUT, "%s_%dx%d-title.png" % (slug, w, h)))
                        print("  %-8s %4dx%-4d f=%.2f az=%.2f pit=%.2f dist=%.0f"
                              % (slug, w, h, win["f"], az, pit, res["dist"]))
                    if errs:
                        print("  PAGE ERRORS:", errs[:3])
                    page.close()
            browser.close()


if __name__ == "__main__":
    main()
