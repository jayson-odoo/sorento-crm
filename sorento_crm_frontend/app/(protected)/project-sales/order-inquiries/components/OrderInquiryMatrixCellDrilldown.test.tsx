/**
 * SF-2: the cell drilldown must ask the list for EXACTLY this cell's axis + axis_key,
 * and must keep the user's own `query` rather than overwriting it. Today the component
 * sets `params.query = cell.axis_label`, which stomps the filters' own `query` and asks
 * a fuzzy text match rather than the row's exact axis value - two rows sharing a display
 * label (or a label containing punctuation `ILIKE` reads as a wildcard) drill down to
 * each other's rows.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderInquiryMatrixCellDrilldown } from './OrderInquiryMatrixCellDrilldown';
import type { OrderInquiryMatrixCell } from '../../_shared/types/orderInquiry.types';

const useOrderInquiryWorklist = vi.fn();
vi.mock('../../_shared/hooks/useOrderInquiry', () => ({
  useOrderInquiryWorklist: (...args: unknown[]) => useOrderInquiryWorklist(...args),
}));

// Under jsdom nothing answers the preferences fetch, so the grid renders skeletons for
// ever and none of its own text is assertable (same note as OrderInquiriesClient.test.tsx).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

function renderDialog(element: React.ReactElement) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>{element}</QueryClientProvider>,
  );
}

function cell(over: Partial<OrderInquiryMatrixCell> = {}): OrderInquiryMatrixCell {
  return {
    axis_key: 'product-uuid-123',
    axis_label: 'SRTWC8605-SC-RL',
    period: '2026-04-13',
    qty: '18',
    buy: '10',
    po: '8',
    spo: '0',
    rows: 2,
    ...over,
  };
}

beforeEach(() => {
  useOrderInquiryWorklist.mockReset();
  useOrderInquiryWorklist.mockReturnValue({
    data: { data: [], total: 0 },
    isLoading: false,
  });
});

describe('OrderInquiryMatrixCellDrilldown (SF-2)', () => {
  it('asks the list with the cells own axis + axis_key, not a text match on axis_label', () => {
    renderDialog(
      <OrderInquiryMatrixCellDrilldown
        cell={cell()}
        granularity="week"
        filters={{ supplier_id: 'sup-1' }}
        rowLabel="SRTWC8605-SC-RL"
        bucketLabel="13 Apr 2026"
        onClose={vi.fn()}
      />,
    );

    const [params] = useOrderInquiryWorklist.mock.calls[0];
    expect(params.axis).toBe('product');
    expect(params.axis_key).toBe('product-uuid-123');
  });

  it('keeps the callers own query rather than overwriting it with axis_label', () => {
    renderDialog(
      <OrderInquiryMatrixCellDrilldown
        cell={cell()}
        granularity="week"
        filters={{ query: 'brown basin' }}
        rowLabel="SRTWC8605-SC-RL"
        bucketLabel="13 Apr 2026"
        onClose={vi.fn()}
      />,
    );

    const [params] = useOrderInquiryWorklist.mock.calls[0];
    expect(params.query).toBe('brown basin');
  });

  it('still narrows to the buckets own delivery range', () => {
    renderDialog(
      <OrderInquiryMatrixCellDrilldown
        cell={cell({ period: '2026-04-13' })}
        granularity="week"
        filters={{}}
        rowLabel="SRTWC8605-SC-RL"
        bucketLabel="13 Apr 2026"
        onClose={vi.fn()}
      />,
    );

    const [params] = useOrderInquiryWorklist.mock.calls[0];
    expect(params.delivery_from).toBe('2026-04-13');
    expect(params.delivery_to).toBe('2026-04-19');
  });
});
