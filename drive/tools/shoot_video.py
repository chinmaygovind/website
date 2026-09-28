"""The game's videos: the store trailer and the home page's background loop.

    python tools/stage_race.py --db media/video/staged.db <every slug>   # first
    python tools/shoot_video.py --db media/video/staged.db trailer
    python tools/shoot_video.py --db media/video/staged.db loop
    python tools/shoot_video.py --db ... trailer --beat launch --aspect landscape
    python tools/shoot_video.py trailer --cut-only      # re-cut frames on disk

Two cuts of the same footage:

* **`trailer`** - 20s, silent, 1920x1080 and 1080x1620, opening on the Spa
  cover. What CrazyGames asks for (at most 20s, under 50MB, no audio, starting
  seamlessly from the store cover), and the same file is the embed on
  cgovind.com (`site/assets/drive/drive-landscape.mp4`).
* **`loop`** - 60s at 1280x720, fifteen tracks at four seconds each, no
  wordmark. The home page's background (`static/video/home.mp4`), which is
  cropped by `object-fit: cover` and so needs no portrait of its own.

**Two kinds of shot.** A `fly` is `_hero.py`'s composition - the same framing
as the track's card and its store cover - with the cars driven on along the
ribbon and the camera pushing in. A `race` is a staged bot race
(`stage_race.py`) played back through `/race/<id>`, the real watch page and
its real chase camera, stepped at 30Hz.

**The race shots pick themselves.** Which car to follow and from when is
chosen off the race's own frames by what the beat asks for - `pack` (most
cars close by), `air` (most time off the ground), `start` (off the grid) or
`finish` (the closest finish in the race) - never across a respawn and never
while the car is crawling. So a restaged race needs no new numbers here. Look
at the contact sheet it prints anyway: a number cannot tell a wall from a view.

**The opener used to lose cars.** Each car was wrapped back to the start of
its window when it reached the end, so a car vanished and reappeared mid-frame
a couple of times a second. Now every car is the one `_hero.SHOOT` placed, and
it simply keeps driving down the road - the field thins at the back as it
goes, which three seconds never shows.

**This renders rather than screen-records**, and that is the whole point: a
recorded viewport is the wrong size, has sound and the site's buttons in it.
The game's `requestAnimationFrame` is taken over (`PUMP`) so each frame is the
real `frame()` advanced by exactly 1/30s.
"""

import argparse
import json
import math
import os
import sqlite3
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, DRIVE)

import _hero  # noqa: E402
from _shots import GL_FLAGS, serving  # noqa: E402
from shoot_covers import _b64, _light_wheel  # noqa: E402

OUT = os.path.join(DRIVE, "media", "video")
COVERS = os.path.join(DRIVE, "media", "covers")
FPS = 30

# Simulation steps per captured frame on a replay. The chase camera is an
# exponential follow, and a replay's pose steps at 15Hz; giving the camera four
# bites per frame is what a 120Hz browser does, and is what takes the judder out.
SUBSTEPS = 4

# Racing pace for a `fly` beat's cars, in units a second.
FLY_SPEED = 45.0

ASPECTS = {
    "landscape": (1920, 1080),
    "portrait": (1080, 1620),
    "web": (1280, 720),
}

# ---------------------------------------------------------------------------
# The edits
# ---------------------------------------------------------------------------

# 20.0s. Opens on Spa because the store's cover is Spa and the video has to
# start on it; everything after that is a track the first trailer never showed.
TRAILER = [
    dict(name="open", kind="fly", slug="spa", secs=2.5, push=0.30, rise=0.05,
         title="out"),
    dict(name="launch", kind="race", slug="baku", secs=2.5, pick="start"),
    dict(name="pack", kind="race", slug="suzuka", secs=2.0, pick="pack"),
    # The montage: the tracks that are a place rather than a road.
    dict(name="m-costco", kind="fly", slug="costco", secs=0.6, push=0.25),
    dict(name="m-dino", kind="fly", slug="dino", secs=0.6, push=0.25),
    dict(name="m-boo", kind="fly", slug="boo", secs=0.6, push=0.25),
    dict(name="m-tokyo", kind="fly", slug="tokyo", secs=0.6, push=0.25),
    dict(name="m-playground", kind="fly", slug="playground", secs=0.6, push=0.25),
    dict(name="m-shroom", kind="fly", slug="shroom", secs=0.6, push=0.25),
    dict(name="cockpit", kind="race", slug="monaco", secs=2.5, pick="pack", view="first"),
    dict(name="air", kind="race", slug="jumpcity", secs=2.0, pick="air"),
    dict(name="train", kind="race", slug="monza", secs=2.0, pick="pack"),
    dict(name="flag", kind="race", slug="silverstone", secs=2.9, pick="finish",
         title="in"),
]

