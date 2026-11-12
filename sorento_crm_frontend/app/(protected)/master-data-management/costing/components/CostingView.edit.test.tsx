/**
 * Products > Costing, Edit / Save in place (lane PRODUCT-COSTING, Phase 2 red tests F2; UAC AC-CG-08).
 * As Sales > Targets: Edit is the one primary header button, Cancel and Save replace it, one Save
 * sends ONE PATCH of only the changed cells, a failure keeps Edit open with the typed values.
 *
 * ASSUMED NAMES (in addition to CostingView.test.tsx; CONTRACT section 5):
 *  - Inputs by accessible name: `Mark-up for {code}` (number, party view only), `Transport for {code}`
 *    (select; option values `add` / `multiply`, empty = Category rule), `Transport value for {code}`
 *    (number), `Cost method for {code}` (select; option values primary / selected / average / last_po,
 *    empty = Company default), `Supplier for {code}` (select, appears when the method is `selected`;
 *    option values are the supplier_id from getCostingRowSuppliers).
 *  - A cleared Mark-up sends `markup_pct: null`; a cleared select sends null for its field(s); a
 *    transport change sends `transport_mode` and `transport_value` together.
 *  - saveCostingRows(body) body = { party_id, changes: [{ product_id, ...changed keys only }] }.
 *  - On success the page leaves edit, toasts via toast.success, and refetches the rows. On failure it
 *    calls toast.error and stays in edit with the typed values.
 *  - Mark-up input of a row whose markup_source is "row" starts at that value; an inherited one starts empty.
 *  - Landing, Final and Margin recompute from the draft: landing = unit_cost * rate_to_base * sst_factor,
 *    then + / x transport; final = landing * (1 + markup / 100); margin = (list - final) / final * 100.
 *    Displayed to 2 dp half-up.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  PARTY, SUPPLIERS, costingRow, partyEnvelope, standardEnvelope,
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
const rowOf = (code: string) => screen.getByText(code).closest('tr') as HTMLElement;
const headerBtn = (name: string) => within(screen.getByTestId('header-actions')).queryByRole('button', { name });
const typeInto = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
const inputValue = (label: string) => (screen.getByLabelText(label) as HTMLInputElement).value;

async function startEdit() {
  await screen.findByText('CGB9032B');
  fireEvent.click(headerBtn('Edit')!);
  await screen.findByLabelText('Transport for CGB9032B');
}
const saveBody = () => service.saveCostingRows.mock.calls[0][0] as { party_id: string | null; changes: Params[] };

beforeEach(() => {
  vi.clearAllMocks();
  router.push.mockReset();
  router.replace.mockReset();
  url.search = 'party=cust-1';
  perms.granted = new Set(['products.cost.view', 'products.party_costing.manage']);
  service.getCostingRows.mockResolvedValue(partyEnvelope());
  service.getCostingRowSuppliers.mockResolvedValue(SUPPLIERS);
  service.saveCostingRows.mockResolvedValue({ updated: 1 });
  service.getCostingRowHistory.mockResolvedValue({ data: [] });
  service.getCostingSettings.mockResolvedValue({ sst_factor: 1.1, default_method: 'primary' });
  service.getCategoryRules.mockResolvedValue({ data: [] });
  service.getExchangeRates.mockResolvedValue({ data: [] });
  service.getParty.mockResolvedValue(PARTY);
  customers.searchCustomersSelect.mockImplementation(async (q: string) =>
    [{ value: 'cust-1', label: '304-R017 - RELATED - BATHPLUS SDN BHD' },
     { value: 'cust-2', label: '304-R018 - OTHER DEBTOR' }].filter((c) => !q || c.label.toLowerCase().includes(q.toLowerCase())));
});

describe('entering and leaving edit', () => {
  it('Edit swaps to Cancel and Save in the header and turns the cells into inputs', async () => {
    mount();
    await startEdit();
    expect(headerBtn('Edit')).toBeNull();
    expect(headerBtn('Cancel')).toBeTruthy();
    expect(headerBtn('Save')).toBeTruthy();
    for (const label of ['Mark-up for CGB9032B', 'Transport for CGB9032B', 'Transport value for CGB9032B', 'Cost method for CGB9032B']) {
      expect(screen.getByLabelText(label)).toBeTruthy();
    }
    expect(screen.getByLabelText('Mark-up for JZ-1xx')).toBeTruthy();
  });

  it('keeps the columns: Cost, Rate and SST stay read-only text', async () => {
    mount();
    await startEdit();
    const tr = rowOf('CGB9032B');
    expect(within(tr).getByText('CNY 34.50')).toBeTruthy();
    expect(within(tr).getByText('1.10')).toBeTruthy();
    expect(screen.queryByLabelText('Cost for CGB9032B')).toBeNull();
    expect(screen.queryByLabelText('Rate for CGB9032B')).toBeNull();
    expect(screen.queryByLabelText('SST for CGB9032B')).toBeNull();
  });

  it('says transport and method edits apply to every party', async () => {
    mount();
    await startEdit();
    expect(screen.getAllByText(/applies to every party/i).length).toBeGreaterThan(0);
  });

  it('shows the hint nowhere before Edit', async () => {
    mount();
    await screen.findByText('CGB9032B');
    expect(screen.queryByText(/applies to every party/i)).toBeNull();
  });

  it('starts a row-level mark-up at its value and an inherited one empty', async () => {
    mount();
    await startEdit();
    expect(inputValue('Mark-up for JZ-1xx')).toBe('10');
    expect(inputValue('Mark-up for CGB9032B')).toBe('');
  });

  it('has no Mark-up input in the company standard view, but Transport and Cost method stay', async () => {
    url.search = '';
    service.getCostingRows.mockResolvedValue(standardEnvelope());
    mount();
    await startEdit();
    expect(screen.queryByLabelText('Mark-up for CGB9032B')).toBeNull();
    expect(screen.getByLabelText('Transport for CGB9032B')).toBeTruthy();
    expect(screen.getByLabelText('Cost method for CGB9032B')).toBeTruthy();
  });

  it('Cancel discards the draft and calls nothing', async () => {
    mount();
    await startEdit();
    typeInto('Mark-up for JZ-1xx', '12');
    fireEvent.click(headerBtn('Cancel')!);
    expect(service.saveCostingRows).not.toHaveBeenCalled();
    expect(headerBtn('Edit')).toBeTruthy();
    expect(headerBtn('Save')).toBeNull();
    fireEvent.click(headerBtn('Edit')!);
    expect(inputValue('Mark-up for JZ-1xx')).toBe('10');
  });

  it('shows no Import and no 0.00 for unknowns while editing', async () => {
    mount();
    await startEdit();
    expect(document.body.textContent).not.toMatch(/import/i);
    expect(rowOf('A-4xx').textContent).not.toMatch(/(^|[^\d.,])0\.00(?!\d)/);
  });
});

describe('recomputing while typing', () => {
  it('a 10% mark-up on WB 245 makes Final 34.89 and Margin 126.42%', async () => {
    mount();
    await startEdit();
    typeInto('Mark-up for CGB9032B', '10');
    const tr = rowOf('CGB9032B');
    await waitFor(() => expect(within(tr).getByText('34.89')).toBeTruthy());
    expect(within(tr).getByText(/126\.42\s?%/)).toBeTruthy();
    expect(within(tr).getByText('31.72')).toBeTruthy();
  });

  it('a flat RM 10 transport makes Landing 33.72 and Final 36.42 at the party 8%', async () => {
    mount();
    await startEdit();
    typeInto('Transport for CGB9032B', 'add');
    typeInto('Transport value for CGB9032B', '10');
    const tr = rowOf('CGB9032B');
    await waitFor(() => expect(within(tr).getByText('33.72')).toBeTruthy());
    expect(within(tr).getByText('36.42')).toBeTruthy();
  });

  it('a multiply 1.07 transport applies the factor to the SST-inclusive cost', async () => {
    mount();
    await startEdit();
    typeInto('Transport for CGB9032B', 'multiply');
    typeInto('Transport value for CGB9032B', '1.07');
    // 34.5 / 1.6 * 1.1 * 1.07 = 25.3790625 -> 25.38; final at 8% = 27.4094... -> 27.41
    const tr = rowOf('CGB9032B');
    await waitFor(() => expect(within(tr).getByText('25.38')).toBeTruthy());
    expect(within(tr).getByText('27.41')).toBeTruthy();
  });
});

describe('typing keeps focus (D1)', () => {
  it('types 12 key by key into a mark-up and keeps the focus and the value', async () => {
    mount();
    await startEdit();
    const input = screen.getByLabelText('Mark-up for CGB9032B') as HTMLInputElement;
    const user = userEvent.setup();
    await user.click(input);
    await user.keyboard('12');
    const after = screen.getByLabelText('Mark-up for CGB9032B') as HTMLInputElement;
    expect(after).toBe(input); // the same node: nothing remounted under the typist
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe('12');
    fireEvent.click(headerBtn('Save')!);
    await waitFor(() => expect(service.saveCostingRows).toHaveBeenCalledTimes(1));
    expect(saveBody().changes).toEqual([{ product_id: 'p-wb245', markup_pct: 12 }]);
  });

  it('keeps focus while typing a transport value too', async () => {
    mount();
    await startEdit();
    typeInto('Transport for CGB9032B', 'add');
    const input = screen.getByLabelText('Transport value for CGB9032B') as HTMLInputElement;
    const user = userEvent.setup();
    await user.click(input);
    await user.keyboard('10');
    expect(screen.getByLabelText('Transport value for CGB9032B')).toBe(input);
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe('10');
  });
});

describe('clearing a transport override', () => {
  it('falls back to the category rule: WB 245 +20 override cleared shows Landing 31.72', async () => {
    service.getCostingRows.mockResolvedValue(partyEnvelope([
      costingRow({
        transport_source: 'product', transport_mode: 'add', transport_value: 20, landing: 43.71875,
        final: 47.2162, margin_pct: 67.3, category_transport_mode: 'add', category_transport_value: 8,
      }),
    ]));
    mount();
    await startEdit();
    const tr = rowOf('CGB9032B');
    expect(within(tr).getByText('43.72')).toBeTruthy();
    typeInto('Transport for CGB9032B', '');
    typeInto('Transport value for CGB9032B', '');
    await waitFor(() => expect(within(tr).getByText('31.72')).toBeTruthy());
    expect(within(tr).getByText('34.26')).toBeTruthy();
  });
});

describe('Save (one PATCH, only changed cells)', () => {
  it('sends one request holding only the changed mark-up', async () => {
    mount();
    await startEdit();
    typeInto('Mark-up for CGB9032B', '10');
    fireEvent.click(headerBtn('Save')!);
    await waitFor(() => expect(service.saveCostingRows).toHaveBeenCalledTimes(1));
    expect(saveBody()).toEqual({ party_id: 'cust-1', changes: [{ product_id: 'p-wb245', markup_pct: 10 }] });
  });

  it('batches two products into one request', async () => {
    mount();
    await startEdit();
    typeInto('Mark-up for CGB9032B', '9');
    typeInto('Mark-up for JZ-1xx', '12');
    fireEvent.click(headerBtn('Save')!);
    await waitFor(() => expect(service.saveCostingRows).toHaveBeenCalledTimes(1));
    expect(saveBody().changes).toHaveLength(2);
    expect(saveBody().changes).toEqual(expect.arrayContaining([
      { product_id: 'p-wb245', markup_pct: 9 },
      { product_id: 'p-jz', markup_pct: 12 },
    ]));
  });

  it('clearing a row mark-up sends null so the party mark-up applies again', async () => {
    mount();
    await startEdit();
    typeInto('Mark-up for JZ-1xx', '');
    fireEvent.click(headerBtn('Save')!);
    await waitFor(() => expect(service.saveCostingRows).toHaveBeenCalledTimes(1));
    expect(saveBody().changes).toEqual([{ product_id: 'p-jz', markup_pct: null }]);
  });

  it('sends a transport override as mode and value together', async () => {
    mount();
    await startEdit();
    typeInto('Transport for CGB9032B', 'add');
    typeInto('Transport value for CGB9032B', '10');
    fireEvent.click(headerBtn('Save')!);
    await waitFor(() => expect(service.saveCostingRows).toHaveBeenCalledTimes(1));
    expect(saveBody().changes).toEqual([{ product_id: 'p-wb245', transport_mode: 'add', transport_value: 10 }]);
  });

  it('sends a changed cost method on its own', async () => {
    mount();
    await startEdit();
    typeInto('Cost method for CGB9032B', 'average');
    fireEvent.click(headerBtn('Save')!);
    await waitFor(() => expect(service.saveCostingRows).toHaveBeenCalledTimes(1));
    expect(saveBody().changes).toEqual([{ product_id: 'p-wb245', cost_method: 'average' }]);
  });

  it('Selected supplier shows a Supplier picker and sends the chosen supplier with the method', async () => {
    mount();
    await startEdit();
    expect(screen.queryByLabelText('Supplier for CGB9032B')).toBeNull();
    typeInto('Cost method for CGB9032B', 'selected');
    const supplier = await screen.findByLabelText('Supplier for CGB9032B');
    await waitFor(() => expect(within(supplier).getByText(/SUP-B07/)).toBeTruthy());
    typeInto('Supplier for CGB9032B', 's-b');
    fireEvent.click(headerBtn('Save')!);
    await waitFor(() => expect(service.saveCostingRows).toHaveBeenCalledTimes(1));
    expect(saveBody().changes).toEqual([
      { product_id: 'p-wb245', cost_method: 'selected', cost_method_supplier_id: 's-b' },
    ]);
  });

  it('on success leaves edit, toasts and reloads the rows', async () => {
    mount();
    await startEdit();
    typeInto('Mark-up for CGB9032B', '10');
    const before = service.getCostingRows.mock.calls.length;
    fireEvent.click(headerBtn('Save')!);
    await waitFor(() => expect(headerBtn('Edit')).toBeTruthy());
    expect(headerBtn('Save')).toBeNull();
    expect(toast.success).toHaveBeenCalled();
    await waitFor(() => expect(service.getCostingRows.mock.calls.length).toBeGreaterThan(before));
  });

  it('on failure stays in edit, keeps the typed value and shows the error', async () => {
    service.saveCostingRows.mockRejectedValue(new Error('Mark-up needs a party product'));
    mount();
    await startEdit();
    typeInto('Mark-up for CGB9032B', '10');
    fireEvent.click(headerBtn('Save')!);
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(headerBtn('Save')).toBeTruthy();
    expect(headerBtn('Edit')).toBeNull();
    expect(inputValue('Mark-up for CGB9032B')).toBe('10');
  });

  it('Save with nothing changed does not send a request', async () => {
    mount();
    await startEdit();
    fireEvent.click(headerBtn('Save')!);
    await new Promise((r) => setTimeout(r, 30));
    expect(service.saveCostingRows).not.toHaveBeenCalled();
  });

  it('company standard Save carries party_id null', async () => {
    url.search = '';
    service.getCostingRows.mockResolvedValue(standardEnvelope());
    mount();
    await startEdit();
    typeInto('Cost method for CGB9032B', 'last_po');
    fireEvent.click(headerBtn('Save')!);
    await waitFor(() => expect(service.saveCostingRows).toHaveBeenCalledTimes(1));
    expect(saveBody().party_id ?? null).toBeNull();
    expect(saveBody().changes).toEqual([{ product_id: 'p-wb245', cost_method: 'last_po' }]);
  });
});
