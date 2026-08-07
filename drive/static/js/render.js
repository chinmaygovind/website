// Everything you see. Deliberately plain: flat shading, no textures, no shadow
// maps, one merged mesh for the track. The look comes from the geometry and a
// two-colour sky, which is also why it holds 60fps on a laptop.
//
// The camera is the part worth reading. It orbits in the *car's* frame rather
// than the world's - its up vector and its idea of "behind" both come from the
// car - so a loop looks like a loop from the driver's seat instead of the world
// flipping over. Everything about it is exponentially smoothed, and the
// smoothing is frame-rate independent, so it never whips or judders. The two
// views you can hold a key for are the same orbit asked two questions: where the
// eye sits, and which way it looks.

import * as THREE from './vendor/three.module.js';
import { mulberry, MeshBuf } from './trackmesh.js';

const BRAKE_OFF = 0x521218;
const BRAKE_ON = 0xff2b2b;
// The colour the record is drawn in on the medals card, and so the only colour
// the record's own badge can be. Kept in step with `garage.RECORD_GREEN` by
// `test_garage.py`, because a badge in a different green from the record it is
// about is a badge about nothing.
const RECORD_GREEN = 0x55e08a;
// What each badge is drawn in. Its own colour each, so the mark says what kind of
// thing was earned and not merely that something was: a gold sunburst for having
// won everything, bronze steps for having been on a lot of podiums, the record's
// own green for the three that are about records.
const BADGE_COLOR = {
  laurel: RECORD_GREEN,
  crown: RECORD_GREEN,
  chevrons: RECORD_GREEN,
  sunburst: 0xe8c34a,      // gold
  podium: 0xc98b4b,        // bronze
  ribbon: 0xd8dee8,        // road grey
  shield: 0xc9ced6,        // silver
  // The one badge that is two colours. Its dark squares take the colour - so a
  // picked colour gives you red-and-white checkers - and the light ones are always
  // white, because a chequered flag with two custom colours is not one.
  checkers: 0x141821,
};
const CHECKER_LIGHT = 0xf2f4f8;
// How see-through a car is when it is not something you can hit. The ghost, a
// replay and a rival you are about to drive through are all the same statement
// - this car is not solid - so they are one number rather than three amounts
// of see-through.
const GHOST_OPACITY = 0.42;

/**
 * A livery, from whatever the caller had.
 *
 * **A bare colour string is still a livery**, and that is not a courtesy - it is
 * what keeps every path that predates the garage working untouched: a ghost from
 * the board, a car in a replay saved last month, a rival on a client that has
 * not reloaded. Those all hand over a hex string and get exactly the car Drive
 * has always drawn them.
 *
 * Every `null` below means "whatever the renderer did before anybody could
 * choose", not a colour that happens to match - so an account with no garage row
 * is byte-identical to one from before the garage existed, rather than merely
 * similar. `test_garage.py` pins that from the Python side and
 * `test_garage_js.py` from this one.
 */
function liveryOf(spec) {
  if (spec == null || typeof spec === 'string') spec = { body: spec || '#8899aa' };
  const body = new THREE.Color(spec.body || '#8899aa');
  const trim = spec.trim ? new THREE.Color(spec.trim) : body.clone().multiplyScalar(0.55);
  return {
    body, trim,
    glass: new THREE.Color(spec.glass || 0x2b3240),
    rim: new THREE.Color(spec.rim || 0xc9ced6),
    // **Whether a rim colour was chosen at all**, which the resolved colour above
    // cannot answer because it has a default baked into it. It is what lets
    // `stock` have a paintable outer lip without every car in the game growing
    // one: no colour, no lip, and an untouched car is byte-identical to the car
    // it was before this existed. The other five styles have a rim face whatever
    // you do, so it only ever decides anything for stock.
    rimSet: spec.rim != null,
    stripe: spec.stripe ? new THREE.Color(spec.stripe) : trim.clone(),
    finish: spec.finish || 'matte',
    livery: spec.livery || 'none',
    rimStyle: spec.rim_style || 'stock',
    // The cabin's own colour, or null for "the same as the body". Replaced the
    // `two_tone` boolean, which could only put the roof in the *trim* colour - so a
    // two-tone was always spoiler-coloured, and a white roof on a red car with a
    // black wing was not expressible at all.
    roof: spec.roof ? new THREE.Color(spec.roof) : null,
    // `null` means the badge's own colour (`BADGE_COLOR`), which is what keeps a
    // record's badge green for anybody who has not gone looking for the picker.
    badgeColor: spec.badge_color ? new THREE.Color(spec.badge_color) : null,
    badge: spec.badge || 'none',
  };
}

// How the paint catches the light. Matte is `MeshLambertMaterial`, which is what
// every car was until now and so is the only one that may be the default.
//
// The other three are `MeshPhongMaterial` and deliberately **not**
// `MeshStandardMaterial`: standard needs an environment map to read as metal and
// without one it goes flat and dark, and there is no env map here on purpose -
// the whole look is flat shading and no textures. Phong's specular highlight is
// the honest way to say "shiny" in a scene lit by one sun and a hemisphere.
//
// **A specular alone is not enough, and the reason is the look.** This car is
// `flatShading: true` boxes lit by one directional light, so a face has one
// normal and the specular term is *constant across it*: nothing travels, nothing
// reflects, and the whole of what a shiny finish did was make a sunlit panel
// slightly lighter. Four finishes that differ only in how much lighter are four
// finishes nobody can tell apart, which is what they were.
//
// So each one also says what it does to **the paint**. Metal is lighter and
// less saturated than the same colour in flat paint; pearl is lighter still with
// a colour that is not quite the one underneath it. Those are the differences the
// eye actually uses on a real car, they survive flat shading because they are in
// the albedo rather than in the lighting, and they leave the colour recognisably
// the one you picked.
//
// `mat` and `paint` are separate keys because `mat()` spreads its half straight
// into the material options, and a stray `lighten` on a `MeshPhongMaterial` is
// junk three.js would silently keep.
const FINISH = {
  // Untouched, and it has to be: `matte` is the default, so a car wearing it
  // must come out byte-identical to a car from before finishes existed.
  matte:    null,
  // **Wet paint, and not merely a harder highlight.** Gloss carries the whole idea
  // of a shiny car on its own now that metallic and pearl are gone, and a specular
  // on a flat-shaded face is a uniform brightening that is easy to miss - so it
  // deepens and enriches the colour as well, which is what wet paint actually does
  // to it. Darker rather than lighter, deliberately: lighter is what metallic was,
  // and the two would have been the same finish again.
  gloss:    { mat: { shininess: 110, specular: 0x8b9096 },
              paint: { darken: 0.13, saturate: 0.22 } },
  // **These two are set against each other, not against matte.** Telling either
  // from a flat car was the easy half; the pair started out both "a bit lighter
  // and slightly off-hue" and were nearly indistinguishable *from one another*,
  // which is a finish with two names. So metallic went less pale and more grey
  // and pearl went the other way: on a #3d8bfd body they are now #6893d3 (steel)
  // against #85aafe (pale and bright), which reads at a glance.
  // **Retired, and kept anyway.** Neither is offered any more - `garage.FINISHES`
  // is two, so `validate` turns a posted one into matte - but a *stored replay*
  // carries the livery it was driven in, unvalidated, and a replay is a record of
  // an afternoon. Deleting these would repaint every car in every race recorded
  // before today, which is the same rule that keeps a replay's livery stored with
  // it rather than looked up.
  metallic: { mat: { shininess: 190, specular: 0xcfd4dc },
              paint: { lighten: 0.10, desat: 0.38 } },
  pearl:    { mat: { shininess: 120, specular: 0xf2e6ff },
              paint: { lighten: 0.22, tint: 0xc9b6ff, amt: 0.30 } },
};

const _paint = new THREE.Color();
const WHITE = new THREE.Color(0xffffff);
const _grey = new THREE.Color();
const _tint = new THREE.Color();

/**
 * The colour a finish paints itself in, given the colour you chose.
 *
 * Applied to the body and the trim and to **nothing else** - see the two calls.
 * Not folded into `mat()`, because the decal material is painted too and is
 * `0xffffff` with `vertexColors`: a pearl tint applied there would multiply
 * every stripe and every badge on the car by a lilac, which is not what "my
 * paint is pearl" means.
 *
 * `L.body` itself is never touched, so the swatch in the garage and the dot on
 * the minimap still show the colour that was chosen rather than the colour the
 * finish made of it.
 */
function paintOf(color, finish) {
  const p = (FINISH[finish] || {}).paint;
  if (!p) return color;
  _paint.copy(color);
  // Toward white, which is the whole of what "lighter" means here - a metallic
  // is a pale version of its own colour and not a different hue.
  if (p.lighten) _paint.lerp(WHITE, p.lighten);
  // Toward its own grey, keeping the luminance it just gained. Flake scatters
  // light back at every angle, and the visible result of that is a colour with
  // the chroma knocked out of it rather than a brighter one.
  if (p.desat) {
    const g = _paint.r * 0.299 + _paint.g * 0.587 + _paint.b * 0.114;
    _paint.lerp(_grey.setRGB(g, g, g), p.desat);
  }
  // Away from white, which deepens a colour without moving its hue - the mirror of
  // `lighten` and the reason gloss cannot be mistaken for the metallic that was
  // here.
  if (p.darken) _paint.multiplyScalar(1 - p.darken);
  // Away from its own grey, which is `desat` run backwards: wet paint reads as more
  // of the colour it is, not less.
  if (p.saturate) {
    const g = _paint.r * 0.299 + _paint.g * 0.587 + _paint.b * 0.114;
    _paint.lerp(_grey.setRGB(g, g, g), -p.saturate);
  }
  if (p.tint) _paint.lerp(_tint.setHex(p.tint), p.amt);
  // Cloned: the scratch colour is reused on the next call, and the caller is
  // handing this straight to a material that keeps it.
  return _paint.clone();
}

