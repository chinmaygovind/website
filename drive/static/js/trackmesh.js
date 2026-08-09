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
  // The whole track is a descent, so the thing you look at for forty seconds is
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
  const legEvery = Math.max(4, Math.round(26 / (track.station || 3.5)));
  for (let i = Math.floor(legEvery / 2); i < line.length; i += legEvery) {
    const e = line[i];
    if (e.air || e.fix || e.pf) continue;       // nor under a pipe, whose edges
                                                // are walls rather than a deck
    if (e.n[1] < 0.7) continue;                 // not under a banked or rolled bit
    const base = groundY != null ? groundY : e.p[1] - 16;
    const drop = e.p[1] - THICK - base;
    if (drop < 1.5) continue;
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
  addScenery(solid, track, pal, bbox, CELL);
  if (groundY == null && pal.below) addWorldBelow(solid, soft, bright, track, pal, bbox, CELL, minY, maxY);

  const mat = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });
  const matBright = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide });
  group.add(solid.toMesh(mat));
  group.add(bright.toMesh(matBright));
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

function addScenery(buf, track, pal, bbox, CELL) {
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
      const baseY = gy;
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
