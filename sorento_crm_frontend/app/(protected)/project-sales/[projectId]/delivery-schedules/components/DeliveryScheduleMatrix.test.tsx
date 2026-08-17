/**
 * P6 - the matrix, structurally.
 *
 * A hand-rolled table is only allowed here because the COLUMNS ARE DATA. The price of that is
 * having to solve what DataGrid would have solved, so those promises are pinned as tests rather
 * than left as intentions: one scroll container so the page body never scrolls sideways, a
 * sticky phase column, an explicit width on every cell (never `table-fixed`, which overlaps its
 * columns as soon as content exceeds the declared width), and the area headings the customer
 * grouped their phases under.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { buildColumnStates, groupPhasesByArea } from '../lib/scheduleTotals';
import { DeliveryScheduleMatrix } from './DeliveryScheduleMatrix';
import type { ScheduleGridController } from './DeliveryScheduleMatrix';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const phases = [
  {
    id: 'ph1',
    area_group: 'TOWER',
    sequence: 1,
    label: 'Level 2 & 7',
    delivery_date: '2026-07-01',
  },
  {
    id: 'ph2',
    area_group: 'COMMON AREA',
    sequence: 3,
    label: null,
    delivery_date: '2027-06-01',
  },
];

const products = [
  {
    product_id: 'p1',
    product_code: 'SRTWC8613-RL',
    product_name: 'One-Piece WC',
    customer_code_raw: 'BUI-HB-SRTWC8613-RL',
    resolution_source: 'map' as const,
    reported_total: '927',
    po_qty: '927',
    product_index: 0,
  },
];

const cells = [{ phase_id: 'ph1', product_id: 'p1', product_index: 0, qty: '927' }];

function controller(overrides: Partial<ScheduleGridController> = {}): ScheduleGridController {
  const columns = buildColumnStates(products, phases, cells);
  return {
    columns,
    phaseGroups: groupPhasesByArea(phases),
    valueFor: (phaseId) => (phaseId === 'ph1' ? '927' : ''),
    setDraft: vi.fn(),
    commit: vi.fn(),
    resolveProduct: vi.fn(),
    canEdit: true,
    learnedColumns: [],
    registerColumnRef: vi.fn(),
    focusRequest: null,
    ...overrides,
  };
}

/** The paint layer a cell declares, or 0 when it declares none. */
function zLayerOf(element: Element): number {
  const match = element.className.match(/(?:^|\s)z-(\d+)/);
  return match ? Number(match[1]) : 0;
}

/** One reconciled column and one that disagrees with the PO, so both tints render. */
function mixedColumns() {
  return buildColumnStates(
    [
      ...products,
      {
        product_id: 'p2',
        product_code: 'SRTFV1001',
        product_name: 'Sensor Urinal Flush Valve',
        customer_code_raw: 'BUI-HB-SRTFV1001',
        resolution_source: 'code' as const,
        reported_total: '16',
        po_qty: '16',
        product_index: 1,
      },
    ],
    phases,
    cells,
  );
}

