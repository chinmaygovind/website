"""Paint High Roller's textures: felts, cards, slot screens, signs, chips, carpet.

    venv/bin/python tools/make_casino_art.py

Writes `static/img/art/casino/*.png`, which `tracks/casino/scenery.js` lays on
panels through the `signs` list (the only path from scenery to a texture).

Drawn off reference photos of real Las Vegas floors and tables, not from memory:

 * craps: green felt, white rules; the 4 5 SIX 8 NINE 10 row along the back,
   COME in red, FIELD with its numbers in yellow, DON'T PASS BAR, PASS LINE
   running along the front and round the end, BIG 6 / BIG 8 in the corner, the
   proposition box in the middle; the two ends are mirror images;
 * roulette: 0 in green, 1-36 in three rows of twelve on red and black, 2 TO 1
   at the column ends, the dozens, then 1-18 EVEN red black ODD 19-36;
 * blackjack: gold arc lettering, BLACKJACK PAYS 3 TO 2, INSURANCE PAYS 2 TO 1;
 * slots: tall saturated screens with the reels in a window, a lit topper with
   a progressive meter in red LED digits;
 * carpet: busy, dark ground with red, gold and purple swirls - the one thing
   every casino floor shares.

Every panel is `MeshBasicMaterial`, unlit, so these are painted at the value
they should *read* at in a dim room - a pure white card would glare.

**Width is always 512.** `artTexture` draws every file into a 512-wide canvas at
the file's own aspect, so the aspect here is the one scenery.js must pass.
"""
import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "static", "img", "art", "casino")
FONTS = os.path.join(ROOT, "static", "fonts")
SS = 2                                   # supersample, then downsample

FELT = (24, 96, 54)
FELT_LINE = (226, 222, 206)
RED = (196, 26, 36)
BLACK = (22, 22, 26)
GOLD = (226, 184, 82)
YELLOW = (240, 206, 70)
CARD = (222, 216, 202)
CARD_RED = (184, 22, 34)
CARD_INK = (24, 24, 28)


def font(name, px):
    return ImageFont.truetype(os.path.join(FONTS, name + ".woff2"), int(px))


SERIF = "titillium-900"   # Cinzel here is a subset: only the glyphs the site uses
SANS = "titillium-900"
SANS7 = "titillium-700"
COND = "barlow-condensed-800-italic"


def canvas(w, h, bg):
    im = Image.new("RGB", (w * SS, h * SS), bg)
    return im, ImageDraw.Draw(im)


def save(im, name, colors=None):
    im = im.resize((im.width // SS, im.height // SS), Image.LANCZOS)
    if colors:
        im = im.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.NONE)
    os.makedirs(OUT, exist_ok=True)
    im.save(os.path.join(OUT, name + ".png"), optimize=True)


def text(d, xy, s, f, fill, anchor="mm", rot=0, im=None, stroke=0, stroke_fill=None):
    """Text centred on xy; `rot` degrees drawn through a temporary layer."""
    if not rot:
        d.text(xy, s, font=f, fill=fill, anchor=anchor,
               stroke_width=stroke, stroke_fill=stroke_fill)
        return
    l, t, r, b = d.textbbox((0, 0), s, font=f, anchor="lt", stroke_width=stroke)
    w, h = r - l + 8, b - t + 8
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((w / 2, h / 2), s, font=f, fill=fill, anchor="mm",
                               stroke_width=stroke, stroke_fill=stroke_fill)
    layer = layer.rotate(rot, expand=True, resample=Image.BICUBIC)
    im.paste(layer, (int(xy[0] - layer.width / 2), int(xy[1] - layer.height / 2)), layer)


def die_face(d, cx, cy, s, n, body=RED, pip=(240, 236, 226)):
    d.rounded_rectangle([cx - s, cy - s, cx + s, cy + s], radius=s * 0.25, fill=body)
    r = s * 0.17
    spots = {1: [(0, 0)], 2: [(-1, -1), (1, 1)], 3: [(-1, -1), (0, 0), (1, 1)],
             4: [(-1, -1), (1, -1), (-1, 1), (1, 1)],
             5: [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)],
             6: [(-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)]}[n]
    for sx, sy in spots:
        x, y = cx + sx * s * 0.5, cy + sy * s * 0.5
        d.ellipse([x - r, y - r, x + r, y + r], fill=pip)


