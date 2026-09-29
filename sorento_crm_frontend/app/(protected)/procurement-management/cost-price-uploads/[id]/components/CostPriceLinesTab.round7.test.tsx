/**
 * CostPriceLinesTab (#1288, round 7, owner hand test 28 Sep 2026).
 *
 * R1 "for cost price, don't need this already": the sticky footer bar ("N changes ready",
 * its Apply, "N rows still need you", Largest rise) is gone from the Lines tab; the header's
 * Apply is the page's one call to action.
 *
 * R2 "this table better show the number, and need to use datagrid table with pagination
 * just like our list view": the sheet tabs carry a count that follows the active filter
 * card ("All sheets (N)", "19系列 (N)"), and the lines are the system DataGrid with the
 * list views' pager (rows per page, page buttons), sortable column headers, and at 375
 * the current page as cards under the same pager.
 *
 * Mocked at the hook boundary, same technique as `CostPriceLinesTab.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, it, expect, vi } from 'vitest';
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
  SearchableSelect: ({ placeholder, value }: { placeholder?: string; value?: string }) => (
    <div data-testid="searchable-select-stub">{value || placeholder}</div>
  ),
}));

let mobile = false;
vi.mock('@/hooks/use-mobile', () => ({ useIsMobile: () => mobile }));

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

import { CostPriceLinesTab, sheetTabLabel } from './CostPriceLinesTab';

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

/** `count` lines on `sheet`, rows numbered from `firstRow`, codes `<prefix>-NNN`. */
function sheetLines(sheet: string, count: number, prefix: string, extra: Partial<CostPriceChangeLine> = {}) {
  return Array.from({ length: count }, (_, i) =>
    line({ id: `${prefix}-${i}`, sheet, row_no: i + 1, supplier_code: `${prefix}-${String(i + 1).padStart(3, '0')}`, ...extra }),
  );
}

function bodyCodes(): string[] {
  const rows = screen.getAllByRole('row').slice(1);
  return rows.map((r) => within(r).getAllByRole('cell')[1].textContent ?? '');
}

beforeEach(() => {
  mobile = false;
  mutateAsync.mockClear();
});

