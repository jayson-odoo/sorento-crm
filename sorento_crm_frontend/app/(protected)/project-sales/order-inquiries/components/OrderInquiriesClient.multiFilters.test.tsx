/**
 * FILTER-MULTISELECT PR6: the order inquiry Lines list's Location, Agent, State, Supplier, Project and
 * Raised by filters take several values (OR within a filter); each rides to the service as one comma-joined
 * set, clearing clears, an old single-value URL or saved view still reads as a one-value filter. Linked,
 * Confirmed and Dead document stay single.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  MOCK_WORKLIST_ROWS,
  MOCK_WORKLIST_SUMMARY,
} from '../../_shared/__mocks__/orderInquiryWorklist';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

const granted = new Set([
  'projects.order_inquiry.action',
  'projects.order_inquiries.acknowledge',
]);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((slug) => granted.has(slug)),
  usePermissions: () => ({
    permissions: [...granted],
    permissionSet: granted,
    isLoading: false,
  }),
}));

const routerReplace = vi.fn();
let currentSearchParams = new URLSearchParams('');

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: (...args: unknown[]) => routerReplace(...args),
  }),
  usePathname: () => '/project-sales/order-inquiries',
  useSearchParams: () => currentSearchParams,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

// Controlled per test (default: nothing stored) - the seam AC-19's "stored blob" case
// drives directly, the same shape `useListingViewPreferences` reads
// (`config.filters`/`config.filtersVersion`).
const getUserListColumnConfig = vi.fn();
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (...args: unknown[]) => getUserListColumnConfig(...args),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, payload: unknown) => ({
    listing_key: listingKey,
    config: payload,
  })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

const listOrderInquiryWorklist = vi.fn();
const getOrderInquiryWorklistSummary = vi.fn();
const exportOrderInquiryWorklistXlsx = vi.fn();
const autoPlaceOrderInquiryRows = vi.fn();
const getUnplaceAllPreview = vi.fn();
const unplaceAllOrderInquiryRows = vi.fn();
const acknowledgeOrderInquiryRows = vi.fn();
const rejectOrderInquiryRows = vi.fn();
const linkNowOrderInquiryRows = vi.fn();
const getOrderInquiryPoCandidates = vi.fn();
const getOrderInquiryUploadJob = vi.fn();
const unplaceOrderInquiryRow = vi.fn();

vi.mock('../../_shared/services/orderInquiryService', () => ({
  listOrderInquiryWorklist: (...args: unknown[]) => listOrderInquiryWorklist(...args),
  getOrderInquiryWorklistSummary: (...args: unknown[]) =>
    getOrderInquiryWorklistSummary(...args),
  exportOrderInquiryWorklistXlsx: (...args: unknown[]) =>
    exportOrderInquiryWorklistXlsx(...args),
  autoPlaceOrderInquiryRows: (...args: unknown[]) => autoPlaceOrderInquiryRows(...args),
  getUnplaceAllPreview: (...args: unknown[]) => getUnplaceAllPreview(...args),
  unplaceAllOrderInquiryRows: (...args: unknown[]) =>
    unplaceAllOrderInquiryRows(...args),
  acknowledgeOrderInquiryRows: (...args: unknown[]) =>
    acknowledgeOrderInquiryRows(...args),
  rejectOrderInquiryRows: (...args: unknown[]) => rejectOrderInquiryRows(...args),
  linkNowOrderInquiryRows: (...args: unknown[]) => linkNowOrderInquiryRows(...args),
  getOrderInquiryPoCandidates: (...args: unknown[]) =>
    getOrderInquiryPoCandidates(...args),
  getOrderInquiryUploadJob: (...args: unknown[]) => getOrderInquiryUploadJob(...args),
  unplaceOrderInquiryRow: (...args: unknown[]) => unplaceOrderInquiryRow(...args),
}));

const getOrderInquiryMatrix = vi.fn();
vi.mock('../../_shared/services/orderInquiryMatrixService', () => ({
  getOrderInquiryMatrix: (...args: unknown[]) => getOrderInquiryMatrix(...args),
}));

vi.mock('../../../scm/reorder/components/OutstandingUploadDialog', () => ({
  OutstandingUploadDialog: () => null,
}));

vi.mock('@/components/upload-activity/useUploadActivity', () => ({
  useUploadActivity: () => ({
    sessions: [],
    badgeCount: 0,
    hasInFlight: false,
    refetch: vi.fn(),
    isLoading: false,
    dismissed: new Set<string>(),
  }),
}));

vi.mock('../../_shared/services/fileDownload', () => ({
  saveBlobAs: vi.fn(),
  filenameFromContentDisposition: vi.fn(),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    id,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    id?: string;
  }) => (
    <select
      aria-label={id ?? placeholder ?? 'select'}
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

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
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

import { OrderInquiriesClient } from './OrderInquiriesClient';

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => listOrderInquiryWorklist.mock.calls.at(-1)?.[0] as Record<string, unknown>;
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

function envelope(rows: OrderInquiryWorklistRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
}

function renderClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiriesClient />
    </QueryClientProvider>,
  );
}

function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), { button: 0, ctrlKey: false });
}

const FACETS = {
  locations: [{ id: 'ZZT-WH-A', label: 'ZZT-WH-A', rows: 2 }, { id: 'ZZT-WH-B', label: 'ZZT-WH-B', rows: 1 }],
  agents: [{ id: 'ag-1', label: 'Agent One', rows: 2 }, { id: 'ag-2', label: 'Agent Two', rows: 1 }],
  projects: [{ id: 'ALPHA', label: 'ALPHA', rows: 2 }, { id: 'BETA', label: 'BETA', rows: 1 }],
};

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  currentSearchParams = new URLSearchParams('');
  listOrderInquiryWorklist.mockResolvedValue(envelope(MOCK_WORKLIST_ROWS));
  getOrderInquiryWorklistSummary.mockResolvedValue({ ...MOCK_WORKLIST_SUMMARY, ...FACETS });
  exportOrderInquiryWorklistXlsx.mockResolvedValue({ id: 'dl-1', kind: 'x', status: 'pending', filename: 'x.xlsx' });
  getUnplaceAllPreview.mockResolvedValue({ count: 0, product_code: null, product_name: null });
  getOrderInquiryPoCandidates.mockResolvedValue([]);
  getOrderInquiryMatrix.mockResolvedValue({ data: [] });
  getUserListColumnConfig.mockResolvedValue({ listing_key: 'projects.projects.view::order-inquiry-worklist', config: null });
});

// [param sent to the service, two option values, label for the test]
const FILTERS: [string, string, string][] = [
  ['location', 'ZZT-WH-A', 'ZZT-WH-B'],
  ['agent', 'ag-1', 'ag-2'],
  ['state', 'raised', 'actioned'],
  ['supplier_id', 'sup-1', 'sup-2'],
  ['project', 'ALPHA', 'BETA'],
  ['raised_by', 'user-cindy', 'user-contact-aa'],
];

describe('Order inquiry lines - multi filters', () => {
  it.each(FILTERS)('%s is a multi control', async (_param, a) => {
    renderClient();
    await screen.findByText('SO385126');
    openFilters();
    expect((await box(a)).hasAttribute('multiple')).toBe(true);
  });

  it.each(FILTERS)('%s: two values reach the service as one set', async (param, a, b) => {
    const user = userEvent.setup();
    renderClient();
    await screen.findByText('SO385126');
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(lastParams()[param])).toEqual([a, b].sort()));
  });

  it.each(FILTERS)('%s: clearing sends nothing, never an "all" value', async (param, a, b) => {
    const user = userEvent.setup();
    renderClient();
    await screen.findByText('SO385126');
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(lastParams()[param])).toEqual([a, b].sort()));
    openFilters();
    await user.deselectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(lastParams()[param])).toEqual([]));
    for (const [params] of listOrderInquiryWorklist.mock.calls) {
      expect(setOf((params as Record<string, unknown>)[param])).not.toContain('all');
    }
  });

  it('an old link holding one value reads as a one-value filter, a comma-joined one as a set', async () => {
    currentSearchParams = new URLSearchParams('location=ZZT-WH-A&agent=ag-1,ag-2');
    renderClient();
    await screen.findByText('SO385126');
    await waitFor(() => expect(setOf(lastParams().location)).toEqual(['ZZT-WH-A']));
    expect(setOf(lastParams().agent)).toEqual(['ag-1', 'ag-2']);
  });

  it('an old saved view holding single values still applies, and a joined one applies as a set', async () => {
    getUserListColumnConfig.mockResolvedValue({
      listing_key: 'projects.projects.view::order-inquiry-worklist',
      config: {
        version: 1, sorting: null, filtersVersion: 1,
        filters: { location: 'ZZT-WH-A', supplier_id: 'sup-1,sup-2', raised_by: 'user-cindy' },
      },
    });
    renderClient();
    await screen.findByText('SO385126');
    await waitFor(() => expect(setOf(lastParams().location)).toEqual(['ZZT-WH-A']));
    expect(setOf(lastParams().supplier_id)).toEqual(['sup-1', 'sup-2']);
    expect(setOf(lastParams().raised_by)).toEqual(['user-cindy']);
  });

  it('Linked, Confirmed and Dead document stay single selects', async () => {
    renderClient();
    await screen.findByText('SO385126');
    openFilters();
    for (const placeholder of ['Anywhere', 'Any', 'Every document']) {
      const el = (await screen.findAllByLabelText(placeholder))[0] as HTMLSelectElement;
      expect(el.hasAttribute('multiple')).toBe(false);
    }
  });
});
