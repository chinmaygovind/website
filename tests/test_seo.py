"""Whether the site can be found at all.

`cgovind.com` was not in Google's index in August 2026 while
`chinmaygovind.github.io` - the GitHub Pages site this repo was derived from -
still ranked for Chinmay's own name. Some of that needs Search Console and some
of it needed the two things this file pins.

**The sitemap is the only way most of this site is discoverable.** The landing
page's tiles open modals or point at the game subdomains, so no internal page is
linked from `/` at all: a crawler that arrives finds one page and stops. That
makes `site/sitemap.xml` load-bearing rather than decorative, and a hand-kept
list of URLs is exactly the kind of file that rots quietly when a page is
renamed - a sitemap full of 404s is worse than no sitemap, because it is a
crawler's evidence that the site is badly kept.

Drive generates its own from the track pool and tests it in
`drive/tests/test_share.py`; this is the static half.
"""

import os
import re
import xml.etree.ElementTree as ET

import pytest

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
ROOT = os.path.join(os.path.dirname(__file__), "..")
SITE = os.path.join(ROOT, "site")
SITEMAP = os.path.join(SITE, "sitemap.xml")
ROBOTS = os.path.join(SITE, "robots.txt")
ORIGIN = "https://cgovind.com"


def locs():
    root = ET.parse(SITEMAP).getroot()
    assert root.tag == NS + "urlset", "not a sitemap: %s" % root.tag
    return [e.text for e in root.iter(NS + "loc")]


def site_tree_is_here():
    """Whether `site/`'s pages are on disk, or only the sliver CI checks out.

    **In the Action every job is a sparse checkout of its own module**, and the
    `site` job asks for `scripts`, `accounts`, `tests` and `site/assets/flags` -
    `site/` is ~513MB and the suite's other 222 tests never read it.
    `actions/checkout` sparse mode is a **cone**, which includes the files of
    every parent directory on the way to each pattern. So `site/assets/flags`
    drags in `site/`'s own files - `index.html`, `robots.txt`, `sitemap.xml`,
    all of which the tests here read quite happily - and `site/assets/`'s, while
    leaving `site/wii/`, `site/home/`, `site/games/` and the rest absent.

    That makes the sentinel fiddly, and getting it wrong is silent. It cannot be
    `site/assets`, which **exists in CI** for the reason above. It cannot be any
    directory the sitemap lists, which would be circular. `site/fonts/` is
    neither: it holds the xkcd Script face the landing page is set in, it is in
    every real checkout, and the cone does not reach it.
    """
    return os.path.isdir(os.path.join(SITE, "fonts"))


def test_the_sitemap_is_well_formed_xml():
    """It is parsed by machines only, so nothing else would ever notice."""
    assert locs(), "sitemap lists no URLs"


def test_every_sitemap_url_is_on_this_host():
    """Cheap half of the check, and the half that needs no pages on disk.

    A sitemap may only list URLs on its own host - a `drive.cgovind.com` entry
    in here would invalidate the file rather than help Drive - so this runs
    everywhere, including the sparse CI checkout.
    """
    wrong = [u for u in locs() if not u.startswith(ORIGIN + "/")]
    assert not wrong, "not on this host: %s" % wrong


def test_every_url_in_the_sitemap_is_a_page_that_exists():
    """The failure this exists for: a page is renamed and the sitemap is not.

    Resolved against the tree rather than over HTTP, so it fails on the laptop
    that made the change instead of in somebody's Search Console a month later.

    **Skipped where `site/` is not checked out, which means it does not run in
    CI** - the same trade `test_no_drift.py` makes for `ttr/`, and the same
    danger, since a skip reads as a pass. It is tolerable only because the two
    things that would break it, editing the sitemap and renaming a page, are
    both done in a full checkout by somebody who can run this. If that ever
    stops being true, the fix is to check `site/` out for this job, not to
    weaken the assertion.
    """
    if not site_tree_is_here():
        pytest.skip("site/ is not checked out here (sparse CI checkout), so "
                    "there are no pages to resolve the sitemap against")
    missing = []
    for url in locs():
        path = url[len(ORIGIN):].strip("/")
        # `app.py` serves GitHub-Pages-style directory indexes, so `/wii/` is
        # `site/wii/index.html`. A bare path is a file as written.
        target = os.path.join(SITE, path, "index.html") if path == "" or \
            os.path.isdir(os.path.join(SITE, path)) else os.path.join(SITE, path)
        if not os.path.exists(target):
            missing.append(url)
    assert not missing, "sitemap points at pages that do not exist: %s" % missing


def test_the_sitemap_lists_nothing_robots_disallows():
    """Asking a crawler to fetch a page and forbidding it are not compatible."""
    robots = open(ROBOTS).read()
    banned = re.findall(r"^Disallow:\s*(\S+)$", robots, re.M)
    clashes = [u for u in locs()
               for b in banned if b != "" and u[len(ORIGIN):].startswith(b)]
    assert not clashes, "sitemap lists disallowed paths: %s" % clashes


def test_robots_names_the_sitemap():
    """Nothing links to it, so this line is how it is found."""
    assert "Sitemap: %s/sitemap.xml" % ORIGIN in open(ROBOTS).read()


@pytest.mark.parametrize("needle,why", [
    ('rel="canonical"', "www and the apex both answer 200, so one has to be named"),
    ('name="description"', "what Google prints under the title"),
    ('"@type": "Person"', "ties this domain to the profiles that already rank"),
])
def test_the_landing_page_carries_what_a_search_engine_reads(needle, why):
    assert needle in open(os.path.join(SITE, "index.html")).read(), why


def test_the_landing_page_title_says_who_this_is():
    """It was "Chinmay's Website", which contains neither the name somebody
    searches for nor the domain they would recognise."""
    head = open(os.path.join(SITE, "index.html")).read()
    title = re.search(r"<title>([^<]*)</title>", head).group(1)
    assert "Chinmay Govind" in title, title


def test_the_canonical_is_the_apex_and_not_www():
    """Both answer 200 with no redirect between them; this is what settles it,
    and it has to keep pointing at one of them rather than at whichever host
    served the page."""
    head = open(os.path.join(SITE, "index.html")).read()
    href = re.search(r'<link rel="canonical" href="([^"]+)"', head).group(1)
    assert href == ORIGIN + "/", href
