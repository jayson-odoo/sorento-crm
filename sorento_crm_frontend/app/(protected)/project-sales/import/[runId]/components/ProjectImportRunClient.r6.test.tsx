/**
 * Round 6 (RED): browser pass 1 defects on the run page.
 *
 * D1  Columns > Next with an already complete mapping saves AND moves to Values.
 * D2  the Columns step has exactly one primary button, Next (the header's Preview is not
 *     primary there).
 * D4  a needs-review row opens Values on its blocking kind AND that line: PreviewStep calls
 *     `onOpenLine(kind, blocking_line)`; the run page passes `focusLine={blocking_line}` to
 *     `ValuesStep`.
 * D7  the revert's pending action refreshes the History: `useDeferredAction` is given an
 *     invalidate key for the run's audit logs (`['audit-logs', 'project_import_run', runId]`,
 *     the key `hooks/useAuditLogs.ts` reads, or its `['audit-logs']` prefix).
 *
 * The real ColumnsStep runs here (service mocked); ValuesStep and PreviewStep are markers
 * that record their props.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

const perms = vi.hoisted(() => ({
  set: new Set<string>(['projects.import.view', 'projects.import.run']),
}));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: [...perms.set], permissionSet: perms.set, isLoading: false,
    isError: false, isFetching: false, error: null, refetch: () => {} }),
  useHasPermission: (slug: string) => perms.set.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => perms.set.has(s)),
  PERMISSIONS_QUERY_KEY: ['my-permissions'],
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/import/run-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
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
  saveColumns: vi.fn(),
  getLinesSummary: vi.fn(),
  listLines: vi.fn(),
  listRows: vi.fn(),
  listRuns: vi.fn(),
  previewRun: vi.fn(),
  startImport: vi.fn(),
}));
vi.mock('../../../_shared/services/projectImportService', () => service);

const seen = vi.hoisted(() => ({ values: [] as Record<string, unknown>[], deferred: [] as Record<string, unknown>[] }));
const LINE = { kind: 'customer', customer_value_key: '', value_key: 'CUSTOMER 013 SDN BHD' };
vi.mock('./ValuesStep', () => {
  const C = (p: Record<string, unknown>) => {
    seen.values.push(p);
    return <div data-testid="step-values" />;
  };
  return { ValuesStep: C, default: C };
});
vi.mock('./PreviewStep', () => {
  const C = (p: { onOpenLine: (kind: string, line?: unknown) => void }) => (
    <div data-testid="step-preview">
      <button type="button" onClick={() => p.onOpenLine('customer', LINE)}>
        open blocking line
      </button>
    </div>
  );
  return { PreviewStep: C, default: C };
});
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (options: Record<string, unknown>) => {
    seen.deferred.push(options);
    return { pending: null, start: vi.fn(), cancel: vi.fn(), isBlocked: false };
  },
}));
// The History reads through react-query under the key `hooks/useAuditLogs.ts` uses, so a test
// can see whether the page refreshes it (round 10).
const history = vi.hoisted(() => ({ fetch: vi.fn(async () => [] as string[]) }));
vi.mock('@/components/audit/AuditTrail', async () => {
  const { useQuery } = await vi.importActual<typeof import('@tanstack/react-query')>(
    '@tanstack/react-query'
  );
  const Trail = ({ entityType, entityId }: { entityType: string; entityId: string }) => {
    const { data } = useQuery({
      queryKey: ['audit-logs', entityType, entityId, 1, 50],
      queryFn: () => history.fetch(),
      staleTime: 60 * 1000,
    });
    return <div data-testid="audit-trail">{(data ?? []).join(' | ')}</div>;
  };
  return { default: Trail };
});

import { ProjectImportRunClient } from './ProjectImportRunClient';

const RUN_ID = '0b5c3a52-6a8e-4f6e-9f43-6a1f2f8e1c11';
const FIELDS = [
  'ps_number', 'salesperson', 'customer_service', 'customer', 'project_name', 'developer',
  'po_number', 'po_value', 'po_date', 'amended_date', 'schedule', 'delivery', 'outstanding',
  'so_number', 'remarks',
];

function run(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: RUN_ID,
    run_no: 'PIM-0006',
    filename: 'SO SUMMARY 2026.xlsx',
    status,
    job_status: 'pending',
    uploaded_by: 'ZZT Importer',
    uploaded_at: '2026-11-12T09:30:00',
    rows: 2,
    created: 0,
    skipped: 0,
    to_review: 0,
    columns: { ps_number: 'RUNNING \nPS NUMBER', customer: 'CUSTOMER ', po_number: 'PO \nNUMBER' },
    missing_columns: [],
    field_labels: Object.fromEntries(FIELDS.map((f) => [f, f.replace(/_/g, ' ')])),
    sheets: [
      {
        name: "JAN'26",
        name_trimmed: "JAN'26",
        has_ps_heading: true,
        row_count: 2,
        ticked: true,
        columns: [
          { position: 1, header: 'RUNNING \nPS NUMBER', sample: 'PS26-0001', field: 'ps_number' },
          { position: 2, header: 'CUSTOMER ', sample: 'CUSTOMER 001 SDN BHD', field: 'customer' },
          { position: 3, header: 'PO \nNUMBER', sample: 'PO-1', field: 'po_number' },
        ],
      },
    ],
    preview_counts: status === 'previewed' ? { created: 1, needs_review: 1 } : null,
    preview_codes: {},
    code_labels: {},
    result_counts: null,
    result_codes: null,
    sheet_errors: [],
    imported_at: null,
    ...extra,
  };
}

let lastClient: QueryClient;

function renderRun() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  lastClient = client;
  return render(
    <QueryClientProvider client={client}>
      <ProjectImportRunClient runId={RUN_ID} />
    </QueryClientProvider>
  );
}

function primaries(container: HTMLElement) {
  return Array.from(container.querySelectorAll('button')).filter((b) =>
    /(^|\s)bg-primary(\s|$)/.test(b.className)
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  seen.values = [];
  seen.deferred = [];
  perms.set = new Set(['projects.import.view', 'projects.import.run']);
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 });
  service.saveColumns.mockResolvedValue({});
  service.getLinesSummary.mockResolvedValue({});
  service.listLines.mockResolvedValue({ items: [], total: 0 });
  service.listRows.mockResolvedValue({ data: [], total: 0 });
  service.listRuns.mockResolvedValue({ data: [], total: 0 });
});

describe('ProjectImportRunClient, round 6', () => {
  it('r6: D1 Next on a complete mapping saves and moves to Values', async () => {
    const user = userEvent.setup();
    service.getRun.mockResolvedValue(run('draft'));
    renderRun();
    await user.click(await screen.findByRole('tab', { name: /^Columns$/ }));
    expect(screen.queryByTestId('step-values')).toBeNull();

    await user.click(await screen.findByRole('button', { name: /^Next$/ }));

    await waitFor(() => expect(service.saveColumns).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId('step-values')).toBeInTheDocument();
  });

  it('r6: D2 the Columns step has exactly one primary button, Next', async () => {
    const user = userEvent.setup();
    service.getRun.mockResolvedValue(run('draft'));
    const { container } = renderRun();
    await user.click(await screen.findByRole('tab', { name: /^Columns$/ }));
    await screen.findByRole('button', { name: /^Next$/ });

    const main = primaries(container);
    expect(main).toHaveLength(1);
    expect(main[0].textContent?.trim()).toBe('Next');
  });

  it('r6: D4 a needs-review row opens Values on that kind with the blocking line', async () => {
    const user = userEvent.setup();
    service.getRun.mockResolvedValue(run('previewed'));
    renderRun();
    await user.click(await screen.findByRole('button', { name: /open blocking line/ }));

    expect(await screen.findByTestId('step-values')).toBeInTheDocument();
    const last = seen.values.at(-1)!;
    expect(last.kind).toBe('customer');
    expect(last.focusLine).toEqual(LINE);
  });

  it('r6: D7 the revert invalidates the run History when it lands', async () => {
    service.getRun.mockResolvedValue(run('imported', {
      result_counts: { created: 1 }, imported_at: '2026-11-12T10:00:00' }));
    renderRun();
    await screen.findAllByText('PIM-0006');
    await waitFor(() => expect(seen.deferred.length).toBeGreaterThan(0));

    const revert = seen.deferred.find((o) => o.actionKey === 'project_import_run.revert')!;
    expect(revert).toBeTruthy();
    const keys = (revert.invalidateKeys ?? []) as unknown[][];
    expect(
      keys.some((k) => k[0] === 'audit-logs' && (k.length === 1 || k[1] === 'project_import_run'))
    ).toBe(true);
  });
});

describe('ProjectImportRunClient, round 9', () => {
  it.each([1280, 375])(
    'r9: a previewed run shows exactly one main button on every tab at %ipx',
    async (width) => {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
      window.dispatchEvent(new Event('resize'));
      const user = userEvent.setup();
      service.getRun.mockResolvedValue(run('previewed'));
      const { container } = renderRun();
      await screen.findAllByText('PIM-0006');
      for (const tab of ['Columns', 'Values', 'Preview', 'History']) {
        await user.click(await screen.findByRole('tab', { name: new RegExp(`^${tab}$`) }));
        await waitFor(() => expect(primaries(container), tab).toHaveLength(1));
      }
      // On Values the one main button is Preview.
      await user.click(screen.getByRole('tab', { name: /^Values$/ }));
      await waitFor(() => expect(primaries(container)[0]?.textContent?.trim()).toBe('Preview'));
    }
  );

  it.each(['draft', 'previewed', 'reverted'])(
    'r9: a %s run offers Delete as a deferred action',
    async (status) => {
      service.getRun.mockResolvedValue(run(status));
      renderRun();
      await screen.findAllByText('PIM-0006');
      await waitFor(() =>
        expect(seen.deferred.some((o) => o.actionKey === 'project_import_run.delete' && o.entityId))
          .toBe(true)
      );
      const del = seen.deferred.filter((o) => o.actionKey === 'project_import_run.delete').at(-1)!;
      expect(del.entityType).toBe('project_import_run');
    }
  );

  it('r9: an imported run offers no Delete (revert it first)', async () => {
    service.getRun.mockResolvedValue(run('imported', { result_counts: { created: 1 } }));
    renderRun();
    await screen.findAllByText('PIM-0006');
    await waitFor(() => expect(seen.deferred.length).toBeGreaterThan(0));
    expect(seen.deferred.some((o) => o.actionKey === 'project_import_run.delete' && o.entityId))
      .toBe(false);
  });

  it('r9: without projects.import.run there is no Delete', async () => {
    perms.set = new Set(['projects.import.view']);
    service.getRun.mockResolvedValue(run('draft'));
    renderRun();
    await screen.findAllByText('PIM-0006');
    expect(seen.deferred.some((o) => o.actionKey === 'project_import_run.delete' && o.entityId))
      .toBe(false);
    expect(screen.queryByText(/^Delete$/)).toBeNull();
  });
});

describe('ProjectImportRunClient, round 10', () => {
  it('r10: History refreshes when the import finishes', async () => {
    const user = userEvent.setup();
    history.fetch.mockResolvedValueOnce(['Previewed']);
    history.fetch.mockResolvedValue(['Previewed', 'Imported']);
    service.getRun.mockResolvedValue(run('importing'));
    renderRun();
    await screen.findAllByText('PIM-0006');
    await user.click(await screen.findByRole('tab', { name: /^History$/ }));
    const trail = await screen.findByTestId('audit-trail');
    await waitFor(() => expect(trail.textContent).toBe('Previewed'));
    const before = history.fetch.mock.calls.length;

    // The run poll comes back imported (what the 2 s refetchInterval does while importing).
    service.getRun.mockResolvedValue(run('imported', {
      result_counts: { created: 1 }, imported_at: '2026-11-12T10:00:00' }));
    await lastClient.refetchQueries({
      predicate: (q) => !String(q.queryKey[0]).startsWith('audit-logs') &&
        JSON.stringify(q.queryKey).includes(RUN_ID),
    });

    await waitFor(() => expect(history.fetch.mock.calls.length).toBeGreaterThan(before));
    await waitFor(() =>
      expect(screen.getByTestId('audit-trail').textContent).toContain('Imported'));
  });
});
