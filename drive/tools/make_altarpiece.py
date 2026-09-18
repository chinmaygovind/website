"""Glaze the altarpiece for BOO!, using a photograph as a reference.

The brief went round four times and the last round settled it: **a stained glass
window, not a filtered photograph.** The first pass abstracted a picture until
nothing survived, the second painted it as an oil panel, the third cut it into
panes fine enough that the sitter was still legible - "i dont want people to
actually see her" - and this one uses the photograph the way a cartoon is used
in a glazier's shop. It is blurred until only the masses are left, those masses
are cut into four bands, and every pane in a band is one flat colour from a
jewel palette with fat black came round it. A pane is wider than an eye socket,
there is no painted detail on any of them, and what is left is a figure, a halo
and a border - a window that is *of* somebody rather than a picture of them.

Two dials, and they pull against each other. `CELL` is the pane size - smaller
brings the sitter back, and 44 is coarse enough that no feature fits in a pane.
The trace strength is how hard the features are painted on afterwards: at 6.0
gain it is recognisably her, which is too much, and at 1.5 there is no face in
the window at all.

Run it by hand; the output is committed. It is not part of any build.
"""
import colorsys
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

W, H = 620, 856
SRC = "/home/cgovind/Pictures/celia.jpeg"
OUT = "static/img/art/boo-altarpiece.jpg"

# Head and shoulders, in fractions of the source, so the crop survives the file
# being replaced by another shot of roughly the same framing.
CROP = (0.206, 0.020, 0.931, 0.774)

im = Image.open(SRC).convert("RGB")
w, h = im.size
im = im.crop((int(CROP[0] * w), int(CROP[1] * h),
              int(CROP[2] * w), int(CROP[3] * h))).resize((W, H), Image.LANCZOS)

# --- lift it out of the night ----------------------------------------------
# The source is a phone photograph after dark: the sitter is a couple of stops
# under and the background is noise. Paint does not have noise in it.
im = ImageEnhance.Brightness(im).enhance(1.22)
im = im.filter(ImageFilter.MedianFilter(3))

# --- the glass -------------------------------------------------------------
# **The photograph is a cartoon, in the glazier's sense: the drawing the glass
# is cut against, not the thing on show.** It is blurred until only the masses
# survive, those masses are cut into a few bands, and each pane is filled flat
# with one colour from a jewel palette. A pane is wider than an eye socket, so
# the glass alone gives a figure and not a portrait - and then the features are
# painted back on faintly, fired over the panes the way a glazier does a face.
# The brief is both halves at once: it has to read as somebody from the far end
# of the nave, and it must not read as *her* from anywhere.
flat = im.filter(ImageFilter.GaussianBlur(4))

# **A window is designed as figure against ground, and that is what finally got
# a head into this one.** Setting a pane's colour from brightness alone cannot
# work here: the sky behind her is the same brightness as her face, so the two
# came out of the same sheet and the silhouette disappeared. The panes inside
# the figure are cut from warm glass and the ones outside it from cool, and the
# head is legible before a single band is chosen.
FIGURE = ((0.30, 292, 0.24), (0.52, 352, 0.48), (0.72, 34, 0.82), (1.01, 44, 0.99))
GROUND = ((0.34, 230, 0.24), (0.62, 208, 0.42), (1.01, 194, 0.60))
# Panes this big are the point. At 18 the head was legible as a person you could
# name; at 44 it is a head.
CELL = 44
random.seed(0xB00)

# **Panes take their colour from a map of masses, not from the pixel under
# them.** Thresholding a blurred photograph per pane puts the two neighbours
# either side of a band edge on different sheets, and since those edges wander
# all over a face the window came out as confetti with no shape in it. Cutting
# the bands first and then running a mode filter over the *labels* is what makes
# a mass a mass: the hair is one region, the brow is one region, and a pane asks
# which region it is in rather than measuring anything itself.
grey_im = flat.convert("L")
grey = grey_im.load()

