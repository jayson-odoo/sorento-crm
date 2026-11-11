/**
 * NON-CANCELLABLE-ITEMS: a line the server flags `is_non_cancellable` reads "Non-cancellable" in
 * the Remark column; an unflagged line leaves the cell blank. Values invented.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { QuotationLine, StagedQuotationLine } from '../../_shared/types/project.types';
import { serverToDraft } from './quotationLineDraft';

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
vi.mock('@/hooks/useDeferredDeleteSeconds', () => ({ useDeferredDeleteSeconds: () => 10 }));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { QuotationLinesGrid } from './QuotationLinesGrid';

const BASE: QuotationLine = {
  id: 'l1',
  version_id: 'v1',
  product_id: 'p1',
  product_code: 'ZZT8518',
  description: 'BATHTUB',
  unit_price: '45.00',
  quantity: '2.00',
  uom: 'PCS',
  line_total: '90.00',
  is_non_standard: false,
  is_below_floor: false,
  sort_order: 0,
};

function staged(source: QuotationLine): StagedQuotationLine {
  return { id: source.id, key: source.id, line: source, draft: serverToDraft(source, false), removed: false };
}

function renderGrid(lines: StagedQuotationLine[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <QuotationLinesGrid
        lines={lines}
        editing={false}
        quotationId="q1"
        emptyHint="No lines yet."
        filterEmptyHint="No line matches."
        fetchProducts={async () => []}
        resolveProduct={() => undefined}
        productCodeOf={() => null}
        fillFromProduct={() => ({})}
        uomOptions={[]}
        uomError={null}
        onUomRetry={() => {}}
        brandOptions={[]}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('Remark column', () => {
  it('shows Non-cancellable for a flagged line', () => {
    renderGrid([staged({ ...BASE, is_non_cancellable: true })]);
    expect(screen.getByRole('columnheader', { name: 'Remark' })).toBeInTheDocument();
    expect(screen.getByText('Non-cancellable')).toBeInTheDocument();
  });

  it('leaves the cell blank for an unflagged line', () => {
    renderGrid([staged({ ...BASE, is_non_cancellable: false })]);
    expect(screen.queryByText('Non-cancellable')).toBeNull();
  });
});
