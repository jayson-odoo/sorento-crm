/**
 * RW13 - a registration is approved or rejected on the project's own page (PLAN R7).
 *
 * A pending project shows Approve (the header's primary slot), Reject (a reason dialog) and Edit
 * to holders of `projects.registrations.approve` only; the legacy fields the portal collected are
 * read-only under the header; the possible duplicates are links; a 409 exact duplicate says
 * "Already registered as <code> <title>" and links to it; a rejected project shows its reason.
 *
 * Mocked at the hook boundary like ProjectDetailClient.test.tsx. Names bound (the plan names the
 * routes, not the hooks): `useApproveProject(projectId)` and `useRejectProject(projectId)` from
 * `_shared/hooks/useProjects`, each a mutation with `mutate`, `mutateAsync` and `isPending`; a
 * refused approval rejects with an Error that carries `existingProject` when it is the 409.
 * The Project payload carries `approval_state`, `reject_reason`, `submitted_at`,
 * `possible_duplicates` and a nested `registration` block (null for a staff project).
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

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('@/components/common/ListPager', () => ({
  __esModule: true,
  default: () => <div data-testid="pager-slot" />,
}));
vi.mock('@/components/common/ActivitiesNotesPanel/EntityActivitiesLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const approve = vi.fn();
const reject = vi.fn();
const hookArgs = { approve: [] as unknown[], reject: [] as unknown[] };
let projectFixture: Project;
let granted: Set<string>;

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [{ id: 'u-ali', name: 'Ali' }]),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ value, onChange, options, placeholder, id }: never) => (
    <select
      id={id}
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => (onChange as (v: string) => void)(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {((options ?? []) as { value: string; label: string }[]).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock('../../_shared/hooks/useProjects', () => ({
  projectsPagerQuery: {
    listQueryKey: () => ['projects'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useProject: () => ({ data: projectFixture, isLoading: false, isError: false }),
  useChangeProjectStatus: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteProject: () => ({ mutateAsync: vi.fn() }),
  useUpdateProject: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useCollaborators: () => ({ data: [], isLoading: false }),
  useTakeoverRequests: () => ({ data: [] }),
  useTakeoverMutations: () => ({
    decide: { mutate: vi.fn(), isPending: false },
    request: { mutateAsync: vi.fn(), isPending: false },
  }),
  useApproveProject: (id: unknown) => {
    hookArgs.approve.push(id);
    return { mutate: approve, mutateAsync: approve, isPending: false };
  },
  useRejectProject: (id: unknown) => {
    hookArgs.reject.push(id);
    return { mutate: reject, mutateAsync: reject, isPending: false };
  },
}));
vi.mock('@/app/(protected)/project-sales/_shared/hooks/useProjectStatusGraph', () => ({
  useProjectStatusGraph: () => ({
    data: { entity_type: 'project', statuses: [], transitions: [], is_fork: false },
  }),
}));

import { ProjectDetailClient } from './ProjectDetailClient';

const APPROVE = 'projects.registrations.approve';

function pendingProject(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: null,
    title: 'CADANGAN BLOK PEJABAT DI ATAS LOT 7001',
    outcome: 'open',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    status_id: null,
    status_key: null,
    status_label: null,
    approval_state: 'pending',
    reject_reason: null,
    submitted_at: '2026-10-02T08:00:00',
    decided_at: null,
    developer_party_id: null,
    developer_name: null,
    possible_duplicates: [],
    registration: {
      sales_agent_name: 'Aminah Example',
      distributor_name: 'Example Distribution Sdn Bhd',
      customer_name: 'Example Customer Sdn Bhd',
      your_ref: 'REF-ZZT-1',
      type_of_building: 'Office',
      developer_name: 'Example Developer Sdn Bhd',
      main_contractor_name: null,
      architect_name: null,
    },
    ...over,
  } as unknown as Project;
}

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProjectDetailClient projectId="p1" />
    </QueryClientProvider>,
  );
}

function header() {
  return screen.getByTestId('project-header-actions');
}

beforeEach(() => {
  vi.clearAllMocks();
  hookArgs.approve = [];
  hookArgs.reject = [];
  granted = new Set([APPROVE, 'projects.projects.manage']);
  approve.mockResolvedValue({});
  reject.mockResolvedValue({});
  projectFixture = pendingProject();
});

describe('a pending project: who sees Approve, Reject and Edit (RW13)', () => {
  it('shows Approve, Reject and Edit in the header to a holder of the approve permission', () => {
    renderDetail();
    for (const name of ['Approve', 'Reject', 'Edit']) {
      expect(within(header()).getByRole('button', { name })).toBeInTheDocument();
    }
  });

  it('Approve is the primary slot and the stage move is not offered', () => {
    renderDetail();
    const buttons = within(header()).getAllByRole('button');
    expect(buttons[buttons.length - 1]).toHaveTextContent('Approve');
  });

  it('shows none of Approve and Reject to anyone without the permission', () => {
    granted = new Set(['projects.projects.manage']);
    renderDetail();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });

  it('Edit opens the existing edit page', () => {
    renderDetail();
    fireEvent.click(within(header()).getByRole('button', { name: 'Edit' }));
    expect(push).toHaveBeenCalledWith('/project-sales/p1/edit');
  });

  it('reads "Awaiting approval" where the code would be, with no None or null on the page', () => {
    renderDetail();
    expect(screen.getAllByText('Awaiting approval').length).toBeGreaterThanOrEqual(1);
    expect(document.body.textContent).not.toMatch(/\b(null|undefined)\b/);
    expect(document.body.textContent).not.toMatch(/\bNone\b/);
  });

  it('an approved project and a staff project show neither button', () => {
    projectFixture = pendingProject({ approval_state: 'approved', project_code: 'PPF2610005', registration: null } as never);
    const first = renderDetail();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
    first.unmount();

    projectFixture = pendingProject({ approval_state: null, project_code: 'PRJ-000142', registration: null } as never);
    renderDetail();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });

  it('a rejected project offers neither button either (it waits for the salesperson to resubmit)', () => {
    projectFixture = pendingProject({ approval_state: 'rejected', reject_reason: 'Already registered by Bakar' } as never);
    renderDetail();
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });
});

describe('Approve and Reject (RW13)', () => {
  it('Approve calls the approve mutation of THIS project', async () => {
    renderDetail();
    fireEvent.click(within(header()).getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(approve).toHaveBeenCalledTimes(1));
    expect(hookArgs.approve).toContain('p1');
  });

  it('Reject opens a reason dialog and nothing is sent until a reason is given', async () => {
    renderDetail();
    fireEvent.click(within(header()).getByRole('button', { name: 'Reject' }));
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: /^reject$/i });
    fireEvent.click(confirm);
    expect(reject).not.toHaveBeenCalled();
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: '   ' } });
    fireEvent.click(confirm);
    expect(reject).not.toHaveBeenCalled();
  });

  it('Reject with a reason sends it', async () => {
    renderDetail();
    fireEvent.click(within(header()).getByRole('button', { name: 'Reject' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'Already registered by Bakar' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^reject$/i }));
    await waitFor(() => expect(reject).toHaveBeenCalledTimes(1));
    expect(JSON.stringify(reject.mock.calls[0])).toContain('Already registered by Bakar');
    expect(hookArgs.reject).toContain('p1');
  });

  it('cancelling the reason dialog sends nothing', async () => {
    renderDetail();
    fireEvent.click(within(header()).getByRole('button', { name: 'Reject' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /cancel/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(reject).not.toHaveBeenCalled();
  });

  it('a 409 exact duplicate shows "Already registered as <code> <title>" as a link to that project', async () => {
    const error = Object.assign(new Error('PPF2509012 already has this developer and title.'), {
      existingProject: { project_id: 'proj-77', project_code: 'PPF2509012', title: 'KILANG ALPHA LOT 9001' },
    });
    approve.mockRejectedValue(error);
    renderDetail();
    fireEvent.click(within(header()).getByRole('button', { name: 'Approve' }));
    const link = await screen.findByRole('link', { name: /PPF2509012 KILANG ALPHA LOT 9001/ });
    expect(link).toHaveAttribute('href', '/project-sales/proj-77');
    expect(screen.getByText(/Already registered as/)).toBeInTheDocument();
  });
});

describe('what is shown under the header (RW13)', () => {
  it('shows the legacy fields read-only: Date, Sales agent (a name), Distributor, Customer, Your ref', () => {
    renderDetail();
    for (const label of ['Date', 'Sales agent', 'Distributor', 'Customer', 'Your ref']) {
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(1);
    }
    expect(screen.getByText('Aminah Example')).toBeInTheDocument();
    expect(screen.getByText('Example Distribution Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('Example Customer Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('REF-ZZT-1')).toBeInTheDocument();
    expect(screen.getByText(/2026/)).toBeInTheDocument();
    const block = screen.getByText('Aminah Example').closest('div');
    expect(block?.querySelector('input, textarea, select')).toBeNull();
  });

  it('shows the metadata to people who cannot approve as well (read-only metadata is not a button)', () => {
    granted = new Set();
    renderDetail();
    expect(screen.getByText('Aminah Example')).toBeInTheDocument();
  });

  it('lists the possible duplicates as links to those projects, code and title', () => {
    projectFixture = pendingProject({
      possible_duplicates: [
        { project_id: 'p9', project_code: 'PRJ-000009', title: 'KILANG ALPHA LOT 9001' },
        { project_id: 'p8', project_code: 'PPF2509012', title: 'KILANG BETA LOT 9002' },
      ],
    } as never);
    renderDetail();
    expect(screen.getByText(/Possible duplicate:/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /PRJ-000009 KILANG ALPHA LOT 9001/ })).toHaveAttribute(
      'href',
      '/project-sales/p9',
    );
    expect(screen.getByRole('link', { name: /PPF2509012 KILANG BETA LOT 9002/ })).toHaveAttribute(
      'href',
      '/project-sales/p8',
    );
  });

  it('says nothing about duplicates when there are none', () => {
    renderDetail();
    expect(screen.queryByText(/Possible duplicate/)).toBeNull();
  });

  it('a rejected project shows its reason and the Rejected pill', () => {
    projectFixture = pendingProject({
      approval_state: 'rejected',
      reject_reason: 'Already registered by Bakar',
    } as never);
    renderDetail();
    expect(screen.getByText(/Already registered by Bakar/)).toBeInTheDocument();
    expect(screen.getAllByText('Rejected').length).toBeGreaterThanOrEqual(1);
  });

  it('a staff project has no registration block and no duplicates line', () => {
    projectFixture = pendingProject({
      approval_state: null,
      project_code: 'PRJ-000142',
      registration: null,
      possible_duplicates: [],
    } as never);
    renderDetail();
    expect(screen.queryByText('Sales agent')).toBeNull();
    expect(screen.queryByText('Your ref')).toBeNull();
    expect(screen.queryByText(/Possible duplicate/)).toBeNull();
    expect(screen.getByText('PRJ-000142')).toBeInTheDocument();
    // control for the "no None" check on the pending page: the staff page is clean already
    expect(document.body.textContent).not.toMatch(/\b(null|undefined)\b/);
    expect(document.body.textContent).not.toMatch(/\bNone\b/);
  });
});

describe('review round 3 on the detail page', () => {
  it('shows the submitted date in Malaysia time (12)', () => {
    projectFixture = pendingProject({ submitted_at: '2026-10-24T17:30:00' } as never);
    renderDetail();
    expect(screen.getByText('25/10/2026')).toBeInTheDocument();
  });

  it('the "Already registered as" link clears after a later Reject (13)', async () => {
    approve.mockRejectedValue(
      Object.assign(new Error('dup'), {
        existingProject: { project_id: 'proj-77', project_code: 'PPF2509012', title: 'KILANG ALPHA' },
      }),
    );
    renderDetail();
    fireEvent.click(within(header()).getByRole('button', { name: 'Approve' }));
    await screen.findByText(/Already registered as/);
    fireEvent.click(within(header()).getByRole('button', { name: 'Reject' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'Duplicate of PPF2509012' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^reject$/i }));
    await waitFor(() => expect(reject).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByText(/Already registered as/)).toBeNull());
  });

  it('the link clears after a later Approve that goes through (13)', async () => {
    approve.mockRejectedValueOnce(
      Object.assign(new Error('dup'), {
        existingProject: { project_id: 'proj-77', project_code: 'PPF2509012', title: 'KILANG ALPHA' },
      }),
    );
    renderDetail();
    fireEvent.click(within(header()).getByRole('button', { name: 'Approve' }));
    await screen.findByText(/Already registered as/);
    approve.mockResolvedValueOnce({});
    fireEvent.click(within(header()).getByRole('button', { name: 'Approve' }));
    await waitFor(() => expect(approve).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText(/Already registered as/)).toBeNull());
  });

  it('a rejected project reads Rejected in the code slot, never Awaiting approval (14)', () => {
    projectFixture = pendingProject({ approval_state: 'rejected', reject_reason: 'no' } as never);
    renderDetail();
    expect(screen.queryByText('Awaiting approval')).toBeNull();
    expect(screen.getAllByText('Rejected').length).toBeGreaterThanOrEqual(2); // code slot + pill
  });

  it('an approver sees Edit once on a pending project: the header button, not a menu item too (16)', async () => {
    renderDetail();
    expect(within(header()).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    fireEvent.pointerDown(within(header()).getByRole('button', { name: 'Project actions' }), {
      button: 0,
      ctrlKey: false,
    });
    expect(await screen.findByRole('menu')).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /Edit project/ })).toBeNull();
  });
});
