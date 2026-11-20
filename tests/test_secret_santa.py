import pytest

from accounts import amazon
from accounts.santa import derange, mail_assignments

API = "/cis-1600/secret-santa-26/api/"

PRODUCT_PAGE = """<html><head><title>Amazon.com: Fuzzy Socks, Blue : Clothing</title>
<meta property="og:image" content="https://m.media-amazon.com/images/I/og.jpg"></head><body>
<span id="productTitle" class="a-size-large">   Fuzzy Socks &amp; Slippers, Blue   </span>
<div id="corePriceDisplay_desktop_feature_div"><span class="a-price"><span class="a-offscreen">$12.99</span></span></div>
<img alt="x" src="https://m.media-amazon.com/images/I/small.jpg" data-old-hires="https://m.media-amazon.com/images/I/big.jpg" id="landingImage">
</body></html>"""


@pytest.fixture
def amazon_pages(monkeypatch):
    """Stand in for Amazon: url -> (status, location, body). Unknown urls answer 503."""
    pages, seen = {}, []

    def fake(url):
        seen.append(url)
        return pages.get(url, (503, None, b""))
    monkeypatch.setattr(amazon, "_fetch", fake)
    return pages, seen


def join(client, logged_in, name):
    """Log in as a fresh account called ``name`` and sign it up."""
    client.get("/accounts/logout")
    logged_in(name)
    return client.post(API + "signup", json={})


def relogin(client, name):
    client.get("/accounts/logout")
    client.post("/accounts/login", data={"username": name, "password": "hunter2hunter2"})


def test_nobody_draws_themselves_and_everyone_is_drawn():
    for n in range(3, 40):
        pairs = derange(range(n))
        assert all(a != b for a, b in pairs.items())
        assert sorted(pairs.values()) == list(range(n))


def test_signing_up_needs_an_account(client):
    r = client.post(API + "signup", json={"name": "a", "email": "a@x.com"})
    assert r.status_code == 401 and r.json["login"].startswith("/accounts/login?next=")
    s = client.get(API + "status").json
    assert s["count"] == 0 and s["user"] is None and "me" not in s


def test_signup_uses_the_account_and_only_once(client, logged_in):
    assert join(client, logged_in, "alice").json == {"ok": True, "name": "alice"}
    assert client.post(API + "signup", json={"name": "fake", "email": "x@y.com"}).json["already"]
    s = client.get(API + "status").json
    assert s["me"] == "alice" and s["count"] == 1 and s["wishes"] == [] and not s["admin"]


def test_admin_is_added_once_draws_and_nothing_is_emailed(client, logged_in, flask_app, capsys):
    join(client, logged_in, "a")
    assert client.post(API + "draw", json={}).status_code == 404
    join(client, logged_in, "b")
    client.get("/accounts/logout")
    logged_in("chinmay")
    for _ in range(2):
        s = client.get(API + "status").json
    assert s["me"] == "Chinmay" and s["count"] == 3 and s["pairs"] == []
    capsys.readouterr()

    assert client.post(API + "draw", json={}).json["ok"]
    s = client.get(API + "status").json
    assert len(s["pairs"]) == 3 and not s["sent"] and "giftee" not in s
    assert "assignment" not in capsys.readouterr().err      # the draw mails nobody

    with flask_app.app_context():
        mail_assignments()
    assert "/cis-1600/secret-santa-26/" in capsys.readouterr().err   # the letter links the page
    s = client.get(API + "status").json
    assert s["sent"] and s["giftee"]["name"] in ("a", "b")
    assert client.post(API + "draw", json={}).status_code == 409
    assert join(client, logged_in, "d").status_code == 409


def test_a_late_signup_voids_the_draw(client, logged_in):
    join(client, logged_in, "a")
    join(client, logged_in, "b")
    client.get("/accounts/logout")
    logged_in("chinmay")
    client.get(API + "status")
    client.post(API + "draw", json={})
    join(client, logged_in, "c")
    relogin(client, "chinmay")
    assert client.get(API + "status").json["pairs"] == []


def test_a_stranger_sees_no_list(client, logged_in):
    logged_in("someone")
    assert client.post(API + "draw", json={}).status_code == 404
    s = client.get(API + "status").json
    assert "people" not in s and "pairs" not in s and "me" not in s and s["user"] == "someone"


