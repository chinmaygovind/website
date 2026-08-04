"""Profile pictures: the round trip through Pillow, and the name it comes out with.

The one rule worth testing hard is that **nothing a visitor uploads is served
back as they sent it**. Every test here is some version of that: the bytes
change, the format changes, the name is not theirs to choose, and a file that
was never an image does not get through at all.
"""

import io
import os

import pytest
from PIL import Image

from accounts import avatars


def png(width=400, height=300, colour=(20, 90, 200)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buf, format="PNG")
    return buf.getvalue()


def test_a_stored_avatar_is_a_square_webp_whatever_arrived(tmp_path):
    name = avatars.store(str(tmp_path), 7, png(900, 300))
    blob = open(os.path.join(str(tmp_path), name), "rb").read()

    img = Image.open(io.BytesIO(blob))
    assert img.format == "WEBP"
    assert img.size == (avatars.SIZE, avatars.SIZE)
    assert blob != png(900, 300)                 # re-encoded, not passed through


def test_the_stored_name_is_ours_and_carries_a_hash_of_the_contents(tmp_path):
    """The name is the cache strategy: a new picture is a new URL, so nothing
    ever has to be invalidated. It also means the uploader never chooses the
    URL, the extension or the content type."""
    name = avatars.store(str(tmp_path), 7, png())
    assert name.startswith("7-") and name.endswith(".webp")
    assert avatars.is_safe_name(name)

    again = avatars.store(str(tmp_path), 7, png())
    assert again == name                         # same picture, same name

    different = avatars.store(str(tmp_path), 7, png(colour=(200, 30, 30)))
    assert different != name


def test_a_file_that_is_not_an_image_is_refused(tmp_path):
    for blob in (b"", b"just some text", b"\x89PNG\r\n\x1a\n" + b"lies" * 40):
        with pytest.raises(avatars.AvatarError):
            avatars.store(str(tmp_path), 7, blob)


def test_something_far_too_big_is_refused_before_it_is_decoded(tmp_path):
    with pytest.raises(avatars.AvatarError, match="5MB"):
        avatars.store(str(tmp_path), 7, b"x" * (avatars.MAX_UPLOAD + 1))


def test_a_format_we_do_not_want_is_refused_even_though_pillow_reads_it(tmp_path):
    """Pillow opens plenty of formats. Only the handful a browser would have
    produced are accepted, so the decoder surface is the one we chose."""
    buf = io.BytesIO()
    Image.new("RGB", (60, 60)).save(buf, format="TIFF")
    with pytest.raises(avatars.AvatarError, match="PNG, JPEG"):
        avatars.store(str(tmp_path), 7, buf.getvalue())


def test_a_tall_picture_is_cropped_from_the_middle(tmp_path):
    """Where a face is. Cropping from a corner is the difference between a
    portrait and somebody's shoulder."""
    tall = Image.new("RGB", (200, 800), (255, 255, 255))
    for y in range(380, 420):
        for x in range(80, 120):
            tall.putpixel((x, y), (255, 0, 0))       # a red mark, dead centre
    buf = io.BytesIO()
    tall.save(buf, format="PNG")

    name = avatars.store(str(tmp_path), 7, buf.getvalue())
    out = Image.open(os.path.join(str(tmp_path), name)).convert("RGB")
    r, g, b = out.getpixel((avatars.SIZE // 2, avatars.SIZE // 2))
    assert r > 150 and g < 110 and b < 110


def test_removing_an_avatar_is_safe_to_do_twice_or_to_a_name_we_never_wrote(tmp_path):
    name = avatars.store(str(tmp_path), 7, png())
    avatars.remove(str(tmp_path), name)
    assert not os.path.exists(os.path.join(str(tmp_path), name))
    avatars.remove(str(tmp_path), name)                     # already gone
    avatars.remove(str(tmp_path), "../../etc/passwd")       # never ours
    avatars.remove(str(tmp_path), None)


def test_is_safe_name_only_accepts_names_this_module_could_have_written():
    assert avatars.is_safe_name("7-9f3a1c2b.webp")
    assert avatars.is_safe_name("1234-00000000.webp")

    for bad in ("../7-9f3a1c2b.webp", "7-9f3a1c2b.png", "7-9f3a1c2.webp",
                "x-9f3a1c2b.webp", "7-9f3a1c2z.webp", "7/9f3a1c2b.webp",
                "", None, "a" * 80 + ".webp"):
        assert not avatars.is_safe_name(bad), bad


def test_the_default_picture_is_the_same_one_for_the_same_person_for_ever():
    """It is derived rather than stored, so it has to be stable - somebody's
    avatar changing colour on a deploy would look like a bug in the site."""
    assert avatars.colour_for("chinmay") == avatars.colour_for("chinmay")
    assert avatars.colour_for("chinmay") == avatars.colour_for("CHINMAY")
    assert avatars.colour_for("chinmay") in avatars.PALETTE
    assert avatars.colour_for(None) in avatars.PALETTE


def test_the_default_picture_always_has_something_to_draw():
    assert avatars.initial_for("chinmay") == "C"
    assert avatars.initial_for("  spaced out") == "S"
    assert avatars.initial_for("42nd") == "4"
    assert avatars.initial_for("!!!") == "?"        # nothing alphanumeric at all
    assert avatars.initial_for("") == "?"
    assert avatars.initial_for(None) == "?"
