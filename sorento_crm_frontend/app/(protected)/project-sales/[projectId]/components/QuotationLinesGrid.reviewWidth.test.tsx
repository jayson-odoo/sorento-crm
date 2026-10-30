/**
 * QUOTE-CUSTOMER-AMEND fix round 2 (D3): in review, the row-actions column is wide enough for a
 * removal's badge over its Accept / Reject, and the Qty column for a decision pair, while the
 * defaults still fit the 893px the grid shows at 1280 with the sidebar open (browser pass). Without
 * a review the columns are as before. Values invented.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { QuotationLinesGrid } from './QuotationLinesGrid';

const LINE: QuotationLine = {
  id: 'l1',
  version_id: 'v1',
  product_id: 'p1',
  product_code: 'ZZT-SHW-5005',
  description: 'Shower head',
  unit_price: '25.00',
  quantity: '10.00',
  uom: 'PCS',
  line_total: '250.00',
  is_non_standard: false,
  is_below_floor: false,
  sort_order: 0,
};

function staged(source: QuotationLine): StagedQuotationLine {
  return { id: source.id, key: source.id, line: source, draft: serverToDraft(source), removed: false };
}

function widths(withReview: boolean): Record<string, number> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { unmount } = render(
    <QueryClientProvider client={client}>
      <QuotationLinesGrid
        lines={[staged(LINE)]}
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
        review={
          withReview
            ? {
                rows: [
                  {
                    id: 'r1',
                    line_id: 'l1',
                    field: 'remove',
                    value_from: null,
                    value_to: null,
                    decision: 'pending',
                    decision_reason: null,
                  },
                ],
                onDecide: vi.fn(),
              }
            : undefined
        }
      />
    </QueryClientProvider>,
  );
  const out: Record<string, number> = {};
  for (const th of screen.getAllByRole('columnheader')) {
    const name = (th.textContent ?? '').trim() || 'Row actions';
    out[name] = parseInt((th as HTMLElement).style.width, 10);
  }
  unmount();
  return out;
}

describe('QuotationLinesGrid review widths', () => {
  it('widens Row actions and Qty in review, and the visible columns still fit 893px', () => {
    const view = widths(false);
    const review = widths(true);
    expect(review['Row actions']).toBeGreaterThanOrEqual(56);
    expect(review['Qty']).toBeGreaterThan(view['Qty']);
    const sum = Object.values(review).reduce((total, width) => total + width, 0);
    expect(sum).toBeLessThanOrEqual(893);
    // The same columns in the same order, review or not.
    expect(Object.keys(review).filter((k) => k !== 'Row actions')).toEqual(Object.keys(view));
  });
});
