/**
 * PS-QUOTE-MATRIX: the Lines grid on a scope with column headers (mock v3 frames 1, 2 and 5).
 * Every existing column stays; the single Qty column becomes grouped quantity columns with a
 * Qty / RM pair per header, Total qty and Amount, two footer lines; on an editable version the
 * header itself is the column editor. A scope with no columns is today's grid. Values invented
 * (card example E1).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '@/lib/toast';
import type {
  QuotationFeedbackRow,
  QuotationLine,
  StagedQuotationLine,
} from '../../_shared/types/project.types';
import type { MatrixHeader } from '../../_shared/lib/quotationMatrix';
import { draftCells, serverToDraft, toBody } from './quotationLineDraft';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/hooks/useProjects')>();
  return {
    ...actual,
    useQuotationLineImages: () => ({ data: undefined, isLoading: false, isError: false }),
    useProductSetLineRef: () => ({ data: undefined, isLoading: false, isError: false }),
  };
});
vi.mock('./QuotationStockChip', () => ({ QuotationStockChip: () => null, SetStockChip: () => null }));
vi.mock('./QuotationLineFlags', () => ({
  LineFlags: () => null,
  MinimumPriceBadge: () => null,
  MinimumPriceFlag: () => null,
}));
// The hard-delete window from System Settings (deferred_delete_seconds), per test.
const settings = { deleteSeconds: 10 };
vi.mock('@/hooks/useDeferredDeleteSeconds', () => ({
  useDeferredDeleteSeconds: () => settings.deleteSeconds,
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { COLUMN_REMOVAL_MS, QuotationLinesGrid, type QuotationLinesMatrix } from './QuotationLinesGrid';

function col(key: string, label: string) {
  return { key, label };
}

const UNIT: MatrixHeader[] = [
  { key: 'a', label: 'Type A - 1 BH', cols: [col('a-bh', '1 BH'), col('a-bal', 'Balcony')] },
  { key: 'b', label: 'Type B - 2 BH', cols: [col('b-bh', '2 BH'), col('b-bal', 'Balcony')] },
  { key: 'c', label: 'Type C - 3 BH', cols: [col('c-bh', '3 BH'), col('c-bal', 'Balcony')] },
];

const TRAP: QuotationLine = {
  id: 'l1',
  version_id: 'v1',
  product_id: 'p1',
  product_code: 'FT100-SS',
  description: 'Floor trap 100mm',
  unit_price: '45.00',
  quantity: '1522.00',
  uom: 'PCS',
  line_total: '68490.00',
  is_non_standard: false,
  is_below_floor: false,
  sort_order: 0,
  qty_cells: {
    'a-bh': '120.00',
    'a-bal': '120.00',
    'b-bh': '500.00',
    'b-bal': '250.00',
    'c-bh': '399.00',
    'c-bal': '133.00',
  },
};

const WC: QuotationLine = {
  ...TRAP,
  id: 'l2',
  product_code: 'WC8518-SH',
  description: 'One-piece WC',
  unit_price: '520.00',
  quantity: '120.00',
  line_total: '62400.00',
  sort_order: 1,
  qty_cells: { 'a-bh': '120.00' },
};

function staged(source: QuotationLine, withCells: boolean): StagedQuotationLine {
  return {
    id: source.id,
    key: source.id,
    line: source,
    draft: serverToDraft(source, withCells),
    removed: false,
  };
}

function renderGrid({
  lines,
  editing = false,
  matrix,
  feedback,
  onStage = vi.fn(),
}: {
  lines: StagedQuotationLine[];
  editing?: boolean;
  matrix?: QuotationLinesMatrix;
  feedback?: QuotationFeedbackRow[];
  onStage?: (lines: StagedQuotationLine[]) => void;
}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const props = {
    editing,
    quotationId: 'q1',
    emptyHint: 'No lines yet.',
    filterEmptyHint: 'No line matches.',
    fetchProducts: async () => [],
    resolveProduct: () => undefined,
    productCodeOf: () => null,
    fillFromProduct: () => ({}),
    uomOptions: [],
    uomError: null,
    onUomRetry: () => {},
    brandOptions: [],
    onStage: editing ? onStage : undefined,
    onToggleRemoved: editing ? vi.fn() : undefined,
    matrix,
    feedback,
  };
  const view = render(
    <QueryClientProvider client={client}>
      <QuotationLinesGrid lines={lines} {...props} />
    </QueryClientProvider>,
  );
  return {
    ...view,
      rerenderWith: (next: {
      lines?: StagedQuotationLine[];
      matrix?: QuotationLinesMatrix;
      editing?: boolean;
    }) =>
      view.rerender(
        <QueryClientProvider client={client}>
          <QuotationLinesGrid
            lines={next.lines ?? lines}
            {...props}
            editing={next.editing ?? editing}
            matrix={next.matrix ?? matrix}
          />
        </QueryClientProvider>,
      ),
  };
}

function headerTexts(): string[] {
  return screen.getAllByRole('columnheader').map((th) => (th.textContent ?? '').trim());
}

/** The last staged set the grid handed up. */
function lastStaged(onStage: ReturnType<typeof vi.fn>): StagedQuotationLine[] {
  return onStage.mock.calls.at(-1)?.[0] as StagedQuotationLine[];
}

