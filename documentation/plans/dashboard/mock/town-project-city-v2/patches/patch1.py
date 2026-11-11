"""TOWN-PROJECT-CITY mock v2, patch 1: map frame, states, islands, bridges, streets, camera.
Applied to a COPY of the live townWorld.ts; every edit is an exact, single-occurrence replacement."""
import sys
p = sys.argv[1]
t = open(p).read()


def rep(old, new, count=1):
    global t
    n = t.count(old)
    assert n == count, (n, old[:90])
    t = t.replace(old, new)


# ---- header: mock note, local camera limits (the map zooms out to all of Malaysia)
rep("import { DEFAULT_VIEW, cameraPosition, dragView, pinchZoom, stepZoom, wheelZoom, type TownView } from '@/app/(protected)/town/lib/townCamera';",
    "import { DEFAULT_VIEW as LIVE_VIEW, cameraPosition, dragView, type TownView } from '@/app/(protected)/town/lib/townCamera';")
rep("const TGT = new THREE.Vector3(-2.5, 0, -2.5);",
    """const TGT = new THREE.Vector3(-2.5, 0, -2.5);
const HOME_TGT = TGT.clone();

/* ======== TOWN-PROJECT-CITY mock v2: the Malaysia map on the live engine ========
 * A fork of the live townWorld.ts for the mock only. The live island is unchanged and is Selangor (HQ, Shah
 * Alam); every other state is an island built with the same slab / beach / foam / tree code, joined by the same
 * causeway as the live bridge. The map frame is turned so the live port (bearing 232) faces west: Port Klang. */
const EX = -Math.cos(232 * DEG);
const EZ = -Math.sin(232 * DEG);
const NX = EZ;
const NZ = -EX;
/** map units (east, north) -> world (x, z); Shah Alam is the origin */
export const mapXZ = (e: number, n: number): [number, number] => [e * EX + n * NX, e * EZ + n * NZ];
export interface StateDef { key: string; name: string; e: number; n: number; rx: number; ry: number; rot: number; parent?: string; exit?: number }
/** schematic, not to scale: (e, n) centre, radii along / across `rot` (map degrees from east), the state its causeway
 * comes from, and for Selangor's children the high-street exit bearing on the live island */
export const STATES: StateDef[] = [
  { key: 'selangor', name: 'Selangor', e: 0, n: 0, rx: 27.6, ry: 27.6, rot: 0 },
  { key: 'kl', name: 'Kuala Lumpur', e: 44, n: 10, rx: 9.5, ry: 8.5, rot: 20, parent: 'selangor', exit: 44 },
  { key: 'putrajaya', name: 'Putrajaya', e: 35, n: -30, rx: 5.5, ry: 5, rot: 0, parent: 'selangor', exit: 92 },
  { key: 'perak', name: 'Perak', e: -36, n: 52, rx: 26, ry: 17, rot: 110, parent: 'selangor', exit: 287 },
  { key: 'penang', name: 'Pulau Pinang', e: -74, n: 84, rx: 7.5, ry: 6, rot: 80, parent: 'perak' },
  { key: 'kedah', name: 'Kedah', e: -38, n: 104, rx: 16, ry: 12, rot: 80, parent: 'perak' },
  { key: 'perlis', name: 'Perlis', e: -46, n: 128, rx: 6.5, ry: 6, rot: 60, parent: 'kedah' },
  { key: 'pahang', name: 'Pahang', e: 40, n: 48, rx: 25, ry: 19, rot: 50, parent: 'kl' },
  { key: 'terengganu', name: 'Terengganu', e: 68, n: 96, rx: 18, ry: 10, rot: 65, parent: 'pahang' },
  { key: 'kelantan', name: 'Kelantan', e: 36, n: 118, rx: 16, ry: 13, rot: 80, parent: 'terengganu' },
  { key: 'ns', name: 'Negeri Sembilan', e: 36, n: -58, rx: 13, ry: 11, rot: 30, parent: 'putrajaya' },
  { key: 'melaka', name: 'Melaka', e: 18, n: -80, rx: 8, ry: 7, rot: 30, parent: 'ns' },
  { key: 'johor', name: 'Johor', e: 68, n: -88, rx: 26, ry: 17, rot: 10, parent: 'ns' },
  { key: 'notset', name: 'State not set', e: -42, n: -58, rx: 8, ry: 7, rot: 0 },
  { key: 'sarawak', name: 'Sarawak', e: 205, n: -6, rx: 48, ry: 17, rot: 25 },
  { key: 'labuan', name: 'Labuan', e: 246, n: 56, rx: 4, ry: 4, rot: 0 },
  { key: 'sabah', name: 'Sabah', e: 282, n: 70, rx: 26, ry: 20, rot: 35 },
];
export const STATE_BY = Object.fromEntries(STATES.map((s) => [s.key, s])) as Record<string, StateDef>;
/** the map's own default: north up (Port Klang on the left), at exactly the live island's scale */
const DEFAULT_VIEW: TownView = { yaw: 142 * DEG, tilt: LIVE_VIEW.tilt, zoom: 1 };
const ZMIN = 0.13;
const ZMAX = 2.2;
const clampZoom = (z: number) => Math.min(ZMAX, Math.max(ZMIN, z));
const wheelZoom = (zoom: number, deltaY: number) => clampZoom(zoom * Math.exp(-deltaY * 0.0015));
const pinchZoom = (z0: number, d0: number, d: number) => clampZoom((z0 * d) / Math.max(1, d0));
const stepZoom = (z: number, dir: 1 | -1) => clampZoom(dir > 0 ? z * 1.25 : z / 1.25);""")
# INTRO_FROM referenced DEFAULT_VIEW before it is declared: move it below
rep("const INTRO_FROM: TownView = { yaw: DEFAULT_VIEW.yaw - 62 * DEG, tilt: 68 * DEG, zoom: 0.5 };\n", "")
rep("const stepZoom = (z: number, dir: 1 | -1) => clampZoom(dir > 0 ? z * 1.25 : z / 1.25);",
    "const stepZoom = (z: number, dir: 1 | -1) => clampZoom(dir > 0 ? z * 1.25 : z / 1.25);\nconst INTRO_FROM: TownView = { yaw: DEFAULT_VIEW.yaw - 62 * DEG, tilt: 68 * DEG, zoom: 0.5 };")
