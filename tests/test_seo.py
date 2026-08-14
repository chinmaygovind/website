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


def test_the_sitemap_is_well_formed_xml():
    """It is parsed by machines only, so nothing else would ever notice."""
    assert locs(), "sitemap lists no URLs"


def test_every_url_in_the_sitemap_is_a_page_that_exists():
    """The failure this exists for: a page is renamed and the sitemap is not.

    Resolved against the tree rather than over HTTP, so it fails on the laptop
    that made the change instead of in somebody's Search Console a month later.
    """
    missing = []
    for url in locs():
        assert url.startswith(ORIGIN + "/"), "not on this host: %s" % url
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
