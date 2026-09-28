/**
 * CostPriceLinesTab (#1288, Lane A) - AC-S1-21 (empty states) and AC-SR-02 (search
 * combined with the active stat filter and sheet tab; the stat card counts follow the
 * search).
 *
 * The filter/search logic lives INLINE in this component (`searchTokens`,
 * `matchesSearch`, `FILTERS`), not in a separate hook - so both ACs are exercised through
 * the rendered component rather than an invented hook name.
 *
 * Mocked at the hook boundary (`../../hooks/useCostPriceChangeSets`), never at
 * `../../services/costPriceService` - the coder is mid-swap on that module from its
 * Phase 1 in-memory mock to the real api-client, and a hook-level mock is correct either
 * way. `SearchableSelect` is stubbed to a plain placeholder (SupplierForm.test.tsx's
 * technique): nothing here exercises the manual-map picker, only that it renders for an
 * unmatched row without a jsdom-hostile Radix popover.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { waitForSectionLoaded } from '@/test-utils';
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

function line(overrides: Partial<CostPriceChangeLine>): CostPriceChangeLine {
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

describe('AC-S1-21: every filter renders an explicit empty state', () => {
  it('shows "No codes need mapping" on the Not found filter with zero unmatched lines', async () => {
    linesData = [line({ id: 'a', line_state: 'changed' })];
    renderTab(changeSet());
    await waitForSectionLoaded().catch(() => undefined);

    fireEvent.click(screen.getByRole('button', { name: /Not found/i }));

    expect(await screen.findByText('No codes need mapping')).toBeInTheDocument();
  });

  it('shows the zero-changed empty state with Discard as the next step', async () => {
    linesData = [line({ id: 'a', line_state: 'unchanged' })];
    renderTab(changeSet({ actions: { ...changeSet().actions, can_discard: true } }));

    expect(await screen.findByText('Nothing changed against current costs')).toBeInTheDocument();
    expect(screen.getByText('Discard this set from the header above.')).toBeInTheDocument();
  });

  it('has no Duplicate code filter: a duplicate code is one line (round 6 R6)', () => {
    linesData = [line({ id: 'a', line_state: 'changed' })];
    renderTab(changeSet());

    expect(screen.queryByRole('button', { name: /Duplicate code/i })).not.toBeInTheDocument();
  });

  it('shows "Nothing needs attention" on that filter with none needing it', () => {
    linesData = [line({ id: 'a', line_state: 'changed' })];
    renderTab(changeSet());

    fireEvent.click(screen.getByRole('button', { name: /Needs attention/i }));

    expect(screen.getByText('Nothing needs attention')).toBeInTheDocument();
  });
});

describe('AC-SR-02: search combines with the active stat filter and sheet tab; counts follow the search', () => {
  it('search narrows the stat card counts and the grid together', () => {
    linesData = [
      line({ id: 'a', supplier_code: 'ALPHA-100', line_state: 'changed' }),
      line({ id: 'b', supplier_code: 'BETA-200', line_state: 'changed' }),
    ];
    renderTab(changeSet());

    // Both rows counted before any search narrows them.
    const changedCard = screen.getByRole('button', { name: /Cost changed/i });
    expect(within(changedCard).getByText('2')).toBeInTheDocument();

    const search = screen.getByPlaceholderText('Search code, configuration or product');
    fireEvent.change(search, { target: { value: 'alpha' } });

    expect(within(screen.getByRole('button', { name: /Cost changed/i })).getByText('1')).toBeInTheDocument();
    expect(screen.getByText('ALPHA-100')).toBeInTheDocument();
    expect(screen.queryByText('BETA-200')).not.toBeInTheDocument();
  });

  it('search matches on product code and on configuration, not only the supplier code', () => {
    linesData = [
      line({ id: 'a', supplier_code: 'ZZT-001', configuration: '不锈钢单把', product: { id: 'p1', product_code: 'MATCHME', description: 'x' } }),
      line({ id: 'b', supplier_code: 'ZZT-002', configuration: 'other config', product: { id: 'p2', product_code: 'NOMATCH', description: 'y' } }),
    ];
    renderTab(changeSet());

    const search = screen.getByPlaceholderText('Search code, configuration or product');
    fireEvent.change(search, { target: { value: 'MATCHME' } });

    expect(screen.getByText('ZZT-001')).toBeInTheDocument();
    expect(screen.queryByText('ZZT-002')).not.toBeInTheDocument();
  });

  it('a sheet tab narrows the grid to that sheet only, on top of the active filter', () => {
    linesData = [
      line({ id: 'a', sheet: '19 series', supplier_code: 'S19', line_state: 'changed' }),
      line({ id: 'b', sheet: '25 series', supplier_code: 'S25', line_state: 'changed' }),
    ];
    renderTab(changeSet());

    // Radix `TabsTrigger` activates on mousedown; `fireEvent.click` alone is not enough
    // in jsdom (see LoadingPlanView.test.tsx's `selectTab`).
    const tab = screen.getByRole('tab', { name: /^19 series \(\d+\)$/ });
    fireEvent.mouseDown(tab, { button: 0 });
    fireEvent.click(tab);

    expect(screen.getByText('S19')).toBeInTheDocument();
    expect(screen.queryByText('S25')).not.toBeInTheDocument();
  });
});
