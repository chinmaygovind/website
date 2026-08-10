// Turns a track's station ribbon into (a) one merged flat-shaded mesh and (b) the
// triangle soup the car actually drives on.
//
// The important idea here: **the collision surface is the render surface.** Every
// driveable triangle that goes into the mesh also goes into a spatial hash, and
// the physics does closest-point queries against it. Hills, banked arcs,
// corkscrews, crests and crossings all work through one code path with no
// per-shape special cases in the car code, and nothing can ever look solid but
// not be (or vice versa). The cost is a few thousand triangles per track, which
// is nothing.
//
// Geometry: a track is a list of stations (see tracks.py), each carrying a centre
// `p`, a surface normal `n`, a road-right vector `lat` and a half-width `hw`. The
// road is the strip of quads between consecutive stations - edges at
// `p ± lat*hw` - so this whole file is one loop over pairs. A station flagged
// `air` emits nothing, which is how gaps exist; `wl`/`wr` add a barrier along
// that edge.

import * as THREE from './vendor/three.module.js';

// BOOST is a road you can drive on in every way ROAD is - the ground query, the
// steering normal, the racing line all treat it identically. It is a separate
// kind purely so the car can *notice* it, the same way OFFROAD is a surface
// rather than an object standing on one. See `Builder.boost` in tracks.py.
export const KIND = { ROAD: 0, WALL: 1, OFFROAD: 2, BOOST: 3 };

// A palette's `sky` is either a plain colour (the old two-tone dome) or a spec
// that render.js turns into a graded dome, a sun and a bank of cloud. See
// makeSky there for the full shape.
const SUNRISE_AZ = 2.42;          // where the sun comes up, radians

const PALETTES = {
  sunrise: {
    // Bases are cooler than they look, because the key light is warm and a
    // neutral grey road mixes down to mud under it. Worth knowing why the
    // compensation has to be this strong: three converts a light's colour from
    // sRGB to linear, but MeshBuf writes vertex colours straight into the
    // buffer unconverted, so a light that reads as a gentle cream in hex is a
    // much deeper orange by the time it multiplies the geometry.
    road: 0x4d5769, kerb: 0xf2ece4, kerb2: 0xe8453c,
    ground: 0x4ea363, rail: 0xf2eee8, prop: 0x27664a, deco: 0xf2c94c,
    fog: 0xf0b98a,
    sky: {
      // Straight down is haze, the horizon burns, and it cools all the way to a
      // deep blue overhead that still has night in it.
      stops: [
        [0.00, 0x8a6a5e], [0.38, 0xd08a63], [0.46, 0xf0a469],
        [0.50, 0xffc98c], [0.55, 0xf3ab7d], [0.63, 0xd28f92],
        [0.72, 0x9d8bb4], [0.84, 0x5f76b8], [1.00, 0x27418c],
      ],
      glow: 0xffd39a,
      glowStrength: 0.92,
      sun: { az: SUNRISE_AZ, el: 0.05, color: 0xffd39a, size: 430 },
      // No cloud here on purpose. Boxes seen from below at a shallow angle read
      // as pale rectangles no matter how they are shaded, and the graded dome,
      // the disc and the glow already carry the whole sky. `clouds` in
      // render.js is for the tracks that float, where you look *down* on it.
      // Low and warm, from the same bearing as the disc.
      light: { color: 0xfff1e0, intensity: 1.45,
               dir: [Math.sin(SUNRISE_AZ) * 0.9, 0.44, Math.cos(SUNRISE_AZ) * 0.9] },
      hemi: { sky: 0xffeadb, ground: 0x50506a, intensity: 0.7 },
      // Far enough out that the near field keeps its own colour and only the
      // distance dissolves into the haze.
      fog: 0xf0b98a, fogNear: 340, fogFar: 1500,
    },
  },
  // Figure Eight in the snow. `snow` is what turns on the white slab laid on
  // top of every whorl of foliage - see addScenery.
  winter:   { road: 0x3f4653, kerb: 0xffffff, kerb2: 0x3d8bfd,
              ground: 0xdfe7f2, rail: 0xf4f8ff,
              prop: 0x244a39, prop2: 0x1f4434, snow: 0xf4f9ff, deco: 0x7fb6e8,
              fog: 0xcfdcea,
              density: 0.26,
              props: { bigpine: 0.34, conifer: 0.3, deadtree: 0.22, rock: 0.14 },
              sky: {
                // A low winter sun that never really warms anything: the horizon
                // is pale gold, but it is white and cold two-thirds of the way up.
                stops: [
                  [0.00, 0x9aa9bc], [0.44, 0xd8dfe8], [0.50, 0xf0ecdf],
                  [0.56, 0xdde6f0], [0.68, 0xa8c4e2], [0.84, 0x6d9ed6],
                  [1.00, 0x3b6fb8],
                ],
                glow: 0xfff2d4, glowStrength: 0.72, glowMode: 'radial', glowFocus: 4,
                sun: { az: 2.0, el: 0.14, color: 0xfff6e2, size: 480 },
                light: { color: 0xfdf3e6, intensity: 1.32,
                         dir: [Math.sin(2.0) * 0.82, 0.56, Math.cos(2.0) * 0.82] },
                // Bounce off snow is bright and slightly blue, which is most of
                // why a snowy scene has no dark shadows in it.
                hemi: { sky: 0xdae8fa, ground: 0xc6d4e4, intensity: 0.95 },
                fog: 0xcfdcea, fogNear: 260, fogFar: 1200,
              } },
  // Chicane Park had `park` too; it has its own now so the two can be art
  // directed apart. Same daylight, but the conifers have grown up: a mix of
  // big pines among them, and a denser scatter to make it a park.
  chicane:  { road: 0x565d6b, kerb: 0xffffff, kerb2: 0x3d8bfd, ground: 0x63b866,
              sky: 0x9ed2f0, fog: 0xb9dcee, rail: 0xf0f0f0,
              prop: 0x347a3c, prop2: 0x4f9440, deco: 0xf2994a,
              density: 0.24,
              props: { bigpine: 0.42, conifer: 0.34, rock: 0.14, block: 0.10 } },
  // A road above the weather. `below` is the world under it: a broken cloud
  // deck with a city drowned in it, only the tallest towers breaking the
  // surface. See addWorldBelow.
  skyline:  { road: 0x4d5464, kerb: 0xf6f6f6, kerb2: 0x56ccf2, ground: 0x4a6b8a,
              sky: 0x7fb6dd, fog: 0x9ec9e6, rail: 0xe9f4ff, prop: 0x6e7f95, deco: 0x56ccf2,
              below: { deck: 92, depth: 190, reach: 950, rise: 46,
                       towerDensity: 0.5, breakThrough: 0.3, cover: 0.58,
                       cloud: 0xf7fbff, tower: 0x2f3b52, floor: 0x141c30 } },
  // Twin Loop: two big loops standing over an empty desert, under a sun you
  // would not want to be out in. `glowMode: radial` puts the halo around the
  // disc itself rather than smearing it along the horizon, which is what the
  // sunrise wants and a midday sun does not.
  desert:   { road: 0x515c6e, kerb: 0xf7f1e6, kerb2: 0xc75b3a,
              ground: 0xd9b478, rail: 0xf7f1e6, prop: 0xb5744a, deco: 0xf2a03c,
              fog: 0xdfc79b,
              sky: {
                stops: [
                  [0.00, 0xb08a5c], [0.42, 0xdcbe8e], [0.50, 0xf4e3c0],
                  [0.58, 0xd3dbdd], [0.70, 0x92b8dd], [0.86, 0x4b86cf],
                  [1.00, 0x1d55a4],
                ],
                // Big, hot and low enough to be in frame from the grid. The
                // halo is wide (a small focus exponent) because that is what a
                // sun you have to squint at actually does to a sky.
                glow: 0xfff9e8, glowStrength: 0.95, glowMode: 'radial', glowFocus: 3.2,
                sun: { az: 1.9, el: 0.32, color: 0xfffdf2, size: 940 },
                // The disc is low; the key light is not, or nothing gets lit.
                light: { color: 0xfff6e6, intensity: 1.62,
                         dir: [Math.sin(1.9) * 0.72, 0.69, Math.cos(1.9) * 0.72] },
                // The ground colour is sand on purpose: over a desert the bounce
                // light really is warm, and it puts a glow on every underside.
                hemi: { sky: 0xdfeaf7, ground: 0xd6ac78, intensity: 0.78 },
                fog: 0xdfc79b, fogNear: 320, fogFar: 1500,
              },
              below: { kind: 'desert', deck: 108, reach: 980,
                       duneDensity: 0.4, mesaDensity: 0.55, rockDensity: 0.18,
                       sand: 0xd9b478, rock: 0xb26a44 } },
  // Hairpin Heights: a climb with nothing under it but weather. Same deck as
  // Skyline but no city in it - the point of this one is altitude, and an
  // unbroken sea of cloud sells height better than anything you could put in it.
  heights:  { road: 0x4f5460, kerb: 0xf4f4f4, kerb2: 0xf2994a,
              ground: 0x7a6a52, rail: 0xfff2e2, prop: 0x8a7358, deco: 0xf2994a,
              fog: 0xc7dcee,
              sky: {
                // Clear high-altitude blue. Cold and bright, so the cloud sea
                // under it reads as white rather than as sand.
                stops: [
                  [0.00, 0x7d95ae], [0.44, 0xc4dcee], [0.50, 0xdcecf7],
                  [0.54, 0xa6cbec], [0.62, 0x74a8e2], [0.74, 0x4785d2],
                  [0.88, 0x2a63c0], [1.00, 0x113d92],
                ],
                glow: 0xffffff, glowStrength: 0.72, glowMode: 'radial', glowFocus: 5,
                sun: { az: 0.9, el: 0.46, color: 0xffffff, size: 560 },
                light: { color: 0xfffaf2, intensity: 1.5,
                         dir: [Math.sin(0.9) * 0.66, 0.75, Math.cos(0.9) * 0.66] },
                // Bounce off the cloud below is white, not warm.
                hemi: { sky: 0xd7e8fa, ground: 0xc3cedb, intensity: 0.8 },
                fog: 0xc7dcee, fogNear: 300, fogFar: 1450,
              },
              below: { deck: 96, depth: 120, reach: 980,
                       towerDensity: 0, cover: 0.6,
                       cloud: 0xfdfdff, floor: 0x7f93a8 } },
  // Jump City: downtown at dusk, and the towers come up *past* the road rather
  // than sitting under it, so the four gaps have a city to fall between.
  city:     { road: 0x434a58, kerb: 0xf2f4f8, kerb2: 0xf2c94c,
              ground: 0x5c6070, rail: 0xeef2f8, prop: 0x6b7180, deco: 0xf2c94c,
              fog: 0x3f4a6b,
              sky: {
                stops: [
                  [0.00, 0x241d33], [0.42, 0x5b3f52], [0.48, 0xa85f57],
                  [0.51, 0xd98a58], [0.55, 0xa96a6a], [0.64, 0x62537f],
                  [0.78, 0x30356b], [1.00, 0x131a41],
                ],
                glow: 0xffb478, glowStrength: 0.95,
                sun: { az: -1.15, el: 0.012, color: 0xffc98a, size: 300 },
                light: { color: 0xdfd4f0, intensity: 0.72,
                         dir: [Math.sin(-1.15) * 0.86, 0.5, Math.cos(-1.15) * 0.86] },
                // Dusk is mostly sky light, and the sky is blue - so the ambient
                // does the work here and the key light barely does any.
                hemi: { sky: 0x6f7ec2, ground: 0x1a1f38, intensity: 1.05 },
                fog: 0x3f4a6b, fogNear: 260, fogFar: 1250,
              },
              below: { kind: 'downtown', deck: 118, reach: 620, step: 4,
                       coreX: 40, coreZ: 150, coreR: 330,
                       low: 46, spread: 74, rise: 165,
                       landmarkX: -30, landmarkZ: 20, landmarkH: 330,
                       tower: 0x36435c, window: 0xffd79a, floor: 0x141a2b } },
  // Spiral Ascent at night. Nothing below and nothing around: the road's own
  // kerbs and banners live in the unlit buffer, so with the key light this low
  // the ribbon is the brightest thing in the world and the helix reads as a
  // lit line climbing out of the dark.
  spiral:   { road: 0x2c3040, kerb: 0xf6f2ff, kerb2: 0xbb6bd9,
              ground: 0x14121f, rail: 0xd9d2ea, prop: 0x3a3550, deco: 0xd88ce8,
              fog: 0x171a30,
              sky: {
                stops: [
                  [0.00, 0x05060e], [0.44, 0x0a0d1e], [0.50, 0x121a35],
                  [0.58, 0x101632], [0.72, 0x0b0f26], [1.00, 0x040611],
                ],
                // Tight halo. A wide one at this brightness stops being a moon
                // and becomes an evenly lit sky, which is the opposite of night.
                glow: 0x9db2e0, glowStrength: 0.42, glowMode: 'radial', glowFocus: 9,
                stars: { count: 1100, seed: 31, size: 2.1 },
                sun: { az: 1.15, el: 0.2, color: 0xe4ecff, size: 190 },
                light: { color: 0xa8bbe8, intensity: 0.72,
                         dir: [Math.sin(1.15) * 0.8, 0.6, Math.cos(1.15) * 0.8] },
                hemi: { sky: 0x3a4570, ground: 0x0d0f1c, intensity: 0.55 },
                fog: 0x171a30, fogNear: 220, fogFar: 1100,
              },
              below: { kind: 'void' } },
  // The Gauntlet: everything twice over, over a lava field, under a storm.
  gauntlet: { road: 0x33363f, kerb: 0xe8e4e2, kerb2: 0xe8453c,
              ground: 0x1b1920, rail: 0xd8d2cf, prop: 0x2a2830, deco: 0xff6a2a,
              fog: 0x2a222a,
              sky: {
                // No sun anywhere in it. The horizon is warm because the lava
                // is lighting the underside of the weather, not because there
                // is anything up there.
                stops: [
                  [0.00, 0x3d1c10], [0.40, 0x4a2314], [0.50, 0x5a2c18],
                  [0.56, 0x3a3038], [0.66, 0x2b2831], [0.82, 0x1e1c25],
                  [1.00, 0x14131b],
                ],
                light: { color: 0xa9b0c4, intensity: 0.9, dir: [0.32, 0.9, 0.28] },
                // Ground bounce is molten orange, so every underside in the
                // world glows. That single number is most of what makes this
                // look like a lava field rather than a dark field.
                hemi: { sky: 0x39404f, ground: 0xc2400f, intensity: 1.0 },
                fog: 0x2a222a, fogNear: 190, fogFar: 780,
              },
              below: { kind: 'lava', deck: 96, reach: 700,
                       crustStep: 5, crustCover: 0.86, spireStep: 16, spireDensity: 0.5,
                       lava: 0xff5510, crust: 0x1b1920,
                       above: { deck: 120, cover: 0.5, cloud: 0x2a2731 } } },
  // Rainbow Road: deep space, and the road is the only light source that
  // matters. `rainbow` is the hue step per station - the road is drawn unlit
  // (see `roadBuf`) and swept through the spectrum along its length, so it
  // glows instead of being dimmed by a key light that is barely there.
  //
  // The lighting is the difficult half. An unlit surface lights nothing by
  // itself, so "well lit from the rainbow stuff" has to come from somewhere
  // real: `hemi.ground` is a saturated magenta, which is the bounce, and it is
  // what puts colour on the underside of the car and the inside of every pipe
  // wall. The key light is cold and weak on purpose - it is starlight, and its
  // whole job is to keep the geometry readable where the road is not.
  rainbow:  { road: 0x6a4bd0, kerb: 0xffffff, kerb2: 0x2a2140,
              ground: 0x140a2e, rail: 0xf2ecff, prop: 0x3a2470, deco: 0x62f0ff,
              fog: 0x120a28,
              // Degrees of hue per station, and no banding. Hard bands were the
              // fix for a per-station step that looked like a flat gradient
              // carpet, but the real problem was the *rate*: at this much
              // slower sweep the road is a long smooth wash of colour, and the
              // shading across its width (see `roadColor`) is what stops it
              // reading flat.
              rainbow: 2.2,
              sky: {
                // Purple rather than black. A true black dome makes the road
                // the only colour anywhere and the world around it reads as
                // nothing; a deep violet keeps it space while giving the stars
                // and the ribbon something to sit against.
                stops: [
                  [0.00, 0x0d0620], [0.42, 0x1a0c38], [0.50, 0x271252],
                  [0.60, 0x22104a], [0.78, 0x150932], [1.00, 0x080418],
                ],
                // A tight halo, and it is a distant star rather than a sun -
                // big and warm here would read as a sunrise, which is the one
                // thing deep space is not.
                glow: 0xb98cff, glowStrength: 0.38, glowMode: 'radial', glowFocus: 10,
                stars: { count: 2200, seed: 77, size: 2.3 },
                sun: { az: 2.1, el: 0.42, color: 0xdfe8ff, size: 150 },
                // Starlight: cold and weak, but not so weak that the car goes
                // black. The road is unlit and lights nothing by itself, so
                // everything solid in the scene is lit by these two alone.
                light: { color: 0xaebcff, intensity: 1.0,
                         dir: [Math.sin(2.1) * 0.7, 0.68, Math.cos(2.1) * 0.7] },
                hemi: { sky: 0x8a6ad0, ground: 0xc0308a, intensity: 1.15 },
                fog: 0x120a28, fogNear: 300, fogFar: 1500,
              },
              below: { kind: 'void' } },
  // Big Red: a long fall through a red sky, above a city drowned in cloud.
  //
  // The whole track is a descent, so the thing you look at for the whole lap is
  // what is *underneath* you - hence the deepest `below` in the pool. The deck
  // sits 130 down rather than Skyline's 92 and the floor another 300 under
  // that, which is what makes the city read as far away rather than as a
  // basement; and `cover` is well under Skyline's, because the point here is
  // seeing through the holes to a city rather than seeing a cloud layer with a
  // few masts in it.
  //
  // Everything is lit from below and behind by a sun that is nearly down. That
  // is why the cloud is a warm salmon rather than white - it is being lit from
  // underneath by the same sunset - and why `hemi.ground` is a deep red: it is
  // the bounce, and on a track with nothing under it but weather the bounce is
  // most of what the car and the barriers are actually lit by.
  bigred:   { road: 0x3a2530, kerb: 0xffe4dc, kerb2: 0xff2f42,
              ground: 0x3a1622, rail: 0xffd6cf, prop: 0x5c2432, deco: 0xff4d5a,
              fog: 0xa8556a,
              // Electric cyan on a red road, which is the one pair of colours
              // nobody has to be told about. The panel under it is nearly black
              // so the chevrons have something to be bright *against* - on bare
              // tarmac they read as paint rather than as light.
              pad: 0x7df9ff, padBase: 0x140710,
              sky: {
                // Down at the horizon it is nearly black - you are above the
                // weather and there is no ground to bounce anything back. It
                // burns through crimson to orange where the sun is, and cools
                // to a deep violet overhead that still has night in it.
                stops: [
                  [0.00, 0x2a0a12], [0.36, 0x7d1526], [0.46, 0xc42d2c],
                  [0.50, 0xf25c34], [0.55, 0xc93650], [0.64, 0x8e2a5e],
                  [0.76, 0x53215e], [0.88, 0x2c1546], [1.00, 0x140a28],
                ],
                glow: 0xff9a5a, glowStrength: 0.95,
                sun: { az: -0.62, el: 0.03, color: 0xff8f52, size: 620 },
                // The disc is on the deck; the key light is not, or the road
                // and the cars are silhouettes. Warm, and strong enough that a
                // banked corner still shows which way it is banked.
                light: { color: 0xffd0b4, intensity: 1.34,
                         dir: [Math.sin(-0.62) * 0.86, 0.5, Math.cos(-0.62) * 0.86] },
                hemi: { sky: 0xff9c86, ground: 0x7a1428, intensity: 0.95 },
                fog: 0xa8556a, fogNear: 280, fogFar: 2100,
              },
              // A real city a long way down, and a thin layer of cloud between
              // it and the road - which is two separate things and needed the
              // `haze` hook to say so.
              //
              // The default `below` world was tried first and is the wrong
              // world for this: it is *one* thing, a cloud deck sitting on top
              // of the towers that are drowned in it, so the city can only ever
              // be at the cloud's own depth. Under a red sunset that came out
              // as a field of pale mesas standing on dark pillars - stone, not
              // sky, and no amount of retuning the cloud fixed it because the
              // problem was that the two layers were one. `downtown` puts a
              // proper skyline down there with lit windows, which is the thing
              // that actually reads as a city from 260 units up, and the haze
              // is then free to be thin and broken because it is not holding
              // anything up.
              below: { kind: 'downtown', deck: 300, reach: 900, step: 5,
                       coreX: 60, coreZ: 120, coreR: 380,
                       low: 34, spread: 58, rise: 115,
                       landmarkX: -40, landmarkZ: -60, landmarkH: 200,
                       tower: 0x2b1b33, window: 0xffc98a, floor: 0x160a16,
                       haze: { deck: 72, cover: 0.15, cloudStep: 20, puff: 1.2,
                               cloud: 0xffe4dc } } },
  // Sandy Cove: a coast road on hot sand. `shore` is what cuts the sea out of
  // the ground plane - see the ground block in buildTrack. Sand is the run-off
  // and the water is scenery, so falling in is a fall like any other.
  cove:     { road: 0x6b6f78, kerb: 0xfffaf0, kerb2: 0x2ab7c8,
              ground: 0xffe87a, rail: 0xfff6e8, prop: 0x3f7d4a, deco: 0xffb03a,
              fog: 0xcfe4ea,
              // Sparse. A beach is mostly empty sand, and the first pass was a
              // palm plantation. No `block` either - a green crate on a beach
              // reads as a crate on a beach.
              density: 0.035,
              props: { palm: 0.56, rock: 0.32, deadtree: 0.12 },
              // Kept in step with SHORE_Z / SHORE_AMP / SHORE_WAVE in tracks.py
              // by test_the_waterline_agrees_with_the_track: the road is
              // authored against this line, so a drift inland floods it.
              shore: { axis: 'z', at: 170, amp: 40, wave: 420, reach: 900,
                       sea: 0x1f7fa8, deep: 0x11527a, foam: 0x9fe0ea, drop: 3.0 },
              sky: {
                stops: [
                  [0.00, 0x8fb6c4], [0.40, 0xbfe0e8], [0.50, 0xd8eef2],
                  [0.58, 0xa8d6ee], [0.74, 0x6fb0e4], [1.00, 0x2f7ac4],
                ],
                glow: 0xfff0c8, glowStrength: 0.55, glowMode: 'radial', glowFocus: 7,
                sun: { az: 1.9, el: 0.62, color: 0xfff3d2, size: 260 },
                light: { color: 0xfff4de, intensity: 1.5,
                         dir: [Math.sin(1.9) * 0.6, 0.86, Math.cos(1.9) * 0.6] },
                // Bounce off pale sand, which is what makes everything here
                // look hot rather than merely bright.
                hemi: { sky: 0xd6efff, ground: 0xffdc72, intensity: 1.08 },
                fog: 0xcfe4ea, fogNear: 320, fogFar: 1600,
              } },
  // Cloudbreak: rock spires standing up through an overcast, a long way down.
  pillars:  { road: 0x4a4e5a, kerb: 0xf4f2ee, kerb2: 0xe07a3c,
              ground: 0x6d6154, rail: 0xf6f2ea, prop: 0x6a5c4c, deco: 0xffc247,
              fog: 0xc2cdd8,
              sky: {
                stops: [
                  [0.00, 0x9aa8b6], [0.42, 0xc4d2de], [0.50, 0xdce7f0],
                  [0.60, 0xa9c4de], [0.78, 0x6d97c2], [1.00, 0x3d6a9c],
                ],
                glow: 0xfff0d8, glowStrength: 0.5, glowMode: 'radial', glowFocus: 6,
                sun: { az: 0.7, el: 0.5, color: 0xfff2dc, size: 240 },
                light: { color: 0xfff0dc, intensity: 1.3,
                         dir: [Math.sin(0.7) * 0.7, 0.78, Math.cos(0.7) * 0.7] },
                // Bounce off cloud: bright and neutral, so undersides stay
                // readable instead of going black over a white floor.
                hemi: { sky: 0xdcebf8, ground: 0xb8c4d0, intensity: 1.0 },
                fog: 0xc2cdd8, fogNear: 380, fogFar: 2000,
              },
              // Fewer and much bigger. The first pass was a thicket of thin
              // poles: from road level a spire has to be wide enough to read as
              // rock and tall enough to stand *beside* you rather than under
              // you, or the track is not threaded between anything.
              // The deck is a long way down so you look *onto* it rather than
              // along it, and `cover` leaves real gaps - an even layer of
              // anything is the one thing cloud can never be. `floor` is
              // deliberately absent: see pillarsBelow.
              below: { kind: 'pillars', deck: 145, reach: 900,
                       cover: 0.34, cloud: 0xeef4fa,
                       puff: 2.1, cloudStep: 13,
                       spireStep: 12, spireDensity: 0.62, rise: 104, root: 110,
                       rock: 0x5f5244 } },
  // Spa-Francorchamps under the weather it is famous for. The only palette in
  // the pool with **no sun disc at all**: `sky.sun` is optional everywhere it is
  // read, so leaving it out gives a flat dome and nothing to cast from.
  //
  // Two things make an overcast read as overcast rather than as a grey bug.
  // First, the zenith is *darker* than the horizon - low cloud pressing down
  // with pale mist under it, which is the opposite of every other sky here and
  // is most of the Ardennes feeling. Second, almost all the light is `hemi`
  // rather than `light`: a heavy overcast is a sky-sized softbox, so the key is
  // weak, nearly straight down, and casts almost nothing. Turning the key up to
  // the 1.3-1.5 the sunny tracks use immediately reads as "sunny day, grey sky".
  //
  // `hemi.ground` is a deep forest green because that is the bounce here, and
  // it is what keeps the undersides of the cars and the armco from going flat
  // black under a sky with no warmth in it.
  spa:      { road: 0x3e444e, kerb: 0xf5f2ee, kerb2: 0xd23b32,
              ground: 0x4a6b3f, rail: 0xd8dde2,
              prop: 0x22482f, prop2: 0x1b3a28, deco: 0xe8b93c,
              // Gravel run-off. Cosmetic only - it is the same OFFROAD surface
              // the grass is, at the same drag, and nothing in the simulation
              // knows the difference. See `runoff` in buildTrack.
              gravel: 0xc7b48c,
              // Ground that follows the ribbon instead of one flat plate. Spa
              // is the only track that needs it and the only one that has it:
              // its road falls 63 units, and a plate at `track.ground` would be
              // a collidable ceiling over the whole second half of the lap.
              // `gravel` is how far from the road centre the run-off stays grit
              // before it turns to grass; `clear` is how far out nothing may
              // grow, which has to reach past the barrier or the forest comes
              // through it. `armco` is the backstop: far enough out that going
              // off costs you time on the gravel rather than the lap, close
              // enough that you never reach the trees.
              // `apron` is how far the swept run-off reaches from the road
              // centre before the height field takes over; `gravel` is where it
              // stops being grit inside that; `armco` is the barrier, which has
              // to sit inside the apron so it stands on swept ground rather
              // than on the grid; `clear` is how far out nothing may grow.
              terrain: { apron: 38, gravel: 21, armco: 27, clear: 44 },
              // Everything beside the road. Positions are fractions of the lap
              // rather than station indices, because the ribbon gets re-solved
              // for closure and that changes how many stations there are - the
              // corners stay where they are in the lap, so the stands do too.
              // `side` is the road's own right (+1) or left (-1).
              furniture: {
                armco: 26, concrete: 0xb9b6ae,
                board: { bg: '#12161c', fg: '#f4f1ea' },
                // The advertising, dealt round the lap in this order. Two in
                // three are this site's own games and the rest are the ones a
                // circuit actually carries; the list is long enough, and shuffled
                // enough, that no brand lands twice in the same braking zone.
                // Every name here has to be a key in SPONSORS or it comes out as
                // the plain fallback board.
                sponsors: ['CGOVIND.COM', 'TICKET TO RIDE', 'TACO BELL', 'RAT SCREW',
                           'KING OF TOKYO', 'MARLBORO', 'DRIVE', 'CGOVIND.COM',
                           'GO BIRDS', 'TICKET TO RIDE', 'RAT SCREW',
                           'PENN ENGINEERING', 'KING OF TOKYO', 'DRIVE', 'TACO BELL',
                           'CGOVIND.COM', 'RAT SCREW', 'MARLBORO', 'TICKET TO RIDE',
                           'GO BIRDS'],
                boardEvery: 26,
                // How tall a hoarding on the barrier stands. Width follows, at
                // the 4:1 the sign canvas is drawn to - so this is the only
                // number that sets how big the advertising is.
                boardH: 2.6,
                // Each stand wears its sponsor's colours - see SPONSORS. Any of
                // these that turns out to sit across another part of the lap is
                // dropped by `stand` rather than drawn through it, which is what
                // happened to the one that used to be behind the pits: twenty
                // units of seating laid over the exit of La Source.
                stands: [
                  // The main stand down the pit straight, opposite the pits.
                  { at: [0.006, 0.068], side: -1, tiers: 9, text: 'CGOVIND.COM',
                    seat: 0x1a56ff, trim: 0xf5b301 },
                  // Round the outside of La Source.
                  { at: [0.080, 0.101], side: -1, tiers: 7, text: 'PENN ENGINEERING',
                    seat: 0x990000, trim: 0x011f5b },
                  // The hillside at Eau Rouge and Raidillon, which is where
                  // everybody actually stands.
                  { at: [0.136, 0.172], side: -1, tiers: 10, text: 'DRIVE',
                    seat: 0x2f333c, trim: 0xc0182b },
                  { at: [0.322, 0.352], side: -1, tiers: 6, text: 'KING OF TOKYO',
                    seat: 0x5c2678, trim: 0xf2c94c },
                  { at: [0.680, 0.712], side: -1, tiers: 6, text: 'TICKET TO RIDE',
                    seat: 0x6b4226, trim: 0xc0182b },
                  // The Bus Stop, the last corner before the line.
                  { at: [0.938, 0.962], side: -1, tiers: 8, text: 'RAT SCREW',
                    seat: 0xb8860b, trim: 0x3f2311 },
                ],
                pits: { at: [0.004, 0.072], side: 1 },
                spans: [
                  { at: 0.0045, lights: true, text: 'DRIVE', clear: 9.5 },
                  { at: 0.250, deck: true, clear: 10.5, text: 'CGOVIND.COM' },
                ],
              },
              fog: 0xc2cbd2,
              // The Ardennes is a pine forest, so this is the densest scatter
              // in the pool and almost all of it is big.
              density: 0.34,
              props: { bigpine: 0.5, conifer: 0.34, deadtree: 0.06, rock: 0.10 },
              sky: {
                stops: [
                  [0.00, 0x8d959c], [0.42, 0xb6bfc6], [0.50, 0xcdd4d9],
                  [0.58, 0xbcc4cb], [0.74, 0xa2acb6], [1.00, 0x7f8b97],
                ],
                // Broken cloud, shaded onto the dome rather than built out of
                // boxes - see skyDome. Without it a flat grey dome reads as an
                // empty background rather than as weather.
                clouds: { scale: 2.9, amount: 1.5, dark: 0x67727f,
                          light: 0xe9eef3, lit: 0.45 },
                // No `sun`, and so no `glow` either - there is nothing for the
                // glow to sit around, and a halo with no disc under it reads as
                // a smudge on the dome.
                light: { color: 0xdfe6ec, intensity: 0.7, dir: [0.3, 0.94, 0.16] },
                hemi: { sky: 0xd2dae0, ground: 0x3f5236, intensity: 1.2 },
                // Closer than the sunny tracks. Mist in the trees is the point,
                // and on a 3167-unit circuit it also keeps the far side of the
                // lap from being visible across the infield.
                fog: 0xc2cbd2, fogNear: 240, fogFar: 1050,
              } },
  // The only track in the pool that goes indoors. `building` is the shell, and
  // the four numbers that place it are a second copy of `SHELL_X`/`SHELL_Z`/
  // `SHELL_CEIL` in tracks.py - deliberately, for the reason the comment there
  // gives, and pinned to them by `test_the_costco_shell_agrees_with_the_track`.
  //
  // Nothing else in a palette is load bearing on the layout the way these are:
  // the road is authored to pass through the doorways these walls imply, so
  // moving one of them by hand moves a wall across a road.
  costco:   { road: 0x585e66, kerb: 0xf4f4f2, kerb2: 0xe31837,
              ground: 0x6b6e74, rail: 0xd8dde2,
              // `prop` is the trestle under raised road, and on this track that
              // is the rooftop deck - so the deck comes to stand on steel
              // columns for free, which is what a rooftop car park stands on.
              prop: 0x9aa0a8, prop2: 0x7d838b, deco: 0x0071ce,
              // No scatter. The vocabulary is conifer/bigpine/deadtree/palm/
              // rock/block and not one of them belongs in a Costco car park, so
              // everything outside the walls is placed by `addBuilding` instead.
              density: 0,
              fog: 0xc9d3dc,
              building: {
                x: [250, 490], z: [-110, 78], ceil: 15,
                // Half-width of a doorway, on the wall. It has to be generously
                // wider than the road: the chase camera trails the car by up to
                // 11.6 units and swings with it, so it comes through the same
                // hole a moment later and from slightly off to one side.
                door: 24,
                // Concrete outside, painted block inside, and the steel that the
                // frame, the roof joists and the racking are all made of.
                wall: 0xdcd8d0, inner: 0xcfcbc4, steel: 0x8e949c,
                floor: 0x74777d,
                // Drawn unlit, so they read as lit rather than as pale grey
                // panels: the daylight panels in the roof, the fluorescent
                // battens under it, and the glow off the refrigerated cases.
                skylight: 0xeef6ff, strip: 0xfff2d8, chill: 0xbfe4f2,
                // Racking. Laid at half an aisle either side of every straight
                // aisle station, which is the midpoint between two aisles - so
                // it is derived from the road rather than authored beside it and
                // cannot drift when a leg changes length. `bay` is how long one
                // bay of shelving is, `h` how tall it stands.
                rack: { off: 14, h: 9.5, pallet: 0xb08657 },
                // The wordmark. Positions are not authored: a facade sign goes
                // over each doorway the road cuts, so it is always over the door
                // however the layout moves, and one more stands on the roof
                // parapet where the deck can read it.
                sign: { facade: 'COSTCO WHOLESALE', roof: 'COSTCO WHOLESALE',
                        food: '$1.50 HOT DOG' },
                lot: { line: 0xe8e8e4 },
              },
              sky: {
                // A big flat afternoon over a big flat car park. The sun is well
                // up, so the glow is `radial` - a halo round the disc - and not
                // the horizon smear a sunrise wants.
                stops: [
                  [0.00, 0xa8bccb], [0.42, 0xc8dae7], [0.50, 0xdcebf5],
                  [0.60, 0xa9c9e6], [0.78, 0x74a5da], [1.00, 0x4478c4],
                ],
                glow: 0xfff6e0, glowStrength: 0.6, glowMode: 'radial', glowFocus: 5,
                sun: { az: 1.15, el: 0.52, color: 0xfffaf0, size: 330 },
                light: { color: 0xfff6e8, intensity: 1.34,
                         dir: [Math.sin(1.15) * 0.62, 0.78, Math.cos(1.15) * 0.62] },
                // The bounce, and the single highest-leverage number here: over
                // concrete and asphalt it is a neutral grey, which is what keeps
                // the undersides of the car and the roof steel from picking up a
                // colour the site does not have.
                hemi: { sky: 0xdfe9f2, ground: 0x6a6d72, intensity: 0.95 },
                // Far enough out that the warehouse is never hidden by haze from
                // the far side of its own car park.
                fog: 0xc9d3dc, fogNear: 300, fogFar: 1400,
              } },
};