def test_wishlist_reads_amazon_and_only_the_owner_can_remove(client, logged_in, amazon_pages):
    pages, _ = amazon_pages
    pages["https://a.co/d/abc"] = (301, "https://www.amazon.com/Fuzzy/dp/B0ABCDEF12?ref=x", b"")
    pages["https://www.amazon.com/Fuzzy/dp/B0ABCDEF12?ref=x"] = (200, None, PRODUCT_PAGE.encode())

    assert client.post(API + "wishlist", json={"url": "https://a.co/d/abc"}).status_code == 401
    logged_in("nobody")
    assert client.post(API + "wishlist", json={"url": "https://a.co/d/abc"}).status_code == 403

    join(client, logged_in, "alice")
    r = client.post(API + "wishlist", json={
        "url": "Check out this Amazon deal: Fuzzy Socks https://a.co/d/abc", "note": "size M"})
    w = r.json["wish"]
    assert w["title"] == "Fuzzy Socks & Slippers, Blue"
    assert w["url"] == "https://www.amazon.com/dp/B0ABCDEF12"
    assert w["image"] == "https://m.media-amazon.com/images/I/big.jpg"
    assert w["price"] == "$12.99" and w["note"] == "size M"
    assert client.get(API + "status").json["wishes"] == [w]

    join(client, logged_in, "bob")
    assert client.post(API + "wishlist/%d/delete" % w["id"], json={}).status_code == 404
    relogin(client, "alice")
    assert client.post(API + "wishlist/%d/delete" % w["id"], json={}).json["ok"]
    assert client.get(API + "status").json["wishes"] == []


def test_wishlist_asks_what_it_is_when_amazon_will_not_say(client, logged_in, amazon_pages):
    join(client, logged_in, "alice")
    r = client.post(API + "wishlist", json={"url": "https://www.amazon.com/dp/B0ABCDEF12"})
    assert r.status_code == 422 and r.json["need_title"]
    r = client.post(API + "wishlist", json={"url": "https://www.amazon.com/dp/B0ABCDEF12",
                                            "title": "Lego set"})
    assert r.json["wish"]["title"] == "Lego set" and r.json["wish"]["image"] is None


def test_wishlist_refuses_anything_but_amazon(client, logged_in, amazon_pages):
    pages, seen = amazon_pages
    join(client, logged_in, "alice")
    for bad in ("https://evil.example/dp/B0ABCDEF12", "file:///etc/passwd",
                "https://amazon.com.evil.example/x", "socks"):
        r = client.post(API + "wishlist", json={"url": bad, "title": "x"})
        assert r.status_code == 400, bad
    assert seen == []
    # a redirect off Amazon is refused before it is followed
    pages["https://amzn.to/x"] = (302, "http://169.254.169.254/latest", b"")
    assert client.post(API + "wishlist", json={"url": "https://amzn.to/x", "title": "x"}).status_code == 400
    assert seen == ["https://amzn.to/x"]


def test_your_santa_sees_your_list_only_after_the_emails(client, logged_in, flask_app, amazon_pages):
    for n in ("a", "b"):
        join(client, logged_in, n)
        client.post(API + "wishlist", json={"url": "https://www.amazon.com/dp/B0ABCDEF12",
                                            "title": "gift for " + n})
    client.get("/accounts/logout")
    logged_in("chinmay")
    client.get(API + "status")
    client.post(API + "draw", json={})
    assert "giftee" not in client.get(API + "status").json
    with flask_app.app_context():
        mail_assignments()
    g = client.get(API + "status").json["giftee"]
    assert [w["title"] for w in g["wishes"]] == ["gift for " + g["name"]]


def test_gift_idea_is_yours_to_set_and_reaches_the_admin(client, logged_in):
    assert client.post(API + "idea", json={"idea": "x"}).status_code == 401
    join(client, logged_in, "a")
    assert client.post(API + "idea", json={"idea": "  warm socks  "}).json["idea"] == "warm socks"
    assert client.get(API + "status").json["idea"] == "warm socks"
    client.get("/accounts/logout")
    logged_in("chinmay")
    people = client.get(API + "status").json["people"]
    assert [p["idea"] for p in people if p["name"] != "Chinmay"] == ["warm socks"]


def test_amazon_parsing():
    assert amazon.asin_of("https://www.amazon.com/Some-Thing/dp/b0abcdef12/ref=sr_1_1?k=x") == "B0ABCDEF12"
    assert amazon.asin_of("https://www.amazon.co.uk/gp/product/B0ABCDEF12") == "B0ABCDEF12"
    assert amazon.asin_of("https://www.amazon.com/s?k=socks") is None
    assert amazon.is_amazon("https://smile.amazon.com/dp/B0ABCDEF12")
    assert not amazon.is_amazon("https://notamazon.com/dp/B0ABCDEF12")
    assert amazon.parse_title("<title>Amazon.com: Thing, Red : Toys &amp; Games</title>") == "Thing, Red"
    assert amazon.parse_title("<title>Amazon.com</title>") is None
    assert amazon.parse_image('<img id="landingImage" src="https://evil.example/x.jpg">') is None
    assert amazon.parse_price(PRODUCT_PAGE) == "$12.99"
