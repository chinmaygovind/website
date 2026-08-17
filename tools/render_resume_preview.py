#!/usr/bin/env python3
"""Render page 1 of the resume PDF to the still that phones show instead of it.

A PDF in an `<iframe>` is only reliable on a desktop browser. On a phone the
built-in viewers render a fixed, non-scrollable snapshot of the top of the page
and stop, so the resume modal showed about a quarter of the resume and no way to
reach the rest. Below 760px the page swaps the iframe for this PNG, which every
browser draws the same way, and tapping it opens the real PDF.

Run this whenever site/assets/Chinmay_Govind_Resume.pdf changes:

    python3 tools/render_resume_preview.py

It writes the PNG and a stamp holding the PDF's sha256; tests/test_resume_preview.py
compares the two and fails when the resume has moved on without the picture,
because nothing about a stale preview looks broken - it is just last year's job.

Needs poppler (`pdftoppm`) and Pillow. The render is greyscale on purpose: the
PDF has no colour in it at all, so 64 levels of grey cost 171KB instead of the
471KB a full-colour render costs, at a maximum error of 4/255.
"""

import hashlib
import pathlib
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF = ROOT / "site" / "assets" / "Chinmay_Govind_Resume.pdf"
PNG = ROOT / "site" / "assets" / "resume-preview.png"
STAMP = ROOT / "site" / "assets" / "resume-preview.sha256"
DPI = 144  # 2x a 72dpi letter page, so it stays sharp on a retina phone


def pdf_digest() -> str:
    return hashlib.sha256(PDF.read_bytes()).hexdigest()


def main() -> int:
    if not PDF.exists():
        print("no resume at %s" % PDF, file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "page"
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(DPI), "-f", "1", "-l", "1", "-singlefile",
             str(PDF), str(out)],
            check=True,
        )
        im = Image.open(out.with_suffix(".png"))

    im = im.convert("L").quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    im.save(PNG, optimize=True)
    STAMP.write_text(pdf_digest() + "\n")
    print("wrote %s (%d bytes, %dx%d)" % (PNG.name, PNG.stat().st_size, *im.size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
