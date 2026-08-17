# Cover art

Store art for the game portals Drive is submitted to (CrazyGames wants a
1920x1080, an 800x1200 and an 800x800). Three tracks, each at the three sizes,
each with and without the wordmark:

```
rainbow_1920x1080.png        the picture
rainbow_1920x1080-title.png  the same picture with the wordmark over it
```

`-title` is what a storefront wants. The plain one is there for anywhere that
puts its own name over the art, and for cropping something else out of.

**These are the game, not a drawing of it.** `tools/shoot_covers.py` loads the
real play page at `?shot=1`, stops the frame loop, and composes a scene with the
game's own `CarView`s seated on the ribbon's own frame - so a car in Rainbow
Road's loop is upside down because the road is. Regenerate with:

```bash
python tools/shoot_covers.py                 # all of them
python tools/shoot_covers.py spa             # one track
python tools/shoot_covers.py spa --explore   # candidate angles, to choose from
```

**They go stale silently.** Change a track's geometry, palette or sky and its
cover is a picture of the old one, and nothing in the suite will say so - the
same trap as the switcher's previews and the share cards. Re-run the tool, look
at the pictures, and commit them.

Which stretch of each lap is in frame is *found* (the tool scans for loops,
pipes, climbs and bends), but the angle on it is recorded in `COVERS` in the
tool, because "which way round is dramatic" is not a thing a number knows. If a
track changes enough to spoil its shot, run `--explore` and pick a new one.
