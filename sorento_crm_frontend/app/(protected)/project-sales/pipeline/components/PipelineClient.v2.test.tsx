/**
 * PROJECT-REGISTER-V2 J1b and J3 on the one Projects page.
 *
 * J1b: "Register a project" is in the Start menu for holders of `projects.projects.edit` OR
 * `projects.registrations.submit`; for a submit-only salesperson it is the ONLY Start entry
 * (no Upload PO, no Upload delivery schedule). A user with neither does not see it.
 * J3: an owner's saved draft is a row in the list with a "Draft" pill (grid view).
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

let granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => granted.has(s)),
  usePermissions: () => ({
    permissions: [...granted],
    permissionSet: granted,
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-me', name: 'Sales A' } }, status: 'authenticated' }),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const listProjects = vi.fn();
const listParties = vi.fn();
const listProjectTypes = vi.fn();
const listingKeys: (string | null | undefined)[] = [];
const push = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/pipeline',
  useRouter: () => ({ push, replace: vi.fn() }),
  // The list restores its page, sort and filters from the query string Back hands
  // it (S3-01), so it reads the URL on every render.
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: async () => {}, isLoading: false };
  },
}));

vi.mock('@/app/(protected)/project-sales/_shared/hooks/useProjectStatusGraph', () => ({
  useProjectStatusGraph: () => ({ data: { statuses: [] }, isLoading: false }),
}));

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listProjects: (...args: unknown[]) => listProjects(...args),
    listParties: (...args: unknown[]) => listParties(...args),
    listProjectTypes: (...args: unknown[]) => listProjectTypes(...args),
    listProjectTemplates: vi.fn(async () => []),
    previewClashes: vi.fn(async () => ({ candidates: [] })),
    registerProject: vi.fn(),
    changeProjectStatus: vi.fn(),
  };
});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
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

import { PipelineClient } from './PipelineClient';

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PipelineClient />
    </QueryClientProvider>,
  );
}
function openStart() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /^start/i }), { button: 0, ctrlKey: false });
}
const startItems = () => screen.getAllByRole('menuitem').map((el) => el.textContent?.trim());

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  granted = new Set(['projects.projects.view']);
  listProjects.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 50 } });
  listParties.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 200 } });
  listProjectTypes.mockResolvedValue([]);
});

describe('J1b Register a project in the Start menu', () => {
  it('shows it to a holder of projects.projects.edit', async () => {
    granted = new Set(['projects.projects.view', 'projects.projects.edit']);
    renderClient();
    openStart();
    expect(await screen.findByRole('menuitem', { name: 'Register a project' })).toBeInTheDocument();
  });

  it('shows it to a submit-only salesperson, as the only Start entry', async () => {
    granted = new Set(['projects.projects.view_own', 'projects.registrations.submit']);
    renderClient();
    openStart();
    await screen.findByRole('menuitem', { name: 'Register a project' });
    expect(startItems()).toEqual(['Register a project']);
  });

  it('a submit-only salesperson who clicks it goes to the register form', async () => {
    granted = new Set(['projects.projects.view_own', 'projects.registrations.submit']);
    renderClient();
    openStart();
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Register a project' }));
    expect(push).toHaveBeenCalledWith('/project-sales/new');
  });

  it('a user with neither slug does not see the entry', async () => {
    granted = new Set(['projects.projects.view']);
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    const start = screen.queryByRole('button', { name: /^start/i });
    if (start) {
      openStart();
      expect(screen.queryByRole('menuitem', { name: 'Register a project' })).toBeNull();
    }
  });
});

describe('J3 a draft is a row in the list with a Draft pill', () => {
  it('grid view shows a Draft pill on an approval_state draft row', async () => {
    granted = new Set(['projects.projects.view_own', 'projects.registrations.submit']);
    listProjects.mockResolvedValue({
      data: [
        {
          id: 'p-draft',
          project_code: null,
          title: 'Draf Menara CONTOH',
          outcome: 'open',
          approval_state: 'draft',
          status_id: null,
          status_key: null,
          status_label: null,
          is_critical: false,
          brands: [],
          brand_ids: [],
          can_edit: true,
          open_task_count: 0,
        } as unknown as Project,
      ],
      pagination: { total: 1, page: 1, limit: 50 },
    });
    renderClient();
    fireEvent.click(screen.getByRole('button', { name: /grid/i }));
    const row = (await screen.findByText('Draf Menara CONTOH')).closest('tr') as HTMLElement;
    expect(within(row).getByText('Draft')).toBeInTheDocument();
  });
});
