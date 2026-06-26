/**
 * Tests for ConversationSLATrackingNavigation — the thin per-resource nav wrapper
 * that reads the active list query off the detail URL (parseDetailSearch), forwards
 * it to useConversationSLATrackingNeighbours, and renders RecordNavigation in IDs
 * mode.
 *
 * Mirrors the complaint / stock-inquiry nav wrapper pattern. The generic
 * useRecordNeighbours hook is covered by hooks/useRecordNeighbours.test.ts; here we
 * assert the wrapper's wiring: URL params -> hook listParams, and query-preserving
 * navigation.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import ConversationSLATrackingNavigation from './ConversationSLATrackingNavigation';

const push = vi.fn();
let searchString = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(searchString),
}));

const neighboursMock = vi.fn();
vi.mock('../hooks/useConversationSLATracking', () => ({
  useConversationSLATrackingNeighbours: (
    trackingId: string | null,
    listParams: unknown,
  ) => neighboursMock(trackingId, listParams),
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

describe('ConversationSLATrackingNavigation', () => {
  it('renders the "index / total" counter from the hook (IDs mode)', () => {
    render(<ConversationSLATrackingNavigation trackingId="cur-1" />);
    // index is 1-based (2) -> RecordNavigation gets currentIndex={1} -> "2 / 5"
    expect(screen.getByText('2 / 5')).toBeInTheDocument();
  });

  it('forwards the parsed list query (search/sort/assignee/policy) to the neighbours hook', () => {
    searchString =
      'page=2&limit=50&sort=current_tier&dir=asc&query=acme&assigned_to=user-9&policy_id=pol-3';
    render(<ConversationSLATrackingNavigation trackingId="cur-1" />);

    expect(neighboursMock).toHaveBeenCalledTimes(1);
    const [trackingId, listParams] = neighboursMock.mock.calls[0];
    expect(trackingId).toBe('cur-1');
    expect(listParams).toMatchObject({
      pageIndex: 1, // page=2 -> 0-based 1
      pageSize: 50,
      searchQuery: 'acme',
      sorting: [{ id: 'current_tier', desc: false }],
      assigned_to: 'user-9',
      policy_id: 'pol-3',
    });
  });

  it('leaves the assignee/policy filters undefined when absent from the URL', () => {
    searchString = 'sort=created_at&dir=desc';
    render(<ConversationSLATrackingNavigation trackingId="cur-1" />);
    const [, listParams] = neighboursMock.mock.calls[0] as [
      string,
      { assigned_to?: string; policy_id?: string },
    ];
    expect(listParams.assigned_to).toBeUndefined();
    expect(listParams.policy_id).toBeUndefined();
  });

  it('preserves the list query in the URL when stepping to a neighbour', () => {
    searchString = 'sort=current_tier&dir=asc&query=acme';
    render(<ConversationSLATrackingNavigation trackingId="cur-1" />);

    fireEvent.click(screen.getByLabelText('Next conversation SLA tracking'));
    expect(push).toHaveBeenCalledWith(
      '/sla-management/conversation-sla-tracking/next-1?sort=current_tier&dir=asc&query=acme',
    );
  });

  it('navigates to a bare detail URL when there is no active list query', () => {
    searchString = '';
    render(<ConversationSLATrackingNavigation trackingId="cur-1" />);
    fireEvent.click(screen.getByLabelText('Previous conversation SLA tracking'));
    expect(push).toHaveBeenCalledWith(
      '/sla-management/conversation-sla-tracking/prev-1',
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
    render(<ConversationSLATrackingNavigation trackingId="cur-1" />);
    expect(screen.getByText('… / 5')).toBeInTheDocument();
  });
});
