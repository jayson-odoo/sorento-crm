/**
 * PS-REGISTER-CHECK-FIRST AC-G7: moving a Registered project to Spec In without a Requirements file is
 * refused by the server (422, code `project_requirements_missing`). The page answers with a
 * "Requirements needed" dialog instead of an error toast; "Upload and move to Spec In" files the
 * documents as Requirements (the attachment type whose code is `project_requirements`) and repeats
 * the move. The code is read from the CodedError (`error.code`) the status call rejects with
 * (lib/api-client codedError). Any other code keeps today's toast and opens no dialog.
 *
 * The hook is mocked here (as in ProjectDetailClient.test.tsx), so "no toast" for the code is pinned
 * on the real hook in useChangeProjectStatus.requirements.test.tsx.
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

// The pager has its own tests; here it is only the first slot in the group.
vi.mock('@/components/common/ListPager', () => ({
  __esModule: true,
  default: () => <div data-testid="pager-slot" />,
}));

vi.mock('@/components/common/ActivitiesNotesPanel/EntityActivitiesLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

type Call = { url: string; method: string; body: unknown; at: number };
const apiCalls: Call[] = [];
let seq = 0;
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiFetch: async (input: string, init: RequestInit = {}) => {
      const method = (init.method ?? 'GET').toUpperCase();
      apiCalls.push({ url: String(input), method, body: init.body ?? null, at: seq++ });
      const ok = (b: unknown) =>
        new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
      if (method === 'GET' && String(input).includes('attachment-types')) {
        return ok({
          data: [
            { id: 'ty-legacy', type_name: 'Old Thing', code: null },
            { id: 'ty-doc', type_name: 'Project Document', code: 'project_document' },
            { id: 'ty-req', type_name: 'Requirements', code: 'project_requirements' },
          ],
        });
      }
      if (method === 'POST') return ok({ id: 'new' });
      return ok({ data: [] });
    },
  };
});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

const changeStatus = vi.fn();
const deleteProject = vi.fn();
const updateProject = vi.fn();
let projectFixture: Project;
let canManage = true;

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
import { toast } from '@/lib/toast';

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


function refuse(code: string | null) {
  changeStatus.mockImplementation(
    (_vars: unknown, options?: { onError?: (e: Error) => void }) => {
      const error = new Error('Upload the requirements document before moving this project to Spec In.') as Error & {
        code: string | null;
      };
      error.code = code;
      options?.onError?.(error);
    },
  );
}

function standRegistered() {
  graphFixture = graph({
    statuses: [
      status('s-reg', 'registered', 'Registered', 1),
      status('s-spec', 'specified', 'Spec In', 2),
      status('s-lost', 'lost', 'Lost', 8, { is_terminal: true }),
    ],
    transitions: [
      transition('t-0', 's-reg', 's-spec', 'Spec In', 0),
      transition('t-1', 's-reg', 's-lost', 'Mark lost', 1),
    ],
  });
  projectFixture = project({ status_id: 's-reg', status_key: 'registered', status_label: 'Registered' });
}

const header = () => within(screen.getByTestId('project-header-actions'));

beforeEach(() => {
  vi.clearAllMocks();
  apiCalls.length = 0;
  canManage = true;
  updateProject.mockResolvedValue({});
  standRegistered();
});

describe('AC-G7 Requirements needed dialog', () => {
  it('AC-G7 a project_requirements_missing refusal opens the dialog and shows no error toast', async () => {
    refuse('project_requirements_missing');
    renderDetail();
    fireEvent.click(header().getByRole('button', { name: 'Spec In' }));
    const dialog = await screen.findByRole('dialog', { name: 'Requirements needed' });
    expect(
      within(dialog).getByText('Upload the requirements document before moving this project to Spec In.'),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Upload and move to Spec In' })).toBeInTheDocument();
    expect(dialog.querySelector('input[type="file"]')).not.toBeNull();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('AC-G7 Upload and move files the document as Requirements, then repeats the move', async () => {
    refuse('project_requirements_missing');
    renderDetail();
    fireEvent.click(header().getByRole('button', { name: 'Spec In' }));
    const dialog = await screen.findByRole('dialog', { name: 'Requirements needed' });
    expect(changeStatus).toHaveBeenCalledTimes(1);
    const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'reqs.pdf', { type: 'application/pdf' })] },
    });
    // The second attempt succeeds.
    changeStatus.mockImplementation(
      (_vars: unknown, options?: { onSuccess?: () => void }) => options?.onSuccess?.(),
    );
    fireEvent.click(within(dialog).getByRole('button', { name: 'Upload and move to Spec In' }));
    await waitFor(() => expect(changeStatus).toHaveBeenCalledTimes(2));
    const posts = apiCalls.filter((c) => c.method === 'POST' && c.url.includes('/attachments'));
    expect(posts).toHaveLength(1);
    const form = posts[0].body as FormData;
    expect(form.get('attachment_type_id')).toBe('ty-req');
    expect(form.get('entity_type')).toBe('project');
    expect(form.get('entity_id')).toBe('p1');
    expect(changeStatus).toHaveBeenLastCalledWith(
      { projectId: 'p1', toStatusId: 's-spec' },
      expect.anything(),
    );
  });

  it('AC-G7 Cancel closes the dialog and uploads nothing', async () => {
    refuse('project_requirements_missing');
    renderDetail();
    fireEvent.click(header().getByRole('button', { name: 'Spec In' }));
    const dialog = await screen.findByRole('dialog', { name: 'Requirements needed' });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Requirements needed' })).toBeNull());
    expect(apiCalls.filter((c) => c.method === 'POST')).toHaveLength(0);
    expect(changeStatus).toHaveBeenCalledTimes(1);
  });

  it.each([['some_other_code'], [null]])('AC-G7 a refusal with code %s opens no dialog', async (code) => {
    refuse(code);
    renderDetail();
    fireEvent.click(header().getByRole('button', { name: 'Spec In' }));
    await waitFor(() => expect(changeStatus).toHaveBeenCalled());
    expect(screen.queryByRole('dialog', { name: 'Requirements needed' })).toBeNull();
    expect(screen.queryByText('Requirements needed')).toBeNull();
  });
});
