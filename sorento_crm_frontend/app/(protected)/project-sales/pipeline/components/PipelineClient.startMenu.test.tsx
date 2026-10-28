/**
 * PORTAL-P3-ROLE-MENU round 2, A1: the Start menu is for `.view` holders; a `view_own` salesperson
 * gets the list without it. Mocks copied from PipelineClient.test.tsx.
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

const permsRef: { set: Set<string> } = { set: new Set() };
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissionSet: permsRef.set, isLoading: false, isError: false }),
  // main (PROJECT-REGISTER-V2) gates Start on edit / registrations.submit: answer from the same set.
  useHasPermission: (slug: string) => permsRef.set.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => permsRef.set.has(s)),
}));

import { PipelineClient } from './PipelineClient';

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Setia Alam Phase 3B',
    outcome: 'open',
    is_critical: false,
    brands: [],
    brand_ids: [],
    can_edit: true,
    open_task_count: 0,
    ...overrides,
  } as Project;
}

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

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  listProjects.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 50 } });
  listParties.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 200 } });
  listProjectTypes.mockResolvedValue([]);
});

describe('PipelineClient Start menu by permission (PORTAL-P3-ROLE-MENU P3-14, P3-17)', () => {
  it('view_own without view: no Start menu at all', async () => {
    permsRef.set = new Set(['projects.projects.view_own']);
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /^start/i })).toBeNull();
    expect(screen.queryByText('Register a project')).toBeNull();
    expect(screen.queryByText('Upload PO')).toBeNull();
  });

  it('view holder: Start opens the same three items as today', async () => {
    // main (PROJECT-REGISTER-V2): Start needs the right to register (edit or registrations.submit).
    permsRef.set = new Set(['projects.projects.view', 'projects.projects.edit']);
    renderClient();
    openStart();
    const items = await screen.findAllByRole('menuitem');
    expect(items.map((i) => i.textContent)).toEqual([
      'Register a project',
      'Upload PO',
      'Upload delivery schedule',
    ]);
  });

  it('view and view_own together: Start is shown', async () => {
    permsRef.set = new Set(['projects.projects.view', 'projects.projects.view_own', 'projects.projects.edit']);
    renderClient();
    expect(screen.getByRole('button', { name: /^start/i })).toBeInTheDocument();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
  });
});
