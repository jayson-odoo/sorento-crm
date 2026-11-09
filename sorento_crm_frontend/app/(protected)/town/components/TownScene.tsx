'use client';

import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { Badge } from '@/components/ui/badge';
import { localStore } from '@/lib/storage';
import type { TownSnapshot } from '@/types/town.types';
import { changePercent, count, rm0, clampInView, sceneSelection, stackTags, tagLabel, townFrame } from '../lib/townFormat';
import type { TownTarget } from './TownPanel';

/**
 * The town in 3D, ported from the approved mock (`documentation/plans/dashboard/mock/sorento-town-mock.html`,
 * `buildScene`). Five things, each answering one question: the scoreboard, the dealer shops (lit when
 * they bought today), the warehouse district with one red "!", the depot with lorries, the approvals
 * office. Orthographic camera, instanced meshes, no shadows, rendered on demand only (nothing moves),
 * 30 fps while dragging, nothing drawn while the tab is hidden. The scene is rebuilt when the snapshot
 * changes (a 304 keeps the same object, so a quiet poll rebuilds nothing); the camera angle survives.
 */

const HINT_KEY = 'town_hint_seen';
const HINT_MS = 6000;
const LORRY_CAP = 10;
const BOARD_Y = 9.2; // the scoreboard's height above the plaza, and its size
const BOARD_W = 16.4;
const BOARD_H = 6.4;
const BOARD_LOOK_Y = 3; // what the camera looks at: the island's centre on screen

const polar = (r: number, deg: number): [number, number] => [
  Math.cos((deg * Math.PI) / 180) * r,
  Math.sin((deg * Math.PI) / 180) * r,
];
const face = (x: number, z: number) => Math.atan2(x, z) + Math.PI;

function part(
  geo: THREE.BufferGeometry,
  color: number,
  x = 0, y = 0, z = 0,
  sx = 1, sy = 1, sz = 1,
  ry = 0, rx = 0,
): THREE.BufferGeometry {
  const g = geo.index ? geo.toNonIndexed() : geo.clone();
  g.applyMatrix4(
    new THREE.Matrix4().compose(
      new THREE.Vector3(x, y, z),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, 0)),
      new THREE.Vector3(sx, sy, sz),
    ),
  );
  const c = new THREE.Color(color);
  const k = g.attributes.position.count;
  const arr = new Float32Array(k * 3);
  for (let i = 0; i < k; i++) arr.set([c.r, c.g, c.b], i * 3);
  g.setAttribute('color', new THREE.BufferAttribute(arr, 3));
  g.deleteAttribute('uv');
  return g;
}

function merge(parts: THREE.BufferGeometry[]): THREE.BufferGeometry {
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
  return out;
}

const BOX = new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0);
const CYL = (r1: number, r2: number, h: number, s = 16) =>
  new THREE.CylinderGeometry(r1, r2, h, s).translate(0, h / 2, 0);
const PRISM = (() => {
  const g = new THREE.CylinderGeometry(0.5, 0.5, 1, 3);
  g.rotateZ(Math.PI / 2);
  g.rotateX(Math.PI / 2);
  g.rotateY(Math.PI / 2);
  g.translate(0, 0.25, 0);
  return g;
})();

type Pickable = [THREE.Object3D, (instanceId: number) => void];