export function palette(track) {
  return PALETTES[track.palette] || PALETTES.sunrise;
}

// ---------------------------------------------------------------------------
// Triangle soup + spatial hash
// ---------------------------------------------------------------------------

export class Collider {
  constructor(cell) {
    this.cell = cell;
    this.v = [];        // 9 floats per triangle
    this.n = [];        // 3 floats per triangle (unit normal)
    this.k = [];        // KIND per triangle
    this.hash = new Map();
  }

  add(a, b, c, kind) {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const len = Math.hypot(nx, ny, nz);
    if (len < 1e-9) return;
    nx /= len; ny /= len; nz /= len;
    const i = this.k.length;
    this.v.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
    this.n.push(nx, ny, nz);
    this.k.push(kind);
    // Register in every XZ hash cell the triangle's footprint touches.
    const s = this.cell;
    const x0 = Math.floor(Math.min(a[0], b[0], c[0]) / s), x1 = Math.floor(Math.max(a[0], b[0], c[0]) / s);
    const z0 = Math.floor(Math.min(a[2], b[2], c[2]) / s), z1 = Math.floor(Math.max(a[2], b[2], c[2]) / s);
    for (let x = x0; x <= x1; x++) {
      for (let z = z0; z <= z1; z++) {
        const key = x * 73856093 ^ z * 19349663;
        let arr = this.hash.get(key);
        if (!arr) this.hash.set(key, arr = []);
        arr.push(i);
      }
    }
  }

  addQuad(a, b, c, d, kind) {
    this.add(a, b, c, kind);
    this.add(a, c, d, kind);
  }

  finish() {
    this.v = new Float32Array(this.v);
    this.n = new Float32Array(this.n);
    this.k = new Uint8Array(this.k);
    // Visited-set for queries, as a stamp array rather than a Set: the ground
    // query runs 120 times a second and allocating there is the one place in
    // this project where GC pressure would actually show up as stutter.
    this._mark = new Int32Array(this.k.length);
    this._gen = 0;
    return this;
  }

  // Triangle indices in the 3x3 block of hash cells around (x,z).
  *near(x, z) {
    const s = this.cell;
    const cx = Math.floor(x / s), cz = Math.floor(z / s);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dz = -1; dz <= 1; dz++) {
        const arr = this.hash.get((cx + dx) * 73856093 ^ (cz + dz) * 19349663);
        if (arr) yield arr;
      }
    }
  }

  /**
   * Closest driveable surface under a point, in that point's own frame.
   *
   * "Under" means the surface normal has to agree with the car's up vector, which
   * is what lets the same query work upside down inside a loop: at the top of a
   * loop the road's normal points down, and so does the car's up.
   *
   * Returns {hit, px,py,pz, nx,ny,nz, dist, kind} - dist measured along the
   * triangle normal, so it is signed and usable as a penetration depth.
   */
  ground(x, y, z, ux, uy, uz, maxDist) {
    let best = -1, bestD = Infinity, bestAlong = 0;
    let bqx = 0, bqy = 0, bqz = 0;
    const gen = ++this._gen, mark = this._mark;
    for (const arr of this.near(x, z)) {
      for (let ii = 0; ii < arr.length; ii++) {
        const i = arr[ii];
        if (mark[i] === gen) continue;
        mark[i] = gen;
        if (this.k[i] === KIND.WALL) continue;
        const nx = this.n[i * 3], ny = this.n[i * 3 + 1], nz = this.n[i * 3 + 2];
        if (nx * ux + ny * uy + nz * uz < 0.15) continue;   // facing away from us
        closestOnTri(x, y, z, this.v, i * 9, Q);
        const dx = x - Q[0], dy = y - Q[1], dz = z - Q[2];
        const d = Math.hypot(dx, dy, dz);
        if (d > maxDist) continue;
        // Height above the surface along its own normal. Slightly negative is a
        // penetration we still want to see (so we can push out of it); deeply
        // negative means we are behind the surface, not on it.
        const along = dx * nx + dy * ny + dz * nz;
        if (along < -0.8) continue;
        // Ranking, not raw distance:
        //  - road beats grass on a near-tie, so a car straddling a kerb is
        //    treated as on-track instead of flickering between grip levels;
        //  - a surface whose normal agrees with where the car already thinks
        //    "up" is beats one that does not. Where a track passes over itself -
        //    a loop's two halves, a bridge - both surfaces can be inside the
        //    probe, and picking the one the car is aligned with is what stops it
        //    snapping onto the wrong deck.
        const agree = nx * ux + ny * uy + nz * uz;
        const score = d - agree * 0.8 + (this.k[i] === KIND.OFFROAD ? 0.35 : 0);
        if (score < bestD) { bestD = score; best = i; bestAlong = along; bqx = Q[0]; bqy = Q[1]; bqz = Q[2]; }
      }
    }
    if (best < 0) return HIT_MISS;
    HIT.hit = true; HIT.px = bqx; HIT.py = bqy; HIT.pz = bqz;
    HIT.nx = this.n[best * 3]; HIT.ny = this.n[best * 3 + 1]; HIT.nz = this.n[best * 3 + 2];
    HIT.dist = bestAlong; HIT.kind = this.k[best];
    return HIT;
  }

  /** Walls overlapping a sphere; calls back with (nx,ny,nz,depth). */
  walls(x, y, z, radius, cb) {
    const gen = ++this._gen, mark = this._mark;
    for (const arr of this.near(x, z)) {
      for (let ii = 0; ii < arr.length; ii++) {
        const i = arr[ii];
        if (mark[i] === gen) continue;
        mark[i] = gen;
        if (this.k[i] !== KIND.WALL) continue;
        closestOnTri(x, y, z, this.v, i * 9, Q);
        let dx = x - Q[0], dy = y - Q[1], dz = z - Q[2];
        const d = Math.hypot(dx, dy, dz);
        if (d >= radius) continue;
        if (d < 1e-4) {
          dx = this.n[i * 3]; dy = this.n[i * 3 + 1]; dz = this.n[i * 3 + 2];
        } else { dx /= d; dy /= d; dz /= d; }
        cb(dx, dy, dz, radius - d);
      }
    }
  }
}

// Scratch space for the queries above, reused rather than reallocated.
const Q = [0, 0, 0];
const HIT = { hit: true, px: 0, py: 0, pz: 0, nx: 0, ny: 1, nz: 0, dist: 0, kind: 0 };
const HIT_MISS = { hit: false, dist: Infinity, kind: 0, nx: 0, ny: 1, nz: 0 };

// Ericson, Real-Time Collision Detection - closest point on a triangle.
// Writes into `out` to keep this allocation-free.
function closestOnTri(px, py, pz, V, o, out) {
  const ax = V[o], ay = V[o + 1], az = V[o + 2];
  const bx = V[o + 3], by = V[o + 4], bz = V[o + 5];
  const cx = V[o + 6], cy = V[o + 7], cz = V[o + 8];
  const abx = bx - ax, aby = by - ay, abz = bz - az;
  const acx = cx - ax, acy = cy - ay, acz = cz - az;
  const apx = px - ax, apy = py - ay, apz = pz - az;
  const put = (x, y, z) => { out[0] = x; out[1] = y; out[2] = z; return out; };
  const d1 = abx * apx + aby * apy + abz * apz;
  const d2 = acx * apx + acy * apy + acz * apz;
  if (d1 <= 0 && d2 <= 0) return put(ax, ay, az);
  const bpx = px - bx, bpy = py - by, bpz = pz - bz;
  const d3 = abx * bpx + aby * bpy + abz * bpz;
  const d4 = acx * bpx + acy * bpy + acz * bpz;
  if (d3 >= 0 && d4 <= d3) return put(bx, by, bz);
  const vc = d1 * d4 - d3 * d2;
  if (vc <= 0 && d1 >= 0 && d3 <= 0) {
    const v = d1 / (d1 - d3);
    return put(ax + abx * v, ay + aby * v, az + abz * v);
  }
  const cpx = px - cx, cpy = py - cy, cpz = pz - cz;
  const d5 = abx * cpx + aby * cpy + abz * cpz;
  const d6 = acx * cpx + acy * cpy + acz * cpz;
  if (d6 >= 0 && d5 <= d6) return put(cx, cy, cz);
  const vb = d5 * d2 - d1 * d6;
  if (vb <= 0 && d2 >= 0 && d6 <= 0) {
    const w = d2 / (d2 - d6);
    return put(ax + acx * w, ay + acy * w, az + acz * w);
  }
  const va = d3 * d6 - d5 * d4;
  if (va <= 0 && (d4 - d3) >= 0 && (d5 - d6) >= 0) {
    const w = (d4 - d3) / ((d4 - d3) + (d5 - d6));
    return put(bx + (cx - bx) * w, by + (cy - by) * w, bz + (cz - bz) * w);
  }
  const denom = 1 / (va + vb + vc);
  const v = vb * denom, w = vc * denom;
  return put(ax + abx * v + acx * w, ay + aby * v + acy * w, az + abz * v + acz * w);
}

// ---------------------------------------------------------------------------
// Mesh building
// ---------------------------------------------------------------------------

export class MeshBuf {
  constructor() { this.pos = []; this.col = []; }
  tri(a, b, c, color) {
    this.pos.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
    const r = ((color >> 16) & 255) / 255, g = ((color >> 8) & 255) / 255, bl = (color & 255) / 255;
    for (let i = 0; i < 3; i++) this.col.push(r, g, bl);
  }
  quad(a, b, c, d, color) { this.tri(a, b, c, color); this.tri(a, c, d, color); }
  /** One colour per corner, so a face can carry a gradient across itself.
   *
   *  `tri` above writes the same colour to all three vertices, which is why the
   *  `fade` livery is ten flat strips rather than a ramp - fine there, where the
   *  strips are 0.34 long and nobody counts them, and not fine for the garage's
   *  studio floor, which is metres across and bands visibly. The attribute is
   *  the one `toGeometry` already publishes; only the writing changes.
   */
  triV(a, b, c, ca, cb, cc) {
    this.pos.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
    for (const k of [ca, cb, cc]) {
      this.col.push(((k >> 16) & 255) / 255, ((k >> 8) & 255) / 255, (k & 255) / 255);
    }
  }
  quadV(a, b, c, d, ca, cb, cc, cd) {
    this.triV(a, b, c, ca, cb, cc); this.triV(a, c, d, ca, cc, cd);
  }
  box(cx, cy, cz, hx, hy, hz, color) {
    const P = (sx, sy, sz) => [cx + sx * hx, cy + sy * hy, cz + sz * hz];
    const v = [P(-1,-1,-1), P(1,-1,-1), P(1,-1,1), P(-1,-1,1),
               P(-1,1,-1), P(1,1,-1), P(1,1,1), P(-1,1,1)];
    this.quad(v[4], v[7], v[6], v[5], color);   // top
    this.quad(v[0], v[1], v[2], v[3], color);   // bottom
    this.quad(v[0], v[4], v[5], v[1], color);
    this.quad(v[1], v[5], v[6], v[2], color);
    this.quad(v[2], v[6], v[7], v[3], color);
    this.quad(v[3], v[7], v[4], v[0], color);
  }
  /** The accumulated triangles as a geometry, for a caller supplying its own
   *  material - or several meshes sharing one buffer, which is how a wheel rim
   *  is four wheels' worth of rim without being four geometries. */
  toGeometry() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.col, 3));
    g.computeVertexNormals();
    return g;
  }
  toMesh(material) { return new THREE.Mesh(this.toGeometry(), material); }
}

const THICK = 0.9;      // depth of the tarmac slab under the road surface
const RAIL_H = 1.15;    // barrier height
const KERB_W = 0.7;     // width of the painted stripe along each edge

