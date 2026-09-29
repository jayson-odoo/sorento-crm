/**
 * CostPriceChangeSetDetail (#1305 reviewer pass, Lane A FE rows, Nit 7): "A second Sorento
 * person decides each line before anything changes." is a feature explanation, not a label
 * or a field name - the cursor rule bars it from the UI itself. It moved to
 * `documentation/user-guides/procurement/cost-price-from-supplier.md`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
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

let detail: CostPriceChangeSetDetailType;
vi.mock('../../hooks/useCostPriceChangeSets', () => ({
  useCostPriceChangeSet: () => ({ data: detail, isLoading: false }),
  useRefreshCostPricePrices: () => ({ mutateAsync: vi.fn(), isPending: false }),
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
    code: 'CPC-0002',
    status: 'pending_verification',
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
    submitted_by_name: 'Mei Ling',
    submitted_at: '2026-09-27T00:05:00',
    returned_reason: null,
    returned_by_name: null,
    returned_at: null,
    applied_by_name: null,
    applied_at: null,
    verified: null,
    verification_enabled: true,
    counts: {
      changed: 0, unchanged: 0, new_link: 0, unmatched: 0, duplicate_code: 0,
      needs_attention: 0, skipped: 0, accepted: 0, rejected: 0, undecided: 0,
    },
    largest_rise: null,
    actions: {
      can_apply: false, apply_blocked_reason: null, apply_count: 0,
      can_submit: false, can_decide: true, can_return: true, can_discard: false,
      decide_blocked_reason: null,
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

describe('Nit 7: no feature explanation inside the UI', () => {
  it('renders no "A second Sorento person decides" sentence on a Pending set', () => {
    detail = makeDetail();
    renderDetail();

    expect(screen.queryByText(/A second Sorento person decides each line before anything changes\./)).not.toBeInTheDocument();
  });
});