afterEach(() => {
  vi.useRealTimers();
});

beforeEach(() => {
  vi.clearAllMocks();
  settings.deleteSeconds = 10;
});

describe('a scope with no columns (AC-1)', () => {
  it('draws exactly today\'s columns, with or without an empty matrix', () => {
    const { unmount } = renderGrid({ lines: [staged(TRAP, false)] });
    const before = headerTexts();
    unmount();
    renderGrid({ lines: [staged(TRAP, false)], matrix: { columns: [] } });
    expect(headerTexts()).toEqual(before);
    expect(before).toContain('Qty');
    expect(before).not.toContain('Total qty');
  });

  it('sends no qty_cells for a plain line, and the grid line\'s cells for a grid line', () => {
    expect(toBody(serverToDraft(TRAP), TRAP)).not.toHaveProperty('qty_cells');
    const body = toBody(serverToDraft(TRAP, true), TRAP);
    expect(body.qty_cells).toEqual(TRAP.qty_cells);
    expect(body.quantity).toBe('1522.00');
  });
});

describe('a scope with columns, read (mock frame 1)', () => {
  it('keeps every product column, replaces Qty with grouped columns, pairs and totals', () => {
    renderGrid({ lines: [staged(TRAP, true), staged(WC, true)], matrix: { columns: UNIT } });
    const headers = headerTexts();
    for (const kept of ['#', 'Photo', 'Drawing', 'Product', 'Description', 'Brand', 'UOM', 'Rate (RM)']) {
      expect(headers).toContain(kept);
    }
    expect(headers).not.toContain('Qty (RM)');
    expect(headers).toEqual(
      expect.arrayContaining(['Type A - 1 BH', '1 BH', 'Balcony', 'Qty', 'RM', 'Total qty', 'Amount (RM)']),
    );
    // The 2-row header: a column header spans its columns and its pair.
    const typeA = screen.getByRole('columnheader', { name: 'Type A - 1 BH' });
    expect(typeA).toHaveAttribute('colspan', '4');
    // An ungrouped product column spans both header rows.
    expect(screen.getByRole('columnheader', { name: 'Description' })).toHaveAttribute('rowspan', '2');

    const trap = screen.getByText('Floor trap 100mm').closest('tr') as HTMLElement;
    const cells = within(trap).getAllByRole('cell').map((td) => (td.textContent ?? '').trim());
    // E1: Type A 240 / 10,800.00; Type B 750 / 33,750.00; Type C 532 / 23,940.00; 1,522; 68,490.00.
    expect(cells).toEqual(
      expect.arrayContaining(['240', '10,800.00', '750', '33,750.00', '532', '23,940.00', '1,522']),
    );
    expect(within(trap).getByText('RM 68,490.00')).toBeInTheDocument();
  });

  it('prints - for a header pair with no quantity, and two footer lines', () => {
    renderGrid({ lines: [staged(TRAP, true), staged(WC, true)], matrix: { columns: UNIT } });
    const wc = screen.getByText('One-piece WC').closest('tr') as HTMLElement;
    expect(within(wc).getAllByText('-').length).toBeGreaterThanOrEqual(4);

    const foot = document.querySelector('tfoot') as HTMLElement;
    expect(within(foot).getByText('Total qty')).toBeInTheDocument();
    expect(within(foot).getByText('Total (RM)')).toBeInTheDocument();
    // Type A 1 BH: 120 + 120 = 240; Type A pair RM: 10,800 + 62,400 = 73,200; overall qty 1,642.
    expect(within(foot).getByText('73,200.00')).toBeInTheDocument();
    expect(within(foot).getByText('1,642')).toBeInTheDocument();
    // Scope total 68,490 + 62,400.
    expect(within(foot).getByText('130,890.00')).toBeInTheDocument();
  });

  it('marks open feedback: an amber corner on its cell, a dot on its item (mock frame 5)', () => {
    const note = (overrides: Partial<QuotationFeedbackRow>): QuotationFeedbackRow => ({
      id: 'f1',
      line_id: 'l1',
      scope_label: 'UNIT',
      line_description: 'Floor trap 100mm',
      cell_key: null,
      cell_label: null,
      kind: 'note',
      value_from: null,
      value_to: null,
      model: null,
      note: 'Check this',
      handled_at: null,
      handled_by_name: null,
      ...overrides,
    });
    renderGrid({
      lines: [staged(TRAP, true), staged(WC, true)],
      matrix: { columns: UNIT },
      feedback: [
        note({ id: 'f1', cell_key: 'c-bal' }),
        note({ id: 'f2', line_id: 'l2' }),
        note({ id: 'f3', line_id: 'l2', cell_key: 'a-bh', handled_at: '2026-11-02T10:00:00' }),
      ],
    });
    expect(screen.getAllByTestId('matrix-feedback-corner')).toHaveLength(1);
    expect(screen.getAllByTestId('line-feedback-dot')).toHaveLength(1);
    const wc = screen.getByText('One-piece WC').closest('tr') as HTMLElement;
    expect(within(wc).getByTestId('line-feedback-dot')).toBeInTheDocument();
  });

  it('offers no header editing on a read', () => {
    renderGrid({ lines: [staged(TRAP, true)], matrix: { columns: UNIT, onChange: vi.fn() } });
    expect(screen.queryByRole('textbox', { name: /Column header/ })).toBeNull();
    expect(screen.queryByRole('button', { name: '+ Column header' })).toBeNull();
  });
});

