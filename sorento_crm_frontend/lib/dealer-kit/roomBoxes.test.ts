import { describe, expect, it } from 'vitest';

import { boxesForSelection, placementsOf, quantityOf, removeBox, type PlacedBox } from './roomBoxes';
import type { Selection, SelectionLine } from '@/app/(protected)/dealer-kit/services/selectionService';

/**
 * The Selection-to-room mapping.
 *
 * The case that matters is deleting the middle copy of a product somebody
 * ordered three of. The server is told only "the quantity is now two", so
 * unless the survivors are renumbered here, the box that disappears is the last
 * one rather than the one the user clicked - they take out the left-hand basin
 * and the right-hand one vanishes.
 */

function line(overrides: Partial<SelectionLine> = {}): SelectionLine {
  return {
    lineId: 'line-1',
    productId: 'prod-1',
    productCode: 'BASIN-1',
    productName: 'Basin',
    quantity: 1,
    price: '100.00',
    invoicePrice: null,
    lineTotal: '100.00',
    dimensionsMm: { length: 600, width: 500, height: 850 },
    isAvailable: true,
    unavailableReason: null,
    ...overrides,
  };
}

function selection(lines: SelectionLine[], room: Selection['room'] = null): Selection {
  return {
    id: 'sel-1',
    name: null,
    currency: 'MYR',
    lines,
    total: '0.00',
    unavailableCount: 0,
    room,
    roomAreaSqm: null,
  };
}

describe('boxesForSelection', () => {
  it('makes one box per unit of quantity', () => {
    const boxes = boxesForSelection(selection([line({ quantity: 3 })]), []);
    expect(boxes).toHaveLength(3);
    expect(boxes.map((box) => box.id)).toEqual(['line-1-0', 'line-1-1', 'line-1-2']);
  });

  it('uses the real dimensions when the catalogue has them', () => {
    const [box] = boxesForSelection(selection([line()]), []);
    expect([box.width, box.depth, box.heightMm]).toEqual([600, 500, 850]);
    expect(box.isEstimated).toBe(false);
  });

  it('falls back to an obvious default and says so', () => {
    const [box] = boxesForSelection(selection([line({ dimensionsMm: null })]), []);
    // A wrong-sized box that looks right is worse than one that admits it.
    expect(box.isEstimated).toBe(true);
    expect([box.width, box.depth, box.heightMm]).toEqual([600, 600, 900]);
  });

  it('restores saved positions when reopening', () => {
    const saved = selection([line()], {
      outline: [],
      placements: [{ lineId: 'line-1-0', productId: 'prod-1', x: 1500, y: 900, rotation: 90 }],
    });
    const [box] = boxesForSelection(saved, []);
    expect([box.x, box.y, box.rotation]).toEqual([1500, 900, 90]);
  });

  it('lets a position being dragged now beat the one last saved', () => {
    // Otherwise a refetch landing mid-drag snaps the box back under the cursor.
    const saved = selection([line()], {
      outline: [],
      placements: [{ lineId: 'line-1-0', productId: 'prod-1', x: 1500, y: 900, rotation: 0 }],
    });
    const dragging: PlacedBox[] = [
      { ...boxesForSelection(saved, [])[0], x: 2500, y: 100 },
    ];
    const [box] = boxesForSelection(saved, dragging);
    expect([box.x, box.y]).toEqual([2500, 100]);
  });

  it('spreads new boxes out rather than stacking them', () => {
    const boxes = boxesForSelection(selection([line({ quantity: 2 })]), []);
    expect(boxes[0].x).not.toBe(boxes[1].x);
  });

  it('treats a fractional quantity as at least one box', () => {
    expect(boxesForSelection(selection([line({ quantity: 0.4 })]), [])).toHaveLength(1);
  });
});

describe('removeBox', () => {
  const three = () => boxesForSelection(selection([line({ quantity: 3 })]), []);

  it('removes the box that was asked for, not the last one', () => {
    const boxes = three();
    const middle = boxes[1];
    const left = boxes[0];
    const right = boxes[2];

    const after = removeBox(boxes, middle.id);

    expect(after).toHaveLength(2);
    // The survivors are the two the user did NOT click, at their own positions.
    expect(after.map((box) => box.x)).toEqual([left.x, right.x]);
  });

  it('renumbers the survivors so the next rebuild finds them', () => {
    const boxes = three();
    const after = removeBox(boxes, boxes[0].id);
    // Quantity becomes 2, so the rebuild looks for -0 and -1. If the survivors
    // kept -1 and -2 their positions would be lost on the next refetch.
    expect(after.map((box) => box.id)).toEqual(['line-1-0', 'line-1-1']);
  });

  it('keeps the survivors where they were standing', () => {
    const boxes = three().map((box, index) => ({ ...box, x: 1000 * index, rotation: 90 * index }));
    const after = removeBox(boxes, boxes[0].id);
    expect(after.map((box) => box.x)).toEqual([1000, 2000]);
    expect(after.map((box) => box.rotation)).toEqual([90, 180]);
  });

  it('leaves other products untouched', () => {
    const boxes = boxesForSelection(
      selection([
        line({ quantity: 2 }),
        line({ lineId: 'line-2', productId: 'prod-2', productCode: 'TAP-1', quantity: 1 }),
      ]),
      [],
    );
    const after = removeBox(boxes, 'line-1-0');
    expect(after.filter((box) => box.productId === 'prod-2').map((box) => box.id)).toEqual([
      'line-2-0',
    ]);
  });

  it('is a no-op for an id that is not there', () => {
    const boxes = three();
    expect(removeBox(boxes, 'nope')).toBe(boxes);
  });
});

describe('quantityOf', () => {
  it('counts the boxes standing for a product', () => {
    const boxes = boxesForSelection(selection([line({ quantity: 3 })]), []);
    expect(quantityOf(boxes, 'prod-1')).toBe(3);
    expect(quantityOf(removeBox(boxes, 'line-1-1'), 'prod-1')).toBe(2);
    expect(quantityOf(boxes, 'prod-missing')).toBe(0);
  });
});

describe('placementsOf', () => {
  it('emits one placement per box, keyed the way a rebuild reads them', () => {
    const boxes = boxesForSelection(selection([line({ quantity: 2 })]), []);
    const placements = placementsOf(boxes);
    expect(placements.map((placement) => placement.lineId)).toEqual(['line-1-0', 'line-1-1']);
    expect(placements[0]).toMatchObject({ productId: 'prod-1', rotation: 0 });
  });
});
