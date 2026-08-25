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
  BoardCell,
  BoardContribution,
  BoardDateBucket,
  BoardLineDecision,
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

/**
 * "Already settled", at a glance.
 *
 * The `n/m decided` badge counts the DRAFT - verdicts the planner has ticked but not
 * confirmed. That is a different statement from "supply for this cell is confirmed in the
 * database", and a cell of eleven confirmed lines showed `0/11 decided` because nothing had
 * been ticked in this session. The marker answers the second question, and only when EVERY
 * contribution in the cell carries an active decision: a partly-decided cell is not decided.
 */
function frozen(revisionNo: number): BoardLineDecision {
  return {
    revision_no: revisionNo,
    timely_spo_qty: '0',
    reserve: [],
    borrow: [],
    buy_qty: '10',
  };
}

function contribution(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: `so-1|1|ZZT-PRODUCT|2026-01-01`,
    sales_order_id: 'so-1',
    so_number: 'SO397450',
    line_no: 1,
    item_code: 'ZZT-PRODUCT',
    qty: '10',
    unplannable: false,
    rank_score: 0,
    rank_factors: [],
    sources: [],
    contested: false,
    covered: false,
    decision: null,
    ...overrides,
  };
}

function cellWith(contributions: BoardContribution[]): BoardCell {
  return {
    item_code: 'ZZT-PRODUCT',
    row_key: 'ZZT-PRODUCT',
    bucket_key: '2026-01-01',
    total_qty: '10',
    locations: [],
    contributions,
    unplannable_count: 0,
    contested_count: 0,
  };
}

function renderMatrix(cells: BoardCell[]) {
  return render(
    <FulfilmentBoardMatrix
      dateBuckets={buckets(2)}
      rows={rows}
      rowHeader="Product"
      cells={cells}
      decidedKeys={new Set()}
      onOpenCell={() => {}}
    />,
  );
}

describe('FulfilmentBoardMatrix marks a cell whose supply is already decided', () => {
  it('ticks the cell and names the revision, when every line is covered', () => {
    renderMatrix([
      cellWith([
        contribution({ covered: true, decision: frozen(3) }),
        contribution({ key: 'so-2|1|ZZT-PRODUCT|2026-01-01', covered: true, decision: frozen(3) }),
      ]),
    ]);

    expect(screen.getByTestId('board-decided-marker')).toHaveAttribute(
      'title',
      'Decided rev 3',
    );
  });

  it('names every revision when the cell spans orders decided at different ones', () => {
    // A cell cuts across sales orders and a revision belongs to ONE order, so naming a single
    // number would attribute the decision to the wrong document.
    renderMatrix([
      cellWith([
        contribution({ covered: true, decision: frozen(1) }),
        contribution({ key: 'so-2|1|ZZT-PRODUCT|2026-01-01', covered: true, decision: frozen(4) }),
      ]),
    ]);

    expect(screen.getByTestId('board-decided-marker')).toHaveAttribute(
      'title',
      'Decided rev 1, 4',
    );
  });

  it('does not tick a cell where one line is still open', () => {
    renderMatrix([
      cellWith([
        contribution({ covered: true, decision: frozen(3) }),
        contribution({ key: 'so-2|1|ZZT-PRODUCT|2026-01-01' }),
      ]),
    ]);

    expect(screen.queryByTestId('board-decided-marker')).not.toBeInTheDocument();
  });
});
