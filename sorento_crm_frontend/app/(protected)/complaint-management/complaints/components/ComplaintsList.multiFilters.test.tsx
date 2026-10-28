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
    await user.selectOptions(box, ['__unassigned__', 'resp-ann']);
    await waitFor(() => expect(asList(lastArgs().assigned_to)).toEqual(['__unassigned__', 'resp-ann']));
  });

  it('the filters AND across each other', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await boxWith('Unassigned');
    await waitFor(() => expect(within(box).queryByText('ZZT Ben')).not.toBeNull());
    await user.selectOptions(box, ['resp-ann', 'resp-ben']);
    await user.selectOptions(await boxWith('Settled on site'), ['new', 'rejected']);
    await waitFor(() => {
      expect(asList(lastArgs().assigned_to)).toEqual(['resp-ann', 'resp-ben']);
      expect(asList(lastArgs().status)).toEqual(['new', 'rejected']);
    });
  });

  it('a comma-joined link reads back into both filters', async () => {
    url.search = 'status=new%2Capproved&assigned_to=resp-ann%2Cresp-ben';
    renderIt();
    await waitFor(() => {
      expect(asList(lastArgs().status)).toEqual(['new', 'approved']);
      expect(asList(lastArgs().assigned_to)).toEqual(['resp-ann', 'resp-ben']);
    });
  });

  it('an older link with one status and one assignee reads back as one-value filters (guard)', async () => {
    url.search = 'status=approved&assigned_to=resp-ann';
    renderIt();
    await waitFor(() => {
      expect(asList(lastArgs().status)).toEqual(['approved']);
      expect(asList(lastArgs().assigned_to)).toEqual(['resp-ann']);
    });
  });
});
