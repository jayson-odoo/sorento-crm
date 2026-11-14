/**
 * PROJECT-LEADS-REASSIGN, Phase 2 red tests: the Access card's ONE leads list (UAC B1, B2, B3,
 * B5, B6).
 *
 * UAC: documentation/plans/project-sales/project-leads-reassign-14nov-acceptance-criteria.md.
 *
 * Observed at the network boundary (`apiFetch`), so hook and service names do not matter.
 * Contract names the tests bind: the project payload's `primary_owner_user_id` +
 * `primary_owner_name`, and `ReassignProjectDialog`'s optional `initialUserId` (the panel opens
 * it with the right-clicked person preselected).
 *
 * Fixture story: Sales A registered the project from a lead (the primary), Sales B's secondary
 * lead was approved so Sales B owns it now, Sales C has a pending secondary lead, Sales D's was
 * dismissed, Sales E only asked to join (not a lead, not in the list).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn();
Element.prototype.setPointerCapture = vi.fn();
Element.prototype.releasePointerCapture = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-m', name: 'Manager M' } }, status: 'authenticated' }),
}));

let granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => granted.has(s)),
  usePermissions: () => ({
    permissions: [...granted],
    permissionSet: granted,
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));
// The lead source is labelled from its editable lookup set, as the Where this came from card does.
vi.mock('@/hooks/useLookupSetOptions', () => ({
  useLookupSetOptions: () => ({
    data: [
      { value: 'bci', label: 'BCI Asia' },
      { value: 'site_visit', label: 'Site visit' },
    ],
    isLoading: false,
  }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-a', name: 'Sales A' },
    { id: 'u-b', name: 'Sales B' },
    { id: 'u-c', name: 'Sales C' },
    { id: 'u-d', name: 'Sales D' },
    { id: 'u-e', name: 'Sales E' },
    { id: 'u-z', name: 'Sales Z' },
  ]),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ id, value, onChange, options }: never) => (
    <select
      id={id}
      aria-label="Salesperson"
      value={value}
      onChange={(e) => (onChange as (v: string) => void)(e.target.value)}
    >
      <option value="" />
      {((options ?? []) as { value: string; label: string }[]).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

type Call = { url: string; method: string; body: unknown };
const calls: Call[] = [];
const REQUESTS = [
  {
    id: 'r-c',
    project_id: 'p1',
    kind: 'dispute',
    status: 'pending',
    requester_user_id: 'u-c',
    requester_name: 'Sales C',
    reason: 'Met the architect at the March launch.',
    created_at: '2026-10-20T02:00:00Z',
  },
  {
    id: 'r-b',
    project_id: 'p1',
    kind: 'dispute',
    status: 'approved',
    requester_user_id: 'u-b',
    requester_name: 'Sales B',
    reason: 'Registered this with the developer in January.',
    created_at: '2026-10-10T02:00:00Z',
  },
  {
    id: 'r-d',
    project_id: 'p1',
    kind: 'dispute',
    status: 'rejected',
    requester_user_id: 'u-d',
    requester_name: 'Sales D',
    reason: 'Saw the hoarding on the highway.',
    created_at: '2026-10-12T02:00:00Z',
  },
  {
    id: 'r-e',
    project_id: 'p1',
    kind: 'join',
    status: 'pending',
    requester_user_id: 'u-e',
    requester_name: 'Sales E',
    reason: 'Please add me.',
    created_at: '2026-10-21T02:00:00Z',
  },
];

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiFetch: async (input: string, init: RequestInit = {}) => {
      const method = (init.method ?? 'GET').toUpperCase();
      calls.push({
        url: String(input),
        method,
        body: typeof init.body === 'string' ? JSON.parse(init.body) : null,
      });
      const ok = (b: unknown) =>
        new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
      if (method === 'GET' && String(input).includes('/takeover-requests')) return ok({ data: REQUESTS });
      if (method === 'POST' && String(input).includes('/decide')) {
        return ok({ id: 'r-c', status: JSON.parse(String(init.body)).approve ? 'approved' : 'rejected' });
      }
      if (method === 'PUT') return ok({ id: 'p1' });
      return ok({ data: [] });
    },
  };
});

import { ProjectAccessPanel } from './ProjectAccessPanel';

function project(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000142',
    title: 'Menara CONTOH',
    outcome: 'open',
    owner_user_id: 'u-b',
    owner_name: 'Sales B',
    primary_owner_user_id: 'u-a',
    primary_owner_name: 'Sales A',
    lead_id: 'l-1',
    lead_code: 'LD-0001',
    lead_source: 'bci',
    lead_created_at: '2026-10-05T02:00:00Z',
    created_at: '2026-10-07T02:00:00Z',
    is_critical: false,
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    approval_state: null,
    ...over,
  } as Project;
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const COLUMNS = ['Salesperson', 'Lead', 'Date', 'How they found it', 'Owner', 'Status'];

const accessCard = async () =>
  (await screen.findByText('Access')).closest('[data-slot="card"]') as HTMLElement;

/** The leads grid: wait until the requests have landed (Sales C is a pending secondary lead). */
async function leadsTable() {
  const card = await accessCard();
  await within(card).findByText('Sales C');
  const tables = within(card).getAllByRole('table');
  return { card, tables, table: tables[0] };
}

