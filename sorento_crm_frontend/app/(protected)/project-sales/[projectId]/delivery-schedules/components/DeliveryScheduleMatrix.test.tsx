/**
 * P6 - the matrix, structurally, and the axis it is drawn on.
 *
 * TRANSPOSED against the customer's printed sheet: dates run across the top, products down the
 * side. The sheet is the other way round and this grid used to mirror it; the captain asked for
 * the axis people actually ask questions along ("what goes out on the first of July" is a
 * column, "how much of this basin is scheduled" is a row). The DATA did not move with it, and
 * that is half of what is pinned here: a cell still carries the same name, the same key and the
 * same write.
 *
 * A hand-rolled table is only allowed here because the COLUMNS ARE DATA - one per delivery
 * phase. The price of that is having to solve what DataGrid would have solved, so those
 * promises are pinned rather than left as intentions: one scroll container so the page body
 * never scrolls sideways, a sticky product column, an explicit width on every cell (never
 * `table-fixed`, which overlaps its columns as soon as content exceeds the declared width),
 * and the area groupings the customer wrote.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
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
    poOptions: [],
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

  it('runs the dates across the top and the products down the side', () => {
    render(<DeliveryScheduleMatrix controller={controller({ columns: mixedColumns() })} />);

    // A delivery phase is a COLUMN now: its date leads, the phase it belongs to follows.
    const july = screen.getByRole('columnheader', { name: /01\/07\/2026/ });
    expect(july).toHaveTextContent('Level 2 & 7');
    // An unlabelled COMMON AREA phase is still identifiable by its number.
    expect(screen.getByRole('columnheader', { name: /Phase 3/ })).toBeInTheDocument();

    // A product is a ROW, headed by its code with the customer's own code beneath.
    const product = screen.getByRole('rowheader', { name: /SRTWC8613-RL/ });
    expect(product).toHaveTextContent('BUI-HB-SRTWC8613-RL');
    expect(product.tagName).toBe('TH');
  });

  it('hands the jump a row, not the pinned cell a browser refuses to scroll to', () => {
    const registerColumnRef = vi.fn();
    render(<DeliveryScheduleMatrix controller={controller({ registerColumnRef })} />);

    const [key, node] = registerColumnRef.mock.calls.find(([, n]) => n) ?? [];
    expect(key).toBe('p1');
    // Chrome logs "Skipping auto-scroll behavior due to position: sticky" and does nothing
    // when scrollIntoView is called on a pinned element, which is what the identity cell is.
    expect((node as HTMLElement).tagName).toBe('TR');
    expect(String((node as HTMLElement).className)).not.toContain('sticky');
  });

  it('keeps the product column visible while the dates scroll', () => {
    render(<DeliveryScheduleMatrix controller={controller()} />);

    const productHeader = screen.getByRole('columnheader', { name: 'Product' });
    expect(productHeader.className).toContain('sticky');
    expect(productHeader.className).toContain('left-0');

    const productRow = screen.getByRole('rowheader', { name: /SRTWC8613-RL/ });
    expect(productRow.className).toContain('sticky');
    expect(productRow.className).toContain('left-0');
  });

  /**
   * The axis moved; the write did not. A cell is still addressed by (phase, product), still
   * named phase-first, and still commits on blur through the same controller.
   */
  it('writes a cell exactly as it did before the transpose', () => {
    const setDraft = vi.fn();
    const commit = vi.fn();
    const state = controller({ setDraft, commit });
    render(<DeliveryScheduleMatrix controller={state} />);

    const cell = screen.getByLabelText('Level 2 & 7, SRTWC8613-RL');
    // The product's own key, so the reconciliation list can still put the cursor in it.
    expect(cell).toHaveAttribute('data-column-key', 'p1');

    fireEvent.change(cell, { target: { value: '16' } });
    expect(setDraft).toHaveBeenCalledWith('ph1', 'p1', '16');

    fireEvent.blur(cell);
    expect(commit).toHaveBeenCalledWith('ph1', state.columns[0]);
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

    const headerCorner = screen.getByRole('columnheader', { name: 'Product' });
    const totalsCorner = screen.getByRole('rowheader', { name: 'Our total for the date' });
    const dateCell = screen.getByRole('columnheader', { name: /01\/07\/2026/ });
    const productCell = screen.getByRole('rowheader', { name: /SRTWC8613-RL/ });

    [dateCell, productCell].forEach((oneAxis) => {
      expect(zLayerOf(headerCorner)).toBeGreaterThan(zLayerOf(oneAxis));
      expect(zLayerOf(totalsCorner)).toBeGreaterThan(zLayerOf(oneAxis));
    });
    // And a pinned cell is always above the rows, which sit on no layer at all.
    expect(zLayerOf(productCell)).toBeGreaterThan(0);
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

  it('names the area on the first date of each group, not on every one of them', () => {
    render(<DeliveryScheduleMatrix controller={controller()} />);

    // The grouping the customer wrote survives the transpose as a label on the column that
    // opens each area, rather than as a band across a row that no longer exists.
    expect(screen.getByRole('columnheader', { name: /TOWER/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /COMMON AREA/ })).toBeInTheDocument();
  });

  it('closes every product row with its three totals, side by side', () => {
    const { container } = render(<DeliveryScheduleMatrix controller={controller()} />);

    // The transpose of the old totals band: what were three rows under a product column are
    // three cells at the end of a product row.
    const head = within(container.querySelector('thead') as HTMLElement);
    expect(head.getByText('Our total')).toBeInTheDocument();
    expect(head.getByText('Schedule TOTAL QTY')).toBeInTheDocument();
    expect(head.getByText('PO quantity')).toBeInTheDocument();

    const row = screen.getByRole('rowheader', { name: /SRTWC8613-RL/ }).closest('tr');
    const cells = Array.from(row?.querySelectorAll('td') ?? []);
    // Two dates, then the three numbers.
    expect(cells).toHaveLength(5);
    expect(cells.slice(2).map((cell) => cell.textContent)).toEqual(['927', '927', '927']);
  });

  it('totals each date at the foot, because that is what the top axis now asks', () => {
    const { container } = render(<DeliveryScheduleMatrix controller={controller()} />);
    const foot = within(container.querySelector('tfoot') as HTMLElement);

    // Ours, and labelled as ours: the printed sheet has no such row.
    expect(foot.getByText('Our total for the date')).toBeInTheDocument();
    const totals = Array.from(
      container.querySelectorAll('tfoot td'),
    ).map((cell) => cell.textContent);
    // 927 goes out on the first date, nothing on the second, 927 across the sheet.
    expect(totals).toEqual(['927', '', '927', '', '']);
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
