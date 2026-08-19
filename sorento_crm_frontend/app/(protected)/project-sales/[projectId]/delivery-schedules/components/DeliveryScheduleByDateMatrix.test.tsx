/**
 * P6 section 9.8 - the schedule turned round by EFFECTIVE date rather than by phase.
 *
 * What is pinned: an accepted override's quantity sits under its NEW date column, not the
 * phase it left (the captain's own question, 19 Aug 2026); the footer totals per date follow
 * the move; a highlighted cell keeps its tint; the whole view is read-only.
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { buildColumnStates, dateColumns } from '../lib/scheduleTotals';
import { DeliveryScheduleByDateMatrix } from './DeliveryScheduleByDateMatrix';
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
  { id: 'ph1', area_group: 'TOWER', sequence: 1, label: 'Level 2 & 7', delivery_date: '2027-01-07' },
  { id: 'ph2', area_group: 'TOWER', sequence: 2, label: 'Level 8 & 10', delivery_date: '2027-01-21' },
];

const products = [
  {
    product_id: 'srt382-6',
    product_code: 'SRT382-6',
    product_name: 'Floor Trap',
    customer_code_raw: 'BUI-HB-SRT382-6',
    resolution_source: 'code' as const,
    reported_total: '259',
    po_qty: '259',
    product_index: 0,
  },
];

const cells = [
  {
    phase_id: 'ph1',
    product_id: 'srt382-6',
    product_index: 0,
    qty: '135',
    delivery_date_override: '2026-07-23',
    highlight: '#ffe08a',
  },
  { phase_id: 'ph2', product_id: 'srt382-6', product_index: 0, qty: '124' },
];

function controller(overrides: Partial<ScheduleGridController> = {}): ScheduleGridController {
  const columns = buildColumnStates(products, phases, cells);
  return {
    columns,
    phaseGroups: [],
    valueFor: () => '',
    setDraft: vi.fn(),
    commit: vi.fn(),
    resolveProduct: vi.fn(),
    poOptions: [],
    canEdit: true,
    learnedColumns: [],
    registerColumnRef: vi.fn(),
    focusRequest: null,
    metaFor: (phaseId, columnKey) =>
      phaseId === 'ph1' && columnKey === 'srt382-6'
        ? { highlight: '#ffe08a', deliveryDateOverride: '2026-07-23' }
        : undefined,
    ...overrides,
  };
}

describe('DeliveryScheduleByDateMatrix', () => {
  it('puts the moved quantity under its new date, was -> now, and drops it from the old one', () => {
    const columns = dateColumns({ phases, cells });
    render(<DeliveryScheduleByDateMatrix controller={controller()} dateColumns={columns} />);

    const grid = within(screen.getByTestId('schedule-by-date-matrix'));
    const newColumn = grid.getByRole('columnheader', { name: /23\/07\/2026/ });
    expect(within(newColumn).getByText('Level 2 & 7')).toBeInTheDocument();

    const rows = grid.getAllByRole('row').filter((row) => row.querySelector('td'));
    const movedCell = within(rows[0]).getAllByRole('cell')[0];
    expect(within(movedCell).getByText('135')).toBeInTheDocument();
    expect(within(movedCell).getByText('07/01/2027')).toBeInTheDocument(); // struck "was"
    expect(within(movedCell).getByText('23/07/2026')).toBeInTheDocument(); // "now"

    // Nothing left under the phase's own 07/01/2027 column - it moved, not copied.
    expect(grid.queryByRole('columnheader', { name: /07\/01\/2027/ })).toBeNull();
  });

  it('tints a highlighted cell and titles it, same as the By phase grid', () => {
    const columns = dateColumns({ phases, cells });
    render(<DeliveryScheduleByDateMatrix controller={controller()} dateColumns={columns} />);

    const body = screen.getByTestId('schedule-by-date-matrix').querySelector('tbody') as HTMLElement;
    const cell = within(body).getByText('135').closest('td');
    expect(cell?.getAttribute('style')).toContain('color-mix(in oklab,');
    expect(cell).toHaveAttribute('title', 'Highlighted in the document');
  });

  it('sums the footer per date column, following the move', () => {
    const columns = dateColumns({ phases, cells });
    render(<DeliveryScheduleByDateMatrix controller={controller()} dateColumns={columns} />);

    const foot = within(screen.getByTestId('schedule-by-date-matrix').querySelector('tfoot') as HTMLElement);
    expect(foot.getByText('135')).toBeInTheDocument();
    expect(foot.getByText('124')).toBeInTheDocument();
  });

  it('renders no input anywhere - read-only', () => {
    const columns = dateColumns({ phases, cells });
    render(<DeliveryScheduleByDateMatrix controller={controller()} dateColumns={columns} />);

    expect(screen.queryByRole('textbox')).toBeNull();
    expect(document.querySelector('input')).toBeNull();
  });

  it('leaves a blank cell blank when a product has no cell on that date', () => {
    const twoProducts = [
      ...products,
      {
        product_id: 'p2',
        product_code: 'OTHER',
        product_name: 'Other product',
        customer_code_raw: 'BUI-HB-OTHER',
        resolution_source: 'code' as const,
        reported_total: '10',
        po_qty: '10',
        product_index: 1,
      },
    ];
    const twoProductCells = [...cells, { phase_id: 'ph2', product_id: 'p2', product_index: 1, qty: '10' }];
    const columns = dateColumns({ phases, cells: twoProductCells });
    const gridController: ScheduleGridController = {
      ...controller(),
      columns: buildColumnStates(twoProducts, phases, twoProductCells),
    };
    render(<DeliveryScheduleByDateMatrix controller={gridController} dateColumns={columns} />);

    const grid = within(screen.getByTestId('schedule-by-date-matrix'));
    const rows = grid.getAllByRole('row').filter((row) => row.querySelector('td'));
    // p2's row has no cell under 23/07/2026 (SRT382-6's own re-date), so its first date
    // cell is empty.
    const p2Row = rows.find((row) => within(row).queryByText('OTHER'));
    expect(p2Row).toBeTruthy();
    const firstCell = within(p2Row as HTMLElement).getAllByRole('cell')[0];
    expect(firstCell.textContent?.trim()).toBe('');
  });
});
