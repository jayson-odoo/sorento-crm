"""TOWN-PROJECT-CITY mock v2, patch 2: shops by state, project sites, trading towers, trees, lorries, coaster,
state pills, split board, camera fly-to. Exact single-occurrence replacements on the patch-1 output."""
import sys
p = sys.argv[1]
t = open(p).read()


def rep(old, new, count=1):
    global t
    n = t.count(old)
    assert n == count, (n, old[:90])
    t = t.replace(old, new)


# ---------------------------------------------------------------- slot fields for a shop on another state's street
rep("  pool: number;\n  flash: number;\n}\n", "  pool: number;\n  flash: number;\n  exit?: number;\n  tail?: THREE.Vector3[];\n}\n")

# ---------------------------------------------------------------- shops: Selangor on the live high street, the rest on their state's street
rep("""  const A0 = -60;
  const A1 = 104;
  const slots: Slot[] = order.map((s, i) => {
    const a = A0 + ((A1 - A0) * i) / Math.max(1, order.length - 1);
    const inner = i % 2 === 0;
    const [x, z] = polar(inner ? 17.6 : 23.0, a);""",
    """  // TOWN-PROJECT-CITY: a shop stands in its own state; Selangor keeps the live high street (now -60..30, the
  // project quarter takes 52..86), every other state its own street; no state = the "State not set" islet
  const stateOf = (s: TownShop) => ((s as TownShop & { state?: string | null }).state ?? 'notset');
  const home = order.filter((s) => stateOf(s) === 'selangor');
  const A0 = -60;
  const A1 = 30;
  const perState: Record<string, number> = {};
  const v3 = (p: [number, number]) => new THREE.Vector3(p[0], 0, p[1]);
  /** the road from the live high street to `along` units down a state's street: exit bearing + waypoints over each causeway */
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
      const along = 4.2 + Math.floor(k / 2) * 2.9;
      [x, z] = streetAt(st, along, side * 2.75);
      const S = streets[st];
      ry = faceTo(-S.uz * side, S.ux * side);
      road = routeTo(st, along);
    }""")
rep("""    return {
      s, a, x, z, ry: inner ? faceOut(a) : faceIn(a), inner, floors, stall: s.kind !== 'shop', lit, litK: lit ? 1 : 0,""",
    """    return {
      s, a, x, z, ry, inner, floors, stall: s.kind !== 'shop', lit, litK: lit ? 1 : 0, exit: road?.exit, tail: road?.tail,""")

