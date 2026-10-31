/**
 * AC-RF-23 / AC-RF-24: the `inquiry_no` URL filter on the Documents list (the reserve email's
 * "View these N order inquiries" button lands here). Services are mocked (not the hooks) so
 * the wiring from hook to service is part of what is tested. TEST-FIRST: red until the list
 * reads, sends, keeps and chips `inquiry_no`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

let searchParamsValue = '';
const replaceSpy = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/order-inquiries',
  useRouter: () => ({ push: vi.fn(), replace: replaceSpy }),
  useSearchParams: () => new URLSearchParams(searchParamsValue),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({ getUserLookup: vi.fn(async () => []) }));

let permissions = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => permissions.has(slug),
}));

const SUMMARY = {
  parked: 17,
  needs_reserve: 0,
  notice_parked: 0,
  reserved: 0,
  my_parked_requests: 17,
  my_parked_notices: 3,
};
const getSummarySpy = vi.fn(async () => ({ ...SUMMARY }));
const previewRequestsSpy = vi.fn(async () => ({ emails: [], unresolved: [] }));
const previewNoticesSpy = vi.fn(async () => ({ emails: [], unresolved: [] }));
vi.mock('../../_shared/services/orderInquiryReserveService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/orderInquiryReserveService')
  >();
  return {
    ...actual,
    getReserveStatusSummary: () => getSummarySpy(),
    previewParkedReserveRequests: () => previewRequestsSpy(),
    previewParkedReserveNotices: () => previewNoticesSpy(),
    sendParkedReserveRequests: vi.fn(),
    sendParkedReserveNotices: vi.fn(),
  };
});

let headers: Array<Record<string, unknown>> = [];
const listSpy = vi.fn(async (_params: Record<string, unknown>) => ({
  data: headers,
  total: headers.length,
  page: 1,
  limit: 25,
}));
vi.mock('../../_shared/services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/orderInquiryService')>();
  return {
    ...actual,
    listOrderInquiryHeaders: (params: Record<string, unknown>) => listSpy(params),
    getOrderInquiryWorklistSummary: vi.fn(async () => ({ agents: [], projects: [] })),
  };
});

import { OrderInquiryHeadersList } from './OrderInquiryHeadersList';

function header(over: Record<string, unknown>) {
  return {
    id: 'h-1',
    inquiry_no: 'OI-0001',
    so_number: 'SO000123',
    sales_order_id: 'so-1',
    status: 'open',
    raised_at: '2026-10-01T00:00:00',
    reserve_status: null,
    parked_by_name: null,
    ...over,
  };
}

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OrderInquiryHeadersList />
    </QueryClientProvider>,
  );
}

async function openReserveOptions() {
  const filtersButton = await screen.findByRole('button', { name: /filters/i });
  fireEvent.pointerDown(filtersButton, { button: 0, ctrlKey: false });
  fireEvent.click(filtersButton);
  fireEvent.click(await screen.findByLabelText('Reserve'));
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsValue = '';
  headers = [header({ reserve_status: 'parked', parked_by_name: 'Joey' })];
  permissions = new Set(['projects.order_inquiries.acknowledge', 'projects.order_inquiries.reserve']);
  getSummarySpy.mockImplementation(async () => ({ ...SUMMARY }));
});


const NUMBERS = 'OI-2610-001,OI-2610-002';
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

/** The API param, whether the list sends it joined or as repeated values. */
function sentInquiryNo(params: Record<string, unknown>): string | undefined {
  const value = params.inquiry_no;
  if (Array.isArray(value)) return value.length ? value.join(',') : undefined;
  return (value as string | undefined) || undefined;
}

function lastParams(): Record<string, unknown> {
  const calls = listSpy.mock.calls;
  return calls[calls.length - 1][0];
}

function lastReplaceQuery(): URLSearchParams {
  const calls = replaceSpy.mock.calls;
  const url = String(calls[calls.length - 1][0]);
  return new URLSearchParams(url.includes('?') ? url.split('?')[1] : '');
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParamsValue = '';
  headers = [header({ inquiry_no: 'OI-2610-001' }), header({ id: 'h-2', inquiry_no: 'OI-2610-002' })];
  permissions = new Set(['projects.order_inquiries.acknowledge']);
  getSummarySpy.mockImplementation(async () => ({ ...SUMMARY }));
});

