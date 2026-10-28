/**
 * PORTAL-P3-ROLE-MENU round 4, R6: an own-only (view_own without view) user makes no request to
 * parties or project types (both answer 403 and toast), sees no filters that need them, and the
 * empty state hint does not mention Start. `.view` holders: unchanged.
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




function openFilters() {
  const btn = screen.queryByRole('button', { name: /filters/i });
  if (btn) fireEvent.pointerDown(btn, { button: 0, ctrlKey: false });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  listProjects.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 50 } });
  listParties.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 200 } });
  listProjectTypes.mockResolvedValue([]);
});

describe('PipelineClient for an own-only user (R6)', () => {
  it('view_own without view: no parties and no project-types request', async () => {
    permsRef.set = new Set(['projects.projects.view_own']);
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    expect(listParties).not.toHaveBeenCalled();
    expect(listProjectTypes).not.toHaveBeenCalled();
  });

  it('view_own without view: Developer and Type filters are hidden', async () => {
    permsRef.set = new Set(['projects.projects.view_own']);
    renderClient();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    openFilters();
    expect(screen.queryByText('Developer')).toBeNull();
    expect(screen.queryByText('Type')).toBeNull();
  });

  it('view_own without view: empty state keeps its heading, hint has no Start', async () => {
    permsRef.set = new Set(['projects.projects.view_own']);
    renderClient();
    expect(await screen.findByText('No projects registered yet')).toBeInTheDocument();
    expect(screen.queryByText(/Start/)).toBeNull();
  });

  it('view holder: parties and types are requested, hint is as today', async () => {
    permsRef.set = new Set(['projects.projects.view', 'projects.projects.edit']); // main: the Start hint needs the right to register
    renderClient();
    await waitFor(() => expect(listParties).toHaveBeenCalled());
    expect(listProjectTypes).toHaveBeenCalled();
    expect(await screen.findByText('Register one from Start.')).toBeInTheDocument();
  });
});