export function buildTrack(track, T) {
  const CELL = T.CELL;
  const pal = palette(track);
  const group = new THREE.Group();
  const col = new Collider(CELL);
  const solid = new MeshBuf();     // flat-shaded, receives light
  const bright = new MeshBuf();    // unlit accents: kerbs, gate banners
  const soft = new MeshBuf();      // lit but translucent: cloud
  const line = track.line;
  let minY = Infinity, maxY = -Infinity;
  const bbox = { x0: Infinity, x1: -Infinity, z0: Infinity, z1: -Infinity };

  function note(p) {
    minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]);
    bbox.x0 = Math.min(bbox.x0, p[0]); bbox.x1 = Math.max(bbox.x1, p[0]);
    bbox.z0 = Math.min(bbox.z0, p[2]); bbox.z1 = Math.max(bbox.z1, p[2]);
  }

  // Walls get ONE collision quad, not two. The wall query derives its push-out
  // direction from the closest point on the triangle rather than from the stored
  // normal, so a single-sided quad stops a car arriving from either side. Adding
  // the back face as well used to make every contact fire twice with opposing
  // normals, which cancelled the car's velocity and scrubbed its speed twice per
  // step - it is what made rails inside a corkscrew undrivable. The *mesh* still
  // gets both faces, so nothing looks hollow.
  //
  // The offset is along the road's own normal rather than world up, so a barrier
  // on the inverted part of a corkscrew still stands off the road.
  function wallStrip(p0, p1, n0, n1, height, color) {
    const at = [p0[0] + n0[0] * height, p0[1] + n0[1] * height, p0[2] + n0[2] * height];
    const bt = [p1[0] + n1[0] * height, p1[1] + n1[1] * height, p1[2] + n1[2] * height];
    col.addQuad(p0, p1, bt, at, KIND.WALL);
    solid.quad(p0, p1, bt, at, color);
    solid.quad(at, bt, p1, p0, color);
  }

  // A drawn box that is also solid: the five faces a car can reach, as WALL.
  // Same single-sided rule as wallStrip - the wall query works out its push-out
  // direction from the closest point on the triangle, so one face per side is
  // both necessary and sufficient.
  function solidBox(cx, cy, cz, hx, hy, hz, color) {
    solid.box(cx, cy, cz, hx, hy, hz, color);
    const P = (sx, sy, sz) => [cx + sx * hx, cy + sy * hy, cz + sz * hz];
    const v = [P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1),
               P(-1, 1, -1), P(1, 1, -1), P(1, 1, 1), P(-1, 1, 1)];
    col.addQuad(v[4], v[7], v[6], v[5], KIND.WALL);   // top
    col.addQuad(v[0], v[4], v[5], v[1], KIND.WALL);
    col.addQuad(v[1], v[5], v[6], v[2], KIND.WALL);
    col.addQuad(v[2], v[6], v[7], v[3], KIND.WALL);
    col.addQuad(v[3], v[7], v[4], v[0], KIND.WALL);
  }

  // Where the surface is at lateral `u` (-1..+1) across a station. A flat
  // station is the plane it always was; a profiled one - a half-pipe, a banked
  // wall - lifts the point along its own normal by the station's baked samples.
  // Those samples come from tracks.py so there is exactly one description of
  // any track's cross-section, and it is the one the lap-time model measured.
  const riseAt = (e, u) => {
    const pf = e.pf;
    if (!pf) return 0;
    if (u <= pf[0][0]) return pf[0][1];
    for (let j = 0; j + 1 < pf.length; j++) {
      const [u0, r0] = pf[j], [u1, r1] = pf[j + 1];
      if (u <= u1) return u1 <= u0 ? r0 : r0 + (r1 - r0) * (u - u0) / (u1 - u0);
    }
    return pf[pf.length - 1][1];
  };
  const surf = (e, u) => {
    const r = riseAt(e, u);
    return [e.p[0] + e.lat[0] * u * e.hw + e.n[0] * r,
            e.p[1] + e.lat[1] * u * e.hw + e.n[1] * r,
            e.p[2] + e.lat[2] * u * e.hw + e.n[2] * r];
  };
  // The lateral samples to build a pair of stations across. A flat pair is the
  // two edges it always was - one quad, exactly as before - so nothing about a
  // track without pipes changes, down to the vertex order.
  const spanOf = (a, b) => {
    const pf = a.pf || b.pf;
    if (pf) return pf.map(s => s[0]);
    // Rainbow Road shades its road across the width as well as along it, and a
    // single quad has one colour, so its flat sections are split into lanes
    // purely to have something to put a gradient on. Every other track gets the
    // two edges it always had - one quad, same vertex order, no change at all.
    if (pal.rainbow) {
      const n = pal.rainbowLanes || 8;
      return Array.from({ length: n + 1 }, (_, k) => -1 + 2 * k / n);
    }
    return [-1, 1];
  };

  // Edge points of the road at a station, and the same points lifted a hair
  // along the normal for the painted kerb (which is drawn, never collided).
  const edge = (e, s) => surf(e, s);
  const inset = (e, s, d) => {
    const u = s * (e.hw - d) / e.hw;
    const p = surf(e, u);
    return [p[0] + e.n[0] * 0.05, p[1] + e.n[1] * 0.05, p[2] + e.n[2] * 0.05];
  };
  const sink = (p, e, d) => [p[0] - e.n[0] * d, p[1] - e.n[1] * d, p[2] - e.n[2] * d];

  // Rainbow Road's surface is drawn unlit and swept through the spectrum along
  // its length, so it glows against a violet sky instead of being dimmed by a
  // key light that is barely there.
  //
  // Two gradients, not one. Along the road `pal.rainbow` degrees of hue per
  // station gives a slow wash - hard bands were tried first and are too loud,
  // and a *fast* per-station sweep was tried before that and read as a flat
  // carpet, because a gradient with no shading across it has no shape. Across
  // the road the lightness falls off toward the kerbs and the saturation comes
  // up, which is what gives the ribbon a lit centre and a deep edge; the small
  // hue skew either side is the iridescence, and it is what stops the two
  // halves of the road looking like one flat colour.
  const roadColor = (i, u) => {
    if (!pal.rainbow) return i % 8 < 4 ? pal.road : shade(pal.road, 0.045);
    const a = Math.abs(u);
    const h = (i * pal.rainbow) / 360 + 0.038 * u;
    return hsl((h % 1 + 1) % 1, Math.min(1, 0.70 + 0.24 * a), 0.62 - 0.19 * a * a);
  };
  const roadBuf = pal.rainbow ? bright : solid;

  // ---- boost pads ---------------------------------------------------------
  // A pad has to be readable from far enough back to aim at, on a road whose
  // colour is the track's business - so it is drawn rather than tinted: a dark
  // inset panel to lift it off the tarmac, and chevrons pointing the way you
  // are going. Both go in the `bright` buffer, so a pad glows on Spiral
  // Ascent's midnight road exactly as it does in daylight and needs no light of
  // its own.
  //
  // Everything is built in the station pair's own (u, s) space and lifted along
  // the *road's* normal, not world up, which is what makes a pad on the wall of
  // a loop lie flat on the wall.
  const PAD_LIFT = 0.03, CHEV_LIFT = 0.05;
  const PAD_LANES = 8;          // lateral strips a chevron is drawn from
  // A chevron is drawn across CHEV_SPAN stations rather than between one pair
  // of them, and that is the whole reason it reads as an arrow. Stations are
  // 3.5 units apart and the road is 12 to 14 wide, so a V confined to a single
  // gap can rake its arms back by at most a couple of units across six of
  // width - which from behind the car is a *straight line*, drawn three times.
  // Over two gaps the tip is four units up the road from the arms and it is
  // unmistakably pointing somewhere.
  const CHEV_SPAN = 2;          // stations a single chevron is drawn across
  const CHEV_EVERY = 2;         // stations between one chevron and the next
  const padPt = (a, b, u, s, lift) => {
    const p = surf(a, u), q = surf(b, u);
    const out = [0, 0, 0];
    for (let k = 0; k < 3; k++) {
      out[k] = p[k] + (q[k] - p[k]) * s
               + (a.n[k] + (b.n[k] - a.n[k]) * s) * lift;
    }
    return out;
  };
  function padStrip(i) {
    const a = line[i], b = line[i + 1];
    const base = pal.padBase != null ? pal.padBase : 0x101828;
    const glow = pal.pad != null ? pal.pad : 0x62f0ff;
    // The panel stops short of the kerb, or it fights the painted stripe that
    // is already there and the edge of the pad reads as a lane marking.
    const w = 0.86;
    bright.quad(padPt(a, b, -w, 0, PAD_LIFT), padPt(a, b, w, 0, PAD_LIFT),
                padPt(a, b, w, 1, PAD_LIFT), padPt(a, b, -w, 1, PAD_LIFT), base);
    if (i % CHEV_EVERY) return;
    // The whole chevron has to fit inside the pad, or the arms of the last one
    // hang off the end and there is a cyan V painted on ordinary road.
    for (let k = 0; k <= CHEV_SPAN; k++) if (!line[i + k] || !line[i + k].bp) return;
    const far = line[i + CHEV_SPAN];
    // A V pointing the way you are travelling: the tip is furthest along the
    // road and the arms rake back toward the kerbs. Drawn as lateral strips
    // because a quad has one colour and the shape is easier to keep on the
    // surface than to fold out of two big triangles.
    const TIP = 0.92, RAKE = 0.62, THICK_S = 0.17;
    for (let j = 0; j < PAD_LANES; j++) {
      const u0 = -w + 2 * w * j / PAD_LANES, u1 = -w + 2 * w * (j + 1) / PAD_LANES;
      const s0 = TIP - Math.abs(u0) * RAKE, s1 = TIP - Math.abs(u1) * RAKE;
      bright.quad(padPt(a, far, u0, s0, CHEV_LIFT), padPt(a, far, u1, s1, CHEV_LIFT),
                  padPt(a, far, u1, s1 - THICK_S, CHEV_LIFT),
                  padPt(a, far, u0, s0 - THICK_S, CHEV_LIFT), glow);
    }
  }

  // ---- the road: one strip of quads between consecutive stations -----------
  //
  // This loop is the entire track geometry. Everything the old grid version
  // needed a separate branch for - straights, corners, ramps, kicker lips,
  // loops, bridges - is the same four vertices here, because the stations
  // already carry the position, the normal, the lateral axis and the width.
  //
  // A profiled station (a half-pipe, a banked wall) is the one thing that is
  // not four vertices: it is the quads between one station's cross-section
  // samples and the next one's. That is still this loop and still ROAD quads,
  // which is why a car can drive up the wall of a pipe with nothing in the
  // physics knowing pipes exist - the ground query finds the closest surface
  // and steering is applied about its normal, exactly as it is inside a loop.
  for (let i = 0; i + 1 < line.length; i++) {
    const a = line[i], b = line[i + 1];
    if (a.air || b.air) continue;          // a gap: no road, by construction

    const aL = edge(a, -1), aR = edge(a, 1);
    const bL = edge(b, -1), bR = edge(b, 1);
    const span = spanOf(a, b);
    for (let j = 0; j + 1 < span.length; j++) {
      const u0 = span[j], u1 = span[j + 1];
      const p0 = surf(a, u0), p1 = surf(a, u1);
      const q0 = surf(b, u0), q1 = surf(b, u1);
      // Wound so the surface normal comes out along `n`, which is what lets the
      // ground query find the road while the car is upside down inside a
      // corkscrew - or high on the wall of a pipe.
      col.addQuad(p0, p1, q1, q0, a.bp ? KIND.BOOST : KIND.ROAD);
      roadBuf.quad(p0, p1, q1, q0, roadColor(i, (u0 + u1) / 2));
    }
    if (a.bp) padStrip(i);
    note(aL); note(aR);

    // Underside: the slab, so the track reads as solid edge-on and from below.
    // It follows the cross-section rather than cutting straight across, or a
    // half-pipe seen from below is a flat plate with a trough floating in it.
    const aLu = sink(aL, a, THICK), aRu = sink(aR, a, THICK);
    const bLu = sink(bL, b, THICK), bRu = sink(bR, b, THICK);
    const under = shade(pal.road, -0.34);
    for (let j = 0; j + 1 < span.length; j++) {
      const u0 = span[j], u1 = span[j + 1];
      solid.quad(sink(surf(b, u0), b, THICK), sink(surf(b, u1), b, THICK),
                 sink(surf(a, u1), a, THICK), sink(surf(a, u0), a, THICK), under);
    }
    solid.quad(aL, bL, bLu, aLu, shade(pal.road, -0.16));   // left flank
    solid.quad(bR, aR, aRu, bRu, shade(pal.road, -0.16));   // right flank

    // Kerbs: painted stripes just inside each edge, alternating colour.
    const stripe = (i % 4 < 2) ? pal.kerb : pal.kerb2;
    bright.quad(inset(a, -1, 0), inset(b, -1, 0),
                inset(b, -1, KERB_W), inset(a, -1, KERB_W), stripe);
    bright.quad(inset(a, 1, KERB_W), inset(b, 1, KERB_W),
                inset(b, 1, 0), inset(a, 1, 0), stripe);

    if (a.wl && b.wl) wallStrip(aL, bL, a.n, b.n, RAIL_H, pal.rail);
    if (a.wr && b.wr) wallStrip(aR, bR, a.n, b.n, RAIL_H, pal.rail);

    // Where the road stops dead - the lip of a jump - paint the end face so you
    // can see exactly where it goes.
    if (i + 2 < line.length && line[i + 2].air) {
      solid.quad(bL, bR, bRu, bLu, shade(pal.deco, -0.1));
      bright.quad(inset(b, -1, 0), inset(b, 1, 0),
                  sink(inset(b, 1, 0), b, 0.4), sink(inset(b, -1, 0), b, 0.4), pal.deco);
    }
  }

  // ---- supports -----------------------------------------------------------
  // A pair of legs every so often, so an elevated road reads as built rather
  // than floating. Sparse on purpose: one every three stations turned every
  // raised section into a picket fence you could not see the track through.
  const groundY = track.ground != null ? track.ground : null;
  // Built here rather than down in the ground block because the supports, the
  // scenery and the trackside furniture all have to stand on it.
  const GRASS_DROP = 1.2;          // how far the run-off sits under the tarmac
  const terrain = (groundY != null && pal.terrain)
    ? buildTerrain(track, CELL, bbox,
                   pal.terrain.apron != null ? pal.terrain.apron : 34, GRASS_DROP)
    : null;
  let armcoRuns = [];              // barrier polylines, for hanging boards on
  const signs = [];                // textured sponsor boards, batched per word
  // Is some lower part of the track underneath station `i`? The same question
  // `crossings` in tracks.py asks, asked here so a support can decline to stand
  // on a road. Neighbours along the ribbon are skipped, or every station is
  // "over" the one before it.
  const overRoad = (i) => {
    const e = line[i];
    const skip = Math.ceil(30 / (track.station || 3.5)) + 1;
    for (let j = 0; j < line.length; j++) {
      if (Math.abs(j - i) <= skip) continue;
      const o = line[j];
      if (o.air || o.p[1] > e.p[1] - 2) continue;
      const dx = o.p[0] - e.p[0], dz = o.p[2] - e.p[2];
      if (Math.hypot(dx, dz) < e.hw + o.hw + 2) return true;
    }
    return false;
  };
  const legEvery = Math.max(4, Math.round(26 / (track.station || 3.5)));
  for (let i = Math.floor(legEvery / 2); i < line.length; i += legEvery) {
    const e = line[i];
    if (e.air || e.fix || e.pf) continue;       // nor under a pipe, whose edges
                                                // are walls rather than a deck
    if (e.n[1] < 0.7) continue;                 // not under a banked or rolled bit
    // On a terrain track the ground is right under the road, so `drop` comes
    // out around the ride height and the `< 1.5` test below skips the legs
    // entirely - which is correct: the road there is built on a hillside, not
    // held up in the air.
    const base = terrain ? terrain.height(e.p[0], e.p[2])
               : groundY != null ? groundY : e.p[1] - 16;
    const drop = e.p[1] - THICK - base;
    if (drop < 1.5) continue;
    // A trestle stands on the ground, never on another part of the track. Until
    // one track put a car park on its own roof, road was only ever over *ground*
    // and this could not come up; the rooftop deck flies over four aisles, and
    // its legs came down straddling roads you drive along - a pair of pillars in
    // the middle of an aisle, and not even solid ones, since supports are drawn
    // and never collided. Where the deck is over floor the legs are right, so
    // this drops the pair rather than the whole run.
    if (overRoad(i)) continue;
    for (const s of [-1, 1]) {
      const p = edge(e, s * 0.7);
      solid.box(p[0], base + drop / 2, p[2], 0.62, drop / 2, 0.62,
                shade(pal.prop, -0.08));
    }
    // a cross-beam under the deck so the pair reads as one trestle
    const l = edge(e, -0.7), r = edge(e, 0.7);
    solid.box((l[0] + r[0]) / 2, e.p[1] - THICK - 0.5, (l[2] + r[2]) / 2,
              Math.abs(r[0] - l[0]) / 2 + 0.4, 0.32,
              Math.abs(r[2] - l[2]) / 2 + 0.4, shade(pal.prop, -0.2));
  }
  // ---- gates --------------------------------------------------------------
  // Positions come from tracks.py, so the thing you drive through and the thing
  // the timer watches can never disagree.
  const gates = [];
  for (const g of track.gates) {
    const color = g.kind === 'start' ? 0xffffff
                : g.kind === 'finish' ? 0xe8453c : pal.deco;
    const st = line[g.si] || { n: [0, 1, 0] };
    const n = st.n;
    gates.push({ kind: g.kind, gi: g.gi, p: g.p, f: g.f, r: g.r, hw: g.hw, y: g.p[1] });
    // The posts are solid, so clipping a checkpoint on the way through costs you
    // the same as clipping a barrier. They sit just *outside* the kerb rather
    // than on it, so the full width of the road is still yours to use.
    const POST = 0.34;
    for (const s of [-1, 1]) {
      const off = s * (g.hw + POST + 0.1);
      const post = [g.p[0] + g.r[0] * off, g.p[1] + g.r[1] * off, g.p[2] + g.r[2] * off];
      solidBox(post[0] + n[0] * 1.9, post[1] + n[1] * 1.9, post[2] + n[2] * 1.9,
               POST, 1.9, POST, color);
    }
    const lift = (p, d) => [p[0] + n[0] * d, p[1] + n[1] * d, p[2] + n[2] * d];
    const L = [g.p[0] - g.r[0] * g.hw, g.p[1] - g.r[1] * g.hw, g.p[2] - g.r[2] * g.hw];
    const R = [g.p[0] + g.r[0] * g.hw, g.p[1] + g.r[1] * g.hw, g.p[2] + g.r[2] * g.hw];
    bright.quad(lift(L, 3.4), lift(R, 3.4), lift(R, 4.4), lift(L, 4.4), color);
    if (g.kind !== 'cp') {
      const w = 0.9;
      const back = (p) => [p[0] - g.f[0] * w + n[0] * 0.06,
                           p[1] - g.f[1] * w + n[1] * 0.06,
                           p[2] - g.f[2] * w + n[2] * 0.06];
      const fwd = (p) => [p[0] + g.f[0] * w + n[0] * 0.06,
                          p[1] + g.f[1] * w + n[1] * 0.06,
                          p[2] + g.f[2] * w + n[2] * 0.06];
      bright.quad(back(L), back(R), fwd(R), fwd(L), color);
    }
  }

  // --- ground / void -------------------------------------------------------
  const pad = CELL * 7;
  const gx0 = bbox.x0 - pad, gx1 = bbox.x1 + pad, gz0 = bbox.z0 - pad, gz1 = bbox.z1 + pad;
  let killY;
  if (groundY != null && pal.shore) {
    // A coast. The ground plane stops at the waterline instead of running to
    // the edge of the world, so what is past it is *nothing* - the sea is drawn
    // and never collided, and driving off the sand is a fall like any other
    // rather than a slow patch. Sand is still the run-off everywhere it exists,
    // which is the whole reason this is a ground track.
    const sh = pal.shore;
    const seaY = groundY - (sh.drop != null ? sh.drop : 3.0);
    // `axis` names the coordinate the waterline is a *value of*: 'z' means the
    // coast runs along x and the sea is everything past some z. `along` is the
    // way we march down the beach, `cross` is the way the water extends.
    const onZ = sh.axis !== 'x';
    const [a0, a1] = onZ ? [gx0, gx1] : [gz0, gz1];
    // `at` is a world coordinate, not a fraction of the bounding box: the track
    // is authored against the waterline (see SHORE_Z in tracks.py), so it has
    // to stay put when the layout changes rather than sliding with the bbox.
    // The water then extends `reach` past it, since the sea is generally
    // outside the track's own extent and would otherwise be a sliver.
    const at = sh.at;
    const c0 = onZ ? gz0 : gx0;
    const c1 = Math.max(onZ ? gz1 : gx1, at + (sh.reach != null ? sh.reach : 700));
    const pt = (a, c, y) => onZ ? [a, y, c] : [c, y, a];

    // Two waves at unrelated wavelengths, so the coast wanders without ever
    // visibly repeating.
    const shoreAt = (a) => at + sh.amp * Math.sin(a / sh.wave * Math.PI * 2)
                              + sh.amp * 0.38 * Math.sin(a / (sh.wave * 0.37) * Math.PI * 2);

    // Open water, drawn unlit so it stays bright into the distance. The sand
    // goes on top, so this only shows where there is no beach.
    bright.quad(pt(a0, c0, seaY), pt(a0, c1, seaY),
                pt(a1, c1, seaY), pt(a1, c0, seaY),
                sh.sea != null ? sh.sea : 0x1f7fa8);
    // Deeper water further out, so the sea has somewhere to go.
    const deepAt = at + sh.amp + 240;
    if (deepAt < c1) {
      bright.quad(pt(a0, deepAt, seaY), pt(a0, c1, seaY),
                  pt(a1, c1, seaY), pt(a1, deepAt, seaY),
                  sh.deep != null ? sh.deep : 0x11527a);
    }

    // The beach: one quad per column with its seaward edge on the waterline, so
    // the coast is a real curve rather than a staircase, at two triangles each.
    const step = CELL * 2;
    const fw = 5.5;
    for (let a = a0; a < a1; a += step) {
      const aa = a, ab = Math.min(a + step, a1);
      const wa = shoreAt(aa), wb = shoreAt(ab);
      const A = pt(aa, c0, groundY), B = pt(aa, wa, groundY);
      const C = pt(ab, wb, groundY), D = pt(ab, c0, groundY);
      col.addQuad(A, B, C, D, KIND.OFFROAD);
      solid.quad(A, B, C, D, pal.ground);
      // Foam, just seaward of the line and a hair above the water.
      bright.quad(pt(aa, wa, seaY + 0.06), pt(aa, wa + fw, seaY + 0.06),
                  pt(ab, wb + fw, seaY + 0.06), pt(ab, wb, seaY + 0.06),
                  sh.foam != null ? sh.foam : 0x9fe0ea);
    }
    killY = groundY - 30;
  } else if (terrain) {
    // Ground that follows the road instead of one flat plate - the only way a
    // track that falls 63 units can still be a ground track. See buildTerrain.
    const APRON = pal.terrain.apron != null ? pal.terrain.apron : 34;
    drawTerrain(solid, col, terrain, pal, APRON,
                pal.terrain.gravel != null ? pal.terrain.gravel : 22);
    addApron(solid, col, track, pal, terrain, pal.terrain, GRASS_DROP);
    armcoRuns = addArmco(solid, col, track, pal, terrain, pal.terrain, GRASS_DROP);
    killY = minY - 40;
    if (pal.furniture) {
      const keepOut = addFurniture(solid, bright, signs, track, pal, terrain,
                                   pal.furniture, GRASS_DROP);
      if (pal.furniture.sponsors) {
        addHoardings(signs, armcoRuns, pal.furniture.sponsors,
                     pal.furniture.boardEvery || 26, pal.furniture, keepOut);
      }
    }
  } else if (groundY != null) {
    // The grass sits well below the road surface, so the track is a raised
    // ribbon of tarmac. Coplanar road and grass is what made the ground query a
    // coin toss between the two - the car spent whole laps behaving as if it
    // were on grass, and the two surfaces z-fought all over the screen.
    const A = [gx0, groundY, gz0], B = [gx0, groundY, gz1];
    const C = [gx1, groundY, gz1], D = [gx1, groundY, gz0];
    col.addQuad(A, B, C, D, KIND.OFFROAD);
    solid.quad(A, B, C, D, pal.ground);
    killY = groundY - 30;
  } else {
    killY = minY - 26;
    // A distant plate so the void has a floor to look at - unless the palette
    // puts a whole world down there, in which case that is the floor.
    if (!pal.below) {
      const gy = minY - 34;
      solid.quad([gx0, gy, gz0], [gx0, gy, gz1], [gx1, gy, gz1], [gx1, gy, gz0],
                 shade(pal.ground, -0.3));
    }
  }

  // --- scenery (procedural, seeded, deterministic) -------------------------
  addScenery(solid, track, pal, bbox, CELL, terrain);
  // The one interior in the pool. A sibling of the scatter rather than of Spa's
  // furniture, which is reachable only from the terrain branch above - see
  // `addBuilding`. It needs the collider because a shelf you can drive through
  // is not a shelf, and `signs` because the wordmark is textured geometry.
  if (pal.building) addBuilding(solid, bright, signs, col, track, pal, pal.building);
  if (groundY == null && pal.below) addWorldBelow(solid, soft, bright, track, pal, bbox, CELL, minY, maxY);

  const mat = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });
  const matBright = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide });
  group.add(solid.toMesh(mat));
  group.add(bright.toMesh(matBright));
  // Sponsor boards, batched by word: every hoarding reading DRIVE is one mesh
  // sharing one canvas, so the circuit's advertising is a handful of draw calls.
  //
  // Skipped when there is no DOM, and that is load bearing rather than tidy:
  // the anti-cheat runs this exact file inside QuickJS to re-drive a lap
  // (`jsrt.bundle`, `verify.py`), and there is no `document` there. Without
  // this guard `buildTrack` throws for any track with boards, which does not
  // fail loudly - it means every fast lap on that track waits in
  // `drive_run_checks` forever and never reaches the leaderboard.
  if (signs.length && typeof document !== 'undefined') {
    const byText = new Map();
    for (const s of signs) {
      let buf = byText.get(s.text);
      if (!buf) byText.set(s.text, buf = new SignBuf());
      const c = buf.panel(s.c, s.r, s.u, s.hw, s.hh, s.n);
      // The back and the edges, in the world mesh. Without these a board is a
      // sheet of paper you can see the wrong way through from behind the stand.
      const n = s.n || [0, 0, 1];
      const B = (p) => [p[0] - n[0] * 0.35, p[1] - n[1] * 0.35, p[2] - n[2] * 0.35];
      const back = 0x2a2e35;
      solid.quad(B(c[0]), B(c[3]), B(c[2]), B(c[1]), back);
      solid.quad(c[0], B(c[0]), B(c[1]), c[1], back);   // bottom
      solid.quad(c[3], c[2], B(c[2]), B(c[3]), back);   // top
      solid.quad(c[0], c[3], B(c[3]), B(c[0]), back);   // ends
      solid.quad(c[1], B(c[1]), B(c[2]), c[2], back);
    }
    for (const [text, buf] of byText) group.add(buf.toMesh(signTexture(text)));
  }
  // Cloud is its own mesh so it can be translucent. depthWrite is off on
  // purpose: it is what lets overlapping boxes *accumulate* into something
  // dense in the middle and wispy at the edges, which is the entire difference
  // between a cloud and a slab of polystyrene.
  if (soft.pos.length) {
    const matSoft = new THREE.MeshLambertMaterial({
      vertexColors: true, flatShading: true, transparent: true,
      opacity: 0.82, depthWrite: false });
    const m = soft.toMesh(matSoft);
    m.renderOrder = 1;
    group.add(m);
  }

  col.finish();

  // Centreline with cumulative distance, for race positions and respawns.
  const s = [0];
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1].p, b2 = line[i].p;
    s.push(s[i - 1] + Math.hypot(b2[0] - a[0], b2[1] - a[1], b2[2] - a[2]));
  }
  // start, then checkpoints in order, then finish - the order you must cross them
  const gateKey = (g) => g.kind === 'start' ? -1 : g.kind === 'finish' ? 1e6 : g.gi;
  gates.sort((a, b2) => gateKey(a) - gateKey(b2));

  return { group, collider: col, gates, line, s, total: s[s.length - 1],
           killY, palette: pal, bbox, minY, maxY };
}

// Hue/sat/lightness to packed RGB. Only Rainbow Road needs it, and it needs it
// per station along the whole road, so it is worth not going through three.js.
function hsl(h, s, l) {
  const f = (n) => {
    const k = (n + h * 12) % 12;
    const a = s * Math.min(l, 1 - l);
    return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
  };
  return (f(0) << 16) | (f(8) << 8) | f(4);
}

