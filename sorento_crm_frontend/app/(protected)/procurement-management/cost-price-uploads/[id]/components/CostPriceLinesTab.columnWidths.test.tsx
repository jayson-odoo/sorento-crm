/**
 * CostPriceLinesTab (#1288, Lane A) - the Decision column must be reachable without
 * horizontal scrolling on a Pending set for a verifier at the 1280 breakpoint. The grid
 * runs `tableLayout: { width: 'fixed', columnsResizable: true }`, so `DataGridTable` sets
 * an inline `width: ${header.getSize()}px` on every `<th>` (`components/ui/data-grid-table.tsx`)
 * - a real, DOM-visible pixel budget, not a computed/CSS layout value jsdom cannot produce.
 * Reading it straight off the rendered `columnheader` elements' inline style is therefore a
 * legitimate jsdom assertion (no `getBoundingClientRect`/real layout involved) - this is NOT
 * the "skip it, I will check it in the browser" case.
 *
 * Today's 8 base columns alone (sheet 110 + row 60 + supplier_code 170 + configuration 190 +
 * product 260 + current 110 + new 110 + change 90 = 1100) already exceed the ~950px budget
 * before the Decision column (220) is even added for a verifier - the grid needs narrower
 * and/or fewer columns at this breakpoint, not just a narrower Decision column.
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
    packaging_method: 'standard',
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
      changed: 1, unchanged: 0, new_link: 0, unmatched: 0, duplicate_code: 0,
      needs_attention: 0, skipped: 0, accepted: 0, rejected: 0, undecided: 1,
    },
    largest_rise: null,
    actions: {
      can_apply: false, apply_blocked_reason: '1 row still needs a decision', apply_count: 1,
      can_submit: false, can_decide: true, can_return: true, can_discard: false,
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

describe('At 1280, a verifier on a Pending set reaches Decision without horizontal scroll', () => {
  it('the rendered column widths sum to at most ~950px (the content width the page gives the grid at 1280)', () => {
    linesData = [line({ decision: null })];
    renderTab(changeSet());

    // Confirms the fixture actually reached the verifier+Pending branch before judging
    // its width budget - a missing Decision column would be finding 2, not this one.
    expect(screen.getByRole('columnheader', { name: 'Decision' })).toBeInTheDocument();

    const headers = screen.getAllByRole('columnheader');
    const widths = headers.map((h) => Number.parseInt(h.style.width || '0', 10));
    expect(widths.every((w) => w > 0)).toBe(true);

    const total = widths.reduce((sum, w) => sum + w, 0);
    const CONTENT_WIDTH_AT_1280 = 950;
    expect(total).toBeLessThanOrEqual(CONTENT_WIDTH_AT_1280);
  });
});
