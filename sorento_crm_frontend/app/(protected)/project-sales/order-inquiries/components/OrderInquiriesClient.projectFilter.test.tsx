/**
 * AC-19 (`PLAN-oi-project-label-from-so.md` section 5, `oi-project-label-from-so-
 * acceptance-criteria.md`): the Project filter follows the Project column - it sends
 * `project=<label>` (never `project_id`), and a filter blob stored before this shipped
 * (holding only the old `project_id` key) restores to no project filter rather than a
 * stale id the Project select no longer has an option for.
 *
 * A sibling of `OrderInquiriesClient.test.tsx` rather than an addition to it (that file
 * is already 1200+ lines) - same mocking pattern, narrowed to the one filter.
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

import { OrderInquiriesClient } from './OrderInquiriesClient';

function envelope(rows: OrderInquiryWorklistRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 25 };
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

/** Radix opens its dropdown menus on pointerdown, which fireEvent.click does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

const PROJECT_FACET = [
  { id: 'ALPHA', label: 'ALPHA', rows: 2 },
  { id: 'BETA', label: 'BETA', rows: 1 },
];

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  currentSearchParams = new URLSearchParams('');
  listOrderInquiryWorklist.mockResolvedValue(envelope(MOCK_WORKLIST_ROWS));
  getOrderInquiryWorklistSummary.mockResolvedValue({
    ...MOCK_WORKLIST_SUMMARY,
    projects: PROJECT_FACET,
  });
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
  // Nothing stored, by default - AC-19's own "stored blob" test overrides this.
  getUserListColumnConfig.mockResolvedValue({
    listing_key: 'projects.projects.view::order-inquiry-worklist',
    config: null,
  });
});

describe('AC-19: the Project filter follows the column (PLAN-oi-project-label-from-so.md S5)', () => {
  it('picking an option sends project=<label> and no project_id', async () => {
    renderClient();
    await screen.findByText('SO385126');

    openFilters();
    fireEvent.change(await screen.findByLabelText('Every project'), {
      target: { value: 'ALPHA' },
    });

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ project: 'ALPHA' }),
      ),
    );
    const lastCall = listOrderInquiryWorklist.mock.calls.at(-1)?.[0] as Record<
      string,
      unknown
    >;
    expect(lastCall.project_id).toBeUndefined();
  });

  it('a blob stored before S5 shipped, holding only project_id, restores to no project filter', async () => {
    getUserListColumnConfig.mockResolvedValue({
      listing_key: 'projects.projects.view::order-inquiry-worklist',
      config: {
        version: 1,
        sorting: null,
        filters: { project_id: 'proj-4' },
        filtersVersion: 1,
      },
    });

    renderClient();
    await screen.findByText('SO385126');
    openFilters();

    const select = (await screen.findByLabelText(
      'Every project',
    )) as HTMLSelectElement;
    expect(select.value).toBe('');
    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalled(),
    );
    const lastCall = listOrderInquiryWorklist.mock.calls.at(-1)?.[0] as Record<
      string,
      unknown
    >;
    expect(lastCall.project).toBeUndefined();
    expect(lastCall.project_id).toBeUndefined();
  });

  it('clearing the filter drops the param', async () => {
    renderClient();
    await screen.findByText('SO385126');

    openFilters();
    const select = await screen.findByLabelText('Every project');
    fireEvent.change(select, { target: { value: 'ALPHA' } });
    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ project: 'ALPHA' }),
      ),
    );

    fireEvent.change(select, { target: { value: '' } });

    await waitFor(() => {
      const lastCall = listOrderInquiryWorklist.mock.calls.at(-1)?.[0] as Record<
        string,
        unknown
      >;
      expect(lastCall.project).toBeUndefined();
    });
  });
});
