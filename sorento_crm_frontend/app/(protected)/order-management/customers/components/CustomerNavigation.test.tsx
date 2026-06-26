/**
 * Tests for the CustomerNavigation wrapper (record-navigation, IDs mode).
 *
 * The wrapper:
 *  - reconstructs the list query from the detail URL via parseDetailSearch,
 *  - feeds it to useCustomerNeighbours (thin wrapper over useRecordNeighbours),
 *  - renders RecordNavigation in IDs mode (prevId/nextId/index/total/isLoading),
 *  - preserves the active list query in the URL when stepping to a neighbour.
 *
 * useCustomerNeighbours is mocked so we assert the wrapping/threading, not the
 * network layer (that is covered by the backend pytest + the shared hook test).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import CustomerNavigation from './CustomerNavigation';
import { useCustomerNeighbours } from '../hooks/useCustomers';

const push = vi.fn();
// Detail URL carries the active list query (sort + search) the user came from.
const searchParams = new URLSearchParams(
  'page=2&limit=50&sort=customer_name&dir=asc&query=acme',
);

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
}));

vi.mock('../hooks/useCustomers', () => ({
  useCustomerNeighbours: vi.fn(),
}));

const mockedNeighbours = vi.mocked(useCustomerNeighbours);

beforeEach(() => {
  push.mockClear();
  mockedNeighbours.mockReset();
});

describe('CustomerNavigation', () => {
  it('passes the parsed list query (sort/dir/search) to useCustomerNeighbours', () => {
    mockedNeighbours.mockReturnValue({
      prevId: 'p1',
      nextId: 'n1',
      index: 2,
      total: 7,
      isLoading: false,
    });

    render(<CustomerNavigation customerId="cur" />);

    expect(mockedNeighbours).toHaveBeenCalledTimes(1);
    const [customerId, listParams] = mockedNeighbours.mock.calls[0];
    expect(customerId).toBe('cur');
    // page 2 -> pageIndex 1; sort/dir -> sorting; query -> searchQuery.
    expect(listParams).toMatchObject({
      pageIndex: 1,
      pageSize: 50,
      sorting: [{ id: 'customer_name', desc: false }],
      searchQuery: 'acme',
    });
  });

  it('renders RecordNavigation in IDs mode with the resolved counter', () => {
    mockedNeighbours.mockReturnValue({
      prevId: 'p1',
      nextId: 'n1',
      index: 3,
      total: 7,
      isLoading: false,
    });

    render(<CustomerNavigation customerId="cur" />);

    // index is 1-based from the backend; rendered verbatim as "3 / 7".
    expect(screen.getByText('3 / 7')).toBeInTheDocument();
    expect(screen.getByLabelText('Previous customer')).not.toBeDisabled();
    expect(screen.getByLabelText('Next customer')).not.toBeDisabled();
  });

  it('disables a chevron when its neighbour id is null', () => {
    mockedNeighbours.mockReturnValue({
      prevId: null,
      nextId: 'n1',
      index: 1,
      total: 7,
      isLoading: false,
    });

    render(<CustomerNavigation customerId="cur" />);

    expect(screen.getByLabelText('Previous customer')).toBeDisabled();
    expect(screen.getByLabelText('Next customer')).not.toBeDisabled();
  });

  it('shows the loading counter while neighbours resolve', () => {
    mockedNeighbours.mockReturnValue({
      prevId: null,
      nextId: null,
      index: null,
      total: 7,
      isLoading: true,
    });

    render(<CustomerNavigation customerId="cur" />);

    expect(screen.getByText('… / 7')).toBeInTheDocument();
  });

  it('preserves the active list query in the URL when stepping to a neighbour', () => {
    mockedNeighbours.mockReturnValue({
      prevId: 'p1',
      nextId: 'n1',
      index: 3,
      total: 7,
      isLoading: false,
    });

    render(<CustomerNavigation customerId="cur" />);
    fireEvent.click(screen.getByLabelText('Next customer'));

    expect(push).toHaveBeenCalledTimes(1);
    const target = push.mock.calls[0][0] as string;
    expect(target.startsWith('/order-management/customers/n1?')).toBe(true);
    // The list query is carried forward so the neighbour set stays stable.
    expect(target).toContain('sort=customer_name');
    expect(target).toContain('query=acme');
  });
});
