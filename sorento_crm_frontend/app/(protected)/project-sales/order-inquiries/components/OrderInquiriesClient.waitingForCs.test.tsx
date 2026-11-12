/**
 * OI-WHOLE-SO-CANCEL v2 (AC-V2-3), red: purchasing cannot Confirm a row that is waiting for
 * CS. Handled the way a cancelled row is today: its tick box is disabled, here with the
 * reason as its title, so it never reaches Confirm (N). Harness copied from
 * `OrderInquiriesClient.confirm.test.tsx`.
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
// These filters are multi-selects now (FILTER-MULTISELECT PR6); a one-value pick stands in for them here.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
    placeholder,
    id,
  }: {
    value: string[];
    onChange: (next: string[]) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    id?: string;
  }) => (
    <select
      aria-label={id ?? placeholder ?? 'select'}
      value={value[0] ?? ''}
      onChange={(event) => onChange(event.target.value ? [event.target.value] : [])}
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

describe('AC-V2-3 (S3): a waiting row can be ticked, but Confirm skips it and says so', () => {
  it('ticks a waiting_for_cs row freely; Confirm sends only the ordinary row and names the skipped one', async () => {
    const waitingRow = ackRow({
      id: 'row-waiting',
      item_code: 'ZZT-WAIT',
      so_number: 'SO-WAIT',
      ack_state: 'awaiting',
      state: 'raised',
      waiting_for_cs: true,
    } as Partial<OrderInquiryWorklistRow>);
    const plainRow = ackRow({
      id: 'row-plain',
      item_code: 'ZZT-PLAIN',
      so_number: 'SO-PLAIN',
      ack_state: 'awaiting',
      state: 'raised',
    });
    listOrderInquiryWorklist.mockResolvedValue(envelope([waitingRow, plainRow]));
    acknowledgeOrderInquiryRows.mockResolvedValue({
      acknowledged: 1,
      linked_rows: 0,
      links: 0,
      after_horizon: 0,
    });

    renderClient();
    await screen.findByText('SO-WAIT');

    const waitingBox = screen.getByLabelText('Select ZZT-WAIT on SO-WAIT');
    expect(waitingBox).toBeEnabled();
    fireEvent.click(waitingBox);
    fireEvent.click(screen.getByLabelText('Select ZZT-PLAIN on SO-PLAIN'));

    fireEvent.click(screen.getByRole('button', { name: /^Confirm \(/ }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }));

    await waitFor(() =>
      expect(acknowledgeOrderInquiryRows).toHaveBeenCalledWith(
        ['row-plain'],
        expect.anything(),
      ),
    );
    const notices = [
      ...(toast.success as unknown as { mock: { calls: unknown[][] } }).mock.calls,
      ...(toast.warning as unknown as { mock: { calls: unknown[][] } }).mock.calls,
    ]
      .map((call) => String(call[0]))
      .join(' | ');
    const shown = `${notices} | ${document.body.textContent ?? ''}`;
    expect(shown).toMatch(/1 row (is )?waiting for CS/i);
    expect(shown).toMatch(/skipped/i);
  });
});