# ---------------------------------------------------------------- project sites and trading towers
SITES = r"""
  /* ======== TOWN-PROJECT-CITY: project sites (look = the project's own timeline; flag = our sales stage) and trading
   * houses (slate-blue glass towers, lit on a project invoice today), in the same materials as the live town ======== */
  interface MapSite { key: string; name?: string; code?: string; stage: string; final_negotiation: boolean; state: string | null; launch_date: string | null; delivery_date: string | null; estimated_value?: string | null }
  interface MapTower { key: string; name?: string; state: string | null; open_projects: number; today_docs: number }
  const mapSnap = snapshot as TownSnapshot & { projects?: { open_count: number; more: number; dormant: number; sites: MapSite[] }; trading_houses?: { more: number; rows: MapTower[] } };
  const STAGE: Record<string, [string, number]> = {
    identified: ['Identified', 0x9ca3af], registered: ['Registered', 0x2563eb], specified: ['Spec In', 0x0d9488],
    quoted: ['Quoted', 0xf59e0b], tendering: ['Tendering', 0xea580c], po_received: ['PO Received', 0x16a34a],
  };
  const LOOK_WORDS: Record<string, string> = { plain: 'no dates yet', before: 'launching', ground: 'groundworks', frame: 'frame going up', clad: 'cladding', done: 'finished' };
  const siteLook = (p: MapSite) => {
    if (!p.launch_date || !p.delivery_date) return 'plain';
    const l = Date.parse(p.launch_date);
    const d = Date.parse(p.delivery_date);
    const now = Date.parse(snapshot.day);
    if (!(d > l)) return 'plain';
    if (now < l) return 'before';
    const k = (now - l) / (d - l);
    return k < 0.25 ? 'ground' : k < 0.6 ? 'frame' : k < 0.95 ? 'clad' : 'done';
  };
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
  const raw = (title: string, detail: string) => ({ kind: 'raw', title, detail }) as unknown as TipSubject;
  const siteTitle = (p: MapSite) => (p.name ? `${p.name} · ${p.code}` : 'Project site');
  const extraBlobs: [number, number, number, number, number][] = [];
  const mapBlockers: [number, number, number][] = [];
  const sitesBy: Record<string, MapSite[]> = {};
  (mapSnap.projects?.sites ?? []).forEach((p) => (sitesBy[p.state ?? 'notset'] ??= []).push(p));
  const towersBy: Record<string, MapTower[]> = {};
  (mapSnap.trading_houses?.rows ?? []).forEach((r) => (towersBy[r.state ?? 'notset'] ??= []).push(r));
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
    const along0 = 4.2 + Math.ceil(shops / 2) * 2.9 + 0.6;
    const side = k % 2 ? 1 : -1;
    const along = tower ? along0 + Math.ceil(nSites / 2) * 3.7 + 1.4 + Math.floor(k / 2) * 3.0 : along0 + 1.5 + Math.floor(k / 2) * 3.7;
    const [x, z] = streetAt(st, along, side * (tower ? 3.1 : 3.4));
    const S = streets[st];
    return [x, z, faceTo(-S.uz * side, S.ux * side)];
  };
  const quarterGate = (st: string): { a: number; exit?: number; tail?: THREE.Vector3[] } | null => {
    if (st === 'selangor') return { a: 68 };
    const shops = perState[st] == null ? 0 : perState[st] + 1;
    const road = routeTo(st, 4.2 + Math.ceil(shops / 2) * 2.9 + 1.4);
    return road ? { a: NaN, ...road } : null;
  };
  const siteFlags: THREE.Mesh[] = [];
  Object.entries(sitesBy).forEach(([st, list]) =>
    list.forEach((p, k) => {
      const [x, z, ry] = quarterAt(st, k, false);
      const look = siteLook(p);
      const g = new THREE.Group();
      g.position.set(x, 0, z);
      g.rotation.y = ry;
      scene.add(g);
      const m = mesh(siteGeo(look), stdMat(), { parent: g });
      mesh(merge([P(CYL(0.035, 0.035, p.final_negotiation ? 1.75 : 1.4, 6), 0x64748b)]), stdMat(), { parent: g }).position.set(1.3, 0, 1.3);
      const f = mesh(siteFlagGeo.clone(), new THREE.MeshStandardMaterial({ color: STAGE[p.stage]?.[1] ?? 0x9ca3af, side: THREE.DoubleSide, flatShading: true, roughness: 0.8 }), { parent: g });
      f.position.set(1.3, 1.12, 1.3);
      siteFlags.push(f);
      if (p.final_negotiation) mesh(pennantGeo, basicMat({ color: 0xdc2626, side: THREE.DoubleSide }), { parent: g, cast: false }).position.set(1.3, 1.45, 1.3);
      const tip = () => raw(siteTitle(p), `${STAGE[p.stage]?.[0] ?? p.stage}${p.final_negotiation ? ', final negotiation' : ''} · ${LOOK_WORDS[look]}`);
      const open = () => select({ kind: 'site', key: p.key } as unknown as TownTarget);
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
    return r ? raw(r.name ?? 'Trading house', `${r.open_projects} open project${r.open_projects === 1 ? '' : 's'} · ${r.today_docs ? 'bought today' : 'no project invoice today'}`) : null;
  };
  const openTower = (i: number) => towerList[i] && select({ kind: 'trading_house', key: towerList[i].r.key } as unknown as TownTarget);
  pickables.push([towerM, openTower, towerTip], [towerWinM, openTower, towerTip]);
"""
rep("  /* ======== warehouses (low stock lives here), depot (lorries), approvals office ======== */",
    SITES + "\n  /* ======== warehouses (low stock lives here), depot (lorries), approvals office ======== */")
rep("    [dx, dz, depotRy, 7.4, 5.2], [ofx, ofz, faceOut(128), 4.9, 4.2], [0, 0, 0, 7.4, 7.4],\n  ];",
    "    [dx, dz, depotRy, 7.4, 5.2], [ofx, ofz, faceOut(128), 4.9, 4.2], [0, 0, 0, 7.4, 7.4], ...extraBlobs,\n  ];")
