/**
 * Tests for the AccessAgentNavigation wrapper (record-navigation, IDs mode).
 *
 * The wrapper:
 *  - reconstructs the list query from the detail URL via parseDetailSearch,
 *  - feeds it to useAccessAgentNeighbours (thin wrapper over useRecordNeighbours),
 *  - renders RecordNavigation in IDs mode (prevId/nextId/index/total/isLoading),
 *  - preserves the active list query in the URL when stepping to a neighbour.
 *
 * useAccessAgentNeighbours is mocked so we assert the wrapping/threading, not the
 * network layer (that is covered by the backend pytest + the shared hook test).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import AccessAgentNavigation from './AccessAgentNavigation';
import { useAccessAgentNeighbours } from '../hooks/useAccessAgents';

const push = vi.fn();
// Detail URL carries the active list query (search) the user came from.
const searchParams = new URLSearchParams('page=2&limit=50&query=acme');

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
}));

vi.mock('../hooks/useAccessAgents', () => ({
  useAccessAgentNeighbours: vi.fn(),
}));

const mockedNeighbours = vi.mocked(useAccessAgentNeighbours);

beforeEach(() => {
  push.mockClear();
  mockedNeighbours.mockReset();
});

describe('AccessAgentNavigation', () => {
  it('passes the parsed list query (search) to useAccessAgentNeighbours', () => {
    mockedNeighbours.mockReturnValue({
      prevId: 'p1',
      nextId: 'n1',
      index: 2,
      total: 7,
      isLoading: false,
    });

    render(<AccessAgentNavigation accessAgentId="cur" />);

    expect(mockedNeighbours).toHaveBeenCalledTimes(1);
    const [agentId, listParams] = mockedNeighbours.mock.calls[0];
    expect(agentId).toBe('cur');
    // page 2 -> pageIndex 1; query -> searchQuery.
    expect(listParams).toMatchObject({
      pageIndex: 1,
      pageSize: 50,
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

    render(<AccessAgentNavigation accessAgentId="cur" />);

    // index is 1-based from the backend; rendered verbatim as "3 / 7".
    expect(screen.getByText('3 / 7')).toBeInTheDocument();
    expect(screen.getByLabelText('Previous access agent')).not.toBeDisabled();
    expect(screen.getByLabelText('Next access agent')).not.toBeDisabled();
  });

  it('disables a chevron when its neighbour id is null', () => {
    mockedNeighbours.mockReturnValue({
      prevId: null,
      nextId: 'n1',
      index: 1,
      total: 7,
      isLoading: false,
    });

    render(<AccessAgentNavigation accessAgentId="cur" />);

    expect(screen.getByLabelText('Previous access agent')).toBeDisabled();
    expect(screen.getByLabelText('Next access agent')).not.toBeDisabled();
  });

  it('shows the loading counter while neighbours resolve', () => {
    mockedNeighbours.mockReturnValue({
      prevId: null,
      nextId: null,
      index: null,
      total: 7,
      isLoading: true,
    });

    render(<AccessAgentNavigation accessAgentId="cur" />);

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

    render(<AccessAgentNavigation accessAgentId="cur" />);
    fireEvent.click(screen.getByLabelText('Next access agent'));

    expect(push).toHaveBeenCalledTimes(1);
    const target = push.mock.calls[0][0] as string;
    expect(target.startsWith('/user-management/access-agents/n1?')).toBe(true);
    // The list query is carried forward so the neighbour set stays stable.
    expect(target).toContain('query=acme');
  });
});