describe('a scope with columns, editing (mock frame 2)', () => {
  it('types a quantity into a cell: the line\'s quantity is the sum of its cells', () => {
    const onStage = vi.fn();
    renderGrid({ lines: [staged(TRAP, true)], editing: true, matrix: { columns: UNIT }, onStage });
    const input = screen.getByRole('textbox', { name: 'Qty on FT100-SS, Type C - 3 BH / Balcony' });
    fireEvent.change(input, { target: { value: '140' } });

    const [line] = lastStaged(onStage);
    expect(draftCells(line.draft)?.['c-bal']).toBe('140');
    expect(line.draft.quantity).toBe('1529.00');
  });

  it('pastes a block from Excel right and down, and refuses a non-number with one message', () => {
    const onStage = vi.fn();
    renderGrid({
      lines: [staged(TRAP, true), staged(WC, true)],
      editing: true,
      matrix: { columns: UNIT },
      onStage,
    });
    const start = screen.getByRole('textbox', { name: 'Qty on FT100-SS, Type A - 1 BH / Balcony' });
    fireEvent.paste(start, { clipboardData: { getData: () => '7\t-\n8\t9\n' } });

    const [trap, wc] = lastStaged(onStage);
    expect(draftCells(trap.draft)).toMatchObject({ 'a-bal': '7' });
    expect(draftCells(trap.draft)).not.toHaveProperty('b-bh');
    expect(draftCells(wc.draft)).toMatchObject({ 'a-bal': '8', 'b-bh': '9' });
    expect(wc.draft.quantity).toBe('137.00');

    onStage.mockClear();
    fireEvent.paste(start, { clipboardData: { getData: () => '1\tabc\n' } });
    expect(onStage).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('"abc"'));
  });

  it('renames a header in place, on blur', () => {
    const onChange = vi.fn();
    renderGrid({ lines: [staged(TRAP, true)], editing: true, matrix: { columns: UNIT, onChange } });
    const label = screen.getByRole('textbox', { name: 'Column header Type B - 2 BH' });
    fireEvent.change(label, { target: { value: 'Type B - 2 BR' } });
    fireEvent.blur(label);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0][1]).toMatchObject({ key: 'b', label: 'Type B - 2 BR' });
  });

  it('adds a column under a header, and a header at the end', () => {
    const onChange = vi.fn();
    renderGrid({ lines: [staged(TRAP, true)], editing: true, matrix: { columns: UNIT, onChange } });
    fireEvent.click(screen.getByRole('button', { name: 'Add a column under Type A - 1 BH' }));
    expect(onChange.mock.calls[0][0][0].cols).toHaveLength(3);
    fireEvent.click(screen.getByRole('button', { name: '+ Column header' }));
    expect(onChange.mock.calls[1][0]).toHaveLength(4);
  });

  it('moves a header with the arrow keys on its grip', () => {
    const onChange = vi.fn();
    renderGrid({ lines: [staged(TRAP, true)], editing: true, matrix: { columns: UNIT, onChange } });
    fireEvent.keyDown(screen.getByRole('button', { name: 'Move Type B - 2 BH' }), { key: 'ArrowLeft' });
    expect(onChange.mock.calls[0][0].map((header: MatrixHeader) => header.key)).toEqual(['b', 'a', 'c']);
  });

  it('removes a header after a countdown in the header itself, and Undo keeps it', () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    renderGrid({ lines: [staged(TRAP, true)], editing: true, matrix: { columns: UNIT, onChange } });

    fireEvent.click(screen.getByRole('button', { name: 'Remove Type A - 1 BH' }));
    const countdown = screen.getByTestId('matrix-removal-countdown');
    expect(countdown).toHaveTextContent('Type A - 1 BH · removing in 10s');
    fireEvent.click(within(countdown).getByRole('button', { name: 'Undo removing Type A - 1 BH' }));
    act(() => {
      vi.advanceTimersByTime(COLUMN_REMOVAL_MS + 100);
    });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByTestId('matrix-removal-countdown')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Remove Type A - 1 BH' }));
    act(() => {
      vi.advanceTimersByTime(COLUMN_REMOVAL_MS + 100);
    });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].map((header: MatrixHeader) => header.key)).toEqual(['b', 'c']);
  });

  it('copies another scope\'s headers and columns from the toolbar menu', async () => {
    const onChange = vi.fn();
    renderGrid({
      lines: [staged(TRAP, true)],
      editing: true,
      matrix: {
        columns: UNIT,
        onChange,
        copySources: [
          { label: 'LEVEL 9', columns: [{ key: 'l9', label: 'Level 9', cols: [col('m', 'Surau M')] }] },
          { label: 'GUARD HOUSE', columns: [] },
        ],
      },
    });
    const trigger = screen.getByRole('button', { name: /Copy columns from/ });
    fireEvent.keyDown(trigger, { key: 'Enter' });
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByRole('menuitem', { name: 'GUARD HOUSE (none)' })).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'LEVEL 9' }));
    const next = onChange.mock.calls[0][0] as MatrixHeader[];
    expect(next.map((header) => header.label)).toEqual([
      'Type A - 1 BH',
      'Type B - 2 BH',
      'Type C - 3 BH',
      'Level 9',
    ]);
    expect(next[3].cols.map((item) => item.label)).toEqual(['Surau M']);
  });

  it('starts a grid on a scope with no columns from + Column header', () => {
    const onChange = vi.fn();
    renderGrid({ lines: [staged(TRAP, false)], editing: true, matrix: { columns: [], onChange } });
    expect(headerTexts()).toContain('Qty');
    fireEvent.click(screen.getByRole('button', { name: 'Column header' }));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toEqual([
      { key: expect.stringMatching(/^[a-z0-9][a-z0-9_-]{0,39}$/), label: 'Header 1', cols: [] },
    ]);
  });
});