# lamps: only inner Selangor slots carry an angle (remote slots have a = NaN and inner = false already)

# ---------------------------------------------------------------- trees on every state, off its street and buildings
rep("  const roundTree = merge(", r"""  for (const i of isles) {
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
      if (off < 5.6 && along > 3 && along < S.len - 1 && (perState[i.d.key] != null || sitesBy[i.d.key] || towersBy[i.d.key]) && along < 4.2 + Math.ceil(((perState[i.d.key] ?? -1) + 1) / 2) * 2.9 + Math.ceil((sitesBy[i.d.key]?.length ?? 0) / 2) * 3.7 + Math.ceil((towersBy[i.d.key]?.length ?? 0) / 2) * 3.0 + 3) continue;
      if ([...blockers, ...mapBlockers].some(([bx, bz, br]) => Math.hypot(x - bx, z - bz) < br)) continue;
      if (treeAt.some(([tx, tz]) => Math.hypot(x - tx, z - tz) < 1.5)) continue;
      treeAt.push([x, z]);
      got++;
    }
  }
  const roundTree = merge(""")
# Selangor's own trees must avoid the new quarter too
rep("    if (blockers.some(([bx, bz, br]) => Math.hypot(x - bx, z - bz) < br)) continue;\n    if (treeAt.some(([tx, tz]) => Math.hypot(x - tx, z - tz) < 1.5)) continue;\n    treeAt.push([x, z]);\n  }",
    "    if ([...blockers, ...mapBlockers].some(([bx, bz, br]) => Math.hypot(x - bx, z - bz) < br)) continue;\n    if ([44, 92].some((d) => angleOff(deg, d) * DEG * r < 2.2 && r > HS)) continue;\n    if (treeAt.some(([tx, tz]) => Math.hypot(x - tx, z - tz) < 1.5)) continue;\n    treeAt.push([x, z]);\n  }")

# ---------------------------------------------------------------- coaster ship: Port Klang to East Malaysia and back
rep("  let animAnchors: (t: number) => void = () => undefined;",
    "  let animAnchors: (t: number) => void = () => undefined;\n  let animCoaster: (t: number) => void = () => undefined;")
rep("    const dockShip = mesh(shipGeo, stdMat());", r"""    const dockShip = mesh(shipGeo, stdMat());
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
      pickables.push([coaster, () => select({ kind: 'deliver' }), () => raw('Coaster to East Malaysia', 'Sabah, Sarawak and Labuan orders go by sea from Port Klang')]);
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
    }""")
rep("    animDock(t, dt);\n", "    animDock(t, dt);\n    animCoaster(t);\n")
# routeTo/v3 are declared with the shops; the port block is later, so they are in scope.

rep("  const animFlags = (t: number) =>\n    flags.forEach((f, k) => {", "  const animFlags = (t: number) =>\n    [...flags, ...siteFlags].forEach((f, k) => {")

# ---------------------------------------------------------------- lorries: over the causeways, to shops or to a project quarter gate
rep("""  function centreline(to: Slot | null) {
    const exitDeg = to ? to.a : BRIDGE_D;""",
    """  type Dest = { a: number; exit?: number; tail?: THREE.Vector3[]; flash?: number };
  function centreline(to: Dest | null) {
    const exitDeg = to ? (to.exit ?? to.a) : BRIDGE_D;""")
rep("    const ringTo = to ? endDeg : endDeg - dir * 4.5;", "    const ringTo = to && !to.tail ? endDeg : endDeg - dir * 4.5;")
rep("    if (!to) [22.2, 25, 40, 70, 100, 128].forEach((r) => pts.push(v2(polar(r, BRIDGE_D))));",
    "    if (to?.tail) pts.push(v2(polar(22.2, exitDeg)), v2(polar(25, exitDeg)), ...to.tail);")
rep("  interface Trip { c: TownDueCustomer; to: Slot | null;", "  interface Trip { c: TownDueCustomer; to: Dest | null;")
rep("""  const driving = due.filter((c) => c.key === null || slots.some((s) => s.s.key === c.key));""",
    """  type MapDue = TownDueCustomer & { kind?: 'dealer' | 'project'; state?: string | null };
  const destOf = (c: MapDue): Dest | null => {
    if (c.kind === 'project') return c.state ? quarterGate(c.state) : null;
    const slot = c.key ? slots.find((s) => s.s.key === c.key) : null;
    if (!slot) return null;
    return slot.tail ? slot : slot.exit == null && Number.isFinite(slot.a) ? slot : null;
  };
  const driving = due.filter((c) => destOf(c as MapDue));""")
