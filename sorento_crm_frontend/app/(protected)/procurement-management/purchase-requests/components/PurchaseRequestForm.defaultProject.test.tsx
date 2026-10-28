/**
 * PROJECT-STAGES-SAMPLE AC-PS-21 (prefill) and AC-PS-27 (no project in the link).
 * `defaultProjectId` seeds the "Registered project (optional)" link; absent, it stays null.
 * Harness copied from PurchaseRequestForm.customerLink.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/procurement-management/purchase-requests/new',
}));

const ITEMS = [
  {
    customer_id: 'cust-302',
    debtor_name: 'CUSTOMER A SDN BHD',
    customer_code: '302-ZZT001',
    debtor_type: 'project_cash',
    sales_type: 'cash_sales',
  },
  {
    customer_id: 'cust-301',
    debtor_name: 'CASH (PERSON A)',
    customer_code: '301-ZZTC01',
    debtor_type: null,
    sales_type: null,
  },
];

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiFetch: vi.fn(async (url: string) => {
      const ok = (body: unknown) =>
        ({ ok: true, status: 200, json: async () => body }) as unknown as Response;
      if (String(url).includes('/purchase-requests/lookups/customers')) return ok(ITEMS);
      return ok([]);
    }),
  };
});

const createMutateAsync = vi.fn().mockResolvedValue({ id: 'new-1' });
vi.mock('../hooks/usePurchaseRequests', () => ({
  usePurchaseRequest: () => ({ data: undefined, isLoading: false }),
  useCreatePurchaseRequest: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdatePurchaseRequest: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePurchaseRequestAndReply: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('../services/purchaseRequestService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/purchaseRequestService')>()),
  searchProjectsForLink: vi.fn().mockResolvedValue([]),
  getOrCreateViewLink: vi.fn(),
}));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('@/components/common/LookupBoundField', () => ({ __esModule: true, default: () => null }));
vi.mock(
  '@/app/(protected)/master-data-management/shared/components/RequestorContactSelect',
  () => ({ RequestorContactSelect: () => null }),
);
vi.mock('./PurchaseRequestAttachmentsSection', () => ({ __esModule: true, default: () => null }));

import PurchaseRequestForm from './PurchaseRequestForm';

function renderForm(defaultProjectId?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const props = { defaultProjectId } as Record<string, unknown>;
  return render(
    <QueryClientProvider client={client}>
      <PurchaseRequestForm defaultRequestType="sponsorship_form" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

async function submitSponsorship() {
  const input = screen.getByLabelText('Customer Name');
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: 'ZZT' } });
  fireEvent.click(await screen.findByRole('option', { name: /CUSTOMER A SDN BHD/ }));
  fireEvent.change(screen.getByPlaceholderText('Item code'), { target: { value: 'ITEM-A' } });
  const qty = document.querySelector('input[name$=".quantity"]') as HTMLInputElement | null;
  if (qty) fireEvent.change(qty, { target: { value: '2' } });
  const up = document.querySelector('input[name$=".unit_price"]') as HTMLInputElement | null;
  if (up) fireEvent.change(up, { target: { value: '10' } });
  fireEvent.click(screen.getByRole('button', { name: /Create/i }));
  await waitFor(() => expect(createMutateAsync).toHaveBeenCalled(), { timeout: 3000 });
  return createMutateAsync.mock.calls[0][0] as { project_id?: string | null };
}

describe('PurchaseRequestForm default project', () => {
  it('AC-PS-21: defaultProjectId seeds project_id in the create payload', async () => {
    renderForm('p1');
    const payload = await submitSponsorship();
    expect(payload.project_id).toBe('p1');
  });

  it('AC-PS-27: without defaultProjectId project_id stays null', async () => {
    renderForm();
    const payload = await submitSponsorship();
    expect(payload.project_id ?? null).toBeNull();
  });
});
