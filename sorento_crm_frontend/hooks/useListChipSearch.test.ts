/**
 * SEARCH-CHIPS slice 2: the chip search state every document list shares, extracted from
 * `SalesOrdersGrid.tsx` (slice 1) into `hooks/useListChipSearch.ts`. Plan
 * `documentation/plans/ui/PLAN-search-chips-b-12nov.md`; behaviour per UAC
 * `documentation/plans/ui/search-chips-acceptance-criteria.md` F5, S2, S4.
 *
 * - `useListChipSearch()`: chips + the debounced typed text make `searchTerms`
 *   (`addSearchChips(chips, [debounced text]).chips`); emptied text settles at once;
 *   `restore(searchQueries)` turns a URL's `query` values back into chips.
 * - `useSearchInAddressBar({ detailSearch, searchTermsKey, enabled })`: writes
 *   `?${detailSearch}` with `history.replaceState` only once the search has changed (never on
 *   the first render) and never while `enabled` is false.
 * Red first: the module does not exist yet.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { SEARCH_DEBOUNCE_MS } from './useDebouncedSearch';
import { useListChipSearch, useSearchInAddressBar } from './useListChipSearch';

describe('useListChipSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts empty', () => {
    const { result } = renderHook(() => useListChipSearch());
    expect(result.current.searchInput).toBe('');
    expect(result.current.chips).toEqual([]);
    expect(result.current.searchTerms).toEqual([]);
    expect(result.current.isSettling).toBe(false);
  });

  it('chips become search terms at once, in order', () => {
    const { result } = renderHook(() => useListChipSearch());
    act(() => result.current.setChips(['SO1', 'Acme, Trading']));
    expect(result.current.chips).toEqual(['SO1', 'Acme, Trading']);
    expect(result.current.searchTerms).toEqual(['SO1', 'Acme, Trading']);
  });

  it('typed text joins the chips one debounce later, and settles in between', () => {
    const { result } = renderHook(() => useListChipSearch());
    act(() => result.current.setChips(['SO1', 'SO2']));
    act(() => result.current.setSearchInput('Fakeco'));

    expect(result.current.searchInput).toBe('Fakeco');
    expect(result.current.searchTerms).toEqual(['SO1', 'SO2']);
    expect(result.current.isSettling).toBe(true);

    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });
    expect(result.current.searchTerms).toEqual(['SO1', 'SO2', 'Fakeco']);
    expect(result.current.isSettling).toBe(false);
  });

  it('typed text the same as a chip (any case) is not a second term', () => {
    const { result } = renderHook(() => useListChipSearch());
    act(() => result.current.setChips(['SO1']));
    act(() => result.current.setSearchInput('so1'));
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });
    expect(result.current.searchTerms).toEqual(['SO1']);
  });

  it('typed text over 100 characters is searched cut to 100', () => {
    const { result } = renderHook(() => useListChipSearch());
    act(() => result.current.setSearchInput('q'.repeat(150)));
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });
    expect(result.current.searchTerms).toEqual(['q'.repeat(100)]);
    expect(result.current.searchInput).toBe('q'.repeat(150));
  });

  it('emptied text settles at once: no debounce carrying the old word', () => {
    const { result } = renderHook(() => useListChipSearch());
    act(() => result.current.setChips(['SO1']));
    act(() => result.current.setSearchInput('Fakeco'));
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });
    expect(result.current.searchTerms).toEqual(['SO1', 'Fakeco']);

    act(() => result.current.setSearchInput(''));
    // No timer advanced: the stale word is gone in the same render.
    expect(result.current.searchInput).toBe('');
    expect(result.current.searchTerms).toEqual(['SO1']);
    expect(result.current.isSettling).toBe(false);
  });

  it('searchTermsKey follows the terms: equal terms, equal key; different terms, different key', () => {
    const { result } = renderHook(() => useListChipSearch());
    const empty = result.current.searchTermsKey;
    act(() => result.current.setChips(['SO1', 'SO2']));
    const two = result.current.searchTermsKey;
    expect(two).not.toBe(empty);
    act(() => result.current.setChips(['SO1']));
    expect(result.current.searchTermsKey).not.toBe(two);
    act(() => result.current.setChips(['SO1', 'SO2']));
    expect(result.current.searchTermsKey).toBe(two);
  });

  it('restore turns the URL query values into chips, deduped, blanks dropped, text emptied', () => {
    const { result } = renderHook(() => useListChipSearch());
    act(() => result.current.setSearchInput('typed'));
    act(() =>
      result.current.restore(['SO371334', 'Acme, Trading', 'so371334', '  ']),
    );

    expect(result.current.chips).toEqual(['SO371334', 'Acme, Trading']);
    expect(result.current.searchInput).toBe('');
    // At once, not one debounce later.
    expect(result.current.searchTerms).toEqual(['SO371334', 'Acme, Trading']);
    expect(result.current.isSettling).toBe(false);
  });

  it('restore with no values clears the chips', () => {
    const { result } = renderHook(() => useListChipSearch());
    act(() => result.current.setChips(['SO1']));
    act(() => result.current.restore([]));
    expect(result.current.chips).toEqual([]);
    expect(result.current.searchTerms).toEqual([]);
  });
});

describe('useSearchInAddressBar', () => {
  let replaceState: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    window.history.replaceState(null, '', '/scm/purchase-orders');
    replaceState = vi.spyOn(window.history, 'replaceState');
  });

  afterEach(() => {
    replaceState.mockRestore();
  });

  type Props = {
    detailSearch: string;
    searchTermsKey: string;
    enabled: boolean;
  };

  function mount(initial: Props) {
    return renderHook((props: Props) => useSearchInAddressBar(props), {
      initialProps: initial,
    });
  }

  it('does not write on the first render', () => {
    mount({
      detailSearch: 'page=1&limit=25&query=SO1',
      searchTermsKey: 'SO1',
      enabled: true,
    });
    expect(replaceState).not.toHaveBeenCalled();
  });

  it('a page change alone, before any search change, does not write', () => {
    const { rerender } = mount({
      detailSearch: 'page=1&limit=25',
      searchTermsKey: '',
      enabled: true,
    });
    rerender({
      detailSearch: 'page=2&limit=25',
      searchTermsKey: '',
      enabled: true,
    });
    expect(replaceState).not.toHaveBeenCalled();
  });

  it('once the search changes, writes ?detailSearch with replaceState', () => {
    const { rerender } = mount({
      detailSearch: 'page=1&limit=25',
      searchTermsKey: '',
      enabled: true,
    });
    rerender({
      detailSearch: 'page=1&limit=25&query=SO1&query=SO2',
      searchTermsKey: 'SO1\nSO2',
      enabled: true,
    });
    expect(replaceState).toHaveBeenCalled();
    const url = String(replaceState.mock.calls.at(-1)![2]);
    expect(url).toBe('?page=1&limit=25&query=SO1&query=SO2');
    expect(window.location.search).toBe('?page=1&limit=25&query=SO1&query=SO2');
  });

  it('after the search changed, later state (a page change) is written too', () => {
    const { rerender } = mount({
      detailSearch: 'page=1&limit=25',
      searchTermsKey: '',
      enabled: true,
    });
    rerender({
      detailSearch: 'page=1&limit=25&query=SO1',
      searchTermsKey: 'SO1',
      enabled: true,
    });
    rerender({
      detailSearch: 'page=2&limit=25&query=SO1',
      searchTermsKey: 'SO1',
      enabled: true,
    });
    expect(String(replaceState.mock.calls.at(-1)![2])).toBe(
      '?page=2&limit=25&query=SO1',
    );
  });

  it('never writes while enabled is false', () => {
    const { rerender } = mount({
      detailSearch: 'page=1&limit=25',
      searchTermsKey: '',
      enabled: false,
    });
    rerender({
      detailSearch: 'page=1&limit=25&query=SO1',
      searchTermsKey: 'SO1',
      enabled: false,
    });
    rerender({
      detailSearch: 'page=2&limit=25&query=SO1',
      searchTermsKey: 'SO1',
      enabled: false,
    });
    expect(replaceState).not.toHaveBeenCalled();
  });
});
