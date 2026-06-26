/**
 * Tests for the OrderNavigation wrapper (record-navigation, IDs mode).
 *
 * The wrapper:
 *  - reconstructs the list query from the detail URL via parseDetailSearch,
 *  - threads the order-specific filters (order_status_id, has_order_lines),
 *  - feeds it to useOrderNeighbours (thin wrapper over useRecordNeighbours),
 *  - renders RecordNavigation in IDs mode (prevId/nextId/index/total/isLoading),
 *  - preserves the active list query in the URL when stepping to a neighbour.
 *
 * useOrderNeighbours is mocked so we assert the wrapping/threading, not the
 * network layer (that is covered by the backend pytest + the shared hook test).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import OrderNavigation from './OrderNavigation';
import { useOrderNeighbours } from '../hooks/useOrders';

const push = vi.fn();
// Detail URL carries the active list query (sort + search + order filters).
const searchParams = new URLSearchParams(
  'page=2&limit=50&sort=order_date&dir=desc&query=acme&order_status_id=stat-1&has_order_lines=yes',
);

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
}));

vi.mock('../hooks/useOrders', () => ({
  useOrderNeighbours: vi.fn(),
}));

const mockedNeighbours = vi.mocked(useOrderNeighbours);

beforeEach(() => {
  push.mockClear();
  mockedNeighbours.mockReset();
});

describe('OrderNavigation', () => {
  it('passes the parsed list query (sort/dir/search + filters) to useOrderNeighbours', () => {
    mockedNeighbours.mockReturnValue({
      prevId: 'p1',
      nextId: 'n1',
      index: 2,
      total: 7,
      isLoading: false,
    });

    render(<OrderNavigation orderId="cur" />);

    expect(mockedNeighbours).toHaveBeenCalledTimes(1);
    const [orderId, listParams] = mockedNeighbours.mock.calls[0];
    expect(orderId).toBe('cur');
    // page 2 -> pageIndex 1; sort/dir -> sorting; query -> searchQuery; filters threaded.
    expect(listParams).toMatchObject({
      pageIndex: 1,
      pageSize: 50,
      sorting: [{ id: 'order_date', desc: true }],
      searchQuery: 'acme',
      order_status_id: 'stat-1',
      has_order_lines: 'yes',
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

    render(<OrderNavigation orderId="cur" />);

    // index is 1-based from the backend; rendered verbatim as "3 / 7".
    expect(screen.getByText('3 / 7')).toBeInTheDocument();
    expect(screen.getByLabelText('Previous delivery order')).not.toBeDisabled();
    expect(screen.getByLabelText('Next delivery order')).not.toBeDisabled();
  });

  it('disables a chevron when its neighbour id is null', () => {
    mockedNeighbours.mockReturnValue({
      prevId: null,
      nextId: 'n1',
      index: 1,
      total: 7,
      isLoading: false,
    });

    render(<OrderNavigation orderId="cur" />);

    expect(screen.getByLabelText('Previous delivery order')).toBeDisabled();
    expect(screen.getByLabelText('Next delivery order')).not.toBeDisabled();
  });

  it('shows the loading counter while neighbours resolve', () => {
    mockedNeighbours.mockReturnValue({
      prevId: null,
      nextId: null,
      index: null,
      total: 7,
      isLoading: true,
    });

    render(<OrderNavigation orderId="cur" />);

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

    render(<OrderNavigation orderId="cur" />);
    fireEvent.click(screen.getByLabelText('Next delivery order'));

    expect(push).toHaveBeenCalledTimes(1);
    const target = push.mock.calls[0][0] as string;
    expect(target.startsWith('/order-management/orders/n1?')).toBe(true);
    // The list query is carried forward so the neighbour set stays stable.
    expect(target).toContain('sort=order_date');
    expect(target).toContain('query=acme');
    expect(target).toContain('order_status_id=stat-1');
    expect(target).toContain('has_order_lines=yes');
  });
});
