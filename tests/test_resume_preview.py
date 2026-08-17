"""Whether the picture of the resume is still a picture of *this* resume.

Below 760px the resume modal shows `site/assets/resume-preview.png` instead of
the PDF, because a phone's built-in viewer renders a fixed, non-scrollable
snapshot of the top of the page in an iframe and nothing reaches the rest of it.

That leaves a derived file next to its source, which is the shape of thing that
rots: replace the PDF and the picture keeps its old job with no symptom at all,
because a stale preview does not look broken, it looks like last year's resume.
So the renderer stamps the PDF's sha256 beside the PNG and this compares them.

Fix a failure by re-rendering, never by editing the stamp:

    python3 tools/render_resume_preview.py
"""

import hashlib
import os

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
ASSETS = os.path.join(ROOT, "site", "assets")
PDF = os.path.join(ASSETS, "Chinmay_Govind_Resume.pdf")
PNG = os.path.join(ASSETS, "resume-preview.png")
STAMP = os.path.join(ASSETS, "resume-preview.sha256")

# CI checks `site` out sparsely. The cone for `site/assets/flags` also takes the
# files sitting in `site/assets/` itself, so all three of these are there - but
# skip rather than fail if that ever stops being true, the way test_seo.py does.
pytestmark = pytest.mark.skipif(
    not os.path.exists(PDF), reason="resume PDF not in this checkout"
)


def test_the_preview_is_of_the_current_resume():
    assert os.path.exists(PNG), "run tools/render_resume_preview.py"
    assert os.path.exists(STAMP), "run tools/render_resume_preview.py"

    want = hashlib.sha256(open(PDF, "rb").read()).hexdigest()
    got = open(STAMP).read().strip()
    assert got == want, (
        "site/assets/resume-preview.png was rendered from a different PDF than the "
        "one in the tree. Re-render it: python3 tools/render_resume_preview.py"
    )
