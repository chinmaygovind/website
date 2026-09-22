"""`/ese5420` is a directory with a file in it and no page of its own.

The formula sheet lives at ``/ese5420/Midterm1_Formulas.pdf`` and there is no
``site/ese5420/index.html``, so the bare directory would 404 while the file
beside it returned 200. The route in ``app.py`` sends it to the landing page
instead.

**The PDF itself is not asserted here, on purpose.** CI checks out the `site`
module sparsely and asks for ``site/ese2100`` by name; ``site/ese5420`` is not
in that list, so a test that read the file would fail in CI and pass locally.
What is worth pinning is the redirect, which is the only logic involved - the
file being served is the catch-all doing what it does for every other path.
"""


def test_the_bare_directory_goes_to_the_landing_page(client):
    for url in ("/ese5420", "/ese5420/"):
        r = client.get(url)
        assert r.status_code == 302, url
        assert r.headers["Location"] == "/", url


def test_it_is_a_302_so_it_can_be_taken_back(client):
    """If a second ESE 5420 page ever arrives this directory should grow its own
    index, the way ``/ese2100/`` did. A 301 cached by everyone who followed it
    would make that unreachable, so the code matters more than it looks."""
    assert client.get("/ese5420").status_code == 302


def test_the_pdf_is_not_swallowed_by_the_redirect(client):
    """Only the two bare spellings are registered. A deeper path under the same
    prefix must still reach the static catch-all rather than bouncing to `/`."""
    r = client.get("/ese5420/Midterm1_Formulas.pdf")
    assert r.status_code != 302, "the redirect is catching the file beside it"
