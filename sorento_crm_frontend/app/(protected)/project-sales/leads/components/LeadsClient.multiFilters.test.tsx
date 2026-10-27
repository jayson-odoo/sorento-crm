/**
 * FILTER-MULTISELECT PR6: the Leads list Outcome and Source filters take several values (OR); one set reaches the service, clearing clears,
 * an old single-value URL still reads, a joined one reads as a set.
 */
/**
 * S2c - LeadsClient (AC-O3, AC-O6), now on the shared DataGrid.
 *
 * Three things carry the design and are pinned here:
 * - the rows are the SHARED grid, with a pinned listing key rather than the pathname
 *     default, because a list that looks unlike every other list is a list people have
 *     to re-learn
 * - a duplicate is SURFACED, never enforced, and it names the other person so the
 *     race becomes a conversation
 * - search, filters and export share ONE toolbar row and nothing sits above the grid:
 *     the summary tiles were removed, and the metrics request with them
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listLeads = vi.fn();
const getLeadMetrics = vi.fn();
const listingKeys: (string | null | undefined)[] = [];

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/leads',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  // The list restores its page, sort and filters from the query string Back hands
  // it (S3-01), so it reads the URL on every render.
  useSearchParams: () => new URLSearchParams((globalThis as unknown as { __zztSearch?: string }).__zztSearch ?? ''),
}));

// The DataGrid persists column preferences over the network; stub that away, and
// record the key it was given so the pathname fallback cannot creep back in.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: async () => {}, isLoading: false };
  },
}));

vi.mock('../../_shared/services/projectService', () => ({
  listLeads: (...args: unknown[]) => listLeads(...args),
  getLeadMetrics: (...args: unknown[]) => getLeadMetrics(...args),
  getLead: vi.fn(),
  createLead: vi.fn(),
  updateLead: vi.fn(),
  changeLeadStatus: vi.fn(),
  previewQualify: vi.fn(),
  qualifyLead: vi.fn(),
  disqualifyLead: vi.fn(),
  reopenLead: vi.fn(),
  deleteLead: vi.fn(),
  listDisqualifyReasons: vi.fn(async () => []),
  getCustomerPortfolio: vi.fn(),
  listProjectTasks: vi.fn(),
  createProjectTask: vi.fn(),
  updateProjectTask: vi.fn(),
  changeTaskStatus: vi.fn(),
  deleteProjectTask: vi.fn(),
  getTaskHistory: vi.fn(),
  listMyTasks: vi.fn(),
  listTemplateTasks: vi.fn(),
  createTemplateTask: vi.fn(),
  updateTemplateTask: vi.fn(),
  deleteTemplateTask: vi.fn(),
  listProjects: vi.fn(),
  getProject: vi.fn(),
  listProjectTypes: vi.fn(),
  listProjectTemplates: vi.fn(),
  listParties: vi.fn(async () => ({ data: [], pagination: { total: 0, page: 1, limit: 50 } })),
  listStakeholders: vi.fn(),
  listCollaborators: vi.fn(),
  listTakeoverRequests: vi.fn(),
  previewClashes: vi.fn(),
  registerProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  changeProjectStatus: vi.fn(),
  addStakeholder: vi.fn(),
  updateStakeholder: vi.fn(),
  removeStakeholder: vi.fn(),
  createParty: vi.fn(),
  updateParty: vi.fn(),
  deleteParty: vi.fn(),
  createTakeoverRequest: vi.fn(),
  decideTakeoverRequest: vi.fn(),
  createProjectType: vi.fn(),
  updateProjectType: vi.fn(),
  deleteProjectType: vi.fn(),
  createProjectTemplate: vi.fn(),
  updateProjectTemplate: vi.fn(),
  deleteProjectTemplate: vi.fn(),
}));

vi.mock('../../_shared/services/leadAcceptanceService', () => ({
  listAwaitingAcceptance: vi.fn(),
  assignLead: vi.fn(),
  acceptLead: vi.fn(),
  declineLead: vi.fn(),
  nudgeLeadAssignee: vi.fn(),
}));

vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => []),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock(
  '@/app/(protected)/order-management/shared/hooks/use-customer-select-query',
  () => ({ useCustomerSelectQuery: () => ({ data: [], isLoading: false }) }),
);

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

import { LeadsClient } from './LeadsClient';

const NO_METRICS = {
  total: 0,
  open: 0,
  qualified: 0,
  disqualified: 0,
  decided: 0,
  conversion_rate: null,
  projects_from_leads: 0,
  disqualified_reasons: [],
};

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LeadsClient />
    </QueryClientProvider>,
  );
}

/** Radix opens its popovers on pointerdown, which fireEvent.click does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  listingKeys.length = 0;
  listLeads.mockResolvedValue({
    data: [],
    pagination: { total: 0, page: 1, limit: 25 },
  });
  getLeadMetrics.mockResolvedValue(NO_METRICS);
});

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : [String(v ?? '')]).flatMap((s) => s.split(',')).map((s) => s.trim()).filter(Boolean).sort();
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}

const last = () => {
  const args = listLeads.mock.calls.at(-1) as unknown[];
  return args.find((a) => a && typeof a === 'object') as Record<string, unknown>;
};
const FILTERS: [string, string, string][] = [['outcome', 'open', 'qualified'], ['source', 'site_visit', 'dealer']];

describe('leads/components/LeadsClient.multiFilters.test.tsx - multi filters', () => {
  beforeEach(() => {
    (globalThis as unknown as { __zztSearch?: string }).__zztSearch = '';
    Element.prototype.scrollIntoView = vi.fn();
  });

  it.each(FILTERS)('%s is a multi control', async (_p, a) => {
    renderClient();
    await waitFor(() => expect(listLeads).toHaveBeenCalled());
    openFilters();
    expect((await box(a)).hasAttribute('multiple')).toBe(true);
  });

  it.each(FILTERS)('%s: two values reach the service as one set', async (param, a, b) => {
    const user = userEvent.setup();
    renderClient();
    await waitFor(() => expect(listLeads).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(last()[param])).toEqual([a, b].sort()));
  });

  it.each(FILTERS)('%s: clearing sends nothing, never an all value', async (param, a, b) => {
    const user = userEvent.setup();
    renderClient();
    await waitFor(() => expect(listLeads).toHaveBeenCalled());
    openFilters();
    await user.selectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(last()[param])).toEqual([a, b].sort()));
    openFilters();
    await user.deselectOptions(await box(a), [a, b]);
    await waitFor(() => expect(setOf(last()[param])).toEqual([]));
    for (const [params] of listLeads.mock.calls) {
      expect(setOf((params as Record<string, unknown>)[param])).not.toContain('all');
    }
  });

  it('an old link with one value reads as one value, a joined one as a set', async () => {
    (globalThis as unknown as { __zztSearch?: string }).__zztSearch = 'outcome=disqualified&source=dealer,architect';
    renderClient();
    await waitFor(() => expect(listLeads).toHaveBeenCalled());
    await waitFor(() => expect(setOf(last().outcome)).toEqual(['disqualified']));
    expect(setOf(last().source)).toEqual(['architect', 'dealer']);
  });
});
