// Everything you see. Deliberately plain: flat shading, no textures, no shadow
// maps, one merged mesh for the track. The look comes from the geometry and a
// two-colour sky, which is also why it holds 60fps on a laptop.
//
// The camera is the part worth reading. It orbits in the *car's* frame rather
// than the world's - its up vector and its idea of "behind" both come from the
// car - so a loop looks like a loop from the driver's seat instead of the world
// flipping over. Everything about it is exponentially smoothed, and the
// smoothing is frame-rate independent, so it never whips or judders.

import * as THREE from './vendor/three.module.js';

const BRAKE_OFF = 0x521218;
const BRAKE_ON = 0xff2b2b;

export class CarView {
  constructor(scene, color, opts = {}) {
    this.group = new THREE.Group();
    this.body = new THREE.Group();
    this.group.add(this.body);
    const ghost = !!opts.ghost;
    const col = new THREE.Color(color);
    const dark = col.clone().multiplyScalar(0.55);

    const mat = (c, extra = {}) => new THREE.MeshLambertMaterial(
      Object.assign({ color: c, flatShading: true,
                      transparent: ghost, opacity: ghost ? 0.42 : 1 }, extra));

    const bodyMat = mat(col);
    const darkMat = mat(dark);
    const glassMat = mat(0x2b3240);
    const tyreMat = mat(0x1c1f26);

    // chassis: a wedge-ish stack of boxes, Polytrack-simple
    const lower = new THREE.Mesh(new THREE.BoxGeometry(1.9, 0.55, 3.4), bodyMat);
    lower.position.y = 0.28;
    this.body.add(lower);
    const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.55, 0.5, 1.6), bodyMat);
    cabin.position.set(0, 0.78, 0.1);
    this.body.add(cabin);
    const glass = new THREE.Mesh(new THREE.BoxGeometry(1.42, 0.34, 1.1), glassMat);
    glass.position.set(0, 0.84, -0.1);
    this.body.add(glass);
    const nose = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.28, 0.7), darkMat);
    nose.position.set(0, 0.2, -1.85);
    this.body.add(nose);
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
    this.wheels = [];
    this.steered = [];
    for (const [x, z, front] of [[-1.0, -1.15, true], [1.0, -1.15, true],
                                 [-1.0, 1.25, false], [1.0, 1.25, false]]) {
      const hub = new THREE.Group();
      hub.position.set(x, 0.4, z);
      const w = new THREE.Mesh(wheelGeo, tyreMat);
      hub.add(w);
      this.body.add(hub);
      this.wheels.push(w);
      if (front) this.steered.push(hub);
    }

    // contact shadow: one dark disc laid on the surface under the car
    this.shadow = new THREE.Mesh(
      new THREE.CircleGeometry(1.5, 14),
      new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true,
                                    opacity: ghost ? 0.1 : 0.24, depthWrite: false }));
    this.shadow.rotation.x = -Math.PI / 2;
    scene.add(this.shadow);

    // Brake lights. Two panels on the tail, unlit material so they read as
    // emissive without a second light in the scene: dark red at rest, full red
    // the instant you touch the brakes. They are on the *car*, not the HUD, so
    // you can see the driver ahead of you braking - which is the only reason a
    // detail like this is worth any geometry at all.
    this.brakeMats = [];
    for (const s of [-1, 1]) {
      const m = new THREE.MeshBasicMaterial({
        color: BRAKE_OFF, transparent: ghost, opacity: ghost ? 0.42 : 1 });
      const lamp = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.22, 0.1), m);
      lamp.position.set(s * 0.6, 0.5, 1.73);
      this.body.add(lamp);
      this.brakeMats.push(m);
    }
    this._braking = false;

    scene.add(this.group);
    this.scene = scene;
    this.color = color;
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
    g.fillStyle = color || '#fff';
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
      this.shadow.material.opacity = 0.24 * fade;
    } else {
      this.shadow.visible = false;
    }
    const braking = !!opts.braking;
    if (braking !== this._braking) {
      this._braking = braking;
      for (const m of this.brakeMats) m.color.setHex(braking ? BRAKE_ON : BRAKE_OFF);
    }
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

