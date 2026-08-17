/**
 * P4 - the 52 lines, edited in place (AC-D3).
 *
 * Two things are pinned here. Money and quantity stay STRINGS: a cell sends back exactly the
 * characters typed, never a re-serialised float. And cancelling a line is a confirmed action
 * that marks the line, never a delete.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { POVersionLine } from '../../_shared/types/poIntake.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/purchase-orders/v1',
  useSearchParams: () => ({ get: () => null }),
}));

// The product picker hits the shared products `/select` endpoint on open; the grid tests do
// not exercise the dropdown, so the fetch is stubbed rather than the component replaced.
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: vi.fn(async () => []),
}));

// The shared DataGrid holds its SKELETON rows until the column-preferences query settles, and
// under jsdom that query never settles, so no assertion about a cell could ever pass. This is
// the mock every grid test in this phase uses.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: vi.fn(),
    warning: vi.fn(),
  },
}));

import {
  POIntakeLinesGrid,
  describeLineHealth,
  isFlaggedLine,
  lineNeedsAttention,
  type POIntakeLinesGridHandle,
} from './POIntakeLinesGrid';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

function line(overrides: Partial<POVersionLine> = {}): POVersionLine {
  return {
    id: 'l1',
    line_no: 1,
    stock_code_raw: 'SRTWC8613-RL',
    description_raw: 'RIMLESS CLOSE COUPLED WC',
    qty: '927',
    uom_raw: 'SETS',
    unit_price: '392.85',
    amount: '364171.95',
    arithmetic_ok: true,
    is_cancelled: false,
    resolved_product_id: 'prod-1',
    resolved_product_code: 'SRTWC8613-RL',
    resolution_source: 'code',
    page_no: 1,
    ...overrides,
  };
}

const onUpdateLine = vi.fn(async () => {});
const onFocusLine = vi.fn();

function renderGrid(lines: POVersionLine[], readOnly = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const gridRef = React.createRef<POIntakeLinesGridHandle>();
  const view = render(
    <QueryClientProvider client={client}>
      <POIntakeLinesGrid
        ref={gridRef}
        lines={lines}
        readOnly={readOnly}
        savingLineIds={[]}
        focusedLineId={null}
        onFocusLine={onFocusLine}
        onUpdateLine={onUpdateLine}
      />
    </QueryClientProvider>,
  );
  const rerenderWith = (next: POVersionLine[]) =>
    view.rerender(
      <QueryClientProvider client={client}>
        <POIntakeLinesGrid
          ref={gridRef}
          lines={next}
          readOnly={readOnly}
          savingLineIds={[]}
          focusedLineId={null}
          onFocusLine={onFocusLine}
          onUpdateLine={onUpdateLine}
        />
      </QueryClientProvider>,
    );
  return { ...view, gridRef, rerenderWith };
}

/** Three healthy lines plus whatever the test wants to be wrong with the middle one. */
function threeLines(middle: Partial<POVersionLine> = {}): POVersionLine[] {
  return [
    line({ id: 'l1', line_no: 1 }),
    line({ id: 'l2', line_no: 2, ...middle }),
    line({ id: 'l3', line_no: 3 }),
  ];
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('POIntakeLinesGrid', () => {
  it('renders every extracted field as an editable cell', async () => {
    renderGrid([line()]);

    expect(await screen.findByLabelText('Code on line 1')).toHaveValue('SRTWC8613-RL');
    expect(screen.getByLabelText('Quantity on line 1')).toHaveValue('927');
    expect(screen.getByLabelText('Unit price on line 1')).toHaveValue('392.85');
    expect(screen.getByLabelText('Amount on line 1')).toHaveValue('364171.95');
  });

  it('sends the typed string for the one field that changed', async () => {
    renderGrid([line()]);

    const qty = await screen.findByLabelText('Quantity on line 1');
    fireEvent.change(qty, { target: { value: '920.50' } });
    fireEvent.blur(qty);

    expect(onUpdateLine).toHaveBeenCalledTimes(1);
    expect(onUpdateLine).toHaveBeenCalledWith('l1', { qty: '920.50' });
  });

  it('saves nothing when a cell is left as it was', async () => {
    renderGrid([line()]);

    const code = await screen.findByLabelText('Code on line 1');
    fireEvent.focus(code);
    fireEvent.blur(code);

    expect(onUpdateLine).not.toHaveBeenCalled();
  });

  it('refuses a quantity that is not a number and puts the cell back', async () => {
    renderGrid([line()]);

    const qty = await screen.findByLabelText('Quantity on line 1');
    fireEvent.change(qty, { target: { value: 'about nine hundred' } });
    fireEvent.blur(qty);

    expect(onUpdateLine).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalledWith('Quantity on line 1 must be a number');
    expect(qty).toHaveValue('927');
  });

  it('marks the line where our arithmetic disagrees with the paper, with the amount', async () => {
    renderGrid([line({ amount: '3410.00', arithmetic_ok: false })]);

    expect(await screen.findByText('Should be RM 364,171.95')).toBeInTheDocument();
  });

  it('flags a line with no product without hiding it', async () => {
    renderGrid([line({ resolved_product_id: null, resolved_product_code: null })]);

    expect(await screen.findByText('No product')).toBeInTheDocument();
  });

  it('confirms before cancelling a line, and marks it rather than deleting it', async () => {
    renderGrid([line({ line_no: 7, stock_code_raw: 'SRTFV1001', amount: '600.00' })]);

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel line 7' }));
    const dialog = screen.getByRole('alertdialog');
    expect(dialog.textContent).toMatch(/stays on the record, marked cancelled/);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel the line' }));
    expect(onUpdateLine).toHaveBeenCalledWith('l1', { is_cancelled: true });
  });

  it('offers a cancelled line back rather than stranding it', async () => {
    renderGrid([line({ line_no: 7, is_cancelled: true })]);

    expect(await screen.findByText('Cancelled')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Restore line 7' }));
    expect(onUpdateLine).toHaveBeenCalledWith('l1', { is_cancelled: false });
  });

  it('gives every line a product picker rather than leaving it unmatchable', async () => {
    renderGrid([line()]);

    expect(await screen.findByLabelText('Product on line 1')).toBeInTheDocument();
  });

  it('shows a reader the values and no inputs at all', async () => {
    renderGrid([line()], true);

    expect(await screen.findByText('927')).toBeInTheDocument();
    expect(screen.queryByLabelText('Quantity on line 1')).toBeNull();
    expect(screen.getByText('364171.95')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Cancel line/ })).toBeNull();
  });
});