# DEG is declared above TGT already (const DEG = Math.PI / 180;) - keep order: DEG line precedes TGT.

rep("export interface WorldHandle {\n  dispose: () => void;",
    "export interface WorldHandle {\n  flyTo: (key: string) => void;\n  dispose: () => void;")

# ---- camera far plane and fog for the zoomed-out map
rep("const cam = new THREE.PerspectiveCamera(30, 1, 4, 760);", "const cam = new THREE.PerspectiveCamera(30, 1, 4, 4000);")

# ---- islands: generalise the slab to any outline, then build every other state with the same materials
rep("""  function slab(off: number, depth: number, bevel: number, top: number) {
    let g: THREE.BufferGeometry = new THREE.ExtrudeGeometry(new THREE.Shape(outline(off)), {""",
    """  function slab(off: number, depth: number, bevel: number, top: number, pts?: THREE.Vector2[]) {
    let g: THREE.BufferGeometry = new THREE.ExtrudeGeometry(new THREE.Shape(pts ?? outline(off)), {""")

ISLANDS = r"""
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
"""
rep("  const seaGeo = new THREE.PlaneGeometry(480, 480, 120, 120);",
    ISLANDS + "  const [seaCx, seaCz] = mapXZ(120, 20);\n  const seaGeo = new THREE.PlaneGeometry(1500, 1500, 300, 300);\n  seaGeo.translate(seaCx, 0, -seaCz);")
# sea colour: shallow near ANY island
rep("""      const k = smooth(clamp((Math.hypot(x, z) - rIsland(Math.atan2(-z, x)) - 3) / 17, 0, 1));""",
    """      let gap = Math.hypot(x, z) - rIsland(Math.atan2(-z, x));
      for (const i of isles) {
        const dx = x - i.cx;
        const dz = z - i.cz;
        if (Math.abs(dx) > 90 || Math.abs(dz) > 90) continue;
        gap = Math.min(gap, Math.hypot(dx, dz) - rIsle(i, Math.atan2(dz, dx)));
      }
      const k = smooth(clamp((gap - 3) / 17, 0, 1));""")

# ---- roads: exits off the live high street to KL and Putrajaya; the live bridge now lands on Perak
rep("radialRoad(PA, HS + 1.0, 25.4, 2.6), radialRoad(BRIDGE_D, HS + 1.0, 29.0),",
    "radialRoad(PA, HS + 1.0, 25.4, 2.6), radialRoad(BRIDGE_D, HS + 1.0, 29.0), radialRoad(44, HS + 1.0, 29.0), radialRoad(92, HS + 1.0, 29.0),")
rep("  dashLine(BRIDGE_D, HS + 2, 140, 0.065);\n", "")
BRIDGES = r"""
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
"""
rep("  const dashM = inst(P(BOX, 0xffffff, 0, 0, 0, 0.13, 0.02, 0.6), stdMat({ roughness: 0.7 }), dashes.length, 'dashes', { cast: false });",
    BRIDGES + "  const dashM = inst(P(BOX, 0xffffff, 0, 0, 0, 0.13, 0.02, 0.6), stdMat({ roughness: 0.7 }), dashes.length, 'dashes', { cast: false });")
# the live bridge: from r 26 out to Perak's shore instead of into the haze
rep("""    const parts: THREE.BufferGeometry[] = [];
    const len = 150 - 26;""", """    const parts: THREE.BufferGeometry[] = [];
    const [pk0, pk1] = edgeToward('perak', ...polar(26, BRIDGE_D), 2.0);
    const len = Math.hypot(pk0, pk1) - 26;""")
rep("    for (let r = 31; r < 150; r += 7) {", "    for (let r = 31; r < 26 + len - 3; r += 7) {")
open(p, 'w').write(t)
print('patch1 ok')