/**
 * The face of a wheel, as one geometry.
 *
 * Everything is white: the colour comes from the material, so all five styles
 * share this code and a rim colour is a material change rather than a rebuild of
 * the buffer. Drawn in the wheel's own frame (X is the axle), a hair proud of
 * the tyre's outer face so it cannot z-fight with it.
 */
function rimGeometry(style) {
  const buf = new MeshBuf();
  const R = 0.40, W = 0.012, C = 0xffffff;
  // The centre boss, common to every style: a short polygon disc.
  const disc = (radius, seg) => {
    for (let i = 0; i < seg; i++) {
      const a0 = (i / seg) * Math.PI * 2, a1 = ((i + 1) / seg) * Math.PI * 2;
      buf.tri([W, 0, 0],
              [W, Math.sin(a0) * radius, Math.cos(a0) * radius],
              [W, Math.sin(a1) * radius, Math.cos(a1) * radius], C);
    }
  };
  // One spoke: a thin slab from the boss out to the rim, at `ang`.
  const spoke = (ang, half) => {
    const s = Math.sin(ang), c = Math.cos(ang);
    const p = (r, t) => [W, s * r - c * t, c * r + s * t];
    buf.quad(p(0.10, -half), p(R, -half), p(R, half), p(0.10, half), C);
  };
  const ring = (seg, inner) => {
    for (let i = 0; i < seg; i++) {
      const a0 = (i / seg) * Math.PI * 2, a1 = ((i + 1) / seg) * Math.PI * 2;
      const P = (a, r) => [W, Math.sin(a) * r, Math.cos(a) * r];
      buf.quad(P(a0, inner), P(a1, inner), P(a1, R), P(a0, R), C);
    }
  };
  if (style === 'stock') {
    // **A lip and nothing else** - no boss, no spokes. Stock is the plain
    // cylinder the wheel has always been, and the point of this is that its
    // outer edge can be painted, not that it quietly becomes a fifth wheel
    // design. Drawn at all only when a rim colour was actually chosen, so an
    // untouched car is exactly the car it was: see `hasRim`.
    ring(16, R - 0.045);
  } else if (style === 'dish') {
    disc(R, 16);                                   // solid: a moon disc
  } else if (style === 'mesh') {
    ring(16, R - 0.05); disc(0.13, 12);
    for (let i = 0; i < 10; i++) spoke((i / 10) * Math.PI * 2, 0.018);
  } else if (style === 'forged') {
    ring(16, R - 0.04); disc(0.14, 12);
    for (let i = 0; i < 5; i++) {                  // split five: paired blades
      const a = (i / 5) * Math.PI * 2;
      spoke(a - 0.14, 0.030); spoke(a + 0.14, 0.030);
    }
  } else {                                         // spoke5, and the fallback
    const n = style === 'spoke6' ? 6 : 5;
    ring(16, R - 0.04); disc(0.13, 12);
    for (let i = 0; i < n; i++) spoke((i / n) * Math.PI * 2, 0.055);
  }
  return buf.toGeometry();
}

// **A vertex colour is not a hex colour.** three.js has colour management on:
// `new THREE.Color(0x55e08a)` is read as sRGB and converted into the linear
// working space, and the renderer encodes back to sRGB on the way out, so a
// `Color` round-trips and comes out as the value you typed. A raw colour
// *attribute* is assumed to already be linear and gets only the encode out - so
// writing 0x55e08a straight into one draws it as roughly 0x9cf0c0, a pale wash
// instead of the record green.
//
// Every decal on the car goes through here, which means **a stripe now matches
// the swatch it was picked from**. It did not before: stripe colours were written
// raw and drew about twice as bright as the chip in the garage. That was liveable
// while a stripe was any old colour, and stopped being liveable when a badge had
// to be recognisably *bronze* rather than recognisably tan.
//
// `MeshBuf` itself is deliberately left alone. The twelve track palettes were
// picked by eye against the unmanaged pipeline, so "fixing" it there would restyle
// every track in the game; the car's decals are a different consumer of the same
// buffer and are the only ones that have to match a managed colour.
const _lin = new THREE.Color();

function linear(hex) {
  _lin.setHex(hex);
  return (Math.round(_lin.r * 255) << 16) | (Math.round(_lin.g * 255) << 8)
       | Math.round(_lin.b * 255);
}

/**
 * Every decal on the car - stripes and the badge - as one `MeshBuf`, or null.
 *
 * **One buffer, so a badge is free.** It used to be its own mesh with its own
 * material, which is a whole draw call for a shape the size of a hand; folded in
 * here it costs nothing at all, because a badge *is* a decal on the bonnet in
 * exactly the way a stripe is.
 *
 * Decals sit `LIFT` above the panel they decorate. That number is the whole of
 * why this is not a texture: at this scale a hundredth of a unit is invisible
 * and is far more than enough to keep two coplanar surfaces from tearing into
 * each other, and the renderer has no textures anywhere else.
 *
 * `fade` is the reason all of this goes through `MeshBuf` rather than a handful
 * of boxes: the buffer carries a colour per vertex, so a gradient is a lerp
 * written into the attribute and costs nothing. A texture would have been the
 * only other way, in a renderer whose entire look is that it has none.
 */
