"""The daily's reel: yesterday's record lap, filmed, with its end card and caption.

    venv/bin/python tools/shoot_daily.py                 # the next one to post
    venv/bin/python tools/shoot_daily.py --queue 26      # just name the next 26
    venv/bin/python tools/shoot_daily.py daily-26        # any one
    venv/bin/python tools/shoot_daily.py --out /some/dir

**It films the live site**, `/solo/<slug>?watch=<id>` on drive.cgovind.com, so it
needs no database and no checkout of the track: a daily is a row on prod, and
the watch page is already the thing that plays a lap back. That is what lets
it run in a GitHub Action with nothing but a browser.

**The record, not the day's record.** It takes the top of `/api/board`, which is
the all-time board. Run a few minutes after midnight Eastern, when the day has
just closed, those are the same lap.

**At 1x**, the whole lap: a daily is priced at 30-40s (`gen_daily`) and records come in under that, which
a reel can hold, and a sped-up lap looked like a toy.

**The sound is the game's own**, engine, tyres, wind and boosts, rendered by
`sound.js` itself: the page's `AudioContext` is swapped for an
`OfflineAudioContext` whose `currentTime` is the film's clock, so every
`setTargetAtTime` the replay makes lands on the frame that made it, and the
whole graph is rendered once the last frame is in. No music: the songs are
other people's, and a reel with them in gets muted.

Writes `<slug>.mp4` (1080x1920, AAC) and `<slug>.txt` (the caption).
"""

import argparse
import base64
import json
import math
import os
import random
import shutil
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, DRIVE)

from _shots import GL_FLAGS  # noqa: E402
from shoot_covers import _b64, _light_wheel  # noqa: E402
from shoot_video import FPS, HIDE, PUMP, SUBSTEPS, _goto, _run, no_tags, snap  # noqa: E402

BASE = "https://drive.cgovind.com"
W, H = 1080, 1920
CARD = 3.0           # seconds the end card is up after the flag, over the held last frame

CARD_PAGE = """
<!doctype html><meta charset="utf-8">
<style>
  @font-face {{ font-family:"T"; font-weight:900; font-display:block;
    src:url(data:font/woff2;base64,{font}) format("woff2"); }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{w}px; height:{h}px; overflow:hidden; background:transparent; }}
  .shot {{ position:relative; width:{w}px; height:{h}px;
           background:rgba(8,4,20,.62); display:flex; flex-direction:column;
           align-items:center; justify-content:center; gap:34px;
           font-family:"T",sans-serif; font-weight:900; color:#fff;
           text-shadow:0 4px 18px rgba(0,0,0,.55); padding-bottom:180px; }}
  .day {{ font-size:150px; text-transform:uppercase; letter-spacing:.03em; line-height:.9; }}
  .rec {{ font-size:84px; color:#ffd96b; }}
  .url {{ font-size:58px; margin-top:60px; display:flex; align-items:center; gap:22px; }}
</style>
<div class="shot">
  <div class="day">{day}</div>
  <div class="rec">Record: {time}</div>
  <div class="url">{wheel}<span>drive.cgovind.com/daily</span></div>
</div>
"""

# Across the top for the whole lap. 150px down, because the top of a reel is the
# platform's own chrome.
BANNER_PAGE = """
<!doctype html><meta charset="utf-8">
<style>
  @font-face {{ font-family:"T"; font-weight:900; font-display:block;
    src:url(data:font/woff2;base64,{font}) format("woff2"); }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{w}px; height:{h}px; overflow:hidden; background:transparent; }}
  .bar {{ position:absolute; top:150px; left:50%; transform:translateX(-50%);
          white-space:nowrap; padding:18px 40px; border-radius:18px;
          background:rgba(8,4,20,.55); font-family:"T",sans-serif; font-weight:900;
          font-size:60px; color:#fff; text-shadow:0 3px 12px rgba(0,0,0,.5); }}
  .bar b {{ color:#ffd96b; }}
  .bar i {{ font-style:normal; opacity:.55; padding:0 18px; }}
</style>
<div class="bar"><b>{day}</b><i>|</i>drive.cgovind.com</div>
"""

