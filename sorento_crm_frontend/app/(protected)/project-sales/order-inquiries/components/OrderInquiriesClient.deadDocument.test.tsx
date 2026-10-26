/**
 * LINKAGE-UNIFY U3 (AC-D3; PLAN section 9): the worklist filters carry a "Dead document"
 * select with the options "PO cancelled" and "SPO withdrawn"; picking one sends
 * `dead_document=<value>`. Same harness and mocks as `OrderInquiriesClient.projectFilter.test.tsx`.
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

const granted = new Set(['projects.order_inquiry.action', 'projects.order_inquiries.acknowledge']);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((slug) => granted.has(slug)),
  usePermissions: () => ({ permissions: [...granted], permissionSet: granted, isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

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
const getUnplaceAllPreview = vi.fn();
const getOrderInquiryPoCandidates = vi.fn();

vi.mock('../../_shared/services/orderInquiryService', () => ({
  listOrderInquiryWorklist: (...args: unknown[]) => listOrderInquiryWorklist(...args),
  getOrderInquiryWorklistSummary: (...args: unknown[]) => getOrderInquiryWorklistSummary(...args),
  exportOrderInquiryWorklistXlsx: vi.fn(),
  autoPlaceOrderInquiryRows: vi.fn(),
  getUnplaceAllPreview: (...args: unknown[]) => getUnplaceAllPreview(...args),
  unplaceAllOrderInquiryRows: vi.fn(),
  acknowledgeOrderInquiryRows: vi.fn(),
  rejectOrderInquiryRows: vi.fn(),
  linkNowOrderInquiryRows: vi.fn(),
  getOrderInquiryPoCandidates: (...args: unknown[]) => getOrderInquiryPoCandidates(...args),
  getOrderInquiryUploadJob: vi.fn(),
  unplaceOrderInquiryRow: vi.fn(),
}));

vi.mock('../../_shared/services/orderInquiryMatrixService', () => ({
  getOrderInquiryMatrix: vi.fn(async () => ({ data: [] })),
}));
vi.mock('../../../scm/reorder/components/OutstandingUploadDialog', () => ({
  OutstandingUploadDialog: () => null,
}));
vi.mock('@/components/upload-activity/useUploadActivity', () => ({
  useUploadActivity: () => ({
    sessions: [], badgeCount: 0, hasInFlight: false, refetch: vi.fn(), isLoading: false,
    dismissed: new Set<string>(),
  }),
}));
vi.mock('../../_shared/services/fileDownload', () => ({
  saveBlobAs: vi.fn(),
  filenameFromContentDisposition: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value, onChange, options, placeholder, id,
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
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiriesClient />
    </QueryClientProvider>,
  );
}

function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  listOrderInquiryWorklist.mockResolvedValue(envelope(MOCK_WORKLIST_ROWS));
  getOrderInquiryWorklistSummary.mockResolvedValue({ ...MOCK_WORKLIST_SUMMARY });
  getUnplaceAllPreview.mockResolvedValue({ count: 0, product_code: null, product_name: null });
  getOrderInquiryPoCandidates.mockResolvedValue([]);
  getUserListColumnConfig.mockResolvedValue({
    listing_key: 'projects.projects.view::order-inquiry-worklist',
    config: null,
  });
});

describe('AC-D3: the "Dead document" filter', () => {
  it('offers "PO cancelled" and "SPO withdrawn", and picking one sends dead_document', async () => {
    renderClient();
    await screen.findByText('SO385126');
    openFilters();

    const option = (await screen.findByRole('option', { name: 'PO cancelled' })) as HTMLOptionElement;
    expect(screen.getByRole('option', { name: 'SPO withdrawn' })).toBeTruthy();
    const select = option.parentElement as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'po_cancelled' } });

    await waitFor(() =>
      expect(listOrderInquiryWorklist).toHaveBeenCalledWith(
        expect.objectContaining({ dead_document: 'po_cancelled' }),
      ),
    );
  });
});