function shade(hex, amt) {
  let r = (hex >> 16) & 255, g = (hex >> 8) & 255, b = hex & 255;
  if (amt >= 0) { r += (255 - r) * amt; g += (255 - g) * amt; b += (255 - b) * amt; }
  else { r *= 1 + amt; g *= 1 + amt; b *= 1 + amt; }
  return (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(b);
}

// A tiny deterministic PRNG so scenery is identical for everyone in a room.
export function mulberry(seed) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

/**
 * The world underneath a track that floats.
 *
 * The six floating tracks have nowhere to stand scenery, so this is the other
 * half of it: whatever is a long way down. `pal.below.kind` picks which world.
 *
 * It is all scenery - none of it is in the collider. Nothing may reach the
 * road, and every generator here obeys the same two rules: stay out of the
 * road corridor, *and* stay under a hard cap below the track's lowest point.
 * Either would usually do; a landmark tower or a mesa is tall enough that it is
 * not worth betting the geometry on one of them.
 */
function addWorldBelow(buf, soft, bright, track, pal, bbox, CELL, minY, maxY) {
  const cfg = pal.below;
  let seed = 91;
  for (let i = 0; i < track.slug.length; i++) seed = seed * 31 + track.slug.charCodeAt(i);
  const rnd = mulberry(seed);

  const deckY = minY - (cfg.deck != null ? cfg.deck : 24);
  const floorY = deckY - (cfg.depth != null ? cfg.depth : 120);
  const reach = cfg.reach != null ? cfg.reach : 460;
  const x0 = bbox.x0 - reach, x1 = bbox.x1 + reach;
  const z0 = bbox.z0 - reach, z1 = bbox.z1 + reach;
  const cap = minY - 10;              // nothing below may rise past this

  // Cells the road passes over, so nothing ever comes up through the track.
  const occupied = new Set();
  for (const e of track.line) {
    const r = Math.ceil((e.hw + CELL * 2) / CELL);
    const cx = Math.round(e.p[0] / CELL), cz = Math.round(e.p[2] / CELL);
    for (let dx = -r; dx <= r; dx++) {
      for (let dz = -r; dz <= r; dz++) occupied.add((cx + dx) + ',' + (cz + dz));
    }
  }
  // Clear of the road, optionally for a whole footprint rather than a point -
  // a tower is wide, and it is its corner that ends up over the kerb.
  const clear = (px, pz, half) => {
    const n = half ? Math.ceil(half / CELL) : 0;
    const cx = Math.round(px / CELL), cz = Math.round(pz / CELL);
    for (let dx = -n; dx <= n; dx++) {
      for (let dz = -n; dz <= n; dz++) if (occupied.has((cx + dx) + ',' + (cz + dz))) return false;
    }
    return true;
  };

  if (cfg.kind === 'desert') {
    desertBelow(buf, cfg, rnd, x0, x1, z0, z1, deckY, cap, CELL, clear);
    return;
  }
  // An overcast ceiling, for the tracks that want weather on top of them too.
  if (cfg.above) {
    cloudDeck(soft, cfg.above, rnd, x0, x1, z0, z1,
              maxY + (cfg.above.deck != null ? cfg.above.deck : 120), CELL);
  }
  // A layer of cloud *between* the road and whatever is under it, at its own
  // depth and its own coverage. The default world already ends in a cloud deck
  // sitting on top of its drowned towers, which is one thing rather than two -
  // so a track that wants to be above the weather and still see a city a long
  // way further down had no way to say so, because every other `kind` returns
  // before the deck is drawn. This is drawn first and dispatched past, so any
  // world can carry one.
  if (cfg.haze) {
    cloudDeck(soft, cfg.haze, rnd, x0, x1, z0, z1,
              minY - (cfg.haze.deck != null ? cfg.haze.deck : 60), CELL);
  }
  if (cfg.kind === 'void') return;      // nothing down there at all, on purpose
  if (cfg.kind === 'lava') {
    lavaBelow(buf, bright, cfg, rnd, x0, x1, z0, z1, deckY, cap, CELL, clear);
    return;
  }
  if (cfg.kind === 'downtown') {
    downtownBelow(buf, bright, cfg, rnd, bbox, x0, x1, z0, z1, deckY, CELL, clear);
    return;
  }
  if (cfg.kind === 'pillars') {
    pillarsBelow(buf, soft, cfg, rnd, x0, x1, z0, z1, deckY, floorY, cap, CELL, clear);
    return;
  }

  // --- default: a city drowned in cloud ------------------------------------
  //
  // Cloud works here because you look *down* on it: from above you see lit
  // tops, and the gaps between slabs read as holes in the layer rather than as
  // the edges of boxes, which is exactly what sank the same idea as a sky.
  solid_plate(buf, x0, x1, z0, z1, floorY, cfg.floor != null ? cfg.floor : 0x2a3446);

  // --- towers ---------------------------------------------------------------
  const tStep = CELL * (cfg.towerStep != null ? cfg.towerStep : 9);
  const towerTop = deckY + (cfg.rise != null ? cfg.rise : 26);
  for (let x = x0; x < x1; x += tStep) {
    for (let z = z0; z < z1; z += tStep) {
      if (rnd() > (cfg.towerDensity != null ? cfg.towerDensity : 0.5)) continue;
      const px = x + rnd() * tStep, pz = z + rnd() * tStep;
      if (!clear(px, pz)) continue;
      // Most are drowned; a few break the surface. That ratio is the whole
      // effect - a forest of towers all poking through is just a city.
      const breaks = rnd() < (cfg.breakThrough != null ? cfg.breakThrough : 0.34);
      // A couple of genuine landmarks among them, rather than every tower
      // topping out at the same height.
      const tall = breaks && rnd() < 0.14;
      const top = Math.min(cap,
        breaks ? deckY + (tall ? 1 : rnd()) * (towerTop - deckY) * (tall ? 1.9 : 1)
               : deckY - 6 - rnd() * 40);
      const w = 4 + rnd() * 11, d = 4 + rnd() * 11;
      const body = shade(cfg.tower != null ? cfg.tower : 0x3a4761, (rnd() - 0.5) * 0.22);
      buf.box(px, (floorY + top) / 2, pz, w / 2, (top - floorY) / 2, d / 2, body);
      if (breaks) {
        // a lighter cap and a thin mast, so the ones you can see have a profile
        buf.box(px, top + 0.8, pz, w * 0.56, 0.8, d * 0.56, shade(body, 0.22));
        if (rnd() < 0.45) {
          buf.box(px, top + 4 + rnd() * 5, pz, 0.5, 4 + rnd() * 5, 0.5, shade(body, 0.3));
        }
      }
    }
  }

  // --- the cloud deck -------------------------------------------------------
  cloudDeck(soft, cfg, rnd, x0, x1, z0, z1, deckY, CELL);
}

/**
 * A layer of cloud, as clumps rather than a lattice.
 *
 * The first version tiled slabs across a grid at 70% coverage and read as a
 * snowfield, which is what any even coverage of opaque boxes will do. Clouds
 * are lumps with sky between them, so: sparse seed points, and around each one
 * a mound of overlapping boxes sampled in a disc - biggest and tallest in the
 * middle, small and low at the rim. Combined with a translucent material the
 * rim boxes fade out on their own and the mass stays solid, so the thing has an
 * edge you cannot point at.
 */
function cloudDeck(soft, cfg, rnd, x0, x1, z0, z1, deckY, CELL) {
  const step = CELL * (cfg.cloudStep != null ? cfg.cloudStep : 16);
  const lit = cfg.cloud != null ? cfg.cloud : 0xf7fbff;
  const cover = cfg.cover != null ? cfg.cover : 0.5;
  const TAU = Math.PI * 2;
  for (let x = x0; x < x1; x += step) {
    for (let z = z0; z < z1; z += step) {
      if (rnd() > cover) continue;
      const cx = x + rnd() * step, cz = z + rnd() * step;
      const R = 38 + rnd() * 58;
      const cy = deckY + (rnd() - 0.5) * 26;
      const puffs = 9 + Math.floor(rnd() * 8);
      for (let i = 0; i < puffs; i++) {
        // sqrt keeps the sample uniform over the disc rather than piling up in
        // the middle; the size falls off with radius instead.
        const a = rnd() * TAU, r = R * Math.sqrt(rnd()) * 0.92;
        const t = 1 - r / R;                       // 1 centre, 0 rim
        const w = R * (0.26 + 0.34 * t) * (0.75 + rnd() * 0.5);
        // `puff` deepens the layer. Flat wide boxes read as floes on water from
        // anywhere near their own level; a lumpier deck keeps looking like
        // cloud from a shallower angle, which is what a long track needs.
        const h = (4 + 11 * t) * (0.7 + rnd() * 0.6) * (cfg.puff != null ? cfg.puff : 1);
        soft.box(cx + Math.cos(a) * r, cy + t * 10 + (rnd() - 0.5) * 5,
                 cz + Math.sin(a) * r,
                 w, h, w * (0.72 + rnd() * 0.55),
                 shade(lit, (rnd() - 0.5) * 0.08));
      }
    }
  }
}

function desertBelow(buf, cfg, rnd, x0, x1, z0, z1, sandY, cap, CELL, clear) {
  solid_plate(buf, x0, x1, z0, z1, sandY, cfg.sand != null ? cfg.sand : 0xd9b478);
  const sand = cfg.sand != null ? cfg.sand : 0xd9b478;
  const rock = cfg.rock != null ? cfg.rock : 0xb5744a;

  // --- dunes ---------------------------------------------------------------
  const dStep = CELL * 10;
  for (let x = x0; x < x1; x += dStep) {
    for (let z = z0; z < z1; z += dStep) {
      if (rnd() > (cfg.duneDensity != null ? cfg.duneDensity : 0.55)) continue;
      const px = x + rnd() * dStep, pz = z + rnd() * dStep;
      // Broad and very low. A dune with any height to it is a crate: from a
      // long way up you only read the footprint, so the swell has to be wide
      // enough that the slab never shows you a side.
      const w = 70 + rnd() * 90, d = 40 + rnd() * 50;
      const drift = (rnd() - 0.5) * w * 0.45;     // which way the wind piled it
      let y = sandY;
      for (let k = 0; k < 2; k++) {
        const u = k / 2;
        const h = 1.5 + rnd() * 1.8;
        buf.box(px + drift * u, y + h, pz + drift * u * 0.4,
                w * (1 - u * 0.42) / 2, h, d * (1 - u * 0.38) / 2,
                shade(sand, (rnd() - 0.35) * 0.1));
        y += h * 1.6;
      }
    }
  }

  // --- mesas ---------------------------------------------------------------
  const mStep = CELL * 22;
  for (let x = x0; x < x1; x += mStep) {
    for (let z = z0; z < z1; z += mStep) {
      if (rnd() > (cfg.mesaDensity != null ? cfg.mesaDensity : 0.42)) continue;
      const px = x + rnd() * mStep, pz = z + rnd() * mStep;
      if (!clear(px, pz)) continue;
      // Narrow buttes rather than broad mesas. You are looking *down* on all of
      // this from a hundred units up, so anything as wide as it is tall shows
      // you its top face and reads as a crate; height is the only thing that
      // survives the angle.
      const hgt = Math.min(cap - sandY, 46 + rnd() * 54);
      if (hgt < 24) continue;
      const w = 14 + rnd() * 22, d = 12 + rnd() * 20;
      const tiers = 2 + Math.floor(rnd() * 2);
      let y = sandY;
      for (let k = 0; k < tiers; k++) {
        const u = (k + 1) / tiers;
        const th = hgt / tiers;
        // stepped and inset going up, and lighter with it, so the top catches
        // the sun and the base sits in its own shade
        buf.box(px, y + th / 2, pz, w * (1 - u * 0.28) / 2, th / 2, d * (1 - u * 0.28) / 2,
                shade(rock, -0.16 + u * 0.26 + (rnd() - 0.5) * 0.08));
        y += th;
      }
    }
  }

  // --- loose rock ----------------------------------------------------------
  const rStep = CELL * 8;
  for (let x = x0; x < x1; x += rStep) {
    for (let z = z0; z < z1; z += rStep) {
      if (rnd() > (cfg.rockDensity != null ? cfg.rockDensity : 0.22)) continue;
      const px = x + rnd() * rStep, pz = z + rnd() * rStep;
      const s = 2 + rnd() * 6;
      buf.box(px, sandY + s * 0.45, pz, s, s * 0.45, s * (0.6 + rnd() * 0.6),
              shade(rock, -0.24 + (rnd() - 0.5) * 0.16));
    }
  }
}

/**
 * A downtown at your own level, not underneath you.
 *
 * The other floating tracks put their world far below and cap it under the
 * road. This one deliberately does not: the towers come up *past* the road, so
 * you are launching between them rather than over them, and the four gaps have
 * something to fall between. That means the corridor test is the only thing
 * keeping geometry out of the track, so it checks a tower's whole footprint
 * rather than its centre.
 *
 * Density falls off from a core, which is most of what makes a skyline read as
 * a city rather than a field of blocks - a financial district with a couple of
 * hundred metres of glass in it, and everything else low around it.
 */
function downtownBelow(buf, bright, cfg, rnd, bbox, x0, x1, z0, z1, groundY, CELL, clear) {
  solid_plate(buf, x0, x1, z0, z1, groundY, cfg.floor != null ? cfg.floor : 0x1a2133);
  const glass = cfg.tower != null ? cfg.tower : 0x36435c;
  const lampCol = cfg.window != null ? cfg.window : 0xffd79a;
  // The core sits off to one side of the track rather than on it, so the
  // skyline is something you drive past and into rather than through.
  const coreX = (bbox.x0 + bbox.x1) / 2 + (cfg.coreX || 0);
  const coreZ = (bbox.z0 + bbox.z1) / 2 + (cfg.coreZ || 0);
  const coreR = cfg.coreR != null ? cfg.coreR : 340;

  const step = CELL * (cfg.step != null ? cfg.step : 4);
  for (let x = x0; x < x1; x += step) {
    for (let z = z0; z < z1; z += step) {
      const px = x + rnd() * step, pz = z + rnd() * step;
      // how downtown this is, 1 in the core and falling away
      const d = Math.hypot(px - coreX, pz - coreZ) / coreR;
      const core = Math.max(0, 1 - d * d * 0.55);
      if (rnd() > 0.25 + core * 0.6) continue;
      const w = (5 + rnd() * 10) * (0.7 + core * 0.7);
      const dp = (5 + rnd() * 10) * (0.7 + core * 0.7);
      if (!clear(px, pz, Math.max(w, dp) * 0.5 + 6)) continue;
      // Most stay under the road; in the core a good number come up past it.
      const tall = rnd() < 0.2 + core * 0.45;
      const hgt = (cfg.low || 46) + rnd() * (cfg.spread || 70) +
                  (tall ? core * (cfg.rise || 150) * (0.35 + rnd() * 0.65) : 0);
      const body = shade(glass, -0.18 + rnd() * 0.3);
      buf.box(px, groundY + hgt / 2, pz, w / 2, hgt / 2, dp / 2, body);
      // a setback or a plant room on top, so the roofline is not all flat
      const r = rnd();
      if (r < 0.32) {
        buf.box(px, groundY + hgt + 3, pz, w * 0.3, 3, dp * 0.3, shade(body, 0.12));
      } else if (r < 0.45) {
        buf.box(px, groundY + hgt + 9, pz, 0.5, 9, 0.5, shade(body, 0.3));
      }
      // Lit windows: thin vertical strips just proud of two faces. Cheaper and
      // more legible at this scale than any per-window geometry, and they are
      // in the unlit buffer so they read as light rather than as paint.
      if (rnd() < 0.82) {
        const lit = shade(lampCol, (rnd() - 0.6) * 0.35);
        const n = 1 + Math.floor(rnd() * 3);
        for (let i = 0; i < n; i++) {
          const u = (i + 1) / (n + 1);
          const y0 = groundY + hgt * (0.05 + rnd() * 0.1);
          const y1 = groundY + hgt * (0.8 + rnd() * 0.18);
          const sx = px - w / 2 + w * u, t = 0.55;
          for (const face of [pz - dp / 2 - 0.06, pz + dp / 2 + 0.06]) {
            bright.quad([sx - t, y0, face], [sx + t, y0, face],
                        [sx + t, y1, face], [sx - t, y1, face], lit);
          }
        }
      }
    }
  }

  // --- the landmark --------------------------------------------------------
  // Every skyline needs the one thing you recognise it by. A tapering shaft, a
  // pod near the top and a long antenna above it.
  if (cfg.landmark !== false) {
    const lx = coreX + (cfg.landmarkX || 0), lz = coreZ + (cfg.landmarkZ || 0);
    const H = cfg.landmarkH || 300;
    const seg = 5;
    for (let i = 0; i < seg; i++) {
      const u0 = i / seg, u1 = (i + 1) / seg;
      const w0 = 9 * (1 - u0 * 0.62);
      buf.box(lx, groundY + H * (u0 + u1) / 2, lz, w0 / 2, H * (u1 - u0) / 2, w0 / 2,
              shade(glass, 0.3 - u0 * 0.1));
    }
    const podY = groundY + H * 0.74;
    buf.box(lx, podY, lz, 11, 5.5, 11, shade(glass, 0.42));
    buf.box(lx, podY + 8, lz, 7.5, 3, 7.5, shade(glass, 0.34));
    buf.box(lx, groundY + H * 0.9, lz, 4.5, 3, 4.5, shade(glass, 0.38));
    buf.box(lx, groundY + H * 1.13, lz, 0.9, H * 0.13, 0.9, shade(glass, 0.5));
    // the pod is lit right round
    for (const s of [-1, 1]) {
      bright.quad([lx - 11, podY - 2.4, lz + s * 11.1], [lx + 11, podY - 2.4, lz + s * 11.1],
                  [lx + 11, podY + 2.4, lz + s * 11.1], [lx - 11, podY + 2.4, lz + s * 11.1],
                  lampCol);
      bright.quad([lx + s * 11.1, podY - 2.4, lz - 11], [lx + s * 11.1, podY - 2.4, lz + 11],
                  [lx + s * 11.1, podY + 2.4, lz + 11], [lx + s * 11.1, podY + 2.4, lz - 11],
                  lampCol);
    }
    // and the domed stadium next door, because that is the pair you picture
    const dx = lx + 62, dz = lz + 26;
    for (let i = 0; i < 4; i++) {
      const u = i / 4;
      buf.box(dx, groundY + 6 + i * 5, dz, 34 * (1 - u * 0.5), 2.6, 30 * (1 - u * 0.5),
              shade(glass, 0.16 + u * 0.1));
    }
  }
}

/**
 * A lava floor, crusted over.
 *
 * The trick is the order: a single glowing plane across the whole area in the
 * *unlit* buffer, then plates of dark crust laid on top of it in the lit one,
 * covering most but not all of it. The gaps between plates are the lava, so the
 * veins come out irregular and connected for free instead of being drawn - and
 * because the lava is unlit it stays at full brightness while everything on top
 * of it sits in the dark, which is what makes it read as molten.
 */
function lavaBelow(buf, bright, cfg, rnd, x0, x1, z0, z1, floorY, cap, CELL, clear) {
  const hot = cfg.lava != null ? cfg.lava : 0xff5a12;
  const crust = cfg.crust != null ? cfg.crust : 0x1c1a20;
  bright.quad([x0, floorY, z0], [x0, floorY, z1], [x1, floorY, z1], [x1, floorY, z0], hot);

  // --- crust ---------------------------------------------------------------
  const step = CELL * (cfg.crustStep != null ? cfg.crustStep : 5);
  for (let x = x0; x < x1; x += step) {
    for (let z = z0; z < z1; z += step) {
      if (rnd() > (cfg.crustCover != null ? cfg.crustCover : 0.86)) continue;
      const px = x + (rnd() - 0.5) * step * 0.3, pz = z + (rnd() - 0.5) * step * 0.3;
      const w = step * (0.4 + rnd() * 0.28), d = step * (0.4 + rnd() * 0.28);
      const h = 1.2 + rnd() * 2.6;
      buf.box(px, floorY + h, pz, w, h, d, shade(crust, (rnd() - 0.4) * 0.5));
    }
  }

  // --- spires --------------------------------------------------------------
  // Black rock, jagged, leaning. Height is what survives being seen from above.
  const sStep = CELL * (cfg.spireStep != null ? cfg.spireStep : 16);
  for (let x = x0; x < x1; x += sStep) {
    for (let z = z0; z < z1; z += sStep) {
      if (rnd() > (cfg.spireDensity != null ? cfg.spireDensity : 0.5)) continue;
      const px = x + rnd() * sStep, pz = z + rnd() * sStep;
      const w0 = 7 + rnd() * 12;
      if (!clear(px, pz, w0)) continue;
      const hgt = Math.min(cap - floorY, 40 + rnd() * 90);
      if (hgt < 20) continue;
      const tiers = 3 + Math.floor(rnd() * 3);
      const lean = (rnd() - 0.5) * 0.6;
      let y = floorY;
      for (let k = 0; k < tiers; k++) {
        const u = k / tiers, th = hgt / tiers;
        const w = w0 * (1 - u * 0.78) * (0.8 + rnd() * 0.4);
        buf.box(px + lean * u * w0, y + th / 2, pz + lean * u * w0 * 0.6,
                w / 2, th / 2, w * (0.7 + rnd() * 0.5) / 2,
                shade(crust, -0.25 + u * 0.22 + (rnd() - 0.5) * 0.12));
        y += th;
      }
      // molten at the base, where it came out of the floor
      if (rnd() < 0.45) {
        bright.quad([px - w0, floorY + 0.4, pz - w0], [px + w0, floorY + 0.4, pz - w0],
                    [px + w0, floorY + 0.4, pz + w0], [px - w0, floorY + 0.4, pz + w0],
                    shade(hot, 0.1));
      }
    }
  }
}

/**
 * Rock spires standing up through an overcast - the world under Cloudbreak.
 *
 * The whole point of this one is that the track threads *between* the spires
 * rather than over a landscape, so unlike the towers and mesas these are
 * allowed all the way up to the cap - they are meant to stand beside you at
 * road level and above it. That makes the footprint test load-bearing on its
 * own (same as Jump City's towers): `clear` is asked about the spire's whole
 * width, because it is a corner of a wide rock that ends up over a kerb.
 *
 * None of it is in the collider. A spire is scenery you drive past, and on a
 * track where missing the road is a fall anyway, one you could hit would only
 * ever be an invisible wall the procedural placement put in the racing line.
 */
function pillarsBelow(buf, soft, cfg, rnd, x0, x1, z0, z1, deckY, floorY, cap, CELL, clear) {
  // **No floor plate.** The first version laid one, and from a camera that is
  // nearly level with the road the result was unmistakably a grey sea with
  // white floes on it and the spires standing in it like pilings. Leaving the
  // bottom open means the space under the cloud is the sky dome fading into
  // fog, which is what being a long way up actually looks like. `floor` is
  // still honoured if a palette explicitly asks for one.
  if (cfg.floor != null) solid_plate(buf, x0, x1, z0, z1, floorY, cfg.floor);

  const rock = cfg.rock != null ? cfg.rock : 0x6a5c4c;
  // Spires grow out of the cloud rather than up off a floor, so their base is
  // just under the deck and their feet are lost in it - which is the whole
  // image, and also why there is nothing to see where a floor would have been.
  const root = deckY - (cfg.root != null ? cfg.root : 80);
  const step = CELL * (cfg.spireStep != null ? cfg.spireStep : 13);
  for (let x = x0; x < x1; x += step) {
    for (let z = z0; z < z1; z += step) {
      if (rnd() > (cfg.spireDensity != null ? cfg.spireDensity : 0.6)) continue;
      const px = x + rnd() * step, pz = z + rnd() * step;
      // Wide enough to read as rock at this distance. Thin reads as a piling.
      const w0 = 26 + rnd() * 38;
      if (!clear(px, pz, w0 * 0.9)) continue;
      const top = Math.min(cap, deckY + (cfg.rise != null ? cfg.rise : 58) * (0.35 + rnd()));
      if (top - root < 40) continue;
      // Stacked tiers, each narrower and slightly offset, so a spire has a
      // silhouette instead of being a column.
      const tiers = 4 + Math.floor(rnd() * 4);
      let y = root, w = w0;
      const lx = (rnd() - 0.5) * 0.5, lz = (rnd() - 0.5) * 0.5;
      for (let t = 0; t < tiers; t++) {
        const h = (top - root) / tiers * (0.8 + rnd() * 0.45);
        const u = t / tiers;
        buf.box(px + lx * (top - root) * u, y + h / 2, pz + lz * (top - root) * u,
                w / 2, h / 2, w * (0.8 + rnd() * 0.4) / 2,
                shade(rock, (rnd() - 0.5) * 0.24 - u * 0.06));
        y += h;
        w *= 0.72 + rnd() * 0.16;
        if (w < 1.6) break;
      }
      // No green cap. These were meant to read as land on top of the taller
      // spires, and at this distance a flat green slab on a grey rock reads as
      // a slab on a rock - it made the good ones look like they were wearing
      // hats. The silhouette does the work instead.
    }
  }

  cloudDeck(soft, cfg, rnd, x0, x1, z0, z1, deckY, CELL);
}

function solid_plate(buf, x0, x1, z0, z1, y, color) {
  buf.quad([x0, y, z0], [x0, y, z1], [x1, y, z1], [x1, y, z0], color);
}

/**
 * Ground that follows the ribbon, for a track whose road climbs and falls too
 * far for one flat plate.
 *
 * Every other ground track keeps its road between 0 and 20 and sits it on a
 * single quad at `track.ground`, which is both the grass you see and the
 * OFFROAD surface you are punished on. Spa falls 63 units, so that plate would
 * be an opaque, collidable ceiling over most of the lap - the car would spend
 * from Pouhon to Stavelot driving underneath the world.
 *
 * So the ground here is a height field sampled off the road itself: near the
 * ribbon it is the height of the closest point *on* it, and further out it
 * blends into an inverse-distance-squared average of the stations in reach.
 * Three things follow from doing it this way rather than authoring a heightmap:
 *
 *  - it cannot disagree with the track, because it is derived from it;
 *  - a road cut into a hillside falls out for free, and so does the bank
 *    between Pouhon and Blanchimont where the two legs pass at different
 *    heights;
 *  - and the same sampler places the trees, the gravel, the armco and the
 *    grandstands, so none of them can float or sink.
 *
 * The field is built once at CELL resolution and bilinear-sampled after that.
 */
function buildTerrain(track, CELL, bbox, apron, drop) {
  const line = track.line;
  const PAD = CELL * 10;
  const x0 = bbox.x0 - PAD, x1 = bbox.x1 + PAD;
  const z0 = bbox.z0 - PAD, z1 = bbox.z1 + PAD;
  const nx = Math.ceil((x1 - x0) / CELL) + 1;
  const nz = Math.ceil((z1 - z0) / CELL) + 1;

  // Bucket the stations so each grid point only looks at what is near it.
  //
  // The buckets live in a flat array indexed by integer coordinates rather than
  // in a Map keyed on `bx + ',' + bz`. It is the same buckets holding the same
  // stations, and it is most of what this function costs: every cell reads its
  // whole 9x9 neighbourhood, so a string key is 15,810 x 81 concatenations and
  // hashes - 1.3 million of them - to answer a question that is an array index.
  const BUCKET = 48, REACH = 190, REACH2 = REACH * REACH;
  const span = Math.ceil(REACH / BUCKET);
  const bxMin = Math.floor(x0 / BUCKET) - span - 1;
  const bzMin = Math.floor(z0 / BUCKET) - span - 1;
  const nbx = Math.floor(x1 / BUCKET) + span + 2 - bxMin;
  const nbz = Math.floor(z1 / BUCKET) + span + 2 - bzMin;
  const buckets = new Array(nbx * nbz).fill(null);
  for (let i = 0; i < line.length; i++) {
    const p = line[i].p;
    const bx = Math.floor(p[0] / BUCKET) - bxMin, bz = Math.floor(p[2] / BUCKET) - bzMin;
    if (bx < 0 || bx >= nbx || bz < 0 || bz >= nbz) continue;
    const k = bx * nbz + bz;
    let a = buckets[k];
    if (!a) buckets[k] = a = [];
    a.push(i);
  }
  // The stations' coordinates, flat. `line[i].p[0]` is three property loads and
  // a bounds check per axis per candidate, and the inner loop below runs about
  // eighteen million times on Spa.
  const px_ = new Float64Array(line.length), py_ = new Float64Array(line.length),
        pz_ = new Float64Array(line.length);
  for (let i = 0; i < line.length; i++) {
    px_[i] = line[i].p[0]; py_[i] = line[i].p[1]; pz_[i] = line[i].p[2];
  }
  // The neighbourhood, nearest bucket first. Visiting it in this order is what
  // lets the projection bound below actually reject anything: scanning from a
  // corner leaves `best` at infinity until most of the work is already done.
  const ring = [];
  for (let dx = -span; dx <= span; dx++) {
    for (let dz = -span; dz <= span; dz++) ring.push([dx, dz]);
  }
  ring.sort((a, b) => (a[0] * a[0] + a[1] * a[1]) - (b[0] * b[0] + b[1] * b[1]));
  const ringX = new Int32Array(ring.map((o) => o[0]));
  const ringZ = new Int32Array(ring.map((o) => o[1]));

  // The nearest road is the nearest point on the *ribbon*, not the nearest
  // station, and that distinction is the whole difference between run-off that
  // reads as gravel and run-off with grass torn through it.
  //
  // Nearest-station makes `near` a staircase: every point in a station's
  // Voronoi cell gets that station's exact height, so the field steps by a
  // whole station's rise at each cell boundary. The swept apron, meanwhile,
  // interpolates smoothly between the same two stations. On Spa's steepest
  // grade a station is 0.64 units of descent, so the two surfaces disagree by
  // up to a third of a unit either way - a hundred times the 0.03 the apron is
  // lifted by - and the height field pokes up through the gravel in patches all
  // the way down the hill. Measured before this: 19% of the run-off had grass
  // standing above it, by as much as 3.4 units.
  //
  // Projecting onto the segment and lerping its height is exactly what the
  // apron's own sweep does, so on a straight the two agree to the bit and on a
  // corner to the ribbon's curvature. It also makes `toRoad` an honest distance
  // to the road rather than to the nearest survey peg, which is what the apron's
  // clipping, the armco and the stands all wanted it to be anyway.
  // Projecting onto a segment costs a divide and a dozen flops, and doing it for
  // every station in reach of every cell is 100M of them on Spa - it took the
  // field from 83ms to build to 630ms, and this runs inside QuickJS on the
  // server as well as in the browser. Two things make it cheap again without
  // changing a single sample:
  //
  //  - `1/L2` is a property of the segment, not of the cell, so it is computed
  //    once here rather than 90,000 times;
  //  - and a segment whose *station* is further off than `best + segMax` cannot
  //    contain a nearer point than the one already found, so it is never
  //    projected at all. That bound is only worth anything if `best` gets small
  //    early, which is why the buckets are visited nearest-first below instead
  //    of starting from a corner of the neighbourhood.
  const closed = !!track.closed;
  const segs = new Float64Array(line.length * 7);
  let segMax = 0;
  for (let i = 0; i < line.length; i++) {
    const a = line[i].p;
    const j = i + 1 < line.length ? i + 1 : (closed ? 0 : i);
    const b = line[j].p;
    const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
    const L2 = dx * dx + dz * dz;
    const o = i * 7;
    segs[o] = a[0]; segs[o + 1] = a[1]; segs[o + 2] = a[2];
    segs[o + 3] = dx; segs[o + 4] = dy; segs[o + 5] = dz;
    segs[o + 6] = L2 > 0 ? 1 / L2 : 0;
    segMax = Math.max(segMax, Math.sqrt(L2));
  }

  // height, and the distance to the nearest road centre - the second is what
  // paints gravel next to the road and grass beyond it.
  const H = new Float32Array(nx * nz);
  const D = new Float32Array(nx * nz);
  for (let ix = 0; ix < nx; ix++) {
    const px = x0 + ix * CELL;
    const bx = Math.floor(px / BUCKET) - bxMin;
    for (let iz = 0; iz < nz; iz++) {
      const pz = z0 + iz * CELL;
      const bz = Math.floor(pz / BUCKET) - bzMin;
      let wsum = 0, hsum = 0, best = Infinity, bestY = 0, gate = Infinity;
      for (let r = 0; r < ringX.length; r++) {
        const qx2 = bx + ringX[r], qz2 = bz + ringZ[r];
        if (qx2 < 0 || qx2 >= nbx || qz2 < 0 || qz2 >= nbz) continue;
        const a = buckets[qx2 * nbz + qz2];
        if (a === null) continue;
        for (let n = 0; n < a.length; n++) {
          const i = a[n];
          const ex = px_[i] - px, ez = pz_[i] - pz;
          const d2 = ex * ex + ez * ez;
          // Nearest point on this station's segment, and its height there -
          // but only where this segment could possibly hold one.
          if (d2 < gate) {
            const o = i * 7;
            const sx = segs[o], sz = segs[o + 2], dx2 = segs[o + 3], dz2 = segs[o + 5];
            const u = Math.max(0, Math.min(1,
              ((px - sx) * dx2 + (pz - sz) * dz2) * segs[o + 6]));
            const ax = sx + dx2 * u - px, az = sz + dz2 * u - pz;
            const q2 = ax * ax + az * az;
            if (q2 < best) {
              best = q2; bestY = segs[o + 1] + segs[o + 4] * u;
              const g = Math.sqrt(best) + segMax;
              gate = g * g;
            }
          }
          if (d2 > REACH2) continue;
          const w = 1 / (d2 + 12);
          wsum += w; hsum += w * py_[i];
        }
      }
      const idx = ix * nz + iz;
      // Nothing in reach happens only out past the padding, where the nearest
      // station is still the only sensible answer - a global base level there
      // turns the outfield into a bowl with the circuit on a plateau in it.
      const far = wsum > 0 ? hsum / wsum : bestY;
      const d = best === Infinity ? 1e6 : Math.sqrt(best);
      // Inside the apron the ground is *exactly* the nearest road's height,
      // less the same drop the apron uses. That is what lets the swept run-off
      // and this grid agree where they meet. An inverse-distance blend right up
      // to the kerb was the first attempt and is what made the gravel wander
      // above and below the road: it averages in stations from further up and
      // down the hill, so beside a climb the ground came out higher than the
      // tarmac and buried it.
      const BLEND = 70;
      const near = bestY - drop;
      const t = Math.max(0, Math.min(1, (d - apron) / BLEND));
      H[idx] = near + (far - near) * (t * t * (3 - 2 * t));
      D[idx] = d;
    }
  }

  const sample = (arr, x, z) => {
    const fx = Math.min(nx - 1.001, Math.max(0, (x - x0) / CELL));
    const fz = Math.min(nz - 1.001, Math.max(0, (z - z0) / CELL));
    const ix = Math.floor(fx), iz = Math.floor(fz);
    const tx = fx - ix, tz = fz - iz;
    const a = arr[ix * nz + iz], b = arr[(ix + 1) * nz + iz];
    const c = arr[ix * nz + iz + 1], d = arr[(ix + 1) * nz + iz + 1];
    return (a * (1 - tx) + b * tx) * (1 - tz) + (c * (1 - tx) + d * tx) * tz;
  };

  return {
    nx, nz, x0, z0, CELL,
    /** Terrain surface height under a world point. */
    height: (x, z) => sample(H, x, z),
    /** Distance from a world point to the nearest road centre. */
    toRoad: (x, z) => sample(D, x, z),
    gridH: H, gridD: D,
  };
}

/**
 * The run-off, swept along the ribbon rather than sampled from the grid.
 *
 * This is the whole reason the gravel is not part of `drawTerrain`. The height
 * field is an 8-unit grid, and its vertices do not lie on the road edge - so a
 * cell straddling the kerb interpolates across it and comes out above the
 * tarmac in some places and below it in others. What that looks like is gravel
 * sawing in and out of the road, gravel lying *over* the road, and a hole at
 * the edge of a corner you can drop through. All of that was one bug.
 *
 * Sweeping the ribbon fixes it by construction: these quads are built from the
 * same stations and the same `lat` the road is, so the inner edge of the run-off
 * is the road's edge, exactly, all the way round.
 *
 * The apron sits `drop` below the road from the kerb outward rather than
 * meeting it flush, for the reason the flat ground plate does: coplanar road
 * and run-off makes the ground query a coin toss between them, and the car
 * spends whole corners behaving as if it were on gravel.
 */
function addApron(buf, col, track, pal, terrain, cfg, drop) {
  const line = track.line;
  const A = cfg.apron != null ? cfg.apron : 34;
  const gTo = cfg.gravel != null ? cfg.gravel : 22;
  const grit = pal.gravel != null ? pal.gravel : pal.ground;
  // Bands, as distances from the road *centre*. The gravel/grass change is a
  // band boundary rather than a per-quad colour test, so the edge is a clean
  // line along the road instead of a staircase.
  // The lift is not slop. Where the swept apron and the height field overlap
  // they are all but coplanar - both are "nearest road height, less the drop" -
  // and coplanar surfaces z-fight into a shimmering mess along the entire
  // circuit, so the apron is raised a hair to settle the depth test in its
  // favour.
  //
  // It was 0.03, and 0.03 is only enough if the two surfaces really do agree.
  // They did not: the field used to take its height from the nearest *station*
  // rather than the nearest point on the ribbon, so it stepped by a whole
  // station's rise while the apron interpolated, and on the descent it stood a
  // third of a unit proud of the gravel in patches all the way down the hill.
  // `buildTerrain` no longer does that, and this is the margin over what is
  // left: an eighth of the drop, well under what reads as a step, and past the
  // 99th percentile of the disagreement that remains.
  //
  // **A banked station has far less room for it, and none to spare.** The apron
  // is one horizontal band at the station's *centre* height, so on a rolled
  // station the road's lower kerb is already `|lat.y| * hw` beneath that centre
  // - 1.17 units through Pouhon's eight degrees, against a drop of 1.2. The
  // whole clearance between the run-off and the low side of the road there is
  // three hundredths of a unit, and a flat 0.15 spends five times it: the gravel
  // comes up *through* the left-hand kerb and the edge of the road reads as
  // lifted, which is exactly what it looks like from the car. So the lift is
  // whatever the bank leaves - full value on the 96% of the circuit that is flat,
  // and squeezed to nothing round the one corner that is not.
  const LIFT = 0.15;
  const lift = (e) => Math.max(0.01,
    Math.min(LIFT, drop - Math.abs(e.lat[1]) * e.hw - 0.01));
  const at = (e, o) => [e.p[0] + e.lat[0] * o, e.p[1] - drop + lift(e),
                        e.p[2] + e.lat[2] * o];

  // How far this station's run-off may reach on this side before it starts
  // laying gravel over some *other* part of the circuit.
  //
  // Spa's legs pass as close as 43 units, and two aprons of 38 do not fit in
  // that - so without this the Pouhon apron is drawn straight across the
  // Blanchimont tarmac, at Pouhon's height. That is the "gravel covering the
  // road" and the stray quads hanging in the infield: both are one apron
  // trespassing on another leg.
  //
  // The test needs nothing to know which corners are tight. `toRoad` is the
  // distance to the *nearest* road centre, so at a point `o` out from our own
  // road it reads back `o` exactly when we are the nearest thing - and less
  // when somebody else is. Clipping on that makes the union of all the aprons
  // cover everything within reach of the ribbon exactly once.
  const reach = (e, s) => {
    let lim = A;
    for (let o = e.hw; o <= A; o += 2) {
      const p = at(e, s * o);
      if (terrain.toRoad(p[0], p[2]) < o - 2.5) { lim = o - 2; break; }
    }
    return Math.max(e.hw, lim);
  };
  const lims = [];
  for (const e of line) lims.push([reach(e, -1), reach(e, 1)]);

  // Taper the limit instead of letting it drop off a cliff. The test above is
  // per station, so a run-off that has to give way to a neighbouring leg used
  // to go from its full width to nothing between two stations 3.5 units apart,
  // and that wedge is the last of the stray shards in the infield. Two sweeps
  // with a slope cap turn the cut into a gentle taper; the track is a ring, so
  // they wrap.
  const N = lims.length, SLOPE = 1.4;
  for (const k of [0, 1]) {
    for (let pass = 0; pass < 2; pass++) {
      for (let i = 1; i <= N; i++) {
        const p = lims[(i - 1) % N][k], c = i % N;
        lims[c][k] = Math.min(lims[c][k], p + SLOPE);
      }
      for (let i = N - 1; i >= -1; i--) {
        const nx = lims[((i + 1) % N + N) % N][k], c = ((i % N) + N) % N;
        lims[c][k] = Math.min(lims[c][k], nx + SLOPE);
      }
    }
  }

  for (let i = 0; i + 1 < line.length; i++) {
    const a = line[i], b = line[i + 1];
    if (a.air || b.air) continue;
    for (const s of [-1, 1]) {
      const cap = Math.min(lims[i][s < 0 ? 0 : 1], lims[i + 1][s < 0 ? 0 : 1]);
      const edges = [a.hw, Math.min(gTo, cap), Math.min(A, cap)];
      for (let k = 0; k + 1 < edges.length; k++) {
        const o0 = s * edges[k], o1 = s * edges[k + 1];
        if (Math.abs(edges[k + 1]) <= Math.abs(edges[k]) + 0.05) continue;
        // No snapping the outer edge onto the height field. It looks like the
        // careful thing to do and it is what produced the shards hanging in the
        // infield: `terrain.height` returns the height of whatever road is
        // *nearest*, so wherever two legs pass close the outer corners of these
        // quads got yanked to the other leg's height and the band came out as a
        // skewed sheet across the gap. It is unnecessary as well as wrong -
        // inside the apron the height field is already `nearest road - drop`
        // by construction (see buildTerrain), which is exactly this height, so
        // the two surfaces meet on their own.
        const p0 = at(a, o0), p1 = at(b, o0), p2 = at(b, o1), p3 = at(a, o1);
        const c = k === 0 ? grit : pal.ground;
        buf.quad(p0, p1, p2, p3, c);
        buf.quad(p3, p2, p1, p0, c);
        col.addQuad(p0, p1, p2, p3, KIND.OFFROAD);
      }
      // The lip under the kerb, so the step down to the gravel reads as a step
      // rather than as the road floating. It has to reach the *kerb*, which on a
      // rolled station is not `drop` above the run-off: the apron is one
      // horizontal band at the station's centre height, so a bank puts one kerb
      // above it and the other below. Standing the lip a fixed `drop` tall was
      // the old way and it built a wall - through Pouhon's eight degrees the
      // inside lip finished 1.19 units *over* the road it was supposed to be
      // holding up, which from the car is the left-hand edge of the track lifted
      // into the air for the length of the corner, and the outside kerb was left
      // hanging over a lip 1.16 too short to meet it. Both are the same missing
      // term. (`e.lat[1] * hw` is the kerb height for a station with no
      // cross-section; the run-off only exists on a terrain track and no track
      // in the pool is both, so there is no profile to sample here.)
      const kerbY = (e) => e.p[1] + e.lat[1] * s * e.hw;
      const k0 = at(a, s * a.hw), k1 = at(b, s * b.hw);
      const t0 = [k0[0], kerbY(a), k0[2]], t1 = [k1[0], kerbY(b), k1[2]];
      buf.quad(t0, t1, k1, k0, shade(pal.road, -0.25));
      buf.quad(k0, k1, t1, t0, shade(pal.road, -0.25));
    }
  }
}

/**
 * The armco: a continuous barrier set well back from the road, standing on the
 * terrain, with sponsor hoardings on it.
 *
 * This is deliberately **not** the `rail` mechanic. A rail is a wall on the
 * kerb, which on a Grand Prix circuit would make the run-off decorative and the
 * whole lap a bobsleigh run. This sits past the gravel: you can run wide, lose
 * time in the grit and come back, but you cannot drive into the forest.
 *
 * Where the circuit doubles back on itself - the inside of La Source, Rivage,
 * the Bus Stop - there is not room for a barrier and the two sides would meet
 * in the middle. Nothing has to know which corners those are: if the nearest
 * road centre to a barrier post is closer than the barrier's own offset, some
 * *other* part of the track is there, and the segment is skipped.
 *
 * One collision quad per segment, not two, for the reason `wallStrip` gives:
 * the wall query works its push-out direction out from the closest point on the
 * triangle, so a single face stops a car arriving from either side, and a
 * second face makes every contact fire twice and scrub the car's speed.
 */
function addArmco(buf, col, track, pal, terrain, cfg, drop) {
  const line = track.line;
  const back = cfg.armco != null ? cfg.armco : 26;
  const H = cfg.armcoH != null ? cfg.armcoH : 1.7;
  const rail = pal.rail != null ? pal.rail : 0xd8dde2;
  const posts = [];                 // where a hoarding may later be hung

  // Each post carries the way back to the road, so a board hung here knows
  // which face to print on.
  //
  // The footing comes from the barrier's *own* station rather than from
  // `terrain.height`, and that is the fix for the jagged pale streak that used
  // to run through the infield. The height field returns the height of whatever
  // road is nearest, so a barrier standing 27 units out beside a place where
  // two legs pass close had its footing flip between the two from post to post
  // and zigzagged through forty units of height. Everything inside the apron
  // stands on the road it belongs to, which is also what the run-off does.
  const at = (e, s) => {
    const x = e.p[0] + e.lat[0] * s * back;
    const z = e.p[2] + e.lat[2] * s * back;
    const p = [x, e.p[1] - drop - 0.2, z];
    p.n = [-s * e.lat[0], 0, -s * e.lat[2]];
    return p;
  };
  for (const s of [-1, 1]) {
    let run = [];
    const flush = () => {
      for (let k = 0; k + 1 < run.length; k++) {
        const a = run[k], b = run[k + 1];
        const at2 = [a[0], a[1] + H, a[2]], bt = [b[0], b[1] + H, b[2]];
        col.addQuad(a, b, bt, at2, KIND.WALL);
        buf.quad(a, b, bt, at2, rail);
        buf.quad(at2, bt, b, a, rail);
        // a dark plinth, so the barrier reads as standing on the ground rather
        // than as a ribbon hovering over it
        buf.quad([a[0], a[1], a[2]], [b[0], b[1], b[2]],
                 [b[0], b[1] - 0.55, b[2]], [a[0], a[1] - 0.55, a[2]], shade(rail, -0.55));
      }
      if (run.length > 3) posts.push(run.slice());
      run = [];
    };
    for (let i = 0; i < line.length; i++) {
      const e = line[i];
      if (e.air || e.pf || e.n[1] < 0.75) { flush(); continue; }
      const p = at(e, s);
      // Another part of the circuit is closer than our own offset, so there is
      // no room here - the inside of a hairpin, or a leg passing alongside.
      if (terrain.toRoad(p[0], p[2]) < back - 2.5) { flush(); continue; }
      run.push(p);
    }
    flush();
  }
  return posts;
}

/**
 * A buffer of textured quads, one per sponsor board.
 *
 * The rest of the world here is flat-shaded vertex colour with no textures at
 * all, and this is the one exception: a hoarding has to be *readable*, and
 * letters built out of boxes stop being letters about forty units away, which
 * is where you actually see them from. So boards carry a canvas texture - the
 * same trick render.js already uses for the name tags over the cars.
 *
 * The quads are written in world space with their UVs, and every board sharing
 * a sponsor shares one buffer, so the whole circuit's advertising is five or
 * six draw calls rather than one per board.
 */
class SignBuf {
  constructor() { this.pos = []; this.uv = []; }
  /** A quad from its centre, a half-width along `r` and a half-height along `u`.
   *
   *  `r` is flipped if needed so the face's winding points at `n` - the board
   *  has to face the road it is advertising to, and which way a mirrored
   *  placement ends up winding is not something the caller should have to
   *  reason about. Everything here is single sided: the back of a board is a
   *  plain panel in the world mesh, not the same word printed in mirror
   *  writing, which is what DoubleSide gives you.
   */
  panel(c, r, u, hw, hh, n) {
    // face normal is r x u; flip r if that points away from the road
    const cr = [r[1] * u[2] - r[2] * u[1], r[2] * u[0] - r[0] * u[2],
                r[0] * u[1] - r[1] * u[0]];
    if (n && cr[0] * n[0] + cr[1] * n[1] + cr[2] * n[2] < 0) {
      r = [-r[0], -r[1], -r[2]];
    }
    const P = (sr, su) => [c[0] + r[0] * sr * hw + u[0] * su * hh,
                           c[1] + r[1] * sr * hw + u[1] * su * hh,
                           c[2] + r[2] * sr * hw + u[2] * su * hh];
    const a = P(-1, -1), b = P(1, -1), d = P(1, 1), e = P(-1, 1);
    for (const [v, uv] of [[a, [0, 0]], [b, [1, 0]], [d, [1, 1]],
                           [a, [0, 0]], [d, [1, 1]], [e, [0, 1]]]) {
      this.pos.push(v[0], v[1], v[2]);
      this.uv.push(uv[0], uv[1]);
    }
    return [a, b, d, e];
  }
  toMesh(tex) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    g.computeVertexNormals();
    return new THREE.Mesh(g, new THREE.MeshBasicMaterial({
      map: tex, side: THREE.FrontSide, fog: true,
    }));
  }
}