# --- craps --------------------------------------------------------------------
def craps_half(mirror):
    W, H = 512, 416
    im, d = canvas(W, H, FELT)
    w, h = W * SS, H * SS
    lw = 3 * SS

    def X(u):
        return (1 - u) * w if mirror else u * w

    def box(u0, v0, u1, v1, fill=None, width=lw):
        xa, xb = sorted((X(u0), X(u1)))
        d.rectangle([xa, v0 * h, xb, v1 * h], outline=FELT_LINE, width=width, fill=fill)

    # Outer rule, inset from the rail.
    box(0.025, 0.04, 1.02, 0.96)
    # Place numbers along the back.
    nums = ["4", "5", "SIX", "8", "NINE", "10"]
    order = nums if not mirror else nums[::-1]
    u0, u1 = 0.21, 0.79
    cw = (u1 - u0) / 6
    for i, s in enumerate(order):
        a = u0 + cw * i
        box(a, 0.06, a + cw, 0.27)
        f = font(SANS, h * (0.1 if len(s) < 3 else 0.052))
        text(d, ((X(a) + X(a + cw)) / 2, 0.17 * h), s, f, YELLOW if s in ("SIX", "NINE") else FELT_LINE)
        text(d, ((X(a) + X(a + cw)) / 2, 0.245 * h), "PLACE TO WIN", font(SANS7, h * 0.016), FELT_LINE)
    # Don't come bar, in the back corner.
    box(0.05, 0.06, 0.21, 0.27)
    text(d, ((X(0.05) + X(0.21)) / 2, 0.135 * h), "DON'T COME", font(SANS7, h * 0.026), FELT_LINE)
    text(d, ((X(0.05) + X(0.21)) / 2, 0.18 * h), "BAR", font(SANS7, h * 0.034), FELT_LINE)
    die_face(d, (X(0.05) + X(0.21)) / 2, 0.235 * h, h * 0.025, 6)
    # COME.
    box(0.21, 0.27, 0.79, 0.50)
    text(d, ((X(0.21) + X(0.79)) / 2, 0.385 * h), "COME", font(SERIF, h * 0.15), RED,
         stroke=SS * 2, stroke_fill=(250, 236, 214))
    # FIELD.
    box(0.16, 0.50, 0.79, 0.69)
    fx = [0.22, 0.30, 0.38, 0.46, 0.56, 0.64, 0.72]
    fnums = ["2", "3", "4", "9", "10", "11", "12"]
    if mirror:
        fnums = fnums[::-1]
    for u, s in zip(fx, fnums):
        x = X(u + 0.02)
        if s in ("2", "12"):
            rr = h * 0.042
            d.ellipse([x - rr, 0.555 * h - rr, x + rr, 0.555 * h + rr], outline=YELLOW, width=lw)
        text(d, (x, 0.555 * h), s, font(SANS, h * 0.055), YELLOW)
    text(d, ((X(0.16) + X(0.79)) / 2, 0.635 * h), "FIELD", font(SERIF, h * 0.075), FELT_LINE)
    text(d, (X(0.30), 0.635 * h), "PAYS DOUBLE", font(SANS7, h * 0.026), YELLOW)
    text(d, (X(0.66), 0.635 * h), "PAYS TRIPLE", font(SANS7, h * 0.026), YELLOW)
    # Don't pass bar.
    box(0.16, 0.69, 0.79, 0.79)
    text(d, ((X(0.16) + X(0.79)) / 2, 0.74 * h), "DON'T PASS BAR", font(SANS, h * 0.052), FELT_LINE)
    die_face(d, X(0.70), 0.74 * h, h * 0.028, 6)
    die_face(d, X(0.74), 0.74 * h, h * 0.028, 6)
    # PASS LINE, along the front and up the end.
    box(0.025, 0.79, 0.79, 0.94)
    text(d, ((X(0.025) + X(0.79)) / 2, 0.865 * h), "PASS  LINE", font(SERIF, h * 0.085), FELT_LINE)
    box(0.025, 0.27, 0.085, 0.79)
    text(d, ((X(0.025) + X(0.085)) / 2, 0.53 * h), "PASS LINE", font(SERIF, h * 0.045),
         FELT_LINE, rot=90 if not mirror else -90, im=im)
    # BIG 6 / BIG 8 in the corner between the pass line and the field.
    box(0.085, 0.50, 0.16, 0.79)
    for v, s in [(0.585, "6"), (0.705, "8")]:
        cx, cy, rr = (X(0.085) + X(0.16)) / 2, v * h, h * 0.05
        d.polygon([(cx, cy - rr), (cx + rr, cy), (cx, cy + rr), (cx - rr, cy)], fill=RED,
                  outline=FELT_LINE)
        text(d, (cx, cy), s, font(SANS, h * 0.06), (250, 240, 220))
    # The proposition box, half of it, against the middle.
    box(0.79, 0.06, 1.02, 0.94, fill=(20, 84, 48))
    text(d, ((X(0.79) + X(1.0)) / 2, 0.11 * h), "SEVEN" if not mirror else "ANY CRAPS",
         font(SANS, h * 0.042), RED)
    text(d, ((X(0.79) + X(1.0)) / 2, 0.155 * h), "4 TO 1" if not mirror else "7 TO 1",
         font(SANS7, h * 0.03), FELT_LINE)
    pairs = [(3, 3), (5, 5), (2, 2), (4, 4)] if not mirror else [(1, 2), (6, 6), (1, 1), (5, 6)]
    for i, (a, b2) in enumerate(pairs):
        col, row = i % 2, i // 2
        cx = X(0.83 + col * 0.09)
        cy = (0.25 + row * 0.2) * h
        die_face(d, cx - h * 0.028, cy, h * 0.021, a)
        die_face(d, cx + h * 0.028, cy, h * 0.021, b2)
        text(d, (cx, cy + h * 0.065), "9 TO 1" if not mirror else "30 TO 1",
             font(SANS7, h * 0.024), FELT_LINE)
    text(d, ((X(0.79) + X(1.0)) / 2, 0.70 * h), "HARDWAYS" if not mirror else "HORN",
         font(SANS7, h * 0.034), YELLOW)
    text(d, ((X(0.79) + X(1.0)) / 2, 0.84 * h), "C  E", font(SERIF, h * 0.07), RED)
    save(im, "craps-" + ("r" if mirror else "l"), colors=48)


