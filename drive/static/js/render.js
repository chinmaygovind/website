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
    // The *style* is what turns rims on, not the colour: `stock` is the single
    // plain cylinder the wheel has always been, and picking a colour for a wheel
    // that has no rim face should not quietly grow one. Colour only tints.
    rim: new THREE.Color(spec.rim || 0xc9ced6),
    stripe: spec.stripe ? new THREE.Color(spec.stripe) : trim.clone(),
    finish: spec.finish || 'matte',
    livery: spec.livery || 'none',
    rimStyle: spec.rim_style || 'stock',
    twoTone: !!spec.two_tone,
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
const FINISH = {
  matte:    null,
  gloss:    { shininess: 55,  specular: 0x555555 },
  metallic: { shininess: 130, specular: 0xa8a8a8 },
  pearl:    { shininess: 85,  specular: 0xd8d0e8 },
};

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
  if (style === 'dish') {
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

/**
 * Every stripe on the car, as one `MeshBuf`, or null for a bare one.
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
function liveryMesh(L) {
  if (!L.livery || L.livery === 'none') return null;
  const buf = new MeshBuf();
  const S = L.stripe.getHex(), B = L.body.getHex();
  const LIFT = 0.01;
  // The two panels a stripe can lie on, from the chassis boxes above.
  const DECK = 0.555 + LIFT, ROOF = 1.03 + LIFT;
  // Wound anticlockwise seen from above, so `computeVertexNormals` gives these
  // an upward normal. The obvious order is the other one and it is silently
  // wrong: the decal still draws, and it is lit from underneath, so a bright
  // stripe comes out as a dark smear on the one surface the sun is hitting.
  const deck = (x0, x1, z0, z1, color) => buf.quad(
    [x0, DECK, z0], [x0, DECK, z1], [x1, DECK, z1], [x1, DECK, z0], color);
  const roof = (x0, x1, z0, z1, color) => buf.quad(
    [x0, ROOF, z0], [x0, ROOF, z1], [x1, ROOF, z1], [x1, ROOF, z0], color);

  switch (L.livery) {
    case 'centre':
      deck(-0.17, 0.17, -1.7, 1.7, S); roof(-0.17, 0.17, -0.7, 0.9, S); break;
    case 'twin':
      for (const x of [-0.42, 0.14]) {
        deck(x, x + 0.28, -1.7, 1.7, S); roof(x, x + 0.28, -0.7, 0.9, S);
      }
      break;
    case 'band':
      deck(-0.45, 0.45, -1.7, 1.7, S); roof(-0.45, 0.45, -0.7, 0.9, S); break;
    case 'hoop':                          // across the car rather than along it
      deck(-0.94, 0.94, 0.35, 0.85, S); roof(-0.76, 0.76, -0.7, 0.9, S); break;
    case 'halves':                        // the nose half, so it reads head on
      deck(-0.94, 0.94, -1.7, 0.05, S); break;
    case 'pinstripe':                     // gated: two hairlines, deliberately fine
      for (const x of [-0.5, 0.44]) {
        deck(x, x + 0.06, -1.7, 1.7, S); roof(x, x + 0.06, -0.7, 0.9, S);
      }
      break;
    case 'fade': {
      // Baked into the vertices: nose in the stripe colour, tail in the body's.
      const N = 10;
      for (let i = 0; i < N; i++) {
        const z0 = -1.7 + (3.4 * i) / N, z1 = -1.7 + (3.4 * (i + 1)) / N;
        const c = new THREE.Color(S).lerp(new THREE.Color(B), i / (N - 1));
        deck(-0.94, 0.94, z0, z1, c.getHex());
      }
      break;
    }
    default: return null;
  }
  return buf;
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
                                spec || {}, extra);
      const m = spec ? new THREE.MeshPhongMaterial(opt)
                     : new THREE.MeshLambertMaterial(opt);
      this._mats.push(m);
      return m;
    };

    const bodyMat = mat(col, {}, true);
    const darkMat = mat(L.trim, {}, true);
    // Two-tone puts the cabin in the trim colour. One material either way, so it
    // costs nothing but a choice of which one the roof gets.
    const cabinMat = L.twoTone ? darkMat : bodyMat;
    const glassMat = mat(L.glass);
    const tyreMat = mat(0x1c1f26);

    // chassis: a wedge-ish stack of boxes, Polytrack-simple
    const lower = new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.55, 3.4), bodyMat);
    lower.position.y = 0.28;
    this.body.add(lower);
    // The cabin is shorter than it was, because the front half of it is now the
    // windscreen rather than a wall.
    const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.55, 0.5, 1.05), cabinMat);
    cabin.position.set(0, 0.78, 0.375);
    this.body.add(cabin);
    // **A raked windscreen, and this is the one that mattered.** The cabin used
    // to be a plain box on a plain slab, so the front of it was a dead-vertical
    // wall rising 0.475 straight out of the bonnet - no car has that, and it was
    // the single most jarring thing about the model. This is a slab lying along
    // the line from the deck at z = -0.75 up to the roof at z = -0.15: a rise of
    // 0.475 over 0.6, which is about 52 degrees off vertical.
    //
    // It replaces the old glass box rather than joining it, so the cabin costs
    // no more than it did. That box was 1.42 wide inside a 1.55 cabin, so its
    // sides were buried and the only part of it anybody ever saw *was* the
    // windscreen face - which is exactly what this is, at the right angle.
    // **Positioned by its top face, not its centre.** A slab has thickness, and
    // the thing that has to land on the line from the deck to the roof is the
    // pane you can see - so the centre sits half a thickness *under* that line,
    // along its own normal. Put the centre on the line instead and the leading
    // edge stands an eighth of a unit proud of the bonnet, which draws a dark
    // fin sticking up out of the paint rather than a windscreen.
    const screen = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.34, 0.765), glassMat);
    screen.position.set(0, 0.656, -0.345);
    screen.rotation.x = -0.667;
    this.body.add(screen);
    // --- the front ---------------------------------------------------------
    // The whole front used to be one box: a 1.7-wide slab in the trim colour,
    // sitting below the body's front face and inset 0.1 from each flank, with
    // nothing above it - a bumper somebody had bolted to a rectangle. It is one
    // box again now, but the *body's own* box: same colour, **exactly the body's
    // width**, and sloping down out of the bonnet rather than hanging off it.
    //
    // Three attempts' worth of things not to do again:
    //
    // * **Not the trim colour.** Trim is what says "this part is an attachment",
    //   and the nose of a car is not one.
    // * **Not inset.** 1.84 inside a 1.9 body leaves a 0.03 step down each
    //   flank, which is enough to read as a separate part from any angle. Flush
    //   means flush.
    // * **Not with a blade in front of it.** A splitter protruding past the nose
    //   is the opposite of flush - it puts a second silhouette in front of the
    //   first. The record badge sits along that bottom edge when it is earned,
    //   which is the only thing that has any business sticking out down there.
    //
    // The tilt is `rotation.x`, and it is **negative**: three.js rotates
    // `y' = y cos - z sin` about X, and the car points at -Z, so a negative
    // angle is what drops the nose. At 0.30 the tip sits 0.15 below the bonnet,
    // which is a nose; at the 0.16 it started on the drop was 0.065 and the
    // slope was invisible, so the flanks were the only thing saying anything had
    // changed - and they were saying "there is a step here".
    const snout = new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.42, 0.50), bodyMat);
    snout.position.set(0, 0.28, -1.95);
    snout.rotation.x = -0.30;
    this.body.add(snout);
    // Headlights: two lenses, one mesh, one material, and **the colour is not
    // yours**. The reasoning is the brake lamps' own, a screen down: the lamps
    // are the only thing another driver reads off your car, which is why the
    // amber drift state was taken out again. A headlight somebody can paint
    // black is the same mistake with a settings page in front of it.
    //
    // Unlit and built by hand rather than through `mat()`, for the same reason
    // the brake lamps are: `mat()` makes a lit material and takes the finish, so
    // a lens would go glossy with the paint and darken on the side away from the
    // sun. A lamp is a lamp at every angle. One `MeshBuf` rather than two meshes
    // because, unlike the brake lamps, these never change independently.
    // On the sloped face, so they sit a little further back than a flat nose
    // would want them - the face at this height is at z = -2.20, and these poke
    // out the same 0.08 the brake lamps do at the other end.
    const lamps = new MeshBuf();
    for (const s of [-1, 1]) lamps.box(s * 0.53, 0.30, -2.23, 0.23, 0.065, 0.05, 0xffeccc);
    const headMat = new THREE.MeshBasicMaterial({
      color: 0xffeccc, transparent: ghost, opacity: this._solid });
    this._mats.push(headMat);
    this.body.add(lamps.toMesh(headMat));
    // --- the rear, unchanged ------------------------------------------------
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
    const hasRim = L.rimStyle && L.rimStyle !== 'stock';
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

    // The livery, as one mesh however many stripes it is made of - and the same
    // trick pays for `fade`, which is a colour ramp baked straight into the
    // vertices rather than a texture the rest of this renderer does not have.
    const deco = liveryMesh(L);
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
    // The record badge: a flash across the nose, and the name above the car in
    // the same green. Green because that is the colour the record already wears
    // on the medals card - "not a medal and cannot be won" - so the badge needs
    // no explaining to anybody who has read that card.
    //
    // The plate is most of the point. A decal on a low-poly car is invisible at
    // the distance you actually see rivals from; the name over it is legible
    // from anywhere, and it is what a rival reads when they are deciding whether
    // to try the move.
    if (L.badge === 'laurel') {
      // **On the nose, not in it.** It used to sit at z -1.86, which was clear
      // air in front of the old flat slab and is the middle of the snout now, so
      // rebuilding the front drew the badge entirely inside the bodywork where
      // no angle could see it. Nothing errored and nothing looked wrong; it was
      // simply not there.
      //
      // It runs along the bottom edge of the nose, which is the one line on the
      // front that nothing else uses and the only place anything is allowed to
      // stand proud of the bodywork - the splitter that used to live there was
      // taken out precisely because it was not flush.
      const flash = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.07, 0.06),
                                   mat(RECORD_GREEN));
      flash.position.set(0, 0.12, -2.16);
      this.body.add(flash);
    }
    this.plateColor = L.badge === 'laurel'
      ? '#' + new THREE.Color(RECORD_GREEN).getHexString()
      : '#' + col.getHexString();

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
