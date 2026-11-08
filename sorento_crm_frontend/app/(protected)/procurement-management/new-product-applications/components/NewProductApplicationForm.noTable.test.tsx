/**
 * NPA-FROM-SI (owner hand test, 8 Nov): an application raised from a stock inquiry has no product
 * table and writes `lines: []`; a standalone one keeps today's table; an older SI application that
 * already has lines shows them read-only.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { NewProductApplicationPrefill } from '@/types/newProductApplication';

const mock = vi.hoisted(() => ({
  createAsync: vi.fn(),
  updateAsync: vi.fn(),
  submitAsync: vi.fn(),
  prefill: undefined as unknown,
  existing: undefined as unknown,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/procurement-management/new-product-applications/npa-1',
}));
vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));
vi.mock('../hooks/useNewProductApplications', () => ({
  useNewProductApplicationMutations: () => ({
    create: { mutateAsync: mock.createAsync, isPending: false },
    update: { mutateAsync: mock.updateAsync, isPending: false },
    submit: { mutateAsync: mock.submitAsync, isPending: false },
  }),
  useNewProductApplicationQuery: () => ({ data: mock.existing, isLoading: false }),
  useNewProductApplicationPrefillQuery: () => ({
    data: mock.prefill,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useNewProductApplicationLookups: () => ({
    brands: async () => [],
    products: async () => [],
    reuse: async () => [],
  }),
}));
vi.mock('../services/newProductApplicationService', () => ({
  searchStockInquiryOptions: vi.fn(async () => []),
  linkNewProductApplicationAttachment: vi.fn(),
}));
vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService',
  () => ({ lookupCustomersForRequest: vi.fn(async () => []) }),
);
vi.mock('@/components/common/LinkAttachmentBrowserDialog', () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
}));

import NewProductApplicationForm from './NewProductApplicationForm';

const PREFILL: NewProductApplicationPrefill = {
  stock_inquiry_id: 'si-1',
  stock_inquiry_number: 'SI26-0412',
  customer_id: null,
  customer_name: 'EXAMPLE DEVELOPER SDN BHD',
  project_name: 'EXAMPLE RESIDENCE, TOWER B',
  needed_by: null,
  remark: null,
  lines: [{ proposed_code: 'XY-1234-MB', description: 'Example sinks', expected_qty: '55' }],
};

function renderForm(props: { applicationId?: string; stockInquiryId?: string } = {}) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <NewProductApplicationForm {...props} />
    </QueryClientProvider>,
  );
}

const saveDraft = () => fireEvent.click(screen.getByRole('button', { name: /save as draft/i }));

const saved = (over: Record<string, unknown> = {}) => ({
  id: 'npa-1',
  status: 'draft',
  status_label: 'Draft',
  source: 'staff',
  application_no: 'NPA-000001',
  applicant_name: 'Owner',
  created_at: '2026-10-17T01:00:00',
  stock_inquiry_id: null,
  customer_id: null,
  customer_name: 'EXAMPLE DEVELOPER SDN BHD',
  project_name: null,
  needed_by: null,
  remark: null,
  lead_time: null,
  attachments: [],
  lines: [
    { id: 'l-1', line_no: 1, proposed_code: 'XY-1', description: 'First sink' },
    { id: 'l-2', line_no: 2, proposed_code: 'XY-2', description: 'Second sink' },
  ],
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  mock.prefill = undefined;
  mock.existing = undefined;
  mock.createAsync.mockResolvedValue({ id: 'npa-1' });
  mock.updateAsync.mockResolvedValue({ id: 'npa-1' });
  mock.submitAsync.mockResolvedValue({ id: 'npa-1' });
});

describe('staff form from a stock inquiry', () => {
  it('renders no product table and no add control, and saves lines: []', async () => {
    mock.prefill = PREFILL;
    renderForm({ stockInquiryId: 'si-1' });
    await screen.findByText('NEW PRODUCT APPLICATION');
    await waitFor(() =>
      expect((screen.getByLabelText('Customer') as HTMLInputElement).value).toBe(
        'EXAMPLE DEVELOPER SDN BHD',
      ),
    );
    expect(screen.queryByRole('columnheader', { name: /product code/i })).toBeNull();
    expect(screen.queryByLabelText('Product type')).toBeNull();
    expect(screen.queryByRole('button', { name: /add (row|product)/i })).toBeNull();

    saveDraft();
    await waitFor(() => expect(mock.createAsync).toHaveBeenCalledTimes(1));
    const body = mock.createAsync.mock.calls[0][0];
    expect(body.stock_inquiry_id).toBe('si-1');
    expect(body.lines).toEqual([]);
  });

  it('an older SI application with lines shows them read-only: text, no inputs, no add', async () => {
    mock.existing = saved({ stock_inquiry_id: 'si-1', stock_inquiry_number: 'SI26-0412' });
    renderForm({ applicationId: 'npa-1' });
    expect(await screen.findByText('First sink')).toBeInTheDocument();
    expect(screen.getByText('Second sink')).toBeInTheDocument();
    expect(screen.queryByLabelText('Product type')).toBeNull();
    expect(screen.queryByRole('button', { name: /add (row|product)/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^remove row/i })).toBeNull();
  });
});

describe('staff form standalone (no stock inquiry)', () => {
  it('still renders today\'s table with Add row', async () => {
    renderForm();
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.getByRole('columnheader', { name: /product code/i })).toBeInTheDocument();
    expect(screen.getAllByLabelText('Product type')).toHaveLength(1);
    expect(screen.getByRole('button', { name: /add row/i })).toBeInTheDocument();
  });

  it('a saved standalone draft keeps editable rows', async () => {
    mock.existing = saved();
    renderForm({ applicationId: 'npa-1' });
    await screen.findByText('NEW PRODUCT APPLICATION');
    expect(screen.getAllByLabelText('Product type')).toHaveLength(2);
  });
});
