/**
 * PLAN-oi-confirm-per-so, `oi-confirm-per-so-acceptance-criteria.md` (AC-CF-*): the
 * Phase 1 pieces committed at 15987331a - Confirm (N) as the primary press, "Select all
 * N matching", the To confirm tile/default, and the remembered sort + filters through
 * `useListingViewPreferences`.
 *
 * A SEPARATE file from `OrderInquiriesClient.test.tsx` (not an addition to it) because
 * the remembered-view assertions need the REAL `useListingViewPreferences` hook wired to
 * a controllable, per-test `listColumnPreferencesService` mock - the existing file's
 * fixed `{ config: null }` stub cannot express "a stored sort" or "gate the first fetch"
 * at all, and `StockInquiriesList.viewMemory.test.tsx` is this pattern's precedent.
 *
 * One `it` per AC, named after the AC.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  MOCK_WORKLIST_ROWS,
  MOCK_WORKLIST_SUMMARY,
} from '../../_shared/__mocks__/orderInquiryWorklist';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

let granted = new Set([
  'projects.order_inquiry.action',
  'projects.order_inquiries.acknowledge',
]);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) =>
    slugs.some((slug) => granted.has(slug)),
  usePermissions: () => ({
    permissions: [...granted],
    permissionSet: granted,
    isLoading: false,
  }),
}));

const routerReplace = vi.fn();
let currentSearchParams = new URLSearchParams('');
// AC-CF-18 (navigate-away guard): mutable so a test can flip the route mid-render and
// prove the write-back effect skips a render that no longer names this page.
let currentPathname = '/project-sales/order-inquiries';

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: (...args: unknown[]) => routerReplace(...args),
  }),
  usePathname: () => currentPathname,
  useSearchParams: () => currentSearchParams,
}));

// Column order/visibility/width - a DIFFERENT hook from the one this file is about.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

// The remembered SORT/FILTERS transport (S6): the REAL `useListingViewPreferences` runs
// against this mock, per-test-configurable via `storedConfig()`, the same shape
// `StockInquiriesList.viewMemory.test.tsx` uses for the same hook.
const service = vi.hoisted(() => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (...args: unknown[]) =>
    service.getUserListColumnConfig(...args),
  upsertUserListColumnConfig: (...args: unknown[]) =>
    service.upsertUserListColumnConfig(...args),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

const LISTING_KEY = 'projects.projects.view::order-inquiry-worklist';

/** Seeds what `getUserListColumnConfig` answers, and makes the PUT echo back. */
function storedConfig(config: Record<string, unknown> | null) {
  service.getUserListColumnConfig.mockResolvedValue({
    listing_key: LISTING_KEY,
    config,
  });
  service.upsertUserListColumnConfig.mockImplementation(
    async (listingKey: string, payload: unknown) => ({
      listing_key: listingKey,
      config: payload,
    }),
  );
}

const listOrderInquiryWorklist = vi.fn();
const getOrderInquiryWorklistSummary = vi.fn();
const exportOrderInquiryWorklistXlsx = vi.fn();
const autoPlaceOrderInquiryRows = vi.fn();
const getUnplaceAllPreview = vi.fn();
const unplaceAllOrderInquiryRows = vi.fn();
const acknowledgeOrderInquiryRows = vi.fn();
const acknowledgeOrderInquiryRowsByFilter = vi.fn();
const unacknowledgeOrderInquiryRows = vi.fn();
const rejectOrderInquiryRows = vi.fn();
const linkNowOrderInquiryRows = vi.fn();
const getOrderInquiryPoCandidates = vi.fn();
const getOrderInquiryUploadJob = vi.fn();
const unplaceOrderInquiryRow = vi.fn();

