/**
 * CostPriceLinesTab (#1288, PR #1305 fix lane round 8): cost per packaging method.
 *
 * Owner, 28 Sep 2026: "there needs to be diffetent cost for differnet packging method
 * correct"; "1 packagin value is free text yeah, a code with no bracket yeah correct".
 * AC-PK-04: a Packaging column beside Supplier code, sortable, a Packaging filter (the system
 * `SearchableMultiSelect`), and the 375 card shows the packaging beside the code.
 *
 * Mocked at the hook boundary, same technique as `CostPriceLinesTab.round7.test.tsx`.
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

// The system multi-select, stubbed to one button per option (its own tests cover the popover).
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    placeholder,
    options,
    value,
    onChange,
  }: {
    placeholder?: string;
    options: { value: string; label: string }[];
    value: string[];
    onChange: (v: string[]) => void;
  }) => (
    <div data-testid={`multi-select-${placeholder}`}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value.includes(o.value)}
          onClick={() => onChange(value.includes(o.value) ? value.filter((v) => v !== o.value) : [...value, o.value])}
        >
          {o.label}
        </button>
      ))}
    </div>
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

import { CostPriceLinesTab, packagingKey } from './CostPriceLinesTab';

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

beforeEach(() => {
  mobile = false;
  mutateAsync.mockClear();
});

/** The supplier's 2500 series rows, as three lines (backend keys them by code AND packaging). */
function series2500(): CostPriceChangeLine[] {
  return [
    line({ id: 'bl-box', row_no: 5, supplier_code: 'CB2500SS-BL', packaging_method: '彩盒', new_unit_cost: 9.5, current_unit_cost: null, change_pct: null }),
    line({ id: 'diy-opp', row_no: 6, supplier_code: 'CB2500SS-BL-DIY', packaging_method: 'OPP', new_unit_cost: 9.9, current_unit_cost: null, change_pct: null }),
    line({ id: 'diy-card', row_no: 7, supplier_code: 'CB2500SS-BL-DIY', packaging_method: '吊卡', new_unit_cost: 9.4, current_unit_cost: null, change_pct: null }),
    line({ id: 'plain', row_no: 8, supplier_code: 'CB2500SS-BL', packaging_method: 'standard', new_unit_cost: 9.0 }),
  ];
}

function headers(): string[] {
  return screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
}

function column(name: string): string[] {
  const index = headers().findIndex((h) => h.includes(name));
  return screen.getAllByRole('row').slice(1).map((r) => within(r).getAllByRole('cell')[index].textContent ?? '');
}

describe('AC-PK-04: the Packaging column sits beside Supplier code', () => {
  it('shows each line\'s packaging as written, beside the code', () => {
    linesData = series2500();
    renderTab(changeSet());

    const h = headers();
    expect(h.findIndex((x) => x.includes('Packaging'))).toBe(h.findIndex((x) => x.includes('Supplier code')) + 1);
    expect(column('Packaging')).toEqual(['彩盒', 'OPP', '吊卡', 'standard']);
    expect(column('Supplier code')).toEqual(['CB2500SS-BL', 'CB2500SS-BL-DIY', 'CB2500SS-BL-DIY', 'CB2500SS-BL']);
  });

  it('sorts by packaging from its header', () => {
    linesData = series2500();
    renderTab(changeSet());

    const header = screen.getByRole('columnheader', { name: /Packaging/ });
    fireEvent.click(within(header).getByRole('button', { name: 'Packaging' }));
    // The grid's own text sort (case-insensitive, then code point).
    expect(column('Packaging')).toEqual(['OPP', 'standard', '吊卡', '彩盒']);
  });

  it('the column budget still fits 950px with a verifier\'s Decision column', () => {
    linesData = series2500();
    renderTab(
      changeSet({
        status: 'pending_verification',
        actions: { ...changeSet().actions, can_decide: true, can_return: true },
      }),
    );
    const total = screen
      .getAllByRole('columnheader')
      .reduce((sum, th) => sum + parseInt((th as HTMLElement).style.width || '0', 10), 0);
    expect(total).toBeLessThanOrEqual(950);
  });
});

describe('AC-PK-04: the Packaging filter', () => {
  it('narrows the lines, the cards and the sheet counts to the picked packaging', () => {
    linesData = series2500();
    renderTab(changeSet());

    const filter = screen.getByTestId('multi-select-Packaging');
    expect(within(filter).getAllByRole('button').map((b) => b.textContent)).toEqual(['彩盒', 'OPP', '吊卡', 'standard']);
    fireEvent.click(within(filter).getByRole('button', { name: 'OPP' }));
    expect(column('Packaging')).toEqual(['OPP']);
    fireEvent.click(within(filter).getByRole('button', { name: '吊卡' }));
    expect(column('Packaging')).toEqual(['OPP', '吊卡']);
  });

  it('folds the key the way the backend does, so OPP and opp are one option', () => {
    expect(packagingKey('OPP')).toBe(packagingKey(' opp '));
    expect(packagingKey('ＯＰＰ')).toBe('opp');
    expect(packagingKey('')).toBe('standard');
    linesData = [...series2500(), line({ id: 'diy-opp-2', row_no: 9, supplier_code: 'CB2500SS-BL-DIY2', packaging_method: 'opp' })];
    renderTab(changeSet());
    const filter = screen.getByTestId('multi-select-Packaging');
    expect(within(filter).getAllByRole('button').map((b) => b.textContent)).toEqual(['彩盒', 'OPP', '吊卡', 'standard']);
    fireEvent.click(within(filter).getByRole('button', { name: 'OPP' }));
    expect(column('Packaging')).toEqual(['OPP', 'opp']);
  });

  it('the search also finds a packaging', () => {
    linesData = series2500();
    renderTab(changeSet());
    fireEvent.change(screen.getByPlaceholderText('Search code, configuration or product'), { target: { value: '吊卡' } });
    expect(column('Packaging')).toEqual(['吊卡']);
  });
});

describe('AC-PK-04: the 375 card shows the packaging beside the code', () => {
  it('renders the packaging on every card', () => {
    mobile = true;
    linesData = series2500();
    renderTab(changeSet());
    expect(screen.getAllByTestId('line-card-packaging').map((n) => n.textContent)).toEqual(['彩盒', 'OPP', '吊卡', 'standard']);
  });
});

describe('Round 8: a duplicate is the same code AND packaging', () => {
  it('shows a same-packaging duplicate\'s cost inline without repeating the packaging', () => {
    linesData = [
      line({
        id: 'opp', supplier_code: 'ZZ-1', packaging_method: 'OPP', flags: ['duplicate_code'],
        duplicate_rows: [{ id: 'd', sheet: '19 series', row_no: 9, supplier_code: 'ZZ-1', packaging_method: 'OPP', new_unit_cost: 9.95 }],
      }),
    ];
    renderTab(changeSet());
    expect(column('Supplier code')).toEqual(['ZZ-1· 9.95']);
  });
});
