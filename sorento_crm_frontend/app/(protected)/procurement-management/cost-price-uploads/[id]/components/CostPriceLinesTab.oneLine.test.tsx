/**
 * CostPriceLinesTab, fix lane round 6 (#1288, PR #1305), the owner's hand test of 28 Sep 2026:
 * "all rows should be 1 line, don't need Lead time (days), show the currency at each line
 * also" and "don't call it price, it should be cost".
 *
 * R2 one line: jsdom has no layout, so the row-height check here is structural - no cell in
 * the grid stacks anything (no block children, no flex-col, no second line of any kind), and
 * every cell's content is a single no-wrap line. The browser pass measures the real height.
 * R3 no lead time input. R4 "CNY 10.50" on every line beside both costs. R5 cost wording.
 * R6 a duplicate code is one line, the other rows' notes and costs inline, no Duplicate
 * code card and no "Skip this one" second line.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
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

let mobile = false;
vi.mock('@/hooks/use-mobile', () => ({ useIsMobile: () => mobile }));

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
    product: { id: 'p-1', product_code: 'OUR-001', description: 'A product' },
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
    duplicate_rows: [],
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
      changed: 1, unchanged: 0, new_link: 0, unmatched: 0, duplicate_code: 0,
      needs_attention: 0, skipped: 0, accepted: 0, rejected: 0, undecided: 0,
    },
    largest_rise: null,
    actions: {
      can_apply: true, apply_blocked_reason: null, apply_count: 1,
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




function renderAllShapes() {
  mobile = false;
  linesData = [
    line({ id: 'changed', packaging_method: '吊卡', duplicate_rows: [
      { id: 'd1', sheet: '19 series', row_no: 8, supplier_code: 'ZZT-001', packaging_method: 'OPP', new_unit_cost: 9.9 },
    ] }),
    line({ id: 'unmatched', supplier_code: 'ZZT-NF', match_outcome: 'unmatched', product: null, line_state: 'needs_attention' }),
    line({ id: 'no-cost', supplier_code: 'ZZT-NC', new_unit_cost: null, change_pct: null, line_state: 'needs_attention' }),
    line({ id: 'stale', supplier_code: 'ZZT-ST', stale: { live_unit_cost: 105, live_currency: 'CNY' } }),
    line({ id: 'merged', supplier_code: 'ZZT-MG', flags: ['configuration_from_merge'], match_rung: 'strip_suffix' }),
  ];
  // The Cost changed filter shows changed lines; the Needs attention ones are read through
  // their own card below.
  return renderTab(changeSet());
}

function assertEveryCellIsOneLine(container: HTMLElement) {
  const cells = Array.from(container.querySelectorAll('tbody td'));
  expect(cells.length).toBeGreaterThan(0);
  for (const td of cells) {
    expect(td.querySelector('br')).toBeNull();
    expect(td.querySelector('.block, .flex-col, textarea, input[type="number"]')).toBeNull();
    const root = td.firstElementChild as HTMLElement | null;
    if (root) expect(root.className).toMatch(/whitespace-nowrap/);
  }
}

describe('R2: every row is exactly one line at 1280', () => {
  it('changed, stale, merged and duplicate lines render no stacked content', () => {
    const { container } = renderAllShapes();
    expect(screen.getAllByRole('row').length).toBeGreaterThan(1);
    assertEveryCellIsOneLine(container);
  });

  it('Not found and No readable cost lines stay one line, skip is an icon, not a second line', () => {
    const { container } = renderAllShapes();
    fireEvent.click(screen.getByRole('button', { name: /Needs attention/ }));
    assertEveryCellIsOneLine(container);
    const skips = screen.getAllByRole('button', { name: 'Skip this one' });
    expect(skips.length).toBe(2);
    for (const b of skips) expect(b.textContent?.trim()).toBe('');
    expect(screen.queryByText('Skip this one')).not.toBeInTheDocument();
  });

  it('the skip icon patches the line as skipped', () => {
    renderAllShapes();
    fireEvent.click(screen.getByRole('button', { name: /Needs attention/ }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Skip this one' })[0]);
    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ patch: expect.objectContaining({ skipped: true }) }));
  });
});

describe('R3: no lead time input', () => {
  it('a new link line has no Lead time (days) field', () => {
    mobile = false;
    linesData = [line({ line_state: 'new_link', current_unit_cost: null, current_currency: null, change_pct: null })];
    renderTab(changeSet());
    fireEvent.click(screen.getByRole('button', { name: /New for this supplier/ }));
    expect(screen.getByText('ZZT-001', { selector: 'span' })).toBeInTheDocument();
    expect(screen.queryByText(/Lead time/i)).not.toBeInTheDocument();
    expect(document.querySelector('input[type="number"]')).toBeNull();
  });

  it('nor on the 375 card', () => {
    mobile = true;
    linesData = [line({ line_state: 'new_link', current_unit_cost: null, current_currency: null, change_pct: null })];
    renderTab(changeSet());
    fireEvent.click(screen.getByRole('button', { name: /New for this supplier/ }));
    expect(screen.queryByText(/Lead time/i)).not.toBeInTheDocument();
    mobile = false;
  });
});

describe('R4: the currency on every line, beside both costs', () => {
  it('shows CNY before the cost now and the new cost', () => {
    mobile = false;
    linesData = [line({ current_unit_cost: 10, current_currency: 'CNY', new_unit_cost: 10.5 })];
    renderTab(changeSet({ currency: 'CNY' }));
    expect(screen.getByText('CNY 10.00')).toBeInTheDocument();
    expect(screen.getByText('CNY 10.50')).toBeInTheDocument();
  });

  it('a cost now in another currency names that currency', () => {
    mobile = false;
    linesData = [line({ current_unit_cost: 15, current_currency: 'USD', new_unit_cost: 114.3 })];
    renderTab(changeSet({ currency: 'CNY' }));
    expect(screen.getByText('USD 15.00')).toBeInTheDocument();
    expect(screen.getByText('CNY 114.30')).toBeInTheDocument();
  });

  it('the 375 card carries the currency too', () => {
    mobile = true;
    linesData = [line({ current_unit_cost: 10, current_currency: 'CNY', new_unit_cost: 10.5 })];
    renderTab(changeSet({ currency: 'CNY' }));
    expect(screen.getByText(/CNY 10\.50/)).toBeInTheDocument();
    mobile = false;
  });
});

describe('R5: cost, never price', () => {
  it('cards and column headers say cost', () => {
    mobile = false;
    linesData = [line()];
    renderTab(changeSet());
    expect(screen.getByRole('button', { name: /Cost changed/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Unchanged/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Cost now' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'New cost' })).toBeInTheDocument();
    expect(screen.queryByText(/price/i)).not.toBeInTheDocument();
  });
});

describe('R6: a duplicate code is one line', () => {
  it('shows the other rows inline and no Duplicate code card', () => {
    const { container } = renderAllShapes();
    expect(screen.queryByRole('button', { name: /Duplicate code/ })).not.toBeInTheDocument();
    const row = screen.getByText('吊卡').closest('tr') as HTMLElement;
    expect(within(row).getByText('· OPP 9.90')).toBeInTheDocument();
    expect(within(row).getByText('CNY 110.00')).toBeInTheDocument();
    assertEveryCellIsOneLine(container);
  });

  it('never renders the rows that rode on another line as lines of their own', () => {
    mobile = false;
    linesData = [
      line({ id: 'used' }),
      line({ id: 'hidden', flags: ['duplicate_code', 'duplicate_row'], skipped: true, skip_reason: 'Duplicate code' }),
    ];
    renderTab(changeSet());
    expect(screen.getAllByText('ZZT-001', { selector: 'span' }).length).toBe(1);
  });
});