vi.mock('../../_shared/services/orderInquiryService', () => ({
  listOrderInquiryWorklist: (...args: unknown[]) =>
    listOrderInquiryWorklist(...args),
  getOrderInquiryWorklistSummary: (...args: unknown[]) =>
    getOrderInquiryWorklistSummary(...args),
  exportOrderInquiryWorklistXlsx: (...args: unknown[]) =>
    exportOrderInquiryWorklistXlsx(...args),
  autoPlaceOrderInquiryRows: (...args: unknown[]) =>
    autoPlaceOrderInquiryRows(...args),
  getUnplaceAllPreview: (...args: unknown[]) => getUnplaceAllPreview(...args),
  unplaceAllOrderInquiryRows: (...args: unknown[]) =>
    unplaceAllOrderInquiryRows(...args),
  acknowledgeOrderInquiryRows: (...args: unknown[]) =>
    acknowledgeOrderInquiryRows(...args),
  // PLAN-oi-confirm-per-so, AC-CF-7/8: "Select all N matching"'s own service call. Left
  // out of the sibling file's mock (no test there reaches the filter path); required
  // here or the real `useOrderInquiryHandshake` throws on an undefined import the
  // instant `selectAllMatchingActive` is taken.
  acknowledgeOrderInquiryRowsByFilter: (...args: unknown[]) =>
    acknowledgeOrderInquiryRowsByFilter(...args),
  // PLAN-oi-worklist-split-customer-project.md: required or the real `useOrderInquiryHandshake`
  // throws on an undefined import the instant Unconfirm is pressed.
  unacknowledgeOrderInquiryRows: (...args: unknown[]) =>
    unacknowledgeOrderInquiryRows(...args),
  rejectOrderInquiryRows: (...args: unknown[]) =>
    rejectOrderInquiryRows(...args),
  linkNowOrderInquiryRows: (...args: unknown[]) =>
    linkNowOrderInquiryRows(...args),
  getOrderInquiryPoCandidates: (...args: unknown[]) =>
    getOrderInquiryPoCandidates(...args),
  getOrderInquiryUploadJob: (...args: unknown[]) =>
    getOrderInquiryUploadJob(...args),
  unplaceOrderInquiryRow: (...args: unknown[]) =>
    unplaceOrderInquiryRow(...args),
}));

const getOrderInquiryMatrix = vi.fn();
vi.mock('../../_shared/services/orderInquiryMatrixService', () => ({
  getOrderInquiryMatrix: (...args: unknown[]) => getOrderInquiryMatrix(...args),
}));

vi.mock('../../../scm/reorder/components/OutstandingUploadDialog', () => ({
  OutstandingUploadDialog: ({
    onQueued,
  }: {
    onQueued?: (queued: { job_id: string; id: string; message: string }) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onQueued?.({ job_id: 'job-1', id: 'job-row-1', message: 'queued' })
      }
    >
      Upload (stub)
    </button>
  ),
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

const saveBlobAs = vi.fn();
vi.mock('../../_shared/services/fileDownload', () => ({
  saveBlobAs: (...args: unknown[]) => saveBlobAs(...args),
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

import { toast } from '@/lib/toast';
import { OrderInquiriesClient } from './OrderInquiriesClient';

function envelope(rows: OrderInquiryWorklistRow[], total?: number) {
  return { data: rows, total: total ?? rows.length, page: 1, limit: 25 };
}

/** A row shaped for the handshake assertions: `MOCK_WORKLIST_ROWS[1]` (raised, unlinked,
 * selectable) with `ack_state` explicit rather than left to `ackStateOf`'s default. */
function ackRow(overrides: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    ...MOCK_WORKLIST_ROWS[1],
    ack_state: 'awaiting',
    ...overrides,
  };
}

function renderClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiriesClient />
    </QueryClientProvider>,
  );
}

function openActionsMenu() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /^actions$/i }), {
    button: 0,
    ctrlKey: false,
  });
}

