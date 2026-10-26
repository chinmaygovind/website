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

**It also films the world-record reels**: any pool track, with `--lap` naming
the lap off its board (written as `<slug>-<lap>.mp4`) and `--rank` the place on
the card. `wr_queue.py` decides which.
"""

import argparse
import base64
import html
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
from wr_queue import comeback  # noqa: E402
from shoot_video import FPS, HIDE, PUMP, SUBSTEPS, _goto, _run, no_tags, pick, snap  # noqa: E402

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
  .day {{ font-size:150px; text-transform:uppercase; letter-spacing:.03em; line-height:.9;
          width:100%; padding:0 60px; text-align:center; }}
  .rec {{ font-size:84px; color:#ffd96b; }}
  .who {{ font-size:64px; margin-top:-14px; }}
  .when {{ font-size:46px; margin-top:-18px; opacity:.8; }}
  .url {{ font-size:58px; margin-top:60px; display:flex; align-items:center; gap:22px; }}
</style>
<div class="shot">
  <div class="day">{day}</div>
  <div class="rec">{rec}</div>
  <div class="who">{who}</div>
  {when}
  <div class="url">{wheel}<span>{url}</span></div>
</div>
"""

# Across the top for the whole lap. 150px down, because the top of a reel is the
# platform's own chrome. 277px was tried and looked worse; Chinmay chose 150.
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

# A race reel keeps the HUD that tells the race - the minimap, the place and
# the lap - and loses everything that is about operating a replay. Filmed at
# half the size and twice the density, so the HUD is the size it is on a phone.
RACE_HUD = """
  .hud-tl, .hud-tr, .mapbtns, .hud-bc, .hud-br, #watchBar, #toast, #startHint
    { display: none !important; }
  /* Below the banner and the platform's own chrome over the top of a reel. */
  .hud { top: 140px !important; }
  * { cursor: none !important; }
"""

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


