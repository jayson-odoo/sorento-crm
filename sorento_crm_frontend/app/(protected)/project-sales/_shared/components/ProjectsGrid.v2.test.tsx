/**
 * PROJECT-REGISTER-V2 G3 (no Brands column) and J3 (Draft pill) on the project list grid.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
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
        onSortingChange={vi.fn()}
        onRefresh={vi.fn()}
        listingKey="projects.projects.view::zzt-v2"
      />
    </QueryClientProvider>,
  );
}

describe('G3 the grid has no Brands column', () => {
  it('lists no Brands header and prints no brand names', async () => {
    renderGrid([project({ brands: ['CONTOH Brand'], brand_ids: ['b1'] } as Partial<Project>)]);
    await screen.findByText('Staff Registered Tower');
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
    expect(headers.some((h) => h?.startsWith('Brands'))).toBe(false);
    expect(screen.queryByText('CONTOH Brand')).toBeNull();
  });
});

describe('J3 a draft row carries a Draft pill', () => {
  it('shows Draft on an approval_state draft project', async () => {
    renderGrid([
      project({
        id: 'p-draft',
        project_code: null,
        title: 'Draf Menara CONTOH',
        status_id: null,
        status_key: null,
        status_label: null,
        approval_state: 'draft',
      } as Partial<Project>),
    ]);
    const row = (await screen.findByText('Draf Menara CONTOH')).closest('tr') as HTMLElement;
    expect(within(row).getByText('Draft')).toBeInTheDocument();
  });
});