function decalMesh(L) {
  const striped = L.livery && L.livery !== 'none';
  const badged = L.badge && L.badge !== 'none';
  if (!striped && !badged) return null;
  const buf = new MeshBuf();
  const S = linear(L.stripe.getHex()), B = linear(L.body.getHex());
  const LIFT = 0.01;
  // The two panels a stripe can lie on, from the chassis boxes above, and **the
  // extent of each of them**. These are named rather than typed out at each case
  // because they are not free numbers - they are the bonnet and the roof, and
  // when either of those changed shape every literal that quietly encoded the old
  // one became a stripe running off the end of the panel it decorates. Both have
  // moved once already: the bonnet now reaches the nose at -2.2 because the body
  // does, and the roof starts at -0.15 because the front of the cabin became a
  // raked windscreen. Written out, the roof stripes hung half a unit past the
  // front of the roof, floating in the air over the screen.
  const DECK = 0.555 + LIFT, ROOF = 1.03 + LIFT;
  const NOSE = -1.7, TAIL = 1.7;            // the bonnet, end to end
  const RF = -0.15, RB = 0.9;               // the roof, front and back
  // **The third panel: the car's sides.** Added because two of the liveries can
  // only be themselves with it. A hoop that stops at the roofline is not a hoop,
  // and a car painted in halves along a line nobody can see from beside it is
  // not painted in halves - which is what both of them were.
  //
  // `FX` is the flank plane, `FY0`/`FY1` its top and bottom. Inset a little
  // inside the `lower` box's own 0.005..0.555 so a decal cannot hang over the
  // edge onto the underside or up over the deck, where it would read as a fold.
  const FX = 0.95 + LIFT;
  const FY0 = 0.03, FY1 = 0.53;
  // The middle of the car, derived rather than typed so it follows the bonnet.
  // `halves` splits here, which is the only split worth calling halves: at the
  // windscreen's foot it was 28% of the car, and the name is a claim about
  // proportion. The stretch from here forward to the cabin passes under the
  // screen and the cabin and simply is not seen, which is what happens to every
  // full-length stripe already.
  const MID = (NOSE + TAIL) / 2;
  // Wound anticlockwise seen from above, so `computeVertexNormals` gives these
  // an upward normal. The obvious order is the other one and it is silently
  // wrong: the decal still draws, and it is lit from underneath, so a bright
  // stripe comes out as a dark smear on the one surface the sun is hitting.
  const deck = (x0, x1, z0, z1, color) => buf.quad(
    [x0, DECK, z0], [x0, DECK, z1], [x1, DECK, z1], [x1, DECK, z0], color);
  const roof = (x0, x1, z0, z1, color) => buf.quad(
    [x0, ROOF, z0], [x0, ROOF, z1], [x1, ROOF, z1], [x1, ROOF, z0], color);
  /**
   * Both sides at once, wound so each one's normal points *out of* the car.
   *
   * Which is the same trap the two above carry a warning about, arrived at from
   * a new direction: the winding that lights the right flank correctly lights
   * the left one from inside the bodywork, so the two cannot share an order -
   * they are mirror images. Getting it wrong is silent in the same way. The
   * decal draws, and one side of the car is a bright stripe while the other is a
   * dark smear.
   */
  const flank = (z0, z1, y0, y1, color) => {
    buf.quad([FX, y0, z0], [FX, y1, z0], [FX, y1, z1], [FX, y0, z1], color);
    buf.quad([-FX, y0, z1], [-FX, y1, z1], [-FX, y1, z0], [-FX, y0, z0], color);
  };

  // Wrapped, because a badge with no livery still wants a buffer - the whole
  // point of folding them together is that either one alone is enough to be worth
  // a mesh, and neither costs a second one.
  if (striped) {
    switch (L.livery) {
      case 'centre':
        deck(-0.17, 0.17, NOSE, TAIL, S); roof(-0.17, 0.17, RF, RB, S); break;
      case 'twin':
        for (const x of [-0.42, 0.14]) {
          deck(x, x + 0.28, NOSE, TAIL, S); roof(x, x + 0.28, RF, RB, S);
        }
        break;
      case 'band':
        deck(-0.45, 0.45, NOSE, TAIL, S); roof(-0.45, 0.45, RF, RB, S); break;
      // **Across the car rather than along it, and now actually across it.** This
      // used to be a full-width band on the deck at z 0.35..0.85 plus the *whole*
      // roof. The cabin stands on the deck from -0.15 to 0.9 and is 1.55 wide
      // against the body's 1.9, so all the band ever showed was two strips of deck
      // 0.175 wide either side of the roof: what you saw was a painted roof with a
      // pair of tabs beside it, which is not a hoop by any reading.
      //
      // A band at one z up the flank, over the roof and down the other side is the
      // thing the name always meant. The deck between flank and cabin stays bare at
      // that z because the cabin is standing on it, which is what a real hoop does
      // too.
      case 'hoop': {
        const H0 = 0.2, H1 = 0.6;
        roof(-0.76, 0.76, H0, H1, S); flank(H0, H1, FY0, FY1, S); break;
      }
      // The front half of the car in the second colour, **sides included**. It used
      // to be the bonnet alone, painted full-width back to z 0.05 - which put the
      // line where the two colours meet underneath the windscreen, so all you could
      // see was a car with a differently coloured bonnet and no join anywhere. With
      // the flanks the join is a vertical line down the middle of the side, which is
      // the thing that makes a two-tone read as one.
      //
      // Not the front *face*: the headlights sit 0.01 proud of it and a decal there
      // would be coplanar with their lenses and z-fight them.
      case 'halves':
        deck(-0.94, 0.94, NOSE, MID, S); flank(NOSE, MID, FY0, FY1, S); break;
      case 'pinstripe':                     // gated: two hairlines, deliberately fine
        for (const x of [-0.5, 0.44]) {
          deck(x, x + 0.06, NOSE, TAIL, S); roof(x, x + 0.06, RF, RB, S);
        }
        break;
      case 'fade': {
        // Baked into the vertices: nose in the stripe colour, tail in the body's.
        // Lerped between the *managed* colours and linearised after, not between
        // `S` and `B` - those are already linear, and reading one back in through
        // `THREE.Color` would convert it a second time and bend the ramp.
        const N = 10, LEN = TAIL - NOSE;
        for (let i = 0; i < N; i++) {
          const z0 = NOSE + (LEN * i) / N, z1 = NOSE + (LEN * (i + 1)) / N;
          const c = L.stripe.clone().lerp(L.body, i / (N - 1));
          deck(-0.94, 0.94, z0, z1, linear(c.getHex()));
        }
        break;
      }
      default: break;
    }
  }

  if (badged) {
    const own = BADGE_COLOR[L.badge];
    badgeShape(buf, L.badge, DECK,
               linear(L.badgeColor ? L.badgeColor.getHex()
                                   : (own == null ? RECORD_GREEN : own)));
  }
  // A livery or badge value this renderer has never heard of - a client that has
  // not reloaded since the vocabulary grew - draws nothing rather than an empty
  // mesh with a material attached to it.
  return buf.pos.length ? buf : null;
}

// Where the badge sits and how big it is. The clear bonnet is the stretch ahead
// of the windscreen's foot, z -1.7 to -0.75, so this is its middle.
//
// **`STRETCH` is the one number here that is not about the shape.** A badge lies
// flat on the bonnet and the camera you actually see it from is behind and above,
// so everything is foreshortened along z - the axis the icons treat as up. Drawn
// square, a crown came out as a blob and a podium's three steps read as one
// smear, because the whole of what distinguishes them is height. So the icons are
// described square and stretched along z on the way out, which is a single number
// rather than a bias baked into eight sets of coordinates.
//
// **Which way is up: toward the tail.** A badge on a bonnet is read by somebody
// standing in front of the car, the way every real one is - so the top of the icon
// has to be the end nearest the windscreen. Pointing it at the nose instead put
// every badge upside down to anyone looking at the front of the car, which is the
// only angle a hood badge is really *for*.
// The two are set together, and the ceiling is the bonnet: it is 1.88 across and
// only 0.95 long, so the *length* is what binds. A round badge stretched to appear
// square therefore tops out at 0.95 long and 0.95/1.28 wide, and these are that
// with a little margin. Going wider is free and going longer is not.
const BADGE_Z = -1.2, BADGE_RAD = 0.34, STRETCH = 1.28;
const TAU = Math.PI * 2;

/**
 * One badge, drawn flat on the bonnet, in icon coordinates.
 *
 * `u` is right across the car and `v` is **up toward the nose**, so a shape
 * described the way you would sketch it comes out the right way up to the driver
 * and to the chase camera looking down at the bonnet.
 *
 * `tri2` fixes its own winding, and that is deliberate rather than lazy. A decal
 * wound the wrong way still draws and is lit from underneath, so it comes out as
 * a dark smear on the one surface the sun is hitting - and seven hand-drawn
 * shapes made of arcs and fans is a lot of chances to get an order backwards for
 * no gain. Describing the corners is the interesting part; their order is not.
 */
