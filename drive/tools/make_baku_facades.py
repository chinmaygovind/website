"""Paint Baku's facade textures: one storey of four bays, per style, lit and shaded.

    venv/bin/python tools/make_baku_facades.py

Writes `static/img/art/baku/<style>-<storey>-<light>.png`, 512x128 each, which
`tracks/baku/scenery.js` tiles across every building face the road can see.

**Why a storey and not a building.** A face is tiled floor by floor and bay
group by bay group, so a four-storey block and an eight-storey one use the same
three pictures - ground, middle and top - and nothing is stretched past the
proportion it was drawn at. Eighteen small files instead of one per building.

**Why two of each.** A textured quad here is `MeshBasicMaterial`, unlit, so the
key light cannot shade it: every face would come out at the same brightness and
the city would read as cardboard. So the light is baked in - `lit` is the
sandstone as it looks in the late sun, `shade` is the same wall turned away
from it - and `scenery.js` picks one per face from the palette's own light
direction.

Everything here came off the reference frames (the 2026 pole lap and a street
walk through the same blocks), not from a mental picture of "Baku":

 * honey sandstone ashlar with fine coursing, never render or brick;
 * tall windows, dark glass, cream stone surrounds with a hood or pediment;
 * black wrought-iron balconies on the middle bays;
 * a rusticated ground floor with deep horizontal grooves and arched openings;
 * a heavy cornice under the parapet;
 * enclosed wooden balconies (the old town's *shebeke*-style bays) on the
   older, ochre blocks.
"""
import os
import random

from PIL import Image, ImageDraw, ImageFilter

OUT = "static/img/art/baku"
W, H = 512, 128
SS = 4                      # supersample, then downsample: clean edges

