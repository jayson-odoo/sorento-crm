/**
 * M5-06 - the create-mode "Line Items" table (a second, near-duplicate copy
 * of PurchaseRequestDocumentEditCard's table, rendered when there is no
 * requestId yet) renders on DataGrid instead of a raw `<Table>`. Same
 * inline-editing shape as PurchaseRequestDocumentEditCard.lineItems.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/procurement-management/purchase-requests/new',
}));

vi.mock('../hooks/usePurchaseRequests', () => ({
  usePurchaseRequest: () => ({ data: undefined, isLoading: false }),
  useCreatePurchaseRequest: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePurchaseRequest: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePurchaseRequestAndReply: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('../services/purchaseRequestService', () => ({
  searchProjectsForLink: vi.fn().mockResolvedValue([]),
  getOrCreateViewLink: vi.fn(),
}));

vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({
  usePublicViewLinksEnabled: () => false,
}));

vi.mock('@/components/common/LookupBoundField', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock(
  '@/app/(protected)/master-data-management/shared/components/RequestorContactSelect',
  () => ({ RequestorContactSelect: () => null }),
);

vi.mock('./PurchaseRequestAttachmentsSection', () => ({
  __esModule: true,
  default: () => null,
}));

import PurchaseRequestForm from './PurchaseRequestForm';

function renderForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PurchaseRequestForm />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('PurchaseRequestForm - create-mode line items DataGrid', () => {
  it('renders the column headers and the default line the form starts with', () => {
    renderForm();

    expect(screen.getByText('Item Code')).toBeInTheDocument();
    expect(screen.getByText('Qty')).toBeInTheDocument();
    expect(screen.getByText('Remark')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Item code')).toBeInTheDocument();
  });

  it('adding a row keeps focus on the input the reader is typing into', () => {
    renderForm();

    fireEvent.click(screen.getByRole('button', { name: /Add row/i }));

    const inputs = screen.getAllByPlaceholderText('Item code');
    expect(inputs).toHaveLength(2);

    const second = inputs[1] as HTMLInputElement;
    second.focus();
    fireEvent.change(second, { target: { value: 'ITEM-Z' } });

    expect(document.activeElement).toBe(second);
    expect(second.value).toBe('ITEM-Z');
  });
});
