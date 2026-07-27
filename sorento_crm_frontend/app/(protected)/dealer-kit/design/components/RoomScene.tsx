'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import { roomBounds, type Box, type Point } from '@/lib/dealer-kit/roomGeometry';
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

export function RoomScene({
  outline,
  boxes,
  selectedBoxId,
  onSelectBox,
}: {
  outline: Point[];
  boxes: SceneBox[];
  selectedBoxId?: string | null;
  onSelectBox?: (boxId: string) => void;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const pickRef = useRef<(boxId: string) => void>(() => {});
  pickRef.current = (boxId: string) => onSelectBox?.(boxId);

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
    controls.update();

    scene.add(new THREE.AmbientLight(0xffffff, 1.4));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(5, 10, 5);
    scene.add(sun);

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
        new THREE.MeshStandardMaterial({ color: '#e2e8f0', side: THREE.DoubleSide }),
      );
      floor.rotation.x = Math.PI / 2;
      scene.add(floor);
    }

    const pickable: THREE.Object3D[] = [];
    const disposables: (THREE.BufferGeometry | THREE.Material | THREE.Texture)[] = [];

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

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const handleClick = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(pickable, false)[0];
      const boxId = hit?.object.userData.boxId;
      if (typeof boxId === 'string') pickRef.current(boxId);
    };
    renderer.domElement.addEventListener('click', handleClick);

    let frame = 0;
    const animate = () => {
      frame = requestAnimationFrame(animate);
      controls.update();
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
      controls.dispose();
      for (const item of disposables) item.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
  }, [outline, boxes, selectedBoxId]);

  return (
    <div
      ref={mountRef}
      className="h-[420px] w-full overflow-hidden rounded-lg border border-border bg-muted/20"
      data-dk-room-scene
    />
  );
}