# 60.0s: the fifteen tracks that look most unlike each other, four seconds
# each - a background wants fewer, longer shots than a trailer does. Ordered so
# no two neighbours share a sky.
_LOOP = [
    ("pillars", "fly"), ("bigred", "air"), ("suzuka", "pack"),
    ("monaco", "first"), ("spa", "pack"), ("boo", "fly"),
    ("dino", "fly"), ("tokyo", "pack"), ("mountjoy", "air"),
    ("rainbow", "first"), ("playground", "air"), ("railway", "first"),
    ("costco", "fly"), ("cove", "first"), ("baku", "pack"),
]


def _loop_beat(slug, how, secs=4.0):
    if how == "fly":
        return dict(name=slug, kind="fly", slug=slug, secs=secs, push=0.25, orbit=0.12)
    if how == "first":
        return dict(name=slug, kind="race", slug=slug, secs=secs, pick="pack", view="first")
    return dict(name=slug, kind="race", slug=slug, secs=secs, pick=how)


LOOP = [_loop_beat(s, h) for s, h in _LOOP]

CUTS = {
    "trailer": dict(beats=TRAILER, aspects=["landscape", "portrait"], crf=19),
    "loop": dict(beats=LOOP, aspects=["web"], crf=30),
}

# What comes off the frame on a replay: everything but the world. The HUD is
# all one `.hud` beside the `#gl` canvas, so this is the whole of it.
HIDE = """
  body > *:not(#gl) { display: none !important; }
  * { cursor: none !important; }
"""

PUMP = """() => {
  window.__raf = [];
  window.__t = performance.now();
  // Kept: `page.screenshot` waits for a composited frame, and asks rAF for one.
  window.__realRaf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => { window.__raf.push(cb); return window.__raf.length; };
  window.__pump = (ms) => {
    window.__t += ms;
    const q = window.__raf; window.__raf = [];
    for (const cb of q) { try { cb(window.__t); } catch (e) { window.__err = String(e); } }
  };
  // The last step of a frame runs *inside* a real animation frame. WebGL's
  // buffer is not preserved, so a frame drawn outside one is thrown away before
  // the screenshot composites it - every capture came back blank page colour.
  window.__present = (ms) => new Promise(r => window.__realRaf(() => { window.__pump(ms); r(1); }));
}"""

# ---------------------------------------------------------------------------
# fly: the hero composition, moving
# ---------------------------------------------------------------------------

