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
    ...overrides,
  };
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

  it('offers no editing at all when the user cannot edit', () => {
    render(<DeliveryScheduleMatrix controller={controller({ canEdit: false })} />);
    expect(screen.getByLabelText('Level 2 & 7, SRTWC8613-RL')).toBeDisabled();
  });
});
