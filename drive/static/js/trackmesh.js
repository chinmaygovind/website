// Turns a track's block list into (a) one merged flat-shaded mesh and (b) the
// triangle soup the car actually drives on.
//
// The important idea here: **the collision surface is the render surface.** Every
// driveable triangle that goes into the mesh also goes into a spatial hash, and
// the physics does closest-point queries against it. That means ramps, banked
// arcs, loops, kicker lips and bridges all work through one code path with no
// per-block special cases in the car code, and nothing can ever look solid but
// not be (or vice versa). The cost is a couple of thousand triangles per track,
// which is nothing.
//
// Coordinates: cell (gx,gy,gz) has its centre at (gx*CELL, gy*LEVEL, gz*CELL).
// A block's rotation r maps its local +X to world DIRS[r]; local +Z is always the
// road's right-hand side. Surface height runs from p.gy*LEVEL at the block's
// local -X edge to (p.gy+dy)*LEVEL at its +X edge, which is the whole elevation
// model - a ramp is just a road with dy.

import * as THREE from './vendor/three.module.js';

export const KIND = { ROAD: 0, WALL: 1, BOOST: 2, OFFROAD: 3 };

const PALETTES = {
  sunrise:  { road: 0x59606e, kerb: 0xf2f2f2, kerb2: 0xe8453c, ground: 0x6fbf5f, sky: 0xa9d8ef, fog: 0xbfe0f0, rail: 0xf5f5f5, prop: 0x3f8f4f, deco: 0xf2c94c },
  park:     { road: 0x565d6b, kerb: 0xffffff, kerb2: 0x3d8bfd, ground: 0x63b866, sky: 0x9ed2f0, fog: 0xb9dcee, rail: 0xf0f0f0, prop: 0x347a3c, deco: 0xf2994a },
  skyline:  { road: 0x4d5464, kerb: 0xf6f6f6, kerb2: 0x56ccf2, ground: 0x4a6b8a, sky: 0x7fb6dd, fog: 0x9ec9e6, rail: 0xe9f4ff, prop: 0x6e7f95, deco: 0x56ccf2 },
  lagoon:   { road: 0x515a68, kerb: 0xfdfdfd, kerb2: 0x27ae60, ground: 0x3aa6a0, sky: 0x8fdce6, fog: 0xb6e8ec, rail: 0xf3fffe, prop: 0x1f8f7a, deco: 0x27ae60 },
  heights:  { road: 0x4f5460, kerb: 0xf4f4f4, kerb2: 0xf2994a, ground: 0x7a6a52, sky: 0xf0c9a0, fog: 0xf3d9bd, rail: 0xfff2e2, prop: 0x8a7358, deco: 0xf2994a },
  city:     { road: 0x4a4f5c, kerb: 0xf7f7f7, kerb2: 0xf2c94c, ground: 0x5c6070, sky: 0x8ea9c9, fog: 0xa9bed6, rail: 0xf2f4f7, prop: 0x6b7180, deco: 0xf2c94c },
  spiral:   { road: 0x525869, kerb: 0xfafafa, kerb2: 0xbb6bd9, ground: 0x5a5570, sky: 0xb9a6e0, fog: 0xd0c4ec, rail: 0xf6f0ff, prop: 0x6d6488, deco: 0xbb6bd9 },
  gauntlet: { road: 0x474c58, kerb: 0xf2f2f2, kerb2: 0xe8453c, ground: 0x3d4250, sky: 0x6f7f9c, fog: 0x8d9ab3, rail: 0xf7f7f7, prop: 0x555c6c, deco: 0xe8453c },
};

const DIRS = [[1, 0], [0, 1], [-1, 0], [0, -1]];

// Rotate a local offset into world space. r quarter-turns about Y, chosen so
// local +X lands on DIRS[r] (see the module comment).
function rot(r, x, y, z) {
  switch (r & 3) {
    case 0: return [x, y, z];
    case 1: return [-z, y, x];
    case 2: return [-x, y, -z];
    default: return [z, y, -x];
  }
}

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

class MeshBuf {
  constructor() { this.pos = []; this.col = []; }
  tri(a, b, c, color) {
    this.pos.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
    const r = ((color >> 16) & 255) / 255, g = ((color >> 8) & 255) / 255, bl = (color & 255) / 255;
    for (let i = 0; i < 3; i++) this.col.push(r, g, bl);
  }
  quad(a, b, c, d, color) { this.tri(a, b, c, color); this.tri(a, c, d, color); }
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
  toMesh(material) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(this.col, 3));
    g.computeVertexNormals();
    return new THREE.Mesh(g, material);
  }
}