/**
 * Every mark that goes on a board, as a file.
 *
 * None of these is drawn in code, and the four that are not this site's used to
 * be. A shield, a bell, a chevron and an eagle's head are each a few dozen
 * canvas paths, they were all *recognisable*, and every one of them was
 * obviously a drawing of a logo rather than the logo - which on a board whose
 * entire job is to read as a brand at a hundred miles an hour is the only thing
 * that matters. The real artwork is smaller than the code that approximated it.
 *
 * Three come from inside this repo: Ticket to Ride's locomotive is the file its
 * own site draws, and King of Tokyo's monster and Rat Screw's pyramid are those
 * games' app icons. The other four are the brands' own, off Wikipedia. Penn's
 * is a PNG resampled to 1200 wide - the original is 2908 and half a megabyte,
 * for a mark that is never drawn wider than about 200 pixels.
 *
 * They load as `Image`s off the static tree and land after the track is built,
 * which is fine - see `signTexture`, which repaints when they do.
 */
const LOGOS = {
  ttr: '/static/img/sponsors/ttr-train.svg',
  kot: '/static/img/sponsors/kot.svg',
  ers: '/static/img/sponsors/ers.svg',
  penn: '/static/img/sponsors/penn.png',
  taco: '/static/img/sponsors/tacobell.svg',
  marlboro: '/static/img/sponsors/marlboro.svg',
  eagles: '/static/img/sponsors/eagles.svg',
  costco: '/static/img/sponsors/costco.svg',
};
const _logo = {};
function logo(key) {
  if (key in _logo) return _logo[key].im;
  const im = new Image();
  const ready = new Promise((res) => { im.onload = res; im.onerror = res; });
  im.src = LOGOS[key];
  _logo[key] = { im, ready };
  return im;
}

/** Every face a board is set in, asked for by name so the browser fetches it.
 *
 *  A `@font-face` is only downloaded when something on the page is *set* in it,
 *  and nothing on the play page is set in any of these - they exist for the
 *  boards alone. Without an explicit `load` the rule sits there unused, the
 *  canvas silently falls back, and Spa's advertising comes out in whatever the
 *  machine had lying around. `document.fonts.ready` on its own does not fix
 *  this: it resolves happily, having loaded nothing.
 */
const BOARD_FONTS = ['700 60px Cinzel', '400 60px "xkcd Script"',
                     '400 60px Metamorphous', '900 60px "Titillium Web"',
                     'italic 800 60px "Barlow Condensed"'];
/** One promise for the whole of a board's artwork, shared by every board.
 *
 *  It has to be shared. Each texture used to hang its own `onload` on the three
 *  `Image`s, which are one object each however many boards want them - so the
 *  ninth board's handler replaced the eighth's, the first eight never heard
 *  that anything had arrived, and the only board on the circuit that ever
 *  repainted was whichever happened to be built last. What you get is the
 *  layout you designed with none of the logos on it and the fallback font, and
 *  it looks deliberate.
 */
let _art = null;
function boardArt() {
  if (_art) return _art;
  if (typeof document === 'undefined') return (_art = Promise.resolve());
  const waits = Object.keys(LOGOS).map((k) => { logo(k); return _logo[k].ready; });
  if (document.fonts) {
    waits.push(...BOARD_FONTS.map((f) => document.fonts.load(f).catch(() => {})));
  }
  return (_art = Promise.all(waits));
}

// --- drawing helpers shared by the boards -----------------------------------

/** Fill the board and put a hairline frame on it. */
function plate(g, W, H, bg, edge) {
  g.fillStyle = bg;
  g.fillRect(0, 0, W, H);
  if (edge) {
    g.strokeStyle = edge;
    g.lineWidth = Math.round(H * 0.035);
    g.strokeRect(g.lineWidth / 2, g.lineWidth / 2, W - g.lineWidth, H - g.lineWidth);
  }
}

/** A wordmark, centred on (cx, cy), squeezed rather than clipped if it is wide.
 *
 *  Canvas has no letter-spacing, so tracking is drawn a glyph at a time. The
 *  squeeze is horizontal only: a sponsor with a long name gets a condensed
 *  wordmark, which is what a real one would do, rather than a smaller one that
 *  stops being readable from the far side of the road.
 */
function word(g, str, cx, cy, maxW, opt) {
  const o = opt || {};
  g.save();
  g.font = o.font;
  g.textAlign = 'left';
  g.textBaseline = 'middle';
  const tr = o.track || 0;
  const glyphs = str.split('');
  const w = glyphs.reduce((a, ch) => a + g.measureText(ch).width, 0) + tr * (glyphs.length - 1);
  const k = w > maxW ? maxW / w : 1;
  g.translate(cx, cy);
  if (o.slant) g.transform(1, 0, -o.slant, 1, 0, 0);
  g.scale(k, 1);
  let x = -w / 2;
  for (const ch of glyphs) {
    if (o.shadow) {
      g.fillStyle = o.shadow;
      g.fillText(ch, x + (o.shadowAt || 3), (o.shadowAt || 3));
    }
    g.fillStyle = o.fill;
    g.fillText(ch, x, 0);
    if (o.stroke) {
      g.lineWidth = o.strokeW || 3;
      g.strokeStyle = o.stroke;
      g.strokeText(ch, x, 0);
    }
    x += g.measureText(ch).width + tr;
  }
  g.restore();
  return w * k;
}

/** A hot dog, in paths, centred on (cx, cy) and `h` tall.
 *
 *  Drawn rather than fetched, and that is not the same decision the four outside
 *  brands made. Their marks are commissioned artwork with a single correct
 *  version, so the file has to *be* that version; a hot dog is a hot dog, there
 *  is no authoritative drawing of one to get wrong, and drawing it keeps the
 *  board free of an eighth asset.
 *
 *  Only ops the board test's stub canvas implements: no `ellipse` and no
 *  `roundRect`, so the rounded ends are `arc` under a `scale` and the mustard is
 *  a `quadraticCurveTo` zigzag. A painter that reaches past the stub throws
 *  inside `buildTrack`, which takes the whole track down with it.
 */
function hotdog(g, cx, cy, h) {
  // Short and fat rather than long and thin. At 1.55 by 0.27 it came out a sliver
  // on the board and read as a stray yellow line, not as food.
  const L = h * 1.28, r = h * 0.38;
  // Bun: a long capsule, drawn as a rect between two round ends.
  const cap = (x, rad, k) => {
    g.beginPath();
    g.arc(x, cy, rad, 0, Math.PI * 2);
    g.fillStyle = k;
    g.fill();
  };
  g.fillStyle = '#e0a75c';
  g.fillRect(cx - L / 2, cy - r, L, r * 2);
  cap(cx - L / 2, r, '#e0a75c');
  cap(cx + L / 2, r, '#e0a75c');
  // Sausage, sitting a little proud of the bun.
  const sr = r * 0.62, sl = L * 1.04;
  g.fillStyle = '#a8422c';
  g.fillRect(cx - sl / 2, cy - sr * 0.55, sl, sr * 1.1);
  for (const s of [-1, 1]) cap(cx + s * sl / 2, sr * 0.55, '#a8422c');
  // Mustard.
  g.strokeStyle = '#f2c033';
  g.lineWidth = Math.max(1, h * 0.075);
  g.beginPath();
  g.moveTo(cx - sl * 0.42, cy);
  const step = sl * 0.84 / 4;
  for (let k = 0; k < 4; k++) {
    const x0 = cx - sl * 0.42 + step * k;
    g.quadraticCurveTo(x0 + step * 0.5, cy + (k % 2 ? sr * 0.85 : -sr * 0.85),
                       x0 + step, cy);
  }
  g.stroke();
}

/** One of the copied SVGs, recoloured and fitted into a box.
 *
 *  Recolouring is a `source-in` fill on a scratch canvas rather than a filter,
 *  because these are flat single-colour marks on boards whose palette is not
 *  the website's - Ticket to Ride's locomotive is black artwork and its board
 *  is gold on near-black. `tint` of null leaves the artwork as it is, which is
 *  what the two app icons want: they are whole badges, not silhouettes.
 *
 *  **Both box dimensions are required and the tint is seventh.** Every call
 *  site used to pass six arguments, so the tint landed in `maxH`: the scale
 *  came out `NaN` for a colour and `0` for a `null`, `drawImage` got a
 *  degenerate rectangle, and not one of the seven logos was ever drawn. Nothing
 *  threw and every board still painted, which is the whole problem - a mark
 *  that fails does so by leaving a gap in a layout that is otherwise correct.
 *  `test_boards.py` now checks the destination rectangle of every `drawImage`.
 */
function mark(g, key, x, y, maxW, maxH, tint) {
  markPart(g, key, null, x, y, maxW, maxH, tint);
}

/** Part of a lockup - its symbol, or its name - as a fraction of the file.
 *
 *  Taco Bell's artwork and Marlboro's are one image with the mark stacked above
 *  the name, and a hoarding is 4:1. Fitted whole, the Taco Bell lockup is a
 *  fifth of the board wide and the other four fifths are plate: from the car
 *  that is a white rectangle with a smudge on it, which is the one thing a
 *  hoarding may not be. Drawn as two source rectangles side by side it fills
 *  the board the way Ticket to Ride's mark-then-wordmark does, and every pixel
 *  is still the brand's own - which matters, because all three of these brands
 *  use commissioned lettering that no font will give you.
 *
 *  `box` is `[x, y, w, h]` in fractions of the natural size, so it survives the
 *  artwork being re-exported at another resolution. **Measure them, do not
 *  guess**: the two are not cleanly stacked. Marlboro's roof reaches lower at
 *  its outer corners than the wordmark's ascenders reach up, so the obvious cut
 *  puts a red triangle over each end of the word and a black serif under the
 *  roof. The boxes below are where the ink actually is.
 */
function markPart(g, key, box, x, y, maxW, maxH, tint) {
  const im = logo(key);
  if (!im.complete || !im.naturalWidth) return;
  // Crop off a rasterised copy, never off the SVG. A source rectangle on an
  // `<img>` holding an SVG is measured against whatever Chrome decided to
  // rasterise it at, which is **not** `naturalWidth` unless the file carries
  // width and height attributes - and `marlboro.svg` carries only a viewBox, so
  // it reports the 249x150 default-replaced-element size and then reads its own
  // source rectangle against a much larger bitmap. What that looks like is both
  // halves of the lockup showing the wrong band of the artwork: the roof came
  // out a plain red bar and the wordmark came out as the right-hand slope of
  // the roof with the tops of four letters under it. Every other file here has
  // intrinsic dimensions and cropped correctly, which is how it survived being
  // looked at. A canvas has exact pixel semantics and no such question.
  const src = box ? sheet(key, im) : im;
  const nw = box ? src.width : im.naturalWidth;
  const nh = box ? src.height : im.naturalHeight;
  const b = box || [0, 0, 1, 1];
  const sx = b[0] * nw, sw = b[2] * nw;
  const sy = b[1] * nh, sh = b[3] * nh;
  const s = Math.min(maxW / sw, maxH / sh);
  const w = sw * s, h = sh * s;
  const dx = x - w / 2, dy = y - h / 2;
  if (!tint) { g.drawImage(src, sx, sy, sw, sh, dx, dy, w, h); return; }
  const sc = document.createElement('canvas');
  sc.width = Math.max(1, Math.round(w)); sc.height = Math.max(1, Math.round(h));
  const sg = sc.getContext('2d');
  sg.drawImage(src, sx, sy, sw, sh, 0, 0, sc.width, sc.height);
  sg.globalCompositeOperation = 'source-in';
  sg.fillStyle = tint;
  sg.fillRect(0, 0, sc.width, sc.height);
  g.drawImage(sc, dx, dy, w, h);
}

const _sheet = {};
/** The artwork rasterised once at a known size, so a crop can index into it.
 *
 *  Drawn whole and unscaled-from, which is the one drawImage form an SVG with
 *  no intrinsic size still gets right. 1024 on the long edge is more than any
 *  board asks for - the widest a mark is ever drawn is about 630.
 */