def set_on(at):
    """`Oct 26, 2026 at 3:57 PM ET`, off a board row's UTC `at`."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    t = datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
    return "%s %d, %d at %d:%02d %s ET" % (t.strftime("%b"), t.day, t.year,
                                           (t.hour - 1) % 12 + 1, t.minute, t.strftime("%p"))


def caption(name, holder, ms, slug, rank=1, podium=(), at=None):
    # Seeded by the name, so a re-run of one reel says the same thing.
    flair = random.Random(name + ("" if rank == 1 else str(rank))).choice("🏁 🏎️ 🔥 ⚡ 🏆 💨 🚀 👑".split())
    tags = "#racinggame #browsergame #indiegame #gaming #speedrun"
    if slug.startswith("daily-"):
        # The top three by name, so more of the board sees itself in the post.
        top = "".join("%s %s %s\n" % (m, r["name"], fmt(r["time_ms"]))
                      for m, r in zip("🥇🥈🥉", podium))
        return ("%s record: %s by %s %s\n\n%s"
                "Play a new track every day: drive.cgovind.com/daily\n\n%s"
                % (name, fmt(ms), holder, flair, top + "\n" if top else "", tags))
    what = "world record" if rank == 1 else "#%d all time" % rank
    nudge = random.Random(name + holder).choice([
        "Your turn:", "Beat it here:", "Can you go faster?",
        "Free in your browser, no download:", "Race this ghost:",
        "Drive the same track:", "Record's up for grabs:"])
    when = " on " + set_on(at) if at else ""
    return ("%s %s: %s by %s%s %s\n\n%s drive.cgovind.com/solo/%s\n\n%s"
            % (name, what, fmt(ms), holder, when, flair, nudge, slug, tags))


def still(browser, tmpl, out, **kw):
    """`tmpl` rendered on transparency, full frame."""
    html = tmpl.format(w=W, h=H, font=_b64(os.path.join(DRIVE, "static", "fonts",
                                                        "titillium-900.woff2")), **kw)
    page = browser.new_page(viewport={"width": W, "height": H})
    page.set_content(html)
    page.wait_for_timeout(600)
    snap(page, out, omit_background=True)
    page.close()


def film(browser, path, secs, d, start=0.0, hz=15, follow=None):
    """Every frame of `secs` from `start` of the replay at `path` into `d`, and
    its sound to `d/audio.wav`. `follow` is a race's car to hold the camera,
    and a race is filmed with its HUD (`RACE_HUD`). Returns the frame count."""
    if follow is None:
        page = browser.new_page(viewport={"width": W, "height": H})
    else:
        page = browser.new_page(viewport={"width": W // 2, "height": H // 2},
                                device_scale_factor=2)
    no_tags(page)
    page.add_init_script(OFFLINE_AUDIO % (int((secs + CARD + 10) * SR), SR))
    try:
        page.goto(BASE + path, wait_until="load", timeout=90000)
        page.wait_for_selector("#watchClock", state="visible", timeout=90000)
        page.wait_for_timeout(8000)
        if follow is not None:
            names = page.eval_on_selector_all("button.wcar span:nth-child(2)",
                                              "els => els.map(e => e.textContent)")
            page.click('button.wcar[data-cam="%d"]' % names.index(follow))
        page.add_style_tag(content=HIDE if follow is None else RACE_HUD)
        page.evaluate(PUMP)
        page.evaluate(CLOCK)
        page.wait_for_timeout(200)
        _goto(page, start, hz)
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
    print("  %s: %d frames" % (path, n))
    return n


def lap_shot(slug, lap_id, rank):
    """A daily's record, or one lap off a pool track's board."""
    track = get("/api/track/" + slug)
    rows = get("/api/board/" + slug)["rows"]
    lap = next((r for r in rows if r["has_ghost"] and (lap_id in (None, r["id"]))), None)
    if not lap:
        raise SystemExit("%s has no lap with a replay" % slug)
    rank = rank or rows.index(lap) + 1
    daily = slug.startswith("daily-")
    label = "Record" if daily else "World Record" if rank == 1 else "#%d All Time" % rank
    print("%s: %s %s (lap %d)" % (track["name"], lap["name"], fmt(lap["time_ms"]), lap["id"]))
    return {"name": slug if lap_id is None else "%s-%d" % (slug, lap["id"]),
            "path": "/solo/%s?watch=%d" % (slug, lap["id"]), "secs": lap["time_ms"] / 1000.0,
            "banner": track["name"],
            "url": "drive.cgovind.com/daily" if daily else "drive.cgovind.com/solo/" + slug,
            "card": {"day": track["name"], "rec": "%s: %s" % (label, fmt(lap["time_ms"])),
                     "who": "by " + html.escape(lap["name"]),
                     "when": '<div class="when">%s</div>' % set_on(lap["at"]).split(" at ")[0]
                     if lap.get("at") and not daily else ""},
            "caption": caption(track["name"], lap["name"], lap["time_ms"], slug, rank, rows[:3],
                               None if daily else lap.get("at"))}


# A race with no comeback in it is filmed as its run to the flag, this long.
# One with a comeback is filmed whole, however long that is.
RACE_SECS = 30.0


def race_shot(race_id):
    """One room race, following whoever climbed furthest through the field
    (`wr_queue.comeback`) over the stretch where they passed the most cars - or,
    with no passing in it, the run to the flag `shoot_video.pick` likes best."""
    race = get("/api/race/%d" % race_id)
    track = get("/api/track/" + race["track"])
    done = sorted((c for c in race["cars"] if c.get("ms")), key=lambda c: c["ms"])
    if len(done) < 2:
        raise SystemExit("race %d has fewer than two finishers" % race_id)
    cb = comeback(race, track["line"], track["closed"], {c["name"] for c in race["cars"] if c.get("bot")})
    gap = (done[1]["ms"] - done[0]["ms"]) / 1000.0
    if cb:
        # The whole comeback: from just before the first car passed to the flag.
        climb, follow, frm, to, passes = cb
        end = next(c["ms"] for c in race["cars"] if c["name"] == follow) / 1000.0 + 0.8
        start = max(0.0, passes[0] - 4.0)
        secs = end - start
        rec, who = "P%d to P%d" % (frm, to), "by " + html.escape(follow)
    else:
        for secs in (min(RACE_SECS, done[0]["ms"] / 1000.0), 20.0, 12.0):
            try:
                follow, start = pick(race, secs, "finish")
                break
            except RuntimeError:
                continue
        else:
            raise SystemExit("race %d has no clean run to the flag" % race_id)
        rec = ("Photo finish: %.3fs" if gap < 0.2 else "Won by %.3fs") % gap
        who = "%s vs %s" % (html.escape(done[0]["name"]), html.escape(done[1]["name"]))
    print("race %d on %s: %s, following %s from %.1fs for %.0fs"
          % (race_id, track["name"], rec, follow, start, secs))
    return {"name": "race-%d" % race_id, "path": "/race/%d" % race_id, "secs": secs,
            "start": start, "hz": race["hz"], "follow": follow,
            "banner": "Multiplayer", "url": "drive.cgovind.com",
            "card": {"day": track["name"], "rec": rec, "who": who, "when": ""},
            "caption": race_caption(race_id, track["name"], done, cb)}


def race_caption(race_id, track, done, cb=None):
    gap = (done[1]["ms"] - done[0]["ms"]) / 1000.0
    flair = random.Random(race_id).choice("🏁 🏎️ 🔥 ⚡ 💨 😤 👀".split())
    top = "".join("%s %s %s\n" % (m, c["name"], fmt(c["ms"])) for m, c in zip("🥇🥈🥉", done))
    if cb and cb[3] == 1:
        head = "%s goes from P%d to the win on %s %s" % (cb[1], cb[2], track, flair)
    elif cb:
        head = "%s climbs from P%d to P%d on %s %s" % (cb[1], cb[2], cb[3], track, flair)
    else:
        head = "%s beats %s by %.3fs on %s %s" % (done[0]["name"], done[1]["name"], gap, track, flair)
    return ("%s\n\n%s\n"
            "Race your friends live, free in your browser: drive.cgovind.com\n\n"
            "#racinggame #browsergame #indiegame #gaming #multiplayer" % (head, top))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--queue", type=int, metavar="N",
                    help="print the next N slugs to post, and film nothing")
    ap.add_argument("--lap", type=int, help="film this lap off the board, not the top one")
    ap.add_argument("--rank", type=int, help="the place to put on the card, if not where "
                    "the lap is now: a world record stays one after it is beaten")
    ap.add_argument("--race", type=int, help="film the finish of this race off /race/<id>")
    ap.add_argument("--name", help="the reel's file name, if not the default one")
    ap.add_argument("--out", default=os.path.join(DRIVE, "media", "video", "daily"))
    args = ap.parse_args()
    if args.queue:
        print(" ".join(next_up(args.queue)))
        return
    if args.race:
        shot = race_shot(args.race)
    else:
        slug = args.slug or (next_up() or [None])[0]
        if not slug:
            print("caught up: nothing to film")
            return
        shot = lap_shot(slug, args.lap, args.rank)
    name = args.name or shot["name"]

    os.makedirs(args.out, exist_ok=True)
    work = os.path.join(args.out, ".frames-" + name)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=GL_FLAGS)
        try:
            card, banner = os.path.join(work, "card.png"), os.path.join(work, "banner.png")
            still(browser, CARD_PAGE, card, url=shot["url"], wheel=_light_wheel(70),
                  **shot["card"])
            still(browser, BANNER_PAGE, banner, day=shot["banner"])
            n = film(browser, shot["path"], shot["secs"], work, shot.get("start", 0.0),
                     shot.get("hz", 15), shot.get("follow"))
        finally:
            browser.close()

    dst = os.path.join(args.out, name + ".mp4")
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
    with open(os.path.join(args.out, name + ".txt"), "w") as f:
        f.write(shot["caption"])
    shutil.rmtree(work)
    print("  -> %s (%.1f MB)" % (dst, os.path.getsize(dst) / 1e6))


if __name__ == "__main__":
    main()