function headers(table: HTMLElement): string[] {
  return within(table)
    .getAllByRole('columnheader')
    .map((h) => (h.textContent ?? '').trim());
}

function dataRows(table: HTMLElement): HTMLElement[] {
  return within(table)
    .getAllByRole('row')
    .filter((r) => within(r).queryAllByRole('columnheader').length === 0)
    .filter((r) => within(r).queryAllByRole('cell').length > 0);
}

/** One row as { column title: cell text }, aligned on the header row's positions. */
function cellsOf(table: HTMLElement, row: HTMLElement): Record<string, string> {
  const names = headers(table);
  const cells = within(row).getAllByRole('cell');
  const out: Record<string, string> = {};
  names.forEach((name, i) => {
    if (name) out[name] = (cells[i]?.textContent ?? '').trim();
  });
  return out;
}

function rowFor(table: HTMLElement, name: string): HTMLElement {
  const row = dataRows(table).find((r) => cellsOf(table, r).Salesperson?.startsWith(name));
  if (!row) throw new Error(`no row for ${name}`);
  return row;
}

const posts = (part: string) => calls.filter((c) => c.method === 'POST' && c.url.includes(part));
const puts = () => calls.filter((c) => c.method === 'PUT');

beforeEach(() => {
  vi.clearAllMocks();
  calls.length = 0;
  granted = new Set();
});

