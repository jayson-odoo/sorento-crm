/**
 * A list arriving with `page=` in its URL opens on that page.
 *
 * `useListStateFromUrl` reads the page during the render, so the list commits on
 * the right page - and then the list's own "reset to page one when a filter
 * changes" effect fires its mount run and stamps page 1 over it. The URL was
 * right and the grid was wrong (M5 run 2 evidence, finding 3).
 *
 * The harness below is the exact shape every list has: restore from the URL,
 * then reset the page when a filter changes.
 */
import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PaginationState } from '@tanstack/react-table';

const searchParams = { value: new URLSearchParams() };
vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams.value,
}));

import { useListStateFromUrl } from './useListStateFromUrl';
import { useResetPageOnFilterChange } from './useResetPageOnFilterChange';

function List({ filter }: { filter: string }) {
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [status, setStatus] = React.useState('all');

  useListStateFromUrl((state) => {
    setPagination({ pageIndex: state.pageIndex, pageSize: state.pageSize });
    setStatus(state.filters.status ?? 'all');
  });

  useResetPageOnFilterChange(setPagination, [status, filter]);

  return (
    <div>
      <span data-testid="page">{pagination.pageIndex}</span>
      <span data-testid="size">{pagination.pageSize}</span>
      <span data-testid="status">{status}</span>
    </div>
  );
}

function page(): string {
  return screen.getByTestId('page').textContent ?? '';
}

describe('a list restored from the URL', () => {
  it('opens on the page the URL names, not page one', () => {
    searchParams.value = new URLSearchParams(
      'page=2&limit=50&sort=created_at&dir=desc&from=abc',
    );

    render(<List filter="none" />);

    expect(page()).toBe('1');
    expect(screen.getByTestId('size').textContent).toBe('50');
  });

  it('honours the URL page under StrictMode, whose effects run twice on mount', () => {
    searchParams.value = new URLSearchParams('page=3&limit=25');

    render(
      <React.StrictMode>
        <List filter="none" />
      </React.StrictMode>,
    );

    expect(page()).toBe('2');
    expect(screen.getByTestId('size').textContent).toBe('25');
  });

  it('keeps the restored page while a filter it also restored settles', () => {
    searchParams.value = new URLSearchParams('page=4&limit=50&status=active');

    render(<List filter="none" />);

    expect(page()).toBe('3');
    expect(screen.getByTestId('status').textContent).toBe('active');
  });

  it('still drops back to page one when a filter actually changes', () => {
    searchParams.value = new URLSearchParams('page=2&limit=50');

    const { rerender } = render(<List filter="none" />);
    expect(page()).toBe('1');

    act(() => {
      rerender(<List filter="brand-a" />);
    });

    expect(page()).toBe('0');
  });

  it('leaves the page alone on a re-render that changed nothing', () => {
    searchParams.value = new URLSearchParams('page=2&limit=50');

    const { rerender } = render(<List filter="none" />);
    act(() => {
      rerender(<List filter="none" />);
    });

    expect(page()).toBe('1');
  });

  it('opens on page one when the URL says nothing', () => {
    searchParams.value = new URLSearchParams();

    render(<List filter="none" />);

    expect(page()).toBe('0');
  });
});