rep("""    const to = c.key ? (slots.find((s) => s.s.key === c.key) ?? null) : null;
    const { out, back } = lanes(centreline(to));
    const p1 = trapezoid(out.getLength(), VMAX, ACC);
    const p2 = trapezoid(back.getLength(), VMAX, ACC);""",
    """    const to = destOf(c as MapDue);
    const { out, back } = lanes(centreline(to));
    const vmax = to?.tail ? VMAX * 2.4 : VMAX;
    const p1 = trapezoid(out.getLength(), vmax, ACC);
    const p2 = trapezoid(back.getLength(), vmax, ACC);""")
rep("        if (!tr.at && tr.to) tr.to.flash = 1;", "        if (!tr.at && tr.to && 'flash' in tr.to) tr.to.flash = 1;")
rep("    const c = i < trips.length ? trips[i].c : waiting[i - trips.length];\n    return c ? { kind: 'lorry', customer: c } : { kind: 'deliver' };",
    "    const c = i < trips.length ? trips[i].c : waiting[i - trips.length];\n    const m = c as MapDue | null;\n    if (m?.kind === 'project') return raw('Lorry', `Project order to ${STATE_BY[m.state ?? 'notset']?.name ?? 'a project'}`);\n    return c ? { kind: 'lorry', customer: c } : { kind: 'deliver' };")

# ---------------------------------------------------------------- labels: deliveries split, state pills, the projects sign
rep("  addLabel({ text: `${total == null ? '-' : count(total)} to deliver`, dot: 'deliver' }",
    "  const projOrders = (deliveries as { project_orders?: number } | undefined)?.project_orders ?? 0;\n  addLabel({ text: `${total == null ? '-' : count(total)} to deliver${projOrders ? ` · ${count(projOrders)} projects` : ''}`, dot: 'deliver' }")
rep("  if (others) {\n    const [x, z] = polar(HS, 22);",
    r"""  {
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
        () => raw(d.name, bits.join(' · ') || 'Nothing here today'),
      );
    });
    const pj = mapSnap.projects;
    if (pj && (pj.more || pj.dormant)) {
      const [x, z] = polar(26.8, 69);
      addLabel({ text: [pj.more ? `+${count(pj.more)} more projects` : '', pj.dormant ? `+${count(pj.dormant)} dormant` : ''].filter(Boolean).join(' · ') }, new THREE.Vector3(x, 0.6, z), true, () => select({ kind: 'projects' } as unknown as TownTarget), () => raw('Open projects', `${count(pj.open_count)} open; the map shows ${pj.sites.length}`));
    }
  }
  if (others) {
    const [x, z] = polar(HS, 22);""")

# ---------------------------------------------------------------- the board: Dealers / Projects / Other under the day's figure
rep("      g.fillText(night ? 'CLOSED FOR THE DAY' : 'SOLD TODAY', 512, 82);", "      g.fillText(night ? 'CLOSED FOR THE DAY' : 'SOLD TODAY', 512, 70);")
rep("      g.fillText(full ? rm0(String(board.amount)) : inv, 512, 224);", "      g.fillText(full ? rm0(String(board.amount)) : inv, 512, 196);")
rep("      g.fillText((full ? `${inv}   ` : '') + vs, 512, 318);",
    """      g.fillText((full ? `${inv}   ` : '') + vs, 512, 270);
      const split = (snapshot.today as { split?: Record<'dealer' | 'project' | 'other', { amount?: string; invoice_count: number }> }).split;
      if (split) {
        g.font = '600 40px Inter, sans-serif';
        const part = (label: string, v: { amount?: string; invoice_count: number }) => `${label} ${v.amount != null ? rm0(v.amount) : count(v.invoice_count)}`;
        const line = [part('Dealers', split.dealer), part('Projects', split.project), part('Other', split.other)].join('  ·  ');
        g.fillStyle = '#f2c46d';
        g.fillText(line + (split.dealer.amount == null ? ' invoices' : ''), 512, 352);
      }""")