/** Radix opens the Filters popover on pointerdown, which `fireEvent.click` does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  granted = new Set([
    'projects.order_inquiry.action',
    'projects.order_inquiries.acknowledge',
  ]);
  currentSearchParams = new URLSearchParams('');
  currentPathname = '/project-sales/order-inquiries';
  storedConfig(null);
  listOrderInquiryWorklist.mockResolvedValue(envelope(MOCK_WORKLIST_ROWS));
  getOrderInquiryWorklistSummary.mockResolvedValue(MOCK_WORKLIST_SUMMARY);
  exportOrderInquiryWorklistXlsx.mockResolvedValue({
    id: 'dl-1', kind: 'order_inquiry_worklist_xlsx', status: 'pending',
    filename: 'order-inquiries-23092026.xlsx',
  });
  getUnplaceAllPreview.mockResolvedValue({
    count: 0,
    product_code: null,
    product_name: null,
  });
  getOrderInquiryPoCandidates.mockResolvedValue([]);
  getOrderInquiryMatrix.mockResolvedValue({ data: [] });
  getOrderInquiryUploadJob.mockResolvedValue({
    job_id: 'job-1',
    status: 'finished',
    finished: true,
    product_ids: [],
    documents: [],
    document_count: 0,
  });
  acknowledgeOrderInquiryRows.mockResolvedValue({
    acknowledged: 0,
    linked_rows: 0,
    links: 0,
    after_horizon: 0,
  });
  acknowledgeOrderInquiryRowsByFilter.mockResolvedValue({
    acknowledged: 0,
    linked_rows: 0,
    links: 0,
    after_horizon: 0,
  });
  unacknowledgeOrderInquiryRows.mockResolvedValue({ updated: 0, skipped: 0 });
});

describe('AC-CF-5: Confirm (N) is the primary press', () => {
  it('disabled at 0 with a reason; two eligible + one cancelled ticked reads Confirm (2); the press confirms exactly those two and refetches', async () => {
    const awaitingRow = ackRow({
      id: 'row-await',
      item_code: 'ZZT-AWAIT',
      so_number: 'SO-AWAIT',
      ack_state: 'awaiting',
      state: 'raised',
    });
    const changedRow = ackRow({
      id: 'row-changed',
      item_code: 'ZZT-CHANGED',
      so_number: 'SO-CHANGED',
      ack_state: 'changed',
      state: 'raised',
    });
    const cancelledRow = ackRow({
      id: 'row-cancelled',
      item_code: 'ZZT-CANCELLED',
      so_number: 'SO-CANCELLED',
      ack_state: 'awaiting',
      state: 'cancelled',
    });
    listOrderInquiryWorklist.mockResolvedValue(
      envelope([awaitingRow, changedRow, cancelledRow]),
    );
    acknowledgeOrderInquiryRows.mockResolvedValue({
      acknowledged: 2,
      linked_rows: 0,
      links: 0,
      after_horizon: 0,
    });
    renderClient();
    await screen.findByText('SO-AWAIT');

    // Disabled at 0, with the reason as the title (D3).
    const primary = screen.getByRole('button', { name: 'Confirm (0)' });
    expect(primary).toBeDisabled();
    expect(primary).toHaveAttribute(
      'title',
      'Tick rows still to confirm, or Select all matching.',
    );

    // "Upload purchase orders" is a menuitem in Actions, never a top-level button.
    expect(
      screen.queryByRole('button', { name: 'Upload purchase orders' }),
    ).toBeNull();
    openActionsMenu();
    expect(
      screen.getByRole('menuitem', { name: 'Upload purchase orders' }),
    ).toBeInTheDocument();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());

    // A cancelled row does not tick at all.
    expect(
      screen.getByLabelText('Select ZZT-CANCELLED on SO-CANCELLED'),
    ).toBeDisabled();

    fireEvent.click(screen.getByLabelText('Select ZZT-AWAIT on SO-AWAIT'));
    fireEvent.click(screen.getByLabelText('Select ZZT-CHANGED on SO-CHANGED'));

    const confirmButton = screen.getByRole('button', { name: 'Confirm (2)' });
    expect(confirmButton).toBeEnabled();
    fireEvent.click(confirmButton);

    expect(await screen.findByText('Confirm 2 rows?')).toBeInTheDocument();
    const listCallsBefore = listOrderInquiryWorklist.mock.calls.length;
    const summaryCallsBefore = getOrderInquiryWorklistSummary.mock.calls.length;
    const dialog = screen.getByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }));

    await waitFor(() =>
      expect(acknowledgeOrderInquiryRows).toHaveBeenCalledWith(
        ['row-await', 'row-changed'],
        expect.anything(),
      ),
    );
    expect(acknowledgeOrderInquiryRowsByFilter).not.toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith('Confirmed 2 rows');
    await waitFor(() =>
      expect(listOrderInquiryWorklist.mock.calls.length).toBeGreaterThan(
        listCallsBefore,
      ),
    );
    await waitFor(() =>
      expect(getOrderInquiryWorklistSummary.mock.calls.length).toBeGreaterThan(
        summaryCallsBefore,
      ),
    );
  });
});

describe('AC-CF-8: skipped rows are named in the toast (review round)', () => {
  it('the toast names how many were skipped, not just what got confirmed', async () => {
    const rows = [ackRow({ id: 'row-only', item_code: 'ZZT-ONLY', so_number: 'SO-ONLY' })];
    listOrderInquiryWorklist.mockResolvedValue(envelope(rows));
    acknowledgeOrderInquiryRows.mockResolvedValue({
      acknowledged: 1,
      linked_rows: 0,
      links: 0,
      after_horizon: 0,
      skipped: 2,
    });
    renderClient();
    await screen.findByText('SO-ONLY');

    fireEvent.click(screen.getByLabelText('Select ZZT-ONLY on SO-ONLY'));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm (1)' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }));

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Confirmed 1 row, 2 skipped'),
    );
  });
});

describe('AC-CF-7: Select all N matching posts filter, not row_ids', () => {
  it('the banner appears at N > loaded, and Confirm sends the current query + ack as `filter`', async () => {
    currentSearchParams = new URLSearchParams('query=SO123');
    const rows = [
      ackRow({ id: 'row-1', item_code: 'ZZT-1', so_number: 'SO-1' }),
      ackRow({ id: 'row-2', item_code: 'ZZT-2', so_number: 'SO-2' }),
    ];
    listOrderInquiryWorklist.mockResolvedValue(envelope(rows, 40));
    // Confirm (N) reads its count off `summary.ack.to_confirm` (review round fix,
    // AC-CF-7), never the list's own `total` - every eligible row in this filtered
    // scope happens to be 40 too here, so the banner and the button agree.
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      ack: { awaiting: 40, acknowledged: 0, changed: 0, rejected: 0, to_confirm: 40 },
    });
    acknowledgeOrderInquiryRowsByFilter.mockResolvedValue({
      acknowledged: 40,
      linked_rows: 0,
      links: 0,
      after_horizon: 0,
    });
    renderClient();
    await screen.findByText('SO-1');

    fireEvent.click(screen.getByLabelText('Select all rows on this page'));

    const banner = await screen.findByRole('button', {
      name: 'Select all 40 records',
    });
    fireEvent.click(banner);

    const confirmButton = await screen.findByRole('button', {
      name: 'Confirm (40)',
    });
    fireEvent.click(confirmButton);
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }));

    await waitFor(() =>
      expect(acknowledgeOrderInquiryRowsByFilter).toHaveBeenCalledWith(
        expect.objectContaining({ query: 'SO123', ack: 'to_confirm' }),
        expect.anything(),
      ),
    );
    expect(acknowledgeOrderInquiryRows).not.toHaveBeenCalled();
  });
});

describe('AC-CF-9: no acknowledge grant, no Confirm button', () => {
  it('renders no Confirm button at all for a CS principal', async () => {
    granted = new Set(['projects.order_inquiry.action']);
    renderClient();
    await screen.findByText('SO385126');

    expect(screen.queryByRole('button', { name: /^Confirm \(/ })).toBeNull();
  });
});

describe('AC-CF-10: confirmed rows leave the To confirm view', () => {
  it('the list query refetches once the mutation resolves', async () => {
    const rows = [ackRow({ id: 'row-only', item_code: 'ZZT-ONLY', so_number: 'SO-ONLY' })];
    listOrderInquiryWorklist.mockResolvedValue(envelope(rows));
    acknowledgeOrderInquiryRows.mockResolvedValue({
      acknowledged: 1,
      linked_rows: 0,
      links: 0,
      after_horizon: 0,
    });
    renderClient();
    await screen.findByText('SO-ONLY');

    fireEvent.click(screen.getByLabelText('Select ZZT-ONLY on SO-ONLY'));
    const before = listOrderInquiryWorklist.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'Confirm (1)' }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(acknowledgeOrderInquiryRows).toHaveBeenCalled());
    await waitFor(() =>
      expect(listOrderInquiryWorklist.mock.calls.length).toBeGreaterThan(before),
    );
  });
});

describe('AC-CF-12: the To confirm tile', () => {
  it('reads summary.ack.to_confirm and clicking it sets ack=to_confirm', async () => {
    currentSearchParams = new URLSearchParams('ack=rejected');
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      ack: { awaiting: 2, acknowledged: 1, changed: 1, rejected: 0, to_confirm: 3 },
    });
    renderClient();
    await screen.findByText('SO385126');

    expect(
      screen.getByTestId('order-inquiry-strip-to-confirm-count'),
    ).toHaveTextContent('3');

    fireEvent.click(screen.getByTestId('order-inquiry-strip-to-confirm'));

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ ack: 'to_confirm' }),
      ),
    );
  });
});

describe('AC-CF-17: the remembered sort drives the first list call, and a change PUTs it back', () => {
  it('opens sorted the way the memory says, then a new column click persists', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'so_number', desc: true }],
      filters: null,
      filtersVersion: 1,
    });
    renderClient();
    await screen.findByText('SO385126');

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'so_number', dir: 'desc' }),
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Qty' }));

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'qty', dir: 'asc' }),
      ),
    );

    // Found by CONTENT, not by `.at(-1)`: another test in this file may still have an
    // 800ms real debounce timer in flight from an EARLIER render (`debounce()` uses a
    // raw `setTimeout` RTL's `cleanup()` cannot cancel), which can land a stale call
    // here after this test's own genuine one. Matching on the 'qty' sort this test is
    // actually about is immune to that interleaving; asserting `.at(-1)` is not.
    await waitFor(
      () =>
        expect(
          service.upsertUserListColumnConfig.mock.calls.some(
            ([, payload]) =>
              JSON.stringify((payload as { sorting: unknown }).sorting) ===
              JSON.stringify([{ id: 'qty', desc: false }]),
          ),
        ).toBe(true),
      { timeout: 3000 },
    );
  });
});

describe('AC-CF-18: a remembered filter with no URL param seeds the first list call', () => {
  it('an unnamed-in-URL `location` comes from the memory', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'delivery_date', desc: false }],
      filters: { location: 'SRT-HQ' },
      filtersVersion: 1,
    });
    renderClient();
    await screen.findByText('SO385126');

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ location: 'SRT-HQ' }),
      ),
    );
  });

  it('a filter set here survives leaving the page and coming back on the SAME warm cache - the return visit asks with it, and nothing behind it writes it away (browser pass 17 Sep)', async () => {
    getOrderInquiryWorklistSummary.mockResolvedValue({
      ...MOCK_WORKLIST_SUMMARY,
      locations: [{ id: 'BRW-IR', label: 'BRW-IR', rows: 3 }],
    });
    // One SPA session: the cache OUTLIVES this page's unmount (no `gcTime: 0` here,
    // unlike `renderClient`), which is what makes the return visit a cache HIT with no
    // second GET - exactly what the browser measured, and the shape the defect needed.
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const first = render(
      <QueryClientProvider client={client}>
        <OrderInquiriesClient />
      </QueryClientProvider>,
    );
    await screen.findByText('SO385126');

    openFilters();
    fireEvent.change(await screen.findByLabelText('Every location'), {
      target: { value: 'BRW-IR' },
    });

    // Found by CONTENT: the PUT this test's own press caused.
    await waitFor(
      () =>
        expect(
          service.upsertUserListColumnConfig.mock.calls.some(
            ([, payload]) =>
              ((payload as { filters?: Record<string, unknown> }).filters ?? {})
                .location === 'BRW-IR',
          ),
        ).toBe(true),
      { timeout: 3000 },
    );
    const putsBefore = service.upsertUserListColumnConfig.mock.calls.length;
    listOrderInquiryWorklist.mockClear();

    // Away through the sidebar and back: this page unmounts, the URL it wrote goes with
    // it (the sidebar link carries no params), and the return visit re-mounts.
    first.unmount();
    currentSearchParams = new URLSearchParams('');
    render(
      <QueryClientProvider client={client}>
        <OrderInquiriesClient />
      </QueryClientProvider>,
    );
    await screen.findByText('SO385126');

    // EVERY list call of the return visit carries the remembered location - not merely
    // one of them after a first, unfiltered request flashed the whole worklist.
    expect(listOrderInquiryWorklist).toHaveBeenCalled();
    for (const [params] of listOrderInquiryWorklist.mock.calls as [
      Record<string, unknown>,
    ][]) {
      expect(params.location).toBe('BRW-IR');
    }
    // The row was never re-read - so anything written from here is written over the
    // memory this session already holds (`staleTime: Infinity`, seeded by the PUT).
    expect(service.getUserListColumnConfig).toHaveBeenCalledTimes(1);

    // Past the hook's 800ms debounce: no write behind the re-mount, and certainly not
    // one that drops the location the way the measured `{ack: 'to_confirm'}` PUT did.
    await new Promise((resolve) => setTimeout(resolve, 1200));
    for (const [, payload] of service.upsertUserListColumnConfig.mock.calls.slice(
      putsBefore,
    ) as [string, { filters?: Record<string, unknown> }][]) {
      expect((payload.filters ?? {}).location).toBe('BRW-IR');
    }
  });
});

describe('AC-CF-19: page and search never reach the remembered-view PUT payload', () => {
  it('a sort change and a search box edit both leave the payload free of them', async () => {
    storedConfig({
      version: 1,
      sorting: [{ id: 'delivery_date', desc: false }],
      filters: null,
      filtersVersion: 1,
    });
    renderClient();
    await screen.findByText('SO385126');

    fireEvent.click(screen.getByRole('button', { name: 'Qty' }));
    fireEvent.change(screen.getByLabelText('Search order inquiry rows'), {
      target: { value: 'ZZT-SEARCH' },
    });

    // Found by CONTENT (see the AC-CF-17 test): the write THIS test's own qty click
    // caused, not whatever a differently-timed call from another test happens to be
    // last. Every recorded call is asserted, not only this one - the claim is that page
    // and search NEVER reach the payload, from any of this file's writers.
    await waitFor(
      () =>
        expect(
          service.upsertUserListColumnConfig.mock.calls.some(
            ([, payload]) =>
              JSON.stringify((payload as { sorting: unknown }).sorting) ===
              JSON.stringify([{ id: 'qty', desc: false }]),
          ),
        ).toBe(true),
      { timeout: 3000 },
    );
    for (const [, payload] of service.upsertUserListColumnConfig.mock.calls as [
      string,
      Record<string, unknown>,
    ][]) {
      expect(payload).not.toHaveProperty('page');
      expect(payload).not.toHaveProperty('pageIndex');
      expect(payload).not.toHaveProperty('query');
      expect(payload).not.toHaveProperty('search');
      expect(
        (payload.filters as Record<string, unknown> | null) ?? {},
      ).not.toHaveProperty('query');
    }
  });
});

describe('AC-CF-20: a URL param wins for this visit, and is written back', () => {
  it('an explicit `?location=` overrides the remembered one and gets persisted', async () => {
    currentSearchParams = new URLSearchParams('location=OTHER-LOC');
    storedConfig({
      version: 1,
      sorting: [{ id: 'delivery_date', desc: false }],
      filters: { location: 'SRT-HQ' },
      filtersVersion: 1,
    });
    renderClient();
    await screen.findByText('SO385126');

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ location: 'OTHER-LOC' }),
      ),
    );

    // Found by CONTENT (see the AC-CF-17 test for why `.at(-1)` is not safe here).
    await waitFor(
      () =>
        expect(
          service.upsertUserListColumnConfig.mock.calls.some(
            ([, payload]) =>
              ((payload as { filters?: Record<string, unknown> }).filters ?? {})
                .location === 'OTHER-LOC',
          ),
        ).toBe(true),
      { timeout: 3000 },
    );
  });
});

describe('AC-CF-21: the first fetch waits for the memory', () => {
  it('no list call goes out while the preferences fetch is still pending', async () => {
    let resolveConfig!: (value: unknown) => void;
    service.getUserListColumnConfig.mockReturnValue(
      new Promise((resolve) => {
        resolveConfig = resolve;
      }),
    );
    renderClient();

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(listOrderInquiryWorklist).not.toHaveBeenCalled();

    resolveConfig({ listing_key: LISTING_KEY, config: null });

    await waitFor(() => expect(listOrderInquiryWorklist).toHaveBeenCalled());
  });
});

describe('AC-CF-23: Choose document (1) is offered for any ticked row that is not cancelled', () => {
  it('a single ticked PLACED row leaves the menu item enabled, not just a raised one', async () => {
    const placedRow = ackRow({
      id: 'row-placed',
      item_code: 'ZZT-PLACED',
      so_number: 'SO-PLACED',
      state: 'placed',
      ack_state: 'acknowledged',
    });
    listOrderInquiryWorklist.mockResolvedValue(envelope([placedRow]));
    renderClient();
    await screen.findByText('SO-PLACED');

    fireEvent.click(screen.getByLabelText('Select ZZT-PLACED on SO-PLACED'));
    openActionsMenu();

    const item = screen.getByRole('menuitem', { name: 'Choose document (1)' });
    expect(item).not.toHaveAttribute('aria-disabled', 'true');
  });

  it('a single ticked ACTIONED row leaves the menu item enabled too', async () => {
    const actionedRow = ackRow({
      id: 'row-actioned',
      item_code: 'ZZT-ACTIONED',
      so_number: 'SO-ACTIONED',
      state: 'actioned',
      ack_state: 'acknowledged',
    });
    listOrderInquiryWorklist.mockResolvedValue(envelope([actionedRow]));
    renderClient();
    await screen.findByText('SO-ACTIONED');

    fireEvent.click(screen.getByLabelText('Select ZZT-ACTIONED on SO-ACTIONED'));
    openActionsMenu();

    const item = screen.getByRole('menuitem', { name: 'Choose document (1)' });
    expect(item).not.toHaveAttribute('aria-disabled', 'true');
  });
});

describe('Unconfirm (N) (PLAN-oi-worklist-split-customer-project.md, owner 18 Sep 2026)', () => {
  it('reads the ticked acknowledged/changed count, calls the service with those ids, and toasts', async () => {
    const acknowledgedRow = ackRow({
      id: 'row-ack',
      item_code: 'ZZT-ACK',
      so_number: 'SO-ACK',
      ack_state: 'acknowledged',
      state: 'raised',
    });
    const changedRow = ackRow({
      id: 'row-changed-uc',
      item_code: 'ZZT-CHANGED-UC',
      so_number: 'SO-CHANGED-UC',
      ack_state: 'changed',
      state: 'raised',
    });
    const awaitingRow = ackRow({
      id: 'row-await-uc',
      item_code: 'ZZT-AWAIT-UC',
      so_number: 'SO-AWAIT-UC',
      ack_state: 'awaiting',
      state: 'raised',
    });
    listOrderInquiryWorklist.mockResolvedValue(
      envelope([acknowledgedRow, changedRow, awaitingRow]),
    );
    unacknowledgeOrderInquiryRows.mockResolvedValue({ updated: 2, skipped: 0 });
    renderClient();
    await screen.findByText('SO-ACK');

    openActionsMenu();
    // Disabled at 0 ticked, with a reason (same D3 pattern the sibling actions use).
    expect(screen.getByRole('menuitem', { name: 'Unconfirm (0)' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Select ZZT-ACK on SO-ACK'));
    fireEvent.click(screen.getByLabelText('Select ZZT-CHANGED-UC on SO-CHANGED-UC'));
    fireEvent.click(screen.getByLabelText('Select ZZT-AWAIT-UC on SO-AWAIT-UC'));

    openActionsMenu();
    // Only the acknowledged + changed rows count - the awaiting one is already there.
    const item = screen.getByRole('menuitem', { name: 'Unconfirm (2 of 3)' });
    expect(item).not.toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(item);

    await waitFor(() =>
      expect(unacknowledgeOrderInquiryRows).toHaveBeenCalledWith([
        'row-ack',
        'row-changed-uc',
      ]),
    );
    expect(toast.success).toHaveBeenCalledWith('2 rows back to To confirm');
  });

  it('is not offered at all without the acknowledge grant', async () => {
    granted = new Set(['projects.order_inquiry.action']);
    const acknowledgedRow = ackRow({
      id: 'row-ack-2',
      item_code: 'ZZT-ACK-2',
      so_number: 'SO-ACK-2',
      ack_state: 'acknowledged',
      state: 'raised',
    });
    listOrderInquiryWorklist.mockResolvedValue(envelope([acknowledgedRow]));
    renderClient();
    await screen.findByText('SO-ACK-2');

    openActionsMenu();
    expect(screen.queryByRole('menuitem', { name: /Unconfirm/ })).toBeNull();
  });

  it('N4 (review round 1): a result with skipped > 0 warns instead of a plain success', async () => {
    const acknowledgedRow = ackRow({
      id: 'row-ack-3',
      item_code: 'ZZT-ACK-3',
      so_number: 'SO-ACK-3',
      ack_state: 'acknowledged',
      state: 'raised',
    });
    listOrderInquiryWorklist.mockResolvedValue(envelope([acknowledgedRow]));
    unacknowledgeOrderInquiryRows.mockResolvedValue({ updated: 1, skipped: 1 });
    renderClient();
    await screen.findByText('SO-ACK-3');

    fireEvent.click(screen.getByLabelText('Select ZZT-ACK-3 on SO-ACK-3'));
    openActionsMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Unconfirm (1)' }));

    await waitFor(() => expect(unacknowledgeOrderInquiryRows).toHaveBeenCalled());
    expect(toast.warning).toHaveBeenCalledWith('1 row back to To confirm, 1 skipped');
    expect(toast.success).not.toHaveBeenCalled();
  });
});
