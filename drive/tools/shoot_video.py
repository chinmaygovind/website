"""The store preview video: five beats of the real game, rendered frame by frame.

    python tools/shoot_video.py --beat cover      # one beat
    python tools/shoot_video.py                   # every beat, then the cuts
    python tools/shoot_video.py --aspect portrait

CrazyGames wants two videos - **1920x1080 (16:9)** and **1080x1620 (2:3)** - of
at most 20 seconds, under 50MB, **silent**, and starting seamlessly from the
store cover (`covers/spa_1920x1080-title.png`). The edit is 15.5s:

    0.0- 3.0  the Spa cover, pushing in, with the cars running
    3.0- 6.0  Rainbow Road, the multiplayer pack            race 113
    6.0- 9.0  Big Red, first person                         chinmay's board lap
    9.0-11.5  Mount Joy, up the ramp                        race 95
   11.5-15.5  winning a multiplayer race                    race 113

**This renders rather than screen-records, and that is the whole point.** A
recorded viewport gave 1852x990 with an audio track and the site's own buttons in
frame - off-spec on resolution, aspect and sound at once, and unccroppable to
either required shape. Rendering hits both sizes natively and can be re-run when
a track changes, which the covers and the switcher previews already need
(`covers/README.md`).

**How it draws.** `?shot=1` is the mode the covers use: HUD off, player car
hidden, the frame loop stopped, and the scene exposed on `window.DriveShot`. So
the opener is composed by the *same* code that made the cover - `shoot_covers`'s
own `SCAN`, `_pick_window` and framing maths, imported rather than copied - and
frame 0 is therefore the cover by construction rather than by eye. The wordmark
is not drawn per frame: it is one transparent PNG laid over the beat by ffmpeg
and faded out, which is both faster and the only way the first frame can be
pixel-identical to the shipped `-title` cover.

**Nothing here may touch the simulation.** The cars in the opener are composed
`CarView`s on the ribbon's own frame, exactly as on the cover - the same fiction,
moved. The other four beats are real recorded laps played back, so what is on
screen is what somebody drove.
"""

import argparse
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shots import GL_FLAGS, serving
from shoot_covers import COVERS, PAINTS, SCAN, _pick_window, _b64, _light_wheel

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.dirname(HERE)
OUT = os.path.join(DRIVE, "video")

FPS = 30
SPAN = 0.16                      # how much of the lap the opener frames

# Simulation steps per captured frame, for the replay beats.
#
# **This is what takes the judder out of the chase camera.** A recorded pose is
# 15Hz (`course.js` GHOST_HZ) and `Ghost.at` interpolates it *linearly*, so the
# speed `updateWatch` measures off it - `p.distanceTo(prev)/dt` - is a step
# function that changes twice a video frame. The chase camera feeds that speed
# into how far back it sits and how hard it chases (`render.js` follow), so the
# whole frame lurches on every step. Running the loop at 120Hz and photographing
# every fourth frame gives that exponential smoother four times as many bites,
# which is what a browser at 120fps would do anyway - so the beat is the game
# rendered properly rather than the game rendered coarsely.
#
# First person needs none of it and shows none of it: that camera *cuts* to the
# eye position every frame instead of chasing, which is why Big Red was the one
# beat that already looked right.
SUBSTEPS = 4

# Both required shapes. Portrait is framed, not cropped: a 2:3 crop out of the
# 16:9 cut throws away a third of the frame and puts the camera somewhere
# nobody chose.
ASPECTS = {
    "landscape": (1920, 1080),
    "portrait": (1080, 1620),
}

