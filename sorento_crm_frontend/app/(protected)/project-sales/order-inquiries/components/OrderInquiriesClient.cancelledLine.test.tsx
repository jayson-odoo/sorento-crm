/**
 * RED tests for `PLAN-oi-cancelled-line-used-confirm.md`, section 3.6 / AC-CL-2d, 16, 17
 * (`oi-cancelled-line-used-confirm-acceptance-criteria.md`).
 *
 * A NEW file (not an addition to `OrderInquiriesClient.test.tsx` or
 * `OrderInquiriesClient.confirm.test.tsx`) - AC-CL-20 keeps both those files, and every
 * other existing vitest file beside `OrderInquiriesClient.tsx`, green and UNCHANGED.
 *
 * Harness copied from `OrderInquiriesClient.confirm.test.tsx` (the fuller mock set: it
 * already stubs `acknowledgeOrderInquiryRowsByFilter` and `unacknowledgeOrderInquiryRows`,
 * which the real `useOrderInquiryHandshake` throws on an undefined import for otherwise).
 * `DataGrid` is NEVER mocked here, so `rowClassName` and `enableRowSelection` run for
 * real and are read straight off the rendered `<tr>`/checkbox.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  useHasAnyPermission: (slugs: string[]) => slugs.some((slug) => granted.has(slug)),
  usePermissions: () => ({
    permissions: [...granted],
    permissionSet: granted,
    isLoading: false,
  }),
}));

const routerReplace = vi.fn();
let currentSearchParams = new URLSearchParams('');
let currentPathname = '/project-sales/order-inquiries';

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: (...args: unknown[]) => routerReplace(...args),
  }),
  usePathname: () => currentPathname,
  useSearchParams: () => currentSearchParams,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));

const service = vi.hoisted(() => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: (...args: unknown[]) => service.getUserListColumnConfig(...args),
  upsertUserListColumnConfig: (...args: unknown[]) =>
    service.upsertUserListColumnConfig(...args),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

function storedConfig(config: Record<string, unknown> | null) {
  service.getUserListColumnConfig.mockResolvedValue({
    listing_key: 'projects.projects.view::order-inquiry-worklist',
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
  listOrderInquiryWorklist: (...args: unknown[]) => listOrderInquiryWorklist(...args),
  getOrderInquiryWorklistSummary: (...args: unknown[]) =>
    getOrderInquiryWorklistSummary(...args),
  exportOrderInquiryWorklistXlsx: (...args: unknown[]) =>
    exportOrderInquiryWorklistXlsx(...args),
  autoPlaceOrderInquiryRows: (...args: unknown[]) => autoPlaceOrderInquiryRows(...args),
  getUnplaceAllPreview: (...args: unknown[]) => getUnplaceAllPreview(...args),
  unplaceAllOrderInquiryRows: (...args: unknown[]) => unplaceAllOrderInquiryRows(...args),
  acknowledgeOrderInquiryRows: (...args: unknown[]) => acknowledgeOrderInquiryRows(...args),
  acknowledgeOrderInquiryRowsByFilter: (...args: unknown[]) =>
    acknowledgeOrderInquiryRowsByFilter(...args),
  unacknowledgeOrderInquiryRows: (...args: unknown[]) =>
    unacknowledgeOrderInquiryRows(...args),
  rejectOrderInquiryRows: (...args: unknown[]) => rejectOrderInquiryRows(...args),
  linkNowOrderInquiryRows: (...args: unknown[]) => linkNowOrderInquiryRows(...args),
  getOrderInquiryPoCandidates: (...args: unknown[]) => getOrderInquiryPoCandidates(...args),
  getOrderInquiryUploadJob: (...args: unknown[]) => getOrderInquiryUploadJob(...args),
  unplaceOrderInquiryRow: (...args: unknown[]) => unplaceOrderInquiryRow(...args),
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
      onClick={() => onQueued?.({ job_id: 'job-1', id: 'job-row-1', message: 'queued' })}
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

import { OrderInquiriesClient } from './OrderInquiriesClient';

function envelope(rows: OrderInquiryWorklistRow[], total?: number) {
  return { data: rows, total: total ?? rows.length, page: 1, limit: 25 };
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
  getUnplaceAllPreview.mockResolvedValue({ count: 0, product_code: null, product_name: null });
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

describe('AC-CL-2d: a line_cancelled row is greyed the same way a used row is', () => {
  it('applies the same row class to a line_cancelled row as to a redirected_to_pool row, and none to a plain row', async () => {
    const usedRow: OrderInquiryWorklistRow = {
      ...MOCK_WORKLIST_ROWS[0],
      id: 'row-used-grey',
      item_code: 'ZZT-USED-GREY',
      so_number: 'SO-USED-GREY',
      redirected_to_pool: true,
    };
    const cancelledLineRow = {
      ...MOCK_WORKLIST_ROWS[0],
      id: 'row-line-cancelled-grey',
      item_code: 'ZZT-CANCELLED-GREY',
      so_number: 'SO-CANCELLED-GREY',
      redirected_to_pool: false,
      // `line_cancelled` does not exist on `OrderInquiryWorklistRow` yet (Phase 2 FE not
      // built) - the coder adds it beside `redirected_to_pool`; cast rather than
      // `@ts-expect-error` so this line does not need editing again once the field lands.
      line_cancelled: true,
    } as OrderInquiryWorklistRow;
    const plainRow: OrderInquiryWorklistRow = {
      ...MOCK_WORKLIST_ROWS[0],
      id: 'row-plain-grey',
      item_code: 'ZZT-PLAIN-GREY',
      so_number: 'SO-PLAIN-GREY',
      redirected_to_pool: false,
    };
    listOrderInquiryWorklist.mockResolvedValue(
      envelope([usedRow, cancelledLineRow, plainRow]),
    );
    renderClient();
    await screen.findByText('SO-USED-GREY');

    const usedTr = screen.getByText('ZZT-USED-GREY').closest('tr') as HTMLElement;
    const cancelledTr = screen
      .getByText('ZZT-CANCELLED-GREY')
      .closest('tr') as HTMLElement;
    const plainTr = screen.getByText('ZZT-PLAIN-GREY').closest('tr') as HTMLElement;

    expect(usedTr.className).toContain('opacity-60');
    expect(cancelledTr.className).toContain('opacity-60');
    expect(plainTr.className).not.toContain('opacity-60');
  });
});

describe('AC-CL-16: a used row and a cancelled-line row stay tickable (guard, expected GREEN today)', () => {
  it('the checkbox is enabled for a used row and a line_cancelled row, disabled only for state=cancelled', async () => {
    // `enableRowSelection` on `OrderInquiriesClient.tsx` already reads ONLY
    // `row.original.state !== 'cancelled'` (line ~964) - neither `redirected_to_pool`
    // nor a future `line_cancelled` narrows it further. This test is a guard against
    // regression, not a red test: it is expected to PASS against today's code.
    const usedRow: OrderInquiryWorklistRow = {
      ...MOCK_WORKLIST_ROWS[0],
      id: 'row-used-select',
      item_code: 'ZZT-USED-SELECT',
      so_number: 'SO-USED-SELECT',
      state: 'actioned',
      redirected_to_pool: true,
    };
    const cancelledLineRow = {
      ...MOCK_WORKLIST_ROWS[0],
      id: 'row-line-cancelled-select',
      item_code: 'ZZT-LINE-CANCELLED-SELECT',
      so_number: 'SO-LINE-CANCELLED-SELECT',
      state: 'actioned',
      redirected_to_pool: false,
      line_cancelled: true,
    } as OrderInquiryWorklistRow;
    const rowStateCancelled: OrderInquiryWorklistRow = {
      ...MOCK_WORKLIST_ROWS[0],
      id: 'row-state-cancelled',
      item_code: 'ZZT-STATE-CANCELLED',
      so_number: 'SO-STATE-CANCELLED',
      state: 'cancelled',
    };
    listOrderInquiryWorklist.mockResolvedValue(
      envelope([usedRow, cancelledLineRow, rowStateCancelled]),
    );
    renderClient();
    await screen.findByText('SO-USED-SELECT');

    expect(
      screen.getByLabelText('Select ZZT-USED-SELECT on SO-USED-SELECT'),
    ).toBeEnabled();
    expect(
      screen.getByLabelText(
        'Select ZZT-LINE-CANCELLED-SELECT on SO-LINE-CANCELLED-SELECT',
      ),
    ).toBeEnabled();
    expect(
      screen.getByLabelText('Select ZZT-STATE-CANCELLED on SO-STATE-CANCELLED'),
    ).toBeDisabled();
  });
});

describe('AC-CL-17: the To confirm card toggles off on a second press, like the other three', () => {
  it('pressing To confirm while active clears the ack filter; pressing again sets it back', async () => {
    renderClient();
    await screen.findByText('SO385126');

    // Default: no `?ack=` in the URL opens on To confirm (AC-CF-11 precedent).
    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ ack: 'to_confirm' }),
      ),
    );
    const card = screen.getByTestId('order-inquiry-strip-to-confirm');
    expect(card).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('Clear filter: To confirm')).toBeInTheDocument();

    fireEvent.click(card);

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ ack: undefined }),
      ),
    );
    expect(screen.queryByLabelText('Clear filter: To confirm')).not.toBeInTheDocument();
    expect(screen.getByTestId('order-inquiry-strip-to-confirm')).toHaveAttribute(
      'aria-pressed',
      'false',
    );

    listOrderInquiryWorklist.mockClear();
    fireEvent.click(screen.getByTestId('order-inquiry-strip-to-confirm'));

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ ack: 'to_confirm' }),
      ),
    );
    expect(screen.getByTestId('order-inquiry-strip-to-confirm')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('guard: the Buy card still toggles on/off as today (untouched by this change)', async () => {
    renderClient();
    await screen.findByText('SO385126');

    const buyCard = screen.getByTestId('order-inquiry-strip-buy');
    expect(buyCard).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(buyCard);
    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ kind: 'buy' }),
      ),
    );
    expect(screen.getByTestId('order-inquiry-strip-buy')).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    fireEvent.click(screen.getByTestId('order-inquiry-strip-buy'));
    await waitFor(() =>
      expect(screen.getByTestId('order-inquiry-strip-buy')).toHaveAttribute(
        'aria-pressed',
        'false',
      ),
    );
  });
});
