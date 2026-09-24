/**
 * S6 (`PLAN-board-oi-mechanical-22sep.md`, AC-B6-3/4/5/6/10/11/12): landing on an exact row
 * from a link on ANOTHER page - search cleared first, the grid pages to wherever the row
 * sits, the row glows for ~2s, the param strips itself off the URL, and a target nowhere on
 * the loaded page toasts rather than erroring.
 */
import { act, renderHook } from '@testing-library/react';
import type { Table } from '@tanstack/react-table';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useTableDeepLinkHighlight } from './useTableDeepLinkHighlight';

const replace = vi.fn();
let search = new URLSearchParams('');

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: (...args: unknown[]) => replace(...args) }),
  usePathname: () => '/scm/sales-orders/so-1',
  useSearchParams: () => search,
}));

const toastInfo = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: { info: (...args: unknown[]) => toastInfo(...args), success: vi.fn(), error: vi.fn() },
}));

interface Row {
  id: string;
}

/** A minimal stand-in for the slice of `Table<TData>` the hook actually reads. */
function fakeTable(rows: Row[], pageSize = 25) {
  const setPageIndex = vi.fn();
  const table = {
    getPrePaginationRowModel: () => ({ rows: rows.map((original) => ({ original })) }),
    getState: () => ({ pagination: { pageSize } }),
    setPageIndex,
  } as unknown as Table<Row>;
  return { table, setPageIndex };
}

beforeEach(() => {
  vi.useFakeTimers();
  replace.mockClear();
  toastInfo.mockClear();
  search = new URLSearchParams('');
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useTableDeepLinkHighlight', () => {
  it('AC-B6-10: jumps to the page holding the target - row 50 of 60 at 25 per page lands on page 3 (index 2)', () => {
    search = new URLSearchParams('line=row-50');
    const rows = Array.from({ length: 60 }, (_unused, index) => ({ id: `row-${index}` }));
    const { table, setPageIndex } = fakeTable(rows, 25);

    renderHook(() =>
      useTableDeepLinkHighlight(table, {
        paramName: 'line',
        rowId: (row: Row) => row.id,
        currentSearch: '',
      }),
    );

    expect(setPageIndex).toHaveBeenCalledWith(2);
  });

  it('AC-B6-11: a leftover search is cleared before the lookup, and nothing pages or glows yet', () => {
    search = new URLSearchParams('line=row-5');
    const rows = Array.from({ length: 10 }, (_unused, index) => ({ id: `row-${index}` }));
    const { table, setPageIndex } = fakeTable(rows, 25);
    const clearSearch = vi.fn();

    renderHook(() =>
      useTableDeepLinkHighlight(table, {
        paramName: 'line',
        rowId: (row: Row) => row.id,
        currentSearch: 'stale search text',
        clearSearch,
      }),
    );

    expect(clearSearch).toHaveBeenCalledTimes(1);
    expect(setPageIndex).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it('AC-B6-3/AC-B6-6: highlights the target row via rowClassName once found, nothing else', () => {
    search = new URLSearchParams('line=row-2');
    const rows = [{ id: 'row-1' }, { id: 'row-2' }, { id: 'row-3' }];
    const { table } = fakeTable(rows);

    const { result } = renderHook(() =>
      useTableDeepLinkHighlight(table, {
        paramName: 'line',
        rowId: (row: Row) => row.id,
        currentSearch: '',
      }),
    );

    expect(result.current.rowClassName({ id: 'row-2' })).toBe('deep-link-highlight');
    expect(result.current.rowClassName({ id: 'row-1' })).toBeUndefined();
    expect(result.current.rowAttributes({ id: 'row-2' })).toEqual({
      id: 'deep-link-row-row-2',
    });
  });

  it('AC-B6-3/AC-B6-4: strips the param via router.replace once the target is found, scroll: false', () => {
    search = new URLSearchParams('line=row-2&tab=lines');
    const rows = [{ id: 'row-1' }, { id: 'row-2' }];
    const { table } = fakeTable(rows);

    renderHook(() =>
      useTableDeepLinkHighlight(table, {
        paramName: 'line',
        rowId: (row: Row) => row.id,
        currentSearch: '',
      }),
    );

    expect(replace).toHaveBeenCalledTimes(1);
    const [url, options] = replace.mock.calls[0];
    expect(url).toBe('/scm/sales-orders/so-1?tab=lines');
    expect(options).toEqual({ scroll: false });
  });

  it('the highlight clears itself again after ~2s', () => {
    search = new URLSearchParams('line=row-2');
    const rows = [{ id: 'row-1' }, { id: 'row-2' }];
    const { table } = fakeTable(rows);

    const { result } = renderHook(() =>
      useTableDeepLinkHighlight(table, {
        paramName: 'line',
        rowId: (row: Row) => row.id,
        currentSearch: '',
      }),
    );

    expect(result.current.highlightId).toBe('row-2');
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(result.current.highlightId).toBeNull();
  });

  it('AC-B6-5/AC-B6-12: a target matching no loaded row toasts "That line is not shown here" and glows nothing', () => {
    search = new URLSearchParams('line=row-missing');
    const rows = [{ id: 'row-1' }, { id: 'row-2' }];
    const { table, setPageIndex } = fakeTable(rows);

    const { result } = renderHook(() =>
      useTableDeepLinkHighlight(table, {
        paramName: 'line',
        rowId: (row: Row) => row.id,
        currentSearch: '',
      }),
    );

    expect(toastInfo).toHaveBeenCalledWith('That line is not shown here');
    expect(setPageIndex).not.toHaveBeenCalled();
    expect(result.current.highlightId).toBeNull();
    expect(result.current.rowClassName({ id: 'row-1' })).toBeUndefined();
    // The param still strips itself off - a dead link does not linger on the URL either.
    expect(replace).toHaveBeenCalledTimes(1);
  });

  it('does nothing at all with no target param on the URL', () => {
    search = new URLSearchParams('');
    const rows = [{ id: 'row-1' }];
    const { table, setPageIndex } = fakeTable(rows);

    renderHook(() =>
      useTableDeepLinkHighlight(table, {
        paramName: 'line',
        rowId: (row: Row) => row.id,
        currentSearch: '',
      }),
    );

    expect(setPageIndex).not.toHaveBeenCalled();
    expect(toastInfo).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it('does nothing while enabled is false - a fetch still in flight is not "not shown here"', () => {
    search = new URLSearchParams('line=row-1');
    const rows = [{ id: 'row-1' }];
    const { table, setPageIndex } = fakeTable(rows);

    renderHook(() =>
      useTableDeepLinkHighlight(table, {
        paramName: 'line',
        rowId: (row: Row) => row.id,
        currentSearch: '',
        enabled: false,
      }),
    );

    expect(setPageIndex).not.toHaveBeenCalled();
    expect(toastInfo).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });
});
