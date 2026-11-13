/**
 * AC-PI-45 / AC-PI-48 (RED): the run page picks its step from the run's status.
 *
 * Assumed (the coder matches these):
 *   `ProjectImportRunClient` (named export) from './ProjectImportRunClient', props:
 *     runId: string
 *   It reads the run through `getRun(runId)` (GET /runs/{id}) and shows:
 *     draft with missing_columns.length > 0 -> `ColumnsStep`   ('./ColumnsStep')
 *     draft with no missing columns         -> `ValuesStep`    ('./ValuesStep')
 *     previewed                             -> `PreviewStep`   ('./PreviewStep')
 *     importing / imported / reverted       -> `ResultsView`   ('./ResultsView', real here),
 *   whose tabs are Results | Values | History (`AuditTrail`), and an imported run offers
 *   Revert through `DeferredActionButton` (verb "Revert", pending action
 *   `project_import_run.revert`). The step components are mocked to markers here; the
 *   shared cards, AuditTrail and DeferredActionButton are mocked at their modules.
 *   The header shows the run number; no UUID is rendered.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
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
  usePathname: () => '/project-sales/import/run-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
  useParams: () => ({}),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ data: [], items: [], total: 0 }),
  })),
}));

const service = vi.hoisted(() => ({
  getRun: vi.fn(),
  getLinesSummary: vi.fn(),
  listLines: vi.fn(),
  listRows: vi.fn(),
  listRuns: vi.fn(),
}));
vi.mock('../../../_shared/services/projectImportService', () => service);

vi.mock('./ColumnsStep', () => {
  const C = () => <div data-testid="step-columns" />;
  return { ColumnsStep: C, default: C };
});
vi.mock('./ValuesStep', () => {
  const C = () => <div data-testid="step-values" />;
  return { ValuesStep: C, default: C };
});
vi.mock('./PreviewStep', () => {
  const C = () => <div data-testid="step-preview" />;
  return { PreviewStep: C, default: C };
});

const deferred = vi.hoisted(() => ({ props: [] as Record<string, unknown>[] }));
vi.mock('@/components/common/DeferredActionButton', () => {
  const D = (p: Record<string, unknown>) => {
    deferred.props.push(p);
    return <div data-testid="deferred-action">{(p.idle as React.ReactNode) ?? null}</div>;
  };
  return { default: D, DeferredCountdown: () => null };
});
vi.mock('@/components/audit/AuditTrail', () => ({
  default: (p: { entityType?: string }) => <div data-testid="audit-trail">{p.entityType}</div>,
}));
vi.mock('@/app/(protected)/system-management/import-jobs/components/OutcomeBreakdownCard', () => {
  const C = () => <div data-testid="outcome-breakdown" />;
  return { OutcomeBreakdownCard: C, default: C };
});
vi.mock('@/app/(protected)/system-management/import-jobs/components/ImportJobRowsCard', () => {
  const C = () => <div data-testid="import-job-rows" />;
  return { ImportJobRowsCard: C, default: C };
});

import { ProjectImportRunClient } from './ProjectImportRunClient';

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const RUN_ID = '0b5c3a52-6a8e-4f6e-9f43-6a1f2f8e1c11';

function run(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: RUN_ID,
    run_no: 'PIM-0003',
    filename: 'SO SUMMARY 2026.xlsx',
    status,
    job_status: 'completed',
    uploaded_by: 'ZZT Importer',
    uploaded_by_id: '7d2a9f4e-1c3b-4e8d-a5f6-2b9c8d7e6f50',
    uploaded_at: '2026-11-12T09:30:00',
    rows: 10,
    created: status === 'imported' ? 4 : 0,
    skipped: 3,
    to_review: 3,
    sheets: [],
    columns: {},
    missing_columns: [],
    preview_counts: { created: 4, skipped: 3, needs_review: 3 },
    preview_codes: {},
    result_counts: status === 'imported' ? { created: 4, skipped: 3, needs_review: 3 } : null,
    result_codes: status === 'imported' ? { project_and_po_created: 4 } : null,
    sheet_errors: [],
    imported_at: status === 'imported' ? '2026-11-12T10:00:00' : null,
    ...extra,
  };
}

function renderRun() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProjectImportRunClient runId={RUN_ID} />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  perms.set = new Set(['projects.import.view', 'projects.import.run']);
  nav.search = '';
  deferred.props = [];
  service.getLinesSummary.mockResolvedValue({
    customer: { total: 0, todo: 0 },
    project: { total: 0, todo: 0 },
    developer: { total: 0, todo: 0 },
    person: { total: 0, todo: 0 },
  });
  service.listLines.mockResolvedValue({ items: [], total: 0 });
  service.listRows.mockResolvedValue({ data: [], total: 0 });
});

describe('ProjectImportRunClient', () => {
  it('a draft with a required column missing opens on Columns', async () => {
    service.getRun.mockResolvedValue(run('draft', { missing_columns: ['customer'] }));
    renderRun();
    expect(await screen.findByTestId('step-columns')).toBeInTheDocument();
    expect(screen.queryByTestId('step-values')).toBeNull();
    expect(screen.queryByTestId('step-preview')).toBeNull();
    expect(service.getRun).toHaveBeenCalledWith(RUN_ID);
  });

  it('a draft with every required column opens on Values', async () => {
    service.getRun.mockResolvedValue(run('draft'));
    renderRun();
    expect(await screen.findByTestId('step-values')).toBeInTheDocument();
    expect(screen.queryByTestId('step-columns')).toBeNull();
  });

  it('a previewed run opens on Preview', async () => {
    service.getRun.mockResolvedValue(run('previewed'));
    renderRun();
    expect(await screen.findByTestId('step-preview')).toBeInTheDocument();
    expect(screen.queryByTestId('step-values')).toBeNull();
  });

  it('an imported run shows Results with a History tab and Revert as a deferred action', async () => {
    service.getRun.mockResolvedValue(run('imported'));
    renderRun();
    expect(await screen.findByText(/^Results$/)).toBeInTheDocument();
    expect(screen.getByText(/^History$/)).toBeInTheDocument();
    expect(screen.queryByTestId('step-preview')).toBeNull();
    expect(screen.queryByTestId('step-columns')).toBeNull();
    expect(deferred.props.length).toBeGreaterThan(0);
    expect(deferred.props.some((p) => /revert/i.test(String(p.verb ?? '')))).toBe(true);
  });

  it.each(['importing', 'reverted'])('a %s run shows Results, not a step', async (status) => {
    service.getRun.mockResolvedValue(run(status));
    renderRun();
    expect(await screen.findByText(/^Results$/)).toBeInTheDocument();
    expect(screen.queryByTestId('step-columns')).toBeNull();
    expect(screen.queryByTestId('step-values')).toBeNull();
    expect(screen.queryByTestId('step-preview')).toBeNull();
  });

  it('shows the run number in the header and no UUID anywhere', async () => {
    service.getRun.mockResolvedValue(run('previewed'));
    const { container } = renderRun();
    expect((await screen.findAllByText('PIM-0003')).length).toBeGreaterThan(0);
    expect(container.textContent ?? '').not.toMatch(UUID_RE);
  });
});

function headerRoot(): HTMLElement {
  // PageHeader: the breadcrumb trail and the actions share one toolbar root.
  const crumb = screen.getAllByText('Project import').find((el) => el.closest('nav'))!;
  let el: HTMLElement | null = crumb.closest('nav');
  while (el && !el.querySelector('button')) el = el.parentElement;
  return el!;
}

describe('ProjectImportRunClient, round 5', () => {
  it.each([
    ['draft', {}],
    ['draft', { missing_columns: ['customer'] }],
    ['previewed', {}],
    ['imported', {}],
  ])('r5: the History tab is there on a %s run (REV-M3)', async (status, extra) => {
    service.getRun.mockResolvedValue(run(status, extra));
    renderRun();
    expect(await screen.findByText(/^History$/)).toBeInTheDocument();
  });

  it('r5: a view-only user gets no Preview, Import or Revert (REV-M4)', async () => {
    perms.set = new Set(['projects.import.view']);
    for (const status of ['draft', 'previewed', 'imported']) {
      deferred.props = [];
      service.getRun.mockResolvedValue(run(status));
      const view = renderRun();
      await screen.findAllByText('PIM-0003');
      // The header holds the page's actions (the step switcher's own "Preview" tab is not one).
      const header = headerRoot();
      expect(within(header).queryAllByRole('button', { name: /^Preview$/ })).toHaveLength(0);
      expect(within(header).queryAllByRole('button', { name: /^Import$/ })).toHaveLength(0);
      expect(screen.queryAllByRole('button', { name: /^Import$/ })).toHaveLength(0);
      expect(screen.queryByText(/^Revert$/)).toBeNull();
      expect(deferred.props.some((p) => /revert/i.test(String(p.verb ?? '')))).toBe(false);
      view.unmount();
    }
  });

  it('r5: with the run permission the Preview and Import buttons are there', async () => {
    service.getRun.mockResolvedValue(run('draft'));
    const first = renderRun();
    await screen.findAllByText('PIM-0003');
    expect(within(headerRoot()).getByRole('button', { name: /^Preview$/ })).toBeInTheDocument();
    first.unmount();
    service.getRun.mockResolvedValue(run('previewed'));
    renderRun();
    await screen.findAllByText('PIM-0003');
    expect(within(headerRoot()).getByRole('button', { name: /^Import$/ })).toBeInTheDocument();
  });

  it('r5: on Preview the Import button sits in the page header (REV-minor11)', async () => {
    service.getRun.mockResolvedValue(run('previewed'));
    renderRun();
    await screen.findAllByText('PIM-0003');
    const header = headerRoot();
    expect(within(header).getByRole('button', { name: /^Import$/ })).toBeInTheDocument();
  });

  it('r5: the file name is in the page header (REV-minor11)', async () => {
    service.getRun.mockResolvedValue(run('previewed'));
    renderRun();
    await screen.findAllByText('PIM-0003');
    expect(headerRoot().textContent).toContain('SO SUMMARY 2026.xlsx');
  });

  it('r5: prev/next follows the list filters and sort carried in the URL (REV-M2)', async () => {
    nav.search = `page=1&limit=25&sort=filename&dir=asc&query=SUMMARY&status=imported&from=${RUN_ID}`;
    service.getRun.mockResolvedValue(run('previewed'));
    service.listRuns.mockResolvedValue({ data: [run('previewed')], total: 1 });
    renderRun();
    await screen.findAllByText('PIM-0003');
    await waitFor(() =>
      expect(
        service.listRuns.mock.calls.some(([grid, filters]) => {
          const sort = grid?.sorting?.[0];
          return (
            sort?.id === 'filename' &&
            sort?.desc === false &&
            grid?.searchQuery === 'SUMMARY' &&
            JSON.stringify(filters ?? {}).includes('imported')
          );
        })
      ).toBe(true)
    );
  });
});