function badgeShape(buf, badge, y, C) {
  const P = ([u, v]) => [u, y, BADGE_Z + v * STRETCH];
  const tri2 = (a, b, c, color) => {
    const A = P(a), B = P(b), D = P(c);
    // The y of (B-A) x (D-A), in **world** space rather than in icon space. That
    // matters: icon-space handedness depends on which way `P` maps v, so the
    // icon-space test silently inverted the moment the badges were turned round to
    // face the front of the car, and every one of them would have gone dark.
    const ny = (B[2] - A[2]) * (D[0] - A[0]) - (B[0] - A[0]) * (D[2] - A[2]);
    const col = color == null ? C : color;
    if (ny >= 0) buf.tri(A, B, D, col);
    else buf.tri(A, D, B, col);
  };
  const quad2 = (a, b, c, d, color) => {
    tri2(a, b, c, color); tri2(a, c, d, color);
  };
  const ring = (r, a) => [Math.cos(a) * r, Math.sin(a) * r];
  const R = BADGE_RAD;

  switch (badge) {
    // A closed wreath of leaves with a 1 standing in it. Closed rather than the
    // two open sprigs a laurel usually is, because at this size the gap at the top
    // read as a broken circle rather than as two branches.
    //
    // **One continuous scalloped ring**, not nine separate leaves. Separate leaves
    // were tried twice - as triangles and as four-cornered leaf shapes - and both
    // times the gaps between them were bigger than the leaves at this size, so it
    // came out as a scatter of green specks rather than as a wreath. A ring whose
    // outer edge rises and falls in nine lobes reads as foliage *and* reads as a
    // ring, which is the thing that has to survive being small.
    case 'laurel': {
      const SEG = 36, LOBES = 9, R0 = R * 0.60;
      const out = (a) => R * (0.84 + 0.16 * Math.abs(Math.sin(a * LOBES / 2)));
      const lobe = (a) => [Math.cos(a) * out(a), Math.sin(a) * out(a)];
      for (let i = 0; i < SEG; i++) {
        const a0 = (i / SEG) * TAU, a1 = ((i + 1) / SEG) * TAU;
        quad2(ring(R0, a0), ring(R0, a1), lobe(a1), lobe(a0));
      }
      // The numeral, narrow and tall so it stays a 1 rather than a blob: a stem,
      // the little flag off the top left, and a foot.
      quad2([-0.030, -0.10], [0.030, -0.10], [0.030, 0.17], [-0.030, 0.17]);
      tri2([-0.085, 0.085], [-0.030, 0.085], [-0.030, 0.17]);
      quad2([-0.080, -0.15], [0.080, -0.15], [0.080, -0.10], [-0.080, -0.10]);
      break;
    }
    // **All sixteen squares, in two colours.** The light ones used to be bare
    // bodywork, which is cheaper and is not a chequered flag: on a white car it was
    // half a flag, and on a green one it was green-and-green. So the dark squares
    // take the badge's colour and the light ones are always white - a flag with two
    // custom colours is not the thing the flag means.
    case 'checkers': {
      const W = R * 0.42;
      for (let r = 0; r < 4; r++) {
        for (let c = 0; c < 4; c++) {
          const u0 = -2 * W + c * W, v0 = 2 * W - (r + 1) * W;
          quad2([u0, v0], [u0 + W, v0], [u0 + W, v0 + W], [u0, v0 + W],
                (r + c) % 2 ? linear(CHECKER_LIGHT) : C);
        }
      }
      break;
    }
    case 'chevrons': {
      const W = R * 0.82, H = 0.15, T = 0.075;
      for (let k = 0; k < 3; k++) {
        const v0 = -0.2 + k * 0.145;
        quad2([-W, v0], [0, v0 + H], [0, v0 + H - T], [-W, v0 - T]);
        quad2([0, v0 + H], [W, v0], [W, v0 - T], [0, v0 + H - T]);
      }
      break;
    }
    // A thin band with three tall points standing well clear of it. The first go
    // had a thick band and short points and came out as a solid arrowhead: the
    // gaps between the points are the whole of what makes it a crown, so they
    // have to be taller than the band rather than notches in it.
    case 'crown': {
      const W = R * 0.80, BAND = [-0.20, -0.11];
      quad2([-W, BAND[0]], [W, BAND[0]], [W, BAND[1]], [-W, BAND[1]]);
      // Half-width 0.055 against a spacing of 0.18, so the gaps are wider than
      // the feet of the points. At 0.085 they were 0.005 apart and the three
      // merged into one solid arrowhead - the gaps *are* the crown.
      for (const u of [-W * 0.66, 0, W * 0.66]) {
        tri2([u - 0.055, BAND[1]], [u + 0.055, BAND[1]], [u, 0.22]);
      }
      break;
    }
    // Three pips in a row with the middle one biggest - **not** the three steps a
    // podium actually is, and the reason is worth writing down because it applies
    // to any badge somebody adds later.
    //
    // This is a decal lying flat on a bonnet, so **there is no up in it**. What the
    // icons call height is length along the car, pointing away from the camera - so
    // three blocks of three different heights come out as three blocks of three
    // different *lengths*, and no arrangement of them reads as a podium. Steps were
    // tried separated and connected; the first was a bar chart and the second a
    // blob with fingers.
    //
    // What survives being flat is anything whose plan view is the whole idea:
    // chequers is a grid, sunburst is radial, the wreath is a ring. So the podium
    // is three pips and a bigger one in the middle, which says first-of-three by
    // size rather than by height - and size is the one thing foreshortening keeps.
    // Discs and not diamonds, for the same reason as everything else here: a
    // diamond tapers to a point at the top and bottom, and a point along the
    // foreshortened axis is the first thing to disappear - three of them came out
    // as three horizontal slivers. A disc has no thin part to lose.
    case 'podium': {
      // Spaced so there is clear bodywork between them: at 0.235 apart the outer
      // discs overlapped the middle one and the three read as a single blob.
      for (const [u, s] of [[-0.285, 0.085], [0, 0.145], [0.285, 0.085]]) {
        for (let i = 0; i < 10; i++) {
          const a0 = (i / 10) * TAU, a1 = ((i + 1) / 10) * TAU;
          tri2([u, 0], [u + Math.cos(a0) * s, Math.sin(a0) * s],
               [u + Math.cos(a1) * s, Math.sin(a1) * s]);
        }
      }
      break;
    }
    case 'sunburst': {
      const R0 = R * 0.33, N = 12, HALF = 0.055, HUB = R * 0.30;
      for (let i = 0; i < N; i++) {
        const a = (i / N) * TAU;
        tri2(ring(R0, a - HALF), ring(R0, a + HALF), ring(R, a));
      }
      for (let i = 0; i < 10; i++) {
        tri2([0, 0], ring(HUB, (i / 10) * TAU), ring(HUB, ((i + 1) / 10) * TAU));
      }
      break;
    }
    // A road going away from you: a tapering strip with a dashed centre line. The
    // first go was a winding one, a sine narrowing as it went, and at this size it
    // read as a squiggle - the curve ate the taper, and the taper is the only thing
    // saying "distance". Straight and tapered says it in one shape, and the dashes
    // are what stop it reading as an arrowhead.
    // Drawn as its *markings* rather than as its surface - two edge lines
    // converging away from you and a dashed centre line - because the badge is one
    // colour, and a solid road with dashes painted on it in the same colour is a
    // solid road. Converging lines are also what actually says distance; the first
    // go filled the whole strip in and read as an arrowhead.
    case 'ribbon': {
      const BOT = -0.24, TOP = 0.26, WB = 0.21, WT = 0.06;
      const vAt = (t) => BOT + (TOP - BOT) * t;
      const wAt = (t) => 0.050 - 0.030 * t;          // the line narrows with it
      const strip = (t0, t1, at, scale) => {
        const w0 = wAt(t0) * scale, w1 = wAt(t1) * scale;
        quad2([at(t0) - w0, vAt(t0)], [at(t0) + w0, vAt(t0)],
              [at(t1) + w1, vAt(t1)], [at(t1) - w1, vAt(t1)]);
      };
      for (const side of [-1, 1]) {
        strip(0, 1, (t) => side * (WB + (WT - WB) * t), 1);
      }
      for (let i = 0; i < 4; i++) {
        strip(i / 4 + 0.05, (i + 1) / 4 - 0.11, () => 0, 0.85);
      }
      break;
    }
    // A crest: flat across the top, shoulders, and a point at the bottom. Chosen
    // for its silhouette being the crown's turned upside down - flat top and one
    // point below against a spiked top and a flat base - which is about as far
    // apart as two shapes get while both still reading as heraldry.
    case 'shield': {
      // A crest, drawn as **two** pieces with the paint showing between them: the
      // chief across the top and the field under it. As one solid outline it was
      // the only badge here with no internal structure at all - a grey blob, which
      // a screenshot from the front is the only thing that says out loud. The split
      // is a *gap* rather than a second colour on purpose: `checkers` needing two
      // is an exception the flag forces, not a pattern to spread, and a gap keeps
      // the whole badge one recolourable thing.
      const W = R * 0.62, TOP = 0.26, WAIST = -0.02, TIP = -0.30;
      const CHIEF = 0.15, GAP = 0.055;      // GAP is wide for the usual reason
      // The silhouette tapers from TOP to WAIST, so both pieces have to read off
      // the same edge or the crest comes out as a box sitting on a spade.
      const hw = (v) => W * (1 - 0.14 * (TOP - v) / (TOP - WAIST));
      quad2([-W, TOP], [W, TOP], [hw(CHIEF), CHIEF], [-hw(CHIEF), CHIEF]);
      const F = CHIEF - GAP;
      quad2([-hw(F), F], [hw(F), F], [hw(WAIST), WAIST], [-hw(WAIST), WAIST]);
      tri2([-hw(WAIST), WAIST], [hw(WAIST), WAIST], [0, TIP]);
      break;
    }
    default: break;
  }
}

