'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import { roomBounds, type Box, type Point } from '@/lib/dealer-kit/roomGeometry';
import { openingSpans, wallPanels, type Opening } from '@/lib/dealer-kit/roomOpenings';
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

/** A ceiling nobody typed. Standard Malaysian residential floor-to-ceiling. */
export const DEFAULT_CEILING_MM = 2700;

export function RoomScene({
  outline,
  boxes,
  selectedBoxId,
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
  const refocusRef = useRef<() => void>(() => {});
  const moveRef = useRef<(boxId: string, x: number, y: number, rotation: number) => void>(
    () => {},
  );
  const commitRef = useRef<() => void>(() => {});
  const moveOpeningRef = useRef<
    (openingId: string, offsetMm: number, wallIndex: number) => void
  >(() => {});
  const selectOpeningRef = useRef<(openingId: string) => void>(() => {});
  const pickRef = useRef<(boxId: string) => void>(() => {});
  pickRef.current = (boxId: string) => onSelectBox?.(boxId);
  // Refs, not deps: the scene is built once per data change, and putting these
  // callbacks in the effect's dependency list would tear the whole scene down
  // on every render of the parent.
  moveRef.current = (boxId, x, y, rotation) => onMoveBox?.(boxId, x, y, rotation);
  commitRef.current = () => onCommit?.();
  moveOpeningRef.current = (openingId, offsetMm, wallIndex) =>
    onMoveOpening?.(openingId, offsetMm, wallIndex);
  selectOpeningRef.current = (openingId) => onSelectOpening?.(openingId);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const width = mount.clientWidth || 640;
    const height = mount.clientHeight || 420;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#f1f5f9');

    const bounds = roomBounds(outline);
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

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.set(centre.x + span, span * 0.9, centre.z + span);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(centre);
    // Zoom toward the cursor, not the orbit target: zooming to centre means
    // every zoom is followed by an orbit to get back to the corner you were
    // looking at.
    controls.zoomToCursor = true;
    controls.update();

    // Refocus: put the camera back where it started. An orbit that has ended up
    // inside a wall is otherwise unrecoverable without a reload.
    const refocus = () => {
      camera.position.set(centre.x + span, span * 0.9, centre.z + span);
      controls.target.copy(centre);
      controls.update();
    };
    refocusRef.current = refocus;

    scene.add(new THREE.AmbientLight(0xffffff, 1.4));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(5, 10, 5);
    scene.add(sun);

    const pickable: THREE.Object3D[] = [];
    const disposables: (THREE.BufferGeometry | THREE.Material | THREE.Texture)[] = [];

    // Floor from the room polygon. A Shape is drawn in XY, so it is laid flat.
    if (outline.length >= 3) {
      const shape = new THREE.Shape();
      shape.moveTo(outline[0].x * MM_TO_M, outline[0].y * MM_TO_M);
      for (const point of outline.slice(1)) {
        shape.lineTo(point.x * MM_TO_M, point.y * MM_TO_M);
      }
      shape.closePath();

      const floor = new THREE.Mesh(
        new THREE.ShapeGeometry(shape),
        new THREE.MeshStandardMaterial({ color: floorColor(finishes), side: THREE.DoubleSide }),
      );
      floor.rotation.x = Math.PI / 2;
      scene.add(floor);
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
    const wallMeshes: { mesh: THREE.Mesh; normal: THREE.Vector3 }[] = [];
    const openingPickable: THREE.Object3D[] = [];
    const wallHeight = Math.max(1, ceilingHeightMm) * MM_TO_M;
    if (outline.length >= 3) {
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
         * A door is a hole, and cutting a hole in a plane properly means
         * boolean geometry - slow, fiddly, and rebuilt on every drag. Building
         * the wall out of the stretches that are still solid, plus the lintel
         * and sill panels above and below each opening, gives the same picture
         * for the cost of a few extra planes.
         */
        const wallOpenings = openings.filter((opening) => opening.wallIndex === index);
        const lengthMm = length / MM_TO_M;
        const pieces: { fromMm: number; toMm: number; bottomMm: number; topMm: number }[] = [];

        for (const span of openingSpans(lengthMm, wallOpenings)) {
          pieces.push({
            fromMm: span.start,
            toMm: span.end,
            bottomMm: 0,
            topMm: ceilingHeightMm,
          });
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
          // Positioned relative to the wall's own centre, then the whole group
          // is placed and turned once.
          pieceMesh.position.set(
            ((piece.fromMm + piece.toMm) / 2 - lengthMm / 2) * MM_TO_M,
            ((piece.bottomMm + piece.topMm) / 2) * MM_TO_M,
            0,
          );
          wallGroup.add(pieceMesh);
          disposables.push(pieceGeometry, pieceMaterial);
        }

        /**
         * An invisible pane filling each hole, so a door can be grabbed in 3D.
         *
         * The opening itself is an absence - there is no geometry to click -
         * and being told to switch to the plan to move a door you are looking
         * at is exactly the kind of thing that makes a tool feel like a form.
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
          openingPickable.push(pane);
          disposables.push(paneGeometry, paneMaterial);
        }

        const mesh = wallGroup as unknown as THREE.Mesh;
        mesh.position.set(
          ((start.x + end.x) / 2) * MM_TO_M,
          0,
          ((start.y + end.y) / 2) * MM_TO_M,
        );
        mesh.rotation.y = -Math.atan2(runZ, runX);
        // The inward normal, decided by pointing it at the room's middle rather
        // than by assuming a winding direction. A user who drags their corners
        // anticlockwise has still drawn a room, and getting this backwards hides
        // exactly the wrong walls - which looks like a broken renderer.
        const normal = new THREE.Vector3(runZ / length, 0, -runX / length);
        const toCentre = new THREE.Vector3(centre.x, 0, centre.z).sub(
          new THREE.Vector3(mesh.position.x, 0, mesh.position.z),
        );
        if (normal.dot(toCentre) < 0) normal.negate();
        scene.add(mesh);
        wallMeshes.push({ mesh, normal });
      }
    }


    for (const box of boxes) {
      const boxWidth = box.width * MM_TO_M;
      const boxDepth = box.depth * MM_TO_M;
      const boxHeight = box.heightMm * MM_TO_M;

      const geometry = new THREE.BoxGeometry(boxWidth, boxHeight, boxDepth);
      const texture = labelTexture(box.label);
      const plain = new THREE.MeshStandardMaterial({
        color: box.isEstimated ? '#f59e0b' : box.id === selectedBoxId ? '#2563eb' : '#94a3b8',
        roughness: 0.75,
      });
      const faced = new THREE.MeshStandardMaterial({ map: texture, roughness: 0.75 });
      // The name goes on the front face so the scene reads without clicking
      // anything (AC-V3). Face order is +x, -x, +y, -y, +z, -z.
      const materials = [plain, plain, plain, plain, faced, plain];

      const mesh = new THREE.Mesh(geometry, materials);
      mesh.position.set(
        (box.x + box.width / 2) * MM_TO_M,
        boxHeight / 2,
        (box.y + box.depth / 2) * MM_TO_M,
      );
      mesh.rotation.y = (-box.rotation * Math.PI) / 180;
      mesh.userData.boxId = box.id;
      scene.add(mesh);
      pickable.push(mesh);

      const outlineMesh = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry),
        new THREE.LineBasicMaterial({
          color: box.id === selectedBoxId ? 0x1d4ed8 : 0x475569,
        }),
      );
      outlineMesh.position.copy(mesh.position);
      outlineMesh.rotation.copy(mesh.rotation);
      scene.add(outlineMesh);

      disposables.push(geometry, plain, faced, texture, outlineMesh.geometry, outlineMesh.material as THREE.Material);
    }

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
    let draggingOpening: { openingId: string } | null = null;

    const setPointer = (event: PointerEvent | MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
    };

    const handleClick = (event: MouseEvent) => {
      setPointer(event);
      const hit = raycaster.intersectObjects(pickable, false)[0];
      const boxId = hit?.object.userData.boxId;
      if (typeof boxId === 'string') pickRef.current(boxId);
    };

    /** Where a pointer lands along a wall, in millimetres from its start. */
    const alongWall = (wallIndex: number): number | null => {
      const start = outline[wallIndex];
      const end = outline[(wallIndex + 1) % outline.length];
      if (!start || !end) return null;
      if (!raycaster.ray.intersectPlane(floorPlane, hitPoint)) return null;
      const runX = end.x - start.x;
      const runY = end.y - start.y;
      const length = Math.hypot(runX, runY);
      if (length < 1e-6) return null;
      const pointX = hitPoint.x / MM_TO_M;
      const pointY = hitPoint.z / MM_TO_M;
      return ((pointX - start.x) * runX + (pointY - start.y) * runY) / length;
    };

    const handlePointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      setPointer(event);

      const openingHit = raycaster.intersectObjects(openingPickable, false)[0];
      if (openingHit && typeof openingHit.object.userData.openingId === 'string') {
        draggingOpening = { openingId: openingHit.object.userData.openingId };
        selectOpeningRef.current(draggingOpening.openingId);
        controls.enabled = false;
        renderer.domElement.setPointerCapture(event.pointerId);
        return;
      }

      const hit = raycaster.intersectObjects(pickable, false)[0];
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
        const opening = openings.find(
          (candidate) => candidate.id === draggingOpening!.openingId,
        );
        if (!opening) return;
        const along = alongWall(opening.wallIndex);
        // Along its own wall only. Hopping walls belongs to the plan, where
        // "nearest wall to the pointer" is a question with an obvious answer.
        if (along !== null) {
          moveOpeningRef.current(opening.id, Math.round(along), opening.wallIndex);
        }
        return;
      }

      if (!dragging) return;
      setPointer(event);
      if (!raycaster.ray.intersectPlane(floorPlane, hitPoint)) return;
      const box = boxes.find((candidate) => candidate.id === dragging!.boxId);
      if (!box) return;
      // Back to millimetres, and back to the box's near corner, which is the
      // co-ordinate the rest of the designer speaks.
      moveRef.current(
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
      commitRef.current();
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
      const selectedMesh = pickable.find((node) => node.userData.boxId === selectedBoxId);
      if (selectedMesh) {
        projected.copy(selectedMesh.position).project(camera);
        const rect = renderer.domElement.getBoundingClientRect();
        const value = `${Math.round(((projected.x + 1) / 2) * rect.width)},${Math.round(
          ((1 - projected.y) / 2) * rect.height,
        )}`;
        if (value !== lastProjection) {
          lastProjection = value;
          mount.setAttribute('data-dk-selected-at', value);
        }
      } else if (lastProjection) {
        lastProjection = '';
        mount.removeAttribute('data-dk-selected-at');
      }

      // A wall whose inside faces away from the camera is between you and the
      // room, so it comes down for this frame.
      for (const wall of wallMeshes) {
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
      for (const item of disposables) item.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
  }, [outline, boxes, selectedBoxId, ceilingHeightMm, openings, finishes]);

  return (
    <div className="relative">
      <div
        ref={mountRef}
        className="h-[420px] w-full overflow-hidden rounded-lg border border-border bg-muted/20"
        data-dk-room-scene
      />
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