# --- roulette -------------------------------------------------------------------
REDS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


def roulette_layout():
    W, H = 512, 205
    im, d = canvas(W, H, FELT)
    w, h = W * SS, H * SS
    lw = 2 * SS
    x0, x1 = 0.10 * w, 0.90 * w
    y0, y1 = 0.06 * h, 0.58 * h
    cw, ch = (x1 - x0) / 12, (y1 - y0) / 3
    # 0, tall, on the left.
    d.polygon([(0.03 * w, (y0 + y1) / 2), (x0, y0), (x0, y1)], fill=(18, 120, 60), outline=FELT_LINE)
    text(d, (0.075 * w, (y0 + y1) / 2), "0", font(SANS, h * 0.13), (240, 236, 226))
    for c in range(12):
        for r in range(3):
            n = c * 3 + (3 - r)
            xa, ya = x0 + c * cw, y0 + r * ch
            d.rectangle([xa, ya, xa + cw, ya + ch], fill=RED if n in REDS else BLACK,
                        outline=FELT_LINE, width=lw)
            text(d, (xa + cw / 2, ya + ch / 2), str(n), font(SANS, ch * 0.55), (240, 236, 226))
    for r in range(3):
        ya = y0 + r * ch
        d.rectangle([x1, ya, x1 + cw * 0.95, ya + ch], outline=FELT_LINE, width=lw)
        text(d, (x1 + cw * 0.47, ya + ch / 2), "2 TO 1", font(SANS7, ch * 0.24), FELT_LINE)
    dz = ["1st 12", "2nd 12", "3rd 12"]
    for i, s in enumerate(dz):
        xa = x0 + i * 4 * cw
        d.rectangle([xa, y1, xa + 4 * cw, y1 + 0.2 * h], outline=FELT_LINE, width=lw)
        text(d, (xa + 2 * cw, y1 + 0.1 * h), s, font(SERIF, h * 0.09), FELT_LINE)
    bottom = ["1-18", "EVEN", "R", "B", "ODD", "19-36"]
    for i, s in enumerate(bottom):
        xa = x0 + i * 2 * cw
        ya = y1 + 0.2 * h
        d.rectangle([xa, ya, xa + 2 * cw, ya + 0.18 * h], outline=FELT_LINE, width=lw)
        cx, cy = xa + cw, ya + 0.09 * h
        if s in ("R", "B"):
            rr = 0.065 * h
            d.polygon([(cx, cy - rr), (cx + rr * 1.6, cy), (cx, cy + rr), (cx - rr * 1.6, cy)],
                      fill=RED if s == "R" else BLACK, outline=FELT_LINE)
        else:
            text(d, (cx, cy), s, font(SERIF, h * 0.08), FELT_LINE)
    save(im, "roulette-layout", colors=48)


# --- cards: drawn whole, then cut into strips that follow the bent ramp ----------
def spade(d, cx, cy, s, fill):
    r = s * 0.32
    d.ellipse([cx - s * 0.62, cy - r * 0.2, cx - s * 0.62 + 2 * r * 1.05, cy + r * 1.9], fill=fill)
    d.ellipse([cx + s * 0.62 - 2 * r * 1.05, cy - r * 0.2, cx + s * 0.62, cy + r * 1.9], fill=fill)
    d.polygon([(cx, cy - s * 0.78), (cx + s * 0.6, cy + s * 0.12), (cx - s * 0.6, cy + s * 0.12)], fill=fill)
    d.polygon([(cx - s * 0.05, cy + s * 0.25), (cx + s * 0.05, cy + s * 0.25),
               (cx + s * 0.3, cy + s * 0.75), (cx - s * 0.3, cy + s * 0.75)], fill=fill)


def heart(d, cx, cy, s, fill):
    r = s * 0.33
    d.ellipse([cx - s * 0.64, cy - s * 0.55, cx - s * 0.64 + 2 * r * 1.02, cy - s * 0.55 + 2 * r], fill=fill)
    d.ellipse([cx + s * 0.64 - 2 * r * 1.02, cy - s * 0.55, cx + s * 0.64, cy - s * 0.55 + 2 * r], fill=fill)
    d.polygon([(cx - s * 0.62, cy - s * 0.18), (cx + s * 0.62, cy - s * 0.18), (cx, cy + s * 0.68)], fill=fill)