# One frame. At phase 0 every car is exactly where `_hero.SHOOT` put it and the
# camera is exactly its camera, so frame 0 of the opener *is* the cover.
FLY_FRAME = r"""
(a) => {
  const C = window.DriveShot, S = C.S, THREE = C.THREE, L = S.built.line, sA = S.built.s;
  const total = sA[sA.length - 1], F = window.__coverFit;
  const at = (s) => {
    s = a.closed ? ((s % total) + total) % total : Math.min(s, total);
    let lo = 0, hi = sA.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (sA[m] <= s) lo = m; else hi = m; }
    return { c0: lo, u: sA[hi] > sA[lo] ? Math.min(1, (s - sA[lo]) / (sA[hi] - sA[lo])) : 0 };
  };
  const V = (x) => new THREE.Vector3(x[0], x[1], x[2]);
  for (const c of window.__coverSlots) {
    const { c0, u } = at(sA[c.i] + a.speed * a.phase);
    const A = L[c0], B = L[Math.min(c0 + 1, L.length - 1)];
    const i = u < 0.5 ? c0 : Math.min(c0 + 1, L.length - 1);
    const p = L[Math.max(0, i - 2)], q = L[Math.min(i + 2, L.length - 1)];
    const fwd = V(q.p).sub(V(p.p)).normalize();
    const up = V(A.n).lerp(V(B.n), u).normalize();
    const lat = V(A.lat).lerp(V(B.lat), u).normalize();
    const hw = A.hw + (B.hw - A.hw) * u;
    const pos = V(A.p).lerp(V(B.p), u)
      .addScaledVector(lat, c.lane * hw).addScaledVector(up, c.lift);
    const back = fwd.clone().negate();
    const right = new THREE.Vector3().crossVectors(up, back).normalize();
    const rot = new THREE.Quaternion().setFromRotationMatrix(
      new THREE.Matrix4().makeBasis(right, up, back));
    rot.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), c.yaw));
    c.view.update(pos, rot, { steer: c.pose.steer, lean: c.pose.lean,
                              spin: c.pose.spin + a.phase * 26 });
    c.view.shadow.visible = c.lift < 1.2 && !L[i].air;
  }

  const cam = S.renderer.camera, e = a.e;
  const centre = F.centre.clone();
  if (a.eye) {
    // A camera standing in the world (BOO!): dolly towards what it looks at.
    centre.set(a.look[0], a.look[1], a.look[2]);
    cam.position.copy(centre).lerp(V(a.eye), 1 - a.push * e);
  } else {
    const vFov = a.fov * Math.PI / 180;
    const hFov = 2 * Math.atan(Math.tan(vFov / 2) * cam.aspect);
    const dist = F.radius / Math.sin(Math.min(vFov, hFov) / 2) * a.pad * (1 - a.push * e);
    const az = a.azimuth + a.orbit * e, pit = a.pitch + a.rise * e;
    cam.position.set(centre.x + dist * Math.cos(pit) * Math.cos(az),
                     centre.y + dist * Math.sin(pit),
                     centre.z + dist * Math.cos(pit) * Math.sin(az));
  }
  cam.up.set(0, 1, 0);
  cam.lookAt(centre);
  cam.updateProjectionMatrix();
  if (S.renderer.sky) S.renderer.sky.position.copy(cam.position);
  S.renderer.render(1 / 30);
  return 1;
}
"""


def shoot_fly(hero, base, aspect, beat, d):
    import tracks as tracks_mod
    w, h = ASPECTS[aspect]
    slug = beat["slug"]
    # No car hanging in mid-air for a whole shot: a still can pose one mid-jump,
    # a moving car at a fixed height over the road is a car hovering.
    cfg = dict(_hero.frame_for(slug), air=0.0, **beat.get("over", {}))
    page = hero.open(slug, (w, h))
    try:
        hero.compose(page, cfg)
        # `compose` leaves a 40ms redraw running so a still always has a fresh
        # frame to capture. Here every frame renders itself, and that interval
        # was a full software-GL render per 40ms between shots - 50s a frame.
        page.evaluate("() => clearInterval(window.__coverTick)")
        closed = bool(tracks_mod.get(slug).get("closed"))
        n = int(round(beat["secs"] * FPS))
        for f in range(n):
            u = f / max(1, n - 1)
            page.evaluate(FLY_FRAME, dict(
                phase=f / FPS, e=u * u * (3 - 2 * u), speed=FLY_SPEED, closed=closed,
                push=beat.get("push", 0.25), orbit=beat.get("orbit", 0.0),
                rise=beat.get("rise", 0.0), pad=cfg["pad"], fov=cfg["fov"],
                azimuth=cfg["azimuth"], pitch=cfg["pitch"],
                eye=cfg.get("eye"), look=cfg.get("look")))
            snap(page, os.path.join(d, "f%04d.png" % f), timeout=_hero.SHOT_MS)
    finally:
        page.close()
    return n


# ---------------------------------------------------------------------------
# race: a staged race, played back
# ---------------------------------------------------------------------------

def snap(page, path, **kw):
    """`page.screenshot`, retried. Software GL now and then answers "Unable to
    capture screenshot" for a frame that is fine a moment later, and one of
    those three thousand captures in should not cost the whole render."""
    for attempt in range(4):
        try:
            return page.screenshot(path=path, **kw)
        except Exception:
            if attempt == 3:
                raise
            page.wait_for_timeout(500)


