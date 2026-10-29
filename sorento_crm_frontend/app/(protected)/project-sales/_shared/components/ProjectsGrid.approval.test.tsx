/**
 * RW12 - the project list shows registrations that wait for a decision (PLAN R6).
 *
 * The Code column reads "Awaiting approval" where a pending or rejected registration has no code
 * yet (one helper, `projectCodeLabel`), and the Stage column shows an "Awaiting approval" /
 * "Rejected" pill instead of "No stage". A staff project is untouched.
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

const PENDING = project({
  id: 'p-pend',
  project_code: null,
  title: 'Pending Registration Tower',
  status_id: null,
  status_key: null,
  status_label: null,
  approval_state: 'pending',
  brands: ['Sorento'],
});
const REJECTED = project({
  id: 'p-rej',
  project_code: null,
  title: 'Rejected Registration Tower',
  status_id: null,
  status_key: null,
  status_label: null,
  approval_state: 'rejected',
});

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
        listingKey="projects.projects.view::zzt-approval"
      />
    </QueryClientProvider>,
  );
}

async function row(title: string): Promise<HTMLElement> {
  return (await screen.findByText(title)).closest('tr') as HTMLElement;
}

describe('ProjectsGrid: registrations that wait for a decision (RW12)', () => {
  it('the Code column says "Awaiting approval" for a project with no code', async () => {
    renderGrid([PENDING, REJECTED, project()]);
    const pend = within(await row('Pending Registration Tower'));
    expect(pend.getAllByText('Awaiting approval').length).toBeGreaterThanOrEqual(1);
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
    const code = headers.findIndex((h) => h?.startsWith('Code'));
    expect(pend.getAllByRole('cell')[code]).toHaveTextContent('Awaiting approval');
    const rejected = within(await row('Rejected Registration Tower'));
    // Review round 3: a rejected registration's code slot says Rejected.
    expect(rejected.getAllByRole('cell')[code]).toHaveTextContent('Rejected');
  });

  it('the Stage column shows an Awaiting approval pill for pending and a Rejected pill for rejected', async () => {
    renderGrid([PENDING, REJECTED, project()]);
    await row('Pending Registration Tower');
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
    const at = headers.findIndex((h) => h?.startsWith('Stage'));
    const stageOf = async (title: string) => within(await row(title)).getAllByRole('cell')[at];
    expect(await stageOf('Pending Registration Tower')).toHaveTextContent('Awaiting approval');
    expect(await stageOf('Rejected Registration Tower')).toHaveTextContent('Rejected');
    expect(await stageOf('Staff Registered Tower')).toHaveTextContent('Quoted');
  });

  it('neither is shown as "No stage"', async () => {
    renderGrid([PENDING, REJECTED]);
    await row('Pending Registration Tower');
    expect(screen.queryByText('No stage')).toBeNull();
  });

  it('a staff project keeps its code and its stage, with no waiting pill', async () => {
    renderGrid([PENDING, project()]);
    const staff = within(await row('Staff Registered Tower'));
    expect(staff.getByText('PRJ-000142')).toBeInTheDocument();
    expect(staff.queryByText('Awaiting approval')).toBeNull();
    expect(staff.queryByText('Rejected')).toBeNull();
  });

  it('never renders None, null or undefined for the missing code, in a cell or a label', async () => {
    const { container } = renderGrid([PENDING, REJECTED]);
    await row('Pending Registration Tower');
    // ("None" is the grid's own word for an empty Brands cell, so it is not searched for alone.)
    expect(screen.queryByText(/\b(null|undefined)\b/i)).toBeNull();
    const labels = Array.from(container.querySelectorAll('[aria-label]')).map((el) => el.getAttribute('aria-label'));
    expect(labels.filter((l) => /\b(none|null|undefined)\b/i.test(l ?? ''))).toEqual([]);
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
    const code = headers.findIndex((h) => h?.startsWith('Code'));
    for (const title of ['Pending Registration Tower', 'Rejected Registration Tower']) {
      expect((await row(title)).querySelectorAll('td')[code].textContent).not.toMatch(/none|null|undefined/i);
    }
  });

  it('the project title still links to the record', async () => {
    renderGrid([PENDING]);
    expect(await screen.findByRole('link', { name: 'Pending Registration Tower' })).toHaveAttribute(
      'href',
      '/project-sales/p-pend',
    );
  });

  it('QUOTE-UI-POLISH AC-QUP-8: the Code and Project links carry no underline, hover included', async () => {
    renderGrid([project()]);
    const title = await screen.findByRole('link', { name: 'Staff Registered Tower' });
    const code = screen.getByRole('link', { name: 'PRJ-000142' });
    for (const link of [title, code]) {
      expect(link.className).not.toMatch(/underline/);
    }
  });
});

describe('ProjectsGrid: the typed developer of a registration (review round 3)', () => {
  it('shows "Typed: <name>" in the Developer column while no developer party is picked', async () => {
    renderGrid([
      { ...PENDING, developer_name: null, registration: { developer_name: 'Example Developer Sdn Bhd' } } as Project,
    ]);
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
    const at = headers.findIndex((h) => h?.startsWith('Developer'));
    const cell = within(await row('Pending Registration Tower')).getAllByRole('cell')[at];
    expect(cell).toHaveTextContent('Typed: Example Developer Sdn Bhd');
  });

  it('shows the party once one is picked, and nothing typed for a staff project', async () => {
    renderGrid([
      { ...PENDING, developer_name: 'SP Setia', registration: { developer_name: 'Typed Name' } } as Project,
      project({ developer_name: null }),
    ]);
    await row('Pending Registration Tower');
    expect(screen.queryByText(/Typed:/)).toBeNull();
    expect(screen.getByText('SP Setia')).toBeInTheDocument();
  });
});
