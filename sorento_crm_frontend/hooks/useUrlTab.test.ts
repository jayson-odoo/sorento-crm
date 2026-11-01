/**
 * The shared `?tab=` hook (S1 AC-A5, NAV-KEEP-TAB).
 *
 * What this pins: an unknown `?tab=` value falls back to the default (a tab the next record
 * lacks), the default tab writes no `tab` param at all, every other query param on the URL
 * survives a tab change, the URL round-trips (a pasted / back-forward URL opens its tab), and a
 * tab switch works with no app router mounted.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useUrlTab } from './useUrlTab';

let search = '';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(search),
}));

const TABS = ['general', 'lines', 'revisions'] as const;
let replaceState: ReturnType<typeof vi.spyOn>;

/** Where jsdom thinks the page is: the record, plus the mocked query string. */
function at(path: string) {
  window.history.pushState(null, '', `${path}${search ? `?${search}` : ''}`);
}
const written = () => replaceState.mock.calls.at(-1)?.[2] as string;

beforeEach(() => {
  search = '';
  at('/x/1');
  replaceState = vi.spyOn(window.history, 'replaceState');
});
afterEach(() => replaceState.mockRestore());

describe('useUrlTab', () => {
  it('defaults to the default tab with no ?tab= on the URL', () => {
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general' }));
    expect(result.current[0]).toBe('general');
  });

  it('falls back to the default, without rewriting the URL, when ?tab= names a tab this record lacks', () => {
    search = 'tab=fulfilment&page=2';
    at('/x/1');
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general' }));
    expect(result.current[0]).toBe('general');
    expect(replaceState).not.toHaveBeenCalled();
  });

  it('URL round-trip: a pasted or back/forward URL opens the tab it names', () => {
    search = 'tab=lines';
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general' }));
    expect(result.current[0]).toBe('lines');
  });

  it('a tab that arrives late (permission still loading) is shown once it is in the list', () => {
    search = 'tab=revisions';
    let tabs: readonly ('general' | 'lines' | 'revisions')[] = ['general', 'lines'];
    const { result, rerender } = renderHook(() => useUrlTab({ tabs, defaultTab: 'general' }));
    expect(result.current[0]).toBe('general');
    tabs = TABS;
    rerender();
    expect(result.current[0]).toBe('revisions');
  });

  it('writes ?tab= for a non-default tab and shows it at once', () => {
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general' }));
    act(() => result.current[1]('lines'));
    expect(written()).toBe('/x/1?tab=lines');
    expect(result.current[0]).toBe('lines');
  });

  it('writes NO tab param when switching back to the default', () => {
    search = 'tab=lines';
    at('/x/1');
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general' }));
    act(() => result.current[1]('general'));
    expect(written()).toBe('/x/1');
    expect(result.current[0]).toBe('general');
  });

  it('carries every other query param (the list state the pager walks) through a tab change', () => {
    search = 'page=2&query=widget&sort=created_at&dir=desc';
    at('/x/1');
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general' }));
    act(() => result.current[1]('lines'));
    const params = new URL(written(), 'http://h').searchParams;
    expect(params.get('page')).toBe('2');
    expect(params.get('query')).toBe('widget');
    expect(params.get('sort')).toBe('created_at');
    expect(params.get('dir')).toBe('desc');
    expect(params.get('tab')).toBe('lines');
  });

  it('drops only tab on a default-tab change, keeping the rest', () => {
    search = 'tab=lines&send=1';
    at('/x/1');
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general' }));
    act(() => result.current[1]('general'));
    expect(written()).toBe('/x/1?send=1');
  });

  it('passes null state so the app router syncs the write into useSearchParams', () => {
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general' }));
    act(() => result.current[1]('lines'));
    expect(replaceState.mock.calls.at(-1)?.[0]).toBeNull();
  });

  it('a new URL (the pager stepped) answers again over a stale local pick', () => {
    const { result, rerender } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general' }));
    act(() => result.current[1]('lines'));
    search = 'page=1&from=b2&tab=revisions';
    rerender();
    expect(result.current[0]).toBe('revisions');
  });
});
