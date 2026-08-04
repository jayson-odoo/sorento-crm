'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import { roomBounds, type Box, type Point } from '@/lib/dealer-kit/roomGeometry';
import {
  openingSpans,
  placeOpeningOnNearestWall,
  wallPanels,
  type Opening,
} from '@/lib/dealer-kit/roomOpenings';
import { floorColor, wallColor, type Finishes } from '@/lib/dealer-kit/finishes';
// One definition of the placeholder size. Two would drift, and the drift would
// show up as a box that is a different size in the plan than in 3D.
export { UNKNOWN_SIZE_MM } from '@/lib/dealer-kit/roomBoxes';

/**
 * The room in 3D, with every product as a correctly-sized box.
 *
 * **Proxy boxes, not models.** Products already carry
 * `dimensions_length/width/height`, so a box is free, exact, and available for
 * the whole catalogue today. A model pipeline would cover the handful of SKUs
 * someone has modelled and leave the rest missing, which is worse than a room
 * of honest boxes. A box also cannot misrepresent a product: it claims to be a
 * volume and a name, nothing more.
 *
 * **Plain three.js, deliberately not react-three-fiber.** R3F augments the
 * global `JSX.IntrinsicElements` with the three.js element set, and many of
 * those are typed `children: never`. That collapses the children prop of every
 * POLYMORPHIC component in the app (anything rendering a generic
 * `ElementType`), breaking files that have nothing to do with 3D. One view is
 * not worth that blast radius, and an imperative scene is a hundred lines.
 *
 * **The scene is built ONCE and then kept in step.** It used to be rebuilt by a
 * single effect whose dependencies included `boxes`, which meant the first
 * pointermove of a drag - which moves a box - tore the canvas down and put a
 * fresh one up: the drag died on its first frame and the camera snapped back to
 * its opening framing, so dragging read as an accidental "refocus". So the
 * mount effect owns the renderer, camera, controls and input for the lifetime
 * of the view, and separate effects SYNC the room and the products into it.
 *
 * Three works in metres, the rest of the designer in millimetres, so the
 * conversion happens HERE, at the boundary, exactly once.
 */

const MM_TO_M = 0.001;

export interface SceneBox extends Box {
  id: string;
  label: string;
  heightMm: number;
  /** True when the product had no dimensions and this size is a guess. */
  isEstimated?: boolean;
}

/** A ceiling nobody typed. Standard Malaysian residential floor-to-ceiling. */
export const DEFAULT_CEILING_MM = 2700;

type Disposable = THREE.BufferGeometry | THREE.Material | THREE.Texture;

/** Draw the label onto a canvas texture - cheaper than a font loader. */
function labelTexture(text: string): THREE.Texture {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 64;
  const context = canvas.getContext('2d');
  if (context) {
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = '#0f172a';
    context.font = 'bold 28px sans-serif';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(text.slice(0, 16), canvas.width / 2, canvas.height / 2);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

interface BoxRecord {
  mesh: THREE.Mesh;
  edges: THREE.LineSegments;
  /** What the geometry was built from. A change here means a rebuild. */
  signature: string;
  disposables: Disposable[];
}

/** Everything the imperative scene owns, so effects can reach into it. */
interface SceneHandle {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  renderer: THREE.WebGLRenderer;
  /** Floor, walls and the invisible panes filling the openings. */
  roomGroup: THREE.Group;
  roomDisposables: Disposable[];
  wallMeshes: { mesh: THREE.Object3D; normal: THREE.Vector3 }[];
  openingPickable: THREE.Object3D[];
  boxGroup: THREE.Group;
  boxRecords: Map<string, BoxRecord>;
}

function boxSignature(box: SceneBox): string {
  return `${box.width}x${box.depth}x${box.heightMm}|${box.label}|${box.isEstimated ? 1 : 0}`;
}

function createBoxRecord(box: SceneBox): BoxRecord {
  const geometry = new THREE.BoxGeometry(
    box.width * MM_TO_M,
    box.heightMm * MM_TO_M,
    box.depth * MM_TO_M,
  );
  const texture = labelTexture(box.label);
  const plain = new THREE.MeshStandardMaterial({ color: '#94a3b8', roughness: 0.75 });
  const faced = new THREE.MeshStandardMaterial({ map: texture, roughness: 0.75 });
  // The name goes on the front face so the scene reads without clicking
  // anything (AC-V3). Face order is +x, -x, +y, -y, +z, -z.
  const mesh = new THREE.Mesh(geometry, [plain, plain, plain, plain, faced, plain]);
  mesh.userData.boxId = box.id;

  const edgeGeometry = new THREE.EdgesGeometry(geometry);
  const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x475569 });
  const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial);

  return {
    mesh,
    edges,
    signature: boxSignature(box),
    disposables: [geometry, plain, faced, texture, edgeGeometry, edgeMaterial],
  };
}