function sheet(key, im) {
  if (_sheet[key]) return _sheet[key];
  const k = 1024 / Math.max(im.naturalWidth, im.naturalHeight);
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(im.naturalWidth * k));
  c.height = Math.max(1, Math.round(im.naturalHeight * k));
  c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
  return (_sheet[key] = c);
}

// Where the mark stops and the name starts in the two stacked lockups, as
// fractions of the file. Measured off the rendered artwork, not authored.
const PARTS = {
  tacoBell: [0, 0, 1, 0.816],       // the bell, clear of the wordmark
  tacoWord: [0, 0.874, 1, 0.126],   // "TACO BELL"
  marlRoof: [0, 0, 1, 0.452],       // the roof, cut at the first serif below it
  marlWord: [0.049, 0.50, 0.902, 0.432],
};

/**
 * The sponsors, each drawing its own board.
 *
 * These used to be a colour and a font stack fed through one generic layout,
 * and six near-identical rectangles is what that looks like from the car. Each
 * one now paints the whole 4:1 canvas, so it can carry the mark the thing it
 * advertises actually uses and be laid out the way that brand lays itself out.
 *
 * The colours are still the ones those pages use, which is what makes a board
 * read as *that* game rather than as advertising in general: the landing page's
 * per-game accents, ERS's wood and gold, King of Tokyo's purple-and-gold poster,
 * Ticket to Ride's gold on near-black, and Drive's own ink-on-paper with the
 * red it uses for a finish line.
 *
 * The four that are not this site are their own artwork end to end. Three of
 * them ship their name as part of it - Penn's shield beside "Penn Engineering",
 * Taco Bell's bell over "TACO BELL", Marlboro's roof over "Marlboro" - and all
 * three of those names are commissioned lettering with no public font behind
 * them, so the file is the only correct version and nothing here is set in
 * type beside it. `GO BIRDS` is the exception and the reason for the fourth
 * self-hosted face: it is a fan phrase, not a wordmark, so no artwork of it
 * exists anywhere to draw.
 */
const SPONSORS = {
  // White ground, lowercase, hand-drawn - the landing page's own voice.
  'CGOVIND.COM': (g, W, H) => {
    plate(g, W, H, '#ffffff', '#1d1d1f');
    word(g, 'cgovind.com', W / 2, H * 0.5, W * 0.80,
         { font: '400 ' + (H * 0.52) + 'px "xkcd Script", cursive', fill: '#1d1d1f' });
  },

  'TICKET TO RIDE': (g, W, H) => {
    plate(g, W, H, '#14120f', '#c8a84b');
    mark(g, 'ttr', H * 0.58, H * 0.5, H * 0.68, H * 0.68, '#c8a84b');
    word(g, 'TICKET TO RIDE', W * 0.60, H * 0.5, W * 0.63,
         { font: '700 ' + (H * 0.42) + 'px Cinzel, Georgia, serif',
           fill: '#e8c97a', track: H * 0.03 });
  },

  // The short name the site's own nav uses, not the full one, and set in caps
  // like every other wordmark on the circuit.
  'RAT SCREW': (g, W, H) => {
    plate(g, W, H, '#3f2311', '#b8860b');
    mark(g, 'ers', H * 0.60, H * 0.5, H * 0.72, H * 0.72, null);
    word(g, 'RAT SCREW', W * 0.60, H * 0.52, W * 0.62,
         { font: '400 ' + (H * 0.50) + 'px Metamorphous, Georgia, serif',
           fill: '#f2c94c', shadow: 'rgba(0,0,0,0.55)', shadowAt: H * 0.035 });
  },

  'KING OF TOKYO': (g, W, H) => {
    plate(g, W, H, '#211b33', '#f2c94c');
    mark(g, 'kot', H * 0.60, H * 0.5, H * 0.74, H * 0.74, null);
    word(g, 'KING OF TOKYO', W * 0.60, H * 0.5, W * 0.64,
         { font: '900 ' + (H * 0.44) + 'px "Arial Narrow", "Franklin Gothic Bold", '
                 + 'Impact, "Titillium Web", sans-serif',
           fill: '#f2c94c', track: H * 0.02, stroke: '#eb5757', strokeW: H * 0.012 });
  },

  // The one lockup that is already horizontal - shield beside wordmark, near
  // enough 3:1 - so unlike the other two it fills a hoarding without being
  // unstacked. The artwork is navy on transparent, which makes the Penn blue
  // this board used to be ground the one colour it cannot go on: navy on navy
  // is a blank board. The blue is the hairline instead, and drawn untinted the
  // shield keeps its red band.
  'PENN ENGINEERING': (g, W, H) => {
    plate(g, W, H, '#f7f5f2', '#011f5b');
    mark(g, 'penn', W / 2, H * 0.5, W * 0.86, H * 0.84, null);
  },

  // The warehouse's own name, over its own front door. Like Penn's this lockup
  // is already horizontal - 2.79:1 against a 4:1 board - so it is drawn whole
  // and untinted rather than unstacked into two source rectangles, which also
  // keeps it clear of the crop-off-a-rasterised-copy problem entirely.
  //
  // No type anywhere in here, and that is the rule rather than laziness: the
  // wordmark is set in a commissioned face with nothing public behind it, so the
  // file *is* the correct spelling of the name and anything set beside it would
  // be a guess at it and a second copy of it. The plate is white because the
  // artwork's own ground is, so the two meet invisibly; the hairline is the
  // brand's blue and the red comes from the artwork.
  'COSTCO WHOLESALE': (g, W, H) => {
    plate(g, W, H, '#ffffff', '#005daa');
    mark(g, 'costco', W / 2, H * 0.5, W * 0.9, H * 0.86, null);
  },

  // The food court board. Type only, and legitimately so - unlike the four
  // outside brands this is a *price*, not a wordmark, so there is no artwork of
  // it that would be the correct version of it. Same reason `GO BIRDS` is set in
  // type: it is a phrase rather than a mark.
  '$1.50 HOT DOG': (g, W, H) => {
    plate(g, W, H, '#e31837', '#ffffff');
    // The picture on the left, the price stacked over the words on the right.
    // Three things side by side does not work on a 4:1 board: `word` centres on
    // its own x and only squeezes once it overruns `maxW`, so laying the price and
    // the name out as neighbours either overlaps them or leaves each condensed
    // into a strip. Stacked, both lines get the full width of their half.
    hotdog(g, W * 0.135, H * 0.5, H * 0.82);
    word(g, '$1.50', W * 0.60, H * 0.36, W * 0.60,
         { font: '900 ' + (H * 0.46) + 'px "Titillium Web", Impact, sans-serif',
           fill: '#ffffff' });
    word(g, 'HOT DOG + SODA', W * 0.60, H * 0.775, W * 0.62,
         { font: '900 ' + (H * 0.235) + 'px "Titillium Web", Impact, sans-serif',
           fill: '#ffffff', track: H * 0.014 });
  },

  // Bell then wordmark, both the brand's own, unstacked to fill the board.
  // Taco Bell's lettering is a 2016 commission and has never been released as a
  // font, so anything set here in type would be a guess at it - the file is the
  // real thing.
  'TACO BELL': (g, W, H) => {
    plate(g, W, H, '#ffffff', '#702082');
    markPart(g, 'taco', PARTS.tacoBell, H * 0.60, H * 0.5, H * 0.86, H * 0.82, null);
    markPart(g, 'taco', PARTS.tacoWord, W * 0.60, H * 0.52, W * 0.62, H * 0.36, null);
  },

  // The roof and the wordmark, which is the whole of what a Marlboro board is.
  // It was drawn here in paths - five `lineTo`s, with Titillium standing in for
  // Neo Contact - back when the other three marks were too, and it was the last
  // of the four still doing it. The plate is white because the artwork's ground
  // is, so the two meet invisibly and the board reads as one piece.
  'MARLBORO': (g, W, H) => {
    plate(g, W, H, '#ffffff', '#d0d0d0');
    // The roof spans the whole width of its own artwork, so drawn to its own
    // aspect beside the wordmark it reads as a flat red stripe rather than as a
    // roof. Squeezed to 0.6 across it gets the pack's proportions back. This is
    // the only mark on the circuit not drawn to its own shape, and it is safe
    // here because the roof is a plain chevron - no lettering is distorted.
    const cx = W * 0.24;
    g.save();
    g.translate(cx, 0); g.scale(0.6, 1); g.translate(-cx, 0);
    markPart(g, 'marlboro', PARTS.marlRoof, cx, H * 0.5, H * 1.60, H * 0.64, null);
    g.restore();
    markPart(g, 'marlboro', PARTS.marlWord, W * 0.65, H * 0.52, W * 0.50, H * 0.54, null);
  },

  // The one outside board that does need type: the eagle is artwork but "GO
  // BIRDS" is a fan phrase, not a wordmark, so no file anywhere has it. The
  // team's lettering is custom and only unofficial recreations of it exist,
  // which is not something to commit here - Barlow Condensed's heavy italic is
  // the nearest face with a licence, and the head does the recognising anyway.
  // Drawn untinted: the artwork's own midnight green is this board's ground, so
  // it drops out and leaves the silver and white of the head behind.
  'GO BIRDS': (g, W, H) => {
    plate(g, W, H, '#004c54', '#a5acaf');
    mark(g, 'eagles', H * 0.66, H * 0.5, H * 1.05, H * 0.80, null);
    word(g, 'GO BIRDS', W * 0.62, H * 0.52, W * 0.58,
         { font: 'italic 800 ' + (H * 0.56) + 'px "Barlow Condensed", "Titillium Web", '
                 + 'Helvetica, Arial, sans-serif',
           fill: '#ffffff', track: H * 0.02 });
  },

  'DRIVE': (g, W, H) => {
    plate(g, W, H, '#1d1d1f', null);
    // Start-line chequer all the way round, so the board is Drive's and not any
    // board. `H / 8` divides a 4:1 hoarding exactly 32 by 8, so the run closes
    // on a whole cell at every corner instead of a sliver; and the colour comes
    // from the cell's own grid position rather than from a counter per side,
    // which is what keeps the alternation correct as it turns each corner.
    const c = H / 8;
    for (let iy = 0; iy * c < H - 0.5; iy++) {
      for (let ix = 0; ix * c < W - 0.5; ix++) {
        const x = ix * c, y = iy * c;
        if (x >= c && y >= c && x < W - c * 1.5 && y < H - c * 1.5) continue;
        g.fillStyle = (ix + iy) % 2 ? '#faf8f4' : '#1d1d1f';
        g.fillRect(x, y, c, c);
      }
    }
    // The red it uses for a finish line, as a rule inside the chequer.
    g.strokeStyle = '#c0182b';
    g.lineWidth = Math.max(1, H * 0.022);
    g.strokeRect(c + g.lineWidth / 2, c + g.lineWidth / 2,
                 W - 2 * c - g.lineWidth, H - 2 * c - g.lineWidth);
    word(g, 'DRIVE', W * 0.5, H * 0.52, W * 0.60,
         { font: '900 ' + (H * 0.56) + 'px "Titillium Web", Helvetica, Arial, sans-serif',
           fill: '#faf8f4', track: H * 0.09 });
  },
};

/** A sponsor board's texture: its wordmark and its mark, drawn onto a 4:1 canvas.
 *
 * 1024x256 rather than the 512x128 this started at, because the boards carry
 * artwork now: a pyramid or a locomotive at 128 tall is a smudge, and this is
 * ten textures on a track that already ships two hundred thousand triangles.
 *
 * **It draws twice, and the second time is the one you see.** Fonts and logos
 * both arrive asynchronously and the track is built long before either lands,
 * so the first pass is whatever is available - usually the right layout in the
 * wrong typeface with a gap where the mark goes. When the last of them resolves
 * the same canvas is repainted and the texture marked dirty, which three.js
 * uploads on the next frame. Getting this wrong is not loud: you get a
 * perfectly good-looking board set in the wrong font, on a track whose preview
 * picture is taken by a headless browser that owns almost no fonts at all.
 */
function signTexture(text) {
  const W = 1024, H = 256;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  const paint = SPONSORS[text] || ((gg, w, h) => {
    plate(gg, w, h, '#12161c', '#c0182b');
    word(gg, text, w / 2, h / 2, w * 0.8,
         { font: '900 ' + (h * 0.45) + 'px "Titillium Web", Helvetica, Arial, sans-serif',
           fill: '#f4f1ea' });
  });
  paint(g, W, H);
  const t = new THREE.CanvasTexture(c);
  t.anisotropy = 4;
  const again = () => {
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.clearRect(0, 0, W, H);
    paint(g, W, H);
    t.needsUpdate = true;
  };
  boardArt().then(again);
  return t;
}

/**
 * Everything beside the road that is not the road: grandstands, the pit
 * building and its wall, the start gantry, the bridge over Kemmel, and the
 * sponsor boards on all of it.
 *
 * Placement is by **fraction of the lap** rather than station index, so it
 * survives the ribbon being re-solved for closure (which changes how many
 * stations there are). Everything stands on `terrain`, so nothing floats or
 * sinks when the hillside moves under it.
 *
 * None of it is in the collider. The armco is the thing that stops a car, and
 * it is between the road and all of this - a grandstand you can hit is a
 * grandstand somebody will spend the lap parked inside.
 */
function addFurniture(solid, bright, signs, track, pal, terrain, cfg, drop) {
  const line = track.line;
  const n = line.length;
  const at = (f) => Math.max(0, Math.min(n - 1, Math.round(f * (n - 1))));
  const conc = cfg.concrete != null ? cfg.concrete : 0xb9b6ae;
  const dark = shade(conc, -0.45);

  // Where a building ended up, so the hoardings can stay out of it.
  //
  // A stand knows to keep off the *road*, and that is not the same as keeping
  // off the barrier: it stands 31 out and the circuit's own legs pass as close
  // as 43, so a stand can be perfectly clear of every road and still be sat on
  // top of another leg's armco - and a board hung on that armco then comes out
  // of the middle of a grandstand's end wall. One box per segment rather than
  // one round the whole building, because the stand at La Source follows 170
  // degrees of corner and its bounding rectangle is most of the infield.
  const keepOut = [];
  const boxes = (i0, i1, oA, oB, y0, y1) => {
    for (let i = i0; i < i1; i++) {
      let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
      for (const j of [i, i + 1]) {
        for (const o of [oA, oB]) {
          const [x, z] = spot(j, o);
          x0 = Math.min(x0, x); x1 = Math.max(x1, x);
          z0 = Math.min(z0, z); z1 = Math.max(z1, z);
        }
      }
      keepOut.push({ x0, x1, z0, z1, y0: y0(i), y1: y1(i) });
    }
  };

  // Every face here is drawn both ways round, and it has to be.
  //
  // The world mesh is `MeshLambertMaterial`, which is FrontSide, so a quad is
  // only visible from the side its winding faces. Furniture is placed by a
  // signed `side`, and flipping that sign mirrors the geometry and therefore
  // reverses the winding - so a stand authored on the left renders and the
  // identical stand on the right is invisible from the track. That is exactly
  // how the pit building came to be an invisible shed with a roof floating in
  // the sky. `wallStrip` solves the same problem the same way.
  const face = (a, b, c, d, col) => {
    solid.quad(a, b, c, d, col);
    solid.quad(a, d, c, b, col);
  };

  // A world point beside station i, `o` units to the road's right, on the deck.
  const spot = (i, o) => {
    const e = line[i];
    const x = e.p[0] + e.lat[0] * o, z = e.p[2] + e.lat[2] * o;
    return [x, z];
  };
  // Ground under a piece of furniture. Inside the apron that is the road's own
  // height less the drop - NOT `terrain.height`, which returns whatever road is
  // nearest and so jumps between legs wherever the circuit folds back on
  // itself. Beyond the apron there is no road to belong to and the field is the
  // only answer.
  const deck = (i, o) => {
    const e = line[i];
    const [x, z] = spot(i, o);
    return Math.abs(o) <= (cfg.apron != null ? cfg.apron : 38)
      ? e.p[1] - drop : terrain.height(x, z);
  };

  /** A grandstand: stepped seating facing the road, under a flat roof. */
  function stand(f0, f1, side, opts) {
    const i0 = at(f0), i1 = at(f1);
    if (i1 - i0 < 3) return;
    const off = (opts.off != null ? opts.off : (cfg.armco || 26) + 5) * side;
    // Refuse to build where another part of the circuit is already. A stand is
    // twenty units deep, so on a track that folds back on itself as tightly as
    // this one it is easy to author one that sits across a corner further round
    // the lap - which is what the stand behind the pits was doing to La Source.
    // Same test the armco and the run-off use: if the nearest road to our
    // footprint is nearer than our own offset, we are standing on someone else.
    const depthOut = Math.abs(off) + (opts.tiers != null ? opts.tiers : 8) * 1.7 + 4;
    for (let i = i0; i <= i1; i++) {
      for (const o of [Math.abs(off), depthOut]) {
        const [cx, cz] = spot(i, side * o);
        if (terrain.toRoad(cx, cz) < o - 3) return;
      }
    }
    const tiers = opts.tiers != null ? opts.tiers : 8;
    // Kept deliberately low. The first pass was 1.5 a row and 2.0 deep, which
    // at ten rows is a fifteen-unit wall standing over a sixteen-unit road -
    // from the car it read as a canyon rather than a circuit.
    const depth = 1.7, riseH = 1.0;
    // Where the roof board stands and how far the roof may wander out from
    // under it. The roof runs from 1.5 out to (tiers+1)*depth, so the shallowest
    // stand in the pool (six tiers) is 10.4 deep: standing the board 4 out with
    // 2.5 of slack keeps it between 1.5 and 6.5, on the roof either way it bows.
    const SET_BACK = 4.0, ROOF_SLACK = 2.5;
    // Level, like a real one. Sat on the highest ground under its footprint so
    // the downhill end is filled in rather than left hanging in the air.
    let base = -Infinity, foot = Infinity;
    for (let i = i0; i <= i1; i++) {
      base = Math.max(base, deck(i, off));
      foot = Math.min(foot, deck(i, off));
    }
    base -= 0.4;
    foot -= 6;                       // where the skirt is carried down to
    // Each stand takes its seating from whatever it is advertising, which is
    // where the colour on an overcast circuit comes from. Rows alternate
    // between the seat colour and a darker version of it, and every few rows
    // there is a band of the trim colour - a solid block of one hue across ten
    // rows reads as a painted ramp rather than as seating.
    const seat = opts.seat != null ? opts.seat : 0x7d8794;
    const trim = opts.trim != null ? opts.trim : shade(seat, 0.3);
    for (let i = i0; i + 1 <= i1; i++) {
      const e0 = line[i], e1 = line[i + 1];
      const lat0 = e0.lat, lat1 = e1.lat;
      const P = (e, lat, o, y) => [e.p[0] + lat[0] * o, y, e.p[2] + lat[2] * o];
      for (let k = 0; k < tiers; k++) {
        const oA = off + side * k * depth, oB = off + side * (k + 1) * depth;
        const y0 = base + k * riseH, y1 = base + (k + 1) * riseH;
        // tread: the row of seats
        face(P(e0, lat0, oA, y0), P(e1, lat1, oA, y0),
                   P(e1, lat1, oB, y0), P(e0, lat0, oB, y0),
                   k % 4 === 2 ? trim : (k % 2 ? seat : shade(seat, -0.22)));
        // riser: the concrete step up to the next row
        face(P(e0, lat0, oB, y0), P(e1, lat1, oB, y0),
                   P(e1, lat1, oB, y1), P(e0, lat0, oB, y1), conc);
      }
      // The front face, carried down to the ground under each end rather than
      // a fixed depth: the stand is level but the hillside is not, so a fixed
      // skirt leaves the downhill end hanging in the air.
      face(P(e0, lat0, off, Math.min(foot, deck(i, off) - 0.5)),
                 P(e1, lat1, off, Math.min(foot, deck(i + 1, off) - 0.5)),
                 P(e1, lat1, off, base), P(e0, lat0, off, base), dark);
      // the roof
      const yR = base + tiers * riseH + 4.2;
      const oBack = off + side * (tiers + 1) * depth;
      face(P(e0, lat0, off + side * 1.5, yR), P(e1, lat1, off + side * 1.5, yR),
                 P(e1, lat1, oBack, yR), P(e0, lat0, oBack, yR), shade(conc, 0.1));
      face(P(e0, lat0, oBack, yR), P(e1, lat1, oBack, yR),
                 P(e1, lat1, oBack, yR - 0.7), P(e0, lat0, oBack, yR - 0.7), dark);
      // the back wall, which is what the stand reads as from behind
      face(P(e0, lat0, oBack, Math.min(foot, deck(i, oBack) - 0.5)),
                 P(e1, lat1, oBack, Math.min(foot, deck(i + 1, oBack) - 0.5)),
                 P(e1, lat1, oBack, yR), P(e0, lat0, oBack, yR), shade(conc, -0.12));
    }
    // The gable ends. Without these a stand is a tube: the treads, the roof and
    // the back wall all run along the road and nothing closes either end, so
    // from anywhere but square on you look straight into it and see the inside
    // of its own roof. It reads as a hollow shell rather than a building, and it
    // is worse than an ordinary missing face because the seating is *lit* in
    // there - the eye reads it as a room you are meant to be looking into.
    //
    // One slab from the ground to the roof, rather than a wall stepped to
    // follow the seating. Stepping it was the first go and it leaves the
    // triangle between the top row and the roof open, which is precisely the
    // hole you look through - a real stand is solid to the roof at its ends for
    // the same reason, and at this polygon count the steps would be invisible
    // behind their own wall anyway.
    const oEndBack = off + side * (tiers + 1) * depth;
    const yRoof = base + tiers * riseH + 4.2;
    boxes(i0, i1, off, oEndBack,
          (i) => Math.min(foot, deck(i, off) - 0.5), () => yRoof);
    for (const j of [i0, i1]) {
      const e = line[j], lat = e.lat;
      const P = (o, y) => [e.p[0] + lat[0] * o, y, e.p[2] + lat[2] * o];
      face(P(off, Math.min(foot, deck(j, off) - 0.5)),
           P(oEndBack, Math.min(foot, deck(j, oEndBack) - 0.5)),
           P(oEndBack, yRoof), P(off, yRoof), shade(conc, -0.18));
    }

    // roof posts, sparse
    for (let i = i0; i <= i1; i += Math.max(3, Math.round((i1 - i0) / 6))) {
      const o = off + side * (tiers + 0.8) * depth;
      const [x, z] = spot(i, o);
      const g = deck(i, o), h = base + tiers * riseH + 4.2;
      solid.box(x, (g + h) / 2, z, 0.4, (h - g) / 2, 0.4, dark);
    }
    // A board standing on the roof, facing the track.
    //
    // It used to hang in front of the roof and 1.7 *below* its lip, which on
    // the three stands that sit on a curve put it straight through the roof and
    // the back rows of seating - the board is one flat quad and a stand round
    // the outside of La Source is not flat. Both halves of that are fixed here:
    // it stands on the roof rather than in front of it, and its width is
    // whatever keeps a straight board on a curved building.
    if (opts.text) {
      const mid = Math.round((i0 + i1) / 2);
      const e = line[mid];
      const oB = off + side * SET_BACK;
      const [x, z] = spot(mid, oB);
      const nx = line[Math.min(n - 1, mid + 1)];
      const along = [nx.p[0] - e.p[0], 0, nx.p[2] - e.p[2]];
      const L = Math.hypot(along[0], along[2]) || 1;
      const r = [along[0] / L, 0, along[2] / L];
      // Walk out from the middle until the roof under the board has wandered
      // off the tangent by more than it can afford, and stop there. On a
      // straight stand that is the whole stand; round La Source it is a shorter
      // board that is still on the building, which is the trade worth making.
      let reach = 0;
      for (let j = 1; j <= Math.max(i1 - mid, mid - i0); j++) {
        let worst = 0;
        for (const s2 of [1, -1]) {
          const jj = mid + s2 * j;
          if (jj < i0 || jj > i1) continue;
          const [px, pz] = spot(jj, oB);
          // perpendicular distance of the roof point from the tangent line
          worst = Math.max(worst, Math.abs((px - x) * r[2] - (pz - z) * r[0]));
        }
        if (worst > ROOF_SLACK) break;
        reach = j;
      }
      const hw = Math.min(12, Math.max(4, reach * 1.6));
      // Sat on the roof with its foot just clear of it.
      signs.push({ text: opts.text, c: [x, base + tiers * riseH + 4.35 + hw / 4, z],
                   r, u: [0, 1, 0], hw, hh: hw / 4,
                   n: [-side * e.lat[0], 0, -side * e.lat[2]] });
    }
  }

  /** The pit building: a long shed with a garage stripe, and the pit wall. */
  function pits(f0, f1, side) {
    const i0 = at(f0);
    const off = ((cfg.armco || 26) + 9) * side;
    const D = 13;
    const oF = off, oB = off + side * D;
    // Truncate where the far wall runs out of infield, rather than trusting the
    // authored end. The building is thirteen units deep and stands 35 out, and
    // La Source doubles the circuit back through 170 degrees a hundred units
    // later - so its back wall was crossing the road down to Eau Rouge and
    // finishing three quarters of a unit off that road's centreline, a shed
    // through the track one corner after the grid.
    //
    // Same signal the armco, the run-off and `stand` all use: `toRoad` is the
    // distance to the *nearest* road centre, so a footprint point that reads
    // back less than its own clearance has some other leg under it. `stand`
    // drops the whole thing; a building down the pit straight wants shortening
    // instead, because most of it is in the right place. CLEAR is twice a road's
    // half width, which keeps it off the tarmac with the run-off still showing
    // between - clearing the armco as well is not affordable here, since the
    // circuit's own legs pass as close as 43 units.
    const CLEAR = 16;
    let i1 = at(f1);
    for (let i = i0; i <= i1; i++) {
      const a = spot(i, oF), b = spot(i, oB);
      if (terrain.toRoad(a[0], a[1]) < CLEAR || terrain.toRoad(b[0], b[1]) < CLEAR) {
        i1 = i - 1;
        break;
      }
    }
    if (i1 - i0 < 3) return;
    // A building has one floor, so it stands on the highest ground under it -
    // and then it has to be carried *down* to the ground everywhere else, which
    // is what a grandstand's skirt does and what this did not. The pit straight
    // climbs eleven units from the grid to La Source, so the whole shed sat at
    // the La Source height with its far end eleven units off the ground: from
    // the grid it was the first thing you saw on your right and it was flying.
    let base = -Infinity, foot = Infinity;
    for (let i = i0; i <= i1; i++) {
      base = Math.max(base, deck(i, oF), deck(i, oB));
      foot = Math.min(foot, deck(i, oF), deck(i, oB));
    }
    foot -= 4;                       // buried, so no gap opens on a rough patch
    const H = 8.5;
    // Ground under the wall at station i, never above the floor it holds up.
    const sole = (i, o) => Math.min(foot, deck(i, o) - 0.5);
    boxes(i0, i1, oF, oB, (i) => sole(i, oF), () => base + H);
    for (let i = i0; i + 1 <= i1; i++) {
      const e0 = line[i], e1 = line[i + 1];
      const P = (e, o, y) => [e.p[0] + e.lat[0] * o, y, e.p[2] + e.lat[2] * o];
      // the plinth: from whatever the ground is doing up to the building's floor
      face(P(e0, oF, sole(i, oF)), P(e1, oF, sole(i + 1, oF)),
                 P(e1, oF, base), P(e0, oF, base), dark);
      face(P(e0, oB, sole(i, oB)), P(e1, oB, sole(i + 1, oB)),
                 P(e1, oB, base), P(e0, oB, base), dark);
      // front wall, with the garage-door band picked out darker
      face(P(e0, oF, base), P(e1, oF, base), P(e1, oF, base + 4.2), P(e0, oF, base + 4.2),
                 (i % 3) ? shade(conc, -0.3) : 0x39404a);
      face(P(e0, oF, base + 4.2), P(e1, oF, base + 4.2),
                 P(e1, oF, base + H), P(e0, oF, base + H), conc);
      face(P(e0, oF, base + H), P(e1, oF, base + H),
                 P(e1, oB, base + H), P(e0, oB, base + H), shade(conc, 0.08));
      face(P(e0, oB, base), P(e1, oB, base), P(e1, oB, base + H), P(e0, oB, base + H),
                 shade(conc, -0.2));
    }
    // The two ends, for the reason a grandstand needs them: an open box is a
    // box you can see the inside of the roof of, and this one is thirteen units
    // deep and right beside the grid.
    for (const j of [i0, i1]) {
      const e = line[j];
      const P = (o, y) => [e.p[0] + e.lat[0] * o, y, e.p[2] + e.lat[2] * o];
      face(P(oF, sole(j, oF)), P(oB, sole(j, oB)), P(oB, base + H), P(oF, base + H),
                 shade(conc, -0.24));
    }
    // the pit wall, low and close in, between the road and the building
    const wOff = ((cfg.armco || 26) - 9) * side;
    for (let i = i0; i + 1 <= i1; i++) {
      const e0 = line[i], e1 = line[i + 1];
      const [x0, z0] = spot(i, wOff), [x1, z1] = spot(i + 1, wOff);
      const y0 = deck(i, wOff), y1 = deck(i + 1, wOff);
      face([x0, y0, z0], [x1, y1, z1], [x1, y1 + 1.15, z1], [x0, y0 + 1.15, z0],
                 i % 4 < 2 ? 0xf0efec : shade(conc, -0.1));
    }
  }

  /** A frame over the road: the start gantry, and the bridge over Kemmel. */
  function span(f, opts) {
    const i = at(f);
    const e = line[i];
    const hw = e.hw + 3.5;
    const clear = opts.clear != null ? opts.clear : 8.5;
    const legs = [];
    for (const s of [-1, 1]) {
      const [x, z] = spot(i, s * hw);
      const g = deck(i, s * hw);
      solid.box(x, (g + e.p[1] + clear) / 2, z, 0.7, (e.p[1] + clear - g) / 2, 0.7,
                opts.color != null ? opts.color : dark);
      legs.push([x, z]);
    }
    const y = e.p[1] + clear;
    const beamH = opts.deck ? 1.9 : 1.1;
    const A = [legs[0][0], y, legs[0][1]], B = [legs[1][0], y, legs[1][1]];
    const f2 = [e.lat[2], 0, -e.lat[0]];       // along the road
    const w = opts.deck ? 3.2 : 1.0;
    const Q = (p, sf, sy) => [p[0] + f2[0] * sf, p[1] + sy, p[2] + f2[2] * sf];
    for (const sf of [-w, w]) {
      face(Q(A, sf, 0), Q(B, sf, 0), Q(B, sf, beamH), Q(A, sf, beamH),
                 opts.color != null ? opts.color : dark);
    }
    face(Q(A, -w, beamH), Q(B, -w, beamH), Q(B, w, beamH), Q(A, w, beamH),
               shade(opts.color != null ? opts.color : dark, 0.15));
    if (opts.deck) {
      face(Q(A, -w, 0), Q(B, -w, 0), Q(B, w, 0), Q(A, w, 0), shade(conc, -0.1));
    }
    // the five red start lights, unlit so they read against a grey sky
    if (opts.lights) {
      for (let k = -2; k <= 2; k++) {
        const t = (k + 2) / 4;
        const p = [A[0] + (B[0] - A[0]) * (0.28 + t * 0.44), y + beamH * 0.5,
                   A[2] + (B[2] - A[2]) * (0.28 + t * 0.44)];
        bright.box(p[0], p[1], p[2], 0.52, 0.52, 0.52, 0xd8202a);
      }
    }
    if (opts.text) {
      const mid = [(A[0] + B[0]) / 2, y + beamH + 1.5, (A[2] + B[2]) / 2];
      const r = [(B[0] - A[0]), 0, (B[2] - A[2])];
      const L = Math.hypot(r[0], r[2]) || 1;
      // Faces back down the road, at the car arriving.
      signs.push({ text: opts.text, c: mid, r: [r[0] / L, 0, r[2] / L], u: [0, 1, 0],
                   hw: L * 0.42, hh: L * 0.42 / 8, n: [-f2[0], 0, -f2[2]] });
    }
  }

  for (const s of (cfg.stands || [])) stand(s.at[0], s.at[1], s.side, s);
  if (cfg.pits) pits(cfg.pits.at[0], cfg.pits.at[1], cfg.pits.side);
  for (const s of (cfg.spans || [])) span(s.at, s);
  return keepOut;
}