describe('AC-RF-23 inquiry_no filter', () => {
  it('reads inquiry_no from the URL and sends it to the list call', async () => {
    searchParamsValue = `inquiry_no=${NUMBERS}`;
    renderList();
    await waitFor(() => expect(sentInquiryNo(lastParams())).toBe(NUMBERS));
  });

  it('shows a removable filter and clearing it stops sending inquiry_no', async () => {
    searchParamsValue = `inquiry_no=${NUMBERS}`;
    renderList();
    const clear = await screen.findByRole('button', { name: /clear filter:.*(inquir|OI-)/i });
    fireEvent.click(clear);
    await waitFor(() => expect(sentInquiryNo(lastParams())).toBeUndefined());
    expect(screen.queryByRole('button', { name: /clear filter:.*(inquir|OI-)/i })).not.toBeInTheDocument();
    await waitFor(() => expect(lastReplaceQuery().get('inquiry_no')).toBeNull());
  });

  it('keeps inquiry_no in the URL across a filter change', async () => {
    searchParamsValue = `inquiry_no=${NUMBERS}`;
    renderList();
    await waitFor(() => expect(replaceSpy).toHaveBeenCalled());
    expect(lastReplaceQuery().get('inquiry_no')).toBe(NUMBERS);
    fireEvent.click(await screen.findByRole('radio', { name: /completed/i }));
    await waitFor(() => expect(lastReplaceQuery().get('state')).toBe('completed'));
    expect(lastReplaceQuery().get('inquiry_no')).toBe(NUMBERS);
    expect(sentInquiryNo(lastParams())).toBe(NUMBERS);
  });

  it('keeps inquiry_no in the URL and the call across a sort change', async () => {
    searchParamsValue = `inquiry_no=${NUMBERS}`;
    renderList();
    await screen.findByText('OI-2610-001');
    const sortable = screen.getAllByRole('columnheader').find((h) => /^OI no/i.test(h.textContent ?? ''));
    expect(sortable).toBeTruthy();
    fireEvent.click(within(sortable as HTMLElement).getByRole('button', { name: /oi no/i }));
    await waitFor(() => expect(lastParams().sort).toBe('inquiry_no'));
    expect(sentInquiryNo(lastParams())).toBe(NUMBERS);
    expect(lastReplaceQuery().get('inquiry_no')).toBe(NUMBERS);
  });

  it('without the param nothing is sent and no chip shows', async () => {
    renderList();
    await screen.findByText('OI-2610-001');
    expect(sentInquiryNo(lastParams())).toBeUndefined();
    expect(screen.queryByRole('button', { name: /clear filter:.*(inquir|OI-)/i })).not.toBeInTheDocument();
  });
});

describe('AC-RF-24 state All on arrival', () => {
  it('inquiry_no with no explicit state shows state All', async () => {
    searchParamsValue = `inquiry_no=${NUMBERS}`;
    renderList();
    await waitFor(() => expect(lastParams()).toEqual(expect.objectContaining({ state: 'all' })));
    expect(screen.getByRole('radio', { name: 'All' })).toBeChecked();
  });

  it('an explicit state wins', async () => {
    searchParamsValue = `inquiry_no=${NUMBERS}&state=completed`;
    renderList();
    await waitFor(() => expect(lastParams()).toEqual(expect.objectContaining({ state: 'completed' })));
    expect(sentInquiryNo(lastParams())).toBe(NUMBERS);
  });

  it('no UUID shows anywhere on the page', async () => {
    searchParamsValue = `inquiry_no=${NUMBERS}`;
    renderList();
    await screen.findByText('OI-2610-001');
    await screen.findByRole('button', { name: /clear filter/i });
    expect(document.body.textContent ?? '').not.toMatch(UUID);
  });
});

describe('AC-RF-26 choosing Outstanding keeps state=outstanding in the URL', () => {
  it.each([
    ['inquiry_no', `inquiry_no=${NUMBERS}`],
    ['reserve', 'reserve=needs_reserve'],
  ])('with %s in the URL', async (_name, query) => {
    searchParamsValue = query;
    renderList();
    await screen.findByText('OI-2610-001');
    fireEvent.click(await screen.findByRole('radio', { name: /outstanding/i }));
    await waitFor(() => expect(lastReplaceQuery().get('state')).toBe('outstanding'));
  });
});