def card_index(im, d, w, h, rank, suit, ink):
    for flip in (False, True):
        layer = Image.new("RGB", (int(w * 0.2), int(h * 0.2)), CARD)
        ld = ImageDraw.Draw(layer)
        text(ld, (layer.width / 2, layer.height * 0.32), rank, font(SERIF, h * 0.085), ink)
        (spade if suit == "s" else heart)(ld, layer.width / 2, layer.height * 0.72, h * 0.04, ink)
        if flip:
            layer = layer.rotate(180)
            im.paste(layer, (int(w * 0.8) - 22 * SS, int(h * 0.8) - 22 * SS))
        else:
            im.paste(layer, (22 * SS, 22 * SS))


def card(rank, suit):
    W, H = 512, 716
    im, d = canvas(W, H, CARD)
    w, h = W * SS, H * SS
    ink = CARD_INK if suit == "s" else CARD_RED
    card_index(im, d, w, h, rank, suit, ink)
    d.rounded_rectangle([0.035 * w, 0.025 * h, 0.965 * w, 0.975 * h], radius=0.04 * w,
                        outline=(176, 168, 150), width=2 * SS)
    if rank == "A":
        # The ace of spades' ornate centre: the big pip in a scrolled ring.
        cx, cy = w / 2, h / 2
        for rr, col in [(0.34, (196, 184, 150)), (0.33, CARD)]:
            d.ellipse([cx - rr * w, cy - rr * w, cx + rr * w, cy + rr * w], fill=col)
        for k in range(24):
            a = k / 24 * math.pi * 2
            x, y = cx + math.cos(a) * 0.3 * w, cy + math.sin(a) * 0.3 * w
            d.ellipse([x - 0.012 * w, y - 0.012 * w, x + 0.012 * w, y + 0.012 * w], fill=(150, 130, 90))
        spade(d, cx, cy - 0.01 * h, 0.3 * w, ink)
        text(d, (cx, cy + 0.27 * h), "HIGH ROLLER", font(SERIF, h * 0.032), (120, 100, 60))
    else:
        # A court card, double-headed like the real thing: draw the top half
        # and turn it round for the bottom. The traditional queen of hearts:
        # crown, a ruff, robes in blocks of red, blue and gold with their own
        # patterns, and the flower she holds.
        fw, fh = 0.66 * w, 0.72 * h
        half = Image.new("RGB", (int(fw), int(fh / 2)), CARD)
        hd = ImageDraw.Draw(half)
        W2, H2 = half.width, half.height
        BLUE, GOLDC, RED2, SKIN = (34, 64, 150), (226, 184, 70), CARD_RED, (238, 206, 176)
        LW = max(1, SS)
        # Robe blocks first, from the shoulders down to the waist (the cut line).
        robe = [(0.05 * W2, H2), (0.12 * W2, 0.66 * H2), (0.5 * W2, 0.56 * H2), (0.88 * W2, 0.66 * H2), (0.95 * W2, H2)]
        hd.polygon(robe, fill=BLUE, outline=CARD_INK)
        hd.polygon([(0.2 * W2, H2), (0.3 * W2, 0.66 * H2), (0.5 * W2, 0.6 * H2), (0.7 * W2, 0.66 * H2), (0.8 * W2, H2)],
                   fill=RED2, outline=CARD_INK)
        for k in range(9):                        # gold stripes on the red
            y = 0.68 * H2 + k * 0.036 * H2
            hd.line([(0.27 * W2 + k * 0.004 * W2, y), (0.73 * W2 - k * 0.004 * W2, y)], fill=GOLDC, width=2 * LW)
        for k in range(14):                       # dots on the blue
            x = 0.1 * W2 + (k % 7) * 0.035 * W2 + (0.7 * W2 if k >= 7 else 0)
            y = 0.74 * H2 + (k % 3) * 0.08 * H2
            hd.ellipse([x - 3 * LW, y - 3 * LW, x + 3 * LW, y + 3 * LW], fill=GOLDC)
        hd.polygon([(0.44 * W2, 0.6 * H2), (0.5 * W2, 0.98 * H2), (0.56 * W2, 0.6 * H2)], fill=GOLDC, outline=CARD_INK)
        for k in range(6):                        # crosshatch on the gold panel
            y = 0.64 * H2 + k * 0.055 * H2
            hd.line([(0.46 * W2, y), (0.54 * W2, y + 0.03 * H2)], fill=RED2, width=LW)
        # The ruff: a scalloped white collar.
        for k in range(11):
            x = 0.26 * W2 + k * 0.048 * W2
            hd.ellipse([x - 0.035 * W2, 0.53 * H2, x + 0.035 * W2, 0.61 * H2], fill=(246, 242, 232), outline=CARD_INK)
        # Hair, face, features.
        hd.ellipse([0.33 * W2, 0.15 * H2, 0.67 * W2, 0.56 * H2], fill=(110, 52, 26), outline=CARD_INK)
        hd.ellipse([0.39 * W2, 0.22 * H2, 0.61 * W2, 0.53 * H2], fill=SKIN, outline=CARD_INK)
        for ex in (0.45, 0.55):
            hd.arc([ex * W2 - 0.03 * W2, 0.32 * H2, ex * W2 + 0.03 * W2, 0.35 * H2], 200, 340, fill=CARD_INK, width=LW * 2)
            hd.ellipse([ex * W2 - 0.012 * W2, 0.34 * H2, ex * W2 + 0.012 * W2, 0.37 * H2], fill=(40, 60, 120))
        hd.line([(0.5 * W2, 0.36 * H2), (0.49 * W2, 0.42 * H2), (0.505 * W2, 0.43 * H2)], fill=(170, 120, 100), width=LW)
        hd.ellipse([0.425 * W2, 0.41 * H2, 0.455 * W2, 0.44 * H2], fill=(236, 160, 150))
        hd.ellipse([0.545 * W2, 0.41 * H2, 0.575 * W2, 0.44 * H2], fill=(236, 160, 150))
        hd.chord([0.47 * W2, 0.44 * H2, 0.53 * W2, 0.48 * H2], 0, 180, fill=RED2)
        # Hair falling to the shoulders either side.
        for s2 in (-1, 1):
            x = 0.5 * W2 + s2 * 0.15 * W2
            hd.polygon([(x - 0.04 * W2, 0.3 * H2), (x + 0.04 * W2, 0.3 * H2), (x + s2 * 0.04 * W2, 0.6 * H2),
                        (x - s2 * 0.02 * W2, 0.6 * H2)], fill=(110, 52, 26), outline=CARD_INK)
        # Crown: gold band and points with jewels.
        hd.rectangle([0.37 * W2, 0.17 * H2, 0.63 * W2, 0.22 * H2], fill=GOLDC, outline=CARD_INK)
        pts = [(0.37 * W2, 0.17 * H2)]
        for k in range(5):
            x = 0.37 * W2 + (k + 0.5) * 0.052 * W2
            pts += [(x, 0.03 * H2 if k % 2 == 0 else 0.08 * H2), (0.37 * W2 + (k + 1) * 0.052 * W2, 0.17 * H2)]
        hd.polygon(pts, fill=GOLDC, outline=CARD_INK)
        for k, jc in enumerate([RED2, BLUE, RED2, BLUE, RED2]):
            x = 0.37 * W2 + (k + 0.5) * 0.052 * W2
            hd.ellipse([x - 0.012 * W2, 0.185 * H2, x + 0.012 * W2, 0.205 * H2], fill=jc)
        # The flower in her hand: a red rose on a green stem across the robe.
        hd.line([(0.2 * W2, 0.98 * H2), (0.3 * W2, 0.7 * H2)], fill=(40, 120, 50), width=3 * LW)
        hd.polygon([(0.24 * W2, 0.86 * H2), (0.18 * W2, 0.82 * H2), (0.25 * W2, 0.8 * H2)], fill=(40, 120, 50))
        for rr, cc in [(0.055, RED2), (0.035, (220, 60, 70)), (0.015, RED2)]:
            hd.ellipse([0.3 * W2 - rr * W2, 0.68 * H2 - rr * W2, 0.3 * W2 + rr * W2, 0.68 * H2 + rr * W2], fill=cc, outline=CARD_INK)
        # The suit and a heart brooch.
        heart(hd, 0.12 * W2, 0.14 * H2, 0.08 * W2, ink)
        heart(hd, 0.5 * W2, 0.9 * H2, 0.03 * W2, GOLDC)
        x0, y0 = int((w - fw) / 2), int((h - fh) / 2)
        im.paste(half, (x0, y0))
        im.paste(half.rotate(180), (x0, y0 + H2))
        d.line([(x0 + fw * 0.02, y0 + H2), (x0 + fw * 0.98, y0 + H2)], fill=(176, 150, 70), width=2 * SS)
        d.rectangle([x0, y0, x0 + fw, y0 + fh], outline=(176, 150, 70), width=4 * SS)
        d.rectangle([x0 + 6 * SS, y0 + 6 * SS, x0 + fw - 6 * SS, y0 + fh - 6 * SS], outline=(176, 150, 70), width=SS)
    return im


