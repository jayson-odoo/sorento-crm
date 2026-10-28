/**
 * FILTER-MULTISELECT PR3: the Sales targets Agents tab's Team filter takes several teams (OR within the
 * filter) plus the "No team" pseudo-value, which OR-combines with a real team. It is URL-persisted, so a
 * comma-joined link and an older single-value link both read back, and the value is written to the URL
 * comma-joined. Harness mirrors SalesTargetsView.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const url = vi.hoisted(() => ({ search: '?tab=agent' }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/targets',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
const hooks = vi.hoisted(() => ({
  useSalesTargets: vi.fn(),
  usePointRatios: () => ({ data: { rows: [] }, isLoading: false }),
  useSavePointRatio: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useImportDealerTargets: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDownloadDealerTemplate: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('../hooks/useSalesTargets', () => hooks);
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

import SalesTargetsView from './SalesTargetsView';

/** The multi control that offers this option text. */
const boxWith = async (option: string) => {
  const boxes = await screen.findAllByRole('listbox');
  const found = boxes.find((b) => within(b).queryByText(option));
  if (!found) throw new Error(`no multi control offers ${option}`);
  return found as HTMLSelectElement;
};
const row = (id: string, team: string) => ({
  target_id: id, target_no: `TGT-${id}`, name: `ZZT ${id}`, subject_kind: 'agent', sales_agent_id: `ag-${id}`,
  sales_team_id: null, subject_label: `Agent ${id}`, team_id: team, team_name: `ZZT Team ${team}`, left_on: null,
  members: null, metric: 'amount', basis: 'ordered', product_scope: 'all', scope_labels: [], period_id: null,
  period_start: null, period_end: null, start_date: '2026-01-01', end_date: '2026-12-31', target_value: 100,
  achieved_value: 10, achieved_pct: 10, parent_target_id: null,
});
const teamCalls = () =>
  hooks.useSalesTargets.mock.calls
    .map((c) => c[0] as Record<string, unknown>)
    .filter((p) => p.subject === 'agent');
const lastTeam = () => teamCalls()[teamCalls().length - 1]?.salesTeamId;

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
  vi.clearAllMocks();
  url.search = '?tab=agent';
  hooks.useSalesTargets.mockImplementation(() => ({
    data: { on: '2026-10-20', rows: [row('a', 'a'), row('b', 'b'), row('c', 'c')], unassigned_amount: 0, no_team_count: 0 },
    isLoading: false, isFetching: false, isError: false, isPlaceholderData: false,
  }));
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  render(<SalesTargetsView />);
  await screen.findByText('TGT-a');
  await user.click(screen.getByRole('button', { name: /^filters/i }));
}

describe('Sales targets - multi Team filter', () => {
  it('is a multi control offering No team', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await boxWith('No team');
    expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two teams go to the hook comma-joined and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await boxWith('No team'), ['a', 'b']);
    await waitFor(() => expect(lastTeam()).toBe('a,b'));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(screen.getByRole('button', { name: /^filters/i })).getByText('1')).toBeInTheDocument());
  });

  it('No team OR-combines with a real team', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await boxWith('No team'), ['none', 'a']);
    await waitFor(() => expect(lastTeam()).toBe('none,a'));
  });

  it('writes the comma-joined value to the URL', async () => {
    const spy = vi.spyOn(window.history, 'replaceState');
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await boxWith('No team'), ['a', 'b']);
    await waitFor(() => {
      const written = spy.mock.calls.map((c) => decodeURIComponent(String(c[2]))).join(' ');
      expect(written).toContain('team=a,b');
    });
    spy.mockRestore();
  });

  it('a comma-joined link reads back into the filter', async () => {
    url.search = '?tab=agent&team=a%2Cb';
    render(<SalesTargetsView />);
    await screen.findByText('TGT-a');
    await waitFor(() => expect(lastTeam()).toBe('a,b'));
  });

  it('an older link with one team reads back as a one-value filter (guard)', async () => {
    url.search = '?tab=agent&team=b';
    render(<SalesTargetsView />);
    await screen.findByText('TGT-a');
    await waitFor(() => expect(lastTeam()).toBe('b'));
  });
});
