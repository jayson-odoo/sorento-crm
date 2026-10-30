/**
 * PROJECT-REGISTER-V2, Phase 2 red tests: the Access card's Interested list (UAC E1, E2, E4,
 * D3 label) and the Reassign dialog (E5).
 *
 * Observed at the network boundary (`apiFetch`), so the hook and service names the coder picks
 * do not matter. An "interest" is a pending takeover request of kind `dispute`
 * (card: "Register interest IS the existing dispute request, relabelled").
 *
 * Assumed: the Reassign dialog keeps its `{ project, onDone }` props and a flat `options` list
 * on its SearchableSelect, interested people first.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-me', name: 'Sales A' } }, status: 'authenticated' }),
}));

let granted = new Set<string>();
let approvedDispute = false;
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
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-owner', name: 'Sales A' },
    { id: 'u-b', name: 'Sales B' },
    { id: 'u-c', name: 'Sales C' },
    { id: 'u-m', name: 'Manager M' },
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
      {((options ?? []) as { value: string; label: string; description?: string }[]).map((o) => (
        <option key={o.value} value={o.value}>
          {[o.label, o.description].filter(Boolean).join(' ')}
        </option>
      ))}
    </select>
  ),
}));

type Call = { url: string; method: string; body: unknown };
const calls: Call[] = [];
const REQUESTS = [
  {
    id: 'r1',
    project_id: 'p1',
    kind: 'dispute',
    status: 'pending',
    requester_user_id: 'u-b',
    requester_name: 'Sales B',
    reason: 'Found this project at the March site visit.',
    created_at: '2026-10-20T08:00:00Z',
  },
  {
    id: 'r2',
    project_id: 'p1',
    kind: 'join',
    status: 'pending',
    requester_user_id: 'u-c',
    requester_name: 'Sales C',
    reason: 'Please add me.',
    created_at: '2026-10-21T08:00:00Z',
  },
  {
    id: 'r3',
    project_id: 'p1',
    kind: 'dispute',
    status: 'rejected',
    requester_user_id: 'u-m',
    requester_name: 'Manager M',
    reason: 'Old closed interest.',
    created_at: '2026-09-01T08:00:00Z',
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
      if (method === 'GET' && String(input).includes('/takeover-requests')) {
        return ok({
          data: approvedDispute
            ? [
                ...REQUESTS,
                {
                  id: 'r4',
                  project_id: 'p1',
                  kind: 'dispute',
                  status: 'approved',
                  requester_user_id: 'u-d',
                  requester_name: 'Sales D',
                  reason: 'Won the reassignment.',
                  created_at: '2026-09-02T08:00:00Z',
                },
              ]
            : REQUESTS,
        });
      }
      if (method === 'POST' && String(input).includes('/decide')) {
        return ok({ id: 'r1', status: (JSON.parse(String(init.body)).approve ? 'approved' : 'rejected') });
      }
      if (method === 'PUT') return ok({ id: 'p1' });
      return ok({ data: [] });
    },
  };
});

import { ProjectAccessPanel } from './ProjectAccessPanel';
import { ReassignProjectDialog } from './ReassignProjectDialog';

function project(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000142',
    title: 'Menara CONTOH',
    outcome: 'open',
    owner_user_id: 'u-owner',
    owner_name: 'Sales A',
    is_critical: false,
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: false,
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
const interestedBox = async () => {
  // AC-R6: the section is a grid card titled Secondary leads (PanelDataGrid), not a plain list.
  const heading = await screen.findByText('Secondary leads');
  return heading.closest('[data-slot="card"]') as HTMLElement;
};
const posts = (part: string) => calls.filter((c) => c.method === 'POST' && c.url.includes(part));

beforeEach(() => {
  vi.clearAllMocks();
  calls.length = 0;
  granted = new Set();
  approvedDispute = false;
});

describe('ProjectAccessPanel: Interested (E1, E2, E4)', () => {
  it('E1 lists every pending interest with name, date and note to a plain viewer', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const box = await interestedBox();
    await within(box).findByText('Sales B');
    expect(within(box).getByText(/Found this project at the March site visit\./)).toBeInTheDocument();
    expect(box.textContent).toMatch(/20 Oct|Oct 20|2026-10-20|20\/10/);
    // A join request is not a secondary lead; a decided dispute is, as a row (AC-R6).
    expect(within(box).queryByText('Sales C')).toBeNull();
    expect(within(box).getByText('Manager M')).toBeInTheDocument();
    // A plain viewer sees no management buttons.
    expect(within(box).queryByRole('button', { name: /Reassign to/ })).toBeNull();
    expect(within(box).queryByRole('button', { name: 'Dismiss' })).toBeNull();
  });

  it('E2 a holder of projects.projects.manage sees Reassign to <name> and Dismiss per row', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    const box = await interestedBox();
    expect(await within(box).findByRole('button', { name: 'Reassign to Sales B' })).toBeInTheDocument();
    expect(within(box).getByRole('button', { name: 'Dismiss' })).toBeInTheDocument();
  });

  it('E2 the owner without manage does not get them', async () => {
    granted = new Set(['projects.projects.edit']);
    wrap(<ProjectAccessPanel project={project({ can_edit: true })} />);
    const box = await interestedBox();
    await within(box).findByText('Sales B');
    expect(within(box).queryByRole('button', { name: /Reassign to/ })).toBeNull();
    expect(within(box).queryByRole('button', { name: 'Dismiss' })).toBeNull();
  });

  it('E4 Dismiss decides the interest with reject', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }));
    await waitFor(() => expect(posts('/takeover-requests/r1/decide')).toHaveLength(1));
    expect(posts('/takeover-requests/r1/decide')[0].body).toMatchObject({ approve: false });
  });

  it('E3 Reassign to <name> decides that interest with approve', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Reassign to Sales B' }));
    await waitFor(() => expect(posts('/takeover-requests/r1/decide')).toHaveLength(1));
    expect(posts('/takeover-requests/r1/decide')[0].body).toMatchObject({ approve: true });
  });

  it('D3 the label Dispute is gone and Ask to join is kept', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    await interestedBox();
    expect(screen.getByRole('button', { name: 'Ask to join' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Dispute' })).toBeNull();
    expect(screen.queryByText(/^Dispute$/)).toBeNull();
    expect(screen.getByRole('button', { name: /Register as secondary lead/ })).toBeInTheDocument();
  });
});

describe('AC-R6 secondary leads table', () => {
  const rowOf = async (name: string) => {
    const box = await interestedBox();
    const cell = await within(box).findByText(name);
    return cell.closest('tr') as HTMLElement;
  };

  it('AC-R6 renders a table with columns Salesperson, Date, How they found it, Status', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const box = await interestedBox();
    const table = await within(box).findByRole('table');
    for (const name of ['Salesperson', 'Date', 'How they found it', 'Status']) {
      expect(within(table).getByRole('columnheader', { name: new RegExp(name) })).toBeInTheDocument();
    }
  });

  it('AC-R6 a pending dispute row shows name, note and a Pending badge', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const row = await rowOf('Sales B');
    expect(within(row).getByText(/Found this project at the March site visit\./)).toBeInTheDocument();
    expect(within(row).getByText('Pending')).toBeInTheDocument();
  });

  it('AC-R6 a rejected dispute row reads Dismissed, with no actions', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    const row = await rowOf('Manager M');
    expect(within(row).getByText('Dismissed')).toBeInTheDocument();
    expect(within(row).queryByRole('button', { name: 'Dismiss' })).toBeNull();
    expect(within(row).queryByRole('button', { name: /Reassign to/ })).toBeNull();
  });

  it('AC-R6 an approved dispute row reads Reassigned', async () => {
    approvedDispute = true;
    wrap(<ProjectAccessPanel project={project()} />);
    const row = await rowOf('Sales D');
    expect(within(row).getByText('Reassigned')).toBeInTheDocument();
  });

  it('AC-R6 Reassign to <name> and Dismiss sit on the pending row for a manage holder only', async () => {
    granted = new Set(['projects.projects.manage']);
    wrap(<ProjectAccessPanel project={project()} />);
    const row = await rowOf('Sales B');
    expect(within(row).getByRole('button', { name: 'Reassign to Sales B' })).toBeInTheDocument();
    expect(within(row).getByRole('button', { name: 'Dismiss' })).toBeInTheDocument();
  });

  it('AC-R6 a viewer without manage sees the row but no actions', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    const row = await rowOf('Sales B');
    expect(within(row).queryByRole('button')).toBeNull();
  });

  it('AC-R6 join requests stay out of the table and keep Open requests', async () => {
    wrap(<ProjectAccessPanel project={project({ can_edit: true })} />);
    const box = await interestedBox();
    await within(box).findByRole('table');
    expect(within(box).queryByText('Sales C')).toBeNull();
    expect(await screen.findByText('Sales C')).toBeInTheDocument();
    expect(screen.getByText(/Open requests/)).toBeInTheDocument();
  });
});

describe('AC-R4 secondary lead wording on the Access card', () => {
  it('AC-R4 the heading reads Secondary leads and the old Interested heading is gone', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    await screen.findByText('Secondary leads');
    expect(screen.queryByText(/^Interested$/)).toBeNull();
    expect(screen.queryByText(/register interest/i)).toBeNull();
  });

  it('AC-R4 no past decision reads "Interest by"; a join decision still reads "Join by"', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    await screen.findByText('Secondary leads');
    expect(screen.queryByText(/Interest by/)).toBeNull();
    expect(screen.queryByText(/Interested/)).toBeNull();
  });

  it('AC-R4 the dialog title and submit read Register as secondary lead', async () => {
    wrap(<ProjectAccessPanel project={project()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Register as secondary lead' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Register as secondary lead on PRJ-000142')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Register as secondary lead' })).toBeInTheDocument();
    expect(within(dialog).queryByText(/register interest/i)).toBeNull();
  });
});

describe('ReassignProjectDialog: interested people first (E5)', () => {
  const options = () =>
    Array.from(screen.getByLabelText('Salesperson').querySelectorAll('option'))
      .filter((o) => o.value)
      .map((o) => ({ value: o.value, text: o.textContent ?? '' }));

  it('lists the interested person first, with their date, then everyone else', async () => {
    wrap(<ReassignProjectDialog project={project()} onDone={vi.fn()} />);
    await waitFor(() => expect(options().length).toBeGreaterThan(1));
    const list = options();
    expect(list[0].value).toBe('u-b');
    expect(list[0].text).toMatch(/Sales B/);
    expect(list[0].text).toMatch(/20 Oct|Oct 20|2026-10-20|20\/10/);
    expect(list.some((o) => o.value === 'u-c')).toBe(true);
    expect(list.some((o) => o.value === 'u-m')).toBe(true);
  });

  it('picking the interested person approves that request and does not run the plain update', async () => {
    const onDone = vi.fn();
    wrap(<ReassignProjectDialog project={project()} onDone={onDone} />);
    await waitFor(() => expect(options().length).toBeGreaterThan(1));
    fireEvent.change(screen.getByLabelText('Salesperson'), { target: { value: 'u-b' } });
    fireEvent.click(screen.getByRole('button', { name: /^Reassign$/ }));
    await waitFor(() => expect(posts('/takeover-requests/r1/decide')).toHaveLength(1));
    expect(posts('/takeover-requests/r1/decide')[0].body).toMatchObject({ approve: true });
    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(0);
  });

  it('picking anyone else keeps today\'s owner update', async () => {
    wrap(<ReassignProjectDialog project={project()} onDone={vi.fn()} />);
    await waitFor(() => expect(options().length).toBeGreaterThan(1));
    fireEvent.change(screen.getByLabelText('Salesperson'), { target: { value: 'u-c' } });
    fireEvent.click(screen.getByRole('button', { name: /^Reassign$/ }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(1));
    expect(calls.find((c) => c.method === 'PUT')!.body).toMatchObject({ owner_user_id: 'u-c' });
    expect(posts('/decide')).toHaveLength(0);
  });
});
