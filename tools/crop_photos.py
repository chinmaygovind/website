#!/usr/bin/env python3
"""Crop the about-modal collage photos into the squares the polaroids want.

The collage in `#modal-about` draws every photo at `aspect-ratio: 1/1` with
`object-fit: cover`, so a phone photo put in unedited is centre-cropped by the
browser and nobody gets a say in which third of it survives. This is that say.

    python3 tools/crop_photos.py

It reads whatever is in the source folder - JPEG, PNG, HEIC straight off an
iPhone - converts each one to a web-safe JPEG, and serves a cropper at
http://localhost:5055. Drag to pan, scroll or use the slider to zoom, pick which
of the twenty slots it fills, and Save writes `site/assets/about/photo-NN.jpg` at
560x560 - the same size and quality as the files already there, so a saved crop
is live on the next reload with no other step.

Nothing is written until you press Save, and only the slots you save are
touched; the rest keep whatever is in them. Re-running is safe and re-cropping a
slot just overwrites it.

`--auto` skips the browser and writes every slot with the crop the cropper opens
on - the whole frame scaled to cover the square, centred, which is what
`object-fit: cover` would have done anyway but done once at 560px instead of on
every visitor's machine. Use it to fill the folder in one go, then open the
cropper to re-do only the few it got wrong.

    --source DIR   where the originals are  (default: the Drive folder below)
    --out DIR      where the crops go       (default: site/assets/about)
    --size N       output edge in pixels    (default: 560)
    --port N       default 5055
    --auto         write all slots centre-cropped and exit, no browser
    --exclude NAME drop a source file by name; repeatable

HEIC needs `pillow-heif`, which is not a dependency of the site itself because
nothing at runtime reads one:

    pip install pillow-heif
"""

import argparse
import base64
import http.server
import io
import json
import os
import pathlib
import re
import socketserver
import threading
import webbrowser

from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF = True
except ImportError:
    HEIF = False

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = pathlib.Path.home() / "GDrive" / "Z Malarkey" / "Website Photos"
DEFAULT_OUT = ROOT / "site" / "assets" / "about"
SLOTS = 20
# Big enough that any square crop of it still beats the 560px output, small
# enough that a dozen of them do not stall the page. A 4032px iPhone frame is
# 4MB of JPEG nobody needs to send to a localhost cropper.
PREVIEW_EDGE = 1600
SUFFIXES = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp", ".tif", ".tiff")


def load_sources(source, exclude=()):
    """Every image in `source`, EXIF-rotated and shrunk to a sane preview size."""
    if not source.is_dir():
        raise SystemExit("no such folder: %s" % source)

    drop = set(exclude)
    files = sorted(p for p in source.iterdir()
                   if p.suffix.lower() in SUFFIXES and not p.name.startswith(".")
                   and p.name not in drop)
    if not files:
        raise SystemExit("no images in %s" % source)
    missing = drop - {p.name for p in source.iterdir()}
    if missing:
        print("  note: --exclude named %s, which is not in the folder"
              % ", ".join(sorted(missing)))

    out, skipped = [], []
    for path in files:
        try:
            im = Image.open(path)
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
        except Exception as exc:                                  # noqa: BLE001
            hint = ""
            if path.suffix.lower() in (".heic", ".heif") and not HEIF:
                hint = "  (pip install pillow-heif)"
            skipped.append("%s: %s%s" % (path.name, exc, hint))
            continue

        im.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88, optimize=True)
        out.append({"name": path.name, "jpeg": buf.getvalue(),
                    "w": im.width, "h": im.height})
        print("  read %-20s %sx%s" % (path.name, im.width, im.height))

    for line in skipped:
        print("  SKIPPED %s" % line)
    if not out:
        raise SystemExit("nothing could be read")
    return out


def write_slot(im, slot, out_dir, size):
    """The one place a square becomes a file, so `--auto` and Save cannot drift."""
    if im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    dest = out_dir / ("photo-%02d.jpg" % slot)
    out_dir.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=82, optimize=True, progressive=True)
    return dest