export class CarView {
  constructor(scene, livery, opts = {}) {
    this.group = new THREE.Group();
    this.body = new THREE.Group();
    this.group.add(this.body);
    const ghost = !!opts.ghost;
    const L = liveryOf(livery);
    this.livery = L;
    const col = L.body;

    // Every material the car is built from, kept so it can be turned
    // translucent and back at run time - see setGhostly. The label is
    // deliberately not one of them: a name has to stay readable whatever the
    // car under it is doing.
    //
    // `_solid` is what "not translucent" means for *this* car, which is not
    // always opaque: a ghost is born translucent, so making one solid because a
    // phase changed would turn the ghost into a fifth real-looking car.
    this._mats = [];
    this._solid = ghost ? GHOST_OPACITY : 1;
    // `painted` picks the finish; everything that is not paint - glass, tyres,
    // the lamps - stays matte whatever the car is wearing, because a shiny tyre
    // is not a thing and a glossy lamp lens fights the one signal on the car
    // that has to be unambiguous.
    const mat = (c, extra = {}, painted = false) => {
      const spec = painted ? FINISH[L.finish] : null;
      const opt = Object.assign({ color: c, flatShading: true,
                                  transparent: ghost, opacity: this._solid },
                                (spec && spec.mat) || {}, extra);
      const m = spec ? new THREE.MeshPhongMaterial(opt)
                     : new THREE.MeshLambertMaterial(opt);
      this._mats.push(m);
      return m;
    };

    // The finish's *paint* half, here and only here - the decal material below is
    // painted too and would tint every stripe on the car. See `paintOf`.
    const bodyMat = mat(paintOf(col, L.finish), {}, true);
    const darkMat = mat(paintOf(L.trim, L.finish), {}, true);
    // The roof is `bodyMat` when nobody has picked a colour for it, which is the
    // one-material case and the common one; a chosen colour is a third painted
    // material and the only thing on the car that costs one.
    const cabinMat = L.roof ? mat(paintOf(L.roof, L.finish), {}, true) : bodyMat;
    const glassMat = mat(L.glass);
    const tyreMat = mat(0x1c1f26);

    // chassis: a wedge-ish stack of boxes, Polytrack-simple
    //
    // **The body is the whole car and its front face is the front of the car.**
    // There is no nose piece, no bumper slab and nothing standing out in front:
    // three separate attempts at a front all read worse than nothing, because a
    // separate panel meeting the bonnet draws a line across the widest, flattest,
    // best-lit surface on the car, and the two sides of that line catch the light
    // differently however carefully the pieces are aligned. Sloped it is a
    // crease, flat it is a step, inset it is a step down the flanks too.
    //
    // So the only things on the front are the lamps, and they sit **flush** in the
    // face rather than proud of it. The overhang goes with the bumper, which
    // leaves the front about as short as the rear already was - the car reads as
    // symmetrical now rather than as a long nose with no tail.
    const lower = new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.55, 3.4), bodyMat);
    lower.position.y = 0.28;
    this.body.add(lower);
    // Shorter than the body it sits on, because the front of it is the windscreen
    // rather than a wall - see below.
    const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.55, 0.5, 1.05), cabinMat);
    cabin.position.set(0, 0.78, 0.375);
    this.body.add(cabin);
    // **The raked windscreen.** The cabin used to be a plain box, so the front of
    // it was a dead-vertical wall rising 0.475 straight out of the bonnet, which
    // no car has. This is a slab lying along the line from the deck at z = -0.75
    // up to the roof at z = -0.15: a rise of 0.475 over 0.6, about 52 degrees off
    // vertical.
    //
    // It replaces the old glass box rather than joining it, so the cabin costs no
    // more than it did. That box was 1.42 wide inside a 1.55 cabin, so its sides
    // were buried and the only part of it anybody ever saw *was* the windscreen
    // face - which is exactly what this is, at the right angle.
    //
    // **Positioned by its top face, not its centre.** A slab has thickness, and
    // the thing that has to land on the line from the deck to the roof is the pane
    // you can see, so the centre sits half a thickness under that line along its
    // own normal. Put the centre on the line instead and the leading edge stands
    // an eighth of a unit proud of the bonnet, drawing a dark fin up out of the
    // paint rather than a windscreen.
    const screen = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.34, 0.765), glassMat);
    screen.position.set(0, 0.656, -0.345);
    screen.rotation.x = -0.667;
    this.body.add(screen);
    // Headlights: one mesh, one material, and **the colour is not yours**. The
    // reasoning is the brake lamps' own, a screen down: the lamps are the only
    // thing another driver reads off your car, which is why the amber drift state
    // was taken out again. A headlight somebody can paint black is the same
    // mistake with a settings page in front of it.
    //
    // Unlit and built by hand rather than through `mat()`, for the same reason the
    // brake lamps are: `mat()` makes a lit material and takes the finish, so a
    // lens would go glossy with the paint and darken on the side away from the
    // sun. A lamp is a lamp at every angle. One `MeshBuf` rather than two meshes
    // because, unlike the brake lamps, these never change independently.
    //
    // **Flush, which means 0.01 proud and not 0.** The body's front face is at
    // z = -1.7; a lens whose own face is at exactly -1.7 is coplanar with it and
    // the two z-fight into a flicker, and a lens set even a thousandth *behind* it
    // vanishes inside the bodywork. A hundredth is the same trick the livery
    // decals use for the same reason, and it is invisible at this scale.
    const lamps = new MeshBuf();
    for (const s of [-1, 1]) lamps.box(s * 0.53, 0.36, -1.67, 0.25, 0.07, 0.04, 0xffeccc);
    const headMat = new THREE.MeshBasicMaterial({
      color: 0xffeccc, transparent: ghost, opacity: this._solid });
    this._mats.push(headMat);
    this.body.add(lamps.toMesh(headMat));
    const wing = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.12, 0.42), darkMat);
    wing.position.set(0, 0.92, 1.72);
    this.body.add(wing);
    for (const s of [-1, 1]) {
      const stay = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.34, 0.12), darkMat);
      stay.position.set(s * 0.7, 0.74, 1.72);
      this.body.add(stay);
    }

    // wheels
    const wheelGeo = new THREE.CylinderGeometry(0.42, 0.42, 0.34, 10);
    wheelGeo.rotateZ(Math.PI / 2);
    // A rim is **one geometry for the whole face**, built once here and shared by
    // all four wheels, not a disc plus N spoke meshes. That is a draw-call
    // decision rather than a tidiness one: five spokes as separate meshes is
    // twenty-four extra meshes on one car and nearly two hundred on a full grid,
    // which is real cost on a phone. Merged, the wheels go from four meshes to
    // eight whatever style is on them.
    //
    // Built with `MeshBuf`, which is the project's own triangle accumulator and
    // already does exactly this for the entire track. `mergeGeometries` is a
    // three.js addon and is deliberately not vendored here.
    // Stock earns a rim face only once somebody paints it - see `rimSet`. So the
    // default car still costs 14 meshes and 7 materials, and a painted stock
    // wheel costs the 4 meshes, 1 material and 1 geometry that choosing any other
    // wheel style already costs.
    const hasRim = !!L.rimStyle && (L.rimStyle !== 'stock' || L.rimSet);
    const rimGeo = hasRim ? rimGeometry(L.rimStyle) : null;
    // Double-sided on purpose: a rim is a flat plate on the outboard face of
    // each wheel, and the left pair are mirrored, so one of the two sides would
    // otherwise be facing away and draw nothing at all.
    const rimMat = hasRim ? mat(L.rim, { side: THREE.DoubleSide }, true) : null;
    this.wheels = [];
    this.steered = [];
    for (const [x, z, front] of [[-1.0, -1.15, true], [1.0, -1.15, true],
                                 [-1.0, 1.25, false], [1.0, 1.25, false]]) {
      const hub = new THREE.Group();
      hub.position.set(x, 0.4, z);
      const w = new THREE.Mesh(wheelGeo, tyreMat);
      hub.add(w);
      if (rimGeo) {
        // One rim per wheel, on the outboard face, and it spins with the tyre -
        // so it is parented to the wheel rather than to the hub. A rim that
        // stayed still while the tyre turned would be the only part of the car
        // that is obviously wrong at any speed.
        const r = new THREE.Mesh(rimGeo, rimMat);
        r.position.x = (x < 0 ? -1 : 1) * 0.175;
        r.rotation.y = x < 0 ? Math.PI : 0;
        w.add(r);
      }
      this.body.add(hub);
      this.wheels.push(w);
      if (front) this.steered.push(hub);
    }

    // Every decal on the car as one mesh - however many stripes the livery is
    // made of, **and the badge with them**. The same trick pays for `fade`, which
    // is a colour ramp baked straight into the vertices rather than a texture the
    // rest of this renderer does not have; and it is what makes a badge free,
    // where it used to be a whole draw call for a shape the size of a hand.
    const deco = decalMesh(L);
    if (deco) {
      const decoMat = mat(0xffffff, { vertexColors: true }, true);
      const m = deco.toMesh(decoMat);
      this.body.add(m);
    }

    // contact shadow: one dark disc laid on the surface under the car
    this._shadowOpacity = ghost ? 0.1 : 0.24;
    this.shadow = new THREE.Mesh(
      new THREE.CircleGeometry(1.5, 14),
      new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true,
                                    opacity: this._shadowOpacity, depthWrite: false }));
    this.shadow.rotation.x = -Math.PI / 2;
    scene.add(this.shadow);

    // Brake lights. Two panels on the tail, unlit material so they read as
    // emissive without a second light in the scene: dark red at rest, full red
    // the instant you touch the brakes. They are on the *car*, not the HUD, so
    // you can see the driver ahead of you braking - which is the only reason a
    // detail like this is worth any geometry at all.
    //
    // Two states and no third one. Drifting had an amber state for a while and
    // it is gone: the handbrake counts as braking, so a slide meant the lamps
    // changed colour rather than coming on, and a car that goes yellow every
    // time it steps out reads as a fault rather than as a driver.
    this.brakeMats = [];
    for (const s of [-1, 1]) {
      const m = new THREE.MeshBasicMaterial({
        color: BRAKE_OFF, transparent: ghost, opacity: this._solid });
      const lamp = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.22, 0.1), m);
      lamp.position.set(s * 0.6, 0.5, 1.73);
      this.body.add(lamp);
      this.brakeMats.push(m);
      this._mats.push(m);
    }
    // **The nameplate is the car's colour and nothing else.** It used to turn the
    // record green for anybody wearing the laurel, which was worth it while the
    // badge was a bar on the bumper that nothing could see: a decal on a low-poly
    // car is invisible at the distance you actually see rivals from, and the name
    // over it is legible from anywhere.
    //
    // It stopped being worth it when the badge became a case of seven. Green would
    // then mean "wearing one of the three green ones", which is not a fact worth a
    // colour; and the alternative - a plate per badge - takes away the one thing
    // the plate is good at, which is being that driver's colour. The badge is on
    // the bonnet now and says what it says by itself.
    //
    // `setLabel(text, color)` stays, so a caller can still override a plate; it
    // simply has nothing to override any more. `test_rules_js.py` pins that
    // nobody does.
    this.plateColor = '#' + col.getHexString();

    this._braking = false;
    this._ghostly = ghost;

    scene.add(this.group);
    this.scene = scene;
    this.color = '#' + col.getHexString();
    this.label = null;
  }

  setLabel(text, color) {
    if (this.label) { this.group.remove(this.label); this.label.material.map.dispose(); }
    if (!text) { this.label = null; return; }
    const c = document.createElement('canvas');
    c.width = 256; c.height = 64;
    const g = c.getContext('2d');
    g.font = 'bold 34px system-ui, sans-serif';
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.lineWidth = 7;
    g.strokeStyle = 'rgba(0,0,0,.75)';
    g.strokeText(text, 128, 34);
    // The badge speaks through the plate when the caller has no opinion, which
    // is what makes a record holder recognisable from behind at racing distance.
    g.fillStyle = color || this.plateColor || '#fff';
    g.fillText(text, 128, 34);
    const tex = new THREE.CanvasTexture(c);
    const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true,
                                                           depthTest: false }));
    spr.scale.set(4.2, 1.05, 1);
    spr.position.set(0, 2.5, 0);
    this.group.add(spr);
    this.label = spr;
  }

  /** Pose from the simulation, plus the cosmetic lean/squash. */
  update(pos, quat, opts = {}) {
    this.group.position.copy(pos);
    this.group.quaternion.copy(quat);
    const lean = opts.lean || 0;
    const steer = opts.steer || 0;
    this.body.rotation.z = lean;
    this.body.rotation.x = (opts.pitch || 0);
    for (const hub of this.steered) hub.rotation.y = -steer * 0.42;
    if (opts.spin != null) for (const w of this.wheels) w.rotation.x = -opts.spin;
    if (opts.groundY != null) {
      this.shadow.visible = true;
      this.shadow.position.set(pos.x, opts.groundY + 0.03, pos.z);
      if (opts.groundN) {
        this.shadow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), opts.groundN);
      }
      const fade = Math.max(0, 1 - Math.abs(pos.y - opts.groundY) / 7);
      this.shadow.material.opacity = this._shadowOpacity * fade;
    } else {
      this.shadow.visible = false;
    }
    const braking = !!opts.braking;
    if (braking !== this._braking) {
      this._braking = braking;
      for (const m of this.brakeMats) m.color.setHex(braking ? BRAKE_ON : BRAKE_OFF);
    }
  }

  /**
   * Solid, or a translucent shell of the same car.
   *
   * Colour is the whole of how you tell one rival from another, so it is not
   * touched: only opacity moves, and the name above the car does not fade at
   * all. `transparent` is part of a material's program key in three.js, so
   * flipping it recompiles a shader - hence the early return, since this is
   * called from the frame loop and the answer changes about twice a race.
   *
   * "Solid" is `_solid` rather than 1, because a ghost is born translucent and
   * turning one opaque would make it a fifth real-looking car.
   */
  setGhostly(on) {
    on = !!on;
    if (on === this._ghostly) return;
    this._ghostly = on;
    const o = on ? GHOST_OPACITY : this._solid;
    for (const m of this._mats) {
      m.transparent = o < 1;
      m.opacity = o;
      m.needsUpdate = true;
    }
    // Through the stored opacity, since `update` redraws the disc every frame
    // from it and would otherwise put it straight back.
    this._shadowOpacity = (on || this._solid < 1) ? 0.1 : 0.24;
    this.shadow.material.opacity = this._shadowOpacity;
  }

  setVisible(v) {
    this.group.visible = v;
    this.shadow.visible = v && this.shadow.visible;
  }

  dispose() {
    this.scene.remove(this.group);
    this.scene.remove(this.shadow);
  }
}

