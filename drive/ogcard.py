"""The 1200x630 cards a link unfurls into, drawn on the box with Pillow.

Two of them, both a layout over a picture of the track that is already on disk:

* `track_card` - a daily's (or any community track's) own link. The pool's
  tracks have theirs pre-rendered by `tools/shoot_og_cards.py`; a daily is made
  on the box after any deploy, so its card has to be made there too.
* `lap_card` - a `?watch=<id>` link, for every track: who drove it and the
  time, laid out like a TV timing row.

**Pillow, not a browser**, because the box has none and could not afford one -
the same reason a daily's cover is taken in the reviewer's browser. The type is
the site's own woff2 files, which FreeType reads directly.
"""

import io
import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "static", "fonts")
SIZE = W, H = 1200, 630
DOMAIN = "drive.cgovind.com"
# `shoot_og_cards.RED`, lifted from `--red` so it reads over a photograph.
RED = (255, 85, 102)
KERB = (225, 6, 0)
PURPLE = (139, 47, 201)
INK = (14, 15, 22)


@lru_cache(maxsize=None)
def _font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def _cover(path):
    """The picture, scaled to cover the card and centre-cropped."""
    im = Image.open(path).convert("RGB")
    k = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * k), round(im.height * k)), Image.BILINEAR)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((x, y, x + W, y + H)).convert("RGBA")


def _scrim(card, height, stops):
    """Darken the foot of the card along `stops`: (fraction down, alpha)."""
    top = H - height
    ramp = Image.new("L", (1, height))
    for y in range(height):
        f = y / max(1, height - 1)
        for (f0, a0), (f1, a1) in zip(stops, stops[1:]):
            if f0 <= f <= f1:
                ramp.putpixel((0, y), round(255 * (a0 + (a1 - a0) * (f - f0) / (f1 - f0))))
                break
    shade = Image.new("RGBA", (W, height), (10, 11, 16, 255))
    shade.putalpha(ramp.resize((W, height)))
    card.alpha_composite(shade, (0, top))


def _spaced(draw, xy, text, font, fill, tracking, anchor="ls"):
    """Letter-spaced text, which Pillow has no setting for. Returns its width."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor=anchor)
        x += draw.textlength(ch, font=font) + tracking
    return x - xy[0] - tracking


def _fit(draw, text, name, size, width):
    """The largest size up to `size` at which `text` fits in `width`."""
    while size > 20 and draw.textlength(text, font=_font(name, size)) > width:
        size -= 2
    return _font(name, size)


def _jpeg(card):
    out = io.BytesIO()
    card.convert("RGB").save(out, "JPEG", quality=88)
    return out.getvalue()


def track_card(cover, name, date=None):
    """The domain, the track's name, and the date under it when it has one."""
    card = _cover(cover)
    _scrim(card, round(H * 0.6), [(0, 0), (0.3, 0.6), (1, 0.95)])
    d = ImageDraw.Draw(card)
    base = H - 64
    if date:
        d.text((72, base), date, font=_font("titillium-600.woff2", 32),
               fill=(255, 255, 255, 220), anchor="ls")
        base -= 58
    title = _fit(d, name, "titillium-900.woff2", 110, W - 144)
    d.text((70, base), name, font=title, fill="white", anchor="ls")
    _spaced(d, (72, base - title.size - 6), DOMAIN.upper(),
            _font("titillium-600.woff2", 22), RED, 3.5)
    return _jpeg(card)


def lap_card(cover, who, time, flag=None):
    """A timing row along the foot: flag, driver, and the time on purple."""
    card = _cover(cover)
    _scrim(card, round(H * 0.45), [(0, 0), (1, 0.65)])
    x0, x1, y0, y1 = 60, W - 60, H - 70 - 118, H - 70
    # Blurred on its own patch rather than across the whole card: same result,
    # a fraction of the work.
    m = 60
    shadow = Image.new("RGBA", (x1 - x0 + 2 * m, y1 - y0 + 2 * m), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((m, m, m + x1 - x0, m + y1 - y0), fill=(0, 0, 0, 130))
    card.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(20)), (x0 - m, y0 + 10 - m))

    d = ImageDraw.Draw(card)
    clock = _font("barlow-condensed-800-italic.woff2", 84)
    tw = round(d.textlength(time, font=clock)) + 68
    d.rectangle((x0, y0, x1 - tw, y1), fill=INK + (240,))
    d.rectangle((x0, y0, x0 + 9, y1), fill=KERB)
    d.rectangle((x1 - tw, y0, x1, y1), fill=PURPLE)
    mid = (y0 + y1) // 2
    d.text((x1 - tw + 34, mid), time, font=clock, fill="white", anchor="lm")

    x = x0 + 44
    if flag:
        f = Image.open(flag).convert("RGBA")
        f = f.resize((round(f.width * 44 / f.height), 44), Image.LANCZOS)
        card.alpha_composite(f, (x, mid - 22))
        x += f.width + 22
    who = who.upper()
    d.text((x, mid), who, anchor="lm", fill="white",
           font=_fit(d, who, "titillium-900.woff2", 62, x1 - tw - x - 30))
    right = W - 60
    font = _font("titillium-600.woff2", 22)
    width = sum(d.textlength(c, font=font) + 3.5 for c in DOMAIN.upper()) - 3.5
    _spaced(d, (right - width, H - 28), DOMAIN.upper(), font, RED, 3.5)
    return _jpeg(card)

