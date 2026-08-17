"""The 1200x630 card a link to one *track* unfurls into.

`shoot_icon.py` makes `og.png`, the card for the site as a whole; this makes the
fourteen beside it, one per track, so that pasting a link to Big Red shows Big
Red rather than a steering wheel. Pasted links are most of how a game like this
travels, and the difference between a generic card and a photograph of the road
is the difference between a link somebody scrolls past and one they click.

    cd drive && venv/bin/python tools/shoot_og_cards.py          # all of them
    cd drive && venv/bin/python tools/shoot_og_cards.py bigred   # just one

**The source is the switcher's preview, not the game.** `static/img/tracks/
<slug>.png` is already a photograph of that track taken through the real
renderer, so re-shooting the world at a second size would be fourteen more
software-GL renders to get a picture we already have - and a second framing that
could disagree with the first. This is a layout over that picture, which is why
it needs no server and no GL and takes about a second a card.

That does mean **a card is only as fresh as the preview under it**, so
`shoot_tracks.py` calls this at the end of its own run: one command re-makes
both, and the staleness note in `drive/CLAUDE.md` covers the pair. Running this
alone is for when the *layout* changed and the tracks did not.

The type is the site's own, loaded over file:// from `static/fonts` for the
reason `shoot_icon.py` gives: a webfont that silently falls back would not fail,
it would just ship a card set in Times.
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import _shots  # noqa: E402

SHOTS = os.path.join(ROOT, "static", "img", "tracks")
OUT = os.path.join(ROOT, "static", "img", "og")
FONTS = os.path.join(ROOT, "static", "fonts")

SIZE = (1200, 630)
# A layout over a picture that is already on disk: no GL, no track to build, and
# nothing to wait for but the fonts. `shoot_tracks.py`'s sixteen seconds here
# would be sixteen seconds of watching a finished page.
BUDGET_MS = 900

# **Not** style.css's `--red` (#c0182b), which og.png uses. That red is drawn for
# the site's near-white paper; over the scrim on a photograph it is a dark colour
# on a dark ground, and on Big Red - whose whole sky is red - the domain line
# nearly vanished. This is the same hue lifted until it reads on every track in
# the pool, including the two pale ones.
RED = "#ff5566"
DOMAIN = "drive.cgovind.com"


def card_html(track):
    """The card for one track. `shot.png` is copied in beside it."""
    pips = "".join(
        '<i class="%s"></i>' % ("on" if i < track["difficulty"] else "")
        for i in range(5))
    return CARD_HTML % {"red": RED, "domain": DOMAIN, "name": track["name"],
                        "pips": pips}


# The photograph is the card and the type sits in a scrim over the foot of it.
# Two things are deliberate. The scrim is a gradient rather than a bar, because
# a hard edge across a photograph reads as a broken image; and it is tall enough
# (55%) that a track shot against a pale sky - Cloudbreak, Sandy Cove - still has
# white type on something dark, which a short scrim does not guarantee.
CARD_HTML = """<!doctype html><meta charset="utf-8">
<style>
@font-face{font-family:"Titillium Web";src:url(titillium-400.woff2);font-weight:400}
@font-face{font-family:"Titillium Web";src:url(titillium-600.woff2);font-weight:600}
@font-face{font-family:"Titillium Web";src:url(titillium-900.woff2);font-weight:900}
html,body{margin:0;padding:0;overflow:hidden;background:#11121a}
body{width:1200px;height:630px;position:relative;
     font-family:"Titillium Web",sans-serif;color:#fff}
.shot{position:absolute;inset:0;background:url(shot.png) center/cover no-repeat}
.scrim{position:absolute;left:0;right:0;bottom:0;height:64%%;
       background:linear-gradient(to bottom,rgba(10,11,16,0) 0%%,
                  rgba(10,11,16,.55) 26%%,rgba(10,11,16,.87) 58%%,
                  rgba(10,11,16,.96) 100%%)}
.txt{position:absolute;left:72px;right:72px;bottom:64px}
/* The eyebrow sits highest in the text block and so over the weakest part of
   the scrim; it needs the heaviest shadow of the three, not the lightest. */
.eyebrow{font-weight:600;font-size:25px;letter-spacing:.16em;text-transform:uppercase;
         color:%(red)s;margin:0 0 10px;
         text-shadow:0 1px 3px rgba(0,0,0,.85),0 2px 16px rgba(0,0,0,.7)}
h1{margin:0;font-weight:900;font-size:104px;line-height:.94;letter-spacing:-.025em;
   text-shadow:0 2px 18px rgba(0,0,0,.55)}
/* The name used to have a one-line description under it and the pips sat on that
   line's last baseline. The description is gone (tracks no longer declare one),
   so the foot is the rating alone - and it stays hard left under the name rather
   than being pushed to the far corner, because with nothing beside it the
   `margin-left:auto` that kept it out of the text's way stranded five small dots
   1100px from the only other thing on the card. */
.foot{display:flex;align-items:center;margin-top:22px}
.pips{display:flex;gap:9px;flex:none}
.pips i{width:17px;height:17px;border-radius:50%%;background:rgba(255,255,255,.28);
        box-shadow:0 1px 6px rgba(0,0,0,.5)}
.pips i.on{background:#fff}
</style>
<div class="shot"></div><div class="scrim"></div>
<div class="txt">
  <div class="eyebrow">%(domain)s</div>
  <h1>%(name)s</h1>
  <div class="foot"><div class="pips">%(pips)s</div></div>
</div>
"""


def _cards(tracks, shooter, work):
    """The loop itself, against a browser somebody else opened."""
    failed = []
    for t in tracks:
        slug = t["slug"]
        src = os.path.join(SHOTS, slug + ".png")
        if not os.path.exists(src):
            print("  %-16s NO PREVIEW - run shoot_tracks.py first" % slug)
            failed.append(slug)
            continue
        shutil.copy(src, os.path.join(work, "shot.png"))
        with open(os.path.join(work, "card.html"), "w") as f:
            f.write(card_html(t))
        out = os.path.join(OUT, slug + ".png")
        size = shooter.shoot("file://" + os.path.join(work, "card.html"), out)
        if size:
            print("  %-16s %6.1f kB" % (slug, size / 1024.0))
        else:
            print("  %-16s FAILED" % slug)
            failed.append(slug)
    return failed


def shoot(tracks):
    """Write a card for each of `tracks` (summary dicts). Returns the failures.

    Opens its own browser rather than borrowing `shoot_tracks.py`'s, even though
    it is called from inside that tool's run. A `Shooter`'s viewport is fixed
    when it is built, so the shared one would render every card at the preview's
    960x540 and still write a file - the silent-wrong-picture failure that tool's
    own docstring is about. A browser launch is about a second.
    """
    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="driveogcard")
    try:
        for weight in ("400", "600", "900"):
            shutil.copy(os.path.join(FONTS, "titillium-%s.woff2" % weight), work)
        with _shots.Shooter(size=SIZE, budget_ms=BUDGET_MS) as shooter:
            return _cards(tracks, shooter, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    if _shots.describe_backend().startswith("NONE"):
        print("no way to take pictures: no Playwright in this venv and no "
              "Chrome on PATH or in /Applications")
        return 1
    sys.path.insert(0, ROOT)
    import tracks as tracks_mod

    wanted = [a for a in argv[1:] if not a.startswith("-")]
    summaries = tracks_mod.summaries()
    unknown = [s for s in wanted if not tracks_mod.get(s)]
    if unknown:
        print("no such track: " + ", ".join(unknown))
        return 1
    if wanted:
        summaries = [t for t in summaries if t["slug"] in wanted]

    print("carding %d track(s) with %s"
          % (len(summaries), _shots.describe_backend()))
    failed = shoot(summaries)
    print("%d/%d written to %s"
          % (len(summaries) - len(failed), len(summaries),
             os.path.relpath(OUT, ROOT)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
