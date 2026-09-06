"""The music manifest against the track pool.

`static/audio/music.json` is the only part of the music in git - the recordings
are not (see `drive/CLAUDE.md`). It is hand-written, it names tracks by slug,
and nothing at runtime complains about a slug that is wrong: a track with no
entry plays nothing, which is exactly what a *typo* looks like too. So the
check that the two agree has to live here.

No QuickJS and no audio files needed, so this runs everywhere - including on a
fresh clone, where `static/audio/` holds nothing but the manifest.
"""

import json
import os

import tracks

MANIFEST = os.path.join(os.path.dirname(__file__), "..", "static", "audio", "music.json")
# The one entry that is not a track. The menu pages play it; `menumusic.js`
# asks for it by this name.
MENU = "menu"


def _manifest():
    with open(MANIFEST) as f:
        return json.load(f)


def test_every_slug_is_a_real_track():
    """A misspelled slug is silence on the track it was meant for and a song
    nothing ever asks for - neither of which fails anything at runtime."""
    pool = {t["slug"] for t in tracks.TRACKS}
    named = set(_manifest()["tracks"]) - {MENU}
    assert named <= pool, "manifest names tracks that do not exist: %s" % sorted(named - pool)


def test_the_menu_has_a_song():
    """`menumusic.js` asks for exactly this key, and the menu pages are most of
    the site - losing it would be quiet in a way nobody would report."""
    assert MENU in _manifest()["tracks"]


def test_every_entry_has_a_file_and_a_credit():
    """The now-playing card is a credit, and a song with no title is a card
    that names nothing. The link is what makes it a credit rather than a label,
    so it is required too."""
    for slug, e in _manifest()["tracks"].items():
        assert e.get("file"), "%s has no file" % slug
        assert e.get("title"), "%s has no title" % slug
        assert e.get("url"), "%s has no link to credit" % slug


def test_the_written_loop_points_make_sense():
    """`in` before `out`, and enough room between them for the crossfade to
    happen inside the song rather than across its end."""
    m = _manifest()
    for slug, e in m["tracks"].items():
        fade = e.get("fade", m.get("fade", 1.2))
        if "out" not in e:
            continue
        start = e.get("in", 0)
        assert e["out"] > start, "%s: out is not after in" % slug
        assert e["out"] - start > fade * 2, "%s: too short for its own crossfade" % slug


def test_the_three_closed_circuits_share_one_file():
    """Driving Spa to Monaco is the same song, and cueing a different file
    would restart it. `MusicPlayer.setSong` compares `src`, so this is what
    makes that comparison true."""
    t = _manifest()["tracks"]
    files = {s: t[s]["file"] for s in ("spa", "silverstone", "monaco") if s in t}
    assert len(set(files.values())) == 1, files
