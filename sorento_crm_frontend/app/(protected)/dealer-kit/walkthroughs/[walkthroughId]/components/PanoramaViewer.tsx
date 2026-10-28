'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';

import {
  MIN_CAMERA_FOV_DEG,
  clampLook,
  lookVector,
  maxCameraFov,
  sphereSegment,
} from '@/lib/dealer-kit/panoramaGeometry';

/**
 * One stop's panorama, wrapped around the camera: drag or arrow keys to look
 * round, wheel or +/- to zoom.
 *
 * Plain three.js, for the reason `design/components/RoomScene.tsx` gives:
 * react-three-fiber's JSX typings break polymorphic components app-wide.
 * The renderer lives for the life of the component; a new panorama only swaps
 * the mesh.
 */
export function PanoramaViewer({
  image,
  hFovDeg,
  vFovDeg,
  label,
}: {
  image: Blob;
  hFovDeg: number;
  vFovDeg: number;
  label: string;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);
    renderer.domElement.style.touchAction = 'none';

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1100);

    const segment = sphereSegment(hFovDeg, vFovDeg);
    const geometry = new THREE.SphereGeometry(
      500,
      64,
      32,
      segment.phiStart,
      segment.phiLength,
      segment.thetaStart,
      segment.thetaLength,
    );
    // Seen from inside: flip so the picture is not mirrored.
    geometry.scale(-1, 1, 1);

    const url = URL.createObjectURL(image);
    const texture = new THREE.TextureLoader().load(url, () => render());
    texture.colorSpace = THREE.SRGBColorSpace;
    const material = new THREE.MeshBasicMaterial({ map: texture });
    scene.add(new THREE.Mesh(geometry, material));

    const view = { lon: 0, lat: 0 };

    function render() {
      const aspect = camera.aspect || 1;
      camera.fov = Math.min(camera.fov, maxCameraFov(hFovDeg, vFovDeg, aspect));
      camera.updateProjectionMatrix();
      Object.assign(view, clampLook(view.lon, view.lat, hFovDeg, vFovDeg, camera.fov, aspect));
      const [x, y, z] = lookVector(view.lon, view.lat);
      camera.lookAt(x, y, z);
      renderer.render(scene, camera);
    }

    const resize = () => {
      const width = host.clientWidth || 1;
      const height = host.clientHeight || 1;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    let drag: { x: number; y: number; lon: number; lat: number } | null = null;
    const onDown = (event: PointerEvent) => {
      drag = { x: event.clientX, y: event.clientY, lon: view.lon, lat: view.lat };
      renderer.domElement.setPointerCapture(event.pointerId);
    };
    const onMove = (event: PointerEvent) => {
      if (!drag) return;
      // Degrees per pixel follow the zoom, so a drag tracks the picture.
      const perPixel = camera.fov / (host.clientHeight || 1);
      view.lon = drag.lon + (drag.x - event.clientX) * perPixel;
      view.lat = drag.lat + (event.clientY - drag.y) * perPixel;
      render();
    };
    const onUp = () => {
      drag = null;
    };
    const zoom = (delta: number) => {
      camera.fov = Math.max(
        MIN_CAMERA_FOV_DEG,
        Math.min(maxCameraFov(hFovDeg, vFovDeg, camera.aspect || 1), camera.fov + delta),
      );
      render();
    };
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      zoom(event.deltaY * 0.05);
    };
    const onKey = (event: KeyboardEvent) => {
      const step = { ArrowLeft: [-5, 0], ArrowRight: [5, 0], ArrowUp: [0, 5], ArrowDown: [0, -5] }[
        event.key
      ];
      if (step) {
        event.preventDefault();
        view.lon += step[0];
        view.lat += step[1];
        render();
      } else if (event.key === '+' || event.key === '=') {
        zoom(-5);
      } else if (event.key === '-') {
        zoom(5);
      }
    };

    const canvas = renderer.domElement;
    canvas.addEventListener('pointerdown', onDown);
    canvas.addEventListener('pointermove', onMove);
    canvas.addEventListener('pointerup', onUp);
    canvas.addEventListener('pointercancel', onUp);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    host.addEventListener('keydown', onKey);

    return () => {
      observer.disconnect();
      canvas.removeEventListener('pointerdown', onDown);
      canvas.removeEventListener('pointermove', onMove);
      canvas.removeEventListener('pointerup', onUp);
      canvas.removeEventListener('pointercancel', onUp);
      canvas.removeEventListener('wheel', onWheel);
      host.removeEventListener('keydown', onKey);
      geometry.dispose();
      material.dispose();
      texture.dispose();
      renderer.dispose();
      URL.revokeObjectURL(url);
      host.removeChild(canvas);
    };
  }, [image, hFovDeg, vFovDeg]);

  return (
    <div
      ref={hostRef}
      tabIndex={0}
      role="img"
      aria-label={`${label}. Drag or use the arrow keys to look around, plus and minus to zoom.`}
      className="relative h-[60vh] min-h-72 w-full cursor-grab overflow-hidden rounded-lg bg-black outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
      data-testid="dk-wt-viewer"
    />
  );
}
