/**
 * The project header: one status, one action.
 *
 * The client's words: "why is there a status on the top right that I can change, we
 * suppose to have 1 call to action that is the most obvious for the form". So these pin
 * three things -- the stage reads as a pill and cannot be set from the header, the header
 * offers exactly ONE action, and Delete has moved into the overflow without losing its
 * confirmation.
 *
 * The moves offered come from the status graph, never from a list written here: a funnel
 * reshaped in the status graph editor has to change the button, and an edge the server
 * would reject must never be offered.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';
import type { StatusGraph } from '@/app/(protected)/system-management/status-graphs/types/statusGraph.types';

// ── jsdom polyfills Radix's dropdown / dialog need ───────────────────────────
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

vi.mock('@/components/common/ActivitiesNotesPanel/EntityActivitiesLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const changeStatus = vi.fn();
const deleteProject = vi.fn();
let projectFixture: Project;

vi.mock('../../_shared/hooks/useProjects', () => ({
  useProject: () => ({ data: projectFixture, isLoading: false, isError: false }),
  useChangeProjectStatus: () => ({ mutate: changeStatus, isPending: false }),
  useDeleteProject: () => ({ mutateAsync: deleteProject }),
  useUpdateProject: () => ({ mutate: vi.fn(), isPending: false }),
  useCollaborators: () => ({ data: [], isLoading: false }),
  useTakeoverRequests: () => ({ data: [] }),
  useTakeoverMutations: () => ({
    decide: { mutate: vi.fn(), isPending: false },
    request: { mutateAsync: vi.fn(), isPending: false },
  }),
}));

let graphFixture: StatusGraph;
vi.mock('@/app/(protected)/system-management/status-graphs/hooks/useStatusGraphs', () => ({
  useStatusGraph: () => ({ data: graphFixture }),
}));

import { ProjectDetailClient } from './ProjectDetailClient';

function status(
  id: string,
  key: string,
  label: string,
  sortOrder: number,
  overrides: Record<string, unknown> = {},
) {
  return {
    id,
    entity_type: 'project',
    scope_id: null,
    key,
    label,
    category: null,
    color_hex: null,
    description: null,
    sort_order: sortOrder,
    is_initial: false,
    is_terminal: false,
    is_active: true,
    is_archived: false,
    is_default: false,
    is_system: false,
    ...overrides,
  } as StatusGraph['statuses'][number];
}

function transition(
  id: string,
  from: string,
  to: string,
  label: string,
  sortOrder: number,
  overrides: Record<string, unknown> = {},
) {
  return {
    id,
    entity_type: 'project',
    scope_id: null,
    from_status_id: from,
    to_status_id: to,
    label,
    sort_order: sortOrder,
    trigger_mode: 'manual',
    conditions_json: null,
    ...overrides,
  } as StatusGraph['transitions'][number];
}

/** The seeded funnel, trimmed to the rungs these tests stand on. */
function graph(overrides: Partial<StatusGraph> = {}): StatusGraph {
  return {
    entity_type: 'project',
    requested_scope_id: null,
    resolved_scope_id: null,
    is_fork: false,
    statuses: [
      status('s-specified', 'specified', 'Specified', 2),
      status('s-quoted', 'quoted', 'Quoted', 3),
      status('s-tendering', 'tendering', 'Tendering', 4),
      status('s-po', 'po_received', 'PO Received', 5, { is_terminal: true }),
      status('s-lost', 'lost', 'Lost', 6, { is_terminal: true }),
    ],
    transitions: [
      transition('t-1', 's-quoted', 's-tendering', 'Tendering', 0),
      transition('t-2', 's-quoted', 's-po', 'PO received', 1),
      transition('t-3', 's-quoted', 's-specified', 'Re-specify', 2),
    ],
    ...overrides,
  };
}

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Test',
    outcome: 'open',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    status_id: 's-quoted',
    status_key: 'quoted',
    status_label: 'Quoted',
    ...overrides,
  } as Project;
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

function openOverflow() {
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Project actions' }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  projectFixture = project();
  graphFixture = graph();
});

