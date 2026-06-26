/**
 * Tests for PurchaseRequestNavigation — the thin per-resource nav wrapper that
 * reads the active list query off the detail URL (parseDetailSearch), forces the
 * request_type from the base path (so PR nav stays in PRs and SF nav in SFs),
 * forwards it to usePurchaseRequestNeighbours, and renders RecordNavigation in
 * IDs mode.
 *
 * Mirrors the complaint / stock-inquiry nav wrapper pattern. The generic
 * useRecordNeighbours hook is covered by hooks/useRecordNeighbours.test.ts; here
 * we assert the wrapper's wiring: URL params -> hook listParams (with request_type
 * forced from basePath), and query-preserving navigation.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import PurchaseRequestNavigation from './PurchaseRequestNavigation';

const push = vi.fn();
let searchString = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(searchString),
}));

const neighboursMock = vi.fn();
vi.mock('../hooks/usePurchaseRequests', () => ({
  usePurchaseRequestNeighbours: (
    requestId: string | null,
    listParams: unknown,
  ) => neighboursMock(requestId, listParams),
}));

const PR_BASE = '/procurement-management/purchase-requests';
const SF_BASE = '/procurement-management/sponsorship-forms';

beforeEach(() => {
  push.mockClear();
  neighboursMock.mockReset();
  neighboursMock.mockReturnValue({
    prevId: 'prev-1',
    nextId: 'next-1',
    index: 2,
    total: 5,
    isLoading: false,
  });
  searchString = '';
});

describe('PurchaseRequestNavigation', () => {
  it('renders the "index / total" counter from the hook (IDs mode)', () => {
    render(
      <PurchaseRequestNavigation
        requestId="cur-1"
        basePath={PR_BASE}
        ariaLabel="purchase request"
      />,
    );
    // index is 1-based (2) -> RecordNavigation gets currentIndex={1} -> "2 / 5"
    expect(screen.getByText('2 / 5')).toBeInTheDocument();
  });

  it('forwards the parsed list query (search/sort/filters) to the neighbours hook', () => {
    searchString =
      'page=2&limit=50&sort=customer_name&dir=asc&query=acme&approval_status=pending&assigned_to=user-9';
    render(
      <PurchaseRequestNavigation
        requestId="cur-1"
        basePath={PR_BASE}
        ariaLabel="purchase request"
      />,
    );

    expect(neighboursMock).toHaveBeenCalledTimes(1);
    const [requestId, listParams] = neighboursMock.mock.calls[0];
    expect(requestId).toBe('cur-1');
    expect(listParams).toMatchObject({
      pageIndex: 1, // page=2 -> 0-based 1
      pageSize: 50,
      searchQuery: 'acme',
      sorting: [{ id: 'customer_name', desc: false }],
      approval_status: 'pending',
      assigned_to: 'user-9',
    });
  });

  it('forces request_type=purchase_request from the purchase-requests base path', () => {
    searchString = 'sort=request_date&dir=desc';
    render(
      <PurchaseRequestNavigation
        requestId="cur-1"
        basePath={PR_BASE}
        ariaLabel="purchase request"
      />,
    );
    const [, listParams] = neighboursMock.mock.calls[0];
    expect(listParams).toMatchObject({ request_type: 'purchase_request' });
  });

  it('forces request_type=sponsorship_form from the sponsorship-forms base path', () => {
    searchString = 'sort=request_date&dir=desc';
    render(
      <PurchaseRequestNavigation
        requestId="cur-1"
        basePath={SF_BASE}
        ariaLabel="sponsorship form"
      />,
    );
    const [, listParams] = neighboursMock.mock.calls[0];
    expect(listParams).toMatchObject({ request_type: 'sponsorship_form' });
  });

  it('preserves the list query in the URL when stepping to a neighbour', () => {
    searchString = 'sort=customer_name&dir=asc&query=acme';
    render(
      <PurchaseRequestNavigation
        requestId="cur-1"
        basePath={PR_BASE}
        ariaLabel="purchase request"
      />,
    );

    fireEvent.click(screen.getByLabelText('Next purchase request'));
    expect(push).toHaveBeenCalledWith(
      `${PR_BASE}/next-1?sort=customer_name&dir=asc&query=acme`,
    );
  });

  it('navigates to a bare detail URL when there is no active list query', () => {
    searchString = '';
    render(
      <PurchaseRequestNavigation
        requestId="cur-1"
        basePath={PR_BASE}
        ariaLabel="purchase request"
      />,
    );
    fireEvent.click(screen.getByLabelText('Previous purchase request'));
    expect(push).toHaveBeenCalledWith(`${PR_BASE}/prev-1`);
  });

  it('renders "… / total" while neighbours are loading', () => {
    neighboursMock.mockReturnValue({
      prevId: null,
      nextId: null,
      index: null,
      total: 5,
      isLoading: true,
    });
    render(
      <PurchaseRequestNavigation
        requestId="cur-1"
        basePath={PR_BASE}
        ariaLabel="purchase request"
      />,
    );
    expect(screen.getByText('… / 5')).toBeInTheDocument();
  });
});
