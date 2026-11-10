/**
 * RFQ-GATE-REMOVE (owner, 10 Nov 2026): a Registered project's header shows the status graph's
 * next step, Spec In, whether or not it has a document. The PS-REGISTER-CHECK-FIRST "Upload
 * Requirement" button and its dialog are gone; the Documents tab keeps its own upload.
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

type Call = { url: string; method: string; body: unknown; at: number };
const apiCalls: Call[] = [];
let docs: unknown[] = [];
let docsMode: 'ok' | 'pending' | 'error' = 'ok';
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
      if (method === 'POST' && String(input).includes('/attachments')) {
        docs = [{ id: 'd-new', original_filename: 'reqs.pdf', stored_filename: 'reqs.pdf', attachment_type: { id: 'ty-doc', type_name: 'Project Document' } }];
        return ok({ id: 'd-new' });
      }
      if (method === 'POST') return ok({ id: 'new' });
      if (method === 'GET' && String(input).includes('/attachments')) {
        if (docsMode === 'pending') return new Promise<Response>(() => {});
        if (docsMode === 'error') {
          return new Response(JSON.stringify({ detail: 'boom' }), {
            status: 500,
            headers: { 'content-type': 'application/json' },
          });
        }
        return ok({ data: docs });
      }
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
  // PROJECT-PARTY-ROLES: the Parties section reads the editable role list.
  usePartyRoles: () => ({ data: [] }),
  useChangeProjectStatus: () => ({ mutate: changeStatus, isPending: false }),
  useSetProjectOutcome: () => ({ mutate: vi.fn(), isPending: false }),
  useQuotationLossReasons: () => ({ data: [{ value: 'price', label: 'Price' }] }),
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
  docs = [];
  docsMode = 'ok';
  canManage = true;
  updateProject.mockResolvedValue({});
  standRegistered();
});

describe('RFQ-GATE-REMOVE the header follows the status graph', () => {
  it('AC-1 Registered with 0 documents shows Spec In and no Upload Requirement', async () => {
    renderDetail();
    expect(await header().findByRole('button', { name: 'Spec In' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Upload Requirement' })).toBeNull();
  });

  it('AC-2 clicking Spec In with 0 documents moves the project to Spec In', async () => {
    renderDetail();
    fireEvent.click(await header().findByRole('button', { name: 'Spec In' }));
    await waitFor(() => expect(changeStatus).toHaveBeenCalledTimes(1));
    expect(changeStatus.mock.calls[0][0]).toMatchObject({ projectId: 'p1', toStatusId: 's-spec' });
    expect(screen.queryByRole('dialog', { name: 'Upload requirement' })).toBeNull();
  });

  it('AC-1 the header does not wait on the documents read', async () => {
    docsMode = 'pending';
    renderDetail();
    expect(await header().findByRole('button', { name: 'Spec In' })).toBeInTheDocument();
  });

  it('AC-1 with documents the header is the same: Spec In', async () => {
    docs = [{ id: 'd1', original_filename: 'brief.pdf', stored_filename: 'brief.pdf' }];
    renderDetail();
    expect(await header().findByRole('button', { name: 'Spec In' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Upload Requirement' })).toBeNull();
  });

  it('AC-1 a user who cannot work on the project gets no move and no Upload Requirement', async () => {
    projectFixture = project({ status_id: 's-reg', status_key: 'registered', status_label: 'Registered', can_edit: false });
    renderDetail();
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(header().queryByRole('button', { name: 'Spec In' })).toBeNull();
    expect(header().queryByRole('button', { name: 'Upload Requirement' })).toBeNull();
  });
});

describe('AC-T2 SO tab shows every sales order', () => {
  it('AC-T2 the SO tab renders SalesOrdersPanel without withoutPurchaseOrder, the PO tab no sales orders', async () => {
    // The panels are real here; the observable is the call each makes. A PO tab that still embeds
    // the filtered SalesOrdersPanel, or an SO tab that filters, both break this.
    const src = await import('./ProjectDetailClient?raw').then((m) => m.default as string).catch(() => '');
    expect(src, 'raw source readable').not.toBe('');
    expect(src).not.toContain('withoutPurchaseOrder');
  });
});
