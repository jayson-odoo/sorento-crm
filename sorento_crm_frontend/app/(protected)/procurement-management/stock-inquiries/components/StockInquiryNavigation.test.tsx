/**
 * Tests for StockInquiryNavigation - the thin per-resource nav wrapper that
 * reads the active list query off the detail URL (parseDetailSearch), forwards
 * it to useStockInquiryNeighbours, and renders RecordNavigation in IDs mode.
 *
 * Mirrors the complaint nav wrapper pattern. The generic useRecordNeighbours
 * hook is covered by hooks/useRecordNeighbours.test.ts; here we assert the
 * wrapper's wiring: URL params -> hook listParams, and query-preserving nav.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import StockInquiryNavigation from './StockInquiryNavigation';

const push = vi.fn();
let searchString = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(searchString),
}));

const neighboursMock = vi.fn();
vi.mock('../hooks/useStockInquiries', () => ({
  useStockInquiryNeighbours: (
    inquiryId: string | null,
    listParams: unknown,
  ) => neighboursMock(inquiryId, listParams),
}));

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

describe('StockInquiryNavigation', () => {
  it('renders the "index / total" counter from the hook (IDs mode)', () => {
    render(<StockInquiryNavigation inquiryId="cur-1" />);
    // index is 1-based (2) -> RecordNavigation gets currentIndex={1} -> "2 / 5"
    expect(screen.getByText('2 / 5')).toBeInTheDocument();
  });

  it('forwards the parsed list query (search/sort/status) to the neighbours hook', () => {
    searchString =
      'page=2&limit=50&sort=product_code&dir=asc&query=widget&status=new,rejected';
    render(<StockInquiryNavigation inquiryId="cur-1" />);

    expect(neighboursMock).toHaveBeenCalledTimes(1);
    const [inquiryId, listParams] = neighboursMock.mock.calls[0];
    expect(inquiryId).toBe('cur-1');
    expect(listParams).toMatchObject({
      pageIndex: 1, // page=2 -> 0-based 1
      pageSize: 50,
      searchQuery: 'widget',
      sorting: [{ id: 'product_code', desc: false }],
      statuses: ['new', 'rejected'],
    });
  });

  it('defaults to an empty status filter when none is present in the URL', () => {
    searchString = 'sort=created_at&dir=desc';
    render(<StockInquiryNavigation inquiryId="cur-1" />);
    const [, listParams] = neighboursMock.mock.calls[0];
    expect(listParams).toMatchObject({ statuses: [] });
  });

  it('preserves the list query in the URL when stepping to a neighbour', () => {
    searchString = 'sort=product_code&dir=asc&query=widget';
    render(<StockInquiryNavigation inquiryId="cur-1" />);

    fireEvent.click(screen.getByLabelText('Next stock inquiry'));
    expect(push).toHaveBeenCalledWith(
      '/procurement-management/stock-inquiries/next-1?sort=product_code&dir=asc&query=widget',
    );
  });

  it('navigates to a bare detail URL when there is no active list query', () => {
    searchString = '';
    render(<StockInquiryNavigation inquiryId="cur-1" />);
    fireEvent.click(screen.getByLabelText('Previous stock inquiry'));
    expect(push).toHaveBeenCalledWith(
      '/procurement-management/stock-inquiries/prev-1',
    );
  });

  it('renders "… / total" while neighbours are loading', () => {
    neighboursMock.mockReturnValue({
      prevId: null,
      nextId: null,
      index: null,
      total: 5,
      isLoading: true,
    });
    render(<StockInquiryNavigation inquiryId="cur-1" />);
    expect(screen.getByText('… / 5')).toBeInTheDocument();
  });
});
