/**
 * FILTER-MULTISELECT PR6 review: the OI documents Agent pick (an agent NAME that may hold a comma) reaches the
 * request whole, as one value of a list, never split.
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
const listSpy = vi.fn<(p: Record<string, unknown>) => Promise<{ data: unknown[]; total: number; page: number; limit: number }>>(
  async () => ({ data: [], total: 0, page: 1, limit: 25 }),
);
vi.mock('../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    listOrderInquiryHeaders: (params: Record<string, unknown>) => listSpy(params),
    getOrderInquiryWorklistSummary: vi.fn(async () => ({
      agents: [{ id: 'ag-1', label: 'ZZT Smith, John', rows: 1 }, { id: 'ag-2', label: 'ZZT Plain', rows: 1 }],
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
  fireEvent.pointerDown(screen.getByRole('button', { name: /^filters/i }), { button: 0, ctrlKey: false });
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

const asList = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : v == null || v === '' ? [] : [String(v)]);

describe('Order inquiry documents - an agent name containing a comma', () => {
  it('reaches the request whole', async () => {
    const user = userEvent.setup();
    renderList();
    await waitFor(() => expect(listSpy).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box('ZZT Smith, John'), ['ZZT Smith, John']);
    await waitFor(() => expect(asList(lastParams().agent)).toEqual(['ZZT Smith, John']));
  });

  it('with a plain name it reaches the request as two values', async () => {
    const user = userEvent.setup();
    renderList();
    await waitFor(() => expect(listSpy).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box('ZZT Smith, John'), ['ZZT Smith, John', 'ZZT Plain']);
    await waitFor(() => expect(asList(lastParams().agent).sort()).toEqual(['ZZT Plain', 'ZZT Smith, John']));
  });
});
