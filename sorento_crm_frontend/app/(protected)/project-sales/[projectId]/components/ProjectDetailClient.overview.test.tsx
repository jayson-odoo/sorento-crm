/**
 * PROJECT-LEADS-REASSIGN, Phase 2 red tests: the Overview tab is one column (UAC C1, C2).
 *
 * jsdom has no layout, so "one column at every width" is pinned on the classes of the
 * containers between the tab panel and each card: none may lay cards side by side
 * (`grid-cols-2` or more, at any breakpoint). The fields inside a card keep their own grid (C2),
 * so only the cards' ancestors are checked, never their contents.
 *
 * Mocks copied from ProjectDetailClient.test.tsx.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
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
  // PROJECT-RELATED-RECORDS: the Related tab's badge reads this hook.
  useProjectRelatedRecords: () => ({ data: undefined }),
  // The pager reads the pipeline page through the entity's shared key + fetch (S3-03).
  projectsPagerQuery: {
    listQueryKey: () => ['projects'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useProject: () => ({ data: projectFixture, isLoading: false, isError: false }),
  // PROJECT-PARTY-ROLES: the Parties section reads the editable role list.
  usePartyRoles: () => ({
    data: [
      { value: 'developer', label: 'Developer', is_active: true, allows_many: false },
      { value: 'architect', label: 'Architect', is_active: true, allows_many: false },
      { value: 'subcontractor', label: 'Subcontractor', is_active: true, allows_many: true },
      { value: 'trading_house', label: 'Trading house', is_active: true, allows_many: true },
      { value: 'interior_designer', label: 'Interior designer', is_active: false, allows_many: false },
    ],
  }),
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

beforeEach(() => {
  vi.clearAllMocks();
  canManage = true;
  updateProject.mockResolvedValue({});
  projectFixture = project();
  graphFixture = graph();
});

const ORDER = [
  'The development',
  'Customer',
  'Value and timing',
  'Parties',
  'Where this came from',
  'Access',
  'Critical / final negotiation',
];

function overviewPanel(): HTMLElement {
  return screen.getByRole('tabpanel');
}

/** Cards directly on the Overview (a card nested inside another card is that card's own). */
function topLevelCards(panel: HTMLElement): HTMLElement[] {
  return Array.from(panel.querySelectorAll<HTMLElement>('[data-slot="card"]')).filter(
    (card) => !card.parentElement?.closest('[data-slot="card"]'),
  );
}

function titleOf(card: HTMLElement): string {
  return (card.querySelector('[data-slot="card-title"]')?.textContent ?? '').trim();
}

const SIDE_BY_SIDE = /(^|\s)([a-z0-9]+:)*grid-cols-([2-9]|1[0-2])(\s|$)/;

describe('Overview one column (C1, C2)', () => {
  it('C1 the cards come in order: development, customer, value, parties, source, access, critical', () => {
    renderDetail();
    const titles = topLevelCards(overviewPanel()).map(titleOf);
    expect(titles).toEqual(ORDER);
  });

  it('C1 no container between the tab panel and a card lays cards side by side, at any width', () => {
    renderDetail();
    const panel = overviewPanel();
    const offenders: string[] = [];
    for (const card of topLevelCards(panel)) {
      for (let el = card.parentElement; el && el !== panel.parentElement; el = el.parentElement) {
        const cls = typeof el.className === 'string' ? el.className : '';
        if (SIDE_BY_SIDE.test(cls)) offenders.push(`${titleOf(card)}: ${cls}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('C2 each card keeps its fields: The development still lists Developer then Location', () => {
    renderDetail();
    const dev = topLevelCards(overviewPanel()).find((c) => titleOf(c) === 'The development')!;
    const labels = Array.from(dev.querySelectorAll('dt')).map((d) => (d.textContent ?? '').trim());
    expect(labels.slice(0, 4)).toEqual([
      'Project title',
      'Developer',
      'Registered company / SPV',
      'Location',
    ]);
  });
});