# The edit. `secs` is how long the beat is on screen; `start` is where in the
# recording it begins, in seconds, chosen by looking at `--probe` sheets.
BEATS = [
    dict(name="cover", secs=3.0),
    # Both multiplayer beats are the *same* race - the pack early on and the
    # flag at the end - so the video has one race running through it rather
    # than two unrelated clips.
    # The field is only together at the start - he wins this race by 2.75s, so
    # by t=8 there is nobody else in shot and it stops being a multiplayer beat.
    dict(name="pack", secs=3.0, url="/race/113", follow="chinmay", start=2.0),
    # Into Big Red's loop, which is the one climb on a track that otherwise only
    # falls, and the only thing on it worth three seconds of a driver's seat.
    dict(name="firstperson", secs=3.0, url="/solo/bigred?watch=97", start=18.0,
         view="first"),
    # Mount Joy is "a boost pad, a ski jump onto the peak": the blue run-in is
    # at t=9 and the car is off the lip and airborne against the sun at t=12.
    dict(name="ramp", secs=2.5, url="/race/95", follow="chinmay", start=10.0),
    # chinmay takes the flag at 49.700, so this ends just past it - at 45.7 the
    # beat ran out 0.06s before he crossed, which is the one thing it is for.
    dict(name="win", secs=4.0, url="/race/113", follow="chinmay", start=46.1),
]

# What comes off the frame. The site's own furniture goes; what names the track
# stays. `#modeLabel` reads "Race replay", which is true and is not what a
# storefront should be told, and `#watchBar` carries a Leave button.
HIDE = """
  #watchBar, #modeLabel, #meters, .hbtn, #startHint, #firstBanner,
  #toast, #btnWatchStop { display: none !important; }
  /* The cursor is a real pixel in a screenshot. */
  * { cursor: none !important; }
"""

# The game's own loop, taken off the compositor and onto a queue we pump. This
# is why the beats are the real game rather than a re-implementation of it:
# `frame()` runs untouched, with its own camera, its own interpolation and its
# own HUD - only the clock driving it is ours. Screenshotting a live rAF loop
# instead would sample it at whatever moment the capture landed, which at ~0.09s
# a frame is nowhere near 30Hz and would stutter.
PUMP = """() => {
  window.__raf = [];
  window.__t = performance.now();
  // Kept, because hijacking rAF also takes away the only way to ask Chrome for
  // a composited frame - and `page.screenshot` waits for one. Without this the
  // capture sits until it times out, having rendered everything correctly.
  window.__realRaf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => { window.__raf.push(cb); return window.__raf.length; };
  window.__pump = (ms) => {
    window.__t += ms;
    const q = window.__raf; window.__raf = [];
    for (const cb of q) { try { cb(window.__t); } catch (e) { window.__err = String(e); } }
  };
  window.__present = () => new Promise(r => window.__realRaf(() => r(1)));
}"""


# ---------------------------------------------------------------------------
# In the page: the opener
# ---------------------------------------------------------------------------

# Build the field once. Creating and disposing fourteen CarViews per frame is
# most of a frame's cost, and the cars do not change - only where they are.
OPEN_SETUP = r"""
async (a) => {
  const C = window.DriveShot, S = C.S, THREE = C.THREE, L = S.built.line;
  window.requestAnimationFrame = () => 0;
  await new Promise(r => setTimeout(r, 150));

  (window.__vidCars || []).forEach(v => v.dispose());
  const pts = [];
  for (let i = a.i0; i <= a.i1; i++) pts.push(new THREE.Vector3(...L[i].p));
  const box = new THREE.Box3().setFromPoints(pts);
  const centre = box.getCenter(new THREE.Vector3());
  const radius = box.getSize(new THREE.Vector3()).length() / 2;

  let s = a.seed || 1;
  const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
  const cars = [];
  for (let k = 0; k < a.cars; k++) {
    // Every per-car random the cover drew is drawn once, here, and kept - so a
    // car's lane, its lift and its yaw stay its own as it moves. Re-rolling
    // them per frame is a field of cars twitching in place.
    //
    // **Drawn in `shoot_covers.SHOOT`'s exact order**, because they come off one
    // seeded sequence: lift (and only when this car is one of the airborne
    // quarter), then lane, then yaw, then the three the CarView gets. Swapping
    // any two shifts every later car onto a different number and frame 0 stops
    // being the cover - it was 39dB PSNR against it with lane and lift the wrong
    // way round, which looks right and is not.
    const lift = k % 4 === 0 ? 1.4 + rnd() * 4.5 : 0.55;
    const lane = (rnd() * 2 - 1) * 0.62;
    const yaw = (rnd() * 2 - 1) * 0.16;
    cars.push({
      t0: a.carFrom + (a.carTo - a.carFrom) * (k / Math.max(1, a.cars - 1)),
      lane: lane,
      lift: lift,
      yaw: yaw,
      steer: (rnd() * 2 - 1) * 0.3,
      lean: (rnd() * 2 - 1) * 0.22,
      spin: 2 + rnd() * 2,
      view: new C.CarView(S.renderer.scene,
                          { body: a.paints[k % a.paints.length], finish: 'gloss' }),
    });
  }
  window.__vidCars = cars.map(c => c.view);
  window.__vid = { cars, centre, radius, i0: a.i0, i1: a.i1 };
  return { radius: +radius.toFixed(1) };
}
"""

