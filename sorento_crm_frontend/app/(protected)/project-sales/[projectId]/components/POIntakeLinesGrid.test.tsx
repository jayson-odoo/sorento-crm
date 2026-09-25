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
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { POAnnotation, POVersionLine } from '../../_shared/types/poIntake.types';

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
vi.mock('@/lib/toast', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: vi.fn(),
    warning: vi.fn(),
  },
}));

import {
  POIntakeLinesGrid,
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
const onShowPage = vi.fn();
const onAcceptAnnotation = vi.fn(async () => {});
const onEditAnnotation = vi.fn(async () => {});
const onRejectAnnotation = vi.fn(async () => {});

function annotation(overrides: Partial<POAnnotation> = {}): POAnnotation {
  return {
    id: 'a1',
    page_no: 1,
    crop_url: null,
    raw_text: 'cancel this, refer to new P/O HQ/26/05/087',
    written_date: '15/5/26',
    refers_to_lines: [1],
    interpretation: 'cancel_line',
    interpretation_json: { line_nos: [1] },
    state: 'proposed',
    actioned_by_name: null,
    actioned_at: null,
    action_note: null,
    ...overrides,
  };
}

interface RenderOptions {
  readOnly?: boolean;
  annotations?: POAnnotation[];
  focusedLineId?: string | null;
  defaultFlaggedOnly?: boolean;
}

function renderGrid(lines: POVersionLine[], options: RenderOptions | boolean = {}) {
  // The old two-arg call (`renderGrid(lines, true)`) stays valid: a bare boolean is readOnly.
  const opts: RenderOptions = typeof options === 'boolean' ? { readOnly: options } : options;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const gridRef = React.createRef<POIntakeLinesGridHandle>();
  const build = (nextLines: POVersionLine[], next: RenderOptions) => (
    <QueryClientProvider client={client}>
      <POIntakeLinesGrid
        ref={gridRef}
        lines={nextLines}
        readOnly={next.readOnly ?? false}
        savingLineIds={[]}
        focusedLineId={next.focusedLineId ?? null}
        onFocusLine={onFocusLine}
        onUpdateLine={onUpdateLine}
        annotations={next.annotations ?? []}
        savingAnnotationIds={[]}
        onShowPage={onShowPage}
        onAcceptAnnotation={onAcceptAnnotation}
        onEditAnnotation={onEditAnnotation}
        onRejectAnnotation={onRejectAnnotation}
        defaultFlaggedOnly={next.defaultFlaggedOnly}
      />
    </QueryClientProvider>
  );
  const view = render(build(lines, opts));
  const rerenderWith = (next: POVersionLine[], nextOpts: RenderOptions = opts) =>
    view.rerender(build(next, nextOpts));
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
 * Owner hand test, 25 Sep 2026, item 1: the Lines tab grid at 1280 cut the Amount column off
 * at the right edge with no way to reach it.
 *
 * jsdom does no real layout, so what this pins is structural, the same way
 * `BoardCellBreakdownDialog.test.tsx`'s "the table scrolls inside its own container" test
 * does: the table lives inside the grid's OWN horizontal scrollport
 * (`data-grid-scroller`, `overflow-x-auto`), and nothing wraps it in a second one. A Radix
 * `ScrollArea` around `DataGridTable` gives the table a `display: table` ancestor that
 * shrink-fits, so `data-grid-scroller` measures `scrollWidth === clientWidth`, never
 * overflows, and the horizontal `ScrollBar` never has anything to move - which is exactly
 * what clipped the Amount column with no way to reach it. See
 * `components/ui/data-grid-scroller.inventory.test.ts` for the tree-wide guard this grid used
 * to be exempted from.
 */
describe('POIntakeLinesGrid: the grid scrolls horizontally inside its own container (owner hand test 25 Sep 2026, item 1)', () => {
  it('puts the table in the grid\'s own scroller, with no second scrollport around it', async () => {
    renderGrid([line()]);
    await screen.findByLabelText('Code on line 1');

    const scroller = document.querySelector('[data-slot="data-grid-scroller"]');
    expect(scroller).not.toBeNull();
    expect(scroller).toHaveClass('overflow-x-auto');
    expect(scroller).toHaveClass('min-w-0');

    const table = document.querySelector('[data-slot="data-grid-table"]') as HTMLElement | null;
    expect(table).not.toBeNull();
    expect(scroller!.contains(table!)).toBe(true);
    for (let node = table!.parentElement; node && node !== scroller; node = node.parentElement) {
      expect(node.hasAttribute('data-radix-scroll-area-viewport')).toBe(false);
    }

    // No second scrollport anywhere between the grid's own scroller and the document root.
    let node: Element | null = scroller;
    while (node) {
      expect(node.getAttribute('data-slot')).not.toBe('scroll-area');
      expect(node.hasAttribute('data-radix-scroll-area-viewport')).toBe(false);
      node = node.parentElement;
    }
  });
});

/**
 * Reviewing exceptions instead of reading the whole document is the promise of this screen,
 * so the flagged lines can be shown on their own. The filter starts OFF: a total cannot be
 * reconciled against a table that is already hiding rows.
 */
describe('POIntakeLinesGrid, showing only what needs attention', () => {
  it('counts a cancelled line as an exception to see, not as work outstanding', () => {
    const cancelled = line({ is_cancelled: true });
    expect(isFlaggedLine(cancelled)).toBe(true);
    expect(lineNeedsAttention(cancelled)).toBe(false);

    const unresolved = line({ resolved_product_id: null });
    expect(isFlaggedLine(unresolved)).toBe(true);
    expect(lineNeedsAttention(unresolved)).toBe(true);
  });

  it('starts by showing every line, unfiltered', async () => {
    renderGrid(threeLines({ arithmetic_ok: false }));

    expect(await screen.findByLabelText('Quantity on line 1')).toBeInTheDocument();
    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();
    expect(screen.getByLabelText('Quantity on line 3')).toBeInTheDocument();
    expect(
      screen.getByRole('radio', { name: /Need attention \(1\)/ }),
    ).toHaveAttribute('aria-checked', 'false');
  });

  it('drops the healthy rows when asked, and puts them back', async () => {
    renderGrid(threeLines({ arithmetic_ok: false }));

    fireEvent.click(await screen.findByRole('radio', { name: /Need attention \(1\)/ }));

    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();
    expect(screen.queryByLabelText('Quantity on line 1')).toBeNull();
    expect(screen.queryByLabelText('Quantity on line 3')).toBeNull();

    expect(
      screen.getByRole('radio', { name: /Need attention \(1\)/ }),
    ).toHaveAttribute('aria-checked', 'true');
    const back = screen.getByRole('radio', { name: 'All lines (3)' });
    expect(back).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(back);
    expect(screen.getByLabelText('Quantity on line 1')).toBeInTheDocument();
  });

  it('keeps a cancelled line in the filtered view', async () => {
    renderGrid(threeLines({ is_cancelled: true }));

    fireEvent.click(await screen.findByRole('radio', { name: /Need attention \(1\)/ }));

    expect(screen.getByText('Cancelled')).toBeInTheDocument();
    expect(screen.queryByLabelText('Quantity on line 1')).toBeNull();
  });

  it('opens on Need attention when defaultFlaggedOnly is set, unlike the default (S6-3)', async () => {
    renderGrid(threeLines({ arithmetic_ok: false }), { defaultFlaggedOnly: true });

    expect(
      await screen.findByRole('radio', { name: /Need attention \(1\)/ }),
    ).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();
    expect(screen.queryByLabelText('Quantity on line 1')).toBeNull();
  });

  it('shows no filter toggle at all when there is nothing to filter down to', async () => {
    renderGrid(threeLines());

    await screen.findByLabelText('Quantity on line 1');
    expect(screen.queryByRole('radio', { name: /Need attention/ })).toBeNull();
    expect(screen.queryByRole('radio', { name: /All lines/ })).toBeNull();
  });

  it('reads an emptied filter as good news, not as an empty table', async () => {
    const { rerenderWith } = renderGrid(threeLines({ arithmetic_ok: false }));

    fireEvent.click(await screen.findByRole('radio', { name: /Need attention \(1\)/ }));
    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();

    // The line gets fixed, so the filter now matches nothing at all.
    rerenderWith(threeLines());

    expect(screen.getByText('Nothing left to fix')).toBeInTheDocument();
    expect(screen.queryByLabelText('Quantity on line 2')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'All lines (3)' }));
    expect(screen.getByLabelText('Quantity on line 1')).toBeInTheDocument();
  });

  it('still lands on a flagged line asked for from outside, with the filter on', async () => {
    const { gridRef } = renderGrid(threeLines({ arithmetic_ok: false }));

    fireEvent.click(await screen.findByRole('radio', { name: /Need attention \(1\)/ }));
    act(() => gridRef.current?.focusLine('l2'));

    expect(onFocusLine).toHaveBeenCalledWith(expect.objectContaining({ line_no: 2 }));
    // Still filtered: the row asked for is one of the flagged ones.
    expect(screen.getByRole('radio', { name: 'All lines (3)' })).toBeInTheDocument();
    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();
  });

  it('gives the filter up rather than swallowing a jump to a healthy line', async () => {
    const { gridRef } = renderGrid(threeLines({ arithmetic_ok: false }));

    fireEvent.click(await screen.findByRole('radio', { name: /Need attention \(1\)/ }));
    expect(screen.queryByLabelText('Quantity on line 3')).toBeNull();

    // This is what a handwriting card naming a perfectly healthy line does.
    act(() => gridRef.current?.focusLine('l3'));

    expect(onFocusLine).toHaveBeenCalledWith(expect.objectContaining({ line_no: 3 }));
    expect(screen.getByLabelText('Quantity on line 3')).toBeInTheDocument();
    expect(
      screen.getByRole('radio', { name: /Need attention \(1\)/ }),
    ).toHaveAttribute('aria-checked', 'false');
  });

  it('counts a line flagged only by an unreviewed note as identified (S7, judgment b)', async () => {
    renderGrid(threeLines(), {
      annotations: [annotation({ id: 'a1', refers_to_lines: [2] })],
    });

    expect(
      await screen.findByRole('radio', { name: 'Need attention (1)' }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: 'Need attention (1)' }));

    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();
    expect(screen.queryByLabelText('Quantity on line 1')).toBeNull();
    expect(screen.queryByLabelText('Quantity on line 3')).toBeNull();
  });

  it('stays on Need attention when the header sends the reader to a note-only line (N1)', async () => {
    const { gridRef } = renderGrid(threeLines(), {
      annotations: [annotation({ id: 'a1', refers_to_lines: [2] })],
      defaultFlaggedOnly: true,
    });

    expect(
      await screen.findByRole('radio', { name: 'Need attention (1)' }),
    ).toHaveAttribute('aria-checked', 'true');

    act(() => {
      gridRef.current?.focusFirstUnreviewedAnnotation();
    });

    expect(
      screen.getByRole('radio', { name: 'Need attention (1)' }),
    ).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText('Quantity on line 2')).toBeInTheDocument();
    // Owner hand test 25 Sep 2026, item 2: "Review them" opens the note's popover directly,
    // rather than only scrolling to a row the reader still has to click themselves.
    expect(
      await screen.findByRole('button', { name: 'Accept the note on line 2' }),
    ).toBeInTheDocument();
  });

  it('states the flagged state once, as the two chips only, never a health sentence or handwriting strip (N3, R22)', async () => {
    renderGrid(
      [
        line({ id: 'l1', line_no: 1, arithmetic_ok: false }),
        line({ id: 'l2', line_no: 2, is_cancelled: true }),
        line({ id: 'l3', line_no: 3 }),
      ],
      { annotations: [annotation({ id: 'a1', refers_to_lines: [3] })] },
    );

    await screen.findByRole('radio', { name: /Need attention/ });

    expect(
      screen.queryByText(/lines? need attention|add up and resolve|with handwriting to review/i),
    ).toBeNull();
    expect(screen.queryByRole('button', { name: 'Next unreviewed' })).toBeNull();
  });
});

