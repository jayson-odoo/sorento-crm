/**
 * Prev/next on a sales order, and how far it is allowed to walk.
 *
 * > "the previous and next should be limited to the pagination, not the whole thing"
 *
 * It used to count against the whole result set - "1 / 13,856" - and borrow a row from each
 * neighbouring page so a step off the edge silently rewrote `page` in the URL. That counter
 * promised a walk nobody wants to take one chevron at a time, and the rewrite moved the reader
 * off the page they had chosen without saying so.
 *
 * So: the items ARE the current page, the counter is a position within it, and the chevron at
 * either end is disabled rather than wrapping round or borrowing.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const push = vi.fn();
let searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
}));

const useSalesOrders = vi.fn();
vi.mock('../../hooks/useSalesOrders', () => ({
  useSalesOrders: (...a: unknown[]) => useSalesOrders(...a),
}));

import SalesOrderNavigation from './SalesOrderNavigation';

/** A page of the list, as the hook hands it over. `total` is the WHOLE book. */
function page(ids: string[], total = 13856) {
  useSalesOrders.mockReturnValue({
    data: {
      data: ids.map((id) => ({ id })),
      pagination: { total, page: 1, limit: ids.length },
    },
  });
}

function counter(): HTMLElement | null {
  return screen.queryByText(/\d+ \/ \d+/);
}

beforeEach(() => {
  push.mockReset();
  useSalesOrders.mockReset();
  searchParams = new URLSearchParams('page=3&limit=25&status=open');
});

describe('SalesOrderNavigation - the walk is this page', () => {
  it('counts within the page, never against the whole result set', () => {
    page(['so-1', 'so-2', 'so-3']);
    render(<SalesOrderNavigation salesOrderId="so-2" />);

    expect(counter()).toHaveTextContent('2 / 3');
    expect(screen.queryByText(/13,?856/)).toBeNull();
  });

  it('stops at the start of the page rather than wrapping to its end', () => {
    page(['so-1', 'so-2', 'so-3']);
    render(<SalesOrderNavigation salesOrderId="so-1" />);

    expect(screen.getByRole('button', { name: 'Previous sales order' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next sales order' })).toBeEnabled();
  });

  it('stops at the end of the page rather than wrapping to its start', () => {
    page(['so-1', 'so-2', 'so-3']);
    render(<SalesOrderNavigation salesOrderId="so-3" />);

    expect(screen.getByRole('button', { name: 'Next sales order' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous sales order' })).toBeEnabled();
  });

  it('reads ONE page - no neighbouring page is fetched to borrow a row from', () => {
    page(['so-1', 'so-2', 'so-3']);
    render(<SalesOrderNavigation salesOrderId="so-2" />);

    expect(useSalesOrders).toHaveBeenCalledTimes(1);
    expect(useSalesOrders.mock.calls[0][0]).toMatchObject({
      pageIndex: 2,
      pageSize: 25,
      status: 'open',
    });
  });

  it('carries the list query, page included, onto the next record', () => {
    page(['so-1', 'so-2', 'so-3']);
    render(<SalesOrderNavigation salesOrderId="so-2" />);

    fireEvent.click(screen.getByRole('button', { name: 'Next sales order' }));

    expect(push).toHaveBeenCalledWith(
      '/scm/sales-orders/so-3?page=3&limit=25&status=open',
    );
  });

  it('renders nothing at all when the page holds one row', () => {
    page(['so-1'], 1);
    const { container } = render(<SalesOrderNavigation salesOrderId="so-1" />);

    expect(container).toBeEmptyDOMElement();
  });
});