# One frame of the opener. `phase` is seconds into the beat; `pad` is the
# cover's framing multiplier, shrunk over the beat to push the camera in.
OPEN_FRAME = r"""
(a) => {
  const C = window.DriveShot, S = C.S, THREE = C.THREE, L = S.built.line;
  const V = window.__vid;

  // Between two stations, not at one. **`Math.round` here is what made the
  // opener judder**: the ribbon's stations are metres apart, so snapping to the
  // nearest one moves a car in visible hops - a couple a second at this speed -
  // while the camera slid smoothly past it. Every frame was a different picture,
  // so nothing downstream could see it; the cars were simply teleporting.
  const lerpAt = (fi) => {
    const c0 = Math.max(0, Math.min(L.length - 2, Math.floor(fi)));
    const u = Math.max(0, Math.min(1, fi - c0));
    const A = L[c0], B = L[c0 + 1];
    const mix = (x, y) => x + (y - x) * u;
    return {
      p: [mix(A.p[0], B.p[0]), mix(A.p[1], B.p[1]), mix(A.p[2], B.p[2])],
      n: [mix(A.n[0], B.n[0]), mix(A.n[1], B.n[1]), mix(A.n[2], B.n[2])],
      lat: [mix(A.lat[0], B.lat[0]), mix(A.lat[1], B.lat[1]), mix(A.lat[2], B.lat[2])],
      hw: mix(A.hw, B.hw), i: c0,
    };
  };

  for (const c of V.cars) {
    // Along the ribbon at `speed` of the window per second, wrapping inside the
    // window so the field never thins out at one end.
    let t = c.t0 + a.phase * a.speed;
    t = t - Math.floor(t);
    const fi = V.i0 + (V.i1 - V.i0) * t;
    const st = lerpAt(fi);
    const i = st.i;
    const p = L[Math.max(0, i - 2)], q = L[Math.min(i + 2, L.length - 1)];
    const fwd = new THREE.Vector3(q.p[0]-p.p[0], q.p[1]-p.p[1], q.p[2]-p.p[2]).normalize();
    const up = new THREE.Vector3(...st.n).normalize();
    const lat = new THREE.Vector3(...st.lat).normalize();
    const pos = new THREE.Vector3(...st.p)
      .addScaledVector(lat, c.lane * st.hw)
      .addScaledVector(up, c.lift);
    const back = fwd.clone().negate();
    const right = new THREE.Vector3().crossVectors(up, back).normalize();
    const rot = new THREE.Quaternion().setFromRotationMatrix(
      new THREE.Matrix4().makeBasis(right, up, back));
    rot.multiply(new THREE.Quaternion().setFromAxisAngle(
      new THREE.Vector3(0, 1, 0), c.yaw));
    c.view.update(pos, rot,
      { steer: c.steer, lean: c.lean, spin: c.spin + a.phase * 26 });
    if (c.lift > 1.2) c.view.shadow.visible = false;
  }

  // The cover's own fit, with `pad` animated. Identical maths, so pad at its
  // cover value reproduces the cover's camera exactly.
  const cam = S.renderer.camera;
  const vFov = a.fov * Math.PI / 180;
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * cam.aspect);
  const dist = V.radius / Math.sin(Math.min(vFov, hFov) / 2) * a.pad;
  cam.position.set(
    V.centre.x + dist * Math.cos(a.pitch) * Math.cos(a.azimuth),
    V.centre.y + dist * Math.sin(a.pitch),
    V.centre.z + dist * Math.cos(a.pitch) * Math.sin(a.azimuth));
  cam.up.set(0, 1, 0);
  cam.lookAt(V.centre);
  cam.fov = a.fov;
  cam.far = Math.max(2600, dist * 3);
  cam.updateProjectionMatrix();
  S.renderer.render(1 / 30);
  return +dist.toFixed(1);
}
"""