export function buildTrack(track, T) {
  const CELL = T.CELL, LEVEL = T.LEVEL, h = CELL / 2;
  const pal = palette(track);
  const group = new THREE.Group();
  const col = new Collider(CELL);
  const solid = new MeshBuf();     // flat-shaded, receives light
  const bright = new MeshBuf();    // unlit accents: kerbs, gates, boosters
  const gates = [];
  let minY = Infinity, maxY = -Infinity;
  const bbox = { x0: Infinity, x1: -Infinity, z0: Infinity, z1: -Infinity };

  const W = (b, lx, ly, lz) => {
    const [x, y, z] = rot(b.r, lx, ly, lz);
    return [b.p[0] * CELL + x, b.p[1] * LEVEL + y, b.p[2] * CELL + z];
  };

  function note(p) {
    minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]);
    bbox.x0 = Math.min(bbox.x0, p[0]); bbox.x1 = Math.max(bbox.x1, p[0]);
    bbox.z0 = Math.min(bbox.z0, p[2]); bbox.z1 = Math.max(bbox.z1, p[2]);
  }

  // Road surface + the slab of "tarmac" under it so the track reads as solid
  // when you see it edge-on or from below.
  function surfaceQuad(a, b, c, d, kind, color) {
    col.addQuad(a, b, c, d, kind);
    solid.quad(a, b, c, d, color);
    [a, b, c, d].forEach(note);
  }

  const THICK = 0.9;
  function underside(a, b, c, d) {
    const lower = [a, b, c, d].map(p => [p[0], p[1] - THICK, p[2]]);
    // bottom face (reverse winding) + four sides
    solid.quad(lower[3], lower[2], lower[1], lower[0], shade(pal.road, -0.45));
    const edges = [[0, 1], [1, 2], [2, 3], [3, 0]];
    for (const [i, j] of edges) {
      solid.quad([a, b, c, d][i], [a, b, c, d][j], lower[j], lower[i], shade(pal.road, -0.25));
    }
  }

  function kerb(p0, p1, color) {
    // a low stripe along an edge, drawn slightly above the road to avoid z-fight
    const lift = 0.06, wide = 0.55;
    const dx = p1[0] - p0[0], dz = p1[2] - p0[2];
    const len = Math.hypot(dx, dz) || 1;
    const sx = -dz / len * wide, sz = dx / len * wide;
    bright.quad(
      [p0[0], p0[1] + lift, p0[2]], [p1[0], p1[1] + lift, p1[2]],
      [p1[0] + sx, p1[1] + lift, p1[2] + sz], [p0[0] + sx, p0[1] + lift, p0[2] + sz], color);
  }

  // Walls get ONE collision quad, not two. The wall query derives its push-out
  // direction from the closest point on the triangle rather than from the stored
  // normal, so a single-sided quad stops a car arriving from either side. Adding
  // the back face as well used to make every contact fire twice with opposing
  // normals, which cancelled the car's velocity and scrubbed its speed twice per
  // step - it is what made loops with rails undrivable. The *mesh* still gets
  // both faces, so nothing looks hollow.
  function wallStrip(p0, p1, height, color) {
    const a = [p0[0], p0[1], p0[2]], b = [p1[0], p1[1], p1[2]];
    const at = [a[0], a[1] + height, a[2]], bt = [b[0], b[1] + height, b[2]];
    col.addQuad(a, b, bt, at, KIND.WALL);
    solid.quad(a, b, bt, at, color);
    solid.quad(at, bt, b, a, color);
  }

  // Same as wallStrip but offset along a supplied normal instead of world up,
  // so a rail on the inverted part of a loop still points away from the road.
  function wallStripN(p0, p1, n0, n1, height, color) {
    const at = [p0[0] + n0[0] * height, p0[1] + n0[1] * height, p0[2] + n0[2] * height];
    const bt = [p1[0] + n1[0] * height, p1[1] + n1[1] * height, p1[2] + n1[2] * height];
    col.addQuad(p0, p1, bt, at, KIND.WALL);
    solid.quad(p0, p1, bt, at, color);
    solid.quad(at, bt, p1, p0, color);
  }

  const RAIL_H = 1.15;

  for (const b of track.blocks) {
    const dyH = (b.dy || 0) * LEVEL;
    const t = b.t;

    if (t === 'road' || t === 'kick') {
      // corners in local space: -X edge at y 0, +X edge at y dyH
      const A = W(b, -h, 0, -h), B = W(b, -h, 0, h);
      const C = W(b, h, dyH, h), D = W(b, h, dyH, -h);
      const boost = !!b.boost;
      surfaceQuad(A, B, C, D, boost ? KIND.BOOST : KIND.ROAD,
                  boost ? shade(pal.deco, -0.15) : pal.road);
      underside(A, B, C, D);
      // kerbs down both sides
      kerb(A, D, pal.kerb);
      kerb(C, B, pal.kerb2);
      if (boost) {
        // chevrons on the pad
        for (let i = 0; i < 3; i++) {
          const f = -h + (i + 0.6) * (CELL / 3.4);
          const y0 = (f + h) / CELL * dyH;
          const p0 = W(b, f, y0 + 0.08, -h * 0.7), p1 = W(b, f + 1.5, y0 + 0.08, 0);
          const p2 = W(b, f, y0 + 0.08, h * 0.7), p3 = W(b, f - 0.5, y0 + 0.08, 0);
          bright.quad(p0, p1, p2, p3, 0xffffff);
        }
      }
      if (b.w) addSideRails(b, b.w, A, B, C, D);
      if (t === 'kick') {
        // paint the launch edge so you can see exactly where the road stops
        const L1 = W(b, h, dyH, -h), L2 = W(b, h, dyH, h);
        solid.quad(L1, L2, [L2[0], L2[1] - THICK, L2[2]], [L1[0], L1[1] - THICK, L1[2]],
                   shade(pal.deco, -0.1));
        kerb(L1, L2, pal.deco);
      }
      if (b.gate) addGate(b, dyH);
      if (b.over) addPiers(b, dyH);

    } else if (t === 'turn') {
      // A quarter disc of radius CELL pivoted on the inside corner. Both the
      // entry edge and the exit edge are then fully road (their far ends are
      // exactly one radius from the pivot), so it joins the straights cleanly,
      // and the opposite corner falls outside the arc and is not road at all.
      const side = b.d === 'r' ? 1 : -1;
      const pvx = -h, pvz = side * h;
      const SEG = 12, R = CELL;
      const P = W(b, pvx, 0, pvz);
      const arc = [];
      for (let i = 0; i <= SEG; i++) {
        const a = (Math.PI / 2) * (i / SEG);
        arc.push(W(b, pvx + Math.cos(a) * R, 0, pvz - side * Math.sin(a) * R));
      }
      for (let i = 0; i < SEG; i++) {
        const A2 = arc[i], B2 = arc[i + 1];
        // A right-hand turn sweeps clockwise in XZ, so its fan winds the other
        // way to keep every road normal pointing up.
        if (side > 0) { col.add(P, B2, A2, KIND.ROAD); solid.tri(P, B2, A2, pal.road); }
        else { col.add(P, A2, B2, KIND.ROAD); solid.tri(P, A2, B2, pal.road); }
        kerb(A2, B2, i % 2 ? pal.kerb : pal.kerb2);
        note(A2);
      }
      // underside: the same fan flipped, plus a skirt around the arc
      for (let i = 0; i < SEG; i++) {
        const A2 = arc[i], B2 = arc[i + 1];
        const lp = [P[0], P[1] - THICK, P[2]];
        const la = [A2[0], A2[1] - THICK, A2[2]], lb = [B2[0], B2[1] - THICK, B2[2]];
        if (side > 0) solid.tri(lp, la, lb, shade(pal.road, -0.45));
        else solid.tri(lp, lb, la, shade(pal.road, -0.45));
        solid.quad(A2, B2, lb, la, shade(pal.road, -0.25));
      }
      if (b.w) {
        for (let i = 0; i < SEG; i++) wallStrip(arc[i], arc[i + 1], RAIL_H, pal.rail);
      }

    } else if (t === 'loop') {
      buildLoop(b);

    } else if (t === 'wall') {
      const A = W(b, -h, 0, -h), B = W(b, -h, 0, h);
      wallStrip(A, B, RAIL_H * 2, pal.rail);
    }
  }

  function addSideRails(b, which, A, B, C, D) {
    if (which.includes('l')) wallStrip(A, D, RAIL_H, pal.rail);   // local -Z side
    if (which.includes('r')) wallStrip(B, C, RAIL_H, pal.rail);
  }

  function addPiers(b, dyH) {
    const y = b.p[1] * LEVEL + dyH / 2;
    const drop = y - (track.ground != null ? track.ground * LEVEL : y - 14);
    for (const s of [-1, 1]) {
      const p = W(b, 0, 0, s * (h - 0.9));
      solid.box(p[0], y - drop / 2 - 0.5, p[2], 0.5, Math.max(1, drop / 2), 0.5,
                shade(pal.prop, -0.1));
    }
  }

  function addGate(b, dyH) {
    const mid = W(b, 0, dyH / 2, 0);
    const [fx, , fz] = rot(b.r, 1, 0, 0);
    const [rx, , rz] = rot(b.r, 0, 0, 1);
    const kind = b.gate;
    const color = kind === 'start' ? 0xffffff : kind === 'finish' ? 0xe8453c : pal.deco;
    gates.push({ kind, gi: b.gi || 0, p: mid, f: [fx, 0, fz], r: [rx, 0, rz],
                 hw: h, y: mid[1] });
    // two posts and a banner
    for (const s of [-1, 1]) {
      const post = [mid[0] + rx * s * h, mid[1], mid[2] + rz * s * h];
      solid.box(post[0], post[1] + 1.9, post[2], 0.34, 1.9, 0.34, color);
    }
    const y0 = mid[1] + 3.4, y1 = mid[1] + 4.4;
    const L = [mid[0] - rx * h, y0, mid[2] - rz * h], R2 = [mid[0] + rx * h, y0, mid[2] + rz * h];
    bright.quad(L, R2, [R2[0], y1, R2[2]], [L[0], y1, L[2]], color);
    // painted line on the road
    if (kind !== 'cp') {
      const w = 0.75;
      const a = [mid[0] - rx * h - fx * w, mid[1] + 0.05, mid[2] - rz * h - fz * w];
      const c = [mid[0] + rx * h + fx * w, mid[1] + 0.05, mid[2] + rz * h + fz * w];
      bright.quad(a, [c[0] - fx * 2 * w, a[1], c[2] - fz * 2 * w], c,
                  [a[0] + fx * 2 * w, a[1], a[2] + fz * 2 * w], color);
    }
  }

  function buildLoop(b) {
    const R = b.rad || 12, adv = (b.length || 2) * CELL, SEG = 56;
    const [fx, , fz] = rot(b.r, 1, 0, 0);
    const [rx, , rz] = rot(b.r, 0, 0, 1);
    const o = [b.p[0] * CELL - fx * h, b.p[1] * LEVEL, b.p[2] * CELL - fz * h];
    const pt = (a, lat) => {
      const s = adv * a / (2 * Math.PI);
      const fwd = s + R * Math.sin(a);
      const up = R * (1 - Math.cos(a));
      return [o[0] + fx * fwd + rx * lat, o[1] + up, o[2] + fz * fwd + rz * lat];
    };
    // Surface normal at angle a points from the road toward the loop's axis -
    // straight up at the bottom, straight down at the top. Rails follow it, so
    // they still stand off the road where the road is upside down.
    const nrm = (a) => [-fx * Math.sin(a), Math.cos(a), -fz * Math.sin(a)];
    let prevL = null, prevR = null, prevN = null;
    for (let i = 0; i <= SEG; i++) {
      const a = 2 * Math.PI * i / SEG;
      const L = pt(a, -h), R2 = pt(a, h), N = nrm(a);
      if (prevL) {
        // Winding chosen so each road normal points to the side the car is on;
        // that is what lets the ground query find the inverted section.
        col.addQuad(prevL, prevR, R2, L, KIND.ROAD);
        solid.quad(prevL, prevR, R2, L, i % 4 < 2 ? pal.road : shade(pal.road, 0.07));
        // back face so the outside of the loop is not see-through
        solid.quad(L, R2, prevR, prevL, shade(pal.road, -0.4));
        for (const s of [-1, 1]) {
          const p0 = [prevL, prevR][s > 0 ? 1 : 0], p1 = [L, R2][s > 0 ? 1 : 0];
          wallStripN(p0, p1, prevN, N, 0.55, pal.rail);
        }
      }
      note(L); note(R2);
      prevL = L; prevR = R2; prevN = N;
    }
    // a couple of ribs so it reads as built, not floating
    for (const a of [Math.PI * 0.5, Math.PI * 1.5]) {
      const p = pt(a, 0);
      solid.box(p[0], (p[1] + o[1]) / 2, p[2], 0.4, Math.abs(p[1] - o[1]) / 2, 0.4,
                shade(pal.prop, -0.15));
    }
  }

  // --- ground / void -------------------------------------------------------
  const pad = CELL * 6;
  const gx0 = bbox.x0 - pad, gx1 = bbox.x1 + pad, gz0 = bbox.z0 - pad, gz1 = bbox.z1 + pad;
  let killY;
  if (track.ground != null) {
    // The ground sits a road-thickness BELOW the level-0 road surface, so the
    // track is a raised ribbon of tarmac rather than being flush with the grass.
    // Coplanar road and grass would make the ground query a coin toss between
    // them, and the car would think it was on grass for an entire lap.
    const gy = track.ground * LEVEL - THICK;
    const A = [gx0, gy, gz0], B = [gx0, gy, gz1], C = [gx1, gy, gz1], D = [gx1, gy, gz0];
    col.addQuad(A, B, C, D, KIND.OFFROAD);
    solid.quad(A, B, C, D, pal.ground);
    killY = gy - 30;
  } else {
    killY = minY - 26;
    // a distant plate so the void has a floor to look at
    const gy = minY - 34;
    solid.quad([gx0, gy, gz0], [gx0, gy, gz1], [gx1, gy, gz1], [gx1, gy, gz0],
               shade(pal.ground, -0.3));
  }

  // --- scenery (procedural, seeded, deterministic) -------------------------
  addScenery(solid, track, pal, bbox, CELL, LEVEL);

  const mat = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });
  const matBright = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide });
  group.add(solid.toMesh(mat));
  group.add(bright.toMesh(matBright));

  col.finish();

  // Centreline with cumulative distance, for race positions and respawns.
  const line = track.line.map(e => ({ p: e.p, lat: e.lat }));
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