/**
 * Owner hand test, 25 Sep 2026, item 2: the always-expanded note cards under a flagged line
 * ("looks messy and bulky like so many expanded sections") are gone. A line's handwritten
 * notes are now one compact indicator in the Flag cell - an icon and a count - and clicking it
 * opens a popover with the same three actions the card used to offer. Row height stays the
 * grid's ordinary one line whether a line carries zero notes or several.
 */
describe('POIntakeLinesGrid, handwriting reviewed from a compact indicator (owner hand test 25 Sep 2026, item 2)', () => {
  it('marks the line with a compact indicator, not an always-open card', async () => {
    renderGrid(threeLines(), {
      annotations: [annotation({ refers_to_lines: [2], id: 'a1' })],
    });

    const indicator = await screen.findByRole('button', {
      name: '1 note to review on line 2',
    });
    expect(indicator).toBeInTheDocument();
    // Collapsed by default: nothing about the note is on screen until it is clicked.
    expect(screen.queryByText('Cancel line')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Accept the note on line 2' })).toBeNull();
    // No indicator at all on the two lines nothing was written about.
    expect(screen.queryByRole('button', { name: /note.*on line 1/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /note.*on line 3/ })).toBeNull();
  });

  it('opens the note and its three actions in a popover on click', async () => {
    const user = userEvent.setup();
    renderGrid(threeLines(), {
      annotations: [annotation({ refers_to_lines: [2], id: 'a1' })],
    });

    await user.click(
      await screen.findByRole('button', { name: '1 note to review on line 2' }),
    );

    expect(
      await screen.findByRole('button', { name: 'Accept the note on line 2' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Cancel line')).toBeInTheDocument();
    expect(
      screen.getByText('cancel this, refer to new P/O HQ/26/05/087'),
    ).toBeInTheDocument();
    expect(screen.getByText('15/5/26')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Edit the note on line 2' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Reject the note on line 2' }),
    ).toBeInTheDocument();
  });

  it('accepts through the confirm step, then moves focus to the next unreviewed line', async () => {
    const user = userEvent.setup();
    const { rerenderWith } = renderGrid(threeLines(), {
      annotations: [
        annotation({ id: 'a1', refers_to_lines: [1] }),
        annotation({ id: 'a2', refers_to_lines: [2], interpretation: 'other' }),
      ],
    });

    await user.click(
      await screen.findByRole('button', { name: '1 note to review on line 1' }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Accept the note on line 1' }),
    );
    fireEvent.click(screen.getByRole('button', { name: /Accept and cancel/i }));
    expect(onAcceptAnnotation).toHaveBeenCalledWith('a1');

    // The parent applies the mutation and hands back fresh data: line 1's note is gone.
    rerenderWith(threeLines(), {
      annotations: [
        annotation({ id: 'a1', refers_to_lines: [1], state: 'accepted' }),
        annotation({ id: 'a2', refers_to_lines: [2], interpretation: 'other' }),
      ],
    });

    expect(onFocusLine).toHaveBeenCalledWith(expect.objectContaining({ line_no: 2 }));
    // The line just resolved has nothing left to show, so its own popover does not linger
    // open behind the scroll to the next one.
    expect(screen.queryByRole('button', { name: 'Accept the note on line 1' })).toBeNull();
  });

  it('shows a note naming several lines on each of them, and clears it everywhere', async () => {
    const user = userEvent.setup();
    const { rerenderWith } = renderGrid(threeLines(), {
      annotations: [annotation({ id: 'a1', refers_to_lines: [1, 2] })],
    });

    expect(
      await screen.findByRole('button', { name: '1 note to review on line 1' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '1 note to review on line 2' }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '1 note to review on line 1' }));
    expect(
      screen.getByRole('button', { name: 'Accept the note on line 1' }),
    ).toBeInTheDocument();

    rerenderWith(threeLines(), {
      annotations: [annotation({ id: 'a1', refers_to_lines: [1, 2], state: 'accepted' })],
    });

    // Resolved everywhere it was named: neither line carries an indicator any more.
    expect(screen.queryByRole('button', { name: /note.*on line 1/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /note.*on line 2/ })).toBeNull();
  });

  it('reads an accepted note back in the popover, muted and with no actions', async () => {
    const user = userEvent.setup();
    renderGrid(threeLines(), {
      readOnly: true,
      annotations: [
        annotation({
          id: 'a1',
          refers_to_lines: [1],
          state: 'accepted',
          interpretation: 'other',
        }),
      ],
    });

    await user.click(await screen.findByRole('button', { name: '1 note on line 1' }));
    expect(screen.getByText('Something else')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Accept/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Reject/ })).toBeNull();
  });

  it('reads a rejected note back in the popover, muted and with no actions', async () => {
    const user = userEvent.setup();
    renderGrid(threeLines(), {
      readOnly: true,
      annotations: [annotation({ id: 'a2', refers_to_lines: [2], state: 'rejected' })],
    });

    await user.click(await screen.findByRole('button', { name: '1 note on line 2' }));
    expect(screen.getByText('Rejected: Cancel line')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Accept/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Reject/ })).toBeNull();
  });

  it('says nothing about handwriting when the document carries none', async () => {
    renderGrid(threeLines());

    await screen.findByLabelText('Quantity on line 1');
    expect(screen.queryByRole('button', { name: /note.*on line/ })).toBeNull();
  });

  it('shows a still-pending note as a muted indicator in read-only, not hidden', async () => {
    const user = userEvent.setup();
    renderGrid(threeLines(), {
      readOnly: true,
      annotations: [annotation({ id: 'a1', refers_to_lines: [2] })],
    });

    const indicator = await screen.findByRole('button', {
      name: '1 note to review on line 2',
    });
    await user.click(indicator);

    expect(screen.getByText('Cancel line')).toBeInTheDocument();
    // No action panel: a viewer without edit rights has nothing to click here.
    expect(screen.queryByRole('button', { name: /^Accept/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Reject/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Edit/ })).toBeNull();
  });
});
