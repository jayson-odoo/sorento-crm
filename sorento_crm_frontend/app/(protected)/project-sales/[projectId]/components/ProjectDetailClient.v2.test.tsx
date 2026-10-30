/**
 * PROJECT-REGISTER-V2 H2 and G3 on the project detail page.
 *
 * H2: the header title is rendered through TruncatedTextCell with lines 2 in every approval
 * state (staff, pending, rejected, approved), so a 60-word title takes at most two lines.
 * G3: the Overview has no "Brands" line.
 *
 * TruncatedTextCell is stubbed to a marker that records the text and `lines` it was given;
 * its own behaviour is covered by components/common/TruncatedTextCell.v2.test.tsx.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
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
  usePathname: () => '/project-sales/p1',
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
vi.mock('@/components/common/TruncatedTextCell', () => ({
  TruncatedTextCell: ({ text, lines }: { text?: string | null; lines?: number }) => (
    <span data-testid="truncated" data-lines={String(lines ?? 1)}>
      {text}
    </span>
  ),
}));
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

const TITLE =
  'Cadangan pembangunan bercampur CONTOH merangkumi pangsapuri servis ruang pejabat kedai runcit dan kemudahan awam';

function fixture(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: TITLE,
    outcome: 'open',
    is_critical: false,
    brands: ['CONTOH Brand'],
    brand_ids: ['b1'],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    status_id: 's1',
    status_key: 'registered',
    status_label: 'Registered',
    approval_state: null,
    possible_duplicates: [],
    registration: null,
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

beforeEach(() => {
  vi.clearAllMocks();
  granted = new Set(['projects.projects.manage', 'projects.registrations.approve']);
});

const STATES: [string, Partial<Project>][] = [
  ['staff (no approval state)', {}],
  ['pending', { approval_state: 'pending', project_code: null, status_id: null, status_key: null, status_label: null }],
  ['rejected', { approval_state: 'rejected', project_code: null, reject_reason: 'Duplicate', status_id: null, status_key: null, status_label: null }],
  ['approved', { approval_state: 'approved' }],
];

describe('H2 the detail header title is clamped to two lines', () => {
  it.each(STATES)('%s: the header title goes through TruncatedTextCell with lines 2', (_name, over) => {
    projectFixture = fixture(over);
    renderDetail();
    const heading = screen.getAllByRole('heading').find((h) => h.textContent?.includes(TITLE));
    const holder = heading ?? screen.getAllByTestId('truncated')[0].parentElement!;
    const cells = within(holder).queryAllByTestId('truncated');
    const cell = cells.find((c) => c.textContent === TITLE) ?? screen.getAllByTestId('truncated').find((c) => c.textContent === TITLE);
    expect(cell, 'title is not rendered through TruncatedTextCell').toBeTruthy();
    expect(cell).toHaveAttribute('data-lines', '2');
  });
});

describe('G3 no Brands line in the Overview', () => {
  it('prints neither a Brands label nor the brand names', () => {
    projectFixture = fixture();
    renderDetail();
    expect(screen.queryByText('Brands')).toBeNull();
    expect(screen.queryByText(/CONTOH Brand/)).toBeNull();
  });
});
