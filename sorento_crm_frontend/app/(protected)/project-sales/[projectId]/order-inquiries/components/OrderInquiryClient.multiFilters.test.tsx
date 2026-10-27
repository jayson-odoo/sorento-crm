/**
 * FILTER-MULTISELECT PR6: the project order inquiry list's Instruction and State filters take several values
 * (OR within a filter); one comma-joined set reaches the service, clearing clears.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listOrderInquiryRows = vi.fn();
const getOrderInquirySummary = vi.fn();
const markOrderInquiryRows = vi.fn();
const downloadOrderInquiryXlsx = vi.fn();
const getProject = vi.fn();
const listingKeys: (string | null | undefined)[] = [];

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/p1/order-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: async () => {}, isLoading: false };
  },
}));

vi.mock('../../../_shared/services/orderInquiryService', () => ({
  listOrderInquiryRows: (...args: unknown[]) => listOrderInquiryRows(...args),
  getOrderInquirySummary: (...args: unknown[]) => getOrderInquirySummary(...args),
  markOrderInquiryRows: (...args: unknown[]) => markOrderInquiryRows(...args),
  getSalesOrderInquiry: vi.fn(),
  downloadOrderInquiryXlsx: (...args: unknown[]) => downloadOrderInquiryXlsx(...args),
}));

vi.mock('../../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../../_shared/services/projectService')
  >();
  return { ...actual, getProject: (...args: unknown[]) => getProject(...args) };
});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

Element.prototype.scrollIntoView = vi.fn();
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

import { OrderInquiryClient } from './OrderInquiryClient';

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => {
  const args = listOrderInquiryRows.mock.calls.at(-1) as unknown[];
  return args.find((a) => a && typeof a === 'object') as Record<string, unknown>;
};
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
function renderClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryClient projectId="p1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listOrderInquiryRows.mockResolvedValue({ data: [], total: 0, page: 1, limit: 25 });
  getOrderInquirySummary.mockResolvedValue({ total: 0, raised: 0, actioned: 0, cancelled: 0 });
  getProject.mockResolvedValue({ id: 'p1', project_code: 'PRJ-0001', title: 'Tuju Residence' });
});

const FILTERS: [string, string, string][] = [
  ['verb', 'ORDER', 'DELAY'],
  ['state', 'raised', 'actioned'],
];

describe('Project order inquiry - multi filters', () => {
  it.each(FILTERS)('%s is a multi control', async (_p, a) => {
    renderClient();
    await waitFor(() => expect(listOrderInquiryRows).toHaveBeenCalled());
    openFilters();
    expect((await box(a)).hasAttribute('multiple')).toBe(true);
  });

  it.each(FILTERS)('%s: two values reach the service as one set', async (param, a, b) => {
    const user = userEvent.setup();
    renderClient();
    await waitFor(() => expect(listOrderInquiryRows).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(lastParams()[param])).toEqual([a, b].sort()));
  });

  it.each(FILTERS)('%s: clearing sends nothing', async (param, a, b) => {
    const user = userEvent.setup();
    renderClient();
    await waitFor(() => expect(listOrderInquiryRows).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(lastParams()[param])).toEqual([a, b].sort()));
    openFilters();
    await user.deselectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(lastParams()[param])).toEqual([]));
  });
});
