import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}));

const packingList = {
  id: 'pl-1',
  shipment_number: 'FJ001',
  supplier_id: 'sup-1',
  shipment_date: '2026-01-01T00:00:00',
  estimated_arrival_date: null,
  shipment_status: 'in_transit',
  shipment_lines: [
    { product_id: 'p-a', quantity_shipped: 5, product: { id: 'p-a', product_code: 'CODE-A', product_name: 'Sink A' } },
    { product_id: 'p-b', quantity_shipped: 6, product: { id: 'p-b', product_code: 'CODE-B', product_name: 'Sink B' } },
    { product_id: 'p-c', quantity_shipped: 7, product: { id: 'p-c', product_code: 'CODE-C', product_name: 'Sink C' } },
  ],
};

const { updateMock } = vi.hoisted(() => ({ updateMock: vi.fn().mockResolvedValue({}) }));

vi.mock('../hooks/usePackingLists', () => ({
  usePackingList: () => ({ data: packingList, isLoading: false }),
  useClearanceCheckpoints: () => ({ data: [] }),
  useCreatePackingList: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePackingList: () => ({ mutateAsync: updateMock, isPending: false }),
}));

vi.mock('../../suppliers/hooks/useSupplierSelectQuery', () => ({
  useSupplierSelectQuery: () => ({ data: [] }),
}));

// The catalog page the combobox holds never contains these lines' products — the
// normal case with a 10k+ catalog and a 100-row page, which is what makes every
// saved line depend on the fallback rather than on the fetched list.
const { getProductsMock } = vi.hoisted(() => ({
  getProductsMock: vi.fn().mockResolvedValue({
    data: [{ id: 'p-z', product_code: 'CODE-Z', product_name: 'Other' }],
  }),
}));
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProducts: getProductsMock,
}));

import PackingListForm from './PackingListForm';

const removeButtons = () =>
  screen.getAllByRole('button').filter((b) => b.className.includes('text-destructive'));

beforeEach(() => {
  updateMock.mockClear();
  getProductsMock.mockClear();
});

describe('PackingListForm shipment lines', () => {
  it('keeps the remaining rows labelled after one line is removed', async () => {
    render(<PackingListForm packingListId="pl-1" />);

    await waitFor(() => {
      expect(screen.getByText(/CODE-A/)).toBeInTheDocument();
      expect(screen.getByText(/CODE-B/)).toBeInTheDocument();
      expect(screen.getByText(/CODE-C/)).toBeInTheDocument();
    });

    // Remove the FIRST line: every row below it shifts index.
    fireEvent.click(removeButtons()[0]);

    await waitFor(() => expect(screen.queryByText(/CODE-A/)).not.toBeInTheDocument());
    expect(screen.getByText(/CODE-B/)).toBeInTheDocument();
    expect(screen.getByText(/CODE-C/)).toBeInTheDocument();
    expect(screen.queryByText('Select product')).not.toBeInTheDocument();
  });

  it('submits the surviving lines, not a cleared list', async () => {
    render(<PackingListForm packingListId="pl-1" />);
    await waitFor(() => expect(screen.getByText(/CODE-C/)).toBeInTheDocument());

    fireEvent.click(removeButtons()[0]);
    await waitFor(() => expect(screen.queryByText(/CODE-A/)).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Update' }));

    await waitFor(() => expect(updateMock).toHaveBeenCalled());
    expect(updateMock.mock.calls[0][0].data.shipment_lines).toEqual([
      { product_id: 'p-b', quantity_shipped: 6 },
      { product_id: 'p-c', quantity_shipped: 7 },
    ]);
  });

  it('a search in one row does not blank the other rows', async () => {
    render(<PackingListForm packingListId="pl-1" />);
    await waitFor(() => expect(screen.getByText(/CODE-A/)).toBeInTheDocument());

    // Every row reads one shared `products` state, so a search narrows the list
    // under all of them at once.
    getProductsMock.mockResolvedValueOnce({
      data: [{ id: 'p-q', product_code: 'CODE-Q', product_name: 'Searched' }],
    });
    fireEvent.click(screen.getAllByRole('combobox')[1]);
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'CODE-Q' } });

    await waitFor(() => expect(screen.getByText(/CODE-A/)).toBeInTheDocument());
    expect(screen.getByText(/CODE-C/)).toBeInTheDocument();
  });
});
