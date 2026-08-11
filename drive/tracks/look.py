"""What a track looks like: the palette contract, and the one every track starts from.

A palette used to be a named entry in a `PALETTES` object inside trackmesh.js,
which meant a track's geometry was in Python and its appearance was in JavaScript
and the two had to agree about anything that was both. Sandy Cove's waterline and
the Costco shell are exactly that: the road is *authored against* them, so they
were written down twice and held together by tests that scraped the JS with a
regular expression.

Palettes are pure data - the only computed values were `Math.sin` of a literal -
so they live here now, and they reach the browser and the anti-cheat through
plumbing that already existed. `_track_payload` in app.py sends the whole track
dict to the page as `window.DRIVE_TRACK`, and `jsrt` sends the whole pool to
QuickJS as JSON. A palette on the track dict rides both for free.

**Colours are packed RGB integers**, written as hex (`0x4d5769`). They are handed
to three.js unconverted, which is worth knowing before picking any of them: a
light's colour goes through sRGB-to-linear and a *vertex* colour does not, so a
warm light multiplies a neutral grey road down to mud. Every base colour in these
palettes is cooler than it looks for that reason.
"""

# The keys `buildTrack` reads for any track, whatever else it has. Missing one
# does not raise in JS - it reads `undefined`, three.js turns that into NaN and
# the geometry draws black - so it is checked here, where the message can say
# which track and which key.
REQUIRED = ("road", "kerb", "kerb2", "ground", "rail", "prop", "deco", "fog")

# Optional blocks, listed so a typo in one is caught rather than silently doing
# nothing. `sky` is not optional in practice - a palette without it gets the old
# two-tone dome - but it is not required to build.
KNOWN = REQUIRED + (
    "sky",            # graded dome, sun, cloud, fog distances: see makeSky
    "below",          # what floats underneath a void track (`kind`: desert,
                      # downtown, lava, pillars, void)
    "terrain",        # a height field instead of one flat ground quad (Spa)
    "furniture",      # grandstands, pits, gantry, hoardings (Spa)
    "building",       # an interior with walls and a roof (Costco)
    "shore",          # a waterline, and the road authored against it (Sandy Cove)
    "density",        # how thickly the scatter plants things; 0 for none
    "props",          # what the scatter plants, by weight
    "snow",           # the white slab under Figure Eight
    "gravel",         # run-off colour, where there is run-off
    "pad", "padBase",  # boost pads
    "prop2",          # second structural colour: trestles, columns
    "rainbow", "rainbowLanes",  # Rainbow Road's per-station hue sweep
)

# Neutral daylight, and deliberately unremarkable. A new track with no
# `palette.py` gets this and renders correctly on the first run, which is the
# difference between "add a folder and drive it" and "add a folder, then find out
# what a palette is". It is a starting point to be replaced, not a house style.
DEFAULT = {
    "road": 0x4d5464,
    "kerb": 0xf4f4f2,
    "kerb2": 0xe8453c,
    "ground": 0x5ea364,
    "rail": 0xf2eee8,
    "prop": 0x37624a,
    "deco": 0xf2c94c,
    "fog": 0xc9d3dc,
    "density": 0.12,
    "sky": {
        "stops": [
            [0.00, 0xa8bccb], [0.42, 0xc8dae7], [0.50, 0xdcebf5],
            [0.60, 0xa9c9e6], [0.78, 0x74a5da], [1.00, 0x4478c4],
        ],
        "glow": 0xfff6e0, "glowStrength": 0.55, "glowMode": "radial",
        "glowFocus": 5,
        "sun": {"az": 1.15, "el": 0.46, "color": 0xfffaf0, "size": 330},
        "light": {"color": 0xfff6e8, "intensity": 1.3,
                  "dir": [0.58, 0.76, 0.29]},
        "hemi": {"sky": 0xdfe9f2, "ground": 0x5d6a52, "intensity": 0.95},
        "fog": 0xc9d3dc, "fogNear": 300, "fogFar": 1400,
    },
}


def check(slug, pal):
    """Raise if a palette is missing something, or has a key nothing reads.

    The unknown-key half matters as much as the missing-key half. `glowStrenth`
    is not an error in JavaScript and not an error in Python; it is a palette that
    quietly ignores the thing you were trying to change, which is the failure mode
    a contributor is most likely to hit and least likely to diagnose.
    """
    missing = [k for k in REQUIRED if k not in pal]
    if missing:
        raise ValueError(
            "tracks/%s/palette.py is missing %s. Every track needs those - "
            "without one, three.js draws that geometry black."
            % (slug, ", ".join(missing)))
    unknown = [k for k in pal if k not in KNOWN]
    if unknown:
        raise ValueError(
            "tracks/%s/palette.py has %s, which nothing reads. Check the "
            "spelling against tracks/look.py:KNOWN."
            % (slug, ", ".join(sorted(unknown))))
    return pal