describe('B1, B2: one leads list on the Access card', () => {
  it('B1 the card holds ONE grid; the old Secondary leads grid is gone', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const { tables } = await leadsTable();
    expect(tables).toHaveLength(1);
    expect(screen.queryByText('Secondary leads')).toBeNull();
  });

  it('B2 columns are Salesperson, Lead, Date, How they found it, Owner, Status (no actions column)', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const { table } = await leadsTable();
    expect(headers(table).filter(Boolean)).toEqual(COLUMNS);
  });

  it('B1 the primary is the first row, then every secondary lead; a join request is not a lead', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const { table } = await leadsTable();
    const rows = dataRows(table).map((r) => cellsOf(table, r));
    expect(rows[0].Salesperson).toBe('Sales A');
    expect(rows[0].Lead).toBe('Primary');
    const secondaries = rows.slice(1);
    expect(secondaries.map((r) => r.Salesperson).sort()).toEqual(['Sales B', 'Sales C', 'Sales D']);
    for (const r of secondaries) expect(r.Lead).toBe('Secondary');
    expect(rows.some((r) => r.Salesperson === 'Sales E')).toBe(false);
  });

  it('B3 primary row: Date is the lead raised date, How they found it is the lead source label', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const { table } = await leadsTable();
    const primary = cellsOf(table, rowFor(table, 'Sales A'));
    expect(primary.Date).toBe('05/10/2026');
    expect(primary['How they found it']).toBe('BCI Asia');
  });

  it('B3 a project with no lead: the primary Date is the registration date', async () => {
    wrap(
      <ProjectAccessPanel
        project={project({ lead_id: null, lead_code: null, lead_created_at: null })}
      />,
    );
    const { table } = await leadsTable();
    expect(cellsOf(table, rowFor(table, 'Sales A')).Date).toBe('07/10/2026');
  });

  it('B2 secondary rows: Date is the request date, How they found it is the note', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const { table } = await leadsTable();
    const c = cellsOf(table, rowFor(table, 'Sales C'));
    expect(c.Date).toBe('20/10/2026');
    expect(c['How they found it']).toBe('Met the architect at the March launch.');
  });

  it('B2 Owner reads Yes only on the current owner row', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const { table } = await leadsTable();
    const owners = Object.fromEntries(
      dataRows(table).map((r) => {
        const c = cellsOf(table, r);
        return [c.Salesperson, c.Owner];
      }),
    );
    expect(owners).toEqual({ 'Sales A': '', 'Sales B': 'Yes', 'Sales C': '', 'Sales D': '' });
  });

  it('B2 Status: Pending for a pending lead, Dismissed for a dismissed one, blank when approved and on the primary', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const { table } = await leadsTable();
    expect(cellsOf(table, rowFor(table, 'Sales C')).Status).toBe('Pending');
    expect(cellsOf(table, rowFor(table, 'Sales D')).Status).toBe('Dismissed');
    expect(cellsOf(table, rowFor(table, 'Sales B')).Status).toBe('');
    expect(cellsOf(table, rowFor(table, 'Sales A')).Status).toBe('');
  });

  it('B1 a current owner who is neither the primary nor a secondary lead gets a row with a blank Lead', async () => {
    wrap(<ProjectAccessPanel project={project({ owner_user_id: 'u-z', owner_name: 'Sales Z' })} />);
    const { table } = await leadsTable();
    const z = cellsOf(table, rowFor(table, 'Sales Z'));
    expect(z.Lead).toBe('');
    expect(z.Owner).toBe('Yes');
    expect(cellsOf(table, rowFor(table, 'Sales B')).Owner).toBe('');
  });

  it('B6 reassigned back to the primary: the primary row reads Owner Yes, still Lead Primary', async () => {
    wrap(<ProjectAccessPanel project={project({ owner_user_id: 'u-a', owner_name: 'Sales A' })} />);
    const { table } = await leadsTable();
    const a = cellsOf(table, rowFor(table, 'Sales A'));
    expect(a.Lead).toBe('Primary');
    expect(a.Owner).toBe('Yes');
    expect(cellsOf(table, rowFor(table, 'Sales B')).Owner).toBe('');
  });

  it('B5 no row carries an action button, even for a manager', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    const { table } = await leadsTable();
    for (const row of dataRows(table)) expect(within(row).queryAllByRole('button')).toHaveLength(0);
  });
});

