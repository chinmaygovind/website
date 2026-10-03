"""PNG copies of the site's flags, for the lap share card (`ogcard.lap_card`).

    cd drive && venv/bin/python tools/raster_flags.py

The flags live on the main site (`site/assets/flags/`), and the country ones are
SVG, which Pillow cannot draw - so the card reads these instead, rasterised once
in a browser at the card's 2x. State flags are already PNG and are just scaled.
Re-run it when a flag is added there; a missing one leaves the card flagless
rather than failing.
"""

import base64
import os
import re
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "..", "site", "assets", "flags")
OUT = os.path.join(ROOT, "static", "img", "flags")
HEIGHT = 88


def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        page = pw.chromium.launch().new_page()
        for name in sorted(os.listdir(os.path.join(SRC, "country"))):
            if not name.endswith(".svg"):
                continue
            with open(os.path.join(SRC, "country", name), "rb") as f:
                svg = f.read()
            m = re.search(rb'viewBox="[\d.\s-]*?([\d.]+)\s+([\d.]+)"', svg)
            w = round(HEIGHT * float(m.group(1)) / float(m.group(2)))
            page.set_viewport_size({"width": w, "height": HEIGHT})
            page.set_content('<style>html,body{margin:0;background:none}</style>'
                             '<img src="data:image/svg+xml;base64,%s" style="width:%dpx;'
                             'height:%dpx;display:block">'
                             % (base64.b64encode(svg).decode(), w, HEIGHT))
            page.wait_for_load_state("load")
            page.screenshot(path=os.path.join(OUT, name[:-4] + ".png"),
                            omit_background=True)
    for name in sorted(os.listdir(os.path.join(SRC, "us"))):
        if name.endswith(".png"):
            im = Image.open(os.path.join(SRC, "us", name)).convert("RGBA")
            im.resize((round(HEIGHT * im.width / im.height), HEIGHT), Image.LANCZOS) \
              .save(os.path.join(OUT, "us-" + name), optimize=True)
    print(len(os.listdir(OUT)), "flags in", os.path.relpath(OUT, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