def card_strips(rank, suit, name, n):
    """Cut a card into `n` strips, bottom strip first: scenery.js lays strip 0
    at the foot of the ramp. Each strip is 512 wide at aspect 512/(716/n)."""
    im = card(rank, suit)
    h = im.height
    for k in range(n):
        top = h - (k + 1) * h // n
        bot = h - k * h // n
        save(im.crop((0, top, im.width, bot)), "%s-%02d" % (name, k), colors=32)


# --- slots ----------------------------------------------------------------------------
GAMES = [
    ("LUCKY 777", (40, 10, 70), (255, 70, 160), ["7", "7", "BAR", "7", "CH", "7", "BAR", "7", "7"]),
    ("DIAMOND DELUXE", (8, 30, 80), (90, 200, 255), ["DI", "BAR", "DI", "7", "DI", "BEL", "DI", "BAR", "DI"]),
    ("WILD CHERRY", (70, 8, 12), (255, 90, 60), ["CH", "CH", "7", "BEL", "CH", "BAR", "CH", "7", "CH"]),
    ("GOLD RUSH", (50, 30, 6), (255, 200, 60), ["BAR", "BEL", "BAR", "7", "BAR", "BEL", "BAR", "BAR", "7"]),
    ("DRAGON FORTUNE", (10, 50, 30), (90, 255, 140), ["BEL", "7", "DI", "BEL", "BEL", "BEL", "DI", "7", "BEL"]),
    ("TRIPLE STARS", (20, 14, 60), (190, 120, 255), ["ST", "7", "ST", "BAR", "ST", "BAR", "ST", "7", "ST"]),
]


