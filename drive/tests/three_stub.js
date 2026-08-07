// Enough of three.js to run the simulation with no browser and no WebGL.
//
// The physics, the collider and the course logic only ever need Vector3 and
// Quaternion maths; everything else three.js provides is scene graph and
// rendering, which the headless tests do not touch. So the vector maths here is
// real (and matches three.js semantics exactly, including the mutate-and-return
// style), and the graphics classes are inert shells that record nothing.
//
// This is what lets test_sim.py drive every track through the actual production
// physics code rather than a Python re-implementation of it.

export class Vector3 {
  constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z; }
  set(x, y, z) { this.x = x; this.y = y; this.z = z; return this; }
  copy(v) { this.x = v.x; this.y = v.y; this.z = v.z; return this; }
  clone() { return new Vector3(this.x, this.y, this.z); }
  add(v) { this.x += v.x; this.y += v.y; this.z += v.z; return this; }
  sub(v) { this.x -= v.x; this.y -= v.y; this.z -= v.z; return this; }
  subVectors(a, b) { this.x = a.x - b.x; this.y = a.y - b.y; this.z = a.z - b.z; return this; }
  addScaledVector(v, s) { this.x += v.x * s; this.y += v.y * s; this.z += v.z * s; return this; }
  multiplyScalar(s) { this.x *= s; this.y *= s; this.z *= s; return this; }
  dot(v) { return this.x * v.x + this.y * v.y + this.z * v.z; }
  lengthSq() { return this.x * this.x + this.y * this.y + this.z * this.z; }
  length() { return Math.sqrt(this.lengthSq()); }
  normalize() { const l = this.length() || 1; return this.multiplyScalar(1 / l); }
  setLength(l) { return this.normalize().multiplyScalar(l); }
  crossVectors(a, b) {
    const ax = a.x, ay = a.y, az = a.z, bx = b.x, by = b.y, bz = b.z;
    this.x = ay * bz - az * by;
    this.y = az * bx - ax * bz;
    this.z = ax * by - ay * bx;
    return this;
  }
  cross(v) { return this.crossVectors(this, v); }
  lerp(v, a) {
    this.x += (v.x - this.x) * a; this.y += (v.y - this.y) * a; this.z += (v.z - this.z) * a;
    return this;
  }
  distanceTo(v) { return Math.sqrt((this.x - v.x) ** 2 + (this.y - v.y) ** 2 + (this.z - v.z) ** 2); }
  applyQuaternion(q) {
    const { x, y, z } = this, qx = q.x, qy = q.y, qz = q.z, qw = q.w;
    const ix = qw * x + qy * z - qz * y;
    const iy = qw * y + qz * x - qx * z;
    const iz = qw * z + qx * y - qy * x;
    const iw = -qx * x - qy * y - qz * z;
    this.x = ix * qw + iw * -qx + iy * -qz - iz * -qy;
    this.y = iy * qw + iw * -qy + iz * -qx - ix * -qz;
    this.z = iz * qw + iw * -qz + ix * -qy - iy * -qx;
    return this;
  }
}

export class Quaternion {
  constructor(x = 0, y = 0, z = 0, w = 1) { this.x = x; this.y = y; this.z = z; this.w = w; }
  set(x, y, z, w) { this.x = x; this.y = y; this.z = z; this.w = w; return this; }
  copy(q) { this.x = q.x; this.y = q.y; this.z = q.z; this.w = q.w; return this; }
  clone() { return new Quaternion(this.x, this.y, this.z, this.w); }
  setFromAxisAngle(axis, angle) {
    const half = angle / 2, s = Math.sin(half);
    this.x = axis.x * s; this.y = axis.y * s; this.z = axis.z * s; this.w = Math.cos(half);
    return this;
  }
  multiplyQuaternions(a, b) {
    const qax = a.x, qay = a.y, qaz = a.z, qaw = a.w;
    const qbx = b.x, qby = b.y, qbz = b.z, qbw = b.w;
    this.x = qax * qbw + qaw * qbx + qay * qbz - qaz * qby;
    this.y = qay * qbw + qaw * qby + qaz * qbx - qax * qbz;
    this.z = qaz * qbw + qaw * qbz + qax * qby - qay * qbx;
    this.w = qaw * qbw - qax * qbx - qay * qby - qaz * qbz;
    return this;
  }
  multiply(q) { return this.multiplyQuaternions(this, q); }
  premultiply(q) { return this.multiplyQuaternions(q, this); }
  normalize() {
    let l = Math.sqrt(this.x ** 2 + this.y ** 2 + this.z ** 2 + this.w ** 2);
    if (l === 0) { this.set(0, 0, 0, 1); return this; }
    l = 1 / l;
    this.x *= l; this.y *= l; this.z *= l; this.w *= l;
    return this;
  }
  slerp(qb, t) {
    if (t === 0) return this;
    if (t === 1) return this.copy(qb);
    const x = this.x, y = this.y, z = this.z, w = this.w;
    let cos = w * qb.w + x * qb.x + y * qb.y + z * qb.z;
    let bx = qb.x, by = qb.y, bz = qb.z, bw = qb.w;
    if (cos < 0) { cos = -cos; bx = -bx; by = -by; bz = -bz; bw = -bw; }
    if (cos >= 1) return this;
    const sqrSin = 1 - cos * cos;
    if (sqrSin <= Number.EPSILON) {
      const s = 1 - t;
      this.w = s * w + t * bw; this.x = s * x + t * bx;
      this.y = s * y + t * by; this.z = s * z + t * bz;
      return this.normalize();
    }
    const sin = Math.sqrt(sqrSin), len = Math.atan2(sin, cos);
    const a = Math.sin((1 - t) * len) / sin, b = Math.sin(t * len) / sin;
    this.w = w * a + bw * b; this.x = x * a + bx * b;
    this.y = y * a + by * b; this.z = z * a + bz * b;
    return this;
  }
  setFromUnitVectors(from, to) {
    let r = from.dot(to) + 1;
    if (r < Number.EPSILON) {
      r = 0;
      if (Math.abs(from.x) > Math.abs(from.z)) this.set(-from.y, from.x, 0, r);
      else this.set(0, -from.z, from.y, r);
    } else {
      this.set(from.y * to.z - from.z * to.y,
               from.z * to.x - from.x * to.z,
               from.x * to.y - from.y * to.x, r);
    }
    return this.normalize();
  }
}

