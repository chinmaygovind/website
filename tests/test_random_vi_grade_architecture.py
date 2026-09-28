"""The ``/random/vi-grade-architecture/`` page.

One self-contained page: Chinmay's Penn Electric Racing REV12 VI-grade sim
architecture, with a clickable diagram. Nothing on the site links to it and it
is ``noindex``: it is a URL handed to the team.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DIR = os.path.join(SITE, "random", "vi-grade-architecture")
PAGE = os.path.join(DIR, "index.html")

requires_page = pytest.mark.skipif(
    not os.path.isfile(PAGE),
    reason="site/random/vi-grade-architecture/ is not checked out here (sparse CI checkout)",
)


@requires_page
def test_the_page_is_noindex():
    assert '<meta name="robots" content="noindex">' in open(PAGE, encoding="utf-8").read()


@requires_page
def test_the_page_ships_no_team_documents():
    # The private artifact bundled DTI manuals and REV11 design binders under
    # docs/. They were left out on purpose; a link back to them would 404 at
    # best and publish them at worst.
    html = open(PAGE, encoding="utf-8").read()
    assert not re.search(r'"(?:u|href)"?[:=] ?"docs/', html)
    assert not os.path.exists(os.path.join(DIR, "docs"))
