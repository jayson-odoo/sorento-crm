/**
 * OI-WHOLE-SO-CANCEL v2 (F1c, crew ruling 12 Nov: same rule for every OI-list filter), red: the
 * purchasing Lines worklist has a "State" column printing the row's own cover state with the
 * same words the State filter offers (`STATE_LABEL`), sortable and hideable; the filter's
 * option labels are exactly what that column prints. Harness copied from
 * `OrderInquiriesClient.confirm.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  renderHook,
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
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';
import { STATE_LABEL } from '../../_shared/components/OrderInquiryVerbPill';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';

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

type Col = ColumnDef<OrderInquiryWorklistRow> & { id?: string; accessorKey?: string };

function stateColumnOf(columns: Col[]): Col | undefined {
  return columns.find((c) => c.id === 'state' || c.accessorKey === 'state');
}

function StateOnly({ rows }: { rows: OrderInquiryWorklistRow[] }) {
  const named = stateColumnOf(useOrderInquiryWorklistColumns() as Col[]);
  if (!named) throw new Error('the worklist has no State column');
  const table = useReactTable({ data: rows, columns: [named], getCoreRowModel: getCoreRowModel() });
  return (
    <table>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id} data-testid={`row-${row.original.id}`}>
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function cellTextFor(state: string): string {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const row = { ...MOCK_WORKLIST_ROWS[1], id: `r-${state}`, state } as OrderInquiryWorklistRow;
  const { unmount } = render(
    <QueryClientProvider client={client}>
      <StateOnly rows={[row]} />
    </QueryClientProvider>,
  );
  const text = screen.getByTestId(`row-r-${state}`).textContent?.trim() ?? '';
  unmount();
  return text;
}

describe('F1c: the State column', () => {
  it('exists, titled State, sortable and hideable', () => {
    const client = new QueryClient();
    const { result } = renderHook(() => useOrderInquiryWorklistColumns(), {
      wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
    });
    const column = stateColumnOf(result.current as Col[]);
    expect(column, 'the worklist has no State column').toBeDefined();
    expect((column as { meta?: { headerTitle?: string } }).meta?.headerTitle).toBe('State');
    expect((column as { enableSorting?: boolean }).enableSorting).not.toBe(false);
    expect((column as { enableHiding?: boolean }).enableHiding).not.toBe(false);
  });

  it.each(['raised', 'partly_linked', 'placed', 'actioned', 'cancelled'])(
    'prints the STATE_LABEL word for a %s row',
    (state) => {
      expect(cellTextFor(state)).toBe(STATE_LABEL[state]);
    },
  );

  it('a cancelled row reads "Cancelled"', () => {
    expect(cellTextFor('cancelled')).toBe('Cancelled');
  });
});

describe('F1c: the State filter offers exactly what the column prints', () => {
  it('each by_state option label equals the column cell text for a row in that state', async () => {
    renderClient();
    await screen.findByText(MOCK_WORKLIST_ROWS[0].so_number as string);
    openFilters();
    const select = (await screen.findByLabelText('Every state')) as HTMLSelectElement;
    const options = Array.from(select.options).filter((option) => option.value !== '');
    expect(options.length).toBeGreaterThan(0);

    for (const option of options) {
      const label = (option.textContent ?? '').replace(/\s*\(\d+\)$/, '').trim();
      expect(label, `option ${option.value}`).toBe(cellTextFor(option.value));
    }
  });
});
