"""Reading an Amazon link into a wishlist item: title, picture, price.

There is no Amazon API behind this. The Product Advertising API needs an
Associates account with recent qualifying sales before it answers at all, which
a Secret Santa page is never going to have, so this fetches the product page
the way a browser would and reads the three things a wishlist shows.

**Best-effort on purpose.** Amazon often answers a datacenter IP with a captcha
instead of the product, and when it does ``lookup`` returns no title and the
page asks the person what the thing is. The link itself is always kept, so the
Santa can open it whatever happened here.

**Only Amazon is ever fetched.** This is a server fetching a URL a visitor
typed, so every hop is checked: redirects are followed by hand, and each one
must land on an Amazon host before anything is requested from it. Short links
(``a.co``, ``amzn.to``) are just the first hop of that.

Timeouts are short because the website runs on two sync gunicorn workers; a
slow Amazon must not hold one of them for long.
"""

import html
import re
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

TIMEOUT = 4            # seconds per request
MAX_HOPS = 4
MAX_BYTES = 3 * 1024 * 1024

# amazon.com, amazon.co.uk, amazon.com.au, smile.amazon.com, ...
STORE_HOST = re.compile(r"^(?:(?:www|smile|m)\.)?amazon\.(?:com|ca|co\.uk|de|fr|it|es|in|co\.jp|com\.au|com\.mx|com\.br|nl|se|sg|ae)$")
SHORT_HOSTS = {"a.co", "amzn.to", "amzn.com", "amzn.eu", "amzn.asia"}
IMAGE_HOST = re.compile(r"(?:^|\.)(?:media-amazon\.com|ssl-images-amazon\.com|images-amazon\.com)$")

ASIN_PATH = re.compile(r"/(?:dp|gp/product|gp/aw/d|exec/obidos/ASIN|o/ASIN)/([A-Z0-9]{10})(?:[/?]|$)", re.I)
URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+", re.I)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


class NotAmazon(ValueError):
    """The link is not an Amazon product link, or led somewhere that is not Amazon."""


def _host(url):
    return (urlparse.urlsplit(url).hostname or "").lower()


def is_amazon(url):
    """True for an http(s) URL on an Amazon store or short-link host."""
    parts = urlparse.urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme in ("http", "https") and (bool(STORE_HOST.match(host)) or host in SHORT_HOSTS)


def find_url(text):
    """The first link in what was pasted. Amazon's share button adds a sentence around it."""
    text = (text or "").strip()
    m = URL_IN_TEXT.search(text)
    if m:
        return m.group(0).rstrip(".,)")
    if text and " " not in text and "." in text:
        return "https://" + text
    return ""


def asin_of(url):
    m = ASIN_PATH.search(urlparse.urlsplit(url).path + "/")
    return m.group(1).upper() if m else None


def product_url(host, asin):
    """The tidy form of a product link, without the tracking parameters."""
    return "https://%s/dp/%s" % (host if STORE_HOST.match(host) else "www.amazon.com", asin)


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urlrequest.build_opener(_NoRedirect)


def _fetch(url):
    """One GET without following redirects. Returns (status, location, body)."""
    req = urlrequest.Request(url, headers=HEADERS)
    try:
        resp = _opener.open(req, timeout=TIMEOUT)
    except urlerror.HTTPError as e:
        return e.code, e.headers.get("Location"), b""
    with resp:
        return resp.status, None, resp.read(MAX_BYTES)


def _follow(url):
    """Follow redirects by hand, refusing any hop off Amazon. Returns (final_url, body)."""
    for _ in range(MAX_HOPS):
        if not is_amazon(url):
            raise NotAmazon(url)
        status, location, body = _fetch(url)
        if status in (301, 302, 303, 307, 308) and location:
            url = urlparse.urljoin(url, location)
            continue
        return url, body if status == 200 else b""
    return url, b""


def _clean(text, limit):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit] or None


def _meta(page, prop):
    for pat in (r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']*)["\']',
                r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']'):
        m = re.search(pat % re.escape(prop), page, re.I)
        if m:
            return m.group(1)
    return None


def parse_title(page):
    m = re.search(r'id=["\']productTitle["\'][^>]*>(.*?)</span>', page, re.S | re.I)
    if m and _clean(m.group(1), 300):
        return _clean(m.group(1), 300)
    title = _meta(page, "og:title") or _meta(page, "title")
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
        title = m and m.group(1)
    title = _clean(title, 300)
    if not title:
        return None
    # "Amazon.com: Thing, Blue : Home & Kitchen" -> "Thing, Blue"
    title = re.sub(r"^Amazon\.[a-z.]+\s*:\s*", "", title, flags=re.I)
    title = re.sub(r"\s+:\s+[^:]+$", "", title)
    if title.lower().rstrip(".") in ("amazon.com", "amazon", "page not found") or "robot check" in title.lower():
        return None
    return title


def parse_image(page):
    for pat in (r'id=["\']landingImage["\'][^>]*data-old-hires=["\']([^"\']+)["\']',
                r'data-old-hires=["\']([^"\']+)["\'][^>]*id=["\']landingImage["\']',
                r'id=["\']landingImage["\'][^>]*src=["\']([^"\']+)["\']',
                r'src=["\']([^"\']+)["\'][^>]*id=["\']landingImage["\']'):
        m = re.search(pat, page, re.I)
        if m and safe_image(m.group(1)):
            return m.group(1)
    og = _meta(page, "og:image")
    return og if og and safe_image(og) else None


def parse_price(page):
    """The headline price, as Amazon prints it ("$24.99"), or None."""
    start = re.search(r'id=["\'](?:corePriceDisplay_desktop_feature_div|corePrice_feature_div|corePrice_desktop|apex_desktop)', page)
    region = page[start.start():start.start() + 6000] if start else ""
    m = re.search(r'class=["\']a-offscreen["\'][^>]*>\s*([^<]{1,20}?)\s*<', region)
    return _clean(m.group(1), 20) if m else None


def safe_image(url):
    """Only Amazon's own image CDN may be drawn on the page, over https."""
    parts = urlparse.urlsplit(url or "")
    return parts.scheme == "https" and bool(IMAGE_HOST.search((parts.hostname or "").lower()))


def lookup(pasted):
    """Turn whatever was pasted into a wishlist item.

    Parameters
    ----------
    pasted : str
        A product link, a short link, or Amazon's share text with a link in it.

    Returns
    -------
    dict
        ``url`` (always), ``asin``, ``title``, ``image`` and ``price``, any of
        which may be None when Amazon would not show the page.

    Raises
    ------
    NotAmazon
        The text has no Amazon link in it, or a redirect left Amazon.
    """
    url = find_url(pasted)
    if not url or not is_amazon(url):
        raise NotAmazon(pasted)
    try:
        final, body = _follow(url)
    except NotAmazon:
        raise
    except Exception:                                    # noqa: BLE001 - network, timeouts, TLS
        final, body = url, b""
    host = _host(final)
    asin = asin_of(final) or asin_of(url)
    page = body.decode("utf-8", "replace")
    return {
        "url": product_url(host, asin) if asin else final,
        "asin": asin,
        "title": parse_title(page) if page else None,
        "image": parse_image(page) if page else None,
        "price": parse_price(page) if page else None,
    }
