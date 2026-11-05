/**
 * Owner hand test on #2195: "every column must be sortable". Every Projects grid column
 * asks the SERVER for its order (manualSorting): a header click hands its column id to
 * onSortingChange, which becomes `sort=<id>` on the list request.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Project } from '../types/project.types';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
Element.prototype.scrollIntoView = vi.fn();

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async () => ({ listing_key: 'k', config: null })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, payload: unknown) => ({
    listing_key: listingKey,
    config: payload,
  })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/projects',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-me' } }, status: 'authenticated' }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

import { ProjectsGrid } from './ProjectsGrid';

function project(over: Partial<Project> = {}): Project {
  return {
    id: 'p-staff',
    project_code: 'PRJ-000142',
    title: 'Staff Registered Tower',
    outcome: 'open',
    status_id: 's-quoted',
    status_key: 'quoted',
    status_label: 'Quoted',
    approval_state: null,
    developer_name: 'SP Setia',
    owner_name: 'Ali',
    is_critical: false,
    brands: [],
    brand_ids: [],
    open_task_count: 0,
    can_edit: true,
    ...over,
  } as Project;
}

const onSortingChange = vi.fn();

function renderGrid(projects: Project[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProjectsGrid
        projects={projects}
        total={projects.length}
        pagination={{ pageIndex: 0, pageSize: 25 }}
        onPaginationChange={vi.fn()}
        sorting={[]}
        onSortingChange={onSortingChange}
        onRefresh={vi.fn()}
        listingKey="projects.projects.view::zzt-v2"
      />
    </QueryClientProvider>,
  );
}

describe('every Projects grid column sorts server-side', () => {
  it.each([
    ['Code', 'project_code'],
    ['Project', 'title'],
    ['Developer', 'developer_name'],
    ['Stage', 'status_label'],
    ['Outcome', 'outcome'],
    ['Estimated', 'estimated_sales_value'],
    ['Owner', 'owner_name'],
    ['Next action', 'next_action'],
    ['Last activity', 'last_meaningful_activity_at'],
    ['Flags', 'flags'],
  ])('%s header sorts by %s', async (title, id) => {
    onSortingChange.mockClear();
    renderGrid([project()]);
    await screen.findByText('Staff Registered Tower');
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${title}$`) }));
    expect(onSortingChange).toHaveBeenCalledWith([{ id, desc: false }]);
  });
});