SR = 48000

# Before any of the page's scripts run.
OFFLINE_AUDIO = """(() => {
  window.__audioT = 0;
  class Film extends OfflineAudioContext {
    constructor() { super(2, %d, %d); window.__ac = this; }
    get currentTime() { return window.__audioT; }
    get state() { return 'running'; }
    resume() { return Promise.resolve(); }
    // Music is off, but the player still builds its decks.
    createMediaElementSource() { return this.createGain(); }
  }
  window.AudioContext = window.webkitAudioContext = Film;
})()"""

# The film clock drives the audio clock from the first filmed frame on.
CLOCK = """() => {
  const pump = window.__pump;
  window.__pump = (ms) => { if (window.__rec) window.__audioT += ms / 1000; pump(ms); };
}"""

# The rendered graph as a 16-bit stereo WAV, base64.
RENDER_AUDIO = """async () => {
  const b = await window.__ac.startRendering();
  const n = b.length, L = b.getChannelData(0), R = b.getChannelData(1);
  const buf = new ArrayBuffer(44 + n * 4), v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + n * 4, true); str(8, 'WAVEfmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 2, true);
  v.setUint32(24, b.sampleRate, true); v.setUint32(28, b.sampleRate * 4, true);
  v.setUint16(32, 4, true); v.setUint16(34, 16, true); str(36, 'data');
  v.setUint32(40, n * 4, true);
  const c = (x) => Math.max(-32768, Math.min(32767, Math.round(x * 32767)));
  for (let i = 0, o = 44; i < n; i++, o += 4) { v.setInt16(o, c(L[i]), true); v.setInt16(o + 2, c(R[i]), true); }
  const u8 = new Uint8Array(buf); let s = '';
  for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  return btoa(s);
}"""