export class Renderer {
  constructor(canvas) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(66, 1, 0.4, 2600);
    this.baseFov = 66;

    this.sun = new THREE.DirectionalLight(0xffffff, 1.65);
    this.sun.position.set(0.45, 1, 0.32).multiplyScalar(120);
    this.scene.add(this.sun);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x5a6172, 0.72));

    this.sky = null;
    this.particles = new Particles(this.scene);
    this.trackGroup = null;

    // camera state, all smoothed
    this.camPos = new THREE.Vector3();
    this.camUp = new THREE.Vector3(0, 1, 0);
    this.camLook = new THREE.Vector3();
    this.camFwd = new THREE.Vector3(0, 0, -1);
    this.shake = 0;
    this.started = false;
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
    this.scene.fog = new THREE.Fog(pal.fog, 190, 900);
    this.scene.background = new THREE.Color(pal.sky);
    if (this.sky) { this.scene.remove(this.sky); this.sky.geometry.dispose(); }
    this.sky = makeSky(pal.sky, pal.fog);
    this.scene.add(this.sky);
    this.started = false;
  }

  /** Chase camera. `car` is the local Car; dt is real seconds. */
  follow(car, dt, opts = {}) {
    const speed = car.speed;
    const back = 8.2 + Math.min(3.4, speed * 0.075);
    const up = 3.2 + Math.min(1.1, speed * 0.02);

    // Smooth the frame we orbit in, not the final position: that is what keeps a
    // loop from throwing the camera around while still following the car over it.
    const kf = 1 - Math.exp(-(car.grounded ? 9 : 4.5) * dt);
    const ku = 1 - Math.exp(-(car.grounded ? 7 : 3.0) * dt);
    this.camFwd.lerp(car.fwd, kf).normalize();
    this.camUp.lerp(car.up, ku).normalize();

    const want = new THREE.Vector3().copy(car.pos)
      .addScaledVector(this.camFwd, -back)
      .addScaledVector(this.camUp, up);

    if (!this.started) { this.camPos.copy(want); this.started = true; }
    // Track the target position hard enough to feel connected, softly enough to
    // absorb kerbs. Faster = tighter, so high speed does not feel laggy.
    const kp = 1 - Math.exp(-(11 + speed * 0.16) * dt);
    this.camPos.lerp(want, kp);

    const look = new THREE.Vector3().copy(car.pos)
      .addScaledVector(this.camFwd, 7 + speed * 0.16)
      .addScaledVector(this.camUp, 1.1);
    this.camLook.lerp(look, 1 - Math.exp(-12 * dt));

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

    // A little FOV with speed - cheap, and it does a lot.
    const fov = this.baseFov + Math.min(13, speed * 0.16);
    if (Math.abs(this.camera.fov - fov) > 0.05) {
      this.camera.fov += (fov - this.camera.fov) * (1 - Math.exp(-6 * dt));
      this.camera.updateProjectionMatrix();
    }

    if (this.sky) this.sky.position.copy(this.camera.position);
    // Keep the sun near the action so the whole track is lit the same way.
    this.sun.position.copy(car.pos).add(new THREE.Vector3(60, 130, 42));
    this.sun.target.position.copy(car.pos);
    this.sun.target.updateMatrixWorld();
    void opts;
  }

  kick(amount) { this.shake = Math.min(2.2, this.shake + amount); }

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

// A big inverted sphere with a vertical two-colour gradient baked into vertex
// colours - a sky without a shader or a texture.
function makeSky(top, bottom) {
  const geo = new THREE.SphereGeometry(1400, 18, 12);
  const pos = geo.attributes.position;
  const colors = [];
  const a = new THREE.Color(top), b = new THREE.Color(bottom);
  for (let i = 0; i < pos.count; i++) {
    const t = Math.max(0, Math.min(1, (pos.getY(i) / 1400) * 0.5 + 0.5));
    const c = b.clone().lerp(a, Math.pow(t, 0.65));
    colors.push(c.r, c.g, c.b);
  }
  geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  return new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    vertexColors: true, side: THREE.BackSide, depthWrite: false, fog: false }));
}
