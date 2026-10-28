/**
 * FILTER-MULTISELECT PR5: the Proforma invoices list's Supplier and Packing list placement filters take
 * several values (OR within a filter, AND across), to the data hook and in the page URL, and the one chip
 * names every chosen value. An older link holding one value reads back as a one-value filter.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/proforma-invoices',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('../../hooks/useFulfilment', () => ({
  useFulfilmentSuppliers: () => ({
    data: [
      { value: 'sup-1', label: 'ZZT Supplier One' },
      { value: 'sup-2', label: 'ZZT Supplier Two' },
      { value: 'sup-3', label: 'ZZT Supplier Three' },
    ],
  }),
  useContainerSizes: () => ({ data: [], isLoading: false }),
}));
vi.mock('./SupplierDocumentsUploadDialog', () => ({ SupplierDocumentsUploadDialog: () => null }));
vi.mock('./ConvertToPackingListDialog', () => ({ ConvertToPackingListDialog: () => null }));
const listCalls = vi.hoisted(() => [] as unknown[][]);
vi.mock('../../hooks/useProformaInvoices', () => ({
  useProformaInvoices: (...args: unknown[]) => {
    listCalls.push(args);
    return {
      data: {
        data: [{
          id: 'pi-1', supplier_id: 'sup-1', supplier_code: 'ZZT1', supplier_name: 'ZZT Supplier One', pi_number: 'ZZT-PI-001',
          supplier_ref: 'ZZT-REF', invoice_date: '2026-08-01', currency: 'CNY', container_no: 'TEMU1', seal_no: 'S1',
          consignee: 'SORENTO', bl_no: 'BL1', total_amount: 1000, line_count: 5, source_ref: null, block_index: 0,
          uploaded_by: 'ZZT', created_at: '2026-08-01T02:00:00', updated_at: '2026-08-01T02:00:00', total_cbm: 1,
          unmeasured_lines: 0, status: 'current', revision_no: 1, revision_count: 1, adjusted_by: null, adjusted_at: null,
          is_adjusted: false, placement: 'not_converted', placed_qty: 0, total_qty: 500, remaining_qty: 500, packing_lists: [],
        }],
        total: 1,
      },
      isLoading: false,
    };
  },
  useProformaInvoice: () => ({ data: undefined, isLoading: false }),
  useConvertProformaInvoicesToDraftShipment: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useBulkDeleteProformaInvoices: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useProformaInvoicesApplied: () => vi.fn(),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import { ProformaInvoicesView } from './ProformaInvoicesView';

const last = () => listCalls[listCalls.length - 1];
const suppliers = () => setOf(last()[0]);
const placements = () => setOf((last()[1] as Record<string, unknown>).placement);
const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}
const selected = (el: HTMLSelectElement) => Array.from(el.selectedOptions, (o) => o.value).sort();
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ProformaInvoicesView />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT-PI-001');
  await user.click(filtersButton());
}

beforeEach(() => {
  cleanup();
  listCalls.length = 0;
  url.search = '';
});
afterEach(() => cleanup());

describe('Proforma invoices - multi Supplier and Packing list filters', () => {
  it('Supplier and Packing list are multi controls', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await box('sup-1')).hasAttribute('multiple')).toBe(true);
    expect((await box('split')).hasAttribute('multiple')).toBe(true);
  });

  it('two suppliers reach the hook as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('sup-1'), ['sup-1', 'sup-2']);
    await waitFor(() => expect(suppliers()).toEqual(['sup-1', 'sup-2']));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('two placements reach the hook as a set of two, ANDed with the supplier', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('sup-1'), ['sup-3']);
    await user.selectOptions(await box('split'), ['not_converted', 'split']);
    await waitFor(() => {
      expect(suppliers()).toEqual(['sup-3']);
      expect(placements()).toEqual(['not_converted', 'split']);
    });
  });

  it('the chip names every chosen value', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('split'), ['not_converted', 'split']);
    await waitFor(() => expect(placements()).toEqual(['not_converted', 'split']));
    await waitFor(() =>
      expect(screen.getAllByText((_c, el) => !!el && el.children.length === 0 && /Not converted/.test(el.textContent ?? '') && /Split/.test(el.textContent ?? '')).length).toBeGreaterThan(0),
    );
  });

  it('Clear filters drops both multi filters', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('sup-1'), ['sup-1', 'sup-2']);
    await user.selectOptions(await box('split'), ['not_converted', 'split']);
    await waitFor(() => expect(placements()).toEqual(['not_converted', 'split']));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => {
      expect(suppliers()).toEqual([]);
      expect(placements()).toEqual([]);
    });
  });

  it('a link with several values restores both controls and the request', async () => {
    url.search = 'supplier_id=sup-1%2Csup-2&placement=not_converted%2Csplit';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(suppliers()).toEqual(['sup-1', 'sup-2']);
      expect(placements()).toEqual(['not_converted', 'split']);
    });
    expect(selected(await box('sup-1'))).toEqual(['sup-1', 'sup-2']);
    expect(selected(await box('split'))).toEqual(['not_converted', 'split']);
  });

  it('an older link with one supplier and one placement reads back as one-value filters', async () => {
    url.search = 'supplier_id=sup-2&placement=converted';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => {
      expect(suppliers()).toEqual(['sup-2']);
      expect(placements()).toEqual(['converted']);
    });
    expect(selected(await box('sup-1'))).toEqual(['sup-2']);
  });
});
