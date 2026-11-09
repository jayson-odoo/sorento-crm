/**
 * SCHEDULED-TASKS-GRID (owner, 9 Nov 2026): the Scheduled Tasks page on the standard grid,
 * ONE line per row, every column sortable server-side, multi-select filters.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ScheduledTask } from '../types/scheduledTask.types';
import type { ScheduledTaskListParams } from '../services/scheduledTaskService';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

const routerPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPush, prefetch: vi.fn() }),
  usePathname: () => '/system-management/scheduled-tasks',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const calls: ScheduledTaskListParams[] = [];
let rows: ScheduledTask[] = [];
vi.mock('../hooks/useScheduledTasks', () => ({
  useScheduledTasks: (params: ScheduledTaskListParams) => {
    calls.push(params);
    return {
      data: { data: rows, pagination: { total: rows.length, page: 1, limit: 50 } },
      isLoading: false,
      isFetching: false,
      isPlaceholderData: false,
      error: null,
      refetch: vi.fn(),
    };
  },
}));

import ScheduledTasksList from './ScheduledTasksList';

const LONG_ERROR =
  'Town snapshot failed for 1 of 2 companies: Mocha: canceling statement due to statement timeout '
  + 'while building the ninety day ranking for every shop in the company';

function task(over: Partial<ScheduledTask> = {}): ScheduledTask {
  return {
    id: 't-1',
    key: 'town_snapshot',
    name: 'Sorento town snapshot',
    description: 'Rebuilds each active company town snapshot, a description long enough to wrap.',
    enabled: true,
    interval_unit: 'minutes',
    interval_value: 3,
    timezone: 'UTC',
    start_at: null,
    next_run_at: '2026-11-09T08:39:00',
    last_run_at: '2026-11-09T08:36:00',
    last_status: 'failed',
    last_error: LONG_ERROR,
    created_at: '2026-11-09T00:00:00',
    updated_at: '2026-11-09T00:00:00',
    due_at: null,
    grace_percent: null,
    grace_seconds: null,
    is_overdue: false,
    late_by_seconds: null,
    ...over,
  };
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ScheduledTasksList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  calls.length = 0;
  rows = [task()];
});

describe('ScheduledTasksList', () => {
  it('lists the Town job with its schedule, status, runs and error', () => {
    renderList();
    const row = screen.getByText('Sorento town snapshot').closest('tr')!;
    expect(within(row).getByText('Every 3 mins')).toBeInTheDocument();
    expect(within(row).getByText('Enabled')).toBeInTheDocument();
    expect(within(row).getByText('Failed')).toBeInTheDocument();
    expect(within(row).getByText('09/11/2026, 4:36 pm')).toBeInTheDocument(); // dd/mm/yyyy, Malaysia
    expect(within(row).getByText('09/11/2026, 4:39 pm')).toBeInTheDocument();
    expect(within(row).getByText(LONG_ERROR)).toBeInTheDocument();
  });

  it('keeps every row on one line: no description line, text cells truncate with a title', () => {
    renderList();
    const row = screen.getByText('Sorento town snapshot').closest('tr')!;
    // The description is detail-page content; it never stacks under the name.
    expect(within(row).queryByText(/Rebuilds each active company/)).not.toBeInTheDocument();
    for (const text of ['Sorento town snapshot', LONG_ERROR, 'Every 3 mins', '09/11/2026, 4:36 pm']) {
      const el = within(row).getByText(text);
      expect(el).toHaveClass('truncate');
      expect(el).toHaveAttribute('title', text);
    }
    // No cell stacks two blocks (the old Name cell was a flex-col of name + description).
    expect(row.querySelector('.flex-col')).toBeNull();
  });

  it('says Never run for a task that has not run', () => {
    rows = [task({ last_status: null, last_run_at: null, last_error: null })];
    renderList();
    expect(screen.getByText('Never run')).toBeInTheDocument();
  });

  it('sorts on the server, by name by default', () => {
    renderList();
    expect(calls.at(-1)?.sorting).toEqual([{ id: 'name', desc: false }]);
  });

  it('asks the server for a new order when a column header sorts', () => {
    renderList();
    fireEvent.click(screen.getByRole('button', { name: /Last error/ }));
    const sortItem = screen.queryByRole('menuitem', { name: /Asc/ });
    if (sortItem) fireEvent.click(sortItem);
    expect(calls.at(-1)?.sorting?.[0]?.id).toBe('last_error');
  });

  it('opens the detail page from the row', () => {
    renderList();
    routerPush.mockClear();
    fireEvent.click(screen.getByText('Every 3 mins'));
    expect(routerPush).toHaveBeenCalledTimes(1);
    expect(String(routerPush.mock.calls[0][0]).startsWith('/system-management/scheduled-tasks/t-1')).toBe(true);
  });
});