// A pool of camera-facing quads used for tyre smoke, sparks and dust. One
// geometry, one draw call per particle - at these counts that is free, and it
// avoids shipping a particle library.
class Particles {
  constructor(scene, count = 90) {
    this.items = [];
    const geo = new THREE.PlaneGeometry(1, 1);
    for (let i = 0; i < count; i++) {
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
        color: 0xffffff, transparent: true, opacity: 0, depthWrite: false,
        blending: THREE.AdditiveBlending }));
      m.visible = false;
      scene.add(m);
      this.items.push({ mesh: m, life: 0, max: 1, vel: new THREE.Vector3(), grow: 1 });
    }
    this.next = 0;
  }
  spawn(pos, vel, color, size, life, grow = 2.2) {
    const p = this.items[this.next = (this.next + 1) % this.items.length];
    p.mesh.position.copy(pos);
    p.mesh.scale.setScalar(size);
    p.mesh.material.color.set(color);
    p.mesh.visible = true;
    p.life = p.max = life;
    p.grow = grow;
    p.vel.copy(vel);
    p.size = size;
  }
  update(dt, camera) {
    for (const p of this.items) {
      if (p.life <= 0) continue;
      p.life -= dt;
      if (p.life <= 0) { p.mesh.visible = false; p.mesh.material.opacity = 0; continue; }
      const u = p.life / p.max;
      p.mesh.position.addScaledVector(p.vel, dt);
      p.vel.multiplyScalar(1 - 1.8 * dt);
      p.mesh.scale.setScalar(p.size * (1 + (1 - u) * p.grow));
      p.mesh.material.opacity = u * 0.55;
      p.mesh.quaternion.copy(camera.quaternion);
    }
  }
}

/**
 * The slipstream, drawn round the car instead of on the HUD.
 *
 * The tow is a thing that happens to your car in the world - you are sitting in
 * a hole in the air - so it is drawn there, the way Mario Kart draws it: streaks
 * of air running past you, thickening as the tow fills and then going amber and
 * flat out when it pays. A bar in the corner said the same thing in a place you
 * cannot look at while you are two metres off somebody's bumper.
 *
 * Each streak is one camera-facing quad, and the whole trick is its
 * orientation: its long axis is the direction of flow (the car's own forward,
 * so this works upside down in a loop with no special case) and its face is
 * turned to whatever is left over pointing at the camera. Turning it to the
 * camera the ordinary way would spin the streak on screen and it would stop
 * reading as motion; leaving it unturned makes it vanish edge-on.
 *
 * They live in the car's frame rather than the world's - front to back, in a
 * ring that closes in slightly as it goes - which is what makes them read as
 * air going past *you* rather than as scenery you are going past.
 *
 * One of these belongs to your car and one to every rival, because a tow is a
 * thing that happens to a car and not a thing that happens to you: the driver
 * winding up behind your gearbox is the only person on the track who cannot see
 * it, and the whole of what makes it a move you can answer is watching somebody
 * else's air thicken. It reads whatever it is handed - position, the three axes,
 * speed and the two tow numbers - so a remote car is a car as far as this is
 * concerned, and it needed no idea that one of them is arriving over a wire.
 */
export class Draft {
  constructor(scene, count = 44) {
    this.scene = scene;
    this.items = [];
    const geo = this.geo = new THREE.PlaneGeometry(1, 1);
    for (let i = 0; i < count; i++) {
      const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
        color: 0xffffff, transparent: true, opacity: 0, depthWrite: false,
        blending: THREE.AdditiveBlending }));
      m.visible = false;
      scene.add(m);
      this.items.push({ mesh: m, t: 1, ang: 0, rad: 0, spd: 1, len: 1 });
    }
    this._m = new THREE.Matrix4();
    this._x = new THREE.Vector3();
    this._y = new THREE.Vector3();
    this._z = new THREE.Vector3();
    this._p = new THREE.Vector3();
  }

  _launch(p, boosting) {
    p.t = 0;
    // Over the top and round the sides, never underneath: the air under a car
    // is the road, and a streak drawn there is a bright bar lying on the
    // tarmac. The arc runs from just below one waistline to just below the
    // other, which is 0.64pi of the circle skipped and none of it missed.
    p.ang = -0.2 * Math.PI + Math.random() * 1.4 * Math.PI;
    // A slow curl about the car as it goes by, which is what stops the ring
    // reading as a cage of static rails. The boost curls harder.
    p.spin = (Math.random() < 0.5 ? -1 : 1) * (boosting ? 0.9 : 0.3)
             * (0.6 + Math.random() * 0.8);
    // The boost draws its air in tighter and longer: the same effect, harder.
    p.rad = (boosting ? 1.9 : 2.3) + Math.random() * (boosting ? 1.1 : 1.2);
    p.spd = 0.85 + Math.random() * 0.45;
    p.len = (boosting ? 2.4 : 1.4) + Math.random() * (boosting ? 2.0 : 1.4);
    p.hot = boosting;
    p.mesh.material.color.set(boosting ? 0xffc35a : 0xcfe9ff);
    p.mesh.visible = true;
  }

  update(car, dt, camera) {
    const T = car.T;
    const boosting = car.slipBoost > 0;
    const bf = boosting ? Math.min(1, car.slipBoost / (T.SLIP_BOOST || 1.6)) : 0;
    /*
     * One number drives the whole thing, and it is the bar this replaced:
     * while the tow fills it *is* the charge, so the air thickens around you
     * gradually and you can see the boost coming. When it pays it goes straight
     * to full and then peters out with the boost rather than being switched
     * off - the streaks already in the air finish their run either way.
     */
    const level = boosting ? Math.pow(bf, 0.45) : Math.min(1, car.slipCharge);
    const want = car.respawnIn > 0 ? 0
               : Math.round(level * this.items.length * (boosting ? 1 : 0.45));
    // Faster air the faster you are going, and much faster once it is paying.
    const flow = (boosting ? 3.2 : 1.3 + level * 0.9) * (0.55 + car.speed / 80);
    // It stops well short of the chase camera. Air blowing through the lens is
    // not a slipstream, it is a windscreen, and it hides the car it is about.
    const FRONT = 7.0, BACK = -5.5;

    let live = 0;
    for (const p of this.items) if (p.t < 1) live++;

    for (const p of this.items) {
      if (p.t >= 1) {
        if (live >= want) continue;
        this._launch(p, boosting);
        live++;
      }
      p.t += dt * flow * p.spd;
      if (p.t >= 1) { p.t = 1; p.mesh.visible = false; live--; continue; }

      /*
       * The cone. A streak comes in wide off the nose, is drawn in tight
       * against the flank as it passes the car, and spills out wide again
       * behind - which is both what air does around a body and the shape that
       * keeps it off the bodywork you are trying to look at. The waist is
       * about 1.1 units off centre at its narrowest, just outside the car.
       */
      const z = FRONT + (BACK - FRONT) * p.t;
      const r = p.rad * (1 - 0.42 * Math.sin(Math.PI * p.t));
      const a = p.ang + p.spin * p.t;
      const c = Math.cos(a), s = Math.sin(a);
      // The ring is an ellipse sitting a little high, because a car is wider
      // than it is tall and the interesting air goes over the roof.
      this._p.copy(car.pos)
        .addScaledVector(car.fwd, z)
        .addScaledVector(car.right, c * r)
        // Floored just under the sills: what the arc does not catch, this
        // does, and nothing is ever drawn through the road.
        .addScaledVector(car.up, Math.max(-0.15, s * r * 0.78) + 0.35);
      p.mesh.position.copy(this._p);

      // Long axis along the flow; face whatever is left over at the camera.
      this._y.copy(car.fwd);
      this._z.subVectors(camera.position, this._p);
      this._z.addScaledVector(this._y, -this._z.dot(this._y));
      if (this._z.lengthSq() < 1e-6) this._z.set(0, 0, 1);
      this._z.normalize();
      this._x.crossVectors(this._y, this._z);
      this._m.makeBasis(this._x, this._y, this._z);
      p.mesh.quaternion.setFromRotationMatrix(this._m);

      p.mesh.scale.set(p.hot ? 0.075 : 0.05, p.len, 1);
      /*
       * In at the front, out at the back: a streak that popped into existence
       * beside you would read as a flash rather than as air arriving. `level`
       * is on it as well, so the tail of a boost fades the air already flying.
       *
       * These are additive, so they stack: what looks discreet on its own is a
       * slab where four of them cross. The envelope is deliberately steeper
       * than a plain sine (squared) so each one is only briefly at full, which
       * is what keeps the effect a suggestion of air rather than a curtain.
       */
      const fade = Math.sin(Math.PI * p.t) ** 2;
      p.mesh.material.opacity = fade * (p.hot ? 0.5 : 0.3) * level;
    }
  }

  dispose() {
    for (const p of this.items) {
      this.scene.remove(p.mesh);
      p.mesh.material.dispose();
    }
    this.geo.dispose();
    this.items.length = 0;
  }
}