function mountScene(
  canvas: HTMLCanvasElement,
  snapshot: TownSnapshot,
  yawRef: { current: number },
  select: (target: TownTarget) => void,
): () => void {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  const scene = new THREE.Scene();
  const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 400);
  let frameId = 0;
  let last = 0;
  let disposed = false;

  const frame = (now: number) => {
    frameId = 0;
    if (disposed || document.hidden) return; // a hidden tab draws nothing; visibilitychange asks again
    if (now - last < 33) {
      frameId = requestAnimationFrame(frame);
      return;
    }
    last = now;
    renderer.render(scene, cam);
  };
  const invalidate = () => {
    if (!frameId && !disposed) frameId = requestAnimationFrame(frame);
  };

  // name tags: re-stacked in screen space whenever the camera turns or the view resizes, so they never
  // cover each other or any fixed label (the scoreboard, the "!" bubble, the depot sign, the approvals
  // badge, the "+N more dealers" pill), and none is clipped at the top. They are in priority order
  // (busiest first); the lowest priority is dropped before one is clipped. The pill is also kept
  // inside the canvas after the town is turned.
  const tagSprites: { sprite: THREE.Sprite; anchor: THREE.Vector3 }[] = [];
  const fixedLabels: THREE.Sprite[] = [];
  const fixed = (sprite: THREE.Sprite) => {
    fixedLabels.push(sprite);
    return sprite;
  };
  let pill: { sprite: THREE.Sprite; anchor: THREE.Vector3 } | null = null;
  const layoutTags = () => {
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(cam.quaternion);
    const box = (position: THREE.Vector3, sprite: THREE.Sprite) => ({
      x: position.dot(right), y: position.dot(up), w: sprite.scale.x, h: sprite.scale.y,
    });
    const centreY = BOARD_LOOK_Y * up.y; // what the camera looks at, on screen
    if (pill) {
      const at = box(pill.anchor, pill.sprite);
      const view = { left: cam.left, right: cam.right, bottom: centreY + cam.bottom, top: centreY + cam.top };
      const spot = clampInView(at, view);
      pill.sprite.position.copy(pill.anchor).addScaledVector(right, spot.x - at.x).addScaledVector(up, spot.y - at.y);
    }
    if (!tagSprites.length) return;
    const obstacles = [
      // the scoreboard: always facing the camera, 16.4 wide, 6.4 tall (foreshortened by the elevation), centred 9.2 up
      { x: 0, y: BOARD_Y * up.y, w: BOARD_W, h: BOARD_H * up.y },
      ...fixedLabels.map((sprite) => box(sprite.position, sprite)),
    ];
    const top = centreY + cam.top - 0.3;
    const raise = stackTags(tagSprites.map(({ sprite, anchor }) => box(anchor, sprite)), 0.3, { obstacles, top });
    tagSprites.forEach(({ sprite, anchor }, i) => {
      const lift = raise[i];
      sprite.visible = lift !== null;
      if (lift !== null) sprite.position.set(anchor.x, anchor.y + lift / up.y, anchor.z);
    });
  };
  const placeCam = () => {
    cam.position.set(Math.cos(yawRef.current) * 80, 70, Math.sin(yawRef.current) * 80);
    cam.lookAt(0, BOARD_LOOK_Y, 0); // the island's centre on screen: its ellipse and the scoreboard above it
    cam.updateMatrixWorld();
    layoutTags();
    invalidate();
  };
  const resize = () => {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    const a = w / h;
    const z = townFrame(a, w < 640);
    cam.left = -z * a;
    cam.right = z * a;
    cam.top = z;
    cam.bottom = -z;
    cam.updateProjectionMatrix();
    layoutTags();
    invalidate();
  };

  scene.add(new THREE.HemisphereLight(0xffffff, 0xb6c2b0, snapshot.phase === 'night' ? 0.55 : 2.0));
  const sun = new THREE.DirectionalLight(0xffffff, snapshot.phase === 'night' ? 0.2 : 1.3);
  sun.position.set(-25, 50, 30);
  scene.add(sun);

  const night = snapshot.phase === 'night';
  const M = new THREE.Matrix4();
  const Q = new THREE.Quaternion();
  const V = new THREE.Vector3();
  const S = new THREE.Vector3();
  const E = new THREE.Euler();
  const lambert = () => new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });
  const pickables: Pickable[] = [];

  // ground: one calm disc, a ring road, four short spokes
  scene.add(
    new THREE.Mesh(
      merge([
        part(CYL(27, 28, 1.2, 48), 0xe7e2d6, 0, -1.2),
        part(CYL(26.6, 26.6, 0.1, 48), 0xd9e8cf, 0, -0.1),
        part(CYL(9.5, 9.5, 0.06, 48), 0xc4c9cf, 0, 0),
        part(CYL(7.3, 7.3, 0.08, 48), 0xf3efe6, 0, 0),
        ...[0, 90, 180, 270].map((a) => {
          const [x, z] = polar(14, a);
          return part(BOX, 0xc4c9cf, x, 0, z, 9, 0.06, 2.2, (-a * Math.PI) / 180);
        }),
      ]),
      new THREE.MeshLambertMaterial({ vertexColors: true }),
    ),
  );

  // one label style, always readable
  const small = canvas.clientWidth < 640;
  function label(text: string, x: number, y: number, z: number, bg: string, fg: string, w = 360, scale = 1) {
    const c = document.createElement('canvas');
    c.width = w * 2;
    c.height = 112;
    const g = c.getContext('2d');
    if (g) {
      g.fillStyle = bg;
      g.beginPath();
      g.roundRect(4, 4, c.width - 8, 104, 40);
      g.fill();
      g.fillStyle = fg;
      g.font = '600 52px Inter, sans-serif';
      const wide = g.measureText(text).width;
      if (wide > c.width - 48) g.font = `600 ${Math.floor((52 * (c.width - 48)) / wide)}px Inter, sans-serif`;
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      g.fillText(text, c.width / 2, 58);
    }
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
    sprite.renderOrder = 10;
    const k = (small ? 2.0 : 1.4) * scale;
    sprite.scale.set((c.width / 70) * k, (c.height / 70) * k, 1);
    sprite.position.set(x, y, z);
    scene.add(sprite);
    return sprite;
  }

  // (1) scoreboard over the plaza
  const full = snapshot.today.amount != null;
  const pct = changePercent(snapshot);
  const board = document.createElement('canvas');
  board.width = 1024;
  board.height = 400;
  const g = board.getContext('2d');
  if (g) {
    g.fillStyle = night ? '#0b1220' : '#0f172a';
    g.beginPath();
    g.roundRect(0, 0, 1024, 400, 36);
    g.fill();
    g.textAlign = 'center';
    g.fillStyle = '#94a3b8';
    g.font = '600 46px Inter, sans-serif';
    g.fillText(night ? 'CLOSED FOR THE DAY' : 'SOLD TODAY', 512, 74);
    g.fillStyle = '#ffffff';
    g.font = '700 112px Inter, sans-serif';
    g.fillText(full ? rm0(snapshot.today.amount as string) : `${count(snapshot.today.invoice_count)} invoices`, 512, 200);
    g.font = '600 48px Inter, sans-serif';
    g.fillStyle = '#cbd5e1';
    const line =
      (full ? `${count(snapshot.today.invoice_count)} invoices   ` : '') +
      (pct == null || !snapshot.compare
        ? ''
        : `${pct >= 0 ? '▲' : '▼'} ${Math.abs(pct).toFixed(0)}% vs all of ${snapshot.compare.label}`);
    g.fillText(line, 512, 300);
  }
  const boardTex = new THREE.CanvasTexture(board);
  boardTex.anisotropy = 4;
  const boardGroup = new THREE.Group();
  boardGroup.add(
    new THREE.Mesh(
      merge([
        part(CYL(0.3, 0.35, 6.2, 8), 0x475569, -6.2, 0, 0),
        part(CYL(0.3, 0.35, 6.2, 8), 0x475569, 6.2, 0, 0),
        part(CYL(1.1, 1.3, 0.4, 16), 0x94a3b8, -6.2, 0, 0),
        part(CYL(1.1, 1.3, 0.4, 16), 0x94a3b8, 6.2, 0, 0),
      ]),
      lambert(),
    ),
  );
  const boardFace = new THREE.Mesh(
    new THREE.PlaneGeometry(BOARD_W, BOARD_H),
    new THREE.MeshBasicMaterial({ map: boardTex, transparent: true }),
  );
  boardFace.position.y = BOARD_Y;
  boardFace.renderOrder = 5; // under every label (10), so a tag never ends up behind the scoreboard
  boardGroup.add(boardFace);
  scene.add(boardGroup);
  pickables.push([boardFace, () => select({ kind: 'sales' })]);
  const faceBoard = () => boardGroup.rotation.set(0, Math.atan2(cam.position.x, cam.position.z), 0);

  // (2) dealer shops in one calm crescent: grey unless bought today; lit ones get a tag
  const { drawn, tagged, others } = sceneSelection(snapshot);
  const list = drawn.filter((s) => s.kind === 'shop');
  drawn.filter((s) => s.kind !== 'shop').forEach((s, k) => list.splice(Math.min(list.length, 4 + k * 9), 0, s));
  const slot = list.map((s, i) => {
    const a = -78 + i * (156 / Math.max(1, list.length - 1));
    const [x, z] = polar(i % 2 ? 22 : 18.5, a);
    return { s, x, z, ry: face(x, z), lit: s.today_docs > 0, h: 1.8 + (s.rank ? ((30 - s.rank) / 30) * 1.6 : 0.6) };
  });
  const shopMesh = new THREE.InstancedMesh(
    merge([
      part(BOX, 0xffffff, 0, 0, 0, 2, 1, 1.8),
      part(PRISM, 0xffffff, 0, 1, 0, 2.3, 1.1, 2.0),
      part(BOX, 0xffffff, 0, 0.55, 1.05, 1.9, 0.08, 0.5, 0, -0.4),
    ]),
    new THREE.MeshLambertMaterial({ flatShading: true }),
    Math.max(1, slot.length),
  );
  slot.forEach((o, i) => {
    M.compose(V.set(o.x, 0, o.z), Q.setFromEuler(E.set(0, o.ry, 0)), S.set(1, o.h / 1.8, 1));
    shopMesh.setMatrixAt(i, M);
    const lit = night ? 0xfde68a : 0xfbbf24;
    shopMesh.setColorAt(i, new THREE.Color(o.lit ? lit : night ? 0x57534e : 0xd6d3d1));
  });
  shopMesh.count = slot.length;
  scene.add(shopMesh);
  pickables.push([shopMesh, (i) => slot[i] && select({ kind: 'shop', key: slot[i].s.key })]);
  [...tagged]
    .map((shop) => slot.find((o) => o.s === shop))
    .forEach((o) => {
      if (!o) return;
      const anchor = new THREE.Vector3(o.x, o.h + 2.6, o.z);
      const sprite = label(tagLabel(o.s), anchor.x, anchor.y, anchor.z, 'rgba(255,251,235,0.97)', '#92400e', 480, 0.85);
      tagSprites.push({ sprite, anchor });
    });
  if (others) {
    const [x, z] = polar(24, 30);
    const sprite = label(`+${others} more dealers bought today`, x, 2.4, z, 'rgba(255,251,235,0.97)', '#92400e', 520, 0.95);
    pill = { sprite, anchor: sprite.position.clone() };
    fixed(sprite);
  }

  // (3) warehouse district: a few calm buildings, one red "!" bubble
  const whSlot = snapshot.warehouses.slice(0, 6).map((w, i) => {
    const [x, z] = polar(i < 3 ? 15 : 21, 160 + (i % 3) * 22);
    return { w, x, z, ry: face(x, z) };
  });
  const barrel = new THREE.CylinderGeometry(1, 1, 1, 14, 1, false, 0, Math.PI);
  barrel.rotateZ(Math.PI / 2);
  barrel.rotateY(Math.PI / 2);
  const whMesh = new THREE.InstancedMesh(
    merge([
      part(BOX, 0xe2e8f0, 0, 0, 0, 4, 1.6, 3),
      part(barrel, 0x94a3b8, 0, 1.6, 0, 2, 0.8, 1.5, Math.PI / 2),
      part(BOX, 0xcbd5e1, 0, 0.02, 1.52, 2.2, 1.1, 0.04),
    ]),
    lambert(),
    Math.max(1, whSlot.length),
  );
  whSlot.forEach((o, i) => {
    M.compose(V.set(o.x, 0, o.z), Q.setFromEuler(E.set(0, o.ry, 0)), S.set(1, 1, 1));
    whMesh.setMatrixAt(i, M);
  });
  whMesh.count = whSlot.length;
  scene.add(whMesh);
  pickables.push([whMesh, () => select({ kind: 'low' })]);
  const [bx, bz] = polar(18, 182);
  pickables.push([
    fixed(label(`!  ${count(snapshot.reorder.below_count)} low`, bx, 7, bz, '#dc2626', '#ffffff', 300, 1.05)),
    () => select({ kind: 'low' }),
  ]);

  // (4) depot with lorries lined up
  const deliveries = snapshot.deliveries;
  const [dx, dz] = polar(18, 248);
  const dry = face(dx, dz);
  const depot = new THREE.Mesh(
    merge([
      part(BOX, 0xe0e7ff, 0, 0, 0, 6, 2.2, 3.4),
      part(BOX, 0x93c5fd, 0, 2.2, 0, 6.3, 0.25, 3.7),
      part(BOX, 0xbfdbfe, -1.5, 0.02, 1.71, 1.8, 1.6, 0.04),
      part(BOX, 0xbfdbfe, 1.5, 0.02, 1.71, 1.8, 1.6, 0.04),
    ]),
    lambert(),
  );
  depot.position.set(dx, 0, dz);
  depot.rotation.y = dry;
  scene.add(depot);
  pickables.push([depot, () => select({ kind: 'deliver' })]);
  const lorryN = Math.min(LORRY_CAP, deliveries ? deliveries.to_deliver : 0);
  const lorries = new THREE.InstancedMesh(
    merge([
      part(BOX, 0xffffff, 0.35, 0.22, 0, 1.4, 0.95, 0.85),
      part(BOX, 0x2563eb, -0.7, 0.22, 0, 0.6, 0.75, 0.82),
      ...[-0.65, 0.6].flatMap((x) =>
        [-0.42, 0.42].map((z) => part(CYL(0.2, 0.2, 0.12, 10), 0x1f2937, x, 0.2, z, 1, 1, 1, 0, Math.PI / 2)),
      ),
    ]),
    lambert(),
    Math.max(1, lorryN),
  );
  const fwd = new THREE.Vector3(Math.sin(dry), 0, Math.cos(dry));
  const side = new THREE.Vector3(Math.cos(dry), 0, -Math.sin(dry));
  for (let i = 0; i < lorryN; i++) {
    const p = new THREE.Vector3(dx, 0, dz)
      .addScaledVector(fwd, 3.2 + Math.floor(i / 5) * 1.3)
      .addScaledVector(side, -2.4 + (i % 5) * 1.2);
    M.compose(p, Q.setFromEuler(E.set(0, dry + Math.PI / 2, 0)), S.set(0.8, 0.8, 0.8));
    lorries.setMatrixAt(i, M);
  }
  lorries.count = lorryN;
  scene.add(lorries);
  pickables.push([lorries, () => select({ kind: 'deliver' })]);
  pickables.push([
    fixed(label(`To deliver: ${deliveries ? count(deliveries.to_deliver) : '-'}`, dx, 5.4, dz, '#1d4ed8', '#ffffff', 380, 0.9)),
    () => select({ kind: 'deliver' }),
  ]);

  // (5) approvals office with a badge
  const total = snapshot.approvals.total;
  const [ox, oz] = polar(16, 112);
  const office = new THREE.Mesh(
    merge([
      part(BOX, 0xf5f3ff, 0, 0, 0, 3.6, 3.2, 3),
      part(BOX, 0xddd6fe, 0, 3.2, 0, 3.9, 0.3, 3.3),
      part(BOX, 0xc4b5fd, 0, 0.02, 1.52, 1, 1.6, 0.04),
    ]),
    lambert(),
  );
  office.position.set(ox, 0, oz);
  office.rotation.y = face(ox, oz);
  scene.add(office);
  pickables.push([office, () => select({ kind: 'approve' })]);
  pickables.push([
    fixed(
      label(
        total ? `Approvals  ${total}` : 'Approvals: all clear',
        ox, 6, oz,
        total ? '#7c3aed' : '#dcfce7',
        total ? '#ffffff' : '#166534',
        380, 0.9,
      ),
    ),
    () => select({ kind: 'approve' }),
  ]);

  // a handful of trees only, for softness
  const treeAt = [[-6, 6], [6, -6], [-6, -6], [6.2, 6.2], ...[0, 72, 144, 216, 288].map((a) => polar(25, a + 30))];
  const trees = new THREE.InstancedMesh(
    merge([
      part(CYL(0.14, 0.18, 0.8, 6), 0xa16207),
      part(new THREE.IcosahedronGeometry(0.8, 1).translate(0, 1.4, 0), 0x86c17a),
    ]),
    lambert(),
    treeAt.length,
  );
  treeAt.forEach(([x, z], i) => {
    M.compose(V.set(x, 0, z), Q.identity(), S.setScalar(0.9));
    trees.setMatrixAt(i, M);
  });
  scene.add(trees);

  // input: drag turns the town, a tap picks a building
  const ray = new THREE.Raycaster();
  const ptr = new THREE.Vector2();
  let drag: { x: number; yaw: number; moved: boolean } | null = null;
  const onDown = (e: PointerEvent) => {
    drag = { x: e.clientX, yaw: yawRef.current, moved: false };
  };
  const onMove = (e: PointerEvent) => {
    if (!drag) return;
    const dxp = e.clientX - drag.x;
    if (Math.abs(dxp) > 4) drag.moved = true;
    if (drag.moved) {
      yawRef.current = drag.yaw - dxp * 0.006;
      placeCam();
      faceBoard();
    }
  };
  const onUp = (e: PointerEvent) => {
    const moved = drag?.moved;
    drag = null;
    if (moved || e.target !== canvas) return;
    const r = canvas.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, cam);
    const hits = ray.intersectObjects(pickables.map((p) => p[0]), false);
    if (!hits.length) return;
    pickables.find((p) => p[0] === hits[0].object)?.[1](hits[0].instanceId ?? 0);
  };
  const onVisible = () => {
    if (!document.hidden) invalidate();
  };
  canvas.addEventListener('pointerdown', onDown);
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  document.addEventListener('visibilitychange', onVisible);
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  placeCam();
  faceBoard();
  resize();

  return () => {
    disposed = true;
    if (frameId) cancelAnimationFrame(frameId);
    canvas.removeEventListener('pointerdown', onDown);
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    document.removeEventListener('visibilitychange', onVisible);
    observer.disconnect();
    scene.traverse((object) => {
      const item = object as THREE.Mesh;
      item.geometry?.dispose();
      const materials = Array.isArray(item.material) ? item.material : item.material ? [item.material] : [];
      for (const material of materials) {
        (material as THREE.MeshBasicMaterial).map?.dispose();
        material.dispose();
      }
    });
    shopMesh.dispose();
    whMesh.dispose();
    lorries.dispose();
    trees.dispose();
    renderer.dispose();
  };
}

