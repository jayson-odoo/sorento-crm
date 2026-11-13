/**
 * PROJECT-RELATED-RECORDS follow-up (tab navigation): the Related panel mirrors its own grid state
 * into the address bar ONLY while the Related tab is the active one, and never writes the tab
 * itself. Before, it set `tab=related` on every address change, so after Back from a record a click
 * on any other project tab was written straight back to Related. Fake values only.
 */
import React from 'react';
import { screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { project, renderWithClient, response, ROWS } from './relatedRecordsTestKit';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const nav = vi.hoisted(() => ({ search: '', replace: vi.fn(), push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    options,
    value,
    onChange,
  }: {
    options: { value: string; label: string }[];
    value: string[];
    onChange: (v: string[]) => void;
  }) => (
    <div data-testid="multi-select">
      {options.map((o) => (
        <button type="button" key={o.value} data-value={o.value} onClick={() => onChange([...(value ?? []), o.value])}>
          {o.label}
        </button>
      ))}
    </div>
  ),
}));

const state = vi.hoisted(() => ({
  related: null as unknown,
  calls: [] as unknown[][],
  rollup: undefined as unknown,
  rollupCalls: [] as unknown[][],
}));
vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useProjectRelatedRecords: (...args: unknown[]) => {
      state.calls.push(args);
      return { data: state.related, isLoading: false, isError: false, error: null, refetch: vi.fn() };
    },
    useSponsorshipRollup: (...args: unknown[]) => {
      state.rollupCalls.push(args);
      return { data: state.rollup, isLoading: false, isError: false, error: null };
    },
  };
});

import { RelatedRecordsPanel } from './RelatedRecordsPanel';


const sortByNumber = async () => {
  await userEvent.setup().click(screen.getByRole('button', { name: /number/i }));
};

const replacedUrls = () =>
  nav.replace.mock.calls.map((c) => new URLSearchParams(String(c[0]).split('?')[1] ?? ''));

beforeEach(() => {
  nav.search = '';
  nav.replace.mockReset();
  nav.push.mockReset();
  state.related = response();
  state.calls = [];
  state.rollup = undefined;
  state.rollupCalls = [];
});

describe('RelatedRecordsPanel tab navigation', () => {
  it('(1) once another project tab is picked, the panel never writes the tab back to Related', () => {
    nav.search = 'tab=related&rel_sort=number&rel_dir=asc';
    const client = new QueryClient();
    const view = renderWithClient(<RelatedRecordsPanel project={project()} />);
    nav.replace.mockReset();
    // The project page's tab click: the address moves to the PO tab while the panel is still mounted.
    nav.search = 'tab=orders&rel_sort=number&rel_dir=asc';
    view.rerender(
      <QueryClientProvider client={client}>
        <RelatedRecordsPanel project={project()} />
      </QueryClientProvider>,
    );
    for (const url of replacedUrls()) expect(url.get('tab')).not.toBe('related');
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it('(1) with no tab in the address (Overview), the panel writes nothing', () => {
    nav.search = '';
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it('(2) on the Related tab its grid state keeps tab=related, so Back from a record lands on Related', async () => {
    nav.search = 'tab=related';
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    await sortByNumber();
    const urls = replacedUrls();
    expect(urls.length).toBeGreaterThan(0);
    const last = urls[urls.length - 1];
    expect(last.get('tab')).toBe('related');
    expect(last.get('rel_sort')).toBeTruthy();
  });
});