def symbol(d, cx, cy, s, kind):
    if kind == "7":
        text(d, (cx, cy), "7", font(SANS, s * 1.9), (210, 20, 30), stroke=SS * 2, stroke_fill=(250, 210, 60))
    elif kind == "BAR":
        d.rounded_rectangle([cx - s * 0.85, cy - s * 0.42, cx + s * 0.85, cy + s * 0.42], radius=s * 0.15,
                            fill=(20, 20, 24))
        text(d, (cx, cy), "BAR", font(SANS, s * 0.62), (245, 240, 230))
    elif kind == "CH":
        for dx in (-0.35, 0.35):
            d.ellipse([cx + dx * s - s * 0.36, cy, cx + dx * s + s * 0.36, cy + s * 0.72], fill=(200, 16, 30))
        d.line([(cx - 0.35 * s, cy), (cx + 0.1 * s, cy - 0.7 * s), (cx + 0.35 * s, cy)],
               fill=(40, 130, 40), width=int(s * 0.12))
    elif kind == "BEL":
        d.pieslice([cx - s * 0.7, cy - s * 0.8, cx + s * 0.7, cy + s * 0.9], 180, 360, fill=(245, 196, 40))
        d.rectangle([cx - s * 0.7, cy + 0.05 * s, cx + s * 0.7, cy + s * 0.35], fill=(245, 196, 40))
        d.ellipse([cx - s * 0.15, cy + 0.3 * s, cx + s * 0.15, cy + 0.6 * s], fill=(200, 140, 20))
    elif kind == "DI":
        d.polygon([(cx, cy - s * 0.8), (cx + s * 0.7, cy - s * 0.2), (cx, cy + s * 0.85),
                   (cx - s * 0.7, cy - s * 0.2)], fill=(80, 190, 250), outline=(220, 245, 255))
        d.line([(cx - s * 0.7, cy - s * 0.2), (cx + s * 0.7, cy - s * 0.2)], fill=(220, 245, 255), width=SS)
    elif kind == "ST":
        pts = []
        for k in range(10):
            a = -math.pi / 2 + k * math.pi / 5
            r = s * (0.85 if k % 2 == 0 else 0.36)
            pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
        d.polygon(pts, fill=(250, 210, 50))


def slot_screen(i):
    title, bg, glow, syms = GAMES[i]
    W, H = 512, 683
    im, d = canvas(W, H, bg)
    w, h = W * SS, H * SS
    for k in range(40):   # a radial burst behind everything
        a = k / 40 * math.pi * 2
        col = tuple(min(255, int(bg[j] * 1.6 + 12)) for j in range(3)) if k % 2 else bg
        d.polygon([(w / 2, h * 0.45), (w / 2 + math.cos(a) * w * 2, h * 0.45 + math.sin(a) * w * 2),
                   (w / 2 + math.cos(a + 0.16) * w * 2, h * 0.45 + math.sin(a + 0.16) * w * 2)], fill=col)
    text(d, (w / 2, 0.11 * h), title, font(COND, h * 0.085), glow, stroke=SS * 3, stroke_fill=(20, 10, 10))
    rx0, rx1, ry0, ry1 = 0.07 * w, 0.93 * w, 0.22 * h, 0.72 * h
    d.rounded_rectangle([rx0 - 8 * SS, ry0 - 8 * SS, rx1 + 8 * SS, ry1 + 8 * SS], radius=10 * SS,
                        fill=(214, 170, 60))
    rw = (rx1 - rx0) / 3
    for c in range(3):
        d.rectangle([rx0 + c * rw + 2 * SS, ry0, rx0 + (c + 1) * rw - 2 * SS, ry1], fill=(236, 232, 222))
        for r in range(3):
            symbol(d, rx0 + c * rw + rw / 2, ry0 + (r + 0.5) * (ry1 - ry0) / 3, rw * 0.3, syms[r * 3 + c])
    d.line([(rx0, (ry0 + ry1) / 2), (rx1, (ry0 + ry1) / 2)], fill=(230, 30, 40), width=3 * SS)
    d.rectangle([0, 0.78 * h, w, h], fill=(10, 10, 14))
    for k, (lab, val) in enumerate([("CREDIT", "2,500"), ("BET", "5"), ("WIN", "1,000")]):
        x = (k + 0.5) * w / 3
        text(d, (x, 0.83 * h), lab, font(SANS7, h * 0.03), (200, 200, 200))
        text(d, (x, 0.89 * h), val, font(SANS, h * 0.05), (250, 214, 70))
    text(d, (w / 2, 0.96 * h), "PLAY 5 LINES", font(SANS7, h * 0.03), glow)
    save(im, "slot-%d" % i, colors=64)


