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
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/procurement-management/sponsorship-forms/new',
}));

const createMutateAsync = vi.fn();
const updateAndReplyMutateAsync = vi.fn().mockResolvedValue({});
let mockRequest: unknown = undefined;
vi.mock('../hooks/usePurchaseRequests', () => ({
  usePurchaseRequest: () => ({ data: mockRequest, isLoading: false }),
  useCreatePurchaseRequest: () => ({ mutateAsync: createMutateAsync, isPending: false }),
  useUpdatePurchaseRequest: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePurchaseRequestAndReply: () => ({
    mutateAsync: updateAndReplyMutateAsync,
    isPending: false,
  }),
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

function renderEditForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseRequestForm requestId="req-1" expectedRequestType="sponsorship_form" />
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
  mockRequest = undefined;
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

describe('PurchaseRequestForm - Update & Reply carries unit_price and total (#1232 blocking 1)', () => {
  /**
   * Regression: the Update & Reply payload was built by a second, hand-rolled
   * `products.map` that dropped `unit_price`/`total`, so every line on a
   * sponsorship form reached `PurchaseRequestUpdateAndReply` price-less and the
   * new backend rule (mandatory unit price) refused the request even though
   * every line on screen had a price. It must use the same mapping as `onSubmit`.
   */
  it('includes unit_price and total in the Update & Reply payload for every line', async () => {
    mockRequest = {
      id: 'req-1',
      request_type: 'sponsorship_form',
      request_number: 'SF-0001',
      project_title: 'Community Fun Run',
      lines: [
        { item_code: 'ITEM-A', quantity: 2, remark: null, unit_price: 15, total: 30 },
      ],
    };

    renderEditForm();

    fireEvent.click(await screen.findByRole('button', { name: /Update & Reply/i }));

    const dialog = await screen.findByRole('dialog');
    fireEvent.change(
      within(dialog).getByLabelText('Message to send'),
      { target: { value: 'Updated the sponsorship form.' } },
    );
    fireEvent.click(within(dialog).getByRole('button', { name: /^Update & Reply$/i }));

    await waitFor(() => expect(updateAndReplyMutateAsync).toHaveBeenCalled());
    const call = updateAndReplyMutateAsync.mock.calls[0][0];
    expect(call.data.formData.products).toEqual([
      expect.objectContaining({
        item_code: 'ITEM-A',
        quantity: 2,
        unit_price: 15,
        total: 30,
      }),
    ]);
  });
});
