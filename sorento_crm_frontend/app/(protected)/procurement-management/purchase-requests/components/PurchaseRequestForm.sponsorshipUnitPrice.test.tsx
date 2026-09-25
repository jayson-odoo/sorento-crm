/**
 * #1227: unit price is mandatory on every sponsorship form line, in system
 * create and edit alike - through the same zod `superRefine` idiom the
 * `sales_type` rule already uses (`purchase-request-schema.ts`). This file
 * covers CREATE (`PurchaseRequestForm` with no `requestId`, matching
 * `sponsorship-forms/new`); `PurchaseRequestDocumentEditCard.lineItems.test.tsx`
 * covers the shared column definitions EDIT renders through.
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
  usePathname: () => '/procurement-management/sponsorship-forms/new',
}));

const createMutateAsync = vi.fn();
vi.mock('../hooks/usePurchaseRequests', () => ({
  usePurchaseRequest: () => ({ data: undefined, isLoading: false }),
  useCreatePurchaseRequest: () => ({ mutateAsync: createMutateAsync, isPending: false }),
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
  return render(
    <QueryClientProvider client={client}>
      <PurchaseRequestForm defaultRequestType="sponsorship_form" />
    </QueryClientProvider>,
  );
}

/** Targets a line cell by its react-hook-form field name (`products.<i>.<field>`)
 *  rather than DOM position - the DataGrid table renders row-motion styles that
 *  can shift a plain positional query between two `fireEvent` calls. */
function lineInput(container: HTMLElement, index: number, field: string): HTMLInputElement {
  const el = container.querySelector<HTMLInputElement>(
    `input[name="products.${index}.${field}"]`,
  );
  if (!el) throw new Error(`no input named products.${index}.${field}`);
  return el;
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('PurchaseRequestForm - sponsorship unit price required (#1227)', () => {
  it('marks the U/P column required', () => {
    renderForm();
    expect(screen.getByText('U/P *')).toBeInTheDocument();
  });

  it('blocks Create and shows the inline message when a real line has no unit price', async () => {
    renderForm();

    fireEvent.change(screen.getByPlaceholderText('Item code'), {
      target: { value: 'ITEM-A' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Create/i }));

    expect(await screen.findByText('Unit price is required.')).toBeInTheDocument();
    expect(createMutateAsync).not.toHaveBeenCalled();
  });

  it('a fully blank filler line never blocks Create by itself', async () => {
    const { container } = renderForm();

    // A second, still-blank row - only the first line gets touched below.
    fireEvent.click(screen.getByRole('button', { name: /Add row/i }));
    fireEvent.change(lineInput(container, 0, 'item_code'), {
      target: { value: 'ITEM-A' },
    });
    fireEvent.change(lineInput(container, 0, 'quantity'), { target: { value: '2' } });
    fireEvent.change(lineInput(container, 0, 'unit_price'), { target: { value: '10' } });

    fireEvent.click(screen.getByRole('button', { name: /Create/i }));

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalled(), { timeout: 3000 });
    expect(screen.queryByText('Unit price is required.')).toBeNull();
  });
});