# The figure is drawn, not found. Head, neck and shoulders as three shapes a
# glazier would cut: nothing here needs to follow the photograph closely, and
# the moment it does the sitter comes back.
fig = Image.new("L", (W, H), 0)
fd = ImageDraw.Draw(fig)
fd.ellipse((W * 0.24, H * 0.09, W * 0.76, H * 0.63), fill=255)          # head and hair
fd.polygon([(W * 0.36, H * 0.52), (W * 0.64, H * 0.52),
            (W * 0.86, H * 1.00), (W * 0.14, H * 1.00)], fill=255)      # shoulders
fig = fig.filter(ImageFilter.GaussianBlur(3))
figm = fig.load()

# **The four warm glasses are spread over the figure's own range, not over the
# photograph's.** Her whole head lives in the middle third of the histogram -
# the black sea and the lit dress are what use the ends - so banding globally
# spent two of the four sheets on things that are not her and left the face flat
# in one. Stretched to the figure's own 4th and 96th percentiles, the face gets
# all four: plum for the hair, ruby for the shaded side, amber and cream for the
# lit one. This is the whole of what brought the likeness back.
hist = grey_im.histogram(mask=fig.point(lambda v: 255 if v > 128 else 0))
inside = sum(hist)
run, lo, hi = 0, 0, 255
for i, n in enumerate(hist):
    run += n
    if run < inside * 0.04:
        lo = i
    if run < inside * 0.96:
        hi = i
lab = grey_im.point(lambda v: min(3, max(0, int((v - lo) / max(1, hi - lo) * 4))) * 60)
lab = lab.filter(ImageFilter.ModeFilter(11)).filter(ImageFilter.ModeFilter(7))
src = lab.load()

# The halo rings the head from outside, in gold, and only ever in the ground.
# Struck tight it crossed her hair and the lit side of her face, and a gold band
# through a face is what stopped an earlier version having a head in it at all.
HX, HY, HR = W * 0.50, H * 0.34, W * 0.44


def mesh(x0, y0, x1, y1, cell):
    """Triangles over a rectangle, as ((ax,ay),(bx,by),(cx,cy)) tuples."""
    nx, ny = max(1, round((x1 - x0) / cell)), max(1, round((y1 - y0) / cell))
    j = cell * 0.34
    pts = [[(x0 + (x1 - x0) * i / nx + (0 if i in (0, nx) else (random.random() - 0.5) * 2 * j),
             y0 + (y1 - y0) * k / ny + (0 if k in (0, ny) else (random.random() - 0.5) * 2 * j))
            for i in range(nx + 1)] for k in range(ny + 1)]
    for k in range(ny):
        for i in range(nx):
            a, b, c, d = pts[k][i], pts[k][i + 1], pts[k + 1][i + 1], pts[k + 1][i]
            if (i + k) % 2:
                yield (a, b, c); yield (a, c, d)
            else:
                yield (a, b, d); yield (b, c, d)


tris = list(mesh(0, 0, W, H, CELL))

glass = Image.new("RGB", (W, H), (0, 0, 0))
gdr = ImageDraw.Draw(glass)
for t in tris:
    cx_ = min(W - 1, max(0, int(sum(p[0] for p in t) / 3)))
    cy_ = min(H - 1, max(0, int(sum(p[1] for p in t) / 3)))
    on_fig = figm[cx_, cy_] > 128
    bands = FIGURE if on_fig else GROUND
    # Inside the figure the band is the label map, which has her features in it
    # as small masses - a brow, an eye, the shadow under the lip - so a pane that
    # lands on one is cut from the dark sheet and the face has something in it.
    # Outside, the label map is only noise off the water and the rigging, so the
    # ground is banded off the smooth photograph instead and stays calm.
    if on_fig:
        # **A pane on the head takes the median of seven samples spread across
        # its own area, not the one pixel under its middle.** An eye is smaller
        # than a pane here, so a centroid sample steps straight over it and the
        # face comes out as one flat oval; a pane that is *mostly* eye now comes
        # out of the dark sheet and the face has something in it. Median rather
        # than darkest, which was tried: on a head this size nearly every pane
        # clips a lash or a nostril, and the whole face went black.
        pts_ = [(min(W - 1, max(0, int(cx_ + (p[0] - cx_) * f))),
                 min(H - 1, max(0, int(cy_ + (p[1] - cy_) * f))))
                for p in t for f in (0.35, 0.7)] + [(cx_, cy_)]
        lum = sorted(src[x, y] for x, y in pts_)[2] / 180.0
    else:
        lum = grey[cx_, cy_] / 255.0
    hue, v = next((u, vv) for lim, u, vv in bands if lum < lim)
    # Per-pane jitter, kept small. Real glass is cut from different sheets and
    # no two panes of "the same" blue match - but much more than this and it
    # stops being cutting and starts being noise.
    v = min(1.0, v * (0.96 + random.random() * 0.08))
    warm = min(abs(hue - 38), 360 - abs(hue - 38)) < 60
    sat = (0.50 if warm else 0.94) + (random.random() - 0.5) * 0.06
    rad = math.hypot(cx_ - HX, (cy_ - HY) * 1.05)
    if not on_fig and HR * 0.80 < rad < HR:
        hue, sat, v = 44, 0.85, 0.88
    # A border band of ruby and indigo round the whole light, alternating pane by
    # pane. Every window has one, and it is what stops the design running off the
    # edge of the glass into the stone.
    elif min(cx_, W - cx_, cy_, H - cy_) < CELL * 1.2:
        hue, sat, v = (350, 0.92, 0.42) if (cx_ + cy_) // CELL % 2 else (226, 0.95, 0.34)
    r2, g2, b2 = colorsys.hsv_to_rgb(hue / 360.0, max(0.0, min(1.0, sat)), v)
    gdr.polygon(t, fill=(int(r2 * 255), int(g2 * 255), int(b2 * 255)))

