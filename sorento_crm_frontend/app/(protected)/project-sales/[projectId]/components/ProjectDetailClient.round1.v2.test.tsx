/**
 * PROJECT-REGISTER-V2 review round 1 on the detail page: J3 (a draft shows only its fields with
 * Edit and Submit for approval), J3b (submit-only Edit visibility) and the nested-block nit
 * (no <div> inside the header <h2> or the "Already registered as" <p>).
 *
 * The real TruncatedTextCell is used on purpose (the nit is about its markup). The collaborators
 * and takeover-requests hooks are spied: a draft must not read them (J3: no Access card, nothing
 * else queried).
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
const spies = vi.hoisted(() => ({ collaborators: vi.fn(), takeover: vi.fn() }));
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
  useProjectStatusGraph: () => ({
    data: { entity_type: 'project', statuses: [], transitions: [], is_fork: false },
  }),
}));

import { ProjectDetailClient } from './ProjectDetailClient';

const SUBMIT_ONLY = ['projects.projects.view_own', 'projects.registrations.submit'];

function fixture(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: null,
    title: 'Draf Menara CONTOH',
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
    approval_state: 'draft',
    reject_reason: null,
    submitted_at: null,
    decided_at: null,
    developer_party_id: null,
    developer_name: 'SP Setia CONTOH',
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
const header = () => screen.getByTestId('project-header-actions');

beforeEach(() => {
  vi.clearAllMocks();
  hookArgs.approve = [];
  hookArgs.reject = [];
  granted = new Set(SUBMIT_ONLY);
  approve.mockResolvedValue({});
  reject.mockResolvedValue({});
  projectFixture = fixture();
});

describe('J3 an owner\'s draft page', () => {
  it('shows the fields with Edit and Submit for approval', () => {
    renderDetail();
    expect(within(header()).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(within(header()).getByRole('button', { name: 'Submit for approval' })).toBeInTheDocument();
    expect(screen.getByText('Draf Menara CONTOH')).toBeInTheDocument();
    expect(screen.getByText('SP Setia CONTOH')).toBeInTheDocument();
  });

  it('has no Access card and no tab other than Overview', () => {
    renderDetail();
    expect(screen.queryByText('Access')).toBeNull();
    const tabs = screen.getAllByRole('tab').map((t) => t.textContent?.trim());
    expect(tabs).toEqual(['Overview']);
  });

  it('does not query collaborators or takeover requests', () => {
    renderDetail();
    expect(spies.collaborators).not.toHaveBeenCalled();
    expect(spies.takeover).not.toHaveBeenCalled();
  });
});

describe('J3b Edit for a submit-only owner', () => {
  it.each([
    ['draft', true],
    ['rejected', true],
    ['pending', false],
  ])('%s: Edit shown = %s', (state, shown) => {
    projectFixture = fixture({ approval_state: state, reject_reason: state === 'rejected' ? 'Duplicate' : null } as never);
    renderDetail();
    const edit = within(header()).queryByRole('button', { name: 'Edit' });
    if (shown) expect(edit).not.toBeNull();
    else expect(edit).toBeNull();
  });
});

describe('nested block nit', () => {
  it('the header h2 holds no div', () => {
    projectFixture = fixture({ approval_state: 'approved', project_code: 'PRJ-000001', status_id: 's1', status_key: 'registered', status_label: 'Registered' } as never);
    renderDetail();
    const h2 = screen.getAllByRole('heading', { level: 2 }).find((h) => h.textContent?.includes('Draf Menara CONTOH'))!;
    expect(h2).toBeTruthy();
    expect(h2.querySelector('div')).toBeNull();
  });

  it('the "Already registered as" paragraph holds no div', async () => {
    granted = new Set(['projects.registrations.approve', 'projects.projects.manage']);
    projectFixture = fixture({ approval_state: 'pending' } as never);
    approve.mockRejectedValue(
      Object.assign(new Error('dup'), {
        existingProject: { project_id: 'proj-77', project_code: 'PPF2509012', title: 'KILANG ALPHA CONTOH' },
      }),
    );
    renderDetail();
    fireEvent.click(within(header()).getByRole('button', { name: 'Approve' }));
    const line = (await screen.findByText(/Already registered as/)).closest('p') as HTMLElement;
    await waitFor(() => expect(line).toBeTruthy());
    expect(line.querySelector('div')).toBeNull();
  });
});
