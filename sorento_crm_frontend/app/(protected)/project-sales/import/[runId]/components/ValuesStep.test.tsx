/**
 * AC-PI-46 / AC-PI-18 / AC-PI-49 (RED): the Values step.
 *
 * Assumed (the coder matches these):
 *   `ValuesStep` (named export) from './ValuesStep', props:
 *     run: ProjectImportRun            (the run as GET /runs/{id} returns it)
 *     kind?: 'customer' | 'project' | 'developer' | 'person'   (controlled tab; default customer)
 *     onKindChange?: (kind) => void
 *   Reads `getLinesSummary(runId)` for the tab labels ("Customers 3 to do"; a kind with 0
 *   to do shows no count) and `listLines(runId, kind, grid, filters)` -> { items, total }.
 *   Bulk: tick lines, then the ONE "Set to" control, then an option ("Skip" for customers):
 *   `bulkSetLines(runId, { kind, keys: [[customer_value_key, value_key], ...], action, ... })`
 *   called ONCE with every ticked key.
 *   A set line shows its `target_label` and "Set by" as "<source word>, <set_by_name>,
 *   dd/mm/yyyy". No UUID is rendered.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
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

// Round 5 (REV-M4): the screen reads projects.import.run. Every test runs with both
// permissions unless it says otherwise.
const perms = vi.hoisted(() => ({
  set: new Set<string>(['projects.import.view', 'projects.import.run']),
}));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({
    permissions: [...perms.set],
    permissionSet: perms.set,
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: () => {},
  }),
  useHasPermission: (slug: string) => perms.set.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => perms.set.has(s)),
  PERMISSIONS_QUERY_KEY: ['my-permissions'],
}));
const nav = vi.hoisted(() => ({ search: '' }));

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/import/run-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ data: [], items: [], total: 0 }),
  })),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => {
  const Stand = (p: { 'aria-label'?: string; placeholder?: string }) => {
    const label = String(p['aria-label'] ?? p.placeholder ?? '');
    const id = /status|show/i.test(label) ? 'multi-select-status' : 'multi-select';
    return <div data-testid={id} aria-label={label} />;
  };
  return { SearchableMultiSelect: Stand, default: Stand };
});

const service = vi.hoisted(() => ({
  getLinesSummary: vi.fn(),
  listLines: vi.fn(),
  setLine: vi.fn(),
  bulkSetLines: vi.fn(),
  getRun: vi.fn(),
}));
vi.mock('../../../_shared/services/projectImportService', () => service);

import { ValuesStep } from './ValuesStep';

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const RUN_ID = '0b5c3a52-6a8e-4f6e-9f43-6a1f2f8e1c11';
const CUSTOMER_ID = '3f1e2d4c-5b6a-4789-8a9b-0c1d2e3f4a5b';

const run = {
  id: RUN_ID,
  run_no: 'PIM-0002',
  filename: 'SO SUMMARY 2026.xlsx',
  status: 'draft',
  missing_columns: [],
  sheets: [],
  columns: {},
  preview_counts: null,
};

function line(value: string, extra: Record<string, unknown> = {}) {
  return {
    kind: 'customer',
    customer_value_key: '',
    value_key: value,
    value_text: value,
    customer_text: null,
    rows: 5,
    action: null,
    target_id: null,
    target_label: null,
    new_title: null,
    source: null,
    set_by_name: null,
    set_at: null,
    status: 'todo',
    ...extra,
  };
}

const lines = [
  line('CUSTOMER 001 SDN BHD', {
    action: 'link',
    target_id: CUSTOMER_ID,
    target_label: 'ZZT DEALER ONE',
    source: 'saved',
    set_by_name: 'STAFF 01',
    set_at: '2026-08-04T10:00:00',
    status: 'set',
  }),
  line('CUSTOMER 002 SDN BHD'),
  line('CUSTOMER 003 SDN BHD'),
  line('CUSTOMER 004 SDN BHD'),
];

function renderStep() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ValuesStep run={run as never} />
    </QueryClientProvider>
  );
}

function textMatch(re: RegExp) {
  return (_: string, el: Element | null) =>
    !!el && re.test((el.textContent ?? '').replace(/\s+/g, ' ').trim()) &&
    Array.from(el.children).every((c) => !re.test((c.textContent ?? '').replace(/\s+/g, ' ').trim()));
}

beforeEach(() => {
  vi.clearAllMocks();
  perms.set = new Set(['projects.import.view', 'projects.import.run']);
  nav.search = '';
  service.getLinesSummary.mockResolvedValue({
    customer: { total: 4, todo: 3 },
    project: { total: 12, todo: 12 },
    developer: { total: 4, todo: 4 },
    person: { total: 2, todo: 0 },
  });
  service.listLines.mockResolvedValue({ items: lines, total: lines.length });
  service.bulkSetLines.mockResolvedValue({ data: [] });
  service.setLine.mockResolvedValue({});
});

describe('ValuesStep', () => {
  it('labels each tab with its "N to do" from the summary', async () => {
    renderStep();
    expect(await screen.findAllByText(textMatch(/^Customers ?3 to do$/))).not.toHaveLength(0);
    expect(screen.getAllByText(textMatch(/^Projects ?12 to do$/))).not.toHaveLength(0);
    expect(screen.getAllByText(textMatch(/^Developers ?4 to do$/))).not.toHaveLength(0);
    expect(screen.queryAllByText(/People ?0 to do/)).toHaveLength(0);
    expect(service.getLinesSummary).toHaveBeenCalledWith(RUN_ID);
  });

  it('lists the lines of the open kind from listLines', async () => {
    renderStep();
    expect(await screen.findByText('CUSTOMER 002 SDN BHD')).toBeInTheDocument();
    const [runId, kind] = service.listLines.mock.calls[0];
    expect(runId).toBe(RUN_ID);
    expect(kind).toBe('customer');
  });

  it('bulk "Set to" calls bulkSetLines ONCE with the three ticked keys', async () => {
    const user = userEvent.setup();
    renderStep();
    await screen.findByText('CUSTOMER 004 SDN BHD');

    for (const value of ['CUSTOMER 002 SDN BHD', 'CUSTOMER 003 SDN BHD', 'CUSTOMER 004 SDN BHD']) {
      const row = screen.getByText(value).closest('tr')!;
      await user.click(within(row).getByRole('checkbox'));
    }
    await user.click(screen.getByRole('button', { name: /Set to/i }));
    // The option sits in the menu the "Set to" control opened (menuitem, option or button).
    const options = await screen.findAllByText(/^Skip$/i);
    await user.click(options[options.length - 1]);

    await waitFor(() => expect(service.bulkSetLines).toHaveBeenCalledTimes(1));
    const [runId, body] = service.bulkSetLines.mock.calls[0];
    expect(runId).toBe(RUN_ID);
    expect(body).toMatchObject({ kind: 'customer', action: 'skip' });
    expect([...body.keys].sort()).toEqual([
      ['', 'CUSTOMER 002 SDN BHD'],
      ['', 'CUSTOMER 003 SDN BHD'],
      ['', 'CUSTOMER 004 SDN BHD'],
    ]);
    expect(service.setLine).not.toHaveBeenCalled();
  });

  it('a set line shows what it links to and who set it, dated dd/mm/yyyy', async () => {
    renderStep();
    const row = (await screen.findByText('CUSTOMER 001 SDN BHD')).closest('tr')!;
    expect(within(row).getByText(/ZZT DEALER ONE/)).toBeInTheDocument();
    expect(within(row).getByText(/STAFF 01/)).toBeInTheDocument();
    expect(within(row).getByText(/04\/08\/2026/)).toBeInTheDocument();
  });

  it('renders no UUID', async () => {
    const { container } = renderStep();
    await screen.findByText('CUSTOMER 001 SDN BHD');
    expect(container.textContent ?? '').not.toMatch(UUID_RE);
  });
});

async function openFiltersIfAny(user: ReturnType<typeof userEvent.setup>) {
  const button = screen.queryByRole('button', { name: /^Filters/ });
  if (button) await user.click(button);
}

describe('ValuesStep, round 5', () => {
  it('r5: a view-only user gets no tick boxes, no Set to and no pickers (REV-M4)', async () => {
    perms.set = new Set(['projects.import.view']);
    renderStep();
    await screen.findByText('CUSTOMER 002 SDN BHD');
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /Set to/i })).toBeNull();
    expect(screen.queryAllByRole('button', { name: /^Change /i })).toHaveLength(0);
  });

  it('r5: the Values grid offers Columns (REV-minor4)', async () => {
    renderStep();
    await screen.findByText('CUSTOMER 002 SDN BHD');
    expect(screen.getByRole('button', { name: /Columns/ })).toBeInTheDocument();
  });

  it('r5: the status filter is a multi-select (REV-minor4)', async () => {
    const user = userEvent.setup();
    renderStep();
    await screen.findByText('CUSTOMER 002 SDN BHD');
    await openFiltersIfAny(user);
    const filter = await screen.findByTestId('multi-select-status');
    expect(filter).toBeInTheDocument();
  });
});

describe('ValuesStep, round 6', () => {
  it('r6: D4 a focus line opens searched (or highlighted) on that line', async () => {
    const focusLine = { kind: 'customer', customer_value_key: '', value_key: 'CUSTOMER 003 SDN BHD' };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ValuesStep run={run as never} kind="customer" focusLine={focusLine as never} />
      </QueryClientProvider>
    );
    const cell = await screen.findByText('CUSTOMER 003 SDN BHD');
    await waitFor(() => {
      const searched = service.listLines.mock.calls.some(([, , grid]) =>
        String(grid?.searchQuery ?? '').toUpperCase().includes('CUSTOMER 003'));
      const tr = cell.closest('tr');
      const highlighted =
        tr?.getAttribute('data-highlighted') === 'true' ||
        tr?.getAttribute('aria-selected') === 'true' ||
        tr?.getAttribute('data-state') === 'selected';
      expect(searched || highlighted).toBe(true);
    });
  });

  it('r6: D8 Value in file and Linked to are the first two data columns', async () => {
    const { container } = renderStep();
    await screen.findByText('CUSTOMER 002 SDN BHD');
    const titles = Array.from(container.querySelectorAll('table thead th'))
      .map((th) => (th.textContent ?? '').trim())
      .filter((t) => t.length > 0);
    expect(titles.slice(0, 2)).toEqual(['Value in file', 'Linked to']);
  });
});

describe('ValuesStep, round 7', () => {
  it('r7: D8 at 375 Linked to starts within the first 300 px', async () => {
    const { container } = renderStep();
    await screen.findByText('CUSTOMER 002 SDN BHD');
    const ths = Array.from(container.querySelectorAll('table thead th')) as HTMLElement[];
    const at = ths.findIndex((th) => (th.textContent ?? '').trim() === 'Linked to');
    expect(at).toBeGreaterThan(-1);
    // The tick column + Value in file, with their cell padding (the th width carries it in a
    // fixed layout): the picker must be on a 360 px phone screen at first paint.
    const before = ths.slice(0, at).reduce((sum, th) => sum + parseFloat(th.style.width || '0'), 0);
    expect(before).toBeLessThanOrEqual(300);
  });
});
