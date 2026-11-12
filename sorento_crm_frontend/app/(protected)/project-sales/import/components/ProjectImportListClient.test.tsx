/**
 * AC-PI-43 (RED): the runs list is the standard DataGrid.
 *
 * Assumed (the coder matches these):
 *   `ProjectImportListClient` (named export) from './ProjectImportListClient', no props.
 *   It reads runs through `useProjectImport` hooks over
 *   `_shared/services/projectImportService.listRuns(grid, filters)`, which answers
 *   `{ data: Run[], total }` (route as built). A Run row carries id, run_no, filename,
 *   status, uploaded_by (a name), uploaded_by_id, uploaded_at (ISO), rows, created, skipped,
 *   to_review.
 *   The toolbar's one CTA is a button named exactly "Create"; it opens
 *   `CreateImportDialog` (mocked here). A row click opens /project-sales/import/<id>.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const push = vi.fn();
// Round 5 (REV-M4): the screen reads projects.import.run. Every test runs with both
// permissions unless it says otherwise.
const perms = vi.hoisted(() => ({
  set: new Set<string>(['projects.import.view', 'projects.import.run']),
}));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({
    permissions: [...perms.set],
    permissionSet: perms.set,
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: () => {},
  }),
  useHasPermission: (slug: string) => perms.set.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => perms.set.has(s)),
  PERMISSIONS_QUERY_KEY: ['my-permissions'],
}));
const nav = vi.hoisted(() => ({ search: '' }));

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/import',
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ data: [], total: 0 }) })),
}));

const service = vi.hoisted(() => ({ listRuns: vi.fn() }));
vi.mock('../../_shared/services/projectImportService', () => service);
vi.mock('./CreateImportDialog', () => ({
  CreateImportDialog: () => null,
  default: () => null,
}));

import { ProjectImportListClient } from './ProjectImportListClient';

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const RUN_ID = '0b5c3a52-6a8e-4f6e-9f43-6a1f2f8e1c11';
const USER_ID = '7d2a9f4e-1c3b-4e8d-a5f6-2b9c8d7e6f50';

const runs = [
  {
    id: RUN_ID,
    run_no: 'PIM-0001',
    filename: 'TOTAL SALES ORDER SUMMARY 2026.xlsx',
    status: 'previewed',
    job_status: 'completed',
    uploaded_by: 'ZZT Importer',
    uploaded_by_id: USER_ID,
    uploaded_at: '2026-11-12T09:30:00',
    rows: 1398,
    created: 0,
    skipped: 468,
    to_review: 930,
    imported_at: null,
  },
];

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProjectImportListClient />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  perms.set = new Set(['projects.import.view', 'projects.import.run']);
  nav.search = '';
  service.listRuns.mockResolvedValue({ data: runs, total: 1 });
});

describe('ProjectImportListClient', () => {
  it('has one toolbar CTA named exactly "Create"', async () => {
    renderList();
    await screen.findByText('PIM-0001');
    const create = screen.getAllByRole('button', { name: /^Create$/ });
    expect(create).toHaveLength(1);
  });

  it('shows run no., file name and the upload date as dd/mm/yyyy', async () => {
    renderList();
    expect(await screen.findByText('PIM-0001')).toBeInTheDocument();
    expect(screen.getByText('TOTAL SALES ORDER SUMMARY 2026.xlsx')).toBeInTheDocument();
    expect(screen.getByText(/12\/11\/2026/)).toBeInTheDocument();
    expect(screen.getByText('ZZT Importer')).toBeInTheDocument();
  });

  it('reads runs from the service with DataGrid params', async () => {
    renderList();
    await screen.findByText('PIM-0001');
    expect(service.listRuns).toHaveBeenCalled();
    const [grid] = service.listRuns.mock.calls[0];
    expect(grid).toMatchObject({ pageIndex: 0 });
    expect(typeof grid.pageSize).toBe('number');
  });

  it('opens the run on a row click', async () => {
    renderList();
    fireEvent.click(await screen.findByText('PIM-0001'));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(String(push.mock.calls[0][0])).toContain(`/project-sales/import/${RUN_ID}`);
  });

  it('renders no UUID', async () => {
    const { container } = renderList();
    await screen.findByText('PIM-0001');
    expect(container.textContent ?? '').not.toMatch(UUID_RE);
  });
});

describe('ProjectImportListClient, round 5', () => {
  it('r5: a view-only user sees no Create (REV-M4)', async () => {
    perms.set = new Set(['projects.import.view']);
    renderList();
    await screen.findByText('PIM-0001');
    expect(screen.queryAllByRole('button', { name: /^Create$/ })).toHaveLength(0);
  });

  it('r5: the list restores search, filter, sort and page from the URL (REV-M2)', async () => {
    nav.search = 'page=2&limit=25&sort=filename&dir=asc&query=SUMMARY&status=imported';
    renderList();
    await waitFor(() =>
      expect(
        service.listRuns.mock.calls.some(([grid, filters]) => {
          const sort = grid?.sorting?.[0];
          return (
            grid?.pageIndex === 1 &&
            sort?.id === 'filename' &&
            sort?.desc === false &&
            grid?.searchQuery === 'SUMMARY' &&
            JSON.stringify(filters ?? {}).includes('imported')
          );
        })
      ).toBe(true)
    );
  });

  it('r5: a row opened from a filtered, sorted list carries that state to the run (REV-M2)', async () => {
    nav.search = 'page=1&limit=25&sort=filename&dir=asc&query=SUMMARY&status=imported';
    renderList();
    fireEvent.click(await screen.findByText('PIM-0001'));
    await waitFor(() => expect(push).toHaveBeenCalled());
    const href = String(push.mock.calls[0][0]);
    expect(href).toContain(`/project-sales/import/${RUN_ID}`);
    const params = new URLSearchParams(href.split('?')[1] ?? '');
    expect(params.get('sort')).toBe('filename');
    expect(params.get('query')).toBe('SUMMARY');
    expect(params.get('status')).toContain('imported');
  });
});
