/**
 * CostPriceChangeSetDetail (#1305 reviewer pass, Lane A FE rows, S6): a Draft set with
 * stale lines needs a way to re-capture current costs. "Refresh costs" (round 6 R5: cost,
 * never price) renders in the
 * header action area only when `actions.can_refresh_prices` is true, and calls the
 * refresh mutation.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { CostPriceChangeSetDetail as CostPriceChangeSetDetailType } from '../../types/costPrice.types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/cost-price-uploads/set-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({ countdown: null, start: vi.fn() }),
}));

vi.mock('../../services/costPriceService', () => ({
  downloadCostPriceSourceFile: vi.fn(),
}));

vi.mock('./CostPriceHistoryTab', () => ({
  CostPriceHistoryTab: () => <div data-testid="history-stub" />,
}));
vi.mock('./CostPriceLinesTab', () => ({
  CostPriceLinesTab: () => <div data-testid="lines-stub" />,
}));

const refreshMutateAsync = vi.fn().mockResolvedValue(undefined);
let detail: CostPriceChangeSetDetailType;
vi.mock('../../hooks/useCostPriceChangeSets', () => ({
  useCostPriceChangeSet: () => ({ data: detail, isLoading: false }),
  useRefreshCostPricePrices: () => ({ mutateAsync: refreshMutateAsync, isPending: false }),
  useApplyCostPriceChangeSet: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSubmitCostPriceChangeSet: () => ({ mutateAsync: vi.fn(), isPending: false }),
  costPriceChangeSetsPagerQuery: {
    listQueryKey: () => ['cost-price-change-sets-pager'],
    fetchPage: async () => ({ ids: ['set-1'], hasNextPage: false }),
  },
}));

import { CostPriceChangeSetDetail } from './CostPriceChangeSetDetail';

function makeDetail(overrides: Partial<CostPriceChangeSetDetailType> = {}): CostPriceChangeSetDetailType {
  return {
    id: 'set-1',
    code: 'CPC-0001',
    status: 'draft',
    channel: 'staff_upload',
    supplier: { id: 'sup-1', supplier_code: 'ZZT-S', supplier_name: 'A Supplier' },
    currency: 'CNY',
    start_date: null,
    end_date: null,
    file_name: 'list.xlsx',
    has_source_file: true,
    sheets: [{ name: '19 series', header_row: 6, rows: 1, skipped_reason: null }],
    total_rows: 1,
    uploaded_by_name: 'Mei Ling',
    created_at: '2026-09-27T00:00:00',
    submitted_by_name: null,
    submitted_at: null,
    returned_reason: null,
    returned_by_name: null,
    returned_at: null,
    applied_by_name: null,
    applied_at: null,
    verified: null,
    verification_enabled: false,
    counts: {
      changed: 0, unchanged: 0, new_link: 0, unmatched: 0, duplicate_code: 0,
      needs_attention: 0, skipped: 0, accepted: 0, rejected: 0, undecided: 0,
    },
    largest_rise: null,
    actions: {
      can_apply: true, apply_blocked_reason: null, apply_count: 0,
      can_submit: false, can_decide: false, can_return: false, can_discard: true,
      decide_blocked_reason: null, can_refresh_prices: false,
    },
    ...overrides,
  };
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CostPriceChangeSetDetail changeSetId="set-1" />
    </QueryClientProvider>,
  );
}

describe('S6: Refresh prices renders only when can_refresh_prices is true', () => {
  it('renders no Refresh costs button when can_refresh_prices is false', () => {
    detail = makeDetail();
    renderDetail();

    expect(screen.queryByRole('button', { name: 'Refresh costs' })).not.toBeInTheDocument();
  });

  it('renders Refresh costs and calls the mutation when can_refresh_prices is true', () => {
    detail = makeDetail({
      actions: {
        can_apply: true, apply_blocked_reason: null, apply_count: 0,
        can_submit: false, can_decide: false, can_return: false, can_discard: true,
        decide_blocked_reason: null, can_refresh_prices: true,
      },
    });
    renderDetail();

    const button = screen.getByRole('button', { name: 'Refresh costs' });
    fireEvent.click(button);

    expect(refreshMutateAsync).toHaveBeenCalled();
  });
});