describe('DeliveryScheduleMatrix', () => {
  it('scrolls inside itself so the page body never scrolls sideways', () => {
    render(<DeliveryScheduleMatrix controller={controller()} />);

    const container = screen.getByTestId('schedule-matrix');
    expect(container.className).toContain('overflow-auto');
    expect(container.className).toContain('overscroll-x-contain');

    const table = container.querySelector('table');
    // `w-max` + per-cell widths, NOT table-fixed: a fixed layout overlaps its columns.
    expect(table?.className).toContain('w-max');
    expect(table?.className).not.toContain('table-fixed');
  });

  it('keeps the phase column visible while the product columns scroll', () => {
    render(<DeliveryScheduleMatrix controller={controller()} />);

    const phaseHeader = screen.getByRole('columnheader', { name: 'Phase' });
    expect(phaseHeader.className).toContain('sticky');
    expect(phaseHeader.className).toContain('left-0');

    const phaseRow = screen.getByRole('rowheader', { name: /Level 2 & 7/ });
    expect(phaseRow.className).toContain('sticky');
    expect(phaseRow.className).toContain('left-0');
  });

  it('paints every pinned cell opaquely, so no row can show through it', () => {
    // An unreconciled column on purpose: its header and totals carried the tint that was
    // 90 percent transparent, and a quantity scrolling underneath showed straight through
    // as a number appearing in the header row.
    const { container } = render(
      <DeliveryScheduleMatrix controller={controller({ columns: mixedColumns() })} />,
    );

    const pinned = Array.from(container.querySelectorAll('.sticky'));
    expect(pinned.length).toBeGreaterThan(0);
    pinned.forEach((cell) => {
      expect(cell.className).toMatch(/\bbg-/);
      // No alpha on a background that something scrolls behind.
      expect(cell.className).not.toMatch(/\bbg-[a-z-]+\/\d+/);
      expect(zLayerOf(cell)).toBeGreaterThan(0);
    });
  });

  it('lets the cell pinned on both axes win the corner it shares', () => {
    render(<DeliveryScheduleMatrix controller={controller({ columns: mixedColumns() })} />);

    const headerCorner = screen.getByRole('columnheader', { name: 'Phase' });
    const totalsCorner = screen.getByRole('rowheader', { name: 'Our total' });
    const headerCell = screen.getByRole('columnheader', { name: /SRTWC8613-RL/ });
    const phaseCell = screen.getByRole('rowheader', { name: /Level 2 & 7/ });

    [headerCell, phaseCell].forEach((oneAxis) => {
      expect(zLayerOf(headerCorner)).toBeGreaterThan(zLayerOf(oneAxis));
      expect(zLayerOf(totalsCorner)).toBeGreaterThan(zLayerOf(oneAxis));
    });
    // And a pinned cell is always above the rows, which sit on no layer at all.
    expect(zLayerOf(phaseCell)).toBeGreaterThan(0);
  });

  it('gives every cell an explicit width', () => {
    const { container } = render(<DeliveryScheduleMatrix controller={controller()} />);
    // The area heading band spans the row on purpose, so it carries no column width.
    const dataCells = Array.from(container.querySelectorAll('tbody td:not([colspan])'));
    expect(dataCells.length).toBeGreaterThan(0);
    dataCells.forEach((cell) => {
      expect(cell.className).toMatch(/min-w-\[\d+px\]/);
    });
  });

  it('groups the phases under the area headings the customer used', () => {
    render(<DeliveryScheduleMatrix controller={controller()} />);
    expect(screen.getByRole('columnheader', { name: 'TOWER' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'COMMON AREA' })).toBeInTheDocument();
    // An unlabeled COMMON AREA row is still identifiable.
    expect(screen.getByRole('rowheader', { name: /Phase 3/ })).toBeInTheDocument();
  });

  it('puts the three totals at the foot of the column, side by side', () => {
    const { container } = render(<DeliveryScheduleMatrix controller={controller()} />);
    const foot = within(container.querySelector('tfoot') as HTMLElement);

    expect(foot.getByText('Our total')).toBeInTheDocument();
    expect(foot.getByText('Schedule TOTAL QTY')).toBeInTheDocument();
    expect(foot.getByText('PO quantity')).toBeInTheDocument();
    expect(foot.getAllByText('927')).toHaveLength(3);
  });

  it('shows a remembered customer code as remembered', () => {
    render(<DeliveryScheduleMatrix controller={controller()} />);
    expect(screen.getByText('Remembered code')).toBeInTheDocument();
    expect(screen.getByText('BUI-HB-SRTWC8613-RL')).toBeInTheDocument();
  });

  it('lets a column that resolved to the wrong product be re-picked', () => {
    render(<DeliveryScheduleMatrix controller={controller({ columns: mixedColumns() })} />);

    // SRTFV1001 has a product and still does not reconcile, which is what a wrong match
    // looks like: withholding the picker from it left the reviewer nothing to press.
    expect(
      screen.getByLabelText('Change the product for BUI-HB-SRTFV1001'),
    ).toBeInTheDocument();
    // A column that agrees with the PO is not asking to be changed.
    expect(screen.queryByLabelText(/for BUI-HB-SRTWC8613-RL/)).toBeNull();
  });

  it('offers no editing at all when the user cannot edit', () => {
    render(
      <DeliveryScheduleMatrix
        controller={controller({ canEdit: false, columns: mixedColumns() })}
      />,
    );
    expect(screen.getByLabelText('Level 2 & 7, SRTWC8613-RL')).toBeDisabled();
    expect(screen.queryByLabelText(/Change the product/)).toBeNull();
    expect(screen.queryByLabelText(/Pick the product/)).toBeNull();
  });
});
