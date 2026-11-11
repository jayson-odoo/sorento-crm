/**
 * Products > Costing, the read side (lane PRODUCT-COSTING, Phase 2 red tests F1; UAC AC-CG-01..07,
 * 09, 10, 11, 12, 14). The workbook in the system: one DataGrid page, party picker, filters.
 *
 * ASSUMED NAMES (the coder implements exactly these; CONTRACT-product-costing.md section 5):
 *  - `./CostingView` default export (a named `CostingView` export is also accepted).
 *  - `../services/costingService` exports getCostingRows(params), getCostingRowSuppliers(productId, params),
 *    saveCostingRows(body), getCostingRowHistory(productId, partyId), exportCosting(params),
 *    getCostingSettings(), saveCostingSettings(body), getCategoryRules(), saveCategoryRule(categoryId, body),
 *    getExchangeRates(), createExchangeRate(body), updateExchangeRate(id, body), getParty(customerId),
 *    saveParty(customerId, body), addPartyProducts(customerId, productIds).
 *  - Service params use the API query names: party_id, q, category_id, brand_id, cost_method (comma
 *    joined), cost (has or none when exactly one is picked; the key is absent otherwise), as_of, page, limit.
 *  - URL params: party, category, brand, method, cost=has,none, as_of. The page writes them with
 *    router.push or router.replace.
 *  - Permissions via useHasPermission from '@/hooks/usePermissions'.
 *  - PageHeader receives `actions`; the party picker is CustomerDebtorCombobox with pickOnly and
 *    placeholder "Company standard"; picking calls onChange(name, item) with item.customer_id,
 *    clearing calls onChange('').
 *  - Filters popover: SearchableMultiSelect labelled "Category", "Brand", "Cost method" and a Switch
 *    labelled "Has cost". Toolbar search placeholder "Search code or name".
 *  - Row expand toggle: button named `Show suppliers for {code}` (`Hide suppliers for {code}` when open).
 *  - Row menu trigger: `{code} actions`, items "History" and (party view, manage) "Remove from party".
 *  - Secondary toolbar actions: "Export" (always) and "Add products" (party view + manage). With two
 *    of them the toolbar collapses them into an "Actions" menu; the helper below handles both.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  ACCESSORY, JACUZZI, NO_PRIMARY, NO_RATE, NO_TRANSPORT, PARTY, SUPPLIERS, WB245,
  costingRow, partyEnvelope, standardEnvelope,
} from './__fixtures__/costingFixtures';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
const url = vi.hoisted(() => ({ search: '', cache: null as null | { s: string; p: URLSearchParams } }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/costing',
  useRouter: () => router,
  useSearchParams: () => {
    if (!url.cache || url.cache.s !== url.search) url.cache = { s: url.search, p: new URLSearchParams(url.search) };
    return url.cache.p;
  },
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title, actions }: { title: string; actions?: React.ReactNode }) => (
    <header>
      <h1>{title}</h1>
      <div data-testid="header-actions">{actions}</div>
    </header>
  ),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string; value: string; onChange: (v: string) => void;
    options?: { value: string; label: string }[]; placeholder?: string; disabled?: boolean;
    'aria-label'?: string;
    fetchOptions?: (q: string, page: number) => Promise<{ value: string; label: string }[]>;
    selectedOption?: { value: string; label: string };
    clearable?: boolean;
  }) => {
    const [fetched, setFetched] = React.useState<{ value: string; label: string }[]>([]);
    React.useEffect(() => {
      if (props.fetchOptions) props.fetchOptions('', 0).then(setFetched);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    const options = props.fetchOptions ? fetched : (props.options ?? []);
    const extra = props.selectedOption && !options.some((o) => o.value === props.selectedOption!.value)
      ? [props.selectedOption] : [];
    return (
      <>
        {props.fetchOptions ? (
          <input aria-label={`${props['aria-label']} search`}
            onChange={(e) => props.fetchOptions!(e.target.value, 0).then(setFetched)} />
        ) : null}
        <select id={props.id} aria-label={props['aria-label']} value={props.value} disabled={props.disabled}
          onChange={(e) => props.onChange(e.target.value)}>
          {props.clearable ? <option value="">{props.placeholder ?? ''}</option> : null}
          {[...extra, ...options].map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </>
    );
  },
}));
const customers = vi.hoisted(() => ({ searchCustomersSelect: vi.fn() }));
vi.mock('../../../order-management/customers/services/customerService', () => customers);
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    id?: string; 'aria-label'?: string; value: string[]; onChange: (v: string[]) => void;
    options?: { value: string; label: string }[];
    fetchOptions?: (q: string) => Promise<{ value: string; label: string }[]>;
  }) => {
    const [options, setOptions] = React.useState(props.options ?? []);
    React.useEffect(() => {
      if (props.fetchOptions) props.fetchOptions('').then(setOptions);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    const shown = props.fetchOptions ? options : (props.options ?? []);
    return (
      <select multiple id={props.id} aria-label={props['aria-label'] ?? props.id ?? 'select'} value={props.value}
        onChange={(e) => props.onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {shown.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    );
  },
}));
vi.mock('../../shared/hooks/use-product-category-select-query', () => ({
  useProductCategorySelectQuery: () => ({ data: [{ id: 'cat-1', category_name: 'Ceramics' }, { id: 'cat-2', category_name: 'Taps' }], error: null, refetch: vi.fn(), isLoading: false }),
}));
vi.mock('../../shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [{ id: 'b1', brand_name: 'Mocha' }], error: null, refetch: vi.fn(), isLoading: false }),
}));

const perms = vi.hoisted(() => ({ granted: new Set<string>() }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.granted.has(slug),
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));

const service = vi.hoisted(() => ({
  getCostingRows: vi.fn(),
  getCostingRowSuppliers: vi.fn(),
  saveCostingRows: vi.fn(),
  getCostingRowHistory: vi.fn(),
  exportCosting: vi.fn(),
  getCostingSettings: vi.fn(),
  saveCostingSettings: vi.fn(),
  getCategoryRules: vi.fn(),
  saveCategoryRule: vi.fn(),
  getExchangeRates: vi.fn(),
  createExchangeRate: vi.fn(),
  updateExchangeRate: vi.fn(),
  getParty: vi.fn(),
  saveParty: vi.fn(),
  addPartyProducts: vi.fn(),
}));
vi.mock('../services/costingService', () => service);

import * as viewModule from './CostingView';
const CostingView = ((viewModule as Record<string, unknown>).default ??
  (viewModule as Record<string, unknown>).CostingView) as React.ComponentType;

type Params = Record<string, unknown>;

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CostingView />
    </QueryClientProvider>,
  );
}
const lastParams = (): Params => service.getCostingRows.mock.calls.at(-1)![0] as Params;
const urlsWritten = () => [...router.push.mock.calls, ...router.replace.mock.calls].map((c) => String(c[0]));
const headers = () =>
  screen.getAllByRole('columnheader').map((h) => h.textContent?.trim()).filter(Boolean);
const rowOf = (code: string) => screen.getByText(code).closest('tr') as HTMLElement;

async function pressAction(name: string) {
  const direct = screen.queryByRole('button', { name });
  if (direct) return fireEvent.click(direct);
  fireEvent.keyDown(screen.getByRole('button', { name: 'Actions' }), { key: 'Enter' });
  fireEvent.click(await screen.findByRole('menuitem', { name }));
}
function openFilters() {
  fireEvent.keyDown(screen.getByRole('button', { name: /filters/i }), { key: 'Enter' });
}

const STANDARD_HEADERS = [
  'Category', 'Code', 'Name', 'Supplier', 'Cost', 'Rate', 'SST', 'Transport', 'Landing (RM)',
  'Cost method', 'Mark-up', 'Final (RM)', 'List price (AutoCount)',
];

beforeEach(() => {
  vi.clearAllMocks();
  router.push.mockReset();
  router.replace.mockReset();
  url.search = '';
  perms.granted = new Set(['products.cost.view', 'products.party_costing.manage']);
  service.getCostingRows.mockResolvedValue(standardEnvelope());
  service.getCostingRowSuppliers.mockResolvedValue(SUPPLIERS);
  service.getCostingRowHistory.mockResolvedValue({
    data: [{ changed_at: '2026-11-10T09:30:00', user_name: 'Hana Tester', field: 'markup_pct', old: 8, new: 10 }],
  });
  service.exportCosting.mockResolvedValue(undefined);
  service.getCostingSettings.mockResolvedValue({ sst_factor: 1.1, default_method: 'primary' });
  service.getCategoryRules.mockResolvedValue({ data: [] });
  service.getExchangeRates.mockResolvedValue({ data: [] });
  service.getParty.mockResolvedValue(PARTY);
  customers.searchCustomersSelect.mockImplementation(async (q: string) =>
    [{ value: 'cust-1', label: '304-R017 - RELATED - BATHPLUS SDN BHD' },
     { value: 'cust-2', label: '304-R018 - OTHER DEBTOR' }].filter((c) => !q || c.label.toLowerCase().includes(q.toLowerCase())));
});

describe('Company standard view (AC-CG-01, AC-CG-03)', () => {
  it('titles the page Costing, with the picker on "Company standard" and no party chips', async () => {
    mount();
    expect(await screen.findByText('CGB9032B')).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Costing' })).toBeTruthy();
    const slot = screen.getByTestId('costing-search-slot'); // inside the toolbar's search slot
    const picker = within(slot).getByLabelText('Party') as HTMLSelectElement;
    expect(picker.value).toBe('');
    expect(within(picker).getByText('Company standard')).toBeTruthy();
    expect(within(slot).getByPlaceholderText('Search code or name')).toBeTruthy();
    expect(screen.queryByText('Party mark-up')).toBeNull();
    expect(screen.queryByText('Rates as of')).toBeNull();
  });

  it('has the Sheet1 columns in order and no Margin column', async () => {
    mount();
    await screen.findByText('CGB9032B');
    expect(headers()).toEqual(STANDARD_HEADERS);
  });

  it('asks for the company standard with no party, no has_cost and no other narrowing (QE)', async () => {
    mount();
    await screen.findByText('CGB9032B');
    const first = service.getCostingRows.mock.calls[0][0] as Params;
    expect(first.party_id ?? undefined).toBeUndefined();
    expect(first.has_cost ?? undefined).toBeUndefined();
    expect(first.category_id ?? undefined).toBeUndefined();
    expect(first.brand_id ?? undefined).toBeUndefined();
    expect(first.cost_method ?? undefined).toBeUndefined();
  });

  it('shows Final as the AutoCount price and Mark-up as the achieved figure (WB 245: 149.06%)', async () => {
    mount();
    await screen.findByText('CGB9032B');
    const tr = rowOf('CGB9032B');
    expect(within(tr).getByText(/149\.06/)).toBeTruthy();
    expect(within(tr).getAllByText(/79\.00/).length).toBeGreaterThan(0);
  });

  it('lists the costless product with its reason and never a 0.00 (AC-CG-05, QE)', async () => {
    mount();
    await screen.findByText('A-4xx');
    const tr = rowOf('A-4xx');
    expect(within(tr).getByText('No cost')).toBeTruthy();
    expect(tr.textContent).not.toMatch(/(^|[^\d.,])0\.00(?!\d)/);
  });
});

describe('Party view (AC-CG-02, AC-CG-04)', () => {
  beforeEach(() => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(partyEnvelope());
  });

  it('reads the party from the URL and asks the server for that party', async () => {
    mount();
    await screen.findByText('CGB9032B');
    expect(lastParams().party_id).toBe('cust-1');
  });

  it('adds the Margin column last and the four header chips', async () => {
    mount();
    await screen.findByText('CGB9032B');
    expect(headers()).toEqual([...STANDARD_HEADERS, 'Margin']);
    for (const chip of ['Party mark-up', 'Cost method', 'Rates as of', 'Products']) {
      expect(screen.getAllByText(chip).length).toBeGreaterThan(0);
    }
  });

  it('shows the workbook row: CNY 34.50, 1.6, 1.10, + RM 8.00, 31.72, 34.26, list 79.00, margin 130.61%', async () => {
    mount();
    await screen.findByText('CGB9032B');
    const tr = rowOf('CGB9032B');
    expect(within(tr).getByText('CNY 34.50')).toBeTruthy();
    expect(within(tr).getByText(/^1\.6\d*$/)).toBeTruthy();
    expect(within(tr).getByText('1.10')).toBeTruthy();
    expect(within(tr).getByText('+ RM 8.00')).toBeTruthy();
    expect(within(tr).getByText('31.72')).toBeTruthy();
    expect(within(tr).getByText('34.26')).toBeTruthy();
    expect(within(tr).getAllByText(/79\.00/).length).toBeGreaterThan(0);
    expect(within(tr).getByText(/130\.61\s?%/)).toBeTruthy();
  });

  it('shows the Jacuzzi row at its own 10% mark-up: 1,861.61 and 114.81%', async () => {
    mount();
    await screen.findByText('JZ-1xx');
    const tr = rowOf('JZ-1xx');
    expect(within(tr).getByText('1,692.38')).toBeTruthy();
    expect(within(tr).getByText('1,861.61')).toBeTruthy();
    expect(within(tr).getByText(/114\.81\s?%/)).toBeTruthy();
  });

  it('marks only values set on the row with "Set on this row" (AC-CG-05)', async () => {
    mount();
    await screen.findByText('JZ-1xx');
    expect(within(rowOf('JZ-1xx')).getAllByTitle('Set on this row').length).toBeGreaterThan(0);
    expect(within(rowOf('CGB9032B')).queryAllByTitle('Set on this row')).toHaveLength(0);
  });

  it('marks a transport or method override set on the product', async () => {
    service.getCostingRows.mockResolvedValue(
      partyEnvelope([costingRow({ transport_source: 'product', cost_method_source: 'product', markup_source: 'party' })]),
    );
    mount();
    await screen.findByText('CGB9032B');
    expect(within(rowOf('CGB9032B')).getAllByTitle('Set on this row').length).toBeGreaterThanOrEqual(2);
  });

  it('turns every unknown into its reason pill, never 0.00 (AC-CG-05)', async () => {
    service.getCostingRows.mockResolvedValue(partyEnvelope([NO_RATE, NO_PRIMARY, NO_TRANSPORT, ACCESSORY]));
    mount();
    await screen.findByText('E-5xx');
    expect(within(rowOf('E-5xx')).getByText('No rate for EUR on 11/11/2026')).toBeTruthy();
    expect(within(rowOf('N-6xx')).getByText('Set a primary supplier')).toBeTruthy();
    expect(within(rowOf('T-7xx')).getByText('No transport rule')).toBeTruthy();
    expect(within(rowOf('A-4xx')).getByText('No cost')).toBeTruthy();
    for (const code of ['E-5xx', 'N-6xx', 'A-4xx']) {
      expect(rowOf(code).textContent).not.toMatch(/(^|[^\d.,])0\.00(?!\d)/);
    }
  });
});

describe('Picking the party (AC-CG-02)', () => {
  it('writes party into the URL when a customer is picked', async () => {
    mount();
    await screen.findByText('CGB9032B');
    const party = screen.getByLabelText('Party');
    await waitFor(() => expect(within(party).getByText('RELATED - BATHPLUS SDN BHD (304-R017)')).toBeTruthy());
    fireEvent.change(party, { target: { value: 'cust-1' } });
    await waitFor(() => expect(urlsWritten().some((u) => /[?&]party=cust-1/.test(u))).toBe(true));
  });

  it('drops party from the URL when the picker is cleared', async () => {
    url.search = 'party=cust-1&cost=has';
    service.getCostingRows.mockResolvedValue(partyEnvelope());
    mount();
    await screen.findByText('CGB9032B');
    fireEvent.change(screen.getByLabelText('Party'), { target: { value: '' } });
    await waitFor(() => expect(urlsWritten().length).toBeGreaterThan(0));
    const written = urlsWritten().at(-1)!;
    expect(written).not.toMatch(/party=/);
    expect(written).toMatch(/cost=has/);
  });

  it('offers one-line "NAME (CODE)" options and searches the shared customer select by what is typed', async () => {
    mount();
    await screen.findByText('CGB9032B');
    const party = screen.getByLabelText('Party');
    await waitFor(() => expect(within(party).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Company standard', 'RELATED - BATHPLUS SDN BHD (304-R017)', 'OTHER DEBTOR (304-R018)',
    ]));
    fireEvent.change(screen.getByLabelText('Party search'), { target: { value: 'bath' } });
    await waitFor(() => expect(customers.searchCustomersSelect).toHaveBeenCalledWith('bath', 0));
    await waitFor(() => expect(within(party).queryByText(/OTHER DEBTOR/)).toBeNull());
    expect(within(party).getByText('RELATED - BATHPLUS SDN BHD (304-R017)')).toBeTruthy();
  });
});

describe('Filters (AC-CG-07)', () => {
  it('opens with nothing narrowing the list and Cost empty', async () => {
    mount();
    await screen.findByText('CGB9032B');
    expect(service.getCostingRows.mock.calls[0][0].cost ?? undefined).toBeUndefined();
    openFilters();
    const cost = (await screen.findByLabelText('Cost')) as HTMLSelectElement;
    expect(Array.from(cost.selectedOptions)).toHaveLength(0);
    expect(Array.from(cost.options).map((o) => o.textContent)).toEqual(['Has cost', 'No cost']);
  });

  it('turning Has cost on writes cost=has to the URL', async () => {
    mount();
    await screen.findByText('CGB9032B');
    openFilters();
    const cost = (await screen.findByLabelText('Cost')) as HTMLSelectElement;
    Array.from(cost.options).find((o) => o.value === 'has')!.selected = true;
    fireEvent.change(cost);
    await waitFor(() => expect(urlsWritten().some((u) => /cost=has/.test(u))).toBe(true));
  });

  it('cost=has narrows the request, cost=none asks for the costless, both is no narrowing', async () => {
    url.search = 'cost=has';
    const first = mount();
    await screen.findByText('CGB9032B');
    expect(lastParams().cost).toBe('has');
    first.unmount();
    url.search = 'cost=none';
    const second = mount();
    await screen.findByText('CGB9032B');
    expect(lastParams().cost).toBe('none');
    second.unmount();
    service.getCostingRows.mockClear();
    url.search = 'cost=has,none';
    mount();
    await screen.findByText('CGB9032B');
    expect(lastParams().cost ?? undefined).toBeUndefined();
  });

  it('is the standard pattern: a labelled multi-select per filter', async () => {
    mount();
    await screen.findByText('CGB9032B');
    openFilters();
    for (const label of ['Category', 'Brand', 'Cost method', 'Cost']) {
      expect((await screen.findByLabelText(label)).tagName).toBe('SELECT');
    }
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('shows a chip per active filter, each with its own clear', async () => {
    url.search = 'category=cat-1&method=average&cost=none';
    mount();
    await screen.findByText('CGB9032B');
    expect(screen.getByText('Category: Ceramics')).toBeTruthy();
    expect(screen.getByText('Cost method: Average of supplier prices')).toBeTruthy();
    expect(screen.getByText('Cost: No cost')).toBeTruthy();
    expect(screen.queryByText(/^Brand:/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Clear filter: Category: Ceramics' }));
    await waitFor(() => expect(urlsWritten().length).toBeGreaterThan(0));
    const written = urlsWritten().at(-1)!;
    expect(written).not.toMatch(/category=/);
    expect(written).toMatch(/method=average/);
  });

  it('puts As of in the toolbar row as the shared date picker, defaulting to the rows date', async () => {
    mount();
    await screen.findByText('CGB9032B');
    const slot = screen.getByTestId('costing-search-slot');
    expect((within(slot).getByLabelText('As of') as HTMLInputElement).value).toBe('11/11/2026');
    openFilters();
    await screen.findByLabelText('Category');
    expect(screen.queryByLabelText('As of', { selector: '#costing-as-of' })).toBeNull();
  });

  it('maps category, brand, method and as_of from the URL onto the request', async () => {
    url.search = 'category=cat-1,cat-2&brand=b1&method=average&as_of=2026-10-01';
    mount();
    await screen.findByText('CGB9032B');
    const p = lastParams();
    expect(p.category_id).toBe('cat-1,cat-2');
    expect(p.brand_id).toBe('b1');
    expect(p.cost_method).toBe('average');
    expect(p.as_of).toBe('2026-10-01');
  });

  it('writes a picked Category to the URL as category=', async () => {
    mount();
    await screen.findByText('CGB9032B');
    openFilters();
    const category = (await screen.findByLabelText('Category')) as HTMLSelectElement;
    const option = Array.from(category.options).find((o) => o.value === 'cat-1')!;
    option.selected = true;
    fireEvent.change(category);
    await waitFor(() => expect(urlsWritten().some((u) => /category=cat-1/.test(u))).toBe(true));
  });

  it('sends the search text as q', async () => {
    mount();
    await screen.findByText('CGB9032B');
    fireEvent.change(screen.getByPlaceholderText('Search code or name'), { target: { value: 'WB 245' } });
    await waitFor(() => expect(lastParams().query).toBe('WB 245'));
  });
});

describe('A party without a profile (D2)', () => {
  const noProfile = () =>
    partyEnvelope([], {
      party: { ...PARTY, has_profile: false, markup_pct: null, product_count: 0, is_active: null },
      total: 0,
    });

  it('offers Set up costing in the header to someone who can manage, and it opens the profile dialog', async () => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(noProfile());
    mount();
    const btn = await within(screen.getByTestId('header-actions')).findByRole('button', { name: 'Set up costing' });
    fireEvent.click(btn);
    expect(await screen.findByRole('dialog')).toBeTruthy();
    expect(screen.getByLabelText('Party mark-up (%)')).toBeTruthy();
  });

  it('shows no Set up costing without manage, nor for a party that has a profile', async () => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(noProfile());
    perms.granted = new Set(['products.cost.view']);
    const { unmount } = mount();
    await screen.findByText('This party has no costing profile yet');
    expect(within(screen.getByTestId('header-actions')).queryByRole('button', { name: 'Set up costing' })).toBeNull();
    unmount();

    perms.granted = new Set(['products.cost.view', 'products.party_costing.manage']);
    service.getCostingRows.mockResolvedValue(partyEnvelope());
    mount();
    await screen.findByText('CGB9032B');
    expect(within(screen.getByTestId('header-actions')).queryByRole('button', { name: 'Set up costing' })).toBeNull();
  });
});

describe('Every column sorts on the server (round 5)', () => {
  const SORT_OF: Record<string, string> = {
    Category: 'category_name', Code: 'product_code', Name: 'product_name', Supplier: 'supplier_name',
    Cost: 'unit_cost', Rate: 'units_per_base', SST: 'sst_factor', Transport: 'transport',
    'Landing (RM)': 'landing', 'Cost method': 'cost_method', 'Mark-up': 'markup_pct',
    'Final (RM)': 'final', 'List price (AutoCount)': 'list_price', Margin: 'margin_pct',
  };

  it('every header has a sort control that puts its key in the request', async () => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(partyEnvelope());
    mount();
    await screen.findByText('CGB9032B');
    expect(Object.keys(SORT_OF)).toEqual([...STANDARD_HEADERS, 'Margin'].sort((a, b) =>
      Object.keys(SORT_OF).indexOf(a) - Object.keys(SORT_OF).indexOf(b)));
    for (const [title, key] of Object.entries(SORT_OF)) {
      const header = screen.getAllByRole('columnheader').find((h) => h.textContent?.trim() === title)!;
      fireEvent.click(within(header).getByRole('button', { name: title }));
      await waitFor(() => expect(lastParams().sort).toBe(key));
      expect(lastParams().dir).toBe('asc');
    }
    // a second press on the same header turns it round
    const margin = screen.getAllByRole('columnheader').find((h) => h.textContent?.trim() === 'Margin')!;
    fireEvent.click(within(margin).getByRole('button', { name: 'Margin' }));
    await waitFor(() => expect(lastParams().dir).toBe('desc'));
  });
});

describe('Round 5 review', () => {
  it('the supplier sub-grid sorts: a header press orders the suppliers and a second reverses them', async () => {
    mount();
    await screen.findByText('CGB9032B');
    fireEvent.click(screen.getByRole('button', { name: 'Show suppliers for CGB9032B' }));
    const grid = await screen.findByTestId('costing-supplier-grid');
    await within(grid).findByText('SUP-B07');
    const order = () => within(grid).getAllByText(/^SUP-/).map((n) => n.textContent);
    const press = () => fireEvent.click(within(grid).getByRole('button', { name: 'Cost' }));
    press();
    await waitFor(() => expect(order()).toEqual(['SUP-A01', 'SUP-B07', 'SUP-L02']));
    press();
    await waitFor(() => expect(order()).toEqual(['SUP-L02', 'SUP-B07', 'SUP-A01']));
  });

  it('changing As of writes the ISO date to the URL', async () => {
    mount();
    await screen.findByText('CGB9032B');
    const input = within(screen.getByTestId('costing-search-slot')).getByLabelText('As of');
    fireEvent.change(input, { target: { value: '15/10/2026' } });
    fireEvent.blur(input);
    await waitFor(() => expect(urlsWritten().some((u) => /as_of=2026-10-15/.test(u))).toBe(true));
  });

  it('names the party in the picker before the rows arrive', async () => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockReturnValue(new Promise(() => {}));
    customers.searchCustomersSelect.mockResolvedValue([]); // not in the first page: the label must come from the read
    mount();
    const party = screen.getByLabelText('Party') as HTMLSelectElement;
    await waitFor(() => expect(party.value).toBe('cust-1'));
    expect(within(party).getByText('RELATED - BATHPLUS SDN BHD (304-R017)')).toBeTruthy();
  });

  it('the party select is clearable: its empty option exists only when it is', async () => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(partyEnvelope());
    mount();
    await screen.findByText('CGB9032B');
    expect(within(screen.getByLabelText('Party')).getByText('Company standard')).toBeTruthy();
  });
});

describe('Supplier name and no selling price (round 5)', () => {
  it('shows the supplier NAME, truncated, with "NAME (CODE)" as its title', async () => {
    mount();
    await screen.findByText('CGB9032B');
    const cell = within(rowOf('CGB9032B')).getByText('Supplier A');
    expect(cell.getAttribute('title')).toBe('Supplier A (SUP-A01)');
    expect(cell.className).toMatch(/truncate/);
    expect(within(rowOf('CGB9032B')).queryByText('SUP-A01')).toBeNull();
  });

  const noPrice = (over: Record<string, unknown> = {}) => costingRow({
    product_code: 'NP-1xx', product_name: 'Unpriced', list_price: null, markup_pct: null, markup_source: 'achieved',
    final: null, margin_pct: null, reasons: [{ code: 'no_list_price' }], party_product_id: null, ...over,
  });

  it('company standard: a landing but no selling price shows "-" and "No list price", never -100 %', async () => {
    service.getCostingRows.mockResolvedValue(standardEnvelope([noPrice()]));
    mount();
    await screen.findByText('NP-1xx');
    const tr = rowOf('NP-1xx');
    expect(within(tr).getByText('No list price')).toBeTruthy();
    expect(within(tr).getByText('31.72')).toBeTruthy();
    expect(tr.textContent).not.toMatch(/-100/);
  });

  it('party view: the margin is "-" with the reason, never -100 %', async () => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(partyEnvelope([noPrice({ markup_pct: 8, markup_source: 'party', final: 34.25625, party_product_id: 'cpp-9' })]));
    mount();
    await screen.findByText('NP-1xx');
    const tr = rowOf('NP-1xx');
    expect(within(tr).getByText('No list price')).toBeTruthy();
    expect(within(tr).getByText('34.26')).toBeTruthy();
    expect(tr.textContent).not.toMatch(/-100/);
  });
});

describe('Toolbar actions (AC-CG-09, AC-CG-10, AC-CG-12)', () => {
  it('Export downloads with the current party and filters', async () => {
    url.search = 'party=cust-1&cost=has';
    service.getCostingRows.mockResolvedValue(partyEnvelope());
    mount();
    await screen.findByText('CGB9032B');
    await pressAction('Export');
    await waitFor(() => expect(service.exportCosting).toHaveBeenCalledTimes(1));
    const sent = service.exportCosting.mock.calls[0][0] as Params;
    expect(sent.party_id).toBe('cust-1');
    expect(sent.cost).toBe('has');
  });

  it('Export is there in the company standard view too', async () => {
    mount();
    await screen.findByText('CGB9032B');
    await pressAction('Export');
    await waitFor(() => expect(service.exportCosting).toHaveBeenCalledTimes(1));
    expect(service.exportCosting.mock.calls[0][0].party_id ?? undefined).toBeUndefined();
  });

  it('has no Import anywhere, in either view', async () => {
    mount();
    await screen.findByText('CGB9032B');
    expect(document.body.textContent).not.toMatch(/import/i);
    expect(screen.queryByRole('button', { name: /import/i })).toBeNull();
  });

  it('offers Add products in the party view with manage', async () => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(partyEnvelope());
    mount();
    await screen.findByText('CGB9032B');
    fireEvent.keyDown(screen.getByRole('button', { name: 'Actions' }), { key: 'Enter' });
    expect(await screen.findByRole('menuitem', { name: 'Add products' })).toBeTruthy();
  });

  it('has no Add products in the company standard view', async () => {
    mount();
    await screen.findByText('CGB9032B');
    expect(screen.queryByText('Add products')).toBeNull();
  });

  it('has no Add products without products.party_costing.manage', async () => {
    perms.granted = new Set(['products.cost.view']);
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(partyEnvelope());
    mount();
    await screen.findByText('CGB9032B');
    expect(screen.queryByText('Add products')).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Add products' })).toBeNull();
  });
});

describe('Permissions (AC-CG-01, AC-CG-08)', () => {
  it('shows Settings and the primary Edit to someone who can manage', async () => {
    mount();
    await screen.findByText('CGB9032B');
    const actions = within(screen.getByTestId('header-actions'));
    expect(actions.getByRole('button', { name: 'Settings' })).toBeTruthy();
    expect(actions.getByRole('button', { name: 'Edit' })).toBeTruthy();
  });

  it('hides Edit without products.party_costing.manage but keeps the page and Settings', async () => {
    perms.granted = new Set(['products.cost.view']);
    mount();
    await screen.findByText('CGB9032B');
    const actions = within(screen.getByTestId('header-actions'));
    expect(actions.queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(actions.getByRole('button', { name: 'Settings' })).toBeTruthy();
  });

  it('renders no costing content and asks for none without products.cost.view', async () => {
    perms.granted = new Set(['products.party_costing.manage']);
    mount();
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByText('CGB9032B')).toBeNull();
    expect(screen.queryByText('Landing (RM)')).toBeNull();
    expect(service.getCostingRows).not.toHaveBeenCalled();
  });

  it('Settings opens the settings dialog', async () => {
    mount();
    await screen.findByText('CGB9032B');
    fireEvent.click(within(screen.getByTestId('header-actions')).getByRole('button', { name: 'Settings' }));
    expect(await screen.findByRole('dialog')).toBeTruthy();
  });
});

describe('Row expand and row menu (AC-CG-06, AC-CG-11, AC-CG-12)', () => {
  it('expands to the supplier sub-grid with Margin if bought here in the party view', async () => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(partyEnvelope());
    mount();
    await screen.findByText('CGB9032B');
    fireEvent.click(screen.getByRole('button', { name: 'Show suppliers for CGB9032B' }));
    await waitFor(() => expect(service.getCostingRowSuppliers).toHaveBeenCalledWith(
      'p-wb245', expect.objectContaining({ party_id: 'cust-1' }),
    ));
    expect(await screen.findByText('Margin if bought here')).toBeTruthy();
    for (const h of ['Primary', 'Lead time']) expect(screen.getAllByText(h).length).toBeGreaterThan(0);
    expect(await screen.findByText('SUP-B07')).toBeTruthy();
    expect(screen.getByText(/114\.35\s?%/)).toBeTruthy();
    expect(screen.getByText(/34\.96\s?%/)).toBeTruthy();
  });

  it('says Mark-up if bought here in the company standard view', async () => {
    mount();
    await screen.findByText('CGB9032B');
    fireEvent.click(screen.getByRole('button', { name: 'Show suppliers for CGB9032B' }));
    expect(await screen.findByText('Mark-up if bought here')).toBeTruthy();
    expect(screen.queryByText('Margin if bought here')).toBeNull();
  });

  it('History reads the row and the party and lists who changed what', async () => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(partyEnvelope());
    mount();
    await screen.findByText('CGB9032B');
    fireEvent.keyDown(screen.getByRole('button', { name: 'CGB9032B actions' }), { key: 'Enter' });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'History' }));
    await waitFor(() => expect(service.getCostingRowHistory).toHaveBeenCalledWith('p-wb245', 'cust-1'));
    expect(await screen.findByText(/Hana Tester/)).toBeTruthy();
  });

  it('History in the company standard view passes no party', async () => {
    mount();
    await screen.findByText('CGB9032B');
    fireEvent.keyDown(screen.getByRole('button', { name: 'CGB9032B actions' }), { key: 'Enter' });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'History' }));
    await waitFor(() => expect(service.getCostingRowHistory).toHaveBeenCalledTimes(1));
    expect(service.getCostingRowHistory.mock.calls[0][0]).toBe('p-wb245');
    expect(service.getCostingRowHistory.mock.calls[0][1] ?? undefined).toBeUndefined();
  });

  it('offers Remove from party only in the party view with manage', async () => {
    url.search = 'party=cust-1';
    service.getCostingRows.mockResolvedValue(partyEnvelope());
    const { unmount } = mount();
    await screen.findByText('CGB9032B');
    fireEvent.keyDown(screen.getByRole('button', { name: 'CGB9032B actions' }), { key: 'Enter' });
    expect(await screen.findByRole('menuitem', { name: 'Remove from party' })).toBeTruthy();
    unmount();

    url.search = '';
    service.getCostingRows.mockResolvedValue(standardEnvelope());
    mount();
    await screen.findByText('CGB9032B');
    fireEvent.keyDown(screen.getByRole('button', { name: 'CGB9032B actions' }), { key: 'Enter' });
    await screen.findByRole('menuitem', { name: 'History' });
    expect(screen.queryByRole('menuitem', { name: 'Remove from party' })).toBeNull();
  });
});

describe('Loading and error (states)', () => {
  it('shows no rows and no crash while loading', () => {
    service.getCostingRows.mockReturnValue(new Promise(() => {}));
    mount();
    expect(screen.getByRole('heading', { name: 'Costing' })).toBeTruthy();
    expect(screen.queryByText('CGB9032B')).toBeNull();
  });

  it('shows the server message when the rows fail to load', async () => {
    service.getCostingRows.mockRejectedValue(new Error('Costing exploded'));
    mount();
    expect(await screen.findByText(/Costing exploded/)).toBeTruthy();
  });
});
