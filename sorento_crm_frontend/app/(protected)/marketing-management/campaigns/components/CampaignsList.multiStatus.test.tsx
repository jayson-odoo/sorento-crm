/**
 * FILTER-MULTISELECT PR3: the Campaigns list's Status filter takes several values (OR within the filter).
 * It is URL-persisted, so a comma-joined link and an older single-value link both read back. The value
 * reaches the data hook as a list or a comma-joined string; either reads the same here.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import CampaignsList from './CampaignsList';

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/marketing-management/campaigns',
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
const useCampaigns = vi.fn();
vi.mock('../hooks/useCampaigns', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useCampaigns')>();
  return { ...actual, useCampaigns: (...a: unknown[]) => useCampaigns(...a) };
});
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

const asList = (v: unknown): string[] =>
  v == null || v === '' ? [] : Array.isArray(v) ? (v as string[]) : String(v).split(',');
const lastArgs = () => {
  const calls = useCampaigns.mock.calls;
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
  useCampaigns.mockReset();
  useCampaigns.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CampaignsList />
    </QueryClientProvider>,
  );
}
async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  renderIt();
  await user.click(await screen.findByRole('button', { name: /^filters/i }));
}

describe('Campaigns - multi Status filter', () => {
  it('is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await screen.findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('two statuses reach the hook and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await screen.findByRole('listbox');
    const two = Array.from((box as HTMLSelectElement).options).slice(0, 2).map((o) => o.value);
    expect(two).not.toContain('all');
    await user.selectOptions(box, two);
    await waitFor(() => expect(asList(lastArgs().status)).toEqual(two));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(screen.getByRole('button', { name: /^filters/i })).getByText('1')).toBeInTheDocument());
  });

  it('a comma-joined link reads back into the filter', async () => {
    url.search = 'status=planning%2Cactive';
    renderIt();
    await waitFor(() => expect(asList(lastArgs().status)).toEqual(['planning', 'active']));
  });

  it('an older link with one status reads back as a one-value filter (guard)', async () => {
    url.search = 'status=active';
    renderIt();
    await waitFor(() => expect(asList(lastArgs().status)).toEqual(['active']));
  });
});
