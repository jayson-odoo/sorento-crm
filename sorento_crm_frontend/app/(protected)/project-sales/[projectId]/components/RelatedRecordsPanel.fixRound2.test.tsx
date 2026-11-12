/**
 * PROJECT-RELATED-RECORDS fix round 2 (review S1, S2, S6): the Related grid's filters live in the
 * toolbar's Filters popover, present even when nothing is linked; a complaint row reads its status
 * as the complaint's own page does (`lib/complaint-status.ts`); the grid's page, sort, search and
 * filters live in the address bar, so Back from a record restores them. Fake values only.
 */
import React from 'react';
import { screen, within } from '@testing-library/react';
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

const state = vi.hoisted(() => ({ related: null as unknown, calls: [] as unknown[][] }));
vi.mock('../../_shared/hooks/useProjects', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useProjectRelatedRecords: (...args: unknown[]) => {
      state.calls.push(args);
      return { data: state.related, isLoading: false, isError: false, error: null, refetch: vi.fn() };
    },
    useSponsorshipRollup: () => ({ data: undefined, isLoading: false, isError: false, error: null }),
  };
});

import { RelatedRecordsPanel } from './RelatedRecordsPanel';

const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

beforeEach(() => {
  nav.search = '';
  nav.replace.mockReset();
  nav.push.mockReset();
  state.related = response();
  state.calls = [];
});

describe('RelatedRecordsPanel fix round 2', () => {
  it('S1 Type and Status sit in the Filters popover, not in the toolbar row', async () => {
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    expect(screen.queryAllByTestId('multi-select')).toHaveLength(0);
    await userEvent.setup().click(filtersButton());
    expect(screen.getAllByTestId('multi-select')).toHaveLength(2);
  });

  it('S1 the Filters button is there even when nothing is linked', () => {
    state.related = response([]);
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    expect(filtersButton()).toBeTruthy();
  });

  it("S2 a complaint row reads its status as the complaint's own page does", () => {
    state.related = response(
      ROWS.map((r) => (r.kind === 'complaint' ? { ...r, status: 'processed_by_cs' } : r)),
    );
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    const row = screen.getByText('CX-ZZT-0001').closest('tr') as HTMLElement;
    expect(within(row).getByText('Processed by CS')).toBeTruthy();
  });

  it('S6 page, sort, search and filters come back from the address bar', () => {
    nav.search =
      'tab=related&rel_page=2&rel_sort=number&rel_dir=asc&rel_query=tile&rel_type=complaint,stock_inquiry&rel_status=submitted';
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    const [projectId, params] = state.calls[0] as [string, Record<string, unknown>];
    expect(projectId).toBe('p1');
    expect(params).toMatchObject({
      pageIndex: 1,
      sorting: [{ id: 'number', desc: false }],
      searchQuery: 'tile',
      types: ['complaint', 'stock_inquiry'],
      statuses: ['submitted'],
    });
  });

  it('S6 a picked filter is written to the address bar, keeping the page params', async () => {
    nav.search = 'tab=related&page=3&sort=title';
    renderWithClient(<RelatedRecordsPanel project={project()} />);
    await userEvent.setup().click(filtersButton());
    const typeFilter = screen
      .getAllByTestId('multi-select')
      .find((el) => el.querySelector('button[data-value="complaint"]')) as HTMLElement;
    await userEvent.setup().click(within(typeFilter).getByText('Complaint', { selector: 'button' }));
    const urls = nav.replace.mock.calls.map((c) => String(c[0]));
    const last = new URLSearchParams(urls[urls.length - 1].split('?')[1]);
    expect(last.get('tab')).toBe('related');
    expect(last.get('rel_type')).toBe('complaint');
    // The projects list's own prev/next query stays.
    expect(last.get('page')).toBe('3');
    expect(last.get('sort')).toBe('title');
  });
});
