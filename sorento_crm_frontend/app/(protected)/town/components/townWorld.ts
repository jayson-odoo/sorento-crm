import * as THREE from 'three';
import type { TownDueCustomer, TownShipment, TownShop, TownSite, TownSnapshot, TownTradingHouse } from '@/types/town.types';
import {
  changePercent,
  count,
  placeTags,
  rm0,
  sceneSelection,
  separateLabels,
  tagLabel,
  tagName,
  type ScreenBox,
} from '../lib/townFormat';
import { DEFAULT_VIEW, cameraPosition, dragView, pinchZoom, stepZoom, wheelZoom, type TownView } from '../lib/townCamera';
import { STAGES, STATES, STATE_BY, mapXZ, siteLook, stateKeyOf, type StateDef } from '../lib/townMap';
import { EASE, mulberry32, trapezoid, type SaleBeat, type Trapezoid } from '../lib/townMotion';
import { townTip, type TipSubject } from '../lib/townTips';
import type { TownTarget } from './TownLightbox';

/**
 * The town in 3D, ported from the owner-approved v6 mock (TOWN-LOOK, 10 Nov): an island in a shallow
 * sea under one warm sun with soft shadows; shops by 90-day rank, stalls, barrel-roof warehouses, the
 * depot, the approvals office, the port with its gantry crane, lorries driving to the customers of
 * orders due, ships at anchor, and DOM label pills projected from 3D anchors. Rendered on demand only:
 * frames are drawn while something moves, never while the tab is hidden. The world is rebuilt per
 * snapshot on one long-lived renderer; the camera view and the motion clock carry across rebuilds.
 *
 * TOWN-PROJECT-CITY (owner-approved mock v2, 11 Nov): the town is a map of Malaysia. The island above is
 * Selangor (HQ at Shah Alam, Port Klang west, north up); every other state is an island built with the same
 * slab, beach and foam (`lib/townMap.ts` places them), joined by causeways like the bridge. Each state's street
 * holds its dealers, its open projects as sites (look = the project's own dates, flag = our sales stage) and its
 * trading houses as glass towers. A state pill or `flyTo` moves the camera; reset returns to Shah Alam.
 */

export interface TownTipState {
  title: string;
  detail: string;
  x: number;
  y: number;
}

export interface WorldOptions {
  canvas: HTMLCanvasElement;
  stage: HTMLElement;
  labelLayer: HTMLElement;
  renderer: THREE.WebGLRenderer;
  snapshot: TownSnapshot;
  /** The snapshot shown before this one: the board and the beat's shop start from it. */
  prev: TownSnapshot | null;
  beat: SaleBeat | null;
  intro: boolean;
  reduced: boolean;
  motion: { current: boolean };
  view: { current: TownView };
  clock: { current: number };
  select: (target: TownTarget) => void;
  hover: (tip: TownTipState | null) => void;
}

export interface WorldHandle {
  flyTo: (key: string) => void;
  dispose: () => void;
  zoom: (direction: 1 | -1) => void;
  reset: () => void;
  setMotion: (on: boolean) => void;
}

const LORRY_CAP = 6;
const PARKED_CAP = 10;
const SHIP_CAP = 6;
const LATE_CAP = 12;
const DEG = Math.PI / 180;
const TGT = new THREE.Vector3(-2.5, 0, -2.5);
const HOME_TGT = TGT.clone();

const INTRO_FROM: TownView = { yaw: DEFAULT_VIEW.yaw - 62 * DEG, tilt: 68 * DEG, zoom: 0.5 };
const INTRO_S = 2.4;

/** The repo's one motion curve, read from the `--ease-standard` token (css/config.reui.css) so the
 * chip's WAAPI animation never carries its own copy; `ease-out` only where no stylesheet is loaded. */
function easeToken(): string {
  try {
    return getComputedStyle(document.documentElement).getPropertyValue('--ease-standard').trim() || 'ease-out';
  } catch {
    return 'ease-out';
  }
}

/** One renderer per mounted scene (kept across snapshot rebuilds, disposed on unmount). */
export function createTownRenderer(canvas: HTMLCanvasElement): THREE.WebGLRenderer {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NeutralToneMapping; // Khronos neutral: keeps the data colours true
  renderer.toneMappingExposure = 1;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  return renderer;
}

/** The snapshot's hour (MYT, as written in `as_of`); night = after closing. */
function hourOf(snapshot: TownSnapshot): number {
  const h = Number(snapshot.as_of.slice(11, 13)) + Number(snapshot.as_of.slice(14, 16)) / 60;
  if (snapshot.phase === 'night') return 22;
  return Number.isFinite(h) ? Math.min(Math.max(h, 7), 21.5) : 15;
}

type Pickable = [THREE.Object3D, (instance: number) => void, (instance: number) => TipSubject | null, ((instance: number) => Slot | null)?];

interface Slot {
  s: TownShop;
  a: number;
  x: number;
  z: number;
  ry: number;
  inner: boolean;
  floors: number;
  stall: boolean;
  lit: boolean;
  litK: number;
  variant: number;
  tint: number;
  slate: number;
  h: number;
  lift: number;
  liftTo: number;
  sq: number;
  rise: number;
  delay: number;
  gi: number;
  ui: number[];
  ri: number;
  si: number;
  pool: number;
  flash: number;
  exit?: number;
  tail?: THREE.Vector3[];
}

interface Particle {
  x: number; y: number; z: number; vx: number; vy?: number; vz: number; t0: number; life: number; r: number; g: number; b: number;
}

interface Label {
  isState?: boolean;
  el: HTMLButtonElement;
  anchor: THREE.Vector3;
  fixed: boolean;
  w: number;
  h: number;
}