// A rival's air is thinner than your own: it is drawn at a distance, there can
// be seven of them, and the one whose tow you have to read is yours.
const RIVAL_STREAKS = 26;

// The driver's eye, in the car's own frame: at the top of the cabin, forward at
// the windscreen. It is *inside* the cabin rather than perched on the roof, and
// that is what keeps the view clear rather than something to work around - a box
// is invisible from within, so the roof, the glass and the pillars are simply not
// there from in here, and what is left is the bonnet and the road.
//
// Forward matters as much as up. Sat back at the cabin's middle, the eye is only
// 0.4 above a bonnet 1.9 wide that runs 1.9 in front of it, and the car's own
// bodywork takes a third of the screen - the view you asked for is mostly of the
// car you are sitting in. At the windscreen it is a fifth, which reads as a car
// rather than as an obstruction.
const EYE_UP = 0.98;
const EYE_FWD = 0.5;

export class Renderer {
  constructor(canvas) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(66, 1, 0.4, 2600);
    this.baseFov = 66;

    this.sun = new THREE.DirectionalLight(0xffffff, 1.65);
    this.lightDir = new THREE.Vector3(0.45, 1, 0.32).normalize().multiplyScalar(140);
    this.sun.position.copy(this.lightDir);
    this.scene.add(this.sun);
    this.hemi = new THREE.HemisphereLight(0xffffff, 0x5a6172, 0.72);
    this.scene.add(this.hemi);

    this.sky = null;
    this.particles = new Particles(this.scene);
    this.draftFx = new Draft(this.scene);
    this.trackGroup = null;

    // camera state, all smoothed
    this.camPos = new THREE.Vector3();
    this.camUp = new THREE.Vector3(0, 1, 0);
    this.camLook = new THREE.Vector3();
    this.camFwd = new THREE.Vector3(0, 0, -1);
    this.shake = 0;
    this.started = false;
    // Which of the views the camera is in, so that follow() can tell a change of
    // view from a frame of the same one and cut rather than sweep.
    this.mode = 'chase';

    this._onResize = () => this.resize();
    window.addEventListener('resize', this._onResize);
    this.resize();
  }

  resize() {
    const c = this.renderer.domElement;
    const w = c.clientWidth || window.innerWidth;
    const h = c.clientHeight || window.innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / Math.max(1, h);
    this.camera.updateProjectionMatrix();
  }

  setTrack(built) {
    if (this.trackGroup) {
      this.scene.remove(this.trackGroup);
      this.trackGroup.traverse(o => { if (o.geometry) o.geometry.dispose(); });
    }
    this.trackGroup = built.group;
    this.scene.add(built.group);

    const pal = built.palette;
    const spec = (pal.sky && pal.sky.stops) ? pal.sky : null;
    // Fog is the haze the world dissolves into, so it has to be the colour of
    // the sky at the horizon or the join shows.
    this.scene.fog = new THREE.Fog(spec ? spec.fog : pal.fog,
                                   spec && spec.fogNear != null ? spec.fogNear : 190,
                                   spec && spec.fogFar != null ? spec.fogFar : 900);
    this.scene.background = new THREE.Color(spec ? spec.fog : pal.sky);
    if (this.sky) {
      this.scene.remove(this.sky);
      this.sky.traverse(o => { if (o.geometry) o.geometry.dispose(); });
    }
    this.sky = makeSky(pal);
    this.scene.add(this.sky);

    // Key light comes from the sun's own azimuth so the warm side of every
    // surface agrees with the warm side of the sky. Its *elevation* is the one
    // honest lie in here: a sun actually on the horizon lights nothing, so the
    // light is lifted well above where the disc is drawn.
    const L = spec && spec.light;
    this.sun.color.set(L ? L.color : 0xffffff);
    this.sun.intensity = L && L.intensity != null ? L.intensity : 1.65;
    this.lightDir.set(...(L ? L.dir : [0.45, 1, 0.32])).normalize().multiplyScalar(140);
    const H = spec && spec.hemi;
    this.hemi.color.set(H ? H.sky : 0xffffff);
    this.hemi.groundColor.set(H ? H.ground : 0x5a6172);
    this.hemi.intensity = H && H.intensity != null ? H.intensity : 0.72;
    this.started = false;
  }

  /**
   * Chase camera. `car` is the local Car; dt is real seconds.
   *
   * `opts.first` and `opts.rear` are the two views you can hold a key for, and
   * they are two questions rather than a list of three cameras: `first` is where
   * you are sitting and `rear` is which way you are looking. Holding both is
   * therefore a glance over your shoulder from the driver's seat, which is the
   * only thing both keys at once could sensibly mean.
   */
  follow(car, dt, opts = {}) {
    const speed = car.speed;
    const first = !!opts.first;
    const dir = opts.rear ? -1 : 1;
    const back = 8.2 + Math.min(3.4, speed * 0.075);
    const up = 3.2 + Math.min(1.1, speed * 0.02);

    // Smooth the frame we orbit in, not the final position: that is what keeps a
    // loop from throwing the camera around while still following the car over it.
    // It is the *car's* frame, which is why it is the same frame in all four
    // views and why a view can be taken up mid-loop without the horizon moving.
    const kf = 1 - Math.exp(-(car.grounded ? 9 : 4.5) * dt);
    const ku = 1 - Math.exp(-(car.grounded ? 7 : 3.0) * dt);
    this.camFwd.lerp(car.fwd, kf).normalize();
    this.camUp.lerp(car.up, ku).normalize();

    // Looking behind you moves the chase camera to the far side of the car
    // rather than turning it where it stands: reversed in place it would be
    // pointing away from the one thing that has to stay in the frame, which is
    // your own car - it is what everything back there is closing on. The seat
    // does not move when you look back out of it, so the driver's does not.
    const want = new THREE.Vector3().copy(car.pos);
    if (first) {
      want.addScaledVector(this.camFwd, EYE_FWD).addScaledVector(this.camUp, EYE_UP);
    } else {
      want.addScaledVector(this.camFwd, -back * dir).addScaledVector(this.camUp, up);
    }

    const look = new THREE.Vector3().copy(first ? want : car.pos)
      .addScaledVector(this.camFwd, (7 + speed * 0.16) * dir)
      .addScaledVector(this.camUp, first ? 0 : 1.1);

    // Two reasons to put the camera where it goes instead of easing it there.
    // Changing view is a cut: the views are metres apart, and easing between
    // them drags the camera through the car and out through the road for a
    // glance that is over before it arrives. And the driver's seat is a fixed
    // point in the car, so it cannot trail the car - the smoothing below sits a
    // couple of metres behind its target at speed, which from in here would be
    // a couple of metres behind the driver.
    const view = (first ? 'first' : 'chase') + (dir < 0 ? '-rear' : '');
    const cut = !this.started || view !== this.mode;
    this.mode = view;
    this.started = true;
    if (cut || first) {
      this.camPos.copy(want);
      this.camLook.copy(look);
    } else {
      // Track the target position hard enough to feel connected, softly enough to
      // absorb kerbs. Faster = tighter, so high speed does not feel laggy.
      this.camPos.lerp(want, 1 - Math.exp(-(11 + speed * 0.16) * dt));
      this.camLook.lerp(look, 1 - Math.exp(-12 * dt));
    }

    this.camera.position.copy(this.camPos);
    if (this.shake > 0) {
      this.shake = Math.max(0, this.shake - dt * 2.4);
      const a = this.shake * 0.22;
      this.camera.position.x += (Math.random() - 0.5) * a;
      this.camera.position.y += (Math.random() - 0.5) * a;
      this.camera.position.z += (Math.random() - 0.5) * a;
    }
    this.camera.up.copy(this.camUp);
    this.camera.lookAt(this.camLook);

    // A little FOV with speed - cheap, and it does a lot. A slipstream boost
    // adds a punch of its own on top, which is most of what makes it feel like
    // more speed rather than a different number.
    const fov = this.baseFov + Math.min(13, speed * 0.16) + (car.slipBoost > 0 ? 7 : 0);
    if (Math.abs(this.camera.fov - fov) > 0.05) {
      this.camera.fov += (fov - this.camera.fov) * (1 - Math.exp(-6 * dt));
      this.camera.updateProjectionMatrix();
    }

    if (this.sky) this.sky.position.copy(this.camera.position);
    // Keep the sun near the action so the whole track is lit the same way.
    this.sun.position.copy(car.pos).add(this.lightDir);
    this.sun.target.position.copy(car.pos);
    this.sun.target.updateMatrixWorld();
  }

  kick(amount) { this.shake = Math.min(2.2, this.shake + amount); }

  /**
   * The air round a car while its tow fills and while it pays out.
   *
   * Yours by default; a rival passes the effect it owns, since the streaks have
   * to fly their own run out and cannot be shared between cars.
   */
  draft(car, dt, fx) { (fx || this.draftFx).update(car, dt, this.camera); }

  /** A tow effect for somebody else's car, to be disposed of with it. */
  makeDraft() { return new Draft(this.scene, RIVAL_STREAKS); }

  smoke(pos, vel, kind) {
    if (kind === 'spark') {
      for (let i = 0; i < 5; i++) {
        this.particles.spawn(pos, new THREE.Vector3(
          (Math.random() - 0.5) * 9, Math.random() * 5 + 1, (Math.random() - 0.5) * 9),
          0xffd27a, 0.3, 0.28, 1.2);
      }
    } else if (kind === 'dust') {
      this.particles.spawn(pos, vel, 0xd8cdb8, 0.9, 0.5);
    } else {
      this.particles.spawn(pos, vel, 0xdfe6ef, 0.75, 0.42);
    }
  }

  render(dt) {
    this.particles.update(dt, this.camera);
    this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    window.removeEventListener('resize', this._onResize);
    this.renderer.dispose();
  }
}

