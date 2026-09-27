/**
 * CostPriceLinesTab (#1288, Lane A) - tester finding, singular copy on the sticky apply
 * bar: today it always reads "N changes ready" / "Apply N changes" even for `N === 1`
 * ("1 changes ready", "Apply 1 changes") - a plain string literal in the JSX with no
 * pluralisation.
 *
 * Mocked at the hook boundary, same technique as `CostPriceLinesTab.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { CostPriceChangeLine, CostPriceChangeSetDetail } from '../../types/costPrice.types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/cost-price-uploads/set-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ placeholder }: { placeholder?: string }) => (
    <div data-testid="searchable-select-stub">{placeholder}</div>
  ),
}));

const mutateAsync = vi.fn().mockResolvedValue(undefined);
const mutation = () => ({ mutateAsync, isPending: false });

let linesData: CostPriceChangeLine[] = [];
vi.mock('../../hooks/useCostPriceChangeSets', () => ({
  useCostPriceChangeLines: () => ({ data: { data: linesData } }),
  usePatchCostPriceChangeLine: () => mutation(),
  useDecideCostPriceLine: () => mutation(),
  useDecideAllCostPriceLines: () => mutation(),
  useSubmitCostPriceChangeSet: () => mutation(),
  useReturnCostPriceChangeSet: () => mutation(),
  useApplyCostPriceChangeSet: () => mutation(),
}));

import { CostPriceLinesTab } from './CostPriceLinesTab';

function line(overrides: Partial<CostPriceChangeLine> = {}): CostPriceChangeLine {
  return {
    id: overrides.id ?? `line-${Math.random()}`,
    sheet: '19 series',
    row_no: 7,
    line_no: '1',
    supplier_code_raw: 'ZZT-001',
    supplier_code: 'ZZT-001',
    code_note: null,
    configuration: 'a configuration',
    flags: [],
    match_outcome: 'exact',
    match_rung: null,
    product: { id: 'p-1', product_code: 'ZZT-001', description: 'A product' },
    current_unit_cost: 100,
    current_currency: 'CNY',
    new_unit_cost: 110,
    change_pct: 10,
    line_state: 'changed',
    skipped: false,
    skip_reason: null,
    new_link_lead_time_days: null,
    decision: null,
    decision_reason: null,
    decided_by_name: null,
    stale: null,
    ...overrides,
  };
}

function changeSet(overrides: Partial<CostPriceChangeSetDetail> = {}): CostPriceChangeSetDetail {
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
      decide_blocked_reason: null,
    },
    ...overrides,
  };
}

function renderTab(cs: CostPriceChangeSetDetail) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CostPriceLinesTab changeSet={cs} />
    </QueryClientProvider>,
  );
}

describe('Sticky apply bar copy is singular for one change, plural for more than one', () => {
  it('1 line reads "1 change ready" and "Apply 1 change"', () => {
    linesData = [line({ id: 'a' })];
    renderTab(
      changeSet({
        actions: {
          can_apply: true, apply_blocked_reason: null, apply_count: 1,
          can_submit: false, can_decide: false, can_return: false, can_discard: true,
          decide_blocked_reason: null,
        },
      }),
    );

    expect(screen.getByText('1 change ready')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apply 1 change' })).toBeInTheDocument();
  });

  it('2 lines read "2 changes ready" and "Apply 2 changes"', () => {
    linesData = [line({ id: 'a' }), line({ id: 'b', supplier_code: 'ZZT-002' })];
    renderTab(
      changeSet({
        actions: {
          can_apply: true, apply_blocked_reason: null, apply_count: 2,
          can_submit: false, can_decide: false, can_return: false, can_discard: true,
          decide_blocked_reason: null,
        },
      }),
    );

    expect(screen.getByText('2 changes ready')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apply 2 changes' })).toBeInTheDocument();
  });
});