# ---------------------------------------------------------------- camera: target tween, the sun follows it, fog for the zoomed-out map
rep("""    cam.lookAt(TGT);
    cam.updateMatrixWorld();
    const d = baseDist / v.zoom;
    fog.near = d + 12;
    fog.far = d + 175;""",
    """    cam.lookAt(TGT);
    cam.updateMatrixWorld();
    sun.position.set(TGT.x - 59.5, 70, TGT.z - 5.5);
    sun.target.position.copy(TGT);
    sun.target.updateMatrixWorld();
    const d = baseDist / v.zoom;
    fog.near = d + 12;
    fog.far = Math.max(d + 175, d * 1.7 + 160);""")
rep("  let camTween: { from: TownView; to: TownView; t: number; dur: number } | null = null;",
    "  let camTween: { from: TownView; to: TownView; t: number; dur: number; tf?: THREE.Vector3; tt?: THREE.Vector3 } | null = null;")
rep("      view.current = { yaw: lerp(from.yaw, to.yaw, e), tilt: lerp(from.tilt, to.tilt, e), zoom: lerp(from.zoom, to.zoom, e) };",
    "      view.current = { yaw: lerp(from.yaw, to.yaw, e), tilt: lerp(from.tilt, to.tilt, e), zoom: lerp(from.zoom, to.zoom, e) };\n      if (camTween.tf && camTween.tt) TGT.lerpVectors(camTween.tf, camTween.tt, e);")
rep("""  const tweenTo = (to: Partial<TownView>, dur: number) => {
    takeOver();
    camTween = { from: { ...view.current }, to: { ...view.current, ...to }, t: 0, dur: reduced ? 0 : dur };
    invalidate();
  };""",
    """  const tweenTo = (to: Partial<TownView>, dur: number, target?: THREE.Vector3) => {
    takeOver();
    camTween = { from: { ...view.current }, to: { ...view.current, ...to }, t: 0, dur: reduced ? 0 : dur, tf: target ? TGT.clone() : undefined, tt: target };
    invalidate();
  };""")
# flyTo is used by the state pills, which are built before tweenTo: a hoisted function that defers to it
rep("  /* ======== DOM labels: pills projected from 3D anchors; fixed ones never dropped, tags culled on collision ======== */",
    """  function flyTo(key: string) {
    if (key === 'all') return tweenTo({ zoom: 0.19, tilt: 62 * DEG }, 0.9, v3(mapXZ(112, 14)).setY(0));
    if (key === 'selangor' || key === 'home') return tweenTo({ ...DEFAULT_VIEW }, 0.8, HOME_TGT.clone());
    const d = STATE_BY[key];
    const [x, z] = centreOf(key);
    tweenTo({ zoom: clamp(24 / Math.max(d.rx, d.ry, 9), 0.55, 1.6), tilt: DEFAULT_VIEW.tilt }, 0.9, new THREE.Vector3(x, 0, z));
  }
  /* ======== DOM labels: pills projected from 3D anchors; fixed ones never dropped, tags culled on collision ======== */""")
rep("""      view.current = { ...view.current, yaw: DEFAULT_VIEW.yaw + dy };
      tweenTo(DEFAULT_VIEW, 0.5);""",
    """      view.current = { ...view.current, yaw: DEFAULT_VIEW.yaw + dy };
      tweenTo(DEFAULT_VIEW, 0.5, HOME_TGT.clone());""")
rep("  return {\n    dispose,\n", "  return {\n    flyTo,\n    dispose,\n")

# ---------------------------------------------------------------- tips: the map's own subjects carry their text
rep("      hover({ ...townTip(snapshot, tip()), x: r.left + r.width / 2 - st.left, y: r.top - st.top });",
    "      hover({ ...tipText(tip()), x: r.left + r.width / 2 - st.left, y: r.top - st.top });")
rep("    hover({ ...townTip(snapshot, subject), x: hit.x, y: hit.y });", "    hover({ ...tipText(subject), x: hit.x, y: hit.y });")
rep("  let labels: Label[] = [];",
    "  const tipText = (s: TipSubject) => ((s as unknown as { kind: string }).kind === 'raw' ? { title: (s as unknown as { title: string }).title, detail: (s as unknown as { detail: string }).detail } : townTip(snapshot, s));\n  let labels: Label[] = [];")
open(p, 'w').write(t)
print('patch2 ok')