describe('the project header', () => {
  it('states the stage as a pill and offers no way to set it directly', () => {
    renderDetail();

    expect(screen.getByText('Quoted')).toBeInTheDocument();
    // The stage dropdown is gone: SearchableSelect exposes role=combobox.
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('carries exactly one action, with everything else behind the overflow', () => {
    renderDetail();

    const actions = within(screen.getByTestId('project-header-actions')).getAllByRole(
      'button',
    );
    expect(actions).toHaveLength(2);
    // The forward move is NAMED, never a generic "Move stage" that opens a menu.
    expect(actions[0]).toHaveTextContent('Tendering');
    expect(actions[1]).toHaveAttribute('aria-label', 'Project actions');
  });

  it('names the move outright when the graph allows only one, and fires it', () => {
    graphFixture = graph({
      transitions: [transition('t-2', 's-quoted', 's-po', 'PO received', 1)],
    });

    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: 'PO received' }));

    expect(changeStatus).toHaveBeenCalledWith({
      projectId: 'p1',
      toStatusId: 's-po',
    });
  });

  it('fires the forward move directly, with no menu to choose from', () => {
    // Several edges are legal, but the header does not ask. Choosing between four is what
    // made the commonest action a decision, and put "Mark lost" beside advancing.
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: 'Tendering' }));

    expect(changeStatus).toHaveBeenCalledWith({
      projectId: 'p1',
      toStatusId: 's-tendering',
    });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('puts an exit behind the gear rather than in the header', async () => {
    graphFixture = graph({
      statuses: [
        status('s-quoted', 'quoted', 'Quoted', 0),
        status('s-po', 'po_received', 'PO Received', 1),
        status('s-lost', 'lost', 'Lost', 2, { is_terminal: true }),
      ],
      transitions: [
        transition('t-2', 's-quoted', 's-po', 'PO received', 1),
        transition('t-4', 's-quoted', 's-lost', 'Mark lost', 2),
      ],
    });

    renderDetail();

    const header = within(screen.getByTestId('project-header-actions'));
    expect(header.getByRole('button', { name: 'PO received' })).toBeInTheDocument();
    expect(header.queryByRole('button', { name: 'Mark lost' })).toBeNull();

    // Radix opens its menus on pointerdown, which fireEvent.click does not send.
    fireEvent.pointerDown(header.getByRole('button', { name: 'Project actions' }), {
      button: 0,
      ctrlKey: false,
    });
    const lost = await screen.findByRole('menuitem', { name: 'Mark lost' });
    fireEvent.click(lost);

    expect(changeStatus).toHaveBeenCalledWith({
      projectId: 'p1',
      toStatusId: 's-lost',
    });
  });

  it('offers no move at all from a final rung, rather than a button the server rejects', () => {
    projectFixture = project({
      status_id: 's-po',
      status_key: 'po_received',
      status_label: 'PO Received',
    });

    renderDetail();

    const actions = within(screen.getByTestId('project-header-actions')).getAllByRole(
      'button',
    );
    expect(actions).toHaveLength(1);
    expect(actions[0]).toHaveAttribute('aria-label', 'Project actions');
  });

  it('gives a reader neither the action nor the overflow', () => {
    projectFixture = project({ can_edit: false });

    renderDetail();

    expect(
      within(screen.getByTestId('project-header-actions')).queryAllByRole('button'),
    ).toHaveLength(0);
    expect(screen.getByText('Quoted')).toBeInTheDocument();
  });
});

describe('deleting a project', () => {
  it('confirms before it deletes, and says the delete cannot be undone', async () => {
    renderDetail();

    openOverflow();
    fireEvent.click(await screen.findByText('Delete project'));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Confirm delete')).toBeInTheDocument();
    expect(within(dialog).getByText(/This action cannot be undone/i)).toBeInTheDocument();
    // Nothing has been deleted by opening the dialog.
    expect(deleteProject).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(deleteProject).toHaveBeenCalledWith('p1'));
  });
});