STYLES = {
    # wall, darker joint, surround, glass, frame, accent
    "sand":   dict(wall=(214, 196, 158), joint=(186, 166, 128), sur=(232, 219, 190),
                   glass=(46, 54, 62), frame=(92, 70, 50), iron=(28, 28, 30)),
    "cream":  dict(wall=(226, 214, 186), joint=(200, 186, 156), sur=(240, 232, 212),
                   glass=(52, 62, 72), frame=(236, 232, 222), iron=(30, 30, 32)),
    "ochre":  dict(wall=(204, 178, 132), joint=(176, 150, 106), sur=(222, 204, 166),
                   glass=(42, 48, 52), frame=(70, 88, 64), iron=(26, 26, 28)),
}


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def storey(style, kind, rnd):
    c = STYLES[style]
    w, h = W * SS, H * SS
    im = Image.new("RGB", (w, h), c["wall"])
    d = ImageDraw.Draw(im)
    bw = w // 4
    # ashlar: courses every ~1/9 storey, staggered vertical joints
    course = h // (5 if kind == "g" else 9)
    for k, y in enumerate(range(0, h, course)):
        d.line([(0, y), (w, y)], fill=c["joint"], width=SS * (3 if kind == "g" else 1))
        off = (k % 2) * bw // 4
        for x in range(off, w, bw // 2):
            if kind != "g":
                d.line([(x, y), (x, y + course)], fill=c["joint"], width=SS)
    # per-block tone variation, which is what makes stone read as stone
    for y in range(0, h, course):
        for x in range(0, w, bw // 2):
            t = rnd.uniform(-0.05, 0.05)
            col = tuple(max(0, min(255, int(v * (1 + t)))) for v in c["wall"])
            d.rectangle([x + SS, y + SS, x + bw // 2 - SS, y + course - SS], fill=col)
    for k in range(4):
        cx = k * bw + bw // 2
        if kind == "g":
            # arched opening: shopfront or doorway, deep reveal
            ow, top, ah = int(bw * 0.62), int(h * 0.36), int(h * 0.2)
            d.rectangle([cx - ow // 2 - 3 * SS, top, cx + ow // 2 + 3 * SS, h], fill=c["sur"])
            d.pieslice([cx - ow // 2 - 3 * SS, top - ah - 3 * SS, cx + ow // 2 + 3 * SS, top + ah + 3 * SS],
                       180, 360, fill=c["sur"])
            d.rectangle([cx - ow // 2, top, cx + ow // 2, h], fill=c["glass"])
            d.pieslice([cx - ow // 2, top - ah, cx + ow // 2, top + ah],
                       180, 360, fill=lerp(c["glass"], (90, 110, 130), 0.35))
            # keystone
            d.polygon([(cx - 5 * SS, top - ah - 3 * SS), (cx + 5 * SS, top - ah - 3 * SS),
                       (cx + 3 * SS, top - ah + 9 * SS), (cx - 3 * SS, top - ah + 9 * SS)], fill=c["sur"])
            d.line([(cx, top), (cx, h)], fill=c["frame"], width=2 * SS)
            # plinth
            d.rectangle([0, h - 6 * SS, w, h], fill=lerp(c["joint"], (80, 70, 60), 0.4))
            if style == "sand" and k in (1, 2) and rnd.random() < 0.7:
                aw = rnd.choice([(170, 40, 36), (40, 110, 70)])
                for s in range(6):
                    x0 = cx - ow // 2 - 6 * SS + s * (ow + 12 * SS) // 6
                    d.rectangle([x0, top + 10 * SS, x0 + (ow + 12 * SS) // 6, top + 26 * SS],
                                fill=aw if s % 2 else lerp(aw, (240, 236, 226), 0.8))
        else:
            ww, wt, wb = int(bw * 0.36), int(h * 0.2), int(h * 0.86)
            if kind == "t":
                wt, wb = int(h * 0.36), int(h * 0.9)
            # surround and hood
            d.rectangle([cx - ww // 2 - 5 * SS, wt - 5 * SS, cx + ww // 2 + 5 * SS, wb + 3 * SS], fill=c["sur"])
            if style == "cream":
                d.rectangle([cx - ww // 2 - 9 * SS, wt - 14 * SS, cx + ww // 2 + 9 * SS, wt - 8 * SS], fill=c["sur"])
            else:
                d.polygon([(cx - ww // 2 - 9 * SS, wt - 7 * SS), (cx + ww // 2 + 9 * SS, wt - 7 * SS),
                           (cx, wt - 20 * SS)], fill=c["sur"])
            # glass, reflecting a little sky toward the top
            for y in range(wt, wb):
                t = (y - wt) / max(1, wb - wt)
                d.line([(cx - ww // 2, y), (cx + ww // 2, y)], fill=lerp((96, 116, 138), c["glass"], min(1, t * 1.6)))
            d.rectangle([cx - ww // 2, wt, cx + ww // 2, wb], outline=c["frame"], width=2 * SS)
            d.line([(cx, wt), (cx, wb)], fill=c["frame"], width=2 * SS)
            d.line([(cx - ww // 2, wt + (wb - wt) // 3), (cx + ww // 2, wt + (wb - wt) // 3)],
                   fill=c["frame"], width=2 * SS)
            # sill
            d.rectangle([cx - ww // 2 - 7 * SS, wb, cx + ww // 2 + 7 * SS, wb + 5 * SS], fill=c["sur"])
            if kind == "m" and style == "ochre" and k == 1:
                # enclosed timber balcony: two bays wide, glazed, green-brown
                bx0, bx1 = cx - int(bw * 0.45), cx + int(bw * 1.45)
                d.rectangle([bx0, int(h * 0.12), bx1, h], fill=c["frame"])
                for j in range(8):
                    x0 = bx0 + 4 * SS + j * (bx1 - bx0 - 8 * SS) // 8
                    d.rectangle([x0 + SS, int(h * 0.2), x0 + (bx1 - bx0 - 8 * SS) // 8 - 2 * SS, int(h * 0.62)],
                                fill=lerp(c["glass"], (110, 130, 140), 0.25))
                d.rectangle([bx0, int(h * 0.66), bx1, int(h * 0.7)], fill=lerp(c["frame"], (0, 0, 0), 0.3))
            elif kind == "m" and not (style == "ochre" and k == 2) and (k in (1, 2) or rnd.random() < 0.25):
                # wrought-iron balcony across the bottom of the window
                by = wb - int(h * 0.2)
                d.rectangle([cx - ww // 2 - 12 * SS, wb + 3 * SS, cx + ww // 2 + 12 * SS, wb + 8 * SS],
                            fill=lerp(c["sur"], (0, 0, 0), 0.25))
                d.rectangle([cx - ww // 2 - 12 * SS, by, cx + ww // 2 + 12 * SS, by + 2 * SS], fill=c["iron"])
                for x in range(cx - ww // 2 - 12 * SS, cx + ww // 2 + 12 * SS, 6 * SS):
                    d.line([(x, by), (x, wb + 3 * SS)], fill=c["iron"], width=SS)
                    d.arc([x, by + 4 * SS, x + 6 * SS, by + 12 * SS], 0, 360, fill=c["iron"], width=SS)
        if style == "cream" and kind != "g":
            # pilasters between bays
            for x in (k * bw, (k + 1) * bw):
                d.rectangle([x - 5 * SS, 0, x + 5 * SS, h], fill=lerp(c["sur"], c["wall"], 0.3))
    if kind == "t":
        # cornice: a heavy moulded band with dentils, and its shadow
        d.rectangle([0, 0, w, int(h * 0.2)], fill=c["sur"])
        d.rectangle([0, int(h * 0.2), w, int(h * 0.25)], fill=lerp(c["wall"], (40, 34, 30), 0.55))
        for x in range(0, w, 10 * SS):
            d.rectangle([x, int(h * 0.14), x + 5 * SS, int(h * 0.2)], fill=lerp(c["sur"], (0, 0, 0), 0.2))
    if kind == "g":
        # string course between ground floor and the rest
        d.rectangle([0, 0, w, int(h * 0.07)], fill=c["sur"])
        d.rectangle([0, int(h * 0.07), w, int(h * 0.09)], fill=lerp(c["wall"], (40, 34, 30), 0.5))
    im = im.filter(ImageFilter.GaussianBlur(SS * 0.4)).resize((W, H), Image.LANCZOS)
    return im


def shade(im):
    """The same wall turned away from a low sun: darker, cooler, flatter."""
    px = im.load()
    out = Image.new("RGB", im.size)
    po = out.load()
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r, g, b = px[x, y]
            po[x, y] = (int(r * 0.58 + 8), int(g * 0.60 + 12), int(b * 0.64 + 22))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    for style in STYLES:
        for kind in ("g", "m", "t"):
            rnd = random.Random(hash((style, kind)) & 0xffff)
            lit = storey(style, kind, rnd)
            lit.save(f"{OUT}/{style}-{kind}-lit.png", optimize=True)
            shade(lit).save(f"{OUT}/{style}-{kind}-shade.png", optimize=True)
    print("wrote", len(STYLES) * 6, "files to", OUT)


if __name__ == "__main__":
    main()