def topper(i):
    title, bg, glow, _ = GAMES[i]
    W, H = 512, 170
    im, d = canvas(W, H, (14, 10, 16))
    w, h = W * SS, H * SS
    d.rounded_rectangle([4 * SS, 4 * SS, w - 4 * SS, h - 4 * SS], radius=18 * SS, fill=bg,
                        outline=glow, width=5 * SS)
    for k in range(28):
        x = (k + 0.5) / 28 * w
        for y in (9 * SS, h - 9 * SS):
            d.ellipse([x - 4 * SS, y - 4 * SS, x + 4 * SS, y + 4 * SS], fill=(255, 236, 170))
    text(d, (w / 2, 0.36 * h), title, font(COND, h * 0.3), glow, stroke=SS * 3, stroke_fill=(10, 6, 6))
    d.rectangle([0.2 * w, 0.58 * h, 0.8 * w, 0.84 * h], fill=(8, 4, 4))
    rnd = random.Random(i)
    jack = "$%s,%03d.%02d" % (format(rnd.randint(120, 2400), ","), rnd.randint(0, 999), rnd.randint(0, 99))
    text(d, (w / 2, 0.71 * h), jack, font(SANS, h * 0.22), (255, 50, 40))
    save(im, "topper-%d" % i, colors=48)


