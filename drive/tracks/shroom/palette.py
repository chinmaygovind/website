"""What Shroom Street looks like.

A bright overcast-edged summer day in a green gorge. Taken off three references -
Mushroom Gorge in MKWii and in MK8 Deluxe, and the crystal-cave remake of it -
and what all three share is narrower than it sounds: **cream-spotted caps on pale
stalks over a chasm, and a warm tan road against saturated green.** Everything
here is in service of those two.

Two decisions are worth stating because both were the reference correcting an
instinct.

**The road is *lighter* than the grass, not just a different hue.** In the MKWii
shot the path is pale sand against mid-green and reads instantly from above; the
MK8 version pushes it orange and it reads slightly worse. Value separation is
also the only thing that keeps `plan.png` legible, since the plan view is lit and
shadowless and two colours of the same value are the same colour from overhead
however different they look side by side.

**The cave reference is deliberately not used for the light.** It is all emitting
crystals and bloom, and a `glowStrength` high enough to imitate that smears the
whole dome from the sun's azimuth - which is precisely how Tokyo Drift came out a
pink dusk. The caves contributed the cap colours and nothing else.

Colours are packed RGB handed to three.js unconverted, so they are picked cooler
than they look - see `tracks/look.py`.
"""

PALETTE = {
    # Pale sandy dirt. Warm, but pulled back from the reference's orange: a warm
    # key light multiplies a vertex colour that is already warm and the road
    # goes to mud.
    # Warmer and more saturated than the first pass's 0xb9a37c, which read as a
    # correct pale sand in `plan.png` and as olive-grey from the car. The plan
    # view is lit flat and shadowless; in the world the sage `hemi.ground` bounce
    # lands on every upward face, and a tan that pale had nothing left to resist
    # it with. The lesson is the palette note's own, one step further on: pick
    # base colours cooler than they look, but check them against the *bounce*
    # and not against the swatch.
    "road": 0xcaa96d,
    # The mushroom's own two colours, which is what makes the kerbs belong to
    # this track rather than to the pool.
    "kerb": 0xf2ead6, "kerb2": 0xc9403a,
    # Saturated mid-green. This is the loudest area colour on the track and it is
    # meant to be - in every reference the grass is the thing the road, the rock
    # and the caps are all read against.
    "ground": 0x458f3c,
    "rail": 0xefe6d2,
    # Grey-green rock, for the gorge walls and for the trestles `buildTrack`
    # stands under raised road. Those want to be the same colour as the cliffs
    # this track's `scenery.js` builds rather than a second material, which is
    # Mount Joy's reasoning for the same pair.
    # Pale limestone rather than the grey-green first pass. On a void track
    # `buildTrack` gives every station a trestle (`base` is a flat `p[1] - 16`),
    # and where two legs of this track pass close the lower one pulls the ground
    # down under the upper, so there is genuinely a fair amount of visible pier.
    # Grey-green read as scaffolding; limestone reads as a viaduct, which is a
    # thing a gorge road plausibly has.
    "prop": 0xa39a86, "prop2": 0x7d7568,
    # Gates and markers. Warm red rather than the pool's usual yellow: against
    # saturated green and a cyan sky, yellow is the one hue with nothing to be
    # seen against, and red is already the track's accent.
    "deco": 0xe0552e,
    "fog": 0xc4dcea,
    # The caps. Slightly deeper and slightly cooler than the reference's
    # vermilion, because they are drawn *unlit* - see `capSpots` in trackmesh.js -
    # so nothing shades them down and a bright base has nowhere left to go.
    "cap": 0xc4342c, "capSpot": 0xf0e6cd,
    # Boost pads, in MKWii's own colours rather than the pool's cyan: yellow
    # chevrons on a red plate. The plate is dark enough to lift the chevrons off
    # a road that is itself pale, which is the job `padBase` does.
    "pad": 0xffc24a, "padBase": 0x8e2f24,
    # There is a gorge under this track, so the void needs no floor of its own.
    # `buildTrack` draws a distant grey plate at `minY - 34` for any floating
    # track with no `below`, and here that would be a second, lower,
    # differently-coloured ground showing past the edge of the meadow. Any
    # `below` at all suppresses it; `void` is the one that then draws nothing.
    "below": {"kind": "void"},
    # Read by this track's own scenery rather than by `addScenery`, which stops
    # at `if (!onGround) continue` - the trees here stand on a height field only
    # `scenery.js` knows the shape of. Low on purpose: the references have a
    # handful of conifers on the skyline, not a forest, and the pool's own
    # cautionary tale is Sandy Cove's first pass coming out a palm plantation.
    "density": 0.07,
    "sky": {
        # A clear summer sky, pale at the horizon and deep overhead. There is
        # deliberately **no cloud in the dome** even though all three references
        # have fat cumulus in them: cloud reads as pale rectangles when you look
        # at it from below, however it is shaded, and only works looked down on.
        "stops": [
            [0.00, 0xdcecf2], [0.30, 0xa8d4ea], [0.50, 0x7cbde4],
            [0.70, 0x4f9fd8], [0.85, 0x2f7fc4], [1.00, 0x1d5faa],
        ],
        "glow": 0xfff8e8, "glowStrength": 0.42, "glowMode": "radial",
        # Tight focus. A broad one is what smears a radial glow into a dusk, and
        # the whole point of this sky is that it is the middle of the day.
        "glowFocus": 7,
        # High, and off to one side rather than behind you. High because a
        # midday sun is what the references have and because a low one throws the
        # gorge wall across the road; off to one side so the cliffs have a lit
        # face and a shaded one and read as rock rather than as flat panels.
        "sun": {"az": 2.15, "el": 0.62, "color": 0xfffdf4, "size": 240},
        "light": {"color": 0xfbfdff, "intensity": 1.26,
                  "dir": [-0.42, 0.82, 0.39]},
        # The bounce, and the number to be careful with. Grass throws back green,
        # so this wants to be green - but `hemi.ground` is the strongest colour
        # in any palette and a *saturated* green here is not a tint, it is a
        # second key light that repaints every upward-facing surface on the
        # track. Muted sage: it reads on the car's underside and on the caps'
        # overhangs and nowhere else.
        # Pulled off the green it started on (0x6f8a5e). Even muted, a green
        # bounce is still a green key light on every upward-facing surface, and
        # what it was actually doing was turning a warm sand road olive. It keeps
        # a bias toward the grass and no more than that.
        "hemi": {"sky": 0xc8e4f6, "ground": 0x8a8d78, "intensity": 0.88},
        "fog": 0xc4dcea, "fogNear": 300, "fogFar": 1400,
    },
}