# --- the lead ---------------------------------------------------------------
# Drawn after every pane is down, or each polygon's fill eats the line before
# it, and drawn **fat**: came is a strip of milled lead a few millimetres wide,
# and at a hairline the panes read as facets of one surface instead of as
# separate pieces held in a frame.
for t in tris:
    gdr.polygon(t, outline=(13, 11, 15), width=3)

# **No fired-on features, and that was the change.** A glazier paints the eyes
# and the mouth onto the glass, which is what an earlier version did - and it
# worked, which was the problem: it put her face back into a window that is
# meant to be a figure, not a portrait.

# --- the fired-on trace -------------------------------------------------------
# **The last of the likeness, and it is what a glazier does rather than what a
# photograph does.** Panes this size cannot hold an eye, so the features are
# painted on the glass and fired: a thin dark line where the photograph is
# darker than its own surroundings, which finds the brows, the eyes, the
# nostrils and the line of the mouth and finds nothing else. It is kept to the
# head - painted over the whole window it turns back into a photograph - and
# kept **faint**: at full strength an earlier version was her, plainly, which is
# the one thing this must not be.
# Off the *unblurred* photograph. Taken off the cartoon it finds nothing -
# the cartoon is 4px of blur, which is most of an eyelash gone already.
sharp = im.convert("L")
trace = ImageChops.subtract(sharp.filter(ImageFilter.GaussianBlur(9)),
                            sharp.filter(ImageFilter.GaussianBlur(1.5)))
trace = trace.point(lambda v: min(132, int(max(0, v - 4) * 4.5)))
# Only on the head, and on a soft-edged mask. Over the shoulders it draws every
# fold of the dress and the window turns back into a photograph; hard-edged, the
# trace stops dead on a line and the line is the thing you then see.
head = Image.new("L", (W, H), 0)
ImageDraw.Draw(head).ellipse((W * 0.28, H * 0.15, W * 0.76, H * 0.64), fill=255)
trace = ImageChops.multiply(trace, head.filter(ImageFilter.GaussianBlur(26)))
trace = trace.filter(ImageFilter.GaussianBlur(1.0))
glass = ImageChops.subtract(glass, Image.merge("RGB", (trace, trace, trace)))

# --- backlight --------------------------------------------------------------
# Glass is lit from behind, not from the side, so this is the one place the
# panel does *not* get the chapel's candle warmth - the light comes through it
# cold and the glass supplies its own colour. The screen blur is the bloom a
# bright pane throws over its own leading, which is what stops the window
# reading as a printed mosaic.
paint = ImageChops.screen(
    glass, glass.filter(ImageFilter.GaussianBlur(7)).point(lambda v: int(v * 0.10)))
paint = ImageEnhance.Color(paint).enhance(1.15)

