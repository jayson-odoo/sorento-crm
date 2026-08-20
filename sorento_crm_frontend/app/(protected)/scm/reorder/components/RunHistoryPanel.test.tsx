import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import type { ReorderRunHistoryItem } from '../services/reorderRunService';

const useReorderRunHistory = vi.fn();
vi.mock('../hooks/useReorderRun', () => ({
  useReorderRunHistory: (...a: unknown[]) => useReorderRunHistory(...a),
}));

import { RunHistoryPanel } from './RunHistoryPanel';

function item(over: Partial<ReorderRunHistoryItem>): ReorderRunHistoryItem {
  return {
    run_id: 'run-1',
    status: 'completed',
    buy_scope: 'network',
    warehouse_codes: ['WH-KL', 'WH-JB'],
    warehouse_count: 2,
    started_at: '2026-07-16T02:00:00',
    finished_at: '2026-07-16T02:00:05',
    summary: {
      buy_count: 4,
      disposition_count: 1,
      exception_count: 0,
      total_cash_impact: 9000,
      recommendation_count: 5,
    },
    ...over,
  };
}

function mockHistory(over: Partial<ReturnType<typeof baseState>> = {}) {
  useReorderRunHistory.mockReturnValue({ ...baseState(), ...over });
}

function baseState() {
  return {
    data: undefined as unknown,
    isLoading: false,
    isError: false,
    error: null as unknown,
    refetch: vi.fn(),
    isFetching: false,
  };
}

beforeEach(() => useReorderRunHistory.mockReset());

describe('RunHistoryPanel', () => {
  it('renders runs with warehouse scope + summary counts, newest first as given', () => {
    mockHistory({
      data: {
        data: [
          item({ run_id: 'run-new', warehouse_codes: ['WH-KL'], warehouse_count: 1 }),
          item({ run_id: 'run-old', started_at: '2026-07-15T02:00:00' }),
        ],
        pagination: { page: 1, limit: 8, total: 2, total_pages: 1 },
      },
    });
    render(<RunHistoryPanel selectedRunId={null} onSelect={vi.fn()} />);

    expect(screen.getByText('Run history')).toBeTruthy();
    expect(screen.getByText('2 runs')).toBeTruthy();
    // both rows render their warehouse scope + a buy count
    expect(screen.getByText('WH-KL')).toBeTruthy();
    expect(screen.getByText('WH-KL, WH-JB')).toBeTruthy();
    expect(screen.getAllByText('Buy').length).toBe(2);
  });

  it('marks the selected run with a Viewing badge', () => {
    mockHistory({
      data: {
        data: [item({ run_id: 'run-sel' })],
        pagination: { page: 1, limit: 8, total: 1, total_pages: 1 },
      },
    });
    render(<RunHistoryPanel selectedRunId="run-sel" onSelect={vi.fn()} />);
    expect(screen.getByText('Viewing')).toBeTruthy();
  });

  it('calls onSelect with the clicked run', () => {
    const onSelect = vi.fn();
    const clicked = item({ run_id: 'run-click' });
    mockHistory({
      data: {
        data: [clicked],
        pagination: { page: 1, limit: 8, total: 1, total_pages: 1 },
      },
    });
    render(<RunHistoryPanel selectedRunId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { pressed: false }));
    expect(onSelect).toHaveBeenCalledWith(clicked);
  });

  it('shows the empty state when there are no runs', () => {
    mockHistory({
      data: { data: [], pagination: { page: 1, limit: 8, total: 0, total_pages: 1 } },
    });
    render(<RunHistoryPanel selectedRunId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('No runs yet')).toBeTruthy();
  });

  it('shows an error state with a retry action', () => {
    const refetch = vi.fn();
    mockHistory({ isError: true, error: new Error('boom'), refetch });
    render(<RunHistoryPanel selectedRunId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('boom')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it('renders a loading skeleton while fetching', () => {
    mockHistory({ isLoading: true });
    const { container } = render(<RunHistoryPanel selectedRunId={null} onSelect={vi.fn()} />);
    expect(within(container).getByLabelText('Loading run history')).toBeTruthy();
  });

  // SF-6 / initialSelectRunId: the `?plan=<id>` deep-link is resolved against the first page
  // of runs once it loads, reported back via onSelect, and never re-tried.
  describe('initialSelectRunId (?plan= deep-link resolution)', () => {
    it('resolves a known id against the loaded page and reports it back via onSelect, once', async () => {
      const onSelect = vi.fn();
      const wanted = item({ run_id: 'run-deep-link' });
      mockHistory({
        data: {
          data: [wanted, item({ run_id: 'run-other' })],
          pagination: { page: 1, limit: 8, total: 2, total_pages: 1 },
        },
      });
      const { rerender } = render(
        <RunHistoryPanel
          selectedRunId={null}
          onSelect={onSelect}
          initialSelectRunId="run-deep-link"
        />,
      );

      await waitFor(() => expect(onSelect).toHaveBeenCalledWith(wanted));
      expect(onSelect).toHaveBeenCalledTimes(1);

      // A later re-render (e.g. the page's own selection state changing) does not re-trigger
      // the resolution - tried at most once.
      rerender(
        <RunHistoryPanel
          selectedRunId="run-deep-link"
          onSelect={onSelect}
          initialSelectRunId="run-deep-link"
        />,
      );
      expect(onSelect).toHaveBeenCalledTimes(1);
    });

    it('ignores an id that is not on the loaded page - falls back silently, onSelect never called', async () => {
      const onSelect = vi.fn();
      mockHistory({
        data: {
          data: [item({ run_id: 'run-other' })],
          pagination: { page: 1, limit: 8, total: 1, total_pages: 1 },
        },
      });
      render(
        <RunHistoryPanel
          selectedRunId={null}
          onSelect={onSelect}
          initialSelectRunId="run-unknown"
        />,
      );

      // Nothing to await for a negative case beyond letting effects flush.
      await waitFor(() => expect(screen.getByText('Run history')).toBeTruthy());
      expect(onSelect).not.toHaveBeenCalled();
    });
  });
});
