import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import OrderFulfilledComplaintsCard from './OrderFulfilledComplaintsCard';
import type { FulfilledComplaint } from '../services/orderFulfilmentService';

const useOrderFulfilledComplaints = vi.fn();

vi.mock('../hooks/useOrderFulfilledComplaints', () => ({
  useOrderFulfilledComplaints: (...a: unknown[]) =>
    useOrderFulfilledComplaints(...a),
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>
      {children}
    </a>
  ),
}));

const COMPLAINTS: FulfilledComplaint[] = [
  { complaint_id: 'c-1', complaint_number: 'CMP26-0042' },
  { complaint_id: 'c-2', complaint_number: 'CMP26-0043' },
];

beforeEach(() => {
  useOrderFulfilledComplaints.mockReset();
});

describe('OrderFulfilledComplaintsCard', () => {
  it('always renders the section title', () => {
    useOrderFulfilledComplaints.mockReturnValue({ data: [], isLoading: true });
    render(<OrderFulfilledComplaintsCard orderId="o-1" />);
    expect(screen.getByText('Fulfils complaints')).toBeInTheDocument();
  });

  it('empty state when the DO fulfils no complaint', () => {
    useOrderFulfilledComplaints.mockReturnValue({ data: [], isLoading: false });
    render(<OrderFulfilledComplaintsCard orderId="o-1" />);
    expect(
      screen.getByText(/not linked to any complaint/i),
    ).toBeInTheDocument();
  });

  it('renders one chip per fulfilled complaint linking to its detail (human number, no UUID)', () => {
    useOrderFulfilledComplaints.mockReturnValue({
      data: COMPLAINTS,
      isLoading: false,
    });
    render(<OrderFulfilledComplaintsCard orderId="o-1" />);

    const a1 = screen.getByRole('link', { name: 'CMP26-0042' });
    expect(a1).toHaveAttribute('href', '/complaint-management/complaints/c-1');
    expect(screen.getByRole('link', { name: 'CMP26-0043' })).toHaveAttribute(
      'href',
      '/complaint-management/complaints/c-2',
    );
    expect(screen.queryByText(/c-1/)).not.toBeInTheDocument();
  });
});