AIR, RESPAWN = 2, 4
NEAR = 25.0          # units: "in the shot with you"


def race_id(db, slug):
    with sqlite3.connect(db) as c:
        row = c.execute("SELECT id FROM drive_races WHERE track=? ORDER BY id DESC LIMIT 1",
                        (slug,)).fetchone()
    if not row:
        raise RuntimeError("no staged race on %s - run stage_race.py %s" % (slug, slug))
    return row[0]


def pick(race, secs, how, near=(0.0, NEAR)):
    """(name to follow, start in seconds) for a beat of `secs` wanting `how`."""
    hz, cars = race["hz"], race["cars"]
    n = int(round(secs * hz))
    best = None
    for c in cars:
        F = c["frames"]
        done = int(c["ms"] / 1000 * hz) if c.get("ms") else len(F)
        if how == "start":
            starts = [0]
        elif how == "finish":
            if not c.get("ms"):
                continue
            starts = [max(0, done - n + int(0.8 * hz))]
        else:
            starts = range(int(6 * hz), done - n, max(1, hz // 3))
        for s in starts:
            win = F[s:s + n]
            if len(win) < n or any(f[7] & RESPAWN for f in win):
                continue
            if any(math.dist(win[k][:3], win[k - 1][:3]) > 15 for k in range(1, n)):
                continue
            if how != "start" and math.dist(win[0][:3], win[-1][:3]) / secs < 25:
                continue
            company = sum(1 for k in range(s, s + n) for o in cars if o is not c
                          and k < len(o["frames"])
                          and near[0] < math.dist(o["frames"][k][:3], F[k][:3]) < near[1]) / n
            score = company
            if how == "air":
                score += 4.0 * sum(1 for f in win if f[7] & AIR) / n
            if how == "finish":
                gap = min((abs(o["ms"] - c["ms"]) for o in cars
                           if o is not c and o.get("ms")), default=9999) / 1000.0
                score = company - 3.0 * gap
            if best is None or score > best[0]:
                best = (score, c["name"], s / hz)
    if best is None:
        raise RuntimeError("nothing in race %s fits a %s shot" % (race["id"], how))
    return best[1], best[2]


def no_tags(page):
    """Serve `render.js` with the name plates switched off. A plate is a sprite
    that scales with distance, so any car near the camera wore its name across
    half the frame; a pack reads as a race without them."""
    def handler(route):
        resp = route.fetch()
        body = resp.text().replace("setLabel(text, color) {",
                                   "setLabel(text, color) { text = null;", 1)
        route.fulfill(response=resp, body=body)
    page.route("**/static/js/render.js*", handler)


def _clock(page):
    txt = (page.text_content("#watchClock") or "").strip()      # m:ss.mmm
    m, rest = txt.split(":")
    return int(m) * 60 + float(rest)


def _goto(page, start, hz):
    """Put the replay at `start` with the camera already settled on its car.

    With the page's clock frozen, the replay's own keys: R back to the flag,
    Space to pause, then 5s and 1/15s steps to a second short of the shot.
    Play, and pump that second so the chase camera has come round onto the
    car at racing speed by the first frame. Pumping the whole way from zero is
    a rendered frame per step - a quarter of an hour to reach the far end -
    and a scrubber click landed the camera looking at the sky.
    """
    pre = min(1.0, start)
    target = start - pre
    page.keyboard.press("KeyR")
    page.keyboard.press("Space")
    for _ in range(int(target // 5)):
        page.keyboard.press("ArrowRight")
    for _ in range(int(round((target % 5) * hz))):
        page.keyboard.press("Period")
    if pre < 0.5:
        # Off the grid there is no second before to settle in; settle paused.
        for _ in range(30):
            page.evaluate("() => window.__pump(1000 / 30)")
        page.keyboard.press("Space")
    else:
        page.keyboard.press("Space")
        for _ in range(int(pre * 30)):
            page.evaluate("() => window.__pump(1000 / 30)")
    return _clock(page)


def shoot_race(browser, base, aspect, beat, d, db):
    w, h = ASPECTS[aspect]
    rid = race_id(db, beat["slug"])
    race = json.load(urllib.request.urlopen("%s/api/race/%d" % (base, rid)))
    # From the driver's seat a car alongside fills the windscreen; what looks
    # like a race from there is a field some way up the road.
    near = (8.0, 40.0) if beat.get("view") == "first" else (0.0, NEAR)
    follow, start = pick(race, beat["secs"], beat["pick"], near)
    print("    race %d: %s from %.1fs" % (rid, follow, start), flush=True)
    page = browser.new_page(viewport={"width": w, "height": h})
    no_tags(page)
    try:
        page.goto("%s/race/%d" % (base, rid), wait_until="load", timeout=90000)
        page.wait_for_selector("#watchClock", timeout=90000)
        page.wait_for_timeout(8000)
        names = page.eval_on_selector_all("button.wcar span:nth-child(2)",
                                          "els => els.map(e => e.textContent)")
        page.click('button.wcar[data-cam="%d"]' % names.index(follow))
        page.add_style_tag(content=HIDE)
        page.evaluate(PUMP)
        page.wait_for_timeout(200)
        at = _goto(page, start, race["hz"])
        if beat.get("view") == "first":
            page.keyboard.down("f")
        n = int(round(beat["secs"] * FPS))
        step = 1000.0 / FPS / SUBSTEPS
        for f in range(n):
            for _ in range(SUBSTEPS - 1):
                page.evaluate("(ms) => window.__pump(ms)", step)
            page.evaluate("(ms) => window.__present(ms)", step)
            snap(page, os.path.join(d, "f%04d.png" % f))
        if beat.get("view") == "first":
            page.keyboard.up("f")
    finally:
        page.close()
    print("    race %d, following %s from %.1fs" % (rid, follow, at))
    return n


# ---------------------------------------------------------------------------
# The wordmark
# ---------------------------------------------------------------------------

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
    """The cover's scrim and wordmark on transparency - kept in step with
    `shoot_covers.TITLE_PAGE`, or frame 0 stops matching the cover."""
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
    snap(page, out, omit_background=True)
    page.close()


# ---------------------------------------------------------------------------
# Cutting
# ---------------------------------------------------------------------------

COVER_FOR = {"landscape": "spa_1920x1080-title.png", "portrait": "spa_800x1200-title.png"}


def frames_dir(cut, aspect, name):
    d = os.path.join(OUT, "frames", cut, aspect, name)
    os.makedirs(d, exist_ok=True)
    return d


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n%s" % p.stderr[-2000:])


def encode_beat(cut, aspect, beat):
    """One beat to a CRF 16 intermediate, overlays and all."""
    w, h = ASPECTS[aspect]
    d = frames_dir(cut, aspect, beat["name"])
    if not any(f.endswith(".png") for f in os.listdir(d)):
        raise RuntimeError("no frames for %s/%s/%s" % (cut, aspect, beat["name"]))
    out = os.path.join(OUT, "beats", cut, aspect)
    os.makedirs(out, exist_ok=True)
    dst = os.path.join(out, beat["name"] + ".mp4")
    common = ["-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
              "-crf", "16", "-preset", "slow", "-an", "-r", str(FPS)]
    src = ["-framerate", str(FPS), "-i", os.path.join(d, "f%04d.png")]
    wm = os.path.join(OUT, "wordmark-%s.png" % aspect)
    title = beat.get("title")
    if title == "out":
        # The true cover file over frame 0, dissolved off, so "starts from the
        # cover" is exactly true rather than true to ~41dB.
        cover = os.path.join(COVERS, COVER_FOR[aspect])
        _run(["ffmpeg", "-v", "error", "-y"] + src +
             ["-loop", "1", "-i", wm, "-loop", "1", "-i", cover, "-filter_complex",
              "[1:v]format=rgba,fade=out:st=0.7:d=1.1:alpha=1[wm];"
              "[0:v][wm]overlay=shortest=1[a];"
              "[2:v]scale=%d:%d,format=rgba,fade=out:st=0.20:d=0.35:alpha=1[cv];"
              "[a][cv]overlay=shortest=1[v]" % (w, h),
              "-map", "[v]"] + common + [dst])
    elif title == "in":
        st = beat["secs"] - 1.5
        _run(["ffmpeg", "-v", "error", "-y"] + src +
             ["-loop", "1", "-i", wm, "-filter_complex",
              "[1:v]format=rgba,fade=in:st=%.2f:d=0.6:alpha=1[wm];"
              "[0:v][wm]overlay=shortest=1[v]" % st,
              "-map", "[v]"] + common + [dst])
    else:
        _run(["ffmpeg", "-v", "error", "-y"] + src + common + [dst])
    return dst


def assemble(cut, aspect):
    spec = CUTS[cut]
    parts = [os.path.join(OUT, "beats", cut, aspect, b["name"] + ".mp4") for b in spec["beats"]]
    lst = os.path.join(OUT, "beats", cut, aspect, "concat.txt")
    with open(lst, "w") as f:
        f.writelines("file '%s'\n" % p for p in parts)
    dst = os.path.join(OUT, "drive-%s.mp4" % aspect if cut == "trailer" else "loop.mp4")
    _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
          "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
          "-crf", str(spec["crf"]), "-preset", "slow", "-an", "-movflags", "+faststart", dst])
    mb = os.path.getsize(dst) / 1048576.0
    total = sum(b["secs"] for b in spec["beats"])
    print("  -> %s  %.1fs  %.1f MB" % (dst, total, mb))
    if cut == "trailer" and (mb > 50 or total > 20):
        print("     OVER the store's limits (20s, 50MB)")
    # One frame from the middle of every beat, for looking at.
    sheet = dst[:-4] + "-sheet.png"
    cols = 6
    _run(["ffmpeg", "-v", "error", "-y"] +
         sum([["-i", os.path.join(frames_dir(cut, aspect, b["name"]),
                                  "f%04d.png" % int(b["secs"] * FPS / 2))]
              for b in spec["beats"]], []) +
         ["-filter_complex",
          "".join("[%d:v]scale=320:-2[s%d];" % (i, i) for i in range(len(parts))) +
          "".join("[s%d]" % i for i in range(len(parts))) +
          "xstack=inputs=%d:layout=%s:fill=black" % (len(parts), _grid(len(parts), cols, aspect)),
          sheet])
    print("     sheet: %s" % sheet)
    return dst


def _grid(n, cols, aspect):
    w, h = ASPECTS[aspect]
    tw, th = 320, int(320 * h / w) // 2 * 2
    return "|".join("%d_%d" % ((i % cols) * tw, (i // cols) * th) for i in range(n))


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cut", choices=list(CUTS))
    ap.add_argument("--beat", action="append", help="only this beat (repeatable)")
    ap.add_argument("--aspect", action="append", choices=list(ASPECTS))
    ap.add_argument("--db", help="sqlite file holding the staged races")
    ap.add_argument("--port", type=int, default=5097)
    ap.add_argument("--cut-only", action="store_true", help="skip rendering")
    args = ap.parse_args()
    spec = CUTS[args.cut]
    aspects = args.aspect or spec["aspects"]
    todo = [b for b in spec["beats"] if not args.beat or b["name"] in args.beat]
    if args.db:
        args.db = os.path.abspath(args.db)
        os.environ["DATABASE_URL"] = "sqlite:///" + args.db

    if not args.cut_only:
        with serving(args.port) as base, _hero.Hero(base) as hero:
            browser = hero._browser
            for aspect in aspects:
                w, h = ASPECTS[aspect]
                print("%s %s (%dx%d)" % (args.cut, aspect, w, h))
                if args.cut == "trailer":
                    write_overlay(browser, w, h, os.path.join(OUT, "wordmark-%s.png" % aspect))
                for b in todo:
                    d = frames_dir(args.cut, aspect, b["name"])
                    for f in os.listdir(d):
                        os.remove(os.path.join(d, f))
                    if b["kind"] == "fly":
                        n = shoot_fly(hero, base, aspect, b, d)
                    else:
                        if not args.db:
                            raise SystemExit("race beats need --db")
                        n = shoot_race(browser, base, aspect, b, d, args.db)
                    print("  %-14s %3d frames" % (b["name"], n), flush=True)
            for slug, msg in hero.errors:
                print("  ! %s: %s" % (slug, msg))

    for aspect in aspects:
        for b in todo:
            encode_beat(args.cut, aspect, b)
        if len(todo) == len(spec["beats"]):
            assemble(args.cut, aspect)


if __name__ == "__main__":
    main()