// ---------------------------------------------------------------------------
// Sky
// ---------------------------------------------------------------------------
//
// A sky here is three things, all of them vertex colours and flat quads - no
// shader, no texture, nothing loaded:
//
//   1. a dome whose colour is a list of stops down the vertical, plus a warm
//      glow smeared around the sun's *azimuth* rather than evenly round the
//      horizon. That last part is what makes a sunrise read as a sunrise: the
//      sky is only on fire in the direction the sun is coming from.
//   2. a sun, drawn as one sprite with a hot core and a soft halo.
//
// There is deliberately no cloud up here. Boxes seen from below at a shallow
// angle read as pale rectangles however they are shaded; cloud only works when
// you look *down* on it, which is what `cloudDeck` in trackmesh.js is for.
//
// Palettes without a `sky` spec fall back to the plain two-colour dome.

const R_SKY = 1800;

/** Direction the sun sits in, from an azimuth and an elevation in radians. */
function sunDir(az, el) {
  return new THREE.Vector3(Math.cos(el) * Math.sin(az), Math.sin(el),
                           Math.cos(el) * Math.cos(az));
}

/** Colour at height `u` (0 straight down, 0.5 horizon, 1 straight up). */
function sampleStops(stops, u) {
  if (u <= stops[0][0]) return new THREE.Color(stops[0][1]);
  const last = stops[stops.length - 1];
  if (u >= last[0]) return new THREE.Color(last[1]);
  for (let i = 1; i < stops.length; i++) {
    if (u <= stops[i][0]) {
      const a = stops[i - 1], b = stops[i];
      const f = (u - a[0]) / Math.max(1e-6, b[0] - a[0]);
      return new THREE.Color(a[1]).lerp(new THREE.Color(b[1]), f);
    }
  }
  return new THREE.Color(last[1]);
}

function skyDome(spec) {
  // Enough segments that the gradient and the glow are smooth; at ~1200 verts
  // this is still nothing.
  const geo = new THREE.SphereGeometry(R_SKY, 48, 26);
  const pos = geo.attributes.position;
  const colors = [];
  const glow = spec.glow != null ? new THREE.Color(spec.glow) : null;
  const strength = spec.glowStrength != null ? spec.glowStrength : 0.8;
  const dir = spec.sun ? sunDir(spec.sun.az, spec.sun.el) : null;
  const sunXZ = dir ? new THREE.Vector3(dir.x, 0, dir.z).normalize() : null;
  const v = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.set(pos.getX(i), pos.getY(i), pos.getZ(i));
    const u = Math.max(0, Math.min(1, v.y / R_SKY * 0.5 + 0.5));
    const c = sampleStops(spec.stops, u);
    if (glow && dir) {
      let g;
      if (spec.glowMode === 'radial') {
        // A tight halo around wherever the sun actually is. This is the one you
        // want for a sun up in the sky - the horizon smear below is only right
        // when the disc is sitting on the horizon.
        const len = v.length() || 1;
        const d = (v.x * dir.x + v.y * dir.y + v.z * dir.z) / len;
        g = Math.pow(Math.max(0, d), spec.glowFocus != null ? spec.glowFocus : 8);
      } else {
        // How much this direction faces the sun's bearing, sharpened so the glow
        // is a wedge rather than a wash, and faded out away from the horizon.
        const h = Math.hypot(v.x, v.z) || 1;
        const facing = Math.max(0, (v.x / h) * sunXZ.x + (v.z / h) * sunXZ.z);
        const band = Math.exp(-Math.pow((u - 0.5) * 5.2, 2));
        g = Math.pow(facing, 3.2) * band;
      }
      c.lerp(glow, g * strength);
    }
    colors.push(c.r, c.g, c.b);
  }
  geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    vertexColors: true, side: THREE.BackSide, depthWrite: false, fog: false }));
  mesh.renderOrder = -1;
  return mesh;
}

/** One sprite: a hot core fading into a wide halo. */
function sunSprite(sun) {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  const col = new THREE.Color(sun.color);
  const rgb = (a) => `rgba(${Math.round(col.r * 255)},${Math.round(col.g * 255)},` +
                     `${Math.round(col.b * 255)},${a})`;
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0.00, 'rgba(255,255,255,1)');
  grad.addColorStop(0.13, rgb(1));
  grad.addColorStop(0.20, rgb(0.72));
  grad.addColorStop(0.38, rgb(0.26));
  grad.addColorStop(0.66, rgb(0.07));
  grad.addColorStop(1.00, rgb(0));
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  const spr = new THREE.Sprite(new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(c), transparent: true, fog: false,
    depthWrite: false, blending: THREE.AdditiveBlending }));
  spr.scale.setScalar(sun.size || 420);
  spr.position.copy(sunDir(sun.az, sun.el)).multiplyScalar(R_SKY * 0.93);
  return spr;
}

/**
 * Stars, as one Points cloud just inside the dome.
 *
 * sizeAttenuation is off so a star is a fixed number of pixels however far away
 * it is - which is both what a star does and the only way it stays visible at
 * this distance. Biased to the upper hemisphere, because the lower half of the
 * dome is under the horizon on a track that has one, and looks wrong on one
 * that does not.
 */
function starfield(cfg) {
  const rnd = mulberry(cfg.seed != null ? cfg.seed : 5);
  const n = cfg.count != null ? cfg.count : 800;
  const pos = [], col = [];
  const warm = new THREE.Color(0xffe6c4), cold = new THREE.Color(0xcfe0ff);
  const white = new THREE.Color(0xffffff);
  for (let i = 0; i < n; i++) {
    const y = -0.12 + rnd() * 1.12;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const a = rnd() * Math.PI * 2;
    const d = R_SKY * 0.97;
    pos.push(Math.cos(a) * r * d, y * d, Math.sin(a) * r * d);
    // a handful of coloured ones, the rest white at varying brightness
    const t = rnd();
    const c = (t < 0.08 ? warm : t < 0.18 ? cold : white).clone()
      .multiplyScalar(0.45 + rnd() * 0.55);
    col.push(c.r, c.g, c.b);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  const m = new THREE.Points(geo, new THREE.PointsMaterial({
    size: cfg.size != null ? cfg.size : 2.2, sizeAttenuation: false,
    vertexColors: true, transparent: true, depthWrite: false, fog: false }));
  m.renderOrder = -1;
  return m;
}

function makeSky(pal) {
  const group = new THREE.Group();
  const spec = pal.sky && pal.sky.stops ? pal.sky : null;
  if (!spec) {
    // legacy two-colour dome, for palettes that have not been art-directed yet
    group.add(skyDome({ stops: [[0, pal.fog], [0.5, pal.fog], [1, pal.sky]] }));
    return group;
  }
  group.add(skyDome(spec));
  if (spec.stars) group.add(starfield(spec.stars));
  if (spec.sun) group.add(sunSprite(spec.sun));
  return group;
}
