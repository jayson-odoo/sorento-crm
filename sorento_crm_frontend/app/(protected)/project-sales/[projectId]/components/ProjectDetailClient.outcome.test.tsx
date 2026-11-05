/**
 * PROJECT-OUTCOME-SINGLE FE1-FE3: one Won/Lost outcome per project, on the project page.
 *
 * Gear: "Mark won" on an open project, "Re-open" on a won or lost one, neither without edit
 * rights. Choosing "Mark lost" asks for a reason in a dialog and moves nothing until Save. The
 * header shows a Won pill when the project is won by a yes before any PO.
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
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));

// The pager has its own tests; here it is only the first slot in the group.
vi.mock('@/components/common/ListPager', () => ({
  __esModule: true,
  default: () => <div data-testid="pager-slot" />,
}));

vi.mock('@/components/common/ActivitiesNotesPanel/EntityActivitiesLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const changeStatus = vi.fn();
const setOutcome = vi.fn();
const lossReasons = [
  { value: 'price', label: 'Price' },
  { value: 'lead_time', label: 'Lead time' },
];
const deleteProject = vi.fn();
const updateProject = vi.fn();
let projectFixture: Project;
let canManage = true;

// PS-REGISTER-CHECK-FIRST: a Registered project with no document hides Spec In. These tests
// are about what Spec In does, so the project has one document.
vi.mock('../../_shared/hooks/useProjectDocuments', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../_shared/hooks/useProjectDocuments')>()),
  useProjectDocuments: () => ({
    isSuccess: true,
    isLoading: false,
    data: [{ id: 'd1', original_filename: 'brief.pdf', stored_filename: 'brief.pdf' }],
  }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => (slug === 'projects.projects.manage' ? canManage : true),
}));

vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-ali', name: 'Ali' },
    { id: 'u-mei', name: 'Mei Ling' },
  ]),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    id,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
    id?: string;
  }) => (
    <select
      id={id}
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

vi.mock('../../_shared/hooks/useProjects', () => ({
  // The pager reads the pipeline page through the entity's shared key + fetch (S3-03).
  projectsPagerQuery: {
    listQueryKey: () => ['projects'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useProject: () => ({ data: projectFixture, isLoading: false, isError: false }),
  useChangeProjectStatus: () => ({ mutate: changeStatus, isPending: false }),
  useSetProjectOutcome: () => ({ mutate: setOutcome, isPending: false }),
  useQuotationLossReasons: () => ({ data: lossReasons }),
  useDeleteProject: () => ({ mutateAsync: deleteProject }),
  useUpdateProject: () => ({ mutate: vi.fn(), mutateAsync: updateProject, isPending: false }),
  useCollaborators: () => ({ data: [], isLoading: false }),
  useTakeoverRequests: () => ({ data: [] }),
  useTakeoverMutations: () => ({
    decide: { mutate: vi.fn(), isPending: false },
    request: { mutateAsync: vi.fn(), isPending: false },
  }),
}));

let graphFixture: StatusGraph;
vi.mock('@/app/(protected)/project-sales/_shared/hooks/useProjectStatusGraph', () => ({
  useProjectStatusGraph: () => ({ data: graphFixture }),
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
  canManage = true;
  projectFixture = project();
  graphFixture = graph({
    statuses: [
      status('s-quoted', 'quoted', 'Quoted', 3),
      status('s-po', 'po_received', 'PO Received', 5, { is_terminal: true }),
      status('s-lost', 'lost', 'Lost', 6, { is_terminal: true }),
    ],
    transitions: [
      transition('t-2', 's-quoted', 's-po', 'PO received', 1),
      transition('t-4', 's-quoted', 's-lost', 'Mark lost', 2),
    ],
  });
});

async function openGear() {
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Project actions' }), {
    button: 0,
    ctrlKey: false,
  });
  // Radix renders the menu after the pointer event.
  await screen.findByRole('menu');
}

describe('gear: Mark won and Re-open', () => {
  it('offers Mark won, and not Re-open, on an open project', async () => {
    projectFixture = project({ outcome: 'open' });
    renderDetail();
    await openGear();

    expect(screen.getByRole('menuitem', { name: 'Mark won' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Re-open' })).toBeNull();
  });

  it('Mark won sets the outcome and does not move the status', async () => {
    renderDetail();
    await openGear();

    fireEvent.click(screen.getByRole('menuitem', { name: 'Mark won' }));

    expect(setOutcome).toHaveBeenCalledTimes(1);
    expect(setOutcome.mock.calls[0][0]).toMatchObject({ projectId: 'p1', outcome: 'won' });
    expect(changeStatus).not.toHaveBeenCalled();
  });

  it.each(['won', 'lost'])('offers Re-open, and not Mark won, on a %s project', async (outcome) => {
    projectFixture = project({ outcome: outcome as Project['outcome'] });
    renderDetail();
    await openGear();

    expect(screen.getByRole('menuitem', { name: 'Re-open' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Mark won' })).toBeNull();
  });

  it('Re-open sets the outcome back to open', async () => {
    projectFixture = project({ outcome: 'lost', status_id: 's-lost', status_key: 'lost', status_label: 'Lost' });
    renderDetail();
    await openGear();

    fireEvent.click(screen.getByRole('menuitem', { name: 'Re-open' }));

    expect(setOutcome.mock.calls[0][0]).toMatchObject({ projectId: 'p1', outcome: 'open' });
  });

  it('offers neither without edit rights', () => {
    projectFixture = project({ outcome: 'open', can_edit: false });
    renderDetail();

    expect(screen.queryByRole('button', { name: 'Project actions' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Mark won' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Re-open' })).toBeNull();
  });
});

describe('gear: Mark lost asks for a reason', () => {
  it('opens a reason dialog and moves nothing until Save', async () => {
    renderDetail();
    await openGear();

    fireEvent.click(screen.getByRole('menuitem', { name: 'Mark lost' }));

    const dialog = await screen.findByRole('dialog');
    expect(changeStatus).not.toHaveBeenCalled();
    expect(within(dialog).getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('Save sends the move with the chosen reason', async () => {
    renderDetail();
    await openGear();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Mark lost' }));
    const dialog = await screen.findByRole('dialog');

    fireEvent.change(within(dialog).getByRole('combobox'), { target: { value: 'price' } });
    const save = within(dialog).getByRole('button', { name: 'Save' });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);

    expect(changeStatus).toHaveBeenCalledTimes(1);
    expect(changeStatus.mock.calls[0][0]).toMatchObject({
      projectId: 'p1',
      toStatusId: 's-lost',
      lossReason: 'price',
    });
  });

  it('Cancel closes the dialog and moves nothing', async () => {
    renderDetail();
    await openGear();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Mark lost' }));
    const dialog = await screen.findByRole('dialog');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(changeStatus).not.toHaveBeenCalled();
  });
});

describe('header Won pill', () => {
  it('shows Won beside the status when the project is won before any PO', () => {
    projectFixture = project({ outcome: 'won' });
    renderDetail();

    expect(screen.getByText('Won')).toBeInTheDocument();
    expect(screen.getByText('Quoted')).toBeInTheDocument();
  });

  it('shows no Won pill on PO Received, where the status already says it', () => {
    projectFixture = project({
      outcome: 'won',
      status_id: 's-po',
      status_key: 'po_received',
      status_label: 'PO Received',
    });
    renderDetail();

    expect(screen.queryByText('Won')).toBeNull();
  });

  it('shows no Won pill on an open project', () => {
    renderDetail();
    expect(screen.queryByText('Won')).toBeNull();
  });
});