def auto_crop(photos, out_dir, size):
    """Fill every slot with the crop the browser would have opened on.

    `ImageOps.fit` centred is exactly the cropper's starting view: scale to
    cover, centre, no pan. Doing it here means the twenty defaults cost one
    command rather than twenty clicks.
    """
    if len(photos) > SLOTS:
        print("  note: %d photos for %d slots - the last %d are ignored"
              % (len(photos), SLOTS, len(photos) - SLOTS))
    manifest = []
    for slot, p in enumerate(photos[:SLOTS], start=1):
        im = Image.open(io.BytesIO(p["jpeg"]))
        dest = write_slot(ImageOps.fit(im, (size, size), Image.LANCZOS,
                                       centering=(0.5, 0.5)),
                          slot, out_dir, size)
        manifest.append({"slot": dest.name, "source": p["name"]})
        print("  %-20s -> %s  (%s KB)"
              % (p["name"], dest.name, dest.stat().st_size // 1024))
    (out_dir / "SOURCES.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print("\nwrote %d crop(s) and SOURCES.json" % len(manifest))


def build_handler(photos, out_dir, size):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            if self.path == "/photos.json":
                meta = [{"i": i, "name": p["name"], "w": p["w"], "h": p["h"]}
                        for i, p in enumerate(photos)]
                body = json.dumps({"photos": meta, "slots": SLOTS,
                                   "size": size, "out": str(out_dir)}).encode()
                return self._send(200, body, "application/json")
            m = re.fullmatch(r"/src/(\d+)\.jpg", self.path)
            if m and int(m.group(1)) < len(photos):
                return self._send(200, photos[int(m.group(1))]["jpeg"], "image/jpeg")
            self._send(404, b"no", "text/plain")

        def do_POST(self):
            if self.path != "/save":
                return self._send(404, b"no", "text/plain")
            n = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(n))
                slot = int(payload["slot"])
                if not 1 <= slot <= SLOTS:
                    raise ValueError("slot %s out of range" % slot)
                raw = base64.b64decode(payload["data"].split(",", 1)[1])
                im = Image.open(io.BytesIO(raw)).convert("RGB")
            except Exception as exc:                              # noqa: BLE001
                return self._send(400, json.dumps({"error": str(exc)}).encode(),
                                  "application/json")

            # The canvas is already square at `size`; re-encoding here rather than
            # trusting the browser's toDataURL quality is what keeps these files
            # the same weight as the ones already in the folder.
            dest = write_slot(im, slot, out_dir, size)
            print("  wrote %s  (%s KB)" % (dest.name, dest.stat().st_size // 1024))
            self._send(200, json.dumps({"ok": True, "file": dest.name}).encode(),
                       "application/json")

    return Handler


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>collage cropper</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; background: #14161a; color: #e9e9e9;
    font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
    display: flex; height: 100vh; overflow: hidden;
  }
  #strip {
    width: 190px; flex: none; overflow-y: auto; padding: 12px;
    border-right: 1px solid #2b2f36; background: #101216;
  }
  #strip h1 { font-size: 13px; text-transform: uppercase; letter-spacing: .08em;
    color: #8b929c; margin: 0 0 10px; font-weight: 600; }
  .thumb {
    position: relative; width: 100%; margin-bottom: 8px; border-radius: 7px;
    overflow: hidden; cursor: pointer; border: 2px solid transparent; display: block;
    background: none; padding: 0;
  }
  .thumb img { display: block; width: 100%; aspect-ratio: 1/1; object-fit: cover; }
  .thumb.active { border-color: #4da3ff; }
  .thumb .tag {
    position: absolute; left: 0; right: 0; bottom: 0; padding: 3px 6px;
    background: rgba(0,0,0,.72); font-size: 11px; color: #cfd4da;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .thumb .done {
    position: absolute; top: 5px; right: 5px; width: 20px; height: 20px;
    border-radius: 50%; background: #2e9e5b; color: #fff; font-size: 13px;
    display: none; align-items: center; justify-content: center;
  }
  .thumb.saved .done { display: flex; }

  main { flex: 1; display: flex; flex-direction: column; padding: 20px; min-width: 0; }
  #bar { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; flex-wrap: wrap; }
  #bar label { color: #8b929c; font-size: 13px; }
  select, button {
    font: inherit; border-radius: 7px; border: 1px solid #39404a;
    background: #1d2128; color: #e9e9e9; padding: 7px 12px; cursor: pointer;
  }
  button.primary { background: #2f6dd0; border-color: #2f6dd0; font-weight: 600; }
  button.primary:hover { background: #3c7ee6; }
  button:disabled { opacity: .45; cursor: default; }
  #stagewrap { flex: 1; display: flex; align-items: center; justify-content: center; min-height: 0; }
  #stage {
    position: relative; overflow: hidden; background: #0b0d10;
    border-radius: 10px; box-shadow: 0 0 0 2px #39404a, 0 18px 50px rgba(0,0,0,.5);
    cursor: grab; touch-action: none;
  }
  #stage.drag { cursor: grabbing; }
  #stage img { position: absolute; transform-origin: 0 0; user-select: none;
    -webkit-user-drag: none; pointer-events: none; }
  #stage::after {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background:
      linear-gradient(to right, transparent 33.33%, rgba(255,255,255,.16) 33.33%,
        rgba(255,255,255,.16) calc(33.33% + 1px), transparent calc(33.33% + 1px),
        transparent 66.66%, rgba(255,255,255,.16) 66.66%,
        rgba(255,255,255,.16) calc(66.66% + 1px), transparent calc(66.66% + 1px)),
      linear-gradient(to bottom, transparent 33.33%, rgba(255,255,255,.16) 33.33%,
        rgba(255,255,255,.16) calc(33.33% + 1px), transparent calc(33.33% + 1px),
        transparent 66.66%, rgba(255,255,255,.16) 66.66%,
        rgba(255,255,255,.16) calc(66.66% + 1px), transparent calc(66.66% + 1px));
  }
  #zoom { width: 220px; accent-color: #4da3ff; }
  #note { color: #8b929c; font-size: 13px; min-height: 20px; margin-top: 12px; }
  #note b { color: #6ee39b; font-weight: 600; }
  kbd { background: #23272f; border: 1px solid #39404a; border-bottom-width: 2px;
    border-radius: 4px; padding: 1px 5px; font-size: 12px; }
</style>
</head>
<body>
  <aside id="strip"><h1>photos</h1></aside>
  <main>
    <div id="bar">
      <label for="slot">slot</label>
      <select id="slot"></select>
      <label for="zoom">zoom</label>
      <input type="range" id="zoom" min="100" max="400" value="100" />
      <button id="reset">recentre</button>
      <button id="save" class="primary">save &amp; next</button>
    </div>
    <div id="stagewrap"><div id="stage"></div></div>
    <p id="note">drag to pan &middot; scroll to zoom &middot; <kbd>&larr;</kbd> <kbd>&rarr;</kbd> to change photo</p>
  </main>
<script>
(function () {
  var cfg = null, photos = [], cur = -1;
  var stage = document.getElementById("stage");
  var strip = document.getElementById("strip");
  var slotSel = document.getElementById("slot");
  var zoomEl = document.getElementById("zoom");
  var note = document.getElementById("note");
  var img = null, view = null, EDGE = 0;

  function stageEdge() {
    var wrap = document.getElementById("stagewrap");
    return Math.max(240, Math.min(wrap.clientWidth - 20, wrap.clientHeight - 20, 640));
  }

  function clamp() {
    // The square must stay fully covered: the image's drawn box has to contain it.
    var dw = img.naturalWidth * view.s, dh = img.naturalHeight * view.s;
    view.x = Math.min(0, Math.max(EDGE - dw, view.x));
    view.y = Math.min(0, Math.max(EDGE - dh, view.y));
  }

  function paint() {
    img.style.transform = "translate(" + view.x + "px," + view.y + "px) scale(" + view.s + ")";
    img.style.width = img.naturalWidth + "px";
    img.style.height = img.naturalHeight + "px";
    zoomEl.value = Math.round(view.s / view.fit * 100);
  }

  function fit() {
    EDGE = stageEdge();
    stage.style.width = stage.style.height = EDGE + "px";
    view.fit = Math.max(EDGE / img.naturalWidth, EDGE / img.naturalHeight);
    if (!view.s || view.s < view.fit) view.s = view.fit;
    view.x = (EDGE - img.naturalWidth * view.s) / 2;
    view.y = (EDGE - img.naturalHeight * view.s) / 2;
    clamp(); paint();
  }

  function select(i) {
    if (i < 0 || i >= photos.length) return;
    cur = i;
    [].forEach.call(strip.querySelectorAll(".thumb"), function (t, n) {
      t.classList.toggle("active", n === i);
    });
    slotSel.value = String(photos[i].slot);
    stage.innerHTML = "";
    img = new Image();
    view = { x: 0, y: 0, s: 0, fit: 0 };
    img.onload = function () { fit(); };
    img.src = "/src/" + i + ".jpg";
    stage.appendChild(img);
    note.textContent = photos[i].name;
  }

  function zoomAt(px, py, next) {
    next = Math.max(view.fit, Math.min(view.fit * 4, next));
    // Keep whatever is under the pointer under the pointer.
    view.x = px - (px - view.x) * (next / view.s);
    view.y = py - (py - view.y) * (next / view.s);
    view.s = next;
    clamp(); paint();
  }

  stage.addEventListener("wheel", function (e) {
    if (!img) return;
    e.preventDefault();
    var r = stage.getBoundingClientRect();
    zoomAt(e.clientX - r.left, e.clientY - r.top, view.s * (e.deltaY < 0 ? 1.12 : 1 / 1.12));
  }, { passive: false });

  stage.addEventListener("pointerdown", function (e) {
    if (!img) return;
    stage.setPointerCapture(e.pointerId);
    stage.classList.add("drag");
    var sx = e.clientX, sy = e.clientY, ox = view.x, oy = view.y;
    function move(ev) {
      view.x = ox + (ev.clientX - sx);
      view.y = oy + (ev.clientY - sy);
      clamp(); paint();
    }
    function up() {
      stage.classList.remove("drag");
      stage.removeEventListener("pointermove", move);
      stage.removeEventListener("pointerup", up);
    }
    stage.addEventListener("pointermove", move);
    stage.addEventListener("pointerup", up);
  });

  zoomEl.addEventListener("input", function () {
    if (!img) return;
    zoomAt(EDGE / 2, EDGE / 2, view.fit * (+zoomEl.value / 100));
  });
  document.getElementById("reset").addEventListener("click", function () {
    if (img) { view.s = 0; fit(); }
  });
  slotSel.addEventListener("change", function () {
    if (cur >= 0) photos[cur].slot = +slotSel.value;
  });
  window.addEventListener("resize", function () { if (img) fit(); });
  document.addEventListener("keydown", function (e) {
    if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT") return;
    if (e.key === "ArrowLeft") select(cur - 1);
    if (e.key === "ArrowRight") select(cur + 1);
  });

  document.getElementById("save").addEventListener("click", function () {
    if (!img || !img.complete) return;
    var btn = this;
    var c = document.createElement("canvas");
    c.width = c.height = cfg.size;
    var g = c.getContext("2d");
    g.imageSmoothingQuality = "high";
    var k = cfg.size / EDGE;
    g.drawImage(img, view.x * k, view.y * k,
                img.naturalWidth * view.s * k, img.naturalHeight * view.s * k);
    btn.disabled = true;
    fetch("/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot: photos[cur].slot, data: c.toDataURL("image/jpeg", 0.95) })
    }).then(function (r) { return r.json(); }).then(function (d) {
      btn.disabled = false;
      if (d.error) { note.textContent = "failed: " + d.error; return; }
      strip.querySelectorAll(".thumb")[cur].classList.add("saved");
      note.innerHTML = "wrote <b>" + d.file + "</b>";
      if (cur + 1 < photos.length) setTimeout(function () { select(cur + 1); }, 450);
    }).catch(function (err) { btn.disabled = false; note.textContent = String(err); });
  });

  fetch("/photos.json").then(function (r) { return r.json(); }).then(function (d) {
    cfg = d;
    for (var s = 1; s <= d.slots; s++) {
      var o = document.createElement("option");
      o.value = String(s);
      o.textContent = "photo-" + (s < 10 ? "0" : "") + s + ".jpg";
      slotSel.appendChild(o);
    }
    photos = d.photos.map(function (p, i) { return { name: p.name, slot: i + 1 }; });
    d.photos.forEach(function (p, i) {
      var b = document.createElement("button");
      b.className = "thumb";
      b.innerHTML = '<img src="/src/' + i + '.jpg" alt="" />' +
                    '<span class="done">&check;</span>' +
                    '<span class="tag">' + p.name + "</span>";
      b.addEventListener("click", function () { select(i); });
      strip.appendChild(b);
    });
    select(0);
  });
})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    ap.add_argument("--size", type=int, default=560)
    ap.add_argument("--port", type=int, default=5055)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--exclude", action="append", default=[], metavar="NAME")
    args = ap.parse_args()

    print("reading %s" % args.source)
    photos = load_sources(args.source, args.exclude)
    print("\n%d photo(s) ready; crops land in %s at %dx%d"
          % (len(photos), args.out, args.size, args.size))

    if args.auto:
        print()
        return auto_crop(photos, args.out, args.size)

    handler = build_handler(photos, args.out, args.size)

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(("127.0.0.1", args.port), handler) as httpd:
        url = "http://localhost:%d" % args.port
        print("cropper on %s   (ctrl-c to stop)\n" % url)
        if not args.no_open and os.environ.get("DISPLAY"):
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
