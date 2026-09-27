/**
 * CostPriceLinesTab (#1288, Lane A) - tester finding 1 (browser evidence run), now a
 * defect against J14 + AC-AU-04: once a set is Applied, a line's Accept/Reject decision
 * (and the reject reason) must stay visible somewhere on the Lines tab, read-only - today
 * `showDecisionColumn` is `isVerifier && changeSet.status === 'pending_verification'`,
 * which is unconditionally false once `status` flips to `applied`, so a rejected line
 * renders identically to an accepted one after Apply and the reason Kelvin typed
 * disappears from view entirely.
 *
 * Mocked at the hook boundary, same technique as `CostPriceLinesTab.test.tsx` (see that
 * file's header for why: the coder is mid-swap on `costPriceService.ts`).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
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
    code: 'CPC-0006',
    status: 'applied',
    channel: 'staff_upload',
    supplier: { id: 'sup-1', supplier_code: 'ZZT-S', supplier_name: 'A Supplier' },
    currency: 'CNY',
    start_date: null,
    end_date: null,
    file_name: 'list.xlsx',
    has_source_file: true,
    sheets: [{ name: '19 series', header_row: 6, rows: 1, skipped_reason: null }],
    total_rows: 2,
    uploaded_by_name: 'Mei Ling',
    created_at: '2026-09-27T00:00:00',
    submitted_by_name: 'Mei Ling',
    submitted_at: '2026-09-27T00:05:00',
    returned_reason: null,
    returned_by_name: null,
    returned_at: null,
    applied_by_name: 'Kelvin',
    applied_at: '2026-09-27T00:10:00',
    verified: true,
    verification_enabled: true,
    counts: {
      changed: 2, unchanged: 0, new_link: 0, unmatched: 0, duplicate_code: 0,
      needs_attention: 0, skipped: 0, accepted: 1, rejected: 1, undecided: 0,
    },
    largest_rise: null,
    actions: {
      can_apply: false, apply_blocked_reason: null, apply_count: 0,
      can_submit: false, can_decide: false, can_return: false, can_discard: false,
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

describe('J14 / AC-AU-04: an Applied set keeps each line decision visible, read-only', () => {
  it('shows Accepted / Rejected badges and the reject reason for an Applied set whose lines carry decisions', () => {
    linesData = [
      line({ id: 'accepted-line', supplier_code: 'ZZCPC-HIST-ACC', decision: 'accepted', decided_by_name: 'Kelvin' }),
      line({
        id: 'rejected-line',
        supplier_code: 'ZZCPC-HIST-REJ',
        decision: 'rejected',
        decision_reason: 'price looks wrong',
        decided_by_name: 'Kelvin',
      }),
    ];
    renderTab(changeSet());

    const decisionHeader = screen.getByRole('columnheader', { name: 'Decision' });
    expect(decisionHeader).toBeInTheDocument();

    const acceptedRow = screen.getByText('ZZCPC-HIST-ACC').closest('tr')!;
    expect(within(acceptedRow).getByText('Accepted')).toBeInTheDocument();

    const rejectedRow = screen.getByText('ZZCPC-HIST-REJ').closest('tr')!;
    const rejectedBadge = within(rejectedRow).getByText('Rejected');
    expect(rejectedBadge).toBeInTheDocument();
    // The reason travels with the row (title or visible text) - a reviewer must not have
    // to cross-reference the set's History tab to learn WHY a line was rejected.
    const rejectedRowText = rejectedRow.textContent ?? '';
    const rejectedTitle = rejectedBadge.getAttribute('title') ?? rejectedRow.querySelector('[title]')?.getAttribute('title') ?? '';
    expect(rejectedRowText.includes('price looks wrong') || rejectedTitle.includes('price looks wrong')).toBe(true);

    // Not presented as if the change simply applied like an accepted row: the Rejected
    // badge itself must be the thing rendered in that row's Decision cell, not blank/'-'.
    expect(within(rejectedRow).queryByText('-')).not.toBeInTheDocument();
  });

  it('renders no Decision column on an Applied set whose lines carry no decisions at all', () => {
    linesData = [line({ id: 'a', supplier_code: 'ZZCPC-HIST-NODECISION', decision: null })];
    renderTab(changeSet({ verification_enabled: false, verified: null }));

    expect(screen.queryByRole('columnheader', { name: 'Decision' })).not.toBeInTheDocument();
  });
});
