/**
 * AC-RF-84, 85, 88: the Documents | Lines toggle keeps the `inquiry_no` filter both ways, and
 * the Documents state (Outstanding, All, Completed) chosen with it comes back on the return.
 * That state is NEVER sent to the Lines API as a row state. Both real screens are mounted
 * behind a router that really moves the URL, so the Lines screen's own URL-sync effect is part
 * of the round trip. With no `inquiry_no` the toggle's URL stays clean (AC-RF-88).
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

// A router that really moves the URL, so the screen's own URL-sync effect, the toggle and the
// list all see each other's writes.
const nav = vi.hoisted(() => {
  const state = { search: '', listeners: new Set<() => void>() };
  const go = (url: string) => {
    state.search = url.includes('?') ? url.split('?')[1] : '';
    state.listeners.forEach((l) => l());
  };
  return { state, go, pushed: [] as string[], replaced: [] as string[] };
});
vi.mock('next/navigation', async () => {
  const React = await import('react');
  return {
    useRouter: () => ({
      push: (url: string) => {
        nav.pushed.push(url);
        nav.go(url);
      },
      replace: (url: string) => {
        nav.replaced.push(url);
        nav.go(url);
      },
      prefetch: () => {},
    }),
    usePathname: () => '/project-sales/order-inquiries',
    useSearchParams: () => {
      const search = React.useSyncExternalStore(
        (cb) => {
          nav.state.listeners.add(cb);
          return () => nav.state.listeners.delete(cb);
        },
        () => nav.state.search,
        () => nav.state.search,
      );
      return React.useMemo(() => new URLSearchParams(search), [search]);
    },
  };
});

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
const listOrderInquiryHeaders = vi.fn();
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
  listOrderInquiryHeaders: (...args: unknown[]) => listOrderInquiryHeaders(...args),
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

import { OrderInquiryHeadersOrLinesView } from './OrderInquiryHeadersOrLinesView';


vi.mock('../../_shared/services/orderInquiryReserveService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/orderInquiryReserveService')>();
  return {
    ...actual,
    getReserveStatusSummary: vi.fn(async () => ({
      parked: 0, needs_reserve: 0, notice_parked: 0, reserved: 0, my_parked_requests: 0, my_parked_notices: 0,
    })),
  };
});
vi.mock('@/services/userSelectService', () => ({ getUserLookup: vi.fn(async () => []) }));


const sent = (value: unknown): string | undefined =>
  (Array.isArray(value) ? value.join(',') : (value as string | undefined)) || undefined;
const NUMBERS = 'OI-2610-001,OI-2610-002';
const query = () => new URLSearchParams(nav.state.search);
const lastHeaders = () => listOrderInquiryHeaders.mock.calls.at(-1)?.[0] as Record<string, unknown>;

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryHeadersOrLinesView />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  nav.state.search = '';
  nav.pushed.length = 0;
  nav.replaced.length = 0;
  listOrderInquiryHeaders.mockResolvedValue({
    data: [
      { id: 'h-1', inquiry_no: 'OI-2610-001', so_number: 'SO1', status: 'open', raised_at: '2026-10-01T00:00:00', reserve_status: null, parked_by_name: null },
    ],
    total: 1, page: 1, limit: 25,
  });
  listOrderInquiryWorklist.mockResolvedValue({ data: MOCK_WORKLIST_ROWS, total: MOCK_WORKLIST_ROWS.length, page: 1, limit: 25 });
  getOrderInquiryWorklistSummary.mockResolvedValue({ ...MOCK_WORKLIST_SUMMARY });
  getOrderInquiryMatrix.mockResolvedValue({ data: [] });
  getUnplaceAllPreview.mockResolvedValue({ count: 0, product_code: null, product_name: null });
  getOrderInquiryPoCandidates.mockResolvedValue([]);
  getUserListColumnConfig.mockResolvedValue({ listing_key: 'projects.projects.view::order-inquiry-worklist', config: null });
});

describe.each(['outstanding', 'all', 'completed'])(
  'AC-RF-84 / 85 a round trip with inquiry_no and state=%s',
  (state) => {
    it('keeps inquiry_no both ways, brings the Documents state back, never sends it to Lines', async () => {
      nav.state.search = `state=${state}&inquiry_no=${NUMBERS}`;
      renderView();
      await screen.findByText('OI-2610-001');
      await waitFor(() => expect(sent(lastHeaders().inquiry_no)).toBe(NUMBERS));

      fireEvent.click(screen.getByRole('button', { name: /^lines$/i }));
      const toLines = new URLSearchParams(String(nav.pushed.at(-1)).split('?')[1] ?? '');
      expect(toLines.get('display')).toBe('lines');
      expect(toLines.get('inquiry_no')).toBe(NUMBERS);

      await screen.findByText('SO385126');
      await waitFor(() => expect(sent((listOrderInquiryWorklist.mock.calls.at(-1)?.[0] as Record<string, unknown>).inquiry_no)).toBe(NUMBERS));
      for (const [params] of listOrderInquiryWorklist.mock.calls) {
        expect(sent((params as Record<string, unknown>).state), 'Lines row state').toBeUndefined();
      }
      expect(query().get('inquiry_no')).toBe(NUMBERS);
      expect(query().get('display')).toBe('lines');

      fireEvent.click(screen.getByRole('button', { name: /^documents$/i }));
      await screen.findByText('OI-2610-001');
      await waitFor(() => expect(query().get('display')).toBeNull());
      expect(query().get('inquiry_no')).toBe(NUMBERS);
      expect(query().get('state')).toBe(state);
      await waitFor(() => expect(lastHeaders()).toEqual(expect.objectContaining({ state })));
      expect(sent(lastHeaders().inquiry_no)).toBe(NUMBERS);
    });
  },
);

describe('AC-RF-88 with no inquiry_no the toggle stays clean', () => {
  it('Lines writes only display=lines, Documents writes the bare path', async () => {
    renderView();
    await screen.findByText('OI-2610-001');
    fireEvent.click(screen.getByRole('button', { name: /^lines$/i }));
    expect(nav.pushed.at(-1)).toBe('/project-sales/order-inquiries?display=lines');
    await screen.findByText('SO385126');
    fireEvent.click(screen.getByRole('button', { name: /^documents$/i }));
    expect(nav.pushed.at(-1)).toBe('/project-sales/order-inquiries');
  });
});
