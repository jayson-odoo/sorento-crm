/**
 * AC-RF-84, 86, 87 on the Lines screen (`OrderInquiriesClient`): it reads `inquiry_no` from the
 * URL, sends it on its list, summary and schedule requests, keeps it across filter, sort and
 * page changes, shows a removable chip, drops it on the chip / "Clear filters", and applies NO
 * default narrowing while it is present (the Documents list shows state All for the same link).
 *
 * Default narrowing found on this screen: `ack` (sent as `to_confirm` unless the URL says
 * `ack=all`), `state` (a Documents `state=outstanding` is read as a Lines ROW state), and the
 * saved-view memory (location, supplier, project, raised by, linked, kind and the rest, replayed
 * onto every visit). The link horizon (`link_up_to`/`link_horizon`) only scopes the link presses
 * and is never on the list request. The router below really moves the URL.
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


const sent = (value: unknown): string | undefined =>
  (Array.isArray(value) ? value.join(',') : (value as string | undefined)) || undefined;
const lastList = () => listOrderInquiryWorklist.mock.calls.at(-1)?.[0] as Record<string, unknown>;
const lastSummary = () => getOrderInquiryWorklistSummary.mock.calls.at(-1)?.[0] as Record<string, unknown>;
const NUMBERS = 'OI-2610-001,OI-2610-002';
const CLEAR_CHIP = /clear filter:.*(inquir|OI-)/i;

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

function arriveWith(search: string) {
  nav.state.search = search;
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  nav.state.search = '';
  nav.pushed.length = 0;
  nav.replaced.length = 0;
  listOrderInquiryWorklist.mockResolvedValue(envelope(MOCK_WORKLIST_ROWS));
  getOrderInquiryWorklistSummary.mockResolvedValue({ ...MOCK_WORKLIST_SUMMARY });
  exportOrderInquiryWorklistXlsx.mockResolvedValue({ id: 'dl-1', kind: 'x', status: 'pending', filename: 'x.xlsx' });
  getUnplaceAllPreview.mockResolvedValue({ count: 0, product_code: null, product_name: null });
  getOrderInquiryPoCandidates.mockResolvedValue([]);
  getOrderInquiryMatrix.mockResolvedValue({ data: [] });
  getUserListColumnConfig.mockResolvedValue({ listing_key: 'projects.projects.view::order-inquiry-worklist', config: null });
});

describe('AC-RF-84 / 86 the Lines screen reads and sends inquiry_no', () => {
  it('sends it on the list and the summary request', async () => {
    arriveWith(`inquiry_no=${NUMBERS}`);
    renderClient();
    await screen.findByText('SO385126');
    await waitFor(() => expect(sent(lastList().inquiry_no)).toBe(NUMBERS));
    expect(sent(lastSummary().inquiry_no)).toBe(NUMBERS);
  });

  it('sends it on the schedule (matrix) request too', async () => {
    arriveWith(`view=schedule&inquiry_no=${NUMBERS}`);
    renderClient();
    await waitFor(() => expect(getOrderInquiryMatrix).toHaveBeenCalled());
    const params = getOrderInquiryMatrix.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(sent(params.inquiry_no)).toBe(NUMBERS);
  });

  it('without the param nothing is sent and no chip shows', async () => {
    renderClient();
    await screen.findByText('SO385126');
    expect(sent(lastList().inquiry_no)).toBeUndefined();
    expect(screen.queryByRole('button', { name: CLEAR_CHIP })).not.toBeInTheDocument();
  });
});

describe('AC-RF-84 no default narrowing while inquiry_no is present', () => {
  const NARROWING = ['ack', 'state', 'kind', 'linked', 'reserve', 'dead_document', 'location', 'supplier_id', 'agent'];

  it('sends no ack, no row state and none of the other narrowing params', async () => {
    arriveWith(`inquiry_no=${NUMBERS}`);
    renderClient();
    await screen.findByText('SO385126');
    await waitFor(() => expect(sent(lastList().inquiry_no)).toBe(NUMBERS));
    for (const request of [lastList(), lastSummary()]) {
      for (const key of NARROWING) expect(sent(request[key]), key).toBeUndefined();
      expect(request).not.toHaveProperty('link_up_to');
      expect(request).not.toHaveProperty('link_horizon');
    }
  });

  it('a Documents state in the URL is never sent as a Lines row state', async () => {
    arriveWith(`state=outstanding&inquiry_no=${NUMBERS}`);
    renderClient();
    await screen.findByText('SO385126');
    await waitFor(() => expect(sent(lastList().inquiry_no)).toBe(NUMBERS));
    for (const [params] of listOrderInquiryWorklist.mock.calls) {
      expect(sent((params as Record<string, unknown>).state)).toBeUndefined();
    }
  });

  it('the remembered view does not narrow it either (the saved-view defaults)', async () => {
    getUserListColumnConfig.mockResolvedValue({
      listing_key: 'projects.projects.view::order-inquiry-worklist',
      config: {
        version: 1, sorting: null, filtersVersion: 1,
        filters: { ack: 'to_confirm', location: 'ZZT-WH-A', supplier_id: 'sup-1', linked: 'po', kind: 'buy' },
      },
    });
    arriveWith(`inquiry_no=${NUMBERS}`);
    renderClient();
    await screen.findByText('SO385126');
    await waitFor(() => expect(sent(lastList().inquiry_no)).toBe(NUMBERS));
    for (const key of ['ack', 'location', 'supplier_id', 'linked', 'kind']) {
      expect(sent(lastList()[key]), key).toBeUndefined();
    }
  });
});

describe('AC-RF-84 / 87 the chip and clearing', () => {
  it('shows a removable chip; removing it drops inquiry_no from the request and the URL', async () => {
    arriveWith(`inquiry_no=${NUMBERS}`);
    renderClient();
    fireEvent.click(await screen.findByRole('button', { name: CLEAR_CHIP }));
    await waitFor(() => expect(sent(lastList().inquiry_no)).toBeUndefined());
    expect(new URLSearchParams(nav.state.search).get('inquiry_no')).toBeNull();
  });

  it('"Clear filters" drops it from the request and the URL', async () => {
    arriveWith(`inquiry_no=${NUMBERS}`);
    renderClient();
    await screen.findByText('SO385126');
    fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), { button: 0, ctrlKey: false });
    fireEvent.click(await screen.findByRole('button', { name: /^clear filters$/i }));
    await waitFor(() => expect(sent(lastList().inquiry_no)).toBeUndefined());
    expect(new URLSearchParams(nav.state.search).get('inquiry_no')).toBeNull();
  });
});

describe('AC-RF-87 a filter change keeps inquiry_no (sort and page ride the same request params; not driven here)', () => {
  it('a search keeps it in the URL and on the request', async () => {
    arriveWith(`inquiry_no=${NUMBERS}`);
    renderClient();
    await screen.findByText('SO385126');
    fireEvent.change(screen.getByLabelText('Search order inquiry rows'), { target: { value: 'CKS' } });
    await waitFor(() => expect(lastList().query).toBe('CKS'));
    expect(sent(lastList().inquiry_no)).toBe(NUMBERS);
    expect(new URLSearchParams(nav.state.search).get('inquiry_no')).toBe(NUMBERS);
  });
});