export function mountWorld(o: WorldOptions): WorldHandle {
  const { canvas, stage, labelLayer, renderer, snapshot, prev, beat, reduced, motion, view, clock, select, hover } = o;
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0xe6eef1, 150, 340);
  const fog = scene.fog;
  const cam = new THREE.PerspectiveCamera(30, 1, 4, 4000);
  let baseDist = 120;
  let labelsDirty = true;
  let raf = 0;
  let last = 0;
  let disposed = false;
  const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
  const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
  const smooth = (t: number) => t * t * (3 - 2 * t);
  const night = snapshot.phase === 'night';
  const full = snapshot.today.amount != null;
  const timers: number[] = [];

  /* ======== light ======== */
  const hemi = new THREE.HemisphereLight(0xe3edf7, 0xcdb994, 1.15);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff1de, 2.7);
  sun.position.set(-62, 70, -8);
  sun.target.position.copy(TGT);
  scene.add(sun, sun.target);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -48, right: 48, top: 48, bottom: -48, near: 20, far: 210 });
  sun.shadow.camera.updateProjectionMatrix();
  sun.shadow.bias = -0.0005;
  sun.shadow.normalBias = 0.04;
  sun.shadow.radius = 4;
  sun.shadow.intensity = 0.8;
  const fill = new THREE.DirectionalLight(0xc7d8ff, 0.45);
  fill.position.set(50, 30, 40);
  scene.add(fill);

  /* ======== geometry helpers: vertex colours + baked occlusion (darker at the foot of every wall) ======== */
  const C = (h: number) => new THREE.Color(h);
  const _m = new THREE.Matrix4();
  const _q = new THREE.Quaternion();
  const _v = new THREE.Vector3();
  const _s = new THREE.Vector3();
  const _e = new THREE.Euler();
  const _c = new THREE.Color();
  const templates: THREE.BufferGeometry[] = [];
  const keep = <T extends THREE.BufferGeometry>(g: T) => {
    templates.push(g);
    return g;
  };
  function P(geo: THREE.BufferGeometry, color: number, x = 0, y = 0, z = 0, sx = 1, sy = 1, sz = 1, ry = 0, rx = 0, rz = 0) {
    const g = geo.index ? geo.toNonIndexed() : geo.clone();
    g.applyMatrix4(
      new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)), new THREE.Vector3(sx, sy, sz)),
    );
    const c = C(color);
    const k = g.attributes.position.count;
    const arr = new Float32Array(k * 3);
    for (let i = 0; i < k; i++) {
      arr[i * 3] = c.r;
      arr[i * 3 + 1] = c.g;
      arr[i * 3 + 2] = c.b;
    }
    g.setAttribute('color', new THREE.BufferAttribute(arr, 3));
    if (g.attributes.uv) g.deleteAttribute('uv');
    templates.push(g);
    return g;
  }
  function merge(parts: THREE.BufferGeometry[], ao = 0, aoH = 1.3) {
    const out = new THREE.BufferGeometry();
    for (const key of ['position', 'normal', 'color']) {
      const arr = new Float32Array(parts.reduce((sum, p) => sum + p.attributes[key].array.length, 0));
      let offset = 0;
      for (const p of parts) {
        arr.set(p.attributes[key].array as Float32Array, offset);
        offset += p.attributes[key].array.length;
      }
      out.setAttribute(key, new THREE.BufferAttribute(arr, 3));
    }
    if (ao) {
      const p = out.attributes.position;
      const c = out.attributes.color;
      for (let i = 0; i < p.count; i++) {
        const k = 1 - ao * (1 - smooth(clamp(p.getY(i) / aoH, 0, 1)));
        c.setXYZ(i, c.getX(i) * k, c.getY(i) * k, c.getZ(i) * k);
      }
    }
    return out;
  }
  function paint(g: THREE.BufferGeometry, fn: (x: number, y: number, z: number, ny: number, c: THREE.Color) => void) {
    const p = g.attributes.position;
    const nr = g.attributes.normal;
    const arr = new Float32Array(p.count * 3);
    for (let i = 0; i < p.count; i++) {
      fn(p.getX(i), p.getY(i), p.getZ(i), nr.getY(i), _c);
      arr[i * 3] = _c.r;
      arr[i * 3 + 1] = _c.g;
      arr[i * 3 + 2] = _c.b;
    }
    g.setAttribute('color', new THREE.BufferAttribute(arr, 3));
    return g;
  }
  const BOX = keep(new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0));
  const CYL = (r1: number, r2: number, h: number, s = 16) => keep(new THREE.CylinderGeometry(r1, r2, h, s).translate(0, h / 2, 0));
  const TRI = keep(
    new THREE.ExtrudeGeometry(new THREE.Shape([new THREE.Vector2(-0.5, 0), new THREE.Vector2(0.5, 0), new THREE.Vector2(0, 1)]), {
      depth: 1,
      bevelEnabled: false,
    }).translate(0, 0, -0.5),
  );
  const HIP = keep(new THREE.CylinderGeometry(0, Math.SQRT1_2, 1, 4, 1).rotateY(Math.PI / 4).translate(0, 0.5, 0));
  const BARREL = keep(new THREE.CylinderGeometry(1, 1, 1, 12, 1, false, -Math.PI / 2, Math.PI).rotateX(-Math.PI / 2).rotateY(Math.PI / 2));
  const stdMat = (opts: THREE.MeshStandardMaterialParameters = {}) =>
    new THREE.MeshStandardMaterial({ vertexColors: true, flatShading: true, roughness: 0.9, metalness: 0, ...opts });
  const basicMat = (opts: THREE.MeshBasicMaterialParameters = {}) => new THREE.MeshBasicMaterial({ toneMapped: false, ...opts });
  const instanced: THREE.InstancedMesh[] = [];
  function inst(geo: THREE.BufferGeometry, mat: THREE.Material, cap: number, name = '', { cast = true, receive = true } = {}) {
    const m = new THREE.InstancedMesh(geo, mat, Math.max(1, cap));
    m.count = cap;
    m.name = name;
    m.castShadow = cast;
    m.receiveShadow = receive;
    m.frustumCulled = false;
    m.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 400);
    scene.add(m);
    instanced.push(m);
    return m;
  }
  function mesh(geo: THREE.BufferGeometry, mat: THREE.Material, { cast = true, receive = true, parent = scene as THREE.Object3D } = {}) {
    const m = new THREE.Mesh(geo, mat);
    m.castShadow = cast;
    m.receiveShadow = receive;
    parent.add(m);
    return m;
  }
  function setInst(m: THREE.InstancedMesh, i: number, x: number, y: number, z: number, ry = 0, sx = 1, sy = 1, sz = 1, rx = 0, rz = 0, order: THREE.EulerOrder = 'XYZ') {
    _e.set(rx, ry, rz, order);
    _q.setFromEuler(_e);
    _v.set(x, y, z);
    _s.set(sx, sy, sz);
    _m.compose(_v, _q, _s);
    m.setMatrixAt(i, _m);
    m.instanceMatrix.needsUpdate = true;
  }
  const polar = (r: number, d: number): [number, number] => [Math.cos(d * DEG) * r, Math.sin(d * DEG) * r];
  const faceOut = (d: number) => Math.atan2(Math.cos(d * DEG), Math.sin(d * DEG));
  const faceIn = (d: number) => Math.atan2(-Math.cos(d * DEG), -Math.sin(d * DEG));
  const faceTo = (dx: number, dz: number) => Math.atan2(dx, dz);
  const radTex = (stops: [number, string][], size = 128) => {
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const g = c.getContext('2d');
    if (g) {
      const gr = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
      stops.forEach(([at, col]) => gr.addColorStop(at, col));
      g.fillStyle = gr;
      g.fillRect(0, 0, size, size);
    }
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  };
  const rng = mulberry32(20261110);
  const SEA = -1.35;
  const pickables: Pickable[] = [];

  /* ======== the island: grass top, cliff, beach, foam, a shallow sea fading into haze ======== */
  const rIsland = (a: number) => 27.6 + 1.0 * Math.sin(3 * a + 0.6) + 0.6 * Math.sin(5 * a + 2.1) + 0.35 * Math.sin(9 * a + 4);
  const outline = (off: number, nseg = 160) =>
    Array.from({ length: nseg }, (_, i) => {
      const a = (i / nseg) * Math.PI * 2;
      const r = rIsland(a) + off;
      return new THREE.Vector2(Math.cos(a) * r, -Math.sin(a) * r);
    });
  function slab(off: number, depth: number, bevel: number, top: number, pts?: THREE.Vector2[]) {
    let g: THREE.BufferGeometry = new THREE.ExtrudeGeometry(new THREE.Shape(pts ?? outline(off)), {
      depth, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 2, curveSegments: 1, steps: 1,
    });
    g.rotateX(-Math.PI / 2);
    g.translate(0, top - depth - bevel, 0);
    g.deleteAttribute('uv');
    if (g.index) {
      const flat = g.toNonIndexed();
      g.dispose();
      g = flat;
    }
    return g;
  }
  const GRASS_A = C(0xa9c98c);
  const GRASS_B = C(0x99bf80);
  mesh(
    paint(slab(0, 1.9, 0.45, 0), (x, y, z, ny, c) => {
      if (ny > 0.92) c.copy(GRASS_A).lerp(GRASS_B, 0.5 + 0.5 * Math.sin(x * 0.21) * Math.sin(z * 0.17 + 1));
      else if (ny > 0.3) c.set(0xc3d497);
      else c.set(0xd9c39d).multiplyScalar(0.7 + 0.3 * clamp((y + 2.4) / 2.4, 0, 1));
    }),
    stdMat(),
    { cast: false },
  );
  mesh(paint(slab(2.0, 1.1, 0.5, -0.72), (_x, _y, _z, ny, c) => { c.set(ny > 0.6 ? 0xeedcb4 : 0xd6c19a); }), stdMat(), { cast: false });
  const foamShape = new THREE.Shape(outline(4.1));
  foamShape.holes.push(new THREE.Path(outline(2.3).reverse()));
  const foam = mesh(new THREE.ShapeGeometry(foamShape, 1).rotateX(-Math.PI / 2), basicMat({ color: 0xffffff, transparent: true, opacity: 0.5, depthWrite: false }), { cast: false, receive: false });
  foam.position.y = SEA + 0.24;
  foam.renderOrder = 1;

  /* ======== TOWN-PROJECT-CITY: the other states, same slab, beach and foam as the live island ======== */
  interface Isle { d: StateDef; cx: number; cz: number; wa: number; sd: number; ux: number; uz: number }
  const isles: Isle[] = STATES.filter((d) => d.key !== 'selangor').map((d) => {
    const [cx, cz] = mapXZ(d.e, d.n);
    const [ax, az] = mapXZ(Math.cos(d.rot * DEG), Math.sin(d.rot * DEG));
    const par = d.parent ? STATE_BY[d.parent] : null;
    const [px, pz] = par ? mapXZ(par.e, par.n) : [cx - ax, cz - az];
    const ul = Math.hypot(cx - px, cz - pz) || 1;
    return { d, cx, cz, wa: Math.atan2(az, ax), sd: [...d.key].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) % 997, 7) / 50, ux: (cx - px) / ul, uz: (cz - pz) / ul };
  });
  const isleBy = Object.fromEntries(isles.map((i) => [i.d.key, i])) as Record<string, Isle>;
  const rIsle = (i: Isle, a: number) => {
    const t = a - i.wa;
    const base = 1 / Math.sqrt((Math.cos(t) / i.d.rx) ** 2 + (Math.sin(t) / i.d.ry) ** 2);
    return base * (1 + 0.05 * Math.sin(3 * a + i.sd) + 0.03 * Math.sin(5 * a + 2 * i.sd) + 0.015 * Math.sin(9 * a + 3 * i.sd));
  };
  const isleOutline = (i: Isle, off: number, nseg = 120) =>
    Array.from({ length: nseg }, (_, k) => {
      const a = (k / nseg) * Math.PI * 2;
      const r = rIsle(i, a) + off;
      return new THREE.Vector2(i.cx + Math.cos(a) * r, -(i.cz + Math.sin(a) * r));
    });
  /** the edge of a state's land toward (x, z), `inset` back toward its centre */
  const edgeToward = (key: string, x: number, z: number, inset = 0): [number, number] => {
    if (key === 'selangor') {
      const a = Math.atan2(z, x);
      const r = rIsland(a) - inset;
      return [Math.cos(a) * r, Math.sin(a) * r];
    }
    const i = isleBy[key];
    const a = Math.atan2(z - i.cz, x - i.cx);
    const r = rIsle(i, a) - inset;
    return [i.cx + Math.cos(a) * r, i.cz + Math.sin(a) * r];
  };
  const centreOf = (key: string): [number, number] => (key === 'selangor' ? [0, 0] : [isleBy[key].cx, isleBy[key].cz]);
  {
    const grass: THREE.BufferGeometry[] = [];
    const beach: THREE.BufferGeometry[] = [];
    isles.forEach((i) => {
      const depth = Math.min(1.9, 0.9 + Math.min(i.d.rx, i.d.ry) * 0.06);
      grass.push(paint(slab(0, depth, 0.45, 0, isleOutline(i, 0)), (x, y, z, ny, c) => {
        if (ny > 0.92) c.copy(GRASS_A).lerp(GRASS_B, 0.5 + 0.5 * Math.sin(x * 0.21) * Math.sin(z * 0.17 + 1));
        else if (ny > 0.3) c.set(0xc3d497);
        else c.set(0xd9c39d).multiplyScalar(0.7 + 0.3 * clamp((y + 2.4) / 2.4, 0, 1));
      }));
      beach.push(paint(slab(0, 1.1, 0.5, -0.72, isleOutline(i, 2.0)), (_x, _y, _z, ny, c) => { c.set(ny > 0.6 ? 0xeedcb4 : 0xd6c19a); }));
      const fs = new THREE.Shape(isleOutline(i, 4.1));
      fs.holes.push(new THREE.Path(isleOutline(i, 2.3).reverse()));
      const f = mesh(new THREE.ShapeGeometry(fs, 1).rotateX(-Math.PI / 2), foam.material as THREE.Material, { cast: false, receive: false });
      f.position.y = SEA + 0.24;
      f.renderOrder = 1;
    });
    mesh(merge(grass), stdMat(), { cast: false });
    mesh(merge(beach), stdMat(), { cast: false });
  }
  const [seaCx, seaCz] = mapXZ(120, 20);
  const seaGeo = new THREE.PlaneGeometry(1500, 1500, 300, 300);
  seaGeo.translate(seaCx, 0, -seaCz);
  seaGeo.rotateX(-Math.PI / 2);
  {
    const p = seaGeo.attributes.position;
    const col = new Float32Array(p.count * 3);
    const shallow = C(0xa3dcd3);
    const deep = C(0x5aa2b0);
    for (let i = 0; i < p.count; i++) {
      const x = p.getX(i);
      const z = p.getZ(i);
      let gap = Math.hypot(x, z) - rIsland(Math.atan2(-z, x));
      for (const i of isles) {
        const dx = x - i.cx;
        const dz = z - i.cz;
        if (Math.abs(dx) > 90 || Math.abs(dz) > 90) continue;
        gap = Math.min(gap, Math.hypot(dx, dz) - rIsle(i, Math.atan2(dz, dx)));
      }
      const k = smooth(clamp((gap - 3) / 17, 0, 1));
      _c.copy(shallow).lerp(deep, k);
      col[i * 3] = _c.r;
      col[i * 3 + 1] = _c.g;
      col[i * 3 + 2] = _c.b;
    }
    seaGeo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    seaGeo.deleteAttribute('uv');
  }
  const seaTime = { value: 0 };
  const seaMat = stdMat({ roughness: 0.78 });
  seaMat.onBeforeCompile = (sh) => {
    // faceted low-poly swell on the GPU: three sines, under 0.21 units
    sh.uniforms.uTime = seaTime;
    sh.vertexShader =
      'uniform float uTime;\n' +
      sh.vertexShader.replace(
        '#include <begin_vertex>',
        `#include <begin_vertex>
      transformed.y += sin(position.x * 0.31 + uTime * 0.9) * 0.10 + sin(position.z * 0.37 - uTime * 0.7) * 0.08 + sin((position.x - position.z) * 0.83 + uTime * 1.5) * 0.03;`,
      );
  };
  mesh(seaGeo, seaMat, { cast: false, receive: false }).position.y = SEA;

  /* ======== streets: plaza, ring road, high street, spokes, port road, bridge; dashed centre lines ======== */
  const HS = 20.3;
  const RING = 10.1;
  const SPOKES = [20, 110, 200, 257];
  const SPOKE_D = 257;
  const BRIDGE_D = 287;
  const PA = 232;
  const ROAD = 0xd8d1c4;
  const PAVE = 0xece4d4;
  const PAVE2 = 0xe1d6c2;
  const ring = (r0: number, r1: number, seg: number, y: number, col: number) => P(keep(new THREE.RingGeometry(r0, r1, seg).rotateX(-Math.PI / 2)), col, 0, y, 0);
  const disc = (r: number, y: number, col: number) => P(keep(new THREE.CircleGeometry(r, 64).rotateX(-Math.PI / 2)), col, 0, y, 0);
  const radialRoad = (deg: number, r0: number, r1: number, w = 2.2) => {
    const [x, z] = polar((r0 + r1) / 2, deg);
    return P(BOX, ROAD, x, 0, z, w, 0.04, r1 - r0, faceOut(deg));
  };
  mesh(
    merge([
      disc(9.0, 0.025, PAVE), disc(3.6, 0.035, PAVE2), ring(RING - 1.1, RING + 1.1, 96, 0.03, ROAD), ring(HS - 1.1, HS + 1.1, 160, 0.03, ROAD),
      ...SPOKES.map((d) => radialRoad(d, RING + 1.0, HS - 1.0)), radialRoad(PA, HS + 1.0, 25.4, 2.6), radialRoad(BRIDGE_D, HS + 1.0, 29.0), radialRoad(44, HS + 1.0, 29.0), radialRoad(92, HS + 1.0, 29.0),
    ]),
    stdMat(),
    { cast: false },
  );
  const dashes: [number, number, number, number][] = [];
  const dashRing = (r: number) => {
    const k = Math.floor((2 * Math.PI * r) / 1.7);
    for (let i = 0; i < k; i++) {
      const a = (i / k) * 360;
      const [x, z] = polar(r, a);
      dashes.push([x, 0.035, z, faceTo(-Math.sin(a * DEG), Math.cos(a * DEG))]);
    }
  };
  const dashLine = (deg: number, r0: number, r1: number, y = 0.045) => {
    for (let r = r0; r <= r1; r += 1.7) {
      const [x, z] = polar(r, deg);
      dashes.push([x, y, z, faceOut(deg)]);
    }
  };
  dashRing(RING);
  dashRing(HS);
  SPOKES.forEach((d) => dashLine(d, RING + 2, HS - 2));

  /* ======== TOWN-PROJECT-CITY: causeways between states (the live bridge, generalised) and each state's street ======== */
  const causeway = (ax: number, az: number, bx: number, bz: number, parts: THREE.BufferGeometry[]) => {
    const len = Math.hypot(bx - ax, bz - az);
    const ry = faceTo(bx - ax, bz - az);
    const cx = (ax + bx) / 2;
    const cz = (az + bz) / 2;
    parts.push(P(BOX, ROAD, cx, -0.32, cz, 2.6, 0.38, len, ry), P(BOX, 0xb8b0a3, cx, -0.62, cz, 2.9, 0.3, len, ry));
    const sx = Math.cos(ry);
    const sz = -Math.sin(ry);
    for (const side of [-1.4, 1.4]) parts.push(P(BOX, 0xf4f1ea, cx + sx * side, 0.06, cz + sz * side, 0.12, 0.28, len, ry));
    const pier = CYL(0.42, 0.5, 2.6, 8);
    for (let d = 5; d < len - 4; d += 7) parts.push(P(pier, 0xb8b0a3, ax + ((bx - ax) * d) / len, -3.0, az + ((bz - az) * d) / len));
    for (let d = 1; d < len; d += 1.7) dashes.push([ax + ((bx - ax) * d) / len, 0.065, az + ((bz - az) * d) / len, ry]);
  };
  /** a state's street: through its centre along the way the causeway arrives (west to east for a state reached by sea) */
  interface Street { key: string; ox: number; oz: number; ux: number; uz: number; len: number }
  const streets: Record<string, Street> = {};
  {
    const parts: THREE.BufferGeometry[] = [];
    isles.forEach((i) => {
      if (i.d.parent && i.d.key !== 'perak') {
        const [pcx, pcz] = centreOf(i.d.parent);
        const from = i.d.parent === 'selangor' ? polar(26, i.d.exit ?? 0) : edgeToward(i.d.parent, i.cx, i.cz, 2.0);
        const to = edgeToward(i.d.key, pcx, pcz, 2.0);
        causeway(from[0], from[1], to[0], to[1], parts);
      }
      const [e0x, e0z] = edgeToward(i.d.key, i.cx - i.ux * 99, i.cz - i.uz * 99, 2.2);
      const [e1x, e1z] = edgeToward(i.d.key, i.cx + i.ux * 99, i.cz + i.uz * 99, 2.2);
      const len = Math.hypot(e1x - e0x, e1z - e0z);
      streets[i.d.key] = { key: i.d.key, ox: e0x, oz: e0z, ux: i.ux, uz: i.uz, len };
      const ry = faceTo(i.ux, i.uz);
      parts.push(P(BOX, PAVE, (e0x + e1x) / 2, 0.02, (e0z + e1z) / 2, 5.4, 0.035, len, ry), P(BOX, ROAD, (e0x + e1x) / 2, 0.03, (e0z + e1z) / 2, 2.2, 0.04, len, ry));
      for (let d = 1; d < len - 0.5; d += 1.7) dashes.push([e0x + i.ux * d, 0.045, e0z + i.uz * d, ry]);
    });
    mesh(merge(parts), stdMat(), { cast: false });
  }
  /** a point on a state's street, `along` units in from where the causeway lands, `side` units off its centre line */
  const streetAt = (key: string, along: number, side = 0): [number, number] => {
    const s = streets[key];
    return [s.ox + s.ux * along + s.uz * side, s.oz + s.uz * along - s.ux * side];
  };
  const dashM = inst(P(BOX, 0xffffff, 0, 0, 0, 0.13, 0.02, 0.6), stdMat({ roughness: 0.7 }), dashes.length, 'dashes', { cast: false });
  dashes.forEach(([x, y, z, ry], i) => setInst(dashM, i, x, y, z, ry));
  {
    // the bridge: a causeway off the island to customers outside the town
    const parts: THREE.BufferGeometry[] = [];
    const [pk0, pk1] = edgeToward('perak', ...polar(26, BRIDGE_D), 2.0);
    const len = Math.hypot(pk0, pk1) - 26;
    const [cx, cz] = polar(26 + len / 2, BRIDGE_D);
    const ry = faceOut(BRIDGE_D);
    parts.push(P(BOX, ROAD, cx, -0.32, cz, 2.6, 0.38, len, ry), P(BOX, 0xb8b0a3, cx, -0.62, cz, 2.9, 0.3, len, ry));
    for (const side of [-1.4, 1.4]) {
      const ox = Math.cos(BRIDGE_D * DEG + Math.PI / 2) * side;
      const oz = Math.sin(BRIDGE_D * DEG + Math.PI / 2) * side;
      parts.push(P(BOX, 0xf4f1ea, cx + ox, 0.06, cz + oz, 0.12, 0.28, len, ry));
    }
    const pier = CYL(0.42, 0.5, 2.6, 8);
    for (let r = 31; r < 26 + len - 3; r += 7) {
      const [x, z] = polar(r, BRIDGE_D);
      parts.push(P(pier, 0xb8b0a3, x, -3.0, z));
    }
    mesh(merge(parts), stdMat());
  }

  /* ======== scoreboard on the plaza: the day's figures, on a plinth, facing the camera ======== */
  const boardCv = document.createElement('canvas');
  boardCv.width = 1024;
  boardCv.height = 420;
  const boardTex = new THREE.CanvasTexture(boardCv);
  boardTex.colorSpace = THREE.SRGBColorSpace;
  boardTex.anisotropy = 8;
  const pct = changePercent(snapshot);
  const startAmount = Number((beat && prev?.today.amount) ?? snapshot.today.amount ?? 0);
  const startInv = beat && prev ? prev.today.invoice_count : snapshot.today.invoice_count;
  const board = { amount: startAmount, inv: startInv };
  let boardAnim: { from: { amount: number; inv: number }; t: number; dur: number } | null = null;
  function drawBoard() {
    const g = boardCv.getContext('2d');
    if (g) {
      g.clearRect(0, 0, 1024, 420);
      g.fillStyle = '#132033';
      g.beginPath();
      g.roundRect(0, 0, 1024, 420, 28);
      g.fill();
      g.strokeStyle = 'rgba(255,255,255,0.08)';
      g.lineWidth = 4;
      g.beginPath();
      g.roundRect(14, 14, 996, 392, 18);
      g.stroke();
      g.textAlign = 'center';
      g.fillStyle = '#8fa3bd';
      g.font = '600 40px Inter, sans-serif';
      g.fillText(night ? 'CLOSED FOR THE DAY' : 'SOLD TODAY', 512, 70);
      g.fillStyle = '#ffffff';
      g.font = '700 124px Inter, sans-serif';
      const inv = `${count(Math.round(board.inv))} invoices`;
      g.fillText(full ? rm0(String(board.amount)) : inv, 512, 196);
      g.font = '600 44px Inter, sans-serif';
      g.fillStyle = '#c8d3e1';
      const vs = pct == null || !snapshot.compare ? '' : `${pct >= 0 ? '▲' : '▼'} ${Math.abs(pct).toFixed(0)}% vs all of ${snapshot.compare.label}`;
      g.fillText((full ? `${inv}   ` : '') + vs, 512, 270);
      const split = (snapshot.today as { split?: Record<'dealer' | 'project' | 'other', { amount?: string; invoice_count: number }> }).split;
      if (split) {
        g.font = '600 40px Inter, sans-serif';
        const part = (label: string, v: { amount?: string; invoice_count: number }) => `${label} ${v.amount != null ? rm0(v.amount) : count(v.invoice_count)}`;
        const line = [part('Dealers', split.dealer), part('Projects', split.project), part('Other', split.other)].join('  ·  ');
        g.fillStyle = '#f2c46d';
        g.fillText(line + (split.dealer.amount == null ? ' invoices' : ''), 512, 352);
      }
    }
    boardTex.needsUpdate = true;
    invalidate();
  }
  const boardGroup = new THREE.Group();
  scene.add(boardGroup);
  mesh(
    merge(
      [
        P(CYL(2.3, 2.45, 0.26, 28), 0xe2d8c6), P(CYL(1.75, 1.9, 0.24, 28), 0xd6cab5, 0, 0.26),
        P(BOX, 0x334155, -4.9, 0.5, 0, 0.36, 4.2, 0.36), P(BOX, 0x334155, 4.9, 0.5, 0, 0.36, 4.2, 0.36), P(BOX, 0x1b2638, 0, 4.5, 0, 12.6, 5.3, 0.36),
      ],
      0.3,
    ),
    stdMat(),
    { parent: boardGroup },
  );
  const boardFace = mesh(new THREE.PlaneGeometry(12.3, 5.04), basicMat({ map: boardTex }), { cast: false, receive: false, parent: boardGroup });
  boardFace.position.set(0, 7.15, 0.19);
  pickables.push([boardFace, () => select({ kind: 'sales' }), () => ({ kind: 'sales' })]);

  /* ======== shops: storeys = 90-day rank, roofs vary; bought today = amber roof, lit windows, warm light pool ======== */
  const FH = 1.15;
  const SW = 2.3;
  const SD = 2.0;
  const WALLS = [0xf7efe3, 0xf3e3d2, 0xeaf0e7, 0xedf0f5, 0xf6e9d8, 0xf1ebe2];
  const SLATE = [0x7d8da2, 0x8a97a8, 0x6f8097, 0x94a1b1];
  const LIT_ROOF = 0xf2a63a;
  const WIN = { litDay: C(0xffcd70), litNight: C(0xffdd94), offDay: C(0x42566b), offNight: C(0x1c2533) };
  const { drawn, tagged, others } = sceneSelection(snapshot);
  const shopsK = drawn.filter((s) => s.kind === 'shop');
  const order = [...shopsK];
  drawn.filter((s) => s.kind !== 'shop').forEach((s, k) => order.splice(Math.min(order.length, 5 + k * 10), 0, s));
  const beatKeys = new Set(beat?.shops.map((s) => s.key) ?? []);
  const prevDocs = new Map(prev?.shops.map((s) => [s.key, s.today_docs]) ?? []);
  // TOWN-PROJECT-CITY: a shop stands in its own state; Selangor keeps the live high street (now -60..30, the
  // project quarter takes 52..86), every other state its own street; no state = the "State not set" islet
  const stateOf = (s: TownShop) => stateKeyOf(s.state);
  const home = order.filter((s) => stateOf(s) === 'selangor');
  const A0 = 104;
  const A1 = 214;
  const perState: Record<string, number> = {};
  const v3 = (p: [number, number]) => new THREE.Vector3(p[0], 0, p[1]);
  /** the road from the live high street to `along` units down a state's street: exit bearing + waypoints over each causeway */
  const countIn = (list: { state: string | null }[] | undefined, st: string) => (list ?? []).filter((r) => stateKeyOf(r.state) === st).length;
  const extra = snapshot;
  /** where a state's row of buildings starts down its street, so shops + sites + towers sit centred on it */
  const startOf = (st: string) => {
    const shops = order.filter((s) => stateOf(s) === st).length;
    const len = Math.ceil(shops / 2) * 2.9 + Math.ceil(countIn(extra.projects?.sites, st) / 2) * 3.7 + Math.ceil(countIn(extra.trading_houses?.rows, st) / 2) * 3.0 + 2.6;
    return Math.max(3.4, (streets[st].len - len) / 2);
  };
  const routeTo = (st: string, along: number): { exit: number; tail: THREE.Vector3[] } | null => {
    const chain: string[] = [];
    for (let k: string | undefined = st; k && k !== 'selangor'; k = STATE_BY[k].parent) chain.unshift(k);
    if (!chain.length || STATE_BY[chain[0]].parent !== 'selangor') return null; // reached by sea, not by road
    const tail: THREE.Vector3[] = [];
    let prev = 'selangor';
    for (const k of chain) {
      if (prev !== 'selangor') tail.push(v3(centreOf(prev)), v3(edgeToward(prev, ...centreOf(k), 2.0)));
      tail.push(v3(edgeToward(k, ...centreOf(prev), 2.0)));
      prev = k;
    }
    tail.push(v3(streetAt(st, along)));
    return { exit: STATE_BY[chain[0]].exit ?? BRIDGE_D, tail };
  };
  const slots: Slot[] = order.map((s, i) => {
    const st = stateOf(s);
    let a = NaN;
    let inner = false;
    let x: number;
    let z: number;
    let ry: number;
    let road: { exit: number; tail: THREE.Vector3[] } | null = null;
    if (st === 'selangor') {
      const hi = home.indexOf(s);
      a = A0 + ((A1 - A0) * hi) / Math.max(1, home.length - 1);
      inner = hi % 2 === 0;
      [x, z] = polar(inner ? 17.6 : 23.0, a);
      ry = inner ? faceOut(a) : faceIn(a);
    } else {
      const k = (perState[st] = (perState[st] ?? -1) + 1);
      const side = k % 2 ? 1 : -1;
      const along = startOf(st) + 0.8 + Math.floor(k / 2) * 2.9;
      [x, z] = streetAt(st, along, side * 2.75);
      const S = streets[st];
      ry = faceTo(-S.uz * side, S.ux * side);
      road = routeTo(st, along);
    }
    const rank = s.rank ?? shopsK.indexOf(s) + 1;
    const floors = s.kind === 'shop' ? (rank <= 6 ? 3 : rank <= 16 ? 2 : 1) : 0;
    // a shop that is about to play the sale beat starts the way the last snapshot showed it
    const lit = beatKeys.has(s.key) ? (prevDocs.get(s.key) ?? 0) > 0 : s.today_docs > 0;
    return {
      s, a, x, z, ry, inner, floors, stall: s.kind !== 'shop', lit, litK: lit ? 1 : 0, exit: road?.exit, tail: road?.tail,
      variant: [0, 1, 2, 0, 2, 1][i % 6], tint: WALLS[(i * 5) % WALLS.length], slate: SLATE[(i * 3) % SLATE.length],
      h: s.kind === 'shop' ? floors * FH + 0.95 : 2.0, lift: 0, liftTo: 0, sq: 0, rise: 0, delay: 0, gi: -1, ui: [], ri: -1, si: -1, pool: -1, flash: 0,
    };
  });
  const gGeo = merge(
    [
      P(BOX, 0xffffff, 0, 0, 0, SW, FH, SD), P(BOX, 0xd3cabb, 0, 0, 0, SW + 0.08, 0.16, SD + 0.08), P(BOX, 0xe6dccb, 0, FH - 0.06, 0, SW + 0.12, 0.08, SD + 0.12),
      P(BOX, 0x6d513f, 0.62, 0, SD / 2 + 0.005, 0.5, 0.84, 0.04), P(BOX, 0x7d9a8f, -0.38, 0.86, SD / 2 + 0.2, 1.25, 0.05, 0.44, 0, 0.32),
    ],
    0.36,
  );
  const uGeo = merge([
    P(BOX, 0xffffff, 0, 0, 0, SW, FH, SD), P(BOX, 0xe6dccb, 0, FH - 0.06, 0, SW + 0.12, 0.08, SD + 0.12),
    ...[-0.52, 0.52].map((x) => P(BOX, 0xe2d7c4, x, 0.2, SD / 2 + 0.04, 0.56, 0.05, 0.1)),
  ]);
  const wgGeo = merge([
    P(BOX, 0xffffff, -0.38, 0.27, SD / 2 + 0.012, 1.05, 0.52, 0.03), P(BOX, 0xffffff, SW / 2 + 0.012, 0.4, 0.05, 0.03, 0.42, 0.62),
    P(BOX, 0xffffff, -SW / 2 - 0.012, 0.4, 0.05, 0.03, 0.42, 0.62),
  ]);
  const wuGeo = merge([
    ...[-0.52, 0.52].map((x) => P(BOX, 0xffffff, x, 0.26, SD / 2 + 0.012, 0.44, 0.52, 0.03)),
    P(BOX, 0xffffff, SW / 2 + 0.012, 0.3, 0, 0.03, 0.46, 0.5), P(BOX, 0xffffff, -SW / 2 - 0.012, 0.3, 0, 0.03, 0.46, 0.5),
  ]);
  const chimney = () => P(BOX, 0xbcb0a2, 0.55, 0.25, -0.38, 0.28, 0.75, 0.28);
  const roofGeos = [
    merge([P(TRI, 0xffffff, 0, 0, 0, SW + 0.36, 0.95, SD + 0.32), chimney()]), // gable end to the street
    merge([P(TRI, 0xffffff, 0, 0, 0, SD + 0.32, 0.85, SW + 0.36, Math.PI / 2), chimney()]), // ridge along the street
    merge([P(HIP, 0xffffff, 0, 0, 0, SW + 0.36, 0.9, SD + 0.32)]), // hipped
  ];
  const stallGeo = merge(
    [
      P(BOX, 0xe6dccb, 0, 0, 0, 1.9, 0.8, 1.1), P(BOX, 0xc9b79c, 0, 0.8, 0, 2.0, 0.06, 1.2),
      ...[-0.9, 0.9].flatMap((x) => [-0.5, 0.5].map((z) => P(BOX, 0x8b6b4f, x, 0, z, 0.08, 1.85, 0.08))),
      ...Array.from({ length: 6 }, (_, k) => P(BOX, k % 2 ? 0xfff3df : 0xf0a23a, -0.85 + k * 0.34, 1.82, 0.05, 0.34, 0.07, 1.5, 0, 0.18)),
    ],
    0.3,
  );
  const shopN = slots.filter((s) => !s.stall).length;
  const upperN = slots.reduce((sum, s) => sum + Math.max(0, s.floors - 1), 0);
  const gM = inst(gGeo, stdMat(), shopN, 'shops');
  const uM = inst(uGeo, stdMat(), upperN, 'upper floors');
  const wgM = inst(wgGeo, basicMat(), shopN, 'windows', { cast: false, receive: false });
  const wuM = inst(wuGeo, basicMat(), upperN, 'upper windows', { cast: false, receive: false });
  const roofMs = roofGeos.map((g, v) => inst(g, stdMat({ roughness: 0.8 }), slots.filter((s) => !s.stall && s.variant === v).length, 'roofs'));
  const stallM = inst(stallGeo, stdMat(), slots.filter((s) => s.stall).length, 'stalls');
  const gTo: Slot[] = [];
  const uTo: Slot[] = [];
  const rTo: Slot[][] = [[], [], []];
  const sTo: Slot[] = [];
  slots.forEach((s) => {
    if (s.stall) {
      s.si = sTo.length;
      sTo.push(s);
      stallM.setColorAt(s.si, C(0xffffff));
      return;
    }
    s.gi = gTo.length;
    gTo.push(s);
    gM.setColorAt(s.gi, C(s.tint));
    for (let k = 1; k < s.floors; k++) {
      s.ui.push(uTo.length);
      uTo.push(s);
      uM.setColorAt(s.ui[s.ui.length - 1], C(s.tint));
    }
    s.ri = rTo[s.variant].length;
    rTo[s.variant].push(s);
  });
  let hour = hourOf(snapshot);
  function shopColours(s: Slot) {
    if (s.stall) return;
    const dark = hour >= 19.5;
    const k = s.litK;
    roofMs[s.variant].setColorAt(s.ri, _c.set(s.slate).lerp(C(LIT_ROOF), k));
    if (roofMs[s.variant].instanceColor) roofMs[s.variant].instanceColor!.needsUpdate = true;
    const on = dark ? WIN.litNight : WIN.litDay;
    const off = dark ? WIN.offNight : WIN.offDay;
    wgM.setColorAt(s.gi, _c.copy(off).lerp(on, k));
    s.ui.forEach((ui) => wuM.setColorAt(ui, _c.copy(off).lerp(on, k)));
    if (wgM.instanceColor) wgM.instanceColor.needsUpdate = true;
    if (wuM.instanceColor) wuM.instanceColor.needsUpdate = true;
  }
  function placeShop(s: Slot) {
    const y0 = s.rise + s.lift;
    const k = 1 + s.sq;
    if (s.stall) {
      setInst(stallM, s.si, s.x, y0, s.z, s.ry, 1, k, 1);
      return;
    }
    setInst(gM, s.gi, s.x, y0, s.z, s.ry, 1, k, 1);
    setInst(wgM, s.gi, s.x, y0, s.z, s.ry, 1, k, 1);
    s.ui.forEach((ui, j) => {
      const y = y0 + FH * (j + 1) * k;
      setInst(uM, ui, s.x, y, s.z, s.ry, 1, k, 1);
      setInst(wuM, ui, s.x, y, s.z, s.ry, 1, k, 1);
    });
    setInst(roofMs[s.variant], s.ri, s.x, y0 + FH * s.floors * k, s.z, s.ry, 1, k, 1);
  }
  slots.forEach((s) => {
    shopColours(s);
    placeShop(s);
  });
  const shopSubject = (s: Slot): TipSubject => ({ kind: 'shop', shop: s.s });
  const shopMaps: [THREE.InstancedMesh, Slot[]][] = [[gM, gTo], [wgM, gTo], [uM, uTo], [wuM, uTo], [stallM, sTo], ...roofMs.map((m, v): [THREE.InstancedMesh, Slot[]] => [m, rTo[v]])];
  shopMaps.forEach(([m, map]) =>
    pickables.push([
      m,
      (i) => map[i] && select({ kind: 'shop', key: map[i].s.key }),
      (i) => (map[i] ? shopSubject(map[i]) : null),
      (i) => map[i] ?? null,
    ]),
  );
  // warm light pools on the pavement in front of shops that bought today (static: the colour carries the state)
  const poolMat = basicMat({
    map: radTex([[0, 'rgba(255,196,92,0.95)'], [0.45, 'rgba(255,170,60,0.38)'], [1, 'rgba(255,160,50,0)']]),
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.55,
  });
  const poolM = inst(keep(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2)), poolMat, slots.length, 'pools', { cast: false, receive: false });
  poolM.count = 0;
  function placePool(s: Slot) {
    if (s.pool < 0) return;
    const x = s.x + Math.sin(s.ry) * (SD / 2 + 0.95);
    const z = s.z + Math.cos(s.ry) * (SD / 2 + 0.95);
    const k = (3.0 + 1.6 * EASE(s.flash)) * Math.min(1, s.litK * 1.4);
    setInst(poolM, s.pool, x, 0.06, z, 0, k, 1, k);
  }
  function addPool(s: Slot) {
    if (s.pool >= 0) return;
    s.pool = poolM.count++;
    placePool(s);
  }
  slots.filter((s) => s.lit).forEach(addPool);


  /* ======== TOWN-PROJECT-CITY: project sites (look = the project's own timeline; flag = our sales stage) and trading
   * houses (slate-blue glass towers, lit on a project invoice today), in the same materials as the live town ======== */
  const mapSnap = snapshot;
  const SIDE = 3.0;
  const H2 = SIDE / 2;
  const fence = () => [
    ...([[0, -H2, SIDE, 0.06], [-H2, 0, 0.06, SIDE], [H2, 0, 0.06, SIDE], [-0.95, H2, 1.1, 0.06], [0.95, H2, 1.1, 0.06]] as number[][]).map(([x, z, w, d]) => P(BOX, 0xdfe5eb, x, 0, z, w, 0.55, d)),
    ...[-H2, H2].flatMap((x) => [-H2, H2].map((z) => P(BOX, 0x8a96a3, x, 0, z, 0.09, 0.62, 0.09))),
  ];
  const siteBoard = (x: number, z: number, face: number, band: number) => [
    P(BOX, 0x7d8896, x - 0.38, 0, z, 0.06, 0.95, 0.06), P(BOX, 0x7d8896, x + 0.38, 0, z, 0.06, 0.95, 0.06),
    P(BOX, face, x, 0.58, z, 1.0, 0.56, 0.05), P(BOX, band, x, 0.98, z, 1.0, 0.11, 0.06),
  ];
  const crane = (h: number) => [
    P(BOX, 0xe9b23c, 1.05, 0, -1.05, 0.2, h, 0.2), P(BOX, 0xe9b23c, 0.1, h, -1.05, 3.6, 0.15, 0.17), P(BOX, 0x39434f, -1.25, h - 0.18, -1.05, 0.55, 0.3, 0.42),
    P(BOX, 0xf1ece2, 1.05, h - 0.55, -0.82, 0.36, 0.42, 0.36), P(BOX, 0x2b313a, 0.75, h - 1.3, -1.05, 0.03, 1.3, 0.03),
  ];
  const bands = (w: number, h: number, step: number, col: number) => {
    const out: THREE.BufferGeometry[] = [];
    for (let y = 0.45; y < h - 0.3; y += step) out.push(P(BOX, col, 0, y, 0, w + 0.04, 0.32, w + 0.04));
    return out;
  };
  function siteGeo(look: string) {
    const pad = (c: number) => P(BOX, c, 0, 0, 0, SIDE, 0.06, SIDE);
    const parts: THREE.BufferGeometry[] = [];
    if (look === 'plain') {
      // a tidy prepared plot: levelled pad, neat edging, survey pegs, a hoarding with the Sorento band, a site cabin, a board
      parts.push(pad(0xd9c7a5), ...([[0, -H2, SIDE + 0.1, 0.12], [0, H2, SIDE + 0.1, 0.12], [-H2, 0, 0.12, SIDE + 0.1], [H2, 0, 0.12, SIDE + 0.1]] as number[][]).map(([x, z, w, d]) => P(BOX, 0xf4f1ea, x, 0, z, w, 0.12, d)));
      parts.push(...[[-0.7, -0.6], [0.7, -0.6], [-0.7, 0.4], [0.7, 0.4]].map(([x, z]) => P(BOX, 0xdc4b3e, x, 0.06, z, 0.07, 0.36, 0.07)));
      parts.push(P(BOX, 0xffffff, 0, 0, -H2 + 0.05, SIDE - 0.2, 0.72, 0.07), P(BOX, 0x2f63d0, 0, 0.5, -H2 + 0.03, SIDE - 0.2, 0.13, 0.08));
      parts.push(P(BOX, 0xe6ebf1, 0.85, 0.06, 0.55, 1.05, 0.62, 0.62), P(BOX, 0x94a3b8, 0.85, 0.68, 0.55, 1.12, 0.07, 0.69), P(BOX, 0x42566b, 0.85, 0.3, 0.87, 0.4, 0.24, 0.02));
      parts.push(...siteBoard(-0.75, 1.0, 0xffffff, 0x2f63d0));
    } else if (look === 'before') {
      parts.push(pad(0xcbb796), ...fence());
      parts.push(...([[0, -0.75, 1.9, 0.07], [0, 0.55, 1.9, 0.07], [-0.95, -0.1, 0.07, 1.37], [0.95, -0.1, 0.07, 1.37]] as number[][]).map(([x, z, w, d]) => P(BOX, 0xffffff, x, 0.06, z, w, 0.02, d)));
      parts.push(...siteBoard(-0.6, 1.05, 0xfef3c7, 0xf59e0b));
    } else if (look === 'ground') {
      parts.push(pad(0xc8b69a), ...fence(), P(BOX, 0x9ca3af, -0.15, 0.06, -0.3, 2.1, 0.22, 1.8));
      parts.push(P(BOX, 0x334155, 0.8, 0.06, 0.8, 0.95, 0.22, 0.62), P(BOX, 0xe9b23c, 0.8, 0.28, 0.8, 0.75, 0.42, 0.52), P(BOX, 0xe9b23c, 0.5, 0.66, 0.55, 0.14, 0.14, 1.05, 0.6, 0.5), P(BOX, 0x39434f, 0.85, 0.72, 0.9, 0.36, 0.3, 0.4));
    } else if (look === 'frame') {
      parts.push(pad(0xc8b69a), P(BOX, 0x9ca3af, 0, 0.06, 0, 2.5, 0.22, 2.5));
      for (const [x, z] of [[-1.1, -1.1], [1.1, -1.1], [-1.1, 1.1], [1.1, 1.1], [0, -1.1], [0, 1.1]]) parts.push(P(BOX, 0x94a3b8, x, 0.25, z, 0.14, 3.4, 0.14));
      for (let y = 1.15; y < 3.7; y += 1.15) parts.push(P(BOX, 0xb4bcc6, 0, y, 0, 2.4, 0.1, 2.4));
      parts.push(...crane(5.8));
    } else if (look === 'clad') {
      parts.push(pad(0xc8b69a), P(BOX, 0xe7e2d6, 0, 0.06, 0, 2.4, 3.4, 2.4), ...bands(2.4, 3.4, 0.95, 0x7fa0bf));
      parts.push(...[-1.1, 1.1].flatMap((x) => [-1.1, 1.1].map((z) => P(BOX, 0x94a3b8, x, 3.4, z, 0.14, 0.9, 0.14))), P(BOX, 0xb4bcc6, 0, 4.3, 0, 2.4, 0.1, 2.4), ...crane(6.2));
    } else {
      parts.push(pad(0xddd5c6), P(BOX, 0xf3efe6, 0, 0.06, 0, 2.45, 4.3, 2.45), ...bands(2.45, 4.3, 0.92, 0x8aa6c1), P(BOX, 0xd6d0c4, 0, 4.36, 0, 2.6, 0.22, 2.6), P(BOX, 0x86c17a, 1.15, 0.06, 1.25, 0.5, 0.5, 0.4));
    }
    return merge(parts, 0.3);
  }
  const siteFlagGeo = keep(new THREE.PlaneGeometry(0.85, 0.5, 8, 1).translate(0.425, 0, 0));
  const pennantGeo = (() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 0, 0.3, 0, 0.5, 0.15, 0], 3));
    g.computeVertexNormals();
    return keep(g);
  })();
  const extraBlobs: [number, number, number, number, number][] = [];
  const mapBlockers: [number, number, number][] = [];
  const sitesBy: Record<string, TownSite[]> = {};
  (mapSnap.projects?.sites ?? []).forEach((p) => (sitesBy[stateKeyOf(p.state)] ??= []).push(p));
  const towersBy: Record<string, TownTradingHouse[]> = {};
  (mapSnap.trading_houses?.rows ?? []).forEach((r) => (towersBy[stateKeyOf(r.state)] ??= []).push(r));
  /** where each state's n-th site / tower stands: Selangor's on the live island (the arc 52..86 beside the high street),
   * every other state's further down its own street, past its shops */
  const quarterAt = (st: string, k: number, tower: boolean): [number, number, number] => {
    if (st === 'selangor') {
      if (tower) {
        const a = [60, 77, 69][k % 3];
        const [x, z] = polar(16.4, a);
        return [x, z, faceOut(a)];
      }
      const a = 56 + (k % 3) * 12.5;
      const [x, z] = polar(24.3, a);
      return [x, z, faceIn(a)];
    }
    const shops = perState[st] == null ? 0 : perState[st] + 1;
    const nSites = sitesBy[st]?.length ?? 0;
    const along0 = startOf(st) + 0.8 + Math.ceil(shops / 2) * 2.9 + 0.6;
    const side = k % 2 ? 1 : -1;
    const along = tower ? along0 + Math.ceil(nSites / 2) * 3.7 + 1.4 + Math.floor(k / 2) * 3.0 : along0 + 1.5 + Math.floor(k / 2) * 3.7;
    const [x, z] = streetAt(st, along, side * (tower ? 3.1 : 3.4));
    const S = streets[st];
    return [x, z, faceTo(-S.uz * side, S.ux * side)];
  };
  const quarterGate = (st: string): { a: number; exit?: number; tail?: THREE.Vector3[] } | null => {
    if (st === 'selangor') return { a: 68 };
    const shops = perState[st] == null ? 0 : perState[st] + 1;
    const road = routeTo(st, startOf(st) + 0.8 + Math.ceil(shops / 2) * 2.9 + 1.4);
    return road ? { a: NaN, ...road } : null;
  };
  const siteFlags: THREE.Mesh[] = [];
  Object.entries(sitesBy).forEach(([st, list]) =>
    list.forEach((p, k) => {
      const [x, z, ry] = quarterAt(st, k, false);
      const look = siteLook(p, snapshot.day);
      const g = new THREE.Group();
      g.position.set(x, 0, z);
      g.rotation.y = ry;
      scene.add(g);
      const m = mesh(siteGeo(look), stdMat(), { parent: g });
      mesh(merge([P(CYL(0.035, 0.035, p.final_negotiation ? 1.75 : 1.4, 6), 0x64748b)]), stdMat(), { parent: g }).position.set(1.3, 0, 1.3);
      const f = mesh(siteFlagGeo.clone(), new THREE.MeshStandardMaterial({ color: (p.stage && STAGES[p.stage]?.color) || 0x9ca3af, side: THREE.DoubleSide, flatShading: true, roughness: 0.8 }), { parent: g });
      f.position.set(1.3, 1.12, 1.3);
      siteFlags.push(f);
      if (p.final_negotiation) mesh(pennantGeo, basicMat({ color: 0xdc2626, side: THREE.DoubleSide }), { parent: g, cast: false }).position.set(1.3, 1.45, 1.3);
      const tip = (): TipSubject => ({ kind: 'site', site: p });
      const open = () => select({ kind: 'site', key: p.key });
      pickables.push([m, open, tip], [f, open, tip]);
      extraBlobs.push([x, z, ry, SIDE * 1.15, SIDE * 1.15]);
      mapBlockers.push([x, z, 2.4]);
    }),
  );
  const towerGeo = merge(
    [
      P(BOX, 0x4f6580, 0, 0, 0, 2.4, 6.6, 2.4), P(BOX, 0x3d5068, 0, 0, 0, 2.5, 0.2, 2.5), P(BOX, 0x334255, 0, 6.6, 0, 2.55, 0.22, 2.55),
      P(BOX, 0x8a96a3, 0.45, 6.82, -0.35, 0.9, 0.45, 0.7), P(BOX, 0x5b6673, -0.6, 6.82, 0.5, 0.4, 0.3, 0.4), P(BOX, 0x2d3a4b, 0, 0, 1.21, 0.8, 0.95, 0.03),
    ],
    0.3,
  );
  const towerWinGeo = merge(Array.from({ length: 6 }, (_, k) => P(BOX, 0xffffff, 0, 1.15 + k * 0.92, 0, 2.44, 0.42, 2.44)));
  const towerList = Object.entries(towersBy).flatMap(([st, list]) => list.map((r, k) => ({ r, st, at: quarterAt(st, k, true) })));
  const towerM = inst(towerGeo, stdMat(), towerList.length, 'trading houses');
  const towerWinM = inst(towerWinGeo, basicMat(), towerList.length, 'trading house windows', { cast: false, receive: false });
  const towerPoolM = inst(keep(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2)), poolMat, towerList.length, 'trading house pools', { cast: false, receive: false });
  towerPoolM.count = 0;
  towerList.forEach(({ r, at: [x, z, ry] }, i) => {
    setInst(towerM, i, x, 0, z, ry);
    setInst(towerWinM, i, x, 0, z, ry);
    towerWinM.setColorAt(i, r.today_docs > 0 ? WIN.litDay : WIN.offDay);
    if (r.today_docs > 0) {
      const k = towerPoolM.count++;
      setInst(towerPoolM, k, x + Math.sin(ry) * 2.3, 0.06, z + Math.cos(ry) * 2.3, 0, 4.2, 1, 4.2);
    }
    extraBlobs.push([x, z, ry, 3.6, 3.6]);
    mapBlockers.push([x, z, 2.4]);
  });
  const towerTip = (i: number) => {
    const r = towerList[i]?.r;
    return r ? ({ kind: 'trading_house', row: r } as TipSubject) : null;
  };
  const openTower = (i: number) => towerList[i] && select({ kind: 'trading_house', key: towerList[i].r.key });
  pickables.push([towerM, openTower, towerTip], [towerWinM, openTower, towerTip]);

  /* ======== warehouses (low stock lives here), depot (lorries), approvals office ======== */
  const wh = snapshot.warehouses.slice(0, 6);
  const WHP = [[14.6, 318], [14.6, 339], [14.6, 0], [24.0, 324], [24.0, 345], [24.0, 6]];
  const whSlot = wh.map((w, i) => {
    const [r, d] = WHP[i];
    const [x, z] = polar(r, d);
    return { w, x, z, ry: r < 20 ? faceOut(d) : faceIn(d), delay: 0 };
  });
  const whGeo = merge(
    [
      P(BOX, 0xe6e9ed, 0, 0, 0, 4.4, 2.1, 3.0), P(BOX, 0xcfd5db, 0, 0, 0, 4.48, 0.18, 3.08),
      ...Array.from({ length: 7 }, (_, k) => P(BOX, 0xd2d9e0, -1.8 + k * 0.6, 0.18, 1.51, 0.08, 1.9, 0.04)),
      P(BOX, 0x8a96a3, 0.7, 0, 1.53, 1.7, 1.4, 0.05), P(BOX, 0x5b6673, -1.3, 0, 1.53, 0.55, 0.9, 0.05),
      P(BARREL, 0x8899ad, 0, 2.1, 0, 4.56, 0.85, 1.58),
    ],
    0.34,
  );
  const whM = inst(whGeo, stdMat(), whSlot.length, 'warehouses');
  whSlot.forEach((w, i) => setInst(whM, i, w.x, 0, w.z, w.ry));
  pickables.push([whM, () => select({ kind: 'low' }), (i) => ({ kind: 'warehouse', index: i })]);
  const [dx, dz] = polar(15.6, 270);
  const [spx, spz] = polar(15.6, SPOKE_D);
  const depotRy = faceTo(spx - dx, spz - dz);
  const depotF = new THREE.Vector3(Math.sin(depotRy), 0, Math.cos(depotRy));
  const depot = mesh(
    merge(
      [
        P(BOX, 0xe8edf6, 0, 0, 0, 5.2, 2.5, 3.6), P(BOX, 0xcdd6e3, 0, 0, 0, 5.3, 0.18, 3.7), P(BOX, 0x3d6fd6, 0, 2.5, 0, 5.5, 0.3, 3.9),
        P(BOX, 0x6c7886, 0, 0, 1.81, 2.7, 1.95, 0.05), P(BOX, 0x2f63d0, 0, 2.05, 1.82, 5.2, 0.32, 0.05),
      ],
      0.34,
    ),
    stdMat(),
  );
  depot.position.set(dx, 0, dz);
  depot.rotation.y = depotRy;
  pickables.push([depot, () => select({ kind: 'deliver' }), () => ({ kind: 'deliver' })]);
  const [ofx, ofz] = polar(15.2, 296);
  const office = mesh(
    merge(
      [
        P(BOX, 0xf4f0fa, 0, 0, 0, 3.4, 2.9, 2.8), P(BOX, 0xddd3ee, 0, 0, 0, 3.5, 0.18, 2.9), P(BOX, 0xe7def3, 0, 1.42, 0, 3.5, 0.08, 2.9),
        P(HIP, 0x7c5cd6, 0, 2.9, 0, 3.8, 1.2, 3.2), P(BOX, 0x5a4636, 0, 0, 1.41, 0.7, 1.05, 0.04),
        ...[-1.2, -0.45, 0.45, 1.2].map((x) => P(BOX, 0x45566a, x, 1.85, 1.41, 0.42, 0.6, 0.04)),
        ...[-1.2, 1.2].map((x) => P(BOX, 0x45566a, x, 0.45, 1.41, 0.5, 0.65, 0.04)),
      ],
      0.34,
    ),
    stdMat(),
  );
  office.position.set(ofx, 0, ofz);
  office.rotation.y = faceOut(296);
  pickables.push([office, () => select({ kind: 'approve' }), () => ({ kind: 'approve' })]);
  // contact shadows: a soft dark blob under every building
  const blobs: [number, number, number, number, number][] = [
    ...slots.map((s): [number, number, number, number, number] => [s.x, s.z, s.ry, s.stall ? 2.6 : SW * 1.55, s.stall ? 1.8 : SD * 1.6]),
    ...whSlot.map((w): [number, number, number, number, number] => [w.x, w.z, w.ry, 6.4, 4.4]),
    [dx, dz, depotRy, 7.4, 5.2], [ofx, ofz, faceOut(296), 4.9, 4.2], [0, 0, 0, 7.4, 7.4], ...extraBlobs,
  ];
  const blobMat = basicMat({
    map: radTex([[0, 'rgba(255,255,255,1)'], [0.55, 'rgba(255,255,255,0.55)'], [1, 'rgba(255,255,255,0)']]),
    color: 0x1d2a36, transparent: true, depthWrite: false, opacity: 0.4,
  });
  const blobM = inst(keep(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2)), blobMat, blobs.length, 'contact shadows', { cast: false, receive: false });
  blobs.forEach(([x, z, ry, w, d], i) => setInst(blobM, i, x, 0.05, z, ry, w, 1, d));

  /* ======== street lamps on the high street kerb: off by day, neutral white after dark ======== */
  const lampAt = slots.filter((s) => s.inner).map((s) => s.a);
  for (let a = 226; a < 410; a += 12) if (![232, 257, 287, 380, 404].some((d) => Math.abs(a - d) < 6)) lampAt.push(a % 360);
  const lampM = inst(merge([P(CYL(0.05, 0.07, 1.9, 6), 0x55606e), P(BOX, 0x55606e, 0, 1.84, 0, 0.12, 0.06, 0.12)]), stdMat(), lampAt.length, 'lamps', { receive: false });
  const headM = inst(merge([P(keep(new THREE.SphereGeometry(0.17, 8, 6)), 0xffffff, 0, 1.98, 0)]), basicMat(), lampAt.length, 'lamp heads', { cast: false, receive: false });
  const lampPoolMat = basicMat({
    map: radTex([[0, 'rgba(255,246,222,0.9)'], [0.5, 'rgba(255,240,210,0.3)'], [1, 'rgba(255,240,210,0)']]),
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0,
  });
  const lampPoolM = inst(keep(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2)), lampPoolMat, lampAt.length, 'lamp pools', { cast: false, receive: false });
  lampAt.forEach((a, i) => {
    const [x, z] = polar(21.75, a);
    setInst(lampM, i, x, 0, z);
    setInst(headM, i, x, 0, z);
    setInst(lampPoolM, i, x, 0.055, z, 0, 2.6, 1, 2.6);
    headM.setColorAt(i, C(0xe6e1d6));
  });

  /* ======== trees (seeded, kept off roads and lots), flags ======== */
  const blockers: [number, number, number][] = [...slots.map((s): [number, number, number] => [s.x, s.z, 2.0]), ...whSlot.map((w): [number, number, number] => [w.x, w.z, 3.3]), [dx, dz, 3.8], [ofx, ofz, 3.0]];
  const treeAt: [number, number][] = [[5.0, 5.0], [-5.0, 5.0], [5.0, -5.0], [-5.0, -5.0]];
  const angleOff = (deg: number, d: number) => Math.abs(((deg - d + 540) % 360) - 180);
  for (let tries = 0; treeAt.length < 52 && tries < 4000; tries++) {
    const a = rng() * Math.PI * 2;
    const r = 9.5 + rng() * (rIsland(a) - 11);
    const x = Math.cos(a) * r;
    const z = Math.sin(a) * r;
    const deg = (((a / DEG) % 360) + 360) % 360;
    if (Math.abs(r - RING) < 1.9 || Math.abs(r - HS) < 2.0) continue;
    if (SPOKES.some((d) => angleOff(deg, d) * DEG * r < 1.9 && r > RING && r < HS)) continue;
    if (angleOff(deg, BRIDGE_D) * DEG * r < 2.2 && r > HS) continue;
    if (angleOff(deg, PA) < 17 && r > HS - 1) continue;
    if ([...blockers, ...mapBlockers].some(([bx, bz, br]) => Math.hypot(x - bx, z - bz) < br)) continue;
    if ([44, 92].some((d) => angleOff(deg, d) * DEG * r < 2.2 && r > HS)) continue;
    if (treeAt.some(([tx, tz]) => Math.hypot(x - tx, z - tz) < 1.5)) continue;
    treeAt.push([x, z]);
  }
  for (const i of isles) {
    const S = streets[i.d.key];
    const want = Math.min(46, Math.round((i.d.rx * i.d.ry) / 7));
    let got = 0;
    for (let tries = 0; got < want && tries < want * 40; tries++) {
      const a = rng() * Math.PI * 2;
      const r = Math.sqrt(rng()) * (rIsle(i, a) - 2.6);
      const x = i.cx + Math.cos(a) * r;
      const z = i.cz + Math.sin(a) * r;
      const along = (x - S.ox) * S.ux + (z - S.oz) * S.uz;
      const off = Math.abs((x - S.ox) * S.uz - (z - S.oz) * S.ux);
      if (off < 3.9 && along > -1 && along < S.len + 1) continue;
      if (off < 5.8 && along > startOf(i.d.key) - 1 && along < S.len - startOf(i.d.key) + 3) continue;
      if ([...blockers, ...mapBlockers].some(([bx, bz, br]) => Math.hypot(x - bx, z - bz) < br)) continue;
      if (treeAt.some(([tx, tz]) => Math.hypot(x - tx, z - tz) < 1.5)) continue;
      treeAt.push([x, z]);
      got++;
    }
  }
  const roundTree = merge([P(CYL(0.12, 0.16, 0.75, 6), 0x8b6b4f), P(keep(new THREE.IcosahedronGeometry(0.85, 0)), 0x7fae6a, 0, 1.4, 0), P(keep(new THREE.IcosahedronGeometry(0.55, 0)), 0x8dbb74, 0.32, 1.92, 0.18)], 0.3, 1.0);
  const pineTree = merge([P(CYL(0.11, 0.14, 0.6, 6), 0x7d5f45), P(keep(new THREE.ConeGeometry(0.78, 1.4, 7)), 0x5f8f57, 0, 1.25, 0), P(keep(new THREE.ConeGeometry(0.56, 1.1, 7)), 0x6b9b60, 0, 1.95, 0)], 0.3, 1.0);
  const trees = treeAt.map(([x, z], i) => ({ x, z, kind: i < 4 ? 0 : rng() < 0.38 ? 1 : 0, s: 0.8 + rng() * 0.4, ry: rng() * 6.28, ph: rng() * 6.28, rise: 0, delay: 0, mi: 0 }));
  const treeMs = [roundTree, pineTree].map((g, k) => inst(g, stdMat(), trees.filter((t) => t.kind === k).length, 'trees'));
  const tIdx = [0, 0];
  trees.forEach((t) => { t.mi = tIdx[t.kind]++; });
  const placeTree = (t: (typeof trees)[number], sway = 0, t2 = 0) =>
    setInst(treeMs[t.kind], t.mi, t.x, t.rise, t.z, t.ry, t.s, t.s, t.s, sway * Math.sin(t2 * 1.1 + t.ph), sway * Math.cos(t2 * 0.83 + t.ph));
  trees.forEach((t) => placeTree(t));
  const flagGeo = keep(new THREE.PlaneGeometry(1.3, 0.75, 8, 1).translate(0.65, 0, 0));
  const flags: THREE.Mesh[] = [];
  const pole = CYL(0.05, 0.05, 1.8, 6);
  function makeFlag(x: number, y: number, z: number, color: number) {
    mesh(merge([P(pole, 0x64748b)]), stdMat()).position.set(x, y, z);
    const f = mesh(flagGeo.clone(), new THREE.MeshStandardMaterial({ color, side: THREE.DoubleSide, flatShading: true, roughness: 0.8 }));
    f.position.set(x, y + 1.4, z);
    flags.push(f);
  }
  makeFlag(ofx, 4.1, ofz, 0x7c5cd6);

  /* ======== the port: quay, gantry crane, late stack, ships at anchor, a ship that docks ======== */
  const incoming = snapshot.incoming;
  const port = new THREE.Group();
  const [pox, poz] = polar(27.6, PA);
  const portRy = faceOut(PA);
  port.position.set(pox, 0, poz);
  port.rotation.y = portRy;
  port.updateMatrixWorld();
  const PL = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z).applyMatrix4(port.matrixWorld);
  const TEAL = 0x13798c;
  const CRANE_X = -3.0;
  const BOOM_Y = 8.3;
  const TROLLEY_Y = BOOM_Y - 0.42;
  const PAD = new THREE.Vector3(-3.0, 0, 0.2);
  const BERTH_Z = 6.0;
  let animDock: (t: number, dt: number) => void = () => undefined;
  let staticDock: () => void = () => undefined;
  let animAnchors: (t: number) => void = () => undefined;
  let animCoaster: (t: number) => void = () => undefined;
  let wakeStep: (t: number) => void = () => undefined;
  const anchorRows: TownShipment[] = [];
  const lateRows: TownShipment[] = [];
  const softTex = radTex([[0, 'rgba(255,255,255,1)'], [0.4, 'rgba(255,255,255,0.45)'], [1, 'rgba(255,255,255,0)']], 64);
  function particles(cap: number, size: number) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(cap * 3), 3));
    g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(cap * 3), 3));
    const pts = new THREE.Points(
      g,
      new THREE.PointsMaterial({ size, map: softTex, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false, sizeAttenuation: true }),
    );
    pts.frustumCulled = false;
    scene.add(pts);
    return { pts, cap, list: [] as (Particle | undefined)[], head: 0 };
  }
  type Particles = ReturnType<typeof particles>;
  const emit = (sys: Particles, p: Particle) => {
    sys.list[sys.head] = p;
    sys.head = (sys.head + 1) % sys.cap;
  };
  function stepParticles(sys: Particles, now: number, bright: number) {
    const pos = sys.pts.geometry.attributes.position;
    const col = sys.pts.geometry.attributes.color;
    for (let i = 0; i < sys.cap; i++) {
      const p = sys.list[i];
      const age = p ? now - p.t0 : 1e9;
      if (!p || age > p.life || age < 0) {
        col.setXYZ(i, 0, 0, 0);
        pos.setXYZ(i, 0, -50, 0);
        continue;
      }
      const k = age / p.life;
      pos.setXYZ(i, p.x + p.vx * age, p.y + (p.vy ?? 0) * age, p.z + p.vz * age);
      const b = bright * smooth(clamp(k / 0.08, 0, 1)) * (1 - k) * (1 - k);
      col.setXYZ(i, b * p.r, b * p.g, b * p.b);
    }
    pos.needsUpdate = true;
    col.needsUpdate = true;
  }
  const spark = particles(48, 1.4);
  if (incoming) {
    scene.add(port);
    const openPort = () => select({ kind: 'port' });
    const portTip = (): TipSubject => ({ kind: 'port' });
    const quay = mesh(
      merge(
        [
          P(BOX, 0xc8ccd1, 0, -2.6, -0.4, 13, 2.6, 7.6), P(BOX, 0x8e97a1, 0, 0, 3.25, 13, 0.14, 0.3),
          ...[-5, -2.5, 0, 2.5, 5].map((x) => P(CYL(0.12, 0.15, 0.32, 8), 0x47505c, x, 0.14, 3.0)),
          ...[-4.5, -1.5, 1.5, 4.5].map((x) => P(BOX, 0x2b313a, x, -1.25, 3.42, 0.55, 0.9, 0.14)),
        ],
        0.25,
      ),
      stdMat(),
      { parent: port },
    );
    const crane = mesh(
      merge([
        ...[-4.3, -1.7].flatMap((x) => [1.0, 2.9].map((z) => P(BOX, TEAL, x, 0, z, 0.3, 8.3, 0.3))),
        P(BOX, TEAL, -3.0, 4.2, 1.0, 2.9, 0.22, 0.22), P(BOX, TEAL, -3.0, 4.2, 2.9, 2.9, 0.22, 0.22),
        P(BOX, TEAL, -3.0, 8.0, 1.0, 2.9, 0.35, 0.35), P(BOX, TEAL, -3.0, 8.0, 2.9, 2.9, 0.35, 0.35),
        P(BOX, 0x0f6474, -3.0, 8.3, 3.7, 0.6, 0.48, 13.0), P(BOX, 0xf1ece2, -3.0, 8.75, -1.4, 1.7, 1.0, 1.7),
      ]),
      stdMat(),
      { parent: port },
    );
    const trolley = mesh(merge([P(BOX, 0x39434f, 0, 0, 0, 0.9, 0.42, 1.0)]), stdMat(), { parent: port });
    const cable = mesh(merge([P(keep(new THREE.BoxGeometry(0.05, 1, 0.05).translate(0, -0.5, 0)), 0x2b313a)]), stdMat(), { parent: port, receive: false });
    const spreader = mesh(merge([P(BOX, 0xe9b23c, 0, 0, 0, 2.1, 0.14, 0.9)]), stdMat(), { parent: port });
    const cargoMat = stdMat({ transparent: true });
    const cargo = mesh(merge([P(BOX, 0xe07b39, 0, 0, 0, 2.0, 0.85, 0.85), P(BOX, 0xc8692e, 0, 0.83, 0, 2.02, 0.04, 0.87), P(BOX, 0xc8692e, 0.98, 0.05, 0, 0.06, 0.75, 0.87)]), cargoMat);
    pickables.push([quay, openPort, portTip], [crane, openPort, portTip], [cargo, openPort, portTip]);
    makeFlag(...(PL(5.8, 0, -3.6).toArray() as [number, number, number]), TEAL);
    const nShip = Math.min(SHIP_CAP, incoming.incoming);
    const nBox = Math.min(LATE_CAP, incoming.late);
    anchorRows.push(...incoming.shipments.filter((r) => !r.late).slice(0, nShip));
    lateRows.push(...incoming.shipments.filter((r) => r.late).slice(0, nBox));
    const lateM = inst(merge([P(BOX, 0xffffff, 0, 0, 0, 2.0, 0.85, 0.85), P(BOX, 0xd8d8d8, 0, 0.83, 0, 2.02, 0.04, 0.87)]), stdMat(), nBox, 'late containers');
    for (let i = 0; i < nBox; i++) {
      const layer = Math.floor(i / 6);
      const k = i % 6;
      const p = PL(1.6 + (k % 3) * 2.15, 0.85 * layer, -2.7 + Math.floor(k / 3) * 1.0);
      setInst(lateM, i, p.x, p.y, p.z, portRy);
      lateM.setColorAt(i, C([0xcc3b3b, 0xb53030, 0xd64848][i % 3]));
    }
    // ships: hull, boot-top stripe at the waterline, pointed bow, bridge, funnel, deck containers (waterline = local y 0)
    const shipGeo = merge([
      P(BOX, 0x22364d, -0.2, -0.75, 0, 6.6, 1.3, 2.1), P(BOX, 0xb5483a, -0.2, -0.06, 0, 6.64, 0.16, 2.14),
      P(BOX, 0x22364d, 3.1, -0.75, 0, 1.48, 1.3, 1.48, Math.PI / 4), P(BOX, 0xb5483a, 3.1, -0.06, 0, 1.5, 0.16, 1.5, Math.PI / 4),
      P(BOX, 0xf3f4f6, -2.75, 0.55, 0, 1.1, 1.45, 1.8), P(BOX, 0x8fa6bd, -2.19, 1.55, 0, 0.04, 0.26, 1.5), P(CYL(0.22, 0.26, 0.7, 10), 0xd9603b, -3.05, 2.0, 0),
      ...[-1.55, -0.55, 0.45, 1.45, 2.4].map((x, k) => P(BOX, [0xe07b39, 0x2b8a99, 0xe8dcc3, 0x5f7085, 0x2b8a99][k], x, 0.55, 0, 0.92, 0.7, 1.8)),
      ...[-1.55, 1.45].map((x, k) => P(BOX, [0xe8dcc3, 0xe07b39][k], x, 1.25, 0, 0.92, 0.7, 1.8)),
    ]);
    const anchorM = inst(shipGeo, stdMat(), nShip, 'ships');
    const ANCH = [[-12.5, 14.0, 0.1], [-5.5, 12.8, -0.12], [1.5, 13.5, 0.06], [9.5, 14.5, -0.1], [-9.0, 20.5, 0.12], [4.5, 20.0, -0.06]];
    const anchors = ANCH.map(([x, z, h], i) => {
      const p = PL(x, 0, z);
      return { x: p.x, z: p.z, ry: portRy - Math.PI / 2 + h, ph: i * 1.9 };
    });
    animAnchors = (t) =>
      anchors.forEach((s, i) => {
        if (i < nShip) setInst(anchorM, i, s.x, SEA + 0.08 * Math.sin(t * 1.2 + s.ph), s.z, s.ry, 1, 1, 1, 0.03 * Math.sin(t * 0.95 + s.ph), 0.02 * Math.sin(t * 1.1 + s.ph * 2));
      });
    animAnchors(0);
    const dockShip = mesh(shipGeo, stdMat());
    {
      // TOWN-PROJECT-CITY: Sabah, Sarawak and Labuan orders go by sea, round Johor and across the South China Sea
      const coaster = mesh(shipGeo, stdMat());
      coaster.scale.setScalar(0.8);
      const sea = new THREE.CatmullRomCurve3(
        [PL(14, SEA, 9.8), v3(mapXZ(-46, -18)), v3(mapXZ(-24, -84)), v3(mapXZ(26, -116)), v3(mapXZ(104, -122)), v3(mapXZ(150, -62)), v3(edgeToward('sarawak', ...mapXZ(120, -40), -3.5))].map((v) => v.setY(SEA)),
        false, 'centripetal',
      );
      const L = sea.getLength();
      const prof = trapezoid(L, 11, 1.6);
      const cycle = prof.T * 2 + 8;
      pickables.push([coaster, () => select({ kind: 'deliver' }), () => ({ kind: 'coaster' })]);
      animCoaster = (t) => {
        const c = ((t % cycle) + cycle) % cycle;
        const back = c > prof.T + 4;
        const s = c < prof.T ? prof.at(c) : back ? L - prof.at(Math.min(prof.T, c - prof.T - 4)) : L;
        const u = clamp(s / L, 0, 1);
        const p = sea.getPointAt(u);
        const tg = sea.getTangentAt(u);
        coaster.position.set(p.x, SEA + 0.06 * Math.sin(t * 1.3), p.z);
        coaster.rotation.set(0.02 * Math.sin(t), Math.atan2(-tg.z, tg.x) + (back ? Math.PI : 0), 0);
      };
      animCoaster(0);
    }
    pickables.push(
      [anchorM, openPort, (i) => (anchorRows[i] ? { kind: 'shipment', row: anchorRows[i] } : portTip())],
      [lateM, openPort, (i) => (lateRows[i] ? { kind: 'shipment', row: lateRows[i] } : portTip())],
      [dockShip, openPort, portTip],
    );
    const docking = incoming.incoming > 0;
    dockShip.visible = cargo.visible = docking;
    // docking route (port-local x along the quay, z out to sea): in from the haze, alongside the quay, out again
    const curveOf = (pts: [number, number][]) => new THREE.CatmullRomCurve3(pts.map(([x, z]) => PL(x, SEA, z)), false, 'centripetal');
    const SHIP_X = CRANE_X - 0.45; // the cargo slot (ship-local x 0.45) sits under the boom
    const dockIn = curveOf([[-70, 64], [-44, 34], [-22, 11.5], [-11, 6.4], [SHIP_X, BERTH_Z]]);
    const dockOut = curveOf([[SHIP_X, BERTH_Z], [4, 6.3], [14, 9.8], [32, 24], [62, 58]]);
    const inP = trapezoid(dockIn.getLength(), 7.5, 1.5);
    const outP = trapezoid(dockOut.getLength(), 7.5, 1.4);
    const HOOK_REST = 1.6;
    const HOOK_HI = 4.4;
    const HOOK_SHIP = TROLLEY_Y - (SEA + 1.25 + 0.85) - 0.14;
    const HOOK_PAD = TROLLEY_Y - 0.85 - 0.14;
    const craneP = trapezoid(BERTH_Z - PAD.z, 4.0, 4.0);
    const downP = trapezoid(HOOK_SHIP - HOOK_REST, 5.0, 6.0);
    const liftP = trapezoid(HOOK_SHIP - HOOK_HI, 3.0, 4.0);
    const lowerP = trapezoid(HOOK_PAD - HOOK_HI, 3.0, 4.0);
    const raiseP = trapezoid(HOOK_PAD - HOOK_REST, 4.0, 5.0);
    const DK = (() => {
      const a = inP.T, b = a + 0.6, c = b + craneP.T, d = c + downP.T, e = d + 0.3, f = e + liftP.T, g = f + craneP.T, h = g + lowerP.T, i = h + 0.3, j = i + raiseP.T;
      return { in: a, settle: b, out: c, down: d, latch: e, up: f, back: g, lower: h, release: i, raise: j, sail: j + 0.4, gone: j + 0.4 + outP.T, cycle: j + 0.4 + outP.T + 4 };
    })();
    const DOCK_PHASE = inP.T - 4.6; // the ship is already sailing in out of the haze as the fly-in lands
    const wake = particles(160, 2.6);
    let wakeAcc = 0;
    const emitWake = (now: number, dt: number, pos: THREE.Vector3, fwd: THREE.Vector3, speed: number) => {
      if (speed < 0.4) return;
      wakeAcc += dt;
      if (wakeAcc < 0.05) return;
      wakeAcc = 0;
      const side = new THREE.Vector3(fwd.z, 0, -fwd.x);
      const stern = pos.clone().addScaledVector(fwd, -3.4);
      const bow = pos.clone().addScaledVector(fwd, 3.9);
      const sp = Math.min(1, speed / 6);
      for (const s of [-1, 1]) emit(wake, { x: stern.x + side.x * s * 0.8, y: SEA + 0.26, z: stern.z + side.z * s * 0.8, vx: side.x * s * 0.9 * sp, vz: side.z * s * 0.9 * sp, t0: now, life: 2.6, r: 0.75, g: 0.85, b: 0.85 });
      emit(wake, { x: stern.x, y: SEA + 0.26, z: stern.z, vx: -fwd.x * 0.4, vz: -fwd.z * 0.4, t0: now, life: 2.0, r: 0.85, g: 0.95, b: 0.95 });
      for (const s of [-1, 1]) emit(wake, { x: bow.x + side.x * s * 0.6, y: SEA + 0.26, z: bow.z + side.z * s * 0.6, vx: side.x * s * 1.3 * sp, vz: side.z * s * 1.3 * sp, t0: now, life: 1.4, r: 0.7, g: 0.8, b: 0.8 });
    };
    wakeStep = (t) => stepParticles(wake, t, 0.85);
    const cargoOnShip = new THREE.Vector3(0.45, 1.25, 0);
    const shipPose = (t: number) => {
      const c = ((((t + DOCK_PHASE) % DK.cycle) + DK.cycle) % DK.cycle);
      let p: THREE.Vector3;
      let tg: THREE.Vector3;
      let v = 0;
      if (c < DK.in) {
        const u = inP.at(c) / inP.L;
        p = dockIn.getPointAt(u);
        tg = dockIn.getTangentAt(u);
        v = inP.vel(c);
      } else if (c < DK.sail) {
        p = dockIn.getPointAt(1);
        tg = dockIn.getTangentAt(1);
      } else if (c < DK.gone) {
        const u = outP.at(c - DK.sail) / outP.L;
        p = dockOut.getPointAt(u);
        tg = dockOut.getTangentAt(u);
        v = outP.vel(c - DK.sail);
      } else {
        p = dockOut.getPointAt(1);
        tg = dockOut.getTangentAt(1);
      }
      return { c, p, tg, v };
    };
    animDock = (t, dt) => {
      if (!docking) return;
      const { c, p, tg, v } = shipPose(t);
      dockShip.position.set(p.x, SEA + 0.07 * Math.sin(t * 1.25), p.z);
      dockShip.rotation.set(0.025 * Math.sin(t * 1.05), Math.atan2(-tg.z, tg.x), 0.02 * Math.sin(t * 0.9));
      dockShip.visible = c < DK.gone;
      emitWake(t, dt, new THREE.Vector3(p.x, 0, p.z), new THREE.Vector3(tg.x, 0, tg.z).normalize(), v);
      let tz = PAD.z;
      let hook = HOOK_REST;
      const carry = c >= DK.latch && c < DK.release ? 'hook' : c >= DK.release && c < DK.cycle - 2.5 ? 'pad' : 'ship';
      if (c < DK.settle) tz = PAD.z;
      else if (c < DK.out) tz = PAD.z + craneP.at(c - DK.settle);
      else if (c < DK.down) { tz = BERTH_Z; hook = HOOK_REST + downP.at(c - DK.out); }
      else if (c < DK.latch) { tz = BERTH_Z; hook = HOOK_SHIP; }
      else if (c < DK.up) { tz = BERTH_Z; hook = HOOK_SHIP - liftP.at(c - DK.latch); }
      else if (c < DK.back) { tz = BERTH_Z - craneP.at(c - DK.up); hook = HOOK_HI; }
      else if (c < DK.lower) { tz = PAD.z; hook = HOOK_HI + lowerP.at(c - DK.back); }
      else if (c < DK.release) { tz = PAD.z; hook = HOOK_PAD; }
      else if (c < DK.raise) { tz = PAD.z; hook = HOOK_PAD - raiseP.at(c - DK.release); }
      trolley.position.set(CRANE_X, TROLLEY_Y, tz);
      cable.position.set(CRANE_X, TROLLEY_Y, tz);
      cable.scale.set(1, hook, 1);
      spreader.position.set(CRANE_X, TROLLEY_Y - hook - 0.14, tz);
      if (carry === 'ship') {
        dockShip.updateMatrixWorld();
        cargo.position.copy(dockShip.localToWorld(cargoOnShip.clone()));
        cargo.rotation.copy(dockShip.rotation);
        cargo.visible = dockShip.visible;
      } else if (carry === 'hook') {
        cargo.position.copy(PL(CRANE_X, TROLLEY_Y - hook - 0.14 - 0.85, tz));
        cargo.rotation.set(0, portRy, 0);
        cargo.visible = true;
      } else {
        cargo.position.copy(PL(PAD.x, 0, PAD.z));
        cargo.rotation.set(0, portRy, 0);
        cargo.visible = true;
      }
      // received: fades off the pad while the next ship is still out in the haze
      cargoMat.opacity = carry === 'pad' ? 1 - EASE(clamp((c - (DK.cycle - 3.0)) / 0.5, 0, 1)) : 1;
    };
    staticDock = () => {
      // reduced motion: ship alongside, cargo on deck, crane parked
      const p = dockIn.getPointAt(1);
      const tg = dockIn.getTangentAt(1);
      dockShip.position.set(p.x, SEA, p.z);
      dockShip.rotation.set(0, Math.atan2(-tg.z, tg.x), 0);
      dockShip.visible = docking;
      trolley.position.set(CRANE_X, TROLLEY_Y, PAD.z);
      cable.position.copy(trolley.position);
      cable.scale.set(1, 1.6, 1);
      spreader.position.set(CRANE_X, TROLLEY_Y - 1.74, PAD.z);
      dockShip.updateMatrixWorld();
      cargo.position.copy(dockShip.localToWorld(cargoOnShip.clone()));
      cargo.rotation.copy(dockShip.rotation);
      cargo.visible = docking;
      cargoMat.opacity = 1;
      wake.list.length = 0;
      stepParticles(wake, 0, 0);
    };
  }

  /* ======== lorries: one per customer with orders due (at most 6), keeping to the left lane ======== */
  const deliveries = snapshot.deliveries;
  const customers = deliveries?.customers;
  const VMAX = 5.2;
  const ACC = 2.4;
  const LANE = 0.55;
  const depotIn = new THREE.Vector3(dx, 0, dz).addScaledVector(depotF, -0.4);
  const depotDoor = new THREE.Vector3(dx, 0, dz).addScaledVector(depotF, 2.0);
  const wrapDeg = (d: number) => (((d % 360) + 540) % 360) - 180;
  const v2 = (p: [number, number]) => new THREE.Vector3(p[0], 0, p[1]);
  type Dest = { a: number; exit?: number; tail?: THREE.Vector3[]; flash?: number };
  function centreline(to: Dest | null) {
    const exitDeg = to ? (to.exit ?? to.a) : BRIDGE_D;
    const d = wrapDeg(exitDeg - SPOKE_D);
    const dir = Math.sign(d) || 1;
    const endDeg = SPOKE_D + d;
    const pts = [depotIn.clone(), depotDoor.clone(), v2(polar(16.6, SPOKE_D)), v2(polar(18.4, SPOKE_D)), v2(polar(HS, SPOKE_D + dir * 4.5))];
    const from = SPOKE_D + dir * 10;
    const ringTo = to && !to.tail ? endDeg : endDeg - dir * 4.5;
    const steps = Math.max(1, Math.ceil(Math.abs(ringTo - from) / 6));
    for (let s = 0; s <= steps; s++) {
      const a = from + ((ringTo - from) * s) / steps;
      if (dir * (ringTo - a) >= -0.01) pts.push(v2(polar(HS, a)));
    }
    if (to?.tail) pts.push(v2(polar(22.2, exitDeg)), v2(polar(25, exitDeg)), ...to.tail);
    return new THREE.CatmullRomCurve3(pts, false, 'centripetal');
  }
  function lanes(cl: THREE.CatmullRomCurve3) {
    const N = Math.ceil(cl.getLength() / 0.45);
    const sp = cl.getSpacedPoints(N);
    const outPts: THREE.Vector3[] = [];
    const backPts: THREE.Vector3[] = [];
    for (let i = 0; i <= N; i++) {
      const t = cl.getTangentAt(i / N);
      outPts.push(new THREE.Vector3(sp[i].x + t.z * LANE, 0, sp[i].z - t.x * LANE));
      backPts.push(new THREE.Vector3(sp[i].x - t.z * LANE, 0, sp[i].z + t.x * LANE));
    }
    // U-turn at the customer: swing across to the other lane
    const E = sp[N];
    const f = cl.getTangentAt(1);
    const l = new THREE.Vector3(f.z, 0, -f.x);
    const uturn = [E.clone().addScaledVector(f, 0.75).addScaledVector(l, 0.42), E.clone().addScaledVector(f, 1.1), E.clone().addScaledVector(f, 0.75).addScaledVector(l, -0.42)];
    const out = new THREE.CatmullRomCurve3(outPts, false, 'centripetal');
    const back = new THREE.CatmullRomCurve3([outPts[N], ...uturn, ...backPts.reverse()], false, 'centripetal');
    out.arcLengthDivisions = back.arcLengthDivisions = 600;
    return { out, back };
  }
  const lorryGeo = merge(
    [
      P(BOX, 0x3a414b, 0, 0.14, 0, 2.1, 0.16, 0.8), P(BOX, 0x2f6fe0, 0.75, 0.22, 0, 0.66, 0.84, 0.96), P(BOX, 0x1f2a36, 1.085, 0.6, 0, 0.03, 0.34, 0.82),
      P(BOX, 0xf8f8f6, -0.36, 0.26, 0, 1.46, 1.05, 1.0), P(BOX, 0x2f6fe0, -0.36, 0.78, 0, 1.48, 0.12, 1.02),
      ...[0.72, -0.78].flatMap((x) => [-0.44, 0.44].map((z) => P(keep(new THREE.CylinderGeometry(0.22, 0.22, 0.16, 10)), 0x20252c, x, 0.22, z, 1, 1, 1, 0, Math.PI / 2))),
    ],
    0.2,
    0.5,
  );
  interface Trip { c: TownDueCustomer | null; project?: string; to: Dest | null; out: THREE.CatmullRomCurve3; back: THREE.CatmullRomCurve3; p1: Trapezoid; p2: Trapezoid; waitC: number; cycle: number; offset: number; at: boolean }
  const due = (customers ?? []).slice(0, LORRY_CAP);
  // a customer whose shop is not drawn, or stands in a state reached by sea, has no road: its lorry waits at the depot
  const destOf = (c: TownDueCustomer): Dest | null => {
    const slot = c.key ? slots.find((s) => s.s.key === c.key) : null;
    if (!slot) return null;
    return slot.tail ? slot : slot.exit == null && Number.isFinite(slot.a) ? slot : null;
  };
  const driving = due.filter((c) => destOf(c));
  const waiting: (TownDueCustomer | null)[] = customers
    ? due.filter((c) => !driving.includes(c))
    : Array.from({ length: Math.min(PARKED_CAP, deliveries?.to_deliver ?? 0) }, () => null);
  // TOWN-PROJECT-CITY: a project order's lorry drives to the gate of its state's project quarter, never to a site
  // (no order carries a project link); East Malaysia goes by the coaster, State not set has no road
  const projectRuns = (deliveries?.project_states ?? [])
    .slice(0, 3)
    .map((p) => ({ name: p.state ?? 'State not set', to: quarterGate(stateKeyOf(p.state)) }))
    .filter((p): p is { name: string; to: Dest } => !!p.to);
  const trip = (c: TownDueCustomer | null, to: Dest, k: number, project?: string): Trip => {
    const { out, back } = lanes(centreline(to));
    const vmax = to.tail ? VMAX * 2.4 : VMAX;
    const p1 = trapezoid(out.getLength(), vmax, ACC);
    const p2 = trapezoid(back.getLength(), vmax, ACC);
    const waitC = 3.4;
    return { c, project, to, out, back, p1, p2, waitC, cycle: p1.T + waitC + p2.T + 2.6, offset: k * 2.4, at: false };
  };
  const trips: Trip[] = [
    ...driving.map((c, k) => trip(c, destOf(c) as Dest, k)),
    ...projectRuns.map((p, k) => trip(null, p.to, driving.length + k, p.name)),
  ];
  const lorryM = inst(lorryGeo, stdMat({ roughness: 0.7 }), trips.length + waiting.length, 'lorries');
  const lorryTip = (i: number): TipSubject => {
    const tr = i < trips.length ? trips[i] : null;
    if (tr?.project) return { kind: 'project_lorry', state: tr.project };
    const c = tr ? tr.c : waiting[i - trips.length];
    return c ? { kind: 'lorry', customer: c } : { kind: 'deliver' };
  };
  pickables.push([lorryM, () => select({ kind: 'deliver' }), lorryTip]);
  const side = new THREE.Vector3(Math.cos(depotRy), 0, -Math.sin(depotRy));
  waiting.forEach((_, k) => {
    const p = new THREE.Vector3(dx, 0, dz).addScaledVector(depotF, 3.4 + Math.floor(k / 5) * 1.3).addScaledVector(side, -2.4 + (k % 5) * 1.2);
    setInst(lorryM, trips.length + k, p.x, 0.045, p.z, depotRy + Math.PI / 2, 0.85, 0.85, 0.85);
  });
  const LORRY_T0 = 2.4;
  function poseLorry(i: number, curve: THREE.CatmullRomCurve3, prof: Trapezoid, t: number) {
    const L = prof.L;
    const s = prof.at(t);
    const u = clamp(s / L, 0, 1);
    const p = curve.getPointAt(u);
    const tg = curve.getTangentAt(u);
    const tg2 = curve.getTangentAt(clamp((s + 0.6) / L, 0, 1));
    const yaw = Math.atan2(-tg.z, tg.x);
    let dy = Math.atan2(-tg2.z, tg2.x) - yaw;
    dy = Math.atan2(Math.sin(dy), Math.cos(dy));
    const v = prof.vel(t);
    const roll = clamp((dy / 0.6) * v * v * 0.03, -0.08, 0.08);
    const pitch = clamp(prof.acc(t) * 0.012, -0.04, 0.04);
    setInst(lorryM, i, p.x, 0.045, p.z, yaw, 0.95, 0.95, 0.95, roll, pitch, 'YZX');
  }
  function animLorries(t: number) {
    trips.forEach((tr, i) => {
      let lt = t - LORRY_T0 - tr.offset;
      if (lt < 0) return poseLorry(i, tr.out, tr.p1, 0);
      lt %= tr.cycle;
      const { p1, p2, waitC } = tr;
      if (lt < p1.T) {
        poseLorry(i, tr.out, p1, lt);
        tr.at = false;
      } else if (lt < p1.T + waitC) {
        poseLorry(i, tr.out, p1, p1.T);
        if (!tr.at && tr.to && 'flash' in tr.to) tr.to.flash = 1; // the customer's shop flashes when its lorry arrives
        tr.at = true;
      } else if (lt < p1.T + waitC + p2.T) poseLorry(i, tr.back, p2, lt - p1.T - waitC);
      else poseLorry(i, tr.back, p2, p2.T);
    });
  }
  const staticLorries = () => trips.forEach((tr, i) => poseLorry(i, tr.out, tr.p1, tr.to ? tr.p1.T : tr.p1.T * 0.32));

  const animFlags = (t: number) =>
    [...flags, ...siteFlags].forEach((f, k) => {
      const p = f.geometry.attributes.position;
      for (let i = 0; i < p.count; i++) {
        const x = p.getX(i);
        p.setZ(i, 0.18 * x * Math.sin(x * 3 - t * 3.2 + k));
      }
      p.needsUpdate = true;
    });

  /* ======== the one delight: a new sale ======== */
  const coin = mesh(
    keep(new THREE.CylinderGeometry(1.25, 1.25, 0.26, 32).rotateX(Math.PI / 2)),
    new THREE.MeshStandardMaterial({ color: 0xf6b52c, roughness: 0.32, metalness: 0.35, emissive: 0x6b4300, emissiveIntensity: 0.55, flatShading: true }),
    { receive: false },
  );
  coin.visible = false;
  const warmTex = radTex([[0, 'rgba(255,214,120,1)'], [0.35, 'rgba(255,180,70,0.45)'], [1, 'rgba(255,160,50,0)']]);
  const coinGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: warmTex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false, opacity: 0.75 }));
  coinGlow.scale.setScalar(5.5);
  coinGlow.visible = false;
  scene.add(coinGlow);
  const haloMat = basicMat({ map: warmTex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0 });
  const boardHalo = mesh(new THREE.PlaneGeometry(1, 1), haloMat, { cast: false, receive: false, parent: boardGroup });
  boardHalo.scale.set(19, 10, 1);
  boardHalo.position.set(0, 7.15, 0.3);
  boardHalo.visible = false;
  const rippleMat = basicMat({ color: 0xffb547, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending });
  const ripple = mesh(new THREE.RingGeometry(0.86, 1, 56).rotateX(-Math.PI / 2), rippleMat, { cast: false, receive: false });
  ripple.visible = false;
  const fx = {
    on: false, t: 0, calm: false, lit: false, hit: false, sparkT: 0, o: null as Slot | null,
    p0: new THREE.Vector3(), p1: new THREE.Vector3(), p2: new THREE.Vector3(),
  };
  const lighting = new Set<Slot>();
  const bez = (p0: THREE.Vector3, p1: THREE.Vector3, p2: THREE.Vector3, u: number) => {
    const a = (1 - u) * (1 - u);
    const b = 2 * u * (1 - u);
    const c = u * u;
    return new THREE.Vector3(p0.x * a + p1.x * b + p2.x * c, p0.y * a + p1.y * b + p2.y * c, p0.z * a + p1.z * b + p2.z * c);
  };
  function lightShop(s: Slot) {
    if (s.lit) return;
    s.lit = true;
    lighting.add(s);
    addPool(s);
    labelsDirty = true;
  }
  function boardTo(dur: number) {
    boardAnim = { from: { ...board }, t: 0, dur };
    invalidate();
  }
  let chipEl: HTMLDivElement | null = null;
  function chip(calm: boolean) {
    if (!beat) return;
    chipEl?.remove();
    const el = document.createElement('div');
    el.className =
      'pointer-events-none absolute left-0 top-0 z-[2] whitespace-nowrap rounded-full border border-transparent bg-warning px-2.5 py-0.5 text-xs font-bold tabular-nums text-warning-foreground shadow-sm';
    el.textContent = beat.amount != null ? `+${rm0(String(beat.amount))}` : `+${count(beat.invoices)} invoice${beat.invoices === 1 ? '' : 's'}`;
    labelLayer.appendChild(el);
    chipEl = el;
    positionChip();
    const done = () => {
      el.remove();
      if (chipEl === el) chipEl = null;
    };
    if (typeof el.animate === 'function') {
      const a = el.animate(
        calm
          ? [{ opacity: 0 }, { opacity: 1, offset: 0.15 }, { opacity: 1, offset: 0.75 }, { opacity: 0 }]
          : [{ opacity: 0, translate: '0 8px' }, { opacity: 1, translate: '0 0', offset: 0.18 }, { opacity: 1, translate: '0 -6px', offset: 0.7 }, { opacity: 0, translate: '0 -16px' }],
        { duration: 1700, easing: easeToken(), fill: 'forwards' },
      );
      a.onfinish = done;
    } else timers.push(window.setTimeout(done, 1700));
  }
  function positionChip() {
    if (!chipEl) return;
    const p = boardGroup.localToWorld(new THREE.Vector3(0, 10.0, 0.2)).project(cam);
    chipEl.style.transform = `translate3d(${((p.x + 1) / 2) * canvas.clientWidth}px, ${((1 - p.y) / 2) * canvas.clientHeight}px, 0) translate(-50%, -100%)`;
  }
  function startSale(s: Slot | null) {
    const calm = reduced || !motion.current || !s;
    Object.assign(fx, { on: true, t: 0, o: s, calm, lit: false, hit: false, sparkT: 0 });
    if (s) {
      fx.p0.set(s.x, s.h + 0.3, s.z);
      boardGroup.updateMatrixWorld();
      fx.p2.copy(boardGroup.localToWorld(new THREE.Vector3(0, 7.15, 0.4)));
      fx.p1.copy(fx.p0).lerp(fx.p2, 0.5);
      fx.p1.y = Math.max(fx.p0.y, fx.p2.y) + 9;
    }
    invalidate();
  }
  function animSale(dt: number) {
    if (!fx.on) return;
    fx.t += dt;
    const t = fx.t;
    const s = fx.o;
    if (fx.calm || !s) {
      // reduced motion or paused: a colour and number change, a chip fades; nothing travels
      if (!fx.lit) {
        fx.lit = true;
        if (s) {
          lightShop(s);
          s.flash = 1;
        }
        boardTo(0);
        chip(true);
      }
      if (t > 0.6) fx.on = false;
      return;
    }
    const L0 = 0.12;
    const FLIGHT = 1.1;
    const T1 = L0 + FLIGHT;
    s.sq = t < L0 ? -0.07 * EASE(t / L0) : -0.07 * Math.exp(-4.5 * (t - L0)) * Math.cos(2 * Math.PI * 2.2 * (t - L0));
    placeShop(s);
    if (t >= L0 && !fx.lit) {
      fx.lit = true;
      lightShop(s);
      s.flash = 1;
    }
    if (t >= L0 && t < T1) {
      const u = (t - L0) / FLIGHT;
      const p = bez(fx.p0, fx.p1, fx.p2, u);
      coin.visible = coinGlow.visible = true;
      coin.position.copy(p);
      coinGlow.position.copy(p);
      coin.rotation.set(0, u * Math.PI * 4, 0);
      coin.scale.setScalar(u < 0.12 ? 0.6 + 0.4 * EASE(u / 0.12) : u > 0.85 ? 1 - 0.35 * EASE((u - 0.85) / 0.15) : 1);
      fx.sparkT += dt;
      if (fx.sparkT > 0.03) {
        fx.sparkT = 0;
        emit(spark, { x: p.x, y: p.y, z: p.z, vx: (rng() - 0.5) * 0.6, vy: -0.4, vz: (rng() - 0.5) * 0.6, t0: fx.t, life: 0.5, r: 1, g: 0.85, b: 0.45 });
      }
    } else coin.visible = coinGlow.visible = false;
    if (t >= L0 && t < L0 + 1.3) {
      const e = EASE((t - L0) / 1.3);
      ripple.visible = true;
      ripple.position.set(s.x, 0.08, s.z);
      ripple.scale.setScalar(1.8 + 5.5 * e);
      rippleMat.opacity = 0.8 * (1 - e);
    } else ripple.visible = false;
    if (t >= T1 && !fx.hit) {
      fx.hit = true;
      boardTo(0.6);
      chip(false);
    }
    if (fx.hit) {
      const bt = t - T1;
      boardGroup.scale.setScalar(1 + 0.04 * Math.exp(-6 * bt) * Math.sin(2 * Math.PI * 2.4 * bt));
      boardHalo.visible = true;
      haloMat.opacity = 0.85 * Math.exp(-3.2 * bt) * smooth(clamp(bt / 0.08, 0, 1));
    }
    stepParticles(spark, fx.t, 1.0);
    if (t > 2.4) {
      fx.on = false;
      s.sq = 0;
      placeShop(s);
      boardGroup.scale.setScalar(1);
      coin.visible = coinGlow.visible = ripple.visible = boardHalo.visible = false;
      spark.list.length = 0;
      stepParticles(spark, 0, 0);
    }
  }
  function stepBoard(dt: number) {
    if (!boardAnim) return;
    boardAnim.t += dt;
    const u = boardAnim.dur ? clamp(boardAnim.t / boardAnim.dur, 0, 1) : 1;
    const to = { amount: Number(snapshot.today.amount ?? 0), inv: snapshot.today.invoice_count };
    board.amount = lerp(boardAnim.from.amount, to.amount, EASE(u));
    board.inv = lerp(boardAnim.from.inv, to.inv, EASE(u));
    drawBoard();
    if (u >= 1) boardAnim = null;
  }
  function stepLighting(dt: number) {
    lighting.forEach((s) => {
      s.litK = Math.min(1, s.litK + dt / (fx.calm ? 0.3 : 0.45));
      shopColours(s);
      placePool(s);
      if (s.litK >= 1) lighting.delete(s);
    });
    slots.forEach((s) => {
      if (s.flash > 0) {
        s.flash = Math.max(0, s.flash - dt * 1.1);
        placePool(s);
      }
    });
  }

  function flyTo(key: string) {
    if (key === 'all') return tweenTo({ zoom: 0.19, tilt: 62 * DEG }, 0.9, v3(mapXZ(112, 14)).setY(0));
    if (key === 'selangor' || key === 'home') return tweenTo({ ...DEFAULT_VIEW }, 0.8, HOME_TGT.clone());
    const d = STATE_BY[key];
    const [x, z] = centreOf(key);
    tweenTo({ zoom: d.rx > 30 ? 1.2 : 1.6, tilt: DEFAULT_VIEW.tilt }, 0.9, new THREE.Vector3(x, 0, z));
  }
  /* ======== DOM labels: pills projected from 3D anchors; fixed ones never dropped, tags culled on collision ======== */
  const tipText = (s: TipSubject) => townTip(snapshot, s);
  let labels: Label[] = [];
  /** A pill that is not shown (during the fly-in, or culled) takes no pointer and no keyboard focus. */
  const setLabelState = (el: HTMLButtonElement, state: 'hidden' | 'shown' | 'culled') => {
    el.dataset.state = state;
    el.tabIndex = state === 'shown' ? 0 : -1;
    if (state === 'shown') el.removeAttribute('aria-hidden');
    else el.setAttribute('aria-hidden', 'true');
  };
  const PILL =
    'pointer-events-auto inline-flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-2xs font-semibold leading-[18px] tabular-nums shadow-sm opacity-0 translate-y-1 motion-reduce:translate-y-0 transition-[opacity,translate,background-color] duration-(--duration-base) ease-(--ease-standard) active:scale-[0.97] data-[state=shown]:translate-y-0 data-[state=shown]:opacity-100 data-[state=hidden]:pointer-events-none data-[state=culled]:pointer-events-none data-[state=culled]:opacity-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:text-xs';
  const TONE = {
    plain: 'border-border bg-background/90 text-foreground hover:bg-background',
    red: 'border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/90',
  };
  const DOT = {
    lit: 'bg-amber-500',
    deliver: 'bg-blue-600',
    port: 'bg-cyan-700',
    approve: 'bg-violet-600',
  };
  function addLabel(parts: { text: string; dot?: keyof typeof DOT; muted?: string; tone?: keyof typeof TONE; title?: string }, anchor: THREE.Vector3, fixed: boolean, open: () => void, tip: () => TipSubject) {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = `absolute left-0 top-0 will-change-transform ${PILL} ${TONE[parts.tone ?? 'plain']}`;
    setLabelState(el, 'hidden');
    el.dataset.townLabel = fixed ? 'fixed' : 'tag';
    if (parts.title) el.setAttribute('aria-label', parts.title);
    if (parts.dot) {
      const dot = document.createElement('i');
      dot.setAttribute('aria-hidden', 'true');
      dot.className = `size-[7px] shrink-0 rounded-full ${DOT[parts.dot]}`;
      el.appendChild(dot);
    }
    el.appendChild(document.createTextNode(parts.text));
    if (parts.muted) {
      const m = document.createElement('span');
      m.className = 'font-medium text-muted-foreground';
      m.textContent = parts.muted;
      el.appendChild(m);
    }
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      hover(null);
      open();
    });
    el.addEventListener('pointerenter', (e) => {
      if (e.pointerType !== 'mouse') return;
      const r = el.getBoundingClientRect();
      const st = stage.getBoundingClientRect();
      hover({ ...tipText(tip()), x: r.left + r.width / 2 - st.left, y: r.top - st.top });
    });
    el.addEventListener('pointerleave', () => hover(null));
    labelLayer.appendChild(el);
    labels.push({ el, anchor, fixed, w: 0, h: 0 });
  }
  const total = deliveries ? deliveries.to_deliver : null;
  const projOrders = (deliveries as { project_orders?: number } | undefined)?.project_orders ?? 0;
  addLabel({ text: `${total == null ? '-' : count(total)} to deliver${projOrders ? ` · ${count(projOrders)} projects` : ''}`, dot: 'deliver' }, new THREE.Vector3(dx, 4.2, dz), true, () => select({ kind: 'deliver' }), () => ({ kind: 'deliver' }));
  if (incoming) {
    const any = incoming.incoming + incoming.late;
    addLabel({ text: any ? `Incoming: ${count(incoming.incoming)}` : 'Incoming: none', dot: 'port' }, PL(CRANE_X, 10.2, 1.9), true, () => select({ kind: 'port' }), () => ({ kind: 'port' }));
    if (incoming.late) addLabel({ text: `${count(incoming.late)} late`, tone: 'red' }, PL(3.7, 2.6, -2.2), true, () => select({ kind: 'port' }), () => ({ kind: 'port' }));
  }
  const wc = whSlot.length
    ? whSlot.reduce<[number, number]>((a, w) => [a[0] + w.x / whSlot.length, a[1] + w.z / whSlot.length], [0, 0])
    : polar(18, 182);
  addLabel({ text: `! ${count(snapshot.reorder.below_count)} low`, tone: 'red' }, new THREE.Vector3(wc[0], 4.4, wc[1]), true, () => select({ kind: 'low' }), () => ({ kind: 'low' }));
  const approvals = snapshot.approvals.total;
  addLabel({ text: approvals ? `${count(approvals)} waiting approval` : 'Approvals: all clear', dot: 'approve' }, new THREE.Vector3(ofx, 5.9, ofz), true, () => select({ kind: 'approve' }), () => ({ kind: 'approve' }));
  {
    // a pill per state: its counts; click flies the camera there
    const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`;
    STATES.forEach((d) => {
      const dealers = slots.filter((s) => stateOf(s.s) === d.key);
      const lit = dealers.filter((s) => s.s.today_docs > 0).length;
      const nSites = sitesBy[d.key]?.length ?? 0;
      const nTowers = towersBy[d.key]?.length ?? 0;
      const bits = [dealers.length ? `${plural(dealers.length, 'dealer')}${lit ? `, ${lit} lit` : ''}` : '', nSites ? plural(nSites, 'site') : '', nTowers ? plural(nTowers, 'trading house', 'trading houses') : ''].filter(Boolean);
      const [cx, cz] = d.key === 'selangor' ? polar(26.5, 330) : centreOf(d.key);
      addLabel(
        { text: d.name, dot: lit ? 'lit' : undefined, muted: bits.length ? ` ${bits.join(' · ')}` : undefined },
        new THREE.Vector3(cx, d.key === 'selangor' ? 3 : 4.5, cz),
        false,
        () => (d.key === 'selangor' ? flyTo('selangor') : flyTo(d.key)),
        () => ({ kind: 'state', name: d.name, detail: bits.join(' · ') }),
      );
      labels[labels.length - 1].isState = true;
      labels[labels.length - 1].el.dataset.townLabel = 'state';
    });
    const pj = mapSnap.projects;
    if (pj && (pj.more || pj.dormant)) {
      const [x, z] = polar(26.8, 69);
      addLabel({ text: [pj.more ? `+${count(pj.more)} more projects` : '', pj.dormant ? `+${count(pj.dormant)} dormant` : ''].filter(Boolean).join(' · ') }, new THREE.Vector3(x, 0.6, z), true, () => select({ kind: 'projects' }), () => ({ kind: 'projects' }));
    }
  }
  if (others) {
    const [x, z] = polar(HS, 222);
    addLabel({ text: `+${count(others)} more bought today`, dot: 'lit' }, new THREE.Vector3(x, 0.6, z), true, () => select({ kind: 'bought' }), () => ({ kind: 'bought', others }));
  }
  tagged.forEach((shop) => {
    const s = slots.find((slot) => slot.s === shop);
    if (!s) return;
    addLabel(
      { text: tagName(shop), dot: 'lit', muted: shop.today_amount ? rm0(shop.today_amount) : undefined, title: tagLabel(shop) },
      new THREE.Vector3(s.x, s.h + 0.5, s.z),
      false,
      () => select({ kind: 'shop', key: shop.key }),
      () => ({ kind: 'shop', shop }),
    );
  });
  const _p = new THREE.Vector3();
  const project = (v: THREE.Vector3, w: number, h: number) => {
    _p.copy(v).project(cam);
    return { x: ((_p.x + 1) / 2) * w, y: ((1 - _p.y) / 2) * h, front: _p.z < 1 };
  };
  function updateLabels() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    // the board's face is a no-label zone, so a tag never covers the day's number
    const corners = [[-6.2, 4.6], [6.2, 4.6], [-6.2, 9.7], [6.2, 9.7]].map(([bx, by]) => project(boardGroup.localToWorld(new THREE.Vector3(bx, by, 0.2)), w, h));
    const xs = corners.map((c) => c.x);
    const ys = corners.map((c) => c.y);
    const boardBox: ScreenBox = {
      x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2,
      w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys),
    };
    const box = (L: Label): ScreenBox | null => {
      if (!L.w) {
        L.w = L.el.offsetWidth;
        L.h = L.el.offsetHeight;
      }
      const p = project(L.anchor, w, h);
      const on = p.front && p.x > -40 && p.x < w + 40 && p.y > -20 && p.y < h + 40;
      const overview = view.current.zoom < 0.45;
      if (overview && !L.isState) return null;
      return on ? { x: p.x, y: p.y - L.h / 2, w: L.w, h: L.h } : null;
    };
    const fixedL = labels.filter((L) => L.fixed);
    const tagL = labels.filter((L) => !L.fixed);
    const fixedAll = fixedL.map((L) => box(L));
    const fixedBoxes = fixedAll.filter((b): b is ScreenBox => !!b);
    const stageView = { left: 0, right: w, bottom: 0, top: h };
    const onSpots = separateLabels(fixedBoxes, boardBox, stageView, 6);
    let k = 0;
    const spots = fixedAll.map((b) => (b ? onSpots[k++] : null));
    const placed = [boardBox, ...fixedBoxes.map((b, i) => ({ ...b, ...onSpots[i] }))];
    const tagSpots = placeTags(tagL.map(box), placed, stageView);
    const put = (L: Label, at: { x: number; y: number } | null) => {
      if (at) L.el.style.transform = `translate3d(${Math.round(at.x - L.w / 2)}px, ${Math.round(at.y - L.h / 2)}px, 0)`;
      if (L.el.dataset.state !== 'hidden') setLabelState(L.el, at ? 'shown' : 'culled');
    };
    fixedL.forEach((L, i) => put(L, spots[i] ?? null));
    tagL.forEach((L, i) => put(L, tagSpots[i]));
    positionChip();
    labelsDirty = false;
  }
  let labelsShown = false;
  function showLabels() {
    if (labelsShown) return;
    labelsShown = true;
    // a 40 ms stagger as a transition delay, so it runs on the same clock as everything else
    labels.forEach((L, k) => {
      L.el.style.transitionDelay = o.intro && !reduced ? `${k * 40}ms` : '0ms';
      setLabelState(L.el, 'shown');
    });
    labelsDirty = true;
    timers.push(window.setTimeout(() => labels.forEach((L) => { L.el.style.transitionDelay = ''; }), 1500));
  }

  /* ======== camera: perspective 30 degree lens; drag turns (with momentum) and tilts, zoom 0.7-2.2 ======== */
  function placeCam() {
    const v = view.current;
    const [x, y, z] = cameraPosition(v, 0, baseDist / v.zoom);
    cam.position.set(TGT.x + x, TGT.y + y, TGT.z + z);
    cam.lookAt(TGT);
    cam.updateMatrixWorld();
    sun.position.set(TGT.x - 59.5, 70, TGT.z - 5.5);
    sun.target.position.copy(TGT);
    sun.target.updateMatrixWorld();
    const d = baseDist / v.zoom;
    fog.near = d + 12;
    fog.far = Math.max(d + 175, d * 1.7 + 160);
    boardGroup.rotation.y = Math.atan2(cam.position.x - boardGroup.position.x, cam.position.z - boardGroup.position.z);
    boardGroup.updateMatrixWorld();
    labelsDirty = true;
    invalidate();
  }
  function resize() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    cam.aspect = w / h;
    const tv = Math.tan((cam.fov * DEG) / 2);
    // width fits the island and its beach; height fits the port too
    baseDist = Math.max((40 * Math.sin(DEFAULT_VIEW.tilt) + 7) / tv, 33 / (tv * cam.aspect));
    cam.updateProjectionMatrix();
    labels.forEach((L) => { L.w = 0; });
    placeCam();
  }

  /* ======== intro: a 2.4 s fly-in on --ease-standard; buildings rise plaza-outward; labels last ======== */
  const intro = { on: false, t: 0, rise: false, rt: 0 };
  const RISE = 0.75;
  let riseK = 1;
  let poolBase = 0.55;
  const riseDelay = (x: number, z: number) => 0.25 + 0.75 * clamp((Math.hypot(x, z) - 6) / 22, 0, 1) + 0.08 * rng();
  slots.forEach((s) => { s.delay = riseDelay(s.x, s.z); });
  whSlot.forEach((w) => { w.delay = riseDelay(w.x, w.z); });
  trees.forEach((t) => { t.delay = riseDelay(t.x, t.z); });
  const risers: [THREE.Object3D, number, number][] = [[depot, riseDelay(dx, dz), 3.0], [office, riseDelay(ofx, ofz), 4.5], [boardGroup, 0.15, 10.6]];
  function applyRise(rt: number) {
    const k = (d: number, h: number) => -(h + 0.8) * (1 - EASE(clamp((rt - d) / RISE, 0, 1)));
    slots.forEach((s) => {
      s.rise = k(s.delay, s.h);
      placeShop(s);
    });
    whSlot.forEach((w, i) => setInst(whM, i, w.x, k(w.delay, 3.0), w.z, w.ry));
    trees.forEach((t) => {
      t.rise = k(t.delay, 2.4 * t.s);
      placeTree(t);
    });
    risers.forEach(([obj, d, h]) => { obj.position.y = k(d, h); });
    // shadows and light pools arrive with their buildings
    riseK = EASE(clamp((rt - 0.7) / 1.0, 0, 1));
    blobMat.opacity = 0.4 * riseK;
    poolMat.opacity = poolBase * riseK;
  }

  /* ======== time of day: light and sky follow the snapshot hour ======== */
  const mix = (a: number[], b: number[], k: number) => a.map((v, i) => Math.round(v + (b[i] - v) * k));
  function setHour(hr: number) {
    hour = hr;
    const day = Math.max(0, Math.sin((Math.PI * (hr - 6)) / 14));
    const warm = Math.max(0, 1 - Math.abs(hr - 18) / 1.8);
    const nightK = clamp((hr - 19) / 2, 0, 1);
    // after dark the town is moonlit, not black: a cool fill keeps every building readable
    hemi.intensity = lerp(0.62, 1.15, day);
    sun.intensity = lerp(0.6, 2.7, day);
    fill.intensity = 0.15 + 0.3 * day;
    sun.color.setRGB(1, 0.95 - 0.2 * warm, 0.87 - 0.4 * warm).lerp(C(0x9db2e6), nightK);
    hemi.color.set(0xe3edf7).lerp(C(0x7f95c8), nightK);
    hemi.groundColor.set(0xcdb994).lerp(C(0x394050), nightK);
    lampAt.forEach((_, i) => headM.setColorAt(i, C(0xe6e1d6).lerp(C(0xfff2d2), nightK)));
    if (headM.instanceColor) headM.instanceColor.needsUpdate = true;
    lampPoolMat.opacity = 0.8 * nightK;
    let top = mix([201, 220, 238], [250, 205, 160], warm);
    let bot = mix([232, 239, 242], [252, 226, 204], warm);
    top = mix(top, [14, 22, 40], nightK);
    bot = mix(bot, [36, 48, 70], nightK);
    stage.style.background = `linear-gradient(180deg, rgb(${top.join(',')}) 0%, rgb(${bot.join(',')}) 62%, rgb(${bot.join(',')}) 100%)`;
    fog.color.setRGB(bot[0] / 255, bot[1] / 255, bot[2] / 255, THREE.SRGBColorSpace);
    poolBase = 0.5 + 0.5 * nightK;
    poolMat.opacity = poolBase * riseK;
    slots.forEach(shopColours);
    invalidate();
  }

  /* ======== loop: render on demand; continuous only while something moves; 60 fps cap; adaptive pixel ratio ======== */
  let fpsEMA = 60;
  let slowT = 0;
  let inertia = 0;
  let camTween: { from: TownView; to: TownView; t: number; dur: number; tf?: THREE.Vector3; tt?: THREE.Vector3 } | null = null;
  const moving = () => motion.current;
  const continuous = () =>
    intro.on || intro.rise || !!camTween || inertia !== 0 || fx.on || !!boardAnim || lighting.size > 0 || slots.some((s) => s.flash > 0 || s.lift !== s.liftTo) || moving();
  function invalidate() {
    if (!raf && !disposed && !document.hidden) raf = requestAnimationFrame(frame);
  }
  function frame(now: number) {
    raf = 0;
    if (disposed) return;
    if (document.hidden) {
      last = 0; // the clock stops while the tab is hidden; visibilitychange asks again
      return;
    }
    if (last && now - last < 14.5) {
      raf = requestAnimationFrame(frame);
      return;
    }
    const dt = last ? Math.min(0.05, (now - last) / 1000) : 1 / 60;
    last = now;
    step(dt);
    render();
    measure(dt);
    if (continuous()) invalidate();
    else last = 0;
  }
  function step(dt: number) {
    if (intro.on) {
      intro.t += dt;
      const e = EASE(clamp(intro.t / INTRO_S, 0, 1));
      view.current = {
        yaw: lerp(INTRO_FROM.yaw, DEFAULT_VIEW.yaw, e),
        tilt: lerp(INTRO_FROM.tilt, DEFAULT_VIEW.tilt, e),
        zoom: lerp(INTRO_FROM.zoom, DEFAULT_VIEW.zoom, e),
      };
      placeCam();
      if (intro.t >= INTRO_S) intro.on = false;
    }
    if (intro.rise) {
      intro.rt += dt;
      applyRise(intro.rt);
      if (intro.rt > 2.0) showLabels();
      if (intro.rt > 2.4) intro.rise = false;
    }
    if (camTween) {
      camTween.t += dt;
      const e = camTween.dur ? EASE(clamp(camTween.t / camTween.dur, 0, 1)) : 1;
      const { from, to } = camTween;
      view.current = { yaw: lerp(from.yaw, to.yaw, e), tilt: lerp(from.tilt, to.tilt, e), zoom: lerp(from.zoom, to.zoom, e) };
      if (camTween.tf && camTween.tt) TGT.lerpVectors(camTween.tf, camTween.tt, e);
      placeCam();
      if (e >= 1) camTween = null;
    }
    if (inertia) {
      view.current = { ...view.current, yaw: view.current.yaw + inertia * dt };
      inertia *= Math.exp(-dt * 4.2);
      if (Math.abs(inertia) < 0.015) inertia = 0;
      placeCam();
    }
    slots.forEach((s) => {
      if (s.lift !== s.liftTo) {
        s.lift += (s.liftTo - s.lift) * (1 - Math.exp(-dt / 0.045));
        if (Math.abs(s.liftTo - s.lift) < 0.003) s.lift = s.liftTo;
        placeShop(s);
      }
    });
    if (moving()) {
      clock.current += dt;
      world(clock.current, dt);
    }
    animSale(dt);
    stepBoard(dt);
    stepLighting(dt);
  }
  function world(t: number, dt: number) {
    seaTime.value = t;
    animLorries(t);
    animAnchors(t);
    animDock(t, dt);
    animCoaster(t);
    wakeStep(t);
    trees.forEach((tr) => placeTree(tr, 0.03, t));
    animFlags(t);
  }
  function staticWorld() {
    seaTime.value = 0;
    staticLorries();
    animAnchors(0);
    staticDock();
    trees.forEach((tr) => placeTree(tr));
    invalidate();
  }
  let ready = false;
  function render() {
    renderer.render(scene, cam);
    if (labelsDirty || chipEl) updateLabels();
    if (!ready) {
      ready = true;
      canvas.dataset.ready = '';
    }
  }
  function measure(dt: number) {
    fpsEMA = fpsEMA * 0.95 + (1 / dt) * 0.05;
    const dpr = renderer.getPixelRatio();
    if (continuous() && fpsEMA < 50 && dpr > 1) {
      slowT += dt;
      if (slowT > 2) {
        renderer.setPixelRatio(Math.max(1, dpr - 0.25));
        resize();
        slowT = 0;
      }
    } else slowT = 0;
  }

  /* ======== input: drag turns and tilts, wheel / pinch zooms, hover lifts + tooltip, click or tap opens ======== */
  const ray = new THREE.Raycaster();
  const ptr = new THREE.Vector2();
  let drag: { x: number; y: number; view: TownView; moved: boolean; hist: [number, number][] } | null = null;
  const touches = new Map<number, { x: number; y: number }>();
  let pinch: { d: number; zoom: number } | null = null;
  let hovered: Slot | null = null;
  const spread = () => {
    const [a, b] = [...touches.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  };
  const pick = (cx: number, cy: number) => {
    const r = canvas.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    ptr.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, cam);
    const objects = pickables.map((p) => p[0]).filter((obj) => obj.visible && !((obj as THREE.InstancedMesh).isInstancedMesh && (obj as THREE.InstancedMesh).count === 0));
    for (const hit of ray.intersectObjects(objects, false)) {
      const p = pickables.find((q) => q[0] === hit.object);
      if (p) return { p, i: hit.instanceId ?? 0, x: cx - r.left, y: cy - r.top };
    }
    return null;
  };
  const takeOver = () => {
    intro.on = false; // input during the fly-in hands the camera over where it is
    camTween = null;
    inertia = 0;
  };
  function setHover(s: Slot | null) {
    if (hovered === s) return;
    if (hovered) hovered.liftTo = 0;
    hovered = s;
    if (s && !reduced) s.liftTo = 0.28;
    invalidate();
  }
  const clearHover = () => {
    setHover(null);
    canvas.style.cursor = '';
    hover(null);
  };
  const setView = (v: TownView) => {
    view.current = v;
    placeCam();
  };
  const onDown = (e: PointerEvent) => {
    takeOver();
    touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (touches.size === 2) {
      pinch = { d: spread(), zoom: view.current.zoom };
      drag = null;
      return;
    }
    drag = { x: e.clientX, y: e.clientY, view: view.current, moved: false, hist: [[e.clientX, performance.now()]] };
  };
  const onMove = (e: PointerEvent) => {
    if (touches.has(e.pointerId)) touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && touches.size === 2) {
      setView({ ...view.current, zoom: pinchZoom(pinch.zoom, pinch.d, spread()) });
      return;
    }
    if (drag) {
      const dxp = e.clientX - drag.x;
      const dyp = e.clientY - drag.y;
      if (Math.hypot(dxp, dyp) > 4 && !drag.moved) {
        drag.moved = true;
        clearHover();
        canvas.style.cursor = 'grabbing';
      }
      if (drag.moved) {
        setView(dragView(drag.view, dxp, dyp));
        drag.hist.push([e.clientX, performance.now()]);
        if (drag.hist.length > 6) drag.hist.shift();
      }
      return;
    }
    if (e.pointerType !== 'mouse' || e.target !== canvas) return;
    const hit = pick(e.clientX, e.clientY);
    const subject = hit ? hit.p[2](hit.i) : null;
    if (!hit || !subject) {
      clearHover();
      return;
    }
    setHover(hit.p[3] ? hit.p[3](hit.i) : null);
    canvas.style.cursor = 'pointer';
    hover({ ...tipText(subject), x: hit.x, y: hit.y });
  };
  const onUp = (e: PointerEvent) => {
    touches.delete(e.pointerId);
    if (touches.size < 2) pinch = null;
    const d = drag;
    drag = null;
    if (d?.moved) {
      canvas.style.cursor = '';
      // momentum: carry the release velocity, decay like a scroll
      const a = d.hist[0];
      const b = d.hist[d.hist.length - 1];
      const dtm = (b[1] - a[1]) / 1000;
      if (!reduced && dtm > 0 && performance.now() - b[1] < 80) {
        inertia = clamp((-(b[0] - a[0]) / dtm) * 0.006, -4, 4);
        invalidate();
      }
      return;
    }
    if (!d || e.target !== canvas) return;
    const hit = pick(e.clientX, e.clientY);
    if (!hit) return;
    clearHover();
    hit.p[1](hit.i); // a click, or a tap on touch, opens the lightbox straight away
  };
  const onCancel = (e: PointerEvent) => {
    touches.delete(e.pointerId);
    if (touches.size < 2) pinch = null;
    drag = null;
  };
  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    takeOver();
    setView({ ...view.current, zoom: wheelZoom(view.current.zoom, e.deltaY) });
  };
  const onVisible = () => {
    if (!document.hidden) {
      last = 0;
      invalidate();
    }
  };
  const tweenTo = (to: Partial<TownView>, dur: number, target?: THREE.Vector3) => {
    takeOver();
    camTween = { from: { ...view.current }, to: { ...view.current, ...to }, t: 0, dur: reduced ? 0 : dur, tf: target ? TGT.clone() : undefined, tt: target };
    invalidate();
  };
  canvas.addEventListener('pointerdown', onDown);
  const onLeave = () => {
    if (!drag) clearHover();
  };
  canvas.addEventListener('pointerleave', onLeave);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('pointercancel', onCancel);
  document.addEventListener('visibilitychange', onVisible);
  const observer = new ResizeObserver(() => {
    resize();
    updateLabels();
  });
  observer.observe(canvas);

  /* ======== boot ======== */
  drawBoard();
  document.fonts?.ready?.then(() => !disposed && drawBoard());
  resize();
  setHour(hour);
  if (reduced && !motion.current) staticWorld();
  else world(clock.current, 0);
  if (o.intro && !reduced) {
    Object.assign(intro, { on: true, t: 0, rise: true, rt: 0 });
    view.current = { ...INTRO_FROM };
    applyRise(0);
    placeCam();
  } else {
    applyRise(99);
    showLabels();
  }
  if (beat) {
    // the busiest shop with new invoices that the town draws plays the beat; without one, the board and chip only
    const s = beat.shops.map((b) => slots.find((slot) => slot.s.key === b.key)).find(Boolean) ?? null;
    startSale(s);
  }
  invalidate();

  const dispose = () => {
    disposed = true;
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    timers.forEach((t) => window.clearTimeout(t));
    canvas.removeEventListener('pointerdown', onDown);
    canvas.removeEventListener('pointerleave', onLeave);
    canvas.removeEventListener('wheel', onWheel);
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', onCancel);
    document.removeEventListener('visibilitychange', onVisible);
    observer.disconnect();
    labels.forEach((L) => L.el.remove());
    labels = [];
    chipEl?.remove();
    chipEl = null;
    canvas.style.cursor = '';
    const textures = new Set<THREE.Texture>();
    const materials = new Set<THREE.Material>();
    scene.traverse((object) => {
      const item = object as THREE.Mesh;
      item.geometry?.dispose();
      const list = Array.isArray(item.material) ? item.material : item.material ? [item.material] : [];
      list.forEach((m) => materials.add(m));
    });
    materials.forEach((m) => {
      const map = (m as THREE.MeshBasicMaterial).map;
      if (map) textures.add(map);
      m.dispose();
    });
    textures.forEach((t) => t.dispose());
    templates.forEach((g) => g.dispose());
    instanced.forEach((m) => m.dispose());
    sun.dispose(); // its shadow map render target
    fill.dispose();
    hemi.dispose();
  };
  return {
    flyTo,
    dispose,
    zoom: (direction) => tweenTo({ zoom: stepZoom(view.current.zoom, direction) }, 0.2),
    reset: () => {
      const dy = Math.atan2(Math.sin(view.current.yaw - DEFAULT_VIEW.yaw), Math.cos(view.current.yaw - DEFAULT_VIEW.yaw));
      view.current = { ...view.current, yaw: DEFAULT_VIEW.yaw + dy };
      tweenTo(DEFAULT_VIEW, 0.5, HOME_TGT.clone());
    },
    setMotion: (on) => {
      motion.current = on;
      if (!on && reduced) staticWorld();
      last = 0;
      invalidate();
    },
  };
}