/**
 * Sponsor boards along the barrier: one every so often down each armco run,
 * standing just proud of it and facing the road.
 *
 * A board is one flat quad and the ground it stands on is not flat, which is
 * the whole difficulty. Two things follow, and neither was here to begin with:
 * 61 of Spa's 67 boards had their bottom edge underground, by a median of 1.8
 * units and as much as 4.3, which from the car is a row of hoardings sunk to
 * the knee in the grass.
 *
 * **The board leans with the barrier.** `r` is the full 3D chord, slope and
 * all, and `u` is square to it - not world up. A horizontal board on a slope
 * has to pick a height, and whichever it picks one end is buried and the other
 * is flying; Spa falls up to 0.64 a station and these span five of them, so
 * that alone is +/-1.6. The armco beside it has always followed the ground, so
 * a board that does not is also the one thing on the barrier that looks wrong.
 *
 * **And it clears every post under it, not just the two it is hung from.** The
 * chord between the ends cuts *under* the polyline over a crest, so squaring up
 * to it is not enough on its own - the middle of the board is what surfaces.
 * The lift is measured against each post in the run and taken to the worst.
 *
 * Size is the palette's, not the chord's. `hw = L/2, hh = L/8` made the board
 * as wide as whatever five stations happened to span and four times taller than
 * an armco, which is most of how far under they reached; a hoarding is a fixed
 * object and reads as one. The 4:1 is the canvas `signTexture` draws.
 */
/** Does a board's panel land in any of the buildings' keep-out boxes? */
function inside(keepOut, c, hw, hh, r, u) {
  if (!keepOut || !keepOut.length) return false;
  // The four corners and the middle. A board is 10 units across and the boxes
  // are one station long, so a corner test alone can straddle one unseen.
  const pts = [[-1, -1], [1, -1], [1, 1], [-1, 1], [0, 0]].map(([a, b]) =>
    [c[0] + r[0] * a * hw + u[0] * b * hh, c[1] + r[1] * a * hw + u[1] * b * hh,
     c[2] + r[2] * a * hw + u[2] * b * hh]);
  for (const b of keepOut) {
    for (const p of pts) {
      if (p[0] >= b.x0 && p[0] <= b.x1 && p[2] >= b.z0 && p[2] <= b.z1
          && p[1] >= b.y0 && p[1] <= b.y1) return true;
    }
  }
  return false;
}

function addHoardings(signs, runs, names, every, opts, keepOut) {
  const H = (opts && opts.boardH != null) ? opts.boardH : 2.6;
  const hwMax = H * 2;             // the sign canvas is 4:1, so width is 4 x H/2
  // Clearance over the barrier's *footing*, which is 0.2 under the ground, and
  // the run-off is another 0.15 over that where it is not banked - so anything
  // under 0.35 here is still a board with its bottom edge in the gravel.
  const SIT = 0.45;
  const PROUD = 0.6;               // clear of the rail, on the road side of it
  let k = 0;
  for (const run of runs) {
    for (let i = 2; i + 6 < run.length; i += every) {
      const a = run[i], b = run[i + 5];
      const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
      const flat = Math.hypot(dx, dz);
      if (flat < 8) continue;
      const L = Math.hypot(dx, dy, dz);
      const r = [dx / L, dy / L, dz / L];
      const n = a.n || [dz / flat, 0, -dx / flat];
      // Up, in the board's own plane: n x r, which is world up on the flat and
      // leans with the barrier where it is not.
      //
      // Then forced to actually point up, which is not a formality. `n` faces
      // the road rather than following from `r`, so it is r turned a quarter
      // turn one way down the left-hand barrier and the other way down the
      // right - and n x r comes out pointing at the sky on one side of the
      // circuit and at the ground on the other. Left alone that builds every
      // board on one side upside down and 2.9 units into the earth, printed
      // wrong way up, which is a good deal worse than the sag it replaced.
      let u = [n[1] * r[2] - n[2] * r[1], n[2] * r[0] - n[0] * r[2],
               n[0] * r[1] - n[1] * r[0]];
      const uL = (Math.hypot(u[0], u[1], u[2]) || 1) * (u[1] < 0 ? -1 : 1);
      u = [u[0] / uL, u[1] / uL, u[2] / uL];
      const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
      // How far the bottom edge has to stand off the chord to clear every post
      // it spans, not merely the two it is measured from.
      let sit = SIT;
      for (let j = i; j <= i + 5; j++) {
        const q = run[j];
        sit = Math.max(sit, (q[0] - mid[0]) * u[0] + (q[1] - mid[1]) * u[1]
                          + (q[2] - mid[2]) * u[2] + SIT);
      }
      const hw = Math.min(hwMax, flat / 2), hh = hw / 4;
      const c = [mid[0] + n[0] * PROUD + u[0] * (sit + hh),
                 mid[1] + n[1] * PROUD + u[1] * (sit + hh),
                 mid[2] + n[2] * PROUD + u[2] * (sit + hh)];
      if (inside(keepOut, c, hw, hh, r, u)) continue;
      signs.push({ text: names[k++ % names.length], c, r, u, hw, hh, n });
    }
  }
}

/**
 * Draw the height field, and put it in the collider as OFFROAD.
 *
 * `drop` is the same trick the flat plate uses: the ground sits a little under
 * the road so the tarmac reads as a raised ribbon and the two surfaces never
 * z-fight or make the ground query a coin toss between them.
 *
 * Cells are painted gravel out to `gravel` units from the road centre and grass
 * past it, which is the whole of the run-off. It is cosmetic: both are one
 * OFFROAD surface at one drag, so nothing in the simulation can tell them
 * apart and no medal time anywhere moved to get it.
 */
function drawTerrain(buf, col, terr, pal, apron, gravelTo) {
  const { nx, nz, x0, z0, CELL, gridH, gridD } = terr;
  const P = (ix, iz) => [x0 + ix * CELL, gridH[ix * nz + iz], z0 + iz * CELL];
  const grit = pal.gravel != null ? pal.gravel : pal.ground;
  // Which cells are run-off. The swept apron draws the *clean* gravel edge on
  // top of this, so the only job here is that whatever the field pokes through
  // with is already the right colour. The test is the cell's *middle* - the
  // mean of its four corners - rather than "any corner inside the band", which
  // was the first go and is wrong in a way you can see: erring a whole cell wide
  // puts an eight-unit ring of grit outside the band, and every place the field
  // stands proud out there is a tan wedge lying in the grass. Centred, the
  // colour can only be wrong within half a cell of a line the apron is drawing
  // over the top of anyway.
  //
  // Painting the ground under the apron as well as the apron itself is belt and
  // braces, and the belt is `buildTerrain` agreeing with the sweep in the first
  // place. It earns its place anyway at distance: the apron's 0.03 lift is
  // below the depth buffer's resolution past about 450 units, and matching
  // colours mean the far side of the infield shimmers between two shades of the
  // same gravel instead of between gravel and grass.
  const gTo = gravelTo != null ? gravelTo : 0;
  for (let ix = 0; ix + 1 < nx; ix++) {
    for (let iz = 0; iz + 1 < nz; iz++) {
      // Nothing is skipped near the road, and that is deliberate. Skipping the
      // cells the swept run-off covers looks like the way to avoid drawing the
      // ground twice, and it tore holes: the apron gets clipped back wherever
      // another leg of the circuit is nearer, so the two rules disagreed about
      // who owned that ground and neither drew it. What you see through a hole
      // in the floor is the sky, which is why it read as pale grey shards lying
      // in the infield.
      //
      // Drawing both is safe because they are coplanar where they overlap -
      // inside the apron this field is "nearest road height, less the drop",
      // which is exactly what the apron is - and the apron is lifted a hair so
      // it wins the depth test. Overlap costs a few thousand quads; a hole in
      // the ground costs you the car.
      const a = P(ix, iz), b = P(ix, iz + 1), c = P(ix + 1, iz + 1), d = P(ix + 1, iz);
      const mid = (gridD[ix * nz + iz] + gridD[ix * nz + iz + 1] +
                   gridD[(ix + 1) * nz + iz] + gridD[(ix + 1) * nz + iz + 1]) / 4;
      buf.quad(a, b, c, d, mid < gTo ? grit : pal.ground);
      col.addQuad(a, b, c, d, KIND.OFFROAD);
    }
  }
}

function addScenery(buf, track, pal, bbox, CELL, terrain) {
  let seed = 0;
  for (let i = 0; i < track.slug.length; i++) seed = seed * 31 + track.slug.charCodeAt(i);
  const rnd = mulberry(seed);
  const onGround = track.ground != null;
  const gy = onGround ? track.ground : null;
  // Keep props off the road. A cell counts as occupied if any station's road
  // reaches into it, plus a ring of clearance so nothing overhangs a kerb.
  const occupied = new Set();
  for (const e of track.line) {
    const reach = Math.ceil((e.hw + CELL) / CELL);
    const cx = Math.round(e.p[0] / CELL), cz = Math.round(e.p[2] / CELL);
    for (let dx = -reach; dx <= reach; dx++) {
      for (let dz = -reach; dz <= reach; dz++) occupied.add((cx + dx) + ',' + (cz + dz));
    }
  }
  // A big tree needs more room than a shrub, so it is only allowed where the
  // whole 3x3 block of cells is clear of the road corridor. Without this a
  // fifteen-unit canopy leans over the kerb on the outside of every corner.
  const roomy = (gx, gz) => {
    for (let dx = -1; dx <= 1; dx++) {
      for (let dz = -1; dz <= 1; dz++) if (occupied.has((gx + dx) + ',' + (gz + dz))) return false;
    }
    return true;
  };

  // What grows here, as weights. Palettes that say nothing get the old mix.
  const mix = pal.props || { conifer: 0.55, rock: 0.25, block: 0.20 };
  const kinds = Object.keys(mix);
  const total = kinds.reduce((s, k) => s + mix[k], 0);
  const pick = (r) => {
    let acc = 0;
    for (const k of kinds) { acc += mix[k] / total; if (r <= acc) return k; }
    return kinds[kinds.length - 1];
  };

  const x0 = Math.floor(bbox.x0 / CELL) - 4, x1 = Math.ceil(bbox.x1 / CELL) + 4;
  const z0 = Math.floor(bbox.z0 / CELL) - 4, z1 = Math.ceil(bbox.z1 / CELL) + 4;
  for (let gx = x0; gx <= x1; gx++) {
    for (let gz = z0; gz <= z1; gz++) {
      if (occupied.has(gx + ',' + gz)) continue;
      if (rnd() > (pal.density != null ? pal.density : (onGround ? 0.17 : 0.05))) continue;
      if (!onGround) continue;         // nothing to stand a tree on in the void
      const px = gx * CELL + (rnd() - 0.5) * CELL * 0.6;
      const pz = gz * CELL + (rnd() - 0.5) * CELL * 0.6;
      // The `occupied` ring only clears the road itself. A circuit with real
      // run-off needs the whole apron kept clear too, or pines grow out of the
      // gravel trap and through the barrier.
      if (terrain && pal.terrain && terrain.toRoad(px, pz) < (pal.terrain.clear || 0)) continue;
      // On a hillside the trees stand where the hill is, not on one level.
      const baseY = terrain ? terrain.height(px, pz) - 0.4 : gy;
      let kind = pick(rnd());
      if (kind === 'bigpine' && !roomy(gx, gz)) kind = 'conifer';

      // On a winter track every horizontal surface has snow sitting on it, so
      // foliage gets a thin white slab laid on top of each whorl. It is the
      // cheapest possible version of the effect and the only one that reads at
      // this scale.
      const snow = pal.snow;
      // Thin, inset, and not on every branch. A thick slab the full width of
      // the whorl turns the tree into a wedding cake; snow that misses a third
      // of them is what makes it look settled rather than applied.
      const cap = (cx, cy, cz, hx, hz) => {
        if (!snow || rnd() < 0.32) return;
        buf.box(cx, cy - 0.06, cz, hx * 0.86, 0.16, hz * 0.86, snow);
      };

      if (kind === 'conifer') {
        // trunk + two stacked prisms
        const hgt = 3 + rnd() * 4;
        buf.box(px, baseY + hgt * 0.22, pz, 0.32, hgt * 0.22, 0.32, 0x6b4f2a);
        buf.box(px, baseY + hgt * 0.62, pz, 1.5, hgt * 0.3, 1.5, pal.prop);
        cap(px, baseY + hgt * 0.92 + 0.16, pz, 1.5, 1.5);
        buf.box(px, baseY + hgt * 1.0, pz, 0.95, hgt * 0.22, 0.95, shade(pal.prop, 0.12));
        cap(px, baseY + hgt * 1.22 + 0.16, pz, 0.95, 0.95);
      } else if (kind === 'deadtree') {
        // A bare tree: trunk plus a handful of stubs going out at different
        // heights. Blocky, but at any distance it reads as branches.
        const hgt = 5 + rnd() * 6;
        const tw = 0.26 + rnd() * 0.2;
        buf.box(px, baseY + hgt * 0.5, pz, tw, hgt * 0.5, tw, shade(0x4c3a29, (rnd() - 0.5) * 0.2));
        const n = 3 + Math.floor(rnd() * 3);
        for (let k = 0; k < n; k++) {
          const a = rnd() * Math.PI * 2, len = 1 + rnd() * 2.2;
          const y = baseY + hgt * (0.45 + rnd() * 0.5);
          buf.box(px + Math.cos(a) * len * 0.6, y, pz + Math.sin(a) * len * 0.6,
                  Math.abs(Math.cos(a)) * len * 0.6 + 0.16, 0.16,
                  Math.abs(Math.sin(a)) * len * 0.6 + 0.16, 0x4c3a29);
        }
      } else if (kind === 'bigpine') {
        // A big pine: a trunk that runs most of the way up with four to six
        // whorls of foliage around it, overlapping enough to read as one tree.
        //
        // The point is that it is conical *ish*. A clean taper looks like a
        // Christmas-tree decal, so every whorl gets its width jittered hard
        // enough to break the silhouette, is nudged off the trunk's axis, is a
        // different depth than it is wide, and about half of them grow one
        // heavier branch out to one side. The leader at the top leans too.
        const leaf = pal.prop2 != null ? pal.prop2 : pal.prop;
        const hgt = 11 + rnd() * 9;
        const tw = 0.4 + rnd() * 0.26;
        buf.box(px, baseY + hgt * 0.4, pz, tw, hgt * 0.4, tw, 0x5f4830);
        const tiers = 5 + Math.floor(rnd() * 3);
        const base = 2.8 + rnd() * 1.8;
        const y0 = baseY + hgt * 0.22, step = (hgt * 0.74) / tiers;
        const lean = (rnd() - 0.5) * 0.5;              // the whole crown drifts
        for (let k = 0; k < tiers; k++) {
          const u = k / (tiers - 1);
          const w = base * (1 - u * 0.82) * (0.78 + rnd() * 0.44);
          // Flat whorls, not cubes. A tier as deep as it is wide stacks into a
          // pile of boxes; keeping each one much wider than it is tall, with
          // trunk showing between them, is what makes it read as a pine.
          const th = step * (0.3 + rnd() * 0.22);
          const cy = y0 + step * k + th;
          const ox = (rnd() - 0.5) * base * 0.3 + lean * u * base;
          const oz = (rnd() - 0.5) * base * 0.3 + lean * u * base * 0.6;
          const col = shade(leaf, (rnd() - 0.45) * 0.22);
          const dep = w * (0.68 + rnd() * 0.58);
          buf.box(px + ox, cy, pz + oz, w, th, dep, col);
          cap(px + ox, cy + th + 0.16, pz + oz, w, dep);
          if (rnd() < 0.5) {
            const a = rnd() * Math.PI * 2, d = w * (0.55 + rnd() * 0.45);
            buf.box(px + ox + Math.cos(a) * d, cy - th * 0.25, pz + oz + Math.sin(a) * d,
                    w * 0.5, th * 0.6, w * 0.5, shade(col, -0.06));
          }
        }
        buf.box(px + lean * base * 1.2, y0 + hgt * 0.76, pz + lean * base * 0.7,
                base * 0.2, hgt * 0.07, base * 0.2, shade(leaf, 0.18));
      } else if (kind === 'palm') {
        // A palm is a lean and a splay, and nothing else reads at this scale: a
        // straight trunk with a blob on top is a lollipop. So the trunk is a
        // few stacked segments that drift steadily one way, and the fronds go
        // out from wherever it ended up, each one much longer than it is thick
        // and angled down at the tip.
        const hgt = 7 + rnd() * 6;
        const a = rnd() * Math.PI * 2;
        const lean = (0.1 + rnd() * 0.22) * hgt;
        const segs = 5;
        let tx = px, tz = pz;
        for (let k = 0; k < segs; k++) {
          const u = (k + 0.5) / segs;
          tx = px + Math.cos(a) * lean * u * u;
          tz = pz + Math.sin(a) * lean * u * u;
          buf.box(tx, baseY + hgt * u, tz, 0.3, hgt / segs * 0.62, 0.3,
                  shade(0x8a6a44, (rnd() - 0.5) * 0.2));
        }
        const fronds = 6 + Math.floor(rnd() * 3);
        for (let k = 0; k < fronds; k++) {
          const fa = a + Math.PI + (k / fronds) * Math.PI * 2 + rnd() * 0.3;
          const len = 2.2 + rnd() * 1.9;
          buf.box(tx + Math.cos(fa) * len * 0.55,
                  baseY + hgt - 0.4 - rnd() * 0.7,
                  tz + Math.sin(fa) * len * 0.55,
                  Math.abs(Math.cos(fa)) * len * 0.55 + 0.3, 0.17,
                  Math.abs(Math.sin(fa)) * len * 0.55 + 0.3,
                  shade(pal.prop, (rnd() - 0.4) * 0.3));
        }
        // A couple of coconuts, which is most of what says palm rather than fern.
        if (rnd() < 0.6) {
          buf.box(tx + 0.3, baseY + hgt - 0.9, tz, 0.34, 0.34, 0.34, 0x6b4a2a);
        }
      } else if (kind === 'rock') {
        const s = 1 + rnd() * 1.8;
        buf.box(px, baseY + s * 0.5, pz, s, s * 0.5, s * 0.9, shade(pal.ground, -0.25));
      } else {
        const hgt = 2 + rnd() * 9;
        buf.box(px, baseY + hgt / 2, pz, 1.7, hgt / 2, 1.7, shade(pal.prop, -0.05));
      }
    }
  }
}

/**
 * The Costco: a shell the road drives into, and everything inside it.
 *
 * This is the pool's only *interior*, and it is a sibling of `addScenery`
 * rather than a use of Spa's `furniture` block, deliberately. `addFurniture` is
 * only reachable from inside `buildTrack`'s `else if (terrain)` branch, so
 * borrowing it would mean giving a flat track a height field it has no use for -
 * and its vocabulary is grandstands, pit buildings and gantries, which is not
 * what a warehouse is made of. What it does borrow is the parts that are already
 * proven: both faces on everything (the world mesh is `MeshLambertMaterial`,
 * which is `FrontSide`), the `bright` buffer for anything that should read as
 * lit, and the existing `signs` contract for the only textured geometry here.
 *
 * Three things are derived from the road rather than authored beside it, because
 * each of them is a place where a second copy would drift:
 *
 *  * **the doorways** are wherever the road crosses a wall. There is no list of
 *    door positions to get wrong, and a leg that moves takes its door with it;
 *  * **the holes in the roof** are wherever the road passes *through* the roof
 *    plane, which is the two travelator ramps and nothing else. The rooftop deck
 *    passes over the roof rather than through it and keeps its roof;
 *  * **the racking** stands half an aisle either side of every straight aisle
 *    station, which is the midpoint between two aisles, clipped by `toRoad` so a
 *    run stops rather than crossing the next aisle - the same signal Spa's
 *    armco, run-off and grandstands all read.
 *
 * The shell's four numbers are the one thing that *is* authored, and they are a
 * second copy of `SHELL_X`/`SHELL_Z`/`SHELL_CEIL` in tracks.py. That is the same
 * trade Sandy Cove's waterline makes and it is right for the same reason: the
 * road is authored to pass through these walls, so they cannot be derived from
 * the road without being circular. A test holds the two copies together.
 */
