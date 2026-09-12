"""The coursework pages under ``/ese2100/``.

These are the only pages on the site served through ``serve()``'s
directory-index branch, so this file is also the first thing that checks that
branch works: ``/ese2100/cobweb/`` reaching its ``index.html`` is the whole
mechanism, and before these pages existed nothing on disk exercised it.

Two of the assertions here are about a URL rather than a file. ``/cobweb`` was
the cobweb page's address for a fortnight before the coursework pages had a
parent, and it was handed to people in that time, so it 301s to the new one
forever. That redirect is a route in ``app.py`` and not a file, because a static
tree cannot answer 301.

The pages themselves are unlinked and ``noindex`` on purpose - they are URLs you
send someone - so nothing else in the suite would notice if a ``robots`` tag
went missing on the next edit. That is what the last test is for.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
ESE = os.path.join(SITE, "ese2100")

PAGES = ["", "cobweb", "bifurcations"]


def pages_are_checked_out():
    """CI checks out a cone of ``site/``, so a test that reads these files has
    to say whether they are there. They are asked for by name in
    ``.github/workflows/deploy.yml``; this is the guard for a checkout that
    does not, and it is deliberately narrow - a skip reads as a pass, so it
    must not be able to fire when only one of the three is missing."""
    return os.path.isdir(ESE)


requires_pages = pytest.mark.skipif(
    not pages_are_checked_out(),
    reason="site/ese2100/ is not checked out here (sparse CI checkout)",
)


@requires_pages
@pytest.mark.parametrize("page", PAGES)
def test_each_page_is_on_disk_as_an_index_html(page):
    assert os.path.isfile(os.path.join(ESE, page, "index.html")), \
        "/ese2100/%s/ has no index.html" % page


@requires_pages
@pytest.mark.parametrize("page", PAGES)
def test_a_directory_url_serves_that_pages_index(client, page):
    url = "/ese2100/" + (page + "/" if page else "")
    r = client.get(url)
    assert r.status_code == 200, url
    assert b"<title>" in r.data


@requires_pages
@pytest.mark.parametrize("page", PAGES)
def test_the_bare_path_redirects_to_the_slashed_one(client, page):
    """GitHub Pages behaviour, and it is load-bearing here: every asset these
    pages ask for is relative, so ``/ese2100/cobweb`` without the slash would
    look for the font one directory too high.

    **It is a 302, and both this file's docstring and ``app.py``'s used to say
    301** - Pages sends 301 and the prose was written from that, but the code
    has always taken ``redirect()``'s default. The 302 is the one worth keeping:
    a path that is a directory today can be a file tomorrow, and a 301 a browser
    has cached is not retractable. That is pinned here rather than left as a
    detail, because these pages are the first thing that ever reached the
    branch.
    """
    if not page:
        bare = "/ese2100"
    else:
        bare = "/ese2100/" + page
    r = client.get(bare)
    assert r.status_code == 302, bare
    assert r.headers["Location"].endswith(bare + "/")


def test_the_old_cobweb_url_still_lands_on_the_page(client):
    for url in ("/cobweb", "/cobweb/"):
        r = client.get(url)
        assert r.status_code == 301, url
        assert r.headers["Location"] == "/ese2100/cobweb/", url


def test_the_old_cobweb_url_is_not_a_file_anymore(client):
    """If somebody ever re-creates ``site/cobweb/index.html`` the route above
    would still win, and the two would drift apart silently."""
    assert not os.path.exists(os.path.join(SITE, "cobweb"))


@requires_pages
@pytest.mark.parametrize("page", PAGES)
def test_every_page_asks_not_to_be_indexed(page):
    """They are coursework, they are linked from nowhere, and the sitemap does
    not list them. The ``noindex`` is the only thing actually keeping them out
    of a search index, since a crawler that is told the URL by any other means
    would otherwise take it."""
    html = open(os.path.join(ESE, page, "index.html"), encoding="utf-8").read()
    assert re.search(r'<meta name="robots" content="[^"]*noindex', html), page


@requires_pages
@pytest.mark.parametrize("page", PAGES)
def test_the_font_is_reached_from_where_the_page_actually_sits(page):
    """The pages are one and two directories deep and they self-host the font
    with a relative URL, so moving a page breaks its ``@font-face`` without
    breaking anything a browser reports. The depth and the number of ``../``
    have to agree, or the page silently renders in Comic Sans."""
    path = os.path.join(ESE, page, "index.html")
    html = open(path, encoding="utf-8").read()
    depth = len(os.path.relpath(os.path.dirname(path), SITE).split(os.sep))
    up = "../" * depth
    for ref in re.findall(r'(?:href|src|url\()="?((?:\.\./)+fonts/[^"\')]+)', html):
        assert ref.startswith(up + "fonts/"), \
            "%s reaches the font as %s, but it is %d deep" % (page, ref, depth)
        target = os.path.normpath(os.path.join(os.path.dirname(path), ref))
        if os.path.isdir(os.path.join(SITE, "fonts")):
            assert os.path.isfile(target), "%s points at a font that is not there" % ref


@requires_pages
def test_the_index_links_to_every_page_under_it(client):
    """The index is the URL that gets handed in each week, so a page that is not
    on it is a page nobody can reach."""
    html = open(os.path.join(ESE, "index.html"), encoding="utf-8").read()
    for page in PAGES:
        if not page:
            continue
        assert '"/ese2100/%s/"' % page in html, page
