/**
 * Tests for PromotionNavigation — the thin per-resource nav wrapper that reads
 * the active list query off the detail URL (parseDetailSearch), forwards it to
 * usePromotionNeighbours, and renders RecordNavigation in IDs mode.
 *
 * Mirrors the complaint / stock-inquiry nav wrapper pattern. The generic
 * useRecordNeighbours hook is covered by hooks/useRecordNeighbours.test.ts; here
 * we assert the wrapper's wiring: URL params -> hook listParams, and
 * query-preserving navigation.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import PromotionNavigation from './PromotionNavigation';

const push = vi.fn();
let searchString = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(searchString),
}));

const neighboursMock = vi.fn();
vi.mock('../hooks/usePromotions', () => ({
  usePromotionNeighbours: (
    promotionId: string | null,
    listParams: unknown,
  ) => neighboursMock(promotionId, listParams),
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

describe('PromotionNavigation', () => {
  it('renders the "index / total" counter from the hook (IDs mode)', () => {
    render(<PromotionNavigation promotionId="cur-1" />);
    // index is 1-based (2) -> RecordNavigation gets currentIndex={1} -> "2 / 5"
    expect(screen.getByText('2 / 5')).toBeInTheDocument();
  });

  it('forwards the parsed list query (search/sort/status/user_type) to the neighbours hook', () => {
    searchString =
      'page=2&limit=50&sort=start_date&dir=asc&query=kitchen&status=active&user_type=dealer';
    render(<PromotionNavigation promotionId="cur-1" />);

    expect(neighboursMock).toHaveBeenCalledTimes(1);
    const [promotionId, listParams] = neighboursMock.mock.calls[0];
    expect(promotionId).toBe('cur-1');
    expect(listParams).toMatchObject({
      pageIndex: 1, // page=2 -> 0-based 1
      pageSize: 50,
      searchQuery: 'kitchen',
      sorting: [{ id: 'start_date', desc: false }],
      status: 'active',
      user_type: 'dealer',
    });
  });

  it('forwards the attachment_state filter when present', () => {
    searchString = 'sort=created_at&dir=desc&attachment_state=unlinked';
    render(<PromotionNavigation promotionId="cur-1" />);
    const [, listParams] = neighboursMock.mock.calls[0];
    expect(listParams).toMatchObject({ attachment_state: 'unlinked' });
  });

  it('leaves filters undefined when none are present in the URL', () => {
    searchString = 'sort=created_at&dir=desc';
    render(<PromotionNavigation promotionId="cur-1" />);
    const [, listParams] = neighboursMock.mock.calls[0];
    expect(listParams.status).toBeUndefined();
    expect(listParams.user_type).toBeUndefined();
    expect(listParams.attachment_state).toBeUndefined();
  });

  it('preserves the list query in the URL when stepping to a neighbour', () => {
    searchString = 'sort=start_date&dir=asc&query=kitchen';
    render(<PromotionNavigation promotionId="cur-1" />);

    fireEvent.click(screen.getByLabelText('Next promotion'));
    expect(push).toHaveBeenCalledWith(
      '/marketing-management/promotions/next-1?sort=start_date&dir=asc&query=kitchen',
    );
  });

  it('navigates to a bare detail URL when there is no active list query', () => {
    searchString = '';
    render(<PromotionNavigation promotionId="cur-1" />);
    fireEvent.click(screen.getByLabelText('Previous promotion'));
    expect(push).toHaveBeenCalledWith(
      '/marketing-management/promotions/prev-1',
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
    render(<PromotionNavigation promotionId="cur-1" />);
    expect(screen.getByText('… / 5')).toBeInTheDocument();
  });
});