describe('a parked column removal (fix round 1)', () => {
  it('counts down the hard-delete window System Settings holds', () => {
    vi.useFakeTimers();
    settings.deleteSeconds = 4;
    const onChange = vi.fn();
    renderGrid({ lines: [staged(TRAP, true)], editing: true, matrix: { columns: UNIT, onChange } });

    fireEvent.click(screen.getByRole('button', { name: 'Remove Type A - 1 BH' }));
    expect(screen.getByTestId('matrix-removal-countdown')).toHaveTextContent('removing in 4s');
    act(() => {
      vi.advanceTimersByTime(3_900);
    });
    expect(onChange).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('falls back to 10s when the setting has not answered', () => {
    expect(COLUMN_REMOVAL_MS).toBe(10_000);
  });

  it('commits at once when edit mode ends mid-countdown, and never shows it in view mode', () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    const view = renderGrid({ lines: [staged(TRAP, true)], editing: true, matrix: { columns: UNIT, onChange } });
    fireEvent.click(screen.getByRole('button', { name: 'Remove Type A - 1 BH' }));
    expect(onChange).not.toHaveBeenCalled();

    // The session ends (Save or Cancel): the read has no editor, so no handler of its own.
    view.rerenderWith({ editing: false, matrix: { columns: UNIT } });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0].map((header: MatrixHeader) => header.key)).toEqual(['b', 'c']);
    expect(screen.queryByTestId('matrix-removal-countdown')).toBeNull();
    act(() => {
      vi.advanceTimersByTime(COLUMN_REMOVAL_MS * 2);
    });
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('commits at once when the grid goes away mid-countdown (Save remounts it, a scope switch unmounts it)', () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    const view = renderGrid({ lines: [staged(TRAP, true)], editing: true, matrix: { columns: UNIT, onChange } });
    // Type C's Balcony column.
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove Balcony' })[2]);
    view.unmount();
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0][2].cols.map((item: { key: string }) => item.key)).toEqual(['c-bh']);
  });
});
