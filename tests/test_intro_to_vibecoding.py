"""The ``/intro-to-vibecoding/`` slide deck.

It is one self-contained page with its own pictures beside it, plus a handful
it borrows from ``site/assets/``. Nothing on the site links to it and it is
``noindex``: it is a URL handed to a room. A renamed photo or track preview
would not break anything visibly except one slide during the talk, so every
relative reference is resolved against the tree here.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DECK = os.path.join(SITE, "intro-to-vibecoding")
PAGE = os.path.join(DECK, "index.html")

requires_deck = pytest.mark.skipif(
    not os.path.isfile(PAGE),
    reason="site/intro-to-vibecoding/ is not checked out here (sparse CI checkout)",
)


def references():
    html = open(PAGE, encoding="utf-8").read()
    refs = re.findall(r'(?:src|poster|href)="([^"#:]+)"', html)
    refs += re.findall(r"loader\.load\(`?\"?([^`\"$)]+)", html)
    return sorted({r for r in refs if not r.startswith(("http", "/", "data:"))})


@requires_deck
def test_the_deck_is_noindex():
    assert '<meta name="robots" content="noindex">' in open(PAGE, encoding="utf-8").read()


@requires_deck
def test_the_decks_own_files_exist():
    own = [r for r in references() if not r.startswith("../")]
    assert own, "the reference scan found nothing, so it is not scanning"
    missing = [r for r in own if not os.path.exists(os.path.join(DECK, r))]
    assert not missing, missing


@requires_deck
@pytest.mark.skipif(
    not os.path.isdir(os.path.join(SITE, "assets", "about")),
    reason="site/assets/ is not checked out here (sparse CI checkout)",
)
def test_what_it_borrows_from_the_site_exists():
    borrowed = [r for r in references() if r.startswith("../")]
    missing = [r for r in borrowed if not os.path.exists(os.path.normpath(os.path.join(DECK, r)))]
    assert not missing, missing
