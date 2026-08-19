"""Cover art for a storefront: a track's hero shot at portal sizes, wordmarked.

    python tools/shoot_covers.py                 # every track, every size
    python tools/shoot_covers.py rainbow         # one track

A portal wants a 1920x1080, an 800x1200 and an 800x800 of something that looks
like the game is worth playing. That picture already exists - it is the cover
every track carries on the home page - so this is the same composition from
`_hero.py` at three more sizes with the wordmark laid across the foot.

**The framing is not duplicated here**, which it used to be: `COVERS` in this
file and the card art in `shoot_tracks.py` were two answers to "where do you
stand to photograph Spa", and only one of them was ever looked at. `_hero.FRAMES`
is the single answer now, so a cover and a card of one track are the same
photograph.

**The pictures go to `drive/covers/` and are not committed.** They are a
deliverable for somewhere else, unlike `static/img/tracks/`, which the site
serves.

**They go stale silently**, the same way the card art does: change a track's
geometry, palette or sky and its cover is of the old one, and nothing will fail.
Re-run this, look at the pictures, and hand them over.
"""

import argparse
import base64
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hero
from _shots import have_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVE = os.path.dirname(HERE)
OUT = os.path.join(DRIVE, "covers")

SIZES = [(1920, 1080), (800, 1200), (800, 800)]


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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tracks", nargs="*", default=None)
    args = ap.parse_args()

    if not have_playwright():
        print("this needs Playwright, and there is none in this venv.")
        return 1
    sys.path.insert(0, DRIVE)
    import tracks as tracks_mod
    slugs = args.tracks or [t["slug"] for t in tracks_mod.TRACKS]
    unknown = [x for x in slugs if not tracks_mod.get(x)]
    if unknown:
        print("no such track: " + ", ".join(unknown))
        return 1

    os.makedirs(OUT, exist_ok=True)
    with _hero.serving(5098) as base, _hero.Hero(base) as hero:
        for slug in slugs:
            cfg = _hero.frame_for(slug)
            for (w, h) in SIZES:
                page = hero.open(slug, (w, h))
                try:
                    res = hero.compose(page, cfg)
                    plain = os.path.join(OUT, "%s_%dx%d.png" % (slug, w, h))
                    page.screenshot(path=plain)
                    _title(page, plain, w, h)
                    page.screenshot(path=os.path.join(
                        OUT, "%s_%dx%d-title.png" % (slug, w, h)))
                finally:
                    page.close()
                print("  %-12s %4dx%-4d f=%.2f dist=%.0f"
                      % (slug, w, h, res["f"], res["dist"]))
        for slug, msg in hero.errors:
            print("  ! %s: %s" % (slug, msg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