def fmt(ms):
    """`0:25.101`, the way the game writes a lap."""
    return "%d:%06.3f" % (ms // 60000, ms % 60000 / 1000)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


def next_up(count=1):
    """The first `count` dailies not yet posted, of those that have ended.

    `post_reel.py` writes the last number it posted to `last-posted.txt` beside
    the reels, so the queue starts at Daily #1 and works forward. Once caught
    up, a run finds the next daily still running and returns nothing.
    """
    try:
        with urllib.request.urlopen(BASE + "/static/reels/last-posted.txt", timeout=30) as r:
            last = int(r.read().decode().strip() or 0)
    except urllib.error.HTTPError:
        last = 0
    with urllib.request.urlopen(BASE + "/daily", timeout=30) as r:
        today = r.geturl().rstrip("/").rsplit("/", 1)[-1]
    if not today.startswith("daily-"):
        return []
    return ["daily-%d" % n for n in range(last + 1, min(last + 1 + count, int(today[6:])))]


def caption(name, holder, ms):
    # Seeded by the name, so a re-run of one daily says the same thing.
    flair = random.Random(name).choice("🏁 🏎️ 🔥 ⚡ 🏆 💨 🚀 👑".split())
    return ("%s record: %s by %s " + flair + "\n\n"
            "Play a new track every day: drive.cgovind.com/daily\n\n"
            "#racinggame #browsergame #indiegame #gaming #speedrun"
            % (name, fmt(ms), holder))


def still(browser, tmpl, out, **kw):
    """`tmpl` rendered on transparency, full frame."""
    html = tmpl.format(w=W, h=H, font=_b64(os.path.join(DRIVE, "static", "fonts",
                                                        "titillium-900.woff2")), **kw)
    page = browser.new_page(viewport={"width": W, "height": H})
    page.set_content(html)
    page.wait_for_timeout(600)
    snap(page, out, omit_background=True)
    page.close()


def film(browser, slug, lap_id, secs, d):
    """Every frame of the lap into `d`, and its sound to `d/audio.wav`.
    Returns the frame count."""
    page = browser.new_page(viewport={"width": W, "height": H})
    no_tags(page)
    page.add_init_script(OFFLINE_AUDIO % (int((secs + CARD + 10) * SR), SR))
    try:
        page.goto("%s/solo/%s?watch=%d" % (BASE, slug, lap_id), wait_until="load", timeout=90000)
        page.wait_for_selector("#watchClock", state="visible", timeout=90000)
        page.wait_for_timeout(8000)
        page.add_style_tag(content=HIDE)
        page.evaluate(PUMP)
        page.evaluate(CLOCK)
        page.wait_for_timeout(200)
        _goto(page, 0.0, 15)
        page.evaluate("() => { window.__rec = true; }")
        n = int(math.ceil(secs * FPS))
        step = 1000.0 / FPS / SUBSTEPS
        for f in range(n):
            for _ in range(SUBSTEPS - 1):
                page.evaluate("(ms) => window.__pump(ms)", step)
            page.evaluate("(ms) => window.__present(ms)", step)
            snap(page, os.path.join(d, "f%04d.png" % f))
        if page.evaluate("() => window.__err || null"):
            print("  ! page error: %s" % page.evaluate("() => window.__err"))
        page.evaluate("() => { window.__audioT += %f; }" % CARD)
        with open(os.path.join(d, "audio.wav"), "wb") as f:
            f.write(base64.b64decode(page.evaluate(RENDER_AUDIO)))
    finally:
        page.close()
    print("  %s: %d frames" % (slug, n))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--queue", type=int, metavar="N",
                    help="print the next N slugs to post, and film nothing")
    ap.add_argument("--out", default=os.path.join(DRIVE, "media", "video", "daily"))
    args = ap.parse_args()
    if args.queue:
        print(" ".join(next_up(args.queue)))
        return
    slug = args.slug or (next_up() or [None])[0]
    if not slug:
        print("caught up: nothing to film")
        return
    track = get("/api/track/" + slug)
    lap = next((r for r in get("/api/board/" + slug)["rows"] if r["has_ghost"]), None)
    if not lap:
        raise SystemExit("%s has no lap with a replay" % slug)
    print("%s: %s %s (lap %d)" % (track["name"], lap["name"], fmt(lap["time_ms"]), lap["id"]))

    os.makedirs(args.out, exist_ok=True)
    work = os.path.join(args.out, ".frames-" + slug)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=GL_FLAGS)
        try:
            card, banner = os.path.join(work, "card.png"), os.path.join(work, "banner.png")
            still(browser, CARD_PAGE, card, day=track["name"], time=fmt(lap["time_ms"]),
                  wheel=_light_wheel(70))
            still(browser, BANNER_PAGE, banner, day=track["name"])
            n = film(browser, slug, lap["id"], lap["time_ms"] / 1000.0, work)
        finally:
            browser.close()

    dst = os.path.join(args.out, slug + ".mp4")
    # The banner for the lap, then the card over the held flag frame.
    _run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(work, "f%04d.png"),
          "-loop", "1", "-i", banner, "-loop", "1", "-i", card,
          "-i", os.path.join(work, "audio.wav"), "-filter_complex",
          "[0:v]tpad=stop_mode=clone:stop_duration=%.2f[bg];"
          "[1:v]format=rgba,fade=out:st=%.2f:d=0.4:alpha=1[b];"
          "[2:v]format=rgba,fade=in:st=%.2f:d=0.5:alpha=1[c];"
          "[bg][b]overlay=shortest=1[a];[a][c]overlay=shortest=1[v];"
          # Phone loud (-14 LUFS, what the platforms normalise to), and the
          # engine let go under the card: a finished replay holds its last note.
          "[3:a]loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st=%.2f:d=%.2f[s]"
          % (CARD, n / FPS, n / FPS, n / FPS, CARD - 0.4),
          "-map", "[v]", "-map", "[s]", "-t", "%.3f" % (n / FPS + CARD),
          "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
          "-crf", "19", "-preset", "slow", "-r", str(FPS),
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst])
    with open(os.path.join(args.out, slug + ".txt"), "w") as f:
        f.write(caption(track["name"], lap["name"], lap["time_ms"]))
    shutil.rmtree(work)
    print("  -> %s (%.1f MB)" % (dst, os.path.getsize(dst) / 1e6))


if __name__ == "__main__":
    main()