describe('B5: right-click a row to reassign or dismiss', () => {
  const openMenu = async (name: string) => {
    const { table } = await leadsTable();
    const row = rowFor(table, name);
    fireEvent.contextMenu(within(row).getAllByRole('cell')[0]);
  };

  it('a manager right-clicking a pending row gets Reassign to <name> and Dismiss', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    await openMenu('Sales C');
    expect(await screen.findByRole('menuitem', { name: 'Reassign to Sales C' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Dismiss' })).toBeInTheDocument();
  });

  it('Dismiss on a pending row decides that request with reject', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    await openMenu('Sales C');
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Dismiss' }));
    await waitFor(() => expect(posts('/takeover-requests/r-c/decide')).toHaveLength(1));
    expect(posts('/takeover-requests/r-c/decide')[0].body).toMatchObject({ approve: false });
  });

  it('a dismissed row offers Reassign but not Dismiss', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    await openMenu('Sales D');
    expect(await screen.findByRole('menuitem', { name: 'Reassign to Sales D' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Dismiss' })).toBeNull();
  });

  it('the owner row offers no Reassign item', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    await openMenu('Sales B');
    // Give a menu the chance to open before asserting it did not.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole('menuitem', { name: /Reassign to/ })).toBeNull();
  });

  it('a non-manager gets no Reassign or Dismiss item on any row', async () => {
    granted = new Set(['projects.projects.edit']);
    wrap(<ProjectAccessPanel project={project()} />);
    for (const name of ['Sales A', 'Sales C', 'Sales D']) {
      await openMenu(name);
      await new Promise((r) => setTimeout(r, 50));
      expect(screen.queryByRole('menuitem', { name: /Reassign to/ })).toBeNull();
      expect(screen.queryByRole('menuitem', { name: 'Dismiss' })).toBeNull();
    }
  });

  it('a touch long-press opens no empty menu: not for a non-manager, not on the owner row', async () => {
    const longPress = async (name: string) => {
      const { table } = await leadsTable();
      fireEvent.pointerDown(within(rowFor(table, name)).getAllByRole('cell')[0], {
        pointerType: 'touch',
        button: 0,
      });
      // Past the long-press timer, so a menu that was going to open has opened.
      await new Promise((r) => setTimeout(r, 900));
    };
    granted = new Set(['projects.projects.edit']);
    const first = wrap(<ProjectAccessPanel project={project()} />);
    await longPress('Sales C');
    expect(screen.queryByRole('menu')).toBeNull();
    first.unmount();

    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    await longPress('Sales B');
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('an owner who also holds a secondary-lead row gets no Reassign to themselves on it', async () => {
    granted = new Set(['projects.projects.manage']);
    // Sales A is the primary AND (here) owner; give Sales A a decided secondary-lead row too.
    REQUESTS.push({
      id: 'r-a',
      project_id: 'p1',
      kind: 'dispute',
      status: 'rejected',
      requester_user_id: 'u-a',
      requester_name: 'Sales A',
      reason: 'Claimed it again.',
      created_at: '2026-10-25T02:00:00Z',
    });
    try {
      wrap(<ProjectAccessPanel project={project({ owner_user_id: 'u-a', owner_name: 'Sales A' })} />);
      const { table } = await leadsTable();
      const secondRow = dataRows(table).find(
        (r) => cellsOf(table, r).Salesperson === 'Sales A' && cellsOf(table, r).Lead === 'Secondary',
      )!;
      fireEvent.contextMenu(within(secondRow).getAllByRole('cell')[0]);
      await new Promise((r) => setTimeout(r, 50));
      expect(screen.queryByRole('menuitem', { name: /Reassign to/ })).toBeNull();
    } finally {
      REQUESTS.pop();
    }
  });

  it('Reassign to the primary opens the reassign dialog with them preselected; submitting moves the owner', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    await openMenu('Sales A');
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Reassign to Sales A' }));
    const dialog = await screen.findByRole('dialog');
    const select = within(dialog).getByLabelText('Salesperson') as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe('u-a'));
    fireEvent.click(within(dialog).getByRole('button', { name: /^Reassign$/ }));
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(puts()[0].body).toMatchObject({ owner_user_id: 'u-a' });
    expect(posts('/decide')).toHaveLength(0);
  });

  it('Reassign to a pending secondary lead preselects them and approves that request', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    await openMenu('Sales C');
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Reassign to Sales C' }));
    const dialog = await screen.findByRole('dialog');
    const select = within(dialog).getByLabelText('Salesperson') as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe('u-c'));
    fireEvent.click(within(dialog).getByRole('button', { name: /^Reassign$/ }));
    await waitFor(() => expect(posts('/takeover-requests/r-c/decide')).toHaveLength(1));
    expect(posts('/takeover-requests/r-c/decide')[0].body).toMatchObject({ approve: true });
    expect(puts()).toHaveLength(0);
  });
});
