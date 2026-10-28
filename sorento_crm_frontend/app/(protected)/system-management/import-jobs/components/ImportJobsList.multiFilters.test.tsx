/**
 * FILTER-MULTISELECT PR7: Import jobs Type and Status are multi dropdowns (they were text boxes); two values reach
 * the request comma-joined and the text boxes are gone.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
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
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/x',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));

const useImportJobs = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useImportJobs', () => ({
  useImportJobs: (...a: unknown[]) => useImportJobs(...a),
  useCancelImportJob: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('../services/importJobService', () => ({ getImportJob: vi.fn() }));
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


import ImportJobsList from './ImportJobsList';

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : [String(v ?? '')]).flatMap((s) => s.split(',')).map((s) => s.trim()).filter(Boolean).sort();
const multis = () => screen.queryAllByRole('listbox').filter((el) => el.hasAttribute('multiple')) as HTMLSelectElement[];
async function multiAt(index: number) {
  await waitFor(() => {
    if (multis().length <= index) throw new Error(`no multi control at position ${index}, found ${multis().length}`);
  });
  return multis()[index];
}
const firstTwo = (el: HTMLSelectElement) => Array.from(el.options).slice(0, 2).map((o) => o.value);
function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
}
afterEach(() => cleanup());

const last = () => useImportJobs.mock.calls.at(-1)?.[0] as Record<string, unknown>;
beforeEach(() => {
  vi.clearAllMocks();
  useImportJobs.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 } }, isLoading: false, isPlaceholderData: false,
    refetch: vi.fn(), isFetching: false, error: null,
  });
});
function open() {
  render(<QueryClientProvider client={client()}><ImportJobsList /></QueryClientProvider>);
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), { button: 0, ctrlKey: false });
}

describe('Import jobs - multi Type and Status', () => {
  it('the text boxes are gone', async () => {
    open();
    await waitFor(() => expect(screen.queryByPlaceholderText('Filter by type...')).toBeNull());
    expect(screen.queryByPlaceholderText('Filter by status...')).toBeNull();
  });

  it('two types reach the request comma-joined', async () => {
    const user = userEvent.setup();
    open();
    const el = await multiAt(0);
    await user.selectOptions(el, firstTwo(el));
    await waitFor(() => expect(setOf(last().job_type)).toEqual(firstTwo(el).sort()));
  });

  it('two statuses reach the request comma-joined', async () => {
    const user = userEvent.setup();
    open();
    const el = await multiAt(1);
    await user.selectOptions(el, firstTwo(el));
    await waitFor(() => expect(setOf(last().status)).toEqual(firstTwo(el).sort()));
  });

  // Browser pass 28 Oct: the Type dropdown replaced a free text box, so every job type the backend
  // writes must be offered or its jobs can no longer be filtered. These are the types missing from
  // the label map at the time (job_type literals in sorento_crm_backend/app, autocount_pull_service.py:48,70).
  it('offers every job type the backend creates', async () => {
    open();
    const el = await multiAt(0);
    const offered = Array.from(el.options).map((o) => o.value);
    for (const type of [
      'attachment_bulk_download',
      'catalogue_photo_read',
      'container_status_import',
      'delivery_order_detail_import',
      'project_series_import',
      'warehouse_import',
      'autocount_products_pull',
      'autocount_products_apply',
      'autocount_stock_pull',
      'autocount_stock_apply',
      'autocount_delivery_orders_pull',
      'autocount_delivery_orders_apply',
      'autocount_grn_pull',
      'autocount_grn_apply',
    ]) {
      expect(offered).toContain(type);
    }
  });
});
