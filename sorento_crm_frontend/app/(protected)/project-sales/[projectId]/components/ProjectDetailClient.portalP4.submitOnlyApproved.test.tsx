/**
 * PORTAL-P4-REQUESTS owner ruling a54382059 (29 Oct): a submit-only user (submit grant, no
 * projects.projects.edit) is narrowed only on UNAPPROVED registrations. On a project with
 * approval_state null or 'approved' that the server says they can edit, they see the stage
 * moves, the gear with Edit, and no Read only badge. Pending stays read only; a draft keeps
 * its draft actions.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
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

const GRAPH_H = vi.hoisted(() => {
const rung = (id: string, key: string, label: string, order: number, terminal = false) => ({
  id, entity_type: 'project', scope_id: null, key, label, category: null, color_hex: null,
  description: null, sort_order: order, is_initial: false, is_terminal: terminal, is_active: true,
  is_archived: false, is_default: false, is_system: false,
});
const edge = (id: string, from: string, to: string, label: string, order: number) => ({
  id, entity_type: 'project', scope_id: null, from_status_id: from, to_status_id: to, label,
  sort_order: order, trigger_mode: 'manual', conditions_json: null,
});
const GRAPH = {
  entity_type: 'project', requested_scope_id: null, resolved_scope_id: null, is_fork: false,
  statuses: [
    rung('s-neg', 'final_negotiation', 'Final Negotiation', 5),
    rung('s-spon', 'sponsorship_form', 'Sponsorship Form', 6),
    rung('s-po', 'po_received', 'PO Received', 7, true),
    rung('s-lost', 'lost', 'Lost', 8, true),
  ],
  transitions: [
    edge('t1', 's-neg', 's-spon', 'Sponsorship', 0),
    edge('t2', 's-neg', 's-po', 'PO received', 1),
    edge('t3', 's-neg', 's-lost', 'Mark lost', 2),
  ],
};
  return GRAPH;
});
const approve = vi.fn();

const spies = vi.hoisted(() => ({ collaborators: vi.fn(), takeover: vi.fn(), changeStatus: vi.fn() }));
const changeStatus = spies.changeStatus;
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
  useChangeProjectStatus: () => ({ mutate: changeStatus, isPending: false }),
  useDeleteProject: () => ({ mutateAsync: vi.fn() }),
  useUpdateProject: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useCollaborators: (...a: unknown[]) => {
    spies.collaborators(...a);
    return { data: [], isLoading: false };
  },
  useTakeoverRequests: (...a: unknown[]) => {
    spies.takeover(...a);
    return { data: [] };
  },
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
  useProjectStatusGraph: () => ({ data: GRAPH_H }),
}));


import { ProjectDetailClient } from './ProjectDetailClient';

const SUBMIT_ONLY = ['projects.projects.view_own', 'projects.registrations.submit'];

function fixture(over: Partial<Project> = {}): Project {
  return {
    id: 'p1', project_code: 'PRJ-000001', title: 'Menara CONTOH', outcome: 'open',
    is_critical: false, brands: [], brand_ids: [], next_action_overdue: false, stale_level: 0,
    is_unattended: false, open_task_count: 0, can_edit: true, status_id: 's-neg',
    status_key: 'final_negotiation', status_label: 'Final Negotiation', approval_state: null,
    reject_reason: null, submitted_at: null, decided_at: null, developer_party_id: null,
    developer_name: 'SP Setia CONTOH', possible_duplicates: [], registration: null, ...over,
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
const header = () => screen.getByTestId('project-header-actions');
function openGear() {
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Project actions' }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  granted = new Set(SUBMIT_ONLY);
});

describe.each([
  ['staff project (approval_state null)', null],
  ['approved registration', 'approved'],
])('submit-only owner of a %s', (_name, state) => {
  beforeEach(() => {
    projectFixture = fixture({ approval_state: state } as never);
  });

  it('has no Read only badge', () => {
    renderDetail();
    expect(screen.queryByText('Read only')).toBeNull();
  });

  it('sees the forward stage move, which opens the sponsorship form after it lands', () => {
    changeStatus.mockImplementation(
      (_vars: unknown, options?: { onSuccess?: () => void }) => options?.onSuccess?.(),
    );
    renderDetail();
    fireEvent.click(within(header()).getByRole('button', { name: 'Sponsorship' }));
    expect(changeStatus).toHaveBeenCalledWith(
      { projectId: 'p1', toStatusId: 's-spon' },
      expect.anything(),
    );
    expect(push).toHaveBeenCalledWith('/procurement-management/sponsorship-forms/new?project_id=p1');
  });

  it('has the gear with Edit project and the side moves', async () => {
    renderDetail();
    openGear();
    const edit = await screen.findByRole('menuitem', { name: /Edit project/ });
    expect(edit).toBeInTheDocument();
    const items = screen.getAllByRole('menuitem').map((el) => (el.textContent || '').trim());
    expect(items).toContain('Mark lost');
  });
});

describe('pins: unapproved registrations of a submit-only owner stay narrowed (green by design)', () => {
  it('pending: Read only, no stage moves, no gear', () => {
    projectFixture = fixture({
      approval_state: 'pending', can_edit: false, status_id: null, status_key: null,
    } as never);
    renderDetail();
    expect(screen.getByText('Read only')).toBeInTheDocument();
    expect(within(header()).queryByRole('button', { name: 'Sponsorship' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Project actions' })).toBeNull();
    expect(within(header()).queryByRole('button', { name: 'Edit' })).toBeNull();
  });

  it('draft: Edit and Submit for approval', () => {
    projectFixture = fixture({ approval_state: 'draft', status_id: null, status_key: null } as never);
    renderDetail();
    expect(within(header()).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(within(header()).getByRole('button', { name: 'Submit for approval' })).toBeInTheDocument();
  });
});