function releaseBoxRecord(handle: SceneHandle, record: BoxRecord) {
  handle.boxGroup.remove(record.mesh, record.edges);
  for (const item of record.disposables) item.dispose();
}

export function RoomScene({
  outline,
  boxes,
  selectedBoxId,
  selectionToolbar,
  onSelectBox,
  onMoveBox,
  onCommit,
  onMoveOpening,
  onSelectOpening,
  ceilingHeightMm = DEFAULT_CEILING_MM,
  openings = [],
  finishes,
}: {
  outline: Point[];
  boxes: SceneBox[];
  selectedBoxId?: string | null;
  /**
   * Buttons to float over the selected product.
   *
   * Passed in rather than built here: what can be done to a box is the
   * designer's business, and this component's job is only to say WHERE the box
   * is on screen.
   */
  selectionToolbar?: ReactNode;
  onSelectBox?: (boxId: string) => void;
  /** Dragging a product across the floor, in the same shape the plan uses. */
  onMoveBox?: (boxId: string, x: number, y: number, rotation: number) => void;
  /** End of a drag, so it becomes one undo step. */
  onCommit?: () => void;
  /** Sliding a door or window along its wall, from the 3D view. */
  onMoveOpening?: (openingId: string, offsetMm: number, wallIndex: number) => void;
  onSelectOpening?: (openingId: string) => void;
  /** Wall height. The only vertical measurement the room itself has. */
  ceilingHeightMm?: number;
  /** Doors and windows, cut out of the walls they belong to. */
  openings?: Opening[];
  /** Surface finishes, by id. */
  finishes?: Finishes;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const handleRef = useRef<SceneHandle | null>(null);
  const refocusRef = useRef<() => void>(() => {});

  // The scene is imperative and outlives every render, so it reads the current
  // props through refs rather than through a closure that would be stale by the
  // time a pointer event arrives.
  /**
   * Where the selected product is on screen, in canvas pixels.
   *
   * The actions belong ON the object, the way the plan puts them there: a bar
   * under the canvas makes the user look away from the thing they just clicked
   * to act on it. 3D has no element to hang them off - it is one canvas - so
   * the position is projected from the camera every frame and the toolbar is an
   * HTML overlay at that point.
   */
  const [selectionAt, setSelectionAt] = useState<{ x: number; y: number } | null>(null);
  // Through a ref so the render loop, which is created once, is not rebuilt
  // every time the position changes.
  const selectionAtRef = useRef(setSelectionAt);
  selectionAtRef.current = setSelectionAt;

  const dataRef = useRef({ outline, boxes, openings, selectedBoxId });
  dataRef.current = { outline, boxes, openings, selectedBoxId };

  const callbacksRef = useRef({
    onSelectBox,
    onMoveBox,
    onCommit,
    onMoveOpening,
    onSelectOpening,
  });
  callbacksRef.current = { onSelectBox, onMoveBox, onCommit, onMoveOpening, onSelectOpening };

  /** Mount: renderer, camera, controls, input, render loop. Built once. */
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const width = mount.clientWidth || 640;
    const height = mount.clientHeight || 420;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#f1f5f9');

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    // Zoom toward the cursor, not the orbit target: zooming to centre means
    // every zoom is followed by an orbit to get back to the corner you were
    // looking at.
    controls.zoomToCursor = true;

    // Refocus: put the camera back where it started, around the room as it is
    // NOW. An orbit that has ended up inside a wall is otherwise unrecoverable
    // without a reload.
    const frameCamera = () => {
      const bounds = roomBounds(dataRef.current.outline);
      const centre = new THREE.Vector3(
        ((bounds.minX + bounds.maxX) / 2) * MM_TO_M,
        0,
        ((bounds.minY + bounds.maxY) / 2) * MM_TO_M,
      );
      const span = Math.max(
        (bounds.maxX - bounds.minX) * MM_TO_M,
        (bounds.maxY - bounds.minY) * MM_TO_M,
        2,
      );
      camera.position.set(centre.x + span, span * 0.9, centre.z + span);
      controls.target.copy(centre);
      controls.update();
    };
    frameCamera();
    refocusRef.current = frameCamera;

    scene.add(new THREE.AmbientLight(0xffffff, 1.4));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(5, 10, 5);
    scene.add(sun);

    const roomGroup = new THREE.Group();
    const boxGroup = new THREE.Group();
    scene.add(roomGroup, boxGroup);

    const handle: SceneHandle = {
      scene,
      camera,
      controls,
      renderer,
      roomGroup,
      roomDisposables: [],
      wallMeshes: [],
      openingPickable: [],
      boxGroup,
      boxRecords: new Map(),
    };
    handleRef.current = handle;

    /**
     * Dragging in 3D.
     *
     * The plan is the precise tool, but a customer looking at the 3D view and
     * saying "put the basin over there" should not have to be told to switch
     * views first. So a product is dragged along the FLOOR plane: the pointer
     * ray is intersected with y=0 and the hit point becomes the new position,
     * which the plan then snaps to a wall exactly as it does for a plan drag.
     * Orbit is disabled while a product is under the pointer, or the camera
     * would spin instead.
     */
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    const hitPoint = new THREE.Vector3();
    let dragging: { boxId: string; grabDx: number; grabDz: number } | null = null;
    /**
     * An opening slides on a horizontal plane at its OWN height, not on the
     * floor. The pointer grabs a door partway up a wall, so a ray taken down to
     * the floor lands a metre or so beyond the room - harmless while the door
     * could only move along the wall it started on, but now that the nearest
     * wall decides where it lands, that error is enough to hop it round a
     * corner nobody dragged it round.
     */
    let draggingOpening: { openingId: string; plane: THREE.Plane } | null = null;

    const setPointer = (event: PointerEvent | MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
    };

    const boxMeshes = () =>
      Array.from(handle.boxRecords.values(), (record) => record.mesh as THREE.Object3D);

    const handleClick = (event: MouseEvent) => {
      setPointer(event);
      const hit = raycaster.intersectObjects(boxMeshes(), false)[0];
      const boxId = hit?.object.userData.boxId;
      if (typeof boxId === 'string') callbacksRef.current.onSelectBox?.(boxId);
    };

    /** Where the pointer lands on a horizontal plane, in the plan's millimetres. */
    const pointOn = (plane: THREE.Plane): { x: number; y: number } | null => {
      if (!raycaster.ray.intersectPlane(plane, hitPoint)) return null;
      return { x: hitPoint.x / MM_TO_M, y: hitPoint.z / MM_TO_M };
    };

    const handlePointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      setPointer(event);

      const openingHit = raycaster.intersectObjects(handle.openingPickable, false)[0];
      if (openingHit && typeof openingHit.object.userData.openingId === 'string') {
        const openingId = openingHit.object.userData.openingId as string;
        // The plane through the point actually grabbed, so the door does not
        // jump when the drag starts.
        draggingOpening = {
          openingId,
          plane: new THREE.Plane(new THREE.Vector3(0, 1, 0), -openingHit.point.y),
        };
        callbacksRef.current.onSelectOpening?.(openingId);
        controls.enabled = false;
        renderer.domElement.setPointerCapture(event.pointerId);
        return;
      }

      const hit = raycaster.intersectObjects(boxMeshes(), false)[0];
      const boxId = hit?.object.userData.boxId;
      if (typeof boxId !== 'string') return;
      if (!raycaster.ray.intersectPlane(floorPlane, hitPoint)) return;

      // Grab OFFSET, not centre: picking a product by its edge should not make
      // it jump so its middle is under the cursor.
      dragging = {
        boxId,
        grabDx: hit.object.position.x - hitPoint.x,
        grabDz: hit.object.position.z - hitPoint.z,
      };
      controls.enabled = false;
      renderer.domElement.setPointerCapture(event.pointerId);
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (draggingOpening) {
        setPointer(event);
        const opening = dataRef.current.openings.find(
          (candidate) => candidate.id === draggingOpening!.openingId,
        );
        if (!opening) return;
        const point = pointOn(draggingOpening.plane);
        if (!point) return;
        // Wall hopping, by the SAME rule the plan uses: the opening goes to
        // whichever wall the pointer is nearest. Dragging a door round a corner
        // is a thing people do, and the two views must land it in the same
        // place or the plan and the 3D view start disagreeing about the room.
        // A wall too short to hold it simply does not take it.
        const placed = placeOpeningOnNearestWall(opening, dataRef.current.outline, point);
        if (placed) {
          callbacksRef.current.onMoveOpening?.(placed.id, placed.offsetMm, placed.wallIndex);
        }
        return;
      }

      if (!dragging) return;
      setPointer(event);
      if (!raycaster.ray.intersectPlane(floorPlane, hitPoint)) return;
      const box = dataRef.current.boxes.find((candidate) => candidate.id === dragging!.boxId);
      if (!box) return;
      // Back to millimetres, and back to the box's near corner, which is the
      // co-ordinate the rest of the designer speaks.
      callbacksRef.current.onMoveBox?.(
        dragging.boxId,
        (hitPoint.x + dragging.grabDx) / MM_TO_M - box.width / 2,
        (hitPoint.z + dragging.grabDz) / MM_TO_M - box.depth / 2,
        box.rotation,
      );
    };

    const endPointer = (event: PointerEvent) => {
      if (!dragging && !draggingOpening) return;
      dragging = null;
      draggingOpening = null;
      controls.enabled = true;
      if (renderer.domElement.hasPointerCapture(event.pointerId)) {
        renderer.domElement.releasePointerCapture(event.pointerId);
      }
      callbacksRef.current.onCommit?.();
    };

    renderer.domElement.addEventListener('click', handleClick);
    renderer.domElement.addEventListener('pointerdown', handlePointerDown);
    renderer.domElement.addEventListener('pointermove', handlePointerMove);
    renderer.domElement.addEventListener('pointerup', endPointer);
    renderer.domElement.addEventListener('pointercancel', endPointer);

    let frame = 0;
    const toWall = new THREE.Vector3();
    const projected = new THREE.Vector3();
    let lastProjection = '';
    let lastOpenings = '';
    // Reused rather than allocated per pane per frame.
    const worldPoint = new THREE.Vector3();

    /** Screen position of a point in the scene, in canvas pixels. */
    const toScreen = (world: THREE.Vector3) => {
      projected.copy(world).project(camera);
      const rect = renderer.domElement.getBoundingClientRect();
      return {
        x: Math.round(((projected.x + 1) / 2) * rect.width),
        y: Math.round(((1 - projected.y) / 2) * rect.height),
      };
    };
    const animate = () => {
      frame = requestAnimationFrame(animate);
      controls.update();

      /**
       * Where the selected product currently is ON SCREEN.
       *
       * Published as an attribute because nothing else can answer it from
       * outside: the scene is a canvas, so a test (or anything else driving the
       * page) has no element to aim at. Written only when it changes.
       */
      const selected = dataRef.current.selectedBoxId;
      const selectedMesh = selected ? handle.boxRecords.get(selected)?.mesh : undefined;
      if (selectedMesh) {
        const at = toScreen(selectedMesh.position);
        const value = `${at.x},${at.y}`;
        if (value !== lastProjection) {
          lastProjection = value;
          mount.setAttribute('data-dk-selected-at', value);
          // The same number the toolbar is positioned by, so the buttons over
          // the object and the attribute anything else reads can never
          // disagree. Only on change - this runs every frame.
          selectionAtRef.current(at);
        }
      } else if (lastProjection) {
        lastProjection = '';
        mount.removeAttribute('data-dk-selected-at');
        selectionAtRef.current(null);
      }

      // And the same for the openings, which have it worse: a door is a HOLE,
      // so there is not even a shape on screen to aim at. The wall it is
      // currently in rides along, because that is the thing a drag across the
      // room changes and nothing on screen states it.
      const openingPoints = handle.openingPickable
        .map((pane) => {
          const at = toScreen(pane.getWorldPosition(worldPoint));
          return `${pane.userData.openingId}:${pane.userData.wallIndex}:${at.x},${at.y}`;
        })
        .join(';');
      if (openingPoints !== lastOpenings) {
        lastOpenings = openingPoints;
        if (openingPoints) mount.setAttribute('data-dk-openings-at', openingPoints);
        else mount.removeAttribute('data-dk-openings-at');
      }

      // A wall whose inside faces away from the camera is between you and the
      // room, so it comes down for this frame.
      for (const wall of handle.wallMeshes) {
        toWall.copy(wall.mesh.position).sub(camera.position).setY(0).normalize();
        // Inward normal pointing the same way as the view means the room is
        // BEHIND this wall: it is in the way, so it goes.
        wall.mesh.visible = wall.normal.dot(toWall) <= 0;
      }
      renderer.render(scene, camera);
    };
    animate();

    const observer = new ResizeObserver(() => {
      const nextWidth = mount.clientWidth || width;
      const nextHeight = mount.clientHeight || height;
      camera.aspect = nextWidth / nextHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(nextWidth, nextHeight);
    });
    observer.observe(mount);

    return () => {
      // WebGL contexts are a finite resource; leaking one per re-render kills
      // the tab after a dozen edits.
      cancelAnimationFrame(frame);
      observer.disconnect();
      renderer.domElement.removeEventListener('click', handleClick);
      renderer.domElement.removeEventListener('pointerdown', handlePointerDown);
      renderer.domElement.removeEventListener('pointermove', handlePointerMove);
      renderer.domElement.removeEventListener('pointerup', endPointer);
      renderer.domElement.removeEventListener('pointercancel', endPointer);
      controls.dispose();
      for (const record of handle.boxRecords.values()) releaseBoxRecord(handle, record);
      handle.boxRecords.clear();
      for (const item of handle.roomDisposables) item.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
      handleRef.current = null;
    };
  }, []);

  /** The room itself: floor, walls, and the panes that make openings grabbable. */
  useEffect(() => {
    const handle = handleRef.current;
    if (!handle) return;

    handle.roomGroup.clear();
    for (const item of handle.roomDisposables) item.dispose();
    handle.roomDisposables = [];
    handle.wallMeshes = [];
    handle.openingPickable = [];

    const bounds = roomBounds(outline);
    const centre = new THREE.Vector3(
      ((bounds.minX + bounds.maxX) / 2) * MM_TO_M,
      0,
      ((bounds.minY + bounds.maxY) / 2) * MM_TO_M,
    );

    // Floor from the room polygon. A Shape is drawn in XY, so it is laid flat.
    if (outline.length >= 3) {
      const shape = new THREE.Shape();
      shape.moveTo(outline[0].x * MM_TO_M, outline[0].y * MM_TO_M);
      for (const point of outline.slice(1)) {
        shape.lineTo(point.x * MM_TO_M, point.y * MM_TO_M);
      }
      shape.closePath();

      const floorGeometry = new THREE.ShapeGeometry(shape);
      const floorMaterial = new THREE.MeshStandardMaterial({
        color: floorColor(finishes),
        side: THREE.DoubleSide,
      });
      const floor = new THREE.Mesh(floorGeometry, floorMaterial);
      floor.rotation.x = Math.PI / 2;
      handle.roomGroup.add(floor);
      handle.roomDisposables.push(floorGeometry, floorMaterial);
    }

    /**
     * Walls, and the trick that makes them usable.
     *
     * A room with four solid walls seen from outside is a box you cannot look
     * into, so every wall facing roughly toward the camera is hidden each
     * frame. That is what the planner we studied does, and it is why its 3D
     * view reads as a room rather than a crate. One plane per wall, no
     * thickness: thickness is a number nobody would type and would only show up
     * as a shadow line.
     */
    for (let index = 0; index < outline.length; index += 1) {
      const start = outline[index];
      const end = outline[(index + 1) % outline.length];
      const runX = (end.x - start.x) * MM_TO_M;
      const runZ = (end.y - start.y) * MM_TO_M;
      const length = Math.hypot(runX, runZ);
      if (length < 0.01) continue;

      /**
       * The wall as PIECES, not one plane.
       *
       * A door is a hole, and cutting a hole in a plane properly means boolean
       * geometry - slow, fiddly, and rebuilt on every drag. Building the wall
       * out of the stretches that are still solid, plus the lintel and sill
       * panels above and below each opening, gives the same picture for the
       * cost of a few extra planes.
       */
      const wallOpenings = openings.filter((opening) => opening.wallIndex === index);
      const lengthMm = length / MM_TO_M;
      const pieces: { fromMm: number; toMm: number; bottomMm: number; topMm: number }[] = [];

      for (const span of openingSpans(lengthMm, wallOpenings)) {
        pieces.push({ fromMm: span.start, toMm: span.end, bottomMm: 0, topMm: ceilingHeightMm });
      }
      for (const opening of wallOpenings) {
        for (const panel of wallPanels(opening, ceilingHeightMm)) {
          pieces.push({
            fromMm: opening.offsetMm - opening.widthMm / 2,
            toMm: opening.offsetMm + opening.widthMm / 2,
            bottomMm: panel.bottom,
            topMm: panel.top,
          });
        }
      }

      const wallGroup = new THREE.Group();
      for (const piece of pieces) {
        const pieceWidth = (piece.toMm - piece.fromMm) * MM_TO_M;
        const pieceHeight = (piece.topMm - piece.bottomMm) * MM_TO_M;
        if (pieceWidth <= 0 || pieceHeight <= 0) continue;

        const pieceGeometry = new THREE.PlaneGeometry(pieceWidth, pieceHeight);
        const pieceMaterial = new THREE.MeshStandardMaterial({
          color: wallColor(finishes, index),
          side: THREE.DoubleSide,
          roughness: 0.9,
        });
        const pieceMesh = new THREE.Mesh(pieceGeometry, pieceMaterial);
        // Positioned relative to the wall's own centre, then the whole group is
        // placed and turned once.
        pieceMesh.position.set(
          ((piece.fromMm + piece.toMm) / 2 - lengthMm / 2) * MM_TO_M,
          ((piece.bottomMm + piece.topMm) / 2) * MM_TO_M,
          0,
        );
        wallGroup.add(pieceMesh);
        handle.roomDisposables.push(pieceGeometry, pieceMaterial);
      }

      /**
       * An invisible pane filling each hole, so a door can be grabbed in 3D.
       *
       * The opening itself is an absence - there is no geometry to click - and
       * being told to switch to the plan to move a door you are looking at is
       * exactly the kind of thing that makes a tool feel like a form.
       */
      for (const opening of wallOpenings) {
        const sill = Math.max(0, Math.min(opening.sillMm, ceilingHeightMm));
        const head = Math.min(sill + opening.heightMm, ceilingHeightMm);
        const paneGeometry = new THREE.PlaneGeometry(
          opening.widthMm * MM_TO_M,
          Math.max(1, head - sill) * MM_TO_M,
        );
        const paneMaterial = new THREE.MeshBasicMaterial({
          transparent: true,
          opacity: 0,
          depthWrite: false,
          side: THREE.DoubleSide,
        });
        const pane = new THREE.Mesh(paneGeometry, paneMaterial);
        pane.position.set(
          (opening.offsetMm - lengthMm / 2) * MM_TO_M,
          ((sill + head) / 2) * MM_TO_M,
          0,
        );
        pane.userData.openingId = opening.id;
        pane.userData.wallIndex = index;
        wallGroup.add(pane);
        handle.openingPickable.push(pane);
        handle.roomDisposables.push(paneGeometry, paneMaterial);
      }

      wallGroup.position.set(
        ((start.x + end.x) / 2) * MM_TO_M,
        0,
        ((start.y + end.y) / 2) * MM_TO_M,
      );
      wallGroup.rotation.y = -Math.atan2(runZ, runX);
      // The inward normal, decided by pointing it at the room's middle rather
      // than by assuming a winding direction. A user who drags their corners
      // anticlockwise has still drawn a room, and getting this backwards hides
      // exactly the wrong walls - which looks like a broken renderer.
      const normal = new THREE.Vector3(runZ / length, 0, -runX / length);
      const toCentre = new THREE.Vector3(centre.x, 0, centre.z).sub(
        new THREE.Vector3(wallGroup.position.x, 0, wallGroup.position.z),
      );
      if (normal.dot(toCentre) < 0) normal.negate();
      handle.roomGroup.add(wallGroup);
      handle.wallMeshes.push({ mesh: wallGroup, normal });
    }
  }, [outline, openings, ceilingHeightMm, finishes]);

  /**
   * The products, kept in step rather than rebuilt.
   *
   * A drag fires this effect on every pointermove, so it MUST be cheap and it
   * must not disturb the camera or the in-flight gesture: a box whose size and
   * label are unchanged just gets moved.
   */
  useEffect(() => {
    const handle = handleRef.current;
    if (!handle) return;

    const present = new Set<string>();
    for (const box of boxes) {
      present.add(box.id);
      const signature = boxSignature(box);
      let record = handle.boxRecords.get(box.id);
      if (record && record.signature !== signature) {
        releaseBoxRecord(handle, record);
        handle.boxRecords.delete(box.id);
        record = undefined;
      }
      if (!record) {
        record = createBoxRecord(box);
        handle.boxGroup.add(record.mesh, record.edges);
        handle.boxRecords.set(box.id, record);
      }

      record.mesh.position.set(
        (box.x + box.width / 2) * MM_TO_M,
        (box.heightMm * MM_TO_M) / 2,
        (box.y + box.depth / 2) * MM_TO_M,
      );
      record.mesh.rotation.y = (-box.rotation * Math.PI) / 180;
      record.edges.position.copy(record.mesh.position);
      record.edges.rotation.copy(record.mesh.rotation);

      const isSelected = box.id === selectedBoxId;
      // Every plain face shares one material instance, so one set does all five.
      const materials = record.mesh.material as THREE.MeshStandardMaterial[];
      materials[0].color.set(box.isEstimated ? '#f59e0b' : isSelected ? '#2563eb' : '#94a3b8');
      (record.edges.material as THREE.LineBasicMaterial).color.set(
        isSelected ? 0x1d4ed8 : 0x475569,
      );
    }

    for (const [id, record] of Array.from(handle.boxRecords.entries())) {
      if (present.has(id)) continue;
      releaseBoxRecord(handle, record);
      handle.boxRecords.delete(id);
    }
  }, [boxes, selectedBoxId]);

  return (
    <div className="relative">
      <div
        ref={mountRef}
        className="h-[420px] w-full overflow-hidden rounded-lg border border-border bg-muted/20"
        data-dk-room-scene
      />
      {selectionToolbar && selectionAt && (
        <div
          className="pointer-events-none absolute z-10"
          // Above the object and centred on it, matching the plan's toolbar.
          // `pointer-events-none` on the wrapper so the space around the
          // buttons still rotates the camera; the buttons re-enable it.
          style={{
            left: selectionAt.x,
            top: Math.max(4, selectionAt.y - 56),
            transform: 'translateX(-50%)',
          }}
          data-dk-scene-actions
        >
          <div className="pointer-events-auto flex items-center gap-0.5 rounded-md border border-border bg-background/95 p-0.5 shadow-sm backdrop-blur">
            {selectionToolbar}
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={() => refocusRef.current()}
        className="absolute bottom-2 start-2 rounded border border-border bg-background/90 px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
        data-dk-scene-refocus
      >
        Refocus
      </button>
    </div>
  );
}
