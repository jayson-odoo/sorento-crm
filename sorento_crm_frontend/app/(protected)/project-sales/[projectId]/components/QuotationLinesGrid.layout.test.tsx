/**
 * PROPOSAL-FORM-COLLAPSE, Q3 (owner, 10 Nov 2026): the quotation table's column layout is the
 * reader's own (per user, the DataGrid precedent) and ONE setting for edit and view, plain and
 * grid scopes alike: the same listing key everywhere, fixed columns dragged the DataGrid way, and
 * the quantity block kept together where the reader put it.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Table } from '@tanstack/react-table';
import type {
  QuotationFeedbackRow,
  QuotationLine,
  StagedQuotationLine,
} from '../../_shared/types/project.types';
import type { MatrixHeader } from '../../_shared/lib/quotationMatrix';
import { serverToDraft } from './quotationLineDraft';

/** What the per-user preference hook was asked for, and the saved order it "applies". */
const prefs: { keys: (string | null | undefined)[]; saved: string[] | null } = { keys: [], saved: null };
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', async () => {
  const ReactModule = await import('react');
  return {
    useListingColumnPreferences: ({ table, listingKey }: { table: Table<unknown>; listingKey?: string | null }) => {
      prefs.keys.push(listingKey);
      ReactModule.useEffect(() => {
        if (prefs.saved) table.setColumnOrder(prefs.saved);
      }, [table]);
      return { resetToDefaults: async () => {}, isLoading: false, isFetching: false };
    },
  };
});

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

import { QuotationLinesGrid, type QuotationLinesMatrix } from './QuotationLinesGrid';

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


const KEY = 'projects.projects.view::quotation-lines';

function headerTexts(): string[] {
  return screen
    .getAllByRole('columnheader')
    .map((th) => (th.textContent ?? '').trim())
    .filter(Boolean);
}

const GROUPS: MatrixHeader[] = [
  { key: 'a', label: 'Type A', cols: [{ key: 'a-bh', label: '1 BH' }, { key: 'a-bal', label: 'Balcony' }] },
];

const LINE: QuotationLine = {
  id: 'l1',
  version_id: 'v1',
  product_id: 'p1',
  product_code: 'FT100-SS',
  description: 'Floor trap',
  unit_price: '45.00',
  quantity: '2.00',
  uom: 'PCS',
  line_total: '90.00',
  is_non_standard: false,
  is_below_floor: false,
  sort_order: 0,
  qty_cells: { 'a-bh': '1.00', 'a-bal': '1.00' },
};

function stagedLine(withCells: boolean): StagedQuotationLine {
  return { id: 'l1', key: 'l1', line: LINE, draft: serverToDraft(LINE, withCells), removed: false };
}

// A plain scope's saved order with Rate dragged in front of Description.
const SAVED = [
  'drag_handle', 'item_no', 'photo', 'drawing', 'product', 'rate', 'description', 'brand',
  'qty', 'uom', 'qty_block', 'total', 'row_actions',
];

beforeEach(() => {
  prefs.keys = [];
  prefs.saved = null;
});

describe('one column layout for edit and view, plain and grid scopes', () => {
  it('asks for the same per-user setting on a grid scope as on a plain one, editing or reading', () => {
    const { unmount } = renderGrid({ lines: [stagedLine(false)] });
    unmount();
    const second = renderGrid({ lines: [stagedLine(true)], matrix: { columns: GROUPS } });
    second.unmount();
    renderGrid({ lines: [stagedLine(true)], editing: true, matrix: { columns: GROUPS, onChange: vi.fn() } });
    expect(new Set(prefs.keys)).toEqual(new Set([KEY]));
  });

  it('lays a grid scope out by the saved order, the quantity block kept together at its place', async () => {
    prefs.saved = SAVED;
    renderGrid({ lines: [stagedLine(true)], matrix: { columns: GROUPS } });
    const texts = headerTexts();
    expect(texts.indexOf('Rate (RM)')).toBeLessThan(texts.indexOf('Description'));
    // The block sits where the plain scope's quantity sat (after UOM), together.
    const uom = texts.indexOf('UOM');
    expect(texts.indexOf('Type A')).toBeGreaterThan(uom);
    expect(texts.indexOf('Total qty')).toBeGreaterThan(texts.indexOf('Type A'));
    expect(texts.indexOf('Amount (RM)')).toBeGreaterThan(texts.indexOf('Total qty'));
  });

  it('reads and edits in the same order', () => {
    prefs.saved = SAVED;
    const read = renderGrid({ lines: [stagedLine(true)], matrix: { columns: GROUPS } });
    const readOrder = headerTexts().filter((text) => ['Product', 'Rate (RM)', 'Description', 'UOM', 'Total qty', 'Amount (RM)'].includes(text));
    read.unmount();
    renderGrid({ lines: [stagedLine(true)], editing: true, matrix: { columns: GROUPS, onChange: vi.fn() } });
    const editOrder = headerTexts().filter((text) => ['Product', 'Rate (RM)', 'Description', 'UOM', 'Total qty', 'Amount (RM)'].includes(text));
    expect(editOrder).toEqual(readOrder);
    expect(readOrder).toEqual(['Product', 'Rate (RM)', 'Description', 'UOM', 'Total qty', 'Amount (RM)']);
  });

  it('drags the fixed columns of a grid scope the DataGrid way', () => {
    renderGrid({ lines: [stagedLine(true)], editing: true, matrix: { columns: GROUPS, onChange: vi.fn() } });
    const description = screen.getByRole('columnheader', { name: 'Description' });
    expect(description.querySelector('.cursor-grab')).not.toBeNull();
    // One header cell per fixed column, spanning both header rows: no empty placeholder above it.
    expect(description).toHaveAttribute('rowspan', '2');
  });
});