const LEGEND = [
  ['bg-amber-500', 'Lit shop = bought today'],
  ['bg-red-600', 'Red ! = low stock'],
  ['bg-blue-600', 'Lorries = to deliver'],
  ['bg-violet-600', 'Badge = waiting approval'],
] as const;

export function TownScene({
  snapshot,
  onSelect,
}: {
  snapshot: TownSnapshot;
  onSelect: (target: TownTarget) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const yawRef = useRef(Math.PI / 4);
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const [hint, setHint] = useState(() => !localStore.getItem(HINT_KEY));

  const dismissHint = () => {
    setHint(false);
    localStore.setItem(HINT_KEY, '1');
  };

  useEffect(() => {
    if (!hint) return;
    const timer = window.setTimeout(dismissHint, HINT_MS);
    return () => window.clearTimeout(timer);
  }, [hint]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    return mountScene(canvas, snapshot, yawRef, (target) => {
      dismissHint();
      selectRef.current(target);
    });
  }, [snapshot]);

  return (
    <div
      className={`flex flex-col overflow-hidden rounded-xl border border-border sm:h-[calc(100dvh-20rem)] sm:min-h-[22rem] sm:max-h-[41rem] ${
        snapshot.phase === 'night' ? 'bg-slate-800' : 'bg-sky-50 dark:bg-slate-800'
      }`}
    >
      <div className="relative aspect-[3/2] sm:aspect-auto sm:min-h-0 sm:flex-1">
        <canvas ref={canvasRef} aria-label="Town" className="absolute inset-0 block size-full touch-none" />
        {snapshot.phase === 'night' ? (
          <Badge variant="secondary" size="lg" className="absolute start-1/2 top-2.5 -translate-x-1/2">
            Closed for the day
          </Badge>
        ) : null}
        {hint ? (
          <div className="pointer-events-none absolute start-1/2 top-3 -translate-x-1/2 rounded-lg border border-border bg-background/80 px-3.5 py-2 text-sm font-semibold backdrop-blur">
            Tap any building
          </div>
        ) : null}
      </div>
      <div
        role="group"
        className="grid grid-cols-2 gap-x-3 gap-y-1 border-t border-border bg-background/80 px-3 py-2 text-xs sm:flex sm:flex-wrap"
        aria-label="Legend"
      >
        {LEGEND.map(([tone, text]) => (
          <div key={text} className="flex items-center gap-2">
            <span aria-hidden="true" className={`inline-block size-3 shrink-0 rounded-sm ${tone}`} />
            {text}
          </div>
        ))}
      </div>
    </div>
  );
}
