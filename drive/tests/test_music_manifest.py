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
# The entries that are not tracks. The menu pages play `menu` and the
# multiplayer lobbies `lobbies`; `menumusic.js` asks for them by these names.
MENU = "menu"
MENUS = {MENU, "lobbies"}


def _manifest():
    with open(MANIFEST) as f:
        return json.load(f)


def test_every_slug_is_a_real_track():
    """A misspelled slug is silence on the track it was meant for and a song
    nothing ever asks for - neither of which fails anything at runtime."""
    pool = {t["slug"] for t in tracks.TRACKS}
    named = set(_manifest()["tracks"]) - MENUS
    assert named <= pool, "manifest names tracks that do not exist: %s" % sorted(named - pool)


def test_the_menu_has_a_song():
    """`menumusic.js` asks for exactly this key, and the menu pages are most of
    the site - losing it would be quiet in a way nobody would report."""
    assert MENU in _manifest()["tracks"]


def _songs(m):
    """(where, song) for every song a track can play, playlists included."""
    for slug, e in m["tracks"].items():
        if "playlist" in e:
            for i, s in enumerate(m.get("playlists", {}).get(e["playlist"], [])):
                yield "%s[%s %d]" % (slug, e["playlist"], i), s
        else:
            yield slug, e


def test_every_playlist_a_track_names_exists_and_has_songs():
    """A missing playlist is silence, the same as a typo'd slug."""
    m = _manifest()
    for slug, e in m["tracks"].items():
        if "playlist" in e:
            assert m.get("playlists", {}).get(e["playlist"]), "%s: no playlist %r" % (slug, e["playlist"])


def test_every_entry_has_a_file_and_a_credit():
    """The now-playing card is a credit, and a song with no title is a card
    that names nothing. The link is what makes it a credit rather than a label,
    so it is required too."""
    for slug, e in _songs(_manifest()):
        assert e.get("file"), "%s has no file" % slug
        assert e.get("title"), "%s has no title" % slug
        assert e.get("url"), "%s has no link to credit" % slug


def test_the_written_loop_points_make_sense():
    """`in` before `out`, and enough room between them for the crossfade to
    happen inside the song rather than across its end."""
    m = _manifest()
    for slug, e in _songs(m):
        fade = e.get("fade", m.get("fade", 1.2))
        if "out" not in e:
            continue
        start = e.get("in", 0)
        assert e["out"] > start, "%s: out is not after in" % slug
        assert e["out"] - start > fade * 2, "%s: too short for its own crossfade" % slug


def test_the_real_circuits_share_one_playlist():
    """Driving Spa to Monaco keeps the song going. `MusicPlayer.setSong` keeps
    playing when the playlist name matches, so they must all name the same one."""
    t = _manifest()["tracks"]
    named = {s: t[s].get("playlist") for s in ("spa", "silverstone", "monaco", "monza",
                                               "suzuka", "sepang", "baku", "singapore") if s in t}
    assert len(set(named.values())) == 1 and None not in named.values(), named
