/**
 * STANDARD-HISTORY wave 5 (AC-W5-5, AC-W5-6, AC-W5-7): the CRM price tag request page gets a
 * fourth tab, History, last after Files. It reads
 *   GET /api/v1/dealer-kit/price-tag-requests/{request_id}/history
 * only once the tab is opened, and renders the shared `AuditTrail` entries mode exactly as the
 * OI / SO tabs: entries, "No history yet" when empty, "Could not load the history" + Retry.
 *
 * The HTTP layer (`apiFetch`) is what is mocked here, not a service function, so the test does
 * not decide which service file holds the history read (UAC AC-W5-6 allows either). The
 * request's own service keeps its real exports through `importOriginal`, with only the calls the
 * page makes on mount replaced, the same stand-ins `PriceTagRequestDetail.test.tsx` uses.
 * Names and numbers are fake.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RecordHistoryEvent } from '@/types/recordHistory.types';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/dealer-kit/price-tag-requests/req-1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="gear-menu">{children}</div>
  ),
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({ children }: { children: React.ReactNode }) => (
    <div role="menuitem">{children}</div>
  ),
}));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({
    pending: null,
    isPending: false,
    isBlocked: false,
    start: vi.fn(),
    cancel: vi.fn(),
    countdown: null,
  }),
}));

/**
 * Every `apiFetch` the page makes. The history URL answers what the test says; anything else
 * stays pending, so no unrelated read can resolve into a state this file does not set up.
 */
const HISTORY_URL = '/api/v1/dealer-kit/price-tag-requests/req-1/history';
const apiFetchSpy = vi.hoisted(() => vi.fn());
let historyAnswer: () => Promise<Response>;
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetchSpy(...args) };
});

function isHistoryCall(call: unknown[]): boolean {
  return String(call[0]).includes(HISTORY_URL);
}

function historyCalls(): unknown[][] {
  return apiFetchSpy.mock.calls.filter(isHistoryCall);
}

vi.mock('../../services/priceTagRequestService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../services/priceTagRequestService')>();
  const { computeLinePricing } = await import(
    '@/app/(auth)/portal/components/__fixtures__/line-pricing'
  );
  return {
    ...actual,
    getPriceTagRequest: vi.fn(),
    getTagSheetDoc: vi.fn(async () => null),
    claimPriceTagRequest: vi.fn(),
    transitionPriceTagRequest: vi.fn(),
    exportTagSheet: vi.fn(),
    listPriceTagRequests: vi.fn(),
    getRequestDesignPayload: vi.fn(async () => null),
    lookupLinePricing: vi.fn(async (mode: string, lines: unknown[]) =>
      computeLinePricing(mode as 'list' | 'selling', lines as never),
    ),
    updatePriceTagLinePrice: vi.fn(),
  };
});

vi.mock('../../services/priceTagDataService', () => ({
  listTagDataChanges: vi.fn(async () => []),
  recheckTagDataChanges: vi.fn(async () => []),
  resolveTagPin: vi.fn(async () => {}),
  updateAllTagPins: vi.fn(async () => {}),
}));

import {
  getPriceTagRequest,
  listPriceTagRequests,
  type PriceTagRequestDetail as PriceTagRequestDetailType,
} from '../../services/priceTagRequestService';
import PriceTagRequestDetail from './PriceTagRequestDetail';

const mockGet = vi.mocked(getPriceTagRequest);
const mockList = vi.mocked(listPriceTagRequests);

const EVENTS: RecordHistoryEvent[] = [
  {
    id: 'ev-3',
    kind: 'status_changed',
    at: '2026-11-12T03:00:00',
    actor: 'ZZT Sales Sam',
    title: 'Status: Design Ready → Approved',
    lines: [],
  },
  {
    id: 'ev-2',
    kind: 'revised',
    at: '2026-11-07T03:00:00',
    actor: 'ZZT Sales Sam',
    title: 'Revised, revision 1: ZZT dealer changed the qty',
    lines: [
      { row_id: 'c1', so_line_no: null, item_code: null, qty: null, change: 'Notes: ZZT first note → ZZT second note' },
      { row_id: 'c2', so_line_no: null, item_code: null, qty: null, change: 'Product line 1 quantity: 2 → 5' },
    ],
  },
  {
    id: 'ev-1',
    kind: 'submitted',
    at: '2026-11-01T03:00:00',
    actor: 'ZZT Sales Sam',
    title: 'Submitted',
    lines: [],
  },
];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function requestWith(overrides: Partial<PriceTagRequestDetailType> = {}): PriceTagRequestDetailType {
  return {
    id: 'req-1',
    doc_number: 'PT-202611-0001',
    debtor_code: 'ZZT001',
    debtor_name: 'ZZT DEALER SDN BHD',
    needed_by_date: '2026-11-20',
    notes: null,
    status: 'designing',
    line_count: 0,
    created_at: '2026-11-01T02:00:00Z',
    assigned_to_id: 'user-1',
    assigned_to_name: 'ZZT Marketing Mei',
    contact_name: 'ZZT Sales Sam',
    contact_id: 'contact-1',
    lines: [],
    attachments: [],
    ...overrides,
  };
}

