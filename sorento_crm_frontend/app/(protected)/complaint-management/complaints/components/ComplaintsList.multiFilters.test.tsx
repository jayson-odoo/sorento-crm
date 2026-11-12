/**
 * FILTER-MULTISELECT PR3: the Complaints list's Status and Assigned to filters take several values (OR
 * within a filter, AND across); Root cause and Resolution already did. Assigned to keeps its
 * "Unassigned" pseudo-value, which OR-combines with a real assignee. The filters are URL-persisted, so a
 * comma-joined link and an older single-value link both read back. Each reaches the data hook as a list or
 * a comma-joined string; either reads the same here.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ComplaintsList from './ComplaintsList';
import { getUserLookup } from '@/services/userSelectService';

const view = vi.hoisted(() => ({ filters: null as Record<string, unknown> | null }));
// LIST-FILTER-MEMORY-4: the filters come back from the remembered view (per user), not the URL.
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (key: string) => ({
    listing_key: key,
    config: view.filters ? { version: 1, filters: view.filters, filtersVersion: 1 } : null,
  })),
  upsertUserListColumnConfig: vi.fn(async (key: string, payload: unknown) => ({ listing_key: key, config: payload })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/complaint-management/complaints',
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
const useComplaints = vi.fn();
vi.mock('../hooks/useComplaints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useComplaints')>();
  return {
    ...actual,
    useComplaints: (...a: unknown[]) => useComplaints(...a),
    useExportComplaintPdf: () => ({ mutate: vi.fn(), isPending: false }),
  };
});
vi.mock('../../complaint-root-causes/hooks/useComplaintRootCauses', () => ({
  useComplaintRootCausesSelect: () => ({ data: [{ id: 'rc-1', name: 'ZZT Cause One' }], error: null, refetch: vi.fn() }),
}));
vi.mock('../../complaint-resolutions/hooks/useComplaintResolutions', () => ({
  useComplaintResolutionsSelect: () => ({ data: [{ id: 'rs-1', name: 'ZZT Fix One' }], error: null, refetch: vi.fn() }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-ann', respond_user_id: 'resp-ann', name: 'ZZT Ann', email: 'a@e.com' },
    { id: 'u-ben', respond_user_id: 'resp-ben', name: 'ZZT Ben', email: 'b@e.com' },
    // ASSIGNED-FILTER-ALL-STAFF: staff never synced to Respond.io carry no respond id.
    { id: 'u-cat', name: 'ZZT Cat' },
  ]),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

/** The multi control that offers this option text. */
const boxWith = async (option: string) => {
  const boxes = await screen.findAllByRole('listbox');
  const found = boxes.find((b) => within(b).queryByText(option));
  if (!found) throw new Error(`no multi control offers ${option}`);
  return found as HTMLSelectElement;
};
const asList = (v: unknown): string[] =>
  v == null || v === '' ? [] : Array.isArray(v) ? (v as string[]) : String(v).split(',');
const lastArgs = () => {
  const calls = useComplaints.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
};

beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
  url.search = '';
  view.filters = null;
  useComplaints.mockReset();
  useComplaints.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintsList />
    </QueryClientProvider>,
  );
}
async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  renderIt();
  await user.click(await screen.findByRole('button', { name: /^filters/i }));
}

describe('Complaints - multi Status and Assigned to filters', () => {
  it('Assigned to, Status, Root cause and Resolution are all multi controls', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(4);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two statuses reach the hook, never with the All placeholder', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await boxWith('Settled on site'), ['new', 'approved']);
    await waitFor(() => expect(asList(lastArgs().status)).toEqual(['new', 'approved']));
    expect(asList(lastArgs().status)).not.toContain('__all__');
  });

  it('two assignees reach the hook and Unassigned OR-combines with a real assignee', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await boxWith('Unassigned');
    await waitFor(() => expect(within(box).queryByText('ZZT Ben')).not.toBeNull());
    await user.selectOptions(box, ['__unassigned__', 'u-ann']);
    await waitFor(() => expect(asList(lastArgs().assigned_to)).toEqual(['__unassigned__', 'u-ann']));
  });

  it('lists every staff member, a Respond.io-unsynced one too, keyed by CRM id (ASSIGNED-FILTER-ALL-STAFF)', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await boxWith('Unassigned');
    await waitFor(() => expect(within(box).queryByText('ZZT Cat')).not.toBeNull());
    expect(getUserLookup).toHaveBeenCalledWith({ include_inactive: true });
    await user.selectOptions(box, ['u-cat', 'u-ann']);
    await waitFor(() => expect(asList(lastArgs().assigned_to)).toEqual(['u-ann', 'u-cat']));
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await boxWith('Unassigned');
    await waitFor(() => expect(within(box).queryByText('ZZT Ben')).not.toBeNull());
    await user.selectOptions(box, ['u-ann', 'u-ben']);
    await user.selectOptions(await boxWith('Settled on site'), ['new', 'rejected']);
    await waitFor(() => {
      expect(asList(lastArgs().assigned_to)).toEqual(['u-ann', 'u-ben']);
      expect(asList(lastArgs().status)).toEqual(['new', 'rejected']);
    });
  });

  it('changing a filter goes back to page 1 (LIST-FILTER-MEMORY-4)', async () => {
    url.search = 'page=3';
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => expect(lastArgs().pageIndex).toBe(2));
    await user.selectOptions(await boxWith('Settled on site'), ['new']);
    await waitFor(() => {
      expect(asList(lastArgs().status)).toEqual(['new']);
      expect(lastArgs().pageIndex).toBe(0);
    });
  });

  it('a remembered multi-value view reads back into both filters', async () => {
    view.filters = { status: 'new,approved', assigned_to: 'resp-ann,resp-ben' };
    renderIt();
    await waitFor(() => {
      expect(asList(lastArgs().status)).toEqual(['new', 'approved']);
      expect(asList(lastArgs().assigned_to)).toEqual(['resp-ann', 'resp-ben']);
    });
  });

  it('a remembered one-value view reads back as one-value filters (guard)', async () => {
    view.filters = { status: 'approved', assigned_to: 'resp-ann' };
    renderIt();
    await waitFor(() => {
      expect(asList(lastArgs().status)).toEqual(['approved']);
      expect(asList(lastArgs().assigned_to)).toEqual(['resp-ann']);
    });
  });
});
