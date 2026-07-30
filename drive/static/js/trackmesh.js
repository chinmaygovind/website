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

export const KIND = { ROAD: 0, WALL: 1, OFFROAD: 2 };

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
  park:     { road: 0x565d6b, kerb: 0xffffff, kerb2: 0x3d8bfd, ground: 0x63b866, sky: 0x9ed2f0, fog: 0xb9dcee, rail: 0xf0f0f0, prop: 0x347a3c, deco: 0xf2994a },
  // Chicane Park had `park` too; it has its own now so the two can be art
  // directed apart. Same daylight, but the conifers have grown up: a mix of
  // big pines among them, and a denser scatter to make it a park.
  chicane:  { road: 0x565d6b, kerb: 0xffffff, kerb2: 0x3d8bfd, ground: 0x63b866,
              sky: 0x9ed2f0, fog: 0xb9dcee, rail: 0xf0f0f0,
              prop: 0x347a3c, prop2: 0x4f9440, deco: 0xf2994a,
              density: 0.24,
              props: { bigpine: 0.42, conifer: 0.34, rock: 0.14, block: 0.10 } },
  skyline:  { road: 0x4d5464, kerb: 0xf6f6f6, kerb2: 0x56ccf2, ground: 0x4a6b8a, sky: 0x7fb6dd, fog: 0x9ec9e6, rail: 0xe9f4ff, prop: 0x6e7f95, deco: 0x56ccf2 },
  lagoon:   { road: 0x515a68, kerb: 0xfdfdfd, kerb2: 0x27ae60, ground: 0x3aa6a0, sky: 0x8fdce6, fog: 0xb6e8ec, rail: 0xf3fffe, prop: 0x1f8f7a, deco: 0x27ae60 },
  heights:  { road: 0x4f5460, kerb: 0xf4f4f4, kerb2: 0xf2994a, ground: 0x7a6a52, sky: 0xf0c9a0, fog: 0xf3d9bd, rail: 0xfff2e2, prop: 0x8a7358, deco: 0xf2994a },
  city:     { road: 0x4a4f5c, kerb: 0xf7f7f7, kerb2: 0xf2c94c, ground: 0x5c6070, sky: 0x8ea9c9, fog: 0xa9bed6, rail: 0xf2f4f7, prop: 0x6b7180, deco: 0xf2c94c },
  spiral:   { road: 0x525869, kerb: 0xfafafa, kerb2: 0xbb6bd9, ground: 0x5a5570, sky: 0xb9a6e0, fog: 0xd0c4ec, rail: 0xf6f0ff, prop: 0x6d6488, deco: 0xbb6bd9 },
  gauntlet: { road: 0x474c58, kerb: 0xf2f2f2, kerb2: 0xe8453c, ground: 0x3d4250, sky: 0x6f7f9c, fog: 0x8d9ab3, rail: 0xf7f7f7, prop: 0x555c6c, deco: 0xe8453c },
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

  // Edge points of the road at a station, and the same points lifted a hair
  // along the normal for the painted kerb (which is drawn, never collided).
  const edge = (e, s) => [e.p[0] + e.lat[0] * s * e.hw,
                          e.p[1] + e.lat[1] * s * e.hw,
                          e.p[2] + e.lat[2] * s * e.hw];
  const inset = (e, s, d) => [e.p[0] + e.lat[0] * s * (e.hw - d) + e.n[0] * 0.05,
                              e.p[1] + e.lat[1] * s * (e.hw - d) + e.n[1] * 0.05,
                              e.p[2] + e.lat[2] * s * (e.hw - d) + e.n[2] * 0.05];
  const sink = (p, e, d) => [p[0] - e.n[0] * d, p[1] - e.n[1] * d, p[2] - e.n[2] * d];

  // ---- the road: one strip of quads between consecutive stations -----------
  //
  // This loop is the entire track geometry. Everything the old grid version
  // needed a separate branch for - straights, corners, ramps, kicker lips,
  // loops, bridges - is the same four vertices here, because the stations
  // already carry the position, the normal, the lateral axis and the width.
  for (let i = 0; i + 1 < line.length; i++) {
    const a = line[i], b = line[i + 1];
    if (a.air || b.air) continue;          // a gap: no road, by construction

    const aL = edge(a, -1), aR = edge(a, 1);
    const bL = edge(b, -1), bR = edge(b, 1);
    // Wound so the surface normal comes out along `n`, which is what lets the
    // ground query find the road while the car is upside down inside a corkscrew.
    col.addQuad(aL, aR, bR, bL, KIND.ROAD);
    solid.quad(aL, aR, bR, bL, i % 8 < 4 ? pal.road : shade(pal.road, 0.045));
    note(aL); note(aR);

    // Underside: the slab, so the track reads as solid edge-on and from below.
    const aLu = sink(aL, a, THICK), aRu = sink(aR, a, THICK);
    const bLu = sink(bL, b, THICK), bRu = sink(bR, b, THICK);
    solid.quad(bLu, bRu, aRu, aLu, shade(pal.road, -0.34));
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
    if (e.air || e.fix) continue;
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
  if (groundY != null) {
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
    // a distant plate so the void has a floor to look at
    const gy = minY - 34;
    solid.quad([gx0, gy, gz0], [gx0, gy, gz1], [gx1, gy, gz1], [gx1, gy, gz0],
               shade(pal.ground, -0.3));
  }

  // --- scenery (procedural, seeded, deterministic) -------------------------
  addScenery(solid, track, pal, bbox, CELL);

  const mat = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });
  const matBright = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide });
  group.add(solid.toMesh(mat));
  group.add(bright.toMesh(matBright));

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

      if (kind === 'conifer') {
        // trunk + two stacked prisms
        const hgt = 3 + rnd() * 4;
        buf.box(px, baseY + hgt * 0.22, pz, 0.32, hgt * 0.22, 0.32, 0x6b4f2a);
        buf.box(px, baseY + hgt * 0.62, pz, 1.5, hgt * 0.3, 1.5, pal.prop);
        buf.box(px, baseY + hgt * 1.0, pz, 0.95, hgt * 0.22, 0.95, shade(pal.prop, 0.12));
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
          buf.box(px + ox, cy, pz + oz, w, th, w * (0.68 + rnd() * 0.58), col);
          if (rnd() < 0.5) {
            const a = rnd() * Math.PI * 2, d = w * (0.55 + rnd() * 0.45);
            buf.box(px + ox + Math.cos(a) * d, cy - th * 0.25, pz + oz + Math.sin(a) * d,
                    w * 0.5, th * 0.6, w * 0.5, shade(col, -0.06));
          }
        }
        buf.box(px + lean * base * 1.2, y0 + hgt * 0.76, pz + lean * base * 0.7,
                base * 0.2, hgt * 0.07, base * 0.2, shade(leaf, 0.18));
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