/**
 * Reviewing exceptions instead of reading the whole document is the promise of this screen,
 * so the flagged lines can be shown on their own. The filter starts OFF: a total cannot be
 * reconciled against a table that is already hiding rows.
 */
describe('POIntakeLinesGrid, showing only what needs attention', () => {
  it('counts the work in a sentence a person can act on', () => {
    expect(describeLineHealth(52, 3, 0)).toBe('3 of 52 lines need attention');
    expect(describeLineHealth(52, 3, 1)).toBe(
      '3 of 52 lines need attention, and 1 is cancelled',
    );
    expect(describeLineHealth(52, 0, 0)).toBe('All 52 lines add up and resolve');
    expect(describeLineHealth(52, 0, 2)).toBe(
      'All 52 lines add up and resolve, 2 are cancelled',
    );
  });

  it('counts a cancelled line as an exception to see, not as work outstanding', () => {
    const cancelled = line({ is_cancelled: true });
    expect(isFlaggedLine(cancelled)).toBe(true);
    expect(lineNeedsAttention(cancelled)).toBe(false);

    const unresolved = line({ resolved_product_id: null });
    expect(isFlaggedLine(unresolved)).toBe(true);
    expect(lineNeedsAttention(unresolved)).toBe(true);
  });

  it('starts by showing every line, and says how many of them are the work', async () => {
    renderGrid(threeLines({ arithmetic_ok: false }));

    expect(await screen.findByText('1 of 3 lines need attention')).toBeInTheDocument();
    expect(screen.getByLabelText('Quantity on line 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();
    expect(screen.getByLabelText('Quantity on line 3')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Show only these 1/ }),
    ).toHaveAttribute('aria-pressed', 'false');
  });

  it('drops the healthy rows when asked, and puts them back', async () => {
    renderGrid(threeLines({ arithmetic_ok: false }));

    fireEvent.click(await screen.findByRole('button', { name: /Show only these 1/ }));

    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();
    expect(screen.queryByLabelText('Quantity on line 1')).toBeNull();
    expect(screen.queryByLabelText('Quantity on line 3')).toBeNull();
    // The count keeps describing the whole document, not the filtered view.
    expect(screen.getByText('1 of 3 lines need attention')).toBeInTheDocument();

    const back = screen.getByRole('button', { name: 'Show all 3 lines' });
    expect(back).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(back);
    expect(screen.getByLabelText('Quantity on line 1')).toBeInTheDocument();
  });

  it('keeps a cancelled line in the filtered view', async () => {
    renderGrid(threeLines({ is_cancelled: true }));

    fireEvent.click(await screen.findByRole('button', { name: /Show only these 1/ }));

    expect(screen.getByText('Cancelled')).toBeInTheDocument();
    expect(screen.queryByLabelText('Quantity on line 1')).toBeNull();
    expect(
      screen.getByText('All 3 lines add up and resolve, 1 is cancelled'),
    ).toBeInTheDocument();
  });

  it('says so plainly when there is nothing to filter down to', async () => {
    renderGrid(threeLines());

    expect(await screen.findByText('All 3 lines add up and resolve')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Show only/ })).toBeNull();
  });

  it('reads an emptied filter as good news, not as an empty table', async () => {
    const { rerenderWith } = renderGrid(threeLines({ arithmetic_ok: false }));

    fireEvent.click(await screen.findByRole('button', { name: /Show only these 1/ }));
    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();

    // The line gets fixed, so the filter now matches nothing at all.
    rerenderWith(threeLines());

    expect(screen.getByText('Nothing left to fix')).toBeInTheDocument();
    expect(
      screen.getByText('Every line adds up and resolves to a product.'),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Quantity on line 2')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Show all 3 lines' }));
    expect(screen.getByLabelText('Quantity on line 1')).toBeInTheDocument();
  });

  it('still lands on a flagged line asked for from outside, with the filter on', async () => {
    const { gridRef } = renderGrid(threeLines({ arithmetic_ok: false }));

    fireEvent.click(await screen.findByRole('button', { name: /Show only these 1/ }));
    act(() => gridRef.current?.focusLine('l2'));

    expect(onFocusLine).toHaveBeenCalledWith(expect.objectContaining({ line_no: 2 }));
    // Still filtered: the row asked for is one of the flagged ones.
    expect(screen.getByRole('button', { name: 'Show all 3 lines' })).toBeInTheDocument();
    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();
  });

  it('gives the filter up rather than swallowing a jump to a healthy line', async () => {
    const { gridRef } = renderGrid(threeLines({ arithmetic_ok: false }));

    fireEvent.click(await screen.findByRole('button', { name: /Show only these 1/ }));
    expect(screen.queryByLabelText('Quantity on line 3')).toBeNull();

    // This is what a handwriting card naming a perfectly healthy line does.
    act(() => gridRef.current?.focusLine('l3'));

    expect(onFocusLine).toHaveBeenCalledWith(expect.objectContaining({ line_no: 3 }));
    expect(screen.getByLabelText('Quantity on line 3')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Show only these 1/ }),
    ).toHaveAttribute('aria-pressed', 'false');
  });
});
