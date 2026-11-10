'use client';

import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { Minus, Plus, RotateCcw } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { localStore } from '@/lib/storage';
import type { TownSnapshot } from '@/types/town.types';
import { changePercent, count, rm0, sceneSelection, separateLabels, stackTags, tagLabel, townFrame } from '../lib/townFormat';
import { DEFAULT_VIEW, cameraPosition, dragView, pinchZoom, stepZoom, wheelZoom, type TownView } from '../lib/townCamera';
import { townTip, type TipSubject } from '../lib/townTips';
import type { TownTarget } from './TownLightbox';

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
const PORT_DEG = 226; // behind the warehouses and the depot: the top of the default view
const PORT_SHIP_CAP = 6;
const PORT_BOX_CAP = 12;
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

/** A clickable thing: what a click / tap opens, and what the mouse tooltip names. */
type Pickable = [THREE.Object3D, (instanceId: number) => void, (instanceId: number) => TipSubject | null];

export interface TownTipState {
  title: string;
  detail: string;
  x: number;
  y: number;
}

export interface SceneHandle {
  dispose: () => void;
  setView: (view: TownView) => void;
}

function mountScene(
  canvas: HTMLCanvasElement,
  snapshot: TownSnapshot,
  viewRef: { current: TownView },
  select: (target: TownTarget) => void,
  hover: (tip: TownTipState | null) => void,
): SceneHandle {
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

  // Labels are laid out in screen space whenever the camera turns or the view resizes. First the fixed
  // ones (the "!" bubble, the depot sign, the approvals badge, the "+N more dealers" pill) are moved up or
  // down the screen until they clear the scoreboard and each other, inside the canvas, never dropped
  // (`separateLabels`). Then the name tags are stacked around the scoreboard and those moved labels, in
  // priority order (busiest first); the lowest priority is dropped before one is clipped.
  const tagSprites: { sprite: THREE.Sprite; anchor: THREE.Vector3 }[] = [];
  const fixedLabels: { sprite: THREE.Sprite; anchor: THREE.Vector3 }[] = [];
  const fixed = (sprite: THREE.Sprite) => {
    fixedLabels.push({ sprite, anchor: sprite.position.clone() });
    return sprite;
  };
  const layoutTags = () => {
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(cam.quaternion);
    const box = (position: THREE.Vector3, sprite: THREE.Sprite) => ({
      x: position.dot(right), y: position.dot(up), w: sprite.scale.x, h: sprite.scale.y,
    });
    const centreY = BOARD_LOOK_Y * up.y; // what the camera looks at, on screen
    // the scoreboard: always facing the camera, 16.4 wide, 6.4 tall (foreshortened by the elevation), centred 9.2 up
    const board = { x: 0, y: BOARD_Y * up.y, w: BOARD_W, h: BOARD_H * up.y };
    const z = cam.zoom; // a zoomed camera shows less of the town: the labels stay inside what is shown
    const view = { left: cam.left / z, right: cam.right / z, bottom: centreY + cam.bottom / z, top: centreY + cam.top / z };
    // the fixed labels first: clear of the scoreboard and of each other, inside the canvas, never dropped
    const at = fixedLabels.map(({ sprite, anchor }) => box(anchor, sprite));
    const spots = separateLabels(at, board, view);
    fixedLabels.forEach(({ sprite, anchor }, i) => {
      sprite.position.copy(anchor).addScaledVector(right, spots[i].x - at[i].x).addScaledVector(up, spots[i].y - at[i].y);
    });
    if (!tagSprites.length) return;
    const obstacles = [board, ...fixedLabels.map(({ sprite }) => box(sprite.position, sprite))];
    const raise = stackTags(tagSprites.map(({ sprite, anchor }) => box(anchor, sprite)), 0.3, {
      obstacles,
      top: view.top - 0.3,
    });
    tagSprites.forEach(({ sprite, anchor }, i) => {
      const lift = raise[i];
      sprite.visible = lift !== null;
      if (lift !== null) sprite.position.set(anchor.x, anchor.y + lift / up.y, anchor.z);
    });
  };
  const placeCam = () => {
    cam.position.set(...cameraPosition(viewRef.current, BOARD_LOOK_Y));
    cam.lookAt(0, BOARD_LOOK_Y, 0); // the island's centre on screen: its ellipse and the scoreboard above it
    cam.zoom = viewRef.current.zoom;
    cam.updateProjectionMatrix();
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
  pickables.push([boardFace, () => select({ kind: 'sales' }), () => ({ kind: 'sales' })]);
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
  pickables.push([
    shopMesh,
    (i) => slot[i] && select({ kind: 'shop', key: slot[i].s.key }),
    (i) => (slot[i] ? { kind: 'shop', shop: slot[i].s } : null),
  ]);
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
  pickables.push([whMesh, () => select({ kind: 'low' }), (i) => ({ kind: 'warehouse', index: i })]);
  const [bx, bz] = polar(18, 182);
  pickables.push([
    fixed(label(`!  ${count(snapshot.reorder.below_count)} low`, bx, 7, bz, '#dc2626', '#ffffff', 300, 1.05)),
    () => select({ kind: 'low' }),
    () => ({ kind: 'low' }),
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
  pickables.push([depot, () => select({ kind: 'deliver' }), () => ({ kind: 'deliver' })]);
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
  pickables.push([lorries, () => select({ kind: 'deliver' }), () => ({ kind: 'deliver' })]);
  pickables.push([
    fixed(label(`To deliver: ${deliveries ? count(deliveries.to_deliver) : '-'}`, dx, 5.4, dz, '#1d4ed8', '#ffffff', 380, 0.9)),
    () => select({ kind: 'deliver' }),
    () => ({ kind: 'deliver' }),
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
  pickables.push([office, () => select({ kind: 'approve' }), () => ({ kind: 'approve' })]);
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
    () => ({ kind: 'approve' }),
  ]);

  // (6) the port (TOWN-V2): a plain dock behind the warehouses and the depot. Ships on the water are the
  // incoming shipments, red containers on the quay the late ones (at most 6 and 12 drawn; the signs keep
  // the exact counts). Plain shapes on purpose: the look and the motion come with the owner's v6 pick.
  const incoming = snapshot.incoming;
  const portMeshes: THREE.InstancedMesh[] = [];
  if (incoming) {
    const openPort = () => select({ kind: 'port' });
    const portTip = (): TipSubject => ({ kind: 'port' });
    const [qx, qz] = polar(28.6, PORT_DEG);
    const qry = face(qx, qz);
    const [wx, wz] = polar(34, PORT_DEG);
    const water = new THREE.Mesh(merge([part(CYL(9, 9, 0.1, 40), 0x7dd3fc, wx, -0.9, wz)]), lambert());
    scene.add(water);
    const quay = new THREE.Mesh(
      merge([part(BOX, 0xcbd5e1, 0, -0.9, 0, 11, 0.9, 4.2), part(BOX, 0x0e7490, 4.3, 0, 1.2, 0.35, 5.2, 0.35)]),
      lambert(),
    );
    quay.position.set(qx, 0, qz);
    quay.rotation.y = qry;
    scene.add(quay);
    pickables.push([quay, openPort, portTip], [water, openPort, portTip]);
    const across = new THREE.Vector3(Math.cos(qry), 0, -Math.sin(qry));
    const inward = new THREE.Vector3(Math.sin(qry), 0, Math.cos(qry));
    const boxN = Math.min(PORT_BOX_CAP, incoming.late);
    const boxes = new THREE.InstancedMesh(merge([part(BOX, 0xdc2626, 0, 0, 0, 1.9, 0.8, 0.8)]), lambert(), Math.max(1, boxN));
    for (let i = 0; i < boxN; i++) {
      const k = i % 6;
      const p = new THREE.Vector3(qx, 0.8 * Math.floor(i / 6), qz)
        .addScaledVector(across, -3.2 + (k % 3) * 2.05)
        .addScaledVector(inward, k < 3 ? -0.3 : 0.6);
      M.compose(p, Q.setFromEuler(E.set(0, qry, 0)), S.set(1, 1, 1));
      boxes.setMatrixAt(i, M);
    }
    boxes.count = boxN;
    const shipN = Math.min(PORT_SHIP_CAP, incoming.incoming);
    const ships = new THREE.InstancedMesh(
      merge([
        part(BOX, 0x1e3a5f, 0, -0.5, 0, 6, 0.9, 1.9),
        part(BOX, 0xf8fafc, -2.1, 0.4, 0, 1.3, 1.1, 1.5),
        part(BOX, 0xf97316, 0.6, 0.4, 0, 2.6, 0.6, 1.5),
      ]),
      lambert(),
      Math.max(1, shipN),
    );
    for (let i = 0; i < shipN; i++) {
      const [x, z] = polar(31.5 + (i >= 3 ? 2.6 : 0), PORT_DEG - 14 + (i % 3) * 14 + (i >= 3 ? 7 : 0));
      M.compose(V.set(x, 0, z), Q.setFromEuler(E.set(0, face(x, z) + Math.PI / 2, 0)), S.setScalar(0.85));
      ships.setMatrixAt(i, M);
    }
    ships.count = shipN;
    scene.add(boxes, ships);
    portMeshes.push(boxes, ships);
    pickables.push([boxes, openPort, portTip], [ships, openPort, portTip]);
    const total = incoming.incoming + incoming.late;
    pickables.push([
      fixed(label(total ? `Incoming: ${count(incoming.incoming)}` : 'Incoming: none', qx, 7.2, qz, '#0e7490', '#ffffff', 340, 0.9)),
      openPort,
      portTip,
    ]);
    if (incoming.late) {
      pickables.push([
        fixed(label(`${count(incoming.late)} late`, qx, 3.4, qz, '#dc2626', '#ffffff', 220, 0.8)),
        openPort,
        portTip,
      ]);
    }
  }

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

  // input: drag sideways turns, drag up and down tilts, wheel / pinch zooms; a click or a tap opens a
  // building's lightbox; a mouse resting on one shows its tooltip (touch has no hover: a tap opens)
  const ray = new THREE.Raycaster();
  const ptr = new THREE.Vector2();
  let drag: { x: number; y: number; view: TownView; moved: boolean } | null = null;
  const touches = new Map<number, { x: number; y: number }>();
  let pinch: { distance: number; zoom: number } | null = null;
  let hovered: string | null = null;
  const spread = () => {
    const [a, b] = [...touches.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  };
  const pick = (clientX: number, clientY: number) => {
    const r = canvas.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    ptr.set(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, cam);
    const hits = ray.intersectObjects(pickables.map((p) => p[0]), false);
    if (!hits.length) return null;
    const found = pickables.find((p) => p[0] === hits[0].object);
    return found ? { pickable: found, instance: hits[0].instanceId ?? 0, x: clientX - r.left, y: clientY - r.top } : null;
  };
  const clearHover = () => {
    if (hovered === null) return;
    hovered = null;
    canvas.style.cursor = '';
    hover(null);
  };
  const setView = (view: TownView) => {
    viewRef.current = view;
    placeCam();
    faceBoard();
  };
  const onDown = (e: PointerEvent) => {
    touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (touches.size === 2) {
      pinch = { distance: spread(), zoom: viewRef.current.zoom };
      drag = null;
      return;
    }
    drag = { x: e.clientX, y: e.clientY, view: viewRef.current, moved: false };
  };
  const onMove = (e: PointerEvent) => {
    if (touches.has(e.pointerId)) touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && touches.size === 2) {
      setView({ ...viewRef.current, zoom: pinchZoom(pinch.zoom, pinch.distance, spread()) });
      return;
    }
    if (drag) {
      const dxp = e.clientX - drag.x;
      const dyp = e.clientY - drag.y;
      if (Math.hypot(dxp, dyp) > 4) drag.moved = true;
      if (drag.moved) {
        clearHover();
        setView(dragView(drag.view, dxp, dyp));
      }
      return;
    }
    if (e.pointerType !== 'mouse' || e.target !== canvas) return;
    const hit = pick(e.clientX, e.clientY);
    const subject = hit ? hit.pickable[2](hit.instance) : null;
    if (!hit || !subject) {
      clearHover();
      return;
    }
    hovered = `${hit.pickable[0].id}:${hit.instance}`;
    canvas.style.cursor = 'pointer';
    hover({ ...townTip(snapshot, subject), x: hit.x, y: hit.y });
  };
  const onUp = (e: PointerEvent) => {
    touches.delete(e.pointerId);
    if (touches.size < 2) pinch = null;
    const moved = drag?.moved;
    drag = null;
    if (moved || e.target !== canvas) return;
    const hit = pick(e.clientX, e.clientY);
    if (!hit) return;
    clearHover();
    hit.pickable[1](hit.instance);
  };
  const onCancel = (e: PointerEvent) => {
    touches.delete(e.pointerId);
    if (touches.size < 2) pinch = null;
    drag = null;
  };
  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    setView({ ...viewRef.current, zoom: wheelZoom(viewRef.current.zoom, e.deltaY) });
  };
  const onVisible = () => {
    if (!document.hidden) invalidate();
  };
  canvas.addEventListener('pointerdown', onDown);
  canvas.addEventListener('pointerleave', clearHover);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('pointercancel', onCancel);
  document.addEventListener('visibilitychange', onVisible);
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  placeCam();
  faceBoard();
  resize();

  const dispose = () => {
    disposed = true;
    if (frameId) cancelAnimationFrame(frameId);
    canvas.removeEventListener('pointerdown', onDown);
    canvas.removeEventListener('pointerleave', clearHover);
    canvas.removeEventListener('wheel', onWheel);
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', onCancel);
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
    portMeshes.forEach((mesh) => mesh.dispose());
    renderer.dispose();
  };
  return { dispose, setView };
}

const LEGEND = [
  ['bg-amber-500', 'Lit shop = bought today'],
  ['bg-red-600', 'Red ! = low stock'],
  ['bg-blue-600', 'Lorries = to deliver'],
  ['bg-violet-600', 'Badge = waiting approval'],
  ['bg-cyan-700', 'Ships = incoming, red boxes = late'],
] as const;

export function TownScene({
  snapshot,
  onSelect,
}: {
  snapshot: TownSnapshot;
  onSelect: (target: TownTarget) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewRef = useRef<TownView>(DEFAULT_VIEW);
  const sceneRef = useRef<SceneHandle | null>(null);
  const [tip, setTip] = useState<TownTipState | null>(null);
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
    const scene = mountScene(
      canvas,
      snapshot,
      viewRef,
      (target) => {
        dismissHint();
        selectRef.current(target);
      },
      setTip,
    );
    sceneRef.current = scene;
    return () => {
      sceneRef.current = null;
      setTip(null);
      scene.dispose();
    };
  }, [snapshot]);

  const changeView = (next: Partial<TownView>) => sceneRef.current?.setView({ ...viewRef.current, ...next });

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
        {tip ? (
          <div
            role="tooltip"
            className="pointer-events-none absolute z-10 max-w-64 -translate-x-1/2 -translate-y-full rounded-md border border-border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md"
            style={{ left: tip.x, top: tip.y - 12 }}
          >
            <div className="truncate font-semibold">{tip.title}</div>
            <div className="truncate text-muted-foreground">{tip.detail}</div>
          </div>
        ) : null}
        <div className="absolute bottom-2 end-2 flex gap-1 rounded-lg border border-border bg-background/80 p-1 backdrop-blur">
          <Button type="button" variant="ghost" mode="icon" size="sm" aria-label="Zoom out" title="Zoom out" onClick={() => changeView({ zoom: stepZoom(viewRef.current.zoom, -1) })}>
            <Minus />
          </Button>
          <Button type="button" variant="ghost" mode="icon" size="sm" aria-label="Zoom in" title="Zoom in" onClick={() => changeView({ zoom: stepZoom(viewRef.current.zoom, 1) })}>
            <Plus />
          </Button>
          <Button type="button" variant="ghost" mode="icon" size="sm" aria-label="Reset view" title="Reset view" onClick={() => changeView(DEFAULT_VIEW)}>
            <RotateCcw />
          </Button>
        </div>
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