/** Radix activates a tab on mousedown, which jsdom does not synthesize from a click. */
function switchTab(name: string) {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

/** The record has loaded: its number is the page heading. */
async function loaded() {
  await screen.findByRole('heading', { name: /PT-202611-0001/, level: 1 });
}

function renderDetail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PriceTagRequestDetail requestId="req-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue(requestWith());
  mockList.mockResolvedValue({
    data: [{ id: 'req-1' }, { id: 'req-2' }] as never,
    pagination: { total: 2, page: 1, limit: 50 },
  });
  historyAnswer = async () => jsonResponse({ events: EVENTS });
  apiFetchSpy.mockImplementation((...args: unknown[]) =>
    isHistoryCall(args) ? historyAnswer() : new Promise<Response>(() => {}),
  );
});

describe('PriceTagRequestDetail History tab (STANDARD-HISTORY wave 5)', () => {
  it('is the fourth and last tab, after Files, and Request / Lines / Files are unchanged', async () => {
    renderDetail();
    await loaded();
    const tabs = screen.getAllByRole('tab').map((t) => t.textContent?.trim());
    expect(tabs).toEqual(['Request', 'Lines', 'Files', 'History']);
  });

  it('does not read the history before the tab is opened', async () => {
    renderDetail();
    await loaded();
    switchTab('Lines');
    switchTab('Files');
    // Give any eager query a chance to fire before asserting it did not.
    await new Promise((r) => setTimeout(r, 50));
    expect(historyCalls()).toHaveLength(0);
  });

  it('opening History reads the endpoint and shows the entries, newest first, with dd/mm/yyyy dates', async () => {
    renderDetail();
    await loaded();
    switchTab('History');

    expect(await screen.findByText('Status: Design Ready → Approved')).toBeInTheDocument();
    expect(historyCalls().length).toBeGreaterThanOrEqual(1);

    const items = screen.getAllByTestId('audit-action').map((el) => el.textContent);
    expect(items).toEqual([
      'Status: Design Ready → Approved',
      'Revised, revision 1: ZZT dealer changed the qty',
      'Submitted',
    ]);
    const revised = screen
      .getByText('Revised, revision 1: ZZT dealer changed the qty')
      .closest('[data-audit-entry]') as HTMLElement;
    expect(revised).toHaveTextContent('07/11/2026');
    expect(revised).toHaveTextContent('ZZT Sales Sam');
    fireEvent.click(within(revised).getByRole('button', { name: 'Show 2 lines' }));
    expect(within(revised).getAllByTestId('audit-change-line').map((l) => l.textContent)).toEqual([
      'Notes: ZZT first note → ZZT second note',
      'Product line 1 quantity: 2 → 5',
    ]);
  });

  it('empty: "No history yet"', async () => {
    historyAnswer = async () => jsonResponse({ events: [] });
    renderDetail();
    await loaded();
    switchTab('History');
    expect(await screen.findByText('No history yet')).toBeInTheDocument();
  });

  it('error: "Could not load the history" with a Retry that reads again', async () => {
    historyAnswer = async () => jsonResponse({ message: 'ZZT boom' }, 500);
    renderDetail();
    await loaded();
    switchTab('History');
    expect(await screen.findByText('Could not load the history')).toBeInTheDocument();

    const before = historyCalls().length;
    historyAnswer = async () => jsonResponse({ events: EVENTS });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(
      await screen.findByText('Revised, revision 1: ZZT dealer changed the qty'),
    ).toBeInTheDocument();
    await waitFor(() => expect(historyCalls().length).toBeGreaterThan(before));
  });
});