function shade(hex, amt) {
  let r = (hex >> 16) & 255, g = (hex >> 8) & 255, b = hex & 255;
  if (amt >= 0) { r += (255 - r) * amt; g += (255 - g) * amt; b += (255 - b) * amt; }
  else { r *= 1 + amt; g *= 1 + amt; b *= 1 + amt; }
  return (Math.round(r) << 16) | (Math.round(g) << 8) | Math.round(b);
}

// A tiny deterministic PRNG so scenery is identical for everyone in a room.
function mulberry(seed) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

function addScenery(buf, track, pal, bbox, CELL, LEVEL) {
  let seed = 0;
  for (let i = 0; i < track.slug.length; i++) seed = seed * 31 + track.slug.charCodeAt(i);
  const rnd = mulberry(seed);
  const onGround = track.ground != null;
  const gy = onGround ? track.ground * LEVEL : null;
  // Keep props off the road: a cell is occupied if any block sits on it.
  const occupied = new Set();
  for (const b of track.blocks) {
    for (let dx = -1; dx <= 1; dx++) {
      for (let dz = -1; dz <= 1; dz++) occupied.add((b.p[0] + dx) + ',' + (b.p[2] + dz));
    }
  }
  const x0 = Math.floor(bbox.x0 / CELL) - 4, x1 = Math.ceil(bbox.x1 / CELL) + 4;
  const z0 = Math.floor(bbox.z0 / CELL) - 4, z1 = Math.ceil(bbox.z1 / CELL) + 4;
  for (let gx = x0; gx <= x1; gx++) {
    for (let gz = z0; gz <= z1; gz++) {
      if (occupied.has(gx + ',' + gz)) continue;
      if (rnd() > (onGround ? 0.17 : 0.05)) continue;
      if (!onGround) continue;         // nothing to stand a tree on in the void
      const px = gx * CELL + (rnd() - 0.5) * CELL * 0.6;
      const pz = gz * CELL + (rnd() - 0.5) * CELL * 0.6;
      const baseY = gy;
      const kind = rnd();
      if (kind < 0.55) {
        // conifer: trunk + two stacked prisms
        const hgt = 3 + rnd() * 4;
        buf.box(px, baseY + hgt * 0.22, pz, 0.32, hgt * 0.22, 0.32, 0x6b4f2a);
        buf.box(px, baseY + hgt * 0.62, pz, 1.5, hgt * 0.3, 1.5, pal.prop);
        buf.box(px, baseY + hgt * 1.0, pz, 0.95, hgt * 0.22, 0.95, shade(pal.prop, 0.12));
      } else if (kind < 0.8) {
        const s = 1 + rnd() * 1.8;
        buf.box(px, baseY + s * 0.5, pz, s, s * 0.5, s * 0.9, shade(pal.ground, -0.25));
      } else {
        const hgt = 2 + rnd() * 9;
        buf.box(px, baseY + hgt / 2, pz, 1.7, hgt / 2, 1.7, shade(pal.prop, -0.05));
      }
    }
  }
}