# --- the gilded ground ------------------------------------------------------
# Outside the arch is gold leaf, which is what makes this read as an altarpiece
# from the far end of the nave rather than as a photograph on a wall. Hatched
# rather than flat, because flat gold is a yellow rectangle.
random.seed(0xB00)
gold = Image.new("RGB", (W, H))
gd = gold.load()
for y in range(H):
    for x in range(W):
        t = 0.5 + 0.5 * math.sin((x * 0.9 + y * 2.1) * 0.06)
        s = 0.5 + 0.5 * math.sin((x - y) * 0.021)
        # **Nearly flat, where this used to be strongly hatched.** Two sines at
        # 0.15 looked like tooled gold leaf at full size and like a bright
        # diagonal stripe on a panel hung twenty units away - and because the
        # two waves beat, the stripe was worse down one side than the other,
        # which reads as an artifact rather than as an intention. A third of the
        # amplitude is still gilding up close and is an even field from the road.
        v = 0.70 + 0.05 * t * s + random.random() * 0.035
        gd[x, y] = (int(206 * v), int(161 * v), int(72 * v))

# A two-centred arch: each side is struck from the *opposite* springing point
# with the span as the radius, which is what makes it pointed rather than
# round. Its apex lands at spring - span * sqrt(3)/2, and if that is off the top
# of the panel the arch is a rectangle - which is what the first version drew.
# **The arch is exactly where it was**, and widening it was tried and put back.
# Opening it to 0.055 either side did remove the gold band beside the picture -
# and it also re-framed the head, which is the one part of this panel that
# works. The band was never the arch's fault; it was the hatching, above.
mask = Image.new("L", (W, H), 0)
mx0, mx1 = W * 0.09, W * 0.91
spring, foot = H * 0.58, H * 0.965
span_ = mx1 - mx0
ImageDraw.Draw(mask).rectangle((mx0, spring, mx1, foot), fill=255)
lobe = None
for cx in (mx0, mx1):
    one = Image.new("L", (W, H), 0)
    ImageDraw.Draw(one).pieslice(
        (cx - span_, spring - span_, cx + span_, spring + span_), 180, 360, fill=255)
    lobe = one if lobe is None else ImageChops.multiply(lobe, one)
cap = Image.new("L", (W, H), 0)
ImageDraw.Draw(cap).rectangle((mx0, 0, mx1, spring), fill=255)
mask = ImageChops.lighter(mask, ImageChops.multiply(cap, lobe))
mask = mask.filter(ImageFilter.GaussianBlur(1.2))
panel = Image.composite(paint, gold, mask)

# --- the window's own falloff -----------------------------------------------
# **Much gentler than the painted version's chiaroscuro, and it has to be.**
# A panel is lit from in front and goes dark at the edges; a window is lit from
# behind and its edges are still glass. All this does is keep the head the
# brightest thing, so the picture still reads at twenty world units down a dark
# nave, without shutting the bottom of the window off.
vig = Image.new("L", (W, H), 0)
dr = ImageDraw.Draw(vig)
cx, cy = W * 0.50, H * 0.32
for i in range(80):
    t = i / 80.0
    rr = (1.0 - t) * W * 1.30
    dr.ellipse((cx - rr, cy - rr * 1.30, cx + rr, cy + rr * 1.30),
               fill=int(168 + 87 * (1.0 - t) ** 0.70))
vig = vig.filter(ImageFilter.GaussianBlur(52))
panel = ImageChops.multiply(panel, Image.merge("RGB", (vig, vig, vig)))
panel = ImageEnhance.Brightness(panel).enhance(1.12)

# **No craquelure and no canvas weave.** Both were right for a painted panel and
# are wrong for this: glass does not crack in a web and it is not woven, and at
# the size this hangs they only greyed the colour off.

dr = ImageDraw.Draw(panel)
for i in range(10):
    v = 14 + i * 3
    dr.rectangle((i, i, W - 1 - i, H - 1 - i), outline=(v + 6, v, v - 4))

# quality 86, not 92: the leading is thousands of hard black edges and JPEG
# spends most of its bits on them - 92 cost 230KB for a picture hanging at the
# end of a dark nave, and this is 170KB with nothing visible lost.
panel.save(OUT, quality=86, optimize=True)
print("wrote", OUT, panel.size)
