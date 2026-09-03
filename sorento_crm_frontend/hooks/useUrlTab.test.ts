/**
 * S1, AC-A5 - the shared `?tab=` hook both the loading plan and the proforma invoice use.
 *
 * What this pins: an unknown `?tab=` value falls back to the default, the default tab writes
 * no `tab` param at all, and every other query param on the URL survives a tab change.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useUrlTab } from './useUrlTab';

const replace = vi.fn();
let search = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(search),
}));

const TABS = ['general', 'lines', 'revisions'] as const;

beforeEach(() => {
  replace.mockReset();
  search = '';
});

describe('useUrlTab', () => {
  it('defaults to the default tab with no ?tab= on the URL', () => {
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general', basePath: '/x/1' }));
    expect(result.current[0]).toBe('general');
  });

  it('falls back to the default when ?tab= names something this record has no tab for', () => {
    search = 'tab=nonsense';
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general', basePath: '/x/1' }));
    expect(result.current[0]).toBe('general');
  });

  it('reads a recognised ?tab= as the active tab', () => {
    search = 'tab=lines';
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general', basePath: '/x/1' }));
    expect(result.current[0]).toBe('lines');
  });

  it('writes ?tab= for a non-default tab', () => {
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general', basePath: '/x/1' }));
    act(() => result.current[1]('lines'));
    expect(replace).toHaveBeenCalledWith('/x/1?tab=lines', { scroll: false });
  });

  it('writes NO tab param when switching back to the default', () => {
    search = 'tab=lines';
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general', basePath: '/x/1' }));
    act(() => result.current[1]('general'));
    expect(replace).toHaveBeenCalledWith('/x/1', { scroll: false });
  });

  it('carries every other query param through a tab change untouched', () => {
    search = 'page=2&query=widget';
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general', basePath: '/x/1' }));
    act(() => result.current[1]('lines'));
    const [url] = replace.mock.calls[0];
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('page')).toBe('2');
    expect(params.get('query')).toBe('widget');
    expect(params.get('tab')).toBe('lines');
  });

  it('drops an unrelated param already present, keeping the rest, on a default-tab change', () => {
    search = 'tab=lines&send=1';
    const { result } = renderHook(() => useUrlTab({ tabs: TABS, defaultTab: 'general', basePath: '/x/1' }));
    act(() => result.current[1]('general'));
    expect(replace).toHaveBeenCalledWith('/x/1?send=1', { scroll: false });
  });
});
