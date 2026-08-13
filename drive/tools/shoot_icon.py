"""Render every raster icon from ``static/img/icon.svg``.

The SVG is the only drawing; everything else in ``static/img`` that is a picture
of the mark is made here, so the two can never drift.

    cd drive && venv/bin/python tools/shoot_icon.py

**The transparency is not uniform, on purpose.** The mark has no tile behind it,
which is what lets it sit on the nav's paper as just a wheel - so the SVG, the
two small PNGs and the .ico are transparent. App icons cannot be: iOS mattes a
transparent apple-touch-icon onto black, and Android crops a maskable icon to a
circle and fills the rest with whatever it likes. Those three (180, 192, 512)
are therefore painted over ``PAPER`` here, which is the same near-white the site
is set on, and the same ground the mark is drawn *for* - a dark rim needs a
light background, and picking the tile colour is the price of not having a tile.

Chrome does the compositing as well as the rasterising: the page it screenshots
just has a background colour under the image. Pillow is only needed for the
multi-size .ico, and only then.

`og.png`, the card a pasted link to Drive unfurls into, is made here too and for
the same reason: it is a picture of the mark, so it has to be re-made when the
mark changes, and the only way to be sure of that is for one command to make all
of them. It is the one target that is a *layout* rather than a resize, so it
also needs the site's own type - the fonts are copied in beside it and loaded
over file://, because a webfont that silently falls back would not fail, it
would just ship a card set in Times.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IMG = os.path.join(ROOT, "static", "img")
FONTS = os.path.join(ROOT, "static", "fonts")
SVG = os.path.join(IMG, "icon.svg")

PAPER = "#faf8f4"        # what the app icons are painted over
INK = "#1d1d1f"
INK_SOFT = "#6b6b73"
RED = "#c0182b"          # style.css's --red, the site's one accent

OG_SIZE = (1200, 630)    # what every unfurler crops from
OG_TAGLINE = "Low-poly time trials and multiplayer races."

CHROME = next((c for c in ("google-chrome", "chromium", "chromium-browser")
               if shutil.which(c)), None)

# size -> (filename, background or None for transparent)
TARGETS = [
    (16,  "icon-16.png",  None),
    (32,  "icon-32.png",  None),
    (180, "icon-180.png", PAPER),
    (192, "icon-192.png", PAPER),
    (512, "icon-512.png", PAPER),
]
ICO_SIZES = (16, 32, 48)


def _chrome(work, page, out, width, height):
    """Screenshot `page` (a file inside `work`) at exactly width x height."""
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--user-data-dir=" + os.path.join(work, "prof"),
           "--default-background-color=00000000",
           "--force-device-scale-factor=1",
           "--window-size=%d,%d" % (width, height),
           "--screenshot=" + out,
           "file://" + os.path.join(work, page)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)


def shoot(size, out, background):
    """One rasterisation, at exactly `size`, through headless Chrome."""
    work = tempfile.mkdtemp(prefix="driveicon")
    try:
        shutil.copy(SVG, os.path.join(work, "icon.svg"))
        bg = background or "transparent"
        with open(os.path.join(work, "p.html"), "w") as f:
            f.write(
                "<style>html,body{margin:0;padding:0;overflow:hidden;"
                "background:%s}img{display:block;width:%dpx;height:%dpx}</style>"
                "<img src='icon.svg'>" % (bg, size, size))
        _chrome(work, "p.html", out, size, size)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def shoot_og(out):
    """The 1200x630 card a pasted link unfurls into: mark, wordmark, one line.

    Laid out to survive the crop. Every unfurler trims this differently and a
    couple square it off, so nothing that matters goes near an edge - the whole
    composition sits in the middle two thirds and the rule under it is the only
    thing allowed to run wide.
    """
    work = tempfile.mkdtemp(prefix="driveog")
    try:
        shutil.copy(SVG, os.path.join(work, "icon.svg"))
        for weight in ("400", "600", "900"):
            shutil.copy(os.path.join(FONTS, "titillium-%s.woff2" % weight), work)
        with open(os.path.join(work, "og.html"), "w") as f:
            f.write(OG_HTML % {"paper": PAPER, "ink": INK, "soft": INK_SOFT,
                               "red": RED, "tagline": OG_TAGLINE})
        _chrome(work, "og.html", out, *OG_SIZE)
    finally:
        shutil.rmtree(work, ignore_errors=True)


OG_HTML = """<!doctype html><meta charset="utf-8">
<style>
@font-face{font-family:"Titillium Web";src:url(titillium-400.woff2);font-weight:400}
@font-face{font-family:"Titillium Web";src:url(titillium-600.woff2);font-weight:600}
@font-face{font-family:"Titillium Web";src:url(titillium-900.woff2);font-weight:900}
html,body{margin:0;padding:0;overflow:hidden;background:%(paper)s}
body{width:1200px;height:630px;display:flex;align-items:center;
     justify-content:center;gap:76px;padding:0 90px;box-sizing:border-box;
     font-family:"Titillium Web",sans-serif;color:%(ink)s}
img{width:296px;height:296px;display:block;flex:none}
h1{margin:0;font-weight:900;font-size:136px;line-height:.92;letter-spacing:-.03em}
p{margin:20px 0 0;font-weight:400;font-size:36px;line-height:1.28;color:%(soft)s;max-width:19ch}
b{display:block;margin-top:26px;font-weight:600;font-size:26px;letter-spacing:.14em;
  text-transform:uppercase;color:%(red)s}
</style>
<img src="icon.svg">
<div><h1>Drive</h1><p>%(tagline)s</p><b>drive.cgovind.com</b></div>
"""


def main():
    if not CHROME:
        print("no chrome/chromium on PATH - cannot render icons")
        return 1
    for size, name, bg in TARGETS:
        out = os.path.join(IMG, name)
        shoot(size, out, bg)
        print("%-16s %3dpx  %s" % (name, size, bg or "transparent"))

    # apple-touch-icon is the 180 under another name; iOS asks for it by that
    # name and rounds the corners itself.
    shutil.copy(os.path.join(IMG, "icon-180.png"),
                os.path.join(IMG, "apple-touch-icon.png"))
    print("%-16s 180px  %s" % ("apple-touch-icon.png", PAPER))

    shoot_og(os.path.join(IMG, "og.png"))
    print("%-16s %dx%d  %s" % ("og.png", OG_SIZE[0], OG_SIZE[1], PAPER))

    try:
        from PIL import Image
    except ImportError:
        print("favicon.ico NOT rebuilt: pip install Pillow")
        return 0
    base = os.path.join(IMG, "_ico-48.png")
    shoot(48, base, None)
    Image.open(base).convert("RGBA").save(os.path.join(IMG, "favicon.ico"),
                                          sizes=[(s, s) for s in ICO_SIZES])
    os.remove(base)
    print("%-16s %s  transparent" % ("favicon.ico", "/".join(str(s) for s in ICO_SIZES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
