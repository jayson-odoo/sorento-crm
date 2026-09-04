import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import ComplaintFulfilmentOrdersSection from './ComplaintFulfilmentOrdersSection';
import type { FulfilmentOrder } from '../services/complaintFulfilmentService';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const useComplaintFulfilmentOrders = vi.fn();

vi.mock('../hooks/useComplaintFulfilmentOrders', () => ({
  useComplaintFulfilmentOrders: (...a: unknown[]) =>
    useComplaintFulfilmentOrders(...a),
}));

// next/link -> plain anchor for jsdom.
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>
      {children}
    </a>
  ),
}));

const ORDER: FulfilmentOrder = {
  order_id: 'o-1',
  order_number: 'REPPS2605-0012',
  status: 'delivered',
  status_label: 'Picked Up / In Transit',
  actual_delivery_date: '2026-06-02T09:00:00',
  is_cancelled: false,
  items: [
    { product_code: 'SKU-1', product_type: 'Mattress', qty: 2 },
    { product_code: 'SKU-2', product_type: null, qty: 1 },
  ],
};

beforeEach(() => {
  useComplaintFulfilmentOrders.mockReset();
});

describe('ComplaintFulfilmentOrdersSection', () => {
  it('always renders the section title', () => {
    useComplaintFulfilmentOrders.mockReturnValue({ data: [], isLoading: true });
    render(<ComplaintFulfilmentOrdersSection complaintId="c-1" />);
    expect(screen.getByText('Fulfilment Delivery Orders')).toBeInTheDocument();
  });

  it('empty state shows the no-linked-DO message', () => {
    useComplaintFulfilmentOrders.mockReturnValue({ data: [], isLoading: false });
    render(<ComplaintFulfilmentOrdersSection complaintId="c-1" />);
    expect(
      screen.getByText(/No replacement delivery order linked yet/i),
    ).toBeInTheDocument();
  });

  it('renders a linked DO row: number link, status pill, delivery date', () => {
    useComplaintFulfilmentOrders.mockReturnValue({ data: [ORDER], isLoading: false });
    render(<ComplaintFulfilmentOrdersSection complaintId="c-1" />);

    const link = screen.getByRole('link', { name: 'REPPS2605-0012' });
    expect(link).toHaveAttribute('href', '/order-management/orders/o-1');
    expect(screen.getByText('Picked Up / In Transit')).toBeInTheDocument();
    // delivery date rendered (not the em-dash placeholder)
    expect(screen.queryByText('-')).not.toBeInTheDocument();
    // no UUID shown anywhere
    expect(screen.queryByText(/o-1/)).not.toBeInTheDocument();
  });

  it('shows an em-dash when delivery date is null', () => {
    useComplaintFulfilmentOrders.mockReturnValue({
      data: [{ ...ORDER, actual_delivery_date: null }],
      isLoading: false,
    });
    render(<ComplaintFulfilmentOrdersSection complaintId="c-1" />);
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('items popover lists product code x qty', async () => {
    useComplaintFulfilmentOrders.mockReturnValue({ data: [ORDER], isLoading: false });
    render(<ComplaintFulfilmentOrdersSection complaintId="c-1" />);

    fireEvent.click(
      screen.getByRole('button', {
        name: /View items for delivery order REPPS2605-0012/i,
      }),
    );
    await waitFor(() => {
      expect(screen.getByText('SKU-1')).toBeInTheDocument();
    });
    expect(screen.getByText('SKU-2')).toBeInTheDocument();
    expect(screen.getByText('2 items')).toBeInTheDocument();
  });
});