function addBuilding(solid, bright, signs, col, track, pal, cfg) {
  const line = track.line, n = line.length;
  const X0 = cfg.x[0], X1 = cfg.x[1], Z0 = cfg.z[0], Z1 = cfg.z[1];
  const CEIL = cfg.ceil != null ? cfg.ceil : 11;
  const DOOR = cfg.door != null ? cfg.door : 24;
  const base = track.ground != null ? track.ground : 0;   // the floor plate
  const WALL = cfg.wall != null ? cfg.wall : 0xdcd8d0;
  const STEEL = cfg.steel != null ? cfg.steel : 0x8e949c;
  const T = 1.4;                       // wall thickness: tilt-up concrete

  // Both faces. A wall is looked at from inside and from out, and a single
  // winding gives you one of those and an invisible wall for the other - which
  // is exactly how Spa's pit building spent an afternoon as a roof floating in
  // the sky.
  const face = (a, b, c, d, k) => { solid.quad(a, b, c, d, k); solid.quad(a, d, c, b, k); };

  // Drawn and solid, five faces as WALL - the same single-sided-per-side rule
  // `solidBox` in buildTrack uses, and for the same reason: the wall query works
  // its push-out direction from the closest point on the triangle.
  const box = (cx, cy, cz, hx, hy, hz, k) => {
    solid.box(cx, cy, cz, hx, hy, hz, k);
    const P = (sx, sy, sz) => [cx + sx * hx, cy + sy * hy, cz + sz * hz];
    const v = [P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1),
               P(-1, 1, -1), P(1, 1, -1), P(1, 1, 1), P(-1, 1, 1)];
    col.addQuad(v[4], v[7], v[6], v[5], KIND.WALL);
    col.addQuad(v[0], v[4], v[5], v[1], KIND.WALL);
    col.addQuad(v[1], v[5], v[6], v[2], KIND.WALL);
    col.addQuad(v[2], v[6], v[7], v[3], KIND.WALL);
    col.addQuad(v[3], v[7], v[4], v[0], KIND.WALL);
  };

  // How far (x,z) is from the nearest road centre that is anywhere near height
  // `y`, in plan.
  //
  // This is `terrain.toRoad` for a track with no terrain to ask, and it answers
  // the one question every piece of trackside furniture in this game has to ask
  // before it builds: is some *other* part of the track already here?
  //
  // **The height window is the whole difference on this track**, and leaving it
  // out is a bug that looks like nothing. Spa's legs all lie in one sheet, so a
  // plan distance is the right question there; here a rooftop car park flies
  // 14.5 units over the aisles, and a plan-only answer reports the deck as being
  // "at" every point below it. What that cost: the racking down the south side of
  // aisle one, silently, because the deck's south leg passes 4.7 units from it in
  // plan and three metres over its head. One aisle came out shelved on one side.
  const toRoad = (x, z, y) => {
    let best = Infinity;
    for (let i = 0; i < n; i++) {
      const p = line[i].p;
      if (y != null && Math.abs(p[1] - y) > 5) continue;
      const dx = p[0] - x, dz = p[2] - z;
      const d = dx * dx + dz * dz;
      if (d < best) best = d;
    }
    return Math.sqrt(best);
  };

  // A board onto the existing `signs` list, so everything textured here is
  // painted by the same canvas path and batched with every other board reading
  // the same words. A board canvas is 4:1, so the height follows the width.
  const put = (text, cx, cy, cz, r, nv, hw) => {
    signs.push({ text, c: [cx, cy, cz], r, u: [0, 1, 0], hw, hh: hw / 4, n: nv });
  };
  const sg = cfg.sign || {};

  const inShell = (x, z) => x > X0 + T && x < X1 - T && z > Z0 + T && z < Z1 - T;

  // The last stretch indoors: everything still at floor level after the
  // travelator has brought you back down, up to the door. Found rather than
  // authored, so it stays the checkout run however the lap is retimed - and
  // worked out up here because the racking needs it too, to keep out of it.
  let lastUp = -1;
  for (let i = 0; i < n; i++) if (line[i].p[1] > 1.0) lastUp = i;
  const tills = [];
  for (let i = lastUp + 1; i < n; i++) {
    if (!inShell(line[i].p[0], line[i].p[2])) break;
    tills.push(i);
  }

  // ---- the walls, and the doorways the road cuts in them -------------------
  // `axis` 0 is a wall of constant x, 2 one of constant z. Returns where along
  // the wall the road goes through it.
  const crossings_ = (axis, at, lo, hi) => {
    const oax = axis === 0 ? 2 : 0;
    const out = [];
    for (let i = 1; i < n; i++) {
      const a = line[i - 1].p, b = line[i].p;
      if ((a[axis] - at) * (b[axis] - at) >= 0) continue;
      const t = (at - a[axis]) / (b[axis] - a[axis]);
      const o = a[oax] + (b[oax] - a[oax]) * t;
      if (o >= lo && o <= hi) out.push(o);
    }
    return out.sort((p, q) => p - q);
  };

  // A doorway is the full height of the wall on purpose, with no header over
  // it. The chase camera rides 4.3 units above the car and swings wide of it
  // through a turn, so a lintel is a thing for the camera to pop through at the
  // exact moment the car is going through the door - and a Costco entrance is a
  // full-height opening anyway.
  const wall = (axis, at, lo, hi) => {
    const cuts = crossings_(axis, at, lo, hi);
    let s = lo;
    const spans = [];
    for (const c of cuts) {
      if (c - DOOR > s) spans.push([s, c - DOOR]);
      s = Math.max(s, c + DOOR);
    }
    if (hi > s) spans.push([s, hi]);
    const h = (CEIL - base) / 2;
    for (const [a, b] of spans) {
      const mid = (a + b) / 2, half = (b - a) / 2;
      if (half <= 0.2) continue;
      if (axis === 0) box(at, base + h, mid, T, h, half, WALL);
      else box(mid, base + h, at, half, h, T, WALL);
      // A parapet, so the roofline reads as built rather than as a cut edge.
      // Lifted off the roof plane rather than resting exactly on it, or its
      // underside is coplanar with the edge roof panel the whole way round.
      if (axis === 0) box(at, CEIL + 0.62, mid, T * 1.2, 0.5, half, shade(WALL, -0.12));
      else box(mid, CEIL + 0.62, at, half, 0.5, T * 1.2, shade(WALL, -0.12));
    }
    return cuts;
  };

  const westDoors = wall(0, X0, Z0, Z1);
  const eastDoors = wall(0, X1, Z0, Z1);
  wall(2, Z0, X0, X1);
  wall(2, Z1, X0, X1);

  // ---- the entrance ------------------------------------------------------
  // A projecting portal round each front door. Two jobs: a 240-by-188 shed 12
  // units tall is honestly what a Costco is, and from the car park it reads as a
  // kerb rather than as a building, so the front needs something with height on
  // it. And it is the one piece of this the preview picture is guaranteed to
  // frame, because the lap starts out here.
  //
  // The header's underside is held at 9.5 deliberately. The chase camera rides
  // about 5 units up and comes through the doorway a beat after the car does, so
  // anything lower is a beam for the camera to pop through at exactly the wrong
  // moment - which is also why the opening itself has no lintel.
  const trim = pal.kerb2 != null ? pal.kerb2 : 0xe31837;
  // The entrance portal, and the board that goes on it. `SIGN_HW` is derived
  // from the header's own height because the board canvas is 4:1 and the header
  // is nearer 9:1 - so the board cannot fill it, and the colour band under it has
  // to agree with the board rather than with the header, or it runs out past both
  // ends of the name and reads as a separate stripe.
  const OUT = 6, TOP = CEIL + 4.5, HEAD = 9.5;
  const SIGN_HW = (TOP - HEAD) * 2;
  const portal = (at, o, sgn) => {
    const xo = at + sgn * OUT / 2;
    for (const q of [-1, 1]) {
      box(xo, base + (TOP - base) / 2, o + q * (DOOR + 2.6), OUT / 2,
          (TOP - base) / 2, 2.6, shade(WALL, 0.05));
    }
    // The header. Its front face is what the wordmark goes on - see the signage
    // block - so all that is added here is a band of colour under it.
    box(xo, (HEAD + TOP) / 2, o, OUT / 2, (TOP - HEAD) / 2, DOOR + 2.6, shade(WALL, 0.05));
    box(at + sgn * (OUT + 0.3), HEAD + 0.45, o, 0.3, 0.45, SIGN_HW + 1.0, trim);
  };
  for (const z of westDoors) portal(X0, z, -1);
  for (const z of eastDoors) portal(X1, z, 1);

  // ---- the roof -----------------------------------------------------------
  // Cells, so a hole is a skipped cell rather than a boolean subtraction. A cell
  // goes if the road is near the roof plane there: that is the two ramps
  // punching through, and the rooftop deck, which is road *above* the roof and
  // is its own roof over the part of the shell it covers.
  const CELLR = 12;
  // How thick the roof slab is - see the note on the soffit below. Small enough
  // that the cut edge at a travelator hole is not worth closing, big enough that
  // the depth buffer never has to choose between the two faces.
  const DEEP = 0.3;
  // A cell goes only where the road passes *through* the roof plane, which on
  // this track is the two travelator ramps and nothing else.
  //
  // The test has to be "near the plane", not "above it". Above it also catches
  // the rooftop deck - which is road 3.5 units over the roof, standing on it -
  // and carved the deck's whole rectangular loop out of the roof it stands on.
  // What that looks like from the aisles is a moth-eaten ceiling with daylight
  // through it, which reads as a lighting bug rather than as missing geometry.
  const throughRoof = (x, z, r) => {
    for (let i = 0; i < n; i++) {
      const p = line[i].p;
      if (Math.abs(p[1] - CEIL) > 2.2) continue;
      if (Math.abs(p[0] - x) < r + line[i].hw && Math.abs(p[2] - z) < r + line[i].hw) return true;
    }
    return false;
  };
  const skyCol = cfg.skylight != null ? cfg.skylight : 0xeef6ff;
  const topCol = shade(WALL, -0.34);
  const litCol = shade(cfg.inner != null ? cfg.inner : 0xcfcbc4, 0.06);
  let ix = 0;
  for (let x = X0; x < X1; x += CELLR, ix++) {
    let iz = 0;
    for (let z = Z0; z < Z1; z += CELLR, iz++) {
      const x2 = Math.min(x + CELLR, X1), z2 = Math.min(z + CELLR, Z1);
      const cx = (x + x2) / 2, cz = (z + z2) / 2;
      if (throughRoof(cx, cz, CELLR / 2)) continue;
      const A = [x, CEIL, z], B = [x, CEIL, z2], C = [x2, CEIL, z2], D = [x2, CEIL, z];
      // A regular grid of daylight panels, which is what a warehouse roof is,
      // and it also stops the inside reading as a cave.
      const day = (ix % 3) === 1 && (iz % 2) === 0;
      // The top, lit, because it is the floor of the view from the rooftop deck.
      solid.quad(A, B, C, D, day ? shade(skyCol, -0.2) : topCol);
      // And the underside *unlit*, which is not a stylistic choice. A
      // downward-facing quad gets nothing from a key light overhead and only the
      // hemisphere's ground colour from below, so a lit ceiling comes out very
      // nearly black - and a black ceiling over the car is the single most
      // obvious thing in here. The `bright` buffer is what makes a surface read
      // as lit rather than as shadowed, and a warehouse ceiling is exactly that:
      // a pale soffit under daylight panels.
      //
      // **`DEEP` below the top, and it has to be something.** Drawn at the same
      // y these two are coplanar, and coplanar quads in two different meshes are
      // a depth-buffer coin toss: the roof flickers between its top and its
      // soffit as the camera moves, which from inside reads as the ceiling
      // strobing. Giving the roof real thickness settles the depth test the same
      // way lifting the apron off the height field does, and a roof having depth
      // is true anyway.
      const U = CEIL - DEEP;
      bright.quad([x, U, z], [x2, U, z], [x2, U, z2], [x, U, z2],
                  day ? skyCol : litCol);
    }
  }
  // Exposed joists under it, and the fluorescent battens hung off them. Neither
  // is in the collider: nothing drives up here, and a joist a car could hit
  // would be a car trap in the one place a driver never looks.
  const strip = cfg.strip != null ? cfg.strip : 0xfff2d8;
  // Hung clear underneath, in that order, and the clearances matter: a joist
  // centred so its top face lands *on* the roof plane is the roof's own flicker
  // again, and a batten inside the joist it hangs from is geometry buried in
  // geometry. Roof at CEIL, soffit at CEIL - DEEP, then these.
  const JOIST = CEIL - DEEP - 0.65, BATTEN = CEIL - DEEP - 1.55;
  for (let x = X0 + 8; x < X1; x += 16) {
    solid.box(x, JOIST, (Z0 + Z1) / 2, 0.35, 0.5, (Z1 - Z0) / 2, STEEL);
    for (let z = Z0 + 14; z < Z1; z += 34) {
      if (throughRoof(x, z, 6)) continue;
      bright.quad([x - 0.5, BATTEN, z - 7], [x + 0.5, BATTEN, z - 7],
                  [x + 0.5, BATTEN, z + 7], [x - 0.5, BATTEN, z + 7], strip);
    }
  }

  // ---- pallet racking -----------------------------------------------------
  // Runs along the ribbon at half an aisle out, which is the midline between
  // this aisle and the next. Straights only: `off` units to the inside of a
  // hairpin is the middle of the hairpin, and a shelf there is a wall on the
  // apex of a corner the racing line is already using.
  const R = cfg.rack || {};
  const off = R.off != null ? R.off : 14;
  const rh = R.h != null ? R.h : 9.5;
  // Shrink-wrapped stock, tinned goods, the blue pallet wrap everything arrives
  // in. Four colours is enough for the floor to stop reading as one product.
  const PALLET = [0xb08657, 0x2f6fb5, 0xb5432f, 0xd8d2c4];
  // What is actually on the shelves. Eight is enough that a hundred and fifty
  // units of racking never reads as one product repeated, and few enough that an
  // aisle still looks like a warehouse rather than a sweet shop.
  const GOODS = [0xc9542e, 0x2f6fb5, 0xe0c04a, 0x3f8f56,
                 0xa8332c, 0xe3ded2, 0x8a5a3c, 0x5f4b8b];
  const rack = [];
  for (let i = 1; i < n; i++) {
    const e = line[i];
    // Nothing past `lastUp`: that is the checkout run and the food court, and
    // shelving it as well leaves the last stretch indoors indistinguishable from
    // the four aisles you have just driven.
    const ok = e.p[1] < 1.0 && !e.curv && !e.air && i <= lastUp
            && inShell(e.p[0], e.p[2]);
    for (const s of [-1, 1]) {
      const k = s < 0 ? 0 : 1;
      // Half an aisle out, or hard against the wall if half an aisle out is
      // through it. The outermost aisle runs closer to the shell than the aisles
      // run to each other, so without the clamp its outer side gets no racking
      // at all and you drive the length of the building beside a blank wall -
      // which reads as unfinished rather than as a design. Racking against the
      // outer wall is what a warehouse does there anyway.
      const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
      const x = clamp(e.p[0] + e.lat[0] * off * s, X0 + 3, X1 - 3);
      const z = clamp(e.p[2] + e.lat[2] * off * s, Z0 + 3, Z1 - 3);
      const good = ok && inShell(x, z) && toRoad(x, z, e.p[1]) > e.hw + 2.5;
      if (!good) { rack[k] = null; continue; }
      const prev = rack[k];
      rack[k] = [x, z, e.lat[0] * -s, e.lat[2] * -s, i];
      if (!prev) continue;
      // The face toward the road, and one collision quad - the same economy
      // `wallStrip` explains: the wall query works its push-out direction from
      // the closest point on the triangle, so one face per side is both
      // necessary and sufficient.
      const a = [prev[0], base, prev[1]], b = [x, base, z];
      const at = [prev[0], base + rh, prev[1]], bt = [x, base + rh, z];
      face(a, b, bt, at, STEEL);
      col.addQuad(a, b, bt, at, KIND.WALL);
      // Shelf beams, so nine units of steel reads as racking and not as a wall.
      //
      // Stood off the face rather than laid on it: coplanar with it they z-fight,
      // and what that looks like at a glancing angle down an aisle is not
      // flicker but long tan splinters shooting off into the distance, which
      // reads as stray geometry rather than as two surfaces at the same depth.
      const nx = prev[2], nz = prev[3], OFF = 0.22;
      const LEVELS = [0.3, 0.56, 0.82];
      for (const f of LEVELS) {
        const y = base + rh * f;
        bright.quad([prev[0] + nx * OFF, y, prev[1] + nz * OFF],
                    [x + nx * OFF, y, z + nz * OFF],
                    [x + nx * OFF, y + 0.42, z + nz * OFF],
                    [prev[0] + nx * OFF, y + 0.42, prev[1] + nz * OFF],
                    shade(R.pallet != null ? R.pallet : 0xb08657, (f - 0.55) * 0.5));
      }
      // Stock on the shelves, two lots per bay per level so a run never reads as
      // one product repeated down the whole aisle.
      //
      // Drawn as panels standing on the beams and proud of the face, rather than
      // as boxes inside the racking: the face is opaque from both sides, so
      // anything tucked in behind it is stock nobody can see. Unlit for the same
      // reason the beams are - the aisles run east-west under a sun off to one
      // side, so a lit panel is bright down one side of an aisle and black down
      // the other, and it is the *variety* that has to survive, not the shading.
      const PO = OFF + 0.07;
      for (let L = 0; L < LEVELS.length; L++) {
        const y0 = base + rh * LEVELS[L] + 0.42;
        const ph = L === LEVELS.length - 1 ? 1.05 : 1.7;
        for (let q = 0; q < 2; q++) {
          const t0 = q / 2, t1 = (q + 1) / 2;
          const ax = prev[0] + (x - prev[0]) * t0, az = prev[1] + (z - prev[1]) * t0;
          const bx = prev[0] + (x - prev[0]) * t1, bz = prev[1] + (z - prev[1]) * t1;
          const g = GOODS[(i * 7 + L * 3 + q) % GOODS.length];
          bright.quad([ax + nx * PO, y0, az + nz * PO], [bx + nx * PO, y0, bz + nz * PO],
                      [bx + nx * PO, y0 + ph, bz + nz * PO],
                      [ax + nx * PO, y0 + ph, az + nz * PO], g);
        }
      }
      // An upright every couple of bays, and the top rail, so the run has a
      // silhouette instead of being a flat panel.
      if ((i % 8) === 0) {
        box(x, base + rh / 2, z, 0.4, rh / 2, 0.4, shade(STEEL, 0.16));
      }
      // Stock broken out onto the floor in front of the racking, which is most of
      // what tells a warehouse from a car park with shelves in it. Kept to the
      // rack's own side so it never reaches the racing line.
      if ((i % 14) === 3) {
        const pc = PALLET[(i / 14 | 0) % PALLET.length];
        const px = x + nx * 2.4, pz = z + nz * 2.4;
        if (toRoad(px, pz, e.p[1]) > e.hw + 2.0) {
          box(px, base + 1.4, pz, 2.0, 1.4, 2.0, pc);
        }
      }
      face([prev[0], base + rh, prev[1]], [x, base + rh, z],
           [x + nx * -1.6, base + rh, z + nz * -1.6],
           [prev[0] + nx * -1.6, base + rh, prev[1] + nz * -1.6],
           shade(STEEL, -0.22));
    }
  }

  // ---- the refrigerated aisle ---------------------------------------------
  // A run of cases down the inside of the north wall, drawn unlit so it reads as
  // lit glass rather than as a pale grey box. It is scenery in every sense - the
  // grip under it is the same tarmac as everywhere else, because a third surface
  // would mean a new collider kind, a constant in tuning.py and a term in
  // laptime.py, which is to say it would move every medal time in the pool for
  // the sake of one aisle.
  const chill = cfg.chill != null ? cfg.chill : 0xbfe4f2;
  for (let x = X0 + 12; x < X1 - 12; x += 9) {
    const z = Z1 - 6;
    if (toRoad(x, z, base) < 12) continue;
    box(x, base + 1.6, z, 4.0, 1.6, 3.0, shade(STEEL, 0.1));
    // Stood off the case's own front face. Laid *on* it the two are coplanar and
    // the glass flickers against the cabinet, which is the roof's bug in
    // miniature.
    const fz = z - 3.06;
    bright.quad([x - 4, base + 3.2, fz], [x + 4, base + 3.2, fz],
                [x + 4, base + 1.0, fz], [x - 4, base + 1.0, fz], chill);
  }

  // ---- structural columns -------------------------------------------------
  // A warehouse is a grid of columns, and this track needs them to be real: the
  // rooftop deck's own trestles now decline to stand on the aisles they fly over
  // (see `overRoad` in buildTrack), so without these the deck reads as floating.
  // `toRoad` is what keeps one out of a road, which is the whole reason the grid
  // is filtered rather than authored.
  for (let x = X0 + 20; x < X1 - 10; x += 30) {
    for (let z = Z0 + 18; z < Z1 - 10; z += 32) {
      if (toRoad(x, z, base) < 11) continue;
      box(x, base + (CEIL - base) / 2, z, 0.7, (CEIL - base) / 2, 0.7, shade(STEEL, -0.1));
    }
  }

  // ---- the checkouts and the food court -----------------------------------
  // A counter standing off the road and following it: front face, top slab, one
  // collision quad. Same shape as the racking, and same reason for one quad.
  const counter = (i0, i1, o, h, k, topk) => {
    if (i1 >= n) return;
    const a = line[i0], b = line[i1];
    const dv = (o < 0 ? -1 : 1) * 2.6;          // away from the road
    const P = (e, off, up) => [e.p[0] + e.lat[0] * off, base + up, e.p[2] + e.lat[2] * off];
    const A = P(a, o, 0), B = P(b, o, 0), At = P(a, o, h), Bt = P(b, o, h);
    face(A, B, Bt, At, k);
    col.addQuad(A, B, Bt, At, KIND.WALL);
    face(At, Bt, P(b, o + dv, h), P(a, o + dv, h), topk);
  };

  // The tills: a line of them either side, with the road running between, which
  // is what makes the chicane through here read as lanes rather than as a kink.
  for (let j = 2; j + 4 < tills.length; j += 6) {
    const i = tills[j], e = line[i];
    for (const s of [-1, 1]) {
      counter(i, tills[j + 4], (e.hw + 3.2) * s, 1.5,
              shade(STEEL, 0.2), shade(WALL, -0.05));
      // The lane divider post, and a lit lane number board on top of it.
      const o = (e.hw + 1.6) * s;
      const px = e.p[0] + e.lat[0] * o, pz = e.p[2] + e.lat[2] * o;
      box(px, base + 1.9, pz, 0.28, 1.9, 0.28, shade(STEEL, -0.1));
      // Clear of the post's front face (0.28), not inside it - at 0.06 the board
      // was buried in the very thing it is mounted on.
      const bz = pz - 0.36;
      bright.quad([px - 0.9, base + 4.1, bz], [px + 0.9, base + 4.1, bz],
                  [px + 0.9, base + 3.0, bz], [px - 0.9, base + 3.0, bz],
                  trim);
    }
  }

  // The food court, down the side of the checkout run with room for it. Serving
  // counter, a scatter of tables, and the one board everybody actually comes for.
  if (tills.length > 10) {
    const mid = tills[Math.floor(tills.length * 0.45)];
    const e = line[mid];
    // Whichever side has the room. The checkout run hugs one wall on its way out.
    const side = (e.p[2] + e.lat[2] * 18 > Z1 - 6) ? -1 : 1;
    const co = (e.hw + 13) * side;
    counter(tills[2], tills[Math.min(tills.length - 1, 14)], co, 2.1,
            shade(trim, -0.1), shade(WALL, 0.04));
    const rnd2 = mulberry(0x150150);
    for (let j = 3; j < Math.min(tills.length - 1, 16); j += 3) {
      const t = line[tills[j]];
      const o = (t.hw + 7.5 + rnd2() * 2.4) * side;
      const tx = t.p[0] + t.lat[0] * o, tz = t.p[2] + t.lat[2] * o;
      if (toRoad(tx, tz, base) < t.hw + 2.4) continue;
      box(tx, base + 0.95, tz, 1.9, 0.12, 1.9, shade(WALL, -0.02));   // table top
      box(tx, base + 0.48, tz, 0.22, 0.48, 0.22, shade(STEEL, -0.1)); // and its leg
    }
    // Hung over the counter, facing the road.
    const so = (e.hw + 11.4) * side;
    const sx = e.p[0] + e.lat[0] * so, sz = e.p[2] + e.lat[2] * so;
    const fx = -e.lat[0] * side, fz = -e.lat[2] * side;   // back toward the road
    put(sg.food || '$1.50 HOT DOG', sx, base + 5.6, sz,
        [fz, 0, -fx], [fx, 0, fz], 5.2);
  }

  // ---- the rooftop railing ------------------------------------------------
  // A parapet down both edges of the deck, because a car park nineteen units up
  // has one and because falling off it is not the point of this track.
  //
  // It cannot be a ribbon `rail`: this is a ground track, and
  // `test_barriers_are_opt_in` requires a ground track to carry no walled
  // stations at all. So it is collider geometry standing beside the road, the way
  // the racking is - which also keeps it outside the kerb, so the racing line
  // never touches it and no medal time moves. It leans with the banking, taking
  // its up from the station's own normal for the reason `wallStrip` does.
  const railH = 1.15, railC = pal.rail != null ? pal.rail : 0xd8dde2;
  const rprev = [null, null];
  for (let i = 0; i < n; i++) {
    const e = line[i];
    const onDeck = e.p[1] > CEIL && !e.air;
    for (const s of [-1, 1]) {
      const k = s < 0 ? 0 : 1;
      if (!onDeck) { rprev[k] = null; continue; }
      const o = (e.hw + 0.9) * s;
      const p = [e.p[0] + e.lat[0] * o, e.p[1] + e.lat[1] * o, e.p[2] + e.lat[2] * o];
      const q = rprev[k];
      rprev[k] = [p, e.n];
      if (!q) continue;
      const t = (v, nv) => [v[0] + nv[0] * railH, v[1] + nv[1] * railH, v[2] + nv[2] * railH];
      const A = q[0], B = p, At = t(q[0], q[1]), Bt = t(p, e.n);
      face(A, B, Bt, At, railC);
      col.addQuad(A, B, Bt, At, KIND.WALL);
    }
  }

  // ---- signage ------------------------------------------------------------
  // `put` and `sg` are declared up with the helpers rather than here, because the
  // food court hangs its board while it is building its counter and a `const` is
  // not merely hoisted - it is in its temporal dead zone until its own line runs,
  // so using it earlier throws rather than reading as undefined.
  // On the front face of each entrance header, filling it, which is where a
  // warehouse puts its name. Not on the wall behind: the portal projects six
  // units and would stand squarely in front of it, and not below the header
  // either, because below the header is the doorway and a board hung across that
  // is a board hung across the road.
  for (const z of westDoors) {
    put(sg.facade || 'COSTCO WHOLESALE', X0 - OUT - 0.5, (HEAD + TOP) / 2 + 0.5, z,
        [0, 0, 1], [-1, 0, 0], SIGN_HW);
  }
  for (const z of eastDoors) {
    put(sg.facade || 'COSTCO WHOLESALE', X1 + OUT + 0.5, (HEAD + TOP) / 2 + 0.5, z,
        [0, 0, -1], [1, 0, 0], SIGN_HW);
  }
  // And one standing on the roof, which is what you read on the way round the
  // deck. It sits on the parapet at the south wall, facing out.
  put(sg.roof || 'COSTCO WHOLESALE', (X0 + X1) / 2, CEIL + 5.4, Z0 - T - 0.4,
      [1, 0, 0], [0, 0, -1], 30);

  // ---- the car park -------------------------------------------------------
  // Placed here rather than by `addScenery`, because the scatter's vocabulary is
  // trees and rocks and the palette therefore sets `density: 0`.
  // Painted bays, and nothing standing up in them. Lamp columns were the first
  // go at this and they are wrong twice over: from a car they are a field of
  // grey posts with no cars under them, which reads as scaffolding rather than as
  // a car park, and being the only vertical thing out here they draw the eye off
  // the building. What says "car park" at this scale is the *paint*.
  //
  // Bays come in back-to-back pairs with a driving aisle between, which is how a
  // lot is actually set out, and the whole of it is one unlit quad per line.
  const L = cfg.lot || {};
  const paint = L.line != null ? L.line : 0xe8e8e4;
  const BAY = 3.4;                  // one bay wide
  const DEEP_BAY = 7.0;             // and deep
  const LIFT = 0.12;                // clear of the ground plate, or they z-fight
  const y = base + LIFT;
  const W2 = 0.17;                  // half the width of a painted line
  const line2 = (xa, za, xb, zb) => bright.quad(
    [xa, y, za], [xb, y, za], [xb, y, zb], [xa, y, zb], paint);
  for (let z = Z0 - 84; z < Z1 + 84; z += DEEP_BAY * 2 + 9) {
    for (let x = -60; x < X1 + 170; x += BAY) {
      // Off the road, and near enough it to be the car park serving it. Without
      // the upper bound the paint runs to the edge of the ground plate, which is
      // the whole bounding box.
      const d = toRoad(x, z, base);
      if (d < 13 || d > 78) continue;
      if (x > X0 - 4 && x < X1 + 4 && z > Z0 - 4 && z < Z1 + 4) continue;
      // A bay is a |_| - two sides and a closed end - not a single stroke. Rows
      // come nose to nose in pairs, so the closed ends meet in the middle at `z`
      // and the open ends face the driving aisle either side; the head line is
      // therefore shared, drawn once, and butts up against its neighbours into a
      // continuous kerb line.
      const rows = [-1, 1].filter(s => toRoad(x + BAY / 2, z + s * DEEP_BAY * 0.6,
                                              base) >= 11);
      if (!rows.length) continue;
      line2(x, z - W2, x + BAY, z + W2);                       // the closed end
      for (const s of rows) {
        for (const e of [0, BAY]) {                            // and the two sides
          line2(x + e - W2, z, x + e + W2, z + s * DEEP_BAY);
        }
      }
    }
  }
}