// --- inert graphics shells -------------------------------------------------
class Obj3 {
  constructor() { this.children = []; this.position = new Vector3(); this.visible = true;
                  this.quaternion = new Quaternion(); this.rotation = { x: 0, y: 0, z: 0 };
                  this.scale = new Vector3(1, 1, 1); }
  add(o) { this.children.push(o); return this; }
  remove() { return this; }
  traverse(fn) { fn(this); this.children.forEach(c => c.traverse && c.traverse(fn)); }
}
export class Group extends Obj3 {}
export class Mesh extends Obj3 {
  constructor(geometry, material) { super(); this.geometry = geometry; this.material = material; }
}
export class BufferGeometry {
  constructor() { this.attributes = {}; }
  setAttribute(n, a) { this.attributes[n] = a; return this; }
  computeVertexNormals() { return this; }
  dispose() {}
  rotateZ() { return this; }
}
export class Float32BufferAttribute {
  constructor(array, itemSize) { this.array = array; this.itemSize = itemSize;
                                 this.count = array.length / itemSize; }
  getY(i) { return this.array[i * this.itemSize + 1]; }
}
// Real colour arithmetic, not a shell. It started as one - `set` took numbers
// only, `lerp` and `multiplyScalar` returned `this` unchanged - which was fine
// while nothing here did anything with a colour but hand it to a material. The
// car is built out of colour arithmetic now (a trim is the body darkened, a fade
// is a lerp along the car), and a stub that answers white to all of it turns
// every test about paint into a test that the code does not throw.
export class Color {
  constructor(c) { this.r = 1; this.g = 1; this.b = 1; if (c != null) this.set(c); }
  set(c) {
    if (c instanceof Color) { this.r = c.r; this.g = c.g; this.b = c.b; return this; }
    if (typeof c === 'number') {
      this.r = ((c >> 16) & 255) / 255; this.g = ((c >> 8) & 255) / 255; this.b = (c & 255) / 255;
    } else if (typeof c === 'string') {
      const m = /^#?([0-9a-f]{6})$/i.exec(c.trim());
      if (m) return this.set(parseInt(m[1], 16));
    }
    return this;
  }
  clone() { const k = new Color(); k.r = this.r; k.g = this.g; k.b = this.b; return k; }
  copy(c) { return this.set(c); }
  lerp(c, t) {
    this.r += (c.r - this.r) * t; this.g += (c.g - this.g) * t; this.b += (c.b - this.b) * t;
    return this;
  }
  multiplyScalar(s) { this.r *= s; this.g *= s; this.b *= s; return this; }
  getHex() {
    const q = (v) => Math.max(0, Math.min(255, Math.round(v * 255)));
    return (q(this.r) << 16) | (q(this.g) << 8) | q(this.b);
  }
  getHexString() { return this.getHex().toString(16).padStart(6, '0'); }
}
const noop = class { constructor() {} dispose() {} };
// Materials keep the options they were built with, and are three distinct
// classes rather than three names for one. Both halves are needed and neither
// was there: they were all the same `noop`, so `instanceof MeshPhongMaterial`
// was true of every material on the car and a test could not tell gloss from
// matte - which is the entire subject of the finish slot. `color` is promoted
// to a real `Color` the way three.js does it, because the brake lamps call
// `material.color.setHex` every frame.
class Mat {
  constructor(o = {}) {
    Object.assign(this, o);
    this.color = new Color(o.color == null ? 0xffffff : o.color);
  }
  dispose() {}
}
export const MeshLambertMaterial = class extends Mat {};
export const MeshBasicMaterial = class extends Mat {};
// The three finishes above matte are Phong, since a specular highlight is the
// only honest way to say "shiny" in a scene with no environment map.
export const MeshPhongMaterial = class extends Mat {};
export const SpriteMaterial = noop;
export const Sprite = Obj3;
export const CanvasTexture = noop;
export const BoxGeometry = BufferGeometry;
export const CylinderGeometry = BufferGeometry;
export const ConeGeometry = BufferGeometry;
export const CircleGeometry = BufferGeometry;
export const PlaneGeometry = BufferGeometry;
export const SphereGeometry = class extends BufferGeometry {
  constructor() { super(); this.attributes.position = new Float32BufferAttribute(new Float32Array(9), 3); }
};
export const Fog = noop;
export const Scene = Obj3;
export const PerspectiveCamera = Obj3;
export const WebGLRenderer = noop;
export const DirectionalLight = Obj3;
export const HemisphereLight = Obj3;
export const AdditiveBlending = 2;
export const DoubleSide = 2;
export const BackSide = 1;
