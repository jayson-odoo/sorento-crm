/**
 * FILTER-MULTISELECT PR6: the order inquiry Documents list's Raised by, Agent and Project filters take several
 * values (OR within a filter); one comma-joined set reaches the service, clearing clears, an old single-value
 * link still reads. Reserve stays single.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

let searchParamsValue = '';
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/order-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'zzt-u1', name: 'ZZT User One' },
    { id: 'zzt-u2', name: 'ZZT User Two' },
  ]),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => false }));
vi.mock('../../_shared/services/orderInquiryReserveService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/orderInquiryReserveService')>();
  return {
    ...actual,
    getReserveStatusSummary: async () => ({
      parked: 0, needs_reserve: 0, notice_parked: 0, reserved: 0, my_parked_requests: 0, my_parked_notices: 0,
    }),
  };
});
const listSpy = vi.fn(async (..._args: unknown[]) => ({ data: [] as unknown[], total: 0, page: 1, limit: 25 }));
vi.mock('../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    listOrderInquiryHeaders: (params: Record<string, unknown>) => listSpy(params),
    getOrderInquiryWorklistSummary: vi.fn(async () => ({
      agents: [{ id: 'ag-1', label: 'ZZT Agent One', rows: 1 }, { id: 'ag-2', label: 'ZZT Agent Two', rows: 1 }],
      projects: [{ id: 'ZZT Alpha', label: 'ZZT Alpha', rows: 1 }, { id: 'ZZT Beta', label: 'ZZT Beta', rows: 1 }],
    })),
  };
});
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


import { OrderInquiryHeadersList } from './OrderInquiryHeadersList';

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => listSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>;
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
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), { button: 0, ctrlKey: false });
}
function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <OrderInquiryHeadersList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsValue = '';
});

// [param sent to the service, two option values]
const FILTERS: [string, string, string][] = [
  ['raised_by', 'zzt-u1', 'zzt-u2'],
  ['agent', 'ZZT Agent One', 'ZZT Agent Two'],
  ['project', 'ZZT Alpha', 'ZZT Beta'],
];

describe('Order inquiry documents - multi filters', () => {
  it.each(FILTERS)('%s is a multi control', async (_p, a) => {
    renderList();
    await waitFor(() => expect(listSpy).toHaveBeenCalled());
    openFilters();
    expect((await box(a)).hasAttribute('multiple')).toBe(true);
  });

  it.each(FILTERS)('%s: two values reach the service as one set', async (param, a, b) => {
    const user = userEvent.setup();
    renderList();
    await waitFor(() => expect(listSpy).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(lastParams()[param])).toEqual([a, b].sort()));
  });

  it.each(FILTERS)('%s: clearing sends nothing', async (param, a, b) => {
    const user = userEvent.setup();
    renderList();
    await waitFor(() => expect(listSpy).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(lastParams()[param])).toEqual([a, b].sort()));
    openFilters();
    await user.deselectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(lastParams()[param])).toEqual([]));
  });

  it('an old link with one value reads as a one-value filter, a joined one as a set', async () => {
    searchParamsValue = 'raised_by=zzt-u1&agent=ZZT Agent One,ZZT Agent Two';
    renderList();
    await waitFor(() => expect(setOf(lastParams()?.raised_by)).toEqual(['zzt-u1']));
    expect(setOf(lastParams().agent)).toEqual(['ZZT Agent One', 'ZZT Agent Two']);
  });

  it('Reserve stays a single select', async () => {
    renderList();
    await waitFor(() => expect(listSpy).toHaveBeenCalled());
    openFilters();
    const el = (await screen.findAllByLabelText('Reserve'))[0] as HTMLSelectElement;
    expect(el.hasAttribute('multiple')).toBe(false);
  });
});