# --- signs ------------------------------------------------------------------------------
def neon(name, s, col, w=512, h=128, bulbs=False, sub=None):
    im, d = canvas(w, h, (12, 6, 10))
    W, H = w * SS, h * SS
    d.rounded_rectangle([3 * SS, 3 * SS, W - 3 * SS, H - 3 * SS], radius=14 * SS, fill=(26, 8, 14),
                        outline=GOLD, width=4 * SS)
    if bulbs:
        n = int(w / 18)
        for k in range(n):
            x = (k + 0.5) / n * W
            for y in (10 * SS, H - 10 * SS):
                d.ellipse([x - 4 * SS, y - 4 * SS, x + 4 * SS, y + 4 * SS], fill=(255, 238, 180))
    glow = Image.new("RGB", im.size, (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    f = font(SERIF, H * (0.5 if not sub else 0.42))
    y = H * (0.5 if not sub else 0.4)
    text(gd, (W / 2, y), s, f, col)
    glow = glow.filter(ImageFilter.GaussianBlur(10 * SS))
    im = ImageChops.add(im, glow)
    d = ImageDraw.Draw(im)
    text(d, (W / 2, y), s, f, (255, 246, 230), stroke=SS * 2, stroke_fill=col)
    if sub:
        text(d, (W / 2, H * 0.78), sub, font(SANS7, H * 0.16), GOLD)
    save(im, name, colors=64)


# --- chips --------------------------------------------------------------------------------
CHIPS = [("5", (176, 20, 32)), ("25", (24, 110, 56)), ("100", (22, 22, 26)),
         ("500", (96, 40, 130)), ("1K", (214, 170, 40))]


def chip_face(i):
    val, col = CHIPS[i]
    W = 512
    im, d = canvas(W, W, col)
    w = W * SS
    c = w / 2
    # The panel is the square inscribed in the chip's top, so the edge spots
    # (which sit on the rim, outside it) are geometry in scenery.js; this is
    # the inlay: a white ring, the value, a gold rule.
    d.ellipse([c - w * 0.36, c - w * 0.36, c + w * 0.36, c + w * 0.36], fill=(236, 232, 222))
    d.ellipse([c - w * 0.33, c - w * 0.33, c + w * 0.33, c + w * 0.33], fill=col)
    d.ellipse([c - w * 0.3, c - w * 0.3, c + w * 0.3, c + w * 0.3], outline=GOLD, width=3 * SS)
    ink = (236, 232, 222) if i != 4 else (30, 24, 10)
    text(d, (c, c - w * 0.02), "$" + val, font(SANS, w * 0.2), ink)
    text(d, (c, c + w * 0.17), "HIGH ROLLER", font(SERIF, w * 0.045), GOLD if i != 4 else (90, 60, 10))
    save(im, "chip-%d" % i, colors=32)


# --- carpet and wall ----------------------------------------------------------------------
def carpet():
    """Seamless: every motif is drawn at its position and at the eight wraps."""
    W = 512
    im, d = canvas(W, W, (34, 10, 30))
    w = W * SS
    rnd = random.Random(7)

    def wrap(fn):
        for ox in (-w, 0, w):
            for oy in (-w, 0, w):
                fn(ox, oy)

    # Ground swirls.
    for _ in range(26):
        x, y, r = rnd.uniform(0, w), rnd.uniform(0, w), rnd.uniform(0.06, 0.14) * w
        a0 = rnd.uniform(0, 360)
        col = rnd.choice([(110, 22, 40), (76, 26, 96), (130, 50, 30)])
        wrap(lambda ox, oy: d.arc([x + ox - r, y + oy - r, x + ox + r, y + oy + r], a0, a0 + 230,
                                  fill=col, width=int(0.018 * w)))
    # Gold medallions on a grid, with a petal ring.
    for gx in range(2):
        for gy in range(2):
            x, y = (gx + 0.5) * w / 2 + (w / 4 if gy % 2 else 0), (gy + 0.5) * w / 2
            def flower(ox, oy, x=x, y=y):
                for k in range(8):
                    a = k / 8 * math.pi * 2
                    px, py = x + ox + math.cos(a) * 0.07 * w, y + oy + math.sin(a) * 0.07 * w
                    d.ellipse([px - 0.04 * w, py - 0.04 * w, px + 0.04 * w, py + 0.04 * w], fill=(170, 120, 40))
                d.ellipse([x + ox - 0.05 * w, y + oy - 0.05 * w, x + ox + 0.05 * w, y + oy + 0.05 * w],
                          fill=(150, 24, 40))
                d.ellipse([x + ox - 0.02 * w, y + oy - 0.02 * w, x + ox + 0.02 * w, y + oy + 0.02 * w],
                          fill=(220, 170, 70))
            wrap(flower)
    # Confetti of small stars and dots.
    for _ in range(120):
        x, y, r = rnd.uniform(0, w), rnd.uniform(0, w), rnd.uniform(0.004, 0.01) * w
        col = rnd.choice([(200, 150, 50), (40, 110, 150), (160, 40, 60), (110, 60, 150)])
        wrap(lambda ox, oy: d.ellipse([x + ox - r, y + oy - r, x + ox + r, y + oy + r], fill=col))
    save(im, "carpet", colors=32)


def wallpaper():
    W = 512
    im, d = canvas(W, W, (70, 14, 22))
    w = W * SS
    for gx in range(3):
        for gy in range(3):
            cx, cy = gx * w / 2, gy * w / 2
            if (gx + gy) % 2:
                continue
            for k in range(8):
                a = k / 8 * math.pi * 2
                d.ellipse([cx + math.cos(a) * 0.12 * w - 0.06 * w, cy + math.sin(a) * 0.12 * w - 0.03 * w,
                           cx + math.cos(a) * 0.12 * w + 0.06 * w, cy + math.sin(a) * 0.12 * w + 0.03 * w],
                          fill=(96, 26, 34))
            d.ellipse([cx - 0.07 * w, cy - 0.07 * w, cx + 0.07 * w, cy + 0.07 * w], fill=(120, 80, 40))
            d.ellipse([cx - 0.04 * w, cy - 0.04 * w, cx + 0.04 * w, cy + 0.04 * w], fill=(86, 20, 28))
    for gx in range(2):
        for gy in range(2):
            cx, cy = (gx + 0.5) * w / 2, (gy + 0.5) * w / 2
            d.polygon([(cx, cy - 0.1 * w), (cx + 0.05 * w, cy), (cx, cy + 0.1 * w), (cx - 0.05 * w, cy)],
                      fill=(104, 30, 38))
    save(im, "wall", colors=16)


# --- blackjack lettering ----------------------------------------------------------------------
def felt_words(name, s, col, w=512, h=96, f=SERIF, scale=0.62):
    im, d = canvas(w, h, FELT)
    text(d, (w * SS / 2, h * SS / 2), s, font(f, h * SS * scale), col)
    save(im, name, colors=16)


def main():
    craps_half(False)
    craps_half(True)
    roulette_layout()
    card_strips("A", "s", "ace", 12)
    card_strips("Q", "h", "queen", 10)
    for i in range(len(GAMES)):
        slot_screen(i)
        topper(i)
    for i in range(len(CHIPS)):
        chip_face(i)
    carpet()
    wallpaper()
    neon("sign-high-roller", "HIGH ROLLER", (255, 60, 120), w=512, h=128, bulbs=True, sub="CASINO")
    neon("sign-craps", "CRAPS", (60, 220, 255))
    neon("sign-roulette", "ROULETTE", (255, 70, 60))
    neon("sign-blackjack", "BLACKJACK", (255, 200, 60))
    neon("sign-slots", "SLOTS", (120, 255, 120))
    neon("sign-cashier", "CASHIER", (255, 230, 180))
    neon("sign-jackpot", "JACKPOT", (255, 210, 40), bulbs=True, sub="777")
    felt_words("bj-pays", "BLACKJACK PAYS 3 TO 2", GOLD, h=64)
    felt_words("bj-insurance", "INSURANCE PAYS 2 TO 1", GOLD, h=64)
    felt_words("bj-dealer", "Dealer must draw to 16 and stand on all 17s", (226, 222, 206), h=48,
               f=SANS7, scale=0.5)
    felt_words("bj-limit", "$25 MIN   $5,000 MAX", (226, 222, 206), h=64, f=SANS, scale=0.6)
    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT))
    print("%d files, %.0f kB in %s" % (len(os.listdir(OUT)), total / 1024, os.path.relpath(OUT, ROOT)))


if __name__ == "__main__":
    main()
