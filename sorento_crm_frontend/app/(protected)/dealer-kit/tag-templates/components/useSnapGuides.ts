'use client';

/**
 * Snap and alignment guides for the canvas editor.
 *
 * While a layer is being dragged, computes snap targets from:
 *   - Canvas edges (0, width_mm, 0, height_mm)
 *   - Canvas center (width_mm/2, height_mm/2)
 *   - Other layers' edges and centers
 *
 * Returns active guide lines (horizontal / vertical) as mm positions, plus
 * the snapped position for the dragged layer. Guide lines disappear when
 * dragging stops.
 */

import { useCallback, useState } from 'react';
import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';

/** Snap threshold in mm. */
const SNAP_THRESHOLD_MM = 2;

export interface GuideLine {
  orientation: 'horizontal' | 'vertical';
  position_mm: number;
}

export interface SnapResult {
  x_mm: number;
  y_mm: number;
  guides: GuideLine[];
}

/** Ruler guide positions to also snap against, split by axis (S6, D9). */
export interface GuideSnapTargets {
  vertical: number[];
  horizontal: number[];
}

export interface SnapGuides {
  /** Compute snap for a layer being dragged to (x_mm, y_mm). */
  computeSnap: (
    layerId: string,
    x_mm: number,
    y_mm: number,
    width_mm: number,
    height_mm: number,
    allLayers: TagLayer[],
    canvasWidth: number,
    canvasHeight: number,
    guideTargets?: GuideSnapTargets,
  ) => SnapResult;
  /** Active guide lines (render these on the canvas). */
  guides: GuideLine[];
  /** Clear all guides (call on drag end). */
  clearGuides: () => void;
}

export function useSnapGuides(): SnapGuides {
  const [guides, setGuides] = useState<GuideLine[]>([]);

  const computeSnap = useCallback(
    (
      layerId: string,
      x_mm: number,
      y_mm: number,
      width_mm: number,
      height_mm: number,
      allLayers: TagLayer[],
      canvasWidth: number,
      canvasHeight: number,
      guideTargets?: GuideSnapTargets,
    ): SnapResult => {
      // Collect snap targets (horizontal = y positions, vertical = x positions).
      // Ruler guides join in cheaply (D9): they are just more numbers in the
      // same two lists, no different from the canvas edges already there.
      const hTargets: number[] = [
        0,
        canvasHeight / 2,
        canvasHeight,
        ...(guideTargets?.horizontal ?? []),
      ];
      const vTargets: number[] = [
        0,
        canvasWidth / 2,
        canvasWidth,
        ...(guideTargets?.vertical ?? []),
      ];

      for (const layer of allLayers) {
        if (layer.id === layerId || !layer.visible) continue;
        // Other layers' edges and centers.
        vTargets.push(layer.x_mm, layer.x_mm + layer.width_mm / 2, layer.x_mm + layer.width_mm);
        hTargets.push(layer.y_mm, layer.y_mm + layer.height_mm / 2, layer.y_mm + layer.height_mm);
      }

      // Dragged layer edges and center.
      const dragEdges = {
        left: x_mm,
        centerX: x_mm + width_mm / 2,
        right: x_mm + width_mm,
        top: y_mm,
        centerY: y_mm + height_mm / 2,
        bottom: y_mm + height_mm,
      };

      let snappedX = x_mm;
      let snappedY = y_mm;
      const activeGuides: GuideLine[] = [];

      // Snap X (vertical guides).
      let bestDx = SNAP_THRESHOLD_MM + 1;
      for (const target of vTargets) {
        for (const edge of [dragEdges.left, dragEdges.centerX, dragEdges.right]) {
          const dx = Math.abs(edge - target);
          if (dx < bestDx) {
            bestDx = dx;
            snappedX = x_mm + (target - edge);
          }
        }
      }
      if (bestDx <= SNAP_THRESHOLD_MM) {
        // Find which target we snapped to.
        const snappedEdges = {
          left: snappedX,
          centerX: snappedX + width_mm / 2,
          right: snappedX + width_mm,
        };
        for (const target of vTargets) {
          for (const edge of [snappedEdges.left, snappedEdges.centerX, snappedEdges.right]) {
            if (Math.abs(edge - target) < 0.01) {
              activeGuides.push({ orientation: 'vertical', position_mm: target });
            }
          }
        }
      }

      // Snap Y (horizontal guides).
      let bestDy = SNAP_THRESHOLD_MM + 1;
      for (const target of hTargets) {
        for (const edge of [dragEdges.top, dragEdges.centerY, dragEdges.bottom]) {
          const dy = Math.abs(edge - target);
          if (dy < bestDy) {
            bestDy = dy;
            snappedY = y_mm + (target - edge);
          }
        }
      }
      if (bestDy <= SNAP_THRESHOLD_MM) {
        const snappedEdges = {
          top: snappedY,
          centerY: snappedY + height_mm / 2,
          bottom: snappedY + height_mm,
        };
        for (const target of hTargets) {
          for (const edge of [snappedEdges.top, snappedEdges.centerY, snappedEdges.bottom]) {
            if (Math.abs(edge - target) < 0.01) {
              activeGuides.push({ orientation: 'horizontal', position_mm: target });
            }
          }
        }
      }

      // Deduplicate guides.
      const unique = activeGuides.filter(
        (g, i, arr) =>
          arr.findIndex(
            (other) => other.orientation === g.orientation && other.position_mm === g.position_mm,
          ) === i,
      );

      setGuides(unique);
      return { x_mm: snappedX, y_mm: snappedY, guides: unique };
    },
    [],
  );

  const clearGuides = useCallback(() => setGuides([]), []);

  return { computeSnap, guides, clearGuides };
}
