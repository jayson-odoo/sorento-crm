/**
 * Turning a Selection into the boxes standing in a room, and back again.
 *
 * The server stores WHAT was chosen - a product and a quantity. The room stores
 * WHERE each copy stands. Neither knows about the other, so this is where the
 * two are reconciled, and it is the only place that mapping exists.
 *
 * The subtle part is identity. A quantity of three is three boxes, and they are
 * distinguished only by their position in the sequence (`{lineId}-0`, `-1`,
 * `-2`). That is fine until somebody deletes the middle one: decrementing the
 * quantity to two leaves ids `-0` and `-1`, so the box that visually disappears
 * is the LAST one, not the one they clicked. Extracted here so that behaviour
 * is pinned by tests rather than discovered in a showroom.
 */

import type { Selection, SelectionLine } from '@/app/(protected)/dealer-kit/services/selectionService';

/** Fallback for a product the catalogue has no dimensions for. */
export const UNKNOWN_SIZE_MM = { width: 600, depth: 600, height: 900 };

export interface PlacedBox {
  id: string;
  lineId: string;
  productId: string;
  code: string;
  label: string;
  x: number;
  y: number;
  width: number;
  depth: number;
  heightMm: number;
  rotation: number;
  isEstimated?: boolean;
}

function copyId(line: SelectionLine, copy: number): string {
  return `${line.lineId}-${copy}`;
}

/**
 * Rebuild the boxes from a Selection, keeping positions already chosen.
 *
 * Precedence is deliberate: a position the user is dragging RIGHT NOW beats the
 * one last saved, which beats a first guess. Anything else and a drag snaps
 * back the moment a refetch lands.
 */
export function boxesForSelection(selection: Selection, previous: PlacedBox[]): PlacedBox[] {
  const savedByCopy = new Map(
    (selection.room?.placements ?? []).map((placement) => [placement.lineId, placement]),
  );
  const currentByCopy = new Map(previous.map((box) => [box.id, box]));

  const boxes: PlacedBox[] = [];
  selection.lines.forEach((line, index) => {
    const count = Math.max(1, Math.round(line.quantity));
    for (let copy = 0; copy < count; copy += 1) {
      const id = copyId(line, copy);
      const existing = currentByCopy.get(id);
      const saved = savedByCopy.get(id);
      const size = line.dimensionsMm;

      boxes.push({
        id,
        lineId: id,
        productId: line.productId,
        code: line.productCode ?? line.productName,
        label: line.productCode ?? line.productName,
        x: existing?.x ?? saved?.x ?? 200 + ((index + copy) % 4) * 800,
        y: existing?.y ?? saved?.y ?? 200 + Math.floor((index + copy) / 4) * 800,
        width: size?.length ?? UNKNOWN_SIZE_MM.width,
        depth: size?.width ?? UNKNOWN_SIZE_MM.depth,
        heightMm: size?.height ?? UNKNOWN_SIZE_MM.height,
        rotation: existing?.rotation ?? saved?.rotation ?? 0,
        isEstimated: size == null,
      });
    }
  });
  return boxes;
}

/**
 * Remove ONE box and renumber the copies that remain.
 *
 * Deleting a box is expressed to the server as "that product's quantity is now
 * one lower", which says nothing about WHICH copy went. Renumbering here is
 * what makes the right one disappear: the survivors keep their positions and
 * take the ids the next rebuild will look for. Without it the user clicks the
 * left-hand basin and the right-hand one vanishes.
 */
export function removeBox(boxes: PlacedBox[], boxId: string): PlacedBox[] {
  const target = boxes.find((box) => box.id === boxId);
  if (!target) return boxes;

  const survivors = boxes.filter((box) => box.id !== boxId);
  let copy = 0;
  return survivors.map((box) => {
    if (box.productId !== target.productId) return box;
    const lineId = box.id.slice(0, box.id.lastIndexOf('-'));
    const renumbered = { ...box, id: `${lineId}-${copy}`, lineId: `${lineId}-${copy}` };
    copy += 1;
    return renumbered;
  });
}

/** How many boxes of a product are standing in the room. */
export function quantityOf(boxes: PlacedBox[], productId: string): number {
  return boxes.filter((box) => box.productId === productId).length;
}

/** The placements to persist, one per box. */
export function placementsOf(boxes: PlacedBox[]) {
  return boxes.map((box) => ({
    lineId: box.lineId,
    productId: box.productId,
    x: box.x,
    y: box.y,
    rotation: box.rotation,
  }));
}