describe('Round 7 R1: no sticky footer bar on the Lines tab', () => {
  it('shows no "N changes ready", no Apply, no "still need you", no Largest rise', () => {
    linesData = sheetLines('19系列', 3, 'A');
    renderTab(
      changeSet({
        largest_rise: { supplier_code: 'A-001', change_pct: 10 },
        actions: {
          can_apply: false, apply_blocked_reason: '2 rows still need you', apply_count: 184,
          can_submit: false, can_decide: false, can_return: false, can_discard: true,
          decide_blocked_reason: null,
        },
      }),
    );

    expect(screen.queryByText(/changes? ready/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Apply \d+ change/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Submit for verification/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/still need you/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Largest rise/)).not.toBeInTheDocument();
  });

  it("keeps a verifier's Accept all and Return to submitter on the tab", () => {
    linesData = sheetLines('19系列', 2, 'A');
    renderTab(
      changeSet({
        verification_enabled: true,
        status: 'pending_verification',
        actions: {
          can_apply: false, apply_blocked_reason: null, apply_count: 2,
          can_submit: false, can_decide: true, can_return: true, can_discard: false,
          decide_blocked_reason: null,
        },
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Accept all' }));
    expect(mutateAsync).toHaveBeenCalledWith('accepted');
    expect(screen.getByRole('button', { name: 'Return to submitter' })).toBeInTheDocument();
  });
});

describe('Round 7 R2: sheet tabs show the row count, following the filter card', () => {
  it('formats a tab as "sheet (count)"', () => {
    expect(sheetTabLabel('19系列', 48)).toBe('19系列 (48)');
    expect(sheetTabLabel('All sheets', 228)).toBe('All sheets (228)');
  });

  it('counts per sheet and in total under the active card, and moves with the card', () => {
    linesData = [
      ...sheetLines('19系列', 3, 'A'),
      ...sheetLines('12系列', 2, 'B'),
      ...sheetLines('12系列', 4, 'C', { line_state: 'unchanged', change_pct: 0, new_unit_cost: 100 }).map((l, i) => ({ ...l, row_no: 10 + i })),
    ];
    renderTab(changeSet());

    expect(screen.getByRole('tab', { name: 'All sheets (5)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '19系列 (3)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '12系列 (2)' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Unchanged/ }));
    expect(screen.getByRole('tab', { name: 'All sheets (4)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '19系列 (0)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '12系列 (4)' })).toBeInTheDocument();
  });
});

describe('Round 7 R2: the lines are the system DataGrid with the list views pager', () => {
  it('pages 60 lines 50 per page with a rows-per-page selector and page buttons', () => {
    linesData = sheetLines('19系列', 60, 'A');
    renderTab(changeSet());

    expect(screen.getAllByRole('row')).toHaveLength(51); // header + 50
    expect(screen.getByText('Rows per page')).toBeInTheDocument();
    expect(screen.getByText('1 - 50 of 60')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Go to next page' }));
    expect(screen.getAllByRole('row')).toHaveLength(11); // header + 10
    expect(screen.getByText('51 - 60 of 60')).toBeInTheDocument();
    expect(bodyCodes()[0]).toContain('A-051');
  });

  it('a sheet tab goes back to page 1 and pages within the sheet', () => {
    linesData = [...sheetLines('19系列', 60, 'A'), ...sheetLines('12系列', 5, 'B')];
    renderTab(changeSet());

    fireEvent.click(screen.getByRole('button', { name: 'Go to next page' }));
    expect(screen.getByText('51 - 65 of 65')).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole('tab', { name: '12系列 (5)' }), { button: 0 });
    fireEvent.click(screen.getByRole('tab', { name: '12系列 (5)' }));
    expect(screen.getByText('1 - 5 of 5')).toBeInTheDocument();
    expect(bodyCodes()).toHaveLength(5);
  });

  it('sorts from the column header: New cost ascending puts the cheapest first', () => {
    linesData = [
      line({ id: 'x', supplier_code: 'X-1', row_no: 1, new_unit_cost: 30 }),
      line({ id: 'y', supplier_code: 'Y-1', row_no: 2, new_unit_cost: 10 }),
      line({ id: 'z', supplier_code: 'Z-1', row_no: 3, new_unit_cost: 20 }),
    ];
    renderTab(changeSet());
    expect(bodyCodes().map((c) => c.slice(0, 3))).toEqual(['X-1', 'Y-1', 'Z-1']);

    const header = screen.getByRole('columnheader', { name: /New cost/ });
    // The system column header, as on every list view: a click sorts ascending.
    fireEvent.click(within(header).getByRole('button', { name: 'New cost' }));
    expect(bodyCodes().map((c) => c.slice(0, 3))).toEqual(['Y-1', 'Z-1', 'X-1']);
  });

  it('keeps every row on one line inside the grid (round 6 rule carried over)', () => {
    linesData = sheetLines('19系列', 2, 'A', { duplicate_rows: [{ id: 'd', supplier_code: 'A-001', packaging_method: 'OPP', new_unit_cost: 9.9, sheet: '19系列', row_no: 99 }] });
    renderTab(changeSet());
    const first = screen.getAllByRole('row')[1];
    expect(within(first).getByText(/OPP 9.90/)).toBeInTheDocument();
    expect(within(first).getAllByText(/CNY/).length).toBeGreaterThanOrEqual(2);
  });
});

describe('Round 7 R2 at 375: the current page as cards under the same pager', () => {
  it('renders 50 cards on page 1 of 60 lines and the next page on Next', () => {
    mobile = true;
    linesData = sheetLines('19系列', 60, 'A');
    renderTab(changeSet());

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getAllByText(/^A-0\d\d$/)).toHaveLength(50);
    expect(screen.getByText('1 - 50 of 60')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Go to next page' }));
    expect(screen.getAllByText(/^A-0\d\d$/)).toHaveLength(10);
    expect(screen.getByText('A-060')).toBeInTheDocument();
  });
});
