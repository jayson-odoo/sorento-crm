/**
 * OCN-ORDER-CHANGE-NOTICE round 17 (crew re-pass, FAIL 2): the Related grid mirrors only its own
 * `rel_*` params into the address bar. It never writes `tab`, and while the page's tab is not
 * Related it leaves the URL alone. Before, it always set `tab=related`, so after Back from a
 * record the page's tab clicks (PO, SO, Overview...) were written over and nothing happened.
 *
 * The URL here is a small store the mocked router writes (as Next's router does), so the panel
 * sees the page move to another tab while it is still mounted, as in a router transition.
 */
import React from 'react';
import { act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { project, renderWithClient, response } from './relatedRecordsTestKit';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

const url = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  const state = {
    search: '',
    replace: (() => {}) as (href: string) => void,
    set(search: string) {
      state.search = search;
      listeners.forEach((l) => l());
    },
    subscribe(l: () => void) {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
  return state;
});

vi.mock('next/navigation', async () => {
  const React = await import('react');
  return {
    useRouter: () => ({ push: vi.fn(), replace: (href: string) => url.replace(href) }),
    usePathname: () => '/project-sales/p1',
    useSearchParams: () => {
      const search = React.useSyncExternalStore(url.subscribe, () => url.search);
      return React.useMemo(() => new URLSearchParams(search), [search]);
    },
  };
});
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useProjectRelatedRecords: () => ({ data: response(), isLoading: false, isError: false, error: null, refetch: vi.fn() }),
    useSponsorshipRollup: () => ({ data: undefined, isLoading: false, isError: false, error: null }),
  };
});

import { RelatedRecordsPanel } from './RelatedRecordsPanel';

const writes: string[] = [];

beforeEach(() => {
  writes.length = 0;
  url.replace = (href: string) => {
    writes.push(href);
    url.set(href.split('?')[1] ?? '');
  };
});

describe('RelatedRecordsPanel and the page tab', () => {
  it('lets the page move to another tab while it is still mounted', () => {
    url.search = 'tab=related&rel_query=basin';
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    writes.length = 0;
    act(() => url.set('tab=orders&rel_query=basin')); // the page's tab click, panel not yet gone
    expect(writes.filter((w) => w.includes('tab=related'))).toEqual([]);
    expect(new URLSearchParams(url.search).get('tab')).toBe('orders');
  });

  it('never writes the tab itself', () => {
    url.search = 'rel_page=2';
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    expect(writes.some((w) => new URLSearchParams(w.split('?')[1] ?? '').has('tab'))).toBe(false);
  });

  it('still mirrors its own grid params while Related is the tab', () => {
    url.search = 'tab=related&rel_sort=number&rel_dir=asc';
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    const params = new URLSearchParams(url.search);
    expect(params.get('tab')).toBe('related');
    expect(params.get('rel_sort')).toBe('number');
    expect(params.get('rel_dir')).toBe('asc');
  });
});
