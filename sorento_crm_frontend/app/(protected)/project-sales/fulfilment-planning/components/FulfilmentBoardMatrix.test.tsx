/**
 * The board fills its container (A4, PLAN-demo-followups-19aug-ladder-v2.md).
 *
 * With the table at `w-max` and every date column pinned to `w-[150px]`, a two-week selection
 * occupied a third of the bordered container and left the rest blank. `w-full` on the table plus
 * a `min-w` FLOOR on the date columns (never a fixed width) lets them stretch to fill it; the
 * product column keeps its fixed width because it is not part of what should stretch. With many
 * columns the table still overflows past the floor, and the container's own `overflow-auto`
 * takes it from there - so this pins the class set at both ends: two columns and twenty.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FulfilmentBoardMatrix } from './FulfilmentBoardMatrix';
import type {
  BoardAxisRow,
  BoardDateBucket,
} from '../../_shared/types/fulfilmentPlanning.types';

function buckets(count: number): BoardDateBucket[] {
  return Array.from({ length: count }, (_unused, index) => ({
    key: `2026-0${(index % 9) + 1}-01`,
    kind: 'dated' as const,
    label: `Bucket ${index + 1}`,
    start: `2026-0${(index % 9) + 1}-01`,
    is_past: false,
  }));
}

const rows: BoardAxisRow[] = [{ key: 'ZZT-PRODUCT', label: 'ZZT-PRODUCT' }];

describe('FulfilmentBoardMatrix fills its container', () => {
  it('renders a w-full table with a min-w floor on the date columns, not a fixed width', () => {
    render(
      <FulfilmentBoardMatrix
        dateBuckets={buckets(2)}
        rows={rows}
        rowHeader="Product"
        cells={[]}
        decidedKeys={new Set()}
        onOpenCell={() => {}}
      />,
    );

    const table = screen.getByRole('table');
    expect(table.className).toContain('w-full');
    expect(table.className).not.toContain('w-max');

    for (const header of screen.getAllByRole('columnheader')) {
      if (header.textContent === 'Product') continue;
      // A floor, never a fixed or maximum width: those are what stopped the columns from
      // stretching in the first place.
      expect(header.className).toContain('min-w-[150px]');
      expect(header.className).not.toMatch(/(?<!min-)w-\[150px\]/);
      expect(header.className).not.toContain('max-w-[150px]');
    }
  });

  it('keeps the product column at a fixed width so it does not stretch with the rest', () => {
    render(
      <FulfilmentBoardMatrix
        dateBuckets={buckets(2)}
        rows={rows}
        rowHeader="Product"
        cells={[]}
        decidedKeys={new Set()}
        onOpenCell={() => {}}
      />,
    );

    const corner = screen.getByRole('columnheader', { name: 'Product' });
    expect(corner.className).toContain('w-[190px]');
    expect(corner.className).toContain('min-w-[190px]');
    expect(corner.className).toContain('max-w-[190px]');
  });

  it('still overflows into the scrollable container with twenty columns', () => {
    render(
      <FulfilmentBoardMatrix
        dateBuckets={buckets(20)}
        rows={rows}
        rowHeader="Product"
        cells={[]}
        decidedKeys={new Set()}
        onOpenCell={() => {}}
      />,
    );

    expect(screen.getAllByRole('columnheader')).toHaveLength(21); // 20 dates + the corner
    const container = screen.getByTestId('fulfilment-board-matrix');
    expect(container.className).toContain('overflow-auto');
    const table = screen.getByRole('table');
    expect(table.className).toContain('w-full');
    for (const header of screen.getAllByRole('columnheader')) {
      if (header.textContent === 'Product') continue;
      expect(header.className).toContain('min-w-[150px]');
    }
  });
});