# ---------------------------------------------------------------------------
# The wordmark, as one transparent overlay
# ---------------------------------------------------------------------------

# The cover's scrim and mark with no picture behind them, so ffmpeg can lay it
# over frame 0 and fade it off. Kept in step with `shoot_covers.TITLE_PAGE` by
# using the same numbers; if that layout moves, this has to move with it or the
# first frame stops matching the cover.
OVERLAY_PAGE = """
<!doctype html><meta charset="utf-8">
<style>
  @font-face {{ font-family:"Titillium Web"; font-weight:900; font-display:block;
    src:url(data:font/woff2;base64,{font}) format("woff2"); }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{w}px; height:{h}px; overflow:hidden; background:transparent; }}
  .shot {{ position:relative; width:{w}px; height:{h}px; }}
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


def write_overlay(browser, w, h, out):
    """The wordmark and its scrim on transparency, at `w`x`h`."""
    k = min(w, h) / 1000.0
    html = OVERLAY_PAGE.format(
        w=w, h=h,
        font=_b64(os.path.join(DRIVE, "static", "fonts", "titillium-900.woff2")),
        wheel=_light_wheel(int(164 * k)),
        bottom=int(56 * k), gap=int(34 * k), size=int(158 * k),
        sh=max(1, int(3 * k)), sh2=max(2, int(14 * k)))
    page = browser.new_page(viewport={"width": w, "height": h})
    page.set_content(html)
    page.wait_for_timeout(600)
    page.screenshot(path=out, omit_background=True)
    page.close()
    return out


# ---------------------------------------------------------------------------
# Beats
# ---------------------------------------------------------------------------

def frames_dir(aspect, beat):
    d = os.path.join(OUT, "frames", aspect, beat)
    os.makedirs(d, exist_ok=True)
    return d


def clear(d):
    """Old frames out first - a short render leaves a long one's tail behind,
    and ffmpeg would happily encode the two spliced together."""
    for f in os.listdir(d):
        if f.endswith(".png"):
            os.remove(os.path.join(d, f))


def shoot_cover_beat(browser, base, aspect, secs, verbose=True):
    """Beat 1: the Spa cover, coming alive and pushing in."""
    w, h = ASPECTS[aspect]
    slug = "spa"
    cfg = COVERS[slug]
    d = frames_dir(aspect, "cover")
    clear(d)

    page = browser.new_page(viewport={"width": w, "height": h})
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    page.goto("%s/solo/%s?shot=1" % (base, slug), wait_until="load", timeout=90000)
    page.wait_for_function("window.DriveShot && window.DriveShot.S.built", timeout=90000)
    # The mesh, the sky, the trackside furniture and the shader precompile all
    # have to be done. A short wait here is a video of a half-built Spa.
    page.wait_for_timeout(8000)

    rows = page.evaluate(SCAN, SPAN)
    win = _pick_window(rows, cfg["at"], SPAN)
    page.evaluate(OPEN_SETUP, dict(i0=win["i0"], i1=win["i1"], cars=cfg["cars"],
                                   carFrom=cfg["carFrom"], carTo=cfg["carTo"],
                                   seed=cfg["seed"], paints=PAINTS))

    n = int(round(secs * FPS))
    for f in range(n):
        phase = f / FPS
        u = f / max(1, n - 1)
        # Ease-in-out on the push, so it starts as a still and arrives settled
        # rather than slamming to a stop.
        e = u * u * (3 - 2 * u)
        page.evaluate(OPEN_FRAME, dict(
            # Racing pace, not a drift: the window is `SPAN` of a lap and Spa
            # takes ~71s, so a car crosses it in ~11.4s - one window in 11.4s is
            # 0.088 of it a second. At 0.030 the field was crawling, which is
            # both wrong and what made the station-snapping so obvious.
            phase=phase, speed=0.088,
            pad=cfg["pad"] * (1 - 0.30 * e),      # 0.50 -> 0.35, a 30% push
            azimuth=cfg["azimuth"],
            pitch=cfg["pitch"] + 0.05 * e,        # rise very slightly with it
            fov=cfg["fov"]))
        page.screenshot(path=os.path.join(d, "f%04d.png" % f))
    page.close()
    if verbose:
        print("  cover      %s %d frames" % (aspect, n))
    if errs:
        print("  PAGE ERRORS:", errs[:3])
    return n


# A pose further than this between two 15Hz samples is not driving. Top speed
# here is about 5.7 units a sample, so 15 only ever catches a respawn or a
# checkpoint reset.
TELEPORT = 15.0

# How many samples the smoother averages over. 7 is 0.47s, which takes the
# timing jitter out (speed swing 3.54x -> 1.19x) while moving the racing line a
# mean of 0.75 units - a fraction of the road's width.
SMOOTH_WINDOW = 7


def smooth_frames(frames, window=SMOOTH_WINDOW):
    """Even out a *race* recording's timing jitter.

    **A race is not recorded the way a lap is, and it is why the replays
    juddered.** `course.js` records a solo ghost by resampling to exactly
    `i / GHOST_HZ` seconds, so a board lap plays back at a constant rate - which
    is why Big Red was the one beat that always looked right. A race is recorded
    server-side off the live pose stream, so its frames land whenever packets
    did, while `Ghost.at` plays them back assuming they are evenly spaced. The
    car therefore appears to surge and slow: measured on race 113, the distance
    covered between consecutive video frames swung 0.81 to 2.87 units inside
    half a second, a 3.5x speed change no car can make.

    Averaging the poses over a short centred window puts that right, and it is
    an honest thing to do: the samples are real, only their *timing* is noise.

    **Never across a teleport.** A respawn moves a car hundreds of units between
    two samples, and a window straddling one would drag it across the map -
    smoothing the whole track blind gave a worst-case error of 332 units. The
    track is cut at every jump over `TELEPORT` and each piece smoothed alone,
    which brings the worst error down to 4.
    """
    n = len(frames)
    if n < 3:
        return frames
    k = window // 2
    cuts = [0]
    for i in range(1, n):
        a, b = frames[i], frames[i - 1]
        if math.dist(a[:3], b[:3]) > TELEPORT:
            cuts.append(i)
    cuts.append(n)

    out = [list(f) for f in frames]
    for s in range(len(cuts) - 1):
        lo0, hi0 = cuts[s], cuts[s + 1]
        for i in range(lo0, hi0):
            lo, hi = max(lo0, i - k), min(hi0, i + k + 1)
            m = hi - lo
            # The pose only: the flag byte on the end is a state, not a
            # quantity, and averaging it would invent lamp settings.
            for c in range(min(7, len(frames[i]))):
                out[i][c] = sum(frames[j][c] for j in range(lo, hi)) / m
    return out


def install_smoothing(page):
    """Serve `/api/race/<id>` with its timing jitter taken out."""
    def handler(route):
        resp = route.fetch()
        try:
            data = resp.json()
        except Exception:
            route.fulfill(response=resp)
            return
        for car in data.get("cars", []):
            if car.get("frames"):
                car["frames"] = smooth_frames(car["frames"])
        route.fulfill(response=resp, json=data)
    page.route("**/api/race/*", handler)


def _clock(page):
    """Where the replay is, in seconds, off the page's own clock.

    `textContent` and not `inner_text`: the clock lives inside `#watchBar`,
    which `HIDE` has just taken off the screen, and `inner_text` is the
    *rendered* text - it answers "" for anything invisible, so the seek would
    read every position as zero and never arrive.
    """
    txt = (page.text_content("#watchClock") or "").strip()      # m:ss.mmm
    if not txt:
        raise RuntimeError("no clock on the page - is this a replay?")
    m, rest = txt.split(":")
    return int(m) * 60 + float(rest)


def _seek(page, target, cap=4000):
    """Pump the loop until the replay reaches `target` seconds.

    Fast-forwarding is done at the loop's own dt ceiling (`Math.min(0.1, ...)`
    in `frame`), so 100ms a pump is the largest step the game will honour - a
    bigger one is silently clamped and the seek would undershoot without saying
    so. The replay wraps at its duration, so a target already behind us is
    reached by going round.
    """
    for _ in range(cap):
        now = _clock(page)
        if abs(now - target) < 0.05 or (now < target and target - now < 0.1):
            return now
        page.evaluate("() => window.__pump(100)")
        if _clock(page) >= target > now:
            return _clock(page)
    return _clock(page)


def shoot_replay_beat(browser, base, aspect, beat, verbose=True):
    """Beats 2-5: a real recorded lap, played back and stepped at 30Hz."""
    w, h = ASPECTS[aspect]
    d = frames_dir(aspect, beat["name"])
    clear(d)

    page = browser.new_page(viewport={"width": w, "height": h})
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    install_smoothing(page)
    page.goto(base + beat["url"], wait_until="load", timeout=90000)
    page.wait_for_selector("#watchClock", timeout=90000)
    # The world, the sky and the shader precompile, same as the opener.
    page.wait_for_timeout(8000)

    # Whose camera. A board lap is one car and offers no choice, so the buttons
    # are only there for a race.
    #
    # **Before the chrome is hidden, not after.** The car buttons live inside
    # `#watchBar`, so hiding it first makes them unclickable and Playwright sits
    # there retrying a click on something it can see is invisible.
    if beat.get("follow"):
        names = page.eval_on_selector_all("button.wcar span:nth-child(2)",
                                          "els => els.map(e => e.textContent)")
        if beat["follow"] not in names:
            raise RuntimeError("%s is not in %s: %s" % (beat["follow"], beat["url"], names))
        page.click('button.wcar[data-cam="%d"]' % names.index(beat["follow"]))
    page.add_style_tag(content=HIDE)

    page.evaluate(PUMP)
    page.wait_for_timeout(200)
    at = _seek(page, beat["start"])

    # Held, not pressed: `viewKeys()` reads the live key set every frame, so the
    # driver's seat lasts exactly as long as the key is down (`game.js:892`).
    if beat.get("view") == "first":
        page.keyboard.down("f")

    n = int(round(beat["secs"] * FPS))
    step = 1000.0 / FPS / SUBSTEPS
    for f in range(n):
        for _ in range(SUBSTEPS):
            page.evaluate("(ms) => window.__pump(ms)", step)
        page.evaluate("() => window.__present()")
        page.screenshot(path=os.path.join(d, "f%04d.png" % f))
    end = _clock(page)
    if beat.get("view") == "first":
        page.keyboard.up("f")
    page.close()

    if verbose:
        print("  %-11s %s %d frames  %.2fs -> %.2fs" % (beat["name"], aspect, n, at, end))
    if errs:
        print("  PAGE ERRORS:", errs[:3])
    return n


def probe(browser, base, aspect, beat, every=2.0):
    """Contact sheet: one frame every `every` seconds of the whole recording.

    Which second of a race is worth three of the video is not a thing a number
    knows - the same reason `shoot_covers` records its angles by hand. This is
    how the `start` values above were chosen.
    """
    w, h = ASPECTS[aspect]
    d = os.path.join(OUT, "probe", beat["name"])
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        os.remove(os.path.join(d, f))

    page = browser.new_page(viewport={"width": w // 2, "height": h // 2})
    install_smoothing(page)
    page.goto(base + beat["url"], wait_until="load", timeout=90000)
    page.wait_for_selector("#watchClock", timeout=90000)
    page.wait_for_timeout(8000)
    if beat.get("follow"):
        names = page.eval_on_selector_all("button.wcar span:nth-child(2)",
                                          "els => els.map(e => e.textContent)")
        page.click('button.wcar[data-cam="%d"]' % names.index(beat["follow"]))
    page.add_style_tag(content=HIDE)
    page.evaluate(PUMP)
    page.wait_for_timeout(200)
    if beat.get("view") == "first":
        page.keyboard.down("f")
    t = 0.0
    # Long enough for any recording here; the clock wraps and the sheet stops.
    while t < 120:
        got = _seek(page, t)
        if got < t - 1:
            break
        # A couple of real frames so the camera spring settles where it would be.
        for _ in range(3):
            page.evaluate("() => window.__pump(1000/30)")
        page.evaluate("() => window.__present()")
        page.screenshot(path=os.path.join(d, "t%05.1f.png" % t))
        t += every
    if beat.get("view") == "first":
        page.keyboard.up("f")
    page.close()
    print("  probe %-11s %s -> %s" % (beat["name"], aspect, d))


# ---------------------------------------------------------------------------
# Cutting it together
# ---------------------------------------------------------------------------

# The store cover each shape starts from. Portrait pairs with the 800x1200,
# which is already 2:3 and so scales to 1080x1620 without reframing.
COVER_FOR = {
    "landscape": "spa_1920x1080-title.png",
    "portrait": "spa_800x1200-title.png",
}


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n%s" % p.stderr[-2000:])


def encode_beat(aspect, beat):
    """One beat's frames to an intermediate, overlays and all.

    Intermediates at CRF 16 rather than straight to the final file: the five are
    concatenated afterwards, and re-encoding a beat that was already at delivery
    quality would show it.
    """
    w, h = ASPECTS[aspect]
    d = frames_dir(aspect, beat["name"])
    n = len([f for f in os.listdir(d) if f.endswith(".png")])
    if not n:
        raise RuntimeError("no frames for %s/%s - render it first" % (aspect, beat["name"]))
    out = os.path.join(OUT, "beats", aspect)
    os.makedirs(out, exist_ok=True)
    dst = os.path.join(out, beat["name"] + ".mp4")

    common = ["-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
              "-crf", "16", "-preset", "slow", "-an", "-r", str(FPS)]

    if beat["name"] != "cover":
        _run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
              "-i", os.path.join(d, "f%04d.png")] + common + [dst])
        return dst

    # The opener carries both overlays.
    #
    # **The true cover file is laid on top of frame 0 and dissolved off**, rather
    # than trusting the render to reproduce it. The two match to ~41dB, which is
    # invisible - but the shipped `-title.png` was re-rasterised through a
    # browser compose and this is not, so they are not identical and "starts from
    # the cover" is a claim worth making exactly true. Under the dissolve the
    # push-in is already moving, so it reads as the still coming to life.
    cover = os.path.join(DRIVE, "covers", COVER_FOR[aspect])
    _run(["ffmpeg", "-v", "error", "-y",
          "-framerate", str(FPS), "-i", os.path.join(d, "f%04d.png"),
          "-loop", "1", "-i", os.path.join(OUT, "wordmark-%s.png" % aspect),
          "-loop", "1", "-i", cover,
          "-filter_complex",
          "[1:v]format=rgba,fade=out:st=0.7:d=1.1:alpha=1[wm];"
          "[0:v][wm]overlay=shortest=1[a];"
          "[2:v]scale=%d:%d,format=rgba,fade=out:st=0.20:d=0.35:alpha=1[cv];"
          "[a][cv]overlay=shortest=1[v]" % (w, h),
          "-map", "[v]"] + common + [dst])
    return dst


def assemble(aspect):
    """The five beats, hard cut, to the delivery file."""
    out = os.path.join(OUT, "beats", aspect)
    parts = [os.path.join(out, b["name"] + ".mp4") for b in BEATS]
    missing = [p for p in parts if not os.path.exists(p)]
    if missing:
        raise RuntimeError("missing beats: %s" % ", ".join(os.path.basename(m) for m in missing))
    lst = os.path.join(out, "concat.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write("file '%s'\n" % os.path.abspath(p))
    dst = os.path.join(OUT, "drive-%s.mp4" % aspect)
    _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
          "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
          "-crf", "19", "-preset", "slow", "-an", "-movflags", "+faststart", dst])
    mb = os.path.getsize(dst) / 1048576.0
    total = sum(b["secs"] for b in BEATS)
    print("  -> %s  %.1fs  %.1f MB" % (dst, total, mb))
    if mb > 50:
        print("     OVER the 50MB limit")
    if total > 20:
        print("     OVER the 20s limit")
    return dst


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beat", action="append",
                    help="only this beat (repeatable): " + ", ".join(b["name"] for b in BEATS))
    ap.add_argument("--aspect", action="append", choices=list(ASPECTS),
                    help="only this shape (repeatable)")
    ap.add_argument("--port", type=int, default=5097)
    ap.add_argument("--probe", action="store_true",
                    help="contact sheets of each replay beat, to choose `start` from")
    ap.add_argument("--every", type=float, default=2.0, help="probe spacing, seconds")
    # The four gameplay beats play back races that exist on prod and in no fresh
    # checkout, so the tool is pointed at a database holding them rather than
    # pretending the default one will do. `tools/pull_video_races.py` makes one.
    ap.add_argument("--db", help="sqlite file holding the races in BEATS")
    ap.add_argument("--cut-only", action="store_true",
                    help="skip rendering; cut the frames already on disk")
    args = ap.parse_args()
    if args.db:
        os.environ["DATABASE_URL"] = "sqlite:///" + os.path.abspath(args.db)

    aspects = args.aspect or list(ASPECTS)
    wanted = args.beat or [b["name"] for b in BEATS]
    todo = [b for b in BEATS if b["name"] in wanted]

    os.makedirs(OUT, exist_ok=True)
    if args.cut_only:
        for aspect in aspects:
            print("%s" % aspect)
            for b in todo:
                encode_beat(aspect, b)
            assemble(aspect)
        return

    from playwright.sync_api import sync_playwright
    with serving(args.port) as base:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=GL_FLAGS)
            for aspect in aspects:
                w, h = ASPECTS[aspect]
                print("%s (%dx%d)" % (aspect, w, h))
                if args.probe:
                    for b in todo:
                        if b.get("url"):
                            probe(browser, base, aspect, b, args.every)
                    continue
                write_overlay(browser, w, h,
                              os.path.join(OUT, "wordmark-%s.png" % aspect))
                for b in todo:
                    if b["name"] == "cover":
                        shoot_cover_beat(browser, base, aspect, b["secs"])
                    else:
                        shoot_replay_beat(browser, base, aspect, b)
            browser.close()

    # Cutting needs no browser, so it happens after the server and Chrome are
    # down rather than holding both open through an encode.
    if not args.probe:
        for aspect in aspects:
            print("%s: cutting" % aspect)
            for b in todo:
                encode_beat(aspect, b)
            if len(todo) == len(BEATS):
                assemble(aspect)


if __name__ == "__main__":
    main()
