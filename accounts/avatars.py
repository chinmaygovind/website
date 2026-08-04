"""Profile pictures: taking one in, and deciding what to show when there isn't one.

Two rules shape all of this.

**Nothing a visitor uploads is ever served back as they sent it.** The file is
decoded, checked, cropped, resized and *re-encoded* by Pillow, and only the
bytes Pillow writes are kept. An image that survives that round trip cannot
still be carrying a payload aimed at whatever opens it next, and an "image" that
was never an image in the first place does not survive it at all. This is also
why the stored name is chosen here rather than taken from the upload: an
attacker who picks the filename picks the URL, the extension and the content
type, and none of those are theirs to pick.

**A profile with no picture is not a blank grey circle.** Everyone gets an
initial on a colour derived from their username - always the same colour for
the same person, drawn from the palette the landing page already uses, so the
empty state is a deliberate look rather than a hole waiting to be filled. That
one is rendered inline in the page (see the ``avatar`` macro) instead of being
an image, so it can use the site's own font; a standalone SVG served to an
``<img>`` cannot load a webfont, and the initial is the whole picture.
"""

import hashlib
import io
import os

SIZE = 256                 # stored square, big enough for a retina hero at 128
MAX_UPLOAD = 5 * 1024 * 1024
# What Pillow is allowed to have decoded. A file claiming to be a PNG that
# decodes as something else is not an upload we want to think about.
ALLOWED = {"PNG", "JPEG", "WEBP", "GIF", "BMP"}

# The landing page's accent colours, which is why a default avatar looks like it
# belongs to this site rather than to a component library.
PALETTE = ["#16295c", "#1565c0", "#c0182b", "#6b4226", "#b8860b",
           "#5c2678", "#3d8bfd", "#1f7a4d", "#333333", "#a03c78"]


class AvatarError(Exception):
    """Something about the upload was wrong, phrased for the person who sent it."""


def colour_for(name):
    """The same colour for the same name, for ever."""
    digest = hashlib.sha256((name or "?").lower().encode()).digest()
    return PALETTE[digest[0] % len(PALETTE)]


def initial_for(name):
    for ch in (name or ""):
        if ch.isalnum():
            return ch.upper()
    return "?"


def store(directory, user_id, data):
    """Re-encode ``data`` as this user's avatar and return the stored filename.

    The name carries a hash of the finished bytes (``7-9f3a1c2b.webp``), so
    changing your picture changes its URL. That is the whole cache strategy:
    nothing has to be invalidated, because nothing is ever served stale - the
    old URL simply stops being mentioned. It also means uploading the same
    picture twice is a no-op rather than a churn of files.
    """
    if not data:
        raise AvatarError("No file was uploaded.")
    if len(data) > MAX_UPLOAD:
        raise AvatarError("That image is larger than 5MB. Try a smaller one.")

    try:
        from PIL import Image, ImageOps
    except ImportError:                                  # pragma: no cover
        raise AvatarError("The server cannot process images right now.")

    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").upper()
        img.load()
    except Exception:                                    # noqa: BLE001
        raise AvatarError("That file is not an image we can read.")
    if fmt not in ALLOWED:
        raise AvatarError("Use a PNG, JPEG, WebP or GIF.")

    # exif_transpose first: a phone photo is usually stored sideways with a
    # rotation flag, and cropping before honouring it crops the wrong edges.
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
    # Centre crop to a square, then down to SIZE. `ImageOps.fit` does both and
    # never upscales past the source's own detail in a way that looks worse
    # than the source did.
    img = ImageOps.fit(img, (SIZE, SIZE), method=Image.LANCZOS, centering=(0.5, 0.5))

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=86, method=4)
    blob = buf.getvalue()

    name = "%d-%s.webp" % (user_id, hashlib.sha256(blob).hexdigest()[:8])
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, name), "wb") as f:
        f.write(blob)
    return name


def remove(directory, name):
    """Delete a stored avatar, if it is still there. Never raises."""
    if not name or not is_safe_name(name):
        return
    try:
        os.remove(os.path.join(directory, name))
    except OSError:
        pass


def is_safe_name(name):
    """True for names this module could have written, and nothing else.

    The stored name always comes from ``store``, but it makes the round trip
    through a database column that four other services can also write, so the
    serving route re-checks the shape rather than trusting it. A name is
    ``<digits>-<8 hex>.webp`` and cannot contain a separator, so it cannot
    address anything outside the avatar directory.
    """
    if not name or len(name) > 64 or not name.endswith(".webp"):
        return False
    stem = name[:-len(".webp")]
    uid, _, digest = stem.partition("-")
    return (uid.isdigit() and len(digest) == 8
            and all(c in "0123456789abcdef" for c in digest))
